# Handover: m2-3-training
_Checkpoint updated: 2026-11-16 (final runs returned; awaiting the EDS's review) · branch: main · last commit: 1749370_

## Goal
Build Stage 3 (M2.3 Modelling) major step 2, Training, from
`worknotes/m2_3_modelling/plan.md` → "Major step 2: Training" (m2.0 to m2.8). The EDS's word:
"Using the plan and all supportive documents, build major step 2 of M2.3". The step ends in
one ML audit (Fable, xhigh), `compat-guardian`, one fix round, the Spark batch, the full suite
once, review guide 2 (replaces `worknotes/m2_3_modelling/review_guide.md`), the docs, and a
stop for the EDS. Commit only on the EDS's word. Nothing is committed.

## State (all uncommitted; ruff clean; tests named are the ones run after the last edit)
- **Q667 is answered: option 1.** The config refuses `absolute_error` with a monotone
  constraint (`config/schema.py`, `Training._check_absolute_error_unconstrained`); `config.md`,
  `TEMPLATE.yml`, `training.md` item 10 and T43 say so.
- **m2.0 to m2.6 are built.** 207 no-Spark tests pass (`test_search`, `test_selection`,
  `test_calibration`, `test_fold_models`, `test_ledger_run`, `test_explain_charts`,
  `test_losses`, `test_training_tables`, `test_code_rules`, `test_config_schema`);
  `tests/test_training.py` passes on Spark (10 tests, 2 min 35 s); `test_frames`, `test_eda`,
  `test_feature_checks`, `test_dataset` passed (122) before the search was written.
  `tests/test_run.py` was changed (the unknown stage is `evaluation`; the two-config test
  names its three stages) and has **not been run since**: it is in the next Spark batch.
- **The search** (`training/search.py`): `Search`, `ClientFolds`, `fold_splitter`,
  `split_budget(cfg)`, `search_metric(metric)`, `build_search_space(space, fixed)`,
  `flaml_settings(family, space, fixed, cfg, budget, threads)`, `search_frame(family, X,
  encoder)`, `search_family(X, y, splitter, settings) -> log text`, `read_trials(family, log,
  searched)`, `check_search(family, trials, starts, budget)`, `search_families(X, y, folds,
  encoder, monotone, cfg, threads)`. Facts found while building it are in `worknotes/log.md`
  (FLAML's refit on every row cannot be switched off under CV; NaN, not infinity, for an
  undefined fold metric).
- **The stage** (`training/run.py`, 432 lines): runs end to end; `training/__init__.py`
  exports `run_training`; top-level `run.py` has `STAGES["training"]` with the `autonomous`
  rule (`_run_training_stage`, `training.gate.missing_stage2`).
- **Fixtures** (`tests/conftest.py`): `QUICK_SEARCH`, `with_training`, `trained_env`,
  `card_quick`, `regression_quick`, `trained_card`, `trained_regression` (both runs are of
  the use case `cc_acquisition`, so their run numbers depend on the order: read
  `result.meta["run_id"]`).
- **Docs:** the `doc-writer`'s five component docs are accepted. `training.md` is the main
  thread's and still says "designing": its rewrite is owed (list below).

## Routing from here (the EDS's word, 2026-11-16: far too many Fable tokens)
The cause, as the main thread reads it: after the reviews came back the main thread did the
fix round itself, in many small tool calls on a large context. From here: every remaining
code, test and doc piece goes to Opus or Sonnet agents with complete briefs; the main thread
runs the Spark batches (one background command each, no polling), reads each diff once and
writes the final report. No further Fable subagent. At the end: `/efficiency`, and the lesson
goes into the memory file `feedback_fable_budget.md`.

## Final runs (returned, 2026-11-16, all after the last code edit)
Spark batch 142 passed, 1 failed (the crash test patched a renamed function; fixed, passes);
slow four-family test 4 passed (4 min 58 s); notebooks 03, 04 and `00_modelling_helper`
executed as scratch copies, no error; canonical search: CatBoost kept, out-of-fold log loss
0.11061, 664 s with the upstream stages (table in review guide 2 §5); local EDA and Feature
Checks reruns of both example configs exit 0; full suite 1028 passed, 15 deselected.

## Done since the last checkpoint
- The Sonnet builder's three regression tests are in. The Spark batch after the fix round:
  142 passed, 1 failed (`test_a_crash_after_the_number_is_reserved…` patched a function the
  cut had renamed; the test now patches `encode_and_select`); the slow four-family test
  passes again (4 passed, 4 min 58 s).
- Both doc-writers reported and their work is read once and accepted: `training.md` (built
  state, real signatures, the audit's numbers), `model_bundle.md`, `architecture.md`,
  `lessons.md` (T44 to T47), `feature_ledger.md`, `docs/README.md`, `glossary.md`; review
  guide 2 (`worknotes/m2_3_modelling/review_guide.md`), `plan.md` §11 A82 to A91 and step
  3's "what step 2 leaves", `docs/decisions.md` (D-140, D-139 (a), D-132 (1) extended),
  `docs/UPDATES.md`, `docs/roadmap.md`. The questions Q668 to Q673 are answered at their
  defaults (the EDS, 2026-11-17; `answers.md`):
  - Q668: the deviance refusal stays.
  - Q669: `run <config>` with no `--stages` trains.
  - Q670: with the 1.0 hardening, in M2.4, fixed once in `write_parquet`.
  - Q671: the caption, no cross-fit.
  - Q672: `xgb_limitdepth` keeps FLAML's own start.
  - Q673: `native` stays the default; the cost goes into notebook 04's budget advice.

## Next
1. Done: `/efficiency` (Fable 40% of the spend since 11-09, this session's main thread 55% of
   its own; 58% of main-thread requests above 300k), the memory `feedback_fable_budget.md`,
   the guide, log, `run_modes.md` and `views.py` leftovers, and the final report to the EDS.
   Major step 2 waits for the EDS's review. Proposed for major step 3, not yet agreed: an
   Opus main thread, fixes sent back to their builders, a checkpoint at every minor step.
2. Nothing is committed; commit only on the EDS's word.
3. Step 2 stays open for the joint review with step 3 (review guide 2; defaults A82 to A91
   open). Major step 3 (Evaluation) starts from `worknotes/handovers/m2-3-evaluation.md`.

## The fix round: what was done (main thread, uncommitted; the no-Spark tests pass)
Everything was run after it (see "Final runs").
- **The search** (`training/search.py`): `fit_parameters(fixed, space, searched)` is the one
  rule for a configuration's parameters, used by FLAML's space and by every framework fit
  (the space wins over a fixed parameter; fixes the review's blocking item, with a test);
  `read_trials(family, log, searched, constants)` refuses a logged trial whose other values
  are not the framework's; `checked_space` and `check_spaces(cfg)` (the budget and every
  listed family's names, run first in `_open_run`); `search_families` refuses folds whose
  index is not the frame's; a missing FLAML log raises; `check_judged_model(search, own_loss,
  timed)`: the fold models' mean fold loss on `score_raw` against the best trial's
  (`LOSS_TOLERANCE` 1e-6), an error under a trial budget, the run's warning under a time
  budget; called in `_fit_out_of_fold` at one dealing only.
- **The stage** (`training/run.py`, 431 lines): `_open_run` runs `check_spaces`, the gate, the
  frames, the count and kind checks and the encoder's fit before `create_run` (`Opened` holds
  the encoder); `_save_ledgers` is called from `run_training`; the self-check rows by
  position. New `training/train_data.py` (131 lines): `TrainData`, `fit_train_encoder`,
  `encode_and_select` (returns the data, the log entries, the warnings), `_encoder_notes`.
- **The gate** (`training/gate.py`): `check_counts` also refuses a window period EDA counted
  that the panel no longer holds; `save_stage2` writes `stage2/_stage2.json`
  (`eda_schema_version` as read, `ledger_schema_version`, `runs`).
- **Selection:** `train_statistics(train, X, encoder, cfg)` no longer takes Stage 2: whether a
  numeric is judged on its best order is `is_non_monotone` on the train split's own numbers
  (`STATISTIC_COLUMNS` gains `non_monotone`); pruning compares the fit without the candidates
  against a fit with them, both without noise (one more fold fit when there are candidates).
- **Config:** `UseCaseConfig._check_deviance_has_a_log_link` (a deviance metric needs
  `tweedie` or `poisson`), with its test, `config.md` and the template. A default for veto.
- **Tables and views:** `train_metrics` adds `note` (`OPTIMISM_NOTE`); `training_views` takes
  `best` and `metrics` and gives `search["best"]`, `calibration["metrics"]`; an empty
  sign-off section names itself; the calibration caption says each method is fitted and
  judged on the same rows; the search caption says "every dealing's folds"; the beeswarm's
  title says "per sampled row". EDA's `edges` table is typed when empty. `row_concordance`
  refuses a non-finite entry. `_run_training_stage`'s loop is an `if` then a `for`.
- **Justified, not changed:** the calibration loss is not cross-fitted (said in the caption,
  the notebook and the doc); the `oof` table gets no new column (a doc line and a "to settle"
  line for step 3); all-None columns typed `null` in parquet stay until every stage's tables
  get schemas before 1.0 (a lessons row, a roadmap backlog line, a guide item).
- **Measured for audit item 11:** LightGBM gives identical trees and margins at auto, forced
  col-wise and forced row-wise layouts and at 1, 2 and 8 threads, on 60,000 × 40, 60,000 ×
  400 and 4,000 × 12 frames, 300 trees (script: the scratchpad's `audit/colwise.py`). No
  change; across machines stays unverified until the pre-release run.
- **m2.8 on `dev`** is in `worknotes/log.md` (the table per family). The canonical seconds
  per family are in the guide.

## Questions for the EDS, each with its default (number from the highest Q in the repo)
1. A deviance metric with an objective other than `tweedie` or `poisson` is refused at
   config load (built; the same shape as Q667). Default: keep.
2. `run <config>` with no `--stages` now trains (each call takes a run number and writes a
   `run` entry). Default: keep, with the note in `UPDATES.md`.
3. Typed parquet schemas for every stage's tables: now in `write_parquet`, or with the 1.0
   hardening. Default: with the hardening (M2.4).
4. The calibration table's per-method loss: cross-fit it by fold (about 15 lines, a new way
   to fail when a fold subset separates) or keep the caption. Default: the caption.
5. `xgb_limitdepth`'s start (FLAML's own: learning rate 0.3, depth 6) trailed on `dev` and
   was still improving at trial 15. Default: keep until the canonical numbers are in.
6. Declared categoricals triple CatBoost's search time on `dev` for the same loss. Default:
   keep `native` as the default; say so in the notebook's budget advice.

## The fix round's list (filled as the reports arrive; edit code only when all are in)
**From `compat-guardian` (done; verdict: nothing released breaks, one code item):**
- Code: `save_stage2` records which versions it copied, as `stage2/_stage2.json`
  (`eda_schema_version` from the `eda.json` read, `LEDGER_SCHEMA_VERSION`, the run tokens),
  so Evaluation can refuse a copy it cannot read.
- Code: EDA's empty `edges` frame gets its dtypes (`position` int64, `edge` float64;
  `eda/run.py` near line 422).
- Justify, not fix now: all-None text columns and all-empty list columns are written to
  parquet as type `null` / `list<null>` (`selection.represented_by`; the sign-off table's and
  the per-run ledger's text and list columns), so a table's schema changes with its data.
  pandas reads them back; Spark's handling is unverified. A lessons row (next T-number) and
  a roadmap backlog line "typed schemas for every stage's tables before the 1.0 freeze";
  listed in review guide 2 for the EDS (fix in `write_parquet` for all stages at once).
- Docs: `training.md` "What Training writes" (the real `training.json` keys, with `summary`'s
  keys as `list_runs`' columns and `oof_<metric>` named by the metric; `trials.fold_loss` is
  a loss; `selection.represented_by`; `explanation_sample`'s columns; `stage2/` holds every
  candidate's ledger rows, linking `model_bundle.md` instead of repeating it);
  `model_bundle.md` line ~54 (`stage2/`) and the recipe row (~251: parameters as `fit` takes
  them, constants and null ones included, e.g. CatBoost's `early_stopping_rounds: null`; a
  later version keeps every stored name accepted; changing `CONSTANTS` changes
  `recipe_hash`); `architecture.md` (Public API: `run`'s default now trains, `run_training`
  row, `--stages training evaluation` names a stage not built; inventory: EDA version 5,
  the Training rows "built"); `UPDATES.md` line ~60 (EDA 5, rerun, `run`'s default trains).

**From `code-reviewer` on m2.1 and m2.6 (done; one blocking, all accepted):**
- **Blocking:** `build_search_space` lets a fixed parameter override the space, while
  `search_families` and pruning let the space override the fixed ones. With
  `search_space.lgbm.monotone_constraints_method: {value: intermediate}` (which the schema
  allows) every trial runs `basic` and the kept model `intermediate`. Fix: a fixed parameter
  is a constant only when the space does not name it; a test case with that override.
- A guard for the whole class: `read_trials` refuses a logged trial whose values outside the
  searched ones are not the constants the framework fits with (the fixed parameters and the
  space's constants, a None left out), or that holds a name the framework does not know.
- Refusals that came after `create_run` move before it: `check_searched` and `check_params`
  on every listed family's space beside `split_budget` (one function in `search.py`, called
  first in `_open_run`), and the encoder's fit with its refusals (a constraint on an
  unordered categorical, a train level missing from `features.order`).
- `check_counts` also refuses when a window period EDA counted is missing from Training's
  population (today only the periods Training holds are compared).
- `_save_ledgers` is called from `run_training` between the bundle and the result, so the
  run's three writes are all visible there.
- The clean cut for `run.py`: `TrainData`, `_encode_and_select`, `_fit_encoder`,
  `_encoder_notes` (about 105 lines) to `training/train_data.py`; `run.py` keeps open, fit,
  write. Taken; listed for the EDS's veto.
- Small ones: the comment on CatBoost's `early_stopping_rounds: None` (FLAML skips a None
  domain, so its own range for it is not searched; `use_best_model: False` is what stops
  early stopping); `search_families` refuses folds whose index is not the frame's; a missing
  FLAML log raises "wrote no log"; `entry["levels"]`, not `.get`; the comment on
  `SIZE_PARAMETERS`; `_run_training_stage`'s loop as `if` then `for`; the self-check rows by
  `.iloc`; `row_concordance` refuses a non-finite prediction.

**From the ML audit (done; no leak at the defaults; verdict "needs evidence"):**
1. Under `training.time_budget_s` FLAML cuts LightGBM's and XGBoost's trees at a per-fold
   deadline while the log keeps the configured count: the kept model may not be the model
   the trial judged. Fix: after the fold models, at one dealing, compare their mean fold
   loss on `score_raw` with the best trial's `fold_loss`; unequal fails loud under a trial
   budget and warns with both numbers under a time budget (declared approximate).
2. The floor's switch for a non-monotone feature read Stage 2's mark, which saw test labels
   (§4.4, beyond D-030). Fix: `train_statistics._record` decides it on train with
   `is_non_monotone(plain, best, se)`; `train_statistics` no longer takes `stage2`.
   Measured by the audit: on noise the best-order concordance sits 2.5 to 2.8 SE above 0.5.
3. `training.md` lines ~371: at z = 1 about 30% of noise features pass (not one in six), at
   z = 2 about 4 to 6% (not 2.3%): the direction is folded out, so the floor is two-sided.
4. The calibration table's `oof_log_loss` is in sample for the calibrator (beta contains
   Platt contains none, so the order is forced; about 1/(2·n_eff) per parameter). Justified,
   not cross-fitted (a fold subset can separate where the whole does not): the caption, the
   notebook guide and the doc say so.
5. The out-of-fold metric's optimism is stated in the metrics view's caption (done) and gets
   a `note` in `training.json`'s `metrics`. Size, weak evidence (3 replicates): about 0.018
   AUC at 300 train events with 150 noise candidates.
6. `oof` under `negative_downsampling`: `score` is at the true rate, `target` at the sampled
   one. Doc line in "What Training writes" and a "to settle" line for step 3; no new column.
7. With `fold_repeats > 1` the search's loss is over every dealing, the fold models' over
   the first: said in both captions.
8. A deviance metric with an identity-link objective is refused at config load (a new
   cross-field check like Q667's; a default for the EDS's veto).
9. Pruning compared a fit with noise against a refit without: now both without noise (one
   more fold fit when there are candidates).
10. `check_counts` two-sided (also the reviewer's).
11. Hypothesis, to measure: LightGBM picks col-wise or row-wise histograms by timing, which
    could move `model_hash` across machines; if a forced comparison differs, fix
    `force_col_wise` in LightGBM's fixed parameters.

## Defaults to list for veto in review guide 2 (next free number A82; re-read §11 first)
EDA's `edges` table and stage version 5; `stage2/` holding every candidate's ledger row and
EDA's `cells`, `edges`, `bins`, `levels` of the final features; `train_concordance` and
`train_sign` in the per-run ledger; `represented_by` in the selection table; `calibrate`'s
return and `sampling` argument; Training's bootstrap weights from pandas' hash (not Spark's);
`C=1e12` with `newton-cholesky` as the unpenalised logistic regression; separated or constant
out-of-fold margins stop calibration; an anti-predictive Platt or beta fit stops Training
whatever the method, a bad level factor only under `mean`; a ranged parameter without a
default start is refused; the sign-off table one row per feature; EDA's direction compared
for numerics only; the chart changes (`importance_bar` as shares, `dependence` with `lift`
takes group labels, the waterfall on the margin's scale); the run number reserved after the
gate; threads = the machine's cores (an environment field if the bank's node needs a cap);
the row concordance on rows for both tasks; `run.py` at 432 lines (a candidate cut: the
writes); the open spec point on the floor for `non_monotone` features; FLAML's refit on
every row left on (it cannot be switched off under CV); a trial budget below the number of
families refused at Training's start; the trials table's `configuration` as the searched
values only; `run`'s default stage list now including `training`; `check_search` refusing
a trial count off the budget.

## Docs owed at the step's end (beyond the doc-writer's five)
`training.md` (Status; "How one run flows" with the gate before `create_run`; the search's
item 5 (FLAML's refit), item 13 (NaN, any non-finite loss) and the row order; selection's and calibration's refusals; "What Training writes"
with the tables' columns and `training.json`'s keys; the sign-off table; Code map and
Interface with `gate.py`, `tables.py`, `train_statistics.py`), `config.md` (Q667's check),
`architecture.md` Public API (`run_training`), `docs/README.md` map, `UPDATES.md` (status
rows; a log line with "rerun EDA, then Feature Checks"), `glossary.md` if a term is new.

## Gotchas
- Subagents run no Spark and never the full suite; one memory-heavy job at a time
  (`pgrep -fl "pytest|SparkSubmit|synthetic"` first); cap background runs with
  `perl -e 'alarm shift; exec @ARGV' <seconds> <command>`. Never `-x` on a batch whose
  count is reported.
- Four old `ipykernel` processes (pids 28775, 28831, 28833, 28847) are still running: ask
  the EDS to close them before the heavy runs.
- Scripts need `import core_modelling` first (the `np.NaN` shim, T1).
- `conf/local/cc_acquisition.yml` is the EDS's own variant: use `conf/base/` for the build.
- Never prune "What the research found" in `worknotes/m2_3_modelling/questions.md`; do not
  edit `worknotes/sync.md` unless asked.
- Fable's share: the main thread, m2.1, m2.6 and the ML audit only.
