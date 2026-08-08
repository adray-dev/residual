"""Stage D phase 3 gate — the tile build (SPEC §10).

Two halves, for two different failure modes:

  * `bin_index` and `build_features` are pure, so they are tested directly with synthetic
    rows. What they encode is the map's entire colour contract — a parcel's shade is a
    lookup on an attribute baked here, and there is no server call to correct it later.
    A silent off-by-one in the bin puts the wrong colour on 132,632 parcels.
  * the area floor and the per-objective ramps are claims about the real data, so they run
    against the baked database and skip cleanly when there isn't one.
"""
from __future__ import annotations

import os

import pytest

from data import repositories as repo
from tiles.build_tiles import (
    BIN_FIELDS,
    MIN_RENDERABLE_AREA_M2,
    TileReport,
    bin_index,
    build_features,
)


def _database_url() -> str | None:
    """DATABASE_URL, which importing `data.repositories` has already loaded from `.env`."""
    return os.environ.get("DATABASE_URL") or None


# ---------------------------------------------------------------------------
# bin_index — the diverging ramp
# ---------------------------------------------------------------------------
NEG = [-432641.0, -245716.0, -45951.0]
POS = [157357.0, 329605.0, 509676.0]


def test_bin_index_matches_the_documented_ramp():
    """The worked example in `bin_index`'s docstring, asserted rather than described."""
    assert bin_index(-500_000, NEG, POS) == -4
    assert bin_index(-300_000, NEG, POS) == -3
    assert bin_index(-100_000, NEG, POS) == -2
    assert bin_index(-10_000, NEG, POS) == -1
    assert bin_index(0, NEG, POS) == 1
    assert bin_index(200_000, NEG, POS) == 2
    assert bin_index(400_000, NEG, POS) == 3
    assert bin_index(900_000, NEG, POS) == 4


def test_unscored_is_its_own_bin_not_a_value():
    """0 is reserved for "no number", so an unscored parcel can never borrow a value shade."""
    assert bin_index(None, NEG, POS) == 0


def test_zero_prices_as_the_weakest_positive_not_a_negative():
    """The split is "does this pencil?" — exactly zero pencils, barely."""
    assert bin_index(0.0, NEG, POS) == 1
    assert bin_index(-0.01, NEG, POS) == -1


def test_bins_are_half_open_so_a_value_on_a_break_goes_up():
    """`[lo, hi)`: bisect_right, not bisect_left. Off by one here shifts a whole arm."""
    assert bin_index(POS[0], NEG, POS) == 2          # on the break -> upper bin
    assert bin_index(POS[0] - 0.01, NEG, POS) == 1   # just under -> lower bin
    assert bin_index(NEG[0], NEG, POS) == -3
    assert bin_index(NEG[0] - 0.01, NEG, POS) == -4


def test_three_breaks_per_arm_yield_exactly_the_eight_stops():
    """The handoff's 8-stop ramp, redistributed around zero: -4..-1 and 1..4, no gaps."""
    values = [-1e9, -500_000, -300_000, -100_000, -10_000,
              0, 200_000, 400_000, 900_000, 1e9]
    assert {bin_index(v, NEG, POS) for v in values} == {-4, -3, -2, -1, 1, 2, 3, 4}


def test_an_empty_arm_still_never_returns_the_unscored_bin():
    """A batch with no negative parcels leaves `negative_breaks` empty. The negative arm
    must collapse to -1, not to 0 — 0 means "unscored" and would mis-shade a real value."""
    assert bin_index(-5.0, [], POS) == -1
    assert bin_index(5.0, NEG, []) == 1


# ---------------------------------------------------------------------------
# build_features — what actually lands in a tile
# ---------------------------------------------------------------------------
def _row(ssl, status="scored", **overrides):
    row = {
        "ssl": ssl,
        "prototype_id": "midrise_5_1",
        "status": status,
        "rlv_total": 200_000.0,
        "rlv_per_buildable_sf": 42.0,
        "feasibility_gap": 150_000.0,
        "confidence": 0.7,
        "was_invalid": False,
        "area_m2": 500.0,
        "geometry": '{"type":"Polygon","coordinates":[[[0,0],[0,1],[1,1],[0,0]]]}',
    }
    row.update(overrides)
    return row


