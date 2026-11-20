# Stage 3 major step 3 (Evaluation): review guide
_Written 2026-11-17 for the EDS · review 1 of step 3, read together with review guide 2
([`review_guide.md`](review_guide.md)) · the plan: [`plan.md`](plan.md) beside this file · this
file holds the current review only_

**In short.** Evaluation is built. `run_evaluation` judges one trained run on its test clients
and the validation period, outside the engine and against the declared baselines. It writes
`evaluation/` into the run folder: the scores table, the metric tables with client-bootstrap
intervals, the explanation tables, the drift reference, the seventeen-view report and the model
card. `compare_runs` sets two evaluated runs side by side, with differences on test only. Every
plan item from m3.1 to m3.10 is built. The version is 0.4.0, and nothing is
committed. **Know this first:** the review of step 2 is still open, and step 3 builds on step
2's contracts as they stand, so a contract the joint review changes is fixed in both (§5). No
review found a leak or a split or time violation. The ML audit's one blocking finding is fixed
(A103).

## 1. Decide first: the defaults taken without asking
The build never stopped for a question. A92 to A102 are the plan's defaults (their planned form
is in `plan.md` → "Settled at the start of step 3"; here they are as built). A103 onwards are the
build's own defaults, numbered here so you can veto by number. Most consequential first.

**These change what a number means, or what you decided before**
- **A103 The score bins are dense at the top** (the ML audit's blocking finding; replaces A93's
  200 bins). Binary has 380 bins: 100 of 0.9% of the rows up to 0.9, then 90 of 0.1%, 90 of
  0.01% and 100 of 0.001%. A second `approxQuantile`, at the same rank error 1e-4, cuts the rows
  at or above the body's 0.99 edge. Regression has 50 bins (25 of 3.6%, 25 of 0.4%). The strata
  take every fourth binary edge (95 bins) and all 50 regression edges. Average precision from
  cells is within 0.0015 of the row value at base rates from 0.05% to 5%. The previous grid read
  it 4.7% low at 1% and up to 61% low at 0.05%, and biased the calibration intercept. Cells per
  replicate grow about 1.5 to 1.8 times.
- **A104 The single-feature baseline is chosen on the train rows where the feature is known,**
  and its nulls score lowest on every row. When the feature has nulls on train, the warning
  `single_feature_baseline_has_nulls` gives the train null share (from the per-run ledger). There
  is no threshold and no new choice rule. *Alternative:* rank the candidates with the null as the
  lowest value.
- **A105 Regression's train concordance is on rows, test's on cells,** which reads up to about
  0.01 higher. The summary's gap sentence says so. *Alternative:* Training computes its own
  concordance on cells.
- **A106 `events` under `strata.min_events` are positive rows.** A conversion counts in every
  period whose target window holds it, so pooled or in a stratum level it can count up to `w`
  times. The report's and `config.md`'s wording changed; the column name stays.
- **A107 Permutation importance averages five seeded permutations,** with `loss_change_sd`
  beside the mean. It is "not available" when the explanation sample's target has one value
  (no positive row, no negative one, a constant amount), decided up front (`evaluation.json` →
  `unavailable`).
- **A108 Training's warnings stay free text,** so the card's considerations carry Evaluation's
  warnings and the recorded facts only. Codes with values would change step 2's `training.json`,
  so this is not built. It is an open question in
  [`evaluation.md`](../../docs/components/evaluation.md).

**The plan's defaults, as built**
- **A92** As planned. The stored `cells` table keeps replicate 0 only: the `split` cells and each
  stratum's, with `by` and `level`.
- **A93** Replaced by A103.
- **A94** As planned: `xxhash64(client, r, "client_bootstrap")` through the inverse Poisson CDF
  (at most 17 comparisons), exploded and summed in one `groupBy`. A weight-0 row counts nowhere
  in that replicate.
- **A95** `bootstrap_intervals(replicate_cells, metric, level, replicates)` gains `replicates`,
  and `replicate_values` sits beside it. A metric undefined in any replicate has no interval.
- **A96** As planned. The meta key is `eligible_rows` (not `population`). It counts null-target
  rows on purpose: a `top_n` list is cut before any target is known.
- **A97** As planned. A carried column that is no candidate is refused. The carried source
  columns are dropped once read (unless a stratum), so only their `baseline_<form>` scores are
  stored.
