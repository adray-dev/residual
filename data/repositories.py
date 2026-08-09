"""The only module that runs SQL (SPEC §7.3).

Plain parameterised SQL via psycopg3. Reads return the engine's dataclasses, so the
engine never learns that a database exists. Writes take plain dicts.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterable, Iterator, Mapping

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from engine.prototypes import PROTOTYPES
from engine.types import (
    Assumptions,
    ConstructionType,
    MarketData,
    Parcel,
    Prototype,
    Use,
    ZoningRules,
)

# `.env` is loaded here, at import of the one module that owns database access, because
# every entry point that needs a connection — uvicorn, `python -m bake.run_bake`,
# `python -m tiles.build_tiles`, pytest — reaches the database through this module and
# nothing else. Loading it in each entry point instead would mean four places to forget.
#
# `override=False`: a DATABASE_URL already exported in the shell wins over the file, so
# pointing a single command at another database stays a one-liner and CI, which sets the
# variable directly and ships no `.env`, is unaffected.
load_dotenv(override=False)

NONE_PROTOTYPE = "__none__"   # bake_results sentinel for status rows (SPEC §7.1)

# Every read that feeds the map or a table must be scoped to ONE batch, or retention's two
# retained batches (SPEC §9) return each parcel twice. This is that scope, named once so a
# new reader cannot quietly omit it. `run_bake` commits a batch atomically, so `max` never
# resolves to a half-written one.
LATEST_BATCH = "(SELECT max(computed_at) FROM bake_results)"

# The map's selectable objectives (SPEC §9/§10). Every one is a STORED bake_results column:
# the read path sorts, it never divides. `rlv_total` is the default — RLV/SF collapses to
# roughly a constant per zone/prototype/submarket, so coloring on it reads as a zoning map,
# while total RLV actually varies parcel to parcel. `is_best` is pinned to the same default
# objective at bake time, so the map colors the measure the bake optimized.
# Values are interpolated into SQL: this dict is the whitelist, never caller input.
MAP_OBJECTIVES = {
    "rlv_total": "b.rlv_total",
    "rlv_per_buildable_sf": "b.rlv_per_buildable_sf",
    "gap": "b.feasibility_gap",
}
DEFAULT_MAP_OBJECTIVE = "rlv_total"

_PARCEL_COLS = """
    ssl, lot_area_sf, zone_code, submarket_id, land_value, improvement_value,
    improvement_ratio, land_use_code, existing_building_sf, is_exempt, is_historic
