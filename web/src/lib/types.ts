/** Wire types — the shapes `api/schemas.py` actually serializes.
 *
 * Field names here are SPEC's (`rlv_total`, `yield_on_cost`, `irr`), never the UI's. The
 * translation to plain language happens once, at render time, through the label block the
 * server ships in /meta (see `vocabulary.ts`). Keeping the wire in SPEC's vocabulary is
 * what lets the two be checked against each other.
 */

export interface Labels {
  metric: Record<string, string>;
  prototype: Record<string, string>;
  construction: Record<string, string>;
  parking: Record<string, string>;
  binding_constraint: Record<string, string>;
  status: Record<string, string>;
  tier: Record<string, string>;
  /** The 1c inputs modal: group headings, per-input labels, and per-input unit kind. */
  assumption_group: Record<string, string>;
  assumption: Record<string, string>;
  assumption_kind: Record<string, string>;
}

/** The editable groups of an assumption set, as /assumptions/default serves them. */
export type AssumptionGroups = Record<string, Record<string, number | boolean | string>>;

/** `/assumptions/default`. The two identifying fields sit alongside the groups on the
 * wire, so the type is an intersection rather than an extension — a group index signature
 * cannot also admit bare strings. */
export type AssumptionSet = AssumptionGroups & {
  assumption_set_id: string;
  name: string;
};

export interface ObjectiveRamp {
  objective: string;
  min: number | null;
  max: number | null;
  negative_breaks: number[];
  positive_breaks: number[];
  negative_count: number;
  positive_count: number;
}

export interface Submarket {
  submarket_id: string;
  name: string;
}

export interface Limits {
  max_page_size: number;
  max_irr_filter_parcels: number;
}

export interface Meta {
  computed_at: string;
  /** Null when no tileset has been built for THIS batch — never a stale one. */
  tileset_url: string | null;
  tileset_available: boolean;
  parcel_count: number;
  status_counts: Record<string, number>;
  objectives: string[];
  default_objective: string;
  ramps: Record<string, ObjectiveRamp>;
  submarkets: Submarket[];
  neighborhoods: string[];
  labels: Labels;
  limits: Limits;
}

/** One row of the map/table read, straight off `bake_results`.
 *
 * `screening_rlv` and `rlv_total` are the same number under two names — SPEC 7.1 pins the
 * first and SPEC 9 names the second as the objective, and the server ships both so the
 * client never has to know that. Every screening field is null on a non-scored row.
 */
export interface ParcelRow {
  parcel_id: string;
  address: string | null;
  neighborhood: string | null;
  display_name: string;
  ward: string | null;
  zone_code: string | null;
  status: string;
  prototype_id: string | null;
  lot_area_sf: number | null;
  land_value: number | null;
  existing_building_sf: number | null;
  screening_rlv: number | null;
  rlv_total: number | null;
  rlv_per_buildable_sf: number | null;
  feasibility_gap: number | null;
  noi: number | null;
  total_development_cost: number | null;
  yield_on_cost: number | null;
  profit_margin: number | null;
  exit_value: number | null;
  gross_sf: number | null;
  net_rentable_sf: number | null;
  unit_count: number | null;
  floors: number | null;
  confidence: number | null;
  binding_constraint: string | null;
  binding_constraint_label: string | null;
  /** Absent from the screening tier by design; set only when the IRR filter ran. */
  irr: number | null;
}

export interface MapQuery {
  computed_at: string;
  total: number;
  returned: number;
  offset: number;
  objective: string;
  sort_key: string;
  sort_dir: string;
  rows: ParcelRow[];
  irr_filter_applied: boolean;
}

/** One `/parcels/search` hit. Carries a centroid so the map can move to it. */
export interface SearchResult {
  parcel_id: string;
  address: string | null;
  neighborhood: string | null;
  ward: string | null;
  display_name: string;
  status: string;
  lon: number | null;
  lat: number | null;
}

export interface ShortlistSummary {
  shortlist_id: string;
  name: string;
  parcel_count: number;
  created_at: string;
}

export interface ShortlistTotals {
  parcel_count: number;
  scored_count: number;
  combined_value: number;
  combined_floor_area: number;
  /** Median, not mean — one deep-negative parcel would drag an average off the list. */
  median_return: number | null;
}

export interface ShortlistDetail {
  shortlist_id: string;
  name: string;
  created_at: string;
  /** The bake these numbers were read from — a shortlist never freezes a figure. */
  computed_at: string;
  parcels: ParcelRow[];
  added_at: Record<string, string>;
  totals: ShortlistTotals;
}

export interface ZoningInfo {
  zone_code: string | null;
  district_code: string | null;
  /** False when the district is not yet in `zoning_rules` — the map's dashed status. */
  encoded: boolean;
  max_far: number | null;
  max_height_ft: number | null;
  max_stories: number | null;
  lot_occupancy_pct: Record<string, number> | null;
  permitted_uses: string[] | null;
  parking_ratio: Record<string, number> | null;
  requires_ground_floor_active: boolean | null;
  matter_of_right: boolean | null;
}

