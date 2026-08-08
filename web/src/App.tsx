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
import {
  ApiError,
  NotModellable,
  getDefaultAssumptions,
  getMeta,
  getParcel,
  getUnderwrite,
  postUnderwrite,
} from "./lib/api";
import type { AssumptionSet, Meta, ParcelRecord, Underwrite } from "./lib/types";
import { changeCount, type Overrides } from "./lib/assumptions";
import { InputsModal } from "./components/InputsModal";
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
  // `fromEdits` marks a refusal the user caused and can undo. Without it the panel
  // cannot tell "this parcel is a park" from "your exit cap broke the program".
  | { kind: "not-modellable"; reason: string; fromEdits: boolean }
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
  const [selectedFromLink, setSelectedFromLink] = useState<string | null>(null);
  const [demolition, setDemolition] = useState(false);
  const [defaults, setDefaults] = useState<AssumptionSet | null>(null);
  const [overrides, setOverrides] = useState<Overrides>({});
  const [modalOpen, setModalOpen] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);
  const [rerunning, setRerunning] = useState(false);
  const [bootError, setBootError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([getMeta(), getDefaultAssumptions()])
      .then(([response, assumptions]) => {
        if (!live) return;
        setMeta(response);
        setObjective(response.default_objective);
        setDefaults(assumptions);
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

  const failed = useCallback((error: unknown, fromEdits: boolean): PanelState => {
    // A 422 is an answer about the parcel, not a fault — render the reason.
    if (error instanceof NotModellable) {
      return { kind: "not-modellable", reason: error.message, fromEdits };
    }
    if (error instanceof ApiError) return { kind: "error", message: error.message };
    return { kind: "error", message: String(error) };
  }, []);

  /** Run the full model on one parcel with a given set of inputs.
   *
   * GET when nothing is overridden, POST otherwise. That is not a style choice: the
   * default-assumption run is a pure function of parcel and batch, so it stays a cacheable,
   * linkable GET, and only an edited run needs a body. */
  const run = useCallback(
    (parcelId: string, next: { overrides: Overrides; demolition: boolean }) => {
      const edited = changeCount(next.overrides) > 0;
      return edited
        ? postUnderwrite(parcelId, { ...next.overrides, include_demolition: next.demolition })
        : getUnderwrite(parcelId, { includeDemolition: next.demolition });
    },
    [],
  );

  /** Open a parcel fresh: default inputs, as the bake ran it. */
  const underwrite = useCallback(
    (parcelId: string) => {
      setDemolition(false);
      setOverrides({});
      setPanel({ kind: "loading" });
      run(parcelId, { overrides: {}, demolition: false })
        .then((data) => setPanel({ kind: "ready", data }))
        .catch((error: unknown) => setPanel(failed(error, false)));
    },
    [run, failed],
  );

  /** The deliberate step into the full model, from the popup. */
  const openFull = useCallback(() => {
    if (selection?.parcelId) underwrite(selection.parcelId);
  }, [selection?.parcelId, underwrite]);

  /** `?parcel=<id>` opens the drill-down directly.
   *
   * A default-assumption underwrite is a pure function of the parcel and the batch, which
   * is why the endpoint is a cacheable GET — so a panel is genuinely linkable, and sharing
   * "look at this one" does not mean "open the map and hunt for it". */
  useEffect(() => {
    const parcelId = new URLSearchParams(window.location.search).get("parcel");
    if (parcelId) {
      setSelectedFromLink(parcelId);
      underwrite(parcelId);
    }
  }, [underwrite]);

  /** Demolition re-runs the whole model, so every figure in the panel moves with it.
   *
   * The previous result stays on screen while the new one is in flight rather than being
   * replaced by a spinner: the old numbers are still true for the old toggle state, and
   * blanking a dense panel for a second of work reads as a fault. */
  const changeDemolition = useCallback(
    (next: boolean) => {
      const parcelId = selection?.parcelId ?? selectedFromLink;
      if (!parcelId) return;
      setDemolition(next);
      setRerunning(true);
      run(parcelId, { overrides, demolition: next })
        .then((data) => setPanel({ kind: "ready", data }))
        // Demolition is itself an edit, so a refusal here is recoverable too.
        .catch((error: unknown) => setPanel(failed(error, true)))
        .finally(() => setRerunning(false));
    },
    [selection?.parcelId, selectedFromLink, overrides, run, failed],
  );

  /** The 1c modal's "Re-underwrite parcel".
   *
   * The modal closes ONLY when the run succeeds. A refusal keeps it open with the reason
   * shown beneath the inputs that caused it, because the alternative — closing, and
   * explaining the problem on a panel that no longer offers the fields — is a dead end. */
  const applyOverrides = useCallback(
    (next: Overrides) => {
      const parcelId = selection?.parcelId ?? selectedFromLink;
      if (!parcelId) return;
      setModalError(null);
      setRerunning(true);
      run(parcelId, { overrides: next, demolition })
        .then((data) => {
          // Committed only on success. Storing a rejected set would leave the app holding
          // inputs that never ran: cancelling out of the modal would look like a recovery
          // while the next demolition toggle silently re-sent the broken values.
          setOverrides(next);
          setPanel({ kind: "ready", data });
          setModalOpen(false);
        })
        .catch((error: unknown) => {
          if (error instanceof NotModellable) setModalError(error.message);
          else setPanel(failed(error, true));
        })
        .finally(() => setRerunning(false));
    },
    [selection?.parcelId, selectedFromLink, demolition, run, failed],
  );

  /** Back to the inputs the bake ran, from anywhere — including a refusal panel. */
  const resetToDefaults = useCallback(() => {
    const parcelId = selection?.parcelId ?? selectedFromLink;
    if (!parcelId) return;
    setOverrides({});
    setDemolition(false);
    setModalError(null);
    setModalOpen(false);
    setPanel({ kind: "loading" });
    run(parcelId, { overrides: {}, demolition: false })
      .then((data) => setPanel({ kind: "ready", data }))
      .catch((error: unknown) => setPanel(failed(error, false)));
  }, [selection?.parcelId, selectedFromLink, run, failed]);

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
              selectedId={selection?.parcelId ?? selectedFromLink}
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
          <Drilldown
            data={panel.data}
            vocab={vocab}
            demolition={demolition}
            busy={rerunning}
            onDemolitionChange={changeDemolition}
            onEditAssumptions={defaults ? () => setModalOpen(true) : undefined}
            onClose={closePanel}
          />
        )}
        {panel.kind === "not-modellable" && (
          <NotModellablePanel
            reason={panel.reason}
            recovery={
              panel.fromEdits
                ? {
                    onEditAssumptions: () => setModalOpen(true),
                    onReset: resetToDefaults,
                    changed: changeCount(overrides) + (demolition ? 1 : 0),
                  }
                : undefined
            }
            onClose={closePanel}
          />
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

      {modalOpen && defaults && meta && vocab && panel.kind !== "loading" && (
        <InputsModal
          defaults={defaults}
          labels={meta.labels}
          vocab={vocab}
          overrides={overrides}
          displayName={panel.kind === "ready" ? panel.data.display_name : "this parcel"}
          confidence={panel.kind === "ready" ? panel.data.confidence : 0}
          busy={rerunning}
          error={modalError}
          onApply={applyOverrides}
          onClose={() => {
            setModalOpen(false);
            setModalError(null);
          }}
        />
      )}
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
