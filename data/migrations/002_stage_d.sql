-- Stage D migration (v1.6) — brings a pre-Stage-D database up to `schema.sql`.
--
-- Idempotent: every statement is IF NOT EXISTS / guarded, so re-running is a no-op.
-- Apply with:  psql "$DATABASE_URL" -f data/migrations/002_stage_d.sql
--
-- Three groups:
--   1. the nine screening columns on bake_results  (schema.sql migration note, v1.6)
--   2. shortlists + shortlist_parcels              (new tables, pure user state)
--   3. parcels.address / parcels.neighborhood      (Stage D: the UI is address-forward)
--
-- Groups 1 and 3 are NOT backfillable from existing rows and are repopulated by
-- re-running the loaders/bake. See the notes on each.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. bake_results — the rest of the screening tier (SPEC §9 "persisted, never
--    derived on read"). Unbackfillable: screening_rlv computed each of these and
--    discarded it, and the program shape was never stored. Added empty, then
--    repopulated by `python -m bake.run_bake`, which appends a fresh batch.
-- ---------------------------------------------------------------------------
ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS noi DOUBLE PRECISION;
ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS total_development_cost DOUBLE PRECISION;
ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS yield_on_cost DOUBLE PRECISION;
ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS profit_margin DOUBLE PRECISION;
ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS exit_value DOUBLE PRECISION;
ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS gross_sf DOUBLE PRECISION;
ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS net_rentable_sf DOUBLE PRECISION;
ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS unit_count INTEGER;
ALTER TABLE bake_results ADD COLUMN IF NOT EXISTS floors INTEGER;

-- ---------------------------------------------------------------------------
-- 2. Shortlists. Pure user state: named collections of parcels with no model
--    output of their own. The 1f card metrics are read live from the latest bake
--    for the member SSLs, so a shortlist never goes stale against a re-bake.
--    (Scenarios are the opposite by design — they freeze, via market_snapshot.)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shortlists (
  shortlist_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  user_id TEXT DEFAULT 'local',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS shortlist_parcels (
  shortlist_id TEXT REFERENCES shortlists(shortlist_id) ON DELETE CASCADE,
  ssl TEXT REFERENCES parcels(ssl),
  added_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (shortlist_id, ssl)
);
CREATE INDEX IF NOT EXISTS shortlist_parcels_ssl_idx ON shortlist_parcels (ssl);

-- ---------------------------------------------------------------------------
-- 3. parcels.address / parcels.neighborhood (Stage D).
--    Six of the seven handoff screens lead with a street address, and the search
--    field accepts "address · parcel ID · ward". Both fields already ride on the
--    Common Ownership Layer we load (PREMISEADD, NBHDNAME/SUBNBHD) — no new
--    dataset and no new spatial join. Added empty, then populated by
--    `python -m data.loaders.dc_addresses`.
--
--    Both are NULLABLE on purpose: not every SSL carries a premise address (vacant
--    interior lots, ROW slivers). The API falls back to the parcel ID, so a missing
--    address degrades the label rather than blanking the screen.
-- ---------------------------------------------------------------------------
ALTER TABLE parcels ADD COLUMN IF NOT EXISTS address TEXT;
ALTER TABLE parcels ADD COLUMN IF NOT EXISTS neighborhood TEXT;

-- Typeahead support for /parcels/search. trigram over the address, plain btree over
-- the neighborhood (which is a small, low-cardinality set used for the geography chips).
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS parcels_address_trgm_idx ON parcels USING GIN (address gin_trgm_ops);
CREATE INDEX IF NOT EXISTS parcels_neighborhood_idx ON parcels (neighborhood);
CREATE INDEX IF NOT EXISTS parcels_ssl_trgm_idx ON parcels USING GIN (ssl gin_trgm_ops);

COMMIT;
