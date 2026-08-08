/** Number formatting for the UI.
 *
 * Two rules from the handoff are enforced here rather than left to call sites, because a
 * single slip is a wrong number on screen:
 *
 *   - Confidence is a PERCENTAGE (5.8%), never the 0.058 the wire carries.
 *   - A missing value renders as an em dash, never as 0, "N/A", or "null". The engine
 *     returns null for genuinely undefined quantities — IRR that did not converge, cost
 *     per unit on a zero-unit program — and showing 0 for those would be a claim the
 *     model never made.
 */

/** What every formatter renders when the engine had no number to give. */
export const NO_VALUE = "—";

/** "$1.72M" / "$425K" / "$633" — the handoff's compact money, used in the metric grid. */
export function money(value: number | null | undefined, decimals = 2): string {
  if (value == null || !Number.isFinite(value)) return NO_VALUE;
  const sign = value < 0 ? "-" : "";
  const magnitude = Math.abs(value);

  // Thresholds are chosen so the compacted number keeps 3 significant figures: $1.72M,
  // $425K. Rounding is applied AFTER picking the unit so 999,999 renders as $1.00M rather
  // than the misleading $1000K.
  if (magnitude >= 1e6) return `${sign}$${(magnitude / 1e6).toFixed(decimals)}M`;
  if (magnitude >= 1e3) return `${sign}$${Math.round(magnitude / 1e3)}K`;
  return `${sign}$${magnitude.toFixed(0)}`;
}

/** "$1,720,400" — exact money, for tooltips and the record tab where precision matters. */
export function moneyExact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return NO_VALUE;
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

/** 0.184 -> "18.4%". Takes the wire's FRACTION, never a pre-multiplied percentage. */
export function percent(value: number | null | undefined, decimals = 1): string {
  if (value == null || !Number.isFinite(value)) return NO_VALUE;
  return `${(value * 100).toFixed(decimals)}%`;
}

/** 1.71 -> "1.71x". The handoff renders equity multiple with a trailing multiplication sign. */
export function multiple(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return NO_VALUE;
  return `${value.toFixed(2)}×`;
}

/** "30,000" — areas and counts, always grouped so columns of digits line up. */
export function count(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return NO_VALUE;
  return Math.round(value).toLocaleString("en-US");
}

/** "$3.20" — per-SF rents, which are small enough that compacting would destroy them. */
export function rate(value: number | null | undefined, decimals = 2): string {
  if (value == null || !Number.isFinite(value)) return NO_VALUE;
  return `$${value.toFixed(decimals)}`;
}

/** Confidence, and ONLY as a percentage. `confidence` on the wire is a 0-1 fraction. */
export function confidence(value: number | null | undefined): string {
  return percent(value, 1);
}
