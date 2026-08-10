"""The draw-an-area filter, against the real baked database.

A drawn polygon is the one filter that cannot be a tile expression — point-in-polygon is
not expressible over tile attributes — so unlike every other filter in the pane, the server
is the only thing that knows which parcels are in. That makes these tests the whole safety
net for the feature, which is why they cover the geometry plumbing (SRID, WKT, index) and
not just the happy path.

They also pin the two defects that made the original scaffolding unusable: this PostGIS is
built without JSON-C, so `ST_GeomFromGeoJSON` raises on every input, and even where it
works it returns SRID 0 against a 4326 column.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from data import repositories as repo

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"
)

# A ring over the West End / Foggy Bottom grid — dense, entirely inside DC, and small
# enough that the count is a meaningful narrowing rather than most of the city.
RING = [
    [-77.05, 38.90],
    [-77.04, 38.90],
    [-77.04, 38.91],
    [-77.05, 38.91],
    [-77.05, 38.90],
]


def polygon(ring=None) -> dict:
    return {"type": "Polygon", "coordinates": [ring or RING]}


def body(**filters) -> dict:
    return {"filters": {"statuses": ["scored"], **filters}, "limit": 5}


@pytest.fixture(scope="module")
def client():
    from api.main import app
    with TestClient(app) as c:
        yield c


# --- the query itself -------------------------------------------------------
def test_polygon_narrows_the_result(client):
    everywhere = client.post("/map/query", json=body()).json()["total"]
    inside = client.post("/map/query", json=body(drawn_polygon=polygon())).json()

    assert inside["total"] > 0, "the test ring covers built-up DC and must match parcels"
    assert inside["total"] < everywhere
    assert len(inside["rows"]) <= 5


def test_every_returned_parcel_really_intersects_the_ring(client):
    """The claim the map makes. Verified against PostGIS one parcel at a time, so a WHERE
    clause that quietly matched on the bounding box instead would fail here."""
    rows = client.post("/map/query", json=body(drawn_polygon=polygon())).json()["rows"]
    assert rows

    wkt = repo.polygon_wkt(polygon())
    with repo.connect() as conn, conn.cursor() as cur:
        for row in rows:
            cur.execute(
                "SELECT ST_Intersects(parcel_geom, ST_SetSRID(ST_GeomFromText(%s), 4326))"
                " AS hit FROM parcels WHERE ssl = %s",
                (wkt, row["parcel_id"]),
            )
            assert cur.fetchone()["hit"] is True, row["parcel_id"]


def test_it_ands_with_the_other_filters(client):
    """A drawn area must narrow alongside the pane, not replace it. An OR here would be
    invisible in the UI — the count would simply be too big."""
    area_only = client.post("/map/query", json=body(drawn_polygon=polygon())).json()["total"]
    proto_only = client.post("/map/query", json=body(prototypes=["garden"])).json()["total"]
    both = client.post(
        "/map/query", json=body(drawn_polygon=polygon(), prototypes=["garden"])
    ).json()["total"]

    assert both <= area_only
    assert both <= proto_only


def test_a_ring_over_open_water_matches_nothing(client):
    """The Potomac, mid-channel. An empty result is a correct answer and must not error."""
    river = [
        [-77.055, 38.870],
        [-77.050, 38.870],
        [-77.050, 38.874],
        [-77.055, 38.874],
        [-77.055, 38.870],
    ]
    response = client.post("/map/query", json=body(drawn_polygon=polygon(river)))
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_a_ring_smaller_than_one_parcel_still_selects_it(client):
    """Intersects, not contains. Dropping a tiny loop inside a lot means that lot — the
    alternative is a selection tool that returns nothing when you aim carefully."""
    with repo.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT p.ssl, ST_X(ST_PointOnSurface(parcel_geom)) AS lon,"
            "       ST_Y(ST_PointOnSurface(parcel_geom)) AS lat"
            " FROM parcels p JOIN bake_results b ON b.ssl = p.ssl"
            " WHERE b.is_best AND b.status = 'scored'"
            "   AND b.computed_at = (SELECT MAX(computed_at) FROM bake_results)"
            " LIMIT 1"
        )
        parcel = cur.fetchone()

    d = 0.00002  # ~2 m
    lon, lat = parcel["lon"], parcel["lat"]
    speck = [
        [lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d],
        [lon - d, lat + d], [lon - d, lat - d],
    ]
    rows = client.post("/map/query", json=body(drawn_polygon=polygon(speck))).json()["rows"]
    assert parcel["ssl"] in [r["parcel_id"] for r in rows]


def test_polygon_composes_with_bounds(client):
    """Both are geometry clauses and both are ANDed; a ring outside the viewport is empty,
    not the whole ring."""
    elsewhere = {
        "bounds": {
            "min_lon": -76.99, "min_lat": 38.86, "max_lon": -76.97, "max_lat": 38.88,
        },
        "filters": {"statuses": ["scored"], "drawn_polygon": polygon()},
        "limit": 5,
    }
    assert client.post("/map/query", json=elsewhere).json()["total"] == 0


# --- validation: a bad ring is a 422 with a sentence, never a 500 ------------
@pytest.mark.parametrize(
    "bad, expected",
    [
        ({"type": "Point", "coordinates": [-77.02, 38.91]}, "Polygon"),
        # Two corners enclose no area.
        ({"type": "Polygon", "coordinates": [[[-77.02, 38.91], [-77.01, 38.91]]]}, "corners"),
        # Unclosed ring — RFC 7946 requires the first position repeated. Four positions,
        # so it clears the minimum-corners check and is refused for the closure alone.
        (
            {"type": "Polygon", "coordinates": [[
                [-77.02, 38.91], [-77.01, 38.91], [-77.01, 38.92], [-77.02, 38.92]]]},
            "closed",
        ),
        # A hole. One exterior ring only.
        (
            {"type": "Polygon", "coordinates": [
                [[-77.02, 38.91], [-77.01, 38.91], [-77.01, 38.92], [-77.02, 38.91]],
                [[-77.018, 38.912], [-77.012, 38.912], [-77.012, 38.918],
                 [-77.018, 38.912]],
            ]},
            "one ring",
        ),
        # Somewhere in the Atlantic. Nothing to select, and an unbounded ring is a way to
        # ask PostGIS to scan the table.
        (
            {"type": "Polygon", "coordinates": [[
                [-40.0, 38.91], [-39.0, 38.91], [-39.0, 39.0], [-40.0, 38.91]]]},
            "Washington DC",
        ),
        # A string where a number belongs.
        (
            {"type": "Polygon", "coordinates": [[
                [-77.02, 38.91], [-77.01, "x"], [-77.01, 38.92], [-77.02, 38.91]]]},
            "coordinate",
        ),
    ],
)
def test_a_malformed_ring_is_rejected(client, bad, expected):
    response = client.post("/map/query", json=body(drawn_polygon=bad))
    assert response.status_code == 422, response.text
    assert expected in response.text


def test_the_vertex_cap_is_enforced(client):
    """Bounded so one drawn shape cannot turn into an expensive scan or a huge body."""
    import math

    from api.schemas import MAX_DRAWN_VERTICES

    def circle(n: int) -> list[list[float]]:
        ring = [
            [-77.02 + 0.004 * math.cos(2 * math.pi * i / n),
             38.91 + 0.004 * math.sin(2 * math.pi * i / n)]
            for i in range(n)
        ]
        return [*ring, ring[0]]

    assert client.post(
        "/map/query", json=body(drawn_polygon=polygon(circle(MAX_DRAWN_VERTICES)))
    ).status_code == 200
    over = client.post(
        "/map/query", json=body(drawn_polygon=polygon(circle(MAX_DRAWN_VERTICES + 1)))
    )
    assert over.status_code == 422
    assert "corners" in over.text


# --- the geometry plumbing --------------------------------------------------
def test_wkt_conversion_round_trips_through_postgis():
    """`ST_GeomFromGeoJSON` is the obvious call and is unusable here — this PostGIS has no
    JSON-C, and it returns SRID 0 regardless. Both are pinned."""
    with repo.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT ST_SRID(g) AS srid, ST_IsValid(g) AS valid, ST_Area(g) AS area"
            " FROM (SELECT ST_SetSRID(ST_GeomFromText(%s), 4326) AS g) t",
            (repo.polygon_wkt(polygon()),),
        )
        row = cur.fetchone()
    assert row["srid"] == 4326
    assert row["valid"] is True
    assert row["area"] > 0


def test_the_polygon_clause_uses_the_spatial_index():
    """Without the GiST scan this is a sequential pass over 132k geometries on every
    keystroke-debounced count."""
    with repo.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "EXPLAIN SELECT count(*) FROM parcels p"
            " WHERE ST_Intersects(p.parcel_geom, ST_SetSRID(ST_GeomFromText(%s), 4326))",
            (repo.polygon_wkt(polygon()),),
        )
        plan = " ".join(r["QUERY PLAN"] for r in cur.fetchall())
    assert "parcels_geom_gix" in plan, plan
