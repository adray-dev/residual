/** The 1b drill-down panel: the full underwriting read on one parcel.
 *
 * This renders the header, the RLV hero, and the metric grid. The charts, program card,
 * and assumption tabs are the next slice — the grid is split into its own component
 * because it is the part every other screen (compare, shortlist, table) reuses.
 */
import type { Underwrite } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { PARCEL_ID_LABEL } from "../lib/vocabulary";
import { confidence, count, money, percent } from "../lib/format";
import { MetricGrid } from "./MetricGrid";
import styles from "./Drilldown.module.css";

/** Below this the handoff shows a "Low confidence · default inputs" chip (amber tint). */
const LOW_CONFIDENCE = 0.5;

function Tags({ data, vocab }: { data: Underwrite; vocab: Vocabulary }) {
  const constraint = vocab.bindingConstraint(data.envelope.binding_constraint_label
    ?? data.envelope.binding_constraint);

  return (
    <div className={styles.tags}>
      <span className={`${styles.tag} ${styles.accent}`}>
        {vocab.metric("prototype_id")} · {vocab.prototype(data.program.prototype_id)}
      </span>
      {constraint && <span className={styles.tag}>{constraint}</span>}
      {data.confidence < LOW_CONFIDENCE && (
        <span className={`${styles.tag} ${styles.amber}`}>
          Low confidence · {confidence(data.confidence)}
        </span>
      )}
      {/* The panel can be run on a prototype the bake did not pick ("Try another
          prototype"). Saying so keeps this number from being read as the city-wide best. */}
      {!data.is_bake_best && <span className={styles.tag}>Alternate build</span>}
    </div>
  );
}

function Hero({ data, vocab }: { data: Underwrite; vocab: Vocabulary }) {
  const { feasibility_value: value, program } = data;
  const units = program.unit_count;

  return (
    <div>
      <div className="micro-label" style={{ marginBottom: 8 }}>
        {vocab.metric("rlv_total")}
      </div>
      <div className={styles.hero}>
        <span className={styles.heroValue}>{money(value.full)}</span>
        <span className={styles.heroAside}>
          {money(data.per_unit_value)} per unit · {count(units)} units
        </span>
      </div>
      {/* SPEC 11: the screening and full tiers WILL diverge, and the product's honesty
          claim is that the difference is labelled rather than reconciled away. The map is
          coloured by the screening number, so a user arriving from the map has seen it. */}
      <p className={styles.tierNote}>
        {value.full_label} · the map is coloured by the {value.screening_label.toLowerCase()}{" "}
        of <b>{money(value.screening)}</b>
        {value.difference_pct != null && (
          <> ({percent(value.difference_pct, 0)} difference)</>
        )}
        . The two are modelled differently and are not expected to match.
      </p>
    </div>
  );
}

export function Drilldown({
  data,
  vocab,
  onClose,
}: {
  data: Underwrite;
  vocab: Vocabulary;
  onClose?: () => void;
}) {
  const lot = data.lot_area_sf ? `${count(data.lot_area_sf)} SF lot` : null;
  const identity = [`${PARCEL_ID_LABEL} ${data.parcel_id.trim()}`, data.ward, lot]
    .filter(Boolean)
    .join(" · ");

  return (
    <aside className={styles.panel} aria-label="Parcel underwriting">
      <header className={styles.header}>
        <div className={styles.headerTop}>
          <div className={styles.address}>{data.display_name}</div>
          {onClose && (
            <button className={styles.iconButton} onClick={onClose} aria-label="Close panel">
              ×
            </button>
          )}
        </div>
        <div className={styles.identity}>{identity}</div>
        <Tags data={data} vocab={vocab} />
      </header>

      <div className={styles.body}>
        <Hero data={data} vocab={vocab} />
        <MetricGrid returns={data.returns} vocab={vocab} />

        {/* SPEC 10's developability flag. A positive RLV on a built parcel does not mean an
            acquirable deal — the seller owns a building, not bare land. Surfaced, never hidden. */}
        {data.developability.has_existing_building && (
          <div className={`${styles.callout} ${styles.warn}`}>
            <span className="micro-label">Existing building</span>
            <span className={styles.calloutText}>
              {data.developability.note ??
                `${count(data.developability.existing_building_sf)} SF standing — acquisition will run above land value.`}
            </span>
          </div>
        )}

        {/* The "gated by" callout: which envelope rule actually capped this program. */}
        <div className={styles.callout}>
          <span className="micro-label">
            {vocab.bindingConstraint(data.envelope.binding_constraint)}
          </span>
          <span className={styles.calloutText}>
            {count(data.envelope.max_buildable_gsf)} SF buildable across{" "}
            {data.envelope.max_floors} floors, on a{" "}
            {count(data.envelope.max_footprint_sf)} SF footprint.
          </span>
        </div>
      </div>
    </aside>
  );
}

/** Shown where the panel's numbers would go when a parcel cannot be modelled at all.
 *
 * Exempt land, historic restriction, unencoded zoning. The server sends a plain-language
 * sentence and it is rendered verbatim — these are answers about the parcel, and dressing
 * one up as an error would tell the user the product is broken when it is working. */
export function NotModellablePanel({
  reason,
  onClose,
}: {
  reason: string;
  onClose?: () => void;
}) {
  return (
    <aside className={styles.panel} aria-label="Parcel underwriting">
      <header className={styles.header}>
        <div className={styles.headerTop}>
          <div className={styles.address}>Not modelled</div>
          {onClose && (
            <button className={styles.iconButton} onClick={onClose} aria-label="Close panel">
              ×
            </button>
          )}
        </div>
      </header>
      <div className={styles.state}>
        <div className={styles.stateTitle}>This parcel has no underwriting</div>
        {reason}
      </div>
    </aside>
  );
}
