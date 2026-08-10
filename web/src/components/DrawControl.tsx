/** The draw-an-area control: the button that starts it, and the coaching while it runs.
 *
 * Every other filter is a control whose state you can read off its own face. A drawn area
 * is a gesture, so the affordances that would be implicit elsewhere — how to finish, how to
 * undo a corner, how to back out — have to be said out loud while the gesture is in
 * progress. That is what the strip is for, and why it disappears the moment there is a
 * committed area to speak for itself.
 */
import { MIN_VERTICES } from "../lib/drawRing";
import styles from "./DrawControl.module.css";

export function DrawControl({
  drawing,
  corners,
  hasArea,
  matched,
  onStart,
  onCancel,
  onClear,
}: {
  drawing: boolean;
  /** Corners placed so far in the current gesture. */
  corners: number;
  hasArea: boolean;
  /** Parcels inside the committed area, once the count comes back. */
  matched: number | null;
  onStart: () => void;
  onCancel: () => void;
  onClear: () => void;
}) {
  if (drawing) {
    return (
      <div className={styles.strip} role="status">
        <span className={styles.dot} />
        <span className={styles.said}>
          {corners === 0
            ? "Click the map to place the first corner."
            : corners < MIN_VERTICES
              ? `${corners} of ${MIN_VERTICES} corners.`
              : "Click the first corner, or press Enter, to close the area."}
        </span>
        <span className={styles.keys}>
          <kbd>Backspace</kbd> undo · <kbd>Esc</kbd> cancel
        </span>
        <button className={styles.cancel} onClick={onCancel}>
          Cancel
        </button>
      </div>
    );
  }

  if (hasArea) {
    return (
      <div className={styles.strip}>
        <span className={styles.said}>
          {/* The count is the server's, over real parcel geometry — the outline on screen
              is only where the user drew, not a claim about what is inside it. */}
          {matched == null
            ? "Counting parcels in this area…"
            : `${matched.toLocaleString()} priced ${matched === 1 ? "parcel" : "parcels"} in this area`}
        </span>
        <button className={styles.redraw} onClick={onStart}>
          Redraw
        </button>
        <button className={styles.cancel} onClick={onClear}>
          Clear
        </button>
      </div>
    );
  }

  return (
    <button className={styles.start} onClick={onStart}>
      <svg width="13" height="13" viewBox="0 0 13 13" aria-hidden="true">
        <path
          d="M2 9.5 L4.5 2.5 L11 5 L8 11 Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.3"
          strokeLinejoin="round"
          strokeDasharray="2.5 1.8"
        />
      </svg>
      Draw area
    </button>
  );
}
