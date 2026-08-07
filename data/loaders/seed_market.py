"""Ward-level `market_data` seed (SPEC §7.2, §2).

v1 ships the SPEC §2 NATIONAL FALLBACK values for every ward, tagged
`source = "national_default"`. They are placeholders, not research: every ward gets the
same rent, the same cap, the same cost — so the map is uniform on market inputs and only
zoning and lot geometry differentiate parcels until real values land.

The real numbers come from the one-time LLM-assisted seeding task described in §7.2
(ward-average residential rents $/SF/mo and prevailing multifamily exit caps from current
DC market reports; construction $/SF from published quarterly cost reports). That task is
run MANUALLY and its output is entered here with a real `source` and `as_of`. The LLM is
never in the runtime path.

`confidence` reads provenance, not these values — so while `source` is "national_default"
the score stays honestly low (SPEC §2.8, §3.6).
"""
from __future__ import annotations

import json

# SPEC §2.4 / §2.6 fallbacks.
FALLBACK_RENT_PSF_MONTHLY = 3.20        # residential $/SF/month
FALLBACK_RETAIL_RENT_PSF_ANNUAL = 40.0  # reserved; no retail revenue in v1 (§2.4)
FALLBACK_EXIT_CAP = 0.055

# SPEC §5 national fallback hard $/SF, keyed by ConstructionType value (matches
# `MarketData.hard_cost_psf`, which the pro forma indexes by `program.construction_type`).
FALLBACK_COST_PSF = {
    "wood_v": 210,
    "podium": 260,
    "concrete_i": 340,
}

SOURCE_TAG = "national_default"
AS_OF = "2026-01-01"

INSERT_SQL = """
INSERT INTO market_data (submarket_id, use_type, rent_psf, cost_psf, exit_cap, as_of, source)
VALUES (%(submarket_id)s, %(use_type)s, %(rent_psf)s, %(cost_psf)s, %(exit_cap)s,
        %(as_of)s, %(source)s)
ON CONFLICT (submarket_id, use_type, as_of) DO UPDATE SET
    rent_psf = EXCLUDED.rent_psf,
    cost_psf = EXCLUDED.cost_psf,
    exit_cap = EXCLUDED.exit_cap,
    source = EXCLUDED.source
"""


def build_rows(submarket_ids: list[str]) -> list[dict]:
    rows: list[dict] = []
    for submarket_id in submarket_ids:
        rows.append(
            dict(
                submarket_id=submarket_id,
                use_type="residential",
                rent_psf=FALLBACK_RENT_PSF_MONTHLY,
                cost_psf=json.dumps(FALLBACK_COST_PSF),
                exit_cap=FALLBACK_EXIT_CAP,
                as_of=AS_OF,
                source=SOURCE_TAG,
            )
        )
        rows.append(
            dict(
                submarket_id=submarket_id,
                use_type="retail",
                rent_psf=FALLBACK_RETAIL_RENT_PSF_ANNUAL,
                cost_psf=json.dumps(FALLBACK_COST_PSF),
                exit_cap=FALLBACK_EXIT_CAP,
                as_of=AS_OF,
                source=SOURCE_TAG,
            )
        )
    return rows


def write_seed(conn) -> int:
    """Seed every loaded submarket with the §2 fallbacks. Returns rows written."""
    with conn.cursor() as cur:
        cur.execute("SELECT submarket_id FROM submarkets ORDER BY submarket_id")
        submarket_ids = [r["submarket_id"] for r in cur.fetchall()]

    rows = build_rows(submarket_ids)
    with conn.cursor() as cur:
        cur.executemany(INSERT_SQL, rows)
    conn.commit()
    return len(rows)
