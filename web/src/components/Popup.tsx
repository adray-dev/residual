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
import { useLayoutEffect, useRef, useState } from "react";
import type { ParcelRecord } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { PARCEL_ID_LABEL } from "../lib/vocabulary";
import { count, money } from "../lib/format";
import { placePopup } from "../lib/popupPlacement";
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
  /** Lists this parcel can be saved to, and which already hold it. */
  lists: { shortlist_id: string; name: string }[];
  memberOf: string[];
  onOpenFull: () => void;
  onToggleCompare: () => void;
  onToggleSave: (shortlistId: string) => void;
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
  lists,
  memberOf,
  onOpenFull,
  onToggleCompare,
  onToggleSave,
  onClose,
}: PopupProps) {
  const [saving, setSaving] = useState(false);
  const card = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<{ x: number; y: number } | null>(null);

  // Position is MEASURED, not estimated.
  //
  // The card used to sit at `translate(-50%, -100%)` above the click with only a horizontal
  // clamp, against `window.innerWidth`. Three ways that put it off screen: a parcel near
  // the top of the map pushed the whole card above the viewport, because nothing clamped
  // vertically at all; the card's height changes with its content (loading, scored, not
  // scored, list picker open) so no fixed offset could be right; and the window is the
  // wrong frame — the popup lives in the map area, which loses 620px the moment the
  // drill-down rail opens beside it.
  //
  // So: measure the card and its container, clamp both axes inside the container, and flip
  // BELOW the parcel when there is no room above.
  useLayoutEffect(() => {
    const element = card.current;
    if (!element) return;

    const place = () => {
      const parent = element.offsetParent as HTMLElement | null;
      setBox(
        placePopup(
          at,
          { width: element.offsetWidth, height: element.offsetHeight },
          {
            width: parent?.clientWidth ?? window.innerWidth,
            height: parent?.clientHeight ?? window.innerHeight,
          },
        ),
      );
    };

    place();

    // The card resizes when its content arrives or the picker opens, and the CONTAINER
    // resizes when the drill-down rail opens beside it. Both move where the card belongs.
    const observer = new ResizeObserver(place);
    observer.observe(element);
    const parent = element.offsetParent;
    if (parent instanceof HTMLElement) observer.observe(parent);
    return () => observer.disconnect();
  }, [at.x, at.y]);

  const best = record?.prototypes.find((p) => p.is_best) ?? record?.prototypes[0] ?? null;
  const scored = record?.status === "scored" && best != null;

  return (
    <div
      className={styles.popup}
      ref={card}
      style={{
        left: box?.x ?? 0,
        top: box?.y ?? 0,
        // Hidden for the one layout pass before the measurement lands, so the card is
        // never briefly painted in the wrong place.
        visibility: box ? "visible" : "hidden",
      }}
    >
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
          onClick={() => setSaving((open) => !open)}
          disabled={!scored}
          title={lists.length ? "Save to a list" : "Create a list on the Shortlist screen first"}
        >
          {memberOf.length ? "Saved ✓" : "Save"}
        </button>
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

      {/* The list picker lives in the popup rather than a separate dialog: saving is a
          one-click decision made while triaging, and bouncing to another screen to do it
          would break the loop the map is for. */}
      {saving && (
        <div className={styles.picker}>
          {lists.length === 0 ? (
            <div className={styles.pickerEmpty}>
              No lists yet — make one on the Shortlist screen.
            </div>
          ) : (
            lists.map((list) => (
              <button
                key={list.shortlist_id}
                className={styles.pickerRow}
                onClick={() => onToggleSave(list.shortlist_id)}
              >
                <span>{list.name}</span>
                <span className={styles.pickerMark}>
                  {memberOf.includes(list.shortlist_id) ? "✓" : ""}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
