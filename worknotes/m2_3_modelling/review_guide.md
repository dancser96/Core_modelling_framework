# Stage 3 major step 2 (Training): review guide
_Written 2026-11-16 for the EDS · review 1 of step 2 · the plan: `plan.md` beside this file · this
file holds the current review only and is replaced by the next step's guide_

**In short.** Training is built. `run_training` fits one model on the train split and writes it
as a numbered run, for a binary and a regression target, from `run --stages training` or
notebook `04_training`. FLAML searches each listed family on the framework's client folds; the
framework selects the features with three rules, fits the fold models, the calibration and the
final model itself, and writes the bundle, the per-run ledger, the run's own copy of Stage 2 and
the sign-off table. The three reviews found three things that mattered, and each is closed:
- the search could judge one LightGBM constraint method while the kept model used another (a
  parameter set in two places with two precedence rules): now one rule, and every logged trial
  is checked against it;
- under a time budget FLAML can cut a trial's trees, so the judged and the kept model can
  differ: the fold models' loss is now compared with the best trial's, an error under a trial
  budget and a warning under a time budget;
- the floor's switch for a non-monotone feature read EDA's mark, which had seen test labels: it
  is now decided on the train split.

The six questions (Q668–Q673) are answered, all at their default (the EDS, 2026-11-17; the
record is `answers.md`). The ten defaults (A82–A91) and the rest of this guide stay open: the
EDS reviews major steps 2 and 3 together. EDA's stage json is at version
5 with a new `edges` table: rerun EDA, then Feature Checks, once per use case. Everything was
run after the last code edit (2026-11-16); nothing is left to run before your review.

