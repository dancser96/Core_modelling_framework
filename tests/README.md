# tests

**Now (Phase 2 build-out): light tests.**
- Correctness invariants (`CLAUDE.md` §4):
  - time separation; OOT target windows not overlapping training's;
  - client-grouped train/test split; label-using checks on train-split clients in the window, and
    label-free checks never on the validation month;
  - train-only sampling (after the split); the prior-shift offset uses the weighted training rate
    (zero when the class balance is unchanged); calibration fitted out-of-fold inside train;
  - lineage exclusion; unseen categorical levels handled;
  - the due-diligence gate; batch-write completeness.
- Config migrations: old configs still load (`CLAUDE.md` §2).
- Generator validation tests for the synthetic data (`docs/components/test_harness.md`).
- One end-to-end test on synthetic data with **real local PySpark**: no stubs, and assertions against
  the generator's ground truth (traps flagged, oracle AUC never beaten).

Tests import the dev-only `synthetic` package. The `unit` preset keeps them fast; the `canonical`
dataset is for notebooks and demos.

**Before migration into the bank:** every function tested, internal CI/CD and Sonar checks passing.

Run with `pytest` (configured to collect only this folder; `legacy/` is excluded). "No tests ran" is
expected until the first tests exist.
