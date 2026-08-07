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
    anyway — so normalise here rather than emitting invalid JSON.
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
    }
