"""Shortlists — screen 1f (SPEC §7.1, Stage D).

A shortlist holds parcel ids and nothing else. Its card metrics are read LIVE from the
latest bake every time it is opened, so a list can never go stale against a re-bake and
never freezes a number. Scenarios are deliberately the opposite: they freeze at save.

The one number that is not a straight bake read is the annual return. Levered IRR does not
exist in the screening tier (SPEC §9 keeps it out of the bake), so it is computed per member
through the same `irr_for_row` path the map's return filter uses — bounded here by the fact
that a shortlist is tens of parcels, not the whole city.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from statistics import median

from fastapi import APIRouter, Depends, HTTPException

from api import serializers as ser
from api.deps import current_batch, get_conn
from api.schemas import (
    ShortlistCreate,
    ShortlistDetail,
    ShortlistSummary,
    ShortlistTotals,
)
from api.settings import settings
from api.underwrite import irr_for_row
from data import repositories as repo

router = APIRouter(prefix="/shortlists", tags=["shortlists"])


@router.get("", response_model=list[ShortlistSummary])
def get_shortlists(conn=Depends(get_conn)) -> list[ShortlistSummary]:
    return [
        ShortlistSummary(
            shortlist_id=row["shortlist_id"],
            name=row["name"],
            parcel_count=row["parcel_count"],
            created_at=row["created_at"],
        )
        for row in repo.list_shortlists(conn)
    ]


@router.post("", response_model=ShortlistSummary, status_code=201)
def post_shortlist(req: ShortlistCreate, conn=Depends(get_conn)) -> ShortlistSummary:
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="A list needs a name.")
    shortlist_id = uuid.uuid4().hex
    repo.create_shortlist(conn, shortlist_id, name)
    conn.commit()
    return ShortlistSummary(
        shortlist_id=shortlist_id, name=name, parcel_count=0, created_at=datetime.now().astimezone()
    )


@router.delete("/{shortlist_id}", status_code=204)
def delete_shortlist(shortlist_id: str, conn=Depends(get_conn)) -> None:
    if not repo.delete_shortlist(conn, shortlist_id):
        raise HTTPException(status_code=404, detail="No such list.")
    conn.commit()


@router.post("/{shortlist_id}/parcels/{parcel_id:path}", status_code=204)
def add_parcel(shortlist_id: str, parcel_id: str, conn=Depends(get_conn)) -> None:
    if repo.get_shortlist(conn, shortlist_id) is None:
        raise HTTPException(status_code=404, detail="No such list.")
    if repo.get_parcel_record(conn, parcel_id) is None:
        raise HTTPException(status_code=404, detail=f"No parcel with ID {parcel_id}.")
    repo.add_to_shortlist(conn, shortlist_id, parcel_id)
    conn.commit()


@router.delete("/{shortlist_id}/parcels/{parcel_id:path}", status_code=204)
def remove_parcel(shortlist_id: str, parcel_id: str, conn=Depends(get_conn)) -> None:
    repo.remove_from_shortlist(conn, shortlist_id, parcel_id)
    conn.commit()


@router.get("/{shortlist_id}", response_model=ShortlistDetail)
def get_shortlist(
    shortlist_id: str,
    with_returns: bool = True,
    conn=Depends(get_conn),
    batch: datetime = Depends(current_batch),
) -> ShortlistDetail:
    """One list, with every member's CURRENT numbers.

    `with_returns` runs the full model per member for the annual return. It is on by default
    because the 1f card shows a return and the list totals report a median of them, and it
    refuses above the same bound the map's return filter uses rather than fanning out.
    """
    record = repo.get_shortlist(conn, shortlist_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No such list.")

    members = repo.shortlist_members(conn, shortlist_id, batch)
    if with_returns and len(members) > settings.max_irr_filter_parcels:
        raise HTTPException(
            status_code=422,
            detail=(
                f"This list holds {len(members):,} parcels, and reporting a return runs the "
                f"full model on each one (limit {settings.max_irr_filter_parcels:,})."
            ),
        )

    irrs = {}
    if with_returns:
        for row in members:
            if row["status"] == "scored":
                irrs[row["ssl"]] = irr_for_row(conn, row, batch)

    rows = [ser.parcel_row(row, irr=irrs.get(row["ssl"])) for row in members]
    scored = [row for row in members if row["status"] == "scored"]
    returns = [v for v in irrs.values() if v is not None]

    return ShortlistDetail(
        shortlist_id=shortlist_id,
        name=record["name"],
        created_at=record["created_at"],
        computed_at=batch,
        parcels=rows,
        added_at={row["ssl"]: row["added_at"] for row in members},
        totals=ShortlistTotals(
            parcel_count=len(members),
            scored_count=len(scored),
            combined_value=sum(row["rlv_total"] or 0.0 for row in scored),
            combined_floor_area=sum(row["gross_sf"] or 0.0 for row in scored),
            # Median, not mean: one -$80M outlier in a shortlist of ten would make an
            # average say nothing about the list.
            median_return=median(returns) if returns else None,
        ),
    )
