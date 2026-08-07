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
from engine.prototypes import PROTOTYPES
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
# (a) FAR-BINDING — the SPEC §4 scaffold parcel, midrise in MU-4.
# ---------------------------------------------------------------------------
def test_a_far_binding_midrise_screening_rlv():
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

    prog = fit_program(env, PROTOTYPES["midrise"], rules, Use.RESIDENTIAL,
                       DEFAULT_ASSUMPTIONS, parcel)
    # PROGRAM HAND CHECK (midrise: 5-12 stories, min_lot 8,000, eff 0.80, podium)
    #   lot 10,000 >= min_lot 8,000            -> admissible
    #   min_stories 5 <= max_floors 5          -> admissible
    #   floors    = min(12, 5)                          = 5
    #   gross_sf  = min(25,000, 6,000*5=30,000)         = 25,000
    #   no ground-floor mandate -> residential_gsf      = 25,000
    #   net       = 25,000 * 0.80                       = 20,000
    #   avg_sf    = .25*500 + .50*750 + .25*1050
    #             = 125 + 375 + 262.5                   = 762.5
    #   units     = int(20,000 // 762.5) = int(26.229)  = 26
    #   mix       = studio int(6.5)=6 | 1br int(13.0)=13 | 2br int(6.5)=6
    #   stalls    = round(26 * 0.5) = round(13.0)       = 13
    assert prog.floors == 5
    assert prog.gross_sf == 25_000
    assert prog.net_rentable_sf == 20_000
    assert prog.unit_count == 26
    assert prog.unit_mix_counts == {"studio": 6, "1br": 13, "2br": 6}
    assert prog.parking_stalls == 13
    assert prog.retail_sf == 0.0
    assert prog.construction_type == ConstructionType.CONCRETE_I

    out = screening_rlv(prog, market, DEFAULT_ASSUMPTIONS, parcel)
    # RLV HAND CHECK — v1.4 product-type adjustment (§2.4) applies: midrise carries a
    # 1.15 rent premium and a -25 bps cap adjustment off the submarket base.
    #   rent_psf          = 3.20 * 1.15                       = 3.68
    #   exit_cap          = 0.055 - 0.0025                    = 0.0525
    #   gross_residential = 20,000 * 3.68 * 12                = 883,200
    #   egi               = 883,200 * 0.94                    = 830,208
    #   noi               = 830,208 * 0.65                    = 539,635.20
    #   exit_value        = 539,635.20 / 0.0525               = 10,278,765.714286
    #   hard shell        = 25,000 * 340                      = 8,500,000
    #   hard parking      = 13 * 45,000 (podium)              =   585,000
    #   hard              =                                     9,085,000
    #   soft              = 9,085,000 * 0.20                  = 1,817,000
    #   contingency       = 9,085,000 * 0.05                  =   454,250
    #   cost_ex_land      =                                    11,356,250   (cost is unchanged)
    #   profit            = 10,278,765.714286 * 0.15          = 1,541,814.857143
    #   RLV = 10,278,765.714286 - 11,356,250 - 1,541,814.857143
    #                                                         = -2,619,299.142857
    #   gap = -2,619,299.142857 - 1,100,000                   = -3,719,299.142857
    #   yoc = 539,635.20 / 11,356,250                         = 0.04751878
    #   margin = (10,278,765.714286 - 11,356,250) / 11,356,250 = -0.09488029
    # The premium+cap lift RLV by 1,484,936.31 vs the flat-rent model; still negative here,
    # which is the point of case (a) — FAR-bound midrise at $3.20 base rent does not pencil.
    assert out.screening_rlv == pytest.approx(-2_619_299.142857, abs=1.0)
    assert out.feasibility_gap == pytest.approx(-3_719_299.142857, abs=1.0)
    assert out.total_development_cost == pytest.approx(11_356_250, abs=1.0)
    assert out.exit_value == pytest.approx(10_278_765.714286, abs=1.0)
    assert out.yield_on_cost == pytest.approx(0.04751878, abs=1e-8)
    assert out.profit_margin == pytest.approx(-0.09488029, abs=1e-8)


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
    with pytest.raises(NotPermitted) as exc:
        fit_program(env, PROTOTYPES["midrise"], rules, Use.RESIDENTIAL,
                    DEFAULT_ASSUMPTIONS, parcel)
    assert str(exc.value) == "midrise needs >= 5 stories; TEST-L allows 4 (gated by height)"


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
    # PROGRAM HAND CHECK (highrise: 12-30 stories, min_lot 12,000, eff 0.75, structured)
    #   floors   = min(30, 13)                          = 13
    #   gross_sf = min(150,000, 15,000*13=195,000)      = 150,000
    #   net      = 150,000 * 0.75                       = 112,500
    #   avg_sf   = .30*480 + .50*720 + .20*1000
    #            = 144 + 360 + 200                      = 704
    #   units    = int(112,500 // 704) = int(159.801)   = 159
    #   stalls   = round(159 * 0.25) = round(39.75)     = 40
    assert prog.floors == 13
    assert prog.gross_sf == 150_000
    assert prog.net_rentable_sf == pytest.approx(112_500)
    assert prog.unit_count == 159
    assert prog.parking_stalls == 40

    # RLV HAND CHECK — highrise concrete priced at the §5 national fallback of $430/SF,
    # with the v1.4 product-type adjustment: 1.30 rent premium, -50 bps cap.
    #   rent_psf          = 2.50 * 1.30               =  3.25
    #   exit_cap          = 0.065 - 0.0050            =  0.060
    #   gross_residential = 112,500 * 3.25 * 12       =  4,387,500
    #   egi               = 4,387,500 * 0.94          =  4,124,250
    #   noi               = 4,124,250 * 0.65          =  2,680,762.50
    #   exit_value        = 2,680,762.50 / 0.060      = 44,679,375  (exact)
    #   hard shell        = 150,000 * 430             = 64,500,000
    #   hard parking      = 40 * 35,000 (structured)  =  1,400,000
    #   hard              =                             65,900,000
    #   soft              = 65,900,000 * 0.20         = 13,180,000
    #   contingency       = 65,900,000 * 0.05         =  3,295,000
    #   cost_ex_land      =                             82,375,000
    #   profit            = 44,679,375 * 0.15         =  6,701,906.25
    #   RLV = 44,679,375 - 82,375,000 - 6,701,906.25  = -44,397,531.25
    #   gap = -44,397,531.25 - 3,000,000              = -47,397,531.25
    # Deeply negative even with the premium: $2.50 base rent cannot carry $430/SF concrete.
    # That is the case this test exists to pin — the premium moves the number, not the sign.
    out = screening_rlv(prog, market, DEFAULT_ASSUMPTIONS, parcel)
    assert out.screening_rlv == pytest.approx(-44_397_531.25, abs=1.0)
    assert out.feasibility_gap == pytest.approx(-47_397_531.25, abs=1.0)
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


