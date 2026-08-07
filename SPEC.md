# Parcel feasibility platform — build specification (v1, Washington DC)

This is the authoritative build document. It resolves every design decision made
so far into concrete instructions, numbers, and formulas. It is written to be built
in **four sequential stages**, each independently verifiable in the terminal before
moving on. Build Stage A first and prove it with `pytest` before touching data.

> **Golden rule.** The engine core (Stage A) is pure functions with no I/O. The same
> engine runs in the batch bake and in the live API. Write the math once, run it two ways.
> If any function in `engine/` imports a database driver or `requests`, that is a bug.

> **Revision v1.1 — hardening pass.** This version resolves the ambiguities that would
> otherwise generate runtime errors:
> - Revenue is driven by **net rentable SF × $/SF**, never per-unit rents. Unit count is a
>   *reporting output only*, never a revenue driver (avoids the per-SF/per-unit mismatch).
> - `Program` carries `construction_type` (stamped by `fit_program`) so the pro forma can price it.
> - `resolve_envelope` computes three explicit candidate limits and labels the true binding one.
> - `DEFAULT_ASSUMPTIONS` is a single canonical object (§2.8). Values are plain numbers; a
>   separate `PROVENANCE` map holds tags (confidence reads the map, math reads the numbers).
> - The bake writes a row for **every** parcel, including infeasible/unencoded ones (colored differently).
> - Unencoded zoning districts **skip gracefully** (no FK crash). Condos are excluded in v1.
> - IRR and the IRR-solve **fail gracefully** (return None / flag), never crash an underwrite.
> - Retail and condos are cut from v1 (`retail_sf` reserved, always 0).

> **Revision v1.2 — metric reframing, simplifications, and gap closures.**
> - **RLV / RLV-per-buildable-SF is the primary metric** (land + site acquisition at $0).
>   `feasibility_gap` (RLV − assessed land) is a secondary, optional comparison, not the headline.
> - **Demolition is a drill-down toggle, default OFF and always off in the bake** — the map
>   ranks clean-site potential uniformly; demo cost is applied on demand per parcel.
> - `parcels` gains `existing_building_sf` (from CAMA) — feeds both the demo toggle and the
>   developability flag — plus `is_exempt` and `is_historic`.
> - **Absorption deleted as an assumption.** `leaseup_months` is the input; absorption is
>   derived: `units_per_month = unit_count / leaseup_months`.
> - Prototype admissibility adds **`min_lot_sf`** (kills high-rises on sliver lots).
> - Split-zoned parcels: zoning spatial join assigns the district of **largest intersection area**.
> - **Exempt/public parcels are pre-filtered before the bake** (federal, NPS, government,
>   church, cemetery, ROW): rendered as "not developable (public/exempt)", never scored.
> - **Historic-district parcels are flagged and gated**: rendered "historic — redevelopment
>   restricted", not scored in v1.
> - Saved scenarios **snapshot their market inputs** at save time — fully frozen and reproducible.
> - Best-prototype selection uses a **5% tie margin** (incumbent holds unless beaten by >5%).
> - Bake is **single-process** in v1 (parallelism deferred to multi-metro scale).
> - Map served as **static vector tiles regenerated per bake** (tippecanoe → PMTiles); no live tile server.
> - Loaders run a **schema-validation guard** (fail loudly if DC renames fields). Repull on the 1st monthly.
> - Initial DC submarket rents are **LLM-seeded once** (search → retrieve → write `market_data`),
>   never in the runtime path.
> - Known accepted simplification (fix later): surface parking's lot-area consumption is not
>   netted out of the buildable footprint.

> **Revision v1.3 — bug-fix pass.**
> - `bake_results.prototype_id` uses sentinel `'__none__'` for status rows (Postgres PK columns cannot be NULL).
> - `fit_program` takes `parcel` (min_lot_sf gate); all call sites and tests updated.
> - `Parcel` new fields have defaults; `land_value` / `improvement_value` / `improvement_ratio`
>   are nullable (untaxed/exempt land has no CAMA row); `feasibility_gap` is None-safe.
> - `solve_irr_rlv` upper bracket computed in-scope (exit value at $0 land).
> - **Ground-floor active-use mandate restored** (previously dropped decision):
>   `zoning_rules.requires_ground_floor_active` — when TRUE the ground floorplate is costed
>   at hard $/SF but excluded from net rentable (cost, no revenue).
> - Bake batches APPEND with `computed_at`; retain last 2; `prior_best` read from the previous
>   batch; first bake is plain argmax. (Resolves overwrite-vs-tie-margin contradiction.)
> - Demolition (toggle on) is spent in the first construction month.
> - `is_best` pinned to the RLV-per-buildable-SF objective.

> **Revision v1.3.1 — ranking metrics persisted; default objective is total RLV.**
> (Supersedes the v1.3 line above.) From the Stage C baseline review:
> - `bake_results` gains **`rlv_total`** (= `screening_rlv`) and **`rlv_per_buildable_sf`**
>   (= `screening_rlv / program.gross_sf`), both written by the bake. `gross_sf` is not a
>   column, so RLV/SF is only computable at bake time; readers ORDER BY the stored column
>   and **never divide at read time** — in particular never by `lot_area_sf`, which was a
>   third measure, agreeing with neither the bake's objective nor the intended one.
> - **Total RLV is the default map coloring/sort objective**, and `is_best` is repinned to
>   it, so the map colors the measure the bake optimized. RLV/SF is demoted to a selectable
>   alternate: it is near-constant within a zone (roughly a constant per zone/prototype/
>   submarket), so coloring on it reproduces the zoning map, while total RLV varies parcel
>   to parcel.
> - Migration: the two columns are added empty; `rlv_per_buildable_sf` cannot be backfilled,
>   so an existing database is repopulated by re-running the bake (see `data/schema.sql`).

> **Revision v1.3.2 — ground-floor active-use mandate scoped to the prototypes it can apply to.**
> `fit_program` took the mandate carve-out for EVERY prototype in a district flagged
> `requires_ground_floor_active`, i.e. it modelled mandatory ground-floor retail in a
> rowhouse — removing one of three floors from revenue while costing all three. Measured
> effect: ≈ −108 $/SF on townhome, in every district, which was the whole reason MU-/D-
> parcels read negative while R-/RF- parcels read positive. Forcing the flag ON in RF-1 and
> R-2 reproduced the same −46 $/SF, confirming the split tracked the flag and not economics.
> The carve-out is now gated on `§5 GROUND_FLOOR_ACTIVE_PROTOTYPES = {midrise, highrise}`
> as well as on the district. The district-wide-vs-street-segment overstatement remains, is
> narrowed to mid/high-rise inside mandated districts, and is recorded in §11.

> **Revision v1.4 — product type enters the revenue model (§2.4, §5).**
> The pro forma applied one submarket rent and one flat exit cap to all four prototypes,
> which made density unwinnable by construction — townhome converts $1 of hard cost into
> 4.286 rentable SF against midrise's 2.353, so at equal rent and equal cap the walk-up wins
> every parcel at every rent level. The bake showed the degenerate result: townhome `is_best`
> on 100% of scored parcels, mid/high-rise winning nowhere.
> - `RENT_PREMIUM_FACTOR` and `EXIT_CAP_ADJUSTMENT` (`engine/prototypes.py`) modulate the
>   submarket base rent and base cap per prototype; `screening_rlv` and `full_cashflow` apply
>   both identically.
> - Both are tagged `national` in `PROVENANCE`. They are **placeholder assumptions, not
>   sourced** (§11), and no `MarketData` row can promote them — so confidence drops from
>   0.0625 to 0.0577 on every parcel, which is the honest signal.
> - The `Prototype` dataclass (§3.1) is unchanged: the factors are module-level maps keyed by
>   `prototype_id`, following the existing `min_lot_sf` / `NATIONAL_HARD_COST_PSF` pattern, so
>   the pinned schema and the `prototypes` table stay as they are.

---

## 0. Product in one paragraph

A subscription web app, CoStar-style: opens to a map of DC parcels, each colored by
development feasibility. Feasibility is computed by a per-parcel pro forma engine.
The map shows a fast, precomputed **screening RLV / feasibility gap**; opening a parcel
runs a full **monthly, levered cash-flow model** on demand. Users adjust a development
program (prototype, stories, units, parking, etc.) and re-underwrite. Developer-mode only
for v1. Zoning is a stored, hand-encoded reference table for DC's districts (matter-of-right).

---

## 1. Tech stack (pin these)

