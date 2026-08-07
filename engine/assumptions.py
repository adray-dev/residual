from engine.types import Assumptions

DEFAULT_ASSUMPTIONS = Assumptions(
    program={},   # filled from the chosen Prototype at fit time
    timeline={
        "predevelopment_months": 12,
        "construction_months": 24,          # override to 30 for midrise/highrise at fit time
        "leaseup_months": 12,
        "hold_after_stabilization_months": 3,
    },
    cost={
        "soft_cost_pct": 0.20,
        "contingency_pct": 0.05,
        "parking_cost_per_stall": {"surface": 5_000, "structured": 35_000, "podium": 45_000},
        "cost_escalation_annual": 0.03,
        "demo_cost_psf": 12.0,              # drill-down toggle only; never applied in the bake
        "include_demolition": False,        # default OFF; user flips per underwrite
    },
    revenue={
        "rent_psf_residential_monthly": 3.20,   # submarket MarketData overrides this
        "stabilized_occupancy": 0.94,
        "opex_ratio": 0.35,
        "rent_growth_annual": 0.03,
    },
    debt={
        "construction_ltc": 0.65,
        "construction_annual_rate": 0.085,
        "perm_ltv": 0.60,
        "perm_annual_rate": 0.065,
        "perm_amortization_years": 30,
        "perm_min_dscr": 1.25,
    },
    exit={
        "exit_cap_rate": 0.055,             # submarket MarketData overrides this
        "selling_cost_pct": 0.02,
        "target_developer_margin": 0.15,
        "discount_rate": 0.10,
    },
    envelope={
        "floor_to_floor_residential_ft": 10,
        "floor_to_floor_ground_retail_ft": 14,   # reserved; no retail in v1
    },
)

# confidence reads ONLY this map. Tags: "local"=1.0, "submarket"=0.5, "national"=0.0
PROVENANCE = {
    "predevelopment_months": "national", "construction_months": "national",
    "leaseup_months": "national", "hold_after_stabilization_months": "national",
    "soft_cost_pct": "national", "contingency_pct": "national",
    "parking_cost_per_stall": "national", "cost_escalation_annual": "national",
    "demo_cost_psf": "national",
    # The three MarketData-supplied inputs below start at "national" — the honest baseline,
    # because with no seeded row the engine really is running the §2 national defaults.
    # `score_confidence` promotes each one to "submarket" only when a MarketData row's own
    # `input_provenance` says that value was researched for THAT submarket (§2.8: "the caller
    # flips that input's tag"). SPEC §2.8's table shows these as "submarket" — that is the
    # post-flip state it describes, and hard-coding it here made the flip a no-op and pinned
    # confidence to one number for every parcel in the city (v1.5).
    "rent_psf_residential_monthly": "national", "stabilized_occupancy": "national",
    "opex_ratio": "national", "rent_growth_annual": "national",
    "construction_ltc": "national", "construction_annual_rate": "national",
    "perm_ltv": "national", "perm_annual_rate": "national",
    "perm_amortization_years": "national", "perm_min_dscr": "national",
    "exit_cap_rate": "national", "selling_cost_pct": "national",
    "target_developer_margin": "national", "discount_rate": "national",
    "hard_cost_psf": "national",   # promoted only by a MarketData row that sources cost
    # v1.4 product-type dimension (§2.4). Tagged "national" deliberately: unlike
    # rent_psf/exit_cap_rate, these are NOT supplied by a MarketData row and are not
    # sourced from anything — they are placeholder factors in engine/prototypes.py. A real
    # submarket row cannot upgrade them (score_confidence only promotes the three keys it
    # names), so every parcel now carries two more un-tailored inputs and confidence falls
    # accordingly. That is the intended signal until rent-by-product-type data exists.
    "rent_premium_factor": "national",
    "exit_cap_adjustment": "national",
}