@pytest.fixture
def fake_scan(monkeypatch):
    """Drive `build_features` off synthetic rows, with a distinct ramp per objective."""
    def install(rows):
        ramps = {
            "rlv_total":            {"negative_breaks": NEG, "positive_breaks": POS},
            # Deliberately different breaks: if an objective ever read another
            # objective's ramp, these bins would come out wrong.
            "rlv_per_buildable_sf": {"negative_breaks": [-50.0, -20.0, -5.0],
                                     "positive_breaks": [10.0, 30.0, 60.0]},
            "gap":                  {"negative_breaks": [-9e6, -1e6, -1e5],
                                     "positive_breaks": [1e5, 1e6, 9e6]},
        }
        monkeypatch.setattr(repo, "objective_ramp",
                            lambda conn, objective, batch: ramps[objective])
        monkeypatch.setattr(repo, "iter_map_geojson", lambda conn, batch: iter(rows))
        report = TileReport()
        return list(build_features(None, None, report)), report
    return install


def test_the_tile_carries_exactly_the_documented_attributes(fake_scan):
    features, _ = fake_scan([_row("0123    0456")])
    assert features[0]["properties"].keys() == {
        "id", "status", "proto", "rlv", "rlv_sf", "gap", "conf",
        "bin", "bin_sf", "bin_gap",
    }


def test_ssl_never_appears_in_a_tile(fake_scan):
    """The handoff's rule: the parcel identifier travels as `id`. Tile attributes are
    readable in devtools, so "SSL" leaking here leaks it to the user."""
    features, _ = fake_scan([_row("0123    0456")])
    properties = features[0]["properties"]
    assert "ssl" not in properties
    assert properties["id"] == "0123    0456"


def test_each_objective_is_binned_against_its_own_ramp(fake_scan):
    """Regression guard. `objective_ramp` falls back to the default objective for an
    unknown key rather than raising, so a typo in BIN_FIELDS would silently colour the
    gap ramp with RLV breaks and nothing would look obviously wrong."""
    features, _ = fake_scan([
        _row("A", rlv_total=200_000.0, rlv_per_buildable_sf=42.0, feasibility_gap=150_000.0)
    ])
    properties = features[0]["properties"]
    assert properties["bin"] == 2       # 200,000 against POS
    assert properties["bin_sf"] == 3    # 42 against [10, 30, 60]
    assert properties["bin_gap"] == 2   # 150,000 against [1e5, 1e6, 9e6]


def test_non_scored_parcels_get_the_unscored_bin_even_when_a_number_exists(fake_scan):
    """A status row can still carry an RLV from a partial run. It must not colour as a
    value — SPEC §10 gives non-scored parcels their own quiet shade."""
    features, _ = fake_scan([_row("A", status="infeasible")])
    properties = features[0]["properties"]
    assert (properties["bin"], properties["bin_sf"], properties["bin_gap"]) == (0, 0, 0)
    assert properties["status"] == "infeasible"
    # The raw numbers still travel — the drill-down explains them; only the colour is muted.
    assert properties["rlv"] == 200_000.0


def test_the_status_sentinel_does_not_leak_as_a_prototype(fake_scan):
    features, _ = fake_scan([_row("A", status="exempt", prototype_id=repo.NONE_PROTOTYPE)])
    assert features[0]["properties"]["proto"] is None