"""

# `address` and `neighborhood` are DISPLAY fields, not model inputs, so they are read
# separately and never reach `Parcel` — SPEC §3.1 pins that dataclass's fields, and the
# engine has no business knowing a street name. Readers that render a label select this
# instead of `_PARCEL_COLS`.
_PARCEL_DISPLAY_COLS = _PARCEL_COLS.rstrip() + ", address, neighborhood\n"


def base_district(zone_code: str | None) -> str | None:
    """The base district of a zone code, with any overlay tag stripped.

    DC zone codes carry overlay tags after a slash: `R-3/GT` is the R-3 district inside the
    Georgetown overlay. The BASE district drives the envelope and the overlay is a separate
    modifier (not modeled in v1), so `parcels.zone_code` keeps the full code verbatim and
    only rule LOOKUP strips the tag. Stored data is never rewritten.
    """
    if not zone_code:
        return None
    return zone_code.split("/", 1)[0].strip() or None


def resolve_rules(
    rules_by_zone: Mapping[str, ZoningRules], zone_code: str | None
) -> ZoningRules | None:
    """Look up rules for a zone code: EXACT match first, base district second.

    Exact-first matters and is not just an optimisation. Not every slash is an overlay:
    Subtitle H names the Neighborhood Mixed-Use zones as base/overlay PAIRS that each carry
    their own standards (NMU-4/CP is FAR 2.0, NMU-4/WP is FAR 2.5, NMU-4/GA is 50 ft), so a
    bare `NMU-4` row would be wrong for every one of them. Encoding `NMU-4/CP` makes the
    exact match win; encoding only `R-3` still resolves `R-3/GT` through the fallback.

    This is the ONE definition of the matching rule. The bake resolves against its in-memory
    dict and `get_rules` resolves against the database, both through here, so the batch path
    and the live API path cannot drift apart.
    """
    if not zone_code:
        return None
    rules = rules_by_zone.get(zone_code)
    if rules is not None:
        return rules
    base = base_district(zone_code)
    if base is None or base == zone_code:
        return None
    return rules_by_zone.get(base)


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env — it is loaded "
            "automatically and does not need to be exported."
        )
    return url


def connect(url: str | None = None) -> psycopg.Connection:
    """Open a connection with dict rows. Callers own the lifecycle."""
    return psycopg.connect(url or database_url(), row_factory=dict_row)


@contextmanager
def connection(url: str | None = None) -> Iterator[psycopg.Connection]:
    conn = connect(url)
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# row -> dataclass
# ---------------------------------------------------------------------------
def _to_parcel(row: dict) -> Parcel:
    return Parcel(
        ssl=row["ssl"],
        lot_area_sf=row["lot_area_sf"],
        zone_code=row["zone_code"],
        submarket_id=row["submarket_id"],
        land_value=row["land_value"],
        improvement_value=row["improvement_value"],
        land_use_code=row["land_use_code"],
        improvement_ratio=row["improvement_ratio"],
        existing_building_sf=row["existing_building_sf"] or 0.0,
        is_exempt=bool(row["is_exempt"]),
        is_historic=bool(row["is_historic"]),
    )


def _to_rules(row: dict) -> ZoningRules:
    return ZoningRules(
        district_code=row["district_code"],
        max_far=row["max_far"],
        max_height_ft=row["max_height_ft"],
        max_stories=row["max_stories"],
        lot_occupancy_pct=row["lot_occupancy"] or {},
        permitted_uses=[Use(u) for u in (row["permitted_uses"] or [])],
        parking_ratio=row["parking_ratio"] or {},
        requires_ground_floor_active=bool(row["requires_ground_floor_active"]),
        matter_of_right=bool(row["matter_of_right"]),
    )


def _to_prototype(row: dict) -> Prototype:
    # SPEC §7.1's `prototypes` table has no `min_lot_sf` column, but §3.1's Prototype
    # dataclass requires it (it is the admissibility gate). Both are pinned, so the
    # schema stays verbatim and `min_lot_sf` is read from the §5 table in
    # engine/prototypes.py — the canonical source for that value either way.
    min_lot_sf = PROTOTYPES[row["prototype_id"]].min_lot_sf
    return Prototype(
        prototype_id=row["prototype_id"],
        construction_type=ConstructionType(row["construction_type"]),
        min_stories=row["min_stories"],
        max_stories=row["max_stories"],
        min_lot_sf=min_lot_sf,
        efficiency_ratio=row["efficiency_ratio"],
        default_unit_mix=row["default_unit_mix"] or {},
        avg_unit_sf=row["avg_unit_sf"] or {},
        parking_type=row["parking_type"],
    )


# ---------------------------------------------------------------------------
# parcels
# ---------------------------------------------------------------------------
def get_parcel(conn, ssl: str) -> Parcel | None:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_PARCEL_COLS} FROM parcels WHERE ssl = %s", (ssl,))
        row = cur.fetchone()
    return _to_parcel(row) if row else None


def get_parcel_record(conn, ssl: str) -> dict | None:
    """The raw parcels row including the display fields (address, neighbourhood).

    The API needs both the engine's `Parcel` and the label in one round trip, so it reads
    this and calls `to_parcel(row)` rather than querying twice.
    """
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_PARCEL_DISPLAY_COLS} FROM parcels WHERE ssl = %s", (ssl,))
        return cur.fetchone()


# Public alias: callers holding a row from `get_parcel_record` build the engine dataclass
# from it without a second query.
to_parcel = _to_parcel


def parcels_in_bbox(conn, bounds: tuple[float, float, float, float]) -> list[Parcel]:
    """bounds = (min_lon, min_lat, max_lon, max_lat) in EPSG:4326."""
    min_lon, min_lat, max_lon, max_lat = bounds
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT {_PARCEL_COLS} FROM parcels
                WHERE parcel_geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                ORDER BY ssl""",
            (min_lon, min_lat, max_lon, max_lat),
        )
        return [_to_parcel(r) for r in cur.fetchall()]


def parcels_in_geo(conn, ward: str) -> list[Parcel]:
    """All parcels in a submarket (v1: a DC ward)."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_PARCEL_COLS} FROM parcels WHERE submarket_id = %s ORDER BY ssl",
            (ward,),
        )
        return [_to_parcel(r) for r in cur.fetchall()]


def iter_parcels(conn, batch_size: int = 5_000) -> Iterator[Parcel]:
    """Stream every parcel — the bake's input (SPEC §9). Server-side cursor."""
    with conn.cursor(name="parcels_scan") as cur:
        cur.itersize = batch_size
        cur.execute(f"SELECT {_PARCEL_COLS} FROM parcels ORDER BY ssl")
        for row in cur:
            yield _to_parcel(row)


