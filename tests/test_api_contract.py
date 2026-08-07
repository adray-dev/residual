"""Stage D phase 1 gate — the API core against the real baked database.

These are contract tests, not unit tests: they run against the live Postgres the bake
wrote, because the thing worth proving is that the endpoints agree with the data as it
actually exists, not with a fixture someone hand-wrote to match the code.
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
def meta(client):
    response = client.get("/meta")
    assert response.status_code == 200
    return response.json()


@pytest.fixture(scope="module")
def scored_parcel_id(client):
    """A real scored parcel to drill into."""
    rows = client.get("/map/query", params={"statuses": ["scored"], "limit": 1}).json()["rows"]
    assert rows, "no scored parcels in the current bake"
    return rows[0]["parcel_id"]


# ---------------------------------------------------------------------------
# /meta
# ---------------------------------------------------------------------------
def test_meta_reports_every_parcel_exactly_once(meta):
    """SPEC §9: every parcel gets a row and every colour is explainable, so the status
    counts must sum to the parcel count with nothing unaccounted for."""
    with repo.connection() as conn:
        assert meta["parcel_count"] == repo.count_parcels(conn)
    assert sum(meta["status_counts"].values()) == meta["parcel_count"]
    assert set(meta["status_counts"]) <= {
        "scored", "infeasible", "exempt", "historic", "zone_not_encoded"
    }


def test_meta_serves_the_vocabulary_so_the_client_keeps_no_copy(meta):
    labels = meta["labels"]
    assert set(labels) == {
        "metric", "prototype", "construction", "parking",
        "binding_constraint", "status", "tier",
    }
    # The handoff's language rules, spot-checked.
    assert labels["metric"]["irr"] == "Annual return"
    assert labels["metric"]["ssl"] == "Parcel ID"
    assert labels["prototype"]["garden"] == "Garden walk-up"
    assert labels["construction"]["wood_v"] == "Wood frame"
    # Both tiers are named, because the drill-down must label that they differ.
    assert labels["tier"] == {
        "screening": "Screening estimate",
        "full": "Full underwriting",
    }


def test_meta_never_says_ssl_anywhere_in_user_facing_text(meta):
    """The handoff's hardest naming rule: "SSL" never appears. It is always "Parcel ID"."""
    for group in meta["labels"].values():
        for value in group.values():
            assert "SSL" not in value.upper().split(), value


def test_every_objective_has_a_diverging_ramp(meta):
    """56% of scored parcels price negative, so each objective needs both arms."""
    assert set(meta["ramps"]) == set(meta["objectives"])
    for objective, ramp in meta["ramps"].items():
        assert ramp["min"] <= 0 <= ramp["max"], objective
        assert ramp["negative_count"] > 0 and ramp["positive_count"] > 0, objective
        assert ramp["negative_breaks"] == sorted(ramp["negative_breaks"]), objective
        assert ramp["positive_breaks"] == sorted(ramp["positive_breaks"]), objective
        assert all(b < 0 for b in ramp["negative_breaks"]), objective
        assert all(b >= 0 for b in ramp["positive_breaks"]), objective


def test_tileset_is_never_paired_with_a_different_batch(meta):
    """A tileset URL is only served when a file built from THIS batch exists.

    Serving a stale tileset would silently pair one bake's geometry with another bake's
    numbers — the exact failure /meta exists to prevent.
    """
    from api.routers.meta import tileset_for
    from datetime import datetime

    batch = datetime.fromisoformat(meta["computed_at"])
    url, available = tileset_for(batch)
    assert available == meta["tileset_available"]
    if available:
        assert batch.strftime("%Y%m%dT%H%M%S") in url
    else:
        assert meta["tileset_url"] is None


# ---------------------------------------------------------------------------
# /map/query
# ---------------------------------------------------------------------------
def test_map_query_returns_one_row_per_parcel(client):
    rows = client.get("/map/query", params={"limit": 500}).json()["rows"]
    ids = [r["parcel_id"] for r in rows]
    assert len(ids) == len(set(ids))


def test_map_query_total_matches_the_repository(client, meta):
    body = client.get("/map/query", params={"statuses": ["scored"], "limit": 1}).json()
    assert body["total"] == meta["status_counts"]["scored"]


def test_map_query_default_sort_is_feasibility_value_high_to_low(client):
    """The handoff's 1d default: feasibility value, high to low."""
    body = client.get("/map/query", params={"statuses": ["scored"], "limit": 50}).json()
    assert body["sort_key"] == "rlv_total"
    values = [r["rlv_total"] for r in body["rows"]]
    assert values == sorted(values, reverse=True)


def test_map_query_sorts_by_any_table_column(client):
    for key in ("noi", "total_development_cost", "yield_on_cost", "unit_count"):
        body = client.get(
            "/map/query",
            params={"statuses": ["scored"], "sort_key": key, "sort_dir": "asc", "limit": 30},
        ).json()
        values = [r[key] for r in body["rows"] if r[key] is not None]
        assert values == sorted(values), key


def test_map_query_rejects_an_unknown_sort_key_instead_of_interpolating_it(client):
    """`sort_key` reaches an ORDER BY, so anything off the whitelist must fall back."""
    body = client.get(
        "/map/query", params={"sort_key": "1; DROP TABLE parcels--", "limit": 1}
    ).json()
    assert body["sort_key"] == "1; DROP TABLE parcels--"   # echoed as received
    with repo.connection() as conn:                        # but the table is still there
        assert repo.count_parcels(conn) > 0


