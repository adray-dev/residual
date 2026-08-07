from engine.types import ConstructionType, Prototype

PROTOTYPES: dict[str, Prototype] = {
    "townhome": Prototype(
        prototype_id="townhome",
        construction_type=ConstructionType.WOOD_V,
        min_stories=2, max_stories=3,
        min_lot_sf=1_500,
        efficiency_ratio=0.90,
        default_unit_mix={"1br": 0.40, "2br": 0.60},
        avg_unit_sf={"1br": 900, "2br": 1300},
        parking_type="surface",
    ),
    "garden": Prototype(
        prototype_id="garden",
        construction_type=ConstructionType.WOOD_V,
        min_stories=2, max_stories=4,
        min_lot_sf=15_000,
        efficiency_ratio=0.85,
        default_unit_mix={"studio": 0.20, "1br": 0.50, "2br": 0.30},
        avg_unit_sf={"studio": 500, "1br": 750, "2br": 1050},
        parking_type="surface",
    ),
    "midrise": Prototype(
        prototype_id="midrise",
        construction_type=ConstructionType.CONCRETE_I,
        min_stories=5, max_stories=12,
        min_lot_sf=8_000,
        efficiency_ratio=0.80,
        default_unit_mix={"studio": 0.25, "1br": 0.50, "2br": 0.25},
        avg_unit_sf={"studio": 500, "1br": 750, "2br": 1050},
        parking_type="podium",
    ),
    "highrise": Prototype(
        prototype_id="highrise",
        construction_type=ConstructionType.CONCRETE_I,
        min_stories=12, max_stories=30,
        min_lot_sf=12_000,
        efficiency_ratio=0.75,
        default_unit_mix={"studio": 0.30, "1br": 0.50, "2br": 0.20},
        avg_unit_sf={"studio": 480, "1br": 720, "2br": 1000},
        parking_type="structured",
    ),
}

# §5: which prototypes can carry a non-residential ground floor at all.
#
# `zoning_rules.requires_ground_floor_active` is a property of the DISTRICT, but the carve-out
# it triggers is only meaningful for building types that actually have a commercial ground
# floor. A rowhouse does not, and neither does a garden-apartment walk-up; applying the
# mandate to them modelled mandatory ground-floor retail in a rowhouse, which cost a third of
# the building's revenue (the ground floorplate is one of three floors) while costing it at
# full hard $/SF. That single defect, not the economics of the MU/D districts, was what drove
# every mandated-zone parcel negative — forcing the flag ON in RF-1 and R-2 reproduced the
# same −46/SF those zones showed.
#
# Membership is stated explicitly rather than derived from `construction_type`. Today
# CONCRETE_I happens to select exactly {midrise, highrise}, but that is a coincidence of the
# current library: a podium-construction midrise would break the derivation silently, and
# "has a commercial ground floor" is not the same claim as "is built of concrete".
GROUND_FLOOR_ACTIVE_PROTOTYPES: frozenset[str] = frozenset({"midrise", "highrise"})

# §5: national fallback hard $/SF, used when a submarket MarketData row is unavailable.
NATIONAL_HARD_COST_PSF = {
    "townhome": 200,
    "garden": 210,
    "midrise": 340,
    "highrise": 430,
}
