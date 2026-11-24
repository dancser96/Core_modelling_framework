# Stage 3 major step 2 (Training): review guide
_For the EDS · reworked 2026-11-23 to the state after the audit's fixes · read together with
guide 3 ([`review_guide_3.md`](review_guide_3.md)) · the plan: [`plan.md`](plan.md) · the audit:
[`audit_steps_2_3.md`](audit_steps_2_3.md), your answers in [`audit_answers.md`](audit_answers.md)
· this file holds the current review only_

**In short.** Training is built and the audit of 2026-11-22 is applied to it. `run_training`
fits one model on the train split and writes it as a numbered run, for a binary and a
regression target, from `run --stages training` or notebook `04_training`. What this round
changed in Training:
- **Selection runs in two parts.** The cluster rule and the floor fit no model and run before
  the run number; pruning runs after it.
- **The floor reads the null pattern too.** A feature passes on its value's concordance or on
  its null indicator's; one null pattern clears one feature.
- **Pruning has its own model size,** so a noise column always gets its turn. Its undo check
  was found wrong during this round and corrected.
- **The kept model is checked on every dealing** of the folds, and the check is recorded.
- **A run folder is a contract.** One function opens it and checks every key, table and column
  a later stage reads, before any Spark work. The `stage2/` copy has its own version.
- **More is refused before the run number,** and nothing a later stage needs can surface as a
  bare error after the Spark work.

No review found a leak or a split or time violation. The package is 0.5.0 and nothing is
committed.

| Run after the last code edit | Result |
|---|---|
| Spark batch over Training, Evaluation, the card, compare, runs, the golden run and the acceptance tests | 678 passed, 3 failed; the three were one new test asking for one trial per family, which found A140; rerun: 4 passed |
| Full suite with the slow tests | 1343 passed, none failed, 32 min 36 s (`-m "slow or not slow"`). After it, two small edits (a docstring wrap in `training/search.py`, the per-stage wording of the missing-`run`-entry message in `config/audit_log.py`); their test files rerun: 105 passed |
| Canonical data, Training and Evaluation | exit 0: 50 final features, CatBoost kept, out-of-fold log loss 0.110528; test AUC 0.805, validation 0.800; Training 586 s and Evaluation 125 s by their own laps (§6) |
| Notebooks `04_training`, `05_evaluation`, `00_modelling_helper` as scratch copies | each executed end to end on the `dev` preset (its own data root, two trials per family): 9 of 9, 17 of 17 and 16 of 16 code cells, no error; the repo's notebooks keep no outputs |
| `ruff check .` and the format check | pass |

## 1. Decide first: the defaults this round took without asking
The build never stopped for a question. Numbered so you can veto by number, most consequential
first. A82 to A91 of the first build follow in §3.

**These change what a run does or what you decided before**
- **A136 The version is 0.5.0, and six formats moved.** `training.json` and `evaluation.json`
  are schema version 2, the per-run ledger 2, the model card 2, the drift reference 2, and the
  `stage2/` copy has its own version 1. A run trained before this round is refused by name:
  train it again. The compatibility check asked for a minor bump because a public signature
  and stored formats changed, and artifacts before and after would otherwise both say 0.4.0.
  *Alternative:* 0.4.1.
- **A137 The pruning model is sized at about ten offers per column** (Q690), not "about twice"
  as Q677 worded it: 4 leaves, three columns a tree, ⌈10 · P / 3⌉ trees. At two to three offers
  a weak column was still crowded out. With this size the best noise share was 0 in none of 31
  simulated cases, so the fallback you did not love (a share of 0 prunes nothing and warns) is
  a safety net. Report: [`pruning_noise_share.md`](pruning_noise_share.md).
- **A138 The undo check is kept, corrected and capped** (Q692). As first built in this round it
  compared two fits that drew different columns per tree, so chance decided: a pure-noise
  candidate was "undone" in a real-data test. Both comparison fits now offer every column to
  every tree, at the yardstick's tree count and at most 300. It judges the candidates as a set.
  On the `dev` preset it undid every pruning in the three acceptance runs (5, 14 and 5
  candidates of 37 or 38), although the final model then gave several of them no split. Read
  with suspicion; dropping the check is the alternative.
