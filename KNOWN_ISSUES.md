# Known issues

Three tiers, and the tier is the point:

- **Must fix before production** — things that make a number wrong or unsupportable. Nobody
  should underwrite real money against this product until every item here is closed.
- **Open bugs** — defects that are contained, understood, and degrade honestly.
- **v2** — deferred improvements. Not correctness.

Fix or delete each entry. An item that is neither is just a stale note.

---

## Must fix before production

Nothing below is cosmetic. Each one either produces a number the model cannot stand behind,
or rests on data nobody has verified.

### 1. The full levered underwrite goes internally inconsistent under some edits

Sources and uses are the same money counted two ways, so they must agree. On a
default run they agree to the dollar. Once an assumption is overridden they diverge:

| Run (parcel `0546    0819`) | Uses | Sources | Gap |
|---|---|---|---|
| defaults | $344,952,542 | $344,952,542 | $0 |
| `soft_cost_pct` 25% | $346,656,065 | $346,656,065 | $0 |
| `exit_cap_rate` 5.0% | $358,789,615 | $366,604,090 | **$7.81M** |
| `construction_ltc` 70% | $351,917,772 | $371,767,921 | **$19.85M** |

This is a **tier-2 correctness problem**, not a charting problem: it means the levered
model's capital stack does not close under inputs the product invites users to change. It
is not caused by the market-override change of 2026-08-08 — `construction_ltc` is a plain
assumption on the older path and shows the larger gap.

The likely locus is the interaction between `solve_irr_rlv` moving the land value and how
`serializers.sources_uses` derives the construction loan (`sum(construction_draw) +
interest`) versus how the cash flow actually funds itself. SPEC §6.4's capitalized-interest
semantics are what make this delicate, and it deserves a dedicated debugging pass rather
than a guess.

Contained meanwhile: `SourcesUses.balanced` is computed server-side and the 1b chart
refuses to draw when it is false, so the UI never presents a broken capital stack as if it
balanced. **Scheduled: a dedicated pass after Stage D's screens are done.**

### 2. Zoning values are plausible, not verified

SPEC §11: "§8 zoning seed and §2 defaults are plausible-not-verified until the human
verification pass." The ZR values behind every envelope — FAR, height, story caps, lot
occupancy, parking ratios — were authored, not read off the regulation by a person. Every
RLV on the map inherits whatever is wrong in them.

### 3. Rents are ward averages, not comps

SPEC §11: "Ward-level rents — submarket averages; parcel-level comps are the data-moat
upgrade." Revenue is `net_rentable_sf × rent_psf`, so rent error flows straight into RLV at
full weight, and a ward average is a poor proxy for a specific block.

### 4. Construction costs are unverified national figures

`hard_cost_psf` is tagged `national` in `PROVENANCE` and is the single largest line in
uses. SPEC's own bake finding — that concrete midrise does not pencil against DC rents
while wood frame does — is a direct consequence of this number, so the prototype ordering
on the map is only as good as it is.

### 5. Product-type rent premium and exit-cap adjustment are placeholders

SPEC §11, verbatim: `RENT_PREMIUM_FACTOR` and `EXIT_CAP_ADJUSTMENT` "were chosen as
plausible starting values to give product type a voice in the model, not measured from
anything. They are load-bearing for which prototype wins a parcel." SPEC's instruction is
explicit: **do not present the resulting prototype ordering as a finding until seeded.**

---

## v2

- **Map first interaction is slow.** The tileset is 30.4 MB across 132,604 parcels and
  MapLibre parses a lot of geometry before the first paint settles. Revisit in v2:
  candidates are dropping `--no-tile-size-limit` in favour of a real budget above z13,
  trimming attributes that only the drill-down needs, and splitting the value bins into
  their own thin overlay so a zoomed-out view does not carry parcel-level geometry.
  Deliberately not optimised now — correctness of what the map *says* came first.
- **No `react-hooks/exhaustive-deps` lint.** A stale-closure bug (a dependency array
  missing `selectedFromLink`) silently made the demolition toggle a no-op with no error and
  no request. ESLint with that rule catches the whole class.