| Layer | Choice |
|---|---|
| Language (engine, data, bake, API) | Python 3.11+ |
| Engine core | Pure functions, `dataclasses`, `numpy` for the cash-flow arrays |
| Numeric solve | `scipy.optimize.brentq` for IRR-based solves; closed-form for margin-based RLV |
| DB | PostgreSQL 15+ with PostGIS 3+ |
| DB access | `psycopg` (v3) + `SQLAlchemy` core (no ORM needed for v1) |
| Spatial | PostGIS for spatial joins; `shapely` + `geopandas` in loaders |
| Bake | Python batch job, **single process** in v1 (~150k parcels of arithmetic runs in minutes; parallelize only at multi-metro scale) |
| API | FastAPI + `uvicorn` |
| Test | `pytest` |
| Frontend (Stage D) | React + MapLibre GL reading **static PMTiles regenerated each bake** (tippecanoe); no live tile server |

Project layout:

```
feasibility/
  engine/            # Stage A — pure functions, no I/O
    __init__.py
    types.py         # dataclasses: Parcel, ZoningRules, MarketData, Prototype, Program, Envelope, Assumptions, CashFlow, Outputs
    prototypes.py    # the 4 prototype definitions as data
    assumptions.py   # the default assumption sets as data
    envelope.py      # resolve_envelope()
    program.py       # fit_program()
    proforma.py      # screening_rlv(), full_cashflow()
    solve.py         # solve_rlv_margin(), solve_irr()
    confidence.py    # score_confidence()
  data/              # Stage B — the only code that talks to the DB
    schema.sql
    repositories.py
    loaders/
      dc_parcels.py
      dc_zoning.py
      market.py
  bake/              # Stage C
    run_bake.py
  api/               # Stage D
    main.py
  tests/
    test_engine_hand_checks.py
  SPEC.md            # this file
```

---

## 2. The default assumption set (v1 standard values)

These are **best-practice, DC-plausible defaults**, flagged tune-later. Each input carries
a provenance tag used by the confidence score: `national` (generic best practice),
`submarket` (DC-market-level), or `local` (parcel-specific). In v1 most inputs are `national`
or `submarket`, so confidence runs honestly low and rises as the data moat matures.

### 2.1 Program defaults (per prototype — see §5)
Set by the prototype. User-overridable at underwrite time.

### 2.2 Timeline defaults (months)
| Field | Value | Provenance |
|---|---|---|
| predevelopment_months | 12 | national |
| construction_months | 24 (mid/high-rise: 30) | national |
| leaseup_months | 12 | national |  <!-- absorption is DERIVED: unit_count/leaseup_months -->
| hold_after_stabilization_months | 3 (then sell) | national |

Exit = sale at stabilization (merchant build). Sale occurs in the month after lease-up
completes + hold buffer.

### 2.3 Cost defaults
| Field | Value | Provenance |
|---|---|---|
| hard_cost_psf | set by construction type (see §5 table) | submarket |
| soft_cost_pct (of hard) | 20% | national |
| contingency_pct (of hard) | 5% | national |
| parking_cost_per_stall_surface | $5,000 | national |
| parking_cost_per_stall_structured | $35,000 | national |
| parking_cost_per_stall_podium | $45,000 | national |
| cost_escalation_annual | 3.0% | national |
| demo_cost_psf (drill-down toggle only, default OFF) | $12 /SF of existing building | national |

### 2.4 Revenue defaults
| Field | Value | Provenance |
|---|---|---|
| rent_psf_residential_monthly | $3.20 /SF/mo (submarket table overrides) | submarket |
| retail_rent_psf_annual | $40 /SF/yr NNN — **reserved, cut in v1 (no retail)** | submarket |
| stabilized_occupancy | 94% | national |
| opex_ratio (of EGI) | 35% | national |
| rent_growth_annual | 3.0% | national |
| rent_premium_factor | product-type multiplier on the base rent (§5) | national |
| exit_cap_adjustment | product-type adjustment on the base cap (§5) | national |

**Product type is a revenue dimension (v1.4).** A submarket supplies ONE base rent and ONE
base cap. Those are quoted for the low-rise product; the pro forma then adjusts both by
prototype before any revenue is computed:

```
effective rent = market.rent_psf_residential_monthly * RENT_PREMIUM_FACTOR[prototype]
effective cap  = market.exit_cap_rate               + EXIT_CAP_ADJUSTMENT[prototype]
```

Both `screening_rlv` and `full_cashflow` apply this identically — the drill-down must not
contradict the map colour it was opened from. Without it, density is unwinnable by
construction: a townhome turns $1 of hard cost into 4.286 rentable SF against a midrise's
2.353, so at one rent and one cap the walk-up wins every parcel in every submarket at every
rent level, which is exactly what the bake produced (townhome `is_best` on 100% of scored
parcels). The factors themselves are **placeholder assumptions, not sourced** — see §5 for
the values and §11 for what they are waiting on. They are tagged `national` in `PROVENANCE`
precisely so confidence reports them as un-tailored; a real `MarketData` row cannot promote
them, so adding them *lowers* every parcel's confidence (0.0625 → 0.0577).

### 2.5 Debt defaults
| Field | Value | Provenance |
|---|---|---|
| construction_ltc | 65% | national |
| construction_annual_rate | 8.5% | national |
| interest_reserve | funded inside the loan (auto-sized, see §6.4) | national |
| perm_ltv | 60% | national |
| perm_annual_rate | 6.5% | national |
| perm_amortization_years | 30 | national |
| perm_min_dscr | 1.25 | national |

### 2.6 Exit / return defaults
| Field | Value | Provenance |
|---|---|---|
| exit_cap_rate | submarket table (fallback 5.5%) | submarket |
| selling_cost_pct | 2.0% | national |
| target_developer_margin | 15% (used for margin-based screening RLV) | national |
| discount_rate (for NPV checks) | 10% | national |
| irr_hurdle (for IRR-based full RLV) | 17% | national |

> **`irr_hurdle` added in v1.6 (Stage D).** `solve_irr_rlv` (§6.8) has always taken the
> hurdle as a caller argument with no default, and §2.6 defined none — fine while the only
> caller was a test passing an explicit value, but the API must supply one on every full
> underwrite. 17% is adopted from the design handoff, which assumes it in two places (the
> inputs modal's Exit & return group and the map's "Annual return ≥" filter). It is
> **not** measured from anything and is tagged `national` accordingly, so confidence
> reports it as un-tailored. Do not conflate it with `discount_rate`: a discount rate for
> NPV is not a developer's required return, and the two are used in different tiers.

### 2.7 Envelope defaults
| Field | Value | Provenance |
|---|---|---|
| floor_to_floor_residential_ft | 10 | national |
| floor_to_floor_ground_retail_ft | 14 | national |
| DC Height Act cap | applied via zoning max_height_ft (already encoded per district) | local |

### 2.8 Canonical `DEFAULT_ASSUMPTIONS` and `PROVENANCE` (`engine/assumptions.py`)

