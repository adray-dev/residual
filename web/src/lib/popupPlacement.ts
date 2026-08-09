/** Where the 1a popup goes, given where the parcel is and how big everything turned out.
 *
 * Pure and separate from the component so the edge cases — a parcel at the very top of the
 * map, hard against the right edge, or a card taller than the space it has — can be checked
 * directly instead of by clicking around and hoping.
 */
export interface Point {
  x: number;
  y: number;
}

export interface Size {
  width: number;
  height: number;
}

/** Distance from the parcel to the card, and the minimum margin against the map edges. */
export const POPUP_GAP = 12;
export const POPUP_EDGE = 12;

export function placePopup(at: Point, card: Size, bounds: Size): Point {
  // Centre on the parcel, then pull whichever edge falls outside back in. The second
  // `Math.max` matters when the card is wider than the container: without it the clamp
  // range inverts and the card is pushed off the LEFT instead.
  const left = Math.min(
    Math.max(at.x - card.width / 2, POPUP_EDGE),
    Math.max(POPUP_EDGE, bounds.width - card.width - POPUP_EDGE),
  );

  // Above the parcel by preference, so the card does not cover what was just clicked.
  let top = at.y - card.height - POPUP_GAP;
  if (top < POPUP_EDGE) {
    // No room above: drop below if it fits there, otherwise sit against the bottom edge.
    const below = at.y + POPUP_GAP;
    top =
      below + card.height + POPUP_EDGE <= bounds.height
        ? below
        : bounds.height - card.height - POPUP_EDGE;
  }
  // Final guard on the top edge. The "below" branch can still land above the container
  // when the anchor itself is off-screen, and a card taller than the container has no
  // position that satisfies both edges — pinning the top is the right degradation, because
  // the address and the headline value live there.
  top = Math.max(top, POPUP_EDGE);

  return { x: left, y: top };
}
