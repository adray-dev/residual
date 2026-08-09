/** Screen 1d: the filtered set as sortable rows.
 *
 * Sorting and paging are SERVER-side. The filtered set runs to tens of thousands of
 * parcels, so sorting the loaded page would silently sort a slice and present it as the
 * ranking — the single most misleading thing a table like this can do.
 *
 * The Return column is the exception to everything else here: levered IRR does not exist
 * in the bake (SPEC §9), so the server runs the full model once per VISIBLE ROW. That is
 * why the page size is small and why Return is the one column you cannot sort by — ranking
 * on it would mean scoring the whole matching set, which is what the map's return filter is
 * for and why that one is bounded.
 */
import { useCallback, useEffect, useState } from "react";
import type { MapQuery, ParcelRow } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { getMapQuery, NotModellable } from "../lib/api";
import { count, money, percent } from "../lib/format";
import { queryParams, type FilterState } from "../lib/filters";
import { MAX_COMPARE } from "../lib/compare";
import styles from "./Table.module.css";

const PAGE_SIZE = 50;

/** Chip colour per build, from the map's own ramp so the table and the map agree. */
const BUILD_TINT: Record<string, { bg: string; fg: string }> = {
  townhome: { bg: "#eaf2f1", fg: "#0a5250" },
  garden: { bg: "#e9eef4", fg: "#2d5473" },
  midrise: { bg: "#fbf0e4", fg: "#8a5a21" },
  highrise: { bg: "#f4f2ed", fg: "#3d3b37" },
};

interface Column {
  key: string;
  label: string;
  /** Absent means the column cannot be sorted server-side. */
  sortKey?: string;
  render: (row: ParcelRow) => string;
  headline?: boolean;
}

/** Column headers use the handoff's SHORT names, not the full vocabulary labels.
 *
 * "Financial feasibility (RLV)" clipped to "ancial feasibility (RLV)" in a 132px column —
 * a header the reader has to decode is worse than a terse one. The full plain-language
 * label is what the drill-down and the map legend show; a table header is a column key. */
function columnsFor(_vocab: Vocabulary): Column[] {
  return [
    {
      key: "total_development_cost",
      label: "Total cost",
      sortKey: "total_development_cost",
      render: (r) => money(r.total_development_cost),
    },
    {
      key: "cost_per_unit",
      label: "Cost / unit",
      render: (r) =>
        r.total_development_cost && r.unit_count
          ? money(r.total_development_cost / r.unit_count)
          : "—",
    },
    { key: "noi", label: "NOI", sortKey: "noi", render: (r) => money(r.noi) },
    {
      key: "rlv_total",
      label: "Feasibility value",
      sortKey: "rlv_total",
      headline: true,
      render: (r) => money(r.rlv_total),
    },
    {
      key: "yield_on_cost",
      label: "Yield",
      sortKey: "yield_on_cost",
      render: (r) => percent(r.yield_on_cost),
    },
    // No sortKey: ranking by return means scoring the whole matching set, not this page.
    { key: "irr", label: "Return", render: (r) => percent(r.irr) },
  ];
}

/** Applied filters, as removable chips. */
function chipsFor(state: FilterState, vocab: Vocabulary): { label: string; clear: Partial<FilterState> }[] {
  const chips: { label: string; clear: Partial<FilterState> }[] = [];
  for (const ward of state.wards) {
    chips.push({
      label: ward.replace("ward_", "Ward "),
      clear: { wards: state.wards.filter((w) => w !== ward) },
    });
  }
  for (const proto of state.prototypes) {
    chips.push({
      label: vocab.prototype(proto),
      clear: { prototypes: state.prototypes.filter((p) => p !== proto) },
    });
  }
  if (state.rlvMin != null) {
    chips.push({ label: `Value ≥ ${money(state.rlvMin, 1)}`, clear: { rlvMin: null } });
  }
  if (state.rlvMax != null) {
    chips.push({ label: `Value ≤ ${money(state.rlvMax, 1)}`, clear: { rlvMax: null } });
  }
  return chips;
}

