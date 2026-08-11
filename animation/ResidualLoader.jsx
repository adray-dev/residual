const S = 2.6; // px per grid unit (mark drawn on a 100-unit grid)
const BG = '#F3F2EF';
const BASE = '#0E7C7B';
const HOT = '#C4187E';
const INK = '#14201E';

const RECTS = [
  { id: 'r1', x: 0, y: 0, w: 56, h: 56, op: 1 },
  { id: 'r2', x: 62, y: 0, w: 38, h: 56, op: 0.45 },
  { id: 'r3', x: 0, y: 62, w: 56, h: 38, op: 0.7 },
  { id: 'r4', x: 62, y: 62, w: 16, h: 16, op: 0.3 },
  { id: 'r5', x: 62, y: 84, w: 38, h: 16, op: 0.3 },
  { id: 'r6', x: 84, y: 62, w: 16, h: 16, op: 1, hot: true },
];

const ENTER_WINDOWS = {
  r1: [0.0, 0.55], r3: [0.15, 0.7], r2: [0.3, 0.85],
  r4: [0.55, 1.0], r5: [0.7, 1.15], r6: [0.9, 1.4],
};

function box(r) {
  return { left: r.x * S, top: r.y * S, width: r.w * S, height: r.h * S };
}

// Variant 1: Drop & Settle — lots fall from above and bounce into place.
function v1(r, T, CUES) {
  const { Easing, animate } = window;
  const [ws, we] = ENTER_WINDOWS[r.id];
  const ty = animate({ from: -220, to: 0, start: ws, end: we, ease: Easing.easeOutBack })(T);
  const op = animate({ from: 0, to: r.op, start: ws, end: ws + (we - ws) * 0.6, ease: Easing.easeOutQuad })(T);
  let scale = 1;
  const midA = CUES.Assemble + 0.25, endA = CUES.Assemble + 0.5;
  if (T >= CUES.Assemble && T < midA) scale = animate({ from: 1, to: 1.03, start: CUES.Assemble, end: midA, ease: Easing.easeOutQuad })(T);
  else if (T >= midA && T < endA) scale = animate({ from: 1.03, to: 1, start: midA, end: endA, ease: Easing.easeInQuad })(T);
  let hotScale = 1, glow = 0;
  if (r.hot) {
    const mid = CUES.Residual + 0.25, end = CUES.Residual + 0.5;
    if (T >= CUES.Residual && T < mid) { hotScale = animate({ from: 1, to: 1.4, start: CUES.Residual, end: mid, ease: Easing.easeOutQuad })(T); glow = hotScale - 1; }
    else if (T >= mid && T < end) { hotScale = animate({ from: 1.4, to: 1, start: mid, end: end, ease: Easing.easeInOutQuad })(T); glow = hotScale - 1; }
  }
  return { transform: `translateY(${ty}px) scale(${scale * hotScale})`, opacity: op, glow };
}

// Variant 2: Subdivide — one solid parcel dissolves into its six lots.
function v2(r, T, CUES) {
  const { Easing, animate } = window;
  const [ws0, we0] = ENTER_WINDOWS[r.id];
  const ws = ws0 + 0.5, we = we0 + 0.5;
  const scale = animate({ from: 0.8, to: 1, start: ws, end: we, ease: Easing.easeOutQuad })(T);
  const op = animate({ from: 0, to: r.op, start: ws, end: we, ease: Easing.easeOutQuad })(T);
  let hotScale = 1, glow = 0;
  if (r.hot) {
    if (T >= 2.6 && T < 2.8) { hotScale = animate({ from: 1, to: 0.5, start: 2.6, end: 2.8, ease: Easing.easeInOutQuad })(T); }
    else if (T >= 2.8 && T < 3.0) { hotScale = animate({ from: 0.5, to: 1.2, start: 2.8, end: 3.0, ease: Easing.easeOutQuad })(T); glow = 0.3; }
    else if (T >= 3.0 && T < 3.3) { hotScale = animate({ from: 1.2, to: 1, start: 3.0, end: 3.3, ease: Easing.easeInOutQuad })(T); glow = animate({ from: 0.3, to: 0, start: 3.0, end: 3.3 })(T); }
  }
  return { transform: `scale(${scale * hotScale})`, opacity: op, glow };
}

// Shared cascading-split math for the "Parcel Split" family (variants 3 & 4).
// windows: [colSplit, rowSplit, vertSmall, horizSmall] each [start,end]; pop: [start,mid,end]
function parcelSplit(r, T, windows, pop) {
  const { Easing, animate } = window;
  const [colW, rowW, vertW, horizW] = windows;
  const colSplit = animate({ from: -6 * S, to: 0, start: colW[0], end: colW[1], ease: Easing.easeInOutCubic });
  const rowSplit = animate({ from: -6 * S, to: 0, start: rowW[0], end: rowW[1], ease: Easing.easeInOutCubic });
  const vertSplitSmall = animate({ from: -6 * S, to: 0, start: vertW[0], end: vertW[1], ease: Easing.easeInOutCubic });
  const horizSplitSmall = animate({ from: -6 * S, to: 0, start: horizW[0], end: horizW[1], ease: Easing.easeInOutCubic });
  let tx = 0, ty = 0;
  if (r.id === 'r2' || r.id === 'r4' || r.id === 'r5' || r.id === 'r6') tx += colSplit(T);
  if (r.id === 'r3') ty += rowSplit(T);
  if (r.id === 'r4' || r.id === 'r5' || r.id === 'r6') ty += rowSplit(T);
  if (r.id === 'r5') ty += vertSplitSmall(T);
  if (r.id === 'r6') tx += horizSplitSmall(T);
  const op = animate({ from: 0, to: r.op, start: 0, end: 0.2, ease: Easing.easeOutQuad })(T);
  let hotScale = 1, glow = 0;
  const [ps, pm, pe] = pop;
  if (r.hot) {
    if (T >= ps && T < pm) { hotScale = animate({ from: 1, to: 1.3, start: ps, end: pm, ease: Easing.easeOutQuad })(T); glow = hotScale - 1; }
    else if (T >= pm && T < pe) { hotScale = animate({ from: 1.3, to: 1, start: pm, end: pe, ease: Easing.easeInOutQuad })(T); glow = hotScale - 1; }
  }
  return { transform: `translate(${tx}px, ${ty}px) scale(${hotScale})`, opacity: op, glow };
}

