# Deploying Residual

Live: **https://residual-six.vercel.app** (`residual.vercel.app` belongs to someone else, so
Vercel assigned the next free name.)

One Vercel project, two services, one Neon database:

| Piece | Where | Why |
|---|---|---|
| React frontend | Vercel service `web`, root `web/` | Static bundle. This is what Vercel is for. |
| `parcels-*.pmtiles` (33 MB) | The same service, as a static file | PMTiles reads by HTTP range request; a CDN is the right thing in front of it. Shipped in `web/public/tiles/`. |
| FastAPI | Vercel service `api`, root `./` | A Python Function. Fluid compute allows 300s and 2 GB on Hobby, so the underwrite path and the 2000-parcel IRR filter both fit. |
| PostGIS | Neon, via the Vercel Marketplace | `/map/query` is an `ST_Intersects` over 132k geometries behind a GiST index. That needs real Postgres, which a function is not. |

**Both services share one origin**, and that is the point. Two projects would mean two
domains, which would in turn mean CORS, a build-time `VITE_API_BASE`, and an absolute
`TILES_BASE_URL`. Under one origin the frontend calls `/meta` and `/map/query` as relative
paths — exactly what it does against the Vite dev proxy — and none of that configuration
exists. `web/src/lib/config.ts` still supports a split origin; it just is not needed here.

`render.yaml` and `Dockerfile` are kept for the container route (Render, Koyeb, Fly). They
are not used by the path below.

---

## Routing

The root `vercel.json` declares both services and the route table. Requests are matched in
order: every prefix the API owns is listed explicitly, and everything else falls through to
the frontend.

The API prefixes are the same list as the Vite dev proxy in `web/vite.config.ts`, and they
have to stay in step — a route missing here returns `index.html` instead of JSON, which
fails as `unexpected token '<'` rather than as a missing route.

`/tiles/` is deliberately **not** routed to the API. The tileset ships with the frontend,
so it is served as a static file by the `web` service.

---

## Setting it up from scratch

### 1. Project and database

```bash
vercel link --yes --project residual
vercel integration add neon
```

The Marketplace install provisions the database and injects `DATABASE_URL` (pooled) and
`DATABASE_URL_UNPOOLED` (direct) into the project. It requires accepting Neon's terms in a
browser once — the CLI prints the URL and will not proceed until that is done.

Enable PostGIS, then move the data. `spatial_ref_sys` is excluded because `CREATE EXTENSION`
already created it and restoring over it conflicts. Use the **unpooled** URL for both:
pgbouncer and a parallel restore disagree.

```bash
psql "$DATABASE_URL_UNPOOLED" -c "CREATE EXTENSION IF NOT EXISTS postgis;"

pg_dump "$DATABASE_URL" -Fc --no-owner --no-privileges \
  -T spatial_ref_sys -f residual.dump          # local bake → ~36 MB compressed

pg_restore -d "$DATABASE_URL_UNPOOLED" --no-owner --no-privileges -j 4 residual.dump
```

Sanity check — these are the numbers the map is drawn from:

```bash
psql "$DATABASE_URL_UNPOOLED" -c "SELECT count(*) FROM parcels;"        # 132,632
psql "$DATABASE_URL_UNPOOLED" -c "SELECT count(*) FROM bake_results;"   # 272,008
psql "$DATABASE_URL_UNPOOLED" -c "\di parcels_geom_gix"                 # the GiST index must exist
```

If the index is missing the map query still returns correct answers, just slowly enough to
look broken — it is a sequential scan over every geometry on each keystroke.

### 2. Environment

```
DB_POOL_MIN    = 0        # serverless: do not idle a connection open per instance
TILES_BASE_URL = /tiles   # see below — this one is not optional
```

`TILES_BASE_URL` looks redundant under one origin but is required. Without it, `/meta`
resolves the tileset by calling `os.path.isfile` against the function's own disk, and the
tileset is not there — it ships with the frontend and is excluded from the function bundle.
`/meta` would then report `tileset_url: null`, which the client honours by drawing no map
at all, silently and by design.

### 3. Deploy

```bash
vercel deploy --prod
```

Both services build from the one command: Vite for `web`, uv for `api`.

---

## Checking it actually works

```bash
curl -s https://residual-six.vercel.app/meta | jq '{parcel_count, tileset_url}'
```

`parcel_count` should be 132632, and fetching `tileset_url` should give a **206** with
`content-type: application/octet-stream`. Then open the site: the map paints DC, clicking a
parcel opens the popup, and "Full underwriting" runs the levered model live.

## Things that will bite

- **Dependencies come from `[project] dependencies`.** Vercel installs that list and does
  not resolve extras. A `requirements.txt` sitting beside `pyproject.toml` is ignored
  outright. Anything the API imports at runtime belongs in the base list or the function
  dies on its first request with `ModuleNotFoundError`, having built perfectly.
- **The tileset name is UTC.** `computed_at` is a `timestamptz`, so it renders in the
  connection's timezone — `America/Los_Angeles` here, `GMT` on Neon. Both `/meta` and
  `tiles/build_tiles.py` normalise with `.astimezone(timezone.utc)` before formatting. If
  they ever diverge, the map requests a tileset that was never built and draws nothing,
  without an error, because a missing tileset is a state `/meta` reports rather than raises.
- **Two cold starts, not one.** The function cold-starts, and Neon's free tier suspends
  compute after five minutes idle. The first request after a quiet spell pays both, and
  `/meta` is the first thing the app calls, so the app looks hung rather than slow.
- **Storage.** The restored database is **144 MB**, not the 293 MB it occupies locally — a
  fresh restore carries no dead-tuple bloat. That is comfortable inside Neon's 0.5 GB free
  tier, but a re-bake writes new rows before the old ones are vacuumed, so check headroom
  before running one against Neon rather than after.
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
- **Debugging the map in a headless browser is misleading.** MapLibre defers its style load
  to `requestAnimationFrame`, which never fires in a hidden tab, so the map stays blank with
  no error, no tile requests, and a correctly sized canvas. That is not a deployment fault.
  Check `document.visibilityState` before believing it.
