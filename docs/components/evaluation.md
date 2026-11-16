# Evaluation
**Status:** designing (the spec settled 2026-11-13; to be built in M2.3 major step 3) · **Legacy:**
`src/evaluate.py`, `src/importance.py`, `src/analysis.py`
**Related:** [model bundle](model_bundle.md) (the run folder, the bundle, `score_frame`, the
hashes) · [training](training.md) (writes the run) · [dataset](dataset.md) (Evaluation's frames)
· [reporting](reporting.md) (the seventeen views, the charts, the model card) ·
[monitoring](monitoring.md) (the drift reference's format) · [config](config.md#the-modelling-fields-stage-3)
(every field) · [feature ledger](feature_ledger.md) · [lifecycle](lifecycle.md) · D-009, D-030,
D-032, D-035, D-036, D-038, D-050, D-054, D-083, D-098, D-100, D-139, D-141 · OD-12 is settled
by this spec (D-141)

Read it in three levels: Level 1 gives the essentials, Level 2 how the parts connect, Level 3
every detail. This doc owns the **scores table**, the **score cells**, the **metrics** and their
**intervals**; the views are [reporting](reporting.md)'s, the drift reference's format
[monitoring](monitoring.md)'s.

## Level 1: Summary
**What it does.** Judges one trained run on clients and a period it never saw, outside the
engine (`CLAUDE.md` §4.5), against declared baselines, and writes the model results report, the
model card and the drift reference. It is its own stage so it can be rerun on any trained run,
with today's evaluation settings, without training again (D-036, D-139).
- **In:** a run folder (the bundle, `stage2/`, `training/`) and the eligible test and validation
  rows in Spark. **Out:** `evaluation/` inside the run folder, a `run` entry naming the scored
  validation period, a `StageResult`.
- **Key numbers:** seventeen views, all on by default; 200 client-bootstrap replicates at 95%.
  Binary: AUC, average precision, log-loss and Brier skill, observed to expected, calibration
  slope and intercept. Regression: RMSE, MAE, R², the deviance, the concordance, predicted to
  observed. No gates, nothing "passed" or "failed".
- **Run it:** `run_evaluation(cfg, entity, env, spark, run=None)`, `python -m core_modelling run
  <config> --stages evaluation [--run r007]`, or notebook `05_evaluation.ipynb`.

## Level 2: How it fits together

### What drives what
- **The run drives everything.** Evaluation reads only the run folder and the data (D-139 (b)):
  the bundle scores, `stage2/` gives EDA's edges, lift and the Stage 2 ledger rows, `training/`
  gives the out-of-fold numbers, the trials and the sign-off table. An EDA rerun never changes
  what an older run's evaluation shows.
- **One scoring path.** Scores come from `score_frame` run inside Spark (`score_spark`), the
  function Training's self-check and Inference use ([model bundle](model_bundle.md)).
- **Every number is a function of the score cells,** a Spark aggregate of the scores, as EDA's
  numbers are of its counts table (D-141 (b)). Rows reach the driver only for the capped
  explanation sample.
- **The decision sets the emphasis:** the headline is `decision.metric` with AUC (regression: the
  concordance) beside it; `decision.baselines` names what the model is compared with; the slices
  come from `evaluation.slices`. All are declared before any result (`CLAUDE.md` §4.3).
- **The per-task spec** (`tasks.py`, D-050) supplies the metric function, the baselines' forms
  and which views a task cannot produce.

### How one run flows
1. Resolve the config (the audit log replayed).
2. Find the run: the latest run with the config's data-definition hash and Training's settings
   digest, or the one named by `run` within the same data definition; none is an error
   (`find_run`, D-139 (d)).
3. Load the bundle; `load_bundle` recomputes `model_hash` and refuses a difference.
4. Build the evaluation rows: `build_frames(…, "evaluation")` gives one Spark frame of test and
   validation with `part` and the strata columns ([dataset](dataset.md)); add the
   baselines' columns.
5. Score both parts in Spark and write the scores table.
6. Aggregate the score cells, with the client-bootstrap weights.
7. The metrics with intervals: pooled and per period, the slices per period, the strata,
   validation on test clients only.
8. The baselines comparison.
9. The explanation sample and its tables: contributions, the feature table, permutation
   importance per cluster, partial dependence and ICE.
10. The drift reference.
11. The report and the model card.
12. `evaluation/` written whole, replacing any earlier one.
13. The `run` entry with the scored validation period.

### The function structure in brief
- `statistics/metrics.py`, `statistics/bootstrap.py`: the metrics and intervals on cells (pure
  pandas).
- `evaluation/scores.py` (scoring, the scores, the weights, the cells), `baselines.py`,
  `tables.py` (the metric tables), `drift_reference.py`, `explain.py`, `views_explain.py`,
  `report.py` (`VIEWS`, `build_report`), `compare.py` (`compare_runs`), `run.py`
  (`run_evaluation`).
- `reporting/model_charts.py`, `reporting/explain_charts.py`, `reporting/card.py`
  ([reporting](reporting.md)).

### How it is checked
- Every metric against scikit-learn on the rows of constructed cells, within the binning's
  tolerance (the oracle, T32); no Spark.
- Spark tests on the `unit` preset, on the fixtures `trained_card` and `trained_regression`:
  the scores' grain, shared weights, the slices per period, the single feature chosen without a
  test row, a rerun leaving `training/` untouched.
- **Acceptance on `dev`** (marker `acceptance`, one shared run of the card config, `lgbm`, 15
  trials):
  1. the model beats the single-feature baseline on validation;
  2. the validation AUC is not above the oracle's on the same rows by more than two standard
     errors (D-100 (e));
  3. with a leak trap kept by a person, the oracle is beaten, so check 2 can fail;
  4. observed to expected is within 10%, with and without `negative_downsampling`.

## Level 3: Details

### Requirements and design constraints
1. **Outside the engine** (`CLAUDE.md` §4.5): Evaluation fits nothing a later step uses and
   chooses nothing. The calibration slope and the single feature's direction are measurements;
   the single feature is chosen on train (§4.4).
2. **The true population** (§4.8): test and validation are every eligible row of their parts,
   never sampled; sampling is Training's, on train only.
3. **Validation is reported, never chosen on** (D-083): every metric is shown on it;
   `compare_runs` computes no difference on it.
4. **Rank metrics are unaffected by calibration,** because every calibration map is strictly
   increasing; the reliability view reads `score`, on axes fitted to the data (T16).
5. **Average precision is not comparable across use cases:** its floor is the base rate; the
   report says so and shows the base rate beside it.
6. **Task-agnostic shapes** (D-050): the scores, the cells and the metrics table have one shape
   for both tasks; what differs is the per-task spec's entry.
7. **Fail loud** (D-035): a view the compatibility table declares compatible must work; a
   failure is an error. A view's runtime is never a reason to drop it.
8. **Reproducible** (§4.10): `evaluation.json` carries the run, `model_hash` and the config's
   identity, so every score traces to its model and config.

### Finding the run
- `find_run(env, resolved, entity, run=None)` takes the latest run whose data-definition hash
  and Training's settings digest equal the resolved config's ([config](config.md#the-modelling-fields-stage-3)
  owns what each digest covers). Changing an evaluation setting or a baseline therefore never
  orphans a trained run.
- `run="r007"` (CLI `--run r007`) evaluates any run of the same data definition with the current
  evaluation settings; a run of another data definition is refused. `--run` with several configs
  is refused.
- The rows are built with the bundle's feature list; a feature list that differs from the
  bundle's is refused, naming the difference.
- A part without rows fails loud, naming the part, when the score cells are aggregated: the
  rows are never collected, so nothing earlier would notice a test split or a validation
  period with no eligible row and a known target.

### Scoring and the scores table
1. **Inside Spark** (D-141 (a)): `score_parts` calls `score_spark`, which runs `score_frame` per
   partition with `mapInPandas`; the driver ships the bundle's bytes and each partition rebuilds
   the model once ([model bundle](model_bundle.md)). Nothing is collected.
2. **The chunked driver path** (collect a period or a hash bucket at a time, score with
   `score_frame`) is built only if the model libraries fail on the bank's executors.
3. **The scores table**, written by `write_scores`, parquet:
   - grain: one row per client, period and part;
   - columns: the keys (the unit id and the period), `part` (`test` or `validation`), the
     client's `split` (`train` or `test`), `target`, `margin`, `score_raw`, `score`, the strata
     columns, so the stratified tables, a re-render and `compare_runs` read the stored scores
     alone;
   - the test part holds test-split clients in the window's periods; the validation part holds
     every eligible client at the validation period, of both splits.
4. The baselines' score columns are computed on the same rows and aggregated into cells of their
   own.

### Score cells
Every metric reads one Spark aggregate of the scores, as EDA's statistics read its counts table
(D-135, D-141 (b)).
- **Grain:** one row per part, period, score bin and the columns of `by` (a stratum variable,
  the client's split for validation on test clients only); for regression also the target's
  bin, as EDA's cells have, which the concordance needs.
- **Columns:** the row count and the target sums the metrics need, and the same sums weighted by
  each bootstrap replicate's client weights (`client_weights`).
- The bin count and the exact columns are fixed when the metrics and the cells are built (M2.3
  major step 3); the tests measure the binning's tolerance against the row-level formulas.
- Row-level formulas (scikit-learn on the rows) are the tests' oracle only; the stage computes
  no reported metric on collected rows (permutation importance alone reads the explanation
  sample).

### Metrics
Every metric is computed per part, pooled and per period, and per stratum level, each with its
interval.

**Binary**
| Metric | Definition |
|---|---|
| Rows, positive events, base rate | the support; the base rate is the part's positive share |
| AUC | the probability that a random positive row scores above a random negative one, ties half |
| Average precision | the mean precision at each positive's rank; always shown with the base rate, its floor |
| Log-loss skill | 1 − log loss / log loss of the base-rate forecast (0 no better than the base rate, 1 perfect); the forecast is the unsampled train split's rate |
| Brier skill | 1 − Brier score / Brier score of the same base-rate forecast |
| Observed to expected | the sum of the target over the sum of `score`; 1 is the right level |
| Calibration slope and intercept | the coefficients of a logistic regression of the target on the logit of `score`; 1 and 0 when calibrated |

**Regression**
| Metric | Definition |
|---|---|
| Rows, non-zero rows, mean | the support |
| RMSE | the square root of the mean squared error |
| MAE | the mean absolute error; it rewards predicting the median, which under a skewed amount is far below the mean |
| R² | 1 − the squared error over the squared deviation from the part's mean |
| The deviance | the mean Tweedie deviance (at a fixed variance power of 1.5, whatever the objective's power) or the mean Poisson deviance, for the objective or the decision that names one |
| Concordance | EDA's scale: the share of pairs with unequal targets that the score orders correctly, ties half |
| Predicted to observed | the mean of `score` over the mean target; 1 is the right level |
| Capture at a slice | the share of the total amount held by the slice |

- **The headline** (report header, `list_runs`, the card) is `decision.metric` with AUC (the
  concordance for regression) always beside it.
- **Not built:** Gini and KS, which restate AUC on other scales; accuracy, F1 and a confusion
  matrix at 0.5, which mean nothing at a rare rate.

### Pooled and per period
D-098: a reader looks for one curve and one headline per split first, and a list is cut inside
one period.
1. **Pooled:** each part's curves (ROC, precision–recall, capture, reliability) and its headline
   are computed on all of its rows.
2. **Per period:** one table gives every metric per observation period, the validation period
   beside them and the mean of the periods in the last row; one line chart draws the headline
   metric per period with its interval. A period below `strata.min_events` is greyed, never
   hidden.
3. **A note, not a rule:** when the pooled AUC and the mean of the per-period AUCs differ by more
   than their intervals, the summary says the base rate moved inside the window and the
   per-period values are the ones to read.
4. **Observed to expected per period** on test and on validation, with no correction for a base
   rate that moves over time.

### Slices
1. Each slice of `evaluation.slices` is cut **inside each period**, then the periods' counts are
   added up, so one conversion is never counted up to `w` times in a slice.
2. A `top_pct` is a share of the period's rows in the part. A `top_n` is read as a share of the
   period's whole eligible population and cut at that share inside the part: 10,000 of 61,884
   eligible rows is the top 16.2% on validation and about 2,970 rows of a test period of 18,400.
3. A `top_n` above the period's population is "not available".
4. The cut is made on the cells, within the binning's tolerance.
5. Per slice: rows, events (regression: the amount) captured, capture (the share of all events or
   of the total amount), the slice's rate (precision) or mean, and lift (that over the part's
   rate or mean).
6. The capture view also shows fixed depths: 1, 2, 5, 10, 20, 30 and 50%.

### Intervals: the client bootstrap
Rows are not independent (a client is in up to six periods of test and positive in up to `w`),
so a formula that counts rows is too narrow, and none exists for lift, average precision or the
skill scores (D-141 (c)).
1. **Weights:** each client gets one Poisson weight (mean 1) per replicate, drawn from a hash of
   its id, the replicate number and a fixed salt (`client_weights`). A client's rows move
   together, and two runs scored on the same rows share the weights, so the interval of their
   difference is right.
2. **Computed on the cells:** the metric is recomputed on each replicate's weighted cells
   (`bootstrap_intervals`), and the interval is the middle `level` share of the values.
3. **Settings:** `evaluation.intervals.replicates` (200) and `.level` (0.95), loggable.
4. **Every metric** carries an interval this way. The formulas (Hanley–McNeil, Wilson, Student t)
   stay only in EDA and in the oracle test's two-standard-error tolerance.

### Baselines
`decision.baselines` (default `[population_base_rate, single_feature]`; the forms:
[config](config.md#the-modelling-fields-stage-3)). D-009, D-141 (e).

| Baseline | What it is | Compared on |
|---|---|---|
| `population_base_rate` | the unsampled train split's rate (regression: the train mean), one number | it ranks nothing (AUC 0.5 by construction); it anchors lift and the skill scores |
| `single_feature` | one feature's values used as the score (below) | the ranking metrics and the slices, like a model |
| `{previous_model: <column>}` | a score column of a source | every metric, like a model |
| `{historic_predicted_rate: <number>}` | one rate in use | the observed rate and the model's mean prediction (it ranks nothing) |
| `{historic_predicted_rate: <column>}` | a historic prediction per client | every metric, like `previous_model` |

- **The base rate** of the skill scores and of `population_base_rate` is the unsampled train
  split's rate: a model with no skill can only know the train rate, and it is the rate the
  prior-shift offset uses (D-098).
- **`single_feature`:**
  1. It is chosen among the numeric features and ordered categoricals of the run's per-run
     ledger, by the train concordance that ledger stores. Evaluation computes nothing on train
     and reads no test row to choose (§4.4).
  2. An unordered categorical is never the single feature: it has no order to score by.
  3. Its values are the score, in the direction train gives.
  4. A null takes the lowest score, and the report says so.
- **The comparison table** (`compare_baselines`): the model against each baseline at the
  decision's metric, with AUC beside it, on test and on validation, each with its interval. A
  cell a baseline cannot fill (the log loss of a raw feature) reads "not available: reason".
- It opens the report's summary and fills the card's performance section. **No gates:** nothing
  says passed or failed; the person who approves a promotion judges it (D-032).

### Strata
D-038: pooled metrics hide within-segment skill.
1. The strata variables come on the evaluation rows and into the scores table; they never reach
   the model. The modelling tags do not: every evaluation row is eligible, so each tag is 1.
2. Per level, on each part: rows, events, base rate, AUC inside the level, observed to expected,
   and at the decision's slice the level's share of the list beside its share of the population,
   with the capture inside it (the list's composition). Regression: the error metrics and
   predicted to observed per level.
3. Levels follow `strata.max_levels` (the rest `__other__`); a level below `strata.min_events`
   is greyed, never hidden.
4. No tests across levels; a note says that many levels are read together.

### The explanation tables
1. **The sample:** a seeded sample of test rows with their raw feature values and scores
   (`collect_explanation_sample`), the only rows the driver holds; it also holds the three
   waterfall rows: the highest score, a row at the decision's cut, a typical row.
2. **Contributions:** the family's own `contributions` on the reloaded booster
   (`sample_contributions`), which equal SHAP's tree explainer exactly on the pinned versions; the
   package imports no `shap`. They sum to the margin and are on the margin's scale (the log
   scale for Tweedie and Poisson), which the charts say.
3. **The feature table** (`feature_table`): per final feature, the test contribution share and
   the null and unseen shares on test and on validation. It is a table of its own under
   `evaluation/`, joined to the per-run ledger when the report is drawn; Evaluation never
   rewrites `ledger_run.parquet`.
4. **Permutation importance per redundancy cluster** (`permutation_importance`): a cluster's
   members (the ledger's `cluster`) are permuted together, so near-duplicates do not split the
   credit; a rank check compares its order with the contributions'.
5. **Partial dependence and ICE** (`partial_dependence`) on the sample, for the effect features.
6. **The effect features** (`effect_features`): the model's ten largest features by contribution
   share plus every EDA key feature the model uses (a person's `include` among them), twenty at
   most. Their effect charts show EDA's lift (from `stage2/`) beside the model's effect.
7. Train's out-of-fold contributions, for the importance bar's train side, come from Training's
   `explanation_sample` ([training](training.md)).
8. **The null and unseen shares need a pass of their own:** `score_frame` and `score_spark`
   return scores only, so the feature table's shares on test and validation are the
   encoder's shares computed on the scored rows. A feature with nulls at scoring whose train
   `null_share` was zero is flagged: the model never saw a null there and scores it as an
   extreme value, differently per library.

### What the report states
The summary says, in plain sentences:
- Training's out-of-fold metric is optimistic, because the features and the configuration were
  chosen on the same folds; the test split is the first honest number for those choices.
- The train–test gap, from the in-sample AUC Training stored on the rows the model was fitted on.
- EDA and Feature Checks used every client, test labels included, so people's feature decisions
  have seen test labels; the validation period, whose labels they never saw, stays the one
  honest number (D-030).
- Validation is reported, never chosen on (D-083); when test chose among variants, the
  test-to-validation gap mixes overfitting with selection.
- Which validation periods earlier Evaluation runs of the use case scored (the audit log's
  Evaluation `run` entries): moving the validation period after one was scored is allowed, so
  the report makes it visible.
- Average precision is not comparable across use cases.

### `compare_runs`
`compare_runs(cfg, entity, env, spark, run_a, run_b)` answers "did it help?" after a person
keeps a feature or changes a budget (D-141 (h)).
1. The two runs' metrics side by side on the rows both scored, read from their scores tables.
2. Each difference, its interval (from the shared weights) and the word "better" on the **test
   split only**.
3. Validation's two numbers side by side under "reported, never chosen on", with no difference
   and no interval of a difference (D-083).
4. The features that entered or left, and the largest changes in importance rank.
5. The two runs' budgets and seconds per family beside their metrics.
6. Runs of two data definitions are refused; a run compared with itself has a zero interval.

The comparison report over many runs and the sweeps are M4's.

### What Evaluation writes
Under `<use_case>/06_models/r007/evaluation/`, written whole by each run; a rerun replaces it and
never touches `training/`, `bundle/` or `ledger_run.parquet`.
- `evaluation.json`: the stamp (its schema version, the framework version), the identity (the
  run, `model_hash`, the config's hashes, the scored validation period) and a flat `summary`
  (the headline metric with AUC or the concordance, per part) that `list_runs` and `show_run`
  display.
- `tables/`:
  - `metrics`: long rows: metric, part, period (or `pooled`), stratum, level, value, interval
    low and high, rows, events;
  - the slices: per part, period (and summed over periods) and slice, the slice's numbers above;
  - `curves`, and the reliability and score-distribution tables the charts draw;
  - the baselines comparison;
  - `strata`: per part, stratum and level;
  - the explanation tables: the sample's contributions, the feature table, permutation
    importance, partial dependence and ICE;
  - the score cells.
- The scores table (parquet, written from Spark).
- `report.html`: the model results report ([reporting](reporting.md)).
- `model_card.json` and `model_card.html` ([reporting](reporting.md)).
- The drift reference, keyed by `model_hash` ([monitoring](monitoring.md)).

The audit log then gains a `run` entry of stage `evaluation` with the run and the scored
validation period in a field of its own; it never blocks a later move of the validation period,
which reads Feature Checks' entries only ([config](config.md)).

### The compatibility table
`VIEWS` (D-035, D-100 (b)) maps each view name to its function, or to "not available: reason"
for a task or family that cannot produce it; the decision is made up front, never by catching
an error (T17). In M2.3 every family has its own contributions, so the entries differ by task
only; several methods per view slot come only when a second kind of family exists (Phase 3). A
view named in `evaluation.skip_views` is left out; the summary always renders.

### Tests
On constructed cells, no Spark: each metric against scikit-learn on rows; the skill scores; the
slope on simulated miscalibration; a `top_n` above the population is not available; an interval
covers the value of a simulated frame. Spark, run by the main thread on `unit`: a differing
feature list is refused; one row per client, period and part; a client's rows share one weight
per replicate and two scorings give it the same weights; the slices are cut inside each period;
the single feature is chosen without a test row; the drift reference is a valid input of `psi`;
a stratum level below the minimum is greyed; the contributions sum to the margin; permuting a
cluster moves its members together; the effect features are at most twenty and hold every key
feature the model uses; a rerun rewrites `evaluation/` only; `run="r001"` evaluates an older
run; `compare_runs` computes nothing on validation, gives a zero interval against itself and
refuses two data definitions; the end-to-end test runs every stage on both configs within two
minutes. On `dev`: the four acceptance tests of Level 2.

### Not built
- Gates, and "passed / failed" anywhere: a line nobody acts on is decoration; whether a metric
  gate returns is a Phase 3 wishlist question (D-032).
- "Too good to be true" warnings: Feature Checks is the screen, and the report shows the
  numbers.
- Gini, KS, accuracy, F1, a confusion matrix at 0.5: see Metrics.
- A correction for a base rate that moves over time: reported per period, not corrected.
- `shap` as an import: the libraries' own contributions equal it, and declared categoricals
  break several of its modes.
- The chunked driver scoring path: only if the libraries fail on the bank's executors.
- The comparison report over many runs, and sweeps: M4.
- Calibration curves against the oracle's probabilities on canonical: M3.

### Code map
- `statistics/metrics.py`: `binary_metrics`, `regression_metrics`, `slice_metrics`,
  `reliability_table`, `threshold_table`, on cells.
- `statistics/bootstrap.py`: `bootstrap_intervals`.
- `tasks.py`: the per-task metric function and baselines (a seam).
- `evaluation/scores.py`: `score_parts`, `write_scores`, `client_weights`, `score_cells`.
- `evaluation/baselines.py`: `add_baselines`, `compare_baselines`.
- `evaluation/tables.py`: `metric_tables` (per period and pooled, the slices per period, the
  strata with the list's composition, validation on test clients only).
- `evaluation/drift_reference.py`: `build_drift_reference`.
- `evaluation/explain.py`: `collect_explanation_sample`, `sample_contributions`, `feature_table`,
  `permutation_importance`, `partial_dependence`, `effect_features`.
- `evaluation/views_explain.py`: views 8–11, 15 and 16.
- `evaluation/report.py`: `VIEWS`, `build_report` (views 1–7, 12–14 and 17; views 12 and 13 call
  `training/views.py`).
- `evaluation/compare.py`: `compare_runs`.
- `evaluation/run.py`: `run_evaluation`, the flow of Level 2.
- Reading order for review: `run_evaluation`, then `score_cells` with `client_weights`, then
  `binary_metrics` against its test, then `compare_runs`.

### Interface
Public: `run_evaluation`, `compare_runs`; `load_bundle` and `score_frame` are
[model bundle](model_bundle.md)'s. CLI: `run --stages evaluation [--run r007]`; a bare `run`
runs every built stage, Training and Evaluation included.

```python
def run_evaluation(cfg, entity, env, spark, run: str | None = None) -> StageResult: ...
def compare_runs(cfg, entity, env, spark, run_a: str, run_b: str) -> dict[str, pd.DataFrame]: ...

def binary_metrics(cells: pd.DataFrame) -> dict[str, float]: ...
def regression_metrics(cells) -> dict[str, float]: ...
def slice_metrics(cells, slices: list[float], population: int) -> pd.DataFrame: ...
def reliability_table(cells, groups: int = 10) -> pd.DataFrame: ...
def threshold_table(cells) -> pd.DataFrame: ...
def bootstrap_intervals(replicate_cells: pd.DataFrame, metric: Callable,
                        level: float) -> tuple[float, float]: ...

def score_parts(spark, bundle_folder: str, rows: DataFrame, cfg) -> DataFrame: ...
def write_scores(scores: DataFrame, folder: str) -> None: ...
def client_weights(client: Column, replicates: int, salt: str) -> Column: ...
def score_cells(scores: DataFrame, cfg, by: list[str]) -> pd.DataFrame: ...
def add_baselines(rows: DataFrame, cfg, run: dict) -> DataFrame: ...
def compare_baselines(metrics: pd.DataFrame, cfg) -> pd.DataFrame: ...
def metric_tables(...) -> dict[str, pd.DataFrame]: ...
def build_drift_reference(run_folder: str, cells: pd.DataFrame) -> dict[str, pd.DataFrame]: ...

def collect_explanation_sample(rows: DataFrame, scores: DataFrame, cfg, env) -> pd.DataFrame: ...
def sample_contributions(bundle: Bundle, sample: pd.DataFrame) -> pd.DataFrame: ...
def feature_table(...) -> pd.DataFrame: ...
def permutation_importance(bundle, sample, clusters: pd.DataFrame, metric: Callable,
                           seed: int) -> pd.DataFrame: ...
def partial_dependence(bundle, sample, features: list[str]) -> pd.DataFrame: ...
def effect_features(run_ledger: pd.DataFrame, key_features: list[str]) -> list[str]: ...

VIEWS: dict[str, Callable]
def build_report(tables: dict, meta: dict, resolved: UseCaseConfig) -> str: ...
```

`cfg, entity, env, spark` are `UseCaseConfig, str, EnvironmentConfig, SparkSession`, as in
`run_eda`. Config: `evaluation.slices`, `skip_views`, `intervals`; `decision.metric` and
`baselines` ([config](config.md#the-modelling-fields-stage-3)).

### Lessons from the crunch
- A pooled AUC over periods inflated the number (Pooled and per period).
- Importance: collinearity split the credit (permutation per cluster); native importance was
  misaligned with raw-string categoricals (the libraries' contributions on the encoder's codes).
- SHAP failed across the original estimator set and was disabled (T17): compatibility is
  declared up front.
- The crunch had no test split and computed importance on the out-of-time month, then sent
  features back on it (D-083). Worth keeping from it: `score_raw` beside `score`, a rank check
  between two importance methods, loading an earlier run, the end-of-notebook checklist.

## Open questions
To measure in the build, not to decide:
- The bootstrap's seconds per replicate on the cells at the bank's size (measured once on a
  constructed frame of that size).
- The three model libraries importing and scoring one batch on a bank executor (spike 5's trip);
  the chunked driver path depends on it.
