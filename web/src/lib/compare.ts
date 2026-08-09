/** The compare set, and which column wins what.
 *
 * Comparison is a FULL-tier read: annual return and equity multiple do not exist in the
 * screening layer (SPEC §9 keeps levered IRR out of the bake on purpose), so each column is
 * a real `/parcel/{id}/underwrite` run rather than a row off the map query.
 */
import type { Underwrite } from "./types";

/** The handoff caps comparison at three, and the layout is built for exactly that. */
export const MAX_COMPARE = 3;

/** Each column owns a color BY POSITION, not by rank.
 *
 * This is deliberate and the handoff calls it out: if the best column were always teal,
 * the eye would read column order as ranking. Fixed positional color means the superlative
 * tags — which do follow the data — are the only thing saying who wins. */
export const COLUMN_COLORS = [
  { key: "teal", solid: "#0e7c7b", tint: "#eaf2f1", text: "#0a5250" },
  { key: "slate", solid: "#3e6e93", tint: "#e9eef4", text: "#2d5473" },
  { key: "amber", solid: "#c08a3e", tint: "#fbf0e4", text: "#8a5a21" },
] as const;

export function toggleCompare(ids: string[], parcelId: string): string[] {
  if (ids.includes(parcelId)) return ids.filter((id) => id !== parcelId);
  if (ids.length >= MAX_COMPARE) return ids;
  return [...ids, parcelId];
}

/** Superlatives, awarded per metric to whichever column actually wins it.
 *
 * A column can earn several or none. The handoff's mock happens to show one each, but
 * hard-coding that would mean labeling a column "Highest return" because of where it sits
 * rather than what it earned.
 */
export interface Superlative {
  label: string;
  /** Index into the compared set. */
  winner: number;
}

export function superlatives(rows: Underwrite[]): Superlative[] {
  const out: Superlative[] = [];

  const best = (
    label: string,
    value: (row: Underwrite) => number | null | undefined,
    prefer: "max" | "min",
  ) => {
    let winner = -1;
    let bestValue: number | null = null;
    rows.forEach((row, index) => {
      const candidate = value(row);
      if (candidate == null || !Number.isFinite(candidate)) return;
      if (
        bestValue === null ||
        (prefer === "max" ? candidate > bestValue : candidate < bestValue)
      ) {
        bestValue = candidate;
        winner = index;
      }
    });
    // With one column everything is trivially the best; a tag would be noise.
    if (winner >= 0 && rows.length > 1) out.push({ label, winner });
  };

  best("Best feasibility value", (r) => r.feasibility_value.full, "max");
  best("Highest return", (r) => r.returns.irr, "max");
  best("Cheapest basis", (r) => r.returns.cost_per_unit, "min");
  return out;
}

export function tagsFor(index: number, all: Superlative[]): string[] {
  return all.filter((s) => s.winner === index).map((s) => s.label);
}
