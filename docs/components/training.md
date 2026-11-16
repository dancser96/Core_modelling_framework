# Training
**Status:** designing (the spec settled 2026-11-13; to be built in M2.3 major step 2) · **Legacy:**
`src/run.py`, `src/dataset.py`, `src/calibration.py`, `src/contract.py`
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
  three selection rules (the cluster rule, a floor at 0.5 + 2 SE, importance pruning against five
  noise columns); calibration by Platt on the margin or beta for binary and a level factor for
  Tweedie and Poisson, with the prior-shift offset whenever sampling happened.
- **Run it:** `run_training(cfg, entity, env, spark)`, `python -m core_modelling run <config>
  --stages training evaluation`, or notebook `04_training.ipynb`. Sign off with `decide
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
  pruning, the fold models and the calibration all use the dataset's client folds (D-106).
- **FLAML only searches.** The framework's own `fit` trains every model it keeps, through
  `FAMILIES`, from the best configuration (D-140 (a)), so the bundle holds one native booster and
  a production retrain needs no FLAML.
- **The encoder comes first.** Every code is fixed before any library sees the frame, and
  FLAML's own transformer is switched off (T38; the encoder is [model
  bundle](model_bundle.md#the-encoder)'s).
- **Training writes, Evaluation reads.** Evaluation, the card and the sign-off view read only the
  run folder and the data (D-139 (b)).
- **The automation level acts in `run` only.** `run` at `autonomous` runs the missing upstream
  stages first; `run_training` itself trains or refuses, at both levels.

### How one run flows
1. Resolve the config; pass the gate (EDA and Feature Checks of the same data definition, the
   counts against EDA's); show the feature set in force.
2. `create_run` reserves the next number and writes `run.json`.
3. Collect the train frame with its folds and check the folds; fit and apply the encoder; refuse
   a constraint Training cannot apply and warn on a constraint against EDA's direction.
4. Select: the cluster rule, the floor, importance pruning.
5. Run one search per family on its budget and check each; take the best family and
   configuration by the fold metric.
6. Fit the K fold models at that configuration: the out-of-fold margins and contributions, the
   calibration, the out-of-fold metric.
7. Fit the final model on every train row; store the in-sample AUC; write the bundle, self-check
   it and run the monotone grid check on the reloaded bundle.
8. Build the per-run ledger, the `stage2/` copies, the sign-off table and the explanation sample.
9. Write `training/` last, the commit marker, then the `run` entry.

### Function structure
`src/core_modelling/training/`:
- `search_space.py` (the ranges, starts, fixed switches and refused names as data) and
  `search.py`: the budget split, the space, the splitter, the metric, one search per family and
  its check;
- `selection.py`: the three rules;
- `fold_models.py` and `calibrate.py`: the out-of-fold margins and the calibration;
- `ledger_run.py` and `views.py`: the per-run ledger, the sign-off table, the search summary;
- `run.py`: `run_training`, which orchestrates only.

It uses `statistics/calibration.py` (Platt, beta, the offset, the level factor),
`reporting/explain_charts.py`, `model/` (the encoder, the families, the bundle), `runs.py`,
`dataset/folds.py`, `ledger.py` and `artifacts.py`.

### How it is checked
Light tests (`CLAUDE.md` §7), constructed frames without Spark wherever pandas suffices:
- **The invariants:** the frames Training asks for hold no test row; no fold row is in the frame
  its fold model was fitted on; a held feature is refused; the offset is zero without sampling.
- **The search:** the exact trial count per family, with a remainder and with `training.trials`;
  every ranged leaf reaches FLAML with a start; a search that did not move fails; the splitter's
  folds are ours; a constraint reaches the trial models; an infinite fold metric fails.
- **Selection:** the rules' order; a kept feature measured and never dropped; pruning undone when
  the loss rises; no noise column leaves the function.
- **The run:** two runs give one `model_hash`; the final model equals the search's best model on
  the encoded frame; a crash before `training/` leaves a run listed as incomplete; `run` at
  `autonomous` runs the missing stages and `run_training` alone fails loud.
- **On `dev`** (marked `slow`): the four families through the search with their round trips; the
  calibration level within 10% with and without `negative_downsampling` (`acceptance`).

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
   tokens (`read_ledger(…, expect={"eda": …, "feature_checks": …})`).
2. **The counts:** Training recomputes the per-period `eligible_rows`, `known_target` and
   `positive_rows` on every client in the window, before the client split, and fails loud when
   they differ from EDA's population table in `eda.json` (D-088). It compares the kinds in the
   ledger with the panel's schema and fails loud on a changed type.
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
5. **The automation level** (D-132): at `autonomous`, `run` runs EDA and Feature Checks when
   their artifacts are missing and then Training; `run_training` called alone fails loud
   at both levels, naming `run` as the fix. A person can stop between stages at either level and
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
   clients than folds.
5. Below 100 converting clients or 200 events the log warns: the fold metric is noisy at this
   size (about ±0.06 AUC per fold at 20 events); set `fold_repeats: 3`, keep the trial budget
   small, and read differences between runs against their intervals. It never advises fewer
   folds, which bias the estimate down and buy no precision [Kohavi95].

### The encoder and the families
The encoder's codes, the four families' functions, their formats and the loader's pins are
[model bundle](model_bundle.md#the-encoder)'s. What Training decides:
1. **The kinds:** each feature's kind is the ledger's `kind` (EDA's, after `features.kinds`); a
   categorical named in `features.order` is `ordered`, every other categorical `unordered`.
   `features.order` is filtered to the features being encoded, and the bundle's encoder holds the
   final features only.
2. **Fitted on train only,** once, before selection; every later fit and every scoring uses the
   same codes. Levels are kept at `training.categoricals.min_level_client_count` distinct train
   clients; `training.categoricals.unordered` passes the codes declared (`native`) or as numbers
   (`codes`).
3. **The families searched** are `training.estimator_list` (all four by default; one entry fixes
   the family). `fixed_params` gives the constants the search and the fit must share: the
   objective, the declared categoricals, the constraints in the library's form, LightGBM's
   `basic` method, CatBoost's `allow_writing_files=False` (T5).
4. **A warning** when a constrained feature has nulls and `catboost` is listed: CatBoost counts a
   null as the smallest value, inside the constraint (a correct constraint cost it 0.011 AUC on a
   feature with 10% nulls, measured). CatBoost's fold loss carries the cost.
5. **The frame's column order is checked before every fit.** The constraints and XGBoost's
   feature types are positional vectors in the encoder's order, and a frame in another order
   trains with the constraint on the wrong feature, without a word. So every fit, the search's
   included, receives the frame `encode_frame` returned, and Training runs `check_order` on it
   once before the search and before each of its own fits, also after each selection drop. The
   pruning frame, which holds five noise columns, is checked against an encoder extended by
   them. As a backstop every family's `fit` refuses a positional vector whose length is not the
   frame's column count.
6. **Every parameter name is checked before the first trial** (`check_params`): LightGBM and
   XGBoost ignore a misspelt parameter silently once their logging is off, so a name outside the
   family's allowed set fails loud, whether it comes from `training.search_space` or from the
   search.
7. **What reaches FLAML how** (measured on the pinned versions): the objective, the seed and the
   constraints pass as search-space constants; LightGBM's `categorical_feature` and CatBoost's
   `use_best_model` only as fit arguments; the thread count only through `AutoML.fit(n_jobs=)`.
   FLAML's CatBoost wrapper declares categoricals only from pandas `category` columns and passes
   `cat_features=[]` itself, while LightGBM and XGBoost need the integer codes, so the search
   gets one frame per family; a `category` column gives CatBoost a model bit-identical to the
   integer codes.

### The search
1. **FLAML only searches** (D-140 (a)); the best configuration is refitted by the framework.
2. **One search per family on its own trial budget** (D-140 (b)): `split_budget` divides
   `training.max_iter` equally over the listed families and gives the remainder, one trial each,
   to the first families of the list (60 over four is 15 each; 62 is 16, 16, 15, 15), unless
   `training.trials` names every listed family's count and replaces `max_iter`. FLAML's own
   selector starved a family (9 of 60 trials) and ignores the seed; a joint round-robin search
   equals separate searches (measured).
3. **The optimiser is FLAML's local search (CFO):** from a start it steps in a random direction,
   keeps an improving step, tries the opposite one, and shrinks the step when neither helps.
4. **Always cross-validated on our folds:** `fold_splitter` gives FLAML the dataset's folds as a
   splitter object, so every trial is fitted R × K times (R dealings of K folds) and its loss is
   the mean over them. Nothing else is held out, and no fit has an inner early-stopping split.
5. **FLAML's `fit` runs with five fixed switches** (D-140 (b)), each fixed because, left free, it
   would break a promise:

   | Switch | Left free it would | Why fixed |
   |---|---|---|
   | `auto_augment=False` | copy a class under 20 rows until it has 20 | it changes the class balance behind the calibration's back; it never acts with our splitter, so this makes that explicit |
   | `ensemble=False` | stack the best learners into one ensemble | the bundle holds one booster in one native file (D-051) |
   | `early_stop=False` | end the search when FLAML judges it converged | a trial budget would no longer mean that many trials |
   | `sample=False` | train early trials on a subsample | it acts only under a holdout; fixed so behaviour cannot change with the evaluation method |
   | `log_type="all"` | log improving trials only | the trials table needs every trial |

   A use case that needs one of them needs a code change with a reason.
6. **`skip_transform=True` on every FLAML fit,** always, and not a config field (T38): given a
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
    `decision.metric: tweedie_deviance`.
11. **CatBoost's tree count is searched** with `use_best_model` off, so CatBoost trains exactly
    the count it is given: every family's tree count is tuned on the client folds.
12. **What repeats:** under a trial budget, the same trials, best configuration and predictions
    at 1 or 2 threads, with and without load (measured). `training.seed` drives the search's
    seed, the fold salt and, through constants, the libraries' seeds. A time budget
    (`training.time_budget_s`, per family) does not repeat, because FLAML then picks by measured
    seconds; the run says "reproducible to the recipe, not the model" in its log, report and
    card, and the final fit stays the framework's own, untruncated. Across machines: unverified,
    checked at the pre-release run.
13. **An infinite fold metric fails loud:** FLAML turns a failed fold metric (a fold without a
    positive under `roc_auc`) into a loss of infinity with only a logged warning.
14. **The trials table** is read from FLAML's log of each family, saved in `training/`: one row
    per trial with its family, configuration, fold metric, seconds and whether it improved (no
    train loss per trial). Per family `training.json` holds the trials run, the seconds in total,
    per trial (median) and of the longest trial, the best fold metric and the trial that reached
    it, and the family's share of the run's time; a chart draws the best fold metric so far
    against the cumulative seconds, one line per family. A quick run thereby tells a person how to
    spend a main run's budget through `training.trials`; seconds enter no hash and no test.
15. **The best family and configuration** are the lowest mean fold loss over every family's
    best trial.
16. **The class-weight names are refused** in `training.search_space` at load, in any case:
    `scale_pos_weight`, `is_unbalance`, `class_weight`, `class_weights`, `auto_class_weights`;
    every family's `fit` refuses them and their library aliases too. Each counts a
    positive row several times, so the model believes positives more common than they are and
    its probabilities come out too high [LGBM-P][XGB-T]. The calibration undoes exactly one change
    of the class balance, the declared sampling with its one keep fraction (§4.12); a weight
    would be a second change it does not know about. The message points to `sampling:
    negative_downsampling`.

### Selection
Automated selection runs at every level, on the train split only, before the search (D-140 (e)).
Boosted trees lose little accuracy to irrelevant features (0.004–0.008 AUC to 390 noise columns,
measured [Grinsztajn22]); selection pays in search time, which grows in a straight line with the
features, and in a sign-off list a person can defend.
1. **Three rules, in this order:**
   1. **The cluster rule** (`training.selection.cluster`): one representative per redundancy
      cluster of the Stage 2 ledger (`cluster`, label-free but computed with test clients, so the
      ranking inside a cluster is on the train split only, D-030). The members it drops are
      recorded under the representative's `represents`.
   2. **The floor** (`training.selection.floor_z`, default 2): a feature is dropped when its
      train concordance is below 0.5 + z · SE, the SE on effective train clients as EDA's rules
      read it (about 0.509 at 3,870 events, 0.533 at 300). The concordance is the plain one, or
      the best-order one for a feature EDA marked `non_monotone` (that marker saw test labels, the
      cost D-030 states). `null` switches the floor off.
   3. **Importance pruning** (`training.selection.prune`): does the model still need the feature
      once the others are there?
2. **Train-split statistics only,** on the train frame as collected: a rank statistic is
   unbiased under label-dependent sampling. EDA's all-client ranking is never read (D-030).
3. **A `keep` is measured, never dropped:** a kept feature shows its value and whether the rule
   would have dropped it; it stays a cluster member, so the representative is chosen with it in
   the comparison, and both stay when the kept one loses.
4. **The pruning, step by step:**
   1. Add five seeded columns of random numbers to the encoded train frame.
   2. Fit the K fold models (the first dealing) with LightGBM at its start configuration,
      whatever families are searched, under the run's constraints; take each feature's
      out-of-fold contribution share.
   3. The candidates to drop are the features that do no better than the best noise column;
      a `keep` survives.
   4. Fit the fold models again without the candidates. The drops stand when the loss did not
      rise: the decision's metric as a loss, out of fold, the mean over the folds. Otherwise
      nothing is pruned, the candidates' outcome is `undone` and the run says so.
   5. No noise column leaves the function; the search runs on what is left.
   Two rounds of K fits cost a minute or two at the card's size (estimated).
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
   out-of-fold margins and contributions and are discarded (D-094 (b)). Calibration is fitted on
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
6. **Every binary run stores the out-of-fold log loss of `none`, `platt` and `beta`,** whatever
   the decision, so the cost of the choice is visible; a person who sees `beta` clearly better
   sets it with one entry and trains again.
7. **The regression level factor** (`mean`) is the total observed over the total predicted on
   the out-of-fold predictions. It is stored with its interval (a client bootstrap of 200
   replicates, the weights drawn by the client-hash rule Evaluation uses) and the number of
   rows that hold half of the target's total, and is never winsorised: capping the target made the
   level worse than no correction (0.90 against 1.00, measured). When the interval is wider than
   ±5% the log warns: the level of this target is decided by a few rows; the factor, and any
   model's level, is uncertain; consider a capped target. The method never switches itself.
8. **The formulas** (the score per link and method, the parameters' shape) are [model
   bundle](model_bundle.md#the-calibration-and-the-output-columns)'s; `apply_calibration` is the
   one code that applies them.
9. **The out-of-fold metric** is the decision's metric on the out-of-fold scores, with AUC (the
   concordance for regression) beside it ([below](#the-honesty-notes)).
10. **Level metrics are taken before the offset.** Under `negative_downsampling` the
    out-of-fold rows are at the sampled rate while `score` is at the true rate, so the
    out-of-fold log loss of `none`, `platt` and `beta` and the out-of-fold metric are computed
    on the calibrated margin without the offset. A fold's average precision and log loss are
    at the sampled prevalence and are never compared with the test split's.
11. **The offset follows the method:** zero under `client_sample` and without sampling, by
    rule, never from the sampling record's two rates, which differ under `client_sample` by
    sampling noise.
12. **A fit that reverses the order stops Training.** The bundle refuses a calibration that
    would reverse or flatten the model's order (a Platt slope at or below zero); Training
    fails loud there, saying the model is anti-predictive out of fold. Its own out-of-fold
    scores are checked for non-finite values, as `score_frame` checks every score.
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
   stored for the train–test gap Evaluation shows (D-106).
4. **The bundle** is written by `write_bundle` and self-checked by `check_bundle` on 1,000 train
   rows ([model bundle](model_bundle.md#how-one-bundle-is-written-loaded-and-scored)); then the
   grid check runs on the reloaded bundle ([above](#monotone-constraints)).

### What Training writes
The run folder's layout is [model bundle](model_bundle.md#the-run-folder)'s. Training writes:
1. `run.json` first, through `create_run` (step 2 of the flow), never again.
2. `bundle/` (step 7).
3. `ledger_run.parquet` with its sidecar ([feature ledger](feature_ledger.md#the-per-run-part)).
4. `stage2/`: the final features' Stage 2 ledger rows, EDA's bin edges and shares per period and
   EDA's lift table, so an EDA rerun never changes this run (D-139 (b)).
5. `training/`, last, through a temporary folder like every stage folder (D-136):
   - `training.json`: the stamp, the identity, the flat `summary` block that `list_runs` and
     `show_run` display (the family, the feature count and signature, the trials, the
     out-of-fold metric, the seconds, `recipe_hash`, `model_hash`), the per-family search table, the space each family searched,
     the out-of-fold metric, the in-sample AUC, the step seconds (selection with pruning, the
     search per family, the fold models with calibration, the final fit, the bundle with its
     self-check) and the warnings;
   - `tables/`:

     | Table | Grain | Columns |
     |---|---|---|
     | `trials` | one row per trial and family | family, trial, configuration, fold metric, seconds, improving |
     | `selection` | one row per feature and rule | feature, rule, value, threshold, outcome |
     | `oof` | one row per train row as trained | the keys, `cv_fold`, `target`, `margin`, `score_raw`, `score` |
     | `explanation_sample` | one row per sampled train row: 5,000 seeded rows, or every row when train has fewer | the keys, the raw feature values, the out-of-fold contributions per feature |
     | `calibration` | one row per method considered | binary: `none`, `platt`, `beta` with its parameters, its out-of-fold log loss, whether it is the bundle's, and the true and sampled rates with the offset; regression: the factor, its interval, the rows holding half of the total |
     | `signoff` | one row per feature | [below](#the-sign-off-view) |

   - FLAML's log of each family; `resolved_config.yml`; `log.json`, as in every stage folder
     (D-136).
6. Then the `run` entry of stage `training` in the audit log, with the run number and no
   `periods`, so a Training run never blocks moving the validation period (D-088).

A folder without `training/` is a crashed run, listed as incomplete; its number stays taken while
the folder exists ([model bundle](model_bundle.md#requirements-and-design-constraints)). Training writes no drift reference: Evaluation does, from `stage2/` (D-054).

### The sign-off view
1. **Train-only evidence** (D-031): its table and charts come from the out-of-fold contributions
   and the explanation sample, so it is readable right after training and needs no evaluated run.
2. **The table's order:** the final list by out-of-fold contribution, each with its share and
   the running total, the model's direction beside EDA's and whether they agree, its declared
   constraint and the wrong-sign mark, the cluster members it represents, its source, Feature
   Checks' notes and any flag a person kept with its reason; then the held features with their
   open flags, the excluded ones with their reasons, and the constrained features "declared, not
   in the model".
3. **Where it shows:** notebook 04 and a section of the model results report; notebook 05 guides
   the sign-off itself.
4. **What the `sign_off` entry covers:** the run, the feature signature and the final list; it
   covers every run of the same data definition with the same signature, earlier ones
   included (a person defends a feature list), and the view of
   such a run says which run was signed. Rejecting a feature is an `exclude` entry with stage
   `sign_off` and a retrain ([config](config.md#decision-audit-log-d-125), D-125). `register`'s
   check is M2.4's.

### The honesty notes
1. **The out-of-fold metric is optimistic:** the features and the configuration were chosen on
   the same folds. The test split is the first honest number.
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
- `training/search_space.py`: rules as data (the bounded ranges and starts per family, the five
  fixed switches, the refused names); `training/search.py`: `split_budget`, `build_search_space`,
  `fold_splitter`, `search_metric`, `search_family`, `check_search`.
- `training/selection.py`: `apply_cluster_rule`, `apply_floor`, `prune_by_importance`,
  `select_features`.
- `statistics/calibration.py`: `fit_platt`, `fit_beta`, `prior_shift_offset`, `level_factor`;
  `training/fold_models.py`: `fit_fold_models`; `training/calibrate.py`: `calibrate`; the
  calibration entries of `TASK_SPECS` in `tasks.py`.
- `reporting/explain_charts.py`: `importance_bar`, `beeswarm`, `waterfall`, `dependence`, drawn
  from the libraries' own contributions, no `shap` import.
- `training/ledger_run.py`: `build_run_ledger`, `save_run_ledger`, `read_run_ledger`,
  `signoff_table`; `training/views.py`: `search_summary`, `search_progress_chart`,
  `selection_view`, `calibration_view`, `signoff_view` (report blocks for notebook 04 and the
  report).
- `training/run.py`: `run_training`; its lines in the top-level `run.py` (`STAGES`, the
  `autonomous` rule).
- The call flow of one run is [How one run flows](#how-one-run-flows).
- Reading order for review: `run_training` (the chain), `check_search` and
  `build_search_space` (T39), `prune_by_importance`, `calibrate`, `signoff_table`.

### Interface
Public: `run_training` (with `sign_off` in `runs.py`, [model bundle](model_bundle.md#interface));
CLI: `run --stages training evaluation`, `decide --sign-off --run`; the config section:
[config](config.md#the-modelling-fields-stage-3). The private functions, as planned:

```python
def run_training(cfg, entity, env, spark) -> StageResult: ...   # public

