"""Stage A gate (SPEC §4). Every expected number below is computed by hand in the comments.

Shared constants used throughout (SPEC §2.8 DEFAULT_ASSUMPTIONS):
    floor_to_floor_residential_ft = 10
    stabilized_occupancy = 0.94   opex_ratio = 0.35
    soft_cost_pct = 0.20          contingency_pct = 0.05
    target_developer_margin = 0.15
    parking $/stall: surface 5,000 | structured 35,000 | podium 45,000
"""

from dataclasses import replace

import numpy as np
import pytest

from engine.assumptions import DEFAULT_ASSUMPTIONS, PROVENANCE
from engine.confidence import score_confidence
from engine.envelope import resolve_envelope
from engine.proforma import full_cashflow, screening_rlv
from engine.program import fit_program
from engine.prototypes import (
    ACTIVE_PROTOTYPES,
    DISABLED_PROTOTYPES,
    EXIT_CAP_ADJUSTMENT,
    NATIONAL_HARD_COST_PSF,
    PROTOTYPES,
    RENT_PREMIUM_FACTOR,
    hard_cost_psf,
)
from engine.solve import safe_irr, solve_irr_rlv
from engine.types import ConstructionType, MarketData, NotPermitted, Parcel, Use, ZoningRules

HARD_COST_PSF = {
    ConstructionType.CONCRETE_I: 340,
    ConstructionType.WOOD_OVER_PODIUM: 260,
    ConstructionType.WOOD_V: 210,
}


def _market(rent=3.20, cap=0.055, hard=None, sid="noma"):
    return MarketData(
        submarket_id=sid,
        rent_psf_residential_monthly=rent,
        retail_rent_psf_annual=40,
        exit_cap_rate=cap,
        hard_cost_psf=hard or HARD_COST_PSF,
        as_of="2026-06",
        source="Cumming Q2 2026",
    )


# ---------------------------------------------------------------------------
# (a) FAR-BINDING — the SPEC §4 scaffold parcel in MU-4.
#
# The prototype changed in v1.8 and the parcel did not. A 50 ft height cap is five
# storeys, and five storeys is now the 5-over-1 band (4-7), not midrise (8-12) — so this
# case also pins the new tier boundary from both sides.
# ---------------------------------------------------------------------------
def test_a_far_binding_five_over_one_screening_rlv():
    parcel = Parcel(ssl="0123 0045", lot_area_sf=10_000, zone_code="MU-4",
                    submarket_id="noma", land_value=1_100_000,
                    improvement_value=200_000, land_use_code="vacant",
                    improvement_ratio=0.15)
    rules = ZoningRules(district_code="MU-4", max_far=2.5, max_height_ft=50,
                        max_stories=None,
                        lot_occupancy_pct={"residential": 0.60, "other": 0.80},
                        permitted_uses=[Use.RESIDENTIAL, Use.RETAIL],
                        parking_ratio={"residential": 0.5})
    market = _market()

    env = resolve_envelope(parcel, rules, Use.RESIDENTIAL, DEFAULT_ASSUMPTIONS)
    # ENVELOPE HAND CHECK
    #   floors_by_height = 50 // 10                 = 5      (max_stories is None -> limiter "height")
    #   far_gsf          = 10,000 * 2.5             = 25,000
    #   footprint        = 10,000 * 0.60            = 6,000
    #   coverage_gsf     = 6,000 * 5                = 30,000
    #   far 25,000 <= coverage 30,000 -> max_gsf = 25,000, binding = "far"
    assert env.max_buildable_gsf == 25_000
    assert env.max_footprint_sf == 6_000
    assert env.max_floors == 5
    assert env.binding_constraint == "far"

    # The band partition, from the other side: at five storeys midrise is now out of range,
    # so it cannot quietly come back as the answer to this case.
    with pytest.raises(NotPermitted) as rejected:
        fit_program(env, PROTOTYPES["midrise"], rules, Use.RESIDENTIAL,
                    DEFAULT_ASSUMPTIONS, parcel)
    assert str(rejected.value) == "midrise needs >= 8 stories; MU-4 allows 5 (gated by far)"

    prog = fit_program(env, PROTOTYPES["5-over-1"], rules, Use.RESIDENTIAL,
                       DEFAULT_ASSUMPTIONS, parcel)
    # PROGRAM HAND CHECK (5-over-1: 4-7 stories, min_lot 6,000, eff 0.85, podium)
    #   lot 10,000 >= min_lot 6,000            -> admissible
    #   min_stories 4 <= max_floors 5          -> admissible
    #   floors    = min(7, 5)                           = 5
    #   gross_sf  = min(25,000, 6,000*5=30,000)         = 25,000
    #   no ground-floor mandate -> residential_gsf      = 25,000
    #   net       = 25,000 * 0.85                       = 21,250
    #   avg_sf    = .25*500 + .50*750 + .25*1050
    #             = 125 + 375 + 262.5                   = 762.5
    #   units     = int(21,250 // 762.5) = int(27.869)  = 27
    #   mix       = studio int(6.75)=6 | 1br int(13.5)=13 | 2br int(6.75)=6
    #   stalls    = round(27 * 0.5) = round(13.5)       = 14   (banker's: ties go even)
    assert prog.floors == 5
    assert prog.gross_sf == 25_000
    assert prog.net_rentable_sf == 21_250
    assert prog.unit_count == 27
    assert prog.unit_mix_counts == {"studio": 6, "1br": 13, "2br": 6}
    assert prog.parking_stalls == 14
    assert prog.retail_sf == 0.0
    assert prog.construction_type == ConstructionType.WOOD_OVER_PODIUM

    out = screening_rlv(prog, market, DEFAULT_ASSUMPTIONS, parcel)
    # RLV HAND CHECK — 5-over-1 carries midrise's product factors (1.40 premium, -25 bps)
    # and wood-over-podium's cost. The REVENUE side is therefore identical to what midrise
    # produced for this parcel in v1.7; only the shell is priced differently.
    #   rent_psf          = 3.20 * 1.40                       = 4.48
    #   exit_cap          = 0.055 - 0.0025                    = 0.0525
    #   gross_residential = 21,250 * 4.48 * 12                = 1,142,400
    #   egi               = 1,142,400 * 0.94                  = 1,073,856
    #   noi               = 1,073,856 * 0.65                  =   698,006.40
    #   exit_value        = 698,006.40 / 0.0525               = 13,295,360    (exact)
    #   hard shell        = 25,000 * 260 (podium, not 340)    = 6,500,000
    #   hard parking      = 14 * 45,000 (podium)              =   630,000
    #   hard              =                                     7,130,000
    #   soft              = 7,130,000 * 0.20                  = 1,426,000
    #   contingency       = 7,130,000 * 0.05                  =   356,500
    #   cost_ex_land      =                                     8,912,500
    #   profit            = 13,295,360 * 0.15                 = 1,994,304
    #   RLV = 13,295,360 - 8,912,500 - 1,994,304              = 2,388,556
    #   gap = 2,388,556 - 1,100,000                           = 1,288,556
    #   yoc = 698,006.40 / 8,912,500                          = 0.07831769
    #   margin = (13,295,360 - 8,912,500) / 8,912,500         = 0.49176550
    #
    # This is the entire point of the v1.8 split, in one number. The identical building —
    # same envelope, same 25,000 GSF, same 21,250 rentable, same rent, same cap — went from
    # RLV -111,444 to +2,388,556 purely because five storeys are now priced as the wood
    # they are built from ($260/SF) instead of as concrete ($340/SF). $2M of shell cost was
    # a modeling artifact, and the feasibility sign flipped with it.
    assert out.screening_rlv == pytest.approx(2_388_556.0, abs=1.0)
    assert out.feasibility_gap == pytest.approx(1_288_556.0, abs=1.0)
    assert out.total_development_cost == pytest.approx(8_912_500, abs=1.0)
    assert out.exit_value == pytest.approx(13_295_360.0, abs=1.0)
    assert out.yield_on_cost == pytest.approx(0.07831769, abs=1e-8)
    assert out.profit_margin == pytest.approx(0.49176550, abs=1e-8)


