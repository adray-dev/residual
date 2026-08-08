/** The 1b Program card: what actually gets built, and the demolition toggle.
 *
 * Every figure here is reporting-only. In particular `unit_count` is labelled "Units
 * (est.)" because SPEC is explicit that revenue is `net_rentable_sf × rent_psf` and unit
 * count is never wired into it — the estimate is there to make the program legible, not
 * because the model priced it.
 *
 * The demolition toggle is the one control on this card that changes the numbers. It is
 * off by default and is never applied in the bake, so flipping it re-runs the full model
 * and every figure in the panel moves with it.
 */
import type { ProgramOut } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { count, rate } from "../lib/format";
import styles from "./ProgramCard.module.css";

export interface ProgramCardProps {
  program: ProgramOut;
  vocab: Vocabulary;
  /** Existing structure on the parcel, in SF. Zero means nothing to demolish. */
  existingBuildingSf: number;
  demolition: boolean;
  busy: boolean;
  onDemolitionChange: (next: boolean) => void;
  onTryAnotherPrototype?: () => void;
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.cell}>
      <span className="micro-label">{label}</span>
      <span className={styles.value} title={value}>
        {value}
      </span>
    </div>
  );
}

export function ProgramCard({
  program,
  vocab,
  existingBuildingSf,
  demolition,
  busy,
  onDemolitionChange,
  onTryAnotherPrototype,
}: ProgramCardProps) {
  const nothingToDemolish = existingBuildingSf <= 0;

  return (
    <div className={styles.card}>
      <div className={styles.head}>
        <span className={styles.title}>
          Program — {vocab.prototype(program.prototype_id).toLowerCase()},{" "}
          {program.floors} {program.floors === 1 ? "floor" : "floors"}
        </span>
        {onTryAnotherPrototype && (
          <button className={styles.link} onClick={onTryAnotherPrototype}>
            Try another prototype
          </button>
        )}
      </div>

      <div className={styles.grid}>
        <Cell label={vocab.metric("gross_sf")} value={count(program.gross_sf)} />
        <Cell label={vocab.metric("net_rentable_sf")} value={count(program.net_rentable_sf)} />
        <Cell label="Units (est.)" value={count(program.unit_count)} />
        <Cell label="Floors" value={String(program.floors)} />
        {/* Pre-phrased server-side: "256 stalls, surface", never "256 podium". */}
        <Cell label="Parking" value={program.parking_phrase} />
        <Cell
          label="Average unit size"
          value={program.avg_unit_sf ? `${count(program.avg_unit_sf)} SF` : "—"}
        />
        <Cell label="Build type" value={vocab.construction(program.construction_type)} />
        <Cell label="Rent" value={`${rate(program.rent_psf_monthly)}/SF/mo`} />
      </div>

      <div className={styles.toggleRow}>
        <div className={styles.toggleText}>
          <div className={styles.toggleLabel}>Include demolition</div>
          <div className={styles.toggleHint}>
            {nothingToDemolish
              ? "Nothing standing on this parcel to demolish."
              : `${count(existingBuildingSf)} SF standing. Adds demolition cost and re-runs the model.`}
          </div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={demolition}
          aria-label="Include demolition"
          disabled={busy || nothingToDemolish}
          className={`${styles.switch} ${demolition ? styles.on : ""}`}
          onClick={() => onDemolitionChange(!demolition)}
        >
          <span className={styles.knob} />
        </button>
      </div>
    </div>
  );
}
