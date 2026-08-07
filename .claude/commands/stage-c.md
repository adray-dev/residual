Prerequisite: Stage B gate passed (data loaded, spot-checks shown). If not, stop and say so.

Build Stage C: the bake, per SPEC.md §9 (read fully first).

Scope: bake/run_bake.py — single process (no multiprocessing). Per parcel:
- pre-filter is_exempt -> status 'exempt' row; is_historic -> 'historic' row
- unencoded zone -> 'zone_not_encoded' row
- else run each prototype through the PURE engine (resolve_envelope, fit_program, screening_rlv, confidence); NotPermitted -> skip prototype
- no admissible prototype -> 'infeasible' row
- is_best on RLV-per-buildable-SF with the 5% tie margin vs prior batch's best (first bake: plain argmax)
- append as a new computed_at batch; retain last 2 batches, delete older

Verification gate (show me all of it):
1. Bake all of DC. Report: runtime, rows written, status breakdown (scored/infeasible/zone_not_encoded/exempt/historic).
2. Re-run the four Stage A hand-check parcel fixtures THROUGH the real pipeline (insert them as synthetic rows or match real equivalents) and confirm outputs match Stage A to the dollar.
3. Print the top 10 parcels by screening RLV/SF with their best prototype and binding constraint; sanity-assess whether they're plausible (no high-rises on sliver lots, no scored federal land).
Then stop — do not start Stage D.
