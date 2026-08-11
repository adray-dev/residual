# Deploying Residual

The app is three things, and they do not want the same host:

| Piece | Where | Why |
|---|---|---|
| React frontend | Vercel project `residual` (root `web/`) | Static bundle. This is what Vercel is for. |
| `parcels-*.pmtiles` (33 MB) | The same project, as a static file | PMTiles reads by HTTP range request; a CDN is the right thing in front of it. Shipped in `web/public/tiles/`. |
| FastAPI | Vercel project `residual-api` (repo root) | A Python Function. Fluid compute allows 300s and 2 GB, so the underwrite path and the bounded IRR filter both fit comfortably. |
| PostGIS | Neon | `/map/query` is an `ST_Intersects` over 132k geometries behind a GiST index. That needs real Postgres, which a function is not. |

Two Vercel projects rather than one, from the same repository: they have different roots,
different runtimes, and different build commands. That means two origins, which is what
`VITE_API_BASE` and `CORS_ORIGINS` exist to bridge. Nothing about the interface changes —
`VITE_API_BASE` is empty in development, so the Vite proxy keeps working as it does today.

`render.yaml` and `Dockerfile` are kept for the container route (Render, Koyeb, Fly). They
are not used by the Vercel path below.

---

## Order matters

Each host needs the other's domain, so deploy in this order and expect to touch the API
project twice.

### 1. Database (Neon)

Create a project at [neon.tech](https://neon.tech) — the free tier is 0.5 GB, and the bake
measures 293 MB, so it fits with room that is real but not generous. Enable PostGIS once:

```bash
psql "$REMOTE_DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

Then move the data. `spatial_ref_sys` is excluded because `CREATE EXTENSION` above already
created it, and restoring over it conflicts:

```bash
# From this machine, against your local bake (293 MB, ~36 MB as a compressed dump):
pg_dump "$DATABASE_URL" -Fc --no-owner --no-privileges \
  -T spatial_ref_sys -f residual.dump

pg_restore -d "$REMOTE_DATABASE_URL" --no-owner --no-privileges -j 4 residual.dump
```

Use Neon's **pooled** connection string (it has `-pooler` in the host) for the API, and the
direct one for `pg_restore` — pgbouncer and a parallel restore disagree.

Sanity check before moving on — these are the numbers the map is drawn from:

```bash
psql "$REMOTE_DATABASE_URL" -c "SELECT count(*) FROM parcels;"        # 132,632
psql "$REMOTE_DATABASE_URL" -c "SELECT count(*) FROM bake_results;"   # 272,008
psql "$REMOTE_DATABASE_URL" -c "\di parcels_geom_gix"                 # the GiST index must exist
```

If the index is missing the map query still returns correct answers, just slowly enough to
look broken — it is a sequential scan over every geometry on each keystroke.

### 2. API

A Vercel project with **root directory `.`** (the repo root), configured as a service in
the root `vercel.json`. `pyproject.toml` drives both halves of the build: `[tool.vercel]
entrypoint` names `api.main:app`, and `[project] dependencies` is the install list.

That install list is why the serving libraries are base dependencies rather than sitting
behind the `api` extra — Vercel installs `[project] dependencies` and does not resolve
extras. A `requirements.txt` does not help; pyproject takes precedence and the file is
ignored outright, which fails at runtime as `ModuleNotFoundError: No module named
'fastapi'` rather than at build time.

Environment variables — set the first now, the other two after step 3:

```
DATABASE_URL   = <Neon POOLED connection string>
DB_POOL_MIN    = 0     # serverless: do not idle a connection open per instance
```

Deploy, and note the domain — `https://residual-api.vercel.app` or similar.

### 3. Frontend

A second Vercel project on the same repository with **root directory `web`**. It reads
`web/vercel.json`, which sets the SPA rewrite (excluding `/tiles/` so the tileset is served
as a file) and immutable caching on the tileset. Vite is auto-detected.

Set one environment variable:

```
VITE_API_BASE = https://residual-api.vercel.app
```

It is read at **build** time — Vite inlines it — so changing it later needs a redeploy, not
a restart. Deploy, and note the domain.

### 4. Back to the API project

Now set the two that needed the frontend's domain, and redeploy:

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
curl -s https://residual-api.vercel.app/meta | jq '{parcel_count, tileset_url}'
```

`parcel_count` should be 132632 and `tileset_url` should be an absolute URL on the frontend
domain. Then open the site: the map paints DC, clicking a parcel opens the popup, and
"Full underwriting" runs the levered model live.

## Things that will bite

- **Two cold starts, not one.** The function cold-starts, and Neon's free tier suspends its
  compute after five minutes idle. The first request after a quiet spell pays both, and
  `/meta` is the first thing the app calls, so the app looks hung rather than slow.
- **Storage headroom.** 293 MB against Neon's 0.5 GB is 59% used. A re-bake writes new rows
  before the old ones are vacuumed, so check free space before running one against Neon
  rather than after.
- **Re-baking.** The bake is not part of the deploy. Run it against the remote database
  (`DATABASE_URL=... python -m bake.run_bake`), then rebuild tiles locally
  (`python -m tiles.build_tiles`, needs tippecanoe), commit the new `.pmtiles` into
  `web/public/tiles/`, delete the old one, and push. `/meta` names the tileset by batch
  stamp, so the new filename and the new rows arrive together or not at all.
- **Repo size.** Each committed tileset is ~33 MB and git keeps it forever. Delete the
  previous one in the same commit that adds the next, and if this gets tiresome move the
  tiles to object storage — `TILES_BASE_URL` already points anywhere.
- **Bundle size.** The function bundle is capped at 500 MB uncompressed and includes every
  file it can reach, with no tree-shaking. `excludeFiles` in `vercel.json` keeps `web/`,
  the tileset, and the tests out; if an import ever pulls `data/loaders/` into the API,
  that exclusion becomes a build failure rather than a silent bloat.
