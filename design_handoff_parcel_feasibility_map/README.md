# Handoff: Parcel Feasibility Platform — map, drill-down, and screening UI

## Overview

Seven screens for a DC parcel-feasibility product ("Residual"). A user searches a
geography, filters the parcel set, and clicks parcels on a map to see whether a
development deal pencils — headline metric is **residual land value (RLV)**,
surfaced to users as **"financial feasibility"**. From the map they can open a full
underwriting panel, edit model inputs, compare parcels, shortlist them, and work the
same set as a sortable table.

The screens correspond to the platform described in `SPEC.md` (v1, Washington DC) in
the attached repo. The repo today is Python only — `engine/`, `bake/`, `data/`,
`tests/`, and an **empty `api/` package**. There is no frontend and no HTTP layer yet.
So this handoff is greenfield on the client side: pick the framework, build the
screens, and wire them to endpoints that still need to be written over the existing
engine.

## About the Design Files

`Parcel Feasibility - Wireframes.dc.html` in this bundle is a **design reference
created in HTML** — a prototype showing intended layout, hierarchy, and behavior. It
is **not production code to copy**. The job is to **recreate these designs in a real
frontend environment** using that environment's established patterns and component
libraries.

Since the repo has no frontend yet, choose the stack. React + TypeScript + Vite with
MapLibre GL (or Mapbox GL) for the map is the natural fit: the map screens are the
product, and the prototype fakes the map with absolutely-positioned `<div>` rectangles
that must become real vector-tile polygon layers.

The HTML file is a single "design canvas" containing all seven screens laid out
vertically, each labeled with an id badge (`1a` through `1g`). Open it in a browser and
scroll. Parcels on screen `1a` are clickable and drive the popup contents.

## Fidelity

**Mid-fidelity.** Real typography, real color, real spacing, real copy, real
information hierarchy — treat all of it as intentional and reproduce it closely. But:

- The map is faked. Parcel geometry is a procedural grid of rectangles, not real
  DC parcel shapes. Replace wholesale with real geometry.
- All numbers are plausible sample data, not engine output. The 1b pro forma is
  internally consistent (see "Worked example" below) and can be used as a sanity
  check on your wiring, but every value must come from the engine in production.
- Charts (S-curve, sources & uses) are hand-plotted SVG. Rebuild with a charting
  library or real SVG bound to engine output.
- Interaction is partial: parcel selection and table sorting work; filters, tabs,
  toggles, and buttons are static.

Where a decision looks arbitrary, prefer the codebase's own conventions. Where it
looks deliberate — the two-tier metric language, the muted map palette with one accent,
the density of the table — it is.

---

## Design Tokens

### Color

| Token | Hex | Use |
|---|---|---|
| Accent / primary | `#0E7C7B` | Logo, primary buttons, RLV values, active states, links |
| Accent dark | `#0A5250` | Text on light-teal chip backgrounds |
| Accent mid | `#4FA39D`, `#2C918C` | Chart series, chip affordances |
| Accent tint bg | `#EAF2F1` | Selected chips, "best" tags |
| Ink | `#1A1D1C` | Primary text, dark buttons, selection ring |
| Ink 80 | `#3D3B37` | Secondary button labels |
| Ink 60 | `#5C5952` | Body text, table secondary values |
| Ink 40 | `#8A8781` | Labels, captions, inactive tabs |
| Ink 25 | `#A5A29B` | Placeholder text, helper text |
| Surface | `#FFFFFF` | Panels, cards, popups, table rows |
| Surface alt | `#FAF9F6` | Zebra rows, footers, sidebars |
| Canvas | `#F4F2ED` | Map base, inputs, neutral chips |
| Canvas deep | `#EFEDE9` | Page background behind the screens |
| Hairline | `rgba(0,0,0,.07)` – `rgba(0,0,0,.12)` | Dividers and borders |
| Amber | `#C08A3E` | Equity series, confidence bar, compare column 3 |
| Amber tint bg | `#FBF0E4` / text `#8A5A21` | Low-confidence badge |
| Slate | `#3E6E93` / tint `#E9EEF4` / text `#2D5473` | Compare column 2, highrise chip |
| Positive | `#2E6B3C` | Positive deltas |
| Negative | `#A5452F` | Negative deltas |

