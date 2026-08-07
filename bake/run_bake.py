"""Stage C — the bake (SPEC §9).

Single process, one pass over every parcel. Every parcel produces at least one
`bake_results` row: either one row per admissible prototype (`status='scored'`) or a single
status row carrying the reason it was not scored. No parcel silently vanishes.

Each run APPENDS a batch keyed by its `computed_at`; batches older than the last `keep`
(default 2) are deleted afterwards. The tie-margin incumbent is read from the previous
batch BEFORE the new one is written.

This module is orchestration only: all SQL lives in `data/repositories.py`, all arithmetic
lives in the pure `engine/`.
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from data import repositories as repo
from data.loaders.seed_market import (
    AS_OF as FALLBACK_AS_OF,
    FALLBACK_COST_PSF,
    FALLBACK_EXIT_CAP,
    FALLBACK_RENT_PSF_MONTHLY,
    FALLBACK_RETAIL_RENT_PSF_ANNUAL,
    SOURCE_TAG as FALLBACK_SOURCE,
)
from engine.assumptions import DEFAULT_ASSUMPTIONS, PROVENANCE
from engine.confidence import score_confidence
from engine.envelope import resolve_envelope
from engine.proforma import screening_rlv
from engine.program import fit_program
from engine.types import (
    Assumptions,
    ConstructionType,
    MarketData,
    NotPermitted,
    Parcel,
    Prototype,
    Use,
    ZoningRules,
)

NONE_PROTOTYPE = repo.NONE_PROTOTYPE
TIE_MARGIN = 0.05

# The bake always underwrites residential clean-site potential (SPEC §3.4: demolition is a
# drill-down-only toggle, and `include_demolition` is already False in DEFAULT_ASSUMPTIONS).
BAKE_USE = Use.RESIDENTIAL

STATUS_SCORED = "scored"
STATUS_INFEASIBLE = "infeasible"
STATUS_ZONE_NOT_ENCODED = "zone_not_encoded"
STATUS_EXEMPT = "exempt"
STATUS_HISTORIC = "historic"

REASON_EXEMPT = "public/exempt ownership"
REASON_HISTORIC = "historic district — redevelopment restricted"
REASON_INFEASIBLE = "no admissible prototype under zoning envelope"

ALL_STATUSES = (
    STATUS_SCORED,
    STATUS_INFEASIBLE,
    STATUS_ZONE_NOT_ENCODED,
    STATUS_EXEMPT,
    STATUS_HISTORIC,
)


# ---------------------------------------------------------------------------
# market fallback
# ---------------------------------------------------------------------------
def national_fallback_market(submarket_id: str | None) -> MarketData:
    """SPEC §7.2: until a submarket is seeded, fall back to the §2 national defaults.

    Reuses the constants `data/loaders/seed_market.py` already authors from SPEC §2.4/§2.6/§5,
    so the fallback and the seed can never drift apart. Provenance (and therefore confidence)
    is unaffected — `score_confidence` reads PROVENANCE, never these values.
    """
    return MarketData(
        submarket_id=submarket_id or "",
        rent_psf_residential_monthly=FALLBACK_RENT_PSF_MONTHLY,
        retail_rent_psf_annual=FALLBACK_RETAIL_RENT_PSF_ANNUAL,
        exit_cap_rate=FALLBACK_EXIT_CAP,
        hard_cost_psf={ConstructionType(k): v for k, v in FALLBACK_COST_PSF.items()},
        as_of=FALLBACK_AS_OF,
        source=FALLBACK_SOURCE,
    )


# ---------------------------------------------------------------------------
# per-parcel evaluation
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Candidate:
    """One admissible prototype's screening result for one parcel."""

    prototype_id: str
    screening_rlv: float
    feasibility_gap: float | None
    confidence: float
    binding_constraint: str
    gross_sf: float
    objective: float   # RLV per buildable SF — the ONE pinned is_best objective (§3.4, §9)


