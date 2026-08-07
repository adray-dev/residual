"""The full-tier service: the ONE place the engine runs live (SPEC §10).

Everything else in the API reads `bake_results`. This module resolves a parcel's inputs,
runs `full_cashflow` / `solve_irr_rlv`, and caches the result. It is deliberately separate
from the routers so the IRR filter and the drill-down share one code path and cannot
produce different numbers for the same parcel.

Purity is preserved: this module reads the database and calls the engine, but the engine
still receives only dataclasses and returns only dataclasses (CLAUDE.md's non-negotiable).
"""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import datetime
from threading import Lock
from typing import Any

from engine.assumptions import DEFAULT_ASSUMPTIONS, PROVENANCE
from engine.confidence import score_confidence
from engine.envelope import resolve_envelope
from engine.program import fit_program
from engine.proforma import full_cashflow, screening_rlv
from engine.prototypes import PROTOTYPES
from engine.solve import solve_irr_rlv
from engine.types import Assumptions, NotPermitted, Parcel, Use
from data import repositories as repo

UNDERWRITE_USE = Use.RESIDENTIAL

# Assumption groups a client may override, matching the 1c modal's sections. `program` is
# excluded: it is stamped by the prototype at fit time, not user-supplied as a flat dict.
OVERRIDABLE_GROUPS = ("timeline", "cost", "revenue", "debt", "exit", "envelope")


class UnderwriteError(Exception):
    """The parcel cannot be underwritten, with a reason fit to show a user."""


# ---------------------------------------------------------------------------
# assumptions
# ---------------------------------------------------------------------------
def build_assumptions(overrides: dict[str, Any] | None) -> tuple[Assumptions, dict]:
    """DEFAULT_ASSUMPTIONS with a shallow per-group merge. Returns (assumptions, applied).

    Only known groups and known keys are merged — an unrecognised key is dropped rather
    than silently widening the model's input surface. `applied` reports what actually took
    effect, so the 1c modal's "N inputs changed from default" counts reality, not intent.
    """
    merged = Assumptions(
        program=dict(DEFAULT_ASSUMPTIONS.program),
        timeline=dict(DEFAULT_ASSUMPTIONS.timeline),
        cost=copy.deepcopy(DEFAULT_ASSUMPTIONS.cost),
        revenue=dict(DEFAULT_ASSUMPTIONS.revenue),
        debt=dict(DEFAULT_ASSUMPTIONS.debt),
        exit=dict(DEFAULT_ASSUMPTIONS.exit),
        envelope=dict(DEFAULT_ASSUMPTIONS.envelope),
    )
    applied: dict[str, dict] = {}
    if not overrides:
        return merged, applied

    for group in OVERRIDABLE_GROUPS:
        supplied = overrides.get(group)
        if not isinstance(supplied, dict):
            continue
        target = getattr(merged, group)
        for key, value in supplied.items():
            if key not in target:
                continue      # unknown input: ignored, never invented
            if target[key] == value:
                continue      # same as default: not an edit
            target[key] = value
            applied.setdefault(group, {})[key] = value
    return merged, applied


def _cache_key(ssl: str, prototype_id: str, batch: datetime, applied: dict, demo: bool) -> str:
    return json.dumps(
        {"ssl": ssl, "proto": prototype_id, "batch": batch.isoformat(),
         "ov": applied, "demo": demo},
        sort_keys=True, default=str,
    )


_cache: dict[str, dict] = {}
_cache_lock = Lock()
_CACHE_MAX = 2_048


