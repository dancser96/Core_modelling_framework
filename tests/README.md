# tests

**Now and at the December pre-release: light tests** (D-014).
- Correctness invariants (`CLAUDE.md` §4):
  - time separation; OOT target windows not overlapping training's;
  - client-grouped train/test split, made after Feature Checks; label-using views in EDA and
    Feature Checks never after the window, fitting and choices from Training on train-split
    clients only, and label-free checks never on the validation month;
  - train-only sampling (after the split), only when the config declares it; the prior-shift
    offset uses the effective training rate (the sampled rate in Phase 2, which has no sample
    weights; zero when the class balance is unchanged); calibration fitted out-of-fold inside train;
  - lineage exclusion; unseen categorical levels handled;
  - the due-diligence gate and the feature sign-off before register; batch-write completeness;
  - `register` writes the plain-data model, and the promoted bundle round-trips without pickle
    (identical predictions, D-051).
- Config migrations: old configs still load (`CLAUDE.md` §2).
- Generator validation tests for the synthetic data (`docs/components/test_harness.md`).
- One end-to-end test on synthetic data with **real local PySpark**: no stubs, and assertions against
  the generator's ground truth (traps flagged, oracle AUC never beaten by more than about two
  standard errors on positive events). On the `unit` preset it stays under two minutes; the
  canonical run is nightly or on request (D-100).

Tests import the dev-only `synthetic` package and generate their data from its seed when they run
(the `unit` preset, 5k clients), so they never read a stored dataset. The package goes into the
bank with the tests as code, never as data (D-041). The `dev` dataset (20k) is for daily work and
the `canonical` one (100k) for the slow tests, notebooks and demos, outside the bank.

**By release 1.0:** every function tested, internal CI/CD and Sonar checks passing (D-014). Tests
are a milestone criterion, not part of a depth level.

Run with `pytest` (configured to collect only this folder; `legacy/` is excluded). "No tests ran" is
expected until the first tests exist.
