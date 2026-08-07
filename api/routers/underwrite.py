"""/parcel/{parcel_id}/underwrite — the only place the full engine runs (SPEC §10).

GET runs the default assumptions, so opening the drill-down is a cacheable, linkable read.
POST carries assumption overrides, because the 1c modal edits ~30 nested fields and SPEC's
`?assumptions` query form cannot hold them.

An unmodellable parcel (exempt, historic, unencoded, no admissible prototype) returns 422
with a plain-language reason. Those are real answers ABOUT a parcel, not server faults,
and the panel renders the reason instead of the numbers.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from api import serializers as ser
from api.deps import current_batch, get_conn
from api.schemas import UnderwriteRequest, UnderwriteResponse
from api.underwrite import UnderwriteError, underwrite

router = APIRouter(tags=["underwrite"])


def _run(conn, parcel_id: str, batch: datetime, req: UnderwriteRequest) -> UnderwriteResponse:
    try:
        result = underwrite(
            conn,
            parcel_id,
            batch,
            prototype_id=req.prototype_id,
            overrides=req.overrides(),
            include_demolition=req.include_demolition,
        )
    except UnderwriteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UnderwriteResponse(**ser.underwrite_response(result))


@router.get("/parcel/{parcel_id:path}/underwrite", response_model=UnderwriteResponse)
def get_underwrite(
    parcel_id: str,
    prototype_id: str | None = None,
    include_demolition: bool | None = None,
    conn=Depends(get_conn),
    batch: datetime = Depends(current_batch),
) -> UnderwriteResponse:
    """Default-assumption underwrite. Cached, so reopening a parcel is free."""
    return _run(
        conn,
        parcel_id,
        batch,
        UnderwriteRequest(prototype_id=prototype_id, include_demolition=include_demolition),
    )


@router.post("/parcel/{parcel_id:path}/underwrite", response_model=UnderwriteResponse)
def post_underwrite(
    parcel_id: str,
    req: UnderwriteRequest,
    conn=Depends(get_conn),
    batch: datetime = Depends(current_batch),
) -> UnderwriteResponse:
    """Re-underwrite with edited inputs (1c -> 1b)."""
    return _run(conn, parcel_id, batch, req)