/** One prototype's screening result — the "Try another prototype" list. */
export interface PrototypeResult {
  prototype_id: string;
  is_best: boolean;
  screening_rlv: number | null;
  rlv_per_buildable_sf: number | null;
  feasibility_gap: number | null;
  noi: number | null;
  total_development_cost: number | null;
  yield_on_cost: number | null;
  profit_margin: number | null;
  exit_value: number | null;
  gross_sf: number | null;
  net_rentable_sf: number | null;
  unit_count: number | null;
  floors: number | null;
  binding_constraint: string | null;
  binding_constraint_label: string | null;
  confidence: number | null;
}

/** The record read behind the 1a popup. Screening tier — the engine does not run. */
export interface ParcelRecord {
  computed_at: string;
  parcel_id: string;
  address: string | null;
  neighborhood: string | null;
  display_name: string;
  ward: string | null;
  lot_area_sf: number | null;
  land_value: number | null;
  improvement_value: number | null;
  improvement_ratio: number | null;
  land_use_code: string | null;
  is_exempt: boolean;
  is_historic: boolean;
  status: string;
  status_label: string;
  developability: Developability;
  zoning: ZoningInfo;
  prototypes: PrototypeResult[];
  best_prototype_id: string | null;
  confidence: number | null;
}

export interface ProgramOut {
  prototype_id: string;
  construction_type: string;
  gross_sf: number;
  net_rentable_sf: number;
  unit_count: number;
  unit_mix_counts: Record<string, number>;
  retail_sf: number;
  parking_stalls: number;
  parking_type: string;
  /** Pre-phrased server-side: "12 stalls, surface", never "12 podium". */
  parking_phrase: string;
  floors: number;
  avg_unit_sf: number | null;
  rent_psf_monthly: number;
}

export interface EnvelopeOut {
  max_buildable_gsf: number;
  max_footprint_sf: number;
  max_floors: number;
  binding_constraint: string;
  binding_constraint_label: string | null;
  admissible: boolean;
  reason: string;
}

export interface ReturnMetrics {
  /** Measured at `irr_basis_value`, NOT at the solved RLV — see `MetricGrid`. */
  irr: number | null;
  irr_basis: string;
  irr_basis_value: number | null;
  equity_multiple: number | null;
  yield_on_cost: number;
  profit_margin: number;
  total_development_cost: number;
  noi: number;
  exit_value: number;
  peak_equity: number | null;
  cost_per_unit: number | null;
  target_return: number;
  /** No land price, even $0, reaches the hurdle. */
  irr_target_unachievable: boolean;
}

export interface FeasibilityValue {
  full: number;
  screening: number;
  difference: number;
  difference_pct: number | null;
  full_label: string;
  screening_label: string;
}

export interface SourcesUses {
  uses: Record<string, number>;
  sources: Record<string, number>;
  uses_total: number;
  sources_total: number;
  /** False means a modeling bug, not rounding — do not draw the chart. */
  balanced: boolean;
}

export interface CashFlowOut {
  months: number;
  /** Month index at which each phase ENDS: predev_end, construction_end, stabilization, sale. */
  phase_bounds: Record<string, number>;
  land: number[];
  hard_cost: number[];
  soft_cost: number[];
  contingency: number[];
  noi: number[];
  construction_draw: number[];
  construction_balance: number[];
  construction_interest: number[];
  perm_balance: number[];
  perm_debt_service: number[];
  equity_cf: number[];
  cumulative_cost: number[];
  cumulative_equity: number[];
}

export interface Developability {
  existing_building_sf: number;
  has_existing_building: boolean;
  note: string | null;
}

export interface Underwrite {
  computed_at: string;
  parcel_id: string;
  display_name: string;
  address: string | null;
  ward: string | null;
  lot_area_sf: number | null;
  prototype_id: string;
  is_bake_best: boolean;
  feasibility_value: FeasibilityValue;
  feasibility_gap: number | null;
  per_unit_value: number | null;
  returns: ReturnMetrics;
  program: ProgramOut;
  envelope: EnvelopeOut;
  sources_uses: SourcesUses;
  cashflow: CashFlowOut;
  developability: Developability;
  /** A 0-1 fraction on the wire; ALWAYS rendered as a percentage. */
  confidence: number;
  applied_overrides: Record<string, unknown>;
  overrides_changed: number;
  assumptions: Record<string, Record<string, number | boolean | string>>;
  market_snapshot: Record<string, unknown>;
}

/** The body of POST-style overrides accepted by /parcel/{id}/underwrite. */
export interface UnderwriteRequest {
  prototype_id?: string | null;
  include_demolition?: boolean | null;
  timeline?: Record<string, number>;
  cost?: Record<string, number>;
  revenue?: Record<string, number>;
  debt?: Record<string, number>;
  exit?: Record<string, number>;
  envelope?: Record<string, number>;
}
