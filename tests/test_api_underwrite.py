"""Stage D phase 2 gate — the full-tier underwrite.

The full model is the only place the engine runs live (SPEC §10), and the drill-down is
where the product makes its honesty claims: two tiers that differ, a binding constraint, a
developability flag, a confidence number, and failures that degrade instead of crashing.
Each of those is a test here.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"
)


@pytest.fixture(scope="module")
def client():
    from api.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def scored(client):
    """A scored parcel that carries an assessed land value, so returns are computable."""
    rows = client.get(
        "/map/query", params={"statuses": ["scored"], "limit": 200}
    ).json()["rows"]
    row = next(r for r in rows if r["land_value"])
    return row["parcel_id"]


@pytest.fixture(scope="module")
def underwriting(client, scored):
    response = client.get(f"/parcel/{scored}/underwrite")
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# the two tiers
# ---------------------------------------------------------------------------
def test_both_tiers_are_returned_and_labeled(underwriting):
    """SPEC §11: screening and full RLV diverge, and the UI must say so rather than hide it."""
    value = underwriting["feasibility_value"]
    assert value["full_label"] == "Full underwriting"
    assert value["screening_label"] == "Screening estimate"
    assert value["difference"] == pytest.approx(value["full"] - value["screening"], rel=1e-9)


def test_the_two_tiers_actually_differ(client):
    """If they ever matched, the two-tier disclosure would be theatre. They do not."""
    rows = client.get("/map/query", params={"statuses": ["scored"], "limit": 25}).json()["rows"]
    differing = 0
    for row in rows:
        body = client.get(f"/parcel/{row['parcel_id']}/underwrite")
        if body.status_code != 200:
            continue
        value = body.json()["feasibility_value"]
        if abs(value["difference"]) > 1.0:
            differing += 1
    assert differing > 0, "screening and full RLV never diverged across 25 parcels"


def test_screening_tier_is_recomputed_under_the_edited_inputs(client, scored):
    """Comparing a new full RLV against the BAKE's screening number would misattribute the
    user's edits to the tier split. Editing an input must move both tiers."""
    base = client.get(f"/parcel/{scored}/underwrite").json()["feasibility_value"]
    edited = client.post(
        f"/parcel/{scored}/underwrite", json={"revenue": {"opex_ratio": 0.45}}
    ).json()["feasibility_value"]
    assert edited["screening"] != base["screening"]
    assert edited["full"] != base["full"]


# ---------------------------------------------------------------------------
# the return metric
# ---------------------------------------------------------------------------
def test_annual_return_is_not_pinned_to_the_hurdle(client):
    """The bug this metric was redefined to fix.

    `solve_irr_rlv` finds the land value where IRR equals the hurdle, so an IRR measured at
    the solved RLV is the hurdle by construction — 17.00% on every parcel, ranking nothing.
    The reported return is measured at the ASSESSED land value instead, and must vary.
    """
    rows = client.get("/map/query", params={"statuses": ["scored"], "limit": 40}).json()["rows"]
    returns = []
    for row in rows:
        if not row["land_value"]:
            continue
        body = client.get(f"/parcel/{row['parcel_id']}/underwrite")
        if body.status_code != 200:
            continue
        data = body.json()["returns"]
        if data["irr"] is not None:
            returns.append(round(data["irr"], 6))
    assert len(returns) >= 5, "not enough underwritable parcels to judge"
    assert len(set(returns)) > 1, f"every parcel returned the same IRR: {returns[0]}"
    hurdle = 0.17
    assert not all(r == pytest.approx(hurdle, abs=1e-4) for r in returns)


def test_return_states_the_price_it_was_measured_at(underwriting):
    """A return with no stated basis could be read as a target. It always carries one."""
    returns = underwriting["returns"]
    assert returns["irr_basis"] == "Assessed land value"
    assert returns["irr_basis_value"] > 0
    assert returns["target_return"] == 0.17    # the hurdle, reported separately


def test_parcel_without_assessed_value_reports_no_return_rather_than_the_hurdle(client):
    """938 parcels carry no assessed land value. Those must show an em-dash, never fall
    back to the hurdle — that would present a target as a result."""
    rows = client.get("/map/query", params={"statuses": ["scored"], "limit": 800}).json()["rows"]
    unvalued = next((r for r in rows if not r["land_value"]), None)
    if unvalued is None:
        pytest.skip("no scored parcel without an assessed land value in this page")
    body = client.get(f"/parcel/{unvalued['parcel_id']}/underwrite")
    if body.status_code != 200:
        pytest.skip("parcel not underwritable for an unrelated reason")
    returns = body.json()["returns"]
    assert returns["irr"] is None
    assert "no assessed land value" in returns["irr_basis"].lower()


