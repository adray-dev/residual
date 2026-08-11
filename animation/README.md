# Logo animation — design source

The design-canvas export of the boot animation. This is the **source**, not what runs.

`Residual Logo Animation.dc.html` only runs inside the design-canvas harness: it loads
`support.js` and `animations-v3.jsx` from global scope and reads its clock from a
`useComposition()` the harness provides. None of that survives a Vite build.

What ships is **`web/src/components/Loader.tsx`** — a port of `ResidualLoader.jsx`'s variant
4 ("Spell Out", the variant the export defaults to). The easing functions, the `animate`
helper, the rect table, and the timings are reproduced verbatim, so the motion is the motion
that was designed. What is not reproduced is the harness: the port drives itself from
`requestAnimationFrame` and dismisses itself when the composition ends.

Editing the files here changes nothing about the app. Change `Loader.tsx`, and mirror it
back here if the design should stay in step.

Two deliberate differences in the port:

- The tagline reads **"Building on every block"**. The export says "Feasibility on every
  block"; the wording was changed when it was wired in.
- Variants 1–3 (Drop & Settle, Subdivide, Parcel Split) are not ported. They are still in
  `ResidualLoader.jsx` if one of them is ever preferred.

The composition is four scenes totalling 4.0s, played once:

| Scene | Duration | What happens |
|---|---|---|
| Emerge | 1.4s | The six lots appear and take their first positions |
| Assemble | 1.2s | The lots settle and align into the final grid |
| Residual | 0.8s | The magenta residual lot ignites, calling out the payoff parcel |
| Hold | 0.6s | The mark settles and the wordmark fades in |

`uploads/` is the brand kit the animation was built against. `web/src/components/ResidualMark.tsx`
is the copy the app actually uses.
