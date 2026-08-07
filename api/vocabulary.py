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

# --- the two tiers ---------------------------------------------------------
# SPEC §11: screening RLV (unlevered, margin-based) and full RLV (levered, IRR-based) WILL
# diverge. That is accepted and must be labeled, never hidden — the drill-down shows both.
TIER_LABELS: dict[str, str] = {
    "screening": "Screening estimate",
    "full": "Full underwriting",
}
