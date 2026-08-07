Build Stage A: the pure engine core, per SPEC.md sections 1-6 (read them fully first).

Scope — ONLY these files:
- engine/types.py — all dataclasses from SPEC.md §3.1, field names exactly as written
- engine/assumptions.py — DEFAULT_ASSUMPTIONS and PROVENANCE verbatim from §2.8
- engine/prototypes.py — the four prototypes from the §5 table (townhome, garden, midrise, highrise), incl. min_lot_sf
- engine/envelope.py — resolve_envelope per §3.2 (the corrected three-candidate binding logic)
- engine/program.py — fit_program per §3.3, including the min_lot_sf gate, the parcel arg, and the required-ground-floor-active carve-out
- engine/proforma.py — screening_rlv per §3.4 (per-SF revenue only, None-safe gap), then full_cashflow per §6 (monthly numpy arrays, S-curve draws, capitalized construction interest, LTV/DSCR perm takeout, derived absorption = unit_count/leaseup_months, demo cost in first construction month when toggled)
- engine/solve.py — safe_irr and solve_irr_rlv per §6.7-6.8 with graceful failure
- engine/confidence.py — provenance-weighted score per §3.6
- tests/test_engine_hand_checks.py — at least the four required cases from §4: (a) FAR-binding, (b) height-binding, (c) prototype not admissible (assert NotPermitted, check message), (d) negative-RLV parcel. For each, COMPUTE THE EXPECTED NUMBERS BY HAND in comments, then assert within $1.

Rules: engine/ imports nothing but stdlib, numpy, numpy_financial, scipy. No DB, no network. Do not touch data/, bake/, or api/.

Definition of done: `pytest -x -q` fully green. Show me the hand-check arithmetic in the test comments so I can verify it myself. Then stop — do not start Stage B.
