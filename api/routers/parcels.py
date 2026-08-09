"""/parcel/{parcel_id} and /parcels/search.

The record read: everything the 1a popup and the 1b header / Zoning / Parcel-record tabs
need, straight from `parcels` and `bake_results`. The engine does not run here — the full
underwrite is a separate call, so opening a popup never pays for a model run.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from api import serializers as ser
from api import vocabulary as vocab
from api.schemas import ParcelResponse
from api.deps import current_batch, get_conn
from data import repositories as repo

router = APIRouter(tags=["parcels"])

NONE_PROTOTYPE = repo.NONE_PROTOTYPE


@router.get("/parcels/search")
def search(q: str = "", limit: int = 10, conn=Depends(get_conn)) -> dict:
    """Typeahead: address · parcel ID · ward · neighbourhood (the handoff's hint text)."""
    hits = repo.search_parcels(conn, q, min(limit, 25))
    return {
        "query": q,
        "results": [
            {
                "parcel_id": h["ssl"],
                "address": h["address"],
                "neighborhood": h["neighborhood"],
                "ward": ser.ward_name(h["submarket_id"]),
                "display_name": ser.display_name(h["address"], h["ssl"]),
                "status": h["status"],
                # Centroid, so picking a result can move the map to the parcel. Without it
                # search could only open a panel, which is not what a map search means.
                "lon": h["lon"],
                "lat": h["lat"],
            }
            for h in hits
        ],
    }


@router.get("/parcel/{parcel_id:path}", response_model=ParcelResponse)
def get_parcel(
    parcel_id: str,
    conn=Depends(get_conn),
    batch: datetime = Depends(current_batch),
) -> ParcelResponse:
    """One parcel's record, zoning, and every prototype's screening result.

    `{parcel_id:path}` because DC SSLs contain spaces ("0546    0819"); a plain path
    segment would be mangled by the internal whitespace.
    """
    record = repo.get_parcel_record(conn, parcel_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No parcel with ID {parcel_id}.")

    rows = repo.bake_rows_for_ssl(conn, parcel_id, batch)
    if not rows:
        # Every parcel gets a bake row (SPEC §9, fix #5). None means this parcel loaded
        # after the last bake — real, and honest to say so rather than inventing a status.
        raise HTTPException(
            status_code=409,
            detail=(
                f"Parcel {parcel_id} has no results in the current bake "
                f"({batch.isoformat()}). It was probably loaded after the last bake ran."
            ),
        )

    status = rows[0]["status"]
    scored = [r for r in rows if r["status"] == "scored"]
    best = next((r for r in rows if r.get("is_best")), rows[0])

    rules = repo.get_rules(conn, record["zone_code"])

    # Prototype results, best first, then by feasibility value — the handoff's "Try
    # another prototype" list and SPEC §9's "surface the top 2-3".
    prototypes = sorted(
        (ser.prototype_result(r) for r in scored),
        key=lambda p: (not p.is_best, -(p.screening_rlv or float("-inf"))),
    )

    return ParcelResponse(
        computed_at=batch,
        parcel_id=parcel_id,
        address=record["address"],
        neighborhood=record["neighborhood"],
        display_name=ser.display_name(record["address"], parcel_id),
        ward=ser.ward_name(record["submarket_id"]),
        lot_area_sf=record["lot_area_sf"],
        land_value=record["land_value"],
        improvement_value=record["improvement_value"],
        improvement_ratio=record["improvement_ratio"],
        land_use_code=record["land_use_code"],
        is_exempt=bool(record["is_exempt"]),
        is_historic=bool(record["is_historic"]),
        status=status,
        status_label=vocab.STATUS_LABELS.get(status, status),
        developability=ser.developability(record["existing_building_sf"]),
        zoning=ser.zoning_info(record["zone_code"], rules),
        prototypes=prototypes,
        best_prototype_id=(
            best["prototype_id"] if best["prototype_id"] != NONE_PROTOTYPE else None
        ),
        confidence=best.get("confidence"),
    )