- **A139 The floor on nulls, as the ML audit corrected it.** The audit's item 4 was built as
  proposed (a feature passes on its null indicator's concordance too) and then found defective
  in two ways. The indicator's standard error ignored ties, so the test was dead at a rare null
  share: it is now multiplied by √(3p(1 − p)), p the null share. And one shared pattern cleared
  every feature that carried it: on the synthetic data "fewer than six months on the book"
  passed ten rollups whatever their values. Now the features whose nulls fall on the same train
  rows form a group, and a pattern clears one feature (none when a member already passed on its
  value); the rest are dropped with `represented_by`. On `dev`: 37 features pass the floor, 4
  of them on nulls (before: 45 and 12), 8 are dropped as represented.
- **A140 A family needs at least two trials.** On one trial FLAML runs no search (it fits the
  start configuration and judges nothing), so Training failed after the run number with "logged
  no trial". `split_budget` now refuses it before the number, naming the families. Found by a
  test written in this round.
- **A141 The selection's screen runs before the run number,** with the new refusals: a feature
  named like a noise column or a derived column, a `tweedie` or `poisson` objective on a
  negative target, a fold whose target takes one value. A screen that leaves no feature takes
  no number.

**Contracts and formats**
- **A142 The run folder is read through one contract check.** `open_run_folder`
  (`run_artifacts.py`) reads `run.json`, the bundle, `training.json`, the per-run ledger and
  the `stage2/` copy once and checks the keys, nested keys, tables and columns a later stage
  reads; table columns come from the parquet footers. Evaluation, `compare_runs` and
  `check_card_inputs` go through it.
- **A143 The `stage2/` copy has its own version and frozen columns.** The EDA and ledger
  versions it records are provenance, never checked, so an EDA bump leaves earlier runs
  readable. The copy's `bins` and `levels` drop regression's extra group columns, which nothing
  reads.
- **A144 No stored run folder until 1.0** (the EDS, 2026-11-24, replacing the golden run folder
  built for item 25). The contract and its 18 damage cases run on the run the suite writes
  (`tests/test_run_contract.py`); a frozen folder per format version, with the writers'
  format test, comes from 1.0's first run in the bank (roadmap backlog).
- **A145 Public surface.** `list_runs(cfg, entity, env)` and `show_run(cfg, entity, env, run)`
  take the stages' argument order, with no deprecation path (0.x). `find_run` returns the newer
  runs it passed over. `core_modelling.model` exports `Bundle`, `load_bundle` and `score_frame`
  only. `run`'s default stages are the explicit `DEFAULT_STAGES`, frozen from 1.0.

**Layout and smaller ones**
- **A146 Where things live now.** `run_artifacts.py` (the readers, the shared names, the
  contract); `reporting/training_views.py` (the former `training/views.py`, whole);
  `training/signoff.py`, `training/automl.py` (the FLAML plumbing), `training/run_bundle.py`
  (the bundle step); `missing_stage2` in `ledger.py`, `split_budget` in `config/schema.py`.
  Nothing outside `training/` imports from it; two tests enforce it.
- **A147 `threads` in the environment file** (null: every core). It is a strict positive
  integer, and since the environment schema refuses unknown keys, a use case pinned to an
  earlier version refuses a file that sets it. `training.json` records the thread count and the
  versions of FLAML, the three model libraries, numpy and scikit-learn.
- **A148 The judged-model check runs on every dealing,** at (R − 1) · K more fits when
  `fold_repeats` is above 1, and writes `judged_model` into `training.json`.
- **A149 Training's and Evaluation's `run` entries retry a lost sequence number** up to five
  times; Feature Checks' does not, on purpose (D-088 (identities)).
- **A150 Left as they are, with the reason.** `score_spark` reads the bundle again, since it
  must verify the very bytes it ships. `tail_start` stays a per-task entry though both tasks
  hold 0.99 (item 51 named it). A truncated stage json still stops `list_runs`: it fails naming
  the file, and a stage folder is swapped in whole, so it means outside damage.

## 2. Questions
Each has a default, taken and built unless you say otherwise.
- **Q687 to Q689** (hashes): [`hashes_and_compatibility.md`](hashes_and_compatibility.md).
  Hash set fields only; a version per hash family; pin the seeded draws. *Defaults:* the first
  two with the 1.0 hardening, the third before the December move (OD-29).
- **Q690** (the pruning size) and **Q691** (a follow-up on the threshold): A137; *default* for
  Q691: not now.
- **Q692. The undo check: keep it, or drop it?** Corrected, it fired in none of 31 simulated
  cases and caught nothing real in the ones built to test it; on `dev` it undid every pruning.
  *Default:* keep, capped at 300 trees (A138).
- **Q693. A tie-corrected standard error for every concordance?** The correction of A139 was
  applied to the null indicator only. A 0/1 flag's own concordance has the same too-large
  standard error, in the floor and in EDA's and Feature Checks' statistics, so a real flag is
  judged too strictly. *Default:* not now; it changes Stage 2's numbers and its stage versions,
  so it is a decision of its own.

## 3. The first build's defaults, A82 to A91
As in `plan.md` §11, still open to veto. This round changed four of them:
- **A82** (the `stage2/` copy): now with its own version and frozen columns (A143).
- **A83** (added columns): plus `floor_cleared_by` in the per-run ledger, `cleared_by` in
  `selection`, `score_in_sample` in `oof`, `target_min` and `target_max` in the folds table;
  the calibration table's `oof_log_loss` is `oof_loss`.
- **A86** (the judged-model check): on every dealing (A148).
- **A87** (every refusal before the run number; threads): the screen too (A141); the thread
  count comes from the environment file (A147); `training/run.py` is 386 lines.
- **A88** (pruning compares like with like): replaced by A137 and A138.

## 4. What to read, in this order
1. **Notebook `notebooks/04_training.ipynb`, its guide cells, read as code** (20 cells, 9 of
   them code). Right looks like: a person who has run `03_feature_checks` can train, read each
   view and iterate without opening a doc. New in this round: the run order (screen, number,
   pruning), the refusals before the number, `threads`, the warnings (a final feature without a
   split, pruning that compared nothing with noise), the floor's `cleared_by`, `oof_loss`, the
   `unreadable` column of the runs.
2. **`docs/components/training.md`, Levels 1 and 2,** then "Selection" in full: the floor's
   two tests and the null-pattern rule, "The pruning, step by step" and "Why this size".
3. **The code, in the order a run calls it** (lines; under `src/core_modelling/`):
   - `training/run.py` (386): orchestrates only. `_open_run` holds every refusal that needs no
     model before `create_run`.
   - `training/gate.py` (259): the Stage 2 gate, `check_stage2_columns`, the name and target
     refusals, `save_stage2` writing the frozen columns.
   - `training/train_data.py` (179): `encode_and_screen` before the number, `finish_selection`
     after it; a warning never changes the run.
   - `training/train_statistics.py` (238) and `training/selection.py` (365): the floor
     (`apply_floor`, `_null_carriers`) and pruning (`prune_by_importance`,
     `_pruning_configuration`, `_comparison_configuration`). **With suspicion:** the group rule
     in `_null_carriers` (exactly equal null masks only), and the undo's "any rise".
   - `training/search_space.py` (115), `training/automl.py` (239), `training/search.py` (226):
     the space as data, FLAML's plumbing, `check_search` and `check_judged_model`.
   - `training/fold_models.py` (157): `every_dealing_loss`; no row scored by a model fitted on
     it.
   - `statistics/calibration.py` (173), `model/calibration.py` (143), `training/calibrate.py`
     (142): `check_order_kept` on every fitted method, a non-finite parameter refused.
   - `training/run_bundle.py` (95): the bundle written, loaded back and checked against the
     model in memory.
   - `training/ledger_run.py` (334), `training/signoff.py` (136), `training/tables.py` (103).
   - `run_artifacts.py` (306): the contract as plain data, `open_run_folder`,
     `read_stage2_copy`. **Right:** every key a later stage indexes is in a list here.
   - `runs.py` (477): `_readable_record` is the one reader of `run.json`; `find_run`,
     `list_runs`.
4. **Two tests to read:**
   - `tests/test_selection.py::test_a_shared_null_pattern_clears_one_feature_not_all`.
   - `tests/test_selection.py::test_a_pure_noise_candidate_is_dropped_not_undone`: the test
     that found the undo check's defect.

## 5. What the reviews found, and how each ended
Five reviews ran on the merged state: two code reviews, the silent-failure audit and the
compatibility check on Opus, the ML audit on Fable. None had a blocking finding.

| Finding | Outcome |
|---|---|
| The undo check compared two fits that drew different columns per tree (a new real-data test) | Fixed: every column offered; measured again (A138) |
| One null pattern cleared every feature sharing it; the null indicator's SE ignored ties (ML audit) | Fixed (A139) |
| Training's and Evaluation's stage formats changed under an unchanged `schema_version` (compatibility) | Fixed: both 2. The guard against a repeat, a stored folder per format version, waits for 1.0 (A136, A144) |
| A budget of one trial per family failed late (a new test) | Fixed: refused before the run number (A140) |
| A truncated `run.json`, `_stage2.json`, sidecar or stage json gave a bare JSON error | Fixed: `artifacts.read_json` names the file and what to do |
| Killed between the two renames of a stage swap, the message told the user to remove the only copy | Fixed: an `.old-…` folder without its target is named as the committed one |
| `check_order_kept` let a NaN parameter through | Fixed |
| Three readers of `run.json`, two copies of the sign-off and calibration column lists | Fixed: one each |
| `training/run.py` held the bundle step; `search_families` was 60 lines | Fixed: `run_bundle.py`, `_search_one` |
| The undo check judges the candidates as a set (ML audit, measured) | Declared: `training.md`, the pruning report, Q692 |
| The cluster rule picks its representative on the value only, so a member that would pass on nulls is lost when the representative fails | Declared: an open point in `training.md` |
| The first build's findings (one parameter rule, the judged-model check, the switch on train, the refusals before the number) | Closed on 2026-11-16; unchanged |

## 6. Measured and verified
**The acceptance runs on `dev` after the fix round** (three runs, 123 features in force):

| | Plain | Downsampled | With a leak kept |
|---|---|---|---|
| Pass the floor (value / best order / nulls) | 37 (32 / 1 / 4) | 37 (32 / 1 / 4) | 38 (33 / 1 / 4) |
| Dropped as represented by a shared null pattern | 8 | 8 | 8 |
| Pruning: nominated, outcome | 5, undone | 5, undone | 14, undone |
| Selection, seconds | 4.0 | 2.2 | 4.1 |
| Judged-model check | agrees | agrees | agrees |

The four that pass on nulls: `loan_personal_maturity_months`, `days_since_last_login_digital`
and two ratio features. On the notebook's `dev` run the comparison's log loss was 0.109218 with
the 5 candidates and 0.109399 without.

**The canonical data** (`conf/base/cc_acquisition.yml` with 15 trials per family, a scratch
data root, 2026-11-23): 257,338 train rows; 123 features in force, 47 held by Feature Checks.
- **Selection left 50** (38 before this round): the cluster rule removed 57, the floor 16, two
  of those as represented by a shared null pattern. Of the 50 that pass the floor, 46 pass on
  the value, 2 on the best order and 2 on their nulls. Pruning nominated 8 at a threshold of
  0.0045 and the undo kept them: the comparison's log loss was 0.110852 with them and 0.110901
  without, a rise in the fifth decimal (A138, Q692). The final model gave 2 of the 50 no split.
- **Kept model:** CatBoost, out-of-fold log loss 0.110528 (0.110617 before), out-of-fold
  concordance 0.806, in-sample 0.820; the judged-model check agrees to the last digit.
- **Seconds per step:** frames 20, selection 16, search 482, fold models 51, final fit 15;
  586 in all (463 before, with 38 features).

| Family | Search s | Best fold log loss | Best at trial |
|---|---|---|---|
| `lgbm` | 34 | 0.110946 | 15 |
| `xgboost` | 52 | 0.110755 | 15 |
| `xgb_limitdepth` | 53 | 0.110624 | 15 |
| `catboost` | 329 | 0.110528 | 14 |

- **Evaluation of that run** (125 s: scoring 11, tables 69, explanation 45): test log loss
  0.1087 (0.1052 to 0.1138), AUC 0.805 (0.791 to 0.816), observed to expected 0.97 (0.93 to
  1.03); validation log loss 0.1123, AUC 0.800, observed to expected 1.00; validation on test
  clients only, AUC 0.790. The top 1% holds 13% of the conversions on test and on validation
  (a lift of 13.5 and 13.2). No warning; permutation importance ran on 50,000 rows.
- The wall-clock of the whole command is not a measurement: the machine slept during
  Evaluation, and the stages' laps do not count sleep.

**Pruning on simulated frames:** [`pruning_noise_share.md`](pruning_noise_share.md) §3 to §6.

**Threads:** each family's saved model was byte-identical at 1, 2, 4 and 8 threads on the
development machine (the ML audit's run, numeric columns).

**The search tables of the first build** (`dev` and the canonical data, measured 2026-11-16)
are not repeated: selection now leaves other features, so their losses and seconds are no
longer the current ones. The readings stand: the bounded ranges lose nothing against FLAML's
own for `lgbm` and `xgboost`, CatBoost takes most of the search time, and 15 trials per family
is a measuring budget, not a converged search.

## 7. Not verified, and known limits
- The pruning measurements use one seed per case and independent features.
- The floor's false-pass rate was simulated before A139's two corrections, not after.
- Across machines: the same `model_hash` from the same config; with categoricals and on the
  bank's hardware, the same model at two thread counts (the bank-trip list in
  `docs/roadmap.md`).
- Inside the bank: the model libraries and `core_modelling` on a Spark executor, plotly in
  JupyterLab, a read-only home at first import.
- Whether the budgets of 60 and 200 trials converge.
- The floor's comparison for a non-monotone numeric (the first build's open point, unchanged).
- On a narrow frame pruning nominates many features and the undo keeps them: on `dev` it
  changed nothing in three runs. Whether that is the behaviour you want is Q692.
