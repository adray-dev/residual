"""/map/query — the table and compare read (SPEC §10).

Reads precomputed `bake_results` and NEVER runs the engine. That is the entire reason the
bake exists: the map and table must stay fast across 132,632 parcels, and the full model
only ever runs one parcel at a time in `/parcel/{id}/underwrite`.

The one exception is the IRR filter, which is called out explicitly below.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from api import serializers as ser
from api.deps import current_batch, get_conn
from api.schemas import Bounds, MapFilters, MapQueryRequest, MapQueryResponse
from api.settings import settings
from api.underwrite import irr_for_row
from data import repositories as repo

router = APIRouter(prefix="/map", tags=["map"])


def _run(
    conn, batch: datetime, req: MapQueryRequest, with_returns: bool = False
) -> MapQueryResponse:
    limit = min(req.limit, settings.max_page_size)
    sort_key = req.sort_key or req.objective

    filters = req.filters.model_dump()
    irr_min = filters.pop("irr_min", None)

    # Ranking by IRR means scoring every matching row, not just the page: levered IRR is
    # absent from the bake (SPEC §9), so there is no column to ORDER BY. It reuses the
    # return filter's path and its bound for exactly that reason — sorting a page and
    # calling it a ranking is the thing a table must never do.
    sort_by_irr = sort_key == repo.IRR_SORT_KEY

    rows, total = repo.map_query(
        conn,
        computed_at=batch,
        bounds=req.bounds.as_tuple() if req.bounds else None,
        filters=filters,
        # IRR has no column; the fallback sort keeps the page deterministic while the
        # scored-and-sorted set is assembled below.
        sort_key=sort_key,
        sort_dir=req.sort_dir,
        limit=limit,
        offset=req.offset,
    )

    # --- ranking by IRR ------------------------------------------------------
    if sort_by_irr and irr_min is None:
        if total > settings.max_irr_filter_parcels:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Sorting by IRR runs the full underwriting model on every matching "
                    f"parcel, and {total:,} is too many (limit "
                    f"{settings.max_irr_filter_parcels:,}). Narrow the filters first."
                ),
            )
        all_rows, _ = repo.map_query(
            conn,
            computed_at=batch,
            bounds=req.bounds.as_tuple() if req.bounds else None,
            filters=filters,
            sort_key=repo.DEFAULT_MAP_OBJECTIVE,
            sort_dir="desc",
            limit=settings.max_irr_filter_parcels,
            offset=0,
        )
        scored_rows = [(row, irr_for_row(conn, row, batch)) for row in all_rows]
        # A parcel with no assessed value has no IRR. It sorts to the BOTTOM in both
        # directions — it is an absence, not a very small or very large number, and
        # treating it as either would rank it against parcels that have an answer.
        reverse = str(req.sort_dir).lower() != "asc"
        scored_rows.sort(
            key=lambda pair: (pair[1] is None, -(pair[1] or 0.0) if reverse else (pair[1] or 0.0))
        )
        page = scored_rows[req.offset : req.offset + limit]
        return MapQueryResponse(
            computed_at=batch,
            total=total,
            returned=len(page),
            offset=req.offset,
            objective=req.objective,
            sort_key=sort_key,
            sort_dir=req.sort_dir,
            rows=[ser.parcel_row(r, irr=v) for r, v in page],
            irr_filter_applied=False,
        )

    # --- the IRR filter -----------------------------------------------------
    # Levered IRR does not exist in the screening tier (SPEC §9 excludes it from the bake
    # on purpose), so filtering by it means running the full model per parcel — ~20ms each.
    # Across the whole scored set that is ~26 minutes, which is a batch job, not a request.
    # So it applies to the ALREADY-NARROWED set and refuses above a bounded size: narrow
    # with the other filters first, then filter by return.
    irr_applied = False
    if irr_min is not None:
        if total > settings.max_irr_filter_parcels:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Filtering by annual return runs the full underwriting model on every "
                    f"matching parcel, and {total:,} is too many (limit "
                    f"{settings.max_irr_filter_parcels:,}). Narrow the area or the other "
                    f"filters first, then filter by return."
                ),
            )
        # Re-read the whole matching set, not just this page: an IRR filter that only
        # considered the visible page would silently report a wrong `total`.
        all_rows, _ = repo.map_query(
            conn,
            computed_at=batch,
            bounds=req.bounds.as_tuple() if req.bounds else None,
            filters=filters,
            sort_key=sort_key,
            sort_dir=req.sort_dir,
            limit=settings.max_irr_filter_parcels,
            offset=0,
        )
        kept = []
        for row in all_rows:
            irr = irr_for_row(conn, row, batch)
            if irr is not None and irr >= irr_min:
                kept.append((row, irr))
        if sort_by_irr:
            kept.sort(key=lambda pair: pair[1], reverse=str(req.sort_dir).lower() != "asc")
        total = len(kept)
        page = kept[req.offset : req.offset + limit]
        irr_applied = True
        return MapQueryResponse(
            computed_at=batch,
            total=total,
            returned=len(page),
            offset=req.offset,
            objective=req.objective,
            sort_key=sort_key,
            sort_dir=req.sort_dir,
            rows=[ser.parcel_row(r, irr=v) for r, v in page],
            irr_filter_applied=True,
        )

    # --- the table's Return column ------------------------------------------
    # Levered IRR is absent from the bake (SPEC §9), so a table that shows it has to run
    # the full model. Scoped to the VISIBLE PAGE, which is tens of rows: the filter above
    # scores the whole matching set and is bounded far higher for that reason.
    page_returns: dict[str, float | None] = {}
    if with_returns:
        if len(rows) > settings.max_returns_per_page:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Returns are computed per row and this page holds {len(rows):,} "
                    f"(limit {settings.max_returns_per_page:,}). Ask for a smaller page."
                ),
            )
        for row in rows:
            if row["status"] == "scored":
                page_returns[row["ssl"]] = irr_for_row(conn, row, batch)

    return MapQueryResponse(
        computed_at=batch,
        total=total,
        returned=len(rows),
        offset=req.offset,
        objective=req.objective,
        sort_key=sort_key,
        sort_dir=req.sort_dir,
        rows=[ser.parcel_row(r, irr=page_returns.get(r["ssl"])) for r in rows],
        irr_filter_applied=irr_applied,
    )


@router.post("/query", response_model=MapQueryResponse)
def post_map_query(
    req: MapQueryRequest,
    with_returns: bool = False,
    conn=Depends(get_conn),
    batch: datetime = Depends(current_batch),
) -> MapQueryResponse:
    """Body form. Required for the draw-an-area polygon, which will not fit in a URL."""
    return _run(conn, batch, req, with_returns)


@router.get("/query", response_model=MapQueryResponse)
def get_map_query(
    conn=Depends(get_conn),
    batch: datetime = Depends(current_batch),
    min_lon: float | None = None,
    min_lat: float | None = None,
    max_lon: float | None = None,
    max_lat: float | None = None,
    wards: list[str] = Query(default=[]),
    neighborhoods: list[str] = Query(default=[]),
    statuses: list[str] = Query(default=[]),
    prototypes: list[str] = Query(default=[]),
    rlv_min: float | None = None,
    rlv_max: float | None = None,
    irr_min: float | None = None,
    min_confidence: float | None = None,
    units_min: int | None = None,
    units_max: int | None = None,
    floors_min: int | None = None,
    floors_max: int | None = None,
    building_sf_min: float | None = None,
    building_sf_max: float | None = None,
    vacant_only: bool = False,
    objective: str = repo.DEFAULT_MAP_OBJECTIVE,
    sort_key: str | None = None,
    sort_dir: str = "desc",
    limit: int = 200,
    offset: int = 0,
    with_returns: bool = False,
) -> MapQueryResponse:
    """Query-string form, per SPEC §10's `GET /map/query?bounds&filters`."""
    bounds = None
    corners = (min_lon, min_lat, max_lon, max_lat)
    if any(c is not None for c in corners):
        if any(c is None for c in corners):
            raise HTTPException(
                status_code=422,
                detail="bounds needs all four of min_lon, min_lat, max_lon, max_lat",
            )
        bounds = Bounds(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat)

    req = MapQueryRequest(
        bounds=bounds,
        filters=MapFilters(
            wards=wards,
            neighborhoods=neighborhoods,
            statuses=statuses,
            prototypes=prototypes,
            rlv_min=rlv_min,
            rlv_max=rlv_max,
            irr_min=irr_min,
            min_confidence=min_confidence,
            units_min=units_min,
            units_max=units_max,
            floors_min=floors_min,
            floors_max=floors_max,
            building_sf_min=building_sf_min,
            building_sf_max=building_sf_max,
            vacant_only=vacant_only,
        ),
        objective=objective,
        sort_key=sort_key,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
    return _run(conn, batch, req, with_returns)