# ---------------------------------------------------------------------------
# model-honesty surfaces (SPEC §10)
# ---------------------------------------------------------------------------
def test_gated_by_callout_is_present(underwriting):
    envelope = underwriting["envelope"]
    assert envelope["binding_constraint"] in {"far", "height", "stories", "lot_coverage"}
    assert envelope["binding_constraint_label"].startswith("Limited by")


def test_developability_flag_and_confidence_are_present(underwriting):
    assert "developability" in underwriting
    assert 0.0 <= underwriting["confidence"] <= 1.0


def test_demolition_toggle_raises_cost_only_when_there_is_something_to_demolish(client):
    """The toggle is off by default and never applied in the bake (SPEC §2.3)."""
    rows = client.get("/map/query", params={"statuses": ["scored"], "limit": 200}).json()["rows"]
    built = next(r for r in rows if (r["existing_building_sf"] or 0) > 0)

    off = client.get(f"/parcel/{built['parcel_id']}/underwrite").json()
    on = client.get(
        f"/parcel/{built['parcel_id']}/underwrite", params={"include_demolition": True}
    ).json()

    assert off["assumptions"]["cost"]["include_demolition"] is False
    assert on["assumptions"]["cost"]["include_demolition"] is True
    # Demolition is a real cost, so it must reduce what the land can be worth.
    assert on["feasibility_value"]["full"] < off["feasibility_value"]["full"]


def test_sources_and_uses_balance(underwriting):
    """Interest capitalizes onto the construction loan, so the loan funds it. If the two
    bars disagree the chart is lying about where the money came from."""
    su = underwriting["sources_uses"]
    assert su["balanced"] is True
    assert su["uses_total"] == pytest.approx(su["sources_total"], abs=1.0)
    assert su["uses_total"] == pytest.approx(
        underwriting["returns"]["total_development_cost"], rel=1e-6
    )


def test_cashflow_vectors_are_all_the_same_length_and_phased(underwriting):
    cf = underwriting["cashflow"]
    n = cf["months"] + 1
    for key in ("land", "hard_cost", "soft_cost", "contingency", "noi", "equity_cf",
                "construction_draw", "cumulative_cost", "cumulative_equity"):
        assert len(cf[key]) == n, key
    bounds = cf["phase_bounds"]
    assert 0 < bounds["predev_end"] <= bounds["construction_end"] <= bounds["stabilization"]
    assert bounds["sale"] == cf["months"]
    # The S-curve series are cumulative, so they never decrease.
    for key in ("cumulative_cost", "cumulative_equity"):
        series = cf[key]
        assert all(b >= a - 1e-6 for a, b in zip(series, series[1:])), key


def test_program_uses_plain_parking_language(underwriting):
    """The handoff: "12 stalls, surface" — never "12 podium"."""
    phrase = underwriting["program"]["parking_phrase"]
    assert "podium" not in phrase
    assert phrase == "None" or "stall" in phrase


# ---------------------------------------------------------------------------
# overrides
# ---------------------------------------------------------------------------
def test_overrides_are_counted_and_change_the_answer(client, scored):
    """The 1c footer says "N inputs changed from default" — it must count what took effect."""
    body = client.post(
        f"/parcel/{scored}/underwrite",
        json={"debt": {"construction_ltc": 0.68}, "exit": {"exit_cap_rate": 0.0525}},
    ).json()
    assert body["overrides_changed"] == 2
    assert body["applied_overrides"]["debt"]["construction_ltc"] == 0.68
    assert body["assumptions"]["exit"]["exit_cap_rate"] == 0.0525


def test_setting_an_input_to_its_default_is_not_an_edit(client, scored):
    body = client.post(
        f"/parcel/{scored}/underwrite", json={"exit": {"selling_cost_pct": 0.02}}
    ).json()
    assert body["overrides_changed"] == 0


def test_unknown_override_keys_are_ignored_not_invented(client, scored):
    """An unrecognised key must not widen the model's input surface."""
    body = client.post(
        f"/parcel/{scored}/underwrite", json={"cost": {"totally_made_up_input": 999}}
    ).json()
    assert body["overrides_changed"] == 0
    assert "totally_made_up_input" not in body["assumptions"]["cost"]


