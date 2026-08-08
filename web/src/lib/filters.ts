/** Filter state, and the two very different things it drives.
 *
 * The MAP is filtered client-side, by a MapLibre expression over attributes already in the
 * tile — SPEC §10 wants narrowing to feel instant, and a round trip per slider tick would
 * not. The COUNT comes from /map/query, which reads `bake_results`, because the tile only
 * knows what is currently loaded in view and "4,182 parcels match" is a claim about the
 * whole city.
 *
 * Those two must be derived from one state object or they will disagree, which is why the
 * expression and the query string are built here, side by side, from the same fields.
 */
import type { ExpressionSpecification, FilterSpecification } from "maplibre-gl";
import { BIN_FIELD } from "./mapStyle";

export interface FilterState {
  /** Raw `submarket_id`s ("ward_6"). Empty means every ward. */
  wards: string[];
  /** Prototype ids ("garden"). Empty means every build. */
  prototypes: string[];
  /** Screening RLV floor/ceiling in dollars. Null means unbounded. */
  rlvMin: number | null;
  rlvMax: number | null;
  /** Hide the four non-scored statuses, which carry no value to compare. */
  scoredOnly: boolean;
}

export const EMPTY_FILTERS: FilterState = {
  wards: [],
  prototypes: [],
  rlvMin: null,
  rlvMax: null,
  scoredOnly: false,
};

export function isEmpty(state: FilterState): boolean {
  return (
    state.wards.length === 0 &&
    state.prototypes.length === 0 &&
    state.rlvMin == null &&
    state.rlvMax == null &&
    !state.scoredOnly
  );
}

/** Toggle a value in one of the list-valued filters. */
export function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/**
 * The MapLibre filter for parcels that MATCH. Non-matching parcels are not hidden —
 * they are drawn in a muted layer instead (see MapView), because a filter that erases
 * two thirds of the city leaves the user staring at floating fragments with no sense of
 * where they are. Dimming keeps the street grid legible.
 */
export function mapFilter(state: FilterState): FilterSpecification | null {
  const clauses: ExpressionSpecification[] = [];

  if (state.wards.length) {
    clauses.push(["in", ["get", "ward"], ["literal", state.wards]]);
  }
  if (state.prototypes.length) {
    clauses.push(["in", ["get", "proto"], ["literal", state.prototypes]]);
  }
  if (state.scoredOnly) {
    clauses.push(["==", ["get", "status"], "scored"]);
  }
  // A value bound is a statement about a value, so it can only apply to parcels that have
  // one. Non-scored parcels carry a null `rlv` and must not be swept up by "over $1M".
  if (state.rlvMin != null || state.rlvMax != null) {
    clauses.push(["==", ["get", "status"], "scored"]);
    if (state.rlvMin != null) {
      clauses.push([">=", ["coalesce", ["get", "rlv"], -Infinity], state.rlvMin]);
    }
    if (state.rlvMax != null) {
      clauses.push(["<=", ["coalesce", ["get", "rlv"], Infinity], state.rlvMax]);
    }
  }

  if (!clauses.length) return null;
  return ["all", ...clauses] as FilterSpecification;
}

/** The same state as /map/query parameters, for the "N parcels match" count. */
export function queryParams(state: FilterState): Record<string, string | number | string[]> {
  const params: Record<string, string | number | string[]> = {
    // One row is enough: the count comes from `total`, which is computed before paging.
    limit: 1,
  };
  if (state.wards.length) params.wards = state.wards;
  if (state.prototypes.length) params.prototypes = state.prototypes;
  if (state.rlvMin != null) params.rlv_min = state.rlvMin;
  if (state.rlvMax != null) params.rlv_max = state.rlvMax;
  if (state.scoredOnly || state.rlvMin != null || state.rlvMax != null) {
    params.statuses = ["scored"];
  }
  return params;
}

/** Objectives whose ramp we can read a slider domain from. */
export const RLV_OBJECTIVE = "rlv_total";
export { BIN_FIELD };