**Map value ramp** (8 stops, low → high feasibility):
`#EDEAE4 · #DCE9E6 · #BEDCD7 · #93C9C3 · #5FAEA8 · #2C918C · #0E7C7B · #0A5250`

Legend gradient uses a 6-stop CSS approximation:
`linear-gradient(90deg,#EDEAE4,#CFE3E0,#93C9C3,#4FA39D,#0E7C7B,#0A5250)`

**Map status colors** (non-scored parcels — these are deliberately distinct from the
value ramp so unscored land never reads as "low value"):

| Status | Fill | Border |
|---|---|---|
| Infeasible under zoning | `#9C968B` | `1px solid rgba(255,255,255,.85)` |
| Not developable — public / exempt | `repeating-linear-gradient(45deg,#C3CBCE 0 3px,#D6DCDE 3px 6px)` | `1px solid rgba(255,255,255,.85)` |
| Historic — restricted | `#B0779A` | `1px solid rgba(255,255,255,.85)` |
| Zoning not yet covered | `#FFFFFF` | `1.5px dashed #9A958C` |

Scored parcels: ramp fill, `1px solid rgba(255,255,255,.85)` border, `1.5px` radius.

### Typography

Two families, loaded from Google Fonts:

- **Public Sans** — 400/500/600/700. All UI text.
- **IBM Plex Mono** — 400/500/600. All numbers, IDs, and uppercase micro-labels.

The mono/sans split is load-bearing: any figure a user might compare across rows is
mono so digits align; any prose is sans.

| Role | Spec |
|---|---|
| Hero metric (1b RLV) | Public Sans 600, 30px, `letter-spacing:-.8px`, `line-height:1` |
| Popup metric | Public Sans 600, 25px, `-.6px` |
| Card metric (1f) | Public Sans 600, 18px |
| Screen title | Public Sans 600, 19px, `-.3px` |
| Modal title | Public Sans 600, 18px, `-.3px` |
| Section/card heading | Public Sans 600, 14–15px, `-.2px` |
| Subhead / group label | Public Sans 600, 12.5px |
| Body | Public Sans 400, 12–13.5px |
| Caption | Public Sans 400, 10.5–11.5px |
| Micro-label (uppercase) | IBM Plex Mono 500–600, 9.5–10px, `letter-spacing:.4–.7px`, `text-transform:uppercase` |
| Data value | IBM Plex Mono 400–600, 11–17px |
| Table numeric cell | IBM Plex Mono 400, 12px (600/13px for the RLV column) |

### Spacing, radius, shadow

- Spacing steps actually used: 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 18, 20, 22, 24, 26px.
- Radius: `3px` checkbox · `5px` small tag · `6–7px` input/button · `8px` control · `9px` inner card · `10–11px` panel/card · `13px` modal · `14px` pill chip · `50%` avatar.
- Shadows: floating panel `0 6px 24px rgba(0,0,0,.11)` · popup `0 10px 34px rgba(0,0,0,.19)` · side panel `-8px 0 30px rgba(0,0,0,.1)` · modal `0 26px 70px rgba(0,0,0,.32)` · map control `0 2px 10px rgba(0,0,0,.09)` · card `0 2px 10px rgba(0,0,0,.07)`.
- Screen canvas: **1440 × 900** for 1a–1f. 1g is two 706 × 520 panels side by side.

### Logo

Inline SVG, 24×24 (21×21 in compact headers), `viewBox="0 0 26 26"`:
teal `#0E7C7B` rounded square (`rx=7`) with three white bars of rising height
(`x=6 y=13 w=4 h=7` at 50% opacity · `x=11.5 y=9 w=4 h=11` at 78% · `x=17 y=5.5 w=4 h=14.5` at 100%)
over a ground line (`x=5 y=21.5 w=16 h=1.6 rx=.8`, 92%). Reads as building massing on
land. Wordmark "Residual", Public Sans 700, 15px, `-.2px`.

