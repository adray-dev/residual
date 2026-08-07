from engine.types import MarketData

WEIGHTS = {"local": 1.0, "submarket": 0.5, "national": 0.0}

# The only inputs a `MarketData` row can supply, and therefore the only tags it can promote.
MARKET_SUPPLIED_INPUTS = ("rent_psf_residential_monthly", "exit_cap_rate", "hard_cost_psf")


def score_confidence(provenance: dict, market: MarketData | None = None) -> float:
    """Share of the consumed input set that is locally tailored vs. national default (§3.6).

    The baseline `PROVENANCE` map tags every market-supplied input `national`, because until
    a real row lands that is exactly what the engine is using. A `market` row then promotes
    the inputs it *genuinely* tailors, per its own `input_provenance` tags (§2.8). A ward
    whose rent was researched but whose cap rate was borrowed from a comparable promotes the
    rent only — so confidence varies across the map by how well each submarket is sourced.

    Promotion is one-way: a row can only raise an input's weight, never lower it. Tags the
    row does not name, and inputs no row supplies, are left alone.
    """
    if not provenance:
        return 0.0

    tags = dict(provenance)
    if market is not None:
        for key in MARKET_SUPPLIED_INPUTS:
            supplied = market.input_provenance.get(key)
            if supplied is None:
                continue
            if WEIGHTS[supplied] > WEIGHTS[tags.get(key, "national")]:
                tags[key] = supplied

    return sum(WEIGHTS[t] for t in tags.values()) / len(tags)
