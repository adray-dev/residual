/** The 1b Program card: what actually gets built.
 *
 * Every figure here is reporting-only. `unit_count` in particular never enters revenue —
 * SPEC is explicit that revenue is `net_rentable_sf × rent_psf` — so the count is here to
 * make the program legible, not because the model priced it.
 *
 * Demolition used to live here as a toggle. It moved into the existing-building flag,
 * because a standing building is the reason the question exists at all, and the warning
 * and the control belong in one place rather than two.
 */
import type { ProgramOut } from "../lib/types";
import type { Vocabulary } from "../lib/vocabulary";
import { count, rate } from "../lib/format";
import styles from "./ProgramCard.module.css";

export interface ProgramCardProps {
  program: ProgramOut;
  vocab: Vocabulary;
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

export function ProgramCard({ program, vocab, onTryAnotherPrototype }: ProgramCardProps) {
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
        <Cell label="Units" value={count(program.unit_count)} />
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
    </div>
  );
}
