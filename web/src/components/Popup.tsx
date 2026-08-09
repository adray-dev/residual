/** The 1a popup: triage a parcel without paying for the full model.
 *
 * This reads `/parcel/{id}`, which is a straight `bake_results` lookup — the engine does
 * not run. That split is the point. Clicking around the map is how a user finds
 * candidates, and it has to stay instant; the levered monthly model is the deliberate
 * next step, taken from the button at the bottom of this card.
 *
 * The number shown here is therefore the SCREENING RLV, the same one the map is coloured
 * by, and it will not match the full underwriting figure in the panel. SPEC §11 accepts
 * that divergence and requires it be labelled rather than reconciled away, which is what
 * the "Screening estimate" caption does.
 */
import type { ParcelRecord } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { PARCEL_ID_LABEL } from "../lib/vocabulary";
import { count, money } from "../lib/format";
import styles from "./Popup.module.css";

export interface PopupProps {
  /** Pixel position of the parcel on screen; the card is anchored above this point. */
  at: { x: number; y: number };
  record: ParcelRecord | null;
  vocab: Vocabulary;
  busy: boolean;
  /** Whether this parcel is already queued for comparison. */
  inCompare: boolean;
  /** False when the compare set is full and this parcel is not in it. */
  canCompare: boolean;
  onOpenFull: () => void;
  onToggleCompare: () => void;
  onClose: () => void;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.row}>
      <span className={styles.rowLabel}>{label}</span>
      <span className={styles.rowValue} title={value}>
        {value}
      </span>
    </div>
  );
}

export function Popup({
  at,
  record,
  vocab,
  busy,
  inCompare,
  canCompare,
  onOpenFull,
  onToggleCompare,
  onClose,
}: PopupProps) {
  // Clamped so a parcel near an edge does not push the card off screen. The right edge
  // also has to clear the drill-down rail when it is open, which is why the clamp reads
  // the live window rather than the handoff's fixed 340-1180 range.
  const half = 150;
  const x = Math.min(Math.max(at.x, half + 12), window.innerWidth - half - 12);

  const best = record?.prototypes.find((p) => p.is_best) ?? record?.prototypes[0] ?? null;
  const scored = record?.status === "scored" && best != null;

  return (
    <div className={styles.popup} style={{ left: x, top: at.y }}>
      <div className={styles.head}>
        <div className={styles.title}>
          <div className={styles.address}>{record?.display_name ?? "Loading…"}</div>
          {record && (
            <div className={styles.identity}>
              {PARCEL_ID_LABEL} {record.parcel_id.trim()}
              {record.ward ? ` · ${record.ward}` : ""}
            </div>
          )}
        </div>
        <button className={styles.close} onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>
      <div className={styles.rule} />

      {!record ? (
        <div className={styles.loading}>Reading the parcel…</div>
      ) : scored ? (
        <>
          <div className={styles.value}>
            <span className={styles.valueMain}>{money(best.screening_rlv)}</span>
            <span className={styles.valuePer}>
              {best.unit_count
                ? `${money((best.screening_rlv ?? 0) / best.unit_count)} per unit`
                : ""}
            </span>
          </div>
          <div className={styles.rows}>
            <Row
              label="Zoning · best build"
              value={`${record.zoning.zone_code ?? "—"} · ${vocab.prototype(best.prototype_id)}`}
            />
            <Row label={vocab.metric("max_buildable_gsf")} value={`${count(best.gross_sf)} SF`} />
            <Row label={vocab.metric("lot_area_sf")} value={`${count(record.lot_area_sf)} SF`} />
            <Row
              label="Current use"
              value={
                record.developability.has_existing_building
                  ? `${count(record.developability.existing_building_sf)} SF building`
                  : "Vacant / land only"
              }
            />
            <Row
              label="Limited by"
              value={
                vocab.bindingConstraint(
                  best.binding_constraint_label ?? best.binding_constraint,
                ) || "—"
              }
            />
          </div>
        </>
      ) : (
        // Not scored: the status sentence goes where the number would, in the quiet
        // neutral register the handoff uses. No dash, no zero, no implied verdict.
        <div className={styles.statusLine}>{record.status_label}</div>
      )}

      <div className={styles.actions}>
        <button
          className={styles.primary}
          onClick={onOpenFull}
          disabled={!scored || busy}
          title={
            scored ? "Runs the levered monthly model on this parcel" : "This parcel is not scored"
          }
        >
          {busy ? "Underwriting…" : "Open full underwriting"}
        </button>
        {/* Comparison is a full-tier read on every column, so it is offered only where
            there is something to compare — a non-scored parcel has no metrics. */}
        <button
          className={styles.secondary}
          onClick={onToggleCompare}
          disabled={!scored || (!inCompare && !canCompare)}
          title={
            inCompare
              ? "Remove from the comparison"
              : canCompare
                ? "Add this parcel to the comparison"
                : "The comparison already holds three parcels"
          }
        >
          {inCompare ? "In compare ✓" : "Compare"}
        </button>
      </div>
    </div>
  );
}