---

## Language rules

This matters as much as the layout. The product's audience is developers/analysts **and**
municipal planners, so the UI defaults to plain language with the technical term kept
in parentheses only where the term is the thing itself.

| Plain (default) | Technical |
|---|---|
| Financial feasibility (RLV) / Feasibility value | Residual land value / Total RLV |
| Annual return | Levered IRR |
| Income vs cost | Yield on cost |
| Cash back on equity | Equity multiple |
| Yearly income (NOI) | Stabilized NOI |
| Total cost to build | Total development cost |
| Cost per unit | Cost / unit |
| Sale value at exit | Exit value |
| Total floor area | Gross SF |
| Rentable area | Net rentable SF |
| Buildable floor area | Buildable GSF |
| Best build | Best program / prototype |
| Limited by floor area / height | Gated by FAR / height |
| Parcel ID | SSL |
| Build type: Wood frame | Wood V |

Additional rules baked into the current copy:

- **"SSL" never appears.** It is always "Parcel ID".
- **Confidence is a percentage** (`5.8%`), never a `0.058` decimal, and carries no
  explanation text — just the number under a "Confidence" label.
- **Assumption provenance is hidden.** The engine tracks national/submarket/local
  sourcing; the UI does not show it. Users see values only.
- **Parking is described in plain terms** — "12 stalls, surface" (or structured /
  underground), never "12 podium".
- **Explainer text is minimal by default.** Roughly a dozen helper lines exist in the
  design but are hidden. Ship without them; they are available if user testing shows
  people need them.
- Data-vintage and estimate disclaimers were deliberately removed from the sign-in and
  empty states. The map footer keeps only the parcel count.

The prototype implements this as two booleans (`plainLabels`, `showHelperText`) plus
`confidenceAsPercent`. In production you likely hard-code the plain labels; keep the
technical strings around only if you want an analyst-mode toggle later.

---

## Screens

### 1a — Map, filters, and parcel popup
**Purpose:** the home screen. Find a geography, narrow the set, and click parcels to
triage them.

**Layout:** full-bleed map with floating overlays. 64px top bar spanning full width
(`rgba(255,255,255,.92)`, `backdrop-filter: blur(8px)`, 1px bottom hairline). Filter
panel floats at `top:84px; left:20px`, width 288px. Legend panel floats at
`top:84px; right:20px`, width 236px. Zoom controls and a parcel-count chip sit at
`left:20px; bottom:18px`. The popup is absolutely positioned over the selected parcel,
`transform: translate(-50%,-100%)`, width 300px, clamped so it never leaves the viewport
(x clamped to 340–1180).

**Top bar:** logo + "Residual" wordmark · search field (max-width 460px, 38px tall,
`#F4F2ED` fill, radius 8, placeholder "Shaw, Ward 6", right-aligned hint
"address · parcel ID · ward") · right cluster: Shortlist with a teal count badge (7),
"Table view", "Export", 32px avatar circle.

**Filter panel** (top to bottom): header "Filters" + teal "Reset" · hairline ·
**Geography** — five pill chips (Ward 1, Ward 2, Ward 5, Ward 6, Shaw; Shaw is
selected: `#EAF2F1` fill, `#0E7C7B` border, `#0A5250` text) plus a 34px dashed
"Draw an area on the map" button · **Feasibility value** — dual-handle range slider,
4px track `#E6E3DC`, teal fill, 14px white handles with 2px teal border; value display
"$1.2M – $9M+" · **Annual return ≥** — single-handle slider at 17.0% · **Prototype** —
2×2 grid of checkbox rows (Townhome, Garden, Midrise ✓, Highrise ✓) · footer with
"**4,182** parcels match" and a dark "See table" button.

