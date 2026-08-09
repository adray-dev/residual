"""bake rows and engine dataclasses -> wire payloads.

Every plain-language decision that the server makes (rather than deferring to the client)
lands here, and every one of them reads its wording from `api.vocabulary`.
"""
from __future__ import annotations

import math
from typing import Any

from api import vocabulary as vocab
from api.schemas import (
    Developability,
    ParcelRow,
    PrototypeResult,
    ZoningInfo,
)
from engine.types import ZoningRules


def display_name(address: str | None, parcel_id: str) -> str:
    """The label every screen leads with.

    The handoff is address-forward, but ~1% of DC parcels carry no premise address
    (unaddressed interior lots, ROW slivers). Those fall back to the parcel ID rather than
    rendering blank — and the fallback still says "Parcel ID", never "SSL".
    """
    return address or f"Parcel ID {parcel_id}"


def ward_name(submarket_id: str | None) -> str | None:
    """`ward_6` -> `Ward 6`. The UI never shows the internal id."""
    if not submarket_id:
        return None
    if submarket_id.startswith("ward_"):
        return f"Ward {submarket_id[5:]}"
    return submarket_id


def _clean(value: Any) -> Any:
    """NaN/inf -> None.

    The engine returns floats from division chains that can produce non-finite values on
    degenerate parcels. JSON has no NaN, and a silently-dropped field reads as "no data"
    anyway — so normalize here rather than emitting invalid JSON.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def developability(existing_building_sf: float | None) -> Developability:
    """SPEC §10's developability flag.

    A parcel with a standing building is not raw land: the seller prices the improvement
    too, so acquisition runs above the land value the RLV is being compared against. The
    model does not net this out (the demolition toggle is opt-in), so the UI states it.
    """
    sf = float(existing_building_sf or 0.0)
    if sf <= 0:
        return Developability(existing_building_sf=0.0, has_existing_building=False, note=None)
    return Developability(
        existing_building_sf=sf,
        has_existing_building=True,
        note=f"Existing building: {sf:,.0f} SF — acquisition will run above land value",
    )


def parcel_row(row: dict, irr: float | None = None) -> ParcelRow:
    """One `latest_bake_for_map` row -> the table/map wire shape."""
    parcel_id = row["ssl"]
    prototype_id = row.get("prototype_id")
    if prototype_id == "__none__":
        prototype_id = None      # the status-row sentinel is internal, never shipped

    return ParcelRow(
        parcel_id=parcel_id,
        address=row.get("address"),
        neighborhood=row.get("neighborhood"),
        display_name=display_name(row.get("address"), parcel_id),
        ward=ward_name(row.get("submarket_id")),
        zone_code=row.get("zone_code"),
        status=row["status"],
        prototype_id=prototype_id,
        lot_area_sf=_clean(row.get("lot_area_sf")),
        land_value=_clean(row.get("land_value")),
        existing_building_sf=_clean(row.get("existing_building_sf")),
        screening_rlv=_clean(row.get("screening_rlv")),
        rlv_total=_clean(row.get("rlv_total")),
        rlv_per_buildable_sf=_clean(row.get("rlv_per_buildable_sf")),
        feasibility_gap=_clean(row.get("feasibility_gap")),
        noi=_clean(row.get("noi")),
        total_development_cost=_clean(row.get("total_development_cost")),
        yield_on_cost=_clean(row.get("yield_on_cost")),
        profit_margin=_clean(row.get("profit_margin")),
        exit_value=_clean(row.get("exit_value")),
        gross_sf=_clean(row.get("gross_sf")),
        net_rentable_sf=_clean(row.get("net_rentable_sf")),
        unit_count=row.get("unit_count"),
        floors=row.get("floors"),
        confidence=_clean(row.get("confidence")),
        binding_constraint=row.get("binding_constraint"),
        binding_constraint_label=vocab.binding_constraint_label(row.get("binding_constraint")),
        irr=_clean(irr),
    )


def prototype_result(row: dict) -> PrototypeResult:
    """One `bake_results` row for a single prototype (drill-down / "try another")."""
    return PrototypeResult(
        prototype_id=row["prototype_id"],
        is_best=bool(row.get("is_best")),
        screening_rlv=_clean(row.get("screening_rlv")),
        rlv_per_buildable_sf=_clean(row.get("rlv_per_buildable_sf")),
        feasibility_gap=_clean(row.get("feasibility_gap")),
        noi=_clean(row.get("noi")),
        total_development_cost=_clean(row.get("total_development_cost")),
        yield_on_cost=_clean(row.get("yield_on_cost")),
        profit_margin=_clean(row.get("profit_margin")),
        exit_value=_clean(row.get("exit_value")),
        gross_sf=_clean(row.get("gross_sf")),
        net_rentable_sf=_clean(row.get("net_rentable_sf")),
        unit_count=row.get("unit_count"),
        floors=row.get("floors"),
        binding_constraint=row.get("binding_constraint"),
        binding_constraint_label=vocab.binding_constraint_label(row.get("binding_constraint")),
        confidence=_clean(row.get("confidence")),
    )


def zoning_info(zone_code: str | None, rules: ZoningRules | None) -> ZoningInfo:
    """Zoning tab. `encoded=False` is a first-class answer, not an error.

    SPEC fix #1: a parcel in a not-yet-encoded district still loads and still appears on
    the map, in its own quiet shade. The UI says "zoning not yet covered", not "unknown".
    """
    if rules is None:
        return ZoningInfo(zone_code=zone_code, district_code=None, encoded=False)
    return ZoningInfo(
        zone_code=zone_code,
        district_code=rules.district_code,
        encoded=True,
        max_far=rules.max_far,
        max_height_ft=rules.max_height_ft,
        max_stories=rules.max_stories,
        lot_occupancy_pct=rules.lot_occupancy_pct,
        permitted_uses=[u.value if hasattr(u, "value") else str(u) for u in rules.permitted_uses],
        parking_ratio=rules.parking_ratio,
        requires_ground_floor_active=rules.requires_ground_floor_active,
        matter_of_right=rules.matter_of_right,
    )


def market_snapshot(market: Any) -> dict:
    """The exact MarketData used, for `scenarios.market_snapshot` (SPEC §7.1, v1.2).

    A saved scenario NEVER re-reads live market data, so every value the model consumed is
    frozen here — including the per-input provenance tags, which is what makes a saved
    scenario's confidence reproducible rather than recomputed against a newer seed.
    """
    return {
        "submarket_id": market.submarket_id,
        "rent_psf_residential_monthly": market.rent_psf_residential_monthly,
        "retail_rent_psf_annual": market.retail_rent_psf_annual,
        "exit_cap_rate": market.exit_cap_rate,
        "hard_cost_psf": {
            (k.value if hasattr(k, "value") else str(k)): v
            for k, v in market.hard_cost_psf.items()
        },
        "as_of": str(market.as_of),
        "source": market.source,
        "input_provenance": dict(getattr(market, "input_provenance", {}) or {}),
    }


def underwrite_response(result: dict) -> dict:
    """A full-tier result -> the 1b drill-down payload.

    Assembled here rather than in the router so the underwrite endpoints, the scenario
    save, and the export all serialize one result the same way.
    """
    import numpy as np

    from api.schemas import (
        AssumptionSet, CashFlowOut, EnvelopeOut, FeasibilityValue, ProgramOut,
        ReturnMetrics, SourcesUses,
    )

    record = result["record"]
    parcel = result["parcel"]
    program = result["program"]
    envelope = result["envelope"]
    outputs = result["outputs"]
    screening = result["screening"]
    cf = result["cashflow"]
    assumptions = result["assumptions"]

    parcel_id = parcel.ssl
    full_rlv = float(result["full_rlv"])
    screening_rlv_value = float(screening.screening_rlv)
    difference = full_rlv - screening_rlv_value
    difference_pct = (
        difference / abs(screening_rlv_value) if screening_rlv_value else None
    )

    def series(vector) -> list[float]:
        return [float(x) for x in np.asarray(vector, dtype=float)]

    costs = (
        np.asarray(cf.land, dtype=float)
        + np.asarray(cf.hard_cost, dtype=float)
        + np.asarray(cf.soft_cost, dtype=float)
        + np.asarray(cf.contingency, dtype=float)
    )
    # DEVELOPMENT equity: the cash put in before stabilization, and only that.
    #
    # This used to sum negative equity flows across the whole hold, which silently swept in
    # two post-development things: a cash-in refinancing at stabilization (when the perm
    # loan comes in below the construction balance) and any month of operating shortfall
    # during hold. Both are real capital, but neither is a source that funded the BUILD, and
    # neither has a matching entry on the uses side — so sources exceeded uses by exactly
    # those flows. It only showed up once an assumption was edited, because the default run
    # has no shortfall of either kind.
    #
    # Scoped to the development period the identity is exact rather than approximate:
    #   sources = (draws + interest) + equity
    #           = (total_cost - equity_needed + interest) + equity_needed
    #           = total_cost + interest
    #           = uses
    #
    # Nothing is lost by excluding the later flows: `peak_equity` spans the whole hold and
    # still carries them, so the capital a developer has to find is never understated.
    # Full length, because the S-curve's equity series runs the whole timeline. Only the
    # sources & uses TOTAL is scoped to the development period.
    stabilization = int(cf.phase_bounds["stabilization"])
    equity_draws = -np.minimum(np.asarray(cf.equity_cf, dtype=float), 0.0)

    hard_total = float(np.sum(cf.hard_cost))
    soft_total = float(np.sum(cf.soft_cost))
    contingency_total = float(np.sum(cf.contingency))
    land_total = float(np.sum(cf.land))
    interest_total = float(np.sum(cf.construction_interest))
    equity_total = float(np.sum(equity_draws[:stabilization]))

    # The construction loan is principal draws PLUS capitalized interest. Interest is not
    # paid in cash during construction — it accrues onto the balance (§6.4), so the loan
    # funds it. Reporting draws alone leaves sources short of uses by exactly the interest,
    # and a sources & uses chart whose two bars disagree is worse than no chart.
    loan_total = float(np.sum(cf.construction_draw)) + interest_total

    unit_count = program.unit_count or 0
    construction_type = (
        program.construction_type.value
        if hasattr(program.construction_type, "value")
        else str(program.construction_type)
    )

    # The return the panel shows is measured at the assessed land value, not at the solved
    # RLV — at the solved RLV it is the hurdle by construction. `irr_basis` travels with it.
    irr_at_assessed = result.get("irr_at_assessed")
    assessed = result.get("assessed_land_value")
    basis = (
        "Assessed land value" if irr_at_assessed is not None
        else "Unavailable — no assessed land value on record"
    )

    return dict(
        computed_at=result["computed_at"],
        parcel_id=parcel_id,
        display_name=display_name(record.get("address"), parcel_id),
        address=record.get("address"),
        ward=ward_name(record.get("submarket_id")),
        lot_area_sf=parcel.lot_area_sf,
        prototype_id=result["prototype_id"],
        is_bake_best=any(
            r.get("is_best") and r["prototype_id"] == result["prototype_id"]
            for r in result["baked_rows"]
        ),
        feasibility_value=FeasibilityValue(
            full=full_rlv,
            screening=screening_rlv_value,
            difference=difference,
            difference_pct=difference_pct,
        ),
        feasibility_gap=_clean(outputs.feasibility_gap),
        per_unit_value=(full_rlv / unit_count) if unit_count else None,
        returns=ReturnMetrics(
            irr=_clean(irr_at_assessed),
            irr_basis=basis,
            irr_basis_value=_clean(assessed),
            equity_multiple=_clean(outputs.equity_multiple),
            yield_on_cost=_clean(outputs.yield_on_cost) or 0.0,
            profit_margin=_clean(outputs.profit_margin) or 0.0,
            total_development_cost=_clean(outputs.total_development_cost) or 0.0,
            noi=_clean(outputs.noi) or 0.0,
            exit_value=_clean(outputs.exit_value) or 0.0,
            peak_equity=_clean(outputs.peak_equity),
            cost_per_unit=(
                (outputs.total_development_cost / unit_count) if unit_count else None
            ),
            target_return=result["hurdle"],
            irr_target_unachievable=bool(result["irr_target_unachievable"]),
        ),
        program=ProgramOut(
            prototype_id=program.prototype_id,
            construction_type=construction_type,
            gross_sf=program.gross_sf,
            net_rentable_sf=program.net_rentable_sf,
            unit_count=unit_count,
            unit_mix_counts=dict(program.unit_mix_counts or {}),
            retail_sf=program.retail_sf,
            parking_stalls=program.parking_stalls,
            parking_type=program.parking_type,
            parking_phrase=vocab.parking_phrase(program.parking_stalls, program.parking_type),
            floors=program.floors,
            avg_unit_sf=(program.net_rentable_sf / unit_count) if unit_count else None,
            rent_psf_monthly=result["market"].rent_psf_residential_monthly,
        ),
        envelope=EnvelopeOut(
            max_buildable_gsf=envelope.max_buildable_gsf,
            max_footprint_sf=envelope.max_footprint_sf,
            max_floors=envelope.max_floors,
            binding_constraint=envelope.binding_constraint,
            binding_constraint_label=vocab.binding_constraint_label(envelope.binding_constraint),
            admissible=envelope.admissible,
            reason=envelope.reason,
        ),
        sources_uses=SourcesUses(
            uses={
                "construction": hard_total,
                "soft_costs": soft_total,
                "contingency": contingency_total,
                "land": land_total,
                "loan_interest": interest_total,
            },
            sources={"construction_loan": loan_total, "equity": equity_total},
            uses_total=hard_total + soft_total + contingency_total + land_total + interest_total,
            sources_total=loan_total + equity_total,
            balanced=abs(
                (hard_total + soft_total + contingency_total + land_total + interest_total)
                - (loan_total + equity_total)
            ) < 1.0,
        ),
        cashflow=CashFlowOut(
            months=cf.months,
            phase_bounds=dict(cf.phase_bounds),
            land=series(cf.land),
            hard_cost=series(cf.hard_cost),
            soft_cost=series(cf.soft_cost),
            contingency=series(cf.contingency),
            noi=series(cf.noi),
            construction_draw=series(cf.construction_draw),
            construction_balance=series(cf.construction_balance),
            construction_interest=series(cf.construction_interest),
            perm_balance=series(cf.perm_balance),
            perm_debt_service=series(cf.perm_debt_service),
            equity_cf=series(cf.equity_cf),
            cumulative_cost=series(np.cumsum(costs)),
            cumulative_equity=series(np.cumsum(equity_draws)),
        ),
        developability=developability(record.get("existing_building_sf")),
        confidence=outputs.confidence,
        applied_overrides=result["applied_overrides"],
        overrides_changed=sum(len(v) for v in result["applied_overrides"].values()),
        assumptions=AssumptionSet(
            assumption_set_id="working",
            name="Working inputs",
            timeline=dict(assumptions.timeline),
            cost=dict(assumptions.cost),
            revenue=dict(assumptions.revenue),
            debt=dict(assumptions.debt),
            exit=dict(assumptions.exit),
            envelope=dict(assumptions.envelope),
            program=dict(assumptions.program),
        ),
        market_snapshot=market_snapshot(result["market"]),
    )


def labels_block() -> dict:
    """The whole vocabulary, shipped in /meta so the client keeps no copy."""
    return {
        "metric": {k: v[0] for k, v in vocab.METRIC_LABELS.items()},
        "prototype": dict(vocab.PROTOTYPE_LABELS),
        "construction": dict(vocab.CONSTRUCTION_LABELS),
        "parking": dict(vocab.PARKING_LABELS),
        "binding_constraint": dict(vocab.BINDING_CONSTRAINT_LABELS),
        "status": dict(vocab.STATUS_LABELS),
        "tier": dict(vocab.TIER_LABELS),
        "assumption_group": dict(vocab.ASSUMPTION_GROUP_LABELS),
        "assumption": {k: v[0] for k, v in vocab.ASSUMPTION_FIELDS.items()},
        # Unit kind per input. Shipped alongside the label because it is a fact about the
        # number's meaning, not a styling choice: `soft_cost_pct` is 0.2 on the wire and
        # must be edited as 20%.
        "assumption_kind": {k: v[1] for k, v in vocab.ASSUMPTION_FIELDS.items()},
    }
