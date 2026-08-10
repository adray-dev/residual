"""Stage D phase 1 gate — the API core against the real baked database.

These are contract tests, not unit tests: they run against the live Postgres the bake
wrote, because the thing worth proving is that the endpoints agree with the data as it
actually exists, not with a fixture someone hand-wrote to match the code.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from api import vocabulary as vocab
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
    """SPEC §9: every parcel gets a row and every color is explainable, so the status
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
        "binding_constraint", "binding_constraint_short", "status", "tier",
        "assumption_group", "assumption", "assumption_kind",
    }
    # The handoff's language rules, spot-checked.
    # "IRR", not a plain-language gloss: the audience reads pro formas, and the metric is
    # the primary one the table ranks on.
    assert labels["metric"]["irr"] == "IRR"
    assert labels["metric"]["ssl"] == "Parcel ID"
    assert labels["prototype"]["garden"] == "Garden walk-up"
    assert labels["construction"]["wood_v"] == "Wood frame"
    # Both tiers are named, because the drill-down must label that they differ.
    assert labels["tier"] == {
        "screening": "Screening estimate",
        "full": "Full underwriting",
    }


def test_every_editable_assumption_is_labeled_and_has_a_unit(meta, client):
    """The 1c modal is driven by /assumptions/default, so every key it will render needs a
    label and a unit kind. A key with a value but no unit would be shown raw — and `0.2`
    presented where `20%` was meant is a 100x error in the user's model, silently."""
    labels = meta["labels"]
    defaults = client.get("/assumptions/default").json()

    for group in ("timeline", "cost", "revenue", "debt", "exit", "envelope"):
        assert group in labels["assumption_group"], group
        for key, value in defaults[group].items():
            if key in vocab.HIDDEN_ASSUMPTION_KEYS:
                assert key not in labels["assumption"], f"{key} is hidden but also labeled"
                continue
            assert key in labels["assumption"], f"{group}.{key} has no label"
            assert key in labels["assumption_kind"], f"{group}.{key} has no unit kind"
            # A labeled input must be a scalar the modal can put in one field.
            assert isinstance(value, (int, float)) and not isinstance(value, bool), key

    assert set(labels["assumption"]) == set(labels["assumption_kind"])
    assert set(labels["assumption_kind"].values()) <= {
        "percent", "money", "months", "years", "rate", "number"
    }


def test_no_labeled_assumption_is_one_the_engine_would_ignore(meta, client):
    """`build_assumptions` drops unknown keys silently. An input offered in the modal that
    the engine then ignores looks like the model disagreeing with the user."""
    defaults = client.get("/assumptions/default").json()
    known = {
        key
        for group in ("timeline", "cost", "revenue", "debt", "exit", "envelope")
        for key in defaults[group]
    }
    assert set(meta["labels"]["assumption"]) <= known


def test_unencoded_zoning_is_never_called_exempt(meta):
    """`zone_not_encoded` means WE have not encoded the district — D-6, CG-4, ARTS-2 and
    other downtown districts among the most developable land in the city. Labelling it
    "exempt" would tell a user those parcels cannot be developed, which is false: the gap
    is in our coverage, not in their development rights."""
    label = meta["labels"]["status"]["zone_not_encoded"]
    assert "exempt" not in label.lower(), label
    assert meta["labels"]["status"]["exempt"] == "Public parcel — exempt"


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
    # Says the district is not covered and the parcel is not assessed. It deliberately does
    # NOT say "exempt": these are ordinary districts (D-6, CG-4, ARTS-2) whose rules we have
    # not encoded, not land that cannot be developed.
    assert body["status_label"] == "Zoning assessment pending"


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


# ---------------------------------------------------------------------------
# the table's Return column (screen 1d)
# ---------------------------------------------------------------------------
def test_returns_are_computed_for_the_visible_page_only(client):
    """Levered IRR is absent from the bake, so a table showing it runs the full model per
    row. Scoped to the page: the whole scored set would be ~26 minutes of engine time."""
    plain = client.get("/map/query", params={"statuses": ["scored"], "limit": 5}).json()
    withr = client.get(
        "/map/query", params={"statuses": ["scored"], "limit": 5, "with_returns": True}
    ).json()

    assert all(row["irr"] is None for row in plain["rows"])
    assert any(row["irr"] is not None for row in withr["rows"])
    # Same rows, same order — the flag adds a column, it does not change the query.
    assert [r["parcel_id"] for r in plain["rows"]] == [r["parcel_id"] for r in withr["rows"]]


def test_a_page_return_matches_a_direct_underwrite(client):
    row = client.get(
        "/map/query", params={"statuses": ["scored"], "limit": 1, "with_returns": True}
    ).json()["rows"][0]
    full = client.get(f"/parcel/{row['parcel_id']}/underwrite").json()
    assert row["irr"] == pytest.approx(full["returns"]["irr"], abs=1e-9)


def test_an_oversized_page_of_returns_is_refused_with_a_number(client):
    """Refusing with the actual limit beats timing out, and beats silently truncating."""
    response = client.get(
        "/map/query", params={"statuses": ["scored"], "limit": 500, "with_returns": True}
    )
    assert response.status_code == 422
    assert "limit" in response.json()["detail"].lower()