# ---------------------------------------------------------------------------
# (b) HEIGHT-BINDING — high FAR, low height cap. Coverage x floors is the cap,
#     and the reason it is capped is the height limit.
# ---------------------------------------------------------------------------
def test_b_height_binding_garden_screening_rlv():
    parcel = Parcel(ssl="0500 0012", lot_area_sf=20_000, zone_code="TEST-H",
                    submarket_id="ward5", land_value=1_000_000,
                    improvement_value=0, land_use_code="vacant",
                    improvement_ratio=0.0)
    rules = ZoningRules(district_code="TEST-H", max_far=6.0, max_height_ft=40,
                        max_stories=None,
                        lot_occupancy_pct={"residential": 0.60, "other": 0.80},
                        permitted_uses=[Use.RESIDENTIAL],
                        parking_ratio={"residential": 1.0})
    market = _market()

    env = resolve_envelope(parcel, rules, Use.RESIDENTIAL, DEFAULT_ASSUMPTIONS)
    # ENVELOPE HAND CHECK
    #   floors_by_height = 40 // 10        = 4     (max_stories None -> limiter "height")
    #   far_gsf          = 20,000 * 6.0    = 120,000
    #   footprint        = 20,000 * 0.60   = 12,000
    #   coverage_gsf     = 12,000 * 4      = 48,000
    #   far 120,000 > coverage 48,000 -> max_gsf = 48,000, binding = floor_limiter = "height"
    assert env.max_buildable_gsf == 48_000
    assert env.max_floors == 4
    assert env.binding_constraint == "height"

    prog = fit_program(env, PROTOTYPES["garden"], rules, Use.RESIDENTIAL,
                       DEFAULT_ASSUMPTIONS, parcel)
    # PROGRAM HAND CHECK (garden: 2-4 stories, min_lot 15,000, eff 0.85, surface)
    #   floors   = min(4, 4)                          = 4
    #   gross_sf = min(48,000, 12,000*4=48,000)       = 48,000
    #   net      = 48,000 * 0.85                      = 40,800
    #   avg_sf   = .20*500 + .50*750 + .30*1050
    #            = 100 + 375 + 315                    = 790
    #   units    = int(40,800 // 790) = int(51.6456)  = 51
    #   mix      = studio int(10.2)=10 | 1br int(25.5)=25 | 2br int(15.3)=15
    #   stalls   = round(51 * 1.0)                    = 51
    assert prog.floors == 4
    assert prog.gross_sf == 48_000
    assert prog.net_rentable_sf == pytest.approx(40_800)
    assert prog.unit_count == 51
    assert prog.unit_mix_counts == {"studio": 10, "1br": 25, "2br": 15}
    assert prog.parking_stalls == 51
    assert prog.construction_type == ConstructionType.WOOD_V

    out = screening_rlv(prog, market, DEFAULT_ASSUMPTIONS, parcel)
    # RLV HAND CHECK
    #   gross_residential = 40,800 * 3.20 * 12                 =  1,566,720
    #   egi               = 1,566,720 * 0.94                   =  1,472,716.80
    #   noi               = 1,472,716.80 * 0.65                =    957,265.92
    #   exit_value        = 957,265.92 / 0.055                 = 17,404,834.909091
    #   hard shell        = 48,000 * 210 (wood_v)              = 10,080,000
    #   hard parking      = 51 * 5,000 (surface)               =    255,000
    #   hard              =                                      10,335,000
    #   soft              = 10,335,000 * 0.20                  =  2,067,000
    #   contingency       = 10,335,000 * 0.05                  =    516,750
    #   cost_ex_land      =                                      12,918,750
    #   profit            = 17,404,834.909091 * 0.15           =  2,610,725.236364
    #   RLV = 17,404,834.909091 - 12,918,750 - 2,610,725.236364
    #                                                          =  1,875,359.672727
    #   gap = 1,875,359.672727 - 1,000,000                     =    875,359.672727
    assert out.screening_rlv == pytest.approx(1_875_359.672727, abs=1.0)
    assert out.feasibility_gap == pytest.approx(875_359.672727, abs=1.0)
    assert out.total_development_cost == pytest.approx(12_918_750, abs=1.0)
    assert out.exit_value == pytest.approx(17_404_834.909091, abs=1.0)


# ---------------------------------------------------------------------------
# (c) PROTOTYPE NOT ADMISSIBLE — all three rejection paths, with messages.
# ---------------------------------------------------------------------------
def test_c_highrise_rejected_by_min_lot_sf():
    parcel = Parcel(ssl="0700 0003", lot_area_sf=5_000, zone_code="D-5",
                    submarket_id="downtown", land_value=2_000_000,
                    improvement_value=0, land_use_code="vacant", improvement_ratio=0.0)
    rules = ZoningRules(district_code="D-5", max_far=10.0, max_height_ft=130,
                        max_stories=None,
                        lot_occupancy_pct={"residential": 1.00, "other": 1.00},
                        permitted_uses=[Use.RESIDENTIAL],
                        parking_ratio={"residential": 0.25})
    env = resolve_envelope(parcel, rules, Use.RESIDENTIAL, DEFAULT_ASSUMPTIONS)
    # floors = 130 // 10 = 13, so the story gate WOULD pass (highrise needs 12).
    # The lot gate fires first: 5,000 SF < highrise min_lot_sf 12,000.
    assert env.max_floors == 13

    with pytest.raises(NotPermitted) as exc:
        fit_program(env, PROTOTYPES["highrise"], rules, Use.RESIDENTIAL,
                    DEFAULT_ASSUMPTIONS, parcel)
    assert str(exc.value) == "highrise requires >= 12,000 SF lot; parcel is 5,000 SF"