def split_budget(cfg) -> dict[str, int]: ...
def build_search_space(family: str, cfg, fixed: dict) -> dict: ...
def fold_splitter(folds: pd.DataFrame) -> object: ...
def search_metric(cfg) -> str | Callable: ...
def search_family(X: pd.DataFrame, y: np.ndarray, folds: pd.DataFrame, family: str,
                  space: dict, trials: int, metric: str | Callable, seed: int,
                  log_path: str) -> tuple[dict, pd.DataFrame]: ...
def check_search(trials: pd.DataFrame, starts: dict) -> None: ...

def apply_cluster_rule(ledger: pd.DataFrame, features: list[str], kept: list[str]) -> pd.DataFrame: ...
def apply_floor(ledger: pd.DataFrame, features: list[str], kept: list[str], floor_z: float) -> pd.DataFrame: ...
def prune_by_importance(X: pd.DataFrame, y: np.ndarray, folds: pd.DataFrame, kept: list[str],
                        task: str, seed: int) -> pd.DataFrame: ...
def select_features(…) -> tuple[list[str], pd.DataFrame]: ...

def fit_platt(margin: np.ndarray, y: np.ndarray) -> dict: ...
def fit_beta(margin, y) -> dict: ...
def prior_shift_offset(true_rate: float, sampled_rate: float) -> float: ...
def level_factor(predicted: np.ndarray, y: np.ndarray, clients: np.ndarray) -> dict: ...
def fit_fold_models(X, y, folds, family: str, params: dict, task: str) -> tuple[np.ndarray, np.ndarray]: ...
def calibrate(margins: np.ndarray, y: np.ndarray, clients: np.ndarray, cfg, rates: dict) -> dict: ...

