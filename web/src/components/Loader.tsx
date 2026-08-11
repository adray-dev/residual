/** The boot animation — the mark subdividing, then the wordmark spelling itself out.
 *
 * Ported from the design-canvas export (`Residual Logo Animation.dc.html` and its
 * `ResidualLoader.jsx`). That export runs inside a preview harness which supplies `animate`,
 * `Easing` and a `useComposition()` clock as globals; none of that ships in a Vite bundle,
 * so the three of them are reproduced here — verbatim, so the motion is the motion that was
 * designed rather than an approximation of it.
 *
 * This is the "Spell Out" variant (4 of the 4 authored), which is the one the export
 * defaults to. The other three live in the source zip if this is ever reconsidered.
 */
import { useEffect, useRef, useState } from "react";

/** px per grid unit — the mark is drawn on a 100-unit grid. */
const S = 2.6;
const BG = "#F3F2EF";
const BASE = "#0E7C7B";
const HOT = "#C4187E";
const INK = "#14201E";

/** The authored composition: Emerge 1.4 + Assemble 1.2 + Residual 0.8 + Hold 0.6. */
const DURATION = 4.0;
const FADE_MS = 400;

type Rect = { id: string; x: number; y: number; w: number; h: number; op: number; hot?: boolean };

const RECTS: Rect[] = [
  { id: "r1", x: 0, y: 0, w: 56, h: 56, op: 1 },
  { id: "r2", x: 62, y: 0, w: 38, h: 56, op: 0.45 },
  { id: "r3", x: 0, y: 62, w: 56, h: 38, op: 0.7 },
  { id: "r4", x: 62, y: 62, w: 16, h: 16, op: 0.3 },
  { id: "r5", x: 62, y: 84, w: 38, h: 16, op: 0.3 },
  { id: "r6", x: 84, y: 62, w: 16, h: 16, op: 1, hot: true },
];

const easeOutQuad = (t: number) => t * (2 - t);
const easeInOutQuad = (t: number) => (t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t);
const easeInOutCubic = (t: number) =>
  t < 0.5 ? 4 * t * t * t : (t - 1) * (2 * t - 2) * (2 * t - 2) + 1;
const easeOutBack = (t: number) => {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
};

type Tween = { from: number; to: number; start: number; end: number; ease?: (t: number) => number };

/** Clamped, eased interpolation over an absolute time window — the harness's `animate`. */
function animate({ from, to, start, end, ease = easeInOutCubic }: Tween) {
  return (t: number) => {
    if (t <= start) return from;
    if (t >= end) return to;
    return from + (to - from) * ease((t - start) / (end - start));
  };
}

/** The cascading split: one lot divides into column, row, then the two small lots. */
function split(r: Rect, T: number) {
  const col = animate({ from: -6 * S, to: 0, start: 0, end: 0.25 })(T);
  const row = animate({ from: -6 * S, to: 0, start: 0.25, end: 0.45 })(T);
  const vert = animate({ from: -6 * S, to: 0, start: 0.45, end: 0.65 })(T);
  const horiz = animate({ from: -6 * S, to: 0, start: 0.65, end: 0.85 })(T);

  let tx = 0;
  let ty = 0;
  if (r.id === "r2" || r.id === "r4" || r.id === "r5" || r.id === "r6") tx += col;
  if (r.id === "r3") ty += row;
  if (r.id === "r4" || r.id === "r5" || r.id === "r6") ty += row;
  if (r.id === "r5") ty += vert;
  if (r.id === "r6") tx += horiz;

  const opacity = animate({ from: 0, to: r.op, start: 0, end: 0.2, ease: easeOutQuad })(T);

  // The residual lot ignites once the block has finished dividing — the payoff parcel.
  let scale = 1;
  let glow = 0;
  if (r.hot) {
    if (T >= 0.95 && T < 1.15) {
      scale = animate({ from: 1, to: 1.3, start: 0.95, end: 1.15, ease: easeOutQuad })(T);
      glow = scale - 1;
    } else if (T >= 1.15 && T < 1.35) {
      scale = animate({ from: 1.3, to: 1, start: 1.15, end: 1.35, ease: easeInOutQuad })(T);
      glow = scale - 1;
    }
  }

  return { transform: `translate(${tx}px, ${ty}px) scale(${scale})`, opacity, glow };
}