def count_parcels(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM parcels")
        return cur.fetchone()["n"]


# ---------------------------------------------------------------------------
# reference data
# ---------------------------------------------------------------------------
def get_rules(conn, zone_code: str | None) -> ZoningRules | None:
    """None when the district is not yet encoded (fix #1) — the bake handles that.

    Resolves overlay-tagged codes the same way the bake does: exact match first, then the
    base district (`R-3/GT` → `R-3`). One query covers both — `resolve_rules` picks the
    winner — so the live path and the batch path share one matching rule.
    """
    base = base_district(zone_code)
    if base is None:
        return None
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM zoning_rules WHERE district_code IN (%s, %s)", (zone_code, base)
        )
        candidates = {r["district_code"]: _to_rules(r) for r in cur.fetchall()}
    return resolve_rules(candidates, zone_code)


def get_all_rules(conn) -> dict[str, ZoningRules]:
    """Whole encoded table in one read — the bake resolves rules per parcel from this."""
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM zoning_rules")
        return {r["district_code"]: _to_rules(r) for r in cur.fetchall()}


def get_market(conn, submarket_id: str | None, as_of: str | None = None) -> MarketData | None:
    """Latest (or as-of) residential market row for a submarket, with retail rent folded in."""
    if not submarket_id:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """SELECT * FROM market_data
               WHERE submarket_id = %s AND use_type = 'residential'
                 AND (%s::date IS NULL OR as_of <= %s::date)
               ORDER BY as_of DESC LIMIT 1""",
            (submarket_id, as_of, as_of),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cur.execute(
            """SELECT rent_psf FROM market_data
               WHERE submarket_id = %s AND use_type = 'retail'
                 AND (%s::date IS NULL OR as_of <= %s::date)
               ORDER BY as_of DESC LIMIT 1""",
            (submarket_id, as_of, as_of),
        )
        retail = cur.fetchone()

    return MarketData(
        submarket_id=row["submarket_id"],
        rent_psf_residential_monthly=row["rent_psf"],
        retail_rent_psf_annual=(retail or {}).get("rent_psf", 0.0),
        exit_cap_rate=row["exit_cap"],
        hard_cost_psf={
            ConstructionType(k): v for k, v in (row["cost_psf"] or {}).items()
        },
        as_of=row["as_of"].isoformat(),
        source=row["source"],
        input_provenance=dict(row["provenance"] or {}),
    )


def get_all_markets(conn, as_of: str | None = None) -> dict[str, MarketData]:
    """One MarketData per submarket — the bake reads this once, not per parcel."""
    with conn.cursor() as cur:
        cur.execute("SELECT submarket_id FROM submarkets ORDER BY submarket_id")
        ids = [r["submarket_id"] for r in cur.fetchall()]
    markets = {}
    for sid in ids:
        market = get_market(conn, sid, as_of)
        if market is not None:
            markets[sid] = market
    return markets


def get_prototypes(conn) -> list[Prototype]:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM prototypes ORDER BY prototype_id")
        return [_to_prototype(r) for r in cur.fetchall()]


def get_default_assumption_set(conn) -> Assumptions | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM assumption_sets WHERE is_default ORDER BY assumption_set_id LIMIT 1"
        )
        row = cur.fetchone()
    if row is None:
        return None
    return Assumptions(
        program=row["program"] or {},
        timeline=row["timeline"] or {},
        cost=row["cost"] or {},
        revenue=row["revenue"] or {},
        debt=row["debt"] or {},
        exit=row["exit"] or {},
        envelope=row["envelope"] or {},
    )


# ---------------------------------------------------------------------------
# bake results
# ---------------------------------------------------------------------------
_BAKE_INSERT = """
INSERT INTO bake_results (
    ssl, prototype_id, is_best, status, screening_rlv, feasibility_gap,
    rlv_total, rlv_per_buildable_sf, confidence, binding_constraint,
    noi, total_development_cost, yield_on_cost, profit_margin, exit_value,
    gross_sf, net_rentable_sf, unit_count, floors, computed_at
) VALUES (
    %(ssl)s, %(prototype_id)s, %(is_best)s, %(status)s, %(screening_rlv)s,
    %(feasibility_gap)s, %(rlv_total)s, %(rlv_per_buildable_sf)s,
    %(confidence)s, %(binding_constraint)s,
    %(noi)s, %(total_development_cost)s, %(yield_on_cost)s, %(profit_margin)s,
    %(exit_value)s, %(gross_sf)s, %(net_rentable_sf)s, %(unit_count)s, %(floors)s,
    %(computed_at)s
)
ON CONFLICT (ssl, prototype_id, computed_at) DO NOTHING
"""


