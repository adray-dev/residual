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

# §5: national fallback hard $/SF, used when a submarket MarketData row is unavailable.
NATIONAL_HARD_COST_PSF = {
    "townhome": 200,
    "garden": 210,
    "midrise": 340,
    "highrise": 430,
}