export function Table({
  filters,
  vocab,
  selected,
  onFiltersChange,
  onToggleSelect,
  onCompare,
  onOpenParcel,
  onShowMap,
}: {
  filters: FilterState;
  vocab: Vocabulary;
  selected: string[];
  onFiltersChange: (next: FilterState) => void;
  onToggleSelect: (parcelId: string) => void;
  onCompare: () => void;
  onOpenParcel: (parcelId: string) => void;
  onShowMap: () => void;
}) {
  const columns = columnsFor(vocab);
  const [sortKey, setSortKey] = useState("rlv_total");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(0);
  const [data, setData] = useState<MapQuery | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setBusy(true);
    getMapQuery(
      {
        ...queryParams(filters),
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        sort_key: sortKey,
        sort_dir: sortDir,
        with_returns: "true",
      },
      controller.signal,
    )
      .then((response) => {
        setData(response);
        setError(null);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof NotModellable || err instanceof Error ? err.message : String(err));
      })
      .finally(() => setBusy(false));
    return () => controller.abort();
  }, [filters, sortKey, sortDir, page]);

  const sort = useCallback(
    (key: string) => {
      if (key === sortKey) setSortDir((d) => (d === "desc" ? "asc" : "desc"));
      else {
        setSortKey(key);
        setSortDir("desc");
      }
      setPage(0);
    },
    [sortKey],
  );

  /** CSV of the rows on screen — a serialization of what the server returned, never a
   * recomputation. The page is what the user is looking at and what they mean by "this". */
  const exportCsv = useCallback(() => {
    if (!data) return;
    const head = ["Parcel ID", "Address", "Ward", "Best build", ...columns.map((c) => c.label)];
    const lines = [head.join(",")];
    for (const row of data.rows) {
      const cells = [
        row.parcel_id.trim(),
        row.display_name,
        row.ward ?? "",
        vocab.prototype(row.prototype_id),
        ...columns.map((c) => c.render(row).replace(/[$,×]/g, "")),
      ];
      lines.push(cells.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `residual-parcels-page-${page + 1}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }, [data, columns, vocab, page]);

  const chips = chipsFor(filters, vocab);
  const total = data?.total ?? 0;
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);
  const sortedLabel = columns.find((c) => c.sortKey === sortKey)?.label ?? sortKey;

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true" aria-label="Parcel table">
      <header className={styles.bar}>
        <span className={styles.wordmark}>Residual</span>
        <div className={styles.segmented} role="tablist">
          <button className={styles.segment} onClick={onShowMap} role="tab" aria-selected="false">
            Map
          </button>
          <button
            className={`${styles.segment} ${styles.active}`}
            role="tab"
            aria-selected="true"
          >
            Table
          </button>
        </div>
        <span className={styles.spacer} />
        <button
          className={styles.ghost}
          onClick={onCompare}
          disabled={selected.length < 2}
          title={`Compare up to ${MAX_COMPARE} selected parcels`}
        >
          Compare {selected.length} selected
        </button>
        <button className={styles.dark} onClick={exportCsv} disabled={!data?.rows.length}>
          Export CSV
        </button>
      </header>

      <div className={styles.filters}>
        <span className={styles.parcelCount}>
          <b>{total.toLocaleString()}</b> parcels
        </span>
        {chips.map((chip) => (
          <span className={styles.chip} key={chip.label}>
            {chip.label}
            <button
              className={styles.chipX}
              onClick={() => {
                onFiltersChange({ ...filters, ...chip.clear });
                setPage(0);
              }}
              aria-label={`Remove ${chip.label}`}
            >
              ×
            </button>
          </span>
        ))}
        <span className={styles.caption}>
          Sorted by {sortedLabel} · click a column to re-sort
        </span>
      </div>

      <div className={styles.scroll}>
        <div className={`${styles.row} ${styles.header}`}>
          <span className={styles.th} />
          <span className={styles.th}>Parcel</span>
          <span className={styles.th}>Ward</span>
          <span className={styles.th}>{vocab.metric("prototype_id")}</span>
          {columns.map((column) => (
            <span
              className={`${styles.th} ${styles.num} ${
                column.sortKey === sortKey ? styles.active : ""
              }`}
              key={column.key}
            >
              {column.sortKey ? (
                <button className={styles.sortable} onClick={() => sort(column.sortKey!)}>
                  {column.label}
                  {column.sortKey === sortKey && (
                    <span className={styles.arrow}>{sortDir === "desc" ? "▼" : "▲"}</span>
                  )}
                </button>
              ) : (
                <span title="Return runs the full model per row, so the table cannot rank by it">
                  {column.label}
                </span>
              )}
            </span>
          ))}
          <span className={styles.th}>{vocab.metric("gross_sf")}</span>
        </div>

        {error && <div className={styles.state}>{error}</div>}
        {!error && busy && !data && <div className={styles.state}>Reading the bake…</div>}
        {!error && data?.rows.length === 0 && (
          <div className={styles.state}>No parcels match these filters.</div>
        )}

        {!error &&
          data?.rows.map((row, index) => {
            const tint = BUILD_TINT[row.prototype_id ?? ""] ?? BUILD_TINT["highrise"]!;
            return (
              <div
                className={`${styles.row} ${styles.data} ${index % 2 ? styles.zebra : ""}`}
                key={row.parcel_id}
              >
                <span className={styles.check}>
                  <input
                    type="checkbox"
                    checked={selected.includes(row.parcel_id)}
                    onChange={() => onToggleSelect(row.parcel_id)}
                    aria-label={`Select ${row.display_name}`}
                  />
                </span>
                <span className={styles.parcelCell}>
                  <span className={styles.parcelName}>{row.display_name}</span>
                  <span className={styles.parcelId}>ID {row.parcel_id.trim()}</span>
                </span>
                <span className={styles.textCell}>{row.ward ?? "—"}</span>
                <span className={styles.textCell}>
                  {row.prototype_id && (
                    <span
                      className={styles.buildChip}
                      style={{ background: tint.bg, color: tint.fg }}
                    >
                      {vocab.prototype(row.prototype_id)}
                    </span>
                  )}
                </span>
                {columns.map((column) => (
                  <span
                    className={`${styles.cell} ${column.headline ? styles.headline : ""}`}
                    key={column.key}
                  >
                    {column.render(row)}
                  </span>
                ))}
                <span className={styles.openCell}>
                  <span className={styles.cell} style={{ padding: 0 }}>
                    {count(row.gross_sf)}
                  </span>
                  <button className={styles.open} onClick={() => onOpenParcel(row.parcel_id)}>
                    Open
                  </button>
                </span>
              </div>
            );
          })}
      </div>

      <footer className={styles.foot}>
        <button
          className={styles.ghost}
          onClick={() => setPage((p) => Math.max(0, p - 1))}
          disabled={page === 0 || busy}
        >
          Previous
        </button>
        <span className={styles.page}>
          Page <b>{page + 1}</b> of <b>{(lastPage + 1).toLocaleString()}</b>
        </span>
        <button
          className={styles.ghost}
          onClick={() => setPage((p) => Math.min(lastPage, p + 1))}
          disabled={page >= lastPage || busy}
        >
          Next
        </button>
        <span className={styles.note}>
          Sorting and paging run on the server across all {total.toLocaleString()} matches.
          Return is computed per visible row.
        </span>
      </footer>
    </div>
  );
}
