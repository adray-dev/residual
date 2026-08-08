/** Editing assumptions: unit conversion, and what counts as a change.
 *
 * The wire carries fractions (`soft_cost_pct` is 0.2) and the modal shows percentages
 * (20%). That conversion is the single most dangerous thing in this screen — get it
 * backwards and the user silently runs a model 100x off — so it lives in one place, is
 * driven by the unit kind the SERVER declares per input, and round-trips through
 * `toDisplay`/`fromDisplay` only.
 */
import type { AssumptionGroups } from "./types";

/** The six groups `build_assumptions` will actually merge, in the modal's nav order. */
export const EDITABLE_GROUPS = [
  "timeline",
  "cost",
  "revenue",
  "debt",
  "exit",
  "envelope",
] as const;

export type EditableGroup = (typeof EDITABLE_GROUPS)[number];

/** Overrides as the API wants them: group -> key -> value, in wire units. */
export type Overrides = Partial<Record<EditableGroup, Record<string, number>>>;

/** Wire value -> what the field shows. Percentages are the only kind that scales. */
export function toDisplay(value: number, kind: string | undefined): number {
  return kind === "percent" ? round(value * 100, 4) : value;
}

/** What the user typed -> the wire value. Exactly the inverse of `toDisplay`. */
export function fromDisplay(value: number, kind: string | undefined): number {
  return kind === "percent" ? round(value / 100, 8) : value;
}

/** Kill float dust so 0.055 * 100 shows as 5.5 rather than 5.500000000000001. */
function round(value: number, places: number): number {
  const factor = 10 ** places;
  return Math.round(value * factor) / factor;
}

/** How a field is rendered and typed: suffix, and how many decimals it shows. */
export function unitOf(kind: string | undefined): { suffix: string; step: number } {
  switch (kind) {
    case "percent":
      return { suffix: "%", step: 0.1 };
    case "money":
      return { suffix: "$", step: 1000 };
    case "rate":
      return { suffix: "$", step: 0.1 };
    case "months":
      return { suffix: "mo", step: 1 };
    case "years":
      return { suffix: "yr", step: 1 };
    default:
      return { suffix: "", step: 0.01 };
  }
}

/** Inputs the modal renders for a group: only keys the server both labels AND accepts.
 *
 * Driven by /assumptions/default rather than a hard-coded list, so an assumption added to
 * the engine appears here automatically and one the engine drops disappears — the modal
 * can never offer an input that `build_assumptions` would silently ignore. */
export function fieldsFor(
  group: EditableGroup,
  defaults: AssumptionGroups,
  assumptionLabels: Record<string, string>,
): string[] {
  const values = defaults[group] ?? {};
  return Object.keys(values).filter(
    (key) => key in assumptionLabels && typeof values[key] === "number",
  );
}

/** Only values that actually differ from default are sent.
 *
 * The server drops a "change" equal to the default anyway, so sending them would just make
 * the cache key noisier and the "N changed" count wrong. */
export function diffFromDefaults(
  working: Record<string, Record<string, number>>,
  defaults: AssumptionGroups,
): Overrides {
  const out: Overrides = {};
  for (const group of EDITABLE_GROUPS) {
    const edited = working[group];
    const base = defaults[group];
    if (!edited || !base) continue;
    for (const [key, value] of Object.entries(edited)) {
      if (base[key] !== value) {
        (out[group] ??= {})[key] = value;
      }
    }
  }
  return out;
}

export function changeCount(overrides: Overrides): number {
  return Object.values(overrides).reduce((n, group) => n + Object.keys(group ?? {}).length, 0);
}

/** A deep-enough copy of the editable groups to edit freely. */
export function workingCopy(defaults: AssumptionGroups): Record<string, Record<string, number>> {
  const out: Record<string, Record<string, number>> = {};
  for (const group of EDITABLE_GROUPS) {
    const values = defaults[group] ?? {};
    out[group] = Object.fromEntries(
      Object.entries(values).filter(([, v]) => typeof v === "number"),
    ) as Record<string, number>;
  }
  return out;
}

/** Re-apply saved overrides onto a fresh working copy, so reopening the modal shows the
 * edits that are currently in effect rather than resetting to defaults. */
export function applyOverrides(
  working: Record<string, Record<string, number>>,
  overrides: Overrides,
): Record<string, Record<string, number>> {
  for (const group of EDITABLE_GROUPS) {
    const supplied = overrides[group];
    if (!supplied) continue;
    Object.assign((working[group] ??= {}), supplied);
  }
  return working;
}
