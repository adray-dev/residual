"""Ward-level `market_data` seed (SPEC §7.2, §2).

v2 (2026-08) replaces the uniform national placeholder with **researched DC ward values**
for the two inputs a submarket actually supplies today: residential rent ($/SF/month) and
the multifamily exit cap rate. This is the one-time, manually-run seeding task described in
§7.2 — the research happens here, at authoring time, and deterministic code serves the
result. Nothing in the runtime path calls out.

Construction cost is NOT seeded. `cost_psf` stays on the SPEC §5 national fallback for every
ward, and its provenance stays `national`, because no DC-specific published cost report was
consulted. That is a real gap, not an oversight — see §11.

**The base rent is the BASE product's rent.** SPEC §5 quotes the submarket rent for the
townhome/garden product (`rent_premium_factor = 1.00`); `screening_rlv` then multiplies it by
1.15 for midrise and 1.30 for highrise, and shifts the cap by −25/−50 bps. The values below
are blended standing-stock rents from listing aggregates — which is what the base tier is —
so the product premium must NOT be pre-baked in. Sanity check on the seeded numbers: Ward 2
highrise underwrites at 4.00 × 1.30 = $5.20/SF/mo and Ward 6 highrise at 3.60 × 1.30 =
$4.68/SF/mo, which is where new Class A downtown / Capitol Riverfront product actually prices.

**Per-value provenance drives confidence (§2.8, §3.6).** Each value carries its own tag:
`submarket` when the source reports a geography *inside that ward*, `national` when the value
is a citywide/class-level figure or a comparable ward borrowed because nothing ward-specific
is published. `market_data.provenance` persists the tags; `score_confidence` upgrades only
the inputs a row genuinely tailors. Wards on the plain fallback promote nothing and score 0.

Sources are recorded per value below and collapsed into the row's `source` column.
Re-run manually each quarter; refresh `AS_OF` when you do.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

# SPEC §2.4 / §2.6 fallbacks. Still used for any submarket not in WARD_MARKET, and by
# `bake.run_bake.national_fallback_market`.
FALLBACK_RENT_PSF_MONTHLY = 3.20        # residential $/SF/month
FALLBACK_RETAIL_RENT_PSF_ANNUAL = 40.0  # reserved; no retail revenue in v1 (§2.4)
FALLBACK_EXIT_CAP = 0.055

# SPEC §5 national fallback hard $/SF, keyed by ConstructionType value (matches
# `MarketData.hard_cost_psf`, which the pro forma indexes by `program.construction_type`).
FALLBACK_COST_PSF = {
    # v1.8: the four prototypes span three construction types, and highrise carries a
    # further +6.25% height factor (§5 HARD_COST_FACTOR) on top of concrete_i, landing it
    # at $340. townhome 220 / 5-over-1 260 / midrise 320 / highrise 340.
    "wood_v": 220,
    "podium": 260,
    "concrete_i": 320,
}

SOURCE_TAG = "national_default"
AS_OF = "2026-08-01"          # as-of of the seeded ward research below
FALLBACK_AS_OF = "2026-01-01"  # the original uniform-placeholder vintage

# PROVENANCE keys this table can tag. `hard_cost_psf` is listed so the shape is complete;
# it is always "national" until a DC cost seed lands.
RENT_KEY = "rent_psf_residential_monthly"
CAP_KEY = "exit_cap_rate"
COST_KEY = "hard_cost_psf"


@dataclass(frozen=True)
class WardMarket:
    """One ward's researched inputs, each with its own source string and provenance tag."""

    rent_psf_monthly: float
    rent_source: str
    rent_provenance: str        # "submarket" = sourced inside this ward; "national" = borrowed
    exit_cap: float
    cap_source: str
    cap_provenance: str
    note: str = ""              # caveat surfaced in the seed report, not in the DB