def write_bake_results(conn, rows: Iterable[dict]) -> int:
    """Append bake rows. `prototype_id` defaults to the '__none__' sentinel (SPEC §7.1).

    Both ranking metrics are written by the bake, never derived on read. `rlv_total`
    defaults to `screening_rlv` (they are the same number under two names); status rows
    leave both NULL.

    The nine screening columns (v1.6) default to None rather than being required, because
    status rows genuinely have none of them — an exempt parcel has no NOI. Scored rows
    always supply all nine; `.get` is the sentinel path, not the normal one.
    """
    params = [
        {
            "ssl": r["ssl"],
            "prototype_id": r.get("prototype_id") or NONE_PROTOTYPE,
            "is_best": r.get("is_best", False),
            "status": r["status"],
            "screening_rlv": r.get("screening_rlv"),
            "feasibility_gap": r.get("feasibility_gap"),
            "rlv_total": r.get("rlv_total", r.get("screening_rlv")),
            "rlv_per_buildable_sf": r.get("rlv_per_buildable_sf"),
            "confidence": r.get("confidence"),
            "binding_constraint": r.get("binding_constraint"),
            "noi": r.get("noi"),
            "total_development_cost": r.get("total_development_cost"),
            "yield_on_cost": r.get("yield_on_cost"),
            "profit_margin": r.get("profit_margin"),
            "exit_value": r.get("exit_value"),
            "gross_sf": r.get("gross_sf"),
            "net_rentable_sf": r.get("net_rentable_sf"),
            "unit_count": r.get("unit_count"),
            "floors": r.get("floors"),
            "computed_at": r["computed_at"],
        }
        for r in rows
    ]
    if not params:
        return 0
    with conn.cursor() as cur:
        cur.executemany(_BAKE_INSERT, params)
    return len(params)


def latest_batch_at(conn) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute("SELECT max(computed_at) AS t FROM bake_results")
        return cur.fetchone()["t"]


def list_bake_batches(conn) -> list[datetime]:
    """Every retained batch, newest first (SPEC §9 keeps the last 2)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT computed_at AS t FROM bake_results ORDER BY computed_at DESC"
        )
        return [r["t"] for r in cur.fetchall()]


def best_prototypes_at(conn, computed_at: datetime) -> dict[str, str]:
    """{ssl: prototype_id} of the scored winners in one batch — the tie-margin incumbents."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT ssl, prototype_id FROM bake_results
               WHERE computed_at = %s AND is_best AND status = 'scored'""",
            (computed_at,),
        )
        return {r["ssl"]: r["prototype_id"] for r in cur.fetchall()}


def bake_status_counts(conn, computed_at: datetime | None = None) -> dict[str, int]:
    """Parcel counts by status in a batch (defaults to the latest)."""
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT status, count(*) AS n FROM bake_results
                WHERE computed_at = COALESCE(%s, {LATEST_BATCH})
                  AND is_best
                GROUP BY status ORDER BY n DESC""",
            (computed_at,),
        )
        return {r["status"]: r["n"] for r in cur.fetchall()}


def bake_rows_for_ssl(conn, ssl: str, computed_at: datetime | None = None) -> list[dict]:
    """Every prototype row baked for one parcel in a batch (defaults to the latest)."""
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT * FROM bake_results
                WHERE ssl = %s
                  AND computed_at = COALESCE(%s, {LATEST_BATCH})
                ORDER BY prototype_id""",
            (ssl, computed_at),
        )
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Stage D reads (SPEC §10)
# ---------------------------------------------------------------------------
# Columns the table view may sort on. A whitelist because the value is interpolated into
# SQL — never accept a caller's string here. Keys are the wire names; values are the
# qualified columns. Levered IRR is absent on purpose: it does not exist in the screening
# tier (SPEC §9), so it cannot be an ORDER BY.
SORTABLE = {
    "rlv_total": "b.rlv_total",
    "rlv_per_buildable_sf": "b.rlv_per_buildable_sf",
    "screening_rlv": "b.screening_rlv",
    "feasibility_gap": "b.feasibility_gap",
    "noi": "b.noi",
    "total_development_cost": "b.total_development_cost",
    "yield_on_cost": "b.yield_on_cost",
    "profit_margin": "b.profit_margin",
    "exit_value": "b.exit_value",
    "gross_sf": "b.gross_sf",
    "net_rentable_sf": "b.net_rentable_sf",
    "unit_count": "b.unit_count",
    "floors": "b.floors",
    "confidence": "b.confidence",
    "lot_area_sf": "p.lot_area_sf",
    "land_value": "p.land_value",
    "address": "p.address",
    "parcel_id": "b.ssl",
}

_MAP_SELECT = """
    b.ssl, b.prototype_id, b.status, b.screening_rlv, b.feasibility_gap,
    b.rlv_total, b.rlv_per_buildable_sf, b.confidence, b.binding_constraint,
    b.noi, b.total_development_cost, b.yield_on_cost, b.profit_margin,
    b.exit_value, b.gross_sf, b.net_rentable_sf, b.unit_count, b.floors,
    p.lot_area_sf, p.submarket_id, p.zone_code, p.land_value,
    p.existing_building_sf, p.address, p.neighborhood
