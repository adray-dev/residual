/**
 * Geometry check for the 1a popup.
 *
 * The popup only appears on a map click, so it cannot be exercised in a headless tab —
 * WebGL does not run there and the map never paints. The placement is pure arithmetic
 * though, so it is checked directly here instead of by clicking around and hoping.
 *
 * Run: npm run check:popup
 */
import { placePopup, POPUP_GAP, POPUP_EDGE } from "../src/lib/popupPlacement.ts";

// The map area at a 1440px window, rail closed and rail open.
const WIDE = { width: 1054, height: 706 };
const NARROW = { width: 434, height: 706 };
const CARD = { width: 300, height: 420 };
// The CSS caps the card at `calc(100% - 24px)`, so this is the tallest it can ever be.
const TALL = { width: 300, height: WIDE.height - 24 };

let failures = 0;

function check(name, at, card, bounds, { allowBottomOverflow = false } = {}) {
  const p = placePopup(at, card, bounds);
  const fits = {
    left: p.x >= POPUP_EDGE - 0.001,
    right: p.x + card.width <= bounds.width - POPUP_EDGE + 0.001,
    top: p.y >= POPUP_EDGE - 0.001,
    bottom: allowBottomOverflow || p.y + card.height <= bounds.height - POPUP_EDGE + 0.001,
  };
  const ok = Object.values(fits).every(Boolean);
  if (!ok) failures++;
  const failed = Object.entries(fits).filter(([, v]) => !v).map(([k]) => k);
  console.log(
    `${ok ? "ok  " : "FAIL"} ${name.padEnd(44)} (${Math.round(p.x)}, ${Math.round(p.y)})` +
      (ok ? "" : `   off: ${failed.join(", ")}`),
  );
}

console.log("corners and edges — every one of these used to escape the map");
check("top-left parcel", { x: 4, y: 6 }, CARD, WIDE);
check("top-centre parcel, no room above", { x: 520, y: 20 }, CARD, WIDE);
check("top-right parcel", { x: 1050, y: 8 }, CARD, WIDE);
check("right edge, mid height", { x: 1052, y: 400 }, CARD, WIDE);
check("bottom-right parcel", { x: 1050, y: 700 }, CARD, WIDE);
check("bottom-left parcel", { x: 2, y: 704 }, CARD, WIDE);
check("parcel outside the container entirely", { x: 2000, y: -50 }, CARD, WIDE);

console.log("\nrail open — the container loses 620px");
check("right edge of the narrowed map", { x: 430, y: 300 }, CARD, NARROW);
check("top of the narrowed map", { x: 200, y: 10 }, CARD, NARROW);
// CSS caps the card at `min(300px, 100% - 24px)`, so this cannot happen in the DOM. The
// function still has to degrade sanely if it ever does: pin the left edge, where the
// address is, rather than centring on an anchor and hanging off both sides.
{
  const narrow = { width: 260, height: 706 };
  const p = placePopup({ x: 100, y: 300 }, CARD, narrow);
  const pinned = p.x === POPUP_EDGE;
  console.log(`${pinned ? "ok  " : "FAIL"} over-wide card pins to the left edge`);
  if (!pinned) failures++;
}

console.log("\ntallest the CSS allows");
check("tall card, parcel near top", { x: 500, y: 30 }, TALL, WIDE);
check("tall card, parcel near bottom", { x: 500, y: 690 }, TALL, WIDE);

console.log("\nthe ordinary case is unchanged");
const normal = placePopup({ x: 500, y: 500 }, CARD, WIDE);
const above = normal.y + CARD.height === 500 - POPUP_GAP;
const centred = Math.abs(normal.x + CARD.width / 2 - 500) < 0.001;
console.log(`${above ? "ok  " : "FAIL"} sits above the parcel`);
console.log(`${centred ? "ok  " : "FAIL"} centred on the parcel`);
if (!above || !centred) failures++;

console.log(`\n${failures === 0 ? "ALL PASS" : `${failures} FAILED`}`);
process.exit(failures ? 1 : 0);
