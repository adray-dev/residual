"""The only module that runs SQL (SPEC §7.3).

Plain parameterised SQL via psycopg3. Reads return the engine's dataclasses, so the
engine never learns that a database exists. Writes take plain dicts.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterable, Iterator

import psycopg
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

NONE_PROTOTYPE = "__none__"   # bake_results sentinel for status rows (SPEC §7.1)

_PARCEL_COLS = """
    ssl, lot_area_sf, zone_code, submarket_id, land_value, improvement_value,
    improvement_ratio, land_use_code, existing_building_sf, is_exempt, is_historic
"""


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (see .env.example)")
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
    """None when the district is not yet encoded (fix #1) — the bake handles that."""
    if not zone_code:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM zoning_rules WHERE district_code = %s", (zone_code,))
        row = cur.fetchone()
    return _to_rules(row) if row else None


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
    confidence, binding_constraint, computed_at
) VALUES (
    %(ssl)s, %(prototype_id)s, %(is_best)s, %(status)s, %(screening_rlv)s,
    %(feasibility_gap)s, %(confidence)s, %(binding_constraint)s, %(computed_at)s
)
ON CONFLICT (ssl, prototype_id, computed_at) DO NOTHING
"""


def write_bake_results(conn, rows: Iterable[dict]) -> int:
    """Append bake rows. `prototype_id` defaults to the '__none__' sentinel (SPEC §7.1)."""
    params = [
        {
            "ssl": r["ssl"],
            "prototype_id": r.get("prototype_id") or NONE_PROTOTYPE,
            "is_best": r.get("is_best", False),
            "status": r["status"],
            "screening_rlv": r.get("screening_rlv"),
            "feasibility_gap": r.get("feasibility_gap"),
            "confidence": r.get("confidence"),
            "binding_constraint": r.get("binding_constraint"),
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
    objective: str = "rlv_per_sf",
    filters: dict[str, Any] | None = None,
) -> list[dict]:
    """Best-per-parcel rows from the latest batch, for the map.

    `objective` picks the sort measure only — `is_best` is pinned to RLV/SF at bake
    time (SPEC §9). `filters` accepts `status`, `min_confidence`, `submarket_id`.
    """
    filters = filters or {}
    where = ["b.computed_at = (SELECT max(computed_at) FROM bake_results)", "b.is_best"]
    params: list[Any] = []

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

    order = {
        "rlv_per_sf": "b.screening_rlv / NULLIF(p.lot_area_sf, 0)",
        "rlv": "b.screening_rlv",
        "gap": "b.feasibility_gap",
    }.get(objective, "b.screening_rlv / NULLIF(p.lot_area_sf, 0)")

    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT b.ssl, b.prototype_id, b.status, b.screening_rlv, b.feasibility_gap,
                       b.confidence, b.binding_constraint, p.lot_area_sf, p.submarket_id,
                       b.screening_rlv / NULLIF(p.lot_area_sf, 0) AS rlv_per_sf
                FROM bake_results b JOIN parcels p USING (ssl)
                WHERE {' AND '.join(where)}
                ORDER BY {order} DESC NULLS LAST""",
            params,
        )
        return cur.fetchall()


# ---------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------
def save_scenario(
    conn,
    scenario_id: str,
    ssl: str,
    prototype_id: str,
    assumption_set_id: str | None,
    market_snapshot: dict,
    cashflow: dict,
    outputs: dict,
    user_id: str = "local",
    saved_at: datetime | None = None,
) -> str:
    """Freeze a scenario. `market_snapshot` is stamped so it never re-reads live data."""
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO scenarios (
                   scenario_id, ssl, prototype_id, assumption_set_id, user_id,
                   market_snapshot, cashflow, outputs, saved_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (scenario_id) DO UPDATE SET
                   market_snapshot = EXCLUDED.market_snapshot,
                   cashflow = EXCLUDED.cashflow,
                   outputs = EXCLUDED.outputs,
                   saved_at = EXCLUDED.saved_at""",
            (
                scenario_id, ssl, prototype_id, assumption_set_id, user_id,
                json.dumps(market_snapshot), json.dumps(cashflow), json.dumps(outputs),
                saved_at or datetime.now().astimezone(),
            ),
        )
    conn.commit()
    return scenario_id


def get_scenario(conn, scenario_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM scenarios WHERE scenario_id = %s", (scenario_id,))
        return cur.fetchone()