# ---------------------------------------------------------------------------
# the underwrite
# ---------------------------------------------------------------------------
def underwrite(
    conn,
    ssl: str,
    batch: datetime,
    prototype_id: str | None = None,
    overrides: dict[str, Any] | None = None,
    include_demolition: bool | None = None,
) -> dict:
    """Run the full levered model for one parcel. Cached per (parcel, prototype, inputs).

    Raises `UnderwriteError` with a user-facing reason when the parcel cannot be modelled —
    exempt, historic, unencoded zoning, or no admissible prototype. Those are real answers
    about a parcel, not failures, and the caller renders them as such.
    """
    record = repo.get_parcel_record(conn, ssl)
    if record is None:
        raise UnderwriteError(f"No parcel with ID {ssl}.")
    parcel: Parcel = repo.to_parcel(record)

    if parcel.is_exempt:
        raise UnderwriteError("This parcel is public or tax-exempt and is not scored.")
    if parcel.is_historic:
        raise UnderwriteError(
            "This parcel is in a historic district. Redevelopment is restricted and v1 "
            "does not model it."
        )

    rules = repo.get_rules(conn, parcel.zone_code)
    if rules is None:
        raise UnderwriteError(f"Zoning district {parcel.zone_code} is not yet covered.")

    # Pick the prototype: caller's choice ("Try another prototype"), else the bake's best.
    baked = repo.bake_rows_for_ssl(conn, ssl, batch)
    if prototype_id is None:
        best = next((r for r in baked if r.get("is_best") and r["status"] == "scored"), None)
        prototype_id = best["prototype_id"] if best else None
    if prototype_id is None or prototype_id not in PROTOTYPES:
        raise UnderwriteError("No admissible prototype for this parcel under its zoning.")

    assumptions, applied = build_assumptions(overrides)
    if include_demolition is not None:
        assumptions.cost["include_demolition"] = bool(include_demolition)
        if bool(include_demolition) != bool(DEFAULT_ASSUMPTIONS.cost["include_demolition"]):
            applied.setdefault("cost", {})["include_demolition"] = bool(include_demolition)
    demo = bool(assumptions.cost["include_demolition"])

    key = _cache_key(ssl, prototype_id, batch, applied, demo)
    with _cache_lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit

    market = repo.get_market(conn, parcel.submarket_id)
    if market is None:
        raise UnderwriteError(f"No market data for submarket {parcel.submarket_id}.")

    try:
        envelope = resolve_envelope(parcel, rules, UNDERWRITE_USE, assumptions)
        program = fit_program(
            envelope, PROTOTYPES[prototype_id], rules, UNDERWRITE_USE, assumptions, parcel
        )
    except NotPermitted as exc:
        raise UnderwriteError(
            f"{PROTOTYPES[prototype_id].prototype_id} is not admissible on this parcel: {exc}"
        ) from exc

    # Tier 1, recomputed under the SAME inputs as tier 2 so the two are comparable. The
    # bake's stored screening RLV used defaults; if the user edited inputs, comparing the
    # new full RLV against the OLD screening number would misattribute the difference to
    # the tier split when it is really the edits.
    screening = screening_rlv(program, market, assumptions, parcel)
    screening.confidence = score_confidence(PROVENANCE, market)

    # Tier 2: solve land value against the levered hurdle (§6.8), then run the cash flow at
    # that land value so the reported vectors are the ones the RLV was solved for.
    hurdle = assumptions.exit["irr_hurdle"]
    full_rlv, unachievable = solve_irr_rlv(program, market, assumptions, parcel, hurdle)
    cashflow, outputs = full_cashflow(program, market, assumptions, parcel, land=full_rlv)
    outputs.confidence = screening.confidence
    outputs.irr_target_unachievable = unachievable

    result = {
        "parcel": parcel,
        "record": record,
        "envelope": envelope,
        "program": program,
        "market": market,
        "assumptions": assumptions,
        "applied_overrides": applied,
        "screening": screening,
        "outputs": outputs,
        "cashflow": cashflow,
        "full_rlv": full_rlv,
        "irr_target_unachievable": unachievable,
        "hurdle": hurdle,
        "prototype_id": prototype_id,
        "baked_rows": baked,
        "computed_at": batch,
    }

    with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.clear()      # crude but bounded; results are cheap to recompute (~20ms)
        _cache[key] = result
    return result


def irr_for_row(conn, row: dict, batch: datetime) -> float | None:
    """Levered IRR for one already-read map row, for the IRR filter.

    `batch` is threaded in from the caller's pinned batch rather than re-resolved, so the
    filter cannot cross bakes mid-request.

    Returns None when the parcel cannot be underwritten or the IRR does not converge —
    both mean "does not meet the threshold" for filtering purposes, and neither may raise
    (SPEC fix #8: IRR failures never propagate to the caller).
    """
    try:
        result = underwrite(conn, row["ssl"], batch, prototype_id=row.get("prototype_id"))
    except UnderwriteError:
        return None
    except Exception:
        # A genuine bug should not turn a 200-row filter into a 500 — but it must not be
        # silently indistinguishable from "below threshold" either, so it is logged.
        import logging
        logging.getLogger(__name__).exception("IRR filter failed for %s", row.get("ssl"))
        return None
    return result["outputs"].irr
