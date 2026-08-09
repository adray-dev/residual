/** The map legend: what the colors mean, and the control that switches objective.
 *
 * SPEC §9's rule is that every color on the map is explainable, so this lists both systems
 * the map uses: the diverging value ramp, and the neutrals for land the model cannot price.
 * A legend showing only the ramp would leave 40% of DC's parcels colored by nothing the
 * reader can look up.
 */
import type { Meta } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { money, rate } from "../lib/format";
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

/** Per-SF figures are single-digit dollars — compacting them would erase the number. */
function rampEnd(objective: string, value: number | null): string {
  if (value == null) return "—";
  return objective === "rlv_per_buildable_sf" ? `${rate(value, 0)}/SF` : money(value, 1);
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
  const ramp = meta.ramps[objective];
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
    <div className={styles.panel}>
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
        <span>{rampEnd(objective, ramp?.min ?? null)}</span>
        <span>{rampEnd(objective, ramp?.max ?? null)}</span>
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
  );
}
