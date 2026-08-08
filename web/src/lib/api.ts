/** The HTTP client. Every network call the app makes goes through here. */
import type {
  AssumptionSet,
  MapQuery,
  Meta,
  ParcelRecord,
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
    response = await fetch(path, {
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

/** The parcel record: everything the popup shows, with no engine run behind it.
 *
 * This is the screening tier, so it stays fast enough to fire on every map click. The
 * full model is a separate, deliberate step the user takes from the popup. */
export function getParcel(parcelId: string, signal?: AbortSignal): Promise<ParcelRecord> {
  return request<ParcelRecord>(parcelPath(parcelId), { signal });
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
