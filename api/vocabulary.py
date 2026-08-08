"""The plain-language vocabulary the UI speaks (design handoff, "Language rules").

The product's audience is developers/analysts AND municipal planners, so the UI defaults
to plain language and keeps the technical term only where the term is the thing itself.
This module is the ONE place that mapping lives; `web/src/lib/vocabulary.ts` mirrors it.

The governing rule for this whole stage: when SPEC and the UI copy disagree about what a
number MEANS, SPEC wins; when they disagree about what to CALL it, the handoff wins. So
every label here is the handoff's, and every value behind it is SPEC's.

Two hard rules from the handoff, enforced below:
  - "SSL" never appears in user-facing text. It is always "Parcel ID".
  - Confidence is a percentage (5.8%), never a 0.058 decimal.
"""
from __future__ import annotations

# --- metric labels ---------------------------------------------------------
# plain (what the UI shows) : technical (kept only for an analyst-mode toggle later)
METRIC_LABELS: dict[str, tuple[str, str]] = {
    # key                        plain                          technical
    "rlv_total":                 ("Financial feasibility (RLV)", "Residual land value"),
    "rlv_per_buildable_sf":      ("Feasibility value per SF",    "RLV per buildable SF"),
    "feasibility_gap":           ("Value above assessed land",   "Feasibility gap"),
    "irr":                       ("Annual return",               "Levered IRR"),
    "yield_on_cost":             ("Income vs cost",              "Yield on cost"),
    "equity_multiple":           ("Cash back on equity",         "Equity multiple"),
    "noi":                       ("Yearly income (NOI)",         "Stabilized NOI"),
    "total_development_cost":    ("Total cost to build",         "Total development cost"),
    "cost_per_unit":             ("Cost per unit",               "Cost / unit"),
    "exit_value":                ("Sale value at exit",          "Exit value"),
    "gross_sf":                  ("Total floor area",            "Gross SF"),
    "net_rentable_sf":           ("Rentable area",               "Net rentable SF"),
    "max_buildable_gsf":         ("Buildable floor area",        "Buildable GSF"),
    "profit_margin":             ("Profit margin",               "Profit margin"),
    "prototype_id":              ("Best build",                  "Best prototype"),
    "ssl":                       ("Parcel ID",                   "SSL"),
    "confidence":                ("Confidence",                  "Confidence"),
    "lot_area_sf":               ("Lot area",                    "Lot area SF"),
}


def label(key: str) -> str:
    """The plain-language label for a metric key. Falls back to the key itself."""
    entry = METRIC_LABELS.get(key)
    return entry[0] if entry else key


# --- prototypes ------------------------------------------------------------
# "Best build: Garden walk-up", never "garden". Values match engine/prototypes.py keys.
PROTOTYPE_LABELS: dict[str, str] = {
    "townhome": "Townhome",
    "garden": "Garden walk-up",
    "midrise": "Midrise",
    "highrise": "Highrise",
}

# --- construction types ----------------------------------------------------
# "Build type: Wood frame", never "Wood V". Values match engine.types.ConstructionType.
CONSTRUCTION_LABELS: dict[str, str] = {
    "wood_v": "Wood frame",
    "podium": "Wood over podium",
    "concrete_i": "Concrete",
}

# --- parking ---------------------------------------------------------------
# Described in plain terms — "12 stalls, surface", never "12 podium".
PARKING_LABELS: dict[str, str] = {
    "surface": "surface",
    "structured": "structured",
    "podium": "underground",
}


def parking_phrase(stalls: int | None, parking_type: str | None) -> str:
    """"12 stalls, surface" — the handoff's phrasing, including the singular case."""
    if not stalls:
        return "None"
    noun = "stall" if stalls == 1 else "stalls"
    kind = PARKING_LABELS.get(parking_type or "", parking_type or "")
    return f"{stalls:,} {noun}, {kind}" if kind else f"{stalls:,} {noun}"


# --- binding constraint ("gated by") ---------------------------------------
# SPEC §3.2 emits far | height | lot_coverage; the bake also emits `stories`. The handoff
# renders these as "Limited by floor area / height". `lot_coverage` and `stories` have no
# handoff copy — worded here in the same voice rather than leaking the raw token.
BINDING_CONSTRAINT_LABELS: dict[str, str] = {
    "far": "Limited by floor area",
    "height": "Limited by height",
    "stories": "Limited by story count",
    "lot_coverage": "Limited by lot coverage",
}