**Legend panel:** "Color by" label · segmented control (Total value / Value per SF) in
a `#F4F2ED` track, active segment white with `0 1px 2px rgba(0,0,0,.14)` · 9px gradient
bar with `$0.4M` / `$9.5M+` end labels (or `$28/SF` / `$210/SF`) · hairline · four
status swatches with labels (13px squares).

**Popup:** address (Public Sans 600, 14px) + "Parcel ID {id} · {ward}" in mono ·
close × · hairline · **Feasibility value** 25px teal + **Per unit** 15px mono ·
five key/value rows separated by hairlines (Zoning · best build, Buildable floor area,
Lot area, Current use, Limited by) · two buttons: teal "Open full underwriting"
(flex:1) and outlined "Save".

**Behavior:** clicking any parcel sets selection — the popup content, the black
selection ring (2.5px ink + 3px white glow), and its position all follow. Parcel hover
is `filter: brightness(1.08)`, 120ms.

---

### 1b — Parcel drill-down
**Purpose:** the full underwriting read on one parcel.

**Layout:** map occupies everything left of the panel; the panel is a fixed right rail
(default **620px**, comfortable range 440–760) from `top:64px` to the bottom, white,
1px left hairline, `-8px 0 30px rgba(0,0,0,.1)`.

**The zoom behavior is the point of this screen.** Selecting a parcel zooms the map to
it: the map's inner layer gets
`transform: translate(tx,ty) scale(z)` with `transform-origin: 0 0`, animated over
**550ms `cubic-bezier(.4,0,.2,1)`**, where `z = 2.6` and `tx,ty` center the parcel's
centroid in the visible map area (viewport width = 1440 − panelWidth, height 836).
Unselected parcels fade to **0.42 opacity** over 350ms; the selected parcel stays at 1.
The selection ring and the address tag counter-scale by `1/z` so their stroke weight and
type size stay constant. A black pill tag showing **the address** sits under the parcel.
Bottom-left: a single "Zoom out to view" control.

In a real map this is a `map.fitBounds(parcelBounds, {padding, duration:550})` plus a
feature-state driven opacity fade — do not literally CSS-transform the map canvas.

**Panel header:** address (19px, `-.3px`) · "Parcel ID {id} · {ward} · {lot} lot" in
mono 11.5px · star and × icon buttons (30px, radius 7) · three tags: "Best build ·
Garden walk-up" (teal tint), "Limited by height" (neutral), "Low confidence · default
inputs" (amber tint).

**Tabs:** Underwriting (active, 2px teal underline) · Cash flow · Zoning · Parcel record.

**Body:**
1. Hero — micro-label "Financial feasibility (RLV)", `$1.72M` at 30px teal, and
   "$72K per unit · 24 units" beside it in mono.
2. Metric grid — 4 columns × 2 rows, 1px gaps showing through as hairlines, radius 9,
   each cell a 9.5px mono uppercase label over a 17px mono value: Annual return 18.4% ·
   Cash back on equity 1.71× · Income vs cost 6.2% · Profit margin 13.0% · Total cost to
   build $10.2M · Cost per unit $425K · Yearly income (NOI) $633K · Sale value at exit
   $11.5M.
3. Two charts side by side (1fr 1fr, 14px gap):
   - **Cost draw S-curve**, 70px tall, `viewBox="0 0 240 96"`,
     `preserveAspectRatio="none"`. Logistic cumulative-cost curve in teal 2.2px;
     equity-draw curve in amber 1.8px dashed `4 3`; predevelopment months shaded
     `rgba(0,0,0,.035)`, construction months `rgba(14,124,123,.07)`; 51-month timeline;
     legend beneath.
   - **Sources & uses**, horizontal stacked bars, 13px tall on `#F4F2ED` tracks: uses =
     Construction $6.36M / Soft costs $1.27M / Contingency $0.32M / Land $1.72M /
     Loan interest $0.52M; sources = Construction loan $6.62M / Equity $3.57M. Label
     column 74px right-aligned, value column 52px.
