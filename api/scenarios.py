"""Saving and exporting a scenario (SPEC §7.1, §10).

A scenario is a *frozen* underwrite. The point of freezing is stated in SPEC §7.1: a saved
scenario never re-reads live market data, so it reproduces forever even after a re-bake
moves the market row or the zoning seed underneath it. Three things are therefore stamped
at save time and never resolved again:

  * `market_snapshot` — the exact MarketData values the run used, including any per-parcel
    override the user applied.
  * the assumption set — written to its own row, because an edited run's inputs exist
    nowhere else and numbers without their inputs are not reproducible.
  * `cashflow` and `outputs` — the serialized result itself.

Shortlists are deliberately the opposite (SPEC §7.1): they hold parcel ids and read live,
so they cannot go stale. Freezing is for "this is the deal I underwrote"; live is for
"these are the parcels I am watching".
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from api import serializers as ser
from data import repositories as repo


def _plain(value: Any) -> Any:
    """Anything the engine or the serializers hand back, as something JSON can hold.

    Three kinds arrive here and none of them serialize on their own: Pydantic models from
    `underwrite_response`, dataclasses from the engine (market, program), and numpy arrays
    inside the cash flow vectors.
    """
    if isinstance(value, BaseModel):
        # mode="json" so nested datetimes and enums come out as strings too.
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _plain(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if hasattr(value, "tolist"):            # numpy array / scalar
        return _plain(value.tolist())
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value") and type(value).__mro__[1].__name__ == "Enum":
        return value.value
    return value


def save(conn, result: dict, name: str | None = None, user_id: str = "local") -> str:
    """Freeze `result` (an `underwrite()` return) as a scenario. Returns its id."""
    scenario_id = uuid.uuid4().hex
    assumptions = result["assumptions"]

    # The assumption set gets the scenario's own id, so an edited set can never collide
    # with `default_v1` or with another scenario's edits.
    assumption_set_id = f"scenario_{scenario_id}"
    repo.upsert_assumption_set(
        conn,
        {
            "assumption_set_id": assumption_set_id,
            "name": name or f"Scenario {scenario_id[:8]}",
            **{
                group: _plain(getattr(assumptions, group))
                for group in ("program", "timeline", "cost", "revenue", "debt",
                              "exit", "envelope")
            },
        },
    )

    # The full response is stored as `outputs`, not just the metric block: it is what the
    # export has to reproduce, and re-deriving it later would mean re-running the engine —
    # the one thing a frozen scenario must never do.
    response = ser.underwrite_response(result)

    repo.save_scenario(
        conn,
        {
            "scenario_id": scenario_id,
            "ssl": result["parcel"].ssl,
            "prototype_id": result["prototype_id"],
            "assumption_set_id": assumption_set_id,
            "user_id": user_id,
            "market_snapshot": _plain(result["market"]),
            "cashflow": _plain(response["cashflow"]),
            "outputs": _plain(response),
        },
    )
    return scenario_id


def export_payload(scenario: dict) -> dict:
    """The exported file: inputs, market, and results, in one self-describing document.

    Everything needed to audit or reproduce the number, and nothing that would require
    reading the live database — an export handed to someone else has to stand on its own.
    """
    return {
        "format": "residual.scenario/v1",
        "scenario_id": scenario["scenario_id"],
        "saved_at": _plain(scenario["saved_at"]),
        "parcel": {
            # "Parcel ID", never "SSL", even in a file the user may open in a text editor.
            "parcel_id": scenario["ssl"],
            "address": scenario.get("address"),
            "ward": ser.ward_name(scenario.get("submarket_id")),
        },
        "prototype_id": scenario["prototype_id"],
        "assumptions": {
            "assumption_set_id": scenario["assumption_set_id"],
            "name": scenario.get("assumption_set_name"),
            **{
                group: scenario.get(group) or {}
                for group in ("program", "timeline", "cost", "revenue", "debt",
                              "exit", "envelope")
            },
        },
        # Frozen at save time; NOT the current market row (SPEC §7.1).
        "market_snapshot": scenario["market_snapshot"],
        "results": scenario["outputs"],
        "cashflow": scenario["cashflow"],
    }