def test_c_midrise_rejected_by_story_count():
    parcel = Parcel(ssl="0800 0004", lot_area_sf=10_000, zone_code="TEST-L",
                    submarket_id="ward5", land_value=500_000,
                    improvement_value=0, land_use_code="vacant", improvement_ratio=0.0)
    rules = ZoningRules(district_code="TEST-L", max_far=2.5, max_height_ft=40,
                        max_stories=None,
                        lot_occupancy_pct={"residential": 0.60, "other": 0.80},
                        permitted_uses=[Use.RESIDENTIAL],
                        parking_ratio={"residential": 0.5})
    env = resolve_envelope(parcel, rules, Use.RESIDENTIAL, DEFAULT_ASSUMPTIONS)
    # ENVELOPE HAND CHECK
    #   floors       = 40 // 10          = 4   (limiter "height")
    #   far_gsf      = 10,000 * 2.5      = 25,000
    #   footprint    = 10,000 * 0.60     = 6,000
    #   coverage_gsf = 6,000 * 4         = 24,000
    #   far 25,000 > coverage 24,000 -> max_gsf = 24,000, binding = "height"
    assert env.max_buildable_gsf == 24_000
    assert env.max_floors == 4
    assert env.binding_constraint == "height"

    # lot 10,000 >= midrise min_lot 8,000, so the lot gate passes and the story gate fires.
    # v1.8 raised midrise's floor from 5 storeys to 8.
    with pytest.raises(NotPermitted) as exc:
        fit_program(env, PROTOTYPES["midrise"], rules, Use.RESIDENTIAL,
                    DEFAULT_ASSUMPTIONS, parcel)
    assert str(exc.value) == "midrise needs >= 8 stories; TEST-L allows 4 (gated by height)"

    # And the band below it picks the parcel up: four storeys is 5-over-1's minimum, so
    # raising midrise's floor did not leave a hole in the height range.
    prog = fit_program(env, PROTOTYPES["5-over-1"], rules, Use.RESIDENTIAL,
                       DEFAULT_ASSUMPTIONS, parcel)
    assert prog.floors == 4
    assert prog.construction_type == ConstructionType.WOOD_OVER_PODIUM


def test_c_use_not_permitted():
    parcel = Parcel(ssl="0900 0005", lot_area_sf=20_000, zone_code="PDR-1",
                    submarket_id="ward5", land_value=400_000,
                    improvement_value=0, land_use_code="industrial", improvement_ratio=0.0)
    rules = ZoningRules(district_code="PDR-1", max_far=3.0, max_height_ft=60,
                        max_stories=None,
                        lot_occupancy_pct={"residential": 0.60, "other": 0.80},
                        permitted_uses=[Use.OFFICE],
                        parking_ratio={"residential": 0.5})
    env = resolve_envelope(parcel, rules, Use.RESIDENTIAL, DEFAULT_ASSUMPTIONS)
    with pytest.raises(NotPermitted) as exc:
        fit_program(env, PROTOTYPES["garden"], rules, Use.RESIDENTIAL,
                    DEFAULT_ASSUMPTIONS, parcel)
    assert str(exc.value) == "residential not permitted in PDR-1"


# ---------------------------------------------------------------------------
# (d) NEGATIVE RLV — expensive concrete highrise against soft rents.
# ---------------------------------------------------------------------------
def test_d_negative_rlv_highrise():
    parcel = Parcel(ssl="1100 0007", lot_area_sf=15_000, zone_code="TEST-D",
                    submarket_id="ward7", land_value=3_000_000,
                    improvement_value=0, land_use_code="vacant", improvement_ratio=0.0)
    rules = ZoningRules(district_code="TEST-D", max_far=10.0, max_height_ft=130,
                        max_stories=None,
                        lot_occupancy_pct={"residential": 1.00, "other": 1.00},
                        permitted_uses=[Use.RESIDENTIAL],
                        parking_ratio={"residential": 0.25})
    market = _market(rent=2.50, cap=0.065,
                     hard={**HARD_COST_PSF, ConstructionType.CONCRETE_I: 430})

    env = resolve_envelope(parcel, rules, Use.RESIDENTIAL, DEFAULT_ASSUMPTIONS)
    # ENVELOPE HAND CHECK
    #   floors       = 130 // 10          = 13
    #   far_gsf      = 15,000 * 10.0      = 150,000
    #   footprint    = 15,000 * 1.00      = 15,000
    #   coverage_gsf = 15,000 * 13        = 195,000
    #   far 150,000 <= 195,000 -> max_gsf = 150,000, binding = "far"
    assert env.max_buildable_gsf == 150_000
    assert env.binding_constraint == "far"

    prog = fit_program(env, PROTOTYPES["highrise"], rules, Use.RESIDENTIAL,
                       DEFAULT_ASSUMPTIONS, parcel)
    # PROGRAM HAND CHECK (highrise: 13-30 stories, min_lot 12,000, eff 0.85, structured)
    #   floors   = min(30, 13)                          = 13   (exactly at the v1.8 floor)
    #   gross_sf = min(150,000, 15,000*13=195,000)      = 150,000
    #   net      = 150,000 * 0.85                       = 127,500
    #   avg_sf   = .30*480 + .50*720 + .20*1000
    #            = 144 + 360 + 200                      = 704
    #   units    = int(127,500 // 704) = int(181.107)   = 181
    #   stalls   = round(181 * 0.25) = round(45.25)     = 45
    assert prog.floors == 13
    assert prog.gross_sf == 150_000
    assert prog.net_rentable_sf == pytest.approx(127_500)
    assert prog.unit_count == 181
    assert prog.parking_stalls == 45

    # RLV HAND CHECK — this market overrides concrete to $430/SF, and highrise then carries
    # the v1.8 height factor on top of it (§5 HARD_COST_FACTOR = 1.0625): the same concrete
    # system costs more to build tall.
    #   hard $/SF         = 430 * 1.0625              =    456.875
    #   rent_psf          = 2.50 * 1.60               =  4.00
    #   exit_cap          = 0.065 - 0.0050            =  0.060
    #   gross_residential = 127,500 * 4.00 * 12       =  6,120,000
    #   egi               = 6,120,000 * 0.94          =  5,752,800
    #   noi               = 5,752,800 * 0.65          =  3,739,320
    #   exit_value        = 3,739,320 / 0.060         = 62,322,000  (exact)
    #   hard shell        = 150,000 * 456.875         = 68,531,250
    #   hard parking      = 45 * 35,000 (structured)  =  1,575,000
    #   hard              =                             70,106,250
    #   soft              = 70,106,250 * 0.20         = 14,021,250
    #   contingency       = 70,106,250 * 0.05         =  3,505,312.50
    #   cost_ex_land      =                             87,632,812.50
    #   profit            = 62,322,000 * 0.15         =  9,348,300
    #   RLV = 62,322,000 - 87,632,812.50 - 9,348,300  = -34,659,112.50
    #   gap = -34,659,112.50 - 3,000,000              = -37,659,112.50
    # Still deeply negative, which is the whole point of case (d): $2.50 base rent cannot
    # carry $430/SF concrete at any premium. v1.8 moved it FURTHER under, not closer — the
    # efficiency gain (0.80 -> 0.85) adds revenue, and the height factor adds more cost than
    # the revenue is worth. The tier split is not a subsidy for going tall.
    out = screening_rlv(prog, market, DEFAULT_ASSUMPTIONS, parcel)
    assert out.screening_rlv == pytest.approx(-34_659_112.50, abs=1.0)
    assert out.feasibility_gap == pytest.approx(-37_659_112.50, abs=1.0)
    assert out.feasibility_gap < 0


