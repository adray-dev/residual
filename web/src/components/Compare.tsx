/** Screen 1e: up to three parcels side by side.
 *
 * Every column is a full-tier underwrite, not a row off the map query — annual return and
 * equity multiple do not exist in the screening layer.
 *
 * The color rule is the load-bearing design decision here. Each column owns a color by
 * POSITION (teal, slate, amber), and the superlative tags follow the DATA. If color
 * tracked rank instead, column order would read as ranking and the first column would look
 * like the answer before anyone had read a number.
 */
import type { Underwrite } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { PARCEL_ID_LABEL } from "../lib/vocabulary";
import { count, money, moneyExact, multiple, percent } from "../lib/format";
import { COLUMN_COLORS, superlatives, tagsFor } from "../lib/compare";
import styles from "./Compare.module.css";

interface Row {
  label: string;
  /** Highlighted rows are the figures a developer actually decides on. */
  highlight?: boolean;
  value: (row: Underwrite) => string;
  /** Prose rather than a figure — rendered in the sans face, not mono. */
  text?: boolean;
}

function rowsFor(vocab: Vocabulary): Row[] {
  return [
    {
      label: vocab.metric("rlv_total"),
      highlight: true,
      value: (r) => money(r.feasibility_value.full),
    },
    // Per-unit figures cluster tightly across columns — $364,094 against $364,049 both
    // compact to "$364K", which makes a "Cheapest basis" badge look arbitrary. Shown exact
    // so the superlative is visibly earned.
    { label: "Value per unit", value: (r) => moneyExact(r.per_unit_value) },
    { label: vocab.metric("irr"), highlight: true, value: (r) => percent(r.returns.irr) },
    { label: vocab.metric("profit_margin"), value: (r) => percent(r.returns.profit_margin) },
    {
      label: vocab.metric("equity_multiple"),
      value: (r) => multiple(r.returns.equity_multiple),
    },
    { label: vocab.metric("noi"), highlight: true, value: (r) => money(r.returns.noi) },
    {
      label: vocab.metric("total_development_cost"),
      value: (r) => money(r.returns.total_development_cost),
    },
    { label: vocab.metric("cost_per_unit"), value: (r) => moneyExact(r.returns.cost_per_unit) },
    {
      label: vocab.metric("max_buildable_gsf"),
      value: (r) => `${count(r.envelope.max_buildable_gsf)} SF`,
    },
    {
      label: vocab.metric("prototype_id"),
      text: true,
      value: (r) => vocab.prototype(r.program.prototype_id),
    },
  ];
}

export function Compare({
  rows,
  vocab,
  onClose,
}: {
  rows: Underwrite[];
  vocab: Vocabulary;
  onClose: () => void;
}) {
  const metrics = rowsFor(vocab);
  const awards = superlatives(rows);
  const template = `220px repeat(${Math.max(rows.length, 1)}, 1fr)`;

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true" aria-label="Compare parcels">
      <header className={styles.bar}>
        <span className={styles.title}>Compare</span>
        <span className={styles.count}>
          {rows.length} {rows.length === 1 ? "parcel" : "parcels"}
        </span>
        <button className={styles.close} onClick={onClose}>
          Close
        </button>
      </header>

      <div className={styles.scroll}>
        {rows.length === 0 ? (
          <div className={styles.empty}>
            Nothing selected. Click a parcel on the map and choose “Add to compare”.
          </div>
        ) : (
          <div className={styles.grid} style={{ gridTemplateColumns: template }}>
            {/* header strip */}
            <div className={`${styles.head} ${styles.headLabel}`} />
            {rows.map((row, index) => {
              const color = COLUMN_COLORS[index % COLUMN_COLORS.length]!;
              return (
                <div className={styles.head} key={`h-${row.parcel_id}`}>
                  <div
                    className={styles.swatch}
                    style={{
                      background: `linear-gradient(135deg, ${color.solid}, ${color.tint})`,
                    }}
                  />
                  <div className={styles.headBody}>
                    <div className={styles.address}>{row.display_name}</div>
                    <div className={styles.identity}>
                      {PARCEL_ID_LABEL} {row.parcel_id.trim()}
                      {row.ward ? ` · ${row.ward}` : ""}
                    </div>
                    <div className={styles.tags}>
                      {tagsFor(index, awards).map((tag) => (
                        <span
                          className={styles.tag}
                          key={tag}
                          style={{ background: color.tint, color: color.text }}
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}

            {/* metric rows */}
            {metrics.map((metric, rowIndex) => {
              const zebra = rowIndex % 2 === 1;
              const rowClass = metric.highlight
                ? styles.highlight
                : zebra
                  ? styles.zebra
                  : "";
              return (
                <div style={{ display: "contents" }} key={metric.label}>
                  <div className={`${styles.rowLabel} ${rowClass}`}>{metric.label}</div>
                  {rows.map((row, index) => {
                    const color = COLUMN_COLORS[index % COLUMN_COLORS.length]!;
                    return (
                      <div
                        className={`${styles.cell} ${rowClass}`}
                        key={`${metric.label}-${row.parcel_id}`}
                      >
                        <span
                          className={metric.text ? styles.text : styles.cellValue}
                          style={
                            metric.highlight && !metric.text
                              ? { color: color.solid }
                              : undefined
                          }
                        >
                          {metric.value(row)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

/** The selection tray: what is queued for comparison, and the way in. */
export function CompareTray({
  ids,
  busy,
  onOpen,
  onClear,
}: {
  ids: string[];
  busy: boolean;
  onOpen: () => void;
  onClear: () => void;
}) {
  if (ids.length === 0) return null;
  return (
    <div className={styles.tray}>
      <span className={styles.trayText}>
        <b>{ids.length}</b> selected to compare
      </span>
      <button className={styles.trayClear} onClick={onClear}>
        Clear
      </button>
      <button className={styles.trayButton} onClick={onOpen} disabled={busy || ids.length < 2}>
        {busy ? "Underwriting…" : ids.length < 2 ? "Pick one more" : "Compare"}
      </button>
    </div>
  );
}