def importance_bar(contributions: pd.DataFrame, compare: pd.DataFrame | None = None,
                   top: int = 15) -> go.Figure: ...
def beeswarm(contributions: pd.DataFrame, values: pd.DataFrame, top: int = 15,
             clients: int = 1500, seed: int = 0) -> go.Figure: ...
def waterfall(contributions: pd.Series, base: float, values: pd.Series, shown: int = 9) -> go.Figure: ...
def dependence(contributions: pd.Series, values: pd.Series, colour: pd.Series | None = None,
               lift: pd.DataFrame | None = None) -> go.Figure: ...

def build_run_ledger(selection: pd.DataFrame, description: dict, contributions: pd.DataFrame,
                     encoder_shares: pd.DataFrame, monotone: dict[str, str],
                     stage2: pd.DataFrame) -> pd.DataFrame: ...
def signoff_table(run_ledger, stage2, entries) -> pd.DataFrame: ...
def search_summary(trials: pd.DataFrame) -> pd.DataFrame: ...
def search_progress_chart(trials) -> go.Figure: ...
```

`save_run_ledger`, `read_run_ledger`, `selection_view`, `calibration_view` and `signoff_view`
get their signatures when built.

### Lessons from the crunch
T5 (CatBoost writes files), T9 (FLAML's metric names), T14 (reading FLAML's trials), T38
(FLAML's hidden imputation), T39 (a search space without starts); the crunch's downsampling and
calibration lessons in `docs/context/lessons.md`.

### Sources
The measurements on the pinned versions are in the stage's research note, which moves to
`docs/guides/modelling_faq.md` at the stage's close.
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
To check before or during the build (m2.0 and m2.8):
- The framework's own fit equals FLAML's model for each family: CatBoost under the tree-count
  rule, every family with declared categoricals, and a Tweedie model.
- FLAML with our splitter, declared categoricals, a ranged space with starts and a monotone
  constraint, all together (each is verified alone or in pairs).
- The bounded ranges against FLAML's own on `dev`, judged against the oracle, with the four
  families' fold loss and seconds, before they become defaults.
- The seconds per family on the canonical card frame, to confirm the budgets of 60 and 200.
- Declared categoricals against numeric codes on `dev`, one run each way; the synthetic
  categoricals reaching Training have at most 10 levels, so this says nothing about high
  cardinality.
- Poisson, the absolute error and Huber through FLAML's search, with the deviances as custom
  metrics (Tweedie ran).
- A larger trial budget repeats the smaller budget's trials as its first trials, so that a main
  run continues a quick run's search.
- scikit-learn 1.8's unpenalised logistic regression, for Platt and beta.
- Only if someone wants `intermediate` as LightGBM's default: one run each way on `dev`.
