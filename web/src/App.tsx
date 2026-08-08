/** App shell: map, filters, legend, popup, and the drill-down rail.
 *
 * The batch is resolved exactly once, by /meta, and everything downstream is pinned to
 * what it returned — the tileset URL it names and the ramps it computed. That is the whole
 * point of that endpoint: if the map and the panel each resolved "latest bake"
 * independently, a bake landing between the two calls would leave them showing different
 * numbers for the same parcel with nothing on screen to reveal it.
 *
 * Clicking a parcel is deliberately cheap. It reads the record (`/parcel/{id}`, a bake
 * lookup) and shows the popup; the levered monthly model only runs when the user asks for
 * it. Triage has to stay instant or the map stops being usable for finding anything.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, NotModellable, getMeta, getParcel, getUnderwrite } from "./lib/api";
import type { Meta, ParcelRecord, Underwrite } from "./lib/types";
import { Vocabulary } from "./lib/vocabulary";
import { EMPTY_FILTERS, mapFilter, type FilterState } from "./lib/filters";
import { Drilldown, NotModellablePanel } from "./components/Drilldown";
import { Filters } from "./components/Filters";
import { Legend } from "./components/Legend";
import { MapView } from "./components/MapView";
import { Popup } from "./components/Popup";
import styles from "./App.module.css";

type PanelState =
  | { kind: "closed" }
  | { kind: "loading" }
  | { kind: "ready"; data: Underwrite }
  | { kind: "not-modellable"; reason: string }
  | { kind: "error"; message: string };

interface Selection {
  parcelId: string;
  at: { x: number; y: number };
  record: ParcelRecord | null;
}

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [objective, setObjective] = useState("rlv_total");
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [panel, setPanel] = useState<PanelState>({ kind: "closed" });
  const [bootError, setBootError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getMeta()
      .then((response) => {
        if (!live) return;
        setMeta(response);
        setObjective(response.default_objective);
      })
      .catch((error: unknown) => {
        if (live) setBootError(error instanceof Error ? error.message : String(error));
      });
    return () => {
      live = false;
    };
  }, []);

  /** Map click: show the popup immediately, fill in the record when it lands. */
  const select = useCallback((parcelId: string, at: { x: number; y: number }) => {
    setSelection({ parcelId, at, record: null });
    setPanel({ kind: "closed" });
    getParcel(parcelId)
      .then((record) =>
        // Ignore a response for a parcel the user has already clicked away from.
        setSelection((current) =>
          current?.parcelId === parcelId ? { ...current, record } : current,
        ),
      )
      .catch(() => setSelection((current) => (current?.parcelId === parcelId ? null : current)));
  }, []);

  const dismiss = useCallback(() => setSelection(null), []);

  /** The deliberate step into the full model. */
  const openFull = useCallback(() => {
    const parcelId = selection?.parcelId;
    if (!parcelId) return;
    setPanel({ kind: "loading" });
    getUnderwrite(parcelId)
      .then((data) => setPanel({ kind: "ready", data }))
      .catch((error: unknown) => {
        // A 422 is an answer about the parcel, not a fault — render the reason.
        if (error instanceof NotModellable) {
          setPanel({ kind: "not-modellable", reason: error.message });
        } else if (error instanceof ApiError) {
          setPanel({ kind: "error", message: error.message });
        } else {
          setPanel({ kind: "error", message: String(error) });
        }
      });
  }, [selection?.parcelId]);

  const closePanel = useCallback(() => setPanel({ kind: "closed" }), []);

  const filter = useMemo(() => mapFilter(filters), [filters]);
  const vocab = useMemo(() => (meta ? new Vocabulary(meta.labels) : null), [meta]);

  if (bootError) {
    return (
      <div className={styles.shell}>
        <div className={styles.boot}>
          <div className={styles.error}>{bootError}</div>
          Is the API running? <code>uvicorn api.main:app --reload</code>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.shell}>
      <header className={styles.topbar}>
        <Logo />
        <span className={styles.wordmark}>Residual</span>
        {meta && (
          <span className={styles.batch}>
            {meta.parcel_count.toLocaleString()} parcels · baked{" "}
            {new Date(meta.computed_at).toLocaleDateString()}
          </span>
        )}
      </header>

      <main className={styles.main}>
        <div className={styles.mapArea}>
          {meta?.tileset_url ? (
            <MapView
              tilesetUrl={meta.tileset_url}
              objective={objective}
              selectedId={selection?.parcelId ?? null}
              filter={filter}
              onSelect={select}
              onSelectNothing={dismiss}
            />
          ) : (
            // /meta returns null rather than a stale tileset when tiles have not been
            // built for THIS batch. Better an honest gap than a map quietly drawn from
            // the previous bake's numbers.
            <div className={styles.boot}>
              {meta ? "No tiles have been built for the current bake." : "Loading…"}
              {meta && (
                <>
                  <br />
                  <code>python -m tiles.build_tiles</code>
                </>
              )}
            </div>
          )}

          {meta && vocab && (
            <>
              <Filters meta={meta} vocab={vocab} state={filters} onChange={setFilters} />
              <Legend
                meta={meta}
                vocab={vocab}
                objective={objective}
                onObjectiveChange={setObjective}
              />
            </>
          )}

          {selection && vocab && (
            <Popup
              at={selection.at}
              record={selection.record}
              vocab={vocab}
              busy={panel.kind === "loading"}
              onOpenFull={openFull}
              onClose={dismiss}
            />
          )}
        </div>

        {panel.kind === "ready" && vocab && (
          <Drilldown data={panel.data} vocab={vocab} onClose={closePanel} />
        )}
        {panel.kind === "not-modellable" && (
          <NotModellablePanel reason={panel.reason} onClose={closePanel} />
        )}
        {panel.kind === "loading" && (
          <div className={styles.panelState}>
            Running the full model…
            <br />
            This is the levered, monthly, IRR-solved tier — it takes a moment.
          </div>
        )}
        {panel.kind === "error" && (
          <div className={`${styles.panelState} ${styles.error}`}>{panel.message}</div>
        )}
      </main>
    </div>
  );
}

/** The handoff's mark: building massing on a ground line. Inline SVG, no icon font. */
function Logo() {
  return (
    <svg width="24" height="24" viewBox="0 0 26 26" aria-hidden="true">
      <rect width="26" height="26" rx="7" fill="var(--accent)" />
      <rect x="6" y="13" width="4" height="7" fill="#fff" opacity=".5" />
      <rect x="11.5" y="9" width="4" height="11" fill="#fff" opacity=".78" />
      <rect x="17" y="5.5" width="4" height="14.5" fill="#fff" />
      <rect x="5" y="21.5" width="16" height="1.6" rx=".8" fill="#fff" opacity=".92" />
    </svg>
  );
}