def evaluate_parcel(
    parcel: Parcel,
    rules: ZoningRules,
    market: MarketData,
    prototypes: list[Prototype],
    assumptions: Assumptions = DEFAULT_ASSUMPTIONS,
) -> list[Candidate]:
    """Run every prototype through the pure engine. Prototypes that don't fit are skipped."""
    # `resolve_envelope` takes no prototype, so it is loop-invariant across the prototype
    # set: hoisted out of the loop, identical result, one call instead of four.
    envelope = resolve_envelope(parcel, rules, BAKE_USE, assumptions)

    candidates: list[Candidate] = []
    for proto in prototypes:
        try:
            program = fit_program(envelope, proto, rules, BAKE_USE, assumptions, parcel)
            out = screening_rlv(program, market, assumptions, parcel)
        except NotPermitted:
            continue          # this prototype doesn't fit; try the next
        out.confidence = score_confidence(PROVENANCE, market)

        if program.gross_sf <= 0:
            continue          # nothing buildable — the objective would be undefined
        candidates.append(
            Candidate(
                prototype_id=proto.prototype_id,
                screening_rlv=out.screening_rlv,
                feasibility_gap=out.feasibility_gap,
                confidence=out.confidence,
                binding_constraint=envelope.binding_constraint,
                gross_sf=program.gross_sf,
                objective=out.screening_rlv / program.gross_sf,
            )
        )
    return candidates


def select_best_with_tie_margin(
    candidates: list[Candidate],
    prior_best_prototype_id: str | None,
    margin: float = TIE_MARGIN,
) -> Candidate:
    """Pick the `is_best` row on RLV-per-buildable-SF, with hysteresis vs. the prior batch.

    The incumbent (last bake's best prototype for this parcel) keeps the flag unless a
    challenger beats it by more than `margin` — this stops the recommended program flipping
    month-to-month on input noise (SPEC §9).

    The band is `margin * abs(incumbent)` rather than `margin * incumbent`: screening RLV is
    frequently negative at v1 defaults, and a signed band would sit on the wrong side of the
    incumbent there, handing the flag to any challenger. `abs` keeps "beat it by 5%" meaning
    the same thing in both signs. On the first-ever bake there is no incumbent and this is a
    plain argmax.

    Ties resolve to the earliest candidate, and `prototypes` arrives in a stable sort order,
    so the choice is deterministic.
    """
    challenger = max(candidates, key=lambda c: c.objective)
    if prior_best_prototype_id is None:
        return challenger

    incumbent = next(
        (c for c in candidates if c.prototype_id == prior_best_prototype_id), None
    )
    if incumbent is None or incumbent is challenger:
        return challenger      # incumbent is no longer admissible, or already won

    if challenger.objective > incumbent.objective + margin * abs(incumbent.objective):
        return challenger
    return incumbent


# ---------------------------------------------------------------------------
# row construction
# ---------------------------------------------------------------------------
def _status_row(parcel: Parcel, status: str, reason: str | None, computed_at: datetime) -> dict:
    return {
        "ssl": parcel.ssl,
        "prototype_id": NONE_PROTOTYPE,
        "is_best": True,
        "status": status,
        "screening_rlv": None,
        "feasibility_gap": None,
        "confidence": None,
        "binding_constraint": reason,
        "computed_at": computed_at,
    }


def rows_for_parcel(
    parcel: Parcel,
    rules_by_zone: dict[str, ZoningRules],
    markets: dict[str, MarketData],
    prototypes: list[Prototype],
    prior_best: dict[str, str],
    computed_at: datetime,
    assumptions: Assumptions = DEFAULT_ASSUMPTIONS,
) -> list[dict]:
    """The SPEC §9 loop body for a single parcel. Always returns at least one row."""
    # --- v1.2 pre-filters: represented, never scored ---
    if parcel.is_exempt:
        return [_status_row(parcel, STATUS_EXEMPT, REASON_EXEMPT, computed_at)]
    if parcel.is_historic:
        return [_status_row(parcel, STATUS_HISTORIC, REASON_HISTORIC, computed_at)]

    rules = rules_by_zone.get(parcel.zone_code) if parcel.zone_code else None
    if rules is None:
        # fix #1: an unencoded district is represented with its zone code as the reason,
        # not a crash. Coverage grows as §8 is extended; no rework here.
        return [_status_row(parcel, STATUS_ZONE_NOT_ENCODED, parcel.zone_code, computed_at)]

    market = markets.get(parcel.submarket_id) or national_fallback_market(parcel.submarket_id)
    candidates = evaluate_parcel(parcel, rules, market, prototypes, assumptions)

    if not candidates:
        # fix #5: no prototype admissible anywhere in this envelope.
        return [_status_row(parcel, STATUS_INFEASIBLE, REASON_INFEASIBLE, computed_at)]

    best = select_best_with_tie_margin(candidates, prior_best.get(parcel.ssl))
    return [
        {
            "ssl": parcel.ssl,
            "prototype_id": c.prototype_id,
            "is_best": c is best,
            "status": STATUS_SCORED,
            "screening_rlv": c.screening_rlv,
            "feasibility_gap": c.feasibility_gap,
            "confidence": c.confidence,
            "binding_constraint": c.binding_constraint,
            "computed_at": computed_at,
        }
        for c in candidates
    ]


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------
@dataclass
class BakeStats:
    computed_at: datetime
    parcels: int = 0
    rows: int = 0
    status_counts: dict[str, int] = field(default_factory=lambda: {s: 0 for s in ALL_STATUSES})
    prototype_counts: dict[str, int] = field(default_factory=dict)
    prior_batch: datetime | None = None
    pruned_rows: int = 0
    seconds: float = 0.0

    @property
    def scored_parcels(self) -> int:
        return self.status_counts[STATUS_SCORED]


