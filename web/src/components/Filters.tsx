/** The left filter pane.
 *
 * Docked, not floating: it is a permanent part of the layout now, so the map is what is
 * left over rather than something the panel sits on top of.
 *
 * Narrowing is instant on the map — a MapLibre expression over attributes already in the
 * tile, no round trip — while the "N parcels match" count is a server read, because the
 * tile only knows what is loaded in view and the count is a claim about the whole city.
 * Both come from one `FilterState` so they cannot drift.
 *
 * Every filter here has a matching tile attribute. That is a hard rule, learned the hard
 * way: a filter with no attribute behind it can only narrow the count while the map sits
 * unchanged, which reads as a broken control. Units, stories and building area were added
 * to the tile for exactly this, and the "for sale" control is inert precisely because
 * there is no data behind it yet.
 */
import { useEffect, useState } from "react";
import type { Meta } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { getMapQuery, NotModellable } from "../lib/api";
import { count, money } from "../lib/format";
import { EMPTY_FILTERS, isEmpty, queryParams, toggle, type FilterState } from "../lib/filters";
import styles from "./Filters.module.css";

/** The four SPEC prototypes, smallest build to largest. */
const PROTOTYPES = ["townhome", "garden", "midrise", "highrise"];

/** Upper bounds for the program sliders, from what the bake actually contains. */
const UNITS_CEILING = 1200;
const FLOORS_CEILING = 14;
const BUILDING_SF_CEILING = 400_000;

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={styles.group}>
      <div className={`micro-label ${styles.groupLabel}`}>{label}</div>
      {children}
    </div>
  );
}

/** A named min/max pair. Each handle clamps AT the other rather than pushing it. */
function Range({
  min,
  max,
  ceiling,
  step,
  format,
  onChange,
}: {
  min: number | null;
  max: number | null;
  ceiling: number;
  step: number;
  format: (value: number) => string;
  onChange: (next: { min?: number | null; max?: number | null }) => void;
}) {
  return (
    <>
      <div className={styles.sliderRow}>
        <span className={styles.sliderLabel}>Min</span>
        <input
          className={styles.slider}
          type="range"
          min={0}
          max={ceiling}
          step={step}
          value={min ?? 0}
          onChange={(event) => {
            const value = Math.min(Number(event.target.value), max ?? ceiling);
            onChange({ min: value <= 0 ? null : value });
          }}
        />
        <span className={styles.sliderValue}>{format(min ?? 0)}</span>
      </div>
      <div className={styles.sliderRow}>
        <span className={styles.sliderLabel}>Max</span>
        <input
          className={styles.slider}
          type="range"
          min={0}
          max={ceiling}
          step={step}
          value={max ?? ceiling}
          onChange={(event) => {
            const value = Math.max(Number(event.target.value), min ?? 0);
            onChange({ max: value >= ceiling ? null : value });
          }}
        />
        <span className={styles.sliderValue}>
          {max == null ? `${format(ceiling)}+` : format(max)}
        </span>
      </div>
    </>
  );
}

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

  // The value slider's domain is the actual range of the current bake, read from /meta's
  // ramp, so a handle cannot be dragged to a value no parcel has.
  const ramp = meta.ramps["rlv_total"];
  const floor = Math.floor(ramp?.min ?? 0);
  const ceiling = Math.ceil(ramp?.max ?? 0);
  const step = Math.max(1, Math.round((ceiling - floor) / 200));

  useEffect(() => {
    // Debounced: dragging a slider fires this on every tick otherwise, and each one counts
    // across 132k rows.
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
    <aside className={styles.pane}>
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
        <Group label="Geography">
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
        </Group>

        <Group label={vocab.metric("rlv_total")}>
          <div className={styles.sliderRow}>
            <span className={styles.sliderLabel}>Min</span>
            <input
              className={styles.slider}
              type="range"
              min={floor}
              max={ceiling}
              step={step}
              value={state.rlvMin ?? floor}
              aria-label="Minimum feasibility value"
              onChange={(event) => {
                const value = Math.min(Number(event.target.value), state.rlvMax ?? ceiling);
                set({ rlvMin: value <= floor ? null : value });
              }}
            />
            <span className={styles.sliderValue}>{money(state.rlvMin ?? floor, 1)}</span>
          </div>
          <div className={styles.sliderRow}>
            <span className={styles.sliderLabel}>Max</span>
            <input
              className={styles.slider}
              type="range"
              min={floor}
              max={ceiling}
              step={step}
              value={state.rlvMax ?? ceiling}
              aria-label="Maximum feasibility value"
              onChange={(event) => {
                const value = Math.max(Number(event.target.value), state.rlvMin ?? floor);
                set({ rlvMax: value >= ceiling ? null : value });
              }}
            />
            <span className={styles.sliderValue}>{money(state.rlvMax ?? ceiling, 1)}</span>
          </div>
        </Group>

        <Group label={vocab.metric("prototype_id")}>
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
        </Group>

        <Group label="Units">
          <Range
            min={state.unitsMin}
            max={state.unitsMax}
            ceiling={UNITS_CEILING}
            step={5}
            format={(v) => count(v)}
            onChange={(patch) =>
              set({
                ...(patch.min !== undefined ? { unitsMin: patch.min } : {}),
                ...(patch.max !== undefined ? { unitsMax: patch.max } : {}),
              })
            }
          />
        </Group>

        <Group label="Stories">
          <Range
            min={state.floorsMin}
            max={state.floorsMax}
            ceiling={FLOORS_CEILING}
            step={1}
            format={(v) => String(v)}
            onChange={(patch) =>
              set({
                ...(patch.min !== undefined ? { floorsMin: patch.min } : {}),
                ...(patch.max !== undefined ? { floorsMax: patch.max } : {}),
              })
            }
          />
        </Group>

        <Group label="Existing building">
          <label className={styles.check}>
            <input
              type="checkbox"
              checked={state.vacantOnly}
              onChange={(event) =>
                set({
                  vacantOnly: event.target.checked,
                  // Vacant means zero building area, so a building-area range alongside it
                  // would be two controls arguing about the same number.
                  ...(event.target.checked ? { buildingSfMin: null, buildingSfMax: null } : {}),
                })
              }
            />
            Vacant land only
          </label>
          {!state.vacantOnly && (
            <div className={styles.subRange}>
              <Range
                min={state.buildingSfMin}
                max={state.buildingSfMax}
                ceiling={BUILDING_SF_CEILING}
                step={1000}
                format={(v) => `${count(v)} SF`}
                onChange={(patch) =>
                  set({
                    ...(patch.min !== undefined ? { buildingSfMin: patch.min } : {}),
                    ...(patch.max !== undefined ? { buildingSfMax: patch.max } : {}),
                  })
                }
              />
            </div>
          )}
        </Group>

        {/* Inert on purpose. There is no for-sale data in the platform, so this reserves
            the space and says so rather than shipping a control that silently does
            nothing — the failure mode of a filter that looks live and is not. */}
        <Group label="Listing status">
          <label className={`${styles.check} ${styles.disabled}`}>
            <input type="checkbox" disabled />
            For sale only
            <span className={styles.soon}>Coming soon</span>
          </label>
        </Group>
      </div>

      {note && <div className={styles.note}>{note}</div>}

      <div className={styles.foot}>
        <span className={`${styles.count} ${stale ? styles.countStale : ""}`}>
          <b>{(matched ?? 0).toLocaleString()}</b> priced parcels match
        </span>
      </div>
    </aside>
  );
}