# ---------------------------------------------------------------------------
# The research (2026-08). Rent $/SF/mo, exit cap as a decimal.
#
# Rent method: RentCafe (Yardi Matrix) publishes average rent AND average unit size per DC
# neighborhood; $/SF/mo is the quotient. Only neighborhoods where BOTH were published are
# averaged into a ward — rent-only neighborhoods are used as directional cross-checks and
# said so explicitly. Citywide reference: $2,446 / 746 SF = $3.28 $/SF/mo (2026-08-01).
#
# Cap method: neighborhood cap-rate ranges where published (Nomadic Real Estate, 2026-06),
# otherwise DC class-level figures (CBRE US Cap Rate Survey H2 2025; ApartmentLoanStore DC
# Q1-2026 outlook). A ward whose cap comes only from a citywide/class figure or from a
# neighbouring ward is tagged `national` — it is a comparable, not a submarket observation.
# ---------------------------------------------------------------------------
WARD_MARKET: dict[str, WardMarket] = {
    "ward_1": WardMarket(
        # Columbia Heights / Adams Morgan / Mount Pleasant / U Street / Park View.
        rent_psf_monthly=3.40,
        rent_source=(
            "RentCafe/Yardi Matrix DC neighborhood rents 2026-08: U Street $2,849/668 SF "
            "= $4.26; Adams Morgan $2,551/716 SF = $3.56; Mount Pleasant $1,811/573 SF = "
            "$3.16; Zumper Columbia Heights $2.70/SF (2026-08-07). 4-neighborhood mean $3.42."
        ),
        rent_provenance="submarket",
        exit_cap=0.0500,
        cap_source=(
            "Nomadic Real Estate DC neighborhood cap-rate ranges 2026-06: Columbia Heights "
            "4.5–5.5%, midpoint 5.0%."
        ),
        cap_provenance="submarket",
    ),
    "ward_2": WardMarket(
        # Downtown / Dupont / Georgetown / West End / Foggy Bottom / Logan / Shaw.
        rent_psf_monthly=4.00,
        rent_source=(
            "RentCafe/Yardi Matrix DC neighborhood rents 2026-07/08: Dupont Circle "
            "$2,471/582 SF = $4.25; West End $3,947/942 SF = $4.19; Penn Quarter "
            "$3,409/835 SF = $4.08; Georgetown $2,241/564 SF = $3.97; Logan Circle "
            "$2,500/659 SF = $3.79; Shaw $2,733/725 SF = $3.77. 6-neighborhood mean $4.01."
        ),
        rent_provenance="submarket",
        exit_cap=0.0490,
        cap_source=(
            "CBRE US Cap Rate Survey H2 2025 (pub. 2026-02-10): Washington DC infill Class A "
            "stabilized multifamily 4.75–5.5%; lower half applied to the core downtown ward. "
            "APPROXIMATED — no Ward-2-specific published cap rate exists; this is a "
            "District-wide figure, so it is tagged national, not submarket."
        ),
        cap_provenance="national",
    ),
    "ward_3": WardMarket(
        # Upper Northwest: Cleveland Park / Woodley Park / Tenleytown / Friendship Heights.
        rent_psf_monthly=3.10,
        rent_source=(
            "RentCafe/Yardi Matrix DC neighborhood rents 2026-08: Woodley Park $3,005/826 SF "
            "= $3.64; Cleveland Park $2,303/745 SF = $3.09. Only two Ward-3 neighborhoods "
            "publish unit size; shaded toward Cleveland Park because the ward's rent-only "
            "entries (McLean Gardens $2,923, Forest Hills $2,358, Glover Park $2,242, "
            "Cathedral Heights $2,203, Chevy Chase $1,974/mo) sit at or below the $2,446 "
            "citywide average on large older floorplates."
        ),
        rent_provenance="submarket",
        exit_cap=0.0515,
        cap_source=(
            "APPROXIMATED — no Ward-3 or Upper-Northwest multifamily cap rate is published. "
            "Closest comparable: ApartmentLoanStore DC 'Multifamily Suburban' Class B 5.15% "
            "(Q1 2026 outlook, retrieved 2026-08-07), which matches Ward 3's low-density, "
            "high-income, thin-trade profile. Tagged national."
        ),
        cap_provenance="national",
    ),
    "ward_4": WardMarket(
        # Petworth / Brightwood / Takoma / 16th Street Heights / Crestwood.
        rent_psf_monthly=2.75,
        rent_source=(
            "RentCafe/Yardi Matrix DC neighborhood rents 2026-07/08: 16th Street Heights "
            "$2,163/710 SF = $3.05; Petworth $1,743/586 SF = $2.97; Brightwood "
            "$1,830/844 SF = $2.17. 3-neighborhood mean $2.73."
        ),
        rent_provenance="submarket",
        exit_cap=0.0600,
        cap_source=(
            "Nomadic Real Estate DC neighborhood cap-rate ranges 2026-06: Petworth "
            "5.5–6.5%, midpoint 6.0%."
        ),
        cap_provenance="submarket",
    ),
    "ward_5": WardMarket(
        # Brookland / Eckington / Edgewood / Trinidad / Fort Totten / Langdon / Ivy City.
        rent_psf_monthly=3.05,
        rent_source=(
            "RentCafe/Yardi Matrix DC neighborhood rents 2026-08: Eckington $2,455/761 SF "
            "= $3.23; Trinidad $2,059/637 SF = $3.23; Brookland $2,129/712 SF = $2.99. "
            "3-neighborhood mean $3.15, shaded down because those three are the ward's "
            "strongest and its north/east rent-only entries are materially cheaper "
            "(Fort Totten $1,875, Carver-Langston $1,952, Langdon $1,805/mo)."
        ),
        rent_provenance="submarket",
        exit_cap=0.0570,
        cap_source=(
            "Nomadic Real Estate DC neighborhood cap-rate ranges 2026-06: Brookland "
            "5.2–6.2%, midpoint 5.7%."
        ),
        cap_provenance="submarket",
    ),
    "ward_6": WardMarket(
        # Capitol Hill / NoMa / H Street / Southwest Waterfront / Buzzard Point.
        rent_psf_monthly=3.60,
        rent_source=(
            "RentCafe/Yardi Matrix DC neighborhood rents 2026-08: Capitol Hill "
            "$3,015/777 SF = $3.88; Southwest Waterfront $2,215/649 SF = $3.41. "
            "2-neighborhood mean $3.65, cross-checked against rent-only entries all above "
            "the $2,446 citywide average (Gallaudet $2,878, Waterfront $2,832, "
            "H Street $2,594, Near Northeast $2,581/mo)."
        ),
        rent_provenance="submarket",
        exit_cap=0.0525,
        cap_source=(
            "Nomadic Real Estate DC neighborhood cap-rate ranges 2026-06: Capitol Hill "
            "4.8–5.2% (mid 5.0%) and H Street/NoMa 5.0–6.0% (mid 5.5%); average 5.25%."
        ),
        cap_provenance="submarket",
    ),
    "ward_7": WardMarket(
        # Deanwood / Hillcrest / Marshall Heights / Fort Dupont / Benning / Randle Highlands.
        rent_psf_monthly=1.90,
        rent_source=(
            "RentCafe/Yardi Matrix 2026-08-05: Marshall Heights $1,390/732 SF = $1.90 — the "
            "ONLY Ward-7 neighborhood publishing unit size. THIN. It sits mid-pack among "
            "Ward 7 rent-only entries (Mayfair $1,305, Randle Highlands $1,381, Fairlawn "
            "$1,402, Fort Dupont $1,494, Hillbrook $1,571/mo), so it is used as the ward "
            "proxy; it is still a genuine in-ward observation, hence submarket."
        ),
        rent_provenance="submarket",
        exit_cap=0.0650,
        cap_source=(
            "APPROXIMATED — no Ward-7 cap rate is published. Borrowed from Ward 8, the "
            "closest comparable (same east-of-the-river tier, same Class B/C workforce "
            "stock): midpoint of ApartmentLoanStore DC Class C 5.68% (Q1 2026 outlook) and "
            "the 7%+ published Anacostia/Congress Heights level (Nomadic Real Estate "
            "2026-06). Tagged national because it is a borrowed comparable."
        ),
        cap_provenance="national",
    ),
    "ward_8": WardMarket(
        # Anacostia / Congress Heights / Washington Highlands / Bellevue — plus, since the
        # 2022 redistricting, the Navy Yard / Capitol Riverfront sliver across the river.
        rent_psf_monthly=1.90,
        rent_source=(
            "RentCafe/Yardi Matrix DC neighborhood rents 2026-07/08: Congress Heights "
            "$1,471/780 SF = $1.89; Washington Highlands $1,500/784 SF = $1.91. Mean $1.90. "
            "East-of-the-river stock only — see note."
        ),
        rent_provenance="submarket",
        exit_cap=0.0650,
        cap_source=(
            "Midpoint of ApartmentLoanStore DC 'Multifamily Metro' Class C 5.68% (Q1 2026 "
            "outlook, retrieved 2026-08-07) and the 7%+ cap rates reported as published for "
            "Anacostia/Congress Heights (Nomadic Real Estate 2026-06). Anacostia and "
            "Congress Heights are both in Ward 8, so this is an in-ward observation."
        ),
        cap_provenance="submarket",
        note=(
            "BIMODAL WARD. The 2022 redistricting moved Navy Yard / Capitol Riverfront "
            "across the Anacostia into Ward 8. 663 of 12,467 Ward-8 parcels (5.3%) sit in "
            "that sliver, where RentCafe reports $2,768/790 SF = $3.50 $/SF/mo — 84% above "
            "the base seeded here. One base rent per submarket cannot carry both, so the "
            "east-of-river body (94.7% of parcels) is seeded and Navy Yard parcels are "
            "knowingly UNDER-rented. Fixing this needs a finer submarket grain than the "
            "ward; SPEC §7.2 already names Neighborhood Clusters as the alternative."
        ),
    ),
}


