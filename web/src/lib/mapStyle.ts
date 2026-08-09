/** The map's colour contract, as MapLibre expressions.
 *
 * Nothing here computes a value. The bake wrote a bin per objective into the tile
 * (`bin` / `bin_sf` / `bin_gap`) precisely so colouring is a lookup and switching
 * objectives needs no server call — SPEC §9 forbids the read path from dividing. So these
 * expressions only ever `match` on an integer that is already in the tile.
 *
 * The bin encoding, from `tiles/build_tiles.py`:
 *   0        unscored — the parcel has no value on this objective
 *   -4..-1   below zero, -4 deepest
 *   1..4     at or above zero, 4 strongest
 *
 * Eight value bins onto the handoff's eight ramp stops. The first four stops are the
 * neutral/pale half and carry the negative arm, the last four are the teal half and carry
 * the positive arm — so the primary read of the map is "does this pencil?", and the
 * quantile detail lives inside each arm rather than competing with that.
 */
import type { ExpressionSpecification } from "maplibre-gl";

/** The teal sequential ramp. NOT the map's value ramp any more — it still dresses the
 * sources & uses bars (parts of one magnitude) and the shortlist card headers, where a
 * single hue light-to-dark is the right encoding. */
export const RAMP = [
  "#edeae4",
  "#dce9e6",
  "#bedcd7",
  "#93c9c3",
  "#5faea8",
  "#2c918c",
  "#0e7c7b",
  "#0a5250",
] as const;

/** The map's DIVERGING value ramp: magenta below $0, green above. 8 stops, low -> high.
 *
 * The old ramp was a single teal hue, so both arms sat on the same scale and the negative
 * half — 56% of scored DC parcels — collapsed into pales barely separable from the canvas.
 * A diverging measure needs two hues meeting at a light midpoint, which is what this is.
 *
 * These are ColorBrewer's PiYG, chosen over a hand-picked green/pink because the obvious
 * pairing fails colour-vision checks badly: a saturated green against a saturated pink
 * separated by only ΔE 5.7 under deuteranopia, which would make "loses money" and "makes
 * money" the same colour for roughly one man in twenty. PiYG separates at ΔE 11.9 deutan
 * and 35.7 in normal vision — verified with the palette validator, not eyeballed.
 */
export const VALUE_RAMP = [
  "#c51b7d",  // deepest negative
  "#de77ae",
  "#f1b6da",
  "#fde0ef",  // just below $0
  "#e6f5d0",  // just above $0
  "#b8e186",
  "#7fbc41",
  "#4d9221",  // strongest positive
] as const;

/** Land the model cannot price, in neutrals.
 *
 * Two rules govern these. They must sit outside the value ramp so unscored land never
 * reads as a value — and now that the ramp OWNS magenta, historic can no longer be the
 * mauve it was, or "restricted" and "loses money" would be the same colour. They are also
 * deliberately desaturated: these parcels are context, not the story, and greys let the
 * ramp carry the eye. Identity comes from the legend label and, for two of them, texture.
 *
 * `infeasible` and `historic` are the only two solid fills, so they are the pair a reader
 * must actually tell apart — separated here to ΔE 20.6 in normal vision, well clear of the
 * 15 floor the earlier pairing failed.
 */
export const STATUS_COLORS = {
  infeasible: "#ada79e",
  exempt: "#c3cbce",
  exempt_alt: "#d6dcde",
  historic: "#5c574f",
  zone_not_encoded: "#ffffff",
  zone_not_encoded_border: "#9a958c",
} as const;

/** Every parcel carries this hairline, which is what separates lots at close zoom. */
export const PARCEL_BORDER = "rgba(255,255,255,.85)";

/** Objective key (as /meta names it) -> the tile attribute holding its bin. */
export const BIN_FIELD: Record<string, string> = {
  rlv_total: "bin",
  rlv_per_buildable_sf: "bin_sf",
  gap: "bin_gap",
};

/** Objective key -> the metric key its label lives under in the served vocabulary.
 *
 * These differ for exactly one objective: the map calls it `gap`, SPEC calls the metric
 * `feasibility_gap`. Mapping it here beats renaming either. */
export const OBJECTIVE_METRIC: Record<string, string> = {
  rlv_total: "rlv_total",
  rlv_per_buildable_sf: "rlv_per_buildable_sf",
  gap: "feasibility_gap",
};

/** Fill colour for scored parcels: a match on the pre-baked bin, nothing computed. */
export function valueRamp(objective: string): ExpressionSpecification {
  const field = BIN_FIELD[objective] ?? "bin";
  return [
    "match",
    ["get", field],
    -4, VALUE_RAMP[0],
    -3, VALUE_RAMP[1],
    -2, VALUE_RAMP[2],
    -1, VALUE_RAMP[3],
    1, VALUE_RAMP[4],
    2, VALUE_RAMP[5],
    3, VALUE_RAMP[6],
    4, VALUE_RAMP[7],
    // Bin 0 is "unscored on this objective" — a scored parcel can still have no
    // feasibility gap, because gap needs an assessed land value the parcel may not have.
    // It gets the ramp's lightest step rather than a value colour it has not earned.
    VALUE_RAMP[3],
  ] as ExpressionSpecification;
}

/** The legend bar, mirroring the diverging ramp stop for stop. */
export const LEGEND_GRADIENT =
  "linear-gradient(90deg,#c51b7d,#de77ae,#f1b6da,#fde0ef,#e6f5d0,#b8e186,#7fbc41,#4d9221)";

/** A 6px 45-degree hatch for exempt land, matching the handoff's repeating gradient.
 *
 * MapLibre has no CSS gradients, so the pattern is drawn once to a canvas and registered
 * as a sprite image. Exempt parcels are the one status the handoff gives a texture rather
 * than a flat fill — it reads as "not part of the analysis" at a glance, which is exactly
 * what public and tax-exempt land is.
 */
export function hatchImage(size = 6): ImageData {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2d canvas context unavailable — cannot build the map pattern");

  ctx.fillStyle = STATUS_COLORS.exempt_alt;
  ctx.fillRect(0, 0, size, size);
  ctx.strokeStyle = STATUS_COLORS.exempt;
  ctx.lineWidth = size / 2;
  // Two strokes so the diagonal band wraps seamlessly across the tile edge.
  ctx.beginPath();
  ctx.moveTo(-size, size);
  ctx.lineTo(size, -size);
  ctx.moveTo(0, size * 2);
  ctx.lineTo(size * 2, 0);
  ctx.stroke();

  return ctx.getImageData(0, 0, size, size);
}
