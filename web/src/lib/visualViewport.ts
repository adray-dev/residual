/** The rectangle the user can actually see, in layout-viewport pixels.
 *
 * `index.html` pins the layout viewport to 1440 so the desktop composition survives intact
 * on a phone. The cost is that every length CSS can reach — `100vw`, `inset: 0`, a percentage
 * of the body — describes that 1440, not the ~390 the screen is showing. A `position: fixed`
 * overlay therefore centres itself around x=720 and sits mostly off-screen, and no media
 * query can tell, because they all measure the same fixed 1440 on every device.
 *
 * `window.visualViewport` is the one thing that reports the real window: its size after
 * pinch-zoom, and its offset within the layout viewport as the user pans. Anything that must
 * appear *in front of the user* rather than merely in front of the page has to be positioned
 * from this.
 *
 * On a desktop browser the two viewports coincide — full width, no offset, scale 1 — so this
 * returns exactly what `inset: 0` would have, and nothing changes.
 */
import { useEffect, useState } from "react";

export type ViewportRect = { left: number; top: number; width: number; height: number };

function read(): ViewportRect {
  const vv = typeof window !== "undefined" ? window.visualViewport : null;
  if (!vv) {
    // No support: the layout viewport is the best available answer, and is the right one
    // on every desktop browser that lacks the API.
    return { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight };
  }
  return { left: vv.offsetLeft, top: vv.offsetTop, width: vv.width, height: vv.height };
}

export function useVisualViewport(): ViewportRect {
  const [rect, setRect] = useState<ViewportRect>(read);

  useEffect(() => {
    const vv = window.visualViewport;
    const update = () => setRect(read());
    update();

    if (!vv) {
      window.addEventListener("resize", update);
      return () => window.removeEventListener("resize", update);
    }
    // `scroll` fires as the user pans a zoomed page, `resize` as they pinch — an overlay
    // pinned to the visible rect has to follow both or it slides out of view again.
    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
    };
  }, []);

  return rect;
}