4. **Program — garden walk-up, 3 floors** card with a teal "Try another prototype"
   link, then a 4×2 grid: Total floor area 30,000 · Rentable area 27,000 · Units (est.)
   24 · Floors 3 · Parking "12 stalls, surface" · Average unit size 1,125 SF · Build type
   Wood frame · Rent $3.20/SF/mo. Below it a demolition toggle row (36×20 track, 16px
   knob, off).

**Footer:** dark "Edit assumptions & re-underwrite" (flex:1) · "Save scenario" ·
"Export".

**Worked example — the numbers tie out.** Use this to verify your wiring:

```
lot 16,450 SF → 30,000 GSF (garden walk-up, 3 floors, height-limited)
hard cost      30,000 × $210/SF (wood frame)   = $6.30M → shown $6.36M
soft           20% of hard                      = $1.27M
contingency    5% of hard                       = $0.32M
interest                                        = $0.52M
land (RLV)                                      = $1.72M
total dev cost                                  = $10.2M  ($425K / unit × 24)
NOI            27,000 NRSF × $3.20 × 12 × 94% occ, 35% opex ≈ $633K
exit           $633K ÷ 5.25–5.5% cap            = $11.5M
yield on cost  $633K ÷ $10.2M                   = 6.2%
```

SPEC's own bake finding holds here: at $340/SF concrete against DC rents, midrise does
not pencil — low-rise wood frame does. The design leads with that.

---

### 1c — Inputs modal
**Purpose:** change model assumptions for one parcel and re-underwrite.

**Layout:** full-screen scrim `rgba(26,29,28,.42)` over a dimmed map. Modal centered
horizontally at `top:44px`, **1000 × 846**, radius 13.

**Header:** "Inputs — Defaults" (18px, `-.3px`) · below it "Editing for **{address}**
only" — the address, not the ID · "Reset to defaults" outlined button · × button.

**Body:** 190px left sidebar (`#FAF9F6`, 1px right hairline) with nav rows — Timeline 4 ·
Cost 6 · Revenue 5 · Debt 7 · Exit & return 4 · Envelope 2 · Program overrides 5 — the
active row white with 600 weight and a teal count. Under the nav, an amber
confidence card: uppercase "Confidence" label and **5.8%** at 22px mono. No explainer.

Right side: assumption groups, each a 12.5px 600 heading over a **two-column grid**
(`1fr 1fr`, `8px 16px` gap) of rows. Each row is `label — value field`: label flexes,
field is 104px × 30px, radius 6, right-aligned mono 12.5px. **Edited fields** get a teal
border and `#F5FAF9` fill. **No provenance tags and no group descriptions** — deliberately
removed.

Groups and values: Timeline (Predevelopment 12, Construction 30 *edited*, Lease-up 12,
Hold after stabilization 3) · Cost (Hard cost $/SF $340, Soft % of hard 20.0%,
Contingency 5.0%, Parking/stall structured $45,000, Cost escalation 3.0%, Demo $/SF $12) ·
Revenue (Base rent $3.20, Rent premium 1.15×, Occupancy 94.0%, Opex ratio 35.0%, Rent
growth 3.0%) · Debt (Construction LTC 68.0% *edited*, Construction rate 8.50%, Perm LTV
60.0%, Perm rate 6.50%, Amortization 30, Min DSCR 1.25) · Exit & return (Exit cap 5.25%
*edited*, Selling cost 2.0%, Target margin 15.0%, IRR hurdle 17.0%).

**Footer:** "3 inputs changed from default" on the left; "Cancel" and teal
"Re-underwrite parcel" on the right.

---

### 1d — Table view
**Purpose:** work the filtered set as rows; sort and export.

**Layout:** 64px header (logo, Map/Table segmented control, "Compare 3 selected", dark
"Export CSV") · 52px filter bar (`#FAF9F6`) with parcel count, applied-filter chips
each with an × affordance, a dashed "+ Add filter" chip, and a right-aligned
"Sorted by {label} · click a column to re-sort" · then the table.