// Variant 3: Parcel Split — one lot cascades into its smallest lots.
function v3(r, T) {
  return parcelSplit(r, T, [[0, 0.5], [0.5, 0.9], [0.9, 1.3], [1.3, 1.7]], [1.8, 2.05, 2.3]);
}

// Variant 4: Spell Out — the block breaks up fast, then the wordmark spells itself.
function v4(r, T) {
  return parcelSplit(r, T, [[0, 0.25], [0.25, 0.45], [0.45, 0.65], [0.65, 0.85]], [0.95, 1.15, 1.35]);
}

const VARIANTS = { '1': v1, '2': v2, '3': v3, '4': v4 };

function ResidualLoader(props) {
  const { useComposition, Easing, animate } = window;
  const variant = String(props.variant || '1');
  const showTagline = props.showTagline !== false;
  const { T, CUES } = useComposition();
  const fn = VARIANTS[variant] || v1;

  const wordOp = animate({ from: 0, to: 1, start: CUES.Hold, end: CUES.Hold + 0.4, ease: Easing.easeOutQuad })(T);
  const wordTy = animate({ from: 10, to: 0, start: CUES.Hold, end: CUES.Hold + 0.4, ease: Easing.easeOutQuad })(T);
  const overlayOp = animate({ from: 1, to: 0, start: 0.9, end: 1.3, ease: Easing.easeInOutQuad })(T);

  const letters = 'Residual'.split('');
  const spellStart = 1.4, stagger = 0.09, dur = 0.35;
  const tagStart = spellStart + letters.length * stagger + dur + 0.15;
  const tagOp = animate({ from: 0, to: 1, start: tagStart, end: tagStart + 0.4, ease: Easing.easeOutQuad })(T);
  const tagTy = animate({ from: 8, to: 0, start: tagStart, end: tagStart + 0.4, ease: Easing.easeOutQuad })(T);

  return (
    <div style={{ position: 'absolute', inset: 0, background: BG, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <div style={{ position: 'relative', width: 100 * S, height: 100 * S }}>
          {variant === '2' && (
            <div style={{
              position: 'absolute', left: 0, top: 0, width: 100 * S, height: 100 * S,
              background: BASE, opacity: overlayOp,
            }} />
          )}
          {RECTS.map((r) => {
            const { transform, opacity, glow } = fn(r, T, CUES);
            const b = box(r);
            return (
              <div key={r.id} style={{
                position: 'absolute', left: b.left, top: b.top, width: b.width, height: b.height,
                background: r.hot ? HOT : BASE,
                opacity,
                transform,
                transformOrigin: 'center center',
                filter: r.hot && glow > 0 ? `drop-shadow(0 0 ${18 * glow}px ${HOT})` : 'none',
              }} />
            );
          })}
        </div>
        {variant === '4' ? (
          <div style={{ marginTop: 28, display: 'flex', fontFamily: '"Public Sans", Helvetica, Arial, sans-serif', fontWeight: 600, fontSize: 44, letterSpacing: '-0.025em', color: INK }}>
            {letters.map((ch, i) => {
              const s = spellStart + i * stagger, e = s + dur;
              const op = animate({ from: 0, to: 1, start: s, end: e, ease: Easing.easeOutBack })(T);
              const ty = animate({ from: 14, to: 0, start: s, end: e, ease: Easing.easeOutBack })(T);
              return <span key={i} style={{ opacity: op, transform: `translateY(${ty}px)`, display: 'inline-block' }}>{ch}</span>;
            })}
          </div>
        ) : (
          <div style={{
            marginTop: 28, fontFamily: '"Public Sans", Helvetica, Arial, sans-serif', fontWeight: 600,
            fontSize: 44, letterSpacing: '-0.025em', color: INK,
            opacity: wordOp, transform: `translateY(${wordTy}px)`,
          }}>Residual</div>
        )}
        {showTagline && (
          <div style={{
            marginTop: 10, fontFamily: '"Public Sans", Helvetica, Arial, sans-serif', fontWeight: 500,
            fontSize: 19, letterSpacing: '0.01em', color: INK,
            opacity: variant === '4' ? tagOp : wordOp, transform: `translateY(${(variant === '4' ? tagTy : wordTy)}px)`,
          }}>Feasibility on every block</div>
        )}
      </div>
    </div>
  );
}

window.ResidualLoader = ResidualLoader;
