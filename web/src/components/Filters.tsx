/** The 1a filter panel.
 *
 * Narrowing is instant on the map (a MapLibre expression over tile attributes, no round
 * trip) while the "N parcels match" count is a server read, because the tile only knows
 * what is loaded in view and the count is a claim about the whole city. Both come from
 * one `FilterState` so they cannot drift — see `lib/filters.ts`.
 */
import { useEffect, useState } from "react";
import type { Meta } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { getMapQuery, NotModellable } from "../lib/api";
import { money } from "../lib/format";
import { EMPTY_FILTERS, isEmpty, queryParams, toggle, type FilterState } from "../lib/filters";
import styles from "./Filters.module.css";

/** The four SPEC prototypes, in the handoff's order (smallest build to largest). */
const PROTOTYPES = ["townhome", "garden", "midrise", "highrise"];

export function Filters({
  meta,
  vocab,
  state,
  onChange,
}: {
  meta: Meta;
  vocab: Vocabulary;
  state: FilterState;
  onChange: (next: FilterState) => void;
}) {
  const [matched, setMatched] = useState<number | null>(null);
  const [stale, setStale] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  // The slider domain is the actual range of the current bake, read from /meta's ramp,
  // so the handles cannot be dragged to a value no parcel has.
  const ramp = meta.ramps["rlv_total"];
  const floor = Math.floor(ramp?.min ?? 0);
  const ceiling = Math.ceil(ramp?.max ?? 0);
  const step = Math.max(1, Math.round((ceiling - floor) / 200));

  useEffect(() => {
    // Debounced: dragging a slider fires this on every tick otherwise, and each one is a
    // count over 132k rows.
    setStale(true);
    const controller = new AbortController();
    const timer = setTimeout(() => {
      getMapQuery(queryParams(state), controller.signal)
        .then((response) => {
          setMatched(response.total);
          setNote(null);
          setStale(false);
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          // The server refuses an IRR filter over too large a set with an actionable
          // sentence; show it rather than a silent empty count.
          if (error instanceof NotModellable) setNote(error.message);
          setStale(false);
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [state]);

  const set = (patch: Partial<FilterState>) => onChange({ ...state, ...patch });

  return (
    <div className={styles.panel}>
      <div className={styles.head}>
        <span className={styles.title}>Filters</span>
        <button
          className={styles.reset}
          disabled={isEmpty(state)}
          onClick={() => onChange(EMPTY_FILTERS)}
        >
          Reset
        </button>
      </div>
      <div className={styles.rule} />

      <div className={styles.body}>
        <div className={styles.group}>
          <div className={`micro-label ${styles.groupLabel}`}>Geography</div>
          <div className={styles.chips}>
            {meta.submarkets.map((submarket) => (
              <button
                key={submarket.submarket_id}
                className={`${styles.chip} ${
                  state.wards.includes(submarket.submarket_id) ? styles.on : ""
                }`}
                onClick={() => set({ wards: toggle(state.wards, submarket.submarket_id) })}
              >
                {submarket.name}
              </button>
            ))}
          </div>
        </div>

        <div className={styles.group}>
          <div className={`micro-label ${styles.groupLabel}`}>
            {vocab.metric("rlv_total")}
          </div>
          <div className={styles.readout}>
            {money(state.rlvMin ?? floor, 1)} – {money(state.rlvMax ?? ceiling, 1)}
          </div>
          <input
            className={styles.slider}
            type="range"
            min={floor}
            max={ceiling}
            step={step}
            value={state.rlvMin ?? floor}
            aria-label="Minimum feasibility value"
            onChange={(event) => {
              const value = Number(event.target.value);
              set({
                rlvMin: value <= floor ? null : value,
                // Keep the handles from crossing, which would match nothing and look broken.
                rlvMax: state.rlvMax != null && value > state.rlvMax ? value : state.rlvMax,
              });
            }}
          />
          <input
            className={styles.slider}
            type="range"
            min={floor}
            max={ceiling}
            step={step}
            value={state.rlvMax ?? ceiling}
            aria-label="Maximum feasibility value"
            onChange={(event) => {
              const value = Number(event.target.value);
              set({
                rlvMax: value >= ceiling ? null : value,
                rlvMin: state.rlvMin != null && value < state.rlvMin ? value : state.rlvMin,
              });
            }}
          />
          <div className={styles.hint}>
            {ramp
              ? `${ramp.negative_count.toLocaleString()} of ${(
                  ramp.negative_count + ramp.positive_count
                ).toLocaleString()} scored parcels price below $0.`
              : ""}
          </div>
        </div>

        <div className={styles.group}>
          <div className={`micro-label ${styles.groupLabel}`}>
            {vocab.metric("prototype_id")}
          </div>
          <div className={styles.checks}>
            {PROTOTYPES.map((prototype) => (
              <label className={styles.check} key={prototype}>
                <input
                  type="checkbox"
                  checked={state.prototypes.includes(prototype)}
                  onChange={() => set({ prototypes: toggle(state.prototypes, prototype) })}
                />
                {vocab.prototype(prototype)}
              </label>
            ))}
          </div>
        </div>

      </div>

      {note && <div className={styles.note}>{note}</div>}

      <div className={styles.foot}>
        {/* "Priced", because the filters below only exist for scored parcels — value and
            best build are meaningless on land the model could not price, and quoting a
            bare count beside a map drawing all 132,632 would read as a contradiction. */}
        <span className={`${styles.count} ${stale ? styles.countStale : ""}`}>
          <b>{(matched ?? 0).toLocaleString()}</b> priced parcels match
        </span>
      </div>
    </div>
  );
}
