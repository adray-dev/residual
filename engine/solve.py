import numpy as np
import numpy_financial as npf
from scipy.optimize import brentq

from engine.types import Assumptions, MarketData, Parcel, Program


def safe_irr(monthly_cf) -> float | None:
    """Annualized IRR of a monthly vector, or None when it does not converge (§6.7)."""
    try:
        m = npf.irr(np.asarray(monthly_cf, dtype=float))
        if m is None or np.isnan(m) or m <= -1:
            return None
        return float((1 + m) ** 12 - 1)
    except Exception:
        return None


def solve_irr_rlv(
    program: Program,
    market: MarketData,
    assumptions: Assumptions,
    parcel: Parcel,
    hurdle: float,
) -> tuple[float, bool]:
    """Month-0 land value that drives the levered IRR to `hurdle`. (land, unachievable_flag)."""
    from engine.proforma import full_cashflow   # deferred: proforma imports safe_irr from here

    _, base = full_cashflow(program, market, assumptions, parcel, land=0.0)
    upper = base.exit_value     # land can never exceed the deal's stabilized exit value
    if upper <= 0:
        return 0.0, True

    def gap(land: float) -> float:
        _, out = full_cashflow(program, market, assumptions, parcel, land=land)
        return (out.irr - hurdle) if out.irr is not None else -1.0

    try:
        return float(brentq(gap, 0.0, upper)), False
    except ValueError:
        return 0.0, True    # unachievable even at $0 land