"""


def _map_where(
    computed_at: datetime | None,
    bounds: tuple[float, float, float, float] | None,
    filters: Mapping[str, Any],
) -> tuple[list[str], list[Any]]:
    """Shared WHERE builder for the count and the page, so the two cannot disagree."""
    where = [f"b.computed_at = COALESCE(%s, {LATEST_BATCH})", "b.is_best"]
    params: list[Any] = [computed_at]

    if bounds is not None:
        where.append("p.parcel_geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)")
        params.extend(bounds)
    if filters.get("drawn_polygon"):
        # ST_Intersects, not &&: a drawn area is an explicit selection, so it should mean
        # the shape rather than the shape's bounding box.
        where.append("ST_Intersects(p.parcel_geom, ST_GeomFromGeoJSON(%s))")
        params.append(json.dumps(filters["drawn_polygon"]))
    if filters.get("statuses"):
        where.append("b.status = ANY(%s)")
        params.append(list(filters["statuses"]))
    if filters.get("wards"):
        where.append("p.submarket_id = ANY(%s)")
        params.append(list(filters["wards"]))
    if filters.get("neighborhoods"):
        where.append("p.neighborhood = ANY(%s)")
        params.append(list(filters["neighborhoods"]))
    if filters.get("prototypes"):
        where.append("b.prototype_id = ANY(%s)")
        params.append(list(filters["prototypes"]))
    if filters.get("rlv_min") is not None:
        where.append("b.rlv_total >= %s")
        params.append(filters["rlv_min"])
    if filters.get("rlv_max") is not None:
        where.append("b.rlv_total <= %s")
        params.append(filters["rlv_max"])
    if filters.get("min_confidence") is not None:
        where.append("b.confidence >= %s")
        params.append(filters["min_confidence"])
    return where, params


def map_query(
    conn,
    computed_at: datetime | None = None,
    bounds: tuple[float, float, float, float] | None = None,
    filters: Mapping[str, Any] | None = None,
    sort_key: str = DEFAULT_MAP_OBJECTIVE,
    sort_dir: str = "desc",
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """The table/compare read (SPEC §10). Returns (page, total_matching).

    Reads precomputed `bake_results` and NEVER runs the engine — that is the whole point of
    the two-tier split. Scoped to one batch AND `is_best`, so exactly one row per parcel.

    `sort_key` is looked up in the SORTABLE whitelist; anything else falls back to the
    default objective rather than reaching SQL.
    """
    filters = filters or {}
    where, params = _map_where(computed_at, bounds, filters)
    clause = " AND ".join(where)

    order_col = SORTABLE.get(sort_key, SORTABLE[DEFAULT_MAP_OBJECTIVE])
    direction = "ASC" if str(sort_dir).lower() == "asc" else "DESC"

    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT count(*) AS n FROM bake_results b JOIN parcels p USING (ssl)
                WHERE {clause}""",
            params,
        )
        total = cur.fetchone()["n"]

        cur.execute(
            f"""SELECT {_MAP_SELECT}
                FROM bake_results b JOIN parcels p USING (ssl)
                WHERE {clause}
                ORDER BY {order_col} {direction} NULLS LAST, b.ssl
                LIMIT %s OFFSET %s""",
            [*params, limit, offset],
        )
        return cur.fetchall(), total


