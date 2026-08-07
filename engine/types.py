from dataclasses import dataclass, field
from enum import Enum


class Use(str, Enum):
    RESIDENTIAL = "residential"
    RETAIL = "retail"
    OFFICE = "office"


class ConstructionType(str, Enum):
    WOOD_V = "wood_v"           # Type V, townhome/garden
    WOOD_OVER_PODIUM = "podium"  # Type III/V over Type I podium (5-over-1)
    CONCRETE_I = "concrete_i"   # Type I, mid/high-rise


@dataclass
class Parcel:
    ssl: str                    # DC Square-Suffix-Lot — the universal key
    lot_area_sf: float
    zone_code: str
    submarket_id: str
    land_value: float | None    # assessed land value; None when no CAMA row (untaxed/exempt land)
    improvement_value: float | None
    land_use_code: str
    improvement_ratio: float | None   # improvement/(land+improvement); None when values missing
    existing_building_sf: float = 0.0   # gross building area from CAMA; 0 if vacant.
                                        # Feeds the demo toggle AND the developability flag.
    is_exempt: bool = False     # federal/public/church/cemetery/ROW — pre-filtered, never scored
    is_historic: bool = False   # in a historic district — flagged, gated, not scored in v1


@dataclass
class ZoningRules:
    district_code: str
    max_far: float
    max_height_ft: float
    max_stories: int | None
    lot_occupancy_pct: dict     # {"residential": 0.60, "other": 0.80}
    permitted_uses: list        # [Use, ...]
    parking_ratio: dict         # {"residential": stalls_per_unit, ...}
    requires_ground_floor_active: bool = False   # district mandates ground-floor retail/active use
    matter_of_right: bool = True


@dataclass
class MarketData:
    submarket_id: str
    rent_psf_residential_monthly: float
    retail_rent_psf_annual: float
    exit_cap_rate: float
    hard_cost_psf: dict         # {ConstructionType: $/SF}  (submarket-adjusted)
    as_of: str
    source: str
    # Per-input provenance tags for the values THIS row genuinely supplies (§2.8: "the
    # caller flips that input's tag"). Keys are PROVENANCE keys; values are "submarket" or
    # "local" when the source reports a geography inside this submarket, "national" when the
    # value is a citywide/class-level figure or a borrowed comparable. Empty (the default)
    # means a plain national fallback row: it promotes nothing.
    input_provenance: dict = field(default_factory=dict)


@dataclass
class Prototype:
    prototype_id: str           # "townhome" | "garden" | "midrise" | "highrise"
    construction_type: ConstructionType
    min_stories: int
    max_stories: int
    min_lot_sf: float           # admissibility gate: prototype needs at least this much lot
    efficiency_ratio: float     # net rentable / gross
    default_unit_mix: dict      # {"studio":0.2,"1br":0.5,"2br":0.3}
    avg_unit_sf: dict           # {"studio":500,"1br":750,"2br":1050}
    parking_type: str           # "surface"|"structured"|"podium"


@dataclass
class Assumptions:
    # flat container built from §2 defaults; every field carries a provenance tag
    # stored as {value, provenance} pairs so confidence.py can read tags
    program: dict
    timeline: dict
    cost: dict
    revenue: dict
    debt: dict
    exit: dict
    envelope: dict


@dataclass
class Envelope:
    max_buildable_gsf: float
    max_footprint_sf: float
    max_floors: int
    binding_constraint: str     # "far" | "height" | "stories"  — for the "gated by" callout
    admissible: bool
    reason: str = ""            # populated when not admissible


@dataclass
class Program:
    prototype_id: str
    construction_type: ConstructionType   # stamped by fit_program so the pro forma can price it (fix #2)
    gross_sf: float
    net_rentable_sf: float
    unit_count: int                       # REPORTING ONLY — never drives revenue (fix #3)
    unit_mix_counts: dict                 # reporting only
    retail_sf: float                      # required ground-floor active-use shell SF (costed, no revenue); 0 elsewhere
    parking_stalls: int
    parking_type: str
    floors: int


@dataclass
class Outputs:
    screening_rlv: float
    feasibility_gap: float | None   # rlv - land_value; None when no assessed value exists
    yield_on_cost: float
    irr: float | None           # None in screening tier
    equity_multiple: float | None
    profit_margin: float
    total_development_cost: float
    peak_equity: float | None
    confidence: float
    exit_value: float = 0.0     # stabilized gross sale value; used by solve_irr_rlv's upper bracket
    noi: float = 0.0            # stabilized NOI, annual. Both tiers compute it to reach
                                # exit_value and yield_on_cost; returning it lets the bake
                                # persist it and the UI show "Yearly income (NOI)" without
                                # back-solving it out of yield_on_cost * TDC.
    irr_target_unachievable: bool = False


@dataclass
class CashFlow:
    """Month-indexed vectors, length T+1 (§6). Numpy arrays."""
    months: int
    land: "object"
    hard_cost: "object"
    soft_cost: "object"
    contingency: "object"
    noi: "object"
    construction_draw: "object"
    construction_balance: "object"
    construction_interest: "object"
    perm_balance: "object"
    perm_debt_service: "object"
    equity_cf: "object"
    phase_bounds: dict          # {"predev_end": p, "construction_end": p+c, "stabilization": p+c+l, "sale": T}


class NotPermitted(Exception):
    """Raised when a use or prototype is not admissible for a parcel/zoning combination."""
