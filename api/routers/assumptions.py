"""GET /assumptions/default — the 1c inputs modal's starting values (SPEC §10).

SPEC calls this "autoloads on app open". It serves the §2 defaults from
`engine/assumptions.py`, which CLAUDE.md pins as the single source of truth for every
monetary and area default.

Provenance is deliberately NOT in the payload. The engine tags every input
national/submarket/local for the confidence score, but the handoff's language rules say
the UI shows values only — confidence is the one number that summarizes sourcing.
"""
from __future__ import annotations

import copy

from fastapi import APIRouter, Depends

from api.schemas import AssumptionSet
from api.deps import get_conn
from data import repositories as repo
from engine.assumptions import DEFAULT_ASSUMPTIONS

router = APIRouter(prefix="/assumptions", tags=["assumptions"])


GROUPS = ("timeline", "cost", "revenue", "debt", "exit", "envelope", "program")


@router.get("/default", response_model=AssumptionSet)
def get_default(conn=Depends(get_conn)) -> AssumptionSet:
    """The default assumption set: in-code §2 defaults, overlaid with the stored row.

    The overlay direction matters. An operator may retune a VALUE without a deploy, but a
    stored row must never be able to remove an INPUT — it was written by whatever version
    of §2 was current when it was seeded, so a row seeded before `irr_hurdle` existed
    would otherwise hide the field from the inputs modal entirely and leave the user
    unable to edit a number the model is using. Defaults define the shape; storage
    overrides the values inside it.
    """
    stored = repo.get_default_assumption_set(conn)
    payload = {}
    for group in GROUPS:
        merged = copy.deepcopy(getattr(DEFAULT_ASSUMPTIONS, group))
        if stored is not None:
            for key, value in (getattr(stored, group) or {}).items():
                if key in merged:
                    merged[key] = value
        payload[group] = merged

    return AssumptionSet(
        assumption_set_id="default_v1",
        name="SPEC §2 defaults (v1)",
        **payload,
    )
