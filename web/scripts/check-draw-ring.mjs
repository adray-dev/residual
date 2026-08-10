/**
 * Geometry check for the draw-an-area tool.
 *
 * Same reason as the popup check: the tool lives inside a WebGL canvas a headless tab never
 * paints, so the part that can actually be wrong is checked directly.
 *
 * Run: npm run check:draw
 */
import {
  closeRing,
  dedupe,
  isDegenerate,
  maskFor,
  ringProblem,
  selfIntersects,
  signedArea,
  withinHandle,
  MAX_VERTICES,
} from "../src/lib/drawRing.ts";

let failures = 0;

function check(name, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (!ok) failures++;
  console.log(
    `${ok ? "ok  " : "FAIL"} ${name.padEnd(52)}` +
      (ok ? "" : `  got ${JSON.stringify(actual)} want ${JSON.stringify(expected)}`),
  );
}

// A block-sized square in Shaw, drawn clockwise on screen.
const SQUARE = [
  [-77.02, 38.91],
  [-77.01, 38.91],
  [-77.01, 38.92],
  [-77.02, 38.92],
];

console.log("degenerate rings — these enclose nothing and must never reach PostGIS");
check("two clicks", isDegenerate(SQUARE.slice(0, 2)), true);
check("one click", isDegenerate(SQUARE.slice(0, 1)), true);
check("no clicks", isDegenerate([]), true);
check(
  "three collinear clicks along a street",
  isDegenerate([
    [-77.03, 38.9],
    [-77.02, 38.9],
    [-77.01, 38.9],
  ]),
  true,
);
check(
  "the same point clicked three times",
  isDegenerate([
    [-77.02, 38.91],
    [-77.02, 38.91],
    [-77.02, 38.91],
  ]),
  true,
);
check("an actual square", isDegenerate(SQUARE), false);
check("a triangle", isDegenerate(SQUARE.slice(0, 3)), false);

console.log("\nduplicate clicks — a double-click must not plant two vertices");
check(
  "consecutive duplicates collapse",
  dedupe([SQUARE[0], SQUARE[0], SQUARE[1], SQUARE[1], SQUARE[1], SQUARE[2]]).length,
  3,
);
check(
  "a repeat that is NOT consecutive is kept",
  dedupe([SQUARE[0], SQUARE[1], SQUARE[0]]).length,
  3,
);

console.log("\nself-intersection — a bow tie is valid GeoJSON and an invalid polygon");
const BOW_TIE = [
  [-77.02, 38.91],
  [-77.01, 38.92],
  [-77.01, 38.91],
  [-77.02, 38.92],
];
check("bow tie", selfIntersects(BOW_TIE), true);
check("square", selfIntersects(SQUARE), false);
check("triangle", selfIntersects(SQUARE.slice(0, 3)), false);
// The classic false positive: adjacent segments share an endpoint, which is a touch, not
// a crossing. A test that used non-strict signs would call every ring self-intersecting.
check(
  "an L, whose segments touch at the corner",
  selfIntersects([
    [-77.02, 38.9],
    [-77.0, 38.9],
    [-77.0, 38.92],
    [-77.01, 38.92],
    [-77.01, 38.91],
    [-77.02, 38.91],
  ]),
  false,
);
// A concave shape is a normal thing to draw around a block face and must be allowed.
check(
  "a concave C",
  selfIntersects([
    [-77.03, 38.9],
    [-77.0, 38.9],
    [-77.0, 38.905],
    [-77.02, 38.905],
    [-77.02, 38.915],
    [-77.0, 38.915],
    [-77.0, 38.92],
    [-77.03, 38.92],
  ]),
  false,
);

console.log("\nclosing");
const ring = closeRing(SQUARE);
check("closes into a Polygon", ring?.type, "Polygon");
check("one ring, no holes", ring?.coordinates.length, 1);
check("first position repeated as last", ring?.coordinates[0].length, SQUARE.length + 1);
check(
  "and it is literally the first position",
  ring?.coordinates[0].at(-1),
  ring?.coordinates[0][0],
);
check("a bow tie refuses to close", closeRing(BOW_TIE), null);
check("two clicks refuse to close", closeRing(SQUARE.slice(0, 2)), null);
check(
  "over the vertex cap refuses to close",
  closeRing(
    Array.from({ length: MAX_VERTICES + 1 }, (_, i) => [
      -77.02 + 0.01 * Math.cos((2 * Math.PI * i) / (MAX_VERTICES + 1)),
      38.91 + 0.01 * Math.sin((2 * Math.PI * i) / (MAX_VERTICES + 1)),
    ]),
  ),
  null,
);
check("at the cap it still closes", closeRing(
  Array.from({ length: MAX_VERTICES }, (_, i) => [
    -77.02 + 0.01 * Math.cos((2 * Math.PI * i) / MAX_VERTICES),
    38.91 + 0.01 * Math.sin((2 * Math.PI * i) / MAX_VERTICES),
  ]),
)?.type, "Polygon");

console.log("\nthe message shown while drawing");
check("three corners minimum", ringProblem(SQUARE.slice(0, 2)) !== null, true);
check("a good square has no problem", ringProblem(SQUARE), null);
// The bow tie is the reason `ringProblem` tests crossing before degeneracy: its two lobes
// cancel to zero signed area, so the degeneracy test claims it and blames collinearity.
check("the bow tie names itself", ringProblem(BOW_TIE), "The outline crosses itself.");
check("...and it really does read as zero-area", isDegenerate(BOW_TIE), true);

console.log("\nthe mask — the map narrows geometrically, since a polygon is not a filter");
const mask = maskFor(ring);
check("outer ring plus one hole", mask.coordinates.length, 2);
check("the hole has the drawn ring's positions", mask.coordinates[1].length,
  ring.coordinates[0].length);
// Winding decides whether MapLibre tessellates the second ring as a hole or as a second
// island. Outer counter-clockwise, hole clockwise, per RFC 7946.
check("outer ring winds counter-clockwise", signedArea(mask.coordinates[0].slice(0, -1)) > 0, true);
check("hole winds clockwise", signedArea(mask.coordinates[1].slice(0, -1)) < 0, true);
// Drawn the other way round, the hole must still come out clockwise.
const reversedRing = closeRing([...SQUARE].reverse());
check(
  "hole is clockwise however the user drew it",
  signedArea(maskFor(reversedRing).coordinates[1].slice(0, -1)) < 0,
  true,
);

console.log("\nclosing by clicking the first vertex");
check("dead on", withinHandle({ x: 100, y: 100 }, { x: 100, y: 100 }), true);
check("within the handle", withinHandle({ x: 100, y: 100 }, { x: 106, y: 107 }), true);
check("outside the handle", withinHandle({ x: 100, y: 100 }, { x: 120, y: 100 }), false);

console.log(`\n${failures === 0 ? "ALL PASS" : `${failures} FAILED`}`);
process.exit(failures ? 1 : 0);
