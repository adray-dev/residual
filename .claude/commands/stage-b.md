Prerequisite: Stage A gate is green (`pytest -x -q` passes). If not, stop and say so.

Build Stage B: data layer + DC loaders, per SPEC.md §7 and §8 (read fully first).

Scope:
- data/schema.sql — verbatim from §7.1 (note: bake_results.prototype_id NOT NULL with '__none__' sentinel; parcels has existing_building_sf/is_exempt/is_historic; zone_code is NOT a foreign key; scenarios has market_snapshot)
- data/loaders/seed_zoning.py — write the §8 starter district rows incl. requires_ground_floor_active flags
- data/loaders/dc_parcels.py — per §7.2 steps 1-8: paginated ArcGIS REST fetch, EPSG:26985 reprojection with the median-lot-area sanity assertion, CAMA Residential+Commercial join on SSL (EXCLUDE condos), existing_building_sf, is_exempt from tax-exempt/owner type, largest-intersection zoning + ward joins, historic-district join, schema-validation guard that aborts loudly on missing fields
- data/loaders/seed_market.py — writes ward-level market_data rows; seed with SPEC §2 fallback values and a clear source tag "national_default" (the real LLM-researched values get entered manually later)
- data/repositories.py — the function list in §7.3, plain SQL via psycopg/SQLAlchemy core
- docker-compose.yml already exists; use DATABASE_URL from .env

Verification gate (do all, show me the output):
1. Load the data. Report row counts: parcels, by-status breakdown of zone matches, exempt count, historic count, condos excluded.
2. Spot-check 3 real parcels: print ssl, lot_area_sf, zone_code, land_value, existing_building_sf and sanity-assess them.
3. Confirm median lot_area_sf is in [1,000, 50,000].
Then stop — do not start Stage C.