const LETTERS = "Residual".split("");
const SPELL_START = 1.4;
const STAGGER = 0.09;
const LETTER_DUR = 0.35;
const TAG_START = SPELL_START + LETTERS.length * STAGGER + LETTER_DUR + 0.15;

export function Loader({ onDone }: { onDone: () => void }) {
  const [T, setT] = useState(0);
  const [leaving, setLeaving] = useState(false);
  const done = useRef(false);

  useEffect(() => {
    const finish = () => {
      if (done.current) return;
      done.current = true;
      setLeaving(true);
      window.setTimeout(onDone, FADE_MS);
    };

    // Anyone who has asked for less motion gets the app, not the show.
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      done.current = true;
      onDone();
      return;
    }

    const started = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const elapsed = (now - started) / 1000;
      setT(elapsed);
      if (elapsed >= DURATION) finish();
      else raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    // requestAnimationFrame does not fire in a background tab, which would otherwise leave
    // the loader on screen indefinitely and the app unreachable. A timer cannot be starved
    // the same way, so it guarantees the animation ends even if it never got to play.
    const guard = window.setTimeout(finish, DURATION * 1000 + 250);

    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(guard);
    };
  }, [onDone]);

  const tagOpacity = animate({ from: 0, to: 1, start: TAG_START, end: TAG_START + 0.4, ease: easeOutQuad })(T);
  const tagShift = animate({ from: 8, to: 0, start: TAG_START, end: TAG_START + 0.4, ease: easeOutQuad })(T);

  return (
    <div
      aria-hidden
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: BG,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        opacity: leaving ? 0 : 1,
        transition: `opacity ${FADE_MS}ms ease-out`,
        pointerEvents: leaving ? "none" : "auto",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
        <div style={{ position: "relative", width: 100 * S, height: 100 * S }}>
          {RECTS.map((r) => {
            const { transform, opacity, glow } = split(r, T);
            return (
              <div
                key={r.id}
                style={{
                  position: "absolute",
                  left: r.x * S,
                  top: r.y * S,
                  width: r.w * S,
                  height: r.h * S,
                  background: r.hot ? HOT : BASE,
                  opacity,
                  transform,
                  transformOrigin: "center center",
                  filter: r.hot && glow > 0 ? `drop-shadow(0 0 ${18 * glow}px ${HOT})` : "none",
                }}
              />
            );
          })}
        </div>

        <div
          style={{
            marginTop: 28,
            display: "flex",
            fontFamily: '"Public Sans", Helvetica, Arial, sans-serif',
            fontWeight: 600,
            fontSize: 44,
            letterSpacing: "-0.025em",
            color: INK,
          }}
        >
          {LETTERS.map((ch, i) => {
            const start = SPELL_START + i * STAGGER;
            const end = start + LETTER_DUR;
            const opacity = animate({ from: 0, to: 1, start, end, ease: easeOutBack })(T);
            const shift = animate({ from: 14, to: 0, start, end, ease: easeOutBack })(T);
            return (
              <span key={i} style={{ opacity, transform: `translateY(${shift}px)`, display: "inline-block" }}>
                {ch}
              </span>
            );
          })}
        </div>

        <div
          style={{
            marginTop: 10,
            fontFamily: '"Public Sans", Helvetica, Arial, sans-serif',
            fontWeight: 500,
            fontSize: 19,
            letterSpacing: "0.01em",
            color: INK,
            opacity: tagOpacity,
            transform: `translateY(${tagShift}px)`,
          }}
        >
          Building on every block
        </div>
      </div>
    </div>
  );
}
