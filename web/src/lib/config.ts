/** Where the API lives.
 *
 * Empty in development and in any same-origin deployment, which is what the Vite proxy and
 * the FastAPI-serves-everything setup both are: a bare `/meta` resolves against the page's
 * own origin and nothing needs configuring.
 *
 * Set `VITE_API_BASE` when the two are split — a static frontend on one host and the API on
 * another, which is what deploying `web/` to Vercel means. It is read at BUILD time (Vite
 * inlines `import.meta.env`), so changing it requires a redeploy, not just a restart.
 *
 * Every URL the client builds goes through `apiUrl`. That is the point: a fetch that forgets
 * the base does not fail loudly in production, it quietly 404s against the static host and
 * looks like a broken API.
 */
const RAW = import.meta.env.VITE_API_BASE ?? "";

/** No trailing slash, so `apiUrl("/meta")` cannot produce a double slash. */
export const API_BASE = RAW.replace(/\/+$/, "");

/** Absolute when a base is configured, unchanged when it is not. */
export function apiUrl(path: string): string {
  return API_BASE ? `${API_BASE}${path}` : path;
}

/** Resolve a URL the API handed us — today that is `/meta`'s `tileset_url`.
 *
 * The tileset is served by the API host, not the static one, so a relative path from /meta
 * has to resolve against the API base rather than `window.location`. Absolute URLs pass
 * through untouched, which is what happens once tiles move to object storage.
 */
export function resolveApiHref(href: string): string {
  if (/^https?:\/\//i.test(href)) return href;
  return apiUrl(href);
}
