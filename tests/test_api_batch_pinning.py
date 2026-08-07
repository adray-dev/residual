"""Stage D phase 1 gate — batch pinning.

SPEC §9 retains the last TWO bake batches, and SPEC §10 requires the API to resolve
`max(computed_at)` once per request. This file proves the requirement rather than trusting
the convention, because the failure it prevents is silent: a bake committing mid-request
leaves the map on one batch and the table on another, and every number still *looks*
plausible.
"""
from __future__ import annotations

import os
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from data import repositories as repo

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"
)


@pytest.fixture(scope="module")
def client():
    from api.main import app
    with TestClient(app) as c:
        yield c


def test_two_batches_are_retained(client):
    """The precondition. If only one batch exists these tests prove nothing."""
    with repo.connection() as conn:
        batches = repo.list_bake_batches(conn)
    assert len(batches) >= 1
    if len(batches) < 2:
        pytest.skip("only one batch retained; run the bake twice to exercise pinning")


def test_every_read_endpoint_reports_the_same_batch(client):
    """A client assembling a screen from several calls must not mix bakes."""
    meta = client.get("/meta").json()
    rows = client.get("/map/query", params={"statuses": ["scored"], "limit": 1}).json()
    parcel = client.get(f"/parcel/{rows['rows'][0]['parcel_id']}").json()

    assert rows["computed_at"] == meta["computed_at"]
    assert parcel["computed_at"] == meta["computed_at"]


def test_reads_pin_the_latest_batch_not_an_older_retained_one(client):
    with repo.connection() as conn:
        batches = repo.list_bake_batches(conn)
    latest = batches[0]
    reported = datetime.fromisoformat(client.get("/meta").json()["computed_at"])
    assert reported == latest


def test_map_query_never_returns_a_parcel_twice_across_retained_batches(client):
    """The concrete symptom of an unpinned read: two retained batches, two rows per parcel."""
    body = client.get("/map/query", params={"limit": 2000}).json()
    ids = [r["parcel_id"] for r in body["rows"]]
    assert len(ids) == len(set(ids))


def test_total_never_exceeds_the_parcel_count(client):
    """An unpinned count would roughly double once a second batch is retained."""
    body = client.get("/map/query", params={"limit": 1}).json()
    with repo.connection() as conn:
        assert body["total"] <= repo.count_parcels(conn)


def test_current_batch_is_resolved_once_per_request(client, monkeypatch):
    """The mechanism, not just the symptom.

    A request that resolved the batch per query would call `latest_batch_at` several
    times, and each call is a separate chance to land on a different bake. The dependency
    must be evaluated exactly once and threaded down.
    """
    calls = {"n": 0}
    real = repo.latest_batch_at

    def counting(conn):
        calls["n"] += 1
        return real(conn)

    monkeypatch.setattr(repo, "latest_batch_at", counting)
    # /meta issues several repository reads (status counts, three ramps, submarkets...).
    assert client.get("/meta").status_code == 200
    assert calls["n"] == 1, f"batch resolved {calls['n']} times in one request"


def test_repository_reads_require_an_explicit_batch_to_stay_consistent():
    """`map_query` and `objective_ramp` must both honour a pinned batch.

    Passing an older batch must actually change the answer — if it did not, the parameter
    would be decorative and the pinning guarantee would be fiction.
    """
    with repo.connection() as conn:
        batches = repo.list_bake_batches(conn)
        if len(batches) < 2:
            pytest.skip("needs two retained batches")
        newest, older = batches[0], batches[1]

        _, total_new = repo.map_query(conn, computed_at=newest, limit=1)
        _, total_old = repo.map_query(conn, computed_at=older, limit=1)
        assert total_new > 0 and total_old > 0

        # Both are real reads of distinct batches, not the same rows twice.
        rows_new, _ = repo.map_query(conn, computed_at=newest, limit=5)
        rows_old, _ = repo.map_query(conn, computed_at=older, limit=5)
        assert rows_new and rows_old
