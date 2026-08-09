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
  /** Minimum IRR. Runs the full model per matching parcel, so the server bounds it. */
  irrMin: number | null;
}

export const EMPTY_FILTERS: FilterState = {
  wards: [],
  prototypes: [],
  rlvMin: null,
  rlvMax: null,
  irrMin: null,
};

export function isEmpty(state: FilterState): boolean {
  return (
    state.wards.length === 0 &&
    state.prototypes.length === 0 &&
    state.rlvMin == null &&
    state.rlvMax == null &&
    state.irrMin == null
  );
}

/** Toggle a value in one of the list-valued filters. */
export function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/**
 * The MapLibre filter for scored parcels that MATCH. Non-matching parcels are not hidden —
 * they are drawn in a muted layer instead (see MapView), because a filter that erases most
 * of what is on screen leaves the user staring at floating fragments with no sense of
 * where they are. Dimming keeps the street grid legible.
 */
export function mapFilter(state: FilterState): FilterSpecification | null {
  // Scored is not a filter any more, it is the premise: the product visualises feasibility,
  // and a parcel with no feasibility has nothing to place on the ramp. It is applied in the
  // layer definitions rather than here, so this only ever narrows WITHIN the scored set.
  const clauses: ExpressionSpecification[] = [];

  if (state.wards.length) {
    clauses.push(["in", ["get", "ward"], ["literal", state.wards]]);
  }
  if (state.prototypes.length) {
    clauses.push(["in", ["get", "proto"], ["literal", state.prototypes]]);
  }
  if (state.rlvMin != null || state.rlvMax != null) {
    if (state.rlvMin != null) {
      clauses.push([">=", ["coalesce", ["get", "rlv"], -Infinity], state.rlvMin]);
    }
    if (state.rlvMax != null) {
      clauses.push(["<=", ["coalesce", ["get", "rlv"], Infinity], state.rlvMax]);
    }
  }

  // IRR is deliberately NOT in the map expression. It does not exist in the tile — levered
  // IRR is absent from the bake by design — so it can only narrow the server-side count and
  // the table, never the map's paint. Trying to fake it client-side would dim parcels on a
  // number the tile does not carry.
  if (!clauses.length) return null;
  return ["all", ...clauses] as FilterSpecification;
}

/** The same state as /map/query parameters, for the "N parcels match" count. */
export function queryParams(state: FilterState): Record<string, string | number | string[]> {
  const params: Record<string, string | number | string[]> = {
    // One row is enough: the count comes from `total`, which is computed before paging.
    limit: 1,
    // Always. The read path has the same premise as the map.
    statuses: ["scored"],
  };
  if (state.wards.length) params.wards = state.wards;
  if (state.prototypes.length) params.prototypes = state.prototypes;
  if (state.rlvMin != null) params.rlv_min = state.rlvMin;
  if (state.rlvMax != null) params.rlv_max = state.rlvMax;
  if (state.irrMin != null) params.irr_min = state.irrMin;
  return params;
}

/** Objectives whose ramp we can read a slider domain from. */
export const RLV_OBJECTIVE = "rlv_total";
export { BIN_FIELD };
