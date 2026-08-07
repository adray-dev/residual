"""Wire models.

Field names on the wire are SPEC's (`rlv_total`, `yield_on_cost`, `irr`), not the UI's
plain-language labels. Two reasons: the payload stays auditable line-by-line against SPEC,
and there is no lossy rename layer between the engine and the client. The plain-language
labels ride separately, in the `labels` block of `/meta`, so `api/vocabulary.py` is their
single source and no TypeScript copy can drift from it.

The one exception is `parcel_id`: the handoff's rule is that "SSL" never appears in
user-facing text, and a field name that shows up in a client-side debugger and in URL
params is close enough to user-facing to honour it.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Objective = Literal["rlv_total", "rlv_per_buildable_sf", "gap"]
Status = Literal["scored", "infeasible", "exempt", "historic", "zone_not_encoded"]


# ---------------------------------------------------------------------------
# /meta
# ---------------------------------------------------------------------------
class RampStop(BaseModel):
    """One bin of the diverging value ramp, as absolute currency bounds."""
    min: float | None = Field(None, description="Inclusive lower bound; None = open")
    max: float | None = Field(None, description="Exclusive upper bound; None = open")


class ObjectiveRamp(BaseModel):
    """Quantile-binned diverging ramp for one objective.

    The handoff's 8-stop teal ramp assumes all-positive values, but 56% of scored DC
    parcels have a NEGATIVE feasibility value (median -$29K, range -$80.6M..+$98.2M), and
    the tails are extreme enough that a linear scale collapses the middle. So the ramp
    diverges at zero and is quantile-binned WITHIN each arm: `negative_breaks` ascending
    below zero, `positive_breaks` ascending above.

    Tiles carry a precomputed bin index per objective, so the client colors by lookup and
    never divides (SPEC §9) and never calls the server to switch objective (SPEC §10).
    """
    objective: Objective
    min: float | None
    max: float | None
    negative_breaks: list[float]
    positive_breaks: list[float]
    negative_count: int
    positive_count: int


class MetaResponse(BaseModel):
    """Boot payload. The client reads this first and pins everything else to it.

    `computed_at` and `tileset_url` come from the SAME batch by construction, which is what
    stops the tiles and the table straddling two bakes.
    """
    computed_at: datetime
    tileset_url: str | None = Field(
        None, description="PMTiles for THIS batch; None until tiles are built"
    )
    tileset_available: bool
    parcel_count: int
    status_counts: dict[str, int]
    objectives: list[Objective]
    default_objective: Objective
    ramps: dict[str, ObjectiveRamp]
    submarkets: list["Submarket"]
    neighborhoods: list[str]
    labels: "Labels"
    limits: "Limits"


class Submarket(BaseModel):
    submarket_id: str
    name: str


class Labels(BaseModel):
    """The handoff's plain-language vocabulary, served so the client needs no copy."""
    metric: dict[str, str]
    prototype: dict[str, str]
    construction: dict[str, str]
    parking: dict[str, str]
    binding_constraint: dict[str, str]
    status: dict[str, str]
    tier: dict[str, str]


class Limits(BaseModel):
    max_page_size: int
    max_irr_filter_parcels: int = Field(
        description="Above this the IRR filter refuses; narrow with other filters first"
    )


# ---------------------------------------------------------------------------
# /map/query
# ---------------------------------------------------------------------------
class Bounds(BaseModel):
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.min_lon, self.min_lat, self.max_lon, self.max_lat)


class MapFilters(BaseModel):
    """The handoff's filter panel, plus the status filter the map legend implies."""
    wards: list[str] = []
    neighborhoods: list[str] = []
    statuses: list[Status] = []
    prototypes: list[str] = []
    rlv_min: float | None = None
    rlv_max: float | None = None
    min_confidence: float | None = None
    # Levered IRR exists only in the full tier, so this filter runs the engine per parcel
    # and is bounded by `Limits.max_irr_filter_parcels` (see the router).
    irr_min: float | None = None
    # GeoJSON Polygon ring(s) from the draw-an-area tool. Not wired in the UI this stage.
    drawn_polygon: dict | None = None


class MapQueryRequest(BaseModel):
    bounds: Bounds | None = None
    filters: MapFilters = MapFilters()
    objective: Objective = "rlv_total"
    sort_key: str | None = None
    sort_dir: Literal["asc", "desc"] = "desc"
    limit: int = 200
    offset: int = 0


