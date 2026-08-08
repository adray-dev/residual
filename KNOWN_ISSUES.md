# Known issues

Deferred problems, with the reason for deferring. Fix or delete each entry — an item
that is neither is just a stale note.

## v2

- **Map first interaction is slow.** The tileset is 30.4 MB across 132,604 parcels and
  MapLibre parses a lot of geometry before the first paint settles. Revisit in v2:
  candidates are dropping `--no-tile-size-limit` in favour of a real budget above z13,
  trimming attributes that only the drill-down needs, and splitting the value bins into
  their own thin overlay so a zoomed-out view does not carry parcel-level geometry.
  Deliberately not optimised now — correctness of what the map *says* came first.
