# Evaluation
**Status:** built 2026-11-17 (M2.3 major step 3); the EDS's joint review of steps 2 and 3 is open
· **Legacy:** `src/evaluate.py`, `src/importance.py`, `src/analysis.py`
**Related:** [model bundle](model_bundle.md) (the run folder, the bundle, `score_spark`, the
hashes) · [training](training.md) (writes the run) · [dataset](dataset.md) (Evaluation's frames,
`carry`, `eligible_rows`) · [reporting](reporting.md) (the seventeen views, the charts, the model
card's content) · [monitoring](monitoring.md) (the drift reference's format) ·
[config](config.md#the-modelling-fields-stage-3) (every field) · [feature ledger](feature_ledger.md)
· [lifecycle](lifecycle.md) · [modelling questions and answers](../guides/modelling_faq.md) ·
D-009, D-030, D-032, D-035, D-036, D-038, D-050, D-054, D-083,
D-098, D-100, D-139, D-141

Read it in three levels: Level 1 gives the essentials, Level 2 how the parts connect, Level 3
every detail. This doc owns Evaluation's **scores table**, the **score cells**, the **metrics**
and their **intervals**; the views are [reporting](reporting.md)'s, the drift reference's format
[monitoring](monitoring.md)'s.

## Level 1: Summary
**What it does.** Judges one trained run on clients and a period it never saw, outside the
engine (`CLAUDE.md` §4.5), against declared baselines, and writes the model results report, the
model card and the drift reference. It is its own stage so it can be rerun on any trained run,
with today's evaluation settings, without training again (D-036, D-139).
- **In:** a run folder (the bundle, `stage2/`, `training/`, the per-run ledger) and the eligible
  test and validation rows in Spark. **Out:** `evaluation/` inside the run folder, a `run` entry
  in the audit log naming the scored validation period, a `StageResult`.
- **Key numbers:** seventeen views, all on by default; 200 client-bootstrap replicates at 95%;
  380 score bins (binary, dense at the top) or 50 (regression). Binary: AUC, average precision, log loss and its
  skill, Brier skill, observed to expected, calibration slope and intercept. Regression: RMSE,
  MAE, R², the deviance, the concordance, predicted to observed. No gates, nothing "passed" or
  "failed".
- **Run it:** `run_evaluation(cfg, entity, env, spark, run=None)`, `python -m core_modelling run
  <config> --stages evaluation [--run r007]`, or notebook `05_evaluation.ipynb`. Two evaluated
  runs: `compare_runs(cfg, entity, env, spark, "r001", "r002")`.

## Level 2: How it fits together

### What drives what
- **The run drives everything.** Evaluation reads only the run folder and the data (D-139 (b)):
  the bundle scores; `stage2/` (through `read_stage2_copy`, which checks `_stage2.json` first)
  gives the feature kinds, the clusters, EDA's key features, groups, edges and counts;
  `training/` gives the train level, Training's metrics, the sign-off, trials and explanation
  sample. An EDA rerun never changes what an older run's evaluation shows.
- **One scoring pass.** Scores come from `score_spark`, the `score_frame` path Training's
  self-check and Inference use ([model bundle](model_bundle.md)). They are written once and read
  back for every later step; nothing is scored twice.
- **Every number is a function of the score cells,** a Spark aggregate of the scores table, as
  EDA's numbers are of its counts table (D-141 (b)). Rows reach the driver only for the
  explanation sample.
- **The decision sets the emphasis:** the headline is `decision.metric` with AUC (regression:
  the concordance) beside it; `decision.baselines` names what the model is compared with; the
  slices come from `evaluation.slices`. All are declared before any result (`CLAUDE.md` §4.3).
- **The per-task spec** (`tasks.TASK_SPECS`, D-050) supplies the cell metrics, the order
  metrics, the metric keys and directions, the reliability's groups, the prediction range of a
  baseline column, the metrics a stratum level cannot have, and which views a task cannot
  produce.

### How one run flows
1. Resolve the config (the audit log replayed); refuse an unknown name in
   `evaluation.skip_views`.
2. Find the run (`find_run`): the latest of the config's data definition, or the one named; a
   run of another data definition is refused before anything else is read.
3. Refuse, before anything is scored, what would otherwise fail only at the end: a leftover
   `.tmp-*`, `.old-*` or staged `.scores-*` folder beside `evaluation/` (`check_siblings`) and a run folder the card
   cannot be built from (`check_card_inputs`). Load the bundle (`load_bundle` recomputes
   `model_hash`), the per-run ledger, the `stage2/` copy and Training's json and tables; choose
   the single feature from the ledgers; read the train level.
4. Build the evaluation rows (`build_frames(…, "evaluation")` with the bundle's features and the
   baselines' source columns as `carry`), add one score column per ranking baseline.
5. Score both parts in Spark and stage the scores table beside `evaluation/`.
6. Per scorer: the score cells, then the metric tables with intervals (the model: `split` and
   each stratum; each ranking baseline: pooled only); then the baselines comparison.
7. The drift reference from the model's cells and the `stage2/` copy.
8. The explanation sample at the decision's cut and its tables.
9. The report's views and the model card.
10. `evaluation/` written whole, the staged scores moved in; then the audit log's `run` entry.
    A failure before the write removes the staged scores. When only the audit entry fails,
    `evaluation/` stays written without its `run` entry; running Evaluation again replaces it and
    records the entry.

### The function structure in brief
- `statistics/score_cells.py`, `statistics/metrics.py`, `statistics/bootstrap.py`: the cells'
  names and their pandas mirror, the metrics and curve tables on cells, the intervals (pure
  pandas and numpy).
- `evaluation/`: `scores.py` (scoring), `cells.py` (the Spark aggregate), `tables.py` (the metric
  tables), `baselines.py`, `drift_reference.py`, `explain.py` and `effects.py` (the explanation
  tables), `views.py`, `views_summary.py`, `views_explain.py`, `report.py` (the page), `card.py`
  (the card's facts), `compare.py` (`compare_runs`), `run.py` (`run_evaluation`).
- `reporting/model_charts.py`, `reporting/explain_charts.py`, `reporting/card.py`
  ([reporting](reporting.md)).

### How it is checked
- Every metric against scikit-learn on the rows of constructed cells, within the binning's
  tolerance (the oracle, T32); the Spark cells against their pandas mirror at replicates 0 and 1.
- Spark tests on the `unit` preset, on the fixtures `evaluated_card` and `evaluated_regression`:
  every table written, the scores' grain, the shared weights, the slices per period, the single
  feature chosen from the ledgers, an older run evaluated again with only `evaluation/` changed.
- **Acceptance on `dev`** (marker `acceptance`, the card config, `lgbm`, 15 trials, 100
  replicates):
  1. the model's validation AUC is above the single-feature baseline's;
  2. the validation AUC is not above the oracle's on the same rows by more than two standard
     errors (D-100 (e));
  3. with a leak trap kept by a person, the oracle is beaten, so check 2 can fail;
  4. observed to expected on test is within 10%, with and without `negative_downsampling`.

## Level 3: Details

### Requirements and design constraints
1. **Outside the engine** (`CLAUDE.md` §4.5): Evaluation fits nothing a later step uses and
   chooses nothing. The calibration slope is a measurement; the single feature and its
   direction come from train (§4.4).
2. **The true population** (§4.8): test and validation are every eligible row of their parts
   with a known target, never sampled; sampling is Training's, on train only.
3. **Validation is reported, never chosen on** (D-083): every metric is shown on it;
   `compare_runs` computes no difference on it, and refuses to.
4. **Rank metrics are unaffected by calibration,** because every calibration map is strictly
   increasing; the reliability view reads `score`, on axes fitted to the data (T16).
5. **Average precision is not comparable across use cases:** its floor is the base rate; the
   report says so and the precision–recall chart marks each part's base rate.
6. **Task-agnostic shapes** (D-050): the scores, the cells and the metrics table have one shape
   for both tasks; what differs is the per-task spec's entry.
7. **Fail loud** (D-035): a view the compatibility table declares compatible must work; a
   failure is an error. A view's runtime is never a reason to drop it.
8. **Reproducible** (§4.10): `evaluation.json` carries the run, `model_hash` and the config's
   identity, so every score traces to its model and config.

### Finding the run
- `find_run(env, resolved, entity, run=None)` takes the latest run whose data-definition hash,
  Training settings digest and sources digest equal the resolved config's ([config](config.md#the-modelling-fields-stage-3)
  owns what each digest covers). Changing an evaluation setting or a baseline therefore never
  orphans a trained run. With none, the error lists the latest runs and why each was passed
  over.
- `run="r007"` (CLI `--run r007`) evaluates a named run with the current evaluation settings.
  It is refused when its data definition, its client split (`data.split`) or its sources differ
  from the config's, or when it has no `training/`. `run` is accepted only with
  `stages=["evaluation"]` and one config, and refused otherwise before anything runs.
- The rows are built with the bundle's feature list. `score_parts` refuses rows whose features
  differ from the bundle's (naming the difference), a baseline column named like a feature or a
  kept column, and a bundle of another task.
- A part without rows fails loud, naming the part, when the score cells are aggregated: the rows
  are never collected, so nothing earlier would notice a test split or a validation period with
  no eligible row and a known target.

### Scoring and the scores table
1. **Inside Spark** (D-141 (a)): `score_parts` calls `score_spark`, which runs `score_frame` per
   partition with `mapInPandas` ([model bundle](model_bundle.md)). Nothing is collected.
2. **Written first** (`write_scores`): Spark writes the table beside the stage's folder as
   `evaluation.scores-<pid>`; every cell reads it back. `write_stage` moves it into
   `evaluation/scores/` before the swap. Any failure before then removes it (when the removal
   fails too, the original error is raised with a note naming what is left); a `.scores-*`
   folder left by a killed process is refused on the next run until a person removes it.
3. **The scores table**, parquet:
   - grain: one row per client, period and part;
   - columns, in order: `unit_id, period, part` (`test` or `validation`), `split` (the client's:
     `train` or `test`), `target, margin, score_raw, score`, the strata variables, then one
     `baseline_<form>` column per ranking baseline (`baseline_single_feature`,
     `baseline_previous_model`, `baseline_historic_predicted_rate`);
   - the baselines' source columns, carried into the rows for `add_baselines`, are dropped once
     read (unless a stratum), so only their score columns are stored;
   - the test part holds test-split clients in the window's periods; the validation part holds
     every eligible client at the validation period, of both splits.
4. The stored scores are enough for the stratified tables, a re-render and `compare_runs`.
5. The folder is covered by `evaluation.json`'s `schema_version`; the `tables` stamp does not
   list it. Its rows carry no model key and it has no version of its own (Open questions).

### Score cells
Every metric reads one aggregate of a scorer's scores, as EDA's statistics read its counts table
(D-135, D-141 (b)). `score_cells(scores, cfg, by, edges, *, loss, column)` builds it in Spark;
`cells_from_rows` is its pandas mirror, the oracle of the Spark test.
- **Grain:** one row per non-empty cell: `part, period` (its label), the columns of `by`,
  `score_bin, target_bin, replicate`. `by` is `["split"]` for the model (the `all` cells are
  those pooled over `split` with `pool_cells`, one Spark pass fewer), a stratum variable, or
  `[]` for a baseline.
- **Sums,** each weighted by the client's replicate weight (1 at replicate 0): `rows,
  target_sum, score_sum, sq_error_sum` (binary: the Brier sum), `abs_error_sum, loss_sum,
  target_sq_sum, link_sum`; beside them `score_min` and `score_max`, the cell's unweighted
  extremes.
  - `loss_sum` is the scorer's row loss (`scorer_loss(cfg, objective)`): `decision.metric` when
    it is a row loss, else the run's objective's (the log loss for binary; the Tweedie or
    Poisson deviance), else none. The objective is the run's, from `run.json`, since a named run
    may have been trained under another. The Tweedie deviance is at the constant variance power
    1.5, never `training.tweedie_variance_power`.
  - `link_sum` is the logit of the score clipped to [1e-15, 1 − 1e-15], filled for the log loss
    only; both are null for a scorer without a loss (the single feature).
- **Score bins** (`SCORE_GRID`, `bin_quantiles(task)`): quantile bins of the scorer's column,
  cut once per scorer over every scored row of test and validation so each `by` shares them.
  They narrow towards the top, where average precision, the top slices and the calibration
  intercept are read:
  - binary, 380 bins: 100 of 0.9% of the rows up to 0.9, 90 of 0.1% up to 0.99, 90 of 0.01% up
    to 0.999, 100 of 0.001%;
  - regression, 50 bins: 25 of 3.6%, 25 of 0.4%.
- **Two quantile passes** (`score_edges`, `quantile_passes`): one `approxQuantile` at rank error
  1e-4 cuts the body; binary's tail (`TAIL_START`, 0.99) is cut by a second over the rows at or
  above the body's 0.99 edge, since its narrowest bins are below one pass's rank error. A value
  that fills a bin becomes its own bin.
- **The edges are a discretisation, not a choice:** they are cut over test and validation
  together, so test's rank metrics move in the fourth decimal when the validation period
  changes.
- **Target bins:** binary, the target itself; regression, EDA's target bins cut from 4,000
  quantiles of the target.
- **Strata cells** use every `STRATA_STEP`-th edge (binary every fourth: 95 bins; regression
  all 50) and, for regression, only the zero bin's edges, so a level's `events` count right. A
  level is capped as EDA caps it (`stratum_labels`): the `strata.max_levels` levels with most
  scored rows, the rest `__other__`, null and NaN `null`. After the aggregate, the `__other__`
  rows are checked against the counts of the levels not kept (`_check_other`, no extra Spark
  job).
- **The weights** (`client_weights`): one `array<int>` column, element r − 1 the Poisson(1)
  weight of replicate r from `xxhash64(client, r, "client_bootstrap")` through the inverse CDF
  (at most 17). Column expressions only; the array is exploded and summed in one `groupBy`, so
  the shuffle carries cells, not rows. A row of weight 0 counts nowhere in that replicate.
- **Checks** on replicate 0: a part of `test` and `validation` without a cell, a null or NaN
  score, and a row outside its loss's domain each fail loud.
- **Tolerance:** the losses, the Brier sum, the errors and the deviance are exact per-row sums;
  only the rank metrics, the slices, the curves and the calibration line carry the binning's
  tolerance. Measured on 1 to 2 million simulated rows at base rates from 0.05% to 5%: average
  precision within 0.0015 of the row value, the calibration intercept within 0.0013, the slope
  within 0.0003; a stratum's average precision 0.0007 low at a 2.9% rate. A grid whose top bins
  were 0.1% read average precision 4.7% low at a 1% rate and 61% low at 0.05%, which is why the
  tail is dense.
- **Size:** at 1 million rows over 12 periods, about 6,900 cells per replicate with the periods
  apart, 715 pooled over them.

### Metrics
Every metric is computed per part, pooled and per period, and per stratum level, each with its
interval. The parts are `test`, `validation` and `validation_test_clients` (the validation
period's test-split clients only: a train client's earlier periods were fitted on). The metric
functions read one replicate's cells of one part; a metric the cells leave undefined is NaN,
decided from the cells, never by catching an error.

**Binary** (`binary_metrics(cells, base, loss=True)`)
| Metric (key) | Definition |
|---|---|
| `rows`, `events`, `base_rate` | the support (`events`: the positive rows); the base rate is the part's positive share |
| `roc_auc` | the concordance of the score bin × target table: positive–negative pairs ordered right, a shared bin half |
| `ap` | the area under the precision–recall curve, a bin's events spread evenly over its rows (Davis and Goadrich); shown with the base rate, its floor |
| `log_loss` | the mean log loss of the clipped score |
| `log_loss_skill` | 1 − log loss / log loss of the constant base forecast (0 no better, 1 perfect); the base is the unsampled train split's rate |
| `brier_skill` | 1 − Brier score / Brier score of the same constant forecast |
| `observed_to_expected` | the sum of the target over the sum of `score`; 1 is the right level |
| `calibration_slope`, `calibration_intercept` | the logistic regression of the target on each cell's mean logit, by Newton from (1, 0); 1 and 0 when calibrated, NaN when no maximum exists |

Without a loss (`loss=False`, decided up front for a raw feature) the probability metrics are
NaN; a loss declared but null in a cell fails loud.

**Regression** (`regression_metrics(cells, base, loss=True)`)
| Metric (key) | Definition |
|---|---|
| `rows`, `events`, `mean` | the support; `events` are the rows with a non-zero target |
| `rmse` | the square root of the mean squared error |
| `mae` | the mean absolute error; it rewards predicting the median, which under a skewed amount is far below the mean |
| `r2` | 1 − the squared error over the squared deviation from the part's mean |
| `deviance` | the mean row loss: the Tweedie deviance at 1.5 or the Poisson deviance, for the decision or the objective that names one (`row_loss`); NaN otherwise. The views name it by `row_loss` and leave it out when there is none |
| `concordance` | EDA's scale, from the score bin × target bin table: pairs with unequal targets ordered right |
| `predicted_to_observed` | the mean of `score` over the mean target; 1 is the right level |

- Every metric row also carries `mean_score` and `mean_target`, which the baselines comparison
  reads and the views hide.
- **The headline** (`headline_names`: the report header, `list_runs`, the card) is
  `decision.metric` with the task's first order metric (`roc_auc`, regression `concordance`)
  beside it. A regression deviance decision is stored under the key `deviance` (`metric_key`).
- **Not built:** Gini and KS, which restate AUC on other scales; accuracy, F1 and a confusion
  matrix at 0.5, which mean nothing at a rare rate.

### Pooled and per period
D-098: a reader looks for one curve and one headline per split first, and a list is cut inside
one period.
1. **Pooled:** each part's curves (`curves`, `reliability`, `score_distribution`) and its
   headline are computed on all of its rows.
2. **Per period:** the `metrics` table holds every metric per observation period, `pooled`, and,
   over two or more periods, `mean` (the plain mean of the periods' values, its interval from
   the same draws). A period or the mean below `strata.min_events` events is `insufficient`:
   greyed in the views, never hidden. `events` are positive rows: a conversion counts once in
   every period whose target window holds it, so up to `w` times when pooled or in a stratum
   level, and the greying is on positive rows.
3. **A note, not a rule** (`pooling`): per part and order metric, the pooled value beside the
   mean of the periods; when their intervals do not overlap, the summary says the base rate moved
   inside the window and the per-period values are the ones to read.
4. **Observed to expected per period** on test and on validation, with no correction for a base
   rate that moves over time.

### Slices
1. The slices are `evaluation.slices` (a `top_n` decision's `decision.n` first), then the fixed
   capture depths 1, 2, 5, 10, 20, 30 and 50% not already configured (`configured` false).
   Labels read `top 5%`, `top 10,000`.
2. Each slice is cut **inside each period**, then the periods' counts are added up, so one
   conversion is never counted up to `w` times in a slice.
3. A `top_pct` is a share of the period's rows in the part. A `top_n` is read as a share of the
   period's eligible rows over both splits, null targets included (the frames'
   `eligible_rows`), and cut at that share inside the part.
4. A `top_n` above the period's population is "not available"; a slice not available in one
   period is not available in the sum, so no period drops out silently.
5. The cut bin is split in proportion to its rows (no row-level tie rule here).
6. Per slice, per period and pooled: rows, `target` (events or amount) captured, `capture` (the
   share of all events or of the total amount), `rate` (precision or mean) and `lift` (over the
   part's), the three rates each with its bootstrap interval.

### Intervals: the client bootstrap
Rows are not independent (a client is in up to six periods of test and positive in up to `w`),
so a formula that counts rows is too narrow, and none exists for lift, average precision or the
skill scores (D-141 (c)).
1. **Weights:** one Poisson weight per client and replicate from a hash of its id
   (`client_weights`, Score cells). A client's rows move together, and two runs scored on the
   same rows share the weights, so the interval of their difference is right.
2. **Computed on the cells:** the value is the metric on replicate 0; the interval is the middle
   `level` share of the metric over replicates 1 to R (`replicate_values`,
   `bootstrap_intervals`). One pass per part gives every metric's interval, for each period, the
   pooled row and the mean.
3. **An undefined replicate never narrows an interval:** a metric NaN in any replicate (no event
   drawn), or a replicate without cells, has no interval.
4. **Settings:** `evaluation.intervals.replicates` (200, at least 20) and `.level` (0.95),
   loggable.
5. **Every metric and slice rate** carries an interval this way. The formulas (Hanley–McNeil,
   Wilson, Student t) stay only in EDA and in the oracle test's two-standard-error tolerance.

### Baselines
`decision.baselines` (default `[population_base_rate, single_feature]`; the forms:
[config](config.md#the-modelling-fields-stage-3)). D-009, D-141 (e).

| Baseline | What it is | Compared on |
|---|---|---|
| `population_base_rate` | the unsampled train split's rate (regression: the train mean), one number | its mean prediction, beside the observed level |
| `single_feature` | one feature's values used as the score (below) | the order metrics |
| `{previous_model: <column>}` | a score column of a source | every metric, like the model (below) |
| `{historic_predicted_rate: <number>}` | one rate in use | its mean prediction, beside the observed level |
| `{historic_predicted_rate: <column>}` | a historic prediction per client | every metric, like `previous_model` |

- **The base** of the skill scores and of `population_base_rate` is the unsampled train
  split's rate (`train_level`): `training.json`'s `sampling.true_rate` when Training sampled,
  else the mean target of `training/tables/oof.parquet`. A model with no skill can only know the
  train rate, and it is the rate the prior-shift offset uses (D-098).
- **`single_feature`** (`choose_single_feature`):
  1. It is the per-run ledger's feature with the highest `train_concordance` among the numerics
     and the ordered categoricals (kind from the `stage2/` ledger; ordered when the run's
     `features.order` names it), the ledger's first on a tie. Evaluation computes nothing on
     train and reads no test row to choose (§4.4).
  2. An unordered categorical is never chosen: it has no order to score by. When none
     qualifies, every cell reads "not available" and a warning says so.
  3. Its score is `train_sign` × the value clipped to ±`CLIP` as the encoder clips it, or an
     ordered categorical's position in its declared order.
  4. A null, a NaN or an undeclared level takes the lowest score, and the report says so.
  5. It is chosen on the train rows where it is known, while its nulls score lowest on every
     row, so a mostly-null feature can win and then look weak. Any null on train (the per-run
     ledger's `null_share`) gives the warning `single_feature_baseline_has_nulls` with the
     share; there is no threshold (Open questions).
- **A column baseline** is checked up front from one Spark aggregate of its column
  (`describe_baseline_columns`: null share, min, max); `baseline_loss` decides what it can
  fill. A null takes the lowest score, so it ranks; with nulls, or outside the task's prediction
  range (binary: [0, 1]), it fills the order metrics only; a deviance needs a positive
  prediction. Otherwise it carries the model's loss and fills every metric. A column that is not
  numeric fails loud.
- **The comparison table** (`compare_baselines`): one row per scorer, part (`test`,
  `validation`) and metric, pooled, each value with its interval. The scorers are `model`, the
  forms in config order and `observed` (the part's observed rate or mean). The metrics are
  `decision.metric`, the task's other order metrics and `mean_prediction`. A cell a scorer cannot
  fill is NaN with its reason in `unavailable` ("not available: a raw feature's values are no
  prediction").
- It opens the report's summary and fills the card's performance section. **No gates:** nothing
  says passed or failed; the person who approves a promotion judges it (D-032).

### Strata
D-038: pooled metrics hide within-segment skill.
1. The strata variables ride on the evaluation rows and into the scores table; they never reach
   the model.
2. Per variable, part (`test`, `validation`) and level, pooled over the periods: every metric
   with its interval in `metrics` (`stratum`, `level`), except what the task's
   `strata_absent_metrics` names (regression: the concordance). The view shows AUC and observed
   to expected (regression: RMSE, MAE, predicted to observed).
3. The list's composition (`strata`): at the decision's slice (`decision_slice`: `decision.n` for
   a `top_n` decision, else the first configured `top_pct`, else the first `top_n`), cut inside
   each period and added up, each level's share of the population, its share of the list and the
   capture inside it. Without a slice it is "not available".
4. Levels are capped on the scored rows (Score cells); a level below `strata.min_events` is
   greyed, never hidden.
5. No tests across levels; a note says that many levels are read together. For binary only it
   adds that a level's ordering metrics come from coarser score bins than the pooled ones, so
   they read slightly low (`VIEWS_BY_TASK[task]["strata_clause"]`); a regression's levels keep
   the pooled grid.

### The explanation tables
1. **The cut** (`explanation_cut`): the decision's slice (`decision_slice`) on test, pooled; the
   score is the lowest of the first test score bin that reaches its depth. Without a slice, or
   when its row is not available, it falls back to `top 10%` with a warning.
2. **The sample** (`collect_explanation_sample`): 5,000 test rows chosen by a hash of the keys
   and `training.seed` (a rerun takes the same rows), with their raw features and scores, plus
   the three waterfall rows (`waterfall`): `highest` (the top score of test), `cut` (the score
   nearest the cut), `typical` (the sampled row nearest the sample's median). The only rows the
   driver holds.
3. **Contributions** (`compute_contributions`, stored as `contributions`): the family's own
   contributions on the encoder's codes, in the shape of Training's `explanation_sample`. A row's
   contributions and base value must sum to its stored margin (within 1e-4), or it fails loud.
   They are on the margin's scale (the log scale for Tweedie and Poisson), which the views say;
   the package imports no `shap`.
4. **The encoder's shares** (`encoding_shares`): `score_spark` returns scores only, so a Spark
   pass runs `encode_frame` per partition and counts, per part and feature, the null and
   unseen-level shares exactly as scoring codes them.
5. **The feature table** (`feature_table`, stored as `features`): per final feature, largest
   first, the test contribution share and rank, train's null share (the per-run ledger's: the
   frame the model was fitted on), the null and unseen shares on test and validation, and
   `null_not_in_train`, true for nulls at scoring and none in train: the model never learnt
   where they go, and a warning names them. Evaluation never rewrites `ledger_run.parquet`.
6. **Permutation importance per redundancy cluster** (`permutation_importance`): a cluster's
   members (the `stage2/` ledger's `cluster`; none, the feature alone) are permuted together,
   so near-duplicates do not split the credit. Each cluster takes `PERMUTATIONS` (5) seeded
   permutations of the sample's rows; `loss_change` is their mean and `loss_change_sd` their
   standard deviation, in `decision.metric` as a loss. A rank check sets its order beside the
   contribution shares': the rank gap, the three largest gaps marked, Spearman's correlation.
   Whether it can be computed is decided up front (`permutation_unavailable`): a sample whose
   target has one value (no positive row, no negative one, a constant amount) has no loss to
   change, so the table is stored empty with its columns and the reason goes to
   `evaluation.json`'s `unavailable`.
7. **The effect features** (`effect_features`): every `stage2/` key feature the model uses
   and the model's ten largest by Training's out-of-fold contribution share, twenty at most, the
   key features first when they do not all fit.
8. **Partial dependence and ICE** (`partial_dependence`) of the effect features on the sample:
   a grid of about 20 quantiles of a numeric, or its 20 most frequent levels; the mean score and
   50 ICE lines.
9. **The effects table** (`effect_table`, stored as `effects`): per effect feature with EDA
   groups, in EDA's group order, the sample's mean contribution per EDA group with its 95%
   interval beside EDA's rows, estimate and lift with its interval, both read from the
   `stage2/` copy. A numeric joins its group by its bucket on EDA's edges, a categorical by its
   level text (`__other__` when EDA has it); rows no group covers are counted
   (`left_out_null`, `left_out_level`). A feature without EDA groups has no row, and the view
   draws its contribution against its value. A feature with groups but no lift (not one of
   EDA's key features, or EDA's base not positive) has one row holding only the reason in
   `unavailable`. A group's first bucket is read back from its label
   (Open questions).
10. **Training's tables, stored again:** its `signoff`, `trials` and `explanation_sample` (train
    out of fold, the importance bar's train side) are copied as `training_signoff`,
    `training_trials`, `training_explanation_sample`, so `evaluation/` renders alone.

### What the report states
The views, their order and their charts are [reporting](reporting.md)'s; the page has four
parts:
- **Summary** (view 1): the run, its model and what it was scored on; the headline metrics per
  part with their intervals; the choices (D-032), with the baselines, the single feature, the
  intervals and the explanation cut; the baselines table; the reading notes; what the numbers
  cannot say; the warnings.
- **Core:** metrics per period, ROC and precision–recall, capture, reliability, score
  distribution, strata, importance, beeswarm, effects, waterfalls, sign-off (train only), search.
- **Extended:** thresholds, permutation importance per cluster, partial dependence and ICE,
  validation on test clients only.
- **Appendix:** the resolved config, the audit log's entries, the collected frames and the
  seconds per phase.

**How to read**, five notes: concordance (0.5 chance, 1 perfect; the AUC for a yes/no target);
lift (a slice's rate over its part's); intervals (the level, the client bootstrap, "value (low
to high)"); grey (fewer than `strata.min_events` events, still shown); null (a missing feature
value, its own group last).

**What these numbers cannot say**, in plain sentences:
- Training's out-of-fold metric is optimistic, because the features and the configuration were
  chosen on the same folds; test is the first honest number for those choices.
- The train–test gap: Training's in-sample concordance on the rows the model was fitted on,
  beside test's. For regression it adds that train's is computed on rows and test's on score
  cells, which reads up to about 0.01 higher, so a test value above train's is no finding
  (`VIEWS_BY_TASK[task]["gap_clause"]`; Open questions).
- EDA and Feature Checks used every eligible client, test labels included, so people's feature
  decisions have seen test labels; the validation period, whose labels they never saw, is the
  one honest number (D-030).
- Validation is reported, never chosen on (D-083); when test chose among variants, the
  test-to-validation gap mixes overfitting with selection.
- Which validation periods earlier Evaluation runs scored (`earlier_validations`, from the audit
  log's Evaluation `run` entries). The validation period is outside the data-definition hash and
  Training's digest, so one run can be evaluated on several; nothing prevents it, and the report
  makes it visible.
- The pooling note, when it applies; binary: average precision is not comparable across use
  cases.

### `compare_runs`
`compare_runs(cfg, entity, env, spark, run_a, run_b)` answers "did it help?" after a person keeps
a feature or changes a budget (D-141 (h)). It reads the two runs' stored scores and run folders
alone and writes nothing.
1. **Refused** from the two `run.json` files alone: a run of another entity, two data
   definitions, another data definition than the config's, a run without `evaluation/`. Refused
   later: a stage json of another schema version; on the shared rows another target or client
   split; a part with no shared row; and a part where one run scored rows the other did not.
   Two runs of one data definition and split score the same rows, so a partial overlap means a
   source period changed after a run; the refusal names each run's rows and the shared ones,
   and asks to evaluate both again.
2. **The rows:** the two scores tables joined on the keys and `part`; `rows` gives per part each
   run's rows, the shared ones (all of them, after the refusals) and those scored differently.
   Each run's cells are summed with its own bins and its own objective's row loss.
3. **Test** (`metrics`, `differences`): both runs' metrics side by side, and per metric with a
   direction (`TASK_SPECS[task]["metric_directions"]`) the difference b − a, the percentile
   interval of the replicates' differences and the verdict `better`, `worse`, `no clear
   difference` or `not available`. A loss metric under two different row losses gets no
   difference, with the reason.
4. **Validation** (`validation`): the validation part and its test clients side by side under
   "reported, never chosen on", with no difference and no interval of a difference (D-083).
5. **Beside them:** the features that entered or left (`features`), the ten largest moves in
   importance rank (`importance`), and per run and family the budget, the trials and seconds
   spent, and the headline on the shared test rows (`budgets`).
6. Two runs that score every shared row alike share one set of cells, so they differ by exactly
   zero. A verdict on a rank metric can lie inside the binning's tolerance.

The comparison report over many runs and the sweeps are M4's.

### What Evaluation writes
Under `<use_case>/06_models/r007/evaluation/`, written whole by one `write_stage` call; a rerun
replaces it and never touches `training/`, `bundle/` or `ledger_run.parquet`.
- `evaluation.json` (the commit marker): the stamp (`schema_version` 1, `stage`,
  `framework_version`, `written_at`, `tables`), the config's identity (`stage_identity`), and:
  - `run_id`, `model_hash`, `validation_period` (its label);
  - `training_config_hash`: `run.json`'s `config_hash`, beside the evaluating config's in the
    identity; the two differ when a named run is evaluated under a changed config;
  - `row_loss`: the row loss the model's cells carry (`scorer_loss`), null when there is none;
  - `summary`: the validation period, `<part>_<metric>` per headline metric for `test` and
    `validation`, and the seconds, which `list_runs` and `show_run` display;
  - `base`: the unsampled train level the skill scores read;
  - `eligible_rows`: `{period label: rows}` over both splits, null targets included, for the
    window's periods and the validation period (the `top_n` population);
  - `choices`: `headline`, `single_feature` (feature, kind, sign, levels, train concordance, or
    null), `explanation_cut`, `key_features`, `effect_features`;
  - `unavailable`: `{table: reason}` for each table decided up front as not computable, `{}`
    when all are; today only `permutation_importance` can appear;
  - `training` (Training's metrics), `trained_at`, `training_seconds`, `timings`;
  - `earlier_validations`: `seq, time, run_id, validation_period` of each earlier Evaluation
    `run` entry in the audit log;
  - `drift_reference_schema_version` (1): nothing reads it until Monitoring is built, which must
    check it;
  - `warnings`: a list of `{code, values…, text}`, the only place they are written:
    `single_feature_baseline_not_chosen`; `single_feature_baseline_has_nulls` with `feature`
    and `train_null_share`; `nulls_not_in_train` with `features`;
    `explanation_cut_not_at_decision_slice` with `slice` and `reason`. The report shows the
    text; the card copies the code and the values.
- `tables/` (parquet):
  - the metric tables: `metrics`, `slices`, `curves`, `reliability`, `score_distribution`,
    `strata`, `pooling`, `baselines`;
  - `cells`: the model's score cells at replicate 0 only, the `split` cells and each stratum's,
    with `by` and `level`; the replicates' intervals are already in `metrics` and `slices`;
  - the explanation tables: `contributions`, `features`, `permutation_importance` (stored empty,
    with its columns, when `unavailable` names it), `partial_dependence`, `effects`;
  - Training's, stored again: `training_signoff`, `training_trials`,
    `training_explanation_sample`;
  - the drift reference: `drift_features`, `drift_edges`, `drift_scores` (the prefix keeps them
    apart from the feature table), built from the `stage2/` copy's counts over the test
    periods and the test part's score cells ([monitoring](monitoring.md)).
- `scores/`: the scores table (Spark parquet).
- `report.html`: the model results report ([reporting](reporting.md)).
- `model_card.json` and `model_card.html`: the card (`CARD_SCHEMA_VERSION` 1;
  [reporting](reporting.md) owns its sections). `build_card` refuses pieces of different runs
  or models, and a config other than the one Evaluation ran with.
- `log.json` (the frames' steps and the explanation sample's collect) and
  `resolved_config.yml`.

The audit log then gains a `run` entry of stage `evaluation` with the run and the scored
validation period in a field of its own; it never blocks a later move of the validation period,
which reads Feature Checks' entries only ([config](config.md)).

### The compatibility table
`VIEWS` (D-035, D-100 (b)) maps each view name, in the report's order, to its function, or per
task to "not available: reason"; the decision is made up front, never by catching an error
(T17). Every family has its own contributions, so the entries differ by task only: regression
has no `curves`, `score_distribution` or `thresholds` ("the target is an amount, without
classes"). A view named in `evaluation.skip_views` is left out; the summary always renders. An
unknown name in `skip_views` is refused at run time (`check_skip_views`), so the view names are
part of the config contract: renaming one needs an alias or a migration.

### Tests
- **No Spark,** on constructed cells: each metric against scikit-learn on rows; the dense-top
  bins; the average precision and the calibration line within 0.002 of the rows at a 0.1% rate
  on a million rows; the slope on simulated miscalibration; a score of exactly 0 or 1 keeps the log loss
  finite; a scorer without a loss is declared up front; the slices add up over periods and a
  `top_n` above the population is not available; the client interval covers the value and is
  wider than a row bootstrap; an undefined replicate gives no interval; the chart tables agree
  with the metrics; the baselines' choices and reasons; the effects' group joins; the card's
  sections, refusals and JSON types; the views of both tasks; `compare_runs`' verdicts,
  directions and refusals of a difference off test, and its refusal of rows only one run
  scored.
- **Spark, run by the main thread on `unit`:** the cells equal their pandas mirror; the weights
  repeat per client and are Poisson(1); a part without rows and a bad request fail loud;
  differing features are refused; one row per client, period and part; the drift reference is a
  valid input of `psi`; the contributions sum to the margin; a cluster is permuted as one; the
  effect features are at most twenty with every used key feature; every table is written; the
  `run` entry; a failure after the scores are staged leaves no staged scores, keeps the earlier
  `evaluation/` and records no entry; a run of another data definition is refused; the explanation cut's fallback; an
  older run evaluated again with only `evaluation/` changed; `compare_runs` against itself
  differs by zero, differs on test only, refuses two data definitions and an unevaluated run; the
  CLI runs every stage on both configs and refuses `run` outside Evaluation alone.
- **On `dev`:** the four acceptance tests of Level 2 (three runs, about 14 minutes alone).

### Not built
- Gates, and "passed / failed" anywhere: a line nobody acts on is decoration; whether a metric
  gate returns is a Phase 3 wishlist question (D-032).
- "Too good to be true" warnings: Feature Checks is the screen, and the report shows the
  numbers.
- Gini, KS, accuracy, F1, a confusion matrix at 0.5: see Metrics.
- A correction for a base rate that moves over time: reported per period, not corrected.
- `shap` as an import: the libraries' own contributions equal it, and declared categoricals
  break several of its modes.
- A chunked driver scoring path: only if the libraries fail on the bank's executors.
- The comparison report over many runs, and sweeps: M4.
- Calibration curves against the oracle's probabilities on canonical: M3.

### Code map
- `statistics/score_cells.py`: the cells' names as data (`CELL_KEYS`, `CELL_SUMS`,
  `SCORE_GRID`, `STRATA_STEP`, `TAIL_START`, `PARTS`, `POOLED`, `MEAN`), `bin_quantiles`,
  `quantile_passes`, `cells_from_rows` (the pandas mirror), `pool_cells`.
- `statistics/metrics.py`: `binary_metrics`, `regression_metrics`, `slice_labels`,
  `slice_metrics`, `slice_rates`, `threshold_table`, `reliability_table`, `distribution_table`.
- `statistics/bootstrap.py`: `bootstrap_intervals`, `replicate_values`.
- `tasks.py`: the per-task entries (`cell_metrics`, `order_metrics`, `metric_keys`,
  `metric_directions`, `undirected_metrics`, `reliability_groups`, `prediction_range`,
  `strata_absent_metrics`, `roc_curve`, `target_class`).
- `runs.py`: `find_run`. `training/gate.py`: `read_stage2_copy`. `training/tables.py`:
  `train_level`.
- `evaluation/scores.py`: `score_parts`, `write_scores`.
- `evaluation/cells.py`: `client_weights`, `scorer_loss`, `score_edges`, `score_cells`,
  `stratum_labels`.
- `evaluation/tables.py`: `metric_tables`, `part_cells`, `decision_slice`, `pooled_metrics`,
  `headline_names`, `metric_key`.
- `evaluation/baselines.py`: `choose_single_feature`, `carried_columns`, `baseline_columns`,
  `describe_baseline_columns`, `add_baselines`, `baseline_loss`, `compare_baselines`.
- `evaluation/drift_reference.py`: `build_drift_reference`.
- `evaluation/explain.py`: `explanation_cut`, `curve_at_depths`, `collect_explanation_sample`,
  `compute_contributions`, `encoding_shares`, `feature_table`, `permutation_importance`,
  `permutation_unavailable`, `partial_dependence`, `effect_features`.
- `evaluation/effects.py`: `effect_table`.
- `evaluation/views.py`: views 2–7, 12–14 and 17 (12 and 13 call `training/views.py`), and
  the shared cell formats (`interval_text`, `wide_metrics`).
- `evaluation/views_summary.py`: view 1, `baseline_table`.
- `evaluation/views_explain.py`: views 8–11, 15 and 16.
- `evaluation/report.py`: `VIEWS`, `check_skip_views`, `report_views`, `render_views`,
  `build_report`.
- `evaluation/card.py`: `check_card_inputs`, `build_card`. `reporting/card.py`:
  `render_card`. `artifacts.py`: `check_siblings`.
- `evaluation/compare.py`: `compare_runs`.
- `evaluation/run.py`: `run_evaluation`, the flow of Level 2; it orchestrates only.
- Reading order for review: `run_evaluation`, then `score_cells` with `client_weights`, then
  `binary_metrics` against `test_metrics.py::test_binary_metrics_match_scikit_learn_on_the_rows`
  and the cells against
  `test_evaluation_tables.py::test_score_cells_equal_their_pandas_mirror_at_replicates_0_and_1`,
  then `compare_runs`.

### Interface
Public: `run_evaluation`, `compare_runs`; `load_bundle` and `score_frame` are
[model bundle](model_bundle.md)'s. CLI: `run <config> --stages evaluation [--run r007]`; a bare
`run` runs every built stage, Training and Evaluation included.

```python
def run_evaluation(cfg, entity, env, spark, run: str | None = None) -> StageResult: ...
def compare_runs(cfg, entity, env, spark, run_a: str, run_b: str) -> dict[str, pd.DataFrame]: ...
def run(config_paths, env_path=None, stages=None, entity=None, run: str | None = None) -> dict: ...

def binary_metrics(cells: pd.DataFrame, base: float, loss: bool = True) -> dict[str, float]: ...
def regression_metrics(cells: pd.DataFrame, base: float, loss: bool = True) -> dict[str, float]: ...
def slice_metrics(cells: pd.DataFrame, slices: Slices, population: int) -> pd.DataFrame: ...
def bootstrap_intervals(replicate_cells: pd.DataFrame, metric: Callable, level: float,
                        replicates: int) -> dict[str, tuple[float, float]]: ...

def score_parts(bundle_folder: str, rows: DataFrame, cfg, baselines: list[str]) -> DataFrame: ...
def write_scores(scores: DataFrame, stage_folder: str) -> str: ...
def client_weights(client: Column, replicates: int, salt: str) -> Column: ...
def score_cells(scores: DataFrame, cfg, by: list[str], edges: dict, *, loss: str | None,
                column: str = "score") -> pd.DataFrame: ...
def metric_tables(cells: dict[str, pd.DataFrame], cfg, base: float, population: dict[str, int],
                  *, loss: bool) -> dict[str, pd.DataFrame]: ...
def compare_baselines(metrics: dict[str, pd.DataFrame | None], cfg, base: float,
                      facts: dict, objective: str) -> pd.DataFrame: ...
def build_drift_reference(run_folder: str, cells: pd.DataFrame,
                          features: list[str]) -> dict[str, pd.DataFrame]: ...
def build_card(run_folder: str, tables: dict, meta: dict, resolved: UseCaseConfig) -> dict: ...
```

`cfg, entity, env, spark` are `UseCaseConfig, str, EnvironmentConfig, SparkSession`, as in
`run_eda`. `compare_runs` returns `rows`, `metrics`, `differences`, `validation`, `features`,
`importance`, `budgets`. Config: `evaluation.slices`, `skip_views`, `intervals`;
`decision.metric` and `baselines`; `strata` ([config](config.md#the-modelling-fields-stage-3)).

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
- **EDA's group order and lift interval.** EDA does not store `bin_order_first` or the lift's
  interval in `bins` and `levels`, so `effects.py` reads a group's first bucket back from its
  label and the lift interval from the estimate's. EDA storing both (an EDA schema change) would
  retire the label parsing.
- **`frames.rows` is computed about six times per run** (the baseline facts, the scoring, the
  explanation sample up to three times, the encoding shares). To time on a full population
  inside the bank before deciding whether to persist it.
- **Training's warnings** in `training.json` are sentences, not codes with values, so the card's
  considerations cannot carry them yet (a Training artifact change).
- **The scores table's identity.** Its rows carry no model key (`model_hash`, `run_id`) and it
  has no version of its own; inside `evaluation/` the folder and `evaluation.json` give both.
  Inference's shared scores table (D-007) is a different table and will need both on its rows.
- **`score_edges` inside the bank:** a binary scorer takes two quantile passes (the grid, then
  the tail above 0.99 at a finer error); to time on a full population.
- **A 0.99 edge on a mass point:** when one value holds nearly every row (a raw-feature
  baseline at 0 on 99% of rows), the tail pass reads nearly every row; the edges stay valid,
  only coarser.
- **The single feature's nulls:** whether the choice should rank candidates with a null as
  their lowest value, as the baseline then scores it, instead of on the rows where they are
  known.
- **Training's regression concordance on cells:** computed on rows today, so it reads up to
  about 0.01 below test's cells; computing it on cells too would make the train–test gap
  like for like.
- **To measure:** the bootstrap's seconds per replicate on the cells at the bank's size; the
  three model libraries importing and scoring one batch on a bank executor (spike 5's trip),
  which the chunked driver path depends on.