# ---------------------------------------------------------------------------
# (e) REQUIRED GROUND-FLOOR ACTIVE USE (v1.3.2). The ground floorplate is costed at
#     hard $/SF but earns nothing. The carve-out is gated on the PROTOTYPE as well as
#     the district: only midrise/highrise plausibly have a commercial ground floor, so
#     townhome and garden are exempt even inside a mandating district.
# ---------------------------------------------------------------------------
def _gfa_case():
    """A mandating district tall enough to admit midrise (min_stories = 5)."""
    parcel = Parcel(ssl="0500 0012", lot_area_sf=20_000, zone_code="TEST-GFA",
                    submarket_id="ward5", land_value=1_000_000,
                    improvement_value=0, land_use_code="vacant", improvement_ratio=0.0)
    rules = ZoningRules(district_code="TEST-GFA", max_far=6.0, max_height_ft=60,
                        max_stories=None,
                        lot_occupancy_pct={"residential": 0.60, "other": 0.80},
                        permitted_uses=[Use.RESIDENTIAL],
                        parking_ratio={"residential": 1.0},
                        requires_ground_floor_active=True)
    return parcel, rules


def test_e_ground_floor_active_carveout_applies_to_five_over_one():
    parcel, rules = _gfa_case()
    env = resolve_envelope(parcel, rules, Use.RESIDENTIAL, DEFAULT_ASSUMPTIONS)
    # ENVELOPE HAND CHECK
    #   floors_by_height = 60 // 10                  = 6   (max_stories None -> "height")
    #   far_gsf          = 20,000 * 6.0              = 120,000
    #   footprint        = 20,000 * 0.60             = 12,000
    #   coverage_gsf     = 12,000 * 6                = 72,000
    #   coverage 72,000 < far 120,000 -> max_gsf = 72,000, binding = "height"
    assert env.max_floors == 6
    assert env.max_buildable_gsf == 72_000
    assert env.binding_constraint == "height"

    # Six storeys is the 5-over-1 band in v1.8. It is in GROUND_FLOOR_ACTIVE_PROTOTYPES —
    # the most literal member of that set, since the "1" in the name IS the podium.
    prog = fit_program(env, PROTOTYPES["5-over-1"], rules, Use.RESIDENTIAL,
                       DEFAULT_ASSUMPTIONS, parcel)
    # PROGRAM HAND CHECK
    #   floors             = min(7, 6)                            = 6
    #   gross_sf           = min(72,000, 12,000 * 6)              = 72,000
    #   required_active_sf = min(footprint 12,000, gross 72,000)  = 12,000
    #   residential_gsf    = 72,000 - 12,000                      = 60,000
    #   net                = 60,000 * 0.85                        = 51,000
    #   avg_sf   = 0.25*500 + 0.50*750 + 0.25*1050                = 762.5
    #   units    = int(51,000 // 762.5) = int(66.885)             = 66
    #   stalls   = round(66 * 1.0)                                = 66
    #   gross_sf stays 72,000 -> the shell IS costed
    assert prog.gross_sf == 72_000
    assert prog.retail_sf == 12_000
    assert prog.net_rentable_sf == pytest.approx(51_000)
    assert prog.unit_count == 66
    assert prog.parking_stalls == 66

    out = screening_rlv(prog, _market(), DEFAULT_ASSUMPTIONS, parcel)
    # RLV HAND CHECK — 5-over-1 carries the 1.40 premium and -25 bps, same as midrise, and
    # wood-over-podium's $260/SF. Efficiency 0.85 applies to the RESIDENTIAL gross only: the
    # mandated ground floor is carved out above, so the 12,000 SF is costed at full shell
    # and never enters net.
    #   rent_psf          = 3.20 * 1.40                  =  4.48
    #   exit_cap          = 0.055 - 0.0025               =  0.0525
    #   gross_residential = 51,000 * 4.48 * 12           =  2,741,760
    #   egi               = 2,741,760 * 0.94             =  2,577,254.40
    #   noi               = 2,577,254.40 * 0.65          =  1,675,215.36
    #   exit_value        = 1,675,215.36 / 0.0525        = 31,908,864    (exact)
    #   hard shell        = 72,000 * 260 (FULL gross)    = 18,720,000
    #   hard parking      = 66 * 45,000 (podium)         =  2,970,000
    #   hard              =                                21,690,000
    #   soft              = 21,690,000 * 0.20            =  4,338,000
    #   contingency       = 21,690,000 * 0.05            =  1,084,500
    #   cost_ex_land      =                                27,112,500
    #   profit            = 31,908,864 * 0.15            =  4,786,329.60
    #   RLV = 31,908,864 - 27,112,500 - 4,786,329.60     =     10,034.40
    #
    # Barely positive, where the same case priced as concrete was -7.19M. Worth keeping in
    # view: the mandate still costs this parcel its whole margin — a 12,000 SF ground floor
    # costed at full shell and earning nothing leaves an RLV of ten thousand dollars on a
    # $27M build, and the feasibility gap against a $1M assessed value is still negative.
    assert out.screening_rlv == pytest.approx(10_034.40, abs=1.0)
    assert out.feasibility_gap == pytest.approx(-989_965.60, abs=1.0)


@pytest.mark.parametrize("proto_id", ["townhome", "garden"])
def test_e_ground_floor_active_exempts_low_rise(proto_id):
    """v1.3.2: a rowhouse or walk-up never carries a mandated commercial ground floor.

    Same parcel and same mandating district as the midrise case above. The program must
    come out identical to the one the *unmandated* district produces — no floorplate is
    carved out, so no revenue is lost. Before v1.3.2 this cost townhome ~108 $/SF of RLV
    in every mandated district and was what inverted the map.
    """
    parcel, rules = _gfa_case()
    env = resolve_envelope(parcel, rules, Use.RESIDENTIAL, DEFAULT_ASSUMPTIONS)
    unmandated = replace(rules, requires_ground_floor_active=False)

    on = fit_program(env, PROTOTYPES[proto_id], rules, Use.RESIDENTIAL,
                     DEFAULT_ASSUMPTIONS, parcel)
    off = fit_program(env, PROTOTYPES[proto_id], unmandated, Use.RESIDENTIAL,
                      DEFAULT_ASSUMPTIONS, parcel)

    assert on.retail_sf == 0.0
    # every square foot built is residential -> net is the full efficiency ratio of gross
    assert on.net_rentable_sf == pytest.approx(
        on.gross_sf * PROTOTYPES[proto_id].efficiency_ratio
    )
    assert on == off


