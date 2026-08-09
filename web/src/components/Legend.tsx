/** The map legend: what the colours mean, and the control that switches objective.
 *
 * SPEC §9's rule is that every colour on the map is explainable. The map now draws ONLY
 * scored parcels, so there is exactly one colour system to explain — the value ramp — and
 * the status swatches went with the statuses. What replaced them is a count of what is not
 * shown, because a large silent absence reads as missing data rather than as a decision.
 */
import type { Meta } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { money, rate } from "../lib/format";
import { LEGEND_GRADIENT, OBJECTIVE_METRIC } from "../lib/mapStyle";
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

  // The status swatches are gone with the statuses themselves: the map draws only scored
  // parcels, so there is no shade left to explain. What replaces them is a plain statement
  // of what is NOT on the map, because 53,559 parcels quietly missing would otherwise read
  // as a gap in the data rather than a deliberate exclusion.
  const excluded = Object.entries(meta.status_counts)
    .filter(([status]) => status !== "scored")
    .reduce((n, [, value]) => n + value, 0);

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

      <div className={styles.excluded}>
        Showing the <strong>{scored.toLocaleString()}</strong> parcels the model could
        price. {excluded.toLocaleString()} more are not shown — public or tax-exempt land,
        historic districts, and zoning not yet encoded.
      </div>
    </div>
  );
}
