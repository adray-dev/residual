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

# ---------------------------------------------------------------------------
# Coverage expansion (pre-Stage-D). 17 districts covering ~96% of the parcels that
# previously baked as `zone_not_encoded`, ranked by parcel count before encoding.
#
# Unlike the starter seed above, these values are transcribed from the CONSOLIDATED
# Zoning Regulations of 2016 as published March 4 2024 (Title 11 DCMR, unofficial export,
# incorporating ZC Order 18-16/19-27 of August 25 2023). That amendment matters: it is what
# splits the Mixed-Use zones into the A/B designations the DC zoning layer actually carries
# (MU-3A, MU-5A, MU-6B, MU-7B, MU-9B). The standalone per-subtitle PDFs on dcoz.dc.gov are
# older and still show undivided MU-3/MU-5-A/MU-7/MU-9 — do not re-source from those.
#
# Overlay-tagged codes (`R-3/GT`) are NOT given rows of their own: the base district drives
# the envelope and `repositories.resolve_rules` strips the tag on lookup. See that function
# for why the match is exact-first (Subtitle H's NMU zones are base/overlay pairs, not
# overlays on a base).
ZR2024 = "2016 ZR consolidated 2024-03-04 (ZC Order 18-16/19-27)"
SOURCE_D = f"{ZR2024} Subtitle D §§ 303.1, 304.1"          # Residential House
SOURCE_E_RF1 = f"{ZR2024} Subtitle E §§ 303.1, 304.1"      # Residential Flat RF-1
SOURCE_E_RF4 = f"{ZR2024} Subtitle E §§ 602.1, 603.1, 604.1"
SOURCE_G = f"{ZR2024} Subtitle G Tables G §§ 201.1, 203.2, 210.1"   # Mixed Use
SOURCE_J = f"{ZR2024} Subtitle J Tables J §§ 201.1, 203.2; § 101.2(d)"  # PDR

# Subtitle D Chapter 3 and Subtitle E Chapter 3 set NO maximum FAR: bulk in the R and RF-1
# zones is controlled by lot occupancy, height, and yards (D §§ 302-308, E §§ 302-306).
# `ZoningRules.max_far` is a required float that `resolve_envelope` multiplies directly, so
# "no FAR standard" is expressed as a sentinel far above any reachable coverage × stories
# product. It can never be the binding constraint, which is the correct outcome: the bake
# will report `stories` or `height` as the gate in these zones, not a FAR that the ZR does
# not impose. Do NOT read this as a real 99.0 FAR allowance.
NO_FAR_LIMIT = 99.0

