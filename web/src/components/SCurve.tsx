/** Cost draw S-curve: cumulative development cost against cumulative equity drawn.
 *
 * One axis, deliberately. Both series are dollars, so they share a scale and the gap
 * between them is readable as a real quantity — the debt carrying the difference. Two
 * y-scales would let that gap mean nothing.
 *
 * The series are distinguished by dash pattern as well as hue (solid cost, dashed equity),
 * which is what keeps the chart legible in greyscale and for color-vision deficiency.
 * That matters more than usual here: the brand teal is deliberately desaturated, so it
 * fails a chroma floor as a chart color. It is kept because it is *the* accent across the
 * product and re-hueing it for one chart would be worse — the dash carries identity, and
 * the pair still separates at ΔE 14 under protanopia against the 8 target.
 *
 * Phase bands come from the engine's own `phase_bounds`, not from re-deriving month counts
 * off the assumptions — the cash flow already knows where predevelopment ends.
 */
import { useState } from "react";
import type { CashFlowOut } from "../lib/types";
import { money } from "../lib/format";
import styles from "./SCurve.module.css";

const COST = "#0e7c7b";
const EQUITY = "#c08a3e";

// A wide, short plot. `preserveAspectRatio="none"` lets it stretch to the panel width;
// `vector-effect: non-scaling-stroke` stops that stretch from distorting the line weights.
const W = 240;
const H = 96;

// Headroom, in viewBox units. The peak of the cost curve IS the maximum, so without this
// it lands on y=0 and the top half of a 2.2px stroke is clipped by the plot edge.
const PAD_TOP = 5;

function y(value: number, max: number): number {
  return H - (value / max) * (H - PAD_TOP);
}

function path(series: number[], max: number): string {
  if (series.length < 2 || max <= 0) return "";
  const step = W / (series.length - 1);
  return series
    .map((value, index) => `${index === 0 ? "M" : "L"}${(index * step).toFixed(2)},${y(value, max).toFixed(2)}`)
    .join(" ");
}

export function SCurve({ cashflow }: { cashflow: CashFlowOut }) {
  const [hover, setHover] = useState<{ index: number; left: number } | null>(null);

  const cost = cashflow.cumulative_cost;
  const equity = cashflow.cumulative_equity;
  const max = Math.max(...cost, ...equity, 1);
  const months = Math.max(cost.length - 1, 1);

  const predevEnd = cashflow.phase_bounds["predev_end"] ?? 0;
  const constructionEnd = cashflow.phase_bounds["construction_end"] ?? predevEnd;

  const band = (from: number, to: number) => ({
    x: (from / months) * W,
    width: (Math.max(to, from) - from) / months * W,
  });

  return (
    <div className={styles.wrap}>
      <svg
        className={styles.plot}
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Cumulative cost reaches ${money(cost[cost.length - 1])} over ${months} months`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(event) => {
          const box = event.currentTarget.getBoundingClientRect();
          const ratio = (event.clientX - box.left) / box.width;
          const index = Math.min(cost.length - 1, Math.max(0, Math.round(ratio * months)));
          setHover({ index, left: (index / months) * box.width });
        }}
      >
        {/* Phase bands: predevelopment neutral, construction tinted with the accent. */}
        <rect {...band(0, predevEnd)} y={0} height={H} fill="rgba(0,0,0,.035)" />
        <rect
          {...band(predevEnd, constructionEnd)}
          y={0}
          height={H}
          fill="rgba(14,124,123,.07)"
        />
        <line x1={0} y1={H} x2={W} y2={H} stroke="rgba(0,0,0,.12)" strokeWidth={1}
              vectorEffect="non-scaling-stroke" />

        <path
          d={path(cost, max)}
          fill="none"
          stroke={COST}
          strokeWidth={2.2}
          vectorEffect="non-scaling-stroke"
        />
        <path
          d={path(equity, max)}
          fill="none"
          stroke={EQUITY}
          strokeWidth={1.8}
          strokeDasharray="4 3"
          vectorEffect="non-scaling-stroke"
        />

        {hover && (
          <g>
            <circle
              cx={(hover.index / months) * W}
              cy={y(cost[hover.index] ?? 0, max)}
              r={3}
              fill={COST}
              stroke="#fff"
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
            />
            <circle
              cx={(hover.index / months) * W}
              cy={y(equity[hover.index] ?? 0, max)}
              r={3}
              fill={EQUITY}
              stroke="#fff"
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
            />
          </g>
        )}
      </svg>

      {hover && (
        <>
          <div className={styles.crosshair} style={{ left: hover.left }} />
          <div className={styles.tooltip} style={{ left: hover.left, top: -6 }}>
            <div className={styles.tipMonth}>Month {hover.index}</div>
            <div className={styles.tipRow}>
              <span className={styles.dot} style={{ background: COST }} />
              {money(cost[hover.index])} cost
            </div>
            <div className={styles.tipRow}>
              <span className={styles.dot} style={{ background: EQUITY }} />
              {money(equity[hover.index])} equity
            </div>
          </div>
        </>
      )}

      <div className={styles.legend}>
        <span className={styles.key}>
          <span className={styles.swatch} style={{ borderTop: `2px solid ${COST}` }} />
          Cost drawn
        </span>
        <span className={styles.key}>
          <span className={styles.swatch} style={{ borderTop: `2px dashed ${EQUITY}` }} />
          Equity drawn
        </span>
        <span className={styles.key}>{months} months to sale</span>
      </div>
    </div>
  );
}
