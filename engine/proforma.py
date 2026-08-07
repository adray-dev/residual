import numpy as np

from engine.solve import safe_irr
from engine.types import (
    Assumptions,
    CashFlow,
    ConstructionType,
    MarketData,
    Outputs,
    Parcel,
    Program,
)


def _demo_cost(parcel: Parcel, assumptions: Assumptions) -> float:
    if not assumptions.cost.get("include_demolition", False):
        return 0.0
    return parcel.existing_building_sf * assumptions.cost["demo_cost_psf"]


def screening_rlv(
    program: Program,
    market: MarketData,
    assumptions: Assumptions,
    parcel: Parcel,
) -> Outputs:
    rev = assumptions.revenue

    # --- stabilized NOI (per-SF basis only; unit_count never enters revenue) ---
    gross_residential = program.net_rentable_sf * market.rent_psf_residential_monthly * 12
    egi = gross_residential * rev["stabilized_occupancy"]
    noi = egi * (1 - rev["opex_ratio"])

    exit_value = noi / market.exit_cap_rate

    # --- costs (land excluded — RLV solves for it) ---
    hard = program.gross_sf * market.hard_cost_psf[program.construction_type]
    hard += program.parking_stalls * assumptions.cost["parking_cost_per_stall"][program.parking_type]
    hard += _demo_cost(parcel, assumptions)
    soft = hard * assumptions.cost["soft_cost_pct"]
    contingency = hard * assumptions.cost["contingency_pct"]
    cost_ex_land = hard + soft + contingency

    # --- margin-based residual ---
    profit = exit_value * assumptions.exit["target_developer_margin"]
    rlv = exit_value - cost_ex_land - profit

    tdc = cost_ex_land                    # screening TDC excludes land
    yoc = noi / tdc if tdc > 0 else 0.0
    margin = (exit_value - tdc) / tdc if tdc > 0 else 0.0

    gap = (rlv - parcel.land_value) if parcel.land_value is not None else None

    return Outputs(
        screening_rlv=rlv,
        feasibility_gap=gap,
        yield_on_cost=yoc,
        irr=None,
        equity_multiple=None,
        profit_margin=margin,
        total_development_cost=tdc,
        peak_equity=None,
        confidence=0.0,   # filled by the caller
        exit_value=exit_value,
    )


def _s_curve_fractions(n: int) -> np.ndarray:
    """Monthly hard-cost draw fractions from the symmetric-triangular CDF (§6.2). Sums to 1."""
    x = np.arange(n + 1) / n
    cdf = np.where(x <= 0.5, 2 * x**2, 1 - 2 * (1 - x) ** 2)
    return np.diff(cdf)


def _construction_months(program: Program, assumptions: Assumptions) -> int:
    # §2.2: 24 months, mid/high-rise 30. Concrete Type I is exactly the mid/high-rise set.
    if program.construction_type == ConstructionType.CONCRETE_I:
        return 30
    return assumptions.timeline["construction_months"]


def _amortizing_payment(principal: float, monthly_rate: float, n_months: int) -> float:
    if monthly_rate == 0:
        return principal / n_months
    return principal * monthly_rate / (1 - (1 + monthly_rate) ** -n_months)


def _principal_from_payment(payment: float, monthly_rate: float, n_months: int) -> float:
    if monthly_rate == 0:
        return payment * n_months
    return payment * (1 - (1 + monthly_rate) ** -n_months) / monthly_rate