def objective_ramp(
    conn, objective: str = DEFAULT_MAP_OBJECTIVE, computed_at: datetime | None = None
) -> dict:
    """Quantile breakpoints for the map's diverging value ramp.

    The handoff's 8-stop teal ramp assumes all-positive values, but 56% of scored DC
    parcels have a negative feasibility value and the tails run to ±$80M+, so a linear
    scale collapses the middle. The ramp therefore diverges at zero and is quantile-binned
    WITHIN each arm — computed here, once per bake, rather than by the client.

    Returns ascending break lists for each arm. Both arms get 4 bins, so the two together
    reproduce the handoff's 8 stops.
    """
    column = MAP_OBJECTIVES.get(objective, MAP_OBJECTIVES[DEFAULT_MAP_OBJECTIVE])
    quartiles = [0.25, 0.5, 0.75]

    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT
                    min({column}) AS lo,
                    max({column}) AS hi,
                    count(*) FILTER (WHERE {column} < 0) AS neg_n,
                    count(*) FILTER (WHERE {column} >= 0) AS pos_n,
                    percentile_cont(%s) WITHIN GROUP (ORDER BY {column})
                        FILTER (WHERE {column} < 0) AS neg_breaks,
                    percentile_cont(%s) WITHIN GROUP (ORDER BY {column})
                        FILTER (WHERE {column} >= 0) AS pos_breaks
                FROM bake_results b
                WHERE b.computed_at = COALESCE(%s, {LATEST_BATCH})
                  AND b.is_best AND b.status = 'scored' AND {column} IS NOT NULL""",
            (quartiles, quartiles, computed_at),
        )
        row = cur.fetchone()

    return {
        "objective": objective,
        "min": row["lo"],
        "max": row["hi"],
        "negative_breaks": list(row["neg_breaks"] or []),
        "positive_breaks": list(row["pos_breaks"] or []),
        "negative_count": row["neg_n"] or 0,
        "positive_count": row["pos_n"] or 0,
    }


def iter_map_geojson(conn, computed_at: datetime, batch_size: int = 5_000) -> Iterator[dict]:
    """Stream geometry + the best bake row per parcel, for the tile build (SPEC §10).

    Server-side cursor: 132,632 MultiPolygons will not fit comfortably in memory.

    Geometry is repaired on the way out. 19 DC parcels carry self-intersecting rings, and
    tippecanoe's behaviour on invalid input is not something to leave to chance — but the
    stored geometry is NOT rewritten, because the loader is the only thing that should own
    what is in the table. `was_invalid` reports how many needed it so a sudden jump is
    visible rather than silent.
    """
    with conn.cursor(name="map_geojson_scan") as cur:
        cur.itersize = batch_size
        cur.execute(
            """SELECT b.ssl, b.prototype_id, b.status, b.rlv_total, b.rlv_per_buildable_sf,
                      b.feasibility_gap, b.confidence, p.submarket_id,
                      NOT ST_IsValid(p.parcel_geom) AS was_invalid,
                      ST_Area(p.parcel_geom::geography) AS area_m2,
                      ST_AsGeoJSON(
                          ST_MakeValid(p.parcel_geom), 6
                      ) AS geometry
                 FROM bake_results b JOIN parcels p USING (ssl)
                WHERE b.computed_at = %s AND b.is_best
                  AND p.parcel_geom IS NOT NULL
                ORDER BY b.ssl""",
            (computed_at,),
        )
        for row in cur:
            yield row


# ---------------------------------------------------------------------------
# shortlists (SPEC §7.1, Stage D)
#
# Pure user state: named collections of parcel ids with no model output of their own. The
# 1f card metrics are read LIVE from the latest bake for the member parcels, so a shortlist
# can never go stale against a re-bake and never freezes a number. Scenarios are deliberately
# the opposite — they freeze, via `market_snapshot`.
# ---------------------------------------------------------------------------
def create_shortlist(conn, shortlist_id: str, name: str, user_id: str = "local") -> str:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO shortlists (shortlist_id, name, user_id)
               VALUES (%s, %s, %s) RETURNING shortlist_id""",
            (shortlist_id, name, user_id),
        )
        return cur.fetchone()["shortlist_id"]


def rename_shortlist(conn, shortlist_id: str, name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE shortlists SET name = %s WHERE shortlist_id = %s", (name, shortlist_id)
        )
        return cur.rowcount > 0


def delete_shortlist(conn, shortlist_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM shortlists WHERE shortlist_id = %s", (shortlist_id,))
        return cur.rowcount > 0


def list_shortlists(conn, user_id: str = "local") -> list[dict]:
    """Every list with its member count — the 1f sidebar, in one query."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT s.shortlist_id, s.name, s.created_at,
                      count(sp.ssl) AS parcel_count
                 FROM shortlists s
                 LEFT JOIN shortlist_parcels sp USING (shortlist_id)
                WHERE s.user_id = %s
                GROUP BY s.shortlist_id, s.name, s.created_at
                ORDER BY s.created_at""",
            (user_id,),
        )
        return cur.fetchall()


def get_shortlist(conn, shortlist_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT shortlist_id, name, created_at FROM shortlists WHERE shortlist_id = %s",
            (shortlist_id,),
        )
        return cur.fetchone()


