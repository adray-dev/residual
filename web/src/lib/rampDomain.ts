/** The numbers printed at the ends of a value range — the legend's ramp and the filter
 * pane's slider track.
 *
 * Both describe the same bake, so both round the same way and from the same function: they
 * sit a few hundred pixels apart, and two different renderings of one domain reads as a bug
 * whichever of them is right.
 *
 * What is rounded is only the LABEL and the slider's reachable bounds. The colour ramp
 * itself is still binned on the true extremes server-side, so "$340M" names a track end,
 * not the value the darkest green is assigned to. That gap is the price of a round number,
 * and it is at most one rounding step.
 */
import { money } from "./format";

/** Outward to a power of ten one order below the domain's magnitude.
 *
 * Derived rather than tabulated, because the two objectives are five orders of magnitude
 * apart: total RLV spans hundreds of millions and rounds to $10M, while RLV per buildable
 * SF spans hundreds of dollars and rounds to $10. A fixed step right for one is absurd for
 * the other, and a new objective would need a new entry in a table nobody would remember.
 */
export function roundedDomain(
  min: number | null | undefined,
  max: number | null | undefined,
): { floor: number; ceiling: number } {
  const low = Number.isFinite(min) ? (min as number) : 0;
  const high = Number.isFinite(max) ? (max as number) : 0;

  const magnitude = Math.max(Math.abs(low), Math.abs(high));
  if (magnitude === 0) return { floor: low, ceiling: high };

  const step = 10 ** (Math.floor(Math.log10(magnitude)) - 1);
  return {
    floor: Math.floor(low / step) * step,
    ceiling: Math.ceil(high / step) * step,
  };
}

/** Money for a rounded end: a decimal where one is meaningful, but no hanging ".0" on a
 *  number that is whole by construction — "-$110.0M" claims a precision it does not have. */
export function domainMoney(value: number): string {
  return money(value, 1).replace(/\.0M$/, "M");
}
