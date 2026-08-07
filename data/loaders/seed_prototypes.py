"""Seed `prototypes` and the default `assumption_sets` row.

Both tables exist in SPEC §7.1 and both are read by SPEC §7.3 functions
(`get_prototypes`, `get_default_assumption_set`) that Stage C's bake calls. Neither is
authored data — each is a straight projection of the engine's canonical constants
(§5 `engine/prototypes.py`, §2.8 `engine/assumptions.py`) into the database, so the DB
and the engine can never disagree.

Note: the §7.1 `prototypes` table has no `min_lot_sf` column even though the §3.1
dataclass requires one; `repositories._to_prototype` reads it from the §5 table.
"""
from __future__ import annotations

import json
from dataclasses import asdict

from engine.assumptions import DEFAULT_ASSUMPTIONS
from engine.prototypes import PROTOTYPES

DEFAULT_ASSUMPTION_SET_ID = "default_v1"

PROTOTYPE_SQL = """
INSERT INTO prototypes (
    prototype_id, construction_type, min_stories, max_stories, efficiency_ratio,
    default_unit_mix, avg_unit_sf, parking_type
) VALUES (
    %(prototype_id)s, %(construction_type)s, %(min_stories)s, %(max_stories)s,
    %(efficiency_ratio)s, %(default_unit_mix)s, %(avg_unit_sf)s, %(parking_type)s
)
ON CONFLICT (prototype_id) DO UPDATE SET
    construction_type = EXCLUDED.construction_type,
    min_stories = EXCLUDED.min_stories,
    max_stories = EXCLUDED.max_stories,
    efficiency_ratio = EXCLUDED.efficiency_ratio,
    default_unit_mix = EXCLUDED.default_unit_mix,
    avg_unit_sf = EXCLUDED.avg_unit_sf,
    parking_type = EXCLUDED.parking_type
"""

ASSUMPTIONS_SQL = """
INSERT INTO assumption_sets (
    assumption_set_id, name, is_default, program, timeline, cost, revenue, debt, exit, envelope
) VALUES (
    %(assumption_set_id)s, %(name)s, TRUE, %(program)s, %(timeline)s, %(cost)s,
    %(revenue)s, %(debt)s, %(exit)s, %(envelope)s
)
ON CONFLICT (assumption_set_id) DO UPDATE SET
    program = EXCLUDED.program, timeline = EXCLUDED.timeline, cost = EXCLUDED.cost,
    revenue = EXCLUDED.revenue, debt = EXCLUDED.debt, exit = EXCLUDED.exit,
    envelope = EXCLUDED.envelope
"""


def write_seed(conn) -> tuple[int, int]:
    """Upsert the four §5 prototypes and the §2.8 default assumption set."""
    prototype_rows = [
        dict(
            prototype_id=p.prototype_id,
            construction_type=p.construction_type.value,
            min_stories=p.min_stories,
            max_stories=p.max_stories,
            efficiency_ratio=p.efficiency_ratio,
            default_unit_mix=json.dumps(p.default_unit_mix),
            avg_unit_sf=json.dumps(p.avg_unit_sf),
            parking_type=p.parking_type,
        )
        for p in PROTOTYPES.values()
    ]

    assumptions = asdict(DEFAULT_ASSUMPTIONS)
    assumption_row = dict(
        assumption_set_id=DEFAULT_ASSUMPTION_SET_ID,
        name="SPEC §2 defaults (v1)",
        **{k: json.dumps(v) for k, v in assumptions.items()},
    )

    with conn.cursor() as cur:
        cur.executemany(PROTOTYPE_SQL, prototype_rows)
        cur.execute(ASSUMPTIONS_SQL, assumption_row)
    conn.commit()
    return len(prototype_rows), 1