**One source of truth.** Values are plain numbers so all engine math reads them directly.
A *separate* `PROVENANCE` dict maps each input name to its tag; `confidence.py` reads only
`PROVENANCE`, never the values. This keeps arithmetic clean and confidence decoupled (fix #10).

```python
DEFAULT_ASSUMPTIONS = Assumptions(
    program = {},   # filled from the chosen Prototype at fit time
    timeline = {
        "predevelopment_months": 12,
        "construction_months": 24,          # override to 30 for midrise/highrise at fit time
        "leaseup_months": 12,
        "hold_after_stabilization_months": 3,
    },
    cost = {
        "soft_cost_pct": 0.20,
        "contingency_pct": 0.05,
        "parking_cost_per_stall": {"surface": 5_000, "structured": 35_000, "podium": 45_000},
        "cost_escalation_annual": 0.03,
        "demo_cost_psf": 12.0,              # drill-down toggle only; never applied in the bake
        "include_demolition": False,        # default OFF; user flips per underwrite
    },
    revenue = {
        "rent_psf_residential_monthly": 3.20,   # submarket MarketData overrides this
        "stabilized_occupancy": 0.94,
        "opex_ratio": 0.35,
        "rent_growth_annual": 0.03,
    },
    debt = {
        "construction_ltc": 0.65,
        "construction_annual_rate": 0.085,
        "perm_ltv": 0.60,
        "perm_annual_rate": 0.065,
        "perm_amortization_years": 30,
        "perm_min_dscr": 1.25,
    },
    exit = {
        "exit_cap_rate": 0.055,             # submarket MarketData overrides this
        "selling_cost_pct": 0.02,
        "target_developer_margin": 0.15,
        "discount_rate": 0.10,
    },
    envelope = {
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
    "rent_psf_residential_monthly": "submarket", "stabilized_occupancy": "national",
    "opex_ratio": "national", "rent_growth_annual": "national",
    "construction_ltc": "national", "construction_annual_rate": "national",
    "perm_ltv": "national", "perm_annual_rate": "national",
    "perm_amortization_years": "national", "perm_min_dscr": "national",
    "exit_cap_rate": "submarket", "selling_cost_pct": "national",
    "target_developer_margin": "national", "discount_rate": "national",
    "hard_cost_psf": "submarket",   # comes from MarketData
}
```

When a submarket `MarketData` row supplies a real local rent/cap/cost, the caller flips that
input's tag to `"submarket"` (or `"local"` once parcel-level data exists), and confidence rises.

**Per-value provenance (v1.5).** The three market-supplied keys above
(`rent_psf_residential_monthly`, `exit_cap_rate`, `hard_cost_psf`) are tagged `"national"` in
the baseline `PROVENANCE` map, not `"submarket"` — the table shows the *post-flip* state, and
hard-coding it made the flip a no-op that pinned every parcel in the city to one confidence
number. The flip is per input and per submarket: `market_data.provenance` (JSONB) stores the
tag for each value **that row** genuinely tailors, `MarketData.input_provenance` carries it,
and `score_confidence` raises (never lowers) the baseline accordingly. So a ward whose rent
was researched but whose cap rate was borrowed from a comparable scores strictly below a ward
where both are ward-specific, and a ward with no seeded row at all scores 0.0 — which is the
honest reading of §3.6 when every input really is a national default. See
`data/loaders/seed_market.py` for the DC seed and its per-value sources.

---

## 3. Stage A — the engine core (BUILD AND VERIFY THIS FIRST)

No database. No network. Pure functions over dataclasses, with the default assumption
set hardcoded as data. You will verify it with `pytest` against hand-computed parcels
before writing any data code.

### 3.1 Core types (`engine/types.py`)

```python
from dataclasses import dataclass, field
from enum import Enum

class Use(str, Enum):
    RESIDENTIAL = "residential"
    RETAIL = "retail"
    OFFICE = "office"

class ConstructionType(str, Enum):
    WOOD_V = "wood_v"           # Type V, townhome/garden
    WOOD_OVER_PODIUM = "podium" # Type III/V over Type I podium (5-over-1)
    CONCRETE_I = "concrete_i"   # Type I, mid/high-rise

@dataclass
class Parcel:
    ssl: str                    # DC Square-Suffix-Lot — the universal key
    lot_area_sf: float
    zone_code: str
    submarket_id: str
    land_value: float | None    # assessed land value; None when no CAMA row (untaxed/exempt land)
    improvement_value: float | None
    land_use_code: str
    improvement_ratio: float | None   # improvement/(land+improvement); None when values missing
    existing_building_sf: float = 0.0   # gross building area from CAMA; 0 if vacant.
                                        # Feeds the demo toggle AND the developability flag.
    is_exempt: bool = False     # federal/public/church/cemetery/ROW — pre-filtered, never scored
    is_historic: bool = False   # in a historic district — flagged, gated, not scored in v1

@dataclass
class ZoningRules:
    district_code: str
    max_far: float
    max_height_ft: float
    max_stories: int | None
    lot_occupancy_pct: dict     # {"residential": 0.60, "other": 0.80}
    permitted_uses: list        # [Use, ...]
    parking_ratio: dict         # {"residential": stalls_per_unit, ...}
    requires_ground_floor_active: bool = False   # district mandates ground-floor retail/active use
    matter_of_right: bool = True

@dataclass
class MarketData:
    submarket_id: str
    rent_psf_residential_monthly: float
    retail_rent_psf_annual: float
    exit_cap_rate: float
    hard_cost_psf: dict         # {ConstructionType: $/SF}  (submarket-adjusted)
    as_of: str
    source: str

@dataclass
class Prototype:
    prototype_id: str           # "townhome" | "garden" | "midrise" | "highrise"
    construction_type: ConstructionType
    min_stories: int
    max_stories: int
    min_lot_sf: float           # admissibility gate: prototype needs at least this much lot
    efficiency_ratio: float     # net rentable / gross
    default_unit_mix: dict      # {"studio":0.2,"1br":0.5,"2br":0.3}
    avg_unit_sf: dict           # {"studio":500,"1br":750,"2br":1050}
    parking_type: str           # "surface"|"structured"|"podium"

@dataclass
class Assumptions:
    # flat container built from §2 defaults; every field carries a provenance tag
    # stored as {value, provenance} pairs so confidence.py can read tags
    program: dict
    timeline: dict
    cost: dict
    revenue: dict
    debt: dict
    exit: dict
    envelope: dict

@dataclass
class Envelope:
    max_buildable_gsf: float
    max_footprint_sf: float
    max_floors: int
    binding_constraint: str     # "far" | "height" | "lot_coverage"  — for the "gated by" callout
    admissible: bool
    reason: str = ""            # populated when not admissible

@dataclass
class Program:
    prototype_id: str
    construction_type: ConstructionType   # stamped by fit_program so the pro forma can price it (fix #2)
    gross_sf: float
    net_rentable_sf: float
    unit_count: int                       # REPORTING ONLY — never drives revenue (fix #3)
    unit_mix_counts: dict                 # reporting only
    retail_sf: float                      # required ground-floor active-use shell SF (costed, no revenue); 0 elsewhere
    parking_stalls: int
    parking_type: str
    floors: int

@dataclass
class Outputs:
    screening_rlv: float
    feasibility_gap: float | None   # rlv - land_value; None when no assessed value exists
    yield_on_cost: float
    irr: float | None           # None in screening tier
    equity_multiple: float | None
    profit_margin: float
    total_development_cost: float
    peak_equity: float | None
    confidence: float
```

### 3.2 `resolve_envelope(parcel, rules, assumptions) -> Envelope`

Pure geometry + code lookup. Uses the coverage-ratio simplification (we have lot **area**,
not dimensions, so no true setback geometry — this is standard screening practice).

The correct logic computes floors from height/story limits first (tracking which one bound
the floor count), then compares the FAR limit against the coverage×floors limit, and labels
the single binding constraint by which produced the minimum. No conflation (fix #4).

```
def resolve_envelope(parcel, rules, requested_use, assumptions):
    ftf = assumptions.envelope["floor_to_floor_residential_ft"]

    # 1. floors — limited by height, and possibly further by an explicit story cap
    floors_by_height = int(rules.max_height_ft // ftf)
    if rules.max_stories is not None and rules.max_stories < floors_by_height:
        floors = rules.max_stories
        floor_limiter = "stories"        # story cap bound the floor count
    else:
        floors = floors_by_height
        floor_limiter = "height"         # height bound the floor count

    # 2. two candidate GSF limits
    far_gsf = parcel.lot_area_sf * rules.max_far
    occ = rules.lot_occupancy_pct["residential" if requested_use == RESIDENTIAL else "other"]
    footprint = parcel.lot_area_sf * occ
    coverage_gsf = footprint * floors

    # 3. the binding constraint is whichever produced the minimum
    if far_gsf <= coverage_gsf:
        max_gsf = far_gsf
        binding = "far"
    else:
        max_gsf = coverage_gsf
        binding = floor_limiter          # "height" or "stories" — the real reason coverage was capped

    return Envelope(max_buildable_gsf=max_gsf, max_footprint_sf=footprint,
                    max_floors=floors, binding_constraint=binding, admissible=True)
```

`binding_constraint` is now always one of `"far"`, `"height"`, or `"stories"`, and is the
literal reason the envelope was capped — this is what the "gated by" callout reads. Use-gate
happens before this (see §3.3); envelope is only computed for a permitted use.

### 3.3 `fit_program(envelope, prototype, rules, requested_use, assumptions, parcel, overrides) -> Program`

Admissibility = the prototype's story range fits inside the envelope's `max_floors`.
If it does not fit, **no compute occurs** — return a rejection the UI shows as a zoning error.

```
def fit_program(envelope, prototype, rules, requested_use, assumptions, parcel, overrides=None):
    # use gate
    if requested_use not in rules.permitted_uses:
        raise NotPermitted(f"{requested_use.value} not permitted in {rules.district_code}")

    # admissibility: lot must be big enough for this prototype (fix B — no sliver high-rises)
    if parcel.lot_area_sf < prototype.min_lot_sf:
        raise NotPermitted(
            f"{prototype.prototype_id} requires >= {prototype.min_lot_sf:,.0f} SF lot; "
            f"parcel is {parcel.lot_area_sf:,.0f} SF")

    # admissibility: prototype must fit the envelope's floor count
    if prototype.min_stories > envelope.max_floors:
        raise NotPermitted(
            f"{prototype.prototype_id} needs >= {prototype.min_stories} stories; "
            f"{rules.district_code} allows {envelope.max_floors} "
            f"(gated by {envelope.binding_constraint})")

    floors = min(prototype.max_stories, envelope.max_floors)
    gross_sf = min(envelope.max_buildable_gsf, envelope.max_footprint_sf * floors)

    # Required ground-floor active use (v1.3): where the district mandates it, the ground
    # floor is built (costed at normal hard $/SF) but produces NO residential rent — it is
    # excluded from net rentable. Cost-without-revenue is the economic penalty of the mandate.
    # v1.3.2: gated on the prototype as well as the district — only building types that
    # plausibly have a commercial ground floor (§5 GROUND_FLOOR_ACTIVE_PROTOTYPES =
    # midrise/highrise) take the carve-out. Townhome and garden never do.
    required_active_sf = 0.0
    if (rules.requires_ground_floor_active
            and prototype.prototype_id in GROUND_FLOOR_ACTIVE_PROTOTYPES
            and floors >= 1):
        required_active_sf = min(envelope.max_footprint_sf, gross_sf)  # one floorplate
        # only the floors above the ground floor generate residential rentable SF
        residential_gsf = max(gross_sf - required_active_sf, 0.0)
    else:
        residential_gsf = gross_sf

    net = residential_gsf * prototype.efficiency_ratio
    avg_sf = sum(prototype.default_unit_mix[k]*prototype.avg_unit_sf[k]
                 for k in prototype.default_unit_mix)
    unit_count = int(net // avg_sf)
    unit_mix_counts = {k: int(unit_count*prototype.default_unit_mix[k])
                       for k in prototype.default_unit_mix}

    parking_ratio = rules.parking_ratio.get("residential", 0.5)
    stalls = int(round(unit_count * parking_ratio))

    program = Program(prototype_id=prototype.prototype_id,
                      construction_type=prototype.construction_type,   # fix #2
                      gross_sf=gross_sf, net_rentable_sf=net,
                      unit_count=unit_count, unit_mix_counts=unit_mix_counts,
                      retail_sf=required_active_sf,   # required ground-floor shell: costed, no revenue
                      parking_stalls=stalls,
                      parking_type=prototype.parking_type, floors=floors)
    if overrides:
        program = apply_overrides(program, overrides)   # user edits units/stories/stalls/etc
    return program
```

Note: `unit_count` and `unit_mix_counts` are computed for **reporting**. They do NOT feed
revenue — revenue is driven entirely by `net_rentable_sf × rent_psf` (fix #3). If a user
override changes `unit_count`, it changes the reported unit figure and parking, not the rent.

### 3.4 `screening_rlv(program, market, assumptions, parcel) -> Outputs` (TIER 1, static)

The fast residual that colors the map. No timeline, no debt. Margin-based, closed-form.

**Metric primacy (v1.2):** the primary output is **RLV** and **RLV per buildable SF**
(`rlv / program.gross_sf`) — "what can a developer pay for this site, cleared, at the
target return." The map colors on RLV/SF by default. `feasibility_gap`
(= RLV − assessed land value) is a *secondary, optional* comparison the user can switch to;
it is not the headline and the product does not depend on assessed values being accurate.

**Demolition (v1.2):** the bake ALWAYS computes with demolition off — the map ranks
clean-site potential uniformly across parcels. `include_demolition` is a drill-down-only
toggle: when on, add `parcel.existing_building_sf * assumptions.cost["demo_cost_psf"]`
to hard costs, lowering RLV for that underwrite. Default `demo_cost_psf` = $12/SF (national).

```
def screening_rlv(program, market, assumptions, parcel):
    rev = assumptions.revenue

    # --- stabilized NOI (per-SF basis only; unit_count never enters revenue) ---
    gross_residential = program.net_rentable_sf * market.rent_psf_residential_monthly * 12
    # No retail REVENUE in v1. Where a district mandates ground-floor active use,
    # program.retail_sf holds that shell SF: it is already inside gross_sf (so it IS costed
    # at hard $/SF) but was excluded from net_rentable_sf (so it earns nothing).
    egi = gross_residential * rev["stabilized_occupancy"]
    noi = egi * (1 - rev["opex_ratio"])

    exit_value = noi / market.exit_cap_rate

    # --- costs (land excluded — RLV solves for it) ---
    hard = program.gross_sf * market.hard_cost_psf[program.construction_type]
    hard += program.parking_stalls * assumptions.cost["parking_cost_per_stall"][program.parking_type]
    soft = hard * assumptions.cost["soft_cost_pct"]
    contingency = hard * assumptions.cost["contingency_pct"]
    cost_ex_land = hard + soft + contingency

    # --- margin-based residual ---
    profit = exit_value * assumptions.exit["target_developer_margin"]
    rlv = exit_value - cost_ex_land - profit

    tdc = cost_ex_land                    # screening TDC excludes land
    yoc = noi / tdc if tdc > 0 else 0.0   # unlevered yield-on-cost (ex-land screening proxy)
    margin = (exit_value - tdc) / tdc if tdc > 0 else 0.0

    # gap is secondary and None-safe: exempt/untaxed parcels have no assessed land value
    gap = (rlv - parcel.land_value) if parcel.land_value is not None else None

    return Outputs(screening_rlv=rlv, feasibility_gap=gap,
                   yield_on_cost=yoc, irr=None, equity_multiple=None,
                   profit_margin=margin, total_development_cost=tdc,
                   peak_equity=None, confidence=0.0)   # confidence filled by the caller
```

`market.hard_cost_psf` is keyed by `ConstructionType`; because `program` now carries its
`construction_type`, the lookup is direct and unambiguous.

### 3.5 `full_cashflow(program, market, assumptions, parcel) -> (CashFlow, Outputs)` (TIER 2)

The full monthly levered model. This is the most important and most error-prone function.
See §6 for the complete month-by-month mechanics. Build it after §3.4 passes its tests.

### 3.6 Confidence (`engine/confidence.py`)

Confidence = share of the input set that is locally tailored vs. national default.
Weight each consumed input by provenance: `local`=1.0, `submarket`=0.5, `national`=0.0.
`confidence = sum(weights) / count(inputs)`. In v1 this returns a low number honestly;
it rises automatically as the moat replaces `national`/`submarket` tags with `local`.

---

## 4. Hand-check tests (the Stage A gate — `tests/test_engine_hand_checks.py`)

Before writing any data code, prove the engine on parcels you compute by hand. Build these
as `pytest` cases with the expected numbers written out. Example scaffold:

```python
def test_midrise_screening_rlv_hand_check():
    parcel = Parcel(ssl="0123 0045", lot_area_sf=10_000, zone_code="MU-4",
                    submarket_id="noma", land_value=1_100_000,
                    improvement_value=200_000, land_use_code="vacant",
                    improvement_ratio=0.15)
    rules = ZoningRules(district_code="MU-4", max_far=2.5, max_height_ft=50,
                        max_stories=None,
                        lot_occupancy_pct={"residential":0.60,"other":0.80},
                        permitted_uses=[Use.RESIDENTIAL, Use.RETAIL],
                        parking_ratio={"residential":0.5})
    market = MarketData(submarket_id="noma", rent_psf_residential_monthly=3.20,
                        retail_rent_psf_annual=40, exit_cap_rate=0.055,
                        hard_cost_psf={ConstructionType.CONCRETE_I:340,
                                       ConstructionType.WOOD_OVER_PODIUM:260,
                                       ConstructionType.WOOD_V:210},
                        as_of="2026-06", source="Cumming Q2 2026")
    env = resolve_envelope(parcel, rules, Use.RESIDENTIAL, DEFAULT_ASSUMPTIONS)
    # HAND CHECK: far_gsf = 10000*2.5 = 25,000 ; floors = 50//10 = 5 ;
    #            coverage_gsf = 10000*0.60*5 = 30,000 ; max_gsf = min = 25,000 ; binding = "far"
    assert env.max_buildable_gsf == 25_000
    assert env.binding_constraint == "far"
    prog = fit_program(env, PROTOTYPES["midrise"], rules, Use.RESIDENTIAL, DEFAULT_ASSUMPTIONS, parcel)
    out = screening_rlv(prog, market, DEFAULT_ASSUMPTIONS, parcel)
    # Compute the expected RLV by hand from the numbers above and assert within $1.
```

Write **at least four** hand-check parcels covering: (a) FAR-binding, (b) height-binding,
(c) a prototype that does NOT fit (asserts `NotPermitted` with the right message), and
(d) a negative-RLV parcel (feasibility gap < 0). Only when these pass do you move to Stage B.

---

## 5. The prototype library (`engine/prototypes.py`)

Four prototypes, all rental. `min_stories` is the admissibility gate against the envelope.

| id | construction_type | min–max stories | min_lot_sf | efficiency | parking | default mix (studio/1br/2br) | avg SF (studio/1br/2br) | hard $/SF (national default) |
|---|---|---|---|---|---|---|---|---|
| townhome | wood_v | 2–3 | 1,500 | 0.90 | surface | 0/40/60 | –/900/1300 | $200 |
| garden | wood_v | 2–4 | 15,000 | 0.85 | surface | 20/50/30 | 500/750/1050 | $210 |
| midrise | concrete_i | 5–12 | 8,000 | 0.80 | podium | 25/50/25 | 500/750/1050 | $340 |
| highrise | concrete_i | 12–30 | 12,000 | 0.75 | structured | 30/50/20 | 480/720/1000 | $430 |

**Product-type revenue factors (v1.4).** Applied by `screening_rlv` and `full_cashflow` to
the submarket base rent and base cap (§2.4). **Placeholder assumptions — not sourced.**

| id | rent_premium_factor | exit_cap_adjustment | rationale (assumed, unverified) |
|---|---|---|---|
| townhome | 1.00 | +0 bps | the base — submarket rent is quoted for this product |
| garden | 1.00 | +0 bps | walk-up, no elevator or amenity package |
| midrise | 1.15 | −25 bps | new elevator product, amenity package |
| highrise | 1.30 | −50 bps | full-service Class A, institutional buyer pool |

The effective cap is floored at `MIN_EXIT_CAP_RATE = 0.001` so a future submarket cap or a
hand-edited assumption set cannot divide by zero in the exit valuation (unreachable at v1's
5.5% base; the engine never raises to the caller).

**Ground-floor active use is a prototype property too (v1.3.2).**
`GROUND_FLOOR_ACTIVE_PROTOTYPES = {midrise, highrise}` — the only building types that
plausibly carry a non-residential ground floor. `zoning_rules.requires_ground_floor_active`
says the *district* mandates active frontage; this set says which prototypes the carve-out
can physically apply to. `fit_program` requires BOTH. Townhome and garden are exempt: a
rowhouse has no ground-floor retail, and charging it one removed a third of its revenue
(one of three floors) while keeping all of its cost — which was, on its own, enough to drive
every parcel in a mandated district negative. Membership is stated explicitly, not derived
from `construction_type`: CONCRETE_I selects exactly {midrise, highrise} today, but that is a
coincidence of this table, and a future podium midrise would break the derivation silently.

Note: 5-over-1 (`podium` construction) can be added as a 5th prototype later; v1 starts with these four.
Hard $/SF here are the *national fallback* values baked into the default `MarketData`; the
submarket loader overrides them with DC-specific cost-report numbers when available.

---

## 6. §3.5 expanded — the full monthly levered cash flow (the crux)

Build a month-indexed model, `t = 0 .. T` where `T = predev + construction + leaseup + hold`.
Use numpy arrays of length `T+1`. All rules below are best-practice defaults.

### 6.1 Phase boundaries
```
predev:      months [0, p)          p = timeline.predevelopment_months
construction:months [p, p+c)        c = timeline.construction_months
leaseup:     months [p+c, p+c+l)    l = timeline.leaseup_months
hold:        months [p+c+l, T]      then SELL at month T
```

### 6.2 Cost timing
- **Land** is spent at month 0 (this is the value we solve for in RLV mode; a fixed input in IRR mode).
- **Soft costs**: spread straight-line across predevelopment + construction months.
- **Hard costs**: spread across construction months on an **S-curve** (use a standard
  beta-distribution / cumulative-normal S-curve; approximate with the normalized cumulative
  of a symmetric triangular distribution if you want it dependency-free). Escalate hard costs
  at `cost_escalation_annual` compounded monthly from month 0 to the month of spend.
- **Contingency**: spread proportionally with hard costs.
- **Demolition** (only when the drill-down toggle is on): spent in full in the **first month
  of construction**, before hard-cost draws begin. It is part of hard costs for loan-draw
  and contingency purposes.

### 6.3 Revenue timing
- Zero revenue until lease-up begins (month `p+c`).
- During lease-up, units fill at the **derived** rate `unit_count / leaseup_months` per month
  (absorption is not an independent assumption; it always reconciles with the timeline).
- Monthly revenue = occupied_units × avg_monthly_rent_per_unit × stabilized_occupancy,
  with rent escalated at `rent_growth_annual` compounded monthly from month 0.
- Retail NOI comes online at stabilization.
- Operating expenses = `opex_ratio` × effective gross income each month once occupied.

### 6.4 Construction loan
- Sized to `construction_ltc` × total project cost (incl. land).
- Equity funds costs first up to the equity share `(1 - ltc)`; the loan funds the remainder,
  drawing monthly as costs are incurred (a "equity-first" or "pari-passu" draw — use equity-first
  as the default, it's conservative and standard).
- Interest accrues monthly on the outstanding drawn balance at `construction_annual_rate/12`.
- **Interest reserve**: interest is capitalized (added to the loan balance) rather than paid in
  cash during construction — this is standard. So the loan balance grows by drawn principal + accrued interest.
- The construction loan is retired at stabilization by the permanent loan takeout.

### 6.5 Permanent loan takeout (at stabilization, month `p+c+l`)
- Perm loan sized = `min(perm_ltv × stabilized_value, dscr_constrained_amount)`
  where `stabilized_value = stabilized_NOI / exit_cap_rate`
  and `dscr_constrained_amount` = the loan whose annual debt service = `stabilized_NOI / perm_min_dscr`,
  solved from the amortizing-loan payment formula at `perm_annual_rate` over `perm_amortization_years`.
- Perm proceeds pay off the construction loan balance. If perm proceeds < construction balance,
  the gap is an additional equity contribution (a "cash-in refi"). If greater, the excess returns to equity.
- During the hold months, the property throws off `NOI - perm_debt_service` to equity.

### 6.6 Exit (month T)
```
gross_sale   = stabilized_NOI (at month T, escalated) / exit_cap_rate
net_sale     = gross_sale * (1 - selling_cost_pct) - perm_loan_balance_at_T
```
`net_sale` is the terminal equity cash flow.

### 6.7 Returns
- Build the monthly **equity cash-flow vector**: negative during construction (equity draws),
  small positive during hold (NOI less debt service), large positive at T (net sale).
- `irr` = monthly IRR of that vector, annualized (`(1+monthly_irr)^12 - 1`).
- `equity_multiple` = total distributions / total equity contributed.
- `peak_equity` = max cumulative equity outflow.
- `yield_on_cost` = stabilized_NOI / total_development_cost (incl. land).
- `profit_margin` = (gross_sale - TDC) / TDC.

**IRR must fail gracefully (fix #8).** `numpy_financial` is a separate package (not part of
numpy) and its `irr` returns `nan` for cash-flow vectors with no sign change or multiple sign
changes — which happens for deals that never turn positive. Compute IRR inside a guard:

```
import numpy_financial as npf   # pip install numpy-financial
def safe_irr(monthly_cf):
    try:
        m = npf.irr(monthly_cf)
        if m is None or np.isnan(m):
            return None
        return (1 + m) ** 12 - 1
    except Exception:
        return None
```

If `safe_irr` returns `None`, the underwrite still succeeds — it just reports IRR as
unavailable (the UI shows "—"). Never let a non-converging IRR crash the response.

### 6.8 Full-model RLV (§solve.py)
- **Margin-based (screening)**: closed-form as in §3.4.
- **IRR-based (full)**: `solve_irr()` — find the month-0 land value that makes the levered IRR
  equal the target hurdle. Use `scipy.optimize.brentq` over land value in `[0, exit_value]`.
  This is the precise RLV shown in the drill-down; it will differ slightly from the screening RLV,
  which is expected and disclosed in the UI ("screening estimate" vs "full underwriting").
- **The solve must fail gracefully (fix #8).** `brentq` raises `ValueError` when the target
  IRR is unachievable at any land value in the bracket (the function doesn't change sign).
  Wrap it: on `ValueError`, fall back to `rlv = 0` with a flag `irr_target_unachievable=True`.
  A land price of $0 that still can't hit the hurdle means the deal is infeasible even with free
  land — surface that honestly rather than crashing.

  ```
  from scipy.optimize import brentq
  def solve_irr_rlv(program, market, assumptions, hurdle):
      # upper bracket: land can never exceed the deal's stabilized exit value
      _, base = full_cashflow_with_land(program, market, assumptions, land=0.0)
      upper = base.exit_value                       # computed inside full_cashflow, on Outputs
      def gap(land):
          _, out = full_cashflow_with_land(program, market, assumptions, land)
          irr = out.irr
          return (irr - hurdle) if irr is not None else -1.0   # treat no-IRR as below hurdle
      try:
          return brentq(gap, 0.0, upper), False
      except ValueError:
          return 0.0, True   # unachievable even at $0 land
  ```

---

## 7. Stage B — data layer + DC loaders

### 7.1 Schema (`data/schema.sql`)
Seven tables per the data model. `ssl` is the DC universal key (Square-Suffix-Lot),
used everywhere we earlier wrote `apn`.

```sql
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE parcels (
  ssl TEXT PRIMARY KEY,
  parcel_geom GEOMETRY(MultiPolygon, 4326),
  lot_area_sf DOUBLE PRECISION,
  zone_code TEXT,          -- NOT a hard FK (fix #1): a parcel in a not-yet-encoded
                           -- district must still load. The bake resolves an unencoded
                           -- zone to a skip-with-reason, not a crash. Coverage of
                           -- zoning_rules improves over time without blocking loads.
  submarket_id TEXT REFERENCES submarkets(submarket_id),
  land_value DOUBLE PRECISION,
  improvement_value DOUBLE PRECISION,
  improvement_ratio DOUBLE PRECISION,
  land_use_code TEXT,
  existing_building_sf DOUBLE PRECISION DEFAULT 0,  -- CAMA gross building area; demo toggle + developability
  is_exempt BOOLEAN DEFAULT FALSE,                  -- public/federal/church/cemetery/ROW
  is_historic BOOLEAN DEFAULT FALSE                 -- in a historic district (flagged, not scored)
);
CREATE INDEX parcels_geom_gix ON parcels USING GIST (parcel_geom);

CREATE TABLE zoning_rules (
  district_code TEXT PRIMARY KEY,
  max_far DOUBLE PRECISION,
  max_height_ft DOUBLE PRECISION,
  max_stories INTEGER,
  lot_occupancy JSONB,
  permitted_uses JSONB,
  parking_ratio JSONB,
  requires_ground_floor_active BOOLEAN DEFAULT FALSE,
  matter_of_right BOOLEAN DEFAULT TRUE,
  source_citation TEXT,
  as_of_date DATE
);

CREATE TABLE submarkets (
  submarket_id TEXT PRIMARY KEY,
  name TEXT,
  boundary GEOMETRY(MultiPolygon, 4326)
);
CREATE INDEX submarkets_geom_gix ON submarkets USING GIST (boundary);

CREATE TABLE market_data (
  submarket_id TEXT REFERENCES submarkets(submarket_id),
  use_type TEXT,
  rent_psf DOUBLE PRECISION,
  cost_psf JSONB,          -- {construction_type: $/SF}
  exit_cap DOUBLE PRECISION,
  as_of DATE,
  source TEXT,
  PRIMARY KEY (submarket_id, use_type, as_of)
);

CREATE TABLE prototypes (
  prototype_id TEXT PRIMARY KEY,
  construction_type TEXT,
  min_stories INTEGER, max_stories INTEGER,
  efficiency_ratio DOUBLE PRECISION,
  default_unit_mix JSONB, avg_unit_sf JSONB, parking_type TEXT
);

CREATE TABLE bake_results (
  ssl TEXT REFERENCES parcels(ssl),
  prototype_id TEXT NOT NULL DEFAULT '__none__',  -- PK columns cannot be NULL in Postgres;
                                -- status rows (exempt/historic/unencoded/infeasible) use the
                                -- sentinel '__none__' instead of NULL
  is_best BOOLEAN,
  status TEXT NOT NULL,         -- 'scored' | 'infeasible' | 'zone_not_encoded' | 'exempt' | 'historic'
  screening_rlv DOUBLE PRECISION,   -- NULL when not 'scored'
  feasibility_gap DOUBLE PRECISION, -- NULL when not 'scored'
  -- v1.3.1: both ranking objectives are STORED, so no reader divides (§9).
  rlv_total DOUBLE PRECISION,            -- = screening_rlv; DEFAULT map objective + is_best
  rlv_per_buildable_sf DOUBLE PRECISION, -- = screening_rlv / gross_sf; alternate objective
  confidence DOUBLE PRECISION,
  binding_constraint TEXT,     -- for 'scored': far/height/stories; for others: the reason
  computed_at TIMESTAMPTZ,
  PRIMARY KEY (ssl, prototype_id, computed_at)
);
CREATE INDEX bake_best_idx ON bake_results (is_best, computed_at);
CREATE INDEX bake_status_idx ON bake_results (status, computed_at);
CREATE INDEX bake_rlv_total_idx ON bake_results (computed_at, rlv_total DESC);

CREATE TABLE assumption_sets (
  assumption_set_id TEXT PRIMARY KEY,
  name TEXT, is_default BOOLEAN DEFAULT FALSE,
  program JSONB, timeline JSONB, cost JSONB,
  revenue JSONB, debt JSONB, exit JSONB, envelope JSONB
);

CREATE TABLE scenarios (
  scenario_id TEXT PRIMARY KEY,
  ssl TEXT REFERENCES parcels(ssl),
  prototype_id TEXT REFERENCES prototypes(prototype_id),
  assumption_set_id TEXT REFERENCES assumption_sets(assumption_set_id),
  user_id TEXT DEFAULT 'local',   -- real auth later; single local user in v1
  market_snapshot JSONB,          -- v1.2: the exact MarketData values used, stamped at save
                                  -- time. A saved scenario NEVER re-reads live market data —
                                  -- it is fully frozen and reproducible. (Future: staleness
                                  -- flag + proposed refresh after N months. Deferred.)
  cashflow JSONB, outputs JSONB, saved_at TIMESTAMPTZ
);
```

### 7.2 DC data sources (pinned, deterministic loaders)

All from Open Data DC / DCGIS ArcGIS REST services. Standard query pattern:
`{FeatureServer_layer}/query?where=1=1&outFields=*&f=geojson&resultOffset=N&resultRecordCount=2000`
(paginate with `resultOffset`; DC caps page size, so loop until fewer than the page size return).

| Dataset | Source | Key fields → our fields |
|---|---|---|
| Parcel geometry | DCGIS "Common Ownership Lots" / parcel polygon layer | `SSL` → `ssl`; geometry → `parcel_geom`; compute `lot_area_sf` from geometry (project to EPSG:26985 / MD State Plane meters, area×10.7639) |
| Assessment values | CAMA Residential + Commercial extracts (joined by `SSL`); **Condo extract excluded in v1** | assessed land → `land_value`; improvement value → `improvement_value`; `USECODE` → `land_use_code` |
| Zoning districts | DCGIS Zoning polygon layer | `ZONING`/`ZONING_LABEL` → spatial-join to parcels → `zone_code` |
| Submarkets | DC Wards (or Neighborhood Clusters) polygon layer | `WARD`/`NAME` → `submarket_id`, `boundary` |
| Historic districts | DCGIS Historic Districts polygon layer | intersection → `is_historic` |

> **The loaders are deterministic code against these pinned endpoints.** LLM-assisted source
> discovery is deferred to the "city #2" expansion tool — it is NOT in the v1 runtime path.

Loader steps (`data/loaders/dc_parcels.py`):
1. Page through the parcel FeatureServer → GeoJSON → `geopandas`.
2. Reproject to EPSG:26985 (MD State Plane **meters**), compute `lot_area_sf = area_m2 * 10.7639`.
   **Sanity assertion (fix #7):** after computing, assert the *median* `lot_area_sf` falls in
   `[1_000, 50_000]`. If it doesn't, the projection/units are wrong — fail loudly, don't load
   garbage. (A median outside this range almost always means a swapped EPSG or a meters/feet mixup.)
3. Fetch the **Residential and Commercial** CAMA extracts only. **Exclude the Condominium
   extract entirely in v1 (fix #6)** — a condo building is one parcel but dozens of CAMA rows
   with values that don't aggregate cleanly, and condos are effectively never redevelopment
   targets (you'd have to buy out every unit owner). Filter them out by `land_use_code` /
   the condo extract, and record the count excluded.
4. For the remaining extracts, dedupe to one row per `SSL` (take `BLDG_NUM=1` for residential;
   for commercial take the single assessment row per `SSL`).
5. Join CAMA to parcels on `SSL`; compute `improvement_ratio = improvement/(land+improvement)`.
   Guard divide-by-zero: if `land+improvement == 0`, set `improvement_ratio = None`.
   Pull gross building area → `existing_building_sf` (0 where absent/vacant).
   Set `is_exempt` from CAMA tax-exempt status / owner type (federal, District, NPS, WMATA,
   religious, cemetery) plus obvious right-of-way land-use codes.
6. Spatial-join parcels to zoning polygons → `zone_code`. **Split-zoned rule (v1.2): assign
   the district with the largest intersection area** (`GROUP BY ssl ORDER BY
   ST_Area(ST_Intersection(...)) DESC LIMIT 1`); optionally flag parcels where the winning
   district covers <80% of the lot. Same largest-intersection rule for wards → `submarket_id`.
7. Spatial-join parcels to the DC **historic districts** layer → `is_historic = TRUE` on
   intersection. (v1 posture: historic parcels are flagged and gated, not scored.)
8. Bulk `COPY` into `parcels`.

**Schema-validation guard (v1.2).** Before any transform, assert the expected field names
exist in each fetched dataset (`SSL`, geometry, the CAMA value/area fields, `ZONING` label,
historic-district name field). On mismatch, **abort the load with a clear error naming the
missing field** — never load a partial/renamed schema silently. DC will rename fields
eventually; this turns that into a loud 5-minute fix instead of silent garbage. Repull
schedule: the 1st of every month, then re-bake.

`data/loaders/dc_zoning.py`: writes the **hand-encoded** `zoning_rules` rows (see §8),
plus loads the zoning polygon layer used only for the spatial join above.

`data/loaders/seed_market.py` — **one-time LLM-assisted rent seeding (v1.2).** The initial
DC submarket rent and cap-rate values are produced by an LLM research task: search current
DC market reports / listings, retrieve ward-average residential rents ($/SF/mo) and prevailing
multifamily exit caps, and write them into `market_data` with `source` and `as_of` recorded.
This is a **seeding task run once (and optionally re-run manually each quarter)** — the same
principle as zoning: the LLM authors reference data, deterministic code serves it. The LLM is
never in the runtime path, never invoked per-parcel, and never invents numbers at query time.
Construction cost $/SF comes from published quarterly cost reports (Cumming/Mortenson/Turner)
entered the same way. Until seeded, the engine falls back to the §2 national defaults (and
confidence reads accordingly low).

### 7.3 Repositories (`data/repositories.py`)
The only module that runs SQL. Functions:
`get_parcel(ssl)`, `parcels_in_bbox(bounds)`, `parcels_in_geo(ward)`,
`get_rules(zone_code)`, `get_market(submarket_id, as_of=None)`,
`get_prototypes()`, `write_bake_results(rows)`, `latest_bake_for_map(bounds, objective, filters)`,
`save_scenario(...)`, `get_scenario(id)`, `get_default_assumption_set()`.

---

## 8. The hand-encoded DC zoning table — starter seed (`data/loaders/seed_zoning.py`)

**Coverage expansion (pre-Stage-D).** The 11-district starter seed below left 65.4% of DC
parcels baking as `zone_not_encoded`. It has been extended by 17 districts — R-1A, R-1B,
R-2, R-3, RF-1, RF-4, MU-3A, MU-5A, MU-6B, MU-7B, MU-9B, MU-10, MU-12, PDR-1…4 — taking
`zone_not_encoded` to 1.0%. Two rules govern the expansion and both live in code:

- **Overlay-tagged codes resolve to their base district.** `parcels.zone_code` keeps the DC
  layer's value verbatim (`R-3/GT`); only rule *lookup* strips the tag, via
  `repositories.resolve_rules` — **exact match first, base district second**. Exact-first is
  load-bearing: Subtitle H names the NMU zones as base/overlay *pairs* with their own
  standards (`NMU-4/CP` FAR 2.0 vs `NMU-4/WP` FAR 2.5), so a bare `NMU-4` row would be wrong
  for every variant. The bake and the live API path share this one function.
- **Districts with no matter-of-right residential get a row with `permitted_uses=[]`**
  (PDR-1…4, Subtitle J § 101.2(d)). They bake as `infeasible` — "residential not permitted"
  — rather than as an uncovered hole in the map.

Expansion values are transcribed from the **consolidated ZR of 2024-03-04** (incorporating
ZC Order 18-16/19-27), not the per-subtitle PDFs, which predate the MU A/B split the DC
zoning layer actually uses. Subtitle D Ch. 3 and Subtitle E Ch. 3 impose **no FAR standard**
at all (bulk is lot occupancy × height); `max_far` is a required float, so those rows carry a
`NO_FAR_LIMIT` sentinel that can never bind and the bake correctly reports `stories`/`height`
as the gate. Districts deliberately left unencoded, with reasons, are listed in
`seed_zoning.NOT_ENCODED_BY_DESIGN` (Downtown D zones need street right-of-way width; CG-4
and ARTS-2 heights unsourced; NMU needs exact combined codes; `UNZONED` and `StE-*` are not
matter-of-right districts).

This is the one genuinely manual reference task. Below is the original **starter seed** of core
development-relevant DC districts with matter-of-right values from the 2016 Zoning Regulations,
so Stage C can run on day one. **These values must be human-verified against the current ZR
before production use** — they are best-effort starting points, flagged tune/verify. FAR and
height shown are the residential matter-of-right figures (many MU/RA districts have higher
figures only via IZ or special exception, which v1 excludes).

| district | max_far | max_height_ft | max_stories | lot_occ resid | lot_occ other | permitted (v1: resi?) | parking /unit | verify |
|---|---|---|---|---|---|---|---|---|
| RA-1 | 0.9 | 40 | null | 0.40 | 0.60 | yes | 1.0 | ✓ |
| RA-2 | 1.8 | 50 | null | 0.60 | 0.80 | yes | 0.5 | ✓ |
| RA-3 | 3.0 | 60 | null | 0.75 | 0.80 | yes | 0.5 | ✓ |
| RA-4 | 3.5 | 90 | null | 0.75 | 0.80 | yes | 0.33 | ✓ |
| RA-5 | 6.0 | 90 | null | 0.80 | 0.80 | yes | 0.33 | ✓ |
| MU-4 | 2.5 | 50 | null | 0.60 | 0.80 | yes | 0.5 | ✓ |
| MU-5 | 3.0 | 65 | null | 0.75 | 0.80 | yes | 0.5 | ✓ |
| MU-7 | 4.0 | 90 | null | 0.75 | 0.80 | yes | 0.33 | ✓ |
| MU-9 | 6.0 | 110 | null | 0.80 | 1.00 | yes | 0.33 | ✓ |
| D-4  | 8.5 | 130 | null | 1.00 | 1.00 | yes | 0.25 | ✓ |
| D-5  | 10.0 | 130 | null | 1.00 | 1.00 | yes | 0.25 | ✓ |

Add `requires_ground_floor_active` per district when encoding (typically TRUE for the
MU- and D- corridors that mandate ground-floor retail/active frontage; verify per district
against the ZR — same verification pass as the dimensional values).

Encode each as a `zoning_rules` row:

```python
SEED = [
  dict(district_code="MU-4", max_far=2.5, max_height_ft=50, max_stories=None,
       lot_occupancy={"residential":0.60, "other":0.80},
       permitted_uses=["residential","retail"], parking_ratio={"residential":0.5},
       matter_of_right=True, source_citation="2016 ZR Subtitle G",
       as_of_date="2026-01-01"),
  # ... one dict per row above ...
]
```

The `✓ verify` column is a checklist: before production, confirm each district's current
matter-of-right FAR/height against the live ZR (DCOZ's Zoning Handbook), since some figures
change and several districts have conditional bonuses this table deliberately omits (v1 is
matter-of-right, no IZ). Districts not in this seed load fine as parcels but bake as
`zone_not_encoded` until added — coverage grows incrementally with zero rework.

---

## 9. Stage C — the bake (`bake/run_bake.py`)

Every parcel produces at least one `bake_results` row — no parcel silently vanishes (fix #5).
Unencoded zones and all-infeasible parcels get a status row instead of a score.

```
for each parcel (single process, v1):
    # v1.2 pre-filters — these parcels are represented but never scored
    if parcel.is_exempt:
        write_row(ssl, prototype_id="__none__", is_best=True, status="exempt",
                  binding_constraint="public/exempt ownership"); continue
    if parcel.is_historic:
        write_row(ssl, prototype_id="__none__", is_best=True, status="historic",
                  binding_constraint="historic district — redevelopment restricted"); continue

    rules = get_rules(parcel.zone_code)     # None if district not encoded

    if rules is None:                        # fix #1: unencoded zone → represent, don't crash
        write_row(ssl=parcel.ssl, prototype_id="__none__", is_best=True,
                  status="zone_not_encoded", binding_constraint=parcel.zone_code)
        continue

    market = get_market(parcel.submarket_id)
    results = []
    for proto in get_prototypes():
        try:
            env  = resolve_envelope(parcel, rules, RESIDENTIAL, DEFAULT_ASSUMPTIONS)
            prog = fit_program(env, proto, rules, RESIDENTIAL, DEFAULT_ASSUMPTIONS, parcel)
            out  = screening_rlv(prog, market, DEFAULT_ASSUMPTIONS, parcel)
            out.confidence = score_confidence(PROVENANCE, market)
            results.append((proto, out, env.binding_constraint))
        except NotPermitted:
            continue                          # this prototype doesn't fit; try the next

    if results:
        # is_best is computed on ONE pinned objective: TOTAL RLV (the default map
        # objective — see the objective note below). Note: gap ordering is identical to
        # RLV ordering within a parcel (land_value is a per-parcel constant), so no second
        # flag is needed for gap; only total-RLV vs RLV/SF can disagree, and the UI's
        # top-2-3 list covers that case.
        # 5% tie margin: the incumbent best (from the prior bake, if any) keeps is_best
        # unless a challenger beats it by >5% on the objective. Prevents the recommended
        # program flipping month-to-month on input noise. Surface the top 2-3 in the UI.
        best = select_best_with_tie_margin(results, prior_best, margin=0.05)
        write all result rows (status="scored", is_best flagged on `best`)
    else:                                     # fix #5: no prototype admissible anywhere
        write_row(ssl=parcel.ssl, prototype_id="__none__", is_best=True,
                  status="infeasible",
                  binding_constraint="no admissible prototype under zoning envelope")
```

**Ranking objectives (v1.3.1 — both metrics are PERSISTED, never derived on read).** The
bake writes two columns on every `scored` row:

| column | value | role |
|---|---|---|
| `rlv_total` | `screening_rlv` | **default** map coloring/sort, and the pinned `is_best` objective |
| `rlv_per_buildable_sf` | `screening_rlv / program.gross_sf` | selectable **alternate** objective |

Total RLV is the default because RLV/SF is near-constant within a zone — it collapses to
roughly a constant per zone/prototype/submarket, so coloring on it reproduces the zoning
map. Total RLV varies parcel to parcel and is the more useful default. `gross_sf` is not a
column, so RLV/SF is computable *only* at bake time; readers (`latest_bake_for_map`, tiles,
tables) ORDER BY the stored column and must never divide by `lot_area_sf` at read time —
that was a third, unintended measure. Migration note in `data/schema.sql`:
`rlv_per_buildable_sf` cannot be backfilled and is repopulated by re-running the bake.

The map reads `status` to color parcels: `scored` → the total-RLV gradient; `infeasible`
→ gray; `zone_not_encoded` → "not yet covered" shade; `exempt` → neutral "not developable
(public/exempt)"; `historic` → "historic — restricted" shade. Every parcel is represented
and every color is explainable. Pre-filtering exempt+historic also shrinks the scored set
substantially (a large share of DC land is federal/public/historic).

Pure engine + data layer only. Run monthly, or whenever `market_data` updates.

**Batch retention (v1.3 — resolves the overwrite/tie-margin contradiction):** each bake
APPENDS a new batch keyed by its `computed_at`; the job then deletes batches older than the
last **2**. `prior_best` for the tie margin is read from the previous batch before writing
the new one; on the first-ever bake there is no incumbent and selection is plain argmax.
The map always reads the latest batch. (Turning on trends later = stop deleting.)

Verify Stage C by re-running the Stage A hand-check parcels through the real pipeline and
confirming the numbers match.

---

## 10. Stage D — API + map (last)

FastAPI endpoints, each mapping to a UI action:

```
(static) map tiles: regenerated ONCE per bake via tippecanoe -> PMTiles, served from flat
     storage/CDN. Tile attributes carry rlv_total, rlv_per_buildable_sf, gap, status,
     confidence, is_best prototype — both objectives ship as baked columns (§9), so
     objective switching and filtering happen CLIENT-SIDE with no server call and no
     client-side division.
GET  /map/query?bounds&filters             -> only for the table/compare views; reads bake_results
GET  /parcel/{ssl}/underwrite?assumptions  -> runs full_cashflow() live for one parcel; caches result
POST /scenario                             -> save_scenario()
GET  /scenario/{id}/export?toggles         -> serialize assumption_set + cashflow + outputs to file
GET  /assumptions/default                  -> get_default_assumption_set()  (autoloads on app open)
```

Frontend: React + MapLibre GL over the static PMTiles. Three panels — left filter/objective/
program pane, center map colored by **total-RLV percentile-within-view** (default: the
baked `rlv_total`, which is also the objective `is_best` is pinned to, so the color and the
recommended program agree; `rlv_per_buildable_sf` and feasibility-gap are the selectable
alternates), right drill-down card with the "gated by"
callout, the demolition toggle, the developability flag ("existing building: N SF — acquisition
will run above land value"), editable-assumptions expanded tab, compare view, export. Light
surfaces, teal single-accent. Query chat is deferred.

The map endpoint reads precomputed results (fast, ~50ms). The underwrite endpoint is the
only place the full engine runs live, one parcel at a time, cached, re-run only on assumption edits.

---

## 11. Known accepted simplifications (documented, fix later)

- **Surface parking lot-area consumption (G):** surface stalls are costed but their land
  take is NOT netted out of the buildable footprint. A full-coverage garden building with
  surface parking is geometrically impossible; v1 knowingly ignores this. Revisit when
  adding real massing.
- **Ground-floor active-use mandate is applied district-wide, not per street segment.** The
  ZR ties active frontage to *designated street segments* (e.g. Subtitle I § 601), not to
  whole zones, and v1 has no street-centerline/segment data to join against. So every
  mid/high-rise parcel in a district flagged `requires_ground_floor_active` takes the
  carve-out, including parcels with no designated frontage. Scope of the overstatement after
  v1.3.2: **mid/high-rise only, inside mandated districts only** — it no longer touches
  townhome/garden, and no longer touches any parcel outside the MU-/D- corridors. Before
  v1.3.2 it applied to every prototype in those districts and was the single largest
  distortion in the bake. Fix needs a street-segment layer.
- Coverage-ratio setback simplification (§3.2) — no true setback geometry without lot dimensions.
- **Product-type rent premium and exit-cap adjustment are placeholder assumptions (§2.4/§5).**
  `RENT_PREMIUM_FACTOR` (1.00/1.00/1.15/1.30) and `EXIT_CAP_ADJUSTMENT` (0/0/−25bps/−50bps)
  were chosen as plausible starting values to give product type a voice in the model, not
  measured from anything. They are load-bearing for which prototype wins a parcel, so the
  `is_best` distribution across the map is only as good as these two numbers. What they want
  is **real rent-by-product-type and cap-by-product-type data per submarket** — DC Class A
  elevator rents versus rowhouse rents is an empirical question with a real answer, and these
  are not it. Both are tagged `national` in `PROVENANCE`, so confidence already reports them
  as un-tailored. Do not present the resulting prototype ordering as a finding until seeded.
- Ward-level rents — submarket averages; parcel-level comps are the data-moat upgrade.
- Historic parcels gated, not modeled — HPRB-compatible redevelopment is a later feature.
- Screening RLV (unlevered, margin-based) vs full RLV (levered, IRR-based) will diverge;
  accepted and labeled in the UI.
- §8 zoning seed and §2 defaults are plausible-not-verified until the human verification pass.

## 12. Build order checklist

- [ ] **Stage A**: `engine/` pure functions + `tests/` hand-checks. `pytest` green on 4+ parcels. **← start here**
- [ ] **Stage B**: `schema.sql`, deterministic DC loaders, `repositories.py`. Load & spot-check real parcels.
- [ ] **Stage C**: `run_bake.py`. Bake DC; confirm hand-check parcels match Stage A.
- [ ] **Stage D**: FastAPI + MapLibre frontend on the baked dataset.

Do not advance a stage until the prior stage's verification passes.