**Columns** (grid template, exact):
`34px 236px 76px 112px 110px 110px 110px 132px 84px 84px 1fr`
→ checkbox · Parcel (address + "ID {n}" beneath) · Ward · Best build (colored chip) ·
Total cost · Cost / unit · NOI · Feasibility value · Yield · Return · Buildable SF + "Open".

All five money/percent columns are the same width so the numeric rhythm is even.
Numeric cells right-aligned mono 12px; the Feasibility value column is 600/13px ink.

**Sorting is implemented.** Clicking any numeric header sorts by that key,
toggling direction; the active header goes ink-colored and shows ▼/▲, and the caption
updates. Default: feasibility value, high to low. Header row 38px, data rows 46px with
zebra `#FAF9F6`, first three rows checked.

---

### 1e — Compare
**Purpose:** three parcels side by side.

**Layout:** `220px 1fr 1fr 1fr` grid. Label column `#FAF9F6`. Each parcel column has a
76px gradient swatch, address, "Parcel ID {n}" (no zoning), and a tag.

**Each column owns a color** — teal `#0E7C7B`, slate `#3E6E93`, amber `#C08A3E` — carried
through its swatch gradient, its tag tint, and its values on highlighted rows. This is
deliberate: it stops the eye reading "column 1 = the good one".

Rows (44px, alternating `#fff` / `#FAF9F6`; highlighted rows get a `#F6FAF9` wash and
600/15px mono values in the column color; others 400/13px ink):
Feasibility value ★ · Value per unit · Annual return ★ · Income vs cost · Cash back on
equity · Yearly income (NOI) ★ · Total cost to build · Cost per unit · Buildable floor
area · Best build. (★ = highlighted.)

Tags: "Best feasibility value" (teal tint) · "Highest return" (slate tint) ·
"Cheapest basis" (amber tint).

---

### 1f — Shortlist
**Purpose:** saved parcels and scenarios.

**Layout:** 250px left sidebar (Lists: Shaw acquisitions 7 *active*, Ward 5 industrial
edge 12, Historic — watch 4, Passed on 19; plus a "List totals" card — Parcels 7,
Combined value $31.2M, Combined floor area 186,400, Median return 17.9%) · 3-column card
grid (16px gap) on `#FAF9F6`.

**Card:** 82px gradient header with a prototype chip top-right · address (14px 600) ·
"Parcel ID {n}" (no zoning) · a metric row using `justify-content: space-between` across
the **full card width** — Value / Return / Yield, all three at **Public Sans 600 18px**,
value in teal and the other two in ink `#1A1D1C`, each under a 9.5px mono uppercase
label · hairline · "Saved N days ago" and a teal "Open scenario" link.

The three metrics share size and weight and differ only in color — that was an explicit
correction, keep it.

---

### 1g — Sign-in and empty state
Two 706 × 520 panels.

**Sign-in:** 330px left column — logo + wordmark, headline "Development feasibility,
parcel by parcel." (24px 600, `-.5px`), sub "150K+ DC parcels, priced for what they
could become.", email field, password field, teal "Sign in". Right side is a map
fragment with a `linear-gradient(90deg,#F4F2ED 0%,rgba(244,242,237,0) 40%)` fade. No
version or workspace footnote.

**Empty state:** 56px dashed rounded square · "Nothing selected yet" (16px 600) ·
"Search a neighborhood, or draw an area on the map." · teal "Jump to Shaw" and outlined
"Draw an area". No data-vintage or estimate disclaimer.

---

## Interactions & Behavior