def test_omissions_are_counted_and_named_never_silent(fake_scan):
    """The build's headline claim is that features + omissions reconcile to the scan."""
    rows = [
        _row("keep"),
        _row("nogeom", geometry=None),
        _row("sliver", area_m2=0.0149),
        _row("repaired", was_invalid=True),
    ]
    features, report = fake_scan(rows)

    assert report.features == 2
    assert report.skipped_no_geom == 1
    assert report.skipped_too_small == 1
    assert sorted(report.skipped_ssls) == ["nogeom", "sliver"]
    assert report.features + len(report.skipped_ssls) == len(rows)
    assert report.invalid_repaired == 1
    assert {f["properties"]["id"] for f in features} == {"keep", "repaired"}


def test_a_parcel_exactly_on_the_area_floor_is_kept(fake_scan):
    """The floor is `< MIN`, so a parcel measuring exactly the threshold survives."""
    features, report = fake_scan([_row("edge", area_m2=MIN_RENDERABLE_AREA_M2)])
    assert report.skipped_too_small == 0
    assert len(features) == 1


def test_status_counts_cover_every_emitted_feature(fake_scan):
    rows = [_row("a"), _row("b", status="exempt"), _row("c", status="exempt"),
            _row("d", geometry=None)]
    features, report = fake_scan(rows)
    assert report.status_counts == {"scored": 1, "exempt": 2}
    assert sum(report.status_counts.values()) == report.features == len(features)


# ---------------------------------------------------------------------------
# Claims about the real baked data
# ---------------------------------------------------------------------------
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


def test_the_area_floor_never_drops_a_scored_parcel(conn):
    """`MIN_RENDERABLE_AREA_M2` is only allowed to catch surveying slivers. The moment it
    would omit a parcel the engine actually priced, the map is lying by omission and this
    fails rather than shipping a quiet gap."""
    batch = repo.latest_batch_at(conn)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT b.ssl, ST_Area(p.parcel_geom::geography) AS area_m2, b.status
                 FROM bake_results b JOIN parcels p USING (ssl)
                WHERE b.computed_at = %s AND b.is_best
                  AND p.parcel_geom IS NOT NULL
                  AND ST_Area(p.parcel_geom::geography) < %s
                ORDER BY area_m2""",
            (batch, MIN_RENDERABLE_AREA_M2),
        )
        under_floor = cur.fetchall()

    scored = [r for r in under_floor if r["status"] == "scored"]
    assert not scored, (
        f"{len(scored)} scored parcel(s) fall below the {MIN_RENDERABLE_AREA_M2:g} m² "
        f"tile floor and would vanish from the map: "
        f"{[(r['ssl'], round(r['area_m2'], 4)) for r in scored[:5]]}"
    )


def test_every_map_objective_resolves_to_its_own_ramp(conn):
    """`objective_ramp` whitelists via `.get` with a default, so an unrecognised objective
    comes back as `rlv_total`'s ramp instead of an error. Pin that every key the tile build
    asks for is genuinely recognised."""
    batch = repo.latest_batch_at(conn)
    ramps = {o: repo.objective_ramp(conn, o, batch) for o in BIN_FIELDS}

    for objective, ramp in ramps.items():
        assert ramp["objective"] == objective
        assert objective in repo.MAP_OBJECTIVES
        assert ramp["negative_count"] + ramp["positive_count"] > 0, (
            f"{objective} has no scored parcels to bin"
        )

    # Different measures, so different breaks. Identical ramps would mean a fallback fired.
    breaks = {o: tuple(r["positive_breaks"]) for o, r in ramps.items()}
    assert len(set(breaks.values())) == len(breaks), f"ramps collapsed together: {breaks}"


def test_the_ramp_breaks_ascend_so_bisect_is_meaningful(conn):
    """`bin_index` uses bisect over these lists; unsorted breaks would bin silently wrong."""
    batch = repo.latest_batch_at(conn)
    for objective in BIN_FIELDS:
        ramp = repo.objective_ramp(conn, objective, batch)
        for arm in ("negative_breaks", "positive_breaks"):
            values = ramp[arm]
            assert values == sorted(values), f"{objective}.{arm} is not ascending: {values}"
