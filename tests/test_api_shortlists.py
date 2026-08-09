"""Shortlists — screen 1f (SPEC §7.1, Stage D).

The property under test is the one the schema calls out: a shortlist holds parcel ids and
reads its numbers LIVE from the current bake, so it never goes stale and never freezes a
figure. That is the deliberate opposite of a scenario.
"""
from __future__ import annotations

import os

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


@pytest.fixture(scope="module")
def parcel_ids(client):
    rows = client.get(
        "/map/query", params={"statuses": ["scored"], "limit": 200}
    ).json()["rows"]
    return [r["parcel_id"] for r in rows if r["land_value"]][:3]


@pytest.fixture
def a_list(client):
    """A list that is removed afterwards, so the suite leaves nothing behind."""
    created: list[str] = []

    def make(name: str = "test list") -> str:
        response = client.post("/shortlists", json={"name": name})
        assert response.status_code == 201, response.text
        shortlist_id = response.json()["shortlist_id"]
        created.append(shortlist_id)
        return shortlist_id

    yield make

    for shortlist_id in created:
        client.delete(f"/shortlists/{shortlist_id}")


def test_a_list_starts_empty_and_counts_its_members(client, a_list, parcel_ids):
    shortlist_id = a_list("counting")
    assert client.get(f"/shortlists/{shortlist_id}").json()["totals"]["parcel_count"] == 0

    for parcel_id in parcel_ids:
        assert client.post(f"/shortlists/{shortlist_id}/parcels/{parcel_id}").status_code == 204

    summary = next(
        row for row in client.get("/shortlists").json() if row["shortlist_id"] == shortlist_id
    )
    assert summary["parcel_count"] == len(parcel_ids)


def test_adding_the_same_parcel_twice_is_a_no_op(client, a_list, parcel_ids):
    """Saving a parcel you already saved is not an error, and must not duplicate it."""
    shortlist_id = a_list("idempotent")
    for _ in range(3):
        assert client.post(f"/shortlists/{shortlist_id}/parcels/{parcel_ids[0]}").status_code == 204
    assert client.get(f"/shortlists/{shortlist_id}").json()["totals"]["parcel_count"] == 1


def test_card_numbers_are_read_live_from_the_current_bake(client, a_list, parcel_ids):
    """A shortlist stores no numbers, so its figures must equal the map's for the same
    parcel and the same batch — not a copy taken when the parcel was saved."""
    shortlist_id = a_list("live")
    client.post(f"/shortlists/{shortlist_id}/parcels/{parcel_ids[0]}")

    detail = client.get(f"/shortlists/{shortlist_id}").json()
    saved = detail["parcels"][0]
    live = client.get(
        "/map/query", params={"statuses": ["scored"], "limit": 200}
    ).json()["rows"]
    same = next(r for r in live if r["parcel_id"] == parcel_ids[0])

    assert saved["rlv_total"] == same["rlv_total"]
    assert saved["yield_on_cost"] == same["yield_on_cost"]
    assert saved["gross_sf"] == same["gross_sf"]
    # And pinned to the same batch /meta advertises, so the whole app reads one bake.
    assert detail["computed_at"] == client.get("/meta").json()["computed_at"]


def test_the_return_comes_from_the_full_model_not_the_bake(client, a_list, parcel_ids):
    """Levered IRR is absent from the screening tier by design (SPEC §9), so the card's
    return has to be computed — and must match a direct underwrite of the same parcel."""
    shortlist_id = a_list("returns")
    client.post(f"/shortlists/{shortlist_id}/parcels/{parcel_ids[0]}")

    card = client.get(f"/shortlists/{shortlist_id}").json()["parcels"][0]
    full = client.get(f"/parcel/{parcel_ids[0]}/underwrite").json()
    assert card["irr"] == pytest.approx(full["returns"]["irr"], abs=1e-9)


def test_totals_use_a_median_return_not_a_mean(client, a_list, parcel_ids):
    """One deep-negative parcel must not drag the headline somewhere no member sits."""
    shortlist_id = a_list("totals")
    for parcel_id in parcel_ids:
        client.post(f"/shortlists/{shortlist_id}/parcels/{parcel_id}")

    detail = client.get(f"/shortlists/{shortlist_id}").json()
    returns = sorted(p["irr"] for p in detail["parcels"] if p["irr"] is not None)
    assert detail["totals"]["median_return"] == pytest.approx(
        returns[len(returns) // 2] if len(returns) % 2 else
        (returns[len(returns) // 2 - 1] + returns[len(returns) // 2]) / 2
    )
    assert detail["totals"]["combined_value"] == pytest.approx(
        sum(p["rlv_total"] for p in detail["parcels"] if p["rlv_total"] is not None)
    )


def test_removing_a_parcel_leaves_the_list_and_the_parcel_intact(client, a_list, parcel_ids):
    shortlist_id = a_list("removal")
    client.post(f"/shortlists/{shortlist_id}/parcels/{parcel_ids[0]}")
    assert client.delete(f"/shortlists/{shortlist_id}/parcels/{parcel_ids[0]}").status_code == 204
    assert client.get(f"/shortlists/{shortlist_id}").json()["totals"]["parcel_count"] == 0
    # The parcel itself is untouched — a shortlist is user state, not model state.
    assert client.get(f"/parcel/{parcel_ids[0]}").status_code == 200


def test_deleting_a_list_takes_its_membership_with_it(client, parcel_ids):
    shortlist_id = client.post("/shortlists", json={"name": "temporary"}).json()["shortlist_id"]
    client.post(f"/shortlists/{shortlist_id}/parcels/{parcel_ids[0]}")
    assert client.delete(f"/shortlists/{shortlist_id}").status_code == 204
    assert client.get(f"/shortlists/{shortlist_id}").status_code == 404
    with repo.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM shortlist_parcels WHERE shortlist_id = %s",
            (shortlist_id,),
        )
        assert cur.fetchone()["n"] == 0


def test_unknown_list_and_unknown_parcel_are_404s(client, a_list):
    assert client.get("/shortlists/nope").status_code == 404
    assert client.post("/shortlists/nope/parcels/0001    0001").status_code == 404
    assert client.post(f"/shortlists/{a_list('x')}/parcels/9999    9999").status_code == 404


def test_a_list_needs_a_name(client):
    assert client.post("/shortlists", json={"name": "   "}).status_code == 422
