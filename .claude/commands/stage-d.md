Prerequisite: Stage C gate passed (bake verified against hand-checks). If not, stop and say so.

Build Stage D: API + map, per SPEC.md §10 (read fully first).

Scope:
- api/main.py — FastAPI: GET /map/query (table/compare reads of latest batch), GET /parcel/{ssl}/underwrite (runs full_cashflow live, one parcel, honors assumption overrides incl. the include_demolition toggle, caches), POST /scenario (stamps market_snapshot at save — frozen forever), GET /scenario/{id}/export, GET /assumptions/default
- tiles: script that exports the latest bake batch to GeoJSON and runs tippecanoe -> PMTiles with attributes (rlv, rlv_psf, gap, status, confidence, best prototype, binding_constraint). Document the tippecanoe install step.
- frontend/ — React + MapLibre GL over the PMTiles. Three panels per SPEC §10: left objective/program filters (client-side over tile attributes), center map colored by RLV/SF percentile-within-view with the status shades (gray infeasible, neutral exempt, historic shade, not-yet-covered shade), right drill-down card: RLV headline, metrics grid, "gated by" callout, developability flag (existing building SF), demolition toggle, editable assumptions tab wired to /underwrite, compare view, export button. Light surfaces, single teal accent, minimal chrome.

Definition of done: I can run docker compose up + uvicorn + the frontend dev server, open the map, see DC colored, click a parcel, get the full underwrite in ~1s, flip the demo toggle and watch RLV drop, save a scenario, export it. Walk me through starting all three processes.
