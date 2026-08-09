/**
 * Validate the map's paint expressions against MapLibre's own style spec.
 *
 * A malformed expression does not throw at build time and does not throw at import time —
 * it fails when MapLibre parses the style, which in a headless tab never happens because
 * the map cannot render there at all. This is the only way to catch one before a human
 * opens the page.
 *
 * Run: npm run check:map
 */
import { validateStyleMin } from "@maplibre/maplibre-gl-style-spec";
import { valueRamp, FILL_OPACITY, STATUS_COLORS, PARCEL_BORDER } from "../src/lib/mapStyle.ts";

const style = {
  version: 8,
  sources: { parcels: { type: "vector", tiles: ["http://x/{z}/{x}/{y}.pbf"] } },
  layers: [
    { id: "canvas", type: "background", paint: { "background-color": "#f4f2ed" } },
    { id: "value", type: "fill", source: "parcels", "source-layer": "parcels",
      filter: ["==", ["get", "status"], "scored"],
      paint: { "fill-color": valueRamp("rlv_total"), "fill-opacity": FILL_OPACITY } },
    { id: "value-sf", type: "fill", source: "parcels", "source-layer": "parcels",
      paint: { "fill-color": valueRamp("rlv_per_buildable_sf"), "fill-opacity": FILL_OPACITY } },
    { id: "infeasible", type: "fill", source: "parcels", "source-layer": "parcels",
      paint: { "fill-color": STATUS_COLORS.infeasible, "fill-opacity": FILL_OPACITY } },
    { id: "border", type: "line", source: "parcels", "source-layer": "parcels",
      paint: { "line-color": PARCEL_BORDER, "line-width": 1,
               "line-opacity": ["interpolate", ["linear"], ["zoom"], 11, 0, 13, 1] } },
  ],
};

const errors = validateStyleMin(style);
if (errors.length) {
  for (const e of errors) console.log("FAIL", e.message);
  process.exit(1);
}
console.log("style expressions valid");

// And check the ramp actually returns three distinct colors below z12 and eight above.
const coarse = valueRamp("rlv_total")[2];
const fine = valueRamp("rlv_total")[4];
const colorsOf = (m) => new Set(m.slice(2).filter((_, i) => i % 2 === 1));
console.log("coarse distinct colors:", colorsOf(coarse).size, [...colorsOf(coarse)].join(" "));
console.log("fine   distinct colors:", colorsOf(fine).size);
console.log("switch zoom:", valueRamp("rlv_total")[3]);

if (colorsOf(coarse).size !== 3) {
  console.log("FAIL coarse ramp should collapse to three bands");
  process.exit(1);
}
if (colorsOf(fine).size !== 8) {
  console.log("FAIL fine ramp should keep all eight quantile stops");
  process.exit(1);
}
console.log("ALL PASS");