def add_to_shortlist(conn, shortlist_id: str, ssl: str) -> bool:
    """Idempotent: adding a parcel twice is a no-op, not an error."""
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO shortlist_parcels (shortlist_id, ssl) VALUES (%s, %s)
               ON CONFLICT DO NOTHING""",
            (shortlist_id, ssl),
        )
        return cur.rowcount > 0


def remove_from_shortlist(conn, shortlist_id: str, ssl: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM shortlist_parcels WHERE shortlist_id = %s AND ssl = %s",
            (shortlist_id, ssl),
        )
        return cur.rowcount > 0


def shortlists_for_parcel(conn, ssl: str, user_id: str = "local") -> list[str]:
    """Which lists already hold this parcel — so the popup can show its state."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT sp.shortlist_id FROM shortlist_parcels sp
                 JOIN shortlists s USING (shortlist_id)
                WHERE sp.ssl = %s AND s.user_id = %s""",
            (ssl, user_id),
        )
        return [row["shortlist_id"] for row in cur.fetchall()]


def shortlist_members(conn, shortlist_id: str, computed_at: datetime | None = None) -> list[dict]:
    """Members with their CURRENT bake row — never a stored copy.

    Same column shape as `map_query`, so the same serializer renders both and a shortlist
    card cannot drift from the table row for the same parcel.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT {_MAP_SELECT}, sp.added_at
                  FROM shortlist_parcels sp
                  JOIN bake_results b ON b.ssl = sp.ssl
                  JOIN parcels p ON p.ssl = sp.ssl
                 WHERE sp.shortlist_id = %s
                   AND b.computed_at = COALESCE(%s, {LATEST_BATCH})
                   AND b.is_best
                 ORDER BY b.rlv_total DESC NULLS LAST, sp.added_at""",
            (shortlist_id, computed_at),
        )
        return cur.fetchall()


# ---------------------------------------------------------------------------
# scenarios (SPEC §7.1, §10)
# ---------------------------------------------------------------------------
def upsert_assumption_set(conn, row: Mapping) -> None:
    """Store the assumption set a scenario was run under, so it can be replayed exactly.

    A scenario references its assumption set by id, and an edited run has a set that exists
    nowhere else — writing it here is what makes the saved scenario reproducible rather
    than a set of numbers with no inputs behind them.
    """
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO assumption_sets
                   (assumption_set_id, name, is_default,
                    program, timeline, cost, revenue, debt, exit, envelope)
               VALUES (%(assumption_set_id)s, %(name)s, FALSE,
                       %(program)s, %(timeline)s, %(cost)s, %(revenue)s,
                       %(debt)s, %(exit)s, %(envelope)s)
               ON CONFLICT (assumption_set_id) DO NOTHING""",
            {
                "assumption_set_id": row["assumption_set_id"],
                "name": row.get("name"),
                **{
                    group: json.dumps(row.get(group) or {})
                    for group in ("program", "timeline", "cost", "revenue", "debt",
                                  "exit", "envelope")
                },
            },
        )


def save_scenario(conn, row: Mapping) -> str:
    """Freeze one underwrite. Returns the scenario id.

    `market_snapshot` is stamped here and never re-read (SPEC §7.1): a saved scenario is
    reproducible forever, even after a re-bake moves the market row underneath it. That is
    the opposite of a shortlist, which deliberately reads live so it cannot go stale.
    """
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO scenarios
                   (scenario_id, ssl, prototype_id, assumption_set_id, user_id,
                    market_snapshot, cashflow, outputs, saved_at)
               VALUES (%(scenario_id)s, %(ssl)s, %(prototype_id)s, %(assumption_set_id)s,
                       %(user_id)s, %(market_snapshot)s, %(cashflow)s, %(outputs)s, now())
               RETURNING scenario_id""",
            {
                "scenario_id": row["scenario_id"],
                "ssl": row["ssl"],
                "prototype_id": row["prototype_id"],
                "assumption_set_id": row["assumption_set_id"],
                "user_id": row.get("user_id", "local"),
                "market_snapshot": json.dumps(row["market_snapshot"]),
                "cashflow": json.dumps(row["cashflow"]),
                "outputs": json.dumps(row["outputs"]),
            },
        )
        return cur.fetchone()["scenario_id"]


_SCENARIO_SELECT = """
    s.scenario_id, s.ssl, s.prototype_id, s.assumption_set_id, s.user_id,
    s.market_snapshot, s.cashflow, s.outputs, s.saved_at,
    p.address, p.submarket_id,
    a.name AS assumption_set_name,
    a.program, a.timeline, a.cost, a.revenue, a.debt, a.exit, a.envelope
"""


def get_scenario(conn, scenario_id: str) -> dict | None:
    """One frozen scenario, with the assumption set it was run under."""
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT {_SCENARIO_SELECT}
                  FROM scenarios s
                  LEFT JOIN parcels p USING (ssl)
                  LEFT JOIN assumption_sets a USING (assumption_set_id)
                 WHERE s.scenario_id = %s""",
            (scenario_id,),
        )
        return cur.fetchone()


def list_scenarios(conn, user_id: str = "local", limit: int = 200) -> list[dict]:
    """Saved scenarios, newest first. Summary only — the frozen blobs stay out of the list."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT s.scenario_id, s.ssl, s.prototype_id, s.saved_at,
                      p.address, p.submarket_id,
                      s.outputs -> 'feasibility_value' ->> 'full' AS full_rlv
                 FROM scenarios s
                 LEFT JOIN parcels p USING (ssl)
                WHERE s.user_id = %s
                ORDER BY s.saved_at DESC
                LIMIT %s""",
            (user_id, limit),
        )
        return cur.fetchall()


