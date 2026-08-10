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
import type { MapQuery } from "./types";
import { getMapQuery, postMapQuery } from "./api";
import type { Ring } from "./drawRing";
import { BIN_FIELD } from "./mapStyle";

export interface FilterState {
  /** Raw `submarket_id`s ("ward_6"). Empty means every ward. */
  wards: string[];
  /** Prototype ids ("garden"). Empty means every build. */
  prototypes: string[];
  /** Screening RLV floor/ceiling in dollars. Null means unbounded. */
  rlvMin: number | null;
  rlvMax: number | null;
  /** Program filters. Each has a tile attribute, so the map narrows with the count. */
  unitsMin: number | null;
  unitsMax: number | null;
  floorsMin: number | null;
  floorsMax: number | null;
  buildingSfMin: number | null;
  buildingSfMax: number | null;
  /** Nothing standing. Mutually informative with the building-area range, not exclusive. */
  vacantOnly: boolean;
  /** The draw-an-area ring. Null means the whole city.
   *
   * The one filter with no tile attribute behind it, and necessarily so: point-in-polygon
   * is not expressible as a MapLibre expression. It is therefore absent from `mapFilter`
   * and the map narrows for it geometrically instead, via the mask in `MapView`. Membership
   * is decided server-side by `ST_Intersects` on real parcel geometry.
   */
  drawnPolygon: Ring | null;
}

// IRR is deliberately NOT a filter. It is absent from the tile — levered IRR is not in the
// bake — so filtering on it can only ever narrow a server count, never the map, and doing
// it at all means running the full model over every match. The API still accepts `irr_min`
// and still bounds it; the client simply does not use it until IRR is in the tile.

export const EMPTY_FILTERS: FilterState = {
  wards: [],
  prototypes: [],
  rlvMin: null,
  rlvMax: null,
  unitsMin: null,
  unitsMax: null,
  floorsMin: null,
  floorsMax: null,
  buildingSfMin: null,
  buildingSfMax: null,
  vacantOnly: false,
  drawnPolygon: null,
};

export function isEmpty(state: FilterState): boolean {
  return (
    state.wards.length === 0 &&
    state.prototypes.length === 0 &&
    state.rlvMin == null &&
    state.rlvMax == null &&
    state.unitsMin == null &&
    state.unitsMax == null &&
    state.floorsMin == null &&
    state.floorsMax == null &&
    state.buildingSfMin == null &&
    state.buildingSfMax == null &&
    !state.vacantOnly &&
    state.drawnPolygon == null
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

  // Program bounds. `coalesce` supplies a sentinel that fails the comparison, so a parcel
  // missing the attribute is excluded rather than swept in by a null.
  const range = (
    attribute: string,
    min: number | null,
    max: number | null,
    missing: number,
  ) => {
    if (min != null) {
      clauses.push([">=", ["coalesce", ["get", attribute], missing], min]);
    }
    if (max != null) {
      clauses.push(["<=", ["coalesce", ["get", attribute], missing], max]);
    }
  };
  range("units", state.unitsMin, state.unitsMax, -1);
  range("floors", state.floorsMin, state.floorsMax, -1);
  // Building area defaults to 0, which is the truthful value: no building recorded.
  range("bldg", state.buildingSfMin, state.buildingSfMax, 0);
  if (state.vacantOnly) {
    clauses.push(["==", ["coalesce", ["get", "bldg"], 0], 0]);
  }

  if (!clauses.length) return null;
  return ["all", ...clauses] as FilterSpecification;
}

/** How the server names these filters. One object, two encodings below, so the GET and
 * POST forms cannot drift — and they must not, because the count and the table would then
 * quietly disagree about what is being counted. */
function serverFilters(state: FilterState): Record<string, unknown> {
  const filters: Record<string, unknown> = {
    // Always. The read path has the same premise as the map.
    statuses: ["scored"],
  };
  if (state.wards.length) filters.wards = state.wards;
  if (state.prototypes.length) filters.prototypes = state.prototypes;
  if (state.rlvMin != null) filters.rlv_min = state.rlvMin;
  if (state.rlvMax != null) filters.rlv_max = state.rlvMax;
  if (state.unitsMin != null) filters.units_min = state.unitsMin;
  if (state.unitsMax != null) filters.units_max = state.unitsMax;
  if (state.floorsMin != null) filters.floors_min = state.floorsMin;
  if (state.floorsMax != null) filters.floors_max = state.floorsMax;
  if (state.buildingSfMin != null) filters.building_sf_min = state.buildingSfMin;
  if (state.buildingSfMax != null) filters.building_sf_max = state.buildingSfMax;
  if (state.vacantOnly) filters.vacant_only = true;
  if (state.drawnPolygon) filters.drawn_polygon = state.drawnPolygon;
  return filters;
}

/** Paging and sort. Separate from the filters because they describe the request, not the
 * set — and because the POST form carries them in the body while `with_returns` stays in
 * the query string, which is a distinction worth having in one place only. */
export interface MapQueryOptions {
  limit?: number;
  offset?: number;
  sortKey?: string;
  sortDir?: "asc" | "desc";
  withReturns?: boolean;
  /** Aggregates over the whole matching set. POST only — the GET form has no such
   * parameter, and the only caller that wants totals is the drawn-area strip, which is
   * on the POST path by definition. */
  includeTotals?: boolean;
}

/** The GET encoding, per SPEC section 10's `GET /map/query?bounds&filters`. */
export function queryParams(
  state: FilterState,
  options: MapQueryOptions = {},
): Record<string, string | number | string[]> {
  const params: Record<string, string | number | string[]> = {
    // One row is enough for a count: `total` is computed before paging.
    limit: options.limit ?? 1,
  };
  for (const [key, value] of Object.entries(serverFilters(state))) {
    if (key === "drawn_polygon") continue; // cannot be a query parameter — see mapQuery
    params[key] = Array.isArray(value)
      ? (value as string[])
      : (value as string | number | boolean).toString();
  }
  if (options.offset) params.offset = options.offset;
  if (options.sortKey) params.sort_key = options.sortKey;
  if (options.sortDir) params.sort_dir = options.sortDir;
  if (options.withReturns) params.with_returns = "true";
  return params;
}

/** The POST encoding. Required once a drawn area is in play. */
export function queryBody(state: FilterState, options: MapQueryOptions = {}): unknown {
  return {
    filters: serverFilters(state),
    limit: options.limit ?? 1,
    offset: options.offset ?? 0,
    ...(options.sortKey ? { sort_key: options.sortKey } : {}),
    ...(options.sortDir ? { sort_dir: options.sortDir } : {}),
    ...(options.includeTotals ? { include_totals: true } : {}),
  };
}

/** Run the read, picking the verb.
 *
 * GET while there is no drawn area, because a URL is inspectable and cacheable and that is
 * worth keeping for the ordinary case. POST once there is one, because a ring is hundreds
 * of coordinates. Both callers — the count in the pane and the table — go through here, so
 * neither can end up on the wrong verb and silently drop the polygon.
 */
export function mapQuery(
  state: FilterState,
  options: MapQueryOptions = {},
  signal?: AbortSignal,
): Promise<MapQuery> {
  if (state.drawnPolygon) {
    return postMapQuery(queryBody(state, options), options.withReturns ?? false, signal);
  }
  return getMapQuery(queryParams(state, options), signal);
}

/** Objectives whose ramp we can read a slider domain from. */
export const RLV_OBJECTIVE = "rlv_total";
export { BIN_FIELD };
