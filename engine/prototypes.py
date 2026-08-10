from engine.types import ConstructionType, Prototype

# The stories bands do not overlap (v1.8): townhome 2-3, 5-over-1 4-7, midrise 8-12,
# highrise 13+. That bounds what each tier BUILDS — not which tiers are admissible.
#
# Admissibility is `min_stories <= envelope.max_floors`, and each prototype then builds up
# to its OWN cap, so a tall envelope admits several tiers at once and they compete. On a
# 9-floor RA-5 lot all of townhome (3 floors), 5-over-1 (7) and midrise (9) are admissible,
# and 5-over-1 wins: seven storeys of wood at $260/SF beats nine of concrete at $320. That
# competition is the point of the split, not a flaw in it — the alternative, forcing the
# tallest admissible tier, would rebuild the v1.7 bug in a new place.
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
    # Wood frame over a concrete podium — the workhorse urban infill product, and the whole
    # reason this tier exists: 4-7 storeys used to be priced as concrete midrise at $340/SF
    # when it is really built in wood at $260. `min_lot_sf` is 6,000: below concrete
    # midrise's 8,000 because a podium building is routinely built on tighter urban lots,
    # well above townhome's 1,500 because it still needs a podium footprint and a core.
    # (Judgment call, flagged in SPEC §11 with the rest of these placeholders.)
    "5-over-1": Prototype(
        prototype_id="5-over-1",
        construction_type=ConstructionType.WOOD_OVER_PODIUM,
        min_stories=4, max_stories=7,
        min_lot_sf=6_000,
        efficiency_ratio=0.85,
        default_unit_mix={"studio": 0.25, "1br": 0.50, "2br": 0.25},
        avg_unit_sf={"studio": 500, "1br": 750, "2br": 1050},
        parking_type="podium",
    ),
    "midrise": Prototype(
        prototype_id="midrise",
        construction_type=ConstructionType.CONCRETE_I,
        min_stories=8, max_stories=12,
        min_lot_sf=8_000,
        efficiency_ratio=0.85,
        default_unit_mix={"studio": 0.25, "1br": 0.50, "2br": 0.25},
        avg_unit_sf={"studio": 500, "1br": 750, "2br": 1050},
        parking_type="podium",
    ),
    "highrise": Prototype(
        prototype_id="highrise",
        construction_type=ConstructionType.CONCRETE_I,
        min_stories=13, max_stories=30,
        min_lot_sf=12_000,
        efficiency_ratio=0.85,
        default_unit_mix={"studio": 0.30, "1br": 0.50, "2br": 0.20},
        avg_unit_sf={"studio": 480, "1br": 720, "2br": 1000},
        parking_type="structured",
    ),
}

# §5: prototypes DEFINED but not competing (v1).
#
# A hide, not a deletion. `garden` stays fully specified above and keeps its label, its
# `prototypes` table row, and its place in the library; it is simply excluded from the
# candidate set the bake ranks, so it can never be `is_best` and never shows as "best
# build". Re-enabling is emptying this set.
#
# Why garden: at the v1.7 premium spread it is structurally dominated by townhome on every
# axis at once — premium 1.00 vs 1.15, efficiency 0.85 vs 0.90, hard cost $210 vs $200/SF,
# min lot 15,000 vs 1,500. Its only advantage is a fourth floor, and per SF of coverage that
# buys 4 x 0.85 x 1.00 = 3.40 revenue-units against townhome's 3 x 0.90 x 1.15 = 3.105 while
# costing 4 x 210 = $840 against 3 x 200 = $600. It cannot win at any rent, and the v1.7
# bake confirmed it: admissible on 2,503 scored parcels, `is_best` on zero. Carrying a
# prototype that is unwinnable by construction is the same defect v1.4 was written to fix,
# so it is benched rather than tuned around.
#
# Retention keeps the previous batch, and that batch DOES contain garden winners. Nothing
# here removes the label or the ability to read those rows — only future competition.
DISABLED_PROTOTYPES: frozenset[str] = frozenset({"garden"})

# The set the bake actually ranks. Every consumer that enumerates candidates reads this;
# `PROTOTYPES` remains the complete library, for lookup by id.
ACTIVE_PROTOTYPES: dict[str, Prototype] = {
    pid: proto for pid, proto in PROTOTYPES.items() if pid not in DISABLED_PROTOTYPES
}


