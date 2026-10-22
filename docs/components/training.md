# Training
**Status:** legacy-only · **Legacy:** `src/run.py`, `src/dataset.py`, `src/calibration.py`, `src/contract.py`
**Related:** [dataset](dataset.md) · [feature ledger](feature_ledger.md) · [evaluation](evaluation.md) ·
[config](config.md) · [lifecycle](lifecycle.md) · [monitoring](monitoring.md) (drift reference) · D-030, D-031, D-032, D-037,
D-049, D-050, D-051, D-052, D-054, D-078, D-080, D-082, D-083, D-093, D-094, D-096, D-104, D-106, D-117, D-120 · OD-27

## Purpose
Fit a model on the train split of the observation window, using only vetted features, through the
modelling path (FLAML in Phase 2; a predefined path joins in Phase 3, D-080). Write a local-tier
run with the frozen config, hashes and training metadata.

## Phase 2 requirements
1. **Due-diligence gate:** refuse to train unless EDA and Feature Checks artifacts exist for the same
   data-definition hash. Hands-off profiles run them first (D-031).
2. **One small model interface** (`fit`, `predict`, `describe`) returning a scikit-learn-compatible
   model bundle (encoder + model + calibration). Phase 2 builds the AutoML path only, as plain
   functions per family behind a dict of family → functions, shaped so a `Protocol` can wrap them
   unchanged when the predefined path and its trade-off chart arrive in Phase 3 (D-080, D-100).
   - **AutoML:** FLAML.
     - Estimator list and time budget, with optional per-learner budgets so one cheap learner can't
       consume the whole budget. M2's list: `lgbm`, `xgboost` and `catboost`, each with a verified
       non-pickle round trip; never the scikit-learn forests; a use case may restrict the list to
       one family (D-093, D-080).
     - Bounded search spaces.
     - Trial selection (D-106, D-120): Phase 2 relies on the client split between train and
       test, and builds no own CV loop around FLAML. No CV fold mixes a client's rows: FLAML gets
       the client groups as `groups`, plus `split_type="group"` for regression, whose automatic
       split stays by rows. For classification, passing `groups` turns the automatic split into a
       group split (verified in FLAML 2.7.0, `decide_split_type` in
       `flaml/automl/task/generic_task.py`). If spike 1 shows the group split fails with sample
       weights, a client-grouped holdout built from the same fold assignment goes in as
       `X_val` / `y_val` instead. An own client-grouped CV loop around the tuner is on the
       Phase 3 wishlist (D-121).
     - The framework encodes categoricals to integer codes before FLAML sees the frame, so FLAML's
       hidden transformer (it drops constant columns, fills `__NAN__` and recodes categoricals;
       verified on 2.7.0) is the identity. Inference calls the saved booster directly, never
       `AutoML.predict`. The bundle records the booster's feature names, and training fails loud
       if they differ from the resolved list. FLAML-specific; other paths handle their own (D-094).
   - **Predefined (Phase 3, D-080):** a named model family (e.g. LightGBM, CatBoost, XGBoost)
     tuned with Optuna.
     - Bounded, regularisation-friendly search spaces per family; early stopping; pruning.
     - An optional two-objective search (in-time metric vs overfitting gap), shown as a **trade-off
       chart**. The user (or a profile rule) picks a point, and the pick is recorded. The chart
       weighs train and test metrics; the validation month never chooses (D-083).
3. **Metric from the decision:** the optimisation metric is derived from the declared business
   decision (D-032). The config template lists the options with when-to-use guidance. Metric names
   are validated against the engine's (T9).
4. **Overfitting guard:** the train–test gap (in-time, unseen clients) is reported for every run
   and may penalise a choice among trials or variants together with the test metric (D-083). The
   validation (OOT) set is never used to choose anything (§4.4).
5. **Automated feature selection** (automated mode): relevance pruning on the train split only.
   The rule comes from the per-task spec (D-050). Binary examples: a univariate AUC floor of ~0.515
   (a speed lever), importance-based pruning inside CV.
   Human `keep` decisions are respected, and every drop is recorded in the ledger.
6. **Categorical handling by the framework:**
   - levels are frozen from train;
   - rare levels (below a minimum count) → `__other__`; missing → `__missing__`;
   - at test, validation and inference, unseen levels → `__other__`, counted per column and reported
     (and monitored in production);
   - structural problems (a missing column, a changed type) fail loud.