# ---------------------------------------------------------------------------
# Cross-cutting behaviors the spec calls out explicitly.
# ---------------------------------------------------------------------------
def test_feasibility_gap_is_none_when_land_value_missing():
    parcel = Parcel(ssl="1200 0008", lot_area_sf=20_000, zone_code="TEST-H",
                    submarket_id="ward5", land_value=None,
                    improvement_value=None, land_use_code="exempt", improvement_ratio=None)
    rules = ZoningRules(district_code="TEST-H", max_far=6.0, max_height_ft=40,
                        max_stories=None,
                        lot_occupancy_pct={"residential": 0.60, "other": 0.80},
                        permitted_uses=[Use.RESIDENTIAL],
                        parking_ratio={"residential": 1.0})
    env = resolve_envelope(parcel, rules, Use.RESIDENTIAL, DEFAULT_ASSUMPTIONS)
    prog = fit_program(env, PROTOTYPES["garden"], rules, Use.RESIDENTIAL,
                       DEFAULT_ASSUMPTIONS, parcel)
    out = screening_rlv(prog, _market(), DEFAULT_ASSUMPTIONS, parcel)
    assert out.feasibility_gap is None
    assert out.screening_rlv == pytest.approx(1_875_359.672727, abs=1.0)


def test_stories_cap_binds_before_height():
    parcel = Parcel(ssl="1300 0009", lot_area_sf=20_000, zone_code="TEST-S",
                    submarket_id="ward5", land_value=1_000_000,
                    improvement_value=0, land_use_code="vacant", improvement_ratio=0.0)
    rules = ZoningRules(district_code="TEST-S", max_far=6.0, max_height_ft=40,
                        max_stories=3,
                        lot_occupancy_pct={"residential": 0.60, "other": 0.80},
                        permitted_uses=[Use.RESIDENTIAL],
                        parking_ratio={"residential": 1.0})
    env = resolve_envelope(parcel, rules, Use.RESIDENTIAL, DEFAULT_ASSUMPTIONS)
    # floors_by_height = 4, but max_stories 3 < 4 -> floors = 3, limiter "stories"
    #   far_gsf 120,000 > coverage 12,000*3 = 36,000 -> binding = "stories"
    assert env.max_floors == 3
    assert env.max_buildable_gsf == 36_000
    assert env.binding_constraint == "stories"


def test_demolition_toggle_lowers_rlv_by_demo_cost_plus_soft_and_contingency():
    from dataclasses import replace as dc_replace

    parcel = Parcel(ssl="1400 0010", lot_area_sf=20_000, zone_code="TEST-H",
                    submarket_id="ward5", land_value=1_000_000,
                    improvement_value=0, land_use_code="improved", improvement_ratio=0.0,
                    existing_building_sf=10_000)
    rules = ZoningRules(district_code="TEST-H", max_far=6.0, max_height_ft=40,
                        max_stories=None,
                        lot_occupancy_pct={"residential": 0.60, "other": 0.80},
                        permitted_uses=[Use.RESIDENTIAL],
                        parking_ratio={"residential": 1.0})
    env = resolve_envelope(parcel, rules, Use.RESIDENTIAL, DEFAULT_ASSUMPTIONS)
    prog = fit_program(env, PROTOTYPES["garden"], rules, Use.RESIDENTIAL,
                       DEFAULT_ASSUMPTIONS, parcel)

    off = screening_rlv(prog, _market(), DEFAULT_ASSUMPTIONS, parcel)
    demo_on = dc_replace(DEFAULT_ASSUMPTIONS,
                         cost={**DEFAULT_ASSUMPTIONS.cost, "include_demolition": True})
    on = screening_rlv(prog, _market(), demo_on, parcel)
    # HAND CHECK: demo = 10,000 SF * $12/SF = 120,000 of hard cost.
    # It carries soft (20%) and contingency (5%) with it: 120,000 * 1.25 = 150,000.
    assert off.screening_rlv - on.screening_rlv == pytest.approx(150_000, abs=1.0)


def test_confidence_is_provenance_weighted():
    # v1.5: every PROVENANCE entry is "national" at baseline, including the three a
    # MarketData row can supply. With no row — or a fallback row that tailors nothing —
    # every input really is a national default, so the honest score is 0.0.
    #
    # The size is pinned because every input dilutes confidence on every parcel in the
    # city: changing it is allowed, but it needs a re-bake and a deliberate edit here
    # rather than passing silently. 27 as of v1.6 (`irr_hurdle` added, §2.6). v1.7 changed
    # the VALUES of the product-type factors but added no key, so the count is unmoved —
    # and efficiency_ratio is not in here at all, being a prototype attribute rather than a
    # market input. §11 records that as a gap in what confidence can see.
    assert len(PROVENANCE) == 27
    assert set(PROVENANCE.values()) == {"national"}
    assert score_confidence(PROVENANCE) == 0.0
    assert score_confidence(PROVENANCE, _market()) == 0.0
    # The three a MarketData row may promote must be present to be promotable.
    assert {"rent_psf_residential_monthly", "exit_cap_rate", "hard_cost_psf"} <= set(PROVENANCE)
    # Both return figures exist and are distinct concepts (§2.6): NPV discount rate vs.
    # the levered hurdle `solve_irr_rlv` solves against.
    assert "discount_rate" in PROVENANCE and "irr_hurdle" in PROVENANCE


def test_confidence_varies_with_what_the_market_row_actually_sources():
    # A row promotes only the inputs its own `input_provenance` claims. The DC seed
    # researches rent and cap but not construction cost, and some wards' caps are borrowed
    # comparables — so wards land on different scores. This is the map's confidence spread.
    fully_sourced = _market()
    fully_sourced.input_provenance = {
        "rent_psf_residential_monthly": "submarket",
        "exit_cap_rate": "submarket",
        "hard_cost_psf": "national",
    }
    rent_only = _market()
    rent_only.input_provenance = {
        "rent_psf_residential_monthly": "submarket",
        "exit_cap_rate": "national",
        "hard_cost_psf": "national",
    }
    # Denominator is the size of the input set, not a literal: adding a genuine input is a
    # normal event and should fail `test_provenance_input_set_is_pinned` (which exists to
    # make that visible), not these two, which are about sourcing behavior.
    n = len(PROVENANCE)
    assert score_confidence(PROVENANCE, fully_sourced) == pytest.approx(1.0 / n)
    assert score_confidence(PROVENANCE, rent_only) == pytest.approx(0.5 / n)
    assert score_confidence(PROVENANCE, fully_sourced) > score_confidence(
        PROVENANCE, rent_only
    ) > score_confidence(PROVENANCE, _market())


def test_market_row_can_only_raise_an_input_not_lower_it():
    # Promotion is one-way (§2.8): a row tagging an input "national" must never pull down a
    # baseline that some future parcel-level source already raised to "local".
    upgraded = dict(PROVENANCE, rent_psf_residential_monthly="local")
    downgrader = _market()
    downgrader.input_provenance = {"rent_psf_residential_monthly": "national"}
    assert score_confidence(upgraded, downgrader) == pytest.approx(1.0 / len(PROVENANCE))