def full_cashflow(
    program: Program,
    market: MarketData,
    assumptions: Assumptions,
    parcel: Parcel,
    land: float = 0.0,
) -> tuple[CashFlow, Outputs]:
    """Monthly levered model (§6). `land` is spent at month 0; solve_irr_rlv sweeps it."""
    tl, cost_a, rev, debt, ex = (
        assumptions.timeline,
        assumptions.cost,
        assumptions.revenue,
        assumptions.debt,
        assumptions.exit,
    )

    p = int(tl["predevelopment_months"])
    c = int(_construction_months(program, assumptions))
    l = int(tl["leaseup_months"])
    h = int(tl["hold_after_stabilization_months"])
    stab = p + c + l
    T = stab + h
    n = T + 1

    z = lambda: np.zeros(n)  # noqa: E731
    land_v, hard_v, soft_v, cont_v = z(), z(), z(), z()
    noi_v, draw_v, cbal_v, cint_v, pbal_v, pds_v, eq_v = z(), z(), z(), z(), z(), z(), z()

    # Annual rates are true annual-equivalents: a 3% escalation compounds to exactly 3%/year.
    esc_m = (1 + cost_a["cost_escalation_annual"]) ** (1 / 12)
    growth_m = (1 + rev["rent_growth_annual"]) ** (1 / 12)

    # ---- costs (§6.2) ----
    land_v[0] = land

    shell = program.gross_sf * market.hard_cost_psf[program.construction_type]
    shell += program.parking_stalls * cost_a["parking_cost_per_stall"][program.parking_type]
    demo = _demo_cost(parcel, assumptions)

    fracs = _s_curve_fractions(c)
    months = np.arange(p, p + c)
    hard_v[p : p + c] = shell * fracs * esc_m**months
    hard_v[p] += demo * esc_m**p        # demolition lands in the first construction month

    hard_total = hard_v.sum()
    cont_total = hard_total * cost_a["contingency_pct"]
    cont_v[p : p + c] = cont_total * hard_v[p : p + c] / hard_total

    soft_total = hard_total * cost_a["soft_cost_pct"]
    soft_v[: p + c] = soft_total / (p + c)

    costs_v = land_v + hard_v + soft_v + cont_v
    total_cost = costs_v.sum()

    # ---- revenue (§6.3) ----
    potential_annual = program.net_rentable_sf * market.rent_psf_residential_monthly * 12
    units_per_month = program.unit_count / l if l > 0 else 0.0   # derived absorption
    for t in range(p + c, n):
        occupied = min(units_per_month * (t - (p + c) + 1), program.unit_count)
        leased = (occupied / program.unit_count) if program.unit_count > 0 else 1.0
        if t >= stab:
            leased = 1.0
        egi = potential_annual / 12 * growth_m**t * leased * rev["stabilized_occupancy"]
        noi_v[t] = egi * (1 - rev["opex_ratio"])

    # ---- construction loan (§6.4), equity-first draws, capitalized interest ----
    loan_cap = debt["construction_ltc"] * total_cost
    equity_needed = total_cost - loan_cap
    c_rate_m = debt["construction_annual_rate"] / 12

    balance = 0.0
    cum_equity = 0.0
    for t in range(0, stab):
        interest = balance * c_rate_m
        cost_t = costs_v[t]
        eq_t = min(cost_t, max(equity_needed - cum_equity, 0.0))
        draw_t = cost_t - eq_t
        cum_equity += eq_t
        balance += draw_t + interest
        draw_v[t], cint_v[t], cbal_v[t] = draw_t, interest, balance
        eq_v[t] -= eq_t
        eq_v[t] += noi_v[t]          # lease-up NOI accrues to equity; interest capitalizes

    construction_interest_total = cint_v.sum()

    # ---- permanent takeout at stabilization (§6.5) ----
    stabilized_noi = noi_v[stab] * 12
    stabilized_value = stabilized_noi / market.exit_cap_rate
    p_rate_m = debt["perm_annual_rate"] / 12
    p_n = int(debt["perm_amortization_years"]) * 12

    ltv_amount = debt["perm_ltv"] * stabilized_value
    dscr_payment = stabilized_noi / debt["perm_min_dscr"] / 12
    dscr_amount = _principal_from_payment(dscr_payment, p_rate_m, p_n)
    perm_loan = max(min(ltv_amount, dscr_amount), 0.0)

    eq_v[stab] += perm_loan - balance     # excess returns to equity; shortfall is a cash-in refi
    cbal_v[stab] = 0.0
    pbal_v[stab] = perm_loan

    payment = _amortizing_payment(perm_loan, p_rate_m, p_n)
    perm_balance = perm_loan
    for t in range(stab, n):
        if t > stab:
            interest = perm_balance * p_rate_m
            perm_balance = max(perm_balance + interest - payment, 0.0)
            pds_v[t] = payment
        pbal_v[t] = perm_balance
        eq_v[t] += noi_v[t] - pds_v[t]

    # ---- exit (§6.6) ----
    gross_sale = noi_v[T] * 12 / market.exit_cap_rate
    net_sale = gross_sale * (1 - ex["selling_cost_pct"]) - perm_balance
    eq_v[T] += net_sale

    # ---- returns (§6.7) ----
    tdc = total_cost + construction_interest_total
    contributions = -eq_v[eq_v < 0].sum()
    distributions = eq_v[eq_v > 0].sum()
    peak_equity = float(max((-np.cumsum(eq_v)).max(), 0.0))

    outputs = Outputs(
        screening_rlv=land,     # the land value this run assumed; solve_irr_rlv solves for it
        feasibility_gap=(land - parcel.land_value) if parcel.land_value is not None else None,
        yield_on_cost=(stabilized_noi / tdc) if tdc > 0 else 0.0,
        irr=safe_irr(eq_v),
        equity_multiple=(distributions / contributions) if contributions > 0 else None,
        profit_margin=((gross_sale - tdc) / tdc) if tdc > 0 else 0.0,
        total_development_cost=tdc,
        peak_equity=peak_equity,
        confidence=0.0,
        exit_value=gross_sale,
    )

    cashflow = CashFlow(
        months=T,
        land=land_v, hard_cost=hard_v, soft_cost=soft_v, contingency=cont_v,
        noi=noi_v, construction_draw=draw_v, construction_balance=cbal_v,
        construction_interest=cint_v, perm_balance=pbal_v, perm_debt_service=pds_v,
        equity_cf=eq_v,
        phase_bounds={"predev_end": p, "construction_end": p + c, "stabilization": stab, "sale": T},
    )
    return cashflow, outputs
