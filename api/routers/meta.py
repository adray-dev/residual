"""GET /meta — the client's boot payload.

This endpoint exists to solve one specific problem. The map reads static PMTiles and the
table reads `bake_results`; if those two resolve the latest bake independently, a bake that
commits between them leaves the map showing one batch and the table another. So /meta
resolves the batch ONCE and names the tileset built from that same batch. Everything the
client does afterwards is pinned to what it read here.
"""
from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, Depends

from api import serializers as ser
from api.deps import current_batch, get_conn
from api.schemas import Limits, MetaResponse, ObjectiveRamp, Submarket
from api.settings import settings
from data import repositories as repo

router = APIRouter(tags=["meta"])


def tileset_for(batch: datetime) -> tuple[str | None, bool]:
    """The PMTiles built from THIS batch, or None if tiles have not been built for it.

    Named by batch timestamp so the URL changes when the data does — the client can cache
    a tileset forever, and a stale tileset can never be silently paired with fresh rows.
    Returning None (rather than a stale file) is deliberate: better a map that says it has
    no tiles than one quietly drawn from the previous bake.
    """
    stamp = batch.strftime("%Y%m%dT%H%M%S")
    filename = f"parcels-{stamp}.pmtiles"
    exists = os.path.isfile(os.path.join(settings.tiles_dir, filename))
    if not exists:
        return None, False
    return f"{settings.tiles_url_prefix}/{filename}", True


@router.get("/meta", response_model=MetaResponse)
def get_meta(conn=Depends(get_conn), batch: datetime = Depends(current_batch)) -> MetaResponse:
    tileset_url, tileset_available = tileset_for(batch)
    status_counts = repo.bake_status_counts(conn, batch)

    ramps = {
        objective: ObjectiveRamp(**repo.objective_ramp(conn, objective, batch))
        for objective in repo.MAP_OBJECTIVES
    }

    return MetaResponse(
        computed_at=batch,
        tileset_url=tileset_url,
        tileset_available=tileset_available,
        parcel_count=sum(status_counts.values()),
        status_counts=status_counts,
        objectives=list(repo.MAP_OBJECTIVES),
        default_objective=repo.DEFAULT_MAP_OBJECTIVE,
        ramps=ramps,
        submarkets=[
            Submarket(submarket_id=s["submarket_id"], name=s["name"])
            for s in repo.list_submarkets(conn)
        ],
        neighborhoods=repo.list_neighborhoods(conn),
        labels=ser.labels_block(),
        limits=Limits(
            max_page_size=settings.max_page_size,
            max_irr_filter_parcels=settings.max_irr_filter_parcels,
        ),
    )
