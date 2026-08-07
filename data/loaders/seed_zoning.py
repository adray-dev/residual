"""The hand-encoded DC zoning table — starter seed (SPEC §8).

The one genuinely manual reference task. Values are the residential matter-of-right
figures from the 2016 Zoning Regulations. v1 is matter-of-right only: no IZ bonus,
no special exception, no PUD.

EVERY ROW IS FLAGGED `verify` IN SPEC §8 — human-verify against the live ZR (DCOZ
Zoning Handbook) before production use. Districts absent from this seed load fine as
parcels and bake as `zone_not_encoded` until added; coverage grows with zero rework.
"""
from __future__ import annotations

import json

SOURCE_CITATION = "2016 ZR (starter seed, SPEC §8 — unverified against live ZR)"
AS_OF_DATE = "2026-01-01"

# `requires_ground_floor_active`: TRUE for the MU-/D- corridors that mandate ground-floor
# retail/active frontage, FALSE for the RA- residential-apartment districts (SPEC §8).
# `permitted_uses`: the §8 table records residential as permitted in every seeded district;
# retail is matter-of-right in the mixed-use/downtown districts, not in the RA- districts.
SEED: list[dict] = [
    dict(district_code="RA-1", max_far=0.9, max_height_ft=40, max_stories=None,
         lot_occupancy={"residential": 0.40, "other": 0.60},
         permitted_uses=["residential"], parking_ratio={"residential": 1.0},
         requires_ground_floor_active=False, matter_of_right=True,
         source_citation=SOURCE_CITATION, as_of_date=AS_OF_DATE),
    dict(district_code="RA-2", max_far=1.8, max_height_ft=50, max_stories=None,
         lot_occupancy={"residential": 0.60, "other": 0.80},
         permitted_uses=["residential"], parking_ratio={"residential": 0.5},
         requires_ground_floor_active=False, matter_of_right=True,
         source_citation=SOURCE_CITATION, as_of_date=AS_OF_DATE),
    dict(district_code="RA-3", max_far=3.0, max_height_ft=60, max_stories=None,
         lot_occupancy={"residential": 0.75, "other": 0.80},
         permitted_uses=["residential"], parking_ratio={"residential": 0.5},
         requires_ground_floor_active=False, matter_of_right=True,
         source_citation=SOURCE_CITATION, as_of_date=AS_OF_DATE),
    dict(district_code="RA-4", max_far=3.5, max_height_ft=90, max_stories=None,
         lot_occupancy={"residential": 0.75, "other": 0.80},
         permitted_uses=["residential"], parking_ratio={"residential": 0.33},
         requires_ground_floor_active=False, matter_of_right=True,
         source_citation=SOURCE_CITATION, as_of_date=AS_OF_DATE),
    dict(district_code="RA-5", max_far=6.0, max_height_ft=90, max_stories=None,
         lot_occupancy={"residential": 0.80, "other": 0.80},
         permitted_uses=["residential"], parking_ratio={"residential": 0.33},
         requires_ground_floor_active=False, matter_of_right=True,
         source_citation=SOURCE_CITATION, as_of_date=AS_OF_DATE),
    dict(district_code="MU-4", max_far=2.5, max_height_ft=50, max_stories=None,
         lot_occupancy={"residential": 0.60, "other": 0.80},
         permitted_uses=["residential", "retail"], parking_ratio={"residential": 0.5},
         requires_ground_floor_active=True, matter_of_right=True,
         source_citation=SOURCE_CITATION, as_of_date=AS_OF_DATE),
    dict(district_code="MU-5", max_far=3.0, max_height_ft=65, max_stories=None,
         lot_occupancy={"residential": 0.75, "other": 0.80},
         permitted_uses=["residential", "retail"], parking_ratio={"residential": 0.5},
         requires_ground_floor_active=True, matter_of_right=True,
         source_citation=SOURCE_CITATION, as_of_date=AS_OF_DATE),
    dict(district_code="MU-7", max_far=4.0, max_height_ft=90, max_stories=None,
         lot_occupancy={"residential": 0.75, "other": 0.80},
         permitted_uses=["residential", "retail"], parking_ratio={"residential": 0.33},
         requires_ground_floor_active=True, matter_of_right=True,
         source_citation=SOURCE_CITATION, as_of_date=AS_OF_DATE),
    dict(district_code="MU-9", max_far=6.0, max_height_ft=110, max_stories=None,
         lot_occupancy={"residential": 0.80, "other": 1.00},
         permitted_uses=["residential", "retail"], parking_ratio={"residential": 0.33},
         requires_ground_floor_active=True, matter_of_right=True,
         source_citation=SOURCE_CITATION, as_of_date=AS_OF_DATE),
    dict(district_code="D-4", max_far=8.5, max_height_ft=130, max_stories=None,
         lot_occupancy={"residential": 1.00, "other": 1.00},
         permitted_uses=["residential", "retail"], parking_ratio={"residential": 0.25},
         requires_ground_floor_active=True, matter_of_right=True,
         source_citation=SOURCE_CITATION, as_of_date=AS_OF_DATE),
    dict(district_code="D-5", max_far=10.0, max_height_ft=130, max_stories=None,
         lot_occupancy={"residential": 1.00, "other": 1.00},
         permitted_uses=["residential", "retail"], parking_ratio={"residential": 0.25},
         requires_ground_floor_active=True, matter_of_right=True,
         source_citation=SOURCE_CITATION, as_of_date=AS_OF_DATE),
]

INSERT_SQL = """
INSERT INTO zoning_rules (
    district_code, max_far, max_height_ft, max_stories, lot_occupancy,
    permitted_uses, parking_ratio, requires_ground_floor_active,
    matter_of_right, source_citation, as_of_date
) VALUES (
    %(district_code)s, %(max_far)s, %(max_height_ft)s, %(max_stories)s, %(lot_occupancy)s,
    %(permitted_uses)s, %(parking_ratio)s, %(requires_ground_floor_active)s,
    %(matter_of_right)s, %(source_citation)s, %(as_of_date)s
)
ON CONFLICT (district_code) DO UPDATE SET
    max_far = EXCLUDED.max_far,
    max_height_ft = EXCLUDED.max_height_ft,
    max_stories = EXCLUDED.max_stories,
    lot_occupancy = EXCLUDED.lot_occupancy,
    permitted_uses = EXCLUDED.permitted_uses,
    parking_ratio = EXCLUDED.parking_ratio,
    requires_ground_floor_active = EXCLUDED.requires_ground_floor_active,
    matter_of_right = EXCLUDED.matter_of_right,
    source_citation = EXCLUDED.source_citation,
    as_of_date = EXCLUDED.as_of_date
"""


def write_seed(conn) -> int:
    """Upsert the §8 starter districts into `zoning_rules`. Returns rows written."""
    params = [
        {
            **row,
            "lot_occupancy": json.dumps(row["lot_occupancy"]),
            "permitted_uses": json.dumps(row["permitted_uses"]),
            "parking_ratio": json.dumps(row["parking_ratio"]),
        }
        for row in SEED
    ]
    with conn.cursor() as cur:
        cur.executemany(INSERT_SQL, params)
    conn.commit()
    return len(params)
