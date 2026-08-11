# Residual logo — integration

Drop-in for the `web/` app. Written against the current tree: `src/App.tsx`,
`src/components/Table.tsx`, `src/styles/tokens.css`, `index.html`.

## 1. Files

| From here | To |
| --- | --- |
| `brand/ResidualMark.tsx` | `web/src/components/ResidualMark.tsx` |
| `brand/residual-mark.svg` | `web/public/brand/residual-mark.svg` |
| `brand/residual-mark-ondark.svg` | `web/public/brand/residual-mark-ondark.svg` |
| `brand/residual-mark-onlight.svg` | `web/public/brand/residual-mark-onlight.svg` |
| `brand/residual-mark-mono.svg` | `web/public/brand/residual-mark-mono.svg` |
| `brand/residual-lockup.svg` | `web/public/brand/residual-lockup.svg` |
| `brand/favicon.svg` | `web/public/favicon.svg` |

Create `web/public/` if it doesn't exist — Vite serves it from the root.

## 2. Token

Add to the accent block in `src/styles/tokens.css`:

```css
  --brand-magenta: #c4187e;   /* logo residual lot only — never a UI color */
```

It is deliberately outside both the value ramp and the semantic set. It exists so
the mark has one moment of heat; nothing in the interface should use it.

## 3. Replace the inline `Logo()` in `App.tsx`

Delete the `function Logo()` block at the bottom of `src/App.tsx` (the massing-on-a-
ground-line placeholder, ~line 664) and its comment. Then:

```tsx
import { ResidualMark } from "./components/ResidualMark";
```

and in the topbar (~line 413):

```tsx
<ResidualMark size={24} />
<span className={styles.wordmark}>Residual</span>
```

`src/components/Table.tsx` (~line 225) has the same wordmark in its own header —
if it renders a mark alongside it, use the same two lines.

## 4. Favicon

In `web/index.html`, inside `<head>`:

```html
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
```

## Usage rules

- **Tones.** `color` (default, inherits `--accent`), `ondark`, `onlight`, `mono`.
  The mark never carries its own teal — it reads `--accent`, so a token change
  moves the logo with the UI.
- **Minimum size 16px.** The smallest lot is 16/100 of the mark; below 16px it
  closes up. The 24px topbar instance is the intended product size.
- **Clear space** = one small lot (16% of the mark's width) on all four sides.
  In the topbar that's ~4px; don't crowd it against the wordmark — 12px gap.
- **Don't** recolor the magenta lot, rotate the mark, add a container/rounded
  square, apply a gradient, or add a stroke. It's six rects on a 100-unit grid;
  every edge is on the grid and `shapeRendering="crispEdges"` keeps it that way.
- **Wordmark** is Public Sans 600, `-0.025em` tracking — already the app's sans.

## Prompt for Claude Code

> Integrate the Residual logo. Copy the files per the table in `handoff/INSTALL.md`
> into `web/`, add the `--brand-magenta` token to `src/styles/tokens.css`, delete
> the placeholder `Logo()` function at the bottom of `src/App.tsx` and render
> `<ResidualMark size={24} />` in its place in the topbar, and add the favicon link
> to `web/index.html`. Do not change any other styling, and do not use
> `--brand-magenta` anywhere outside the mark.
