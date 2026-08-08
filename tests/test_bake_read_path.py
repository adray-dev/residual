"""Batch scoping and retention on the bake read path (SPEC §9).

Retention keeps the last TWO batches, so every read that feeds the map or a table has to be
scoped to one `computed_at` or each parcel comes back twice. These tests pin that:
one row per parcel out of `latest_bake_for_map`, no matter how many batches are retained.

Needs a loaded database (Stage B + Stage C). Skips cleanly when there isn't one, so the
Stage A gate still runs anywhere. Every test that writes does so inside a transaction it
rolls back — the real batches are never mutated.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from data import repositories as repo


def _database_url() -> str | None:
    """DATABASE_URL, which importing `data.repositories` has already loaded from `.env`."""
    return os.environ.get("DATABASE_URL") or None


@pytest.fixture(scope="module")
def conn():
    url = _database_url()
    if not url:
        pytest.skip("DATABASE_URL is not set — Stage B/C database tests skipped")
    try:
        connection = repo.connect(url)
    except Exception as exc:                      # noqa: BLE001 — any driver error means no DB
        pytest.skip(f"database unreachable ({type(exc).__name__}) — skipping")
    try:
        if not repo.list_bake_batches(connection):
            pytest.skip("bake_results is empty — run `python -m bake.run_bake` first")
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def rollback(conn):
    """Hand back the connection, then undo whatever the test wrote."""
    yield conn
    conn.rollback()


def _batch_row_template(ssl: str, computed_at: datetime) -> dict:
    return {
        "ssl": ssl,
        "prototype_id": repo.NONE_PROTOTYPE,
        "is_best": True,
        "status": "infeasible",
        "binding_constraint": "synthetic test batch",
        "computed_at": computed_at,
    }


# ---------------------------------------------------------------------------
# the read path: exactly one row per parcel
# ---------------------------------------------------------------------------
def test_map_read_returns_one_row_per_parcel(conn):
    """The headline invariant: one row per (ssl, is_best) parcel in the latest batch."""
    rows = repo.latest_bake_for_map(conn)
    ssls = [r["ssl"] for r in rows]

    assert ssls, "latest_bake_for_map returned nothing"
    duplicated = len(ssls) - len(set(ssls))
    assert duplicated == 0, f"{duplicated} parcels returned more than once"


def test_map_read_ignores_the_older_retained_batch(conn):
    """With 2 batches retained, an unscoped read would return ~2x the parcels."""
    batches = repo.list_bake_batches(conn)
    if len(batches) < 2:
        pytest.skip("only one batch retained — nothing for the scope to exclude")

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM bake_results WHERE is_best")
        unscoped = cur.fetchone()["n"]

    scoped = len(repo.latest_bake_for_map(conn))
    assert scoped < unscoped, "read is not scoped to a single batch"


def test_every_parcel_in_the_latest_batch_has_exactly_one_best_row(conn):
    """`is_best` is the map's join key: 0 or 2+ per parcel would drop or double a parcel."""
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT count(*) AS offenders FROM (
                    SELECT ssl FROM bake_results
                    WHERE computed_at = {repo.LATEST_BATCH}
                    GROUP BY ssl
                    HAVING count(*) FILTER (WHERE is_best) <> 1
                ) bad"""
        )
        assert cur.fetchone()["offenders"] == 0


def test_latest_batch_covers_every_parcel(conn):
    """SPEC §9: every parcel gets a row — no parcel silently vanishes."""
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT count(*) AS missing FROM parcels p
                WHERE NOT EXISTS (
                    SELECT 1 FROM bake_results b
                    WHERE b.ssl = p.ssl AND b.computed_at = {repo.LATEST_BATCH})"""
        )
        assert cur.fetchone()["missing"] == 0


def test_map_read_stays_one_row_per_parcel_with_a_third_batch(rollback):
    """The regression guard: appending another batch must not change the map's row count."""
    conn = rollback
    before = repo.latest_bake_for_map(conn)
    sample = [r["ssl"] for r in before[:200]]

    newer = datetime.now(timezone.utc) + timedelta(days=1)
    repo.write_bake_results(conn, [_batch_row_template(s, newer) for s in sample])

    after = repo.latest_bake_for_map(conn)
    after_ssls = [r["ssl"] for r in after]

    assert len(after_ssls) == len(set(after_ssls)), "new batch duplicated parcels on the map"
    # The map now reads the newest batch, which only covers the sample.
    assert set(after_ssls) == set(sample)


# ---------------------------------------------------------------------------
# retention
# ---------------------------------------------------------------------------
def test_prune_keeps_exactly_the_two_newest_batches(rollback):
    conn = rollback
    original = repo.list_bake_batches(conn)
    if len(original) < 2:
        pytest.skip("need 2 existing batches to prove the oldest is the one dropped")

    newer = datetime.now(timezone.utc) + timedelta(days=1)
    sample = [r["ssl"] for r in repo.latest_bake_for_map(conn)[:50]]
    repo.write_bake_results(conn, [_batch_row_template(s, newer) for s in sample])
    assert len(repo.list_bake_batches(conn)) == len(original) + 1

    pruned = repo.prune_bake_batches(conn, keep=2)
    kept = repo.list_bake_batches(conn)

    assert len(kept) == 2, f"retention left {len(kept)} batches, expected 2"
    assert kept == [newer, original[0]], "the wrong batches survived"
    assert original[-1] not in kept, "the oldest batch was not pruned"
    assert pruned > 0, "prune reported deleting nothing"


def test_prune_is_a_noop_when_already_at_the_limit(rollback):
    conn = rollback
    before = repo.list_bake_batches(conn)
    if len(before) > 2:
        pytest.skip("table is over the retention limit — pruning is expected to delete")

    assert repo.prune_bake_batches(conn, keep=2) == 0
    assert repo.list_bake_batches(conn) == before


# ---------------------------------------------------------------------------
# idempotency within a batch
# ---------------------------------------------------------------------------
def test_rewriting_a_batch_at_the_same_stamp_inserts_no_duplicates(rollback):
    """`computed_at` is part of the PK and the insert is ON CONFLICT DO NOTHING, so a
    retried flush inside one run cannot double-write. Re-running the bake with a NEW stamp
    is an append (SPEC §9), which is a different thing."""
    conn = rollback
    stamp = datetime.now(timezone.utc) + timedelta(days=1)
    sample = [r["ssl"] for r in repo.latest_bake_for_map(conn)[:50]]
    rows = [_batch_row_template(s, stamp) for s in sample]

    repo.write_bake_results(conn, rows)
    repo.write_bake_results(conn, rows)          # the retry

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM bake_results WHERE computed_at = %s", (stamp,))
        assert cur.fetchone()["n"] == len(sample)