def test_e_ground_floor_active_carveout_applies_to_midrise():
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

    prog = fit_program(env, PROTOTYPES["midrise"], rules, Use.RESIDENTIAL,
                       DEFAULT_ASSUMPTIONS, parcel)
    # PROGRAM HAND CHECK
    #   floors             = min(12, 6)                           = 6
    #   gross_sf           = min(72,000, 12,000 * 6)              = 72,000
    #   required_active_sf = min(footprint 12,000, gross 72,000)  = 12,000
    #   residential_gsf    = 72,000 - 12,000                      = 60,000
    #   net                = 60,000 * 0.80                        = 48,000
    #   avg_sf   = 0.25*500 + 0.50*750 + 0.25*1050                = 762.5
    #   units    = int(48,000 // 762.5) = int(62.95)              = 62
    #   stalls   = round(62 * 1.0)                                = 62
    #   gross_sf stays 72,000 -> the shell IS costed
    assert prog.gross_sf == 72_000
    assert prog.retail_sf == 12_000
    assert prog.net_rentable_sf == pytest.approx(48_000)
    assert prog.unit_count == 62
    assert prog.parking_stalls == 62

    out = screening_rlv(prog, _market(), DEFAULT_ASSUMPTIONS, parcel)
    # RLV HAND CHECK — midrise, so the v1.4 premium (1.15) and cap adjustment (-25 bps) apply
    #   rent_psf          = 3.20 * 1.15                  =  3.68
    #   exit_cap          = 0.055 - 0.0025               =  0.0525
    #   gross_residential = 48,000 * 3.68 * 12           =  2,119,680
    #   egi               = 2,119,680 * 0.94             =  1,992,499.20
    #   noi               = 1,992,499.20 * 0.65          =  1,295,124.48
    #   exit_value        = 1,295,124.48 / 0.0525        = 24,669,037.714286
    #   hard shell        = 72,000 * 340 (FULL gross)    = 24,480,000
    #   hard parking      = 62 * 45,000 (podium)         =  2,790,000
    #   hard              =                                27,270,000
    #   soft              = 27,270,000 * 0.20            =  5,454,000
    #   contingency       = 27,270,000 * 0.05            =  1,363,500
    #   cost_ex_land      =                                34,087,500
    #   profit            = 24,669,037.714286 * 0.15     =  3,700,355.657143
    #   RLV = 24,669,037.714286 - 34,087,500 - 3,700,355.657143
    #                                                    = -13,118,817.942857
    assert out.screening_rlv == pytest.approx(-13_118_817.942857, abs=1.0)


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
# Cross-cutting behaviours the spec calls out explicitly.
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
    # v1.5: all 26 PROVENANCE entries are "national" at baseline, including the three a
    # MarketData row can supply. With no row — or a fallback row that tailors nothing —
    # every input really is a national default, so the honest score is 0.0.
    assert len(PROVENANCE) == 26
    assert set(PROVENANCE.values()) == {"national"}
    assert score_confidence(PROVENANCE) == 0.0
    assert score_confidence(PROVENANCE, _market()) == 0.0


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
    assert score_confidence(PROVENANCE, fully_sourced) == pytest.approx(1.0 / 26)
    assert score_confidence(PROVENANCE, rent_only) == pytest.approx(0.5 / 26)
    assert score_confidence(PROVENANCE, fully_sourced) > score_confidence(
        PROVENANCE, rent_only
    ) > score_confidence(PROVENANCE, _market())


def test_market_row_can_only_raise_an_input_not_lower_it():
    # Promotion is one-way (§2.8): a row tagging an input "national" must never pull down a
    # baseline that some future parcel-level source already raised to "local".
    upgraded = dict(PROVENANCE, rent_psf_residential_monthly="local")
    downgrader = _market()
    downgrader.input_provenance = {"rent_psf_residential_monthly": "national"}
    assert score_confidence(upgraded, downgrader) == pytest.approx(1.0 / 26)


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
