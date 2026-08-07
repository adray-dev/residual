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

# ---------------------------------------------------------------------------
# §2.4 / §5: product-type variation in the revenue model (v1.4)
# ---------------------------------------------------------------------------
# Before v1.4 the pro forma applied ONE submarket rent and ONE flat exit cap to all four
# prototypes. That made density unwinnable by construction: townhome converts $1 of hard
# cost into 4.286 rentable SF against midrise's 2.353, so if a square foot earns the same
# rent and trades at the same cap in both, the walk-up wins every parcel in every submarket
# at every rent level. The bake showed exactly that — townhome was `is_best` on 100% of
# scored parcels and mid/high-rise never won anywhere.
#
# Two product-type dimensions now sit between the submarket inputs and the pro forma:
#
#   effective rent = market.rent_psf_residential_monthly * RENT_PREMIUM_FACTOR[prototype]
#   effective cap  = market.exit_cap_rate               + EXIT_CAP_ADJUSTMENT[prototype]
#
# !! PLACEHOLDER ASSUMPTIONS — NOT SOURCED (SPEC §11) !!
# These are plausible starting values chosen to give product type a voice, NOT measured
# figures. They are deliberately tagged "national" in PROVENANCE so confidence reports them
# as un-tailored, exactly like the other national defaults. What they want, and do not yet
# have, is real rent-by-product-type and cap-by-product-type data per submarket — DC Class A
# elevator rents versus rowhouse rents are an empirical question with a real answer, and
# these numbers are not it. Do not read the ordering here as a finding.
RENT_PREMIUM_FACTOR: dict[str, float] = {
    "townhome": 1.00,   # the base: submarket rent is quoted for this product
    "garden": 1.00,
    "midrise": 1.15,    # new elevator product, amenity package
    "highrise": 1.30,   # full-service Class A
}

# Signed adjustment in absolute cap-rate terms, added to the submarket base cap.
# Denser institutional-grade product typically trades tighter (lower cap = higher value).
EXIT_CAP_ADJUSTMENT: dict[str, float] = {
    "townhome": 0.0,
    "garden": 0.0,
    "midrise": -0.0025,   # -25 bps
    "highrise": -0.0050,  # -50 bps
}

# A cap rate at or below zero would divide by zero (or invert) in the exit valuation. The
# engine never raises to the caller, so the effective cap is floored instead. With v1's
# 5.5% base and a -50 bps worst case this is unreachable; it exists so a future submarket
# cap or a hand-edited assumption set cannot produce a non-finite exit value.
MIN_EXIT_CAP_RATE = 0.001


def rent_premium_factor(prototype_id: str) -> float:
    """Product-type rent multiplier. Unknown prototypes fall back to the base rent."""
    return RENT_PREMIUM_FACTOR.get(prototype_id, 1.0)


def effective_rent_psf_monthly(base_rent_psf_monthly: float, prototype_id: str) -> float:
    """Submarket base rent adjusted for product type (§2.4)."""
    return base_rent_psf_monthly * rent_premium_factor(prototype_id)


def effective_exit_cap(base_exit_cap: float, prototype_id: str) -> float:
    """Submarket base cap adjusted for product type (§2.4), floored above zero."""
    return max(base_exit_cap + EXIT_CAP_ADJUSTMENT.get(prototype_id, 0.0), MIN_EXIT_CAP_RATE)