# ---------------------------------------------------------------------------
# Tier 2: the full monthly levered model and the solvers.
# ---------------------------------------------------------------------------
def _garden_deal():
    parcel = Parcel(ssl="1500 0011", lot_area_sf=20_000, zone_code="TEST-H",
                    submarket_id="ward5", land_value=1_000_000,
                    improvement_value=0, land_use_code="vacant", improvement_ratio=0.0)
    rules = ZoningRules(district_code="TEST-H", max_far=6.0, max_height_ft=40,
                        max_stories=None,
                        lot_occupancy_pct={"residential": 0.60, "other": 0.80},
                        permitted_uses=[Use.RESIDENTIAL],
                        parking_ratio={"residential": 1.0})
    env = resolve_envelope(parcel, rules, Use.RESIDENTIAL, DEFAULT_ASSUMPTIONS)
    prog = fit_program(env, PROTOTYPES["garden"], rules, Use.RESIDENTIAL,
                       DEFAULT_ASSUMPTIONS, parcel)
    return parcel, prog, _market()


def test_full_cashflow_structure_and_timing():
    parcel, prog, market = _garden_deal()
    cf, out = full_cashflow(prog, market, DEFAULT_ASSUMPTIONS, parcel, land=1_500_000)

    # TIMELINE HAND CHECK (wood_v -> 24 construction months, not the 30 for concrete):
    #   p = 12, c = 24, l = 12, h = 3 -> stabilization = 48, T = 51, arrays are 52 long
    assert cf.phase_bounds == {"predev_end": 12, "construction_end": 36,
                               "stabilization": 48, "sale": 51}
    assert len(cf.equity_cf) == 52

    assert cf.land[0] == 1_500_000
    assert cf.land[1:].sum() == 0
    # hard costs land only in construction months [12, 36)
    assert cf.hard_cost[:12].sum() == 0
    assert cf.hard_cost[36:].sum() == 0
    # soft costs spread straight-line over predev + construction = 36 months
    assert cf.soft_cost[35] == pytest.approx(cf.soft_cost[0])
    assert cf.soft_cost[36:].sum() == 0
    # zero revenue before lease-up begins at month 36
    assert cf.noi[:36].sum() == 0
    assert cf.noi[36] > 0
    # S-curve: the middle construction month draws more than the first
    assert cf.hard_cost[24] > cf.hard_cost[12]
    # construction loan is retired by the perm takeout at stabilization
    assert cf.construction_balance[47] > 0
    assert cf.construction_balance[48] == 0
    assert cf.perm_balance[48] > 0
    # perm amortizes during the hold
    assert cf.perm_balance[51] < cf.perm_balance[48]

    assert out.total_development_cost > cf.land.sum() + cf.hard_cost.sum()  # + capitalized interest
    assert out.peak_equity > 0
    assert out.exit_value > 0


def test_demolition_is_spent_in_first_construction_month():
    from dataclasses import replace as dc_replace

    parcel, prog, market = _garden_deal()
    parcel = dc_replace(parcel, existing_building_sf=10_000)
    demo_on = dc_replace(DEFAULT_ASSUMPTIONS,
                         cost={**DEFAULT_ASSUMPTIONS.cost, "include_demolition": True})

    base, _ = full_cashflow(prog, market, DEFAULT_ASSUMPTIONS, parcel)
    with_demo, _ = full_cashflow(prog, market, demo_on, parcel)
    # 10,000 SF * $12 = 120,000, escalated 12 months at 3%/yr -> 120,000 * 1.03 = 123,600
    assert with_demo.hard_cost[12] - base.hard_cost[12] == pytest.approx(123_600, abs=1.0)


def test_safe_irr_returns_none_instead_of_raising():
    assert safe_irr([-100.0, -100.0, -100.0]) is None       # never turns positive
    assert safe_irr([0.0, 0.0, 0.0]) is None                # degenerate
    # a clean doubling over 12 months annualizes to ~100%
    assert safe_irr([-100.0] + [0.0] * 11 + [200.0]) == pytest.approx(1.0, abs=0.02)


def test_solve_irr_rlv_finds_land_that_hits_the_hurdle():
    parcel, prog, market = _garden_deal()
    land, unachievable = solve_irr_rlv(prog, market, DEFAULT_ASSUMPTIONS, parcel, hurdle=0.15)
    assert not unachievable
    assert land > 0
    _, out = full_cashflow(prog, market, DEFAULT_ASSUMPTIONS, parcel, land=land)
    assert out.irr == pytest.approx(0.15, abs=1e-4)


def test_solve_irr_rlv_flags_unachievable_hurdle_instead_of_raising():
    parcel, prog, market = _garden_deal()
    land, unachievable = solve_irr_rlv(prog, market, DEFAULT_ASSUMPTIONS, parcel, hurdle=5.0)
    assert unachievable
    assert land == 0.0


def test_engine_imports_nothing_but_stdlib_numpy_scipy():
    """engine/ is pure (CLAUDE.md non-negotiable): no DB, no network, no file I/O."""
    import ast
    import pathlib

    allowed = {"engine", "numpy", "numpy_financial", "scipy", "dataclasses", "enum"}
    engine_dir = pathlib.Path(__file__).resolve().parent.parent / "engine"
    for path in sorted(engine_dir.glob("*.py")):
        imported = set()
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported <= allowed, f"{path.name} imports {sorted(imported - allowed)}"


def test_s_curve_fractions_sum_to_one():
    from engine.proforma import _s_curve_fractions

    for n in (12, 24, 30):
        f = _s_curve_fractions(n)
        assert len(f) == n
        assert f.sum() == pytest.approx(1.0)
        assert np.all(f > 0)


# ---------------------------------------------------------------------------
# The v1 product set. Pinned, because "which prototypes compete" is a product decision
# that the bake reads without announcing, and both directions of drift are silent:
# un-benching garden would put a dominated product back on the map, and benching another
# would shrink the library with nothing failing.
# ---------------------------------------------------------------------------
def test_garden_is_defined_but_benched():
    # Defined: the library is still complete, so a stored row or an old batch naming garden
    # can be looked up rather than crashing.
    assert set(PROTOTYPES) == {"townhome", "garden", "5-over-1", "midrise", "highrise"}
    assert PROTOTYPES["garden"].efficiency_ratio == 0.85

    # Benched: it is not a candidate, so it can never be `is_best`.
    assert DISABLED_PROTOTYPES == frozenset({"garden"})
    assert set(ACTIVE_PROTOTYPES) == {"townhome", "5-over-1", "midrise", "highrise"}
    assert "garden" not in ACTIVE_PROTOTYPES
    assert ACTIVE_PROTOTYPES["townhome"] is PROTOTYPES["townhome"]


