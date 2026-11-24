# Handover: audit_fixes
_Written: 2026-11-23, after wave B · branch: main · last commit: 38e2ce3 (everything below is uncommitted)_

## Goal
Apply the audit of Training and Evaluation (`worknotes/m2_3_modelling/audit_steps_2_3.md`) as
the EDS answered it (`audit_answers.md`, Q676 to Q686 all at their defaults): every fix, every
refactor (40 to 58), the tests (59 to 68), then the docs (69 to 82, after the refactors), a
full suite, and the two review guides reworked to the current state. Two extra worknotes
reports are written: `pruning_noise_share.md` (Q690, Q691) and `hashes_and_compatibility.md`
(Q687 to Q689, OD-29; "washings" read as "hashings"). Item 14 is skipped, 24 dropped, 34 and 38
need nothing; 26, 32, 33 and 36 are on the roadmap (the `write_parquet` line, the transport
line, the bank-trip checks 6 and 7).

## State
- **Waves A and B are done and verified**: `ruff check src tests` clean; Spark batch over both
  chains 523 passed, 3 failed, the three being tests that lagged another builder's change
  (fixed on the main thread, rerun 3 passed). The acceptance runs on the dev preset: no `prune`
  row at threshold 0 (thresholds 0.009 to 0.011), 45 features pass the floor, 12 of them on
  `null_concordance`, selection takes 3 to 5 s, `judged_model.agrees` true, the "no split in
  the final model" warning names 3 to 5 final features per run.
