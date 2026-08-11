type Tone = "color" | "ondark" | "onlight" | "mono";

const TONES: Record<Tone, { base: string; hot: string }> = {
  // `color` and `ondark` inherit the product's accent token so the mark never
  // drifts from the UI teal; `mono` collapses to currentColor for one-ink contexts.
  color: { base: "var(--accent, #0e7c7b)", hot: "var(--brand-magenta, #c4187e)" },
  ondark: { base: "#f3f2ef", hot: "var(--brand-magenta, #c4187e)" },
  onlight: { base: "var(--ink, #1a1d1c)", hot: "var(--brand-magenta, #c4187e)" },
  mono: { base: "currentColor", hot: "currentColor" },
};

/**
 * Residual mark — a block subdividing from one large lot down to the smallest,
 * with the residual lot called out in magenta. Six rects, no strokes: it holds
 * at 16px, which is why nothing here is thinner than 16 units of the 100 grid.
 */
export function ResidualMark({
  size = 24,
  tone = "color",
  title,
}: {
  size?: number;
  tone?: Tone;
  title?: string;
}) {
  const { base, hot } = TONES[tone];
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      shapeRendering="crispEdges"
    >
      <rect x="0" y="0" width="56" height="56" fill={base} />
      <rect x="62" y="0" width="38" height="56" fill={base} opacity=".45" />
      <rect x="0" y="62" width="56" height="38" fill={base} opacity=".7" />
      <rect x="62" y="62" width="16" height="16" fill={base} opacity=".3" />
      <rect x="62" y="84" width="38" height="16" fill={base} opacity=".3" />
      <rect x="84" y="62" width="16" height="16" fill={hot} />
    </svg>
  );
}
