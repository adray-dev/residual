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

### 1. Zoning values are plausible, not verified

SPEC §11: "§8 zoning seed and §2 defaults are plausible-not-verified until the human
verification pass." The ZR values behind every envelope — FAR, height, story caps, lot
occupancy, parking ratios — were authored, not read off the regulation by a person. Every
RLV on the map inherits whatever is wrong in them.

### 2. Rents are ward averages, not comps

SPEC §11: "Ward-level rents — submarket averages; parcel-level comps are the data-moat
upgrade." Revenue is `net_rentable_sf × rent_psf`, so rent error flows straight into RLV at
full weight, and a ward average is a poor proxy for a specific block.

### 3. Construction costs are unverified national figures

`hard_cost_psf` is tagged `national` in `PROVENANCE` and is the single largest line in
uses. SPEC's own bake finding — that concrete midrise does not pencil against DC rents
while wood frame does — is a direct consequence of this number, so the prototype ordering
on the map is only as good as it is.

### 4. Product-type rent premium and exit-cap adjustment are placeholders

SPEC §11, verbatim: `RENT_PREMIUM_FACTOR` and `EXIT_CAP_ADJUSTMENT` "were chosen as
plausible starting values to give product type a voice in the model, not measured from
anything. They are load-bearing for which prototype wins a parcel." SPEC's instruction is
explicit: **do not present the resulting prototype ordering as a finding until seeded.**

---

## Fixed

- **Sources and uses stopped balancing once an assumption was overridden.** Closed
  2026-08-08. Development equity was summed from negative equity cash flows across the
  WHOLE hold, so a cash-in refinancing at stabilization (perm loan below the construction
  balance) and any month of operating shortfall during hold were both counted as sources
  that funded the build — with no matching entry in uses. The gap equalled those flows
  exactly, which is why it only appeared on edited scenarios: the default run has neither.

  Scoping equity to the development period makes the identity exact rather than
  approximate: `sources = (draws + interest) + equity_needed = total_cost + interest =
  uses`. Nothing is lost — `peak_equity` spans the whole hold and still carries the later
  capital, so what a developer has to find is never understated. Pinned by 15 parametrized
  cases across the inputs the 1c modal exposes, and the Excel export inherited the fix by
  construction because it computes the stack the same way.

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