- **A98** `metric_tables(cells, cfg, base, population, *, loss)` also returns `pooling`.
  `feature_table(contributions, shares, run_ledger)` takes no `stage2`: train's null share is the
  per-run ledger's, taken on the frame the model was fitted on.
- **A99** Named `training/gate.py::read_stage2_copy`, since `read_stage2` was taken.
- **A100** As planned.
- **A101** As planned. `write_stage(…, folders=)` moves `evaluation.scores-<pid>` in before the
  swap. A leftover `.scores-*` is refused until a person removes it.
- **A102** As planned, plus `mean_score` and `mean_target` on every `metrics` row and an interval
  on each slice's capture, rate and lift. `distribution_table` gives `score_bin, score,
  percentile, class, rows, share, ratio`, and the chart draws `ratio` (1 is chance) against
  `percentile`: per-class shares stepped at the 90th percentile under unequal bins.

**Finding the run, refusals, what is written**
- **A109** `find_run` matches the data-definition hash, the Training settings digest and the
  sources digest. A named run with another client split or other sources, or without
  `training/`, is refused.
- **A110** Every refusal comes before Spark: leftovers beside `evaluation/`, a killed run's
  staged `evaluation.scores-*` among them (`check_siblings`), a
  run folder the card cannot be built from (`check_card_inputs`), and missing `training.json`
  keys.
- **A111** `evaluation.json` gains `training_config_hash`, `row_loss`, `unavailable`,
  `eligible_rows` and `earlier_validations`. Its `warnings` are `{code, values…, text}`, and this
  is the only place warnings are written.
- **A112** A config that names one baseline form twice is refused at load. No schema version
  changes.
- **A113** `evaluation/tables/` stores Training's `signoff`, `trials` and `explanation_sample`
  again (prefixed `training_`), so `evaluation/` renders alone. It stores the `effects` table in
  place of copies of EDA's tables.

**Scoring and cells**
- **A114** Prediction threads: each family's `predict(…, threads=None)` and
  `score_frame(…, threads=None)`; `score_spark` predicts on `spark.task.cpus`. Measured by
  default, LightGBM uses 7.3 cores and XGBoost 5.9. Margins are bit-identical at any count, and
  XGBoost restores its booster's own setting afterwards.
- **A115** The score edges are cut over test and validation together. This is a discretisation:
  when the validation period moves, test's rank metrics move in the fourth decimal.
  *Alternative:* cut on test alone and bin validation on test's edges.
- **A116** Stratum levels are capped on the scored rows, not EDA's snapshot, and the `__other__`
  rows are checked against the levels not kept. A regression stratum's cells carry only the
  zero-bin target edges, so a level has no concordance.
- **A117** The row loss is `decision.metric` when it is a row loss, else the run's objective's.
  The objective is read from `run.json`, not today's config.

**Metrics, slices, baselines**
- **A118** `log_loss` is itself a metric. Over two or more periods, a `mean` row sits beside
  `pooled`, and the `pooling` note fires when their intervals do not overlap.
- **A119** The fixed capture depths 1, 2, 5, 10, 20, 30 and 50% are added to the configured
  slices.
- **A120** `decision_slice` is `decision.n` for a `top_n` decision, else the first `top_pct`,
  else the first `top_n`. It sets the strata's list composition and the explanation cut. With no
  usable slice the cut falls back to `top 10%` with a warning, and a configured label without a
  row fails.
- **A121** `base` is `sampling.true_rate` when Training sampled, else the mean target of
  `oof.parquet` (`train_level`). No key is added to `training.json`.
- **A122** `population_base_rate` and a historic rate number are compared on mean prediction,
  beside an `observed` row. A column baseline with nulls, or outside [0, 1], fills the order
  metrics only, with nulls scoring lowest. Baselines are measured pooled (`all` cells) only.
- **A123** The single feature is the per-run ledger's highest `train_concordance` among the
  numerics and the ordered categoricals (ordered = named in the run's `features.order`), with
  ties going to the ledger's first. An unordered categorical is never chosen.

**Explanations**
- **A124** EDA's key features are the `stage2/` ledger's rows with a `key_feature` value.
  Unverified: whether a person's `include` reaches that column.
- **A125** The effect features are ranked by Training's out-of-fold contribution share, not
  test's.
- **A126** `effects.py` finds a numeric's EDA group by parsing the group label's opening bound.
  A feature without a lift gets one row, with its reason in `unavailable`, and view 10 draws its
  dependence scatter instead. *Alternative:* EDA stores `bin_order_first` and the lift's interval
  (EDA schema 5 to 6), which retires the parsing.

**Report, card, drift reference, `compare_runs`, notebook, acceptance**
- **A127** Report views:
  - view 5 adds the calibration intercept, and the reliability axes run from 0 to 1.25 × the
    highest value, with nothing greyed;
  - view 7 in regression shows RMSE, MAE and predicted to observed;
  - view 14 is read from the curves at the capture depths;
  - view 17 puts all validation clients beside the test-split ones;
  - view 2's line plots `decision.metric` only.
- **A128** A cell reads "value (low to high)", `undefined`, or "value (no interval)". The
  regression deviance is named by `row_loss`, and dropped when there is none.
- **A129** `skip_views` takes `report.py::VIEWS` names, and an unknown name is refused, so the
  view names are now config contract.
- **A130** `build_card` lives in `evaluation/card.py` and `render_card` in `reporting/card.py`
  (`render_report(plotly=False)`). `CARD_SCHEMA_VERSION` is 1. Config sections are embedded as
  dumped, so the card follows the config schema. The card names no one who started the run. The
  model key, the parent run and its metrics are None until M2.4. The card refuses another
  `config_hash`.
- **A131** The drift reference is three tables in `evaluation/tables/` (`drift_features`,
  `drift_edges`, `drift_scores`), with `drift_reference_schema_version` 1 in `evaluation.json`.
  It is not a separate artifact keyed by `model_hash` (D-054 (a drift reference per run, keyed by
  `model_hash`)). Its scores are 10 quantile groups of the pooled test scores, not 20 per period.
- **A132** `compare_runs`:
  - only a metric with a direction gets a difference;
  - runs that score every shared row alike share one set of cells (a difference of exactly 0);
  - a loss metric under two different row losses gets no difference;
  - it refuses another entity, an unevaluated run, shared rows with another target or split,
    and a partial overlap of the scored rows.
- **A133** Notebook 05:
  - there is no helper module: the run cell flattens `result.views` in one dict comprehension,
    and each view cell is `display(*views[...])`;
  - as shipped, step 11 compares the run with itself;
  - a view named in `skip_views` must be deleted from the notebook by hand.
- **A134** Acceptance tests:
  - test 1 is a plain `>`, with no interval;
  - test 4 checks observed to expected on test only;
  - the runs use 100 replicates and `lgbm` at 15 trials; the downsampled run uses 20 replicates.
- **A135** Nine modules exceed the ~300-line guideline and are kept whole as tied functions
  (`CLAUDE.md` §1.5). They are `run.py` 511, `compare.py` 484, `tables.py` 441, `explain.py`
  412, `cells.py` 398, `statistics/metrics.py` 376, `evaluation/card.py` 358, `baselines.py` 351
  and `views.py` 346. Where to cut is your call.

## 2. What step 3 changed in step 2's code and contracts
No `schema_version` changed, and step 2's run folders still load (`compat-guardian`).
`training/run.py` is untouched.
- `training/gate.py::read_stage2_copy` is the only reader of `stage2/`. It reads `_stage2.json`
  first and refuses an EDA stage or ledger schema version it does not read.
- `training/tables.py::train_level` returns the base (A121).
- `training/views.py::search_table` is now public, shared by notebook 04 and report view 13.
- The families' `predict` and `score_frame` take `threads`; `score_spark` passes the task's CPUs
  (A114). Training passes nothing, so each library keeps its default.
- `dataset/frames.py`: `build_frames(…, carry=)` (Evaluation's only), the meta's
  `eligible_rows`, and a callout for the explanation sample's collect.
- `artifacts.py`: `write_stage(…, folders=)`, `check_siblings` (now public) and
  `read_stage_meta`.
- `run.py` and `__main__.py`: `STAGES` gains `evaluation`, so a bare `run <config>` now trains
  **and** evaluates (A91 extended). `run=` and `--run` work with Evaluation alone (A100).
- `tasks.py`: `TASK_SPECS` gains Evaluation's keys, `ZERO_BIN_EDGES` is public (shared with EDA's
  target bins), and `tasks.py` imports `statistics/metrics.py`.
- `config/schema.py`: a baseline form named twice is refused (A112).
- `statistics/distributions.py::bin_orders` moved there from `eda/deep_dives.py`.
- `reporting/html.py::render_report(plotly=False)`.
- `reporting/explain_charts.py`: `group_means` and `effect_chart` are public, and
  `pdp_ice_chart` is new.
- Notebook 04's closing line; `00_modelling_helper` gains section 10 (Evaluation).
- `training.json` is now a contract. Evaluation and the card read its `run_id, settings, search,
  metrics, final_features, sampling, folds, reproducible_to, written_at, timings.seconds`, and
  Training's tables `signoff, calibration, selection, trials, explanation_sample` and `oof`.

## 3. What was run
| Check | Result |
|---|---|
| Spark batch after the fix round: the evaluation, card, report, views, effects, compare, metric and explain tests with `test_run` | 201 passed, 5 min 49 s; they ran again inside the full suite after the last code edit |
| Acceptance and trap tests on `dev` | 20 passed, 6 min 45 s, before the fix round; after it they passed inside the full suite |
| Slow tests | all passed inside the full suite except the four family tests on `dev`, which met `dev_stage2`'s EDA under a shared data root and were refused ("read from other data"). They now have a data root of their own (`family_env_file` in `tests/test_training.py`). Run again in one session with the trap tests: 156 passed, 1 failed (three families passed; `lgbm` hit the laptop's socket-buffer fault in a collect, T51). The four alone after that: 4 passed, 4 min 43 s |
| Full suite once, after the last code edit (`-m "slow or not slow"`) | 1204 passed, 5 failed, 26 min 9 s. Neither cause was in the framework's code: a comment in `TEMPLATE.yml` read as an unfilled placeholder, and the four slow family tests shared a data root with the new `dev_stage2` fixture (see "Slow tests"). Both are corrected and the five were run again; the whole suite was not run a second time |
| Notebooks `05_evaluation` and `00_modelling_helper`, scratch copies on `dev`, after the last edit | 17 of 17 and 16 of 16 code cells, no error |
| One run evaluated twice, `evaluation/tables/` compared (rerun determinism) | all 20 tables identical: largest numeric gap 0, the other columns and the nulls equal |
| `ruff check .` and the format check, after the last code edit | pass: no finding, 222 files already formatted (`src/`, `tests/`, `notebooks/`, `synthetic/`) |
| `__version__` | `0.4.0`, printed from the installed package |

**The reviews.**
- Each wave had one combined `code-reviewer`. Every blocking finding was fixed: 1, 1, 3 and 5
  by wave.
- The Spark tests caught one real bug: Spark's `greatest` and `least` skip a null, so the
  single-feature baseline gave a null numeric the top score for a falling feature. Fixed.
- At the close:
  - the ML audit of Training through Evaluation found 1 blocking and 8 should-fix findings. The
    blocking one is A103. For the should-fix ones, A104 to A107 and the named run's
    `training_config_hash` and `row_loss` (A111) were taken as defaults; the rest are fixed by
    A103's grid or by one sentence;
  - `compat-guardian` found no break and called for a minor bump;
  - `silent-failure-hunter` found 0 blocking and 4 should-fix findings, all fixed;
  - after one fix round, a `code-reviewer` ran on it: 0 blocking, 4 should-fix findings and
    4 nits. The should-fix ones are fixed (A107's refusal on one target value, A110's check
    for staged scores before any Spark work, one read of the run folder for the card, three
    stale texts). Two nits are left: `compare_runs`' `rows` table shows three counts that
    are now always equal, and the bundle is hashed three times per run.

**Measured.** Binned minus row values, on 1 to 2 million simulated rows:

| At | Old grid | Dense grid |
|---|---|---|
| Average precision, 1% | −0.008 | −0.0002 |
| Average precision, 0.1% | −0.164 (−44%) | −0.0013 |
| Average precision, 0.05% | −0.399 (−61%) | −0.0014 |
| Calibration intercept, 0.1% | −0.358 | +0.0009 |
| Stratum's average precision, 2.9% | −0.0101 | −0.0007 |

- The calibration slope is within 0.0003 on both grids.
- Cells per replicate at 1 million rows over 12 periods: per period 4,485 → 6,859, pooled 400 →
  715.
- `metric_tables` takes 11.1 s at 200 replicates with three strata (on the old grid).
- The pages are 5.9 MB for binary and 5.6 MB for regression, mostly plotly.js.

## 4. What to read, in this order, and what "right" looks like
1. **Notebook `05_evaluation.ipynb`, run right after `04_training`** (35 cells, 17 of them
   code). Read its guide cells as code, then `report.html` section by section; the page is the
   evidence for the views' code. **Right:** a person who ran 04 can evaluate, read every view,
   compare and sign off without opening a doc. What to check, step by step:
   - step 1: `RUN = None` takes the latest trained run;
   - step 2: a failure leaves the run as it was;
   - step 3: the summary opens with what was chosen before any result (§4.3), shows the
     baselines without "passed", the "cannot say" list, and each warning with what to do;
   - step 4: grey is shown, never hidden, and the `mean` row sits beside `pooled`;
   - steps 5 to 7: slices cut per period, the score distribution as a ratio to chance, each
     stratum level with its support;
   - step 8: test against train out of fold, the effects beside EDA's lift;
   - step 11: the comparison on test only;
   - step 12: the sign-off gate with Training's view;
   - the closing checklist.
2. **`evaluation/run.py`** (511; `scores.py` 103 with it): the stage. **Right:**
   - it only orchestrates;
   - `_open_run` holds every refusal before Spark (A110);
   - it scores once, writes first, and reads the scores back (A101);
   - `score` is `score_frame`'s, with calibration and the prior-shift offset applied, so
     observed to expected reads the true rate;
   - the base comes from train and the single feature from the ledgers;
   - it makes one `write_stage` call, then the audit entry;
   - `_discard` keeps the original error.

   **With suspicion:** anything computed inline, and any read of test or validation that feeds
   a choice. The explanation cut reads test, but only to place the sample.
3. **The cells and the client bootstrap:** `statistics/score_cells.py` (206), `evaluation/cells.py`
   (398), `statistics/bootstrap.py` (97). **Right:**
   - every sum is per row, in Spark, so the losses, errors and deviance are exact, and only
     rank metrics, slices, curves and the calibration line carry the binning;
   - the score edges use no label;
   - a client's rows share one weight per replicate, and two runs share the weights;
   - replicate 0's checks fail loud: a part without cells, a null score, a row outside its
     loss's domain;
   - an undefined replicate gives no interval.

   **With suspicion:** `quantile_passes` and the tail pass in `score_edges` (A103),
   `_check_other`, `pool_cells`.
4. **`statistics/metrics.py`** (376). **Right:**
   - each metric is a function of one replicate's cells;
   - a NaN is decided from the cells, never by catching (D-035 (incompatible outputs decided
     up front));
   - the AUC counts a shared bin as half;
   - average precision is the binned precision–recall area;
   - the log loss is on the clipped score;
   - the skill scores are against the train base.

   **With suspicion:** `slice_metrics`, with the cut bin split in proportion and a `top_n` as a
   share of `eligible_rows`.
5. **`evaluation/tables.py`** (441). **Right:** the parts `test`, `validation` and
   `validation_test_clients` are reported per period, pooled and as the mean. Nothing is chosen
   here (D-083 (validation reported, never chosen on)). Greying counts positive rows (A106).
6. **`evaluation/baselines.py`** (351). **Right:**
   - no test row is read to choose the feature (§4.4);
   - what a column baseline can fill is decided up front from one aggregate (`baseline_loss`);
   - `compare_baselines` writes no "passed" or "failed" (D-032 (no gates; a person judges)).

   **With suspicion:** the null handling in `_single_feature_score` (the bug in §3), and A104.
7. **`evaluation/explain.py`** (412) **with `effects.py`** (162). **Right:**
   - 5,000 seeded test rows, the same on a rerun;
   - contributions plus the base value equal the margin within 1e-4;
   - `encoding_shares` codes nulls exactly as scoring does;
   - a cluster is permuted as one;
   - `permutation_unavailable` is decided before any permutation (A107).

   **With suspicion:** the label parsing in `effects.py` (A126).
8. **Views and the page, skim:** `views.py` (346), `views_summary.py` (174), `views_explain.py`
   (231), `report.py` (163), `reporting/model_charts.py` (239). **Right:** `VIEWS` declares per
   task what is not available (regression has no `curves`, `score_distribution` or
   `thresholds`), and `check_skip_views` runs first.
9. **`evaluation/card.py`** (358) **with `reporting/card.py`** (86). **Right:** facts only, no
   sentence written; pieces of other runs, models or configs refused; considerations as codes.
10. **`evaluation/compare.py`** (484). **Right:** differences on test only, refused elsewhere; a
    run against itself differs by zero; the refusals come before the cells.
11. **`evaluation/drift_reference.py`** (124). **Right:** it reads the `stage2/` copy's counts
    and the test cells at replicate 0, and its output is a valid input of `psi`.

**On a first pass, skip** items 8 to 11 and `scores.py`: nothing reads the drift reference until
Monitoring exists, and the page is the evidence for the views.

**Two tests to read:**
- `tests/test_modelling_acceptance.py`, lines 213–255: the model's validation AUC is above the
  single-feature baseline's and never above the oracle's on the same rows by more than two
  standard errors. With a leak kept, it does exceed the oracle, so the bound can fail.
- `tests/test_metrics.py::test_the_average_precision_holds_at_a_rare_rate`: at a 0.1% rate on a
  million rows, the cells' average precision and calibration line are within 0.002 of the rows'.
  The old grid read the average precision 43% low here.

## 5. Reviewing steps 2 and 3 in one sitting
1. **Both veto lists first:** guide 2 §2 (A82 to A91), then §1 here. Step 3 read step 2's
   outputs as they are, so a veto in one can reach the other.
2. **The notebooks back to back on one run:** guide 2 §1 item 1 (notebook 04's nine guide cells,
   then notebook 03's walk-through), then §4 item 1 here (notebook 05 on the run 04 just wrote).
   Record the sign-off in 05's step 12.
3. **Levels 1 and 2** of `training.md`, then of `evaluation.md`.
4. **Training's code** in guide 2's order (its §1 item 3), reading step 3's additions in place
   (§2 here). Guide 3 takes over at Evaluation's code (§4 items 2 to 11).
5. **Judge these contracts once, for both steps:**
   - the run folder `06_models/rNNN/`: `bundle/`, `stage2/` with `_stage2.json` (written by
     Training, read only through `read_stage2_copy`), `training/`, `ledger_run.parquet`, and now
     `evaluation/`. An Evaluation rerun replaces `evaluation/` only;
   - `training.json`: the keys and tables Evaluation and the card read (§2), and the warnings as
     sentences (A108). Under `negative_downsampling`, `oof`'s target is at the sampled rate,
     which is why `train_level` reads `sampling.true_rate` instead;
   - the sign-off: Training's table and view (A83), shown again in report view 12 and notebook
     05's step 12, and recorded with `sign_off` or `decide --sign-off`;
   - `search_table`: one function for notebook 04 and report view 13.
6. **The four tests:** guide 2's two, then the two here.

**Still open from guide 2. This guide closes none of them:**
- the defaults A82 to A91;
- the floor's optimism on a non-monotone feature (A88);
- whether the budgets of 60 and 200 trials converge (the canonical run used 15).

## 6. Open risks, and what is unverified
- **Inside the bank:**
  - Spark scoring through `mapInPandas` on the executors, with the model libraries importing and
    scoring there (spike 5's trip; the chunked driver path is the fallback);
  - two quantile passes per binary scorer (the model and each ranking baseline);
  - the cells collected to the driver: about 6,900 per replicate at 1 million rows over 12
    periods, for 201 replicates; the bootstrap's seconds per replicate at that size are not
    measured;
  - `frames.rows` is computed about six times per run;
  - plotly's 5.9 MB page in the bank's browser and JupyterLab.
- **Rerun determinism** of the binned rank metrics (`approxQuantile` on re-read parquet), which
  the ML audit left unconfirmed: confirmed on `dev` (§3: one run evaluated twice, all 20
  tables identical). It is not confirmed on a cluster, where partitions differ from run to run.
- **The scores table** has no model key and no version of its own. That is fine inside
  `evaluation/`, but Inference's shared scores table is another table and needs both (D-007
  (shared outputs stay readable across versions)).
- **The view names became config contract** through `skip_views`: renaming one needs an alias
  or a migration (A129).
- **One run can be evaluated on several validation periods.** This is disclosed by
  `earlier_validations` and the summary, but not enforced.
- **The drift reference's scores are test clients only.** Production also scores train clients,
  so an overfitted model starts Monitoring with a score PSI above zero.
- **Average precision below a 0.05% rate** is not measured.
- **Verified right by the ML audit:** the Poisson weights; AUC from cells within 2e-4; observed
  to expected, RMSE, R² and the deviances equal to scikit-learn; the prior-shift offset under
  sampling (observed to expected 0.999 and 1.008 with it, 0.287 and 0.083 without); the rows;
  `v ≥ tk + w` at config load; train-only fits; label-free score edges; `compare_runs` test-only.
