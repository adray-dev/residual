/** Screen 1f: saved parcels, as named lists.
 *
 * A shortlist holds parcel ids and nothing else. Every figure on a card is read LIVE from
 * the current bake each time the list is opened, so a list cannot go stale against a
 * re-bake — the deliberate opposite of a scenario, which freezes at save.
 *
 * Card values are SCREENING numbers, the same tier the map is colored by, so they will not
 * match the full underwriting figure in the drill-down. Return is the exception — levered
 * IRR does not exist in the screening tier, so the server runs the full model for it.
 */
import { useState } from "react";
import type { ShortlistDetail, ShortlistSummary, ParcelRow } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { PARCEL_ID_LABEL } from "../lib/vocabulary";
import { money, percent } from "../lib/format";
import { RAMP } from "../lib/mapStyle";
import styles from "./Shortlist.module.css";

/** "Saved 3 days ago" — the handoff's phrasing, including today. */
function savedAgo(iso: string | undefined): string {
  if (!iso) return "";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "Saved today";
  if (days === 1) return "Saved yesterday";
  return `Saved ${days} days ago`;
}

/** A card header gradient keyed to the parcel, so cards are distinguishable at a glance
 * without the color meaning anything — it is decoration, not an encoding. */
function gradientFor(parcelId: string): string {
  let hash = 0;
  for (const ch of parcelId) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  const from = RAMP[4 + (hash % 4)] ?? RAMP[5];
  const to = RAMP[1 + (hash % 3)] ?? RAMP[2];
  return `linear-gradient(135deg, ${from}, ${to})`;
}

function Card({
  parcel,
  addedAt,
  vocab,
  onOpen,
  onRemove,
}: {
  parcel: ParcelRow;
  addedAt: string | undefined;
  vocab: Vocabulary;
  onOpen: () => void;
  onRemove: () => void;
}) {
  return (
    <div className={styles.card}>
      <div className={styles.cardHead} style={{ background: gradientFor(parcel.parcel_id) }}>
        {parcel.prototype_id && (
          <span className={styles.chip}>{vocab.prototype(parcel.prototype_id)}</span>
        )}
      </div>
      <div className={styles.cardBody}>
        <div className={styles.address}>{parcel.display_name}</div>
        <div className={styles.identity}>
          {PARCEL_ID_LABEL} {parcel.parcel_id.trim()}
          {parcel.ward ? ` · ${parcel.ward}` : ""}
        </div>
      </div>

      {/* All three share size and weight; only color differs. Explicit handoff correction. */}
      <div className={styles.metrics}>
        <div className={styles.metric}>
          <span className="micro-label">Value</span>
          <span className={`${styles.metricValue} ${styles.value}`}>
            {money(parcel.rlv_total)}
          </span>
        </div>
        <div className={styles.metric}>
          <span className="micro-label">Return</span>
          <span className={`${styles.metricValue} ${styles.plain}`}>
            {percent(parcel.irr)}
          </span>
        </div>
        <div className={styles.metric}>
          <span className="micro-label">Margin</span>
          <span className={`${styles.metricValue} ${styles.plain}`}>
            {percent(parcel.profit_margin)}
          </span>
        </div>
      </div>

      <div className={styles.cardFoot}>
        <span className={styles.saved}>{savedAgo(addedAt)}</span>
        <span>
          <button className={styles.remove} onClick={onRemove} title="Remove from this list">
            Remove
          </button>
          <button className={styles.link} onClick={onOpen}>
            Open
          </button>
        </span>
      </div>
    </div>
  );
}

export function Shortlist({
  lists,
  active,
  detail,
  vocab,
  busy,
  onSelect,
  onCreate,
  onOpenParcel,
  onRemove,
  onClose,
}: {
  lists: ShortlistSummary[];
  active: string | null;
  detail: ShortlistDetail | null;
  vocab: Vocabulary;
  busy: boolean;
  onSelect: (shortlistId: string) => void;
  onCreate: (name: string) => void;
  onOpenParcel: (parcelId: string) => void;
  onRemove: (parcelId: string) => void;
  onClose: () => void;
}) {
  const [newName, setNewName] = useState("");

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true" aria-label="Shortlists">
      <header className={styles.bar}>
        <span className={styles.title}>Shortlist</span>
        <button className={styles.close} onClick={onClose}>
          Close
        </button>
      </header>

      <div className={styles.body}>
        <nav className={styles.side}>
          <div className={`micro-label ${styles.sideHead}`}>Lists</div>
          {lists.map((list) => (
            <button
              key={list.shortlist_id}
              className={`${styles.listRow} ${list.shortlist_id === active ? styles.active : ""}`}
              onClick={() => onSelect(list.shortlist_id)}
            >
              <span>{list.name}</span>
              <span className={styles.listCount}>{list.parcel_count}</span>
            </button>
          ))}

          <form
            className={styles.newList}
            onSubmit={(event) => {
              event.preventDefault();
              if (!newName.trim()) return;
              onCreate(newName.trim());
              setNewName("");
            }}
          >
            <input
              className={styles.newInput}
              placeholder="New list…"
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
            />
            <button className={styles.newButton} type="submit" disabled={!newName.trim()}>
              Add
            </button>
          </form>

        </nav>

        <div className={styles.main}>
          {busy && <div className={styles.empty}>Reading the current bake…</div>}

          {!busy && !detail && (
            <div className={styles.empty}>
              {lists.length === 0
                ? "No lists yet. Name one on the left, then save parcels to it from the map."
                : "Pick a list."}
            </div>
          )}

          {!busy && detail && detail.parcels.length === 0 && (
            <div className={styles.empty}>
              Nothing saved to “{detail.name}” yet.
              <br />
              Click a parcel on the map and choose “Save”.
            </div>
          )}

          {!busy && detail && detail.parcels.length > 0 && (
            <>
              <div className={styles.grid}>
                {detail.parcels.map((parcel) => (
                  <Card
                    key={parcel.parcel_id}
                    parcel={parcel}
                    addedAt={detail.added_at[parcel.parcel_id]}
                    vocab={vocab}
                    onOpen={() => onOpenParcel(parcel.parcel_id)}
                    onRemove={() => onRemove(parcel.parcel_id)}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