# §5: which prototypes can carry a non-residential ground floor at all.
#
# `zoning_rules.requires_ground_floor_active` is a property of the DISTRICT, but the carve-out
# it triggers is only meaningful for building types that actually have a commercial ground
# floor. A rowhouse does not, and neither does a garden-apartment walk-up; applying the
# mandate to them modeled mandatory ground-floor retail in a rowhouse, which cost a third of
# the building's revenue (the ground floorplate is one of three floors) while costing it at
# full hard $/SF. That single defect, not the economics of the MU/D districts, was what drove
# every mandated-zone parcel negative — forcing the flag ON in RF-1 and R-2 reproduced the
# same −46/SF those zones showed.
#
# Membership is stated explicitly rather than derived from `construction_type`. Today
# CONCRETE_I happens to select exactly {midrise, highrise}, but that is a coincidence of the
# current library: a podium-construction midrise would break the derivation silently, and
# "has a commercial ground floor" is not the same claim as "is built of concrete".
# 5-over-1 joins the set in v1.8, and it is the most literal member of it: the "1" in the
# name IS the podium, and a ground-floor commercial bay is the standard way that podium is
# used. Townhome and garden stay out for the reason above.
GROUND_FLOOR_ACTIVE_PROTOTYPES: frozenset[str] = frozenset(
    {"5-over-1", "midrise", "highrise"}
)

# §5: national fallback hard $/SF BY PROTOTYPE, used when a submarket MarketData row is
# unavailable. Kept in sync with the construction-type table below times HARD_COST_FACTOR;
# `test_cost_tables_agree` pins that they cannot drift.
NATIONAL_HARD_COST_PSF = {
    "townhome": 220,
    "garden": 220,     # rides the wood_v line; benched, so nothing depends on it
    "5-over-1": 260,
    "midrise": 320,
    "highrise": 340,
}

# ---------------------------------------------------------------------------
# §5: the height premium on an identical structural system (v1.8)
# ---------------------------------------------------------------------------
# The pro forma prices a building as `market.hard_cost_psf[construction_type]`, which is
# right — cost follows how a thing is built, and it is the hook a submarket cost row plugs
# into. But midrise and highrise are BOTH concrete Type I and are not the same price:
# $320/SF against $340/SF. That difference is not a different structural system, it is the
# cost of going tall in the same one — deeper foundations, crane and hoist logistics, more
# elevators, higher wind loading.
#
# So it is modeled as a factor on the construction-type cost rather than as a fourth
# invented construction type. Two reasons. A fake `ConstructionType.CONCRETE_HIGHRISE`
# would claim a distinction in structural system that does not exist, and — the practical
# one — the factor is multiplicative, so a submarket that one day seeds its own concrete
# cost still gets its number scaled instead of overwritten by a national constant.
#
# 340 / 320 = 1.0625.
HARD_COST_FACTOR: dict[str, float] = {
    "townhome": 1.0,
    "garden": 1.0,
    "5-over-1": 1.0,
    "midrise": 1.0,
    "highrise": 1.0625,   # +6.25% over the same concrete: height, not system
}


def hard_cost_psf(base_psf: float, prototype_id: str) -> float:
    """Construction-type $/SF adjusted for the prototype's height premium (§5)."""
    return base_psf * HARD_COST_FACTOR.get(prototype_id, 1.0)

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
#
# v1.7 re-tuned the factors. GARDEN is now the 1.00 base rather than townhome: a rowhouse
# with its own front door and no shared corridor rents above a walk-up flat, so the previous
# 1.00/1.00 pair had the two low-rise products backwards. Midrise and highrise moved up to
# 1.40/1.60 so the elevator products earn a premium large enough to matter against their
# hard cost — at 1.15/1.30 the spread never covered $340–430/SF concrete and neither ever
# won a parcel. The point of the change is to give the map product variety to show, and it
# does not make these numbers any more sourced than they were.
RENT_PREMIUM_FACTOR: dict[str, float] = {
    "townhome": 0.90,   # v1.9: rowhouse rents BELOW the walk-up base per SF — big units,
                        #   and the per-SF rent of a 1,300 SF 2br is not the per-SF rent of
                        #   a 750 SF 1br. Also the correction to a model that had townhome
                        #   winning 98.8% of the city.
    "garden": 1.00,     # the base — walk-up, no elevator and no amenity package
    "5-over-1": 1.40,   # elevator product with an amenity package; same rent as midrise,
    "midrise": 1.40,    #   because to a tenant they are the same building — only the
                        #   structure behind the drywall differs, and that is a cost fact
    "highrise": 1.60,   # full-service Class A, views, doorman
}

# Signed adjustment in absolute cap-rate terms, added to the submarket base cap.
# Denser institutional-grade product typically trades tighter (lower cap = higher value).
EXIT_CAP_ADJUSTMENT: dict[str, float] = {
    "townhome": 0.0,
    "garden": 0.0,
    "5-over-1": -0.0025,  # -25 bps, matching midrise: a buyer prices the income stream and
    "midrise": -0.0025,   #   the amenity set, which are the same for both
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