class ParcelRow(BaseModel):
    """One row of the map/table read. Straight off `bake_results` — the engine never runs.

    `screening_rlv` and `rlv_total` are the same number under two names (SPEC §7.1 pins
    the first, §9 names the second as the objective). Both ship so the client never has to
    know that.
    """
    parcel_id: str
    address: str | None
    neighborhood: str | None
    display_name: str = Field(
        description="Address when known, else 'Parcel ID <id>'. The handoff leads with "
                    "an address on six of seven screens; ~1% of parcels have none."
    )
    ward: str | None
    zone_code: str | None
    status: Status
    prototype_id: str | None
    lot_area_sf: float | None
    land_value: float | None
    existing_building_sf: float | None

    # screening tier — NULL on every non-scored row
    screening_rlv: float | None
    rlv_total: float | None
    rlv_per_buildable_sf: float | None
    feasibility_gap: float | None
    noi: float | None
    total_development_cost: float | None
    yield_on_cost: float | None
    profit_margin: float | None
    exit_value: float | None
    gross_sf: float | None
    net_rentable_sf: float | None
    unit_count: int | None
    floors: int | None
    confidence: float | None
    binding_constraint: str | None
    binding_constraint_label: str | None

    # Levered IRR is absent from the screening tier by design (SPEC §9). Populated only
    # when the IRR filter ran the full model over this row.
    irr: float | None = None


class MapQueryResponse(BaseModel):
    computed_at: datetime
    total: int = Field(description="Matching parcels before paging")
    returned: int
    offset: int
    objective: Objective
    sort_key: str
    sort_dir: str
    rows: list[ParcelRow]
    irr_filter_applied: bool = False


# ---------------------------------------------------------------------------
# /parcel/{parcel_id}
# ---------------------------------------------------------------------------
class ZoningInfo(BaseModel):
    zone_code: str | None
    district_code: str | None = Field(None, description="Encoded district the rules came from")
    encoded: bool = Field(description="False when the district is not yet in zoning_rules")
    max_far: float | None = None
    max_height_ft: float | None = None
    max_stories: int | None = None
    lot_occupancy_pct: dict | None = None
    permitted_uses: list[str] | None = None
    parking_ratio: dict | None = None
    requires_ground_floor_active: bool | None = None
    matter_of_right: bool | None = None


class PrototypeResult(BaseModel):
    """One prototype's screening result. The handoff's "Try another prototype" needs the
    non-best options, and SPEC §9 asks the UI to surface the top 2-3."""
    prototype_id: str
    is_best: bool
    screening_rlv: float | None
    rlv_per_buildable_sf: float | None
    feasibility_gap: float | None
    noi: float | None
    total_development_cost: float | None
    yield_on_cost: float | None
    profit_margin: float | None
    exit_value: float | None
    gross_sf: float | None
    net_rentable_sf: float | None
    unit_count: int | None
    floors: int | None
    binding_constraint: str | None
    binding_constraint_label: str | None
    confidence: float | None


class Developability(BaseModel):
    """SPEC §10's developability flag.

    An existing building means acquisition costs more than the land is worth on its own,
    so a positive RLV does not by itself mean an acquirable deal. Surfaced, not hidden.
    """
    existing_building_sf: float
    has_existing_building: bool
    note: str | None = Field(
        None,
        description='e.g. "Existing building: 6,400 SF — acquisition will run above land value"',
    )


class ParcelResponse(BaseModel):
    computed_at: datetime
    parcel_id: str
    address: str | None
    neighborhood: str | None
    display_name: str
    ward: str | None
    lot_area_sf: float | None
    land_value: float | None
    improvement_value: float | None
    improvement_ratio: float | None
    land_use_code: str | None
    is_exempt: bool
    is_historic: bool
    status: Status
    status_label: str
    developability: Developability
    zoning: ZoningInfo
    prototypes: list[PrototypeResult]
    best_prototype_id: str | None
    confidence: float | None


# ---------------------------------------------------------------------------
# /assumptions/default
# ---------------------------------------------------------------------------
class AssumptionSet(BaseModel):
    """The §2 defaults, grouped as the 1c inputs modal groups them.

    Provenance is deliberately NOT exposed: the engine tracks national/submarket/local
    sourcing, and the handoff's language rules say the UI shows values only. Confidence is
    the one number that summarises it.
    """
    assumption_set_id: str
    name: str
    timeline: dict
    cost: dict
    revenue: dict
    debt: dict
    exit: dict
    envelope: dict
    program: dict


