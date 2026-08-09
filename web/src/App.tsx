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
  getShortlist,
  getShortlists,
  createShortlist,
  addToShortlist,
  removeFromShortlist,
  getUnderwrite,
  postUnderwrite,
  saveScenario,
  exportWorkbook,
} from "./lib/api";
import type {
  AssumptionSet,
  Meta,
  ParcelRecord,
  ShortlistDetail,
  ShortlistSummary,
  Underwrite,
} from "./lib/types";
import { changeCount, type Overrides } from "./lib/assumptions";
import { InputsModal } from "./components/InputsModal";
import { Vocabulary } from "./lib/vocabulary";
import { EMPTY_FILTERS, mapFilter, type FilterState } from "./lib/filters";
import { Drilldown, NotModellablePanel } from "./components/Drilldown";
import { Filters } from "./components/Filters";
import { Legend } from "./components/Legend";
import { MapView } from "./components/MapView";
import { Popup } from "./components/Popup";
import { Compare, CompareTray } from "./components/Compare";
import { Shortlist } from "./components/Shortlist";
import { MAX_COMPARE, toggleCompare } from "./lib/compare";
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
  // Whether the panel's current inputs have been saved as a scenario. Export no longer
  // depends on this — it re-runs server-side — but "Saved ✓" must stop claiming a save
  // that no longer describes what is on screen.
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const [exporting, setExporting] = useState(false);
  // Compare holds parcel IDS, not results: each column is a full-tier underwrite, and
  // running three of them on every selection change would be wasteful. They resolve when
  // the view opens.
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareRows, setCompareRows] = useState<Underwrite[] | null>(null);
  const [comparing, setComparing] = useState(false);
  const [lists, setLists] = useState<ShortlistSummary[]>([]);
  const [activeList, setActiveList] = useState<string | null>(null);
  const [listDetail, setListDetail] = useState<ShortlistDetail | null>(null);
  const [listOpen, setListOpen] = useState(false);
  const [listBusy, setListBusy] = useState(false);
  const [memberOf, setMemberOf] = useState<string[]>([]);
  const [bootError, setBootError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getShortlists().then(setLists).catch(() => undefined);
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
    setMemberOf([]);
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
      setSaveState("idle");
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
    const params = new URLSearchParams(window.location.search);
    const parcelId = params.get("parcel");
    if (parcelId) {
      setSelectedFromLink(parcelId);
      underwrite(parcelId);
    }
    // `?compare=a,b,c` opens the comparison directly, for the same reason `?parcel=` opens
    // the panel: "look at these three side by side" is a thing people send each other.
    const compare = params.get("compare");
    if (compare) {
      const ids = compare.split(",").map((id) => id.trim()).filter(Boolean).slice(0, MAX_COMPARE);
      if (ids.length) {
        setCompareIds(ids);
        setComparing(true);
        Promise.all(ids.map((id) => getUnderwrite(id)))
          .then(setCompareRows)
          .catch(() => undefined)
          .finally(() => setComparing(false));
      }
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
      setSaveState("idle");
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
          // The saved scenario froze the OLD inputs, so it no longer describes what is on
          // screen. Exporting it here would hand someone a file that disagrees with the
          // panel they were just looking at.
          setSaveState("idle");
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

  /** Freeze the current underwrite. The server re-runs from these inputs and stores its
   * own numbers, so what is saved is what the model said. */
  const save = useCallback(() => {
    const parcelId = selection?.parcelId ?? selectedFromLink;
    if (!parcelId) return;
    setSaveState("saving");
    saveScenario(parcelId, { ...overrides, include_demolition: demolition })
      .then(() => setSaveState("saved"))
      .catch((error: unknown) => setPanel(failed(error, changeCount(overrides) > 0)));
  }, [selection?.parcelId, selectedFromLink, overrides, demolition, failed]);

  /** Download a live Excel workbook of what is on screen. No save required.
   *
   * The server re-runs the model from these inputs and builds the file from its own
   * output, so the workbook cannot disagree with the panel. */
  const exportScenario = useCallback(() => {
    const parcelId = selection?.parcelId ?? selectedFromLink;
    if (!parcelId) return;
    setExporting(true);
    exportWorkbook(parcelId, { ...overrides, include_demolition: demolition })
      .catch((error: unknown) => setPanel(failed(error, changeCount(overrides) > 0)))
      .finally(() => setExporting(false));
  }, [selection?.parcelId, selectedFromLink, overrides, demolition, failed]);

  // --- shortlists --------------------------------------------------------
  const openList = useCallback((shortlistId: string) => {
    setActiveList(shortlistId);
    setListBusy(true);
    getShortlist(shortlistId)
      .then(setListDetail)
      .catch(() => setListDetail(null))
      .finally(() => setListBusy(false));
  }, []);

  const refreshLists = useCallback(
    (focus?: string) =>
      getShortlists().then((next) => {
        setLists(next);
        const target = focus ?? activeList ?? next[0]?.shortlist_id ?? null;
        if (target) openList(target);
        return next;
      }),
    [activeList, openList],
  );

  /** Toggle this parcel's membership of one list, from the popup. */
  const toggleSave = useCallback(
    (shortlistId: string) => {
      const parcelId = selection?.parcelId;
      if (!parcelId) return;
      const isMember = memberOf.includes(shortlistId);
      const action = isMember
        ? removeFromShortlist(shortlistId, parcelId)
        : addToShortlist(shortlistId, parcelId);
      setMemberOf((ids) =>
        isMember ? ids.filter((id) => id !== shortlistId) : [...ids, shortlistId],
      );
      action
        .then(() => getShortlists().then(setLists))
        .catch((error: unknown) => setPanel(failed(error, false)));
    },
    [selection?.parcelId, memberOf, failed],
  );

  const closePanel = useCallback(() => setPanel({ kind: "closed" }), []);

  /** Resolve the compare set. Each column is its own full model run (SPEC §9 keeps levered
   * IRR out of the bake), so this is the one place the app fires several at once. */
  const openCompare = useCallback(() => {
    setComparing(true);
    Promise.all(compareIds.map((id) => getUnderwrite(id)))
      .then((rows) => setCompareRows(rows))
      .catch((error: unknown) => setPanel(failed(error, false)))
      .finally(() => setComparing(false));
  }, [compareIds, failed]);

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
        <button
          className={styles.topAction}
          onClick={() => {
            setListOpen(true);
            if (!listDetail && lists[0]) openList(lists[0].shortlist_id);
          }}
        >
          Shortlist
          {lists.length > 0 && (
            <span className={styles.badge}>
              {lists.reduce((n, l) => n + l.parcel_count, 0)}
            </span>
          )}
        </button>
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
              inCompare={compareIds.includes(selection.parcelId)}
              canCompare={compareIds.length < MAX_COMPARE}
              onOpenFull={openFull}
              onToggleCompare={() =>
                setCompareIds((ids) => toggleCompare(ids, selection.parcelId))
              }
              lists={lists}
              memberOf={memberOf}
              onToggleSave={toggleSave}
              onClose={dismiss}
            />
          )}

          <CompareTray
            ids={compareIds}
            busy={comparing}
            onOpen={openCompare}
            onClear={() => setCompareIds([])}
          />
        </div>

        {panel.kind === "ready" && vocab && (
          <Drilldown
            data={panel.data}
            vocab={vocab}
            demolition={demolition}
            busy={rerunning}
            onDemolitionChange={changeDemolition}
            onEditAssumptions={defaults ? () => setModalOpen(true) : undefined}
            onSaveScenario={save}
            onExport={exportScenario}
            exporting={exporting}
            saveState={saveState}
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

      {listOpen && vocab && (
        <Shortlist
          lists={lists}
          active={activeList}
          detail={listDetail}
          vocab={vocab}
          busy={listBusy}
          onSelect={openList}
          onCreate={(name) =>
            createShortlist(name)
              .then((created) => refreshLists(created.shortlist_id))
              .catch((error: unknown) => setPanel(failed(error, false)))
          }
          onOpenParcel={(parcelId) => {
            setListOpen(false);
            setSelectedFromLink(parcelId);
            underwrite(parcelId);
          }}
          onRemove={(parcelId) => {
            if (!activeList) return;
            removeFromShortlist(activeList, parcelId)
              .then(() => refreshLists(activeList))
              .catch((error: unknown) => setPanel(failed(error, false)));
          }}
          onClose={() => setListOpen(false)}
        />
      )}

      {compareRows && vocab && (
        <Compare rows={compareRows} vocab={vocab} onClose={() => setCompareRows(null)} />
      )}

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
