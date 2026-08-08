/** Sources & uses: the same money counted two ways, so the two totals must match.
 *
 * Drawn as labelled rows on a shared track rather than one segmented bar. Every line item
 * carries its own name and figure, which is what the reader actually wants ("how much is
 * land?"), and it keeps a $10M sliver readable — in a single stacked bar the contingency
 * segment is a few pixels wide and effectively unlabelable.
 *
 * The track is the group total, so all bars share one baseline and one scale and lengths
 * compare directly, both down a column and between the two groups.
 *
 * Colour is a sequential teal ramp, not a categorical set: these are parts of one
 * magnitude, not independent identities, and every row is already directly labelled, so
 * hue is carrying grouping rather than meaning. Equity is the exception — it takes the
 * handoff's amber, the same colour it has in the S-curve, because it is the one line a
 * developer tracks across both charts.
 */
import type { SourcesUses as SourcesUsesData } from "../lib/types";
import { money } from "../lib/format";
import { RAMP } from "../lib/mapStyle";
import styles from "./SourcesUses.module.css";

/** Fixed display order and copy. Order is the money's order, never the values' rank —
 * re-sorting by size would repaint the chart every time an assumption changed. */
const USES: [string, string, string][] = [
  ["construction", "Construction", RAMP[7]],
  ["soft_costs", "Soft costs", RAMP[6]],
  ["contingency", "Contingency", RAMP[5]],
  ["land", "Land", RAMP[4]],
  ["loan_interest", "Loan interest", RAMP[3]],
];

const SOURCES: [string, string, string][] = [
  ["construction_loan", "Construction loan", RAMP[6]],
  ["equity", "Equity", "#c08a3e"],
];

function Group({
  title,
  items,
  values,
  total,
}: {
  title: string;
  items: [string, string, string][];
  values: Record<string, number>;
  total: number;
}) {
  return (
    <div className={styles.group}>
      <div className={styles.groupHead}>
        <span className="micro-label">{title}</span>
        <span className={styles.total}>{money(total)}</span>
      </div>
      {items.map(([key, label, color]) => {
        const value = values[key];
        if (value == null) return null;
        const pct = total > 0 ? Math.min(100, (value / total) * 100) : 0;
        return (
          <div className={styles.row} key={key}>
            <span className={styles.label} title={label}>
              {label}
            </span>
            <div className={styles.track}>
              <div className={styles.bar} style={{ width: `${pct}%`, background: color }} />
            </div>
            <span className={styles.value}>{money(value)}</span>
          </div>
        );
      })}
    </div>
  );
}

export function SourcesUses({ data }: { data: SourcesUsesData }) {
  // The server computes this; it is a modelling bug, not a rounding artefact. Drawing the
  // chart anyway would present a broken capital stack as if it balanced.
  if (!data.balanced) {
    return (
      <div className={styles.unbalanced}>
        Sources ({money(data.sources_total)}) and uses ({money(data.uses_total)}) do not
        balance. The capital stack is not drawn, because the difference is a modelling
        error rather than rounding.
      </div>
    );
  }

  return (
    <div>
      <Group title="Uses" items={USES} values={data.uses} total={data.uses_total} />
      <Group title="Sources" items={SOURCES} values={data.sources} total={data.sources_total} />
    </div>
  );
}
