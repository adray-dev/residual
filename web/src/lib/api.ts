/** The HTTP client. Every network call the app makes goes through here.
 *
 * Every path is wrapped in `apiUrl` so a split deployment (static frontend on one host,
 * API on another) works without touching call sites. Same-origin setups configure nothing
 * and get the identical relative URLs they had before. */
import { apiUrl } from "./config";
import type {
  AssumptionSet,
  MapQuery,
  Meta,
  ParcelRecord,
  SearchResult,
  ShortlistDetail,
  ShortlistSummary,
  Underwrite,
  UnderwriteRequest,
} from "./types";

/** A 422 from the underwrite endpoint is an answer ABOUT the parcel, not a fault.
 *
 * Exempt land, historic restriction, unencoded zoning, and "no prototype fits" all come
 * back this way with a plain-language reason, and the panel is supposed to render that
 * sentence where the numbers would go. Distinguishing it from a real failure is the whole
 * reason this class exists — showing "something went wrong" for a parcel that is simply a
 * park would be a lie.
 */
export class NotModellable extends Error {}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    options?: ErrorOptions,
  ) {
    super(message, options);
  }
}

/** FastAPI puts the human-readable message in `detail`; fall back to the status text. */
async function failure(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return "The request was rejected as malformed.";
  } catch {
    /* not JSON — fall through */
  }
  return response.statusText || `HTTP ${response.status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...init,
      headers: { "content-type": "application/json", ...init?.headers },
    });
  } catch (cause) {
    // fetch only rejects on a transport failure — the API being down, not a bad request.
    throw new ApiError("Could not reach the server.", 0, { cause });
  }
  if (!response.ok) {
    const message = await failure(response);
    if (response.status === 422) throw new NotModellable(message);
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

/** SSLs carry literal spaces ("0123    0456"), so the id must be encoded, not interpolated. */
const parcelPath = (parcelId: string) => `/parcel/${encodeURIComponent(parcelId)}`;

export function getMeta(): Promise<Meta> {
  return request<Meta>("/meta");
}

/** SPEC section 2's defaults, which the 1c modal is generated from. Fetched once at boot. */
export function getDefaultAssumptions(): Promise<AssumptionSet> {
  return request<AssumptionSet>("/assumptions/default");
}

/** The table/compare read. Never runs the engine — it is a straight read of the bake.
 *
 * The one exception is `irr_min`, which the server refuses above a bounded set size
 * because filtering by return means running the full model per parcel. That refusal
 * arrives as a 422 with an actionable sentence, so it surfaces as `NotModellable`.
 */
export function getMapQuery(
  params: Record<string, string | number | string[]> = {},
  signal?: AbortSignal,
): Promise<MapQuery> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (Array.isArray(value)) value.forEach((v) => query.append(key, v));
    else query.set(key, String(value));
  }
  return request<MapQuery>(`/map/query?${query}`, { signal });
}

/** The body form of the same read.
 *
 * Exists for one reason: a drawn area is hundreds of coordinates and will not fit in a
 * URL. `with_returns` stays in the query string because that is where the endpoint takes
 * it — it is a shape-of-response flag, not a filter.
 */
export function postMapQuery(
  body: unknown,
  withReturns = false,
  signal?: AbortSignal,
): Promise<MapQuery> {
  const suffix = withReturns ? "?with_returns=true" : "";
  return request<MapQuery>(`/map/query${suffix}`, {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
}

/** The parcel record: everything the popup shows, with no engine run behind it.
 *
 * This is the screening tier, so it stays fast enough to fire on every map click. The
 * full model is a separate, deliberate step the user takes from the popup. */
export function getParcel(parcelId: string, signal?: AbortSignal): Promise<ParcelRecord> {
  return request<ParcelRecord>(parcelPath(parcelId), { signal });
}

/** Typeahead over address, parcel ID, ward and neighborhood. */
export async function searchParcels(q: string, signal?: AbortSignal): Promise<SearchResult[]> {
  const response = await request<{ results: SearchResult[] }>(
    `/parcels/search?q=${encodeURIComponent(q)}&limit=8`,
    { signal },
  );
  return response.results;
}

// --- shortlists ------------------------------------------------------------
// Pure user state. The card metrics are read live from the current bake every time, so a
// list cannot go stale against a re-bake — the opposite of a scenario, which freezes.
export function getShortlists(): Promise<ShortlistSummary[]> {
  return request<ShortlistSummary[]>("/shortlists");
}

export function getShortlist(shortlistId: string): Promise<ShortlistDetail> {
  return request<ShortlistDetail>(`/shortlists/${encodeURIComponent(shortlistId)}`);
}

export function createShortlist(name: string): Promise<ShortlistSummary> {
  return request<ShortlistSummary>("/shortlists", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

async function noContent(path: string, method: string): Promise<void> {
  const response = await fetch(apiUrl(path), { method });
  if (!response.ok) throw new ApiError(await failure(response), response.status);
}

export function addToShortlist(shortlistId: string, parcelId: string): Promise<void> {
  return noContent(
    `/shortlists/${encodeURIComponent(shortlistId)}/parcels/${encodeURIComponent(parcelId)}`,
    "POST",
  );
}

export function removeFromShortlist(shortlistId: string, parcelId: string): Promise<void> {
  return noContent(
    `/shortlists/${encodeURIComponent(shortlistId)}/parcels/${encodeURIComponent(parcelId)}`,
    "DELETE",
  );
}

/** Default-assumption underwrite. Cached server-side, so reopening a parcel is free. */
export function getUnderwrite(
  parcelId: string,
  options: { prototypeId?: string; includeDemolition?: boolean; signal?: AbortSignal } = {},
): Promise<Underwrite> {
  const query = new URLSearchParams();
  if (options.prototypeId) query.set("prototype_id", options.prototypeId);
  if (options.includeDemolition !== undefined) {
    query.set("include_demolition", String(options.includeDemolition));
  }
  const suffix = query.size ? `?${query}` : "";
  return request<Underwrite>(`${parcelPath(parcelId)}/underwrite${suffix}`, {
    signal: options.signal,
  });
}

/** Freeze the current underwrite as a scenario (SPEC 7.1).
 *
 * The body carries INPUTS, never results: the server re-runs and stores its own numbers,
 * so a scenario records what the model said rather than what the client claimed. */
export function saveScenario(
  parcelId: string,
  body: UnderwriteRequest & { name?: string },
): Promise<{ scenario_id: string; parcel_id: string }> {
  return request("/scenario", {
    method: "POST",
    body: JSON.stringify({ ...body, parcel_id: parcelId }),
  });
}

/** The saved scenario's JSON export URL. */
export const scenarioExportUrl = (scenarioId: string) =>
  apiUrl(`/scenario/${encodeURIComponent(scenarioId)}/export`);

/** Download a live Excel workbook of the CURRENT inputs. No saved scenario needed.
 *
 * The server re-runs the engine and builds the file from its own result, so this can never
 * become a spreadsheet of numbers the client was holding. Saving is still available for a
 * scenario worth keeping; it is just not a precondition for getting a workbook. */
export async function exportWorkbook(
  parcelId: string,
  body: UnderwriteRequest,
): Promise<void> {
  const response = await fetch(apiUrl("/export.xlsx"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ...body, parcel_id: parcelId }),
  });
  if (!response.ok) {
    const message = await failure(response);
    if (response.status === 422) throw new NotModellable(message);
    throw new ApiError(message, response.status);
  }

  // The filename is the server's — it is built from the address, and rebuilding it here
  // would be a second place for that rule to drift.
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = match?.[1] ?? "residual-export.xlsx";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** Re-underwrite with edited inputs (the 1c modal -> 1b panel round trip). */
export function postUnderwrite(
  parcelId: string,
  overrides: UnderwriteRequest,
  signal?: AbortSignal,
): Promise<Underwrite> {
  return request<Underwrite>(`${parcelPath(parcelId)}/underwrite`, {
    method: "POST",
    body: JSON.stringify(overrides),
    signal,
  });
}