def _row_source(wm: WardMarket) -> str:
    """Collapse the per-value sources into the single `source` TEXT column.

    The column is one-per-row, so per-value attribution is preserved by prefixing each
    citation with the input it belongs to. The authoritative record stays in WARD_MARKET.
    """
    return f"rent: {wm.rent_source} || cap: {wm.cap_source}"


def _provenance(wm: WardMarket) -> dict[str, str]:
    """Per-input tags persisted to `market_data.provenance` and read by `score_confidence`.

    `hard_cost_psf` is always "national": this seed does not touch construction cost.
    """
    return {
        RENT_KEY: wm.rent_provenance,
        CAP_KEY: wm.cap_provenance,
        COST_KEY: "national",
    }


INSERT_SQL = """
INSERT INTO market_data (submarket_id, use_type, rent_psf, cost_psf, exit_cap, as_of,
                         source, provenance)
VALUES (%(submarket_id)s, %(use_type)s, %(rent_psf)s, %(cost_psf)s, %(exit_cap)s,
        %(as_of)s, %(source)s, %(provenance)s)
ON CONFLICT (submarket_id, use_type, as_of) DO UPDATE SET
    rent_psf = EXCLUDED.rent_psf,
    cost_psf = EXCLUDED.cost_psf,
    exit_cap = EXCLUDED.exit_cap,
    source = EXCLUDED.source,
    provenance = EXCLUDED.provenance
"""


