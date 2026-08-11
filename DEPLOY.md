# Deploying Residual

The app is three things, and they do not want the same host:

| Piece | Where | Why |
|---|---|---|
| React frontend | Vercel | Static bundle. This is what Vercel is for. |
| `parcels-*.pmtiles` (33 MB) | Vercel, as a static file | PMTiles reads by HTTP range request; a CDN is the right thing in front of it. Shipped in `web/public/tiles/`. |
| FastAPI + PostGIS | Render (or Railway / Fly) | `/map/query` is an `ST_Intersects` over 132k geometries behind a GiST index, and the bake writes 136k rows in one transaction. That needs a real Postgres and a process that can hold a connection. |

Nothing about the interface changes. `VITE_API_BASE` is empty in development, so the Vite
proxy keeps working exactly as it does today.

---

## Order matters

Each host needs the other's domain, so deploy in this order and expect to touch Render
twice.

### 1. Database

Create the Postgres instance first — it takes longest and the API will not boot without it.

```bash
# On the new database, once:
psql "$REMOTE_DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

Then move the data. `spatial_ref_sys` is excluded because `CREATE EXTENSION` above already
created it, and restoring over it conflicts:

```bash
# From this machine, against your local bake (~293 MB, compresses to roughly half):
pg_dump "$DATABASE_URL" -Fc --no-owner --no-privileges \
  -T spatial_ref_sys -f residual.dump

pg_restore -d "$REMOTE_DATABASE_URL" --no-owner --no-privileges -j 4 residual.dump
```

Sanity check before moving on — these are the numbers the map is drawn from:

```bash
psql "$REMOTE_DATABASE_URL" -c "SELECT count(*) FROM parcels;"        # 132,632
psql "$REMOTE_DATABASE_URL" -c "SELECT count(*) FROM bake_results;"   # 272,008
psql "$REMOTE_DATABASE_URL" -c "\di parcels_geom_gix"                 # the GiST index must exist
```

If the index is missing the map query still returns correct answers, just slowly enough to
look broken — it is a sequential scan over every geometry on each keystroke.

### 2. API

`render.yaml` is a blueprint: point Render at this repo and it reads it. `DATABASE_URL` is
wired automatically; the other two are marked `sync: false` because they are not known yet.

Deploy once with them unset. Note the service URL — `https://residual-api.onrender.com` or
similar.

### 3. Frontend

Import the repo into Vercel. `vercel.json` already sets the build command, output
directory, the SPA rewrite (which excludes `/tiles/` so the tileset is served as a file),
and immutable caching on the tileset.

Set one environment variable:

```
VITE_API_BASE = https://residual-api.onrender.com
```

It is read at **build** time — Vite inlines it — so changing it later needs a redeploy, not
a restart. Deploy, and note the Vercel domain.

### 4. Back to Render

Now set the two that needed the Vercel domain, and redeploy:

```
CORS_ORIGINS   = https://residual.vercel.app
TILES_BASE_URL = https://residual.vercel.app/tiles
```

`CORS_ORIGINS` wrong shows up as a CORS error in the browser console with nothing in the
server logs. `TILES_BASE_URL` wrong shows up as a map that draws no parcels, with a
404 for the `.pmtiles` file in the network tab.

---

## Checking it actually works

```bash
curl -s https://residual-api.onrender.com/meta | jq '{parcel_count, tileset_url}'
```

`parcel_count` should be 132632 and `tileset_url` should be an absolute Vercel URL. Then
open the site: the map paints DC, clicking a parcel opens the popup, and "Full underwriting"
runs the levered model live.

## Things that will bite

- **Cold starts.** Render's free tier sleeps after inactivity. The first request wakes it —
  tens of seconds — and `/meta` is the first thing the app calls, so the app looks hung
  rather than slow. A paid instance or a keep-warm ping fixes it.
- **Re-baking.** The bake is not part of the deploy. Run it against the remote database
  (`DATABASE_URL=... python -m bake.run_bake`), then rebuild tiles locally
  (`python -m tiles.build_tiles`, needs tippecanoe), commit the new `.pmtiles` into
  `web/public/tiles/`, delete the old one, and push. `/meta` names the tileset by batch
  stamp, so the new filename and the new rows arrive together or not at all.
- **Repo size.** Each committed tileset is ~33 MB and git keeps it forever. Delete the
  previous one in the same commit that adds the next, and if this gets tiresome move the
  tiles to object storage — `TILES_BASE_URL` already points anywhere.
- **The database is the whole product.** 293 MB of baked results. Check the plan's storage
  ceiling before restoring; free tiers sit between 256 MB and 1 GB and some expire.