# ---------------------------------------------------------------------------
# /parcel/{parcel_id}/underwrite
# ---------------------------------------------------------------------------
class UnderwriteRequest(BaseModel):
    """Assumption overrides for a re-underwrite (the 1c modal's "Re-underwrite parcel").

    Only the six editable groups; `program` is stamped by the prototype at fit time.
    Unknown keys are ignored rather than widening the model's input surface.
    """
    prototype_id: str | None = Field(
        None, description="Override the bake's best build ('Try another prototype')"
    )
    include_demolition: bool | None = Field(
        None, description="The 1b demolition toggle. Default off; never applied in the bake."
    )
    timeline: dict = {}
    cost: dict = {}
    revenue: dict = {}
    debt: dict = {}
    exit: dict = {}
    envelope: dict = {}

    def overrides(self) -> dict:
        return {
            "timeline": self.timeline, "cost": self.cost, "revenue": self.revenue,
            "debt": self.debt, "exit": self.exit, "envelope": self.envelope,
        }


class ProgramOut(BaseModel):
    """The 1b Program card. Labels come from /meta; this is the data behind them."""
    prototype_id: str
    construction_type: str
    gross_sf: float
    net_rentable_sf: float
    unit_count: int
    unit_mix_counts: dict
    retail_sf: float
    parking_stalls: int
    parking_type: str
    parking_phrase: str = Field(description='"12 stalls, surface" — never "12 podium"')
    floors: int
    avg_unit_sf: float | None
    rent_psf_monthly: float


class EnvelopeOut(BaseModel):
    """The "gated by" callout (SPEC §10)."""
    max_buildable_gsf: float
    max_footprint_sf: float
    max_floors: int
    binding_constraint: str
    binding_constraint_label: str | None
    admissible: bool
    reason: str = ""


class ReturnMetrics(BaseModel):
    """The 1b metric grid.

    `irr` is measured at the ASSESSED land value, not at the solved RLV. At the solved RLV
    the IRR is the hurdle by construction (that is what the solve does), so it would read
    17.00% on every parcel and rank nothing. `irr_basis` says which price it used so the
    number can never be mistaken for a target.
    """
    irr: float | None
    irr_basis: str
    irr_basis_value: float | None
    equity_multiple: float | None
    yield_on_cost: float
    profit_margin: float
    total_development_cost: float
    noi: float
    exit_value: float
    peak_equity: float | None
    cost_per_unit: float | None
    target_return: float = Field(description="The hurdle the RLV was solved against")
    irr_target_unachievable: bool = Field(
        description="True when no land price, even $0, reaches the hurdle (SPEC fix #8)"
    )


class FeasibilityValue(BaseModel):
    """Both tiers, side by side. SPEC §11 accepts that they diverge; the UI must label it.

    `full` is the levered IRR-based RLV (§6.8) and leads the panel. `screening` is the
    unlevered margin-based RLV (§3.4) — the number the MAP is coloured by, recomputed here
    under the same assumptions so any difference is the tier split and not stale inputs.
    """
    full: float
    screening: float
    difference: float
    difference_pct: float | None
    full_label: str = "Full underwriting"
    screening_label: str = "Screening estimate"


class SourcesUses(BaseModel):
    """The 1b stacked-bar chart. Uses and sources each sum to total development cost.

    `construction_loan` includes capitalized interest: interest accrues onto the balance
    during construction rather than being paid in cash (§6.4), so the loan funds it. That
    is what makes the two bars balance.
    """
    uses: dict[str, float]
    sources: dict[str, float]
    uses_total: float
    sources_total: float
    balanced: bool = Field(
        description="Sources equal uses to within $1. False means a modelling bug, not a "
                    "rounding artefact — the UI should not draw the chart."
    )


class CashFlowOut(BaseModel):
    """Monthly vectors for the Cash flow tab and the S-curve, length months+1."""
    months: int
    phase_bounds: dict
    land: list[float]
    hard_cost: list[float]
    soft_cost: list[float]
    contingency: list[float]
    noi: list[float]
    construction_draw: list[float]
    construction_balance: list[float]
    construction_interest: list[float]
    perm_balance: list[float]
    perm_debt_service: list[float]
    equity_cf: list[float]
    cumulative_cost: list[float] = Field(description="S-curve teal series")
    cumulative_equity: list[float] = Field(description="S-curve amber dashed series")


class UnderwriteResponse(BaseModel):
    computed_at: datetime
    parcel_id: str
    display_name: str
    address: str | None
    ward: str | None
    lot_area_sf: float | None
    prototype_id: str
    is_bake_best: bool
    feasibility_value: FeasibilityValue
    feasibility_gap: float | None
    per_unit_value: float | None
    returns: ReturnMetrics
    program: ProgramOut
    envelope: EnvelopeOut
    sources_uses: SourcesUses
    cashflow: CashFlowOut
    developability: Developability
    confidence: float
    applied_overrides: dict
    overrides_changed: int
    assumptions: AssumptionSet
    market_snapshot: dict


MetaResponse.model_rebuild()
