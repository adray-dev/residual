/** App shell: the map, the legend, and the drill-down rail.
 *
 * The batch is resolved exactly once, by /meta, and everything downstream is pinned to
 * what it returned — the tileset URL it names and the rows it counted. That is the whole
 * point of that endpoint: if the map and the panel each resolved "latest bake"
 * independently, a bake landing between the two calls would leave them showing different
 * numbers for the same parcel with nothing on screen to reveal it.
 */
import { useCallback, useEffect, useState } from "react";
import { ApiError, NotModellable, getMeta, getUnderwrite } from "./lib/api";
import type { Meta, Underwrite } from "./lib/types";
import { Vocabulary } from "./lib/vocabulary";
import { Drilldown, NotModellablePanel } from "./components/Drilldown";
import { Legend } from "./components/Legend";
import { MapView } from "./components/MapView";
import styles from "./App.module.css";

type PanelState =
  | { kind: "empty" }
  | { kind: "loading" }
  | { kind: "ready"; data: Underwrite }
  | { kind: "not-modellable"; reason: string }
  | { kind: "error"; message: string };

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [objective, setObjective] = useState<string>("rlv_total");
  const [selected, setSelected] = useState<string | null>(null);
  const [panel, setPanel] = useState<PanelState>({ kind: "empty" });
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

  const open = useCallback((parcelId: string) => {
    setSelected(parcelId);
    setPanel({ kind: "loading" });
    getUnderwrite(parcelId)
      .then((data) => setPanel({ kind: "ready", data }))
      .catch((error: unknown) => {
        // A 422 is an answer about the parcel, not a fault — render the reason, not an error.
        if (error instanceof NotModellable) {
          setPanel({ kind: "not-modellable", reason: error.message });
        } else if (error instanceof ApiError) {
          setPanel({ kind: "error", message: error.message });
        } else {
          setPanel({ kind: "error", message: String(error) });
        }
      });
  }, []);

  const close = useCallback(() => {
    setPanel({ kind: "empty" });
    setSelected(null);
  }, []);

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

  const vocab = meta ? new Vocabulary(meta.labels) : null;

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
              selectedId={selected}
              onSelect={open}
            />
          ) : (
            // /meta returns null rather than a stale tileset when tiles have not been
            // built for THIS batch. Better an honest gap than a map quietly drawn from
            // the previous bake's numbers.
            <div className={styles.boot}>
              {meta
                ? "No tiles have been built for the current bake."
                : "Loading…"}
              {meta && (
                <>
                  <br />
                  <code>python -m tiles.build_tiles</code>
                </>
              )}
            </div>
          )}
          {meta && vocab && (
            <Legend
              meta={meta}
              vocab={vocab}
              objective={objective}
              onObjectiveChange={setObjective}
            />
          )}
        </div>

        {panel.kind === "ready" && vocab && (
          <Drilldown data={panel.data} vocab={vocab} onClose={close} />
        )}
        {panel.kind === "not-modellable" && (
          <NotModellablePanel reason={panel.reason} onClose={close} />
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
