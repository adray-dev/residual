# Known issues

Deferred problems, with the reason for deferring. Fix or delete each entry — an item
that is neither is just a stale note.

## Open bugs

- **Sources and uses stop balancing once an assumption is overridden.** Found 2026-08-08
  while building the 1c modal. On the default run the two sides agree to the dollar; with
  an edit they diverge by millions, and the 1b chart correctly refuses to draw:

  | Run (parcel `0546    0819`) | Uses | Sources | Gap |
  |---|---|---|---|
  | defaults | $344,952,542 | $344,952,542 | $0 |
  | `soft_cost_pct` 25% | $346,656,065 | $346,656,065 | $0 |
  | `exit_cap_rate` 5.0% | $358,789,615 | $366,604,090 | **$7.81M** |
  | `construction_ltc` 70% | $351,917,772 | $371,767,921 | **$19.85M** |

  This is NOT caused by the market-override change made the same day: `construction_ltc`
  is a plain assumption on the pre-existing path and shows the largest gap. The pattern
  suggests it appears when an edit moves the solved land value enough to change how the
  construction loan sizes, and that `serializers.sources_uses` derives the loan from
  `sum(construction_draw) + interest` in a way that stops agreeing with the cash flow's
  own funding once the sizing constraint shifts.

  Not fixed here because it lives in the pro forma / serializer and touches SPEC §6.4's
  capitalized-interest semantics — worth getting right rather than guessing. The
  `balanced` flag means the UI degrades honestly in the meantime.

## v2

- **Map first interaction is slow.** The tileset is 30.4 MB across 132,604 parcels and
  MapLibre parses a lot of geometry before the first paint settles. Revisit in v2:
  candidates are dropping `--no-tile-size-limit` in favour of a real budget above z13,
  trimming attributes that only the drill-down needs, and splitting the value bins into
  their own thin overlay so a zoomed-out view does not carry parcel-level geometry.
  Deliberately not optimised now — correctness of what the map *says* came first.