def test_trying_another_prototype_changes_the_program(client):
    """The 1b "Try another prototype" link."""
    rows = client.get("/map/query", params={"statuses": ["scored"], "limit": 300}).json()["rows"]
    for row in rows:
        record = client.get(f"/parcel/{row['parcel_id']}").json()
        options = [p["prototype_id"] for p in record["prototypes"]]
        if len(options) < 2:
            continue
        alternate = next(p for p in options if p != record["best_prototype_id"])
        body = client.get(
            f"/parcel/{row['parcel_id']}/underwrite", params={"prototype_id": alternate}
        )
        assert body.status_code == 200, body.text
        data = body.json()
        assert data["prototype_id"] == alternate
        assert data["is_bake_best"] is False
        return
    pytest.skip("no parcel with two admissible prototypes in this page")


# ---------------------------------------------------------------------------
# failure modes degrade, never crash (SPEC fix #8)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("status", ["exempt", "historic", "zone_not_encoded", "infeasible"])
def test_unmodellable_parcels_explain_themselves(client, status):
    """Exempt/historic/unencoded/infeasible are real answers about a parcel, not faults."""
    rows = client.get("/map/query", params={"statuses": [status], "limit": 1}).json()["rows"]
    response = client.get(f"/parcel/{rows[0]['parcel_id']}/underwrite")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail and detail[0].isupper() and detail.endswith(".")
    assert "Traceback" not in detail


def test_absurd_inputs_do_not_raise(client, scored):
    """A non-converging IRR must report as unavailable, never as a 500 (SPEC fix #8)."""
    response = client.post(
        f"/parcel/{scored}/underwrite",
        json={"revenue": {"opex_ratio": 0.99}, "exit": {"exit_cap_rate": 0.2}},
    )
    assert response.status_code in (200, 422)
    if response.status_code == 200:
        body = response.json()
        assert body["returns"]["irr"] is None or isinstance(body["returns"]["irr"], float)


def test_missing_parcel_underwrite_is_422_with_a_readable_reason(client):
    response = client.get("/parcel/9999    9999/underwrite")
    assert response.status_code == 422
    assert "9999" in response.json()["detail"]


# ---------------------------------------------------------------------------
# caching
# ---------------------------------------------------------------------------
def test_repeat_underwrite_is_cached(client, scored):
    """SPEC §10: the underwrite endpoint caches. Same inputs must give the same numbers."""
    first = client.get(f"/parcel/{scored}/underwrite").json()
    second = client.get(f"/parcel/{scored}/underwrite").json()
    assert first["feasibility_value"] == second["feasibility_value"]
    assert first["returns"] == second["returns"]


def test_market_snapshot_is_stamped_for_scenario_freezing(underwriting):
    """SPEC §7.1 v1.2: a saved scenario never re-reads live market data."""
    snapshot = underwriting["market_snapshot"]
    for key in ("submarket_id", "rent_psf_residential_monthly", "exit_cap_rate",
                "hard_cost_psf", "as_of", "source"):
        assert key in snapshot, key


# ---------------------------------------------------------------------------
# market-backed inputs (the 1c modal's two most important levers)
# ---------------------------------------------------------------------------
def test_editing_the_exit_cap_actually_changes_the_model(client, scored):
    """`proforma` reads the exit cap off MarketData, not off Assumptions, so overriding it
    in the assumption set alone reported "1 input changed" and returned byte-identical
    numbers. An input that says it applied and does nothing is worse than no input."""
    base = client.get(f"/parcel/{scored}/underwrite").json()
    tighter = client.post(
        f"/parcel/{scored}/underwrite",
        json={"exit": {"exit_cap_rate": round(base["assumptions"]["exit"]["exit_cap_rate"] - 0.01, 4)}},
    ).json()

    assert tighter["overrides_changed"] == 1
    # A lower cap capitalises the same NOI into a larger exit value, and more residual.
    assert tighter["returns"]["exit_value"] > base["returns"]["exit_value"]
    assert tighter["feasibility_value"]["full"] > base["feasibility_value"]["full"]


def test_editing_the_rent_actually_changes_the_model(client, scored):
    """Same trap as the exit cap: rent is market-supplied (SPEC §2.8)."""
    base = client.get(f"/parcel/{scored}/underwrite").json()
    richer = client.post(
        f"/parcel/{scored}/underwrite",
        json={"revenue": {"rent_psf_residential_monthly":
                          round(base["program"]["rent_psf_monthly"] + 1.0, 4)}},
    ).json()

    assert richer["overrides_changed"] == 1
    assert richer["returns"]["noi"] > base["returns"]["noi"]
    assert richer["feasibility_value"]["full"] > base["feasibility_value"]["full"]