def test_sorting_is_server_side_across_the_whole_match_set(client):
    """The table sorts by asking the server, never by reordering the loaded page — sorting
    a slice and presenting it as the ranking is the worst thing a table can do."""
    for key in ("rlv_total", "noi", "total_development_cost", "yield_on_cost"):
        desc = client.get(
            "/map/query", params={"statuses": ["scored"], "limit": 25, "sort_key": key}
        ).json()
        values = [r[key] for r in desc["rows"] if r[key] is not None]
        assert values == sorted(values, reverse=True), key
        assert desc["sort_key"] == key

        asc = client.get(
            "/map/query",
            params={"statuses": ["scored"], "limit": 25, "sort_key": key, "sort_dir": "asc"},
        ).json()
        ascending = [r[key] for r in asc["rows"] if r[key] is not None]
        assert ascending == sorted(ascending), key


# ---------------------------------------------------------------------------
# /parcels/search — the 1a search field
# ---------------------------------------------------------------------------
def test_search_finds_a_parcel_by_address_and_by_id(client):
    row = client.get("/map/query", params={"statuses": ["scored"], "limit": 1}).json()["rows"][0]

    by_id = client.get("/parcels/search", params={"q": row["parcel_id"]}).json()["results"]
    assert any(hit["parcel_id"] == row["parcel_id"] for hit in by_id)

    if row["address"]:
        by_address = client.get("/parcels/search", params={"q": row["address"]}).json()["results"]
        assert any(hit["parcel_id"] == row["parcel_id"] for hit in by_address)


def test_search_matches_a_ward_the_way_a_person_types_it(client):
    """Wards are stored as `ward_6`; nobody types that. The docstring claimed ward was
    searchable long before the WHERE clause actually mentioned the column."""
    for term in ("Ward 6", "ward 6", "ward_6"):
        results = client.get("/parcels/search", params={"q": term}).json()["results"]
        assert results, term
        assert all(hit["ward"] == "Ward 6" for hit in results), term


def test_every_search_hit_carries_a_point_to_move_the_map_to(client):
    """Search on a map screen means "take me there", which needs a coordinate."""
    results = client.get("/parcels/search", params={"q": "Ward 6"}).json()["results"]
    for hit in results:
        assert hit["lon"] is not None and hit["lat"] is not None, hit["parcel_id"]
        # Inside DC's bounding box, so a bad centroid cannot silently fly the map to null island.
        assert -77.2 < hit["lon"] < -76.8, hit
        assert 38.7 < hit["lat"] < 39.1, hit


def test_search_never_says_ssl(client):
    """The identifier is "Parcel ID" everywhere a person can read it, fallbacks included."""
    results = client.get("/parcels/search", params={"q": "Ward 6"}).json()["results"]
    for hit in results:
        assert "SSL" not in (hit["display_name"] or "").upper().split()


def test_an_empty_search_returns_nothing_rather_than_everything(client):
    assert client.get("/parcels/search", params={"q": ""}).json()["results"] == []
    assert client.get("/parcels/search", params={"q": "   "}).json()["results"] == []


# ---------------------------------------------------------------------------
# §5.1: the engine's build-type ids never reach a user.
# ---------------------------------------------------------------------------
FORBIDDEN_IN_UI = "5-over-1"


def test_meta_labels_never_expose_the_engine_build_id(meta):
    """Both wood and concrete multifamily must render as one name.

    The label block is what every surface reads, so if `5-over-1` survives here it survives
    into the popup, the table, the drill-down, compare and both exports at once.
    """
    labels = meta["labels"]["prototype"]
    assert labels["5-over-1"] == "Multifamily"
    assert labels["midrise"] == "Multifamily"
    assert FORBIDDEN_IN_UI not in labels.values()
    # Three names over the four prototypes that compete.
    assert {v for k, v in labels.items() if k != "garden"} == {
        "Townhome", "Multifamily", "High-rise",
    }


def test_a_refusal_names_the_product_not_the_prototype(client):
    """`engine/` is pure and raises "5-over-1 requires >= 6,000 SF lot" — correct for a log
    and wrong for a user. The API boundary translates it; this pins that it still does."""
    from api import vocabulary as vocab

    engine_message = "5-over-1 requires >= 6,000 SF lot; parcel is 4,000 SF"
    assert vocab.humanize(engine_message) == (
        "Multifamily requires >= 6,000 SF lot; parcel is 4,000 SF"
    )
    assert FORBIDDEN_IN_UI not in vocab.humanize(engine_message)

    # A real refusal, end to end: ask for a build the parcel cannot take and read the 422.
    rows = client.get(
        "/map/query", params={"statuses": ["scored"], "limit": 40}
    ).json()["rows"]
    for row in rows:
        response = client.get(
            f"/parcel/{row['parcel_id'].replace(' ', '%20')}/underwrite",
            params={"prototype_id": "5-over-1"},
        )
        if response.status_code == 422:
            assert FORBIDDEN_IN_UI not in response.text, response.text
            assert "Multifamily" in response.json()["detail"]
            break


def test_no_endpoint_leaks_the_engine_build_id_in_prose(client, scored_parcel_id):
    """Sweep the read endpoints. Wire FIELDS may carry the id — SPEC's convention is that
    payload keys and values are the engine's — but no human-readable string may."""
    import json

    def prose(node):
        """Every display string in a payload, ignoring the raw `prototype_id` field."""
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"prototype_id", "best_prototype_id"}:
                    continue
                yield from prose(value)
        elif isinstance(node, list):
            for item in node:
                yield from prose(item)
        elif isinstance(node, str):
            yield node

    encoded = scored_parcel_id.replace(" ", "%20")
    for path in (
        "/meta",
        f"/parcel/{encoded}",
        f"/parcel/{encoded}/underwrite",
        "/map/query?statuses=scored&limit=25&with_returns=true",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        offenders = [s for s in prose(response.json()) if FORBIDDEN_IN_UI in s]
        assert not offenders, f"{path} leaked: {json.dumps(offenders[:3])}"