def delete_scenario(conn, scenario_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM scenarios WHERE scenario_id = %s", (scenario_id,))
        return cur.rowcount > 0


def list_submarkets(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT submarket_id, name FROM submarkets ORDER BY submarket_id")
        return cur.fetchall()


def list_neighborhoods(conn, min_parcels: int = 25) -> list[str]:
    """Neighbourhood names for the geography filter chips.

    Thresholded because the assessment layer carries a long tail of near-empty names that
    would make the filter useless as a picker.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT neighborhood FROM parcels
               WHERE neighborhood IS NOT NULL
               GROUP BY neighborhood HAVING count(*) >= %s
               ORDER BY neighborhood""",
            (min_parcels,),
        )
        return [r["neighborhood"] for r in cur.fetchall()]


def search_parcels(conn, q: str, limit: int = 10) -> list[dict]:
    """Typeahead over address, parcel ID, ward and neighbourhood (the handoff's hint text).

    Prefix matches rank above interior matches so typing a house number behaves.
    """
    term = (q or "").strip()
    if not term:
        return []
    like = f"%{term}%"
    prefix = f"{term}%"
    with conn.cursor() as cur:
        cur.execute(
            """SELECT p.ssl, p.address, p.neighborhood, p.submarket_id, b.status
               FROM parcels p
               LEFT JOIN bake_results b
                 ON b.ssl = p.ssl AND b.is_best
                AND b.computed_at = (SELECT max(computed_at) FROM bake_results)
               WHERE p.address ILIKE %s OR p.ssl ILIKE %s OR p.neighborhood ILIKE %s
               ORDER BY (p.address ILIKE %s) DESC, (p.ssl ILIKE %s) DESC, p.address, p.ssl
               LIMIT %s""",
            (like, like, like, prefix, prefix, limit),
        )
        return cur.fetchall()


def prune_bake_batches(conn, keep: int = 2) -> int:
    """Delete all but the most recent `keep` batches (SPEC §9 batch retention)."""
    with conn.cursor() as cur:
        cur.execute(
            """DELETE FROM bake_results WHERE computed_at NOT IN (
                   SELECT DISTINCT computed_at FROM bake_results
                   ORDER BY computed_at DESC LIMIT %s)""",
            (keep,),
        )
        return cur.rowcount


def latest_bake_for_map(
    conn,
    bounds: tuple[float, float, float, float] | None = None,
    objective: str = DEFAULT_MAP_OBJECTIVE,
    filters: dict[str, Any] | None = None,
    computed_at: datetime | None = None,
) -> list[dict]:
    """Best-per-parcel rows from one batch (defaults to the latest), for the map.

    `objective` picks the sort measure, and every option is a STORED column — the read
    path never divides (SPEC §9). It defaults to `rlv_total`, which is also the objective
    `is_best` is pinned to at bake time, so the map colors the measure the bake optimized.
    `filters` accepts `status`, `min_confidence`, `submarket_id`.

    Pass `computed_at` to pin the batch explicitly. The API resolves it ONCE per request and
    threads it into every read, so a bake that commits mid-request cannot leave the tiles on
    one batch and the table on another. Left None, each statement re-evaluates LATEST_BATCH
    independently — fine for a one-shot script, wrong for a multi-query request.
    """
    filters = filters or {}
    # Scoped to one batch AND is_best: exactly one row per parcel (SPEC §9).
    where = [f"b.computed_at = COALESCE(%s, {LATEST_BATCH})", "b.is_best"]
    params: list[Any] = [computed_at]

    if bounds is not None:
        where.append("p.parcel_geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)")
        params.extend(bounds)
    if filters.get("status"):
        where.append("b.status = %s")
        params.append(filters["status"])
    if filters.get("submarket_id"):
        where.append("p.submarket_id = %s")
        params.append(filters["submarket_id"])
    if filters.get("min_confidence") is not None:
        where.append("b.confidence >= %s")
        params.append(filters["min_confidence"])

    order = MAP_OBJECTIVES.get(objective, MAP_OBJECTIVES[DEFAULT_MAP_OBJECTIVE])

    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT b.ssl, b.prototype_id, b.status, b.screening_rlv, b.feasibility_gap,
                       b.rlv_total, b.rlv_per_buildable_sf,
                       b.confidence, b.binding_constraint,
                       b.noi, b.total_development_cost, b.yield_on_cost, b.profit_margin,
                       b.exit_value, b.gross_sf, b.net_rentable_sf, b.unit_count, b.floors,
                       p.lot_area_sf, p.submarket_id, p.zone_code, p.land_value,
                       p.existing_building_sf, p.address, p.neighborhood
                FROM bake_results b JOIN parcels p USING (ssl)
                WHERE {' AND '.join(where)}
                ORDER BY {order} DESC NULLS LAST, b.ssl""",
            params,
        )
        return cur.fetchall()