def build_rows(submarket_ids: list[str]) -> list[dict]:
    """One residential + one retail row per submarket.

    Seeded wards get their researched rent/cap and per-value provenance. Anything not in
    WARD_MARKET falls back to the §2 nationals with an empty provenance map, so it promotes
    nothing and scores 0 confidence — honestly.
    """
    rows: list[dict] = []
    for submarket_id in submarket_ids:
        wm = WARD_MARKET.get(submarket_id)
        if wm is None:
            rent, cap = FALLBACK_RENT_PSF_MONTHLY, FALLBACK_EXIT_CAP
            source, provenance, as_of = SOURCE_TAG, {}, FALLBACK_AS_OF
        else:
            rent, cap = wm.rent_psf_monthly, wm.exit_cap
            source, provenance, as_of = _row_source(wm), _provenance(wm), AS_OF

        rows.append(
            dict(
                submarket_id=submarket_id,
                use_type="residential",
                rent_psf=rent,
                cost_psf=json.dumps(FALLBACK_COST_PSF),
                exit_cap=cap,
                as_of=as_of,
                source=source,
                provenance=json.dumps(provenance),
            )
        )
        # Retail stays on the national placeholder: v1 books no retail revenue (§2.4), so
        # researching it would be effort spent on a number the pro forma never reads.
        rows.append(
            dict(
                submarket_id=submarket_id,
                use_type="retail",
                rent_psf=FALLBACK_RETAIL_RENT_PSF_ANNUAL,
                cost_psf=json.dumps(FALLBACK_COST_PSF),
                exit_cap=cap,
                as_of=as_of,
                source=SOURCE_TAG,
                provenance=json.dumps({}),
            )
        )
    return rows


def write_seed(conn) -> int:
    """Seed every loaded submarket. Returns rows written."""
    with conn.cursor() as cur:
        cur.execute("SELECT submarket_id FROM submarkets ORDER BY submarket_id")
        submarket_ids = [r["submarket_id"] for r in cur.fetchall()]

    rows = build_rows(submarket_ids)
    with conn.cursor() as cur:
        cur.executemany(INSERT_SQL, rows)
    conn.commit()
    return len(rows)