def test_the_story_bands_are_contiguous_and_non_overlapping():
    """No overlaps and no gaps across the ACTIVE set (§5).

    This constrains what each tier BUILDS, not which tiers are ADMISSIBLE — admissibility
    is `min_stories <= envelope.max_floors`, so a tall envelope admits several tiers at
    once and they compete on RLV (see `test_tall_envelopes_admit_several_tiers`). What the
    bands guarantee is that no two tiers can produce the same building height, and that no
    height between 2 and 30 is left without a product that tops out at it.

    Garden is excluded because it is benched — its 2-4 band overlaps two others, which is
    part of why it cannot compete.
    """
    bands = sorted(
        (p.min_stories, p.max_stories, pid) for pid, p in ACTIVE_PROTOTYPES.items()
    )
    assert bands == [
        (2, 3, "townhome"),
        (4, 7, "5-over-1"),
        (8, 12, "midrise"),
        (13, 30, "highrise"),
    ]
    for (_, upper, _), (lower, _, _) in zip(bands, bands[1:]):
        assert lower == upper + 1


def test_tall_envelopes_admit_several_tiers():
    """The corrective to reading the bands as a partition of admissibility.

    A 9-floor envelope admits townhome, 5-over-1 AND midrise; each builds to its own cap
    and the pro forma picks. Pinned because the tempting "simplification" — snapping a
    parcel to the single tier whose band contains `max_floors` — would silently force the
    tallest option and rebuild the v1.7 defect (density winning by construction) in a new
    place.
    """
    parcel = Parcel(ssl="2873 1110", lot_area_sf=116_161, zone_code="RA-5",
                    submarket_id="ward1", land_value=5_000_000,
                    improvement_value=0, land_use_code="vacant", improvement_ratio=0.0)
    rules = ZoningRules(district_code="RA-5", max_far=6.0, max_height_ft=90,
                        max_stories=None,
                        lot_occupancy_pct={"residential": 0.80, "other": 0.80},
                        permitted_uses=[Use.RESIDENTIAL],
                        parking_ratio={"residential": 0.5})
    env = resolve_envelope(parcel, rules, Use.RESIDENTIAL, DEFAULT_ASSUMPTIONS)
    assert env.max_floors == 9

    built = {}
    for pid in ("townhome", "5-over-1", "midrise"):
        prog = fit_program(env, PROTOTYPES[pid], rules, Use.RESIDENTIAL,
                           DEFAULT_ASSUMPTIONS, parcel)
        built[pid] = prog.floors
    # Each stops at its OWN ceiling, not the envelope's.
    assert built == {"townhome": 3, "5-over-1": 7, "midrise": 9}

    # 13 > 9, so the one tier whose band starts above the envelope is genuinely out.
    with pytest.raises(NotPermitted):
        fit_program(env, PROTOTYPES["highrise"], rules, Use.RESIDENTIAL,
                    DEFAULT_ASSUMPTIONS, parcel)

    # And the shorter wood building beats the taller concrete one, which is the whole
    # economic claim of the v1.8 split.
    market = _market(rent=3.40, cap=0.05)
    rlv = {
        pid: screening_rlv(
            fit_program(env, PROTOTYPES[pid], rules, Use.RESIDENTIAL,
                        DEFAULT_ASSUMPTIONS, parcel),
            market, DEFAULT_ASSUMPTIONS, parcel,
        ).screening_rlv
        for pid in built
    }
    assert rlv["5-over-1"] > rlv["midrise"] > rlv["townhome"]


def test_cost_tables_agree():
    """`NATIONAL_HARD_COST_PSF` must equal construction-type cost x height factor.

    Two tables describing the same dollars is a drift risk, and the per-prototype one is
    only a fallback — so it is the one that would go stale unnoticed while the pro forma
    quietly used the other.
    """
    from data.loaders.seed_market import FALLBACK_COST_PSF

    for pid, proto in PROTOTYPES.items():
        base = FALLBACK_COST_PSF[proto.construction_type.value]
        assert hard_cost_psf(base, pid) == pytest.approx(NATIONAL_HARD_COST_PSF[pid]), pid

    # The requested v1.8 schedule, spelled out so a silent edit to either table fails here.
    assert NATIONAL_HARD_COST_PSF["townhome"] == 220
    assert NATIONAL_HARD_COST_PSF["5-over-1"] == 260
    assert NATIONAL_HARD_COST_PSF["midrise"] == 320
    assert NATIONAL_HARD_COST_PSF["highrise"] == 340
    # Same structural system, different price — that is the factor's whole job.
    assert (
        PROTOTYPES["midrise"].construction_type
        == PROTOTYPES["highrise"].construction_type
    )


def test_the_two_multifamily_tiers_are_one_product_to_the_user():
    """5-over-1 and midrise differ ONLY in how they are built, never in how they sell."""
    from api.vocabulary import PROTOTYPE_LABELS

    assert RENT_PREMIUM_FACTOR["5-over-1"] == RENT_PREMIUM_FACTOR["midrise"]
    assert EXIT_CAP_ADJUSTMENT["5-over-1"] == EXIT_CAP_ADJUSTMENT["midrise"]
    assert (
        PROTOTYPES["5-over-1"].efficiency_ratio == PROTOTYPES["midrise"].efficiency_ratio
    )
    assert (
        PROTOTYPES["5-over-1"].default_unit_mix == PROTOTYPES["midrise"].default_unit_mix
    )
    # ...and they cost different amounts, which is the reason they are separate at all.
    assert NATIONAL_HARD_COST_PSF["5-over-1"] != NATIONAL_HARD_COST_PSF["midrise"]

    # One user-facing name over both, and three labels over the four active prototypes.
    assert PROTOTYPE_LABELS["5-over-1"] == PROTOTYPE_LABELS["midrise"] == "Multifamily"
    assert {PROTOTYPE_LABELS[pid] for pid in ACTIVE_PROTOTYPES} == {
        "Townhome", "Multifamily", "High-rise",
    }


def test_garden_is_no_longer_dominated_and_the_bench_is_now_a_product_choice():
    """The bench outlived its original justification. This test says so out loud.

    History, because it matters for whether the bench should survive:
      v1.7  townhome premium 1.15, garden 1.00 -> garden dominated on every axis; it won
            0 of the 2,503 parcels it was admissible on. Benching cost nothing.
      v1.8  townhome returned to 1.00 -> equal rent, garden losing only on efficiency and
            the fourth floor's cost. Still dominated, by 5.9%.
      v1.9  townhome cut to 0.90 -> garden now EARNS MORE per dollar of shell than
            townhome. Measured over the real bake with the full library ranked on
            rlv_total, garden takes 1,679 of 79,073 scored parcels (67% of its admissible
            set), beating townhome on 1,604 of them and 5-over-1 on 75.

    So `DISABLED_PROTOTYPES` is no longer hiding a product that cannot win. It is hiding
    1,679 parcels whose best build is a garden walk-up and which currently display as
    something else. That may still be the right product call — three build types demo
    better than four — but it is a presentation decision now, not a modeling one, and
    §11 records it as such.
    """
    town, garden = PROTOTYPES["townhome"], PROTOTYPES["garden"]
    town_rev = town.max_stories * town.efficiency_ratio * RENT_PREMIUM_FACTOR["townhome"]
    garden_rev = garden.max_stories * garden.efficiency_ratio * RENT_PREMIUM_FACTOR["garden"]
    town_cost = town.max_stories * NATIONAL_HARD_COST_PSF["townhome"]
    garden_cost = garden.max_stories * NATIONAL_HARD_COST_PSF["garden"]

    assert RENT_PREMIUM_FACTOR["townhome"] == 0.90
    assert RENT_PREMIUM_FACTOR["garden"] == 1.00
    assert town_rev == pytest.approx(2.43)      # 3 x 0.90 x 0.90
    assert garden_rev == pytest.approx(3.40)    # 4 x 0.85 x 1.00
    assert (town_cost, garden_cost) == (660, 880)

    # The flip. Garden now returns ~4.9% more revenue-area per dollar of shell.
    assert garden_rev / garden_cost > town_rev / town_cost
    assert (garden_rev / garden_cost) / (town_rev / town_cost) == pytest.approx(
        1.049, abs=5e-4
    )

    # Benched regardless — deliberately, and this is the line to delete to bring it back.
    assert DISABLED_PROTOTYPES == frozenset({"garden"})


