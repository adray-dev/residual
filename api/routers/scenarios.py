"""POST /scenario, GET /scenario/{id}, GET /scenario/{id}/export (SPEC §10).

Saving re-runs the underwrite server-side from the parcel and the inputs, rather than
accepting numbers from the client. A scenario is a record of what the model said; letting
the caller post its own figures would make it a record of what the client claimed.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from api import scenarios as svc
from api.deps import current_batch, get_conn
from api.schemas import ScenarioRef, ScenarioSaveRequest, ScenarioSummary
from api.underwrite import UnderwriteError, underwrite
from data import repositories as repo

router = APIRouter(tags=["scenarios"])


@router.post("/scenario", response_model=ScenarioRef, status_code=201)
def post_scenario(
    req: ScenarioSaveRequest,
    conn=Depends(get_conn),
    batch: datetime = Depends(current_batch),
) -> ScenarioRef:
    """Freeze the current underwrite of one parcel."""
    try:
        result = underwrite(
            conn,
            req.parcel_id,
            batch,
            prototype_id=req.prototype_id,
            overrides=req.overrides(),
            include_demolition=req.include_demolition,
        )
    except UnderwriteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    scenario_id = svc.save(conn, result, name=req.name)
    conn.commit()
    return ScenarioRef(scenario_id=scenario_id, parcel_id=req.parcel_id)


@router.get("/scenarios", response_model=list[ScenarioSummary])
def list_scenarios(conn=Depends(get_conn)) -> list[ScenarioSummary]:
    from api import serializers as ser

    return [
        ScenarioSummary(
            scenario_id=row["scenario_id"],
            parcel_id=row["ssl"],
            display_name=ser.display_name(row.get("address"), row["ssl"]),
            ward=ser.ward_name(row.get("submarket_id")),
            prototype_id=row["prototype_id"],
            saved_at=row["saved_at"],
            full_rlv=float(row["full_rlv"]) if row.get("full_rlv") is not None else None,
        )
        for row in repo.list_scenarios(conn)
    ]


def _load(conn, scenario_id: str) -> dict:
    scenario = repo.get_scenario(conn, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"No scenario {scenario_id}.")
    return scenario


@router.get("/scenario/{scenario_id}")
def get_scenario(scenario_id: str, conn=Depends(get_conn)) -> dict:
    """The frozen scenario, exactly as saved. The engine does not run."""
    return svc.export_payload(_load(conn, scenario_id))


@router.get("/scenario/{scenario_id}/export")
def export_scenario(scenario_id: str, conn=Depends(get_conn)) -> Response:
    """The same payload as a downloadable file.

    Served as an attachment rather than inline JSON so the browser saves it: this is the
    "Export" button's target, and the point is to end up with a file someone can keep.
    """
    scenario = _load(conn, scenario_id)
    payload = svc.export_payload(scenario)

    stamp = scenario["saved_at"].strftime("%Y%m%d")
    # The address, not the parcel id — "SSL" never appears in anything a user sees, and a
    # filename is very much user-facing.
    slug = (scenario.get("address") or scenario["ssl"]).strip().lower()
    slug = "".join(c if c.isalnum() else "-" for c in slug).strip("-")[:48] or "parcel"

    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={
            "content-disposition": f'attachment; filename="residual-{slug}-{stamp}.json"'
        },
    )
