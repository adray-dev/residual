/** The map legend: what the colours mean, and the control that switches objective.
 *
 * Every status the bake can emit is listed with its count, because SPEC §9's rule is that
 * every parcel gets a row and every colour is explainable. A legend that showed only the
 * value ramp would leave a third of the city's parcels coloured by nothing the user can
 * look up.
 */
import type { Meta } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { money, rate } from "../lib/format";
import { LEGEND_GRADIENT, OBJECTIVE_METRIC, STATUS_COLORS } from "../lib/mapStyle";
import styles from "./Legend.module.css";

/** Chrome copy for the segmented control, which is 236px wide and cannot hold the full
 * metric names ("Financial feasibility (RLV)"). The handoff specifies these exact short
 * forms for this control; the full served label rides along as the title attribute. */
const SEGMENT_COPY: Record<string, string> = {
  rlv_total: "Total value",
  rlv_per_buildable_sf: "Per SF",
  gap: "vs. assessed",
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

  const statuses: [keyof typeof STATUS_COLORS, string][] = [
    ["infeasible", "infeasible"],
    ["exempt", "exempt"],
    ["historic", "historic"],
    ["zone_not_encoded", "zone_not_encoded"],
  ];

  return (
    <div className={styles.panel}>
      <div className={`micro-label ${styles.heading}`}>Color by</div>
      <div className={styles.segmented} role="tablist">
        {meta.objectives.map((key) => (
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

      <div className={styles.gradient} style={{ background: LEGEND_GRADIENT }} />
      <div className={styles.ends}>
        <span>{rampEnd(objective, ramp?.min ?? null)}</span>
        <span>{rampEnd(objective, ramp?.max ?? null)}</span>
      </div>

      {/* Where the ramp crosses zero, stated rather than left to be inferred from a hue. */}
      {scored > 0 && (
        <div className={styles.zero}>
          The ramp turns teal at $0.{" "}
          <strong>{Math.round((negative / scored) * 100)}%</strong> of scored parcels price
          below it.
        </div>
      )}

      <div className={styles.rule} />

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
