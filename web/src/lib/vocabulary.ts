/** Plain-language labels, read from the server rather than duplicated here.
 *
 * `api/vocabulary.py` is the one place the mapping lives and /meta ships the whole block
 * (`serializers.labels_block`), so this module is a typed reader over what arrives, not a
 * second copy. A copy would drift, and the failure mode of drift is the UI confidently
 * calling a number something the engine does not mean by it.
 *
 * The fallback in every lookup is the raw key. That is deliberate: a missing label shows
 * up as an obviously-wrong `yield_on_cost` in the interface, which gets noticed and fixed,
 * whereas a blank or a guessed English phrase does not.
 */
import type { Labels } from "./types";

export type LabelKind = keyof Labels;

/** Bound to one /meta payload and passed down, so no component reaches for a global. */
export class Vocabulary {
  constructor(private readonly labels: Labels) {}

  private lookup(kind: LabelKind, key: string | null | undefined): string {
    if (!key) return "";
    return this.labels[kind]?.[key] ?? key;
  }

  /** "Annual return" for `irr`. */
  metric(key: string): string {
    return this.lookup("metric", key);
  }

  /** "Garden walk-up" for `garden`. */
  prototype(key: string | null | undefined): string {
    return this.lookup("prototype", key);
  }

  /** "Wood frame" for `wood_v`. */
  construction(key: string | null | undefined): string {
    return this.lookup("construction", key);
  }

  /** "Limited by height" for `height`. Status rows already carry a sentence — passed through. */
  bindingConstraint(key: string | null | undefined): string {
    return this.lookup("binding_constraint", key);
  }

  /** "Floor area" — the bare noun, for a row already headed "Limited by". Without it the
   * popup read "Limited by / Limited by floor area". */
  bindingConstraintShort(key: string | null | undefined): string {
    if (!key) return "";
    return this.labels.binding_constraint_short?.[key] ?? this.bindingConstraint(key);
  }

  /** "Infeasible under zoning" for `infeasible`. */
  status(key: string | null | undefined): string {
    return this.lookup("status", key);
  }

  /** "Full underwriting" / "Screening estimate" — the two-tier split, always labeled. */
  tier(key: string): string {
    return this.lookup("tier", key);
  }

  /** "Exit & return" for `exit` — the 1c modal's group headings. */
  assumptionGroup(key: string): string {
    return this.lookup("assumption_group", key);
  }

  /** "Soft cost % of hard" for `soft_cost_pct`. */
  assumption(key: string): string {
    return this.lookup("assumption", key);
  }

  /** The unit an input is expressed in — percent / money / months / years / rate / number.
   * Declared by the server because it is a fact about the value, not a styling choice. */
  assumptionKind(key: string): string {
    return this.labels.assumption_kind?.[key] ?? "number";
  }
}

/** The one label the UI must never render, guarded so it cannot be reintroduced by hand.
 *
 * The handoff's rule is absolute: "SSL" never appears in user-facing text; it is always
 * "Parcel ID". The tiles already ship the identifier as `id` for the same reason. This is
 * the copy for anywhere the identifier is shown to a person.
 */
export const PARCEL_ID_LABEL = "Parcel ID";
