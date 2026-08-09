/** The 1b drill-down panel: the full underwriting read on one parcel.
 *
 * This renders the header, the RLV hero, and the metric grid. The charts, program card,
 * and assumption tabs are the next slice — the grid is split into its own component
 * because it is the part every other screen (compare, shortlist, table) reuses.
 */
import type { Underwrite } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { PARCEL_ID_LABEL } from "../lib/vocabulary";
import { count, money } from "../lib/format";
import { MetricGrid } from "./MetricGrid";
import { ProgramCard } from "./ProgramCard";
import { SCurve } from "./SCurve";
import { SourcesUses } from "./SourcesUses";
import styles from "./Drilldown.module.css";

function Tags({ data, vocab }: { data: Underwrite; vocab: Vocabulary }) {
  const constraint = vocab.bindingConstraint(data.envelope.binding_constraint_label
    ?? data.envelope.binding_constraint);

  return (
    <div className={styles.tags}>
      <span className={`${styles.tag} ${styles.accent}`}>
        {vocab.metric("prototype_id")} · {vocab.prototype(data.program.prototype_id)}
      </span>
      {constraint && <span className={styles.tag}>{constraint}</span>}
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
    </div>
  );
}

export function Drilldown({
  data,
  vocab,
  demolition,
  busy = false,
  onDemolitionChange,
  onEditAssumptions,
  onSaveScenario,
  onExport,
  exporting = false,
  saveState = "idle",
  onClose,
}: {
  data: Underwrite;
  vocab: Vocabulary;
  demolition: boolean;
  /** A re-underwrite is in flight; the panel still shows the previous, valid numbers. */
  busy?: boolean;
  onDemolitionChange: (next: boolean) => void;
  onEditAssumptions?: () => void;
  onSaveScenario?: () => void;
  onExport?: () => void;
  /** A workbook build is in flight — it re-runs the model server-side. */
  exporting?: boolean;
  /** "Saved" / "Saving…" — transient feedback on the footer's save button. */
  saveState?: "idle" | "saving" | "saved";
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

        {/* Program leads: what gets built comes before how it performs. */}
        <ProgramCard program={data.program} vocab={vocab} />

        <MetricGrid returns={data.returns} vocab={vocab} />

        {/* SPEC 10's developability flag, now carrying the demolition control itself. A
            standing building is the reason demolition is a question at all, so the flag and
            the switch belong in one box rather than a warning here and a toggle further
            down the panel. */}
        {data.developability.has_existing_building ? (
          <div className={`${styles.callout} ${styles.warn}`}>
            <div className={styles.calloutRow}>
              <div>
                <span className="micro-label">Existing building</span>
                <div className={styles.calloutHeadline}>
                  {count(data.developability.existing_building_sf)} SF standing
                </div>
              </div>
              <div className={styles.toggleWrap}>
                <span className={styles.toggleLabel}>Include demolition</span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={demolition}
                  aria-label="Include demolition"
                  disabled={busy}
                  className={`${styles.switch} ${demolition ? styles.switchOn : ""}`}
                  onClick={() => onDemolitionChange(!demolition)}
                >
                  <span className={styles.knob} />
                </button>
              </div>
            </div>
          </div>
        ) : null}

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

        {/* Charts last: the cash-flow detail is what you scroll to, not what you land on. */}
        <div className={styles.charts}>
          <section>
            <div className={`micro-label ${styles.chartTitle}`}>Sources &amp; uses</div>
            <SourcesUses data={data.sources_uses} />
          </section>
          <section>
            <div className={`micro-label ${styles.chartTitle}`}>Cost draw</div>
            <SCurve cashflow={data.cashflow} />
          </section>
        </div>
      </div>

      <footer className={styles.footer}>
        <button
          className={styles.footerPrimary}
          onClick={onEditAssumptions}
          disabled={!onEditAssumptions || busy}
        >
          {data.overrides_changed > 0
            ? `Edit assumptions · ${data.overrides_changed} changed`
            : "Edit assumptions & re-underwrite"}
        </button>
        {/* Saving freezes this underwrite (SPEC 7.1): the market values it used are
            stamped and never re-read, so it reproduces after a re-bake. */}
        <button
          className={styles.footerSecondary}
          onClick={onSaveScenario}
          disabled={!onSaveScenario || busy || saveState === "saving"}
        >
          {saveState === "saving" ? "Saving…" : saveState === "saved" ? "Saved ✓" : "Save scenario"}
        </button>
        {/* No save required. The server re-runs the model from the current inputs and
            builds the workbook from its own output, so the file always agrees with this
            panel without a scenario row having to exist first. */}
        <button
          className={styles.footerSecondary}
          onClick={onExport}
          disabled={!onExport || busy || exporting}
          title="Download a live Excel workbook of these inputs"
        >
          {exporting ? "Building…" : "Export to Excel"}
        </button>
      </footer>
    </aside>
  );
}

/** Shown where the panel's numbers would go when a parcel cannot be modeled.
 *
 * Two different situations land here, and conflating them is what made this a dead end.
 *
 *   - The PARCEL cannot be modeled: exempt, historic, zoning not yet encoded. Nothing the
 *     user can change; the server's sentence is the whole answer.
 *   - The user's INPUTS cannot be modeled: an edit pushed the program outside what zoning
 *     allows. That is recoverable, and the panel has to say how — previously it explained
 *     the refusal and then offered no route back to the values that caused it.
 *
 * `recovery` is what separates them. It is absent in the first case on purpose.
 */
export function NotModellablePanel({
  reason,
  recovery,
  onClose,
}: {
  reason: string;
  recovery?: { onEditAssumptions: () => void; onReset: () => void; changed: number };
  onClose?: () => void;
}) {
  return (
    <aside className={styles.panel} aria-label="Parcel underwriting">
      <header className={styles.header}>
        <div className={styles.headerTop}>
          <div className={styles.address}>
            {recovery ? "These inputs cannot be modeled" : "Not modeled"}
          </div>
          {onClose && (
            <button className={styles.iconButton} onClick={onClose} aria-label="Close panel">
              ×
            </button>
          )}
        </div>
      </header>
      <div className={styles.state}>
        <div className={styles.stateTitle}>
          {recovery ? "The model was not run" : "This parcel has no underwriting"}
        </div>
        {reason}
        {recovery && (
          <p className={styles.stateHint}>
            {recovery.changed === 1
              ? "One edited input put this parcel outside what its zoning allows."
              : `${recovery.changed} edited inputs put this parcel outside what its zoning allows.`}{" "}
            Change them back, or return to the default inputs.
          </p>
        )}
      </div>
      {recovery && (
        <footer className={styles.footer}>
          <button className={styles.footerPrimary} onClick={recovery.onEditAssumptions}>
            Edit assumptions
          </button>
          <button className={styles.footerSecondary} onClick={recovery.onReset}>
            Reset to defaults
          </button>
        </footer>
      )}
    </aside>
  );
}
