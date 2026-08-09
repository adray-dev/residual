/** The 1b metric grid: the five figures the drill-down leads on.
 *
 * The order is fixed, not sorted — return first, then what it costs and produces.
 * Reordering by value would break the comparison a user makes scanning two parcels.
 *
 * IRR is measured at the ASSESSED land value, not at the RLV the panel just solved. At the
 * solved RLV it is the hurdle by construction, so it would read 17.00% on every parcel in
 * the city and rank nothing. Measuring at the assessed price gives a number that varies and
 * can be the primary metric. The basis is no longer captioned under the value — the
 * computation is unchanged, only the annotation is gone.
 */
import type { ReturnMetrics } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { money, percent, NO_VALUE } from "../lib/format";
import styles from "./MetricGrid.module.css";

interface Cell {
  /** Metric key — the label comes from the server vocabulary, never hard-coded. */
  key: string;
  value: string;
  note?: string;
  /** Renders the note in amber: the number is real but qualified. */
  warning?: boolean;
}

/** The IRR cell, which has three distinct states and must not blur them together. */
function returnCell(returns: ReturnMetrics): Cell {
  // Nothing reaches the hurdle even at a land price of zero (SPEC fix #8). The solved RLV
  // is meaningless for this parcel, and saying so is more useful than a dash.
  if (returns.irr_target_unachievable) {
    return {
      key: "irr",
      value: NO_VALUE,
      note: `Does not reach ${percent(returns.target_return, 0)} at any land price`,
      warning: true,
    };
  }
  // No CAMA row — exempt or untaxed land has no assessed value to measure against (519
  // scored parcels). `irr_basis` already carries the server's phrasing for this, so it is
  // rendered rather than reworded here: the basis line is the one place the wire and the
  // UI must agree, and a second copy of the sentence is a second thing to drift.
  if (returns.irr == null) {
    return { key: "irr", value: NO_VALUE, note: returns.irr_basis };
  }
  // The basis is no longer captioned. It is still the assessed land value — that is what
  // makes IRR vary per parcel instead of reading as the hurdle on every one — but the
  // caption was explaining a modeling choice at the cost of the number's legibility.
  return { key: "irr", value: percent(returns.irr) };
}

export function MetricGrid({
  returns,
  vocab,
}: {
  returns: ReturnMetrics;
  vocab: Vocabulary;
}) {
  const cells: Cell[] = [
    returnCell(returns),
    { key: "yield_on_cost", value: percent(returns.yield_on_cost) },
    { key: "total_development_cost", value: money(returns.total_development_cost) },
    { key: "cost_per_unit", value: money(returns.cost_per_unit) },
    { key: "noi", value: money(returns.noi) },
  ];

  return (
    <div className={styles.grid} role="list" aria-label="Underwriting metrics">
      {cells.map((cell) => (
        <div className={styles.cell} key={cell.key} role="listitem">
          <span className={`micro-label ${styles.label}`}>{vocab.metric(cell.key)}</span>
          <span
            className={`${styles.value} ${cell.value === NO_VALUE ? styles.missing : ""}`}
          >
            {cell.value}
          </span>
          {cell.note && (
            <span className={`${styles.note} ${cell.warning ? styles.warning : ""}`}>
              {cell.note}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
