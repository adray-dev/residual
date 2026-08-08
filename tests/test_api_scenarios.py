"""Stage D — saving and exporting a scenario (SPEC §7.1, §10).

The claim under test is SPEC §7.1's: a saved scenario is FROZEN. It stamps the market
values it used and never re-reads live data, so it reproduces after a re-bake, after a
market refresh, and after someone edits the defaults. Everything else here is plumbing;
that one property is the product promise.
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
def parcel_id(client):
    rows = client.get(
        "/map/query", params={"statuses": ["scored"], "limit": 200}
    ).json()["rows"]
    return next(r for r in rows if r["land_value"])["parcel_id"]


@pytest.fixture
def saved(client, parcel_id):
    """Scenarios created by a test, removed afterwards so the table stays clean."""
    created: list[str] = []

    def save(**body):
        response = client.post("/scenario", json={"parcel_id": parcel_id, **body})
        assert response.status_code == 201, response.text
        scenario_id = response.json()["scenario_id"]
        created.append(scenario_id)
        return scenario_id

    yield save

    with repo.connection() as conn:
        for scenario_id in created:
            repo.delete_scenario(conn, scenario_id)
        conn.commit()


# ---------------------------------------------------------------------------
# saving
# ---------------------------------------------------------------------------
def test_a_scenario_records_what_the_model_said_not_what_the_client_sent(
    client, parcel_id, saved
):
    """The request carries INPUTS only; the server re-runs and stores its own numbers."""
    live = client.get(f"/parcel/{parcel_id}/underwrite").json()
    scenario = client.get(f"/scenario/{saved(name='baseline')}").json()

    assert scenario["results"]["feasibility_value"]["full"] == pytest.approx(
        live["feasibility_value"]["full"]
    )
    assert scenario["parcel"]["parcel_id"] == parcel_id
    assert scenario["prototype_id"] == live["prototype_id"]


def test_the_edited_inputs_are_saved_alongside_the_result(client, parcel_id, saved):
    """Numbers without their inputs are not reproducible, so the assumption set is stored
    as its own row rather than referencing the shared default."""
    scenario_id = saved(name="tight cap", exit={"exit_cap_rate": 0.05})
    scenario = client.get(f"/scenario/{scenario_id}").json()

    assert scenario["assumptions"]["exit"]["exit_cap_rate"] == 0.05
    assert scenario["assumptions"]["assumption_set_id"] != "default_v1"
    assert scenario["assumptions"]["name"] == "tight cap"


def test_the_market_snapshot_records_the_values_actually_used(client, parcel_id, saved):
    """A per-parcel edit to a market-backed input displaces the market row, so the snapshot
    has to show the displaced value — otherwise the frozen record disagrees with the frozen
    result it sits next to."""
    scenario = client.get(f"/scenario/{saved(exit={'exit_cap_rate': 0.05})}").json()
    assert scenario["market_snapshot"]["exit_cap_rate"] == 0.05


def test_an_edited_scenario_stores_different_numbers_than_the_default_one(
    client, parcel_id, saved
):
    plain = client.get(f"/scenario/{saved()}").json()
    edited = client.get(f"/scenario/{saved(exit={'exit_cap_rate': 0.05})}").json()
    assert (
        edited["results"]["feasibility_value"]["full"]
        > plain["results"]["feasibility_value"]["full"]
    )


# ---------------------------------------------------------------------------
# frozen (SPEC §7.1)
# ---------------------------------------------------------------------------
def test_a_saved_scenario_does_not_re_read_live_market_data(client, parcel_id, saved):
    """The freeze, tested directly: move the submarket's market row underneath a saved
    scenario and it must still report what it was saved with.

    The market row is restored afterwards — this is the live database the whole suite
    reads."""
    scenario_id = saved(name="frozen")
    before = client.get(f"/scenario/{scenario_id}").json()
    original_cap = before["market_snapshot"]["exit_cap_rate"]

    with repo.connection() as conn:
        submarket = repo.get_parcel_record(conn, parcel_id)["submarket_id"]
        # `market_data` is keyed (submarket_id, use_type, as_of), so each row is bumped and
        # restored individually — a blanket UPDATE would flatten distinct caps into one.
        with conn.cursor() as cur:
            cur.execute(
                "SELECT use_type, as_of, exit_cap FROM market_data WHERE submarket_id = %s",
                (submarket,),
            )
            original = cur.fetchall()
            assert original, f"no market rows for {submarket}"
            for row in original:
                cur.execute(
                    """UPDATE market_data SET exit_cap = %s
                        WHERE submarket_id = %s AND use_type = %s AND as_of = %s""",
                    (float(row["exit_cap"]) + 0.02, submarket, row["use_type"], row["as_of"]),
                )
        conn.commit()
        try:
            after = client.get(f"/scenario/{scenario_id}").json()
        finally:
            with conn.cursor() as cur:
                for row in original:
                    cur.execute(
                        """UPDATE market_data SET exit_cap = %s
                            WHERE submarket_id = %s AND use_type = %s AND as_of = %s""",
                        (row["exit_cap"], submarket, row["use_type"], row["as_of"]),
                    )
            conn.commit()

    assert after["market_snapshot"]["exit_cap_rate"] == original_cap
    assert (
        after["results"]["feasibility_value"]["full"]
        == before["results"]["feasibility_value"]["full"]
    )


# ---------------------------------------------------------------------------
# listing and export
# ---------------------------------------------------------------------------
def test_saved_scenarios_are_listed_newest_first(client, saved):
    first, second = saved(name="one"), saved(name="two")
    rows = client.get("/scenarios").json()
    ids = [r["scenario_id"] for r in rows]
    assert first in ids and second in ids
    assert ids.index(second) < ids.index(first)


def test_the_export_is_a_download_named_after_the_address_not_the_parcel_id(client, saved):
    """"SSL" never appears in user-facing text, and a filename is very much user-facing."""
    response = client.get(f"/scenario/{saved()}/export")
    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "ssl" not in disposition.lower()


def test_the_export_carries_inputs_market_and_results_together(client, saved):
    """An exported file is handed to someone else, so it has to stand on its own — the
    numbers, the inputs behind them, and the market they assumed."""
    payload = client.get(f"/scenario/{saved()}/export").json()
    assert payload["format"] == "residual.scenario/v1"
    assert set(payload) >= {
        "scenario_id", "saved_at", "parcel", "prototype_id",
        "assumptions", "market_snapshot", "results", "cashflow",
    }
    for group in ("timeline", "cost", "revenue", "debt", "exit", "envelope"):
        assert payload["assumptions"][group], group
    assert payload["cashflow"]["cumulative_cost"]


def test_an_unknown_scenario_is_a_404_not_an_empty_document(client):
    assert client.get("/scenario/does-not-exist").status_code == 404
    assert client.get("/scenario/does-not-exist/export").status_code == 404


def test_saving_an_unmodellable_parcel_is_refused_with_a_reason(client):
    """Exempt land cannot be underwritten, so there is nothing to freeze."""
    rows = client.get("/map/query", params={"statuses": ["exempt"], "limit": 1}).json()["rows"]
    response = client.post("/scenario", json={"parcel_id": rows[0]["parcel_id"]})
    assert response.status_code == 422
    assert "exempt" in response.json()["detail"].lower()
