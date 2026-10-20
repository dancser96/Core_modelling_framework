# Training
**Status:** legacy-only · **Legacy:** `src/run.py`, `src/dataset.py`, `src/calibration.py`, `src/contract.py`
**Related:** [dataset](dataset.md) · [feature ledger](feature_ledger.md) · [evaluation](evaluation.md) ·
[config](config.md) · [lifecycle](lifecycle.md) · [monitoring](monitoring.md) (drift reference) · D-030, D-031, D-032, D-037,
D-049, D-050, D-051, D-052, D-054, D-078, D-080 · OD-22, OD-27

## Purpose
Fit a model on the train split of the observation window, using only vetted features, through one of
two modelling paths. Write a local-tier run with the frozen config, hashes and training metadata.

## Phase 2 requirements
1. **Due-diligence gate:** refuse to train unless EDA and Feature Checks artifacts exist for the same
   data-definition hash. Hands-off profiles run them first (D-031).
2. **Two modelling paths behind one small model interface** (`fit`, `predict`, `describe`). Both
   return a scikit-learn-compatible model bundle (encoder + model + calibration). Phase 2 builds
   the AutoML path only; the predefined path and its trade-off chart come in Phase 3 (D-080).
   - **AutoML:** FLAML.
     - Estimator list and time budget, with optional per-learner budgets so one cheap learner can't
       consume the whole budget.
     - Bounded search spaces.
     - CV grouped by client.
   - **Predefined:** a named model family (e.g. LightGBM, CatBoost, XGBoost) tuned with Optuna.
     - Bounded, regularisation-friendly search spaces per family; early stopping; pruning.
     - An optional two-objective search (in-time metric vs overfitting gap), shown as a **trade-off
       chart**. The user (or a profile rule) picks a point, and the pick is recorded. Whether the
       chart may use the test metric, or only client-grouped CV inside train, is under review
       (OD-22; leaning: CV only).
3. **Metric from the decision:** the optimisation metric is derived from the declared business
   decision (D-032). The config template lists the options with when-to-use guidance. Metric names
   are validated against the engine's (T9).
4. **Overfitting guard:** the train–test gap (in-time, unseen clients) is reported for every run;
   whether it may gate is part of OD-22. The validation (OOT) set is never used to choose anything
   (§4.4).
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
8. **Sampling and row budget** as in [dataset](dataset.md). Calibration comes from the per-task spec
   (§4.7, D-049). Binary:
   - a prior-shift offset whenever sampling happened, from the effective (weighted) training rate;
   - a general calibration step (e.g. Platt or isotonic): optional, on by default when the decision
     is `probability`, fitted on client-grouped out-of-fold predictions inside train.
9. **Record what the engine actually did:** best estimator and config, trials per learner (FLAML
   `config_history`, T14), Optuna trials, seeds.
10. **Runtime levers** in config, with profile defaults: budget, learners, trials, sampling.
11. **Versioned model bundle** (D-051, D-078): every part as plain data, never pickle. Encoder
    levels and calibration as JSON; the model in a lossless non-pickle format, JSON where possible,
    with library versions recorded. A model family is offered only once that format is verified for
    it on the pinned versions (a round trip giving identical predictions), so FLAML's estimator list
    is limited to such families.
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
- Classes are allowed here where they earn it: the model-interface `Protocol` and the
  scikit-learn-compatible wrappers (`CLAUDE.md` §1 rule 2).
- Training is single-node, on a sample built in Spark ([dataset](dataset.md)). A Spark-native engine
  would be another entry behind the interface; it is not built in Phase 2.

## Lessons from the crunch
T9, T14; downsampling, calibration and FLAML-search lessons in `docs/context/lessons.md`.

## Interface
*(fill when built)*

## Open questions
- Verify FLAML 2.7 + xgboost 3.2 before enabling xgboost by default; verify FLAML grouped CV on 2.7.
- Verify the Optuna 5.0 API (multi-objective, pruning) when first used.
- The default pick rule on the trade-off chart for hands-off profiles.
- Calibration under the sampling options in [dataset](dataset.md) (OD-17): month-stratified negative
  sampling shifts the class balance per month, so the prior-shift offset must use the sampled vs true
  rate over the whole window (or per month); under outcome-stratified client sampling the
  weighted rate equals the true rate, so the offset is zero (D-049). Verify both against the
  synthetic oracle (reliability curves) before choosing the default.
- Platt vs isotonic for the general calibration step.
- A lossless non-pickle format per model family on the pinned versions (D-078), all unverified:
  XGBoost's JSON; LightGBM's text model (its JSON dump may not load back); CatBoost's JSON;
  scikit-learn's forests (FLAML `rf`, `extra_tree`) have none without a new dependency (e.g. skops)
  or our own exporter. Any non-executable plain-data format counts, JSON preferred (D-078).
