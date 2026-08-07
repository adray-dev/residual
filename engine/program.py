from dataclasses import replace

from engine.prototypes import GROUND_FLOOR_ACTIVE_PROTOTYPES
from engine.types import (
    Assumptions,
    Envelope,
    NotPermitted,
    Parcel,
    Program,
    Prototype,
    Use,
    ZoningRules,
)


def fit_program(
    envelope: Envelope,
    prototype: Prototype,
    rules: ZoningRules,
    requested_use: Use,
    assumptions: Assumptions,
    parcel: Parcel,
    overrides: dict | None = None,
) -> Program:
    if requested_use not in rules.permitted_uses:
        raise NotPermitted(f"{requested_use.value} not permitted in {rules.district_code}")

    if parcel.lot_area_sf < prototype.min_lot_sf:
        raise NotPermitted(
            f"{prototype.prototype_id} requires >= {prototype.min_lot_sf:,.0f} SF lot; "
            f"parcel is {parcel.lot_area_sf:,.0f} SF"
        )

    if prototype.min_stories > envelope.max_floors:
        raise NotPermitted(
            f"{prototype.prototype_id} needs >= {prototype.min_stories} stories; "
            f"{rules.district_code} allows {envelope.max_floors} "
            f"(gated by {envelope.binding_constraint})"
        )

    floors = min(prototype.max_stories, envelope.max_floors)
    gross_sf = min(envelope.max_buildable_gsf, envelope.max_footprint_sf * floors)

    # Required ground-floor active use (v1.3): the ground floorplate is costed at normal
    # hard $/SF but excluded from net rentable — cost without revenue.
    #
    # v1.3.2: the mandate applies only to prototypes that plausibly have a non-residential
    # ground floor (§5 `GROUND_FLOOR_ACTIVE_PROTOTYPES` = midrise/highrise). Townhome and
    # garden are exempt: a rowhouse has no ground-floor retail, and charging it one removed
    # a third of its revenue while keeping all of its cost.
    #
    # KNOWN v1 SIMPLIFICATION (SPEC §11): the mandate is still applied district-wide. The ZR
    # ties active frontage to DESIGNATED STREET SEGMENTS (e.g. Subtitle I § 601), not to
    # whole zones, and we have no street-segment data. So this still overstates the mandate
    # — but now only for mid/high-rise on non-designated frontage inside mandated districts,
    # rather than for every building type on every parcel of those districts.
    required_active_sf = 0.0
    if (
        rules.requires_ground_floor_active
        and prototype.prototype_id in GROUND_FLOOR_ACTIVE_PROTOTYPES
        and floors >= 1
    ):
        required_active_sf = min(envelope.max_footprint_sf, gross_sf)
        residential_gsf = max(gross_sf - required_active_sf, 0.0)
    else:
        residential_gsf = gross_sf

    net = residential_gsf * prototype.efficiency_ratio
    avg_sf = sum(
        prototype.default_unit_mix[k] * prototype.avg_unit_sf[k]
        for k in prototype.default_unit_mix
    )
    unit_count = int(net // avg_sf)
    unit_mix_counts = {
        k: int(unit_count * prototype.default_unit_mix[k]) for k in prototype.default_unit_mix
    }

    parking_ratio = rules.parking_ratio.get("residential", 0.5)
    stalls = int(round(unit_count * parking_ratio))

    program = Program(
        prototype_id=prototype.prototype_id,
        construction_type=prototype.construction_type,
        gross_sf=gross_sf,
        net_rentable_sf=net,
        unit_count=unit_count,
        unit_mix_counts=unit_mix_counts,
        retail_sf=required_active_sf,
        parking_stalls=stalls,
        parking_type=prototype.parking_type,
        floors=floors,
    )
    if overrides:
        program = apply_overrides(program, overrides)
    return program


def apply_overrides(program: Program, overrides: dict) -> Program:
    """User edits to units/stories/stalls/etc. Unknown keys raise, so typos surface loudly."""
    unknown = set(overrides) - {f for f in program.__dataclass_fields__}
    if unknown:
        raise ValueError(f"unknown program override(s): {sorted(unknown)}")
    return replace(program, **overrides)
