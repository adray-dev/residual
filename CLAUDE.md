# Parcel Feasibility Platform — project instructions

Read `SPEC.md` (v1.3) before writing any code. It is the authoritative design: every formula,
default value, schema, and decision. When this file and SPEC.md conflict, SPEC.md wins.
Do not re-litigate settled decisions in SPEC.md's revision notes; implement them.

## What this is
Per-parcel real-estate development feasibility engine for Washington DC. Map colored by
precomputed screening RLV/SF; full monthly levered cash-flow model on demand per parcel.

## Non-negotiable rules
- `engine/` is PURE: no DB, no network, no file I/O, no imports of psycopg/sqlalchemy/requests.
  It receives dataclasses, returns dataclasses. If an engine function needs data, it takes it
  as an argument.
- Only `data/repositories.py` and `data/loaders/` touch the database.
- No LLM calls anywhere in runtime code. LLM work (zoning, rent seeding) is one-time authoring,
  already done or run manually.
- Revenue is `net_rentable_sf × rent_psf`. `unit_count` is reporting-only. Never wire unit
  count into revenue.
- Every parcel gets a `bake_results` row. Status rows use prototype_id sentinel `'__none__'`.
- IRR and solvers fail gracefully (None / flag), never raise to the caller.
- All monetary/area defaults come from SPEC.md §2 (`engine/assumptions.py` is the single
  source of truth). Do not invent numbers; do not change defaults without asking.

## Build order — HARD GATES, do not skip ahead
1. **Stage A** — engine core + hand-check tests. Gate: `pytest` green on tests/test_engine_hand_checks.py.
2. **Stage B** — schema + DC loaders + repositories. Gate: real parcels loaded, spot-checks pass.
3. **Stage C** — the bake. Gate: bake runs on DC; hand-check parcels match Stage A outputs.
4. **Stage D** — FastAPI + static tiles + React map.
Never start a stage until the previous gate passes. If a gate fails, fix it; do not proceed
with known-red tests. Use `/stage-a` … `/stage-d` slash commands to kick off each stage.

## Commands
- Setup: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- Tests: `pytest -x -q`
- DB (Stage B+): Postgres runs LOCALLY via Homebrew, not Docker. `brew services start
  postgresql@14`, then `psql "$DATABASE_URL" -f data/schema.sql` for a fresh schema.
  `docker-compose.yml` is vestigial — do not use it, and do not suggest `docker compose`.
- Bake (Stage C): `python -m bake.run_bake`
- API (Stage D): `uvicorn api.main:app --reload`
- Frontend (Stage D): `cd web && npm install && npm run dev` → http://localhost:5173
  (Vite proxies /meta, /map, /parcel, /assumptions, /tiles to the API on :8000)
- Tiles (Stage D): `python -m tiles.build_tiles` (needs `brew install tippecanoe`)

`.env` is loaded automatically by `data/repositories.py` at import, so DATABASE_URL never
needs exporting by hand — for uvicorn, pytest, the bake, or the tile build. Copy
`.env.example` to `.env` on a fresh checkout. An exported DATABASE_URL still overrides it.

## Layout (create exactly this; see SPEC.md §1)
```
engine/    types.py prototypes.py assumptions.py envelope.py program.py proforma.py solve.py confidence.py
data/      schema.sql repositories.py loaders/{dc_parcels.py,dc_zoning.py,seed_zoning.py,seed_market.py}
bake/      run_bake.py
api/       main.py
tests/     test_engine_hand_checks.py
```

## Conventions
- Python 3.11+, type hints everywhere, dataclasses per SPEC.md §3.1 exactly (field names matter:
  downstream stages and tests depend on them).
- Keep functions small and deterministic; same inputs → same outputs, always.
- When SPEC.md is ambiguous (it shouldn't be), STOP and ask rather than deciding silently.
- Commit at each green gate with a message naming the stage.
