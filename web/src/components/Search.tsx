/** The 1a search field: address, parcel ID, ward, or neighbourhood.
 *
 * Picking a result moves the MAP to the parcel and selects it, rather than opening a panel
 * directly. Search on a map screen means "take me there" — landing in a drill-down with no
 * idea where the parcel sits would answer a different question. The full model is still one
 * deliberate click away, from the popup.
 *
 * The placeholder names a real DC neighbourhood rather than the handoff's "Shaw", because
 * the parcel layer stores assessment-district names ("Old City 1", "R. L. A. SW",
 * "Trinidad") and searching Shaw genuinely returns nothing. A placeholder that promises
 * something the data cannot do is worse than a plainer one.
 */
import { useEffect, useRef, useState } from "react";
import { searchParcels } from "../lib/api";
import type { SearchResult } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { STATUS_COLORS } from "../lib/mapStyle";
import styles from "./Search.module.css";

const STATUS_DOT: Record<string, string> = {
  scored: "#0e7c7b",
  infeasible: STATUS_COLORS.infeasible,
  exempt: STATUS_COLORS.exempt,
  historic: STATUS_COLORS.historic,
  zone_not_encoded: STATUS_COLORS.zone_not_encoded_border,
};

export function Search({
  vocab,
  onPick,
}: {
  vocab: Vocabulary;
  onPick: (result: SearchResult) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [busy, setBusy] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  // Picking a result writes the parcel's name into the field, which looks to the debounce
  // like the user typing — so the list would reopen ~200ms later showing the thing they
  // just chose. This suppresses exactly that one round trip.
  const fromPick = useRef(false);

  // Debounced: this is a LIKE across 132,632 parcels, and firing it per keystroke would
  // queue queries faster than they return.
  useEffect(() => {
    if (fromPick.current) {
      fromPick.current = false;
      return;
    }
    const term = query.trim();
    if (term.length < 2) {
      setResults([]);
      return;
    }
    const controller = new AbortController();
    setBusy(true);
    const timer = setTimeout(() => {
      searchParcels(term, controller.signal)
        .then((hits) => {
          setResults(hits);
          setActive(0);
          setOpen(true);
        })
        .catch(() => undefined)
        .finally(() => setBusy(false));
    }, 180);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  // Clicking anywhere else dismisses the list.
  useEffect(() => {
    const away = (event: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, []);

  const pick = (result: SearchResult) => {
    onPick(result);
    fromPick.current = true;
    setOpen(false);
    setQuery(result.display_name);
  };

  return (
    <div className={styles.wrap} ref={wrap}>
      <div className={styles.field}>
        <input
          className={styles.input}
          value={query}
          placeholder="Old City 1, Ward 6, 1301 Delaware Ave SW"
          aria-label="Search parcels"
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => results.length && setOpen(true)}
          onKeyDown={(event) => {
            if (!open || !results.length) return;
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActive((i) => Math.min(i + 1, results.length - 1));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((i) => Math.max(i - 1, 0));
            } else if (event.key === "Enter") {
              event.preventDefault();
              const hit = results[active];
              if (hit) pick(hit);
            } else if (event.key === "Escape") {
              setOpen(false);
            }
          }}
        />
        {query ? (
          <button
            className={styles.clear}
            onClick={() => {
              setQuery("");
              setResults([]);
              setOpen(false);
            }}
            aria-label="Clear search"
          >
            ×
          </button>
        ) : (
          <span className={styles.hint}>address · parcel ID · ward</span>
        )}
      </div>

      {open && (
        <div className={styles.results} role="listbox">
          {busy && results.length === 0 && <div className={styles.state}>Searching…</div>}
          {!busy && results.length === 0 && (
            <div className={styles.state}>Nothing matches “{query.trim()}”.</div>
          )}
          {results.map((result, index) => (
            <button
              key={result.parcel_id}
              role="option"
              aria-selected={index === active}
              className={`${styles.result} ${index === active ? styles.active : ""}`}
              onMouseEnter={() => setActive(index)}
              onClick={() => pick(result)}
            >
              <span
                className={styles.dot}
                style={{ background: STATUS_DOT[result.status] ?? STATUS_COLORS.infeasible }}
                title={vocab.status(result.status)}
              />
              <span className={styles.resultText}>
                <span className={styles.resultName}>{result.display_name}</span>
                <span className={styles.resultMeta}>
                  {[result.ward, result.neighborhood, vocab.status(result.status)]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