| Run after the last fix round | Result |
|---|---|
| Spark batch | 142 passed, 1 failed; the failure patched a renamed function, the test now patches `training_run.encode_and_select` and passes (127 s) |
| Slow four-family test on `dev` | 4 passed, 4 min 58 s |
| Notebooks `03_feature_checks` (17 code cells), `04_training` (9), `00_modelling_helper` (15) | each executed end to end as a scratch copy against `dev`, no error; the repo's notebooks keep no outputs |
| Canonical data, 15 trials per family | table in §5; no warnings |
| `--stages target_factory eda feature_checks` on the EDS's local data, both example configs | exit 0, no decision recorded |
| Full suite | 1028 passed, 15 deselected (`slow`), 6 warnings (pyspark's `is_categorical_dtype`), 13 min 22 s |

## 1. What to read, in this order
1. **Notebook `notebooks/04_training.ipynb`, its nine guide cells, read as code.** Right looks
   like: a person who has run `03_feature_checks` can train, read each view and iterate without
   opening a doc, and each cell says what to check.
   1. Train: what `run_training` prints, the budget for a first look, and what a failure before
      and after the run number leaves behind.
   2. The feature set in force and the warnings: held, excluded, kept, and each warning with
      what to do.
   3. What the search did: one search per family, a trial, the steps, the winner, the table.
   4. Selection: the three rules in order, `protected`, `undone`.
   5. Calibration and the out-of-fold numbers: the fold models, the methods, the table, the
      offset.
   6. The explanation: the importance bars and the beeswarm.
   7. The sign-off view: its four sections; the sign-off itself is recorded in `05_evaluation`.
   8. The runs so far: `list_runs`, `show_run`, the CLI.
   9. How to iterate: one change as an audit-log entry, train again, compare.

   Then **notebook 03's walk-through** (`notebooks/03_feature_checks.ipynb`, step 9): its last
   cell now undoes the exclude only, so the keep of the three static attributes stays in force
   and notebook 04 trains with them while it shows the look-ahead feature as held.
2. **`docs/components/training.md`, Levels 1 and 2.** Right looks like: the order of a run, the
   function structure and the checks match the code below.
3. **The code, in the order a run calls it** (lines; `training/` and `statistics/` are under
   `src/core_modelling/`):
   - `training/run.py` (432): orchestrates only. `_open_run` holds every refusal that needs no
     fit before `create_run`; the fold-model loss is checked against the search's at one
     dealing; the writes go bundle, per-run ledger, `stage2/`, `training/`, then the `run`
     entry. Over the ~300-line guideline (A87).
   - `training/gate.py` (190): a missing Stage 2 stage is refused naming `run`; `check_counts`
     compares the periods both ways; `save_stage2` writes the copies and `_stage2.json`;
     nothing here runs an upstream stage.
   - `training/train_data.py` (131): the encoder is fitted on train only and applied once, with
     its two refusals; selection runs on the encoded frame; a warning never changes the run.
   - `training/train_statistics.py` (188) and `training/selection.py` (260): the train
     statistics come from the statistics engine on the encoded train frame; `_record` decides
     `non_monotone` on train; the three rules run in order; a kept feature is measured and
     never dropped; pruning's two comparison fits both leave the noise out.
   - `training/search_space.py` (106) and `training/search.py` (425): ranges, starts and
     FLAML's fixed switches as data; `fit_parameters` is the one rule for a configuration's
     parameters; `read_trials` and `check_search` refuse a search that did not run as declared;
     `check_judged_model` closes the loop.
   - `training/fold_models.py` (57): no row is scored by a model fitted on it; the first
     dealing only.
   - `statistics/calibration.py` (167) and `training/calibrate.py` (155): unpenalised fits,
     separation refused, the offset set by the sampling method; every method the task allows is
     fitted and tabled, the chosen one goes to the bundle; losses are taken without the offset.
   - `training/ledger_run.py` (458): the per-run ledger written once and never overwritten; the
     sign-off table one row per feature in four sections; EDA's direction compared for numerics
     only.
   - `training/tables.py` (106): the `oof` table refuses a non-finite score; the explanation
     sample is 5,000 seeded train rows; `train_metrics` carries the optimism `note`.
   - `training/views.py` (347): the captions say what each number is (the out-of-fold metric
     optimistic, the calibration loss in sample, the search over every dealing's folds); an
     empty sign-off section names itself.
   - `reporting/explain_charts.py` (427, under `src/core_modelling/`): each chart from a table,
     at most 1,500 rows per feature, no `shap` import.
   - The Training stage in `src/core_modelling/run.py` (145): `STAGES["training"]` and
     `_run_training_stage`; at `autonomous` the missing EDA and Feature Checks run first, at
     `assisted` the run is refused.
4. **Two tests to read:**
   - `tests/test_search.py::test_the_best_trials_loss_is_the_frameworks_own_fold_loss`: the
     framework's own fold models reproduce the loss FLAML reported for the best trial.
   - `tests/test_training.py::test_a_second_run_repeats_the_model_and_reads_train_only`: two
     runs of one config give one `model_hash` and `recipe_hash`, and the only frame Training
     asks for holds no test row.

## 2. Defaults to veto, by number
Each is explained in `plan.md` §11.

| # | Default |
|---|---|
| A82 | EDA writes an `edges` table (stage json version 5); a run's `stage2/` holds every candidate's ledger row and EDA's `cells`, `edges`, `bins`, `levels` of the final features, with `_stage2.json` naming the versions |
| A83 | Added columns: `train_concordance` and `train_sign` in the per-run ledger, `represented_by` in `selection`, `note` in `training.json`'s `metrics`; the trials' `configuration` holds the searched values only; the sign-off table is one row per feature; EDA's direction is compared for numerics only |
| A84 | Calibration: `calibrate` takes the sampling record and returns the calibration, the table and the warnings; `C=1e12` with `newton-cholesky`; separated or constant margins and an anti-predictive Platt or beta fit stop Training; a bad level factor only under `mean`; bootstrap weights from pandas' hash |
| A85 | The search's signatures as built differ from the plan's m2.1; a budget below the number of families, a trial count off the budget and a range with no start to take are refused |
| A86 | One rule for a configuration's parameters; every logged trial checked against it; the judged-model check; FLAML's refit on every row left on |
| A87 | Every refusal before the run number; `check_counts` both ways; threads = the machine's cores; the module cut (`gate.py`, `train_data.py`, `tables.py`), `run.py` at 432 lines |
| A88 | The `non_monotone` switch decided on train; pruning compares like with like; the floor's optimism on a non-monotone feature stays an open spec point |
| A89 | The concordance is computed on rows for both tasks; the fold loss uses FLAML's definitions |
| A90 | The explanation charts' changes from the prototype |
| A91 | `run` with no `--stages` trains; a deviance metric needs `tweedie` or `poisson` (Q667's refusal of `absolute_error` with a constraint is the EDS's decision) (settled by Q668 and Q669) |

## 3. Questions
All six are answered at their default (the EDS, 2026-11-17; the full text is in
`answers.md`).
- **Q668.** Kept: a deviance metric with an objective other than `tweedie` or `poisson` is
  refused at config load.
- **Q669.** Kept: `run <config>` with no `--stages` trains; the note is in `docs/UPDATES.md`.
- **Q670.** With the 1.0 hardening, in M2.4: fixed once in `write_parquet` for every stage.
- **Q671.** The caption, no cross-fit: the per-method loss is in sample for each calibrator.
- **Q672.** Kept: `xgb_limitdepth` keeps FLAML's own start (§5).
- **Q673.** Kept: `native` stays the default; the cost goes into notebook 04's budget advice.

## 4. What the reviews found, and how each ended
Each minor step had one combined review; the step ended with the code review of the search and
the stage, the ML audit and the compatibility check, then one fix round. The compatibility
check's verdict: nothing released breaks. The audit found no leak at the defaults.

| Finding | Outcome |
|---|---|
| A fixed parameter overrode the space in FLAML's space, the space overrode it in the framework's fits: with LightGBM's `monotone_constraints_method` set in `training.search_space`, every trial ran `basic` and the kept model `intermediate` | Fixed: `fit_parameters`, one rule for both; `read_trials` refuses a trial fitted with other values; a test with that override |
| Under `training.time_budget_s` FLAML cuts LightGBM's and XGBoost's trees at a deadline while its log keeps the configured count | Fixed: `check_judged_model` (an error under a trial budget, the run's warning under a time budget) |
| The floor's switch for a non-monotone numeric read EDA's mark, which saw test labels (`CLAUDE.md` §4.4) | Fixed: decided on train |
| Refusals after `create_run` took a run number: a misspelt name in a family's space, the encoder's refusals | Fixed: before it |
| `check_counts` missed a window period EDA counted that the panel no longer holds | Fixed |
| Pruning compared a fit with the noise columns against a refit without them | Fixed: both without |
| A deviance metric with an identity-link objective stops mid-search | Fixed: refused at config load (Q668) |
| `training.md` gave the floor's pass rate for noise as one in six at z = 1 and 2.3% at z = 2 | Fixed in the doc: about 30% and 4 to 6%; the floor is two-sided |
| The `stage2/` copies did not record which versions they were copied from | Fixed: `_stage2.json` |
| EDA's empty `edges` table had no dtypes | Fixed |
| Small: a missing FLAML log, folds on another index, a non-finite prediction in `row_concordance` | Fixed: each fails loud |
| The out-of-fold metric is optimistic (weak evidence, three replicates: about 0.018 AUC at 300 train events with 150 noise candidates) | Documented, since it is inherent (the features and the configuration were chosen on the same folds): the caption and `note` in `training.json`'s `metrics`; the test split is the first honest number |
| The calibration table's loss is in sample for each calibrator | Documented, since cross-fitting adds a way to fail (Q671): the caption, the notebook, the doc |
| Under `negative_downsampling` the `oof` table's `score` is at the true rate, its rows and `target` at the sampled one | Documented, since Evaluation is its only reader: a doc line and step 3's list; no new column |
| With `training.fold_repeats > 1` the search's loss covers every dealing, the fold models' the first only | Documented, since the two are different quantities by design: both captions; the judged-model check runs at one dealing only |
| All-null columns written to parquet as type `null` | Documented, since the fix belongs in `write_parquet` for every stage at once: a lessons row, a roadmap backlog line, Q670 |
| LightGBM chooses col-wise or row-wise histograms by timing, which could move `model_hash` across machines | Measured: no difference (§5); no change |

## 5. Measured and verified
**The search on `dev`** (m2.8): the shipped card config at `assisted`, 51,040 train rows, 33
final features of 123 in force, 15 trials per family, fold log loss (lower is better). One run
each, so a gap under about 0.0005 is noise. Each cell is the best fold log loss, then the
search's seconds.

| Family | Bounded ranges | Categoricals as codes | FLAML's own ranges |
|---|---|---|---|
| `lgbm` | 0.10878, 11 | 0.10879, 8 | 0.10881, 9 |
| `xgboost` | 0.10868, 11 | 0.10867, 10 | 0.10839, 18 |
| `xgb_limitdepth` | 0.10960, 15 | 0.10925, 14 | 0.10868, 9 |
| `catboost` | 0.10907, 79 | 0.10908, 27 | 0.11206, 58 |

- The bounded ranges lose nothing against FLAML's own for `lgbm` and `xgboost`, win clearly for
  `catboost` (FLAML's own holds 8,192 trees behind early stopping) and trail for
  `xgb_limitdepth` by 0.0009 (Q672).
- Declared categoricals against codes: the same loss in every family; CatBoost three times
  slower declared (79 s against 27 s; Q673).
- The best family's out-of-fold AUC is 0.796 with the three static attributes held; the
  oracle's is 0.83 to 0.86 by window, so nothing beats it.
- At 60 trials: frames 7 s, selection 5 s, the search 117 s (CatBoost 79 of them), the fold
  models 1 s, the final fit and the bundle under 1 s; Target Factory, EDA and Feature Checks
  before it about 105 s together.

**The search on the canonical data** (`conf/base/cc_acquisition.yml`, 15 trials per family,
native categoricals): 257,338 train rows; 123 features in force, 47 held by Feature Checks;
selection left 38 (cluster removed 57, floor 18, pruning 10). Kept model: CatBoost, out-of-fold
log loss 0.11061, out-of-fold concordance 0.806, in-sample 0.818. Seconds per step: frames 12,
selection 15, search 404, fold models 25, final fit 5, tables 2; 664 s with Target Factory, EDA
and Feature Checks before it.

| Family | Search s | s per trial | Longest trial s | Best fold log loss | Best at trial |
|---|---|---|---|---|---|
| `lgbm` | 29 | 1.8 | 2.4 | 0.111004 | 15 |
| `xgboost` | 37 | 2.4 | 3.2 | 0.110806 | 15 |
| `xgb_limitdepth` | 47 | 2.9 | 4.4 | 0.110718 | 15 |
| `catboost` | 284 | 19.1 | 39.6 | 0.110617 | 12 |

Two readings, observations and not decisions: CatBoost takes 70% of the search time; three
families found their best configuration at the last of 15 trials, so 15 trials is a measuring
budget and not a converged search.

**The slow test** (`pytest tests/test_training.py -m slow`; 5 min 19 s before the fix round,
run again after it: 4 passed, 4 min 58 s): each of the four families alone through the whole stage on `dev`, 123 features in force
with declared categoricals and `age` constrained; each kept model's fold loss equals its
search's best to 1e-8, and the bundle's round trip and the constraint's sweep pass inside the
run.

**LightGBM's histogram layout and threads:** identical trees and margins at the automatic,
forced col-wise and forced row-wise layouts and at 1, 2 and 8 threads, on 60,000 × 40,
60,000 × 400 and 4,000 × 12 frames with 300 trees.

**The Spark batch** before the fix round passed: `tests/test_training.py` (10 tests, 2 min
35 s, both tasks' run folders whole) and 122 tests of the frames, EDA, Feature Checks and the
dataset (4 min 51 s). After it: 142 passed, 1 failed, and the failure is fixed (status table
above).

## 6. Not verified, and known limits
- Across machines: the same `model_hash` from the same config (the layout check above was on
  one machine); it is checked at the pre-release run.
- Inside the bank: the model libraries on a Spark executor, plotly in JupyterLab (spike 5's
  trip), Spark reading a parquet column of type `null` (Q670).
- Whether the budgets of 60 and 200 trials converge: the canonical run (§5) used 15 and three
  families were still improving at its last trial.
- Whether FLAML ever draws an integer range's upper bound (its bound is exclusive, so the space
  passes `high + 1`).
- The floor's comparison for a non-monotone numeric: on a noise feature the best-order
  concordance sits 2.5 to 2.8 SE above 0.5, so such a feature tends to pass a floor at z = 2;
  the SE-scaled margin of `is_non_monotone` is the guard today (A88).

## 7. What step 3 starts from
`docs/UPDATES.md`, the plan's "Major step 3: Evaluation" (which opens with what to settle
first, step 2's outputs included), `docs/components/evaluation.md`, `docs/components/training.md`
→ "What Training writes", and the top entry of `worknotes/log.md`. m3.1 and m3.2 can start now;
m3.3 after this review's fixes.
