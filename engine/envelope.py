from engine.types import Assumptions, Envelope, Parcel, Use, ZoningRules


def resolve_envelope(
    parcel: Parcel,
    rules: ZoningRules,
    requested_use: Use,
    assumptions: Assumptions,
) -> Envelope:
    ftf = assumptions.envelope["floor_to_floor_residential_ft"]

    # 1. floors — limited by height, and possibly further by an explicit story cap
    floors_by_height = int(rules.max_height_ft // ftf)
    if rules.max_stories is not None and rules.max_stories < floors_by_height:
        floors = rules.max_stories
        floor_limiter = "stories"
    else:
        floors = floors_by_height
        floor_limiter = "height"

    # 2. two candidate GSF limits
    far_gsf = parcel.lot_area_sf * rules.max_far
    occ = rules.lot_occupancy_pct["residential" if requested_use == Use.RESIDENTIAL else "other"]
    footprint = parcel.lot_area_sf * occ
    coverage_gsf = footprint * floors

    # 3. the binding constraint is whichever produced the minimum
    if far_gsf <= coverage_gsf:
        max_gsf = far_gsf
        binding = "far"
    else:
        max_gsf = coverage_gsf
        binding = floor_limiter

    return Envelope(
        max_buildable_gsf=max_gsf,
        max_footprint_sf=footprint,
        max_floors=floors,
        binding_constraint=binding,
        admissible=True,
    )
