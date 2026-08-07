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


MetaResponse.model_rebuild()