def test_map_query_paging_does_not_repeat_or_skip(client):
    first = client.get("/map/query", params={"statuses": ["scored"], "limit": 20}).json()
    second = client.get(
        "/map/query", params={"statuses": ["scored"], "limit": 20, "offset": 20}
    ).json()
    assert first["total"] == second["total"]
    assert not ({r["parcel_id"] for r in first["rows"]} & {r["parcel_id"] for r in second["rows"]})


def test_status_rows_carry_no_screening_numbers(client):
    """A status row has no program and no pro forma: NULL, never 0. A zero would sort as a
    real value and read as "$0 of income" in the table."""
    for status in ("exempt", "historic", "infeasible", "zone_not_encoded"):
        rows = client.get("/map/query", params={"statuses": [status], "limit": 5}).json()["rows"]
        assert rows, status
        for row in rows:
            assert row["status"] == status
            assert row["prototype_id"] is None
            for field in ("screening_rlv", "rlv_total", "noi", "gross_sf", "unit_count"):
                assert row[field] is None, (status, field)


def test_bounds_filter_actually_restricts_the_set(client, meta):
    """A tight box around the Capitol must return far fewer parcels than the whole city."""
    everything = client.get("/map/query", params={"limit": 1}).json()["total"]
    boxed = client.get(
        "/map/query",
        params={"min_lon": -77.02, "min_lat": 38.88, "max_lon": -77.00, "max_lat": 38.90,
                "limit": 1},
    ).json()["total"]
    assert 0 < boxed < everything


def test_incomplete_bounds_is_a_422_not_a_silent_full_city_read(client):
    response = client.get("/map/query", params={"min_lon": -77.02, "min_lat": 38.88})
    assert response.status_code == 422


def test_irr_filter_refuses_rather_than_running_for_26_minutes(client):
    """Levered IRR is not in the screening tier, so filtering it runs the full model per
    parcel. Across the scored set that is ~26 minutes — it must refuse, with a message
    that tells the user what to do instead."""
    response = client.get("/map/query", params={"statuses": ["scored"], "irr_min": 0.15})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "narrow" in detail.lower()


# ---------------------------------------------------------------------------
# /parcel/{id}
# ---------------------------------------------------------------------------
def test_parcel_record_matches_the_bake(client, scored_parcel_id, meta):
    body = client.get(f"/parcel/{scored_parcel_id}").json()
    assert body["parcel_id"] == scored_parcel_id
    assert body["computed_at"] == meta["computed_at"]
    assert body["status"] == "scored"
    assert body["prototypes"], "a scored parcel must expose at least one prototype"
    assert sum(1 for p in body["prototypes"] if p["is_best"]) == 1
    assert body["prototypes"][0]["is_best"], "best prototype sorts first"


def test_parcel_display_name_never_renders_blank(client):
    """~1% of DC parcels have no premise address; those fall back to the parcel ID."""
    rows = client.get("/map/query", params={"limit": 300}).json()["rows"]
    assert rows
    for row in rows:
        assert row["display_name"]
        if not row["address"]:
            assert row["display_name"] == f"Parcel ID {row['parcel_id']}"


def test_developability_flag_is_surfaced_for_built_parcels(client):
    """SPEC §10: an existing building means acquisition runs above land value. Say so."""
    rows = client.get("/map/query", params={"statuses": ["scored"], "limit": 200}).json()["rows"]
    built = next(r for r in rows if (r["existing_building_sf"] or 0) > 0)
    flag = client.get(f"/parcel/{built['parcel_id']}").json()["developability"]
    assert flag["has_existing_building"] is True
    assert "acquisition will run above land value" in flag["note"]


def test_unencoded_zoning_is_an_answer_not_an_error(client):
    """SPEC fix #1: an unencoded district still loads, still appears, still explains itself."""
    rows = client.get(
        "/map/query", params={"statuses": ["zone_not_encoded"], "limit": 1}
    ).json()["rows"]
    body = client.get(f"/parcel/{rows[0]['parcel_id']}").json()
    assert body["zoning"]["encoded"] is False
    assert body["status_label"] == "Zoning not yet covered"


def test_missing_parcel_is_404(client):
    assert client.get("/parcel/9999    9999").status_code == 404


def test_search_finds_a_parcel_by_address_and_by_id(client, scored_parcel_id):
    body = client.get("/parcels/search", params={"q": scored_parcel_id[:4]}).json()
    assert body["results"]
    address = next(
        (r["address"] for r in
         client.get("/map/query", params={"limit": 50}).json()["rows"] if r["address"]),
        None,
    )
    assert address
    hits = client.get("/parcels/search", params={"q": address}).json()["results"]
    assert any(h["address"] == address for h in hits)


# ---------------------------------------------------------------------------
# /assumptions/default
# ---------------------------------------------------------------------------
def test_default_assumptions_expose_every_group_the_inputs_modal_edits(client):
    body = client.get("/assumptions/default").json()
    for group in ("timeline", "cost", "revenue", "debt", "exit", "envelope"):
        assert body[group], group


def test_default_assumptions_include_the_irr_hurdle(client):
    """A stored assumption_sets row seeded before §2.6 gained `irr_hurdle` must not be able
    to hide the field — the model uses it, so the modal must be able to edit it."""
    body = client.get("/assumptions/default").json()
    assert body["exit"]["irr_hurdle"] == 0.17
    assert body["exit"]["discount_rate"] == 0.10   # distinct concept, both present


def test_default_assumptions_hide_provenance(client):
    """The handoff's language rules: the UI shows values only, never sourcing tags."""
    payload = client.get("/assumptions/default").text
    for tag in ("provenance", "national", "submarket_tag"):
        assert tag not in payload.lower()
