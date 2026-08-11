/** The map legend: what the colors mean, and the control that switches objective.
 *
 * SPEC §9's rule is that every color on the map is explainable, so this lists both systems
 * the map uses: the diverging value ramp, and the neutrals for land the model cannot price.
 * A legend showing only the ramp would leave 40% of DC's parcels colored by nothing the
 * reader can look up.
 */
import { useState } from "react";
import type { Meta } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { rate } from "../lib/format";
import { domainMoney, roundedDomain } from "../lib/rampDomain";
import { LEGEND_GRADIENT, OBJECTIVE_METRIC, STATUS_COLORS } from "../lib/mapStyle";
import styles from "./Legend.module.css";

/** Chrome copy for the segmented control, which cannot hold the full metric names
 * ("Financial feasibility (RLV)"). The full served label rides along as the title.
 *
 * The handoff's control has two segments; this one has three, because /meta advertises a
 * third objective. At the handoff's 236px these ellipsised to "Total val…" and
 * "vs. asses…", so the copy is shortened and the panel widened to 264px rather than
 * shipping two truncated labels — a legend nobody can read is worse than a wider legend. */
const SEGMENT_COPY: Record<string, string> = {
  rlv_total: "Total",
  rlv_per_buildable_sf: "Per SF",
};

/** Per-SF figures are two- and three-digit dollars — compacting them would erase the
 *  number, so only the total is abbreviated. Both arrive already rounded. */
function rampEnd(objective: string, value: number): string {
  if (!Number.isFinite(value)) return "—";
  return objective === "rlv_per_buildable_sf" ? `${rate(value, 0)}/SF` : domainMoney(value);
}

export function Legend({
  meta,
  vocab,
  objective,
  onObjectiveChange,
}: {
  meta: Meta;
  vocab: Vocabulary;
  objective: string;
  onObjectiveChange: (objective: string) => void;
}) {
  // Only ever consulted at narrow widths: the toggle that sets it is display:none above the
  // breakpoint, and the rule that acts on it lives inside the same media query. So a desktop
  // renders the full panel no matter what this says, and a phone that was minimised and then
  // widened does not end up with a legend it cannot open.
  const [collapsed, setCollapsed] = useState(true);

  const ramp = meta.ramps[objective];
  // Rounded for total RLV only, by the same function the filter slider uses: those two
  // print the same domain a few hundred pixels apart and have to agree, and a slider whose
  // track ended at -$103,720,782 would be reporting the extreme parcel rather than a range.
  //
  // Nothing governs the per-SF ramp but the ramp itself, so there is nothing to agree with,
  // and it reports what the bake actually holds — -$132/SF is a readable number already,
  // and rounding it to -$140 would only move the label away from the data for no gain.
  const domain =
    objective === "rlv_total"
      ? roundedDomain(ramp?.min, ramp?.max)
      : { floor: ramp?.min ?? NaN, ceiling: ramp?.max ?? NaN };
  const negative = ramp?.negative_count ?? 0;
  const positive = ramp?.positive_count ?? 0;
  const scored = negative + positive;

  // SPEC §9: every color on the map is explainable, so every status the bake can emit is
  // listed with its count. Order runs lightest to darkest, which is also roughly least to
  // most restricted.
  const statuses: [keyof typeof STATUS_COLORS, string][] = [
    ["zone_not_encoded", "zone_not_encoded"],
    ["exempt", "exempt"],
    ["infeasible", "infeasible"],
    ["historic", "historic"],
  ];

  return (
    <div className={styles.panel} data-collapsed={collapsed || undefined}>
      {/* Hidden above the breakpoint, where the legend costs nothing to leave open. The
          gradient rides on the button so the control still says what it opens. */}
      <button
        type="button"
        className={styles.toggle}
        aria-expanded={!collapsed}
        onClick={() => setCollapsed((value) => !value)}
      >
        <span className={styles.toggleSwatch} style={{ background: LEGEND_GRADIENT }} />
        <span className={styles.toggleLabel}>Legend</span>
        <span className={styles.chevron} aria-hidden="true" />
      </button>

      <div className={styles.content}>
        <div className={styles.segmented} role="tablist">
          {meta.objectives.filter((key) => key !== "gap").map((key) => (
            <button
              key={key}
              role="tab"
              aria-selected={key === objective}
              title={vocab.metric(OBJECTIVE_METRIC[key] ?? key)}
              className={`${styles.segment} ${key === objective ? styles.active : ""}`}
              onClick={() => onObjectiveChange(key)}
            >
              {SEGMENT_COPY[key] ?? vocab.metric(OBJECTIVE_METRIC[key] ?? key)}
            </button>
          ))}
        </div>

        <div className={styles.gradientWrap}>
          <div className={styles.gradient} style={{ background: LEGEND_GRADIENT }} />
          {/* $0 sits at the exact midpoint: the ramp is quantile-binned into four bins per
              arm, so four of eight stops fall either side of zero by construction. */}
          <span className={styles.zeroTick} aria-hidden="true" />
          <span className={styles.zeroLabel}>$0</span>
        </div>
        <div className={styles.ends}>
          <span>{rampEnd(objective, domain.floor)}</span>
          <span>{rampEnd(objective, domain.ceiling)}</span>
        </div>

        {scored > 0 && (
          <div className={styles.zero}>
            <strong>{Math.round((positive / scored) * 100)}%</strong> of scored parcels are
            positive.
          </div>
        )}

        <div className={styles.rule} />

        {/* Land the model cannot price. Neutral on the map and neutral here — these are
            context for the value ramp, not competitors with it. */}
        <div className={`micro-label ${styles.notPriced}`}>Not priced</div>
        {statuses.map(([colorKey, statusKey]) => {
          const count = meta.status_counts[statusKey];
          if (!count) return null;
          return (
            <div className={styles.status} key={statusKey}>
              <span
                className={styles.swatch}
                style={
                  statusKey === "exempt"
                    ? {
                        backgroundImage: `repeating-linear-gradient(45deg,${STATUS_COLORS.exempt} 0 3px,${STATUS_COLORS.exempt_alt} 3px 6px)`,
                      }
                    : statusKey === "zone_not_encoded"
                      ? {
                          background: STATUS_COLORS.zone_not_encoded,
                          borderStyle: "dashed",
                          borderColor: STATUS_COLORS.zone_not_encoded_border,
                        }
                      : { background: STATUS_COLORS[colorKey] }
                }
              />
              {vocab.status(statusKey)}
              <span className={styles.count}>{count.toLocaleString()}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