7. **Contract checks** as owned by [dataset](dataset.md), on the true population before any
   sampling (§4.8).
8. **Sampling and row budget** as in [dataset](dataset.md), without sample weights in Phase 2
   (D-123). Calibration comes from the per-task spec (§4.7, D-049). Binary, as one chain (D-094): raw score → general calibration (Platt in M2,
   isotonic in M3; optional, on by default when the decision is `probability`), fitted on the
   framework's own client-grouped out-of-fold predictions that refit `best_config`, since FLAML
   exposes none (kept under D-106) → the prior-shift offset in logit space whenever sampling
   happened, from the effective (weighted) training rate. Parameters are stored as plain numbers
   with the framework's own predict code, never as scikit-learn objects. Retail propensity use cases
   default to the `probability` decision, because their scores are compared across products
   downstream; correct calibration is a release requirement, not an option (D-104,
   [inference](inference.md) requirement 4).
9. **Record what the engine actually did:** best estimator and config, trials per learner (FLAML
   `config_history`, T14), seeds, and the time spent.
10. **Runtime levers** in config, with profile defaults: budget, learners, trials, sampling. The
    default budget is a trial count (`max_iter`) plus seeds, so a rerun of the frozen config gives
    the same model; a time budget is an option, labelled "reproducible to the recipe, not the
    model" (D-099).
11. **Versioned model bundle** (D-051, D-078): every part as plain data, never pickle. Encoder
    levels and calibration as JSON; the model in a lossless non-pickle format, JSON where possible,
    with library versions recorded. A model family is offered only once that format is verified for
    it on the pinned versions (a round trip giving identical predictions), so FLAML's estimator list
    is limited to such families. `model_hash` is a hash over the per-part hashes (encoder, model,
    calibration with the prior-shift offset, metadata), so a refit with recomputed calibration gets
    a new hash (D-094); the bundle also carries the recipe and its `recipe_hash` (D-096).
12. **Drift reference** (D-054): feature distributions of the training window and a score
    distribution, computed in Spark on the true eligible population (not the sample), saved with
    the run for [monitoring](monitoring.md).
13. **Optional refit** (D-052), off by default: on all clients (train + test) or on an extended
    window (the latest months whose labels have matured). The refit is a new run linked to its
    evaluated parent, with the same features and hyperparameters and calibration recomputed. Its
    card shows the parent's evaluation metrics and says it is a refit. Retraining in production
    could run this refit from the promoted recipe (OD-27).

## Design constraints
- The engine never sees the raw feature universe; evaluation happens outside it (§4.5).
- No hidden retries or silent fallbacks.
- Classes are allowed here where they earn it: the scikit-learn-compatible wrappers, and from
  Phase 3 the model-interface `Protocol` (`CLAUDE.md` §1 rule 2, D-100).
- Training is single-node, on a sample built in Spark ([dataset](dataset.md)). A Spark-native engine
  would be another entry behind the interface; it is not built in Phase 2.

## Lessons from the crunch
T9, T14; downsampling, calibration and FLAML-search lessons in `docs/context/lessons.md`.

## Interface
*(fill when built)*

## Open questions
- Verify FLAML 2.7 + xgboost 3.2 before enabling xgboost by default.
- Spike 1: verify FLAML 2.7's group split on the synthetic data (no sample weights in Phase 2,
  D-123); the fallback is in requirement 2 (D-120).
- Verify the Optuna 5.0 API (multi-objective, pruning) when first used (Phase 3).
- The default pick rule on the trade-off chart for hands-off profiles (Phase 3).
- Calibration under uniform negative downsampling ([dataset](dataset.md)): one keep fraction for
  the whole window, so one prior-shift offset from the sampled vs true rate holds for every month
  (D-117). Verify it against the synthetic oracle (reliability curves). Weighted sampling, whose
  offset is zero (D-049), is on the Phase 3 wishlist (D-123).
- A lossless non-pickle format per model family on the pinned versions (D-078), all unverified
  and all three needed in M2 (D-093): XGBoost's JSON; LightGBM's text model (its JSON dump may
  not load back); CatBoost's JSON. Scikit-learn's forests (FLAML `rf`, `extra_tree`) have none
  without a new dependency (e.g. skops) or our own exporter and are never offered. Any
  non-executable plain-data format counts, JSON preferred (D-078).