# Parking, all rows below: Subtitle C Table C § 701.5 —
#   "Residential, single dwelling unit"  1 per principal dwelling      -> 1.0
#   "Residential, flat"                  1 per 2 dwelling units        -> 0.5
#   "Residential, multiple dwelling unit" 1 per 3 units over 4, except
#                                         1 per 2 units in an R or RF zone -> 0.33 / 0.5
# The § 702 half-off reduction near Metrorail/streetcar/priority-bus is site-specific, not
# zone-specific, so it is not applied here (it would need a transit-distance join).
#
# `requires_ground_floor_active`: the ZR ties active-frontage mandates to DESIGNATED street
# segments (e.g. Subtitle I § 601), not to whole zones. v1 has no street-segment data, so
# this stays a zone-level approximation and follows the starter seed's convention — TRUE for
# the MU corridors, FALSE for the R/RF house and flat zones. VERIFY when street segments land.

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

    # -----------------------------------------------------------------------
    # Residential House (R) — Subtitle D, Chapter 3.
    # Height 40 ft / 3 stories for all four zones (D § 303.1). Lot occupancy from
    # Table D § 304.1. No FAR standard — see NO_FAR_LIMIT above.
    # Note the district_code spelling: the DC zoning layer writes `R-1A`, the ZR text
    # writes `R-1-A`. The KEY must match `parcels.zone_code`, so the layer's spelling wins.
    # -----------------------------------------------------------------------
    dict(district_code="R-1A", max_far=NO_FAR_LIMIT, max_height_ft=40, max_stories=3,
         # 40% all other structures; 60% places of worship (non-residential, so -> "other").
         lot_occupancy={"residential": 0.40, "other": 0.60},
         permitted_uses=["residential"], parking_ratio={"residential": 1.0},
         requires_ground_floor_active=False, matter_of_right=True,
         source_citation=SOURCE_D, as_of_date=AS_OF_DATE),
    dict(district_code="R-1B", max_far=NO_FAR_LIMIT, max_height_ft=40, max_stories=3,
         lot_occupancy={"residential": 0.40, "other": 0.60},
         permitted_uses=["residential"], parking_ratio={"residential": 1.0},
         requires_ground_floor_active=False, matter_of_right=True,
         source_citation=SOURCE_D, as_of_date=AS_OF_DATE),
    dict(district_code="R-2", max_far=NO_FAR_LIMIT, max_height_ft=40, max_stories=3,
         lot_occupancy={"residential": 0.40, "other": 0.60},
         permitted_uses=["residential"], parking_ratio={"residential": 1.0},
         requires_ground_floor_active=False, matter_of_right=True,
         source_citation=SOURCE_D, as_of_date=AS_OF_DATE),
    dict(district_code="R-3", max_far=NO_FAR_LIMIT, max_height_ft=40, max_stories=3,
         # VERIFY: Table D § 304.1 gives R-3 THREE figures — 60% attached dwellings,
         # 60% places of worship, 40% all other structures. The schema holds one number
         # per use, so this takes the attached-dwelling figure: R-3 is the rowhouse zone,
         # the townhome prototype is the attached case, and it is the prototype that
         # actually wins here. A detached or multi-unit building in R-3 is capped at 40%
         # and this row overstates it. Revisit if per-building-type occupancy is modeled.
         lot_occupancy={"residential": 0.60, "other": 0.40},
         permitted_uses=["residential"], parking_ratio={"residential": 1.0},
         requires_ground_floor_active=False, matter_of_right=True,
         source_citation=SOURCE_D, as_of_date=AS_OF_DATE),

    # -----------------------------------------------------------------------
    # Residential Flat (RF) — Subtitle E.
    # RF-1: 35 ft / 3 stories (E § 303.1), 60% occupancy for row dwellings and flats
    # (Table E § 304.1), no FAR standard. RF-4 DOES have one: FAR 1.8 (E § 602.1).
    # -----------------------------------------------------------------------
    dict(district_code="RF-1", max_far=NO_FAR_LIMIT, max_height_ft=35, max_stories=3,
         # 60% row dwellings/flats/places of worship; 40% all other structures.
         lot_occupancy={"residential": 0.60, "other": 0.40},
         permitted_uses=["residential"], parking_ratio={"residential": 0.5},
         requires_ground_floor_active=False, matter_of_right=True,
         source_citation=SOURCE_E_RF1, as_of_date=AS_OF_DATE),
    dict(district_code="RF-4", max_far=1.8, max_height_ft=40, max_stories=3,
         lot_occupancy={"residential": 0.60, "other": 0.60},   # E § 604.1: 60%, flat rate
         permitted_uses=["residential"], parking_ratio={"residential": 0.5},
         requires_ground_floor_active=False, matter_of_right=True,
         source_citation=SOURCE_E_RF4, as_of_date=AS_OF_DATE),

    # -----------------------------------------------------------------------
    # Mixed Use (MU) — Subtitle G, as split into A/B designations by ZC Order 18-16/19-27.
    # FAR: Table G § 201.1 "Maximum Total FAR" (the non-IZ figure; v1 is matter-of-right
    # only, so IZ bonus densities are deliberately not taken).
    # Height/stories: Table G § 203.2 (non-IZ). "No Limit" stories -> max_stories=None.
    # Lot occupancy: Table G § 210.1, residential (non-IZ).
    # -----------------------------------------------------------------------
    dict(district_code="MU-3A", max_far=1.0, max_height_ft=40, max_stories=3,
         # VERIFY: MU-3A is the one zone absent from Table G § 210.1 — the table jumps from
         # MU-2 to MU-3B. 60% is MU-3B's figure, used here as the nearest in-family value.
         # This is the only lot-occupancy number below that is not directly in the table.
         lot_occupancy={"residential": 0.60, "other": 0.60},
         permitted_uses=["residential", "retail"], parking_ratio={"residential": 0.33},
         requires_ground_floor_active=True, matter_of_right=True,
         source_citation=SOURCE_G, as_of_date=AS_OF_DATE),
    dict(district_code="MU-5A", max_far=3.5, max_height_ft=65, max_stories=None,
         lot_occupancy={"residential": 0.80, "other": 0.80},
         permitted_uses=["residential", "retail"], parking_ratio={"residential": 0.33},
         requires_ground_floor_active=True, matter_of_right=True,
         source_citation=SOURCE_G, as_of_date=AS_OF_DATE),
    dict(district_code="MU-6B", max_far=6.0, max_height_ft=90, max_stories=None,
         lot_occupancy={"residential": 0.75, "other": 0.80},
         permitted_uses=["residential", "retail"], parking_ratio={"residential": 0.33},
         requires_ground_floor_active=True, matter_of_right=True,
         source_citation=SOURCE_G, as_of_date=AS_OF_DATE),
    dict(district_code="MU-7B", max_far=4.0, max_height_ft=65, max_stories=None,
         lot_occupancy={"residential": 0.75, "other": 0.80},
         permitted_uses=["residential", "retail"], parking_ratio={"residential": 0.33},
         requires_ground_floor_active=True, matter_of_right=True,
         source_citation=SOURCE_G, as_of_date=AS_OF_DATE),
    dict(district_code="MU-9B", max_far=6.5, max_height_ft=90, max_stories=None,
         # Table G § 210.1 gives MU-9A/MU-9B as "N/A" — no lot-occupancy limit in this
         # zone, so full coverage. FAR is the binding density control here, as intended.
         lot_occupancy={"residential": 1.00, "other": 1.00},
         permitted_uses=["residential", "retail"], parking_ratio={"residential": 0.33},
         requires_ground_floor_active=True, matter_of_right=True,
         source_citation=SOURCE_G, as_of_date=AS_OF_DATE),
    dict(district_code="MU-10", max_far=6.0, max_height_ft=90, max_stories=None,
         lot_occupancy={"residential": 0.75, "other": 0.80},
         permitted_uses=["residential", "retail"], parking_ratio={"residential": 0.33},
         requires_ground_floor_active=True, matter_of_right=True,
         source_citation=SOURCE_G, as_of_date=AS_OF_DATE),
    dict(district_code="MU-12", max_far=2.5, max_height_ft=45, max_stories=None,
         lot_occupancy={"residential": 0.80, "other": 0.80},
         permitted_uses=["residential", "retail"], parking_ratio={"residential": 0.33},
         requires_ground_floor_active=True, matter_of_right=True,
         source_citation=SOURCE_G, as_of_date=AS_OF_DATE),

    # -----------------------------------------------------------------------
    # Production, Distribution, and Repair (PDR) — Subtitle J.
    # `permitted_uses=[]` is deliberate and is the whole point of these four rows.
    # Subtitle J § 101.2(d): the PDR zones exist to "minimize encroachment by uses that are
    # incompatible with PDR uses, INCLUDING RESIDENTIAL USES". Residential is not a
    # matter-of-right use here, so `fit_program` raises NotPermitted for every prototype and
    # the parcel bakes as `infeasible` ("no admissible prototype") rather than as
    # `zone_not_encoded`. That is honest colouring: these parcels are represented and the
    # map can say why they are not developable as housing, instead of "not yet covered".
    # FAR is the § 201.3 "All Other Uses" column (not the § 201.2 PDR-use column), heights
    # from Table J § 203.2. Both are recorded for completeness; with no permitted
    # residential use neither is ever reached by the residential bake.
    # -----------------------------------------------------------------------
    dict(district_code="PDR-1", max_far=2.0, max_height_ft=50, max_stories=None,
         lot_occupancy={"residential": 0.80, "other": 0.80},
         permitted_uses=[], parking_ratio={"residential": 0.33},
         requires_ground_floor_active=False, matter_of_right=True,
         source_citation=SOURCE_J, as_of_date=AS_OF_DATE),
    dict(district_code="PDR-2", max_far=3.0, max_height_ft=60, max_stories=None,
         lot_occupancy={"residential": 0.80, "other": 0.80},
         permitted_uses=[], parking_ratio={"residential": 0.33},
         requires_ground_floor_active=False, matter_of_right=True,
         source_citation=SOURCE_J, as_of_date=AS_OF_DATE),
    dict(district_code="PDR-3", max_far=4.0, max_height_ft=90, max_stories=None,
         lot_occupancy={"residential": 0.80, "other": 0.80},
         permitted_uses=[], parking_ratio={"residential": 0.33},
         requires_ground_floor_active=False, matter_of_right=True,
         source_citation=SOURCE_J, as_of_date=AS_OF_DATE),
    dict(district_code="PDR-4", max_far=1.0, max_height_ft=90, max_stories=None,
         lot_occupancy={"residential": 0.80, "other": 0.80},
         permitted_uses=[], parking_ratio={"residential": 0.33},
         requires_ground_floor_active=False, matter_of_right=True,
         source_citation=SOURCE_J, as_of_date=AS_OF_DATE),
]

