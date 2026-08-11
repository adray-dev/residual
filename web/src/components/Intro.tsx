/** The opening note, shown once the logo animation has played out.
 *
 * Any click or key dismisses it — there is no close button and no dismiss affordance to
 * find, because the whole surface is the affordance. It covers the map rather than sitting
 * beside it, so the first thing a reader does with the app is get rid of this, which is
 * the intended cost: one gesture, any gesture.
 */
import { useEffect, useRef, useState } from "react";
import { useVisualViewport } from "../lib/visualViewport";
import styles from "./Intro.module.css";

const FADE_MS = 180;

/** Below this the panel is wider than the window, so it drops to the compact scale. */
const COMPACT_BELOW = 560;

export function Intro({ onDismiss }: { onDismiss: () => void }) {
  const [leaving, setLeaving] = useState(false);
  const done = useRef(false);
  // Pinned to what the user can see, not to the 1440 layout — see lib/visualViewport.
  const view = useVisualViewport();
  const compact = view.width < COMPACT_BELOW;

  useEffect(() => {
    const dismiss = () => {
      if (done.current) return;
      done.current = true;
      setLeaving(true);
      window.setTimeout(onDismiss, FADE_MS);
    };

    // Capture phase, so this wins even if something beneath would have swallowed the
    // event. `pointerdown` rather than `click` so it goes on the press, and so a touch
    // counts; `keydown` covers every key without enumerating any.
    window.addEventListener("pointerdown", dismiss, { capture: true });
    window.addEventListener("keydown", dismiss, { capture: true });
    window.addEventListener("wheel", dismiss, { capture: true, passive: true });

    return () => {
      window.removeEventListener("pointerdown", dismiss, { capture: true });
      window.removeEventListener("keydown", dismiss, { capture: true });
      window.removeEventListener("wheel", dismiss, { capture: true });
    };
  }, [onDismiss]);

  return (
    <div
      className={styles.scrim}
      data-leaving={leaving || undefined}
      style={{
        left: view.left,
        top: view.top,
        width: view.width,
        height: view.height,
        padding: compact ? 16 : 20,
      }}
      role="dialog"
      aria-modal="true"
      aria-label="About Residual"
    >
      <div className={`${styles.card} ${compact ? styles.compact : ""}`}>
        <h2 className={styles.lead}>Find out what pencils.</h2>
        <p className={styles.body}>
          Residual evaluates every parcel within a given geography to identify its most
          financially feasible use, surfacing prime development opportunities across an
          entire city.
        </p>
        <p className={styles.body}>
          Search any address to assess its potential, and adjust the financial inputs to
          reflect your own assumptions. Compare parcels side by side, and export a pro forma
          once you’ve identified an opportunity worth pursuing.
        </p>
        <p className={styles.hint}>Click anywhere to continue</p>
      </div>
    </div>
  );
}
