# Evaluation
**Status:** built 2026-11-17 (M2.3 major step 3); the audit of 2026-11-22 applied 2026-11-23;
the EDS's joint review of Training and Evaluation is open · **Legacy:** `src/evaluate.py`, `src/importance.py`, `src/analysis.py`
**Related:** [model bundle](model_bundle.md) (the run folder, the bundle, `score_spark`, the
hashes) · [training](training.md) (writes the run) · [dataset](dataset.md) (Evaluation's frames,
`carry`, `eligible_rows`) · [reporting](reporting.md) (the views, the charts, the model
card's content) · [monitoring](monitoring.md) (the drift reference's format) ·
[config](config.md#the-modelling-fields-stage-3) (every field) · [feature ledger](feature_ledger.md)
· [lifecycle](lifecycle.md) · [modelling questions and answers](../guides/modelling_faq.md) ·
D-009, D-030, D-032, D-035, D-036, D-038, D-050, D-054, D-083,
D-098, D-100, D-139, D-141

Read it in three levels: Level 1 gives the essentials, Level 2 how the parts connect, Level 3
every detail. This doc owns Evaluation's **scores table**, the **score cells**, the **metrics**
and their **intervals**, and the counts of views and score bins; the views are
[reporting](reporting.md)'s, the drift reference's format [monitoring](monitoring.md)'s.

## Level 1: Summary
**What it does.** Judges one trained run on clients and a period it never saw, outside the
engine (`CLAUDE.md` §4.5), against declared baselines, and writes the model results report, the
model card and the drift reference. It is its own stage so it can be rerun on any trained run,
with today's evaluation settings, without training again (D-036, D-139).
- **In:** a run folder (the bundle, `stage2/`, `training/`, the per-run ledger) and the eligible
  test and validation rows in Spark. **Out:** `evaluation/` inside the run folder, a `run` entry
  in the audit log naming the scored validation period, a `StageResult`.
- **Key numbers:** seventeen views, all on by default; 200 client-bootstrap replicates at 95%;
  380 score bins (binary) or 100 (regression), both dense at the top. Binary: AUC, average
  precision, log loss and its skill, Brier skill, observed to expected, calibration slope and
  intercept. Regression: RMSE, MAE, R², the deviance, the concordance, predicted to observed. No
  gates, nothing "passed" or "failed".
- **Run it:** `run_evaluation(cfg, entity, env, spark, run=None)`, `python -m core_modelling run
  <config> --stages evaluation [--run r007]`, or notebook `05_evaluation.ipynb`. Two evaluated
  runs: `compare_runs(cfg, entity, env, spark, "r001", "r002")`.

## Level 2: How it fits together

### What drives what
- **The run drives everything.** Evaluation reads only the run folder and the data (D-139 (b)).
  It opens the run folder once, through its contract (`check_card_inputs`, which calls
  `open_run_folder`: [model bundle](model_bundle.md#the-run-folders-contract)), before any Spark
  work: the bundle scores; the `stage2/` copy gives the feature kinds, the clusters, EDA's key
  features, groups, edges and counts; `training/` gives the train level, Training's metrics and
  warnings, its in-sample scores, the sign-off, trials and explanation sample. An EDA rerun
  never changes what an older run's evaluation shows.
- **One scoring pass.** Scores come from `score_spark`, the `score_frame` path Training's
  self-check and Inference use ([model bundle](model_bundle.md)). They are written once and read
  back for every later step; nothing is scored twice.
- **Every metric is a function of the score cells,** a Spark aggregate of the scores table's
  rows with a known target, as EDA's numbers are of its counts table (D-141 (b)). Rows reach the
  driver only in the two seeded test samples (explanation and permutation) and in Training's
  stored in-sample scores.
- **The decision sets the emphasis:** the headline is `decision.metric` with AUC (regression:
  the concordance) beside it; `decision.baselines` names what the model is compared with; the
  slices come from `evaluation.slices`. All are declared before any result (`CLAUDE.md` §4.3).
- **The per-task spec** (`tasks.TASK_SPECS`, D-050) supplies the cell metrics, the order
  metrics, the metric keys and directions, the reliability's groups, the prediction range of a
  baseline column, the metrics a stratum level cannot have, the score grid, the strata's step
  and the tail's start, each objective's row loss, and the report's per-task wording. Which views
  a task cannot produce is the compatibility table's ([below](#the-compatibility-table)).

### How one run flows
1. Resolve the config (the audit log replayed); refuse an unknown name in
   `evaluation.skip_views`.
2. Find the run (`find_run`): the latest of the config's data definition, or the one named; a
   run of another data definition is refused before anything else is read. The newer runs it
   passed over are kept for the warnings.
3. Refuse, before anything is scored, what would otherwise fail only at the end: a leftover
   `.tmp-*`, `.old-*` or staged `.scores-*` folder beside `evaluation/` (`check_siblings`) and a
   run folder that fails its contract (`check_card_inputs`, which returns what
   `open_run_folder` read as a `RunFolder`: the bundle with `model_hash` recomputed, `run.json`,
   `training.json`, the per-run ledger, the `stage2/` copy). Read Training's tables the report
   draws (`read_training_tables` with `CARRIED_TABLES`), choose the single feature from the
   ledgers, read the train level.
4. Build the evaluation rows (`build_frames(…, "evaluation")` with the bundle's features and the
   baselines' source columns as `carry`), add one score column per ranking baseline.
5. Score both parts in Spark, the test part's null-target rows included, and stage the scores
   table beside `evaluation/`.
6. On the rows with a known target, per scorer: the score cells, then the metric tables with
   intervals (the model: `split` and each stratum; each ranking baseline: pooled only); then the
   baselines comparison and, for regression, train's in-sample concordance on test's cells.
7. The drift reference from every scored test row and the `stage2/` copy.
8. The explanation and permutation samples at the decision's cut, and their tables.
9. `evaluation.json`'s content (`build_result`), the report's views and the model card.
10. `evaluation/` written whole, the staged scores moved in; then the audit log's `run` entry.
    A failure before the write removes the staged scores. When only the audit entry fails,
    `evaluation/` stays written without its `run` entry; running Evaluation again replaces it and
    records the entry.

### The function structure in brief
- `statistics/score_cells.py`, `statistics/metrics.py`, `statistics/bootstrap.py`: the cells'
  names and grid, the metrics, slices and curve tables on cells, the intervals (pure pandas and
  numpy).
- `run_artifacts.py`: the run folder's contract and readers, shared with `compare_runs` and,
  from M2.4, every later stage.
- `evaluation/`: `scores.py` (scoring), `cells.py` (the Spark aggregate and the row losses),
  `tables.py` (the metric tables), `slices.py` (the slices and the narrow-slice guard),
  `baselines.py`, `drift_reference.py`, `explain.py`, `permutation.py` and `effects.py` (the
  explanation tables), `views.py`, `views_summary.py`, `views_explain.py`, `report.py` (the view
  table and the page), `card.py` (the card's facts), `compare.py` (`compare_runs`), `meta.py`
  (`evaluation.json`'s content and the warnings), `run.py` (`run_evaluation`, which only
  orchestrates).
- `reporting/model_charts.py`, `reporting/explain_charts.py`, `reporting/card.py`
  ([reporting](reporting.md)).

### How it is checked
- Every metric against scikit-learn on the rows of constructed cells, within the binning's
  tolerance (the oracle, T32); the Spark cells against their pandas oracle at replicates 0 and 1.
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
2. **The true population** (§4.8): every metric reads every eligible row of its part with a
   known target, never sampled; sampling is Training's, on train only. The test part's
   null-target rows are scored and count in the drift reference's score side only.
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
   identity, so every score traces to its model and config. Evaluating a run again on the same
   rows gives the same tables to the binning's tolerance, not bit for bit (Score cells).

### Finding the run
- `find_run(env, resolved, entity, run=None)` takes the latest run whose data-definition hash,
  Training settings digest and sources digest equal the resolved config's ([config](config.md#the-modelling-fields-stage-3)
  owns what each digest covers). Changing an evaluation setting or a baseline therefore never
  orphans a trained run. It returns the run and the newer runs it passed over. When the run
  taken is not the newest, it prints them with why, and Evaluation stores them as the warning
  `newer_runs_passed_over`; with none, the error lists the latest runs and why each was passed
  over.
- `run="r007"` (CLI `--run r007`) evaluates a named run with the current evaluation settings.
  It is refused when its data definition, its client split (`data.split`) or its sources differ
  from the config's, or when it has no `training/`. `run` is accepted only with
  `stages=["evaluation"]` and one config, and refused otherwise before anything runs.
- The run found is opened through the run folder's contract before any Spark work; what it
  requires of `run.json`, `training.json`, Training's tables and the `stage2/` copy is
  [model bundle](model_bundle.md#the-contract-in-detail)'s.
- The rows are built with the bundle's feature list. `score_parts` refuses rows whose features
  differ from the bundle's (naming the difference), a baseline column named like a feature or a
  kept column, and a bundle of another task.
- A part without a row with a known target fails loud, naming the part, when the score cells
  are aggregated: the rows are never collected, so nothing earlier would notice a test split or
  a validation period with no eligible row and a known target.

### Scoring and the scores table
1. **Inside Spark** (D-141 (a)): `score_parts` calls `score_spark`, which runs `score_frame` per
   partition with `mapInPandas` and reads the bundle's bytes itself
   ([model bundle](model_bundle.md#how-one-bundle-is-written-loaded-and-scored)). Nothing is
   collected.
2. **Written first** (`write_scores`): Spark writes the table beside the stage's folder as
   `evaluation.scores-<token>` (a random token); every cell reads it back. `write_stage` moves
   it into `evaluation/scores/` before the swap. Any failure before then removes it (when the
   removal fails too, the original error is raised with a note naming what is left); a
   `.scores-*` folder left by a killed process is refused on the next run until a person
   removes it.
3. **The scores table**, parquet:
   - grain: one row per client, period and part;
   - columns, in order: `unit_id, period, part` (`test` or `validation`), `split` (the client's:
     `train` or `test`), `target, margin, score_raw, score`, the strata variables, then one
     `baseline_<form>` column per ranking baseline (`baseline_single_feature`,
     `baseline_previous_model`, `baseline_historic_predicted_rate`);
   - the baselines' source columns, carried into the rows for `add_baselines`, are dropped once
     read (unless a stratum), so only their score columns are stored;
   - the test part holds the test-split clients in the window's periods, a null target
     included; the validation part holds every eligible client at the validation period with a
     known target, of both splits (`NULL_TARGETS` in `dataset/frames.py` logs both rules);
   - every cell, slice, baseline and sample reads the rows with a known target only
     (`KNOWN_TARGET`); the drift reference's score side reads every test row.
4. The stored scores are enough for the stratified tables, a re-render and `compare_runs`.
5. The folder is covered by `evaluation.json`'s `schema_version`; the `tables` stamp does not
   list it. Its rows carry no model key and it has no version of its own (Open questions).

### Score cells
Every metric reads one aggregate of a scorer's scores, as EDA's statistics read its counts table
(D-135, D-141 (b)). `score_cells(scores, cfg, by, edges, *, loss, column)` builds it in Spark;
`cells_from_rows` (`tests/cells_oracle.py`) is its pandas mirror, the oracle of the Spark test.
- **Grain:** one row per non-empty cell: `part, period` (its label), the columns of `by`,
  `score_bin, target_bin, replicate`. `by` is `["split"]` for the model (the `all` cells are
  those pooled over `split` with `pool_cells`, one Spark pass fewer), a stratum variable, or
  `[]` for a baseline. Strata cells are passed apart from the part's, so a stratum named `all`
  never stands for them.
- **Sums,** each weighted by the client's replicate weight (1 at replicate 0): `rows,
  target_sum, score_sum, sq_error_sum` (binary: the Brier sum), `abs_error_sum, loss_sum,
  target_sq_sum, link_sum`; beside them `score_min` and `score_max`, the cell's unweighted
  extremes.
  - `loss_sum` is the scorer's row loss (`scorer_loss(cfg, objective)`): `decision.metric` when
    it is a row loss, else the run's objective's (the task's `objective_losses`: the log loss for
    binary; the Tweedie or Poisson deviance), else none. The objective is the run's, from `run.json`, since a named run
    may have been trained under another. The Tweedie deviance is at the constant variance power
    1.5, never `training.tweedie_variance_power`. `cells.ROW_LOSSES` is the only definition of
    the row losses.
  - `link_sum` is the logit of the score clipped to [1e-15, 1 − 1e-15], filled for the log loss
    only; both are null for a scorer without a loss (the single feature).
- **Score bins** (the task's `score_grid` in `TASK_SPECS`, `bin_quantiles(grid)`): quantile
  bins of the scorer's column,
  cut once per scorer over every scored row with a known target of test and validation, so each
  `by` shares them. They narrow towards the top, where average precision, the top slices and the
  calibration intercept are read:
  - binary: 100 of 0.9% of the rows up to 0.9, 90 of 0.1% up to 0.99, 90 of 0.01% up to 0.999,
    100 of 0.001%;
  - regression: 25 of 3.6% up to 0.9, 25 of 0.36% up to 0.99, 25 of 0.036% up to 0.999, 25 of
    0.004%; fewer than binary, since each meets 20 target bins.
- **Two quantile passes** (`score_edges`, `quantile_passes(grid, tail_start)`): one
  `approxQuantile` at rank error 1e-4 cuts the body; the tail above the task's `tail_start`
  (0.99, both tasks) is cut by a second over the
  rows at or above the body's 0.99 edge, since its narrowest bins are below one pass's rank
  error. A value that fills a bin becomes its own bin.
- **The edges are a discretisation, not a choice:** they are cut over test and validation
  together, so test's rank metrics move in the fourth decimal when the validation period
  changes. `approxQuantile` merges one sketch per partition, so the edges also move inside its
  rank error with the partition layout: evaluating a run again gives the same tables to the
  binning's tolerance, the headline metrics to four digits.
- **Target bins:** binary, the target itself; regression, EDA's target bins cut from 4,000
  quantiles of the target.
- **Strata cells** use every `strata_step`-th edge (the task's; binary every fourth, regression
  every one)
  and, for regression, only the zero bin's edges, so a level's `events` count right. A
  level is capped as EDA caps it (`stratum_labels`): the `strata.max_levels` levels with most
  scored rows, the rest `__other__`, null and NaN `null`. After the aggregate, the `__other__`
  rows are checked against the counts of the levels not kept (`_check_other`, no extra Spark
  job).
- **The weights** (`client_weights`): one `array<int>` column, element r − 1 the Poisson(1)
  weight of replicate r from `xxhash64(client, r, "client_bootstrap")` through the inverse CDF
  (at most 17). Column expressions only; the array is exploded and summed in one `groupBy`, so
  the shuffle carries cells, not rows. A row of weight 0 counts nowhere in that replicate.
- **Checks** on replicate 0: a part of `test` and `validation` without a cell, a row with a
  null target (the caller passes the known-target rows), a null or NaN score, and a row outside
  its loss's domain each fail loud.
- **Tolerance:** the losses, the Brier sum, the errors and the deviance are exact per-row sums;
  only the rank metrics, the slices, the curves and the calibration line carry the binning's
  tolerance.
  - Binary, measured on 1 to 2 million simulated rows at base rates from 0.05% to 5%: average
    precision within 0.0015 of the row value, the calibration slope within 0.0003, the
    intercept up to about 0.0025 (0.0024 measured on a miscalibrated score at a 0.05% rate); a
    stratum's average precision 0.0007 low at a 2.9% rate. A grid whose top bins were 0.1% read
    average precision 4.7% low at a 1% rate and 61% low at 0.05%, which is why the tail is
    dense.
  - Regression, the capture of a top slice against the rows' own top list, on a million
    simulated amounts at three tail weights (maximum relative error):

    | Slice | 1 period | 4 periods |
    |---|---|---|
    | top 0.004% | 0 | 0.41 |
    | top 0.01% | 0.15 | 0.20 |
    | top 0.05% | 0.03 | 0.045 |
    | top 0.1% | 0 | 0.022 |
    | top 0.3% | 0.010 | 0.014 |
    | top 1% | 0 | 0.006 |
    | top 5% | 0.002 | 0.003 |

    The row list's own bootstrap error is 0.4 at 0.004%, 0.1 at 0.05% and 0.05 at 0.3%, so the
    binning's error stays inside the sampling error.
- **Size:** binary, at 1 million rows over 12 periods, about 6,900 cells per replicate with the
  periods apart, 715 pooled over them; regression about 1,050 to 1,600 non-empty cells per
  replicate on a million rows.

### Metrics
Every metric is computed per part, pooled and per period, and per stratum level, each with its
interval. The parts are `test`, `validation` and `validation_test_clients` (the validation
period's test-split clients only: a train client's earlier periods were fitted on). The metric
functions read one replicate's cells of one part; a metric the cells leave undefined is NaN,
decided from the cells, never by catching an error.

**Binary** (`binary_metrics(cells, base, has_loss=True)`)
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

Without a loss (`has_loss=False`, decided up front for a raw feature) the probability metrics are
NaN; a loss declared but null in a cell fails loud. On tied scores the cells' `ap` is the
expected value under random tie-breaking, while Training's, on rows, is scikit-learn's, which
gives every tied event the group's last precision: the two differ on heavily tied scores (0.1937
against 0.1664 on nine distinct scores).

**Regression** (`regression_metrics(cells, base, has_loss=True)`)
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
  Validation's headline pools both client splits: at the default `data.split.test_share` of
  0.3, about 70% of its rows are train clients, whose earlier periods were fitted on; view 17
  sets the test clients alone beside it.
- **Not built:** Gini and KS, which restate AUC on other scales; accuracy, F1 and a confusion
  matrix at 0.5, which mean nothing at a rare rate.

### Pooled and per period
D-098: a reader looks for one curve and one headline per split first, and a list is cut inside
one period.
1. **Pooled:** each part's curves (`curves`, `reliability`, `score_distribution`) and its
   headline are computed on all of its rows.
2. **Per period:** the `metrics` table holds every metric per observation period, `pooled`, and,
   over two or more periods, `mean` (the plain mean of the periods' values, its interval from
   the same draws). The pooled row and the mean are flags of the call, never read from a label,
   so a stratum level named `pooled` or `mean` is a level like any other. A period or the mean
   below `strata.min_events` events is `insufficient`: greyed in the views, never hidden.
   `events` are positive rows: a conversion counts once in every period whose target window
   holds it, so up to `w` times when pooled or in a stratum level, and the greying is on
   positive rows.
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
4. **Not available, decided from the declared slice and the population before any number**
   (D-035): a `top_n` above the period's population, and a slice narrower than 12 of the finest
   score bins (`narrowest_slice(grid, step=1)`, `MIN_SLICE_BINS`): 0.012% of the rows on
   binary's pooled grid, 0.048% for regression; the strata's composition reads its own grid at
   the task's `strata_step`, 0.048% for both tasks. A narrower slice reads "not available:
   narrower than X% of the rows, below which the score bins' error nears a slice's sampling
   error". Why 12: from there the measured binning error of regression capture is under half
   the sampling error ([the tolerance table](#score-cells)); binary near its guard is not
   measured. A slice not available in one period is not available in the sum, so no period
   drops out silently.
5. The cut bin is split in proportion to its rows (`cut_slices`, no row-level tie rule here),
   the one cut the slices and the strata's composition share.
6. Per slice, per period and pooled: rows, `target` (events or amount) captured, `capture` (the
   share of all events or of the total amount), `rate` (precision or mean) and `lift` (over the
   part's), the three rates each with its bootstrap interval; `unavailable` holds why a slice is
   not available and `no_interval` why a rate with a value has none. The capture view shows
   either in one `note` column.

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
   drawn), or a replicate without cells, has no interval. A replicate that drew no client of one
   period leaves only that period's slice rates and the pooled ones without an interval.
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
     share (`single_feature_warnings`); there is no threshold (Open questions).
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
  prediction"); a value the part's rows leave undefined reads `UNDEFINED` ("not available:
  undefined on this part's rows"). A cell is available only with no reason and a finite value.
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
   each period on the strata's grid and added up, each level's share of the population, its
   share of the list and the capture inside it. Without a slice, or one narrower than 12 of the
   strata's finest bins (0.048% of the rows, [slices](#slices)), it is "not available".
4. Levels are capped on the scored rows (Score cells); a level below `strata.min_events` is
   greyed, never hidden.
5. No tests across levels; a note says that many levels are read together. For binary only it
   adds that a level's ordering metrics come from coarser score bins than the pooled ones, so
   they read slightly low (`TASK_SPECS[task]["strata_clause"]`); a regression's levels keep
   the pooled grid.

### The explanation tables
1. **The cut** (`explanation_cut`): the decision's slice (`decision_slice`) on test, pooled; the
   score is the lowest of the first test score bin that reaches its depth (`curve_at_depths`).
   Without a slice, or when its row is not available, it falls back to `top 10%`
   (`FALLBACK_SLICE`, labelled by `slice_labels` as every slice is) with a warning.
2. **The samples** (`collect_explanation_sample`), from one collect of test rows with a known
   target, with their raw features and scores: the first `PERMUTATION_ROWS` (50,000; every row
   when fewer) in the order of a hash of the keys and `training.seed`, so a rerun takes the same
   rows, plus the three waterfall rows (`waterfall`): `highest` (the top score of test), `cut`
   (the score nearest the cut), `typical` (the sampled row nearest the sampled rows' median).
   - the **explanation sample** is the first 5,000 hashed rows (`EXPLANATION_ROWS`, flagged
     `sampled`) and the waterfall rows;
   - the **permutation sample** is every hashed row (`choices.permutation_rows` in the meta).

   They are the only test rows the driver holds.
3. **Contributions** (`compute_contributions`, stored as `contributions` with `waterfall` and
   `sampled`): the family's own contributions on the encoder's codes, in the shape of Training's
   `explanation_sample`. A row's contributions and base value must sum to its stored margin
   (within 1e-4), or it fails loud. They are on the margin's scale (the log scale for Tweedie and
   Poisson), which the views say; the package imports no `shap`. Every statistic below, and the
   importance bar and the beeswarm, reads the sampled rows only (`sampled_rows`): the waterfall
   rows are picked by hand, so they are drawn, never counted.
4. **The encoder's shares** (`encoding_shares`): `score_spark` returns scores only, so a Spark
   pass runs `encode_frame` per partition and counts, per part and feature, the null and
   unseen-level shares exactly as scoring codes them.
5. **The feature table** (`feature_table`, stored as `features`): per final feature, largest
   first, the test contribution share and rank, train's null share (the per-run ledger's: the
   frame the model was fitted on), the null and unseen shares on test and validation, and
   `null_not_in_train`, true for nulls at scoring and none in train: the model never learnt
   where they go, and a warning names them. Evaluation never rewrites `ledger_run.parquet`.
6. **Permutation importance per redundancy cluster** (`permutation_importance`, on the
   permutation sample): a cluster's members (the `stage2/` ledger's `cluster`; none, the feature
   alone) are permuted together, so near-duplicates do not split the credit. Each cluster takes
   `PERMUTATIONS` (5) seeded permutations; `loss_change` is their mean and `loss_change_sd`
   their standard deviation, in `decision.metric` as a loss. The SD covers the five
   permutations of the same rows only, not the draw of the rows. A rank check sets its order
   beside the contribution shares': the rank gap, the three largest gaps marked, Spearman's
   correlation. Whether it can be computed is decided up front (`permutation_unavailable`):
   - fewer events than `strata.min_events` in the sample, the count shown (events: rows with a
     non-zero target, the positive rows of a 0/1 target); a regression target without zeros
     makes every row an event, so the minimum then guards nothing;
   - a target of one value, with no loss to change;
   - a deviance metric under an objective without a log link, whose permuted predictions can
     leave the deviance's domain.

   The table is then stored empty with its columns and the bare reason goes to
   `evaluation.json`'s `unavailable`.
7. **The effect features** (`effect_features(run_ledger, eda_ledger)`): every key feature of
   the `stage2/` ledger the model uses (`key_features`) and the model's ten largest by
   Training's out-of-fold contribution share, twenty at most, the key features first when they
   do not all fit.
8. **Partial dependence and ICE** (`partial_dependence`) of the effect features on the sampled
   rows: a grid of about 20 quantiles of a numeric, or its 20 most frequent levels; the mean
   score and 50 ICE lines. A feature null on every sampled row is left out
   (`all_null_features`), with one line under `unavailable.partial_dependence` naming it.
9. **The effects table** (`effect_table`, stored as `effects`): per effect feature with EDA
   groups, in EDA's group order, the sampled rows' mean contribution per EDA group with its 95%
   interval beside EDA's rows, estimate and lift with its interval, both read from the
   `stage2/` copy. Each feature's kind is the `stage2/` ledger's. A numeric joins its group by
   its bucket on EDA's edges (a numeric without edges in the copy fails loud), a categorical by
   its level text (`__other__` when EDA has it); rows no group covers are counted
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
  cannot say; the warnings, Evaluation's first, then Training's under "From Training".
- **Core:** metrics per period, ROC and precision–recall, capture, reliability, score
  distribution, strata, importance, beeswarm, effects, waterfalls, sign-off (train only), search.
- **Extended:** thresholds, permutation importance per cluster, partial dependence and ICE,
  validation on test clients only.
- **Appendix:** the resolved config, the audit log's entries, the collected frames and the
  seconds per phase.

**How to read**, five notes: concordance (0.5 chance, 1 perfect; the AUC for a yes/no target);
lift (a slice's rate over its part's); intervals (the level, the client bootstrap, "value (low
to high)", "(no interval)" where a replicate left the metric undefined); grey (fewer than
`strata.min_events` events, still shown); null (a missing feature value, its own group last).

**What these numbers cannot say**, in plain sentences:
- Training's out-of-fold metric is optimistic, because the features and the configuration were
  chosen on the same folds; test is the first honest number for those choices.
- The train–test gap: train's in-sample concordance on the rows the model was fitted on,
  beside test's. For regression it is read on test's cells (`binned_concordance` of Training's
  `score_in_sample` on test's score edges and target bins; `in_sample_concordance_cells` in the
  meta), so both tie the same pairs; binary's is Training's on rows. In-sample scores above
  test's top edge tie in the last bin, so a regression's gap reads slightly small.
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
   definitions, another data definition than the config's, a run without `evaluation/`. Each
   run folder is then opened and its Training config (`training/resolved_config.yml`) read
   before any Spark work, so a missing or unreadable one fails first. Refused later: a stage json of another schema version; on the shared rows another target or client
   split; a part with no shared row; and a part where one run scored rows the other did not.
   Two runs of one data definition and split score the same rows, so a partial overlap means a
   source period changed after a run; the refusal names each run's rows and the shared ones,
   and asks to evaluate both again.
2. **The rows:** the two scores tables' rows with a known target, joined on the keys and
   `part`; `rows` gives per part each run's rows, the shared ones (all of them, after the
   refusals) and those scored differently. Each run's cells are summed with its own bins and its
   own objective's row loss.
3. **Test** (`metrics`, `differences`): both runs' metrics side by side, and per metric with a
   direction (`TASK_SPECS[task]["metric_directions"]`) the difference b − a, the percentile
   interval of the replicates' differences and the verdict `better`, `worse`, `no clear
   difference` or `not available`. A loss metric under two different row losses gets no
   difference, with the reason; a difference undefined on the shared rows or in a replicate
   reads `not available` with `NO_DIFFERENCE` as its reason.
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
- `evaluation.json` (the commit marker; its content is assembled by `build_result` in
  `evaluation/meta.py`): the stamp (`schema_version` 2, `stage`,
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
  - `choices`: `headline`, `objective` (the run's own `training.objective`, from its
    `run.json`: a named run may have been trained under another config; the contribution
    views' scale note reads it), `single_feature` (feature, kind, sign, levels, train
    concordance, or null), `explanation_cut`, `key_features`, `effect_features`,
    `permutation_rows`;
  - `unavailable`: `{table: reason}`, the bare reason, for each table decided up front as not
    computable or not whole, `{}` when none is: `permutation_importance` and
    `partial_dependence` can appear;
  - `in_sample_concordance_cells`: train's in-sample concordance on test's cells (regression;
    null for binary);
  - `training` (Training's metrics), `training_warnings` (Training's sentences, as written),
    `trained_at`, `training_seconds`;
  - `timings.seconds`: the laps `open`, `scoring`, `tables`, `explanation`, `views`, `card`;
  - `earlier_validations`: `seq, time, run_id, validation_period` of each earlier Evaluation
    `run` entry in the audit log;
  - `drift_reference_schema_version` (2), as in the drift reference's sidecar below;
  - `warnings`: a list of `{code, values…, text}`, the only place they are written:
    `newer_runs_passed_over` with `runs` (each "r007: why it was passed over");
    `single_feature_baseline_not_chosen`; `single_feature_baseline_has_nulls` with `feature`
    and `train_null_share`; `nulls_not_in_train` with `features`;
    `explanation_cut_not_at_decision_slice` with `slice` and `reason`. The report shows the
    text; the card copies the code and the values. Training's warnings reach the report only,
    never the card's considerations (Open questions).
- `tables/` (parquet; a table name two steps write fails loud, `_merge_tables`):
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
    periods and every scored test row's score counts on the model's edges, a null target
    included (`reference_score_counts`, which refuses a null or NaN score;
    [monitoring](monitoring.md)).
- `_drift_reference.json` (`DRIFT_REFERENCE_FILE`), the drift reference's sidecar, written in
  the same stage write: `drift_reference_schema_version` (2), the `model_hash` and `run_id` it
  is the yardstick of, `framework_version` and `written_at`. Nothing reads it until Monitoring
  is built, which must check it. The reference lives inside `evaluation/`, so a re-evaluation
  replaces it; `register` taking a snapshot of it, so a production model's yardstick cannot
  move under one `model_hash`, is planned for M2.4, not built.
- `scores/`: the scores table (Spark parquet).
- `report.html`: the model results report ([reporting](reporting.md)).
- `model_card.json` and `model_card.html`: the card. `reporting/card.py` owns
  `CARD_SCHEMA_VERSION` (2) and `CARD_SECTIONS`, and `render_card` refuses a card of another
  version; [reporting](reporting.md) owns the sections' content. `build_card` takes the
  `RunFolder` that `check_card_inputs` read, or reads it itself through `open_run_folder`, and
  refuses pieces of different runs or models, and a config other than the one Evaluation ran
  with. It writes `framework_versions.card`, the version that wrote the card, beside the
  training version; the data section's `rows_per_period` holds per-period rows only, with
  `rows_pooled` and `rows_validation_test_clients` beside it. What every score is conditional
  on and the score's column are declared constants (`CONDITIONAL_ON`, `SCORE_COLUMN`), not
  read from the run; so are the keys it copies from Training
  ([reporting](reporting.md#the-model-card)).
- `log.json` (the frames' steps and the samples' collect) and `resolved_config.yml`.

The audit log then gains a `run` entry of stage `evaluation` with the run and the scored
validation period in a field of its own; it never blocks a later move of the validation period,
which reads Feature Checks' entries only ([config](config.md)).

### The compatibility table
`VIEWS` in `evaluation/report.py` (D-035, D-100 (b)) holds one row per view, keyed by its name
in the report's order: its `title`, its `section` (summary, core or extended) and its `view`, the
function, or per task the function or the reason the task cannot produce it. A new view is one
row. The decision is made up front, never by catching an error (T17), and a reason renders as
"Not available: reason." (`not_available`). Every family has its own contributions, so the
entries differ by task only: regression has no `curves`, `score_distribution` or `thresholds`
("the target is an amount, without classes"). A view named in `evaluation.skip_views` is left
out; the summary always renders. An unknown name in `skip_views` is refused at run time
(`check_skip_views`), so the view names are part of the config contract: renaming one needs an
alias or a migration.

### Tests
- **No Spark,** on constructed cells: each metric against scikit-learn on rows; the dense-top
  bins; the average precision and the calibration line within 0.002 of the rows at a 0.1% rate
  on a million rows; the slope on simulated miscalibration; a score of exactly 0 or 1 keeps the log loss
  finite; a scorer without a loss is declared up front; the slices add up over periods, a
  `top_n` above the population is not available, and a regression slice reads the rows' own top
  while a narrower one is not available; a stratum named `all` with levels `mean` and `pooled`
  reads its own cells; `binned_concordance` on the cells' buckets; the client interval covers
  the value and is wider than a row bootstrap; an undefined replicate gives no interval; the
  chart tables agree with the metrics; the baselines' choices and reasons, an undefined value
  read as not available; the effects' group joins; the effect features at most twenty with
  every used key feature; the permutation guards, and a cluster
  permuted as one on its own sample; a feature null on every sample row leaves the partial
  dependence; train's in-sample concordance read on test's cells; the card's sections,
  refusals, JSON types and a card of another version refused; the views of both tasks, the
  warnings section; two steps' tables of one name refused; `compare_runs`' verdicts, directions
  and refusals of a difference off test, and its refusal of rows only one run scored.
- **Spark, run by the main thread on `unit`:** the cells equal their pandas oracle; the weights
  repeat per client and are Poisson(1); a part without rows and a bad request fail loud;
  differing features are refused; one row per client, period and part; null-target rows change
  no cell and count in the drift reference; the drift reference is a valid input of `psi`; the
  contributions sum to the margin; the samples repeat and the waterfall rows are marked; every
  table is written; the `run` entry; a
  failure after the scores are staged leaves no staged scores, keeps the earlier `evaluation/`
  and records no entry; a run of another data definition is refused; the explanation cut's
  fallback; an older run evaluated again with only `evaluation/` changed; `compare_runs` against
  itself differs by zero, differs on test only, refuses two data definitions and an unevaluated
  run; the CLI runs every stage on both configs and refuses `run` outside Evaluation alone.
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
  `CELL_EXTREMES`, `PARTS`, `POOLED`, `MEAN`); `bin_quantiles(grid)`,
  `narrowest_bin(grid, step=1)`, `quantile_passes(grid, tail_start)`, which take the task's
  grid from the caller; `pool_cells`.
- `statistics/metrics.py`: `binary_metrics`, `regression_metrics`, `binned_concordance`,
  `slice_labels`, `cut_slices`, `slice_metrics`, `slice_rates`, `threshold_table`,
  `curve_at_depths`, `reliability_table`, `distribution_table`.
- `statistics/bootstrap.py`: `bootstrap_intervals`, `replicate_values`.
- `tasks.py`: the per-task entries: the metrics (`cell_metrics`, `order_metrics`,
  `metric_keys`, `metric_directions`, `undirected_metrics`, `reliability_groups`,
  `prediction_range`, `strata_absent_metrics`, `roc_curve`, `target_class`); the cells
  (`score_grid`, `strata_step`, `tail_start`, `objective_losses`); the report's wording
  (`calibration_metrics`, `note_below_events`, `strata_metrics`, `events_noun`,
  `strata_clause`, `summary_statement`, `margin_scale`, `log_link_scale`).
- `runs.py`: `find_run` (the run and the newer runs it passed over). `run_artifacts.py`:
  `open_run_folder` (`RunFolder`), `read_training_tables`, `CARRIED_TABLES`,
  `read_stage2_copy`, `read_run_ledger`, `train_level`, `read_in_sample`. `artifacts.py`:
  `check_siblings`.
- `evaluation/scores.py`: `score_parts`, `write_scores`.
- `evaluation/cells.py`: `client_weights`, `scorer_loss`, `score_edges`, `score_cells`,
  `reference_score_counts`, `stratum_labels`, `ROW_LOSSES`.
- `evaluation/tables.py`: `metric_tables`, `metric_rows`, `part_cells`, `pooled_metrics`,
  `headline_names`, `metric_key`.
- `evaluation/slices.py`: `decision_slice`, `slices_table`, `composition`, `narrowest_slice`
  (`MIN_SLICE_BINS`), `CAPTURE_DEPTHS`.
- `evaluation/baselines.py`: `choose_single_feature`, `single_feature_warnings`,
  `carried_columns`, `baseline_columns`, `describe_baseline_columns`, `add_baselines`,
  `baseline_loss`, `compare_baselines`, `UNDEFINED`.
- `evaluation/drift_reference.py`: `build_drift_reference`, `drift_reference_sidecar`
  (`DRIFT_REFERENCE_SCHEMA_VERSION`, `DRIFT_REFERENCE_FILE`).
- `evaluation/explain.py`: `explanation_cut`, `collect_explanation_sample`, `sampled_rows`,
  `compute_contributions`, `encoding_shares`, `contribution_shares`, `feature_table`,
  `all_null_features`, `partial_dependence`, `FALLBACK_SLICE`.
- `evaluation/permutation.py`: `permutation_unavailable`, `permutation_importance`,
  `PERMUTATION_ROWS`, `PERMUTATIONS`.
- `evaluation/effects.py`: `key_features`, `effect_features`, `effect_table`.
- `evaluation/views.py`: views 2–7, 12–14 and 17 (12 and 13 call
  `reporting/training_views.py`), the shared cell formats (`interval_text`, `wide_metrics`), and
  `CALIBRATION_CHARTS`, the calibration chart per task, which stays beside the views because
  `tasks.py` must not import the reporting side.
- `evaluation/views_summary.py`: view 1, `baseline_table`.
- `evaluation/views_explain.py`: views 8–11, 15 and 16.
- `evaluation/report.py`: `VIEWS`, `check_skip_views`, `report_views`, `render_views`.
- `evaluation/card.py`: `check_card_inputs`, `build_card`, `CONDITIONAL_ON`, `SCORE_COLUMN`,
  `CARD_FOLD_KEYS`, `CARD_SEARCH_KEYS`, `CARD_CALIBRATION_COLUMNS`.
  `reporting/card.py`: `CARD_SCHEMA_VERSION`, `CARD_SECTIONS`, `render_card`.
- `evaluation/compare.py`: `compare_runs`, `NO_DIFFERENCE`.
- `evaluation/meta.py`: `build_result` (`Opened`, the run as found and read, with the newer
  runs passed over), `evaluation.json`'s content and the warnings.
- `evaluation/run.py`: `run_evaluation`, the flow of Level 2; it orchestrates only, the
  permutation table included (`_permutation_table`).
- Reading order for review: `run_evaluation`, then `score_cells` with `client_weights`, then
  `binary_metrics` against `test_metrics.py::test_binary_metrics_match_scikit_learn_on_the_rows`
  and the cells against
  `test_evaluation_tables.py::test_score_cells_equal_their_pandas_oracle_at_replicates_0_and_1`,
  then `compare_runs`.

### Interface
Public: `run_evaluation`, `compare_runs`, `check_card_inputs`; `load_bundle`, `Bundle` and
`score_frame` are [model bundle](model_bundle.md)'s. CLI: `run <config> --stages evaluation
[--run r007]`; a bare `run` runs `DEFAULT_STAGES`, Training and Evaluation included.

```python
def run_evaluation(cfg, entity, env, spark, run: str | None = None) -> StageResult: ...
def compare_runs(cfg, entity, env, spark, run_a: str, run_b: str) -> dict[str, pd.DataFrame]: ...
def run(config_paths, env_path=None, stages=None, entity=None, run: str | None = None) -> dict: ...

def binary_metrics(cells: pd.DataFrame, base: float, has_loss: bool = True) -> dict[str, float]: ...
def regression_metrics(cells: pd.DataFrame, base: float, has_loss: bool = True) -> dict[str, float]: ...
def slice_metrics(cells: pd.DataFrame, slices: Slices, population: int,
                  narrowest: float) -> pd.DataFrame: ...
def bootstrap_intervals(replicate_cells: pd.DataFrame, metric: Callable, level: float,
                        replicates: int) -> dict[Hashable, tuple[float, float]]: ...

def score_parts(bundle_folder: str, bundle: Bundle, rows: DataFrame, cfg,
                baselines: list[str]) -> DataFrame: ...
def write_scores(scores: DataFrame, stage_folder: str) -> str: ...
def client_weights(client: Column, replicates: int, salt: str) -> Column: ...
def score_cells(scores: DataFrame, cfg, by: list[str], edges: dict, *, loss: str | None,
                column: str = "score") -> pd.DataFrame: ...
def metric_tables(cells: dict[str, pd.DataFrame], strata: dict[str, pd.DataFrame], cfg,
                  base: float, population: dict[str, int], *,
                  loss: str | None) -> dict[str, pd.DataFrame]: ...
def compare_baselines(metrics: dict[str, pd.DataFrame | None], cfg, base: float,
                      facts: dict, objective: str) -> pd.DataFrame: ...
def build_drift_reference(stage2: dict[str, pd.DataFrame], counts: pd.DataFrame,
                          features: list[str]) -> dict[str, pd.DataFrame]: ...
def check_card_inputs(run_folder: str, resolved: UseCaseConfig) -> RunFolder: ...
def build_card(run_folder: str, tables: dict, meta: dict, resolved: UseCaseConfig,
               read: RunFolder | None = None) -> dict: ...
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
- **`frames.rows` is computed several times per run** (the baseline facts, the scoring, the
  samples' collect, the encoding shares). To time on a full population inside the bank before
  deciding whether to persist it.
- **Training's warnings** in `training.json` are sentences, not codes with values, so the card's
  considerations cannot carry them yet (a Training artifact change); the report shows them.
- **The scores table's identity.** Its rows carry no model key (`model_hash`, `run_id`) and it
  has no version of its own; inside `evaluation/` the folder and `evaluation.json` give both.
  Inference's shared scores table (D-007) is a different table and will need both on its rows.
- **`score_edges` inside the bank:** every scorer takes two quantile passes (the grid, then the
  tail above 0.99 at a finer error); to time on a full population.
- **A 0.99 edge on a mass point:** when one value holds nearly every row (a raw-feature
  baseline at 0 on 99% of rows), the tail pass reads nearly every row; the edges stay valid,
  only coarser.
- **The single feature's nulls:** whether the choice should rank candidates with a null as
  their lowest value, as the baseline then scores it, instead of on the rows where they are
  known.
- **To measure:** the bootstrap's seconds per replicate on the cells at the bank's size; the
  three model libraries importing and scoring one batch on a bank executor (spike 5's trip),
  which the chunked driver path depends on.
