"""Request-scoped dependencies: the database connection and the bake batch.

The batch dependency is the important one. SPEC §9 retains the last TWO bake batches, so
any read that does not pin a batch can return a parcel twice — and worse, two reads in the
same request can land on different batches if a bake commits between them, leaving the
tiles on one bake and the table on another.

`current_batch` resolves `max(computed_at)` ONCE per request and every repository call
threads it through. `latest_bake_for_map(..., computed_at=...)` already accepts it; this
is the thing that guarantees it is always supplied.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterator

from fastapi import Depends, HTTPException, Request

from data import repositories as repo


def get_conn(request: Request) -> Iterator:
    """One connection per request, from the app-wide pool."""
    pool = request.app.state.pool
    with pool.connection() as conn:
        yield conn


def current_batch(conn=Depends(get_conn)) -> datetime:
    """The one bake batch this request reads from, resolved once.

    Every read endpoint depends on this and passes it down. A 503 rather than an empty
    result when no bake exists: an unbaked database is an operational state, not a valid
    empty answer, and a map rendering "0 parcels" would misreport it.
    """
    batch = repo.latest_batch_at(conn)
    if batch is None:
        raise HTTPException(
            status_code=503,
            detail="No bake results are available yet. Run `python -m bake.run_bake`.",
        )
    return batch