def binding_constraint_label(value: str | None) -> str | None:
    """"Limited by height". For status rows the value is a sentence already — pass it through."""
    if not value:
        return None
    return BINDING_CONSTRAINT_LABELS.get(value, value)


# --- statuses --------------------------------------------------------------
# Every parcel is represented and every color is explainable (SPEC §9). The non-scored
# wording is deliberately quiet and neutral — unscored land must never read as "bad land".
STATUS_LABELS: dict[str, str] = {
    "scored": "Scored",
    "infeasible": "Infeasible under zoning",
    "exempt": "Not developable — public / exempt",
    "historic": "Historic — restricted",
    "zone_not_encoded": "Zoning not yet covered",
}

# --- assumption inputs (the 1c modal) ---------------------------------------
# Group headings, in the modal's nav order.
ASSUMPTION_GROUP_LABELS: dict[str, str] = {
    "timeline": "Timeline",
    "cost": "Cost",
    "revenue": "Revenue",
    "debt": "Debt",
    "exit": "Exit & return",
    "envelope": "Envelope",
}

# Per-input plain label AND unit kind. The kind is here rather than in the client because
# it is a fact about what the number MEANS: `soft_cost_pct` is 0.2 on the wire and must be
# shown and typed as 20%, and getting that wrong silently changes a user's model by 100x.
#
# Keys mirror `engine/assumptions.py` exactly. Anything the engine does not accept is
# absent — notably hard cost per SF, which the handoff's mock lists under Cost but which is
# MARKET data (per construction type), not an assumption. Offering an input the engine
# would ignore is worse than not offering it.
#
# kind: percent (0-1 fraction) | money | months | years | rate ($ per unit) | number
ASSUMPTION_FIELDS: dict[str, tuple[str, str]] = {
    # timeline
    "predevelopment_months":            ("Predevelopment",            "months"),
    "construction_months":              ("Construction",              "months"),
    "leaseup_months":                   ("Lease-up",                  "months"),
    "hold_after_stabilization_months":  ("Hold after stabilization",  "months"),
    # cost
    "soft_cost_pct":                    ("Soft cost % of hard",       "percent"),
    "contingency_pct":                  ("Contingency",               "percent"),
    "cost_escalation_annual":           ("Cost escalation",           "percent"),
    "demo_cost_psf":                    ("Demolition $/SF",           "rate"),
    # revenue
    "rent_psf_residential_monthly":     ("Base rent $/SF/mo",         "rate"),
    "stabilized_occupancy":             ("Occupancy",                 "percent"),
    "opex_ratio":                       ("Operating expense ratio",   "percent"),
    "rent_growth_annual":               ("Rent growth",               "percent"),
    # debt
    "construction_ltc":                 ("Construction LTC",          "percent"),
    "construction_annual_rate":         ("Construction rate",         "percent"),
    "perm_ltv":                         ("Permanent LTV",             "percent"),
    "perm_annual_rate":                 ("Permanent rate",            "percent"),
    "perm_amortization_years":          ("Amortization",              "years"),
    "perm_min_dscr":                    ("Minimum DSCR",              "number"),
    # exit & return
    "exit_cap_rate":                    ("Exit cap rate",             "percent"),
    "selling_cost_pct":                 ("Selling cost",              "percent"),
    "target_developer_margin":          ("Target margin",             "percent"),
    "discount_rate":                    ("Discount rate",             "percent"),
    "irr_hurdle":                       ("Return hurdle",             "percent"),
    # envelope
    "floor_to_floor_residential_ft":    ("Floor to floor, residential", "number"),
    "floor_to_floor_ground_retail_ft":  ("Floor to floor, ground retail", "number"),
}

# Inputs the modal must NOT show, with the reason.
HIDDEN_ASSUMPTION_KEYS: frozenset[str] = frozenset({
    # Owned by the 1b demolition toggle. Two controls for one value would let the panel
    # and the modal disagree about what was actually run.
    "include_demolition",
    # A per-parking-type mapping, not a scalar; the modal's field is a single number and
    # there is no product need to edit stall costs by type yet.
    "parking_cost_per_stall",
})


# --- the two tiers ---------------------------------------------------------
# SPEC §11: screening RLV (unlevered, margin-based) and full RLV (levered, IRR-based) WILL
# diverge. That is accepted and must be labeled, never hidden — the drill-down shows both.
TIER_LABELS: dict[str, str] = {
    "screening": "Screening estimate",
    "full": "Full underwriting",
}
