/** The 1c inputs modal: change assumptions for one parcel and re-underwrite.
 *
 * Every field is generated from `/assumptions/default` filtered by the labels the server
 * ships, never from a hard-coded list. That is what guarantees the modal cannot offer an
 * input `build_assumptions` would silently drop, and cannot miss one the engine gained —
 * the handoff's mock, for instance, lists a "Hard cost $/SF" field that is market data
 * here, not an assumption, and would have done nothing at all.
 *
 * Edits are held in a working copy and only committed on "Re-underwrite parcel". Typing in
 * a field must not fire the full levered model on every keystroke.
 *
 * Provenance is deliberately absent. The engine tracks national/submarket/local sourcing
 * per input; the handoff's language rules say the UI shows values only, with confidence as
 * the one number that summarises how much to trust them.
 */
import { useMemo, useState } from "react";
import type { AssumptionGroups } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { confidence as formatConfidence } from "../lib/format";
import {
  EDITABLE_GROUPS,
  changeCount,
  diffFromDefaults,
  fieldsFor,
  fromDisplay,
  toDisplay,
  unitOf,
  workingCopy,
  applyOverrides,
  type EditableGroup,
  type Overrides,
} from "../lib/assumptions";
import styles from "./InputsModal.module.css";

export interface InputsModalProps {
  defaults: AssumptionGroups;
  labels: { assumption: Record<string, string>; assumption_kind: Record<string, string> };
  vocab: Vocabulary;
  /** Overrides currently in effect, so reopening shows the edits, not the defaults. */
  overrides: Overrides;
  /** Address, never the parcel id — the handoff edits "for {address} only". */
  displayName: string;
  confidence: number;
  busy: boolean;
  onApply: (overrides: Overrides) => void;
  onClose: () => void;
}

export function InputsModal({
  defaults,
  labels,
  vocab,
  overrides,
  displayName,
  confidence,
  busy,
  onApply,
  onClose,
}: InputsModalProps) {
  const [working, setWorking] = useState(() =>
    applyOverrides(workingCopy(defaults), overrides),
  );
  // Raw text per field, so a half-typed "3." or "" is not coerced to a number mid-keystroke.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [group, setGroup] = useState<EditableGroup>("timeline");

  const fieldsByGroup = useMemo(
    () =>
      Object.fromEntries(
        EDITABLE_GROUPS.map((g) => [g, fieldsFor(g, defaults, labels.assumption)]),
      ) as Record<EditableGroup, string[]>,
    [defaults, labels.assumption],
  );

  const pending = diffFromDefaults(working, defaults);
  const changed = changeCount(pending);
  const invalid = Object.values(drafts).some((text) => text !== "" && !Number.isFinite(Number(text)));

  const editedIn = (g: EditableGroup) => Object.keys(pending[g] ?? {}).length;

  const setField = (g: EditableGroup, key: string, text: string) => {
    setDrafts((d) => ({ ...d, [`${g}.${key}`]: text }));
    const parsed = Number(text);
    if (text === "" || !Number.isFinite(parsed)) return;
    const kind = labels.assumption_kind[key];
    setWorking((w) => ({ ...w, [g]: { ...w[g], [key]: fromDisplay(parsed, kind) } }));
  };

  const reset = () => {
    setWorking(workingCopy(defaults));
    setDrafts({});
  };

  return (
    <div
      className={styles.scrim}
      role="dialog"
      aria-modal="true"
      aria-label="Model inputs"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className={styles.modal}>
        <header className={styles.head}>
          <div className={styles.headText}>
            <div className={styles.title}>
              Inputs — {changed ? "Edited" : "Defaults"}
            </div>
            <div className={styles.subtitle}>
              Editing for <b>{displayName}</b> only
            </div>
          </div>
          <button className={styles.ghost} onClick={reset} disabled={!changed || busy}>
            Reset to defaults
          </button>
          <button className={styles.close} onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className={styles.body}>
          <nav className={styles.nav}>
            {EDITABLE_GROUPS.map((g) => {
              const edits = editedIn(g);
              return (
                <button
                  key={g}
                  className={`${styles.navRow} ${g === group ? styles.active : ""}`}
                  onClick={() => setGroup(g)}
                >
                  <span>{vocab.assumptionGroup(g)}</span>
                  {edits > 0 && <span className={styles.navDot} aria-label={`${edits} edited`} />}
                  <span className={styles.navCount}>{fieldsByGroup[g].length}</span>
                </button>
              );
            })}
            {/* Confidence, as a percentage and with no explanation — the handoff is
                explicit that this number carries no helper text. */}
            <div className={styles.confidence}>
              <span className="micro-label">Confidence</span>
              <div className={styles.confidenceValue}>{formatConfidence(confidence)}</div>
            </div>
          </nav>

          <div className={styles.panel}>
            <div className={styles.groupTitle}>{vocab.assumptionGroup(group)}</div>
            <div className={styles.fields}>
              {fieldsByGroup[group].map((key) => {
                const kind = labels.assumption_kind[key];
                const { suffix, step } = unitOf(kind);
                const draftKey = `${group}.${key}`;
                const stored = working[group]?.[key];
                const shown =
                  drafts[draftKey] ??
                  String(toDisplay(stored ?? 0, kind));
                const isEdited = pending[group]?.[key] !== undefined;
                const isInvalid = shown !== "" && !Number.isFinite(Number(shown));

                return (
                  <label className={styles.field} key={key}>
                    <span className={styles.fieldLabel}>{vocab.assumption(key)}</span>
                    <span className={styles.inputWrap}>
                      <input
                        className={`${styles.input} ${isEdited ? styles.edited : ""} ${
                          isInvalid ? styles.invalid : ""
                        }`}
                        inputMode="decimal"
                        step={step}
                        value={shown}
                        disabled={busy}
                        onChange={(event) => setField(group, key, event.target.value)}
                      />
                      {suffix && <span className={styles.suffix}>{suffix}</span>}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>
        </div>

        <footer className={styles.foot}>
          <span className={styles.count}>
            <b>{changed}</b> {changed === 1 ? "input" : "inputs"} changed from default
          </span>
          <button className={styles.ghost} onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            className={styles.primary}
            disabled={busy || invalid}
            onClick={() => onApply(pending)}
          >
            {busy ? "Re-underwriting…" : "Re-underwrite parcel"}
          </button>
        </footer>
      </div>
    </div>
  );
}