| Interaction | Behavior |
|---|---|
| Parcel click (1a) | Selects; popup content, position, and selection ring update |
| Parcel hover | `filter: brightness(1.08)`, 120ms |
| Parcel click (1b) | Map zooms to parcel, 550ms `cubic-bezier(.4,0,.2,1)`; others fade to 0.42 over 350ms; address tag appears |
| Legend "Color by" | Switches the value ramp between total feasibility value and value per SF; ramp end labels update |
| Column header click (1d) | Sorts by that key; re-click reverses; header state and caption update |
| Panel/modal close | × dismisses |
| "Open full underwriting" | 1a popup → 1b panel |
| "Edit assumptions" | 1b → 1c modal |
| "Re-underwrite parcel" | Applies edited inputs, re-runs, returns to 1b |

**Not yet designed** — you will need these and should ask before inventing them:
loading/skeleton states for the map and for a re-underwrite (the full model is slow
enough to need one), error and empty-result states for filters, the draw-an-area
interaction, and responsive/mobile behavior. Everything here assumes a ≥1440px desktop.

## State

```
view              'map' | 'table' | 'compare' | 'shortlist'
selectedParcelId  string | null          // drives popup, panel, zoom
mapObjective      'total' | 'per_sf'     // legend ramp
mapBounds/zoom                            // geography
filters           { wards[], drawnPolygon, rlvMin, rlvMax, irrMin, prototypes[] }
sort              { key, dir }            // 1d
compareIds        string[]                // max 3
shortlists        { id, name, parcelIds[] }[]
assumptionEdits   Partial<AssumptionSet>  // 1c working copy
scenarios         saved { parcelId, assumptions, results, savedAt }[]
```

Two data tiers, straight from SPEC: the **baked screening layer** (fast, all 154,318
parcels, powers map color and filtering) and the **full model** (slow, levered,
IRR-solved, one parcel at a time, powers 1b/1c/1e). The UI must never imply they are the
same number — 1b explicitly shows both and says they differ. An IRR-threshold filter
runs the full model across the filtered set and will be slow; design the loading state
for it.

## API — to be built

`repo/api/` is an empty package. The engine and bake pipeline exist; the HTTP layer does
not. These screens need roughly:

```
GET  /parcels/tiles/{z}/{x}/{y}      vector tiles: geometry + screening value + status
GET  /parcels/search?q=              address / parcel ID / ward typeahead
POST /parcels/query                  filters → parcel list for map + table, sortable
GET  /parcels/{id}                   record, zoning, current use, screening result
POST /parcels/{id}/underwrite        assumption overrides → full model result
GET  /assumptions/defaults           default input set
CRUD /shortlists, /scenarios
```

Read `SPEC.md` in the repo for field names and model semantics before naming anything —
the vocabulary there (screening vs. full, prototypes, gating, confidence) is what the UI
labels are translating from.

## Screenshots

`screens/` holds a 2× PNG of each screen, captured from the prototype at its design
size (1440 × 900; 1g is the two 706 × 520 panels side by side):

- `1a-map-filters-popup.png`
- `1b-parcel-drilldown.png`
- `1c-inputs-modal.png`
- `1d-table-view.png`
- `1e-compare.png`
- `1f-shortlist.png`
- `1g-signin-and-empty-state.png`

Use them for visual reference, but **read exact values from this README and the HTML,
not from the pixels** — and note the screenshots are single-state: they cannot show the
1b zoom transition, sort toggling, or hover states.

## Assets

None external. The logo is inline SVG (spec above); charts are inline SVG; there are no
raster images, no icon font, and no photography. Fonts load from Google Fonts —
substitute your own hosting if the codebase self-hosts.

## Files

- `Parcel Feasibility - Wireframes.dc.html` — all seven screens on one canvas. Open in a
  browser; scroll; click parcels on 1a and column headers on 1d.
- `screens/*.png` — 2× captures of all seven screens (see Screenshots above).
- `support.js` — runtime for the prototype file only. **Not part of the design**; do not
  port it.
- `SPEC.md` (in the repo, not this bundle) — the source of truth for model behavior,
  field names, and defaults. The UI copy is a plain-language translation of it; when the
  two disagree about what a number *means*, SPEC wins.
