/** App shell.
 *
 * The map is the next slice; until it lands, parcels are picked from a plain list off
 * /map/query so the drill-down can be exercised against real baked data. The list is
 * deliberately not dressed up to look like a map — a fake map would be harder to tell
 * apart from a broken one.
 */
import { useCallback, useEffect, useState } from "react";
import { ApiError, NotModellable, getMapQuery, getMeta, getUnderwrite } from "./lib/api";
import type { Meta, ParcelRow, Underwrite } from "./lib/types";
import { Vocabulary } from "./lib/vocabulary";
import { money } from "./lib/format";
import { Drilldown, NotModellablePanel } from "./components/Drilldown";
import styles from "./App.module.css";

type PanelState =
  | { kind: "empty" }
  | { kind: "loading" }
  | { kind: "ready"; data: Underwrite }
  | { kind: "not-modellable"; reason: string }
  | { kind: "error"; message: string };

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [rows, setRows] = useState<ParcelRow[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [panel, setPanel] = useState<PanelState>({ kind: "empty" });
  const [bootError, setBootError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([
      getMeta(),
      getMapQuery({ statuses: ["scored"], limit: 60, sort_dir: "desc" }),
    ])
      .then(([metaResponse, query]) => {
        if (!live) return;
        setMeta(metaResponse);
        setRows(query.rows);
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

  if (bootError) {
    return (
      <div className={styles.shell}>
        <div className={`${styles.panelState} ${styles.error}`} style={{ width: "100%" }}>
          {bootError}
          <br />
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
        <div className={styles.picker}>
          <div className={styles.pickerHead}>
            {rows.length
              ? `Top ${rows.length} by feasibility value — the map replaces this list.`
              : "Loading parcels…"}
          </div>
          <div className={styles.rows}>
            {rows.map((row) => (
              <button
                key={row.parcel_id}
                className={`${styles.row} ${selected === row.parcel_id ? styles.active : ""}`}
                onClick={() => open(row.parcel_id)}
              >
                <span className={styles.rowName}>{row.display_name}</span>
                <span className={styles.rowMeta}>{row.ward}</span>
                <span className={styles.rowValue}>{money(row.rlv_total)}</span>
              </button>
            ))}
          </div>
        </div>

        {panel.kind === "ready" && vocab && (
          <Drilldown
            data={panel.data}
            vocab={vocab}
            onClose={() => {
              setPanel({ kind: "empty" });
              setSelected(null);
            }}
          />
        )}
        {panel.kind === "not-modellable" && (
          <NotModellablePanel
            reason={panel.reason}
            onClose={() => setPanel({ kind: "empty" })}
          />
        )}
        {panel.kind === "loading" && (
          <div className={styles.panelState}>
            Running the full model…
            <br />
            This is the levered, monthly, IRR-solved tier — it takes a moment.
          </div>
        )}
        {panel.kind === "empty" && (
          <div className={styles.panelState}>Select a parcel to underwrite it.</div>
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