def test_the_story_bands_are_contiguous_and_non_overlapping():
    """No overlaps and no gaps across the ACTIVE set (§5).

    This constrains what each tier BUILDS, not which tiers are ADMISSIBLE — admissibility
    is `min_stories <= envelope.max_floors`, so a tall envelope admits several tiers at
    once and they compete on RLV (see `test_tall_envelopes_admit_several_tiers`). What the
    bands guarantee is that no two tiers can produce the same building height, and that no
    height between 2 and 30 is left without a product that tops out at it.

    Garden is excluded because it is benched — its 2-4 band overlaps two others, which is
    part of why it cannot compete.
    """
    bands = sorted(
        (p.min_stories, p.max_stories, pid) for pid, p in ACTIVE_PROTOTYPES.items()
    )
    assert bands == [
        (2, 3, "townhome"),
        (4, 7, "5-over-1"),
        (8, 12, "midrise"),
        (13, 30, "highrise"),
    ]
    for (_, upper, _), (lower, _, _) in zip(bands, bands[1:]):
        assert lower == upper + 1


def test_tall_envelopes_admit_several_tiers():
    """The corrective to reading the bands as a partition of admissibility.

    A 9-floor envelope admits townhome, 5-over-1 AND midrise; each builds to its own cap
    and the pro forma picks. Pinned because the tempting "simplification" — snapping a
    parcel to the single tier whose band contains `max_floors` — would silently force the
    tallest option and rebuild the v1.7 defect (density winning by construction) in a new
    place.
    """
    parcel = Parcel(ssl="2873 1110", lot_area_sf=116_161, zone_code="RA-5",
                    submarket_id="ward1", land_value=5_000_000,
                    improvement_value=0, land_use_code="vacant", improvement_ratio=0.0)
    rules = ZoningRules(district_code="RA-5", max_far=6.0, max_height_ft=90,
                        max_stories=None,
                        lot_occupancy_pct={"residential": 0.80, "other": 0.80},
                        permitted_uses=[Use.RESIDENTIAL],
                        parking_ratio={"residential": 0.5})
    env = resolve_envelope(parcel, rules, Use.RESIDENTIAL, DEFAULT_ASSUMPTIONS)
    assert env.max_floors == 9

    built = {}
    for pid in ("townhome", "5-over-1", "midrise"):
        prog = fit_program(env, PROTOTYPES[pid], rules, Use.RESIDENTIAL,
                           DEFAULT_ASSUMPTIONS, parcel)
        built[pid] = prog.floors
    # Each stops at its OWN ceiling, not the envelope's.
    assert built == {"townhome": 3, "5-over-1": 7, "midrise": 9}

    # 13 > 9, so the one tier whose band starts above the envelope is genuinely out.
    with pytest.raises(NotPermitted):
        fit_program(env, PROTOTYPES["highrise"], rules, Use.RESIDENTIAL,
                    DEFAULT_ASSUMPTIONS, parcel)

    # And the shorter wood building beats the taller concrete one, which is the whole
    # economic claim of the v1.8 split.
    market = _market(rent=3.40, cap=0.05)
    rlv = {
        pid: screening_rlv(
            fit_program(env, PROTOTYPES[pid], rules, Use.RESIDENTIAL,
                        DEFAULT_ASSUMPTIONS, parcel),
            market, DEFAULT_ASSUMPTIONS, parcel,
        ).screening_rlv
        for pid in built
    }
    assert rlv["5-over-1"] > rlv["midrise"] > rlv["townhome"]


def test_cost_tables_agree():
    """`NATIONAL_HARD_COST_PSF` must equal construction-type cost x height factor.

    Two tables describing the same dollars is a drift risk, and the per-prototype one is
    only a fallback — so it is the one that would go stale unnoticed while the pro forma
    quietly used the other.
    """
    from data.loaders.seed_market import FALLBACK_COST_PSF

    for pid, proto in PROTOTYPES.items():
        base = FALLBACK_COST_PSF[proto.construction_type.value]
        assert hard_cost_psf(base, pid) == pytest.approx(NATIONAL_HARD_COST_PSF[pid]), pid

    # The requested v1.8 schedule, spelled out so a silent edit to either table fails here.
    assert NATIONAL_HARD_COST_PSF["townhome"] == 220
    assert NATIONAL_HARD_COST_PSF["5-over-1"] == 260
    assert NATIONAL_HARD_COST_PSF["midrise"] == 320
    assert NATIONAL_HARD_COST_PSF["highrise"] == 340
    # Same structural system, different price — that is the factor's whole job.
    assert (
        PROTOTYPES["midrise"].construction_type
        == PROTOTYPES["highrise"].construction_type
    )


def test_the_two_multifamily_tiers_are_one_product_to_the_user():
    """5-over-1 and midrise differ ONLY in how they are built, never in how they sell."""
    from api.vocabulary import PROTOTYPE_LABELS

    assert RENT_PREMIUM_FACTOR["5-over-1"] == RENT_PREMIUM_FACTOR["midrise"]
    assert EXIT_CAP_ADJUSTMENT["5-over-1"] == EXIT_CAP_ADJUSTMENT["midrise"]
    assert (
        PROTOTYPES["5-over-1"].efficiency_ratio == PROTOTYPES["midrise"].efficiency_ratio
    )
    assert (
        PROTOTYPES["5-over-1"].default_unit_mix == PROTOTYPES["midrise"].default_unit_mix
    )
    # ...and they cost different amounts, which is the reason they are separate at all.
    assert NATIONAL_HARD_COST_PSF["5-over-1"] != NATIONAL_HARD_COST_PSF["midrise"]

    # One user-facing name over both, and three labels over the four active prototypes.
    assert PROTOTYPE_LABELS["5-over-1"] == PROTOTYPE_LABELS["midrise"] == "Multifamily"
    assert {PROTOTYPE_LABELS[pid] for pid in ACTIVE_PROTOTYPES} == {
        "Townhome", "Multifamily", "High-rise",
    }
