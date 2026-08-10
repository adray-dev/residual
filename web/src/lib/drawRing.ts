/** Ring geometry for the draw-an-area tool.
 *
 * Pure, and separate from the map for the same reason `popupPlacement` is: the tool only
 * exists inside a WebGL canvas that a headless tab never paints, so the one part that can
 * actually be wrong — the geometry — is checked directly (`npm run check:draw`) rather than
 * by clicking around and hoping.
 *
 * Everything here is lon/lat. Planar math on degrees is fine at DC's scale for what these
 * functions decide (does this segment cross that one, is this ring degenerate); the
 * authoritative membership test is `ST_Intersects` on the server, on real geometry.
 */

/** A lon/lat pair, in GeoJSON order. */
export type Position = [number, number];

/** The polygon shape the server accepts. One exterior ring, no holes. */
export interface Ring {
  type: "Polygon";
  coordinates: Position[][];
}

/** The server's cap, mirrored here so the UI stops you before the request does. */
export const MAX_VERTICES = 500;

/** Below this the ring is a point or a line, not an area. Three distinct corners. */
export const MIN_VERTICES = 3;

/** Screen-space radius for "you clicked the first vertex again", in pixels. */
export const CLOSE_HANDLE_PX = 10;

/** Two positions equal to within floating-point noise. ~1e-9° is a tenth of a millimetre. */
function same(a: Position, b: Position): boolean {
  return Math.abs(a[0] - b[0]) < 1e-9 && Math.abs(a[1] - b[1]) < 1e-9;
}

/** Drop consecutive duplicates. A double-click, or a click that does not move the cursor,
 * otherwise plants two vertices in the same spot and makes a zero-length segment that
 * every intersection test then has to special-case. */
export function dedupe(points: Position[]): Position[] {
  const out: Position[] = [];
  for (const point of points) {
    const last = out.at(-1);
    if (!last || !same(last, point)) out.push(point);
  }
  return out;
}

/** The closed ring's edges, as [start, end] pairs — the last one wrapping to the first.
 *
 * Everything below works in edges rather than indices. That is not only tidier: with
 * `noUncheckedIndexedAccess` on, every `points[i + 1]` is a `Position | undefined` that has
 * to be talked out of the type, and the wrap-around is exactly where an off-by-one hides.
 */
function edges(points: Position[]): [Position, Position][] {
  return points.flatMap((a, i) => {
    const b = points[(i + 1) % points.length];
    return b ? [[a, b] as [Position, Position]] : [];
  });
}

/** Twice the signed area. Sign gives winding; zero means every point is collinear. */
export function signedArea(points: Position[]): number {
  let sum = 0;
  for (const [[x1, y1], [x2, y2]] of edges(points)) sum += x1 * y2 - x2 * y1;
  return sum;
}

/** No area to select: fewer than three distinct corners, or all of them on one line.
 *
 * The collinear case is the one worth catching — three clicks along a street look like a
 * shape in progress but enclose nothing, and PostGIS would happily accept the polygon and
 * return zero parcels, which reads as the tool being broken. */
export function isDegenerate(points: Position[]): boolean {
  const clean = dedupe(points);
  if (clean.length < MIN_VERTICES) return true;
  return Math.abs(signedArea(clean)) < 1e-14;
}

/** Do the open segments ab and cd cross? Proper crossings only — segments that merely
 * touch at a shared endpoint are how a ring is built and are not intersections. */
function crosses(a: Position, b: Position, c: Position, d: Position): boolean {
  const side = (p: Position, q: Position, r: Position) =>
    (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
  const d1 = side(a, b, c);
  const d2 = side(a, b, d);
  const d3 = side(c, d, a);
  const d4 = side(c, d, b);
  // Strict signs on both pairs: a zero means collinear or touching, which we allow.
  return ((d1 > 0) !== (d2 > 0)) && ((d3 > 0) !== (d4 > 0));
}

/** Does the closed ring through these points cross itself?
 *
 * A bow tie is a valid GeoJSON literal and an invalid polygon — PostGIS will either error
 * or silently interpret it, neither of which is a good answer to a stray click. Cheaper to
 * refuse to close than to explain afterwards. O(n²), which at a 500-vertex cap is nothing. */
export function selfIntersects(points: Position[]): boolean {
  const clean = dedupe(points);
  if (clean.length < 4) return false;
  const sides = edges(clean);
  const n = sides.length;
  return sides.some(([a, b], i) =>
    sides.some(([c, d], j) => {
      // Only each unordered pair once, and never two edges that share an endpoint —
      // neighbours touch by construction, and the first and last edge do too.
      if (j <= i) return false;
      if ((i + 1) % n === j || (j + 1) % n === i) return false;
      return crosses(a, b, c, d);
    }),
  );
}

/** Why a set of clicks cannot become a polygon yet, or null if it can. */
export function ringProblem(points: Position[]): string | null {
  const clean = dedupe(points);
  if (clean.length < MIN_VERTICES) return "An area needs at least three corners.";
  if (clean.length > MAX_VERTICES) {
    return `An area can have at most ${MAX_VERTICES} corners.`;
  }
  // Self-intersection is tested FIRST, and the order is not cosmetic. A bow tie's two
  // lobes have opposite winding, so its signed area cancels to zero and the degeneracy
  // test claims it — telling the user their corners are "all in a line" when they are
  // plainly not. Both refuse the ring; only one of them explains it.
  if (selfIntersects(clean)) return "The outline crosses itself.";
  if (isDegenerate(clean)) return "Those corners are all in a line — they enclose no area.";
  return null;
}

/** Close a click sequence into a GeoJSON Polygon, or return null if it is not one.
 *
 * The first position is repeated as the last, per RFC 7946 — the server checks for it, so
 * it is done here rather than left to the wire format to imply. */
export function closeRing(points: Position[]): Ring | null {
  const clean = dedupe(points);
  const first = clean.at(0);
  if (!first || ringProblem(clean)) return null;
  return { type: "Polygon", coordinates: [[...clean, first]] };
}

/** The world with the ring punched out of it, for the mask layer.
 *
 * A drawn area cannot be a MapLibre filter — point-in-polygon is not expressible over tile
 * attributes — so the map narrows geometrically instead: this covers everything and leaves
 * a hole where the selection is. Same visual grammar as the dim layer, no attribute needed.
 *
 * The outer ring is wound counter-clockwise and the hole clockwise, which is what RFC 7946
 * asks for and what MapLibre's tessellator expects for a hole to actually be a hole. */
export function maskFor(ring: Ring): Ring {
  const world: Position[] = [
    [-180, -85],
    [180, -85],
    [180, 85],
    [-180, 85],
    [-180, -85],
  ];
  const hole = ring.coordinates.at(0) ?? [];
  // `signedArea` on the closed ring: positive is counter-clockwise, so reverse when the
  // user happened to draw that way.
  const inner = signedArea(hole.slice(0, -1)) > 0 ? [...hole].reverse() : hole;
  return { type: "Polygon", coordinates: [world, inner] };
}

/** Screen distance, for the click-the-first-vertex-to-close test. */
export function withinHandle(
  a: { x: number; y: number },
  b: { x: number; y: number },
  radius = CLOSE_HANDLE_PX,
): boolean {
  return Math.hypot(a.x - b.x, a.y - b.y) <= radius;
}
