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
import { NotModellable } from "../lib/api";
import { domainMoney, roundedDomain } from "../lib/rampDomain";
import { EMPTY_FILTERS, isEmpty, mapQuery, toggle, type FilterState } from "../lib/filters";
import styles from "./Filters.module.css";

/** The build-type filter, as the USER's three products — smallest to largest.
 *
 * Each entry is the list of engine prototypes that product covers, because the engine has
 * four and the interface shows three: `5-over-1` and `midrise` are both "Multifamily",
 * separated in the model only so 4-7 storeys can be priced as the wood it is built from.
 * One checkbox therefore selects both ids, and the label comes from the first — /meta maps
 * both to the same string, so which one is asked is immaterial.
 *
 * Garden is absent: defined in `engine/prototypes.py` but benched (§5), so a chip for it
 * would always return zero. Its LABEL still exists server-side, because the retained
 * previous batch has garden winners whose rows must render a name.
 */
const BUILD_TYPES: string[][] = [["townhome"], ["5-over-1", "midrise"], ["highrise"]];

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={styles.group}>
      <div className={`micro-label ${styles.groupLabel}`}>{label}</div>
      {children}
    </div>
  );
}

/** A typed min/max pair.
 *
 * Boxes rather than sliders, for every program range: units, stories and building area are
 * values a user arrives with ("I want 50 to 200 units"), not values they discover by
 * dragging. A slider makes an exact number the hardest thing to enter, and these three
 * span 0–1,200, 0–14 and 0–400,000, so the same drag distance means wildly different
 * precision in each. Only the feasibility-value filter is still a slider, because that one
 * genuinely is a "how far along the distribution" question.
 *
 * A box also has no ceiling to invent. The slider's upper bound was whatever the current
 * bake happened to top out at, which quietly made "everything above 400,000 SF" unaskable.
 *
 * Empty means unbounded, which is why the state is `number | null` and not a sentinel.
 */
function NumberRange({
  min,
  max,
  step = 1,
  unit,
  showUnit = true,
  onChange,
}: {
  min: number | null;
  max: number | null;
  step?: number;
  unit?: string;
  /** Whether to PRINT the unit. It is always used for the field's accessible name, which
   *  has no heading above it to inherit meaning from the way the visible caption does. */
  showUnit?: boolean;
  onChange: (next: { min?: number | null; max?: number | null }) => void;
}) {
  // Raw text, so a half-typed value is not coerced mid-keystroke and clearing a box does
  // not immediately snap back to a bound.
  const [draft, setDraft] = useState<{ min?: string; max?: string }>({});

  const commit = (which: "min" | "max", text: string) => {
    setDraft((d) => ({ ...d, [which]: text }));
    if (text.trim() === "") {
      onChange({ [which]: null });
      return;
    }
    const value = Number(text);
    if (Number.isFinite(value) && value >= 0) onChange({ [which]: value });
  };

  const box = (which: "min" | "max", value: number | null, placeholder: string) => (
    <span className={styles.numberWrap}>
      <input
        className={styles.numberInput}
        type="number"
        inputMode="numeric"
        min={0}
        step={step}
        placeholder={placeholder}
        aria-label={`${which === "min" ? "Minimum" : "Maximum"} ${unit ?? "value"}`}
        value={draft[which] ?? (value == null ? "" : String(value))}
        onChange={(event) => commit(which, event.target.value)}
      />
    </span>
  );

  return (
    <div className={styles.numberRow}>
      {box("min", min, "Min")}
      <span className={styles.numberDash}>–</span>
      {box("max", max, "Max")}
      {showUnit && unit && <span className={styles.numberUnit}>{unit}</span>}
    </div>
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

  // The value slider's domain comes from the current bake, read from /meta's ramp, then
  // rounded outward so the track ends on a number rather than on wherever the extreme
  // parcel happened to land. Shared with the legend, which prints the same two numbers a
  // few hundred pixels away — see lib/rampDomain.
  const ramp = meta.ramps["rlv_total"];
  const { floor, ceiling } = roundedDomain(ramp?.min, ramp?.max);
  const step = Math.max(1, Math.round((ceiling - floor) / 200));

  useEffect(() => {
    // Debounced: dragging the value slider fires this on every tick otherwise, and a
    // typed box fires on every keystroke. Each one counts across 132k rows.
    setStale(true);
    const controller = new AbortController();
    const timer = setTimeout(() => {
      mapQuery(state, {}, controller.signal)
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
        {/* Only present once there is one. A drawn area is made on the map, not here — but
            it is a filter, so it has to be visible where the filters are, or Reset clearing
            it comes out of nowhere. */}
        {state.drawnPolygon && (
          <Group label="Drawn area">
            <div className={styles.areaRow}>
              <span className={styles.areaText}>
                {state.drawnPolygon.coordinates[0]
                  ? `${state.drawnPolygon.coordinates[0].length - 1} corners`
                  : "Custom shape"}
              </span>
              <button
                className={styles.areaClear}
                onClick={() => set({ drawnPolygon: null })}
              >
                Clear
              </button>
            </div>
          </Group>
        )}

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
            <span className={styles.sliderValue}>{domainMoney(state.rlvMin ?? floor)}</span>
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
            <span className={styles.sliderValue}>{domainMoney(state.rlvMax ?? ceiling)}</span>
          </div>
        </Group>

        <Group label={vocab.metric("prototype_id")}>
          <div className={styles.checks}>
            {BUILD_TYPES.map((ids) => {
              // Checked when the group is fully selected; toggling adds or removes the
              // whole group, so a half-selected "Multifamily" is not reachable from here.
              const on = ids.every((id) => state.prototypes.includes(id));
              return (
                <label className={styles.check} key={ids.join()}>
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() =>
                      set({
                        prototypes: on
                          ? state.prototypes.filter((p) => !ids.includes(p))
                          : [...state.prototypes, ...ids.filter((id) => !state.prototypes.includes(id))],
                      })
                    }
                  />
                  {vocab.prototype(ids[0])}
                </label>
              );
            })}
          </div>
        </Group>

        <Group label="Units">
          <NumberRange
            min={state.unitsMin}
            max={state.unitsMax}
            unit="units"
            showUnit={false}
            step={5}
            onChange={(patch) =>
              set({
                ...(patch.min !== undefined ? { unitsMin: patch.min } : {}),
                ...(patch.max !== undefined ? { unitsMax: patch.max } : {}),
              })
            }
          />
        </Group>

        <Group label="Stories">
          <NumberRange
            min={state.floorsMin}
            max={state.floorsMax}
            unit="floors"
            showUnit={false}
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
              <NumberRange
                min={state.buildingSfMin}
                max={state.buildingSfMax}
                step={1000}
                unit="SF"
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
          <b>{(matched ?? 0).toLocaleString()}</b> parcels matched
        </span>
      </div>
    </aside>
  );
}