- **Docs done**: `training.md` and `evaluation.md` rewritten by doc-writers (wave B's content;
  wave C's is not in them yet). `docs/roadmap.md`: OD-29, the deferred items.
- **Wave C running** (see Running agents). Nothing is committed.
- New files (untracked or intent-to-add): `run_artifacts.py`, `training/signoff.py`,
  `training/automl.py`, `evaluation/slices.py`, `evaluation/permutation.py`,
  `tests/cells_oracle.py`, `tests/test_permutation.py`, the two reports, the audit files.
  `.claude/worktrees/` must not be committed.

## What wave B built (for the docs pass and the review guides)
- Training selection: `screen_features` and `prune_features`; `encode_and_screen` before the
  run number, `finish_selection` after; the floor passes on value or null-indicator concordance
  (`cleared_by`); the pruning model is 4 leaves, `ceil(10·P/3)` trees, `colsample_bytree = 3/P`;
  a best noise share of 0 prunes nothing and warns; `check_noise_names` in the gate.
- Training run: `training/automl.py` (`SEARCH_FRAMES`); `check_judged_model` on every dealing
  (`training.json` → `judged_model`); `check_target_range`, `check_derived_names`; a one-value
  fold refused (`target_min`, `target_max`); `training.json` gains `threads`,
  `library_versions`, a `ledger_and_stage2` lap; `oof_log_loss` renamed `oof_loss`; `oof` gains
  `score_in_sample`; per-run ledger schema 2 (`floor_cleared_by`); `check_bundle` takes a
  `Bundle`; `check_order_kept` public; `threads` in the environment file; `few_events_warning`
  in `TASK_SPECS`; `level_factor` returns `zero_replicates`.
- Evaluation metrics: `evaluation/slices.py`, regression's 100 score bins with a tail pass,
  the narrow-slice guard (binary slices stop at 1e-5, regression at 4e-5), `no_interval`,
  `ROW_LOSSES`, `baselines.UNDEFINED`, meta `training_warnings`.
- Evaluation explanations: `evaluation/permutation.py` (its own 50,000-row hashed test sample;
  the event minimum applies to regression too), null-target test rows scored for the drift
  reference only (`NULL_TARGETS`, `KNOWN_TARGET`), `in_sample_concordance_cells`, `sampled`
  flag, the all-null partial dependence line, `timings.seconds` laps, `RunFolder`.
- Views: one `VIEWS` table (`entry["view"]` is a function or a per-task dict),
  `reporting/card.py` owns `CARD_SCHEMA_VERSION`, hovers in `,.4~r`, bare integers on the card.

## Decisions in this chat (not yet in docs/decisions.md; they extend D-139, D-140, D-141)
- Layout: run-folder readers in `run_artifacts.py`; `training/views.py` to
  `reporting/training_views.py`; nothing outside `training/` imports from it.
- The pruning sizing (ten offers per column) and the zero-share fallback; the floor on nulls.
- Item 5: Training stores `score_in_sample`; Evaluation computes train's concordance on cells.
- Permutation importance on its own sample; null-target test rows for the drift reference.
- Wave C's designs: one contract checked when a run is opened; the `stage2/` copy's own
  version with frozen columns; a sidecar for the drift reference; a committed golden run
  folder; `DEFAULT_STAGES`; `list_runs(cfg, entity, env)`; `score_spark` left as it is (it
  must verify the bytes it ships, so the bundle is read twice in Evaluation).
- Notebooks may show a package-built line of run facts as HTML output (Q686).

## Open points for the review guides and the ML audit
- A feature with nulls is tested twice at the floor (value, null indicator): pure noise passes
  more often. Not measured; 12 of 45 floor passes on dev come from nulls.
- Below about 15 columns the pruning model has fewer than 50 trees.
- `test_report_views_refuses_an_unknown_skip_name` was deleted: check a run-level test covers
  the refusal.
- The guard sits at the finest bin although capture is noisy there (tolerance table in
  `evaluation.md`).
- Reading the audit log once per Training run needs `resolve_config` to return its entries
  (not done; `config/audit_log.py`). `ledger.py` still cites V10.

## Doc follow-ups collected (for the propagation pass after wave C)
- `reporting.md`: lines 25, 60 to 68, 100, 131, 228, 247 (view 15 runs on the permutation
  sample), 284, 292, 349, 474 to 481, 535 to 547, 601 to 603, 622: `build_report` gone, one
  `VIEWS` row, `reporting/training_views.py`, `reporting/card.py` owns the version, bare
  stored reasons, chart fixes, `check_card_inputs` returns a `RunFolder`, no lift mode.
- `architecture.md`: §11 inventory (`run_artifacts.py`, `reporting/training_views.py`,
  `training/signoff.py`, `training/automl.py`, `evaluation/slices.py`, `permutation.py`,
  `cap_levels`), Public API (`Bundle`, `check_card_inputs`, `list_runs`, `show_run`), lines
  46 and 240 (view and bin counts: link `evaluation.md`).
- `feature_ledger.md`: lines 86, 265, 354, 371 (`read_run_ledger` and `signoff_table` moved,
  schema 2, `floor_cleared_by`, the no-split warning). `model_bundle.md`: 90, 288
  (`build_bundle`, `check_bundle(bundle, sample, expected, threads)`), lenient run numbers,
  `list_runs`' `unreadable` column, `find_run`'s message. `config.md`: the `run` entry's retry.
- `dataset.md:127`, `monitoring.md:59` (null-target rows), `glossary.md` (462, 482; entries:
  per-run ledger, `stage2/` copy, sign-off table, protected, headline, permutation sample,
  automated selection, importance pruning), `docs/context/environment.md` (143 categoricals
  round trips hold; `threads`), `components/environment.md` (`threads`), `lessons.md` (T42's
  "one dealing"; a new T-row: a module-level `F.col` needs a live SparkContext in PySpark 3.4),
  `modelling_faq.md` 11 and 217, `UPDATES.md` 27 and 63, `roadmap.md` 105 and 221.
- D-140: six switches, the pruning model's own size, every dealing, the null concordance.
  D-141 (b): regression's grid, the rerun promise to the binning's tolerance.
- Notebooks 04 and 05, `00_modelling_helper.ipynb`, `notebooks/README.md` (Q686).

## State after wave C (2026-11-23, later)
- Wave C is done and verified: `ruff check` and `ruff format --check` clean on `src` and `tests`;
  Spark batch 293 passed (Training, Evaluation, card, compare, runs, the golden run, acceptance).
- Built in wave C: `run_artifacts.open_run_folder` and the contract (`RUN_PATHS`,
  `TRAINING_PATHS`, `SAMPLED_PATH`, `SEARCH_KEYS`, `TRAINING_TABLE_COLUMNS`), the `stage2/`
  copy's own version (`STAGE2_COPY_SCHEMA_VERSION`, `STAGE2_COLUMNS`, `check_stage2_columns`),
  `evaluation/_drift_reference.json`, card version 2 (`rows_pooled`,
  `rows_validation_test_clients`, `framework_versions.card`), `DEFAULT_STAGES`,
  `list_runs(cfg, entity, env)`, `show_run(cfg, entity, env, run)`, the Public API test reading
  `docs/architecture.md`, 14 new `TASK_SPECS` keys with `bin_quantiles(grid)`,
  `narrowest_bin(grid, step)`, `quantile_passes(grid, tail_start)`.
- The golden run folder is generated and checked (`tests/data/golden_run/`, 405 KB, no login or
  home path; selection rules off, as the tests' five-feature runs).
- Found by the new real-data selection test and fixed on the main thread: pruning's undo check
  compared two fits that drew different columns per tree; both comparison fits now use
  `colsample_bytree = 1.0`. `pruning_noise_share.md` §5 and §6 still describe the old check:
  update them from the re-measurement.
- Model-side test gaps done (items 59, 60, 66, 68); the citation sweep done (item 77, 76).
- Docs done: `training.md`, `evaluation.md`, both propagation batches, the small follow-ups
  (D-041's exception, card fields in `reporting.md`, the sidecar in `monitoring.md`, the
  glossary, `tests/README.md`). Not yet: D-139 (add (f): the contract, the golden folder, the
  layout; D-041 already cites it), D-140, D-141, `UPDATES.md`, `worknotes/log.md`, the guides.

## Wave E: what the five reviews found (no blocking finding in any) and what was decided
- **ML audit (Fable):** the invariants hold. Fixed in the fix round: the null indicator's SE
  gets the tie correction `sqrt(3p(1-p))`; one null pattern clears one feature, not every
  feature that shares it (on the synthetic data "fewer than six months on the book" cleared ten
  rollups at once: the 12 of 45 null passes on dev); `check_order_kept` refuses a non-finite
  parameter; the narrow-slice guard moves from 1 to 12 finest bins (`MIN_SLICE_BINS`). Declared,
  not changed: the undo check judges the candidates as a set (measured: real features of about
  2 SE were nominated 115 of 200 times and dropped; about 4 SE, 20 of 120); the cluster rule
  picks its representative on the value only; in-sample scores above test's top edge tie in
  the last bin; a regression target without zeros makes permutation's event minimum vacuous;
  the one-value-fold refusal can meet a zero-inflated amount with very few non-zero clients.
  Sound: the judged-model check, `score_in_sample`, the null-target rows, permutation's sample,
  the refusals, byte-identical models at 1 to 8 threads for every family on this machine
  (categoricals and the bank's x86 build not run: a bank-trip check).
- **Compatibility (Opus):** `STAGE_SCHEMA_VERSIONS` training and evaluation 1 to 2, the drift
  reference 1 to 2, `__version__` 0.4.0 to 0.5.0 (a default to put first in the guides), a
  format fingerprint test against the golden folder, explicit card column lists, the contract
  also requires `training/resolved_config.yml`. Docs still to write: `threads` needs this
  framework version on every use case that shares the environment file; the Public API rows of
  `list_runs` and `show_run` note the changed argument order; `RunFolder` in the table.
- **Silent failures (Opus):** fixed in the fix round: bare JSON errors on a truncated
  `run.json`, `_stage2.json`, `_ledger_run.json`, stage json; the swap's message when
  `.old-<token>` is the only copy; `find_run` returns the runs it passed over and Evaluation
  stores them as a warning (`newer_runs_passed_over`); `list_runs` on a run with a bad bundle;
  strict `threads`; a null score in the drift counts; `effect_table`'s kind from the encoder.
- **Code review, Training side (Opus):** one reader of `run.json`; one definition of the
  sign-off and calibration columns; `missing_stage2` to `ledger.py`, `split_budget` to
  `config/`; the bundle step out of `training/run.py`; `search_families` split; leftovers.
  Justified, not done: `tail_start` stays a per-task entry (item 51, the EDS's word).
- **Code review, Evaluation side (Opus):** the scale note reads the run's own objective
  (`choices.objective`); `SCORE_COLUMN` a literal again; meta assembly to `evaluation/meta.py`;
  two card assertions that could not fail; small ones. Justified, not done: no further cut of
  `explain.py` (351 lines) or `compare.py` (tied functions; listed for the EDS).
- **Left for the main thread after both fix builders:** `model/__init__.py` exports only public
  names (the tests import from the submodules); the docs for everything above; D-139 (f).
- **Pruning re-measurement (31 cases, corrected undo check):** best noise share 0 in none;
  noise columns kept by an undo 199 before, 0 now; real features dropped 67 before (two undos
  were luck), 217 now, all in four cases at about 1,000 events and 400 columns; the comparison
  fits take 3.5 to 4.5 times longer at 400 columns; with `ceil(10P/3)` trees and every column
  offered they overfit at about 1,000 events. Pending: T1 (as now), T2 100 trees, T3 300 trees,
  and a feature that only works jointly with another.

## Fix round (2026-11-23, evening)
- The 5-hour limit stopped both fix builders at 15:31; resumed after the reset, both finished.
- Done and lint-clean: the Evaluation-side and the Training-side fix rounds as decided above,
  with the comparison fits capped at `COMPARISON_TREES = 300` (the measurement: T1, the
  yardstick's count, and T3, 300 trees, gave the same outcomes, 100 trees fired on noise; the
  undo caught nothing real in any variant: Q692 in `pruning_noise_share.md`, rewritten §5 to §8).
- Main thread after them: `tests/test_model_charts.py` (the `groups` argument),
  `model/__init__.py` exports `Bundle`, `load_bundle`, `score_frame` only, the helper notebook's
  `split_budget` import and `find_run` tuple, the golden folder regenerated (versions 2,
  framework 0.5.0, 405 KB, no login or home path).
- Written: D-139 (with (f)), D-140, D-141 extended; `UPDATES.md` status rows; the roadmap (M2.3
  row, bank-trip checks 6 to 8); `CLAUDE.md`'s state line (0.5.0). Not yet: the `UPDATES.md` log
  line, `worknotes/log.md`, the two review guides.
- Justified, not done: a truncated stage json still stops `list_runs` (it fails loud naming
  the file; the stage folder is swapped in whole); `tail_start` per task; no cut of
  `explain.py` or `compare.py`.
- New defaults to lead the guides (A136 onwards; re-check the highest A-number first): version
  0.5.0; the pruning size (Q690); the undo check kept and capped (Q692); the null-pattern rule
  and the tie correction; the slice guard at 12 bins; the screen before the run number; the
  changed argument order of `list_runs` and `show_run`; the layout moves; the contract and the
  copy's own version; the golden folder and its fingerprint test; `threads`; every dealing in
  the judged-model check; Feature Checks' `run` entry not retried; `score_spark` unchanged.

## Final state (2026-11-23, night): the build is finished, nothing is committed
- Verified after the fix round: the Spark batch (678 passed; the 3 failures were one new test
  that found the two-trial minimum, fixed, rerun 4 passed); the full suite with the slow tests,
  1343 passed in 32 min 36 s; after it two small edits (a docstring wrap in
  `training/search.py`, the per-stage wording of the missing-`run`-entry message in
  `config/audit_log.py`) with their test files rerun, 105 passed; `ruff check .` clean.
- The canonical data end to end under a scratch root (15 trials per family): 50 final features
  (cluster 57, floor 16; pruning nominated 8, undone on a rise from 0.110852 to 0.110901),
  CatBoost kept at 0.110528; Training 586 s, Evaluation 125 s by their laps (the Mac slept
  during Evaluation, so no wall-clock); test AUC 0.805, validation 0.800.
- Notebooks 04, 05 and the helper executed as scratch copies on `dev`: 9, 17 and 16 code cells,
  no error.
- Written: both review guides (defaults A136 to A164 first; Q687 to Q693), D-139 to D-141,
  D-041's exception, `UPDATES.md` (status and log line), the roadmap, `CLAUDE.md`'s state line,
  `worknotes/log.md`, `pruning_noise_share.md` (rewritten §5 to §8), the component docs.
- Usage of the whole session (audit and build): Fable 39% of the list-price total, above the
  25 to 30% ceiling; 167 of 318 main-thread requests ran above 300k tokens.

## Running agents
None.

## Next steps
1. The EDS reviews with the two guides; vetoes by A-number, answers Q687 to Q693.
2. Commit only on the EDS's word. New files to add then: `src/core_modelling/run_artifacts.py`,
   `training/automl.py`, `training/signoff.py`, `training/run_bundle.py`,
   `evaluation/slices.py`, `evaluation/permutation.py`, `evaluation/meta.py`,
   `reporting/training_views.py`, `tests/test_run_contract.py` (the golden run folder, its
   generator and `test_golden_run.py` were deleted on 2026-11-24 on the EDS's word: no stored
   run folder until 1.0, roadmap backlog), `tests/test_permutation.py`, `tests/cells_oracle.py`, and the
   five worknotes files of this build.
3. Leftovers found after the full suite, not fixed (small; one batch after the review):
   - `statistics/metrics.py` (around line 285): the docstring still says "a few of the finest
     score bins";
   - `worknotes/m2_3_modelling/plan.md` (around line 590) still gives the slice guard as 0.001%;
   - `docs/components/training.md`: the floor's false-pass rates may conflict (4 to 6% against
     1.7%); check which is current;
   - the environment file's `schema_version` stays 1 although `threads` was added;
   - `ruff format --check .` would reformat the Python blocks of 5 `docs/*.md` files.
4. The `doc-sync` skill has not been run at the end of this build.

## Gotchas
- Subagents run no Spark; one Spark job at a time and none while agents run pytest.
- Builders must not weaken tests; a failing Spark test goes back to its builder with the output.
- The last full suite ran on 2026-11-23 at the end of this build: 1343 passed.
- The scratchpad path holds a user name: never write it into a repo file.

## Read first
`worknotes/m2_3_modelling/audit_steps_2_3.md`, `audit_answers.md`, this file.