def run_bake(
    conn,
    computed_at: datetime | None = None,
    keep_batches: int = 2,
    flush_every: int = 20_000,
    progress_every: int = 20_000,
    log=lambda msg: print(msg, file=sys.stderr, flush=True),
) -> BakeStats:
    started = time.perf_counter()
    computed_at = computed_at or datetime.now(timezone.utc)

    rules_by_zone = repo.get_all_rules(conn)
    markets = repo.get_all_markets(conn)
    prototypes = repo.get_prototypes(conn)

    # The incumbent for the tie margin comes from the previous batch, read BEFORE the new
    # batch is written (SPEC §9 batch retention).
    prior_batch = repo.latest_batch_at(conn)
    prior_best = repo.best_prototypes_at(conn, prior_batch) if prior_batch else {}

    stats = BakeStats(computed_at=computed_at, prior_batch=prior_batch)
    log(
        f"bake {computed_at.isoformat()} — {len(rules_by_zone)} encoded districts, "
        f"{len(markets)} submarkets, {len(prototypes)} prototypes, "
        f"{len(prior_best):,} incumbents from {prior_batch.isoformat() if prior_batch else 'no prior batch'}"
    )

    pending: list[dict] = []
    for parcel in repo.iter_parcels(conn):
        rows = rows_for_parcel(
            parcel, rules_by_zone, markets, prototypes, prior_best, computed_at
        )
        stats.parcels += 1
        stats.rows += len(rows)
        stats.status_counts[rows[0]["status"]] += 1
        for row in rows:
            if row["is_best"] and row["status"] == STATUS_SCORED:
                stats.prototype_counts[row["prototype_id"]] = (
                    stats.prototype_counts.get(row["prototype_id"], 0) + 1
                )
        pending.extend(rows)

        if len(pending) >= flush_every:
            repo.write_bake_results(conn, pending)
            pending.clear()
        if progress_every and stats.parcels % progress_every == 0:
            log(f"  {stats.parcels:,} parcels — {stats.rows:,} rows — {time.perf_counter()-started:,.0f}s")

    repo.write_bake_results(conn, pending)
    conn.commit()

    stats.pruned_rows = repo.prune_bake_batches(conn, keep=keep_batches)
    conn.commit()

    stats.seconds = time.perf_counter() - started
    return stats


def format_report(stats: BakeStats) -> str:
    lines = [
        "",
        "=" * 68,
        f"BAKE COMPLETE  {stats.computed_at.isoformat()}",
        "=" * 68,
        f"runtime        {stats.seconds:,.1f}s",
        f"parcels        {stats.parcels:,}",
        f"rows written   {stats.rows:,}",
        f"rows pruned    {stats.pruned_rows:,} (batch retention: last 2)",
        "",
        "status breakdown (one status per parcel):",
    ]
    for status in ALL_STATUSES:
        n = stats.status_counts[status]
        pct = (100.0 * n / stats.parcels) if stats.parcels else 0.0
        lines.append(f"  {status:<20} {n:>9,}  {pct:5.1f}%")
    if stats.prototype_counts:
        lines += ["", "best prototype among scored parcels:"]
        for proto, n in sorted(stats.prototype_counts.items(), key=lambda kv: -kv[1]):
            pct = 100.0 * n / stats.scored_parcels
            lines.append(f"  {proto:<20} {n:>9,}  {pct:5.1f}%")
    lines.append("=" * 68)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Stage C — bake screening RLV for every parcel.")
    ap.add_argument("--keep", type=int, default=2, help="batches to retain (SPEC §9: 2)")
    ap.add_argument("--flush-every", type=int, default=20_000, help="rows per insert flush")
    ap.add_argument("--quiet", action="store_true", help="suppress progress lines")
    args = ap.parse_args(argv)

    def log(msg: str) -> None:
        if not args.quiet:
            print(msg, file=sys.stderr, flush=True)

    with repo.connection() as conn:
        stats = run_bake(
            conn, keep_batches=args.keep, flush_every=args.flush_every, log=log
        )
    print(format_report(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