# ---------------------------------------------------------------------------
# Confirmed for encoding but NOT encoded, with the reason. These are left as
# `zone_not_encoded` on purpose; each is a data problem, not an oversight.
#
#   D-4-R (146 parcels), D-5-R (136), D-6 (312)
#       Subtitle I sets Downtown height as a function of the abutting STREET RIGHT-OF-WAY
#       WIDTH (I § 556.1: 130 ft where the ROW is >= 110 ft, sliding down to "ROW width
#       + 20 ft" below 90 ft). We have no street-width attribute on the parcel, so any
#       single max_height_ft would be right on wide streets and badly wrong on narrow
#       ones. Same class of limitation as SPEC §11's setback-geometry note. Needs a
#       street-centerline join first.
#
#   CG-4 (120 parcels), ARTS-2 (209)
#       ARTS FAR is sourced (Table K § 801.1: ARTS-2 total 3.5) but the matching height
#       table in Subtitle K Chapter 8 could not be read cleanly for ARTS-1/ARTS-2, and no
#       CG-4 standards table was located. Encoding either would mean inventing a height.
#
#   NMU-4 (427), NMU-5A (83), NMU-7B (189)
#       These are NOT base districts with overlays. Subtitle H defines each Neighborhood
#       Mixed-Use zone as a base/overlay PAIR carrying its own standards — NMU-4/CP is FAR
#       2.0 and 40 ft, NMU-4/WP is FAR 2.5, NMU-4/GA is 50 ft with 70% occupancy. A bare
#       `NMU-4` row would be wrong for all three and, worse, `resolve_rules` would silently
#       apply it to every variant. They must be encoded as exact combined codes
#       (`NMU-4/GA`, ...), which `resolve_rules` already prefers over any base. Deferred:
#       ~14 combinations, several not present in the current parcel set.
# ---------------------------------------------------------------------------
NOT_ENCODED_BY_DESIGN = {
    "D-4-R": "Downtown height depends on street right-of-way width (no street data)",
    "D-5-R": "Downtown height depends on street right-of-way width (no street data)",
    "D-6": "Downtown height depends on street right-of-way width (no street data)",
    "CG-4": "no standards table sourced",
    "ARTS-2": "height not sourced (FAR is: Table K § 801.1 = 3.5)",
    "NMU-4": "Subtitle H defines base/overlay pairs individually; needs exact combined codes",
    "NMU-5A": "Subtitle H defines base/overlay pairs individually; needs exact combined codes",
    "NMU-7B": "Subtitle H defines base/overlay pairs individually; needs exact combined codes",
    "UNZONED": "DC sentinel, not a district",
    "StE-*": "St. Elizabeths campus zones (Subtitle K) — campus-plan driven, not matter-of-right",
}

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
