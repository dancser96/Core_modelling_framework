# Handover: synthetic-0.6.0
_Written: 2026-11-10 (build done, the SDS's answers Q560–Q561 applied) · branch: main · last
commit: 42e8db0 (Run guide); everything below is uncommitted on top of it_

## Goal
Build synthetic 0.6.0 from `worknotes/synthetic_trap_coverage_plan.md` (§6): every Feature Checks
finding gets a trap that must raise it and a control close to its threshold that must not. The
SDS: "Using the defined plan in synthetic_trap_coverage_plan, please build the new version of the
synthetic data generation. I am accepting your default answer to every question you raised."
The build is one major step: it ends in the SDS's review, then a commit when they ask.

## State
- **Done:** all of §6.1–6.5. Generator 0.6.0 (nine trap columns, six natural-control rows, the
  streams `controls` and `control_leaks`, 166 columns); checks (`checks/controls.py`, a new
  family; four look-ahead checks in `checks/traps.py`); the trap test's second mapping
  (`CONTROL_FINDINGS`) and the new tests; both datasets regenerated with `--checks`; both
  example configs re-run on canonical by CLI; notebook 00 re-run in place; docs and the log.
  The measured table and every deviation are in `worknotes/log.md` (2026-11-10 entry).
- **Verified:** full suite 621 passed (17 min); trap test 15 passed; canonical 1,373 of 1,373
  check rows in ten families; `ruff check .` clean.
- **Not started:** the SDS's review of the build; the commit (only when the SDS asks).
- **Uncommitted, this topic's files:** `synthetic/src/synthetic/{__init__,generate}.py`,
  `spec/traps.py`, `mechanisms/{traps,controls}.py` (controls new), `checks/{traps,controls,
  table,mart,suite}.py` (controls new); `tests/{test_traps,test_synthetic_traps,
  test_synthetic_mart,test_synthetic_population}.py`, the Cohen's d test and
  `REGRESSION_CANDIDATES` in `tests/test_feature_checks.py`, `REGRESSION_CANDIDATES` in
  `tests/test_eda.py`, `tests/data/synthetic_mart_columns.txt`, `tests/README.md`;
  `docs/components/{test_harness,feature_checks}.md` (the trap sections), `docs/glossary.md`,
  D-064 in `docs/decisions.md`, the synthetic lines and one backlog item in `docs/roadmap.md`,
  `docs/UPDATES.md` (synthetic row, one log line), `docs/context/environment.md` (dev tools),
  `requirements-dev.txt`, `synthetic/REVIEW.md`, `notebooks/00_synthetic_data.ipynb`,
  `worknotes/log.md`, `worknotes/synthetic_trap_coverage_plan.md` (renumbering),
  `worknotes/synthetic_trap_coverage.md` (deleted, as the plan says).
- **Uncommitted, NOT this topic's:** the Feature Checks session's work (`src/core_modelling/*`,
  `conf/base/TEMPLATE.yml`, `docs/components/config.md`, `docs/context/project.md`, the
  roadmap's Phase 2 merge, deleted `docs/reference/*`, notebook 03, `worknotes/README.md`,
  `worknotes/m2_2_understanding/*`, the `concordance_range_floor` lines in
  `feature_checks.md` and the tests). Several files carry both (`feature_checks.md`,
  `roadmap.md`, `UPDATES.md`, `decisions.md`, `log.md`, `test_feature_checks.py`): don't revert
  hunks you didn't write.

## Decisions in this chat
- In D-064 (extended in place): controls as the test's second mapping, the natural rows, the
  `unstable` kind built now, no lagged flip / 60%-lag control / few-events minority, the two
  streams.
- Not D-rows (build choices, recorded in the log and the spec's `expected` texts):
  - the deposit rate blanks `blank_share` 0.5 of the converters, because the 3-month prevalence
    is 0.82% and a full blank sits above EDA's 0.5% null-share range;
  - the spend threshold is 60,000; the honest and vendor scores are standardised (same spread
    every month), honest σ `{even: 0.3, odd: 0.9}`, wait factor 1.6;
  - the monthly columns in a new `mechanisms/controls.py` and `checks/controls.py`;
  - `CONTROL_FINDINGS` lists only findings that could fire and no trap assertion already
    excludes; `_measured` asserts each control's measure was computed (the rare-value effect:
    `dominant_share_window ≥ dominant_share_min`) and raises on a measure the ledger lacks;
  - the legitimate-columns guard exempts only trap columns, listed rows and rows whose own
    findings are leak or lag flags (`_may_leak_by_design`).
- The SDS's answers: Q560 "Don't separate" (the trap modules stay whole); Q561 "Yes, add to it"
  (`nbclient>=0.10` in `requirements-dev.txt`, installed 0.11.0).
- Question numbers: the plan's Q546 and Q547 became Q558 and Q559 (a parallel session used them);
  Q560–Q561 were this chat's; the Feature Checks session was told to start at Q562.

## Open questions
- None open on this topic. Q557's candidate (a saved model input does not notice new source
  columns) is a backlog line in `docs/roadmap.md`, not decided.

## Next steps
1. Take the SDS's review of the build. Their review order is in the plan's §7: `spec/traps.py`
   (the fifteen rows), then `mechanisms/controls.py` and `_u_leak`, `_blanked_on_conversion`,
   `_application_status`, `_spend_leak` in `mechanisms/traps.py`, then `tests/test_traps.py`
   (`TRAP_FINDINGS`, `CONTROL_FINDINGS`, `_measured`,
   `test_sub_range_missing_leak_fires_on_its_target_only`, `_may_leak_by_design`).
2. Apply the review's fixes; rerun the touched tests (the trap test runs in its own process, about
   5–6 minutes); regenerate the datasets only if a spec value changes.
3. Commit when the SDS asks, this topic's files only (see State).

## Gotchas
- `python -m synthetic --out` refuses a non-empty folder: delete `data/01_raw/synthetic_*` first.
  A saved model input doesn't notice new source columns: delete
  `data/05_model_input/retail_acquisition/` and re-run `--stages target_factory`.
- A spec parameter change must be restated in the checks (`checks/controls.py` and
  `checks/traps.py` constants blocks): the checks never read the spec.
- The U leak must stay out of the `leaks` stream (`finalize_lookahead` filters it by column), or
  every existing leak's draws move.
- The deposit trap sits near its bounds (0.42–0.44% null against 0.5%; null concordance 0.75
  against 0.70): a change to the deposit's prevalence fails the trap test loudly, by design.
- macOS has no `timeout`: deadlines use `perl -e 'alarm shift; exec @ARGV' <s> <cmd>`.
- Notebooks: `jupyter execute --inplace <notebook>` now works (nbclient). Write the notebook back
  with `\u` escapes (`ensure_ascii`), as the committed file has them, or the diff fills with noise.
- The canonical CLI run uses `conf/local/environment.yml` (the canonical dataset); the deposit
  config had no feature folder before this chat, so its audit log is new.

## Read first
1. `worknotes/log.md`, the 2026-11-10 "Synthetic 0.6.0" entry (measured table, deviations,
   reviews).
2. `worknotes/synthetic_trap_coverage_plan.md` §2–§5 and §7.
3. `docs/components/test_harness.md`: "Trap summary" (the new rows, Controls, Not planted).
4. `docs/components/feature_checks.md`: "Trap acceptance test".
5. `synthetic/src/synthetic/spec/traps.py`, `mechanisms/controls.py`, `tests/test_traps.py`.
