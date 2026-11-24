# Training
**Status:** built 2026-11-16 (M2.3 major step 2; the spec settled 2026-11-13); the audit of
2026-11-22 applied 2026-11-23; the EDS's joint review of Training and Evaluation is open ·
**Legacy:** `src/run.py`, `src/dataset.py`, `src/calibration.py`, `src/contract.py`
**Related:** [model bundle](model_bundle.md) (the run folder, the bundle, the encoder, the
calibration's shape, the hashes) · [config](config.md#the-modelling-fields-stage-3) (every field
and default) · [dataset](dataset.md) (the train frame and its folds) · [feature
ledger](feature_ledger.md) (the per-run part) · [feature checks](feature_checks.md) (the hold-out
rule) · [EDA](eda.md) · [evaluation](evaluation.md) (reads the run) · [lifecycle](lifecycle.md) ·
[reporting](reporting.md) · D-020, D-030, D-031, D-037, D-049, D-051, D-052, D-083, D-094, D-100,
D-106, D-117, D-125, D-134, D-139, D-140

Read it in three levels: Level 1 gives the essentials, Level 2 how the parts connect, Level 3
every detail.

## Level 1: Summary
Training fits one model on the **train split** of the observation window from the vetted feature
set and writes it as a numbered **run**, `<use_case>/06_models/r007/`: the bundle, the per-run
ledger, its own copy of what it needs from Stage 2 and the `training/` folder ([model
bundle](model_bundle.md#the-run-folder)). It stands alone because it is where labels choose:
features, configuration and calibration are chosen on train clients only (`CLAUDE.md` §4.4), so
Training never sees a test or validation row and Evaluation can be rerun without it. It writes
artifacts only; the model results report is Evaluation's (D-036).

- **In:** the resolved config, EDA's and Feature Checks' artifacts of the same data definition,
  the train frame with its client folds. **Out:** the run folder and a `run` entry in the audit log.
- **Key numbers:** four families (`lgbm`, `xgboost`, `xgb_limitdepth`, `catboost`); 60 trials at
  `autonomous` and 200 at `assisted`, one search per family on an equal share; 5 client folds;
  three selection rules (the cluster rule, a floor at 0.5 + 2 SE on the value's or the nulls'
  concordance, importance pruning against five noise columns); calibration by Platt on the
  margin or beta for binary and a level factor for Tweedie and Poisson, with the prior-shift
  offset whenever sampling happened.
- **Run it:** `run_training(cfg, entity, env, spark)`, `python -m core_modelling run <config>
  --stages training` (or no `--stages`: the default, `DEFAULT_STAGES`, includes Training),
  or notebook `04_training.ipynb`. Each call trains a new numbered run. Sign off with `decide
  --sign-off --run r007 --reason …`.

## Level 2: How it fits together

### What drives what
- **The decision sets the yardstick.** `decision.type` (or `decision.metric`) gives the search
  metric, which is also the headline metric, and the binary calibration method. It is declared
  before any result and no audit-log entry changes it (`CLAUDE.md` §4.3); the training settings
  can be changed through the log and rerun from Training (D-140 (d)).
- **Stage 2 sets the feature set.** `resolve_features` gives candidates − lineage − unsupported
  − excluded − held; an open flag holds a feature out (D-134), a `keep` protects it from the
  automated rules, and a person signs off the final list after training (D-031).
- **One fold assignment serves every out-of-fold number:** the search's trials, importance
  pruning, the fold models and the calibration all use the dataset's client folds (D-106). The
  search averages every dealing; the other out-of-fold numbers read the first.
- **FLAML only searches.** The framework's own `fit` trains every model it keeps, through
  `FAMILIES`, from the best configuration (D-140 (a)), so the bundle holds one native booster and
  a production retrain needs no FLAML.
- **The encoder comes first.** Every code is fixed before any library sees the frame, and
  FLAML's own transformer is switched off (T38; the encoder is [model
  bundle](model_bundle.md#the-encoder)'s).
- **Training writes, Evaluation reads.** Evaluation, the card and the sign-off view read only the
  run folder and the data (D-139 (b)), through the run folder's contract in `run_artifacts.py`
  ([model bundle](model_bundle.md#the-run-folders-contract)), so reading a run needs neither
  FLAML nor Training's code.
- **The automation level acts in `run` only.** `run` at `autonomous` runs the missing upstream
  stages first; `run_training` itself trains or refuses, at both levels.

### How one run flows
Every refusal that needs no model comes before the run number, so a refused run takes none.
1. Open the run, refusing as it goes:
   1. resolve the config; check every listed family's search space and the trial budget;
   2. pass the gate (EDA and Feature Checks of the same data definition, their tables holding
      every column the run's `stage2/` copy keeps); take the feature set in force, refusing a
      feature named like a noise column or a derived column;
   3. collect the train frame with its folds (a fold whose target takes one value is refused);
      check the panel's counts and kinds against EDA's;
   4. fit the encoder on train: a constraint on an unordered categorical, or a train level
      `features.order` does not list, is refused here; so is a target below 0 under `tweedie`
      or `poisson`;
   5. encode the frame once and screen it (`encode_and_screen`): the train statistics, the
      cluster rule and the floor, which fit no model; a screen that leaves no feature is refused.
2. `create_run` reserves the next number and writes `run.json`; the feature set in force is
   printed with the warnings so far.
3. Prune by importance, the one selection rule that fits models (`finish_selection`); the drop
   is undone when two comparison fits, which offer every column to every tree on at most 300
   trees, lose more without the candidates than with them.
4. Run one search per family on its budget and check each; take the best family and
   configuration by the fold loss.
5. Fit the K fold models at that configuration: the out-of-fold margins and contributions. Fit
   the further dealings' fold models too and check the mean loss over every dealing against the
   search's; then the calibration.
6. Fit the final model on every train row; write the bundle, self-check it and run the
   monotone grid check on the reloaded bundle (`write_run_bundle`).
7. Write the per-run ledger (a constraint against EDA's direction, or a final feature without a
   split, warns here) and `stage2/`; build the tables, `training.json`'s content and the views.
8. Write `training/` last, the commit marker, then the `run` entry.

The `run` entry point adds one step before all of this: at `autonomous` it runs a missing EDA or
Feature Checks first ([the gate](#the-gate), item 5).

### Function structure
`src/core_modelling/training/`:
- `search_space.py`: the ranges, starts, constants and FLAML's fixed switches as data, and the
  one parameter rule; `search.py`: the search's contract (one search per family on its budget,
  its checks, the best family, the judged-model check); `automl.py`: FLAML's side (the
  splitter, the space and settings, the metric, the frame each family gets, the log read back);
- `gate.py`: the gate, the feature set in force, the name, count, kind and target checks, the
  `stage2/` copy's write;
- `train_data.py`: the encoder fitted on train, the frame encoded and screened before the run
  number, selection finished after it; `train_statistics.py`: the train-split statistics;
  `selection.py`: the three rules;
- `fold_models.py` (the fold models of every dealing, the final model) and `calibrate.py`;
  `run_bundle.py`: the bundle written, reloaded and checked;
- `ledger_run.py`: the per-run ledger and its warnings; `signoff.py`: the sign-off table;
  `tables.py`: the `oof` table, the explanation sample, the train-side metrics;
- `run.py`: `run_training`, which orchestrates only.

Outside the package: `run_artifacts.py` holds the run folder's readers and the names both sides
share, and `reporting/training_views.py` the report blocks. Training also uses
`statistics/calibration.py` (Platt, beta, the offset, the level factor), `statistics/losses.py`
(the decision's metric as a loss, the row concordance), `reporting/explain_charts.py`, `model/`
(the encoder, the families, the bundle, its self-check), `runs.py`, `dataset/folds.py`,
`ledger.py` and `artifacts.py`.

### How it is checked
Light tests (`CLAUDE.md` §7), constructed frames without Spark wherever pandas suffices:
- **The invariants:** the frames Training asks for hold no test row; no fold row is in the frame
  its fold model was fitted on; a held feature is refused; the offset is zero without sampling.
- **The search:** the exact trial count per family, with a remainder and with `training.trials`;
  a bad space, or a budget that leaves a family fewer than two trials, refused before any work; every ranged leaf reaches FLAML with a start; a
  search that did not move fails; every trial is fitted on our folds, unshuffled; a constraint
  method named in the space reaches the trials and the framework's fits alike; the best trial's
  loss is the framework's own fold loss, also over two dealings, and a kept model the search did
  not judge is refused; a fold the metric is not defined on stops the search.
- **Selection:** the rules' order; the floor on the best order for a feature judged non-monotone
  on train; a feature whose nulls predict the target passes the floor, also at a rare null
  share on the tie-corrected SE, and a NaN statistic never does; a null pattern shared by
  several features clears one of them, and none when a member passes on its value; a kept
  feature measured and never dropped; on a wide frame pruning compares with noise
  and keeps every real feature; a best noise share of 0 prunes nothing and warns; pruning undone
  when the loss of the two comparison fits (every column offered to every tree, no noise
  column) rises without the candidates, and a pure-noise candidate dropped; the comparison's
  tree count capped; no noise column leaves the function.
- **The refusals before the number:** a family's trial budget below two, a feature named like a
  noise column or a derived column, a
  negative target under a log link, a fold whose target takes one value, a Stage 2 table
  without a column the `stage2/` copy keeps; a screen that leaves no feature takes no run
  number.
- **The run folder:** a folder Training wrote meets the run folder's contract, and one whose
  `training.json` lacks a nested key is refused by name; the `stage2/` copy reads back, and a
  copy of another version is refused.
- **Calibration:** separated margins and an anti-predictive model stop Training; a fit the
  bundle's rule refuses stops it too; the offset follows the method of sampling.
- **The run:** the run folder holds every artifact; two runs give one `model_hash` and the frame
  asked for is train only; no held feature enters; the `run` entry has no periods; a crash after
  the number is reserved leaves a run listed as incomplete; `run` at `autonomous` runs the
  missing stages and refuses at `assisted`.
- **On `dev`** (marked `slow`): each family alone through the whole stage, with declared
  categoricals and a constraint, its kept model's fold loss equal to its search's best. Not
  built yet: the calibration level within 10% with and without `negative_downsampling`.

## Level 3: Details

### Requirements and design constraints
1. **Train only** (`CLAUDE.md` §4.4): Training reads the train split and nothing else; every
   choice (features, configuration, calibration) is made on train clients. Test and validation
   never reach it.
2. **The engine sees only the vetted feature set** (§4.5); validation runs outside it.
3. **Task-agnostic shapes** (D-050): one flow for binary and regression; what differs (metric,
   objective, calibration method, folds) comes from the per-task spec in `tasks.py`.
4. **Fail loud, no fallbacks:** no hidden retry, no silent default. A warning never changes what
   the run does.
5. **Reproducible:** a trial budget and `training.seed` give the same trials, model and
   `model_hash` on the same machine and library versions (D-094 (d)).
6. **Single node:** the train frame is collected and trained in pandas ([dataset](dataset.md));
   a Spark-native engine would be another entry behind `FAMILIES`, not built in Phase 2.
7. **One model interface:** plain functions per family behind `FAMILIES` (D-037, D-100 (a)); a
   `Protocol` may wrap them when the predefined path arrives (`CLAUDE.md` §1 rule 2).
8. **No refit in the sandpit** (D-052): the evaluated model is the one registered. The recipe in
   the bundle is what a production retrain repeats; its check against the evaluated parent is
   [lifecycle](lifecycle.md)'s.

### The gate
1. **Data knowledge first** (§4.13, D-031): Training refuses to run unless EDA and Feature Checks
   artifacts exist for the same data-definition hash, their settings digests match the current
   resolved config and their sources' digests the environment file (`check_upstream`: a source
   pointed at another path or table is other data). The ledger is read with both stages' run
   tokens (`read_ledger(…, expect={"eda": …, "feature_checks": …})`). The ledger and EDA's
   `cells`, `edges`, `bins` and `levels` must hold every column the run's `stage2/` copy keeps
   (`check_stage2_columns`, [what Training writes](#what-training-writes)), else the gate
   refuses before the run number and names the table and the columns.
2. **The counts:** Training recomputes the per-period `eligible_rows`, `known_target` and
   `positive_rows` on every client in the window, before the client split, and fails loud when
   they differ from EDA's population table in `eda.json` (D-088). The check runs both ways: a
   window period EDA counted that the panel no longer holds is refused too, as is a period EDA
   did not count. It compares the kinds in the ledger with the panel's schema and fails loud on
   a changed type.
3. **The feature set in force:** `resolve_features(ledger, resolved)`, passed to
   `build_frames(…, "training", features=…)`, which refuses a held or excluded name
   ([dataset](dataset.md#frames-d-030-d-131-d-135)). For Training a held feature is an excluded
   feature without a final decision, and the log says so in those words.
4. **Training opens**, in the notebook and in the run's log at both levels, with the resolved
   config's choices and the feature set in force: the held, excluded and kept features with the
   audit-log entries that set them, beside the count Feature Checks' run held
   (`feature_checks.json` → `held`). When fewer are held now (a `revert` undid that run's flags),
   a warning says so and that `rerun feature_checks` restores them. It never refuses for that: a
   revert is a person's explicit act, and at `autonomous` Feature Checks runs right before
   Training.
5. **The automation level** (D-132): the rule lives in `run`, not in `run_training`. At
   `autonomous`, `run` runs EDA and then Feature Checks when their artifacts are missing
   (`missing_stage2`, looked up again after each, since an EDA run removes Feature Checks'
   folder) and then Training. Stale artifacts are not missing: they are refused at both levels.
   `run_training` called alone fails loud at both levels, naming `run` as the fix. A person can
   stop between stages at either level and
   record `keep` or `exclude` entries; those change the resolved input, not the data definition,
   so EDA and Feature Checks stay valid.

### The frame and the folds
1. `build_frames(…, "training")` returns train only, collected, with the keys, the features,
   `target`, `split` and the fold columns `cv_fold` (and `cv_fold_2`, … under
   `training.fold_repeats`); the dataset owns how folds are dealt
   ([dataset](dataset.md)). The folds are dealt on the train rows as trained, after
   `training.sampling`, so the balance of converting clients holds on what the model sees; under
   `negative_downsampling` every converting client stays and keeps its fold.
2. Rows with a null target are dropped as the frames do; the share is reported per period, and
   the scores read as conditional on staying.
3. Contract checks run on the true population before any sampling (§4.8); sampling happens only
   when the config declares it, on the train split after the client split (§4.12, D-117).
4. `check_folds` (run by `build_frames` before the collect) fails loud when a fold holds no train
   row or, for binary, no positive event, which happens only with fewer clients or converting
   clients than folds. It also fails loud on a fold whose targets take one value (the folds
   table's `target_min` equals its `target_max`): no metric can tell trials apart there, and a
   regression's concordance or r2 is not defined. A zero-inflated amount with very few non-zero
   train clients can meet this refusal: a fold may then hold zeros only.
5. Below 100 converting clients or 200 events in the train split the log warns: the fold metric
   is noisy at this size (about ±0.06 AUC per fold at 20 events); set `fold_repeats: 3`, keep
   the trial budget small, and read differences between runs against their intervals. It never
   advises fewer folds, which bias the estimate down and buy no precision [Kohavi95]. The
   sentence is the task's `few_events_warning` entry of `TASK_SPECS`, which EDA's window warning
   also uses; a regression counts the clients and rows with a non-zero target.

### The encoder and the families
The encoder's codes, the four families' functions, their formats and the loader's pins are
[model bundle](model_bundle.md#the-encoder)'s. What Training decides:
1. **The kinds:** each feature's kind is the ledger's `kind` (EDA's, after `features.kinds`); a
   categorical named in `features.order` is `ordered`, every other categorical `unordered`.
   `features.order` is filtered to the features being encoded, and the bundle's encoder holds the
   final features only.
2. **Fitted on train only,** once, before selection; every later fit and every scoring uses the
   same codes. Levels are kept at `training.categoricals.min_level_client_count` distinct train
   clients, counted after `training.sampling`: under `negative_downsampling` on the clients the
   sampling left. `training.categoricals.unordered` passes the codes declared (`native`) or as
   numbers (`codes`). `native` stays the default though it makes CatBoost's search several times
   slower: 79 s against 27 s for 15 trials on `dev`, for the same fold loss, and 329 s of a
   482 s search on the canonical data (22 s per trial against 2 to 4 s for the other three
   families). Notebook 04's budget advice says so.
3. **The families searched** are `training.estimator_list` (all four by default; one entry fixes
   the family). `fixed_params` gives the constants the search and the fit must share: the
   objective, the declared categoricals, the constraints in the library's form, LightGBM's
   `basic` method, CatBoost's `allow_writing_files=False` (T5).
4. **A warning** when a constrained final feature has nulls and `catboost` is listed: CatBoost
   counts a null as the smallest value, inside the constraint (a correct constraint cost it
   0.011 AUC on a feature with 10% nulls, measured). CatBoost's fold loss carries the cost.
5. **The frame's column order is checked before every fit.** The constraints and XGBoost's
   feature types are positional vectors in the encoder's order, and a frame in another order
   trains with the constraint on the wrong feature, without a word. So every fit, the search's
   included, receives the frame `encode_frame` returned, and Training runs `check_order` on it
   before the screen and after each of its rules, before each pruning fit, and once on the final
   features' frame, which the search and every later fit take. The pruning frame, which holds
   five noise columns, is checked against an encoder extended by them. As a backstop every
   family's `fit` refuses a positional vector whose length is not the frame's column count.
6. **Every parameter name is checked before the run number is taken** (`check_spaces`, through
   `check_params` and `check_searched`): LightGBM and XGBoost ignore a misspelt parameter
   silently once their logging is off, so a name outside the family's allowed set fails loud,
   and so does a name the framework sets itself; `fit` checks the names again on every fit.
7. **What reaches FLAML how** (measured on the pinned versions): the objective, the seed and the
   constraints pass as search-space constants; LightGBM's `categorical_feature` and CatBoost's
   `use_best_model` only as fit arguments; the thread count only through `AutoML.fit(n_jobs=)`.
   FLAML's CatBoost wrapper declares categoricals only from pandas `category` columns and passes
   `cat_features=[]` itself, while LightGBM and XGBoost need the integer codes, so the search
   gets one frame per family (`SEARCH_FRAMES`); a `category` column gives CatBoost a model
   bit-identical to the integer codes.

### The search
1. **FLAML only searches** (D-140 (a)); the best configuration is refitted by the framework.
   - **One rule gives a configuration's parameters** (`fit_parameters`), to FLAML's trials and
     to every framework fit alike (pruning, the fold models, the final model): the family's
     fixed parameters, the space's values over them (a constant, or a ranged leaf's start),
     then the searched values. The space wins over a fixed parameter: LightGBM's constraint
     method is the one fixed name a config may set (`{value: intermediate}`).
   - **A trial fitted with other parameters is refused.** Every logged trial's values outside
     the searched ones must be the constants the framework fits with (a None constant left
     out, as FLAML leaves it out); otherwise the search judged another model than the one that
     is kept, and Training fails loud naming the differing names.
2. **One search per family on its own trial budget** (D-140 (b)): `split_budget`
   (`config/schema.py`) divides `training.max_iter` equally over the listed families and gives
   the remainder, one trial each, to the first families of the list (60 over four is 15 each;
   62 is 16, 16, 15, 15), unless `training.trials` names every listed family's count and
   replaces `max_iter`. **Every family needs at least two trials:** a budget that leaves a
   listed family fewer is refused before the run number is taken (through `check_spaces`),
   naming the families and the three ways out: raise `training.max_iter`, list fewer families,
   or give each at least 2 in `training.trials`. On one trial FLAML 2.7 runs no search (its
   `max_iter < 2` shortcut fits the start configuration and judges nothing), so Training would
   have no trial to keep. FLAML's own
   selector starved a family (9 of 60 trials) and ignores the seed; a joint round-robin search
   equals separate searches (measured).
3. **The optimiser is FLAML's local search (CFO):** from a start it steps in a random direction,
   keeps an improving step, tries the opposite one, and shrinks the step when neither helps.
4. **Always cross-validated on our folds:** `fold_splitter` gives FLAML the dataset's folds as a
   splitter object, so every trial is fitted R × K times (R dealings of K folds) and its loss is
   the mean over them. Nothing else is held out, and no fit has an inner early-stopping split.
5. **FLAML's `fit` runs with six fixed switches** (`FLAML_SWITCHES`, D-140 (b)), each fixed
   because, left free, it would break a promise:

   | Switch | Left free it would | Why fixed |
   |---|---|---|
   | `auto_augment=False` | copy a class under 20 rows until it has 20 | it changes the class balance behind the calibration's back; it never acts with our splitter, so this makes that explicit |
   | `ensemble=False` | stack the best learners into one ensemble | the bundle holds one booster in one native file (D-051) |
   | `early_stop=False` | end the search when FLAML judges it converged | a trial budget would no longer mean that many trials |
   | `sample=False` | train early trials on a subsample | it acts only under a holdout; fixed so behaviour cannot change with the evaluation method |
   | `log_type="all"` | log improving trials only | the trials table needs every trial |
   | `skip_transform=True` | impute, drop and recode columns before the folds are cut | the search would judge data the saved booster never scores (item 6) |

   A use case that needs one of them needs a code change with a reason.

   **FLAML's refit on every row stays on.** At the end of each family's search FLAML refits the
   best trial on every row, and under cross-validation this cannot be switched off:
   `retrain_full=False` does not stop it whenever `max_iter > 0` (T46). It costs one fit per
   family, about a quarter of one trial at five folds; Training never reads that model.
6. **`skip_transform=True` on every FLAML fit,** and not a config field (T38): given a
   DataFrame, FLAML would fill numeric nulls with the median before the folds are cut, drop
   constant columns and recode categoricals, so the search would judge data the saved booster
   never scores (0.40 apart in probability on a 6,000-row check; 5.7 to 16.1 in the target's
   units for regression). Nulls go to the libraries, which learn where they belong.
7. **Bounded ranges, few dimensions on purpose** (D-140 (c)): four or five per family, every
   other parameter FLAML would search passed as a constant at the library's default. At 15 to 50
   trials a wide space is noise (50 to 100 evaluations per dimension is one rule of thumb
   [Bischl23]); the penalties are worth about 0.003 AUC [Probst19]. The ranges come from the
   tools surveyed, every one narrower than FLAML's own [Spaces]. "Log" is a log scale; each start
   is FLAML 2.7.0's own start clipped into the range (`flaml/automl/model.py`):

   **`lgbm`**

   | Parameter | Range | Scale | Start |
   |---|---|---|---|
   | `learning_rate` | 0.01–0.3 | log | 0.1 |
   | `n_estimators` | 50–2,000 | log, integer | 50 |
   | `num_leaves` | 4–255 | log, integer | 4 |
   | `min_child_samples` | 5–500 | log, integer | 20 |
   | `colsample_bytree` | 0.4–1 | linear | 1 |

   **`xgboost`** (leaf-wise)

   | Parameter | Range | Scale | Start |
   |---|---|---|---|
   | `learning_rate` | 0.01–0.3 | log | 0.1 |
   | `n_estimators` | 50–2,000 | log, integer | 50 |
   | `max_leaves` | 4–255 | log, integer | 4 |
   | `min_child_weight` | 0.5–20 | log | 1 |
   | `colsample_bytree` | 0.4–1 | linear | 1 |

   **`xgb_limitdepth`** (depth-wise)

   | Parameter | Range | Scale | Start |
   |---|---|---|---|
   | `learning_rate` | 0.01–0.3 | log | 0.3 |
   | `n_estimators` | 50–2,000 | log, integer | 50 |
   | `max_depth` | 3–10 | linear, integer | 6 |
   | `min_child_weight` | 0.5–20 | log | 1 |
   | `colsample_bytree` | 0.4–1 | linear | 1 |

   **`catboost`**

   | Parameter | Range | Scale | Start |
   |---|---|---|---|
   | `learning_rate` | 0.01–0.3 | log | 0.1 |
   | `n_estimators` | 50–2,000 | log, integer | 50 (FLAML holds 8,192 unsearched; the range's low end, like the others) |
   | `depth` | 4–8 | linear, integer | 6 (FLAML does not search it: the library's default) |
   | `l2_leaf_reg` | 1–10 | log | 3 (the same) |

   `min_child_weight` bounds the sum of p(1 − p) in a leaf, not a row count: at a 2% rate a
   weight of 1 is about 50 rows. A person overrides one leaf in `training.search_space`
   ([config](config.md#the-modelling-fields-stage-3)). The `dev` measurement of the build
   reports every family's fold loss and seconds; a start can be revisited there.
8. **Every ranged leaf reaches FLAML with its start** (T39): the default start or the config's
   `start`, clipped into the range. FLAML drops its own start for every parameter the space
   overrides, and with all of them overridden and none given a start it searches nothing and
   applies none of the constants. `check_search` fails loud after each family's search unless
   trial 1 is at the starts and, for a budget above one, the trials differ.
9. **The search metric comes from the decision** (D-140 (d)), FLAML's names (T9):

   | Task, `decision.type` | Search metric | Why |
   |---|---|---|
   | binary, `probability` or `threshold` | `log_loss` | the score is used, or cut, as a probability; log loss rewards the level as well as the order [Gneiting07] |
   | binary, `ranking` or `top_n` | `roc_auc` | order only; `decision.metric: ap` is the override for a shallow list with plenty of events |
   | regression | `rmse`, or `decision.metric`: `mae`, `r2`, `tweedie_deviance`, `poisson_deviance` | the deviances as custom metrics, Tweedie's at a fixed power of 1.5 |

   No study shows that selecting on average precision gives better lists, and a noisy criterion
   overfits the selection [Cawley10].
10. **Regression objectives** (`training.objective`): `squared_error` (default), `tweedie` (with
    `tweedie_variance_power`, default 1.5), `poisson`, `absolute_error`, `huber`; binary has
    `log_loss` only. The objective is how the booster learns; a trial is still judged by the
    declared metric. For an amount with many zeros and a long tail: `tweedie` with
    `decision.metric: tweedie_deviance`. `absolute_error` with a monotone constraint is refused
    at config load, whatever the families: LightGBM refuses the pair, XGBoost breaks the
    constraint silently, and pruning fits LightGBM for every run (T43); `huber` holds a
    constraint in all four. A deviance metric (`tweedie_deviance`, `poisson_deviance`) is
    refused at config load unless the objective is `tweedie` or `poisson`: under an identity
    link a prediction can be zero or negative, where the deviance is not defined, and the run
    would stop mid-search.
11. **CatBoost's tree count is searched** with `use_best_model` off, so CatBoost trains exactly
    the count it is given: every family's tree count is tuned on the client folds.
12. **What repeats:** under a trial budget, the same trials, best configuration and predictions
    at 1 or 2 threads, with and without load (measured); LightGBM's trees and margins are
    identical whether it builds its histograms column-wise or row-wise and at 1, 2 or 8 threads
    (measured). `training.seed` drives the search's seed, the fold salt and, through constants,
    the libraries' seeds. A time budget (`training.time_budget_s`, per family) does not repeat,
    because FLAML then picks by measured seconds; `training.json` holds `reproducible_to:
    recipe` and the run's warnings say "reproducible to the recipe, not the model". Across
    machines: unverified, checked at the pre-release run.
    - **What the promise rests on is recorded:** `training.json` holds `threads`, the thread
      count every fit and predict ran on, and `library_versions`, the installed `flaml`,
      `lightgbm`, `xgboost`, `catboost`, `numpy` and `scikit-learn`, beside the code version.
      The thread count is the environment file's `threads` (null: every core of the machine;
      [environment](environment.md)); no hash holds it. The models were byte-identical at 1 to
      8 threads for every family on the development machine (LightGBM 4.6.0, XGBoost 3.2.0,
      CatBoost 1.2.8, measured); not checked with declared categoricals or on the bank's
      hardware.
    - **The judged-model check.** Under a time budget FLAML also stops adding LightGBM's and
      XGBoost's trees at its deadline while its log keeps the configured count (T45), so the
      model a trial was judged on may have fewer trees than the configuration the framework
      fits. After the fold models of the first dealing, Training fits the best configuration's
      fold models on every further dealing too ((R − 1) · K more fits) and compares their mean
      fold loss on `score_raw` over every dealing, as FLAML averages a trial, with the best
      trial's (`check_judged_model`). The two agree when they differ by at most 1e-6, taken
      relative to the loss above a loss of 1 (`LOSS_TOLERANCE` · max(1, loss)); XGBoost's
      float32 margins move a fold loss by about 1e-10. Unequal fails loud under a trial budget
      and is a warning with both numbers under a time budget, where every number of the run is
      the framework's own. `training.json` records the check as `judged_model: {dealings,
      search_loss, fold_models_loss, agrees}`.
13. **A non-finite fold loss fails loud:** FLAML logs NaN for a fold metric that is not defined
    (a fold without a positive under `roc_auc` or `ap`) and searches on without raising (T47);
    `check_search` refuses any trial whose fold loss is NaN or infinite.
14. **The trials table** is read from FLAML's log of each family (saved in `training/` as
    `flaml_<family>.log`): one row per trial, `family, trial, fold_loss, seconds, improving,
    configuration`. `fold_loss` is the decision's metric as a loss (lower is better: `1 − AUC`
    for `roc_auc`), `trial` counts from 1, `improving` marks a new best and `configuration` holds
    the searched values only, as JSON text; the constants are in `training.json`'s
    `search_space`. There is no train loss per trial. Per family `training.json`'s `search`
    holds the trials run, the seconds in total, per trial (median) and of the longest trial, the
    best fold metric and the trial that first reached it, and the family's share of the run's
    seconds; a chart draws the best fold metric so far against the cumulative seconds, one line
    per family. A quick run thereby tells a person how to spend a main run's budget through
    `training.trials`; seconds enter no hash and no test. `check_search` also fails loud when a
    family logged no trial or, under a trial budget, a count other than its budget.
15. **The best family and configuration** are the lowest mean fold loss over every family's
    best trial, the list's order deciding a tie.
16. **The class-weight names are refused** in `training.search_space` at load, in any case:
    `scale_pos_weight`, `is_unbalance`, `class_weight`, `class_weights`, `auto_class_weights`;
    every family's `fit` refuses them and their library aliases too. Each counts a
    positive row several times, so the model believes positives more common than they are and
    its probabilities come out too high [LGBM-P][XGB-T]. The calibration undoes exactly one change
    of the class balance, the declared sampling with its one keep fraction (§4.12); a weight
    would be a second change it does not know about. The message points to `sampling:
    negative_downsampling`.

### Selection
Automated selection runs at every level, on the train split only, before the search (D-140 (e)),
in two parts: the screen (the train statistics, the cluster rule and the floor) fits no model
and runs before the run number, so a screen that leaves no feature takes none; importance
pruning fits models and runs after it. Boosted trees lose little accuracy to irrelevant
features (0.004–0.008 AUC to 390 noise columns, measured [Grinsztajn22]); selection pays in
search time, which grows in a straight line with the features, and in a sign-off list a person
can defend.
1. **Three rules, in this order:**
   1. **The cluster rule** (`training.selection.cluster`): one representative per redundancy
      cluster of the Stage 2 ledger (`cluster`, label-free but computed with test clients, so the
      ranking inside a cluster is on the train split only, D-030). The members it drops are
      recorded under the representative's `represents`.
   2. **The floor** (`training.selection.floor_z`, default 2): a feature passes when its train
      concordance, or its null indicator's (`null_concordance`, on every train row), is at least
      0.5 + z · SE, each with its own SE on effective train clients as EDA's rules read it
      (about 0.509 at 3,870 events, 0.533 at 300). The value is tested first; the floor row's
      `cleared_by` names the statistic that cleared (`concordance`, `concordance_best_order` or
      `null_concordance`). Otherwise the feature is dropped with the value's numbers, a null
      value when its concordance is not available on train. A NaN statistic or threshold never
      passes. The nulls count because the families take them natively and nothing is imputed:
      a feature whose being filled predicts the target ("months since the last X", null for
      clients who never had X) is used by the model. A feature without nulls has no null
      concordance. The value's concordance is the plain one, or for a numeric the best-order one
      when the train split shows it as non-monotone: EDA's rule (`is_non_monotone`: the best
      order beats the value order by ≥ max(0.03, 4 · SE)) applied to the train numbers. Stage
      2's own `non_monotone` mark is never read here, since it has seen test labels. On noise
      the best-order concordance sits 2.5 to 2.8 SE above 0.5 (measured by the audit), so for
      such a feature the rule's margin is the guard; the floor for it is an open point
      ([below](#open-questions)). `null` switches the floor off.
      - **The null indicator's SE** is the task's SE times `sqrt(3·p·(1 − p))`, `p` the
        feature's null share on the train rows: the tie correction of a two-valued feature.
        Without it the test could not pass at a rare null share. The SE floor of 0.005 stays,
        which sets the bar at about 1% nulls.
      - **One null pattern clears at most one feature.** The features whose nulls fall on the
        same train rows (`null_pattern`, a digest of the null mask in the train statistics)
        share one null indicator and form a group. When no member passes on its value and the
        indicator clears, the member with the highest value passes on the nulls (`cleared_by`
        `null_concordance`); the others are dropped with `represented_by` naming it. When a
        member passes on its value, the pattern is already in the model through it: no other
        member clears on the nulls, and each failing one is dropped with `represented_by`
        naming the value-passing member with the highest value. On the synthetic data "fewer
        than six months on the book" makes every six-month rollup null on the same rows, and
        without the rule ten features passed on that one pattern whatever their values.
      - **When to lower it.** The default suits many candidates and plenty of events. With few
        converting train clients the floor is high and drops real but weak features often,
        and a use case with few, expert-chosen candidates (corporate) loses more by a wrong
        drop than by a kept noise feature: below about 300 converting train clients set
        `floor_z` to 1 or `null` and rely on kept features and pruning. The value is never
        derived from the event count: a person sets it. The floor is a two-sided test: the
        concordance has its direction folded out, so a noise feature passes when it lands far
        enough from 0.5 on either side. The chance that a feature is dropped at z = 2, by its
        true concordance (normal approximation, SE ≈ 0.29 / √converting clients, both tails;
        the lower tail is negligible from a true 0.53):

        | Converting train clients | Floor | Noise (0.50) | True 0.53 | True 0.55 | True 0.60 | True 0.65 |
        |---|---|---|---|---|---|---|
        | 50 | 0.582 | 95% | 90% | 78% | 33% | 5% |
        | 100 | 0.558 | 95% | 83% | 61% | 7% | under 1% |
        | 300 | 0.533 | 95% | 58% | 16% | under 1% | under 1% |
        | 1,000 | 0.518 | 95% | 10% | under 1% | under 1% | under 1% |

        The table is for the value's concordance alone. On noise the audit measured about 4 to
        6% passing at z = 2 and about 30% at z = 1. A noise feature with nulls is tested twice:
        in the ML audit's simulation pure noise passed 1.7% without nulls and 1.7 to 2.8% with
        1 to 50% nulls at z = 2; at z = 1, 21% and up to 38% at 50% nulls. That was measured
        before the tie correction and the pattern rule and has not been measured again since.
        At z = 1 and 100 converting clients a true 0.55 is dropped about one time in four.
   3. **Importance pruning** (`training.selection.prune`): does the model still need the feature
      once the others are there?
2. **Train-split statistics only,** on the train frame as collected: a rank statistic is
   unbiased under label-dependent sampling. Each feature's cells are built in pandas from its
   encoded column and read by the statistics engine EDA uses (`train_statistics`). EDA's
   all-client ranking and its `non_monotone` mark are never read (D-030); the per-run ledger
   shows EDA's direction and mark beside the model's for display and the wrong-sign warning
   only.
3. **A `keep` is measured, never dropped:** a kept feature shows its value and whether the rule
   would have dropped it; it stays a cluster member, so the representative is chosen with it in
   the comparison, and both stay when the kept one loses.
4. **The pruning, step by step:**
   1. Add five seeded columns of random numbers to the encoded train frame.
   2. Fit the K fold models (the first dealing) with LightGBM, whatever families are searched,
      under the run's constraints, at the pruning's own size. P being the columns with the noise
      columns: 4 leaves, ⌈10 · P / 3⌉ trees and `colsample_bytree` = 3 / P, at LightGBM's
      default rate (0.1) and leaf size (20). Each tree is offered three columns, one per split,
      and each column about ten trees; LightGBM rounds the share times the columns to the
      nearest whole count, never below one. Take each feature's out-of-fold contribution share.
   3. The candidates to drop are the features that do no better than the best noise column;
      a `keep` survives. A best noise share of exactly 0 means no noise column got a split, so
      nothing was compared with noise: pruning then drops nothing and the run warns.
   4. When there are candidates, fit the fold models twice more, both without the noise columns,
      at the same leaves and with every column offered to every tree (`colsample_bytree` = 1),
      on the yardstick's tree count capped at 300 (`COMPARISON_TREES`): once with every
      feature, once without the candidates. Any rise in the loss (the decision's metric as a
      loss, out of fold, the mean over the folds) undoes the drop: nothing is pruned, the
      candidates' outcome is `undone` and the run says so. The two fits differ only by the
      candidates, so a candidate no tree uses changes nothing; at three columns a tree the two
      frames would draw different columns per tree, and that chance alone would move the loss.
      The comparison judges the candidates as a set: one needed feature keeps every candidate,
      and many weak ones go together.
   5. No noise column leaves the function; the search runs on what is left.

   **Why this size.** A pruning model at the search's start size (50 trees of 4 leaves) could
   not split every column of a wide frame, so on simulated frames with 1,000 or more events the
   best noise share was 0 in most cases and every unsplit real feature was dropped; at about ten
   offers per column the zero case occurred in 0 of 31 cases. The price is that about 13% of
   pure-noise columns survive pruning, and in a run the floor has removed most junk before it.

   **Why the comparison's size.** At 400 columns the cap of 300 trees gave the same outcomes as
   the full count in about a third of the time, and the full count overfits at about 1,000
   events (measured). On 31 simulated cases after the change the undo fired in none and kept no
   noise column; the first version, at three columns a tree, kept 199 noise columns by the draw
   alone. In four cases at about 1,000 events and 400 columns pruning dropped 217 weak real
   features in all, and that did not hurt a model of realistic size. A feature that works only
   jointly with another is nominated and not reliably caught: a `keep` is the answer
   ([below](#open-questions)).

   Pruning costs one round of K fits without candidates and three with them, and its tree count
   grows with the columns (334 trees at P = 100); its seconds are still to read
   ([below](#open-questions)).
5. **Every drop is a row of the per-run ledger** with the rule, its value and its threshold, and
   nothing else records it: no audit-log entry is written, because a drop shapes no later input
   (the next run recomputes its own, D-125). The config holds only the rules, so a rerun on
   unchanged data gives the same drops (D-043).
6. **Final features** = the feature set in force minus the drops. Columns another use case's
   target was built from are ordinary candidates; Feature Checks' leakage step and the floor are
   their guards.

### Fold models and calibration
1. **K fold models** at the chosen family and configuration, each fitted on K − 1 folds of the
   first dealing and scoring the fold it did not see, under the run's constraints; they give the
   out-of-fold margins and contributions and are discarded (D-094 (b)). Under
   `training.fold_repeats` the further dealings' fold models serve the judged-model check only
   ([the search](#the-search), item 12). Calibration is fitted on
   these out-of-fold margins inside train, never on test or validation (§4.7).
2. **The method follows the decision** (D-049): binary `platt` for a `probability` decision,
   `none` otherwise, and a person may set `platt`, `beta` or `none`; regression `mean` for
   `tweedie` and `poisson`, `none` for the other objectives. Following the decision, not the
   evidence, keeps the steps fixed before any result and makes a production retrain run the
   steps of its parent.
3. **Platt** is an unpenalised logistic regression of the label on the margin; its family holds
   "leave as is" (a = 1, b = 0). On the probability instead it cannot, and it degraded strong
   tabular models [Kull17][CalArena26].
4. **Beta** (three parameters on p = sigmoid(m), [Kull17]) is refitted without a term whose
   coefficient comes out negative, so the map stays increasing.
5. **The offset** = logit(true rate) − logit(sampled rate) under `negative_downsampling`, zero
   without sampling and under `client_sample`, always zero for regression; exact for every
   period under one keep fraction [KZ01][He14].
6. **Every binary run stores the out-of-fold log loss of `none`, `platt` and `beta`** (the
   `calibration` table's `oof_loss`), whatever the decision, so the cost of the choice is
   visible; a person who sees `beta` clearly better sets it with one entry and trains again.
   Each method's loss is in sample for its calibrator: it is fitted and judged on the same
   out-of-fold rows, and beta contains Platt, which contains `none`, so a method with more
   parameters never looks worse (by about 1 / (2 × effective rows) per parameter). A gap in the
   fourth decimal is no reason to switch; the table's caption says so. The loss is not
   cross-fitted by fold, since a fold's subset can separate the labels where the whole does not.
7. **The regression level factor** (`mean`) is the total observed over the total predicted on
   the out-of-fold predictions. It is stored with its interval (a client bootstrap of 200
   replicates, each client's Poisson(1) weight drawn from pandas' fixed hash of the client, so
   a client's rows move together and a rerun draws the same interval) and the number of
   rows that hold half of the target's total, and is never winsorised: capping the target made the
   level worse than no correction (0.90 against 1.00, measured). When the interval is wider than
   ±5% the log warns: the level of this target is decided by a few rows; the factor, and any
   model's level, is uncertain; consider a capped target. When a replicate's weighted
   predictions total 0 the factor is undefined there, the interval is null and the log warns
   with the count of such replicates (`zero_replicates`). The method never switches itself.
8. **The formulas** (the score per link and method, the parameters' shape) are [model
   bundle](model_bundle.md#the-calibration-and-the-output-columns)'s; `apply_calibration` is the
   one code that applies them.
9. **The out-of-fold metric** is the decision's metric on the out-of-fold scores, the mean over
   the folds of the first dealing, with the concordance (the AUC for a binary target) beside it,
   computed exactly on rows for both tasks ([below](#the-honesty-notes)). Training's average
   precision is scikit-learn's on rows, while Evaluation's on tied scores is the expected value
   under random tie-breaking on cells, so the two differ where scores tie
   ([evaluation](evaluation.md#metrics) owns the cells side).
10. **Level metrics are taken before the offset.** Under `negative_downsampling` the
    out-of-fold rows are at the sampled rate while `score` is at the true rate, so the
    out-of-fold log loss of `none`, `platt` and `beta` and the out-of-fold metric are computed
    on the calibrated margin without the offset. A fold's average precision and log loss are
    at the sampled prevalence and are never compared with the test split's.
11. **The offset follows the method:** zero under `client_sample` and without sampling, by
    rule, never from the sampling record's two rates, which differ under `client_sample` by
    sampling noise.
12. **What stops calibration, and Training with it:**
    - constant out-of-fold margins (the fold models learned nothing), for both tasks;
    - for binary, margins that separate the labels (no maximum-likelihood fit exists; out of
      fold this means a leaking feature) or a Platt or beta fit that does not converge; every
      binary run fits all three methods, so this holds whatever the method;
    - an anti-predictive fit, whatever the method: every fitted Platt and beta is checked by
      the bundle's own rule (`check_order_kept`: Platt a > 0; beta a ≥ 0 and b ≥ 0, not both
      0), since a fit outside it would reverse or flatten the model's order; a parameter that
      is not a finite number is refused first, since a NaN compares false and would pass;
    - for regression, a level factor that is not positive and finite, only when `mean` is the
      method; under `none` it is a warning.

    A non-finite out-of-fold margin or score fails loud, as `score_frame` refuses one.
13. **A null the model never saw.** With no null in train, a null at scoring is an extreme
    value, differently per library, and an unseen level of an ordered feature becomes such a
    null. Training warns on an ordered feature without train nulls, and the per-run ledger's
    train `null_share` lets Evaluation flag a feature that has nulls at scoring and had none
    in train.

### Monotone constraints
1. **A person declares them,** `training.monotone: {income: increasing, utilisation:
   decreasing}`; nothing is derived from the data. A constraint may be changed through the audit
   log after reading the sign-off view.
2. **Allowed on numeric features and ordered categoricals.** On an unordered categorical Training
   refuses when it starts, naming the feature: the libraries fail in three ways there (LightGBM
   aborts the process, XGBoost ignores it, CatBoost raises).
3. **The framework builds each library's form itself** for the features being fitted and checks
   it before any library is called; each library takes another form and fails silently on a
   wrong one (LightGBM drops the first entry of a bracketed string, XGBoost pads a short vector).
4. **It applies to every fit of the run:** the trials, the pruning and fold models, the final
   model, in every family; it is part of the recipe, so a production retrain keeps it.
5. **The wrong-sign warning:** when EDA's direction for the feature is the opposite, or EDA
   marked it `non_monotone`, the log and the sign-off view say so. It never refuses: the person
   may know more than the window shows.
6. **A constraint protects nothing from selection;** `keep` does. A constrained feature that is
   held or dropped is listed as "declared, not in the model".
7. **The grid check:** right after the self-check, the bundle reloaded from disk is swept over a
   grid on 200 rows for each constrained feature, and Training fails loud on any step in the
   wrong direction (`check_monotone`). Like the self-check it tests what was written, so it
   catches a loader or library failure, such as LightGBM's `advanced` method, which broke the
   constraint on 28 of 300 rows.
8. **LightGBM runs its `basic` method,** a fixed parameter: `intermediate` showed no gain (its
   holdout log loss minus `basic`'s from −0.0006 to +0.0009, mean 0.0000, over 18 comparisons).
   A person may try it with a `{value: intermediate}` leaf; `advanced` is refused, and so is
   `intermediate` with `colsample_bynode`, under which LightGBM falls back to `basic` with only a
   warning [LGBM-src].

### The final fit and the bundle
1. **The final model** is `FAMILIES[family].fit` on every train row as trained, at the best
   configuration with the fixed parameters; it equals FLAML's own refit on the encoded frame
   (bit for bit for LightGBM and both XGBoost variants, measured).
2. **The booster's feature names** equal the final list, else Training fails loud (D-094 (a)).
3. **The in-sample AUC** (the concordance for regression) on the rows the model was fitted on is
   stored for the train–test gap Evaluation shows (D-106), and so is each train row's in-sample
   score (the `oof` table's `score_in_sample`), from which Evaluation takes a regression's
   train concordance on test's cells ([evaluation](evaluation.md)).
4. **The bundle** is written by `write_run_bundle` (`training/run_bundle.py`): `write_bundle`
   writes it, and it is loaded once and self-checked by `check_bundle` on 1,000 train rows
   (`SELF_CHECK_ROWS`;
   [model bundle](model_bundle.md#how-one-bundle-is-written-loaded-and-scored)); then the grid
   check runs on the same loaded bundle ([above](#monotone-constraints)).

### What Training writes
The run folder's layout is [model bundle](model_bundle.md#the-run-folder)'s. Training writes:
1. `run.json` first, through `create_run` (step 2 of the flow), never again.
2. `bundle/` (step 6).
3. `ledger_run.parquet` with its sidecar ([feature ledger](feature_ledger.md#the-per-run-part)),
   at `ledger_run_schema_version` 2, which carries `floor_cleared_by`. It adds two warnings to
   the run's: a constraint against EDA's direction or its `non_monotone` mark, and a final
   feature the final model never split on.
4. `stage2/`, the run's own copy of what it read from Stage 2, so an EDA rerun never changes
   this run (D-139 (b)). The copy has its own format, `stage2_copy_schema_version` 1
   (`STAGE2_COPY_SCHEMA_VERSION`), and `save_stage2` writes exactly the columns
   `STAGE2_COLUMNS` freezes per table, so a later EDA or ledger column changes no copy:
   - `ledger.parquet`: every candidate's Stage 2 ledger row (the sign-off table lists the held
     and excluded ones too), without the ledger's sidecar;
   - EDA's `cells`, `edges`, `bins` and `levels` tables, the rows of the final features only;
     `bins` and `levels` keep the group columns both tasks share and drop regression's extra
     ones (the median and the non-zero columns), which nothing reads;
   - `_stage2.json`: `stage2_copy_schema_version`, which `read_stage2_copy` checks with the
     columns before anything reads the copy; and, as provenance never checked, the versions it
     was copied from (`eda_schema_version` as read, `ledger_schema_version`) and `runs`, the
     two Stage 2 run tokens. A later EDA schema bump therefore leaves earlier runs readable. A
     copy of another version, or without one, is refused with "train the run again".
5. `training/`, last, through a temporary folder like every stage folder (D-136):
   - `training.json` (`schema_version` 2, `STAGE_SCHEMA_VERSIONS` in `artifacts.py`), its
     keys:

     | Key | Holds |
     |---|---|
     | the stamp | `schema_version`, `stage`, `framework_version`, `written_at`, `tables` |
     | the identity | the resolved config's hashes, `entity`, `replayed_to`, the settings Training reads with their digest, the sources with their digest (`stage_identity`) |
     | `run_id`, `stage2` | the run, and the EDA and Feature Checks run tokens it was trained against |
     | `summary` | the flat block `list_runs` shows as columns and `show_run` displays: `family`, `features`, `feature_signature`, `trials`, `oof_<metric>` (a key named by the decision's metric, e.g. `oof_log_loss`), `recipe_hash`, `model_hash`, `seconds` (the laps' sum, without the write of `training/` itself) |
     | `best` | the best `family` and its `parameters` (no thread count) |
     | `search` | one row per family, as item 14 of [the search](#the-search) |
     | `search_space` | the leaves each family searched, ranges and constants |
     | `metrics` | `metric`, `out_of_fold`, `out_of_fold_concordance`, `in_sample_concordance` and `note`, the optimism note ([below](#the-honesty-notes)) |
     | `final_features` | the final list, in the model's order |
     | `sampling`, `folds` | the frames' sampling record and fold counts |
     | `reproducible_to` | `model`, or `recipe` under a time budget |
     | `judged_model` | `dealings`, `search_loss`, `fold_models_loss`, `agrees` ([the search](#the-search), item 12) |
     | `threads`, `library_versions` | the thread count of every fit and predict; the versions of `flaml`, `lightgbm`, `xgboost`, `catboost`, `numpy` and `scikit-learn` |
     | `warnings` | every warning of the run; Evaluation's report shows them under "From Training" |
     | `timings` | `seconds`, per step: `frames` (the opening: the gate, the collect, the encoder and the screen), `selection` (pruning), `search`, `fold_models` (every dealing's, with the calibration), `final_fit`, `bundle` (with the self-check and the grid check), `ledger_and_stage2`, `tables` (the tables, `training.json`'s content and the views) |

   - `tables/`:

     | Table | Grain | Columns |
     |---|---|---|
     | `trials` | one row per trial and family | `family, trial, fold_loss, seconds, improving, configuration` ([the search](#the-search), item 14) |
     | `selection` | one row per feature and rule | `feature, rule, value, threshold, outcome, represented_by` (on a dropped row, the feature it went to: a `cluster` drop's representative, a `floor` drop's member that carries its null pattern, when one does; else null), `cleared_by` (on a `floor` row that passed, the statistic that cleared, else null) |
     | `oof` | one row per train row as trained | `unit_id, period, cv_fold, target, margin, score_raw, score`, `score_in_sample` (the final model's score on the row it was fitted on) |
     | `explanation_sample` | one row per sampled train row: 5,000 seeded rows, or every row when train has fewer | `unit_id, period`, the final features' raw values, `<feature>__contribution` per feature (out of fold), `base_value` |
     | `calibration` | one row per method the task fits | `method, chosen, parameters` (JSON text), `oof_loss` (the task's calibration loss: binary's log loss, null for regression), `true_rate, sampled_rate, offset`, and for regression `factor, factor_low, factor_high, half_total_rows`; null where a column does not apply |
     | `signoff` | one row per feature | [below](#the-sign-off-view) |

     Under `negative_downsampling` the `oof` rows and their `target` are at the sampled rate,
     while `score` is at the true rate (the offset applied), so `score` and `target` do not
     compare level for level; Training's own level metrics leave the offset out
     ([fold models and calibration](#fold-models-and-calibration), item 10).
   - `flaml_<family>.log`, FLAML's log of each family; `resolved_config.yml`; `log.json`, as in
     every stage folder (D-136). Training writes no report: its views are notebook 04's and a
     section of Evaluation's report.
6. Then the `run` entry of stage `training` in the audit log, with the run number and no
   `periods`, so a Training run never blocks moving the validation period (D-088).

What a later stage reads of all this, keys, nested keys and table columns, is the run folder's
contract in `run_artifacts.py`, checked once when the run is opened
([model bundle](model_bundle.md#the-contract-in-detail)).

A folder without `training/` is a crashed run, listed as incomplete; its number stays taken while
the folder exists ([model bundle](model_bundle.md#requirements-and-design-constraints)). Training writes no drift reference: Evaluation does, from `stage2/` (D-054).

### The sign-off view
1. **Train-only evidence** (D-031): its table and charts come from the out-of-fold contributions
   and the explanation sample, so it is readable right after training and needs no evaluated run.
2. **The table's order:** one row per feature, in four sections (`section`): `model`, the final
   list by out-of-fold contribution, each with its share and the running total, the model's
   direction beside EDA's (numerics only) and whether they agree, its declared constraint and
   the wrong-sign mark, the cluster members it represents, its source, Feature Checks' notes and
   any flag a person kept; `held`, with their open flags; `excluded`, with the `exclude` entry in
   force and its reason; `declared_not_in_model`, a constrained feature that is none of these
   (dropped by selection, with `dropped_by`). A constrained feature that is held or excluded
   stays in its own section; the view's "declared, not in the model" block lists every
   constrained feature outside the model.
3. **Where it shows:** notebook 04 and a section of the model results report; notebook 05 guides
   the sign-off itself.
4. **What the `sign_off` entry covers:** the run, the feature signature and the final list; it
   covers every run of the same data definition with the same signature, earlier ones
   included (a person defends a feature list), and the view of
   such a run says which run was signed. Rejecting a feature is an `exclude` entry with stage
   `sign_off` and a retrain ([config](config.md#decision-audit-log-d-125), D-125). `register`'s
   check is M2.4's.

### The honesty notes
1. **The out-of-fold metric is optimistic:** selection, the search and the calibration were
   chosen or fitted on the same folds. The test split is the first honest number. The size,
   weak evidence (the audit's three replicates): about 0.018 AUC at 300 train events with 150
   noise candidates, 0.010 of it from selecting on the same rows. `training.json`'s `metrics`
   carry the `note` saying so, and the metrics view's caption repeats it, so nobody reads the
   numbers as a test result.
2. **The train–test gap** comes from the in-sample AUC, a rank metric that downsampling leaves
   unbiased, and is used only by a sweep that picks, together with the test metric (D-083).
3. **People's feature decisions in EDA and Feature Checks have seen test labels** (D-030); the
   model results report says so. The validation period informs no choice here (§4.4).

### Deliberately not built
- **Class weights or any balancing:** they damage probabilities, and the offset undoes only the
  declared sampling.
- **Imputation:** the libraries' native null handling was the best single method in the largest
  benchmark [PerezLebel22]; a family that needs filling brings it (Phase 3).
- **Isotonic calibration:** it ties scores and outputs exact 0 and 1, which breaks a top-N cut and
  the offset.
- **An own cross-validation loop around the tuner:** the client folds inside the search and the
  client split are the requirement (D-106; Phase 3 wishlist).
- **A refit command in the sandpit:** the evaluated model is the one registered (D-052).
- **BlendSearch and the trade-off chart:** they come with the predefined path (Phase 3).
- **Ranges and an objective suggested from the data:** an EDA or Feature Checks item (M3/M4).
- **Fitting the calibrator at the true rate** instead of adding the offset: decided by the oracle
  check under downsampling (M3).

### The predefined path (Phase 3)
A named model family tuned with Optuna (D-020), behind the same `FAMILIES` interface:
- bounded, regularisation-friendly search spaces per family; early stopping; pruning;
- an optional two-objective search (in-time metric against the overfitting gap), shown as a
  **trade-off chart**; a person or a level's rule picks a point, and the pick is recorded. The
  chart weighs train and test metrics; the validation period never chooses (D-083). The default
  pick rule at `autonomous` and the Optuna 5.0 API (multi-objective, pruning) are settled when it
  is built;
- nulls: a family that imputes fills outside the value range with a missing indicator, never the
  median, since the `nulls_informative` advice ([feature checks](feature_checks.md)) relies on
  nulls staying a group.

### Code map
- `training/search_space.py`: rules as data (`RANGES`, the bounded ranges and starts per
  family; `CONSTANTS`, every other parameter FLAML would search, at the library's default;
  `FLAML_SWITCHES`), `family_space`, `start_configuration`, `fit_parameters`.
- `training/search.py`: the search's contract: `checked_space`, `check_spaces`,
  `check_search`, `search_families` (`Search`, whose `recorded_parameters` drop the thread
  count for the recipe and `training.json`) with `_search_one` per family,
  `check_judged_model` (`LOSS_TOLERANCE`). `split_budget`, the trial budget per family, is in
  `config/schema.py`, beside the config fields it reads.
- `training/automl.py`: FLAML's side: `fold_splitter` (`ClientFolds`), `search_metric`,
  `build_search_space`, `flaml_settings` (`FIT_ARGUMENTS`, `NOT_CONSTANTS`), `SEARCH_FRAMES`
  (the frame each family's search gets), `search_family`, `read_trials`.
- `training/gate.py`: `read_stage2` (`Stage2`), `check_stage2_columns`, `feature_set`,
  `check_noise_names`, `check_derived_names`, `check_target_range`, `check_counts`,
  `check_kinds`, `save_stage2`.
- `training/train_data.py`: `fit_train_encoder`, `encode_and_screen` (`Screened`),
  `finish_selection` (`TrainData`); `training/train_statistics.py`: `train_statistics` (its
  columns `null_se` and `null_pattern` among them); `training/selection.py`: `screen_features`, `prune_features`,
  `apply_cluster_rule`, `apply_floor` (`_null_carriers`, one null pattern's carrier),
  `prune_by_importance` (`NOISE_COLUMNS`, `PRUNING_MODEL`, `COMPARISON_TREES`).
- `training/fold_models.py`: `fit_fold_models`, `every_dealing_loss`, `fit_final_model`,
  `out_of_fold_loss`; `training/calibrate.py`: `calibrate`; `statistics/calibration.py`:
  `fit_platt`, `fit_beta`, `prior_shift_offset`, `level_factor`; the calibration entries of
  `TASK_SPECS` in `tasks.py` (`calibration_fits`, `calibration_loss`, and the view's
  `calibration_table_columns` and `calibration_table_caption`); `model/calibration.py`:
  `check_order_kept`, which `calibrate` applies to every fitted method;
  `statistics/losses.py`: `LOSSES`, `metric_loss`, `mean_fold_loss`, `metric_value`,
  `row_concordance`.
- `training/ledger_run.py`: `build_run_ledger`, `ledger_warnings`, `save_run_ledger`;
  `training/signoff.py`: `signoff_table`; `training/tables.py`: `oof_table`,
  `explanation_sample`, `train_metrics`; `training/run_bundle.py`: `write_run_bundle`
  (`SELF_CHECK_ROWS`), the bundle written, reloaded, self-checked and grid-checked.
- `run_artifacts.py`: the run folder as every later stage reads it: `open_run_folder`
  (`RunFolder`) and the contract it checks ([model bundle](model_bundle.md#the-contract-in-detail)),
  `read_training_tables`, `read_stage2_copy`, `read_run_ledger`, `train_level`,
  `read_in_sample`, `sample_contributions`, and the names both sides share, each defined once
  there (the per-run ledger's `LEDGER_RUN_SCHEMA_VERSION`, `LEDGER_RUN_FILE`, `SIDECAR_FILE`,
  `RULES`, `OUTCOMES`; the sign-off's `SECTIONS`, `LIST_COLUMNS` and `SIGNOFF_COLUMNS`; the
  calibration table's `CALIBRATION_COLUMNS`; the explanation sample's `EXPLANATION_ROWS`,
  `CONTRIBUTION_SUFFIX`, `BASE_COLUMN`; the stored names `TRAINING_SIGNOFF`,
  `TRAINING_TRIALS`, `TRAIN_SAMPLE` and `CARRIED_TABLES`; the copy's `STAGE2_TABLES`,
  `STAGE2_FILE`, `STAGE2_COPY_SCHEMA_VERSION`, `STAGE2_COLUMNS`).
- `ledger.py`: `missing_stage2`, which the gate and `run` at `autonomous` read
  ([feature ledger](feature_ledger.md#code-map)).
- `reporting/training_views.py`: `search_summary`, `search_table`, `search_progress_chart`,
  `selection_view`, `calibration_view`, `signoff_view`, `training_views` (the blocks notebook 04
  shows; `search_table` and `signoff_view` are Evaluation's report's too); `CALIBRATION_LINES`,
  the calibration view's summary line per task, which stays beside its functions because
  `tasks.py` must not import the reporting side.
- `reporting/explain_charts.py`: `importance_bar`, `beeswarm`, `waterfall`, `dependence`, drawn
  from the libraries' own contributions, no `shap` import.
- `model/bundle.py`: `write_bundle`, `load_bundle`, `build_bundle` (the bundle from its files'
  bytes); `model/scoring.py`: `check_bundle` (the self-check, on the loaded `Bundle`).
- `training/run.py`: `run_training`, which orchestrates only; its lines in the top-level
  `run.py` (`STAGES["training"]`, the `autonomous` rule).
- The call flow of one run is [How one run flows](#how-one-run-flows).
- Reading order for review: `run_training` and `_open_run` (the chain), `encode_and_screen`,
  `search_families`, `fit_parameters` and `read_trials`, `check_search` and
  `build_search_space` (T39), `check_judged_model` and `every_dealing_loss`,
  `train_statistics`, `apply_floor`, `prune_by_importance`, `calibrate`, `signoff_table`.

### Interface
Public: `run_training` (with `sign_off` in `runs.py`, [model bundle](model_bundle.md#interface));
CLI: `run <config>… --stages training`, `decide --sign-off --run`; the config section:
[config](config.md#the-modelling-fields-stage-3). The private functions:

```python
def run_training(cfg, entity, env, spark) -> StageResult: ...   # public

# search_space.py, search.py, automl.py
def family_space(family: str, overrides: dict) -> dict[str, dict]: ...
def start_configuration(space: dict[str, dict]) -> dict: ...
def fit_parameters(fixed: dict, space: dict[str, dict], searched: dict | None = None) -> dict: ...
def checked_space(family: str, cfg) -> dict[str, dict]: ...
def check_spaces(cfg) -> None: ...
def check_search(family: str, trials: pd.DataFrame, starts: dict, budget: int | None) -> None: ...
def search_families(X: pd.DataFrame, y: np.ndarray, folds: pd.DataFrame, encoder: dict,
                    monotone: dict[str, str], cfg, threads: int) -> Search: ...
def check_judged_model(search: Search, own_loss: float, timed: bool,
                       dealings: int) -> tuple[dict, list[str]]: ...   # the record, the warnings
def split_budget(cfg) -> dict[str, int]: ...                    # config/schema.py
def fold_splitter(folds: pd.DataFrame) -> ClientFolds: ...
def search_metric(metric: str) -> str | Callable: ...
def build_search_space(space: dict[str, dict], fixed: dict) -> dict: ...
def flaml_settings(family: str, space: dict[str, dict], fixed: dict, cfg, budget: int,
                   threads: int) -> dict: ...
SEARCH_FRAMES: dict[str, Callable[[pd.DataFrame, dict], pd.DataFrame]]  # (X, encoder) -> frame
def search_family(X: pd.DataFrame, y: np.ndarray, splitter: ClientFolds,
                  settings: dict) -> str: ...                    # the log's text
def read_trials(family: str, log: str, searched: list[str], constants: dict) -> pd.DataFrame: ...

# gate.py
def read_stage2(resolved, entity: str, env) -> Stage2: ...
def check_stage2_columns(stage2: Stage2) -> None: ...
def feature_set(stage2: Stage2, resolved, entries: list[Entry]
                ) -> tuple[list[str], dict, list[str]]: ...
def check_noise_names(features: list[str], prune: bool) -> None: ...
def check_derived_names(features: list[str]) -> None: ...
def check_target_range(train: pd.DataFrame, objective: str) -> None: ...
def check_counts(population: pd.DataFrame, eda_population: list[dict]) -> None: ...
def check_kinds(ledger: pd.DataFrame, kinds: dict[str, str]) -> None: ...
def save_stage2(folder: str, stage2: Stage2, final: list[str]) -> None: ...

# train_data.py, train_statistics.py, selection.py
def fit_train_encoder(train: pd.DataFrame, features: list[str], ledger: pd.DataFrame,
                      resolved) -> dict: ...
def encode_and_screen(train: pd.DataFrame, encoder: dict, ledger: pd.DataFrame,
                      resolved) -> tuple[Screened, dict, list[str]]: ...
def finish_selection(train: pd.DataFrame, encoder: dict, screened: Screened, resolved,
                     threads: int) -> tuple[TrainData, dict, list[str]]: ...
def train_statistics(train: pd.DataFrame, X: pd.DataFrame, encoder: dict, cfg) -> pd.DataFrame: ...
def screen_features(train: pd.DataFrame, X: pd.DataFrame, encoder: dict, stage2: pd.DataFrame,
                    cfg) -> tuple[list[str], pd.DataFrame, pd.DataFrame]: ...
def prune_features(train: pd.DataFrame, X: pd.DataFrame, encoder: dict, features: list[str],
                   cfg, threads: int) -> tuple[list[str], pd.DataFrame]: ...
def apply_cluster_rule(statistics: pd.DataFrame, stage2: pd.DataFrame, features: list[str],
                       kept: list[str]) -> pd.DataFrame: ...
def apply_floor(statistics: pd.DataFrame, features: list[str], kept: list[str],
                floor_z: float) -> pd.DataFrame: ...
def prune_by_importance(X: pd.DataFrame, y: np.ndarray, folds: pd.DataFrame, encoder: dict,
                        kept: list[str], cfg, threads: int) -> pd.DataFrame: ...

# fold_models.py, calibrate.py, statistics/calibration.py, statistics/losses.py
def fit_fold_models(X: pd.DataFrame, y: np.ndarray, folds: pd.DataFrame, family: str,
                    params: dict, task: str, threads: int | None = None
                    ) -> tuple[np.ndarray, np.ndarray]: ...
def every_dealing_loss(X: pd.DataFrame, y: np.ndarray, folds: pd.DataFrame, margins: np.ndarray,
                       family: str, params: dict, cfg, threads: int | None = None) -> float: ...
def fit_final_model(X: pd.DataFrame, y: np.ndarray, family: str, params: dict, task: str,
                    threads: int | None) -> FinalModel: ...
def out_of_fold_loss(metric: str, y: np.ndarray, margins: np.ndarray, fold: np.ndarray,
                     calibration: dict, task: str) -> float: ...
def calibrate(margins: np.ndarray, y: np.ndarray, clients: np.ndarray, cfg,
              sampling: dict) -> tuple[dict, pd.DataFrame, list[str]]: ...
def fit_platt(margin: np.ndarray, y: np.ndarray) -> dict: ...
def fit_beta(margin: np.ndarray, y: np.ndarray) -> dict: ...
def prior_shift_offset(true_rate: float, sampled_rate: float) -> float: ...
def level_factor(predicted: np.ndarray, y: np.ndarray, clients: np.ndarray,
                 replicates: int = 200) -> dict: ...
def metric_loss(metric: str, y: np.ndarray, prediction: np.ndarray) -> float: ...
def mean_fold_loss(metric: str, y: np.ndarray, prediction: np.ndarray,
                   fold: np.ndarray) -> float: ...
def metric_value(metric: str, loss: float) -> float: ...
def row_concordance(y: np.ndarray, prediction: np.ndarray) -> float: ...

# ledger_run.py, signoff.py, tables.py
def build_run_ledger(selection: pd.DataFrame, statistics: pd.DataFrame, description: dict,
                     contributions: pd.DataFrame, values: pd.DataFrame, encoder: dict,
                     encoder_shares: pd.DataFrame, monotone: dict[str, str],
                     stage2: pd.DataFrame, kept: list[str]) -> pd.DataFrame: ...
def ledger_warnings(run_ledger: pd.DataFrame) -> list[str]: ...
def save_run_ledger(ledger: pd.DataFrame, run_folder: str, meta: dict) -> None: ...
def signoff_table(run_ledger: pd.DataFrame, stage2: pd.DataFrame, entries: list[Entry],
                  resolved) -> pd.DataFrame: ...
def oof_table(train: pd.DataFrame, margins: np.ndarray, calibration: dict, task: str,
              in_sample: np.ndarray) -> pd.DataFrame: ...
def explanation_sample(train: pd.DataFrame, contributions: pd.DataFrame,
                       seed: int) -> pd.DataFrame: ...
def train_metrics(metric: str, task: str, y: np.ndarray, fold: np.ndarray, margins: np.ndarray,
                  calibration: dict, in_sample: np.ndarray) -> dict: ...

# run_bundle.py
def write_run_bundle(folder: str, resolved, run: str, data: TrainData, search: Search,
                     final: FinalModel, calibration: dict, train: pd.DataFrame,
                     threads: int) -> dict: ...                  # the manifest

# run_artifacts.py, ledger.py
def open_run_folder(run_folder: str) -> RunFolder: ...
def read_training_tables(read: RunFolder, names: Iterable[str]) -> dict[str, pd.DataFrame]: ...
def read_stage2_copy(run_folder: str) -> dict[str, pd.DataFrame]: ...
def read_run_ledger(run_folder: str) -> pd.DataFrame: ...
def train_level(read: RunFolder) -> float: ...
def read_in_sample(read: RunFolder) -> pd.DataFrame: ...       # target, score_in_sample
def sample_contributions(sample: pd.DataFrame, features: list[str]) -> pd.DataFrame: ...
def missing_stage2(resolved, entity: str, env) -> list[str]: ...   # ledger.py

# model/bundle.py, model/scoring.py (the bundle's; model_bundle.md owns them)
def build_bundle(files: dict[str, bytes], folder: str) -> Bundle: ...
def check_bundle(bundle: Bundle, sample: pd.DataFrame, expected: pd.DataFrame,
                 threads: int | None = None) -> None: ...

# reporting/training_views.py, reporting/explain_charts.py
def search_summary(trials: pd.DataFrame, metric: str) -> pd.DataFrame: ...
def search_table(trials: pd.DataFrame, metric: str) -> Styler: ...   # shared with Evaluation's report
def search_progress_chart(trials: pd.DataFrame, metric: str) -> go.Figure: ...
def selection_view(run_ledger: pd.DataFrame, selection: pd.DataFrame) -> dict: ...
def calibration_view(calibration: pd.DataFrame, task: str) -> dict: ...
def signoff_view(signoff: pd.DataFrame, signed: Entry | None) -> dict: ...
def training_views(run: str, opening: dict, warnings: list[str],
                   tables: dict[str, pd.DataFrame], run_ledger: pd.DataFrame, resolved,
                   signed: Entry | None, best: dict, metrics: dict) -> dict: ...
def importance_bar(contributions: pd.DataFrame, compare: pd.DataFrame | None = None,
                   top: int = 15) -> go.Figure: ...
def beeswarm(contributions: pd.DataFrame, values: pd.DataFrame, top: int = 15,
             clients: int = 1500, seed: int = 0) -> go.Figure: ...
def waterfall(contributions: pd.Series, base: float, values: pd.Series,
              shown: int = 9) -> go.Figure: ...
def dependence(contributions: pd.Series, values: pd.Series,
               colour: pd.Series | None = None) -> go.Figure: ...
```

### Lessons from the crunch
T5 (CatBoost writes files), T9 (FLAML's metric names), T14 (reading FLAML's trials), T38
(FLAML's hidden imputation), T39 (a search space without starts), T42 (FLAML shuffles each
fold's rows), T43 (the absolute error breaks constraints), T44 (all-null columns in parquet),
T45 (a time budget cuts trees), T46 (FLAML's refit on every row), T47 (NaN fold metrics); the
crunch's downsampling and calibration lessons in `docs/context/lessons.md`.

### Sources
The measurements on the pinned versions are in the stage's research note, in
[modelling_faq](../guides/modelling_faq.md).
- [Bischl23] Bischl et al. 2023, Hyperparameter optimization, https://arxiv.org/abs/2107.05847
- [CalArena26] Berta et al. 2026, CalArena, https://arxiv.org/abs/2605.30188
- [Cawley10] Cawley and Talbot 2010, On over-fitting in model selection,
  https://www.jmlr.org/papers/v11/cawley10a.html
- [Gneiting07] Gneiting and Raftery 2007, Strictly proper scoring rules,
  https://doi.org/10.1198/016214506000001437
- [Grinsztajn22] Grinsztajn et al. 2022, tree-based models on tabular data,
  https://arxiv.org/abs/2207.08815
- [He14] He et al. 2014, Practical lessons from predicting clicks on ads at Facebook,
  https://quinonero.net/Publications/predicting-clicks-facebook.pdf
- [Kohavi95] Kohavi 1995, cross-validation and bootstrap for model selection,
  https://ijcai.org/proceedings/1995/147
- [Kull17] Kull et al. 2017, Beta calibration, https://proceedings.mlr.press/v54/kull17a.html
- [KZ01] King and Zeng 2001, Logistic regression in rare events data,
  https://gking.harvard.edu/files/0s.pdf
- [LGBM-P] LightGBM, Parameters, https://lightgbm.readthedocs.io/en/latest/Parameters.html
- [LGBM-src] LightGBM 4.6.0, `Config::CheckParamConflict`,
  https://github.com/microsoft/LightGBM/blob/v4.6.0/src/io/config.cpp
- [PerezLebel22] Perez-Lebel et al. 2022, missing-values approaches on health databases,
  https://academic.oup.com/gigascience/article/doi/10.1093/gigascience/giac013/6568998
- [Probst19] Probst et al. 2019, Tunability,
  https://www.jmlr.org/papers/volume20/18-444/18-444.pdf
- [Spaces] the search spaces of AutoGluon, TabArena, TabZilla, Optuna's LightGBM tuner,
  mljar-supervised, LightAutoML and H2O, read in their source (links in the research note)
- [XGB-T] XGBoost, Notes on parameter tuning,
  https://xgboost.readthedocs.io/en/stable/tutorials/param_tuning.html

## Open questions
- Training's warnings are free text: the model results report shows them as written, and the
  model card carries Evaluation's considerations only. Codes with values in `training.json`
  would let the card carry Training's too.
- The floor for a feature judged non-monotone on train reads its best-order concordance, which
  sits 2.5 to 2.8 SE above 0.5 on noise; the rule's margin is the only guard today.
- The cluster rule picks its representative on the value only, so a member that would clear
  the floor on its nulls is lost when the representative fails the floor.
- Pruning's comparison does not reliably catch a feature that works only jointly with another;
  a `keep` protects it.

Still to measure:
- Whether the budgets of 60 and 200 are enough. On the canonical card frame, 60 trials over the
  four families (15 each) took 482 s of search with 50 final features (404 s with 38), and
  three families found their best configuration at their last trial; 200 has not been run.
- Across machines, the same trials and model under a trial budget (the pre-release run).
- Whether an integer range's upper bound is ever drawn (FLAML's bound is exclusive, so the
  space passes `high + 1`).
- Only if someone wants `intermediate` as LightGBM's default: one run each way on `dev`.
- Selection's seconds at bank size. Measured: 2 to 4 seconds on the `dev` preset, and 16
  seconds on the canonical one (257,338 train rows, 55 columns with the noise, the two
  comparison fits included); a wide frame with candidates is not measured on real-size data.
