/** The 1b metric grid: eight cells, 4 x 2, in the handoff's fixed order.
 *
 * The order is not arbitrary and is not sorted — the top row is the return story (how well
 * does this perform) and the bottom row is the money story (what does it cost and produce).
 * Reordering by value would break the comparison a user makes scanning down two parcels.
 *
 * One cell needs explaining. "Annual return" is the levered IRR measured at the ASSESSED
 * land value, not at the RLV the panel just solved. At the solved RLV the IRR is the
 * hurdle by construction — that is what the solve does — so it would read 17.00% on every
 * parcel in the city and rank nothing. Measuring at the assessed price gives a number that
 * varies and means something ("if you bought at the assessment, this is your return"), but
 * only if the basis is visible. So the basis is rendered under the value rather than
 * hidden in a tooltip: an unlabelled 18.4% next to a solved RLV invites exactly the wrong
 * reading, that it is the return at the price shown above it.
 */
import type { ReturnMetrics } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { money, multiple, percent, NO_VALUE } from "../lib/format";
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
  return {
    key: "irr",
    value: percent(returns.irr),
    note: `at ${returns.irr_basis.toLowerCase()} ${money(returns.irr_basis_value)}`,
  };
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
    { key: "equity_multiple", value: multiple(returns.equity_multiple) },
    { key: "yield_on_cost", value: percent(returns.yield_on_cost) },
    { key: "profit_margin", value: percent(returns.profit_margin) },
    { key: "total_development_cost", value: money(returns.total_development_cost) },
    { key: "cost_per_unit", value: money(returns.cost_per_unit) },
    { key: "noi", value: money(returns.noi) },
    { key: "exit_value", value: money(returns.exit_value) },
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
