-- Parcel feasibility platform — schema (SPEC.md §7.1)
-- `ssl` is the DC universal key (Square-Suffix-Lot).

CREATE EXTENSION IF NOT EXISTS postgis;

-- submarkets is created first: parcels and market_data reference it.
CREATE TABLE submarkets (
  submarket_id TEXT PRIMARY KEY,
  name TEXT,
  boundary GEOMETRY(MultiPolygon, 4326)
);
CREATE INDEX submarkets_geom_gix ON submarkets USING GIST (boundary);

CREATE TABLE parcels (
  ssl TEXT PRIMARY KEY,
  parcel_geom GEOMETRY(MultiPolygon, 4326),
  lot_area_sf DOUBLE PRECISION,
  zone_code TEXT,          -- NOT a hard FK (fix #1): a parcel in a not-yet-encoded
                           -- district must still load. The bake resolves an unencoded
                           -- zone to a skip-with-reason, not a crash. Coverage of
                           -- zoning_rules improves over time without blocking loads.
  submarket_id TEXT REFERENCES submarkets(submarket_id),
  land_value DOUBLE PRECISION,
  improvement_value DOUBLE PRECISION,
  improvement_ratio DOUBLE PRECISION,
  land_use_code TEXT,
  existing_building_sf DOUBLE PRECISION DEFAULT 0,  -- CAMA gross building area; demo toggle + developability
  is_exempt BOOLEAN DEFAULT FALSE,                  -- public/federal/church/cemetery/ROW
  is_historic BOOLEAN DEFAULT FALSE                 -- in a historic district (flagged, not scored)
);
CREATE INDEX parcels_geom_gix ON parcels USING GIST (parcel_geom);

CREATE TABLE zoning_rules (
  district_code TEXT PRIMARY KEY,
  max_far DOUBLE PRECISION,
  max_height_ft DOUBLE PRECISION,
  max_stories INTEGER,
  lot_occupancy JSONB,
  permitted_uses JSONB,
  parking_ratio JSONB,
  requires_ground_floor_active BOOLEAN DEFAULT FALSE,
  matter_of_right BOOLEAN DEFAULT TRUE,
  source_citation TEXT,
  as_of_date DATE
);

CREATE TABLE market_data (
  submarket_id TEXT REFERENCES submarkets(submarket_id),
  use_type TEXT,
  rent_psf DOUBLE PRECISION,
  cost_psf JSONB,          -- {construction_type: $/SF}
  exit_cap DOUBLE PRECISION,
  as_of DATE,
  source TEXT,
  PRIMARY KEY (submarket_id, use_type, as_of)
);

CREATE TABLE prototypes (
  prototype_id TEXT PRIMARY KEY,
  construction_type TEXT,
  min_stories INTEGER, max_stories INTEGER,
  efficiency_ratio DOUBLE PRECISION,
  default_unit_mix JSONB, avg_unit_sf JSONB, parking_type TEXT
);

CREATE TABLE bake_results (
  ssl TEXT REFERENCES parcels(ssl),
  prototype_id TEXT NOT NULL DEFAULT '__none__',  -- PK columns cannot be NULL in Postgres;
                                -- status rows (exempt/historic/unencoded/infeasible) use the
                                -- sentinel '__none__' instead of NULL
  is_best BOOLEAN,
  status TEXT NOT NULL,         -- 'scored' | 'infeasible' | 'zone_not_encoded' | 'exempt' | 'historic'
  screening_rlv DOUBLE PRECISION,   -- NULL when not 'scored'
  feasibility_gap DOUBLE PRECISION, -- NULL when not 'scored'
  -- Both ranking metrics are STORED, not derived at read time (SPEC §9). The map used to
  -- divide screening_rlv by lot_area_sf on read while the bake selected on
  -- screening_rlv/gross_sf — two different measures, and gross_sf was never a column.
  -- Readers now order on these columns and never divide.
  rlv_total DOUBLE PRECISION,           -- = screening_rlv. The DEFAULT map objective.
                                        -- screening_rlv is kept verbatim (SPEC §7.1 pins it);
                                        -- rlv_total is its objective-named twin, so the two
                                        -- selectable objectives are a matched pair of columns.
  rlv_per_buildable_sf DOUBLE PRECISION,-- = screening_rlv / program.gross_sf. Alternate
                                        -- objective. NULL when not 'scored' or gross_sf = 0.
  confidence DOUBLE PRECISION,
  binding_constraint TEXT,     -- for 'scored': far/height/stories; for others: the reason
  computed_at TIMESTAMPTZ,
  PRIMARY KEY (ssl, prototype_id, computed_at)
);
CREATE INDEX bake_best_idx ON bake_results (is_best, computed_at);
CREATE INDEX bake_status_idx ON bake_results (status, computed_at);
-- The map's default sort: latest batch, best row per parcel, ordered by total RLV.
CREATE INDEX bake_rlv_total_idx ON bake_results (computed_at, rlv_total DESC);

-- MIGRATION NOTE (pre-Stage-D, applied to any database created before this revision).
-- `rlv_per_buildable_sf` cannot be backfilled from existing rows — gross_sf was never
-- persisted — so the columns are added empty and repopulated by re-running the bake
-- (`python -m bake.run_bake`), which appends a fresh batch. Retention (last 2 batches)
-- ages the pre-migration batch out on the following run.
--
--   ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS rlv_total DOUBLE PRECISION;
--   ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS rlv_per_buildable_sf DOUBLE PRECISION;
--   UPDATE bake_results SET rlv_total = screening_rlv WHERE rlv_total IS NULL;
--   CREATE INDEX IF NOT EXISTS bake_rlv_total_idx
--       ON bake_results (computed_at, rlv_total DESC);

CREATE TABLE assumption_sets (
  assumption_set_id TEXT PRIMARY KEY,
  name TEXT, is_default BOOLEAN DEFAULT FALSE,
  program JSONB, timeline JSONB, cost JSONB,
  revenue JSONB, debt JSONB, exit JSONB, envelope JSONB
);

CREATE TABLE scenarios (
  scenario_id TEXT PRIMARY KEY,
  ssl TEXT REFERENCES parcels(ssl),
  prototype_id TEXT REFERENCES prototypes(prototype_id),
  assumption_set_id TEXT REFERENCES assumption_sets(assumption_set_id),
  user_id TEXT DEFAULT 'local',   -- real auth later; single local user in v1
  market_snapshot JSONB,          -- v1.2: the exact MarketData values used, stamped at save
                                  -- time. A saved scenario NEVER re-reads live market data —
                                  -- it is fully frozen and reproducible. (Future: staleness
                                  -- flag + proposed refresh after N months. Deferred.)
  cashflow JSONB, outputs JSONB, saved_at TIMESTAMPTZ
);
