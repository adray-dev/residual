# Parcel Feasibility Platform (DC pilot)

Development-feasibility screening: a map of DC parcels colored by residual land value,
with a full monthly levered pro forma on demand per parcel.

**Start here:** `SPEC.md` is the authoritative design (v1.3). `CLAUDE.md` carries the
build rules Claude Code loads automatically.

## Building with Claude Code

From this directory, start Claude Code (`claude`), then run the stages **in order**,
waiting for each gate to pass:

1. `/stage-a` — pure engine core + hand-check tests. Gate: `pytest -x -q` green.
2. `/stage-b` — Postgres/PostGIS schema + DC Open Data loaders. Gate: data loaded, spot-checks shown.
3. `/stage-c` — the city-wide bake. Gate: outputs match Stage A hand-checks.
4. `/stage-d` — API + tiles + map frontend.

Do not skip gates. The engine math being provably correct in isolation (Stage A) is what
makes every later stage debuggable.

## Manual prerequisites

- Python 3.11+, Docker (for Postgres/PostGIS from Stage B), Node 18+ (Stage D frontend),
  tippecanoe (Stage D tiles).
- Copy `.env.example` to `.env`.

## Post-build verification tasks (human)

- Verify SPEC §8 zoning seed values against the current DC ZR (the `verify` checklist column).
- Replace the national-default market values with researched DC ward rents/caps
  (see SPEC §7.2 `seed_market.py` notes).
