# tests

**Now and at the December pre-release: light tests** (D-014).
- Correctness invariants (`CLAUDE.md` §4):
  - time separation; OOT target windows not overlapping training's;
  - client-grouped train/test split, made after Feature Checks; label-using views in EDA and
    Feature Checks never after the window, fitting and choices from Training on train-split
    clients only, and label-free checks never on the validation period;
  - train-only sampling (after the split), only when the config declares it; the prior-shift
    offset uses the effective training rate (the sampled rate in Phase 2, which has no sample
    weights; zero when the class balance is unchanged); calibration fitted out-of-fold inside train;
  - lineage exclusion; unseen categorical levels handled;
  - the due-diligence gate and the feature sign-off before register; batch-write completeness;
  - `register` writes the plain-data model, and the promoted bundle round-trips without pickle
    (identical predictions, D-051).
- Config migrations: old configs still load (`CLAUDE.md` §2).
- Generator validation tests for the synthetic data (`docs/components/test_harness.md`).
- One end-to-end test on synthetic data with **real local PySpark**, no stubs:
  `test_run.py::test_run_two_configs_runs_every_stage` runs every built stage through `run` on
  the two example configs at once (one model input, then EDA, Feature Checks, Training and Evaluation per config).
  The tests read frozen copies of the examples in `tests/conf/`, so a try-out in `conf/base/`
  changes no test; `test_config_schema.py::test_the_shipped_examples_load` checks that every
  example there still loads. From
  Training on it also asserts against the generator's ground truth (oracle AUC never beaten by
  more than about two standard errors on positive events). On the `unit` preset it stays under
  two minutes; the canonical run is nightly or on request (D-100).
- The trap acceptance test (`test_traps.py`, marker `traps`, D-064, D-137): EDA and Feature Checks
  on the `dev` preset (20k clients, generated in the test run) for both example configs, against
  two mappings of `truth.json`'s trap list: every trap is caught by its findings
  (`TRAP_FINDINGS`) or listed in `NOT_CHECKS` with a reason, and every control, a column close to
  a check's threshold on the safe side, raises none of the findings it must not
  (`CONTROL_FINDINGS`; a row may be both), with each forbidden finding's measure computed; the
  deposit's sub-range missing leak is also asserted to raise no missingness leak on the card
  config. The other false-positive checks are the null controls (pure noise) staying unflagged
  and, count-free, no legitimate card column, the control-only real columns included, raising a
  leak or lag flag (`NEVER_ON_LEGITIMATE`); there is no bound on the count of held non-trap
  features. The test runs in the default suite; skip it in a quick loop with
  `pytest -m "not slow and not traps"` (a `-m` replaces the default `not slow`). The regression
  trap (Cohen's d) is asserted in `test_feature_checks.py`.
- The modelling acceptance tests (`test_modelling_acceptance.py`, marker `acceptance`;
  [evaluation](../docs/components/evaluation.md)): four tests on the `dev` preset over three
  Training and Evaluation runs of the card config (`lgbm`, 15 trials, 100 bootstrap replicates):
  the plain run beats the single-feature baseline on validation and stays within two standard
  errors of the oracle's AUC; a run with the strongest leak trap kept by a person beats the
  oracle; observed to expected is within 10% with and without `negative_downsampling`. They
  share `dev`'s EDA and Feature Checks with the trap test (`dev_stage2`), each run on its own
  copy of their folder: with the trap test, 20 passed in 6 min 45 s on the 8 GB laptop. They run in the default suite; skip them in a quick loop as `traps` is:
  `pytest -m "not slow and not traps and not acceptance"`.
- The `slow` marker also holds the four model families through the search, each with its round
  trip, on the `dev` preset (`test_training.py`; [training](../docs/components/training.md)).
  It stays outside the default suite, like the canonical-size checks.

Tests import the dev-only `synthetic` package and generate their data from its seed when they run
(the `unit` preset, 5k clients), so they never read a stored dataset. The package goes into the
bank with the tests as code, never as data (D-041). The `dev` dataset (20k) is for daily work and
the `canonical` one (100k) for the slow tests, notebooks and demos, outside the bank.

A stage runs once per session where several modules read it: `conftest.py` builds EDA's frames
(`eda_frames`) and the EDA runs of the card config and the regression variant on the unit preset
(`eda_card`, `eda_regression`, on the data root `eda_env`), and holds the config variants
(`in_memory`, `regression_cfg`) and the audit-log entry builder (`build_entry`) the modules
share. A shared value is read-only: a test that changes one, or a file under its data root, works
on its own copy (Feature Checks' tests copy the EDA runs' root).

`test_code_rules.py` checks the code rules a linter can't: every function has a docstring,
framework code never names a trap column, and every notebook but `00_synthetic_data` is
committed without outputs (`notebooks/README.md`).

**By release 1.0:** every function tested, internal CI/CD and Sonar checks passing (D-014). Tests
are a milestone criterion, not part of a depth level.

Run with `pytest` (configured to collect only this folder; `legacy/` is excluded).
