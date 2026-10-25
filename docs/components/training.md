# Training
**Status:** legacy-only · **Legacy:** `src/run.py`, `src/dataset.py`, `src/calibration.py`, `src/contract.py`
**Related:** [dataset](dataset.md) · [feature ledger](feature_ledger.md) · [evaluation](evaluation.md) ·
[config](config.md) · [lifecycle](lifecycle.md) · [monitoring](monitoring.md) (drift reference) · D-020, D-030, D-031, D-032, D-033,
D-037, D-049, D-050, D-051, D-052, D-054, D-082, D-083, D-088, D-094, D-100, D-106, D-117 · OD-27

## Purpose
Fit a model on the train split of the observation window, using only vetted features, through the
modelling path (FLAML in Phase 2; a predefined path joins in Phase 3, D-020). Write a local-tier
run with the resolved config, hashes and training metadata. Training writes artifacts only; the
model results report comes from [evaluation](evaluation.md) (D-036).

## Phase 2 requirements
1. **Due-diligence gate:** refuse to train unless EDA and Feature Checks artifacts exist for the same
   data-definition hash. The `autonomous` level runs them first (D-031). After training, a person
   signs off the model's final feature list before register, in one gate at every level (D-031,
   [feature checks](feature_checks.md)).
2. **One small model interface:** the function triple per family (`fit`, `predict`, `describe`,
   D-100 (a)), producing the model bundle (encoder + model + calibration); explainers such as SHAP
   get the booster (D-037). Phase 2 builds the AutoML path only, as plain
   functions per family behind a dict of family → functions, shaped so a `Protocol` can wrap them
   unchanged when the predefined path and its trade-off chart arrive in Phase 3 (D-020, D-100;
   [below](#phase-3-the-predefined-path)).
   - **AutoML:** FLAML.
     - Estimator list, and a trial budget (`max_iter`) plus seeds by default; a time budget is
       optional and labelled (requirement 10, D-094). Per-learner budgets, so one cheap learner
       can't consume the whole budget, are unverified for FLAML 2.7. M2's list: `lgbm`, `xgboost`
       and `catboost`, all three built in M2 together with their non-pickle round trips for
       promotion (D-051), since fewer would be less than the crunch; never the scikit-learn
       forests; a use case may restrict the list to one family (D-037, D-020).
     - Bounded search spaces.
     - Trial selection (D-106): Phase 2 relies on the client split between train and
       test, and builds no own CV loop around FLAML. No CV fold mixes a client's rows: FLAML gets
       the client groups as `groups`, plus `split_type="group"` for regression, whose automatic
       split stays by rows. For classification, passing `groups` turns the automatic split into a
       group split (verified in FLAML 2.7.0, `decide_split_type` in
       `flaml/automl/task/generic_task.py`). If the group split fails (spike 1), a client-grouped
       holdout built from the same fold assignment goes in as
       `X_val` / `y_val` instead. An own client-grouped CV loop around the tuner is on the
       Phase 3 wishlist (D-106).
     - The framework encodes categoricals to integer codes before FLAML sees the frame, so FLAML's
       hidden transformer (it drops constant columns, fills `__NAN__` and recodes categoricals;
       verified on 2.7.0) is the identity. Inference calls the saved booster directly, never
       `AutoML.predict`. The bundle records the booster's feature names, and training fails loud
       if they differ from the resolved list. FLAML-specific; other paths handle their own (D-094).
3. **Metric from the decision:** the optimisation metric is derived from the declared business
   decision (D-032). The config template lists the options with when-to-use guidance. Metric names
   are validated against the engine's (T9).
4. **Overfitting guard:** the train–test gap (in-time, unseen clients) is reported for every run,
   as AUC (a rank metric that downsampling leaves unbiased), its train side on the rows the model
   was fitted on, and used only by a sweep that picks,
   together with the test metric (D-083, D-106); penalising FLAML's trials by it waits for the
   Phase 3 trade-off chart. The validation (OOT) set is never used to choose anything (§4.4).
5. **Automated feature selection** (by rule, at every level): relevance pruning on the train split only.
   The rule comes from the per-task spec (D-050) and reads train-split statistics only, never EDA's
   all-client ranking (D-030). Binary examples: a univariate AUC floor of ~0.515 recomputed on the
   train split (a speed lever), importance-based pruning on the calibration step's client-grouped
   out-of-fold folds (D-106). Pruning comes first; then the final features are fixed and
   calibration's out-of-fold predictions are made on the same folds with them.
   People's `keep` decisions (audit-log entries the run replays, never config content, D-125) are
   respected, and every drop is recorded in the ledger.
6. **Categorical handling by the framework:**
   - levels are frozen from train;
   - rare levels (below a minimum count) → `__other__`; missing → `__missing__`;
   - at test, validation and inference, unseen levels → `__other__`, counted per column and reported
     (and monitored in production);
   - structural problems (a missing column, a changed type) fail loud.
7. **Contract checks** as owned by [dataset](dataset.md), on the true population before any
   sampling (§4.8).
8. **Sampling and row budget** as in [dataset](dataset.md): sampling only when the config declares
   it, without sample weights in Phase 2 (D-117). Calibration comes from the per-task spec (§4.7, D-049). Binary, as one chain (D-094): raw score → general calibration (Platt in M2,
   isotonic in M3; optional, on by default when the decision is `probability`), fitted on the
   framework's own client-grouped out-of-fold predictions that refit `best_config`, since FLAML
   exposes none (kept under D-106) → the prior-shift offset in logit space whenever sampling
   happened, from the effective training rate (in Phase 2, without weights, the sampled rate,
   D-049). Parameters are stored as plain numbers
   with the framework's own predict code, never as scikit-learn objects. The retail examples
   default to the `probability` decision through a comment in the example config, not a code
   default, because their scores are compared across products
   downstream; correct calibration is a release requirement, not an option (D-049,
   [inference](inference.md) requirement 4).
9. **Record what the engine actually did:** best estimator and config, trials per learner (FLAML
   `config_history`, T14), seeds, and the time spent.
10. **Runtime levers** in config, with level defaults: budget, learners, trials, sampling. The
    default budget is a trial count (`max_iter`) plus seeds, so a rerun of the resolved config gives
    the same model; a time budget is an option, labelled "reproducible to the recipe, not the
    model" (D-094).
11. **Versioned model bundle** (D-051): every part as plain data, never pickle once promoted. The
    sandpit (the local and registered tiers) may save any format, pickle included; the only pickle
    issue is the move to production, and what is promoted is never pickle. So `register` always
    writes the lossless plain-data model too (any other format may sit beside it), every registered
    version stays promotable without unpickling, and promote takes the plain-data model. Encoder
    levels and calibration as JSON; the model in a lossless non-pickle format, JSON where possible,
    with library versions recorded. A model family is offered only once that format is verified for
    it on the pinned versions (a round trip giving identical predictions), so FLAML's estimator list
    is limited to such families. `model_hash` is a hash over the per-part hashes (encoder, model,
    calibration with the prior-shift offset, metadata), so a retrain with recomputed calibration
    gets a new hash (D-094); the bundle also carries the recipe and its `recipe_hash` (D-052).
12. **Drift reference** (D-054): feature distributions of the training window and a score
    distribution, computed in Spark on the true eligible population (not the sample), saved with
    the run for [monitoring](monitoring.md).
13. **Retraining in production; no refit in the sandpit** (D-052, D-033): Phase 2 has no refit
    command in the sandpit, and the evaluated model is the one registered; the refit shape exists
    for the production retrain. By default, deploy moves the promoted bundle and production
    retrains its recipe on the same data definition (neither more clients nor a longer window)
    before it scores, linked to its evaluated parent by `parent_run_id`; deploying the fitted model
    without a retrain is also allowed. A Phase 2 production retrain keeps the window and the
    clients; only the inference month moves, since inference always runs on the latest month
    (D-052, D-088). Its parameters differ only because production data differs from sandpit data.
    Before it scores, it passes a check against its evaluated parent: label-free agreement on the
    inference month; its own test-split AUC and calibration (mean predicted against observed rate)
    per window month; per-month rows and positive events against the parent's EDA artifact; each
    within tolerances declared in the config before the run, never on the validation month.
    Failing keeps whatever production model is current and is recorded; at a first deploy the
    deploy fails loud (D-052). Whether production has the data and compute, determinism and what "deployed" records
    stay open (OD-27, M4). Retraining on moved or extended data (later months, all clients, a
    longer window) is on the Phase 3 wishlist.

## Design constraints
- The engine never sees the raw feature universe; evaluation happens outside it (§4.5).
- No hidden retries or silent fallbacks.
- Phase 2's model interface is plain functions (D-037, D-100 (a)); from Phase 3 a model-interface
  `Protocol` may wrap them (`CLAUDE.md` §1 rule 2, D-100).
- Training is single-node, on a sample built in Spark ([dataset](dataset.md)). A Spark-native engine
  would be another entry behind the interface; it is not built in Phase 2.

## Phase 3: the predefined path
A named model family (e.g. LightGBM, CatBoost, XGBoost) tuned with Optuna (D-020), behind the same
interface:
- bounded, regularisation-friendly search spaces per family; early stopping; pruning;
- an optional two-objective search (in-time metric vs overfitting gap), shown as a **trade-off
  chart**. The user (or a level's rule) picks a point, and the pick is recorded. The chart weighs
  train and test metrics; the validation month never chooses (D-083).

## Lessons from the crunch
T9, T14; downsampling, calibration and FLAML-search lessons in `docs/context/lessons.md`.

## Interface
*(fill when built)*

## Open questions
- Verify FLAML 2.7 + xgboost 3.2 before enabling xgboost by default.
- Spike 1: verify FLAML 2.7's group split on the synthetic data (no sample weights in Phase 2,
  D-117); the fallback is in requirement 2 (D-106).
- Verify the Optuna 5.0 API (multi-objective, pruning) when first used (Phase 3).
- The default pick rule on the trade-off chart at the `autonomous` level (Phase 3).
- Calibration under uniform negative downsampling ([dataset](dataset.md)): one keep fraction for
  the whole window, so one prior-shift offset from the sampled vs true rate holds for every month
  (D-117). Verify it against the synthetic oracle (reliability curves). Weighted sampling, whose
  offset is zero (D-049), is on the Phase 3 wishlist (D-117).
- A lossless non-pickle format per model family on the pinned versions (D-051), all unverified
  until spike 2 and all three needed in M2 (D-037): XGBoost's JSON; LightGBM's text model (its
  JSON dump may not load back); CatBoost's `.cbm` or its JSON (which one round-trips losslessly is spike 2's question). Scikit-learn's forests (FLAML `rf`, `extra_tree`) have none
  without a new dependency (e.g. skops) or our own exporter and are never offered. Any
  non-executable plain-data format counts, JSON preferred (D-051).
