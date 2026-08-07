from engine.types import MarketData

WEIGHTS = {"local": 1.0, "submarket": 0.5, "national": 0.0}


def score_confidence(provenance: dict, market: MarketData | None = None) -> float:
    """Share of the consumed input set that is locally tailored vs. national default (§3.6).

    A real `market` row upgrades the inputs it supplies to at least "submarket".
    """
    if not provenance:
        return 0.0

    tags = dict(provenance)
    if market is not None:
        for key in ("rent_psf_residential_monthly", "exit_cap_rate", "hard_cost_psf"):
            if tags.get(key) == "national":
                tags[key] = "submarket"

    return sum(WEIGHTS[t] for t in tags.values()) / len(tags)
