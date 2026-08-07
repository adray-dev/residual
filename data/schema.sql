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
  -- Stage D (v1.6): the UI is address-forward — six of the seven handoff screens lead
  -- with a street address, and search accepts "address · parcel ID · ward". Both fields
  -- ride on the Common Ownership Layer already loaded (PREMISEADD, NBHDNAME/SUBNBHD),
  -- so this is two extra outFields, not a new dataset or a new spatial join.
  -- NULLABLE on purpose: not every SSL has a premise address (vacant interior lots, ROW
  -- slivers). Readers fall back to the parcel ID rather than rendering a blank label.
  address TEXT,
  neighborhood TEXT,       -- assessment neighbourhood, e.g. "Old City 2" / "Shaw"
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
-- Typeahead for /parcels/search (Stage D): trigram over the free-text keys, btree over
-- the low-cardinality neighbourhood used by the geography filter chips.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX parcels_address_trgm_idx ON parcels USING GIN (address gin_trgm_ops);
CREATE INDEX parcels_ssl_trgm_idx ON parcels USING GIN (ssl gin_trgm_ops);
CREATE INDEX parcels_neighborhood_idx ON parcels (neighborhood);

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
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {input_name: "local"|"submarket"|"national"}
                           -- per-value tags for what THIS row genuinely tailors (§2.8).
                           -- One `source` column cannot say that a ward's rent was
                           -- researched but its cap rate borrowed from a comparable;
                           -- confidence needs to know, so the tags are stored, not parsed
                           -- back out of prose. Empty {} = plain national fallback.
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
  -- Stage D (v1.6): the rest of the SCREENING tier, persisted for the same reason as the
  -- two ranking columns above — `screening_rlv` already computes every one of these and
  -- then throws them away, and the table view needs to SORT on them. Deriving them on read
  -- would mean re-running the engine per visible page, which §9's "persisted, never derived
  -- on read" rule exists to prevent. All NULL when status <> 'scored'.
  -- NOT here: levered IRR. It does not exist in the screening tier at all (`Outputs.irr` is
  -- None until `full_cashflow` runs), so the table's Return column is filled on demand.
  noi DOUBLE PRECISION,                  -- stabilized NOI, annual
  total_development_cost DOUBLE PRECISION,   -- screening TDC (excludes land)
  yield_on_cost DOUBLE PRECISION,
  profit_margin DOUBLE PRECISION,
  exit_value DOUBLE PRECISION,
  gross_sf DOUBLE PRECISION,
  net_rentable_sf DOUBLE PRECISION,
  unit_count INTEGER,          -- REPORTING ONLY (§3.1 fix #3); never drives revenue
  floors INTEGER,
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
--
-- MIGRATION NOTE (Stage D, v1.6). The nine screening columns are likewise unbackfillable —
-- NOI, TDC, and the program shape were never persisted — so they are added empty and
-- repopulated by re-running the bake. Same retention behaviour as above.
--
--   ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS noi DOUBLE PRECISION;
--   ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS total_development_cost DOUBLE PRECISION;
--   ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS yield_on_cost DOUBLE PRECISION;
--   ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS profit_margin DOUBLE PRECISION;
--   ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS exit_value DOUBLE PRECISION;
--   ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS gross_sf DOUBLE PRECISION;
--   ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS net_rentable_sf DOUBLE PRECISION;
--   ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS unit_count INTEGER;
--   ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS floors INTEGER;

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

-- Stage D (v1.6). Shortlists are pure user state: named collections of parcels, with no
-- model output of their own. The 1f card metrics are read live from the latest bake for the
-- member SSLs, so a shortlist never goes stale against a re-bake and never freezes a number.
-- (Scenarios are the opposite by design — they DO freeze, via market_snapshot.)
CREATE TABLE shortlists (
  shortlist_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  user_id TEXT DEFAULT 'local',   -- matches scenarios; real auth later (SPEC §7.1)
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE shortlist_parcels (
  shortlist_id TEXT REFERENCES shortlists(shortlist_id) ON DELETE CASCADE,
  ssl TEXT REFERENCES parcels(ssl),
  added_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (shortlist_id, ssl)
);
CREATE INDEX shortlist_parcels_ssl_idx ON shortlist_parcels (ssl);