def test_a_market_override_does_not_leak_into_the_next_parcel(client, scored):
    """`get_market` hands back a shared row; substituting on it rather than on a copy would
    make one user's what-if the whole submarket's reality for the rest of the process."""
    before = client.get(f"/parcel/{scored}/underwrite").json()
    client.post(
        f"/parcel/{scored}/underwrite",
        json={"exit": {"exit_cap_rate": 0.03}},
    )
    after = client.get(f"/parcel/{scored}/underwrite").json()
    assert after["feasibility_value"]["full"] == before["feasibility_value"]["full"]
    assert after["overrides_changed"] == 0


# ---------------------------------------------------------------------------
# §6.4 — sources and uses must close
# ---------------------------------------------------------------------------
# Sources and uses are the same money counted two ways. If they disagree, one of the two
# is wrong, and the drill-down refuses to draw the chart — so this is a correctness gate,
# not a presentation one. It stayed broken for a while because it only appears once an
# assumption is EDITED, and the default run balances.
BALANCE_CASES = [
    ("defaults", {}),
    ("soft cost 25%", {"cost": {"soft_cost_pct": 0.25}}),
    ("contingency 10%", {"cost": {"contingency_pct": 0.10}}),
    ("construction LTC 70%", {"debt": {"construction_ltc": 0.70}}),
    ("construction LTC 50%", {"debt": {"construction_ltc": 0.50}}),
    ("construction rate 12%", {"debt": {"construction_annual_rate": 0.12}}),
    ("perm LTV 40%", {"debt": {"perm_ltv": 0.40}}),
    ("perm rate 9%", {"debt": {"perm_annual_rate": 0.09}}),
    ("min DSCR 1.6", {"debt": {"perm_min_dscr": 1.6}}),
    ("exit cap 5.0%", {"exit": {"exit_cap_rate": 0.05}}),
    ("exit cap 7.0%", {"exit": {"exit_cap_rate": 0.07}}),
    ("rent +$1", {"revenue": {"rent_psf_residential_monthly": 4.6}}),
    ("occupancy 85%", {"revenue": {"stabilized_occupancy": 0.85}}),
    ("demolition on", {"include_demolition": True}),
    ("several at once", {"debt": {"construction_ltc": 0.72, "perm_ltv": 0.45},
                         "exit": {"exit_cap_rate": 0.048},
                         "cost": {"soft_cost_pct": 0.23}}),
]


@pytest.mark.parametrize("label,overrides", BALANCE_CASES, ids=[c[0] for c in BALANCE_CASES])
def test_sources_and_uses_balance_under_every_edit(client, scored, label, overrides):
    """The identity the capital stack has to satisfy, across the inputs the 1c modal
    actually lets a user change.

    The failure this pins: development equity was summed from negative equity cash flows
    over the WHOLE hold, so a cash-in refinancing at stabilization (perm loan smaller than
    the construction balance) and any operating shortfall during hold were both counted as
    development sources — with no matching use. The gap equalled those flows exactly.
    """
    body = client.post(f"/parcel/{scored}/underwrite", json=overrides).json()
    su = body["sources_uses"]
    gap = su["sources_total"] - su["uses_total"]
    assert abs(gap) < 1.0, f"{label}: sources and uses differ by ${gap:,.0f}"
    assert su["balanced"] is True, label


def test_uses_and_sources_each_sum_to_their_own_total(client, scored):
    """The line items must add up to the total shown beside them, or the chart's bars and
    its caption are telling different stories."""
    su = client.get(f"/parcel/{scored}/underwrite").json()["sources_uses"]
    assert sum(su["uses"].values()) == pytest.approx(su["uses_total"], abs=0.01)
    assert sum(su["sources"].values()) == pytest.approx(su["sources_total"], abs=0.01)


def test_a_refinancing_shortfall_is_still_reported_somewhere(client, scored):
    """Excluding post-stabilization cash-in from the DEVELOPMENT sources & uses must not
    make it disappear from the model: peak equity spans the whole hold and still carries
    it, so the capital a developer actually has to find is never understated."""
    body = client.post(
        f"/parcel/{scored}/underwrite", json={"debt": {"construction_ltc": 0.70}}
    ).json()
    peak = body["returns"]["peak_equity"]
    development_equity = body["sources_uses"]["sources"]["equity"]
    assert peak is not None and peak >= development_equity
