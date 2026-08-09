"""FastAPI application (SPEC §10, Stage D).

Two tiers, and the split is the product's central honesty claim:

  * the BAKED screening layer — fast, all 132,632 parcels, powers map color, filtering,
    and the table. Every endpoint that touches it reads `bake_results` and never runs the
    engine.
  * the FULL model — levered, monthly, IRR-solved, one parcel at a time. It runs in
    exactly one place, `api/underwrite.py`, reached only from `/parcel/{id}/underwrite`.

The two produce different RLVs for the same parcel and that is expected (SPEC §11). The
API ships both numbers side by side so the UI can label the difference rather than hide it.

Run: `uvicorn api.main:app --reload`
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from api.routers import (
    assumptions,
    map as map_router,
    meta,
    parcels,
    scenarios,
    shortlists,
    underwrite as underwrite_router,
)
from api.settings import settings
from data.repositories import database_url


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A pool rather than a connection per request: the underwrite path is CPU-bound and
    # FastAPI runs sync endpoints in a threadpool, so several requests really are in
    # flight at once.
    app.state.pool = ConnectionPool(
        conninfo=database_url(),
        min_size=1,
        max_size=int(os.environ.get("DB_POOL_MAX", "10")),
        kwargs={"row_factory": dict_row},
        open=True,
    )
    try:
        yield
    finally:
        app.state.pool.close()


app = FastAPI(
    title="Residual — parcel feasibility API",
    version="1.6.0",
    summary="Per-parcel development feasibility for Washington DC.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(map_router.router)
# The underwrite router mounts BEFORE the parcel router: both match
# `/parcel/{parcel_id:path}`, and a path converter is greedy, so `/parcel/X/underwrite`
# would otherwise be swallowed by the record route with parcel_id="X/underwrite".
app.include_router(underwrite_router.router)
app.include_router(parcels.router)
app.include_router(assumptions.router)
app.include_router(scenarios.router)
app.include_router(shortlists.router)

# Static PMTiles (SPEC §10: regenerated once per bake, served from flat storage, no live
# tile server). Mounted only when the directory exists so the API still boots before the
# first tile build.
if os.path.isdir(settings.tiles_dir):
    app.mount(
        settings.tiles_url_prefix,
        StaticFiles(directory=settings.tiles_dir),
        name="tiles",
    )


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness only — deliberately does not touch the database or the bake."""
    return {"status": "ok"}
