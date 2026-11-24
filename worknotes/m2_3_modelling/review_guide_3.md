# Stage 3 major step 3 (Evaluation): review guide
_For the EDS · reworked 2026-11-23 to the state after the audit's fixes · read together with
guide 2 ([`review_guide.md`](review_guide.md)) · the plan: [`plan.md`](plan.md) · the audit:
[`audit_steps_2_3.md`](audit_steps_2_3.md), your answers in [`audit_answers.md`](audit_answers.md)
· this file holds the current review only_

**In short.** Evaluation is built and the audit of 2026-11-22 is applied to it.
`run_evaluation` judges one trained run on its test clients and the validation period, outside
the engine and against the declared baselines, and writes `evaluation/` into the run folder:
the scores, the metric tables with client-bootstrap intervals, the explanation tables, the
drift reference, the report and the model card. `compare_runs` sets two evaluated runs side by
side. What this round changed in Evaluation:
- **Narrow slices no longer read low.** Regression's score grid is as dense at the top as
  binary's needs to be, and a slice narrower than twelve score bins is not shown.
- **Permutation importance runs on its own sample** of up to 50,000 test rows, and says "not
  available" where it has too few events.
- **Test rows with a null target are scored** for the drift reference only, so Monitoring will
  compare like with like; no metric reads them.
- **Regression's train-to-test gap is read on the same score cells** for both, from a score
  Training now stores.
- **The run folder is opened through one contract check** before any Spark work (guide 2,
  A142), and the report shows Training's warnings.

No review found a leak or a split or time violation. The package is 0.5.0 and nothing is
committed. What was run is in guide 2's status table; the checks of this step are in §4.

## 1. Decide first: the defaults this round took without asking
Numbered on from guide 2's (A136 to A150), most consequential first. The first build's
defaults, A92 to A135, follow in §2 with what this round changed in them.

**These change what a number means, or what is shown**
- **A151 A slice is read from the cells only when it spans twelve of the finest score bins:**
  0.012% of the rows on binary's pooled grid, 0.048% on binary's strata grid and for
  regression. A narrower one reads "not available" with that share. The audit's item 1 was
  first built with the guard at one bin; the ML audit called that unproven, since at one bin
  the binning's error is as large as the slice's sampling error and no interval shows it.
  Twelve is where the measured error of regression capture is under half the sampling error
  (the table in `evaluation.md` → Score cells). Binary near its guard is not measured.
  *Alternative:* the guard at one bin, with a mark on slices below twelve.
- **A152 Regression's grid has 100 score bins with a tail pass** (item 2): 25 each of 3.6%,
  0.36%, 0.036% and 0.004% of the rows. Cells per replicate grow from 830 to 1,000 to about
  1,050 to 1,600 on a million rows.
- **A153 The test part keeps its rows with a null target** (item 13). They are scored, stored
  in the scores table and counted in the drift reference's score side; every metric, slice,
  baseline, interval and sample filters them out, and the cells refuse them. Validation drops
  them, as Training does. The drift reference is version 2 and has a sidecar
  (`evaluation/_drift_reference.json`) with its version and `model_hash`; register taking a
  snapshot of it is M2.4.
- **A154 Permutation importance has its own sample** (Q681): up to 50,000 hashed test rows, of
  which the first 5,000 are the explanation sample. It reads "not available" below
  `strata.min_events` events in the sample, with the count. The minimum applies to regression
  too, where an event is a row with a non-zero target; for a target without zeros it never
  binds. Its standard deviation covers the five permutations, not the sample.
- **A155 Regression's train-to-test gap is read on cells for both** (item 5; replaces A105,
  where train's was on rows and read up to about 0.01 higher). Training stores the final
  model's score on its own rows (`score_in_sample` in `oof`), and Evaluation bins it on test's
  edges. In-sample scores above test's top edge tie in the last bin, so the gap reads slightly
  small. Binary's train concordance stays on rows, where the cells agree to 2e-4. I read your
  answer to item 5 this way; say so if you meant otherwise.
- **A156 A rerun gives the same tables to the binning's tolerance,** not bit for bit (item 83):
  the score edges come from an approximate quantile that moves inside its rank error with the
  partition layout. The headline metrics agree to four digits.

**Report, card, warnings**
- **A157 The model card is version 2.** `rows_per_period` holds per-period rows only, with
  `rows_pooled` and `rows_validation_test_clients` beside it; `framework_versions.card` is the
  version that wrote the card; the records the card copies from Training have explicit key
  lists, so a Training column cannot enter the card unannounced. An integer prints bare on the
  card page (a seed is no quantity).
- **A158 What the summary now says.** The validation headline pools the clients of both splits
  and only the view "Validation on test clients only" shows the test clients alone (item 74).
  Training's warnings appear under "From Training"; they still do not reach the card's
  considerations (A108). A new warning, `newer_runs_passed_over`, names the newer runs
  Evaluation did not take and why.
- **A159 The views read the run's own objective** (`choices.objective` in the meta), not the
  evaluating config's: a named run may have been trained under another config.
- **A160 Charts.** Hovers show four significant digits (123,456 reads 123,500), labels go
  through `plain_number`, every y axis is titled, the importance bar uses the part colours, and
  a waterfall step keeps its size. Inside the bank: one beeswarm hover on a large and a tiny
  value.
- **A161 A feature that is all null in the sample** gets one "not available" line for its
  partial dependence (Q680).

**Layout and smaller ones**
- **A162 Where things live now.** `evaluation/slices.py` (the slices and the guard),
  `evaluation/permutation.py`, `evaluation/meta.py` (the assembly of `evaluation.json`);
  `evaluation/report.py` has one `VIEWS` table; `reporting/card.py` owns the card's version and
  sections. `explain.py` (354 lines) and `compare.py` (480) are kept whole as tied functions:
  the code review named a possible cut of each, and where to cut is your call.
- **A163 Per-task choices are in `TASK_SPECS`** (item 51): the score grid, the strata step, the
  tail's start, the objective's loss, the views' per-task sentences and columns. Two dicts that
  hold only chart and line functions stay beside them (`CALIBRATION_CHARTS`,
  `CALIBRATION_LINES`), since `tasks.py` must not import the reporting side.
- **A164 Notebooks may show a package-built line of run facts as HTML output** (Q686); guide
  text stays in markdown cells, and notebook 05's optional `shap` cell stays.

## 2. The first build's defaults, A92 to A135
As built on 2026-11-17 and still open to veto. Unchanged unless a line says otherwise.

**Changed by this round**
- **A93, A103 (the score bins).** Binary as before: 380 bins, dense at the top. Regression now
  100 bins with a tail pass (A152). The strata take every fourth binary edge and every
  regression edge.
- **A99.** `read_stage2_copy` lives in `run_artifacts.py`; it checks the copy's own version.
- **A101.** The staged scores folder is `evaluation.scores-<token>`, a random token instead of
  the process id.
- **A105.** Replaced by A155.
- **A107.** Permutation importance: its own sample and one more "not available" case (A154).
- **A110, A111.** Every refusal still comes before Spark, now through the run folder's contract
  (guide 2, A142). `evaluation.json` gains `training_warnings`, `in_sample_concordance_cells`,
  `choices.objective`, `choices.permutation_rows`, `timings.seconds` (open, scoring, tables,
  explanation, views, card) and `unavailable.partial_dependence`; it is schema version 2.
- **A121.** `train_level` takes the opened run folder.
- **A130.** The card is version 2 (A157); `CARD_SCHEMA_VERSION` is owned by `reporting/card.py`.
- **A131.** The drift reference is version 2, has a sidecar and counts every scored test row
  (A153).
- **A135.** Module sizes now: `compare.py` 480, `cells.py` 440, `statistics/metrics.py` 428,
  `run.py` 410, `baselines.py` 383, `explain.py` 354, `evaluation/card.py` 352, `tables.py`
  329, `views.py` 327.

**Unchanged**
- **A92** The stored `cells` table keeps replicate 0 only.
- **A94** Bootstrap weights from `xxhash64(client, r, "client_bootstrap")` through the inverse
  Poisson CDF; a weight-0 row counts nowhere in that replicate.
- **A95** `bootstrap_intervals(…, replicates)`; a metric undefined in any replicate has no
  interval.
- **A96** The meta key `eligible_rows` counts null-target rows on purpose: a `top_n` list is
  cut before any target is known.
- **A97** A carried column that is no candidate is refused; carried source columns are dropped
  once read.
- **A98** `metric_tables` also returns `pooling`; `feature_table` takes train's null share from
  the per-run ledger.
- **A100** As planned (`run=` and `--run`).
- **A102** `mean_score` and `mean_target` on every `metrics` row; the distribution chart draws
  the ratio to chance.
- **A104** The single-feature baseline is chosen on the train rows where the feature is known;
  its nulls score lowest; the warning `single_feature_baseline_has_nulls`. *Alternative:* rank
  the candidates with the null as the lowest value.
- **A106** `events` under `strata.min_events` are positive rows; a conversion can count in up
  to `w` periods.
- **A108** Training's warnings stay free text.
- **A109** `find_run` matches the data-definition hash, the Training settings digest and the
  sources digest.
- **A112** A config that names one baseline form twice is refused at load.
- **A113** `evaluation/tables/` stores Training's `signoff`, `trials` and `explanation_sample`
  again, so `evaluation/` renders alone.
- **A114** Prediction threads: `score_spark` predicts on `spark.task.cpus`.
- **A115** The score edges are cut over test and validation together. *Alternative:* cut on
  test alone.
- **A116** Stratum levels are capped on the scored rows; a regression stratum has no
  concordance.
- **A117** The row loss is `decision.metric` when it is a row loss, else the run's objective's.
- **A118** `log_loss` is itself a metric; a `mean` row sits beside `pooled`.
- **A119** The fixed capture depths 1, 2, 5, 10, 20, 30 and 50% are added to the configured
  slices.
- **A120** `decision_slice` sets the strata's list composition and the explanation cut; with no
  usable slice the cut falls back to `top 10%` with a warning.
- **A122** `population_base_rate` and a historic rate number are compared on mean prediction; a
  column baseline with nulls, or outside [0, 1], fills the order metrics only.
- **A123** The single feature is the per-run ledger's highest `train_concordance` among the
  numerics and the ordered categoricals.
- **A124** EDA's key features are the `stage2/` ledger's rows with a `key_feature` value.
  Unverified: whether a person's `include` reaches that column.
- **A125** The effect features are ranked by Training's out-of-fold contribution share.
- **A126** `effects.py` finds a numeric's EDA group by parsing the group label's opening bound.
  *Alternative:* EDA stores `bin_order_first` and the lift's interval.
- **A127, A128** The report's views and cell formats as built.
- **A129** `skip_views` takes `report.py::VIEWS` names, so the view names are config contract.
- **A132** `compare_runs`: differences on test only, a run against itself differs by zero, the
  refusals before the cells.
- **A133** Notebook 05 has no helper module; step 11 compares the run with itself as shipped.
- **A134** The acceptance tests' bounds and budgets.

## 3. What this round changed in step 2's contract, as Evaluation reads it
- `training.json` (schema version 2): Evaluation, the card and `compare_runs` read the keys and
  nested keys listed in `run_artifacts.py` (`TRAINING_PATHS`, `SAMPLED_PATH`, `SEARCH_KEYS`),
  and Training's tables with the columns in `TRAINING_TABLE_COLUMNS`. A missing one is refused
  when the run is opened, naming the file.
- New in what Training writes for Evaluation: `score_in_sample` in `oof`, `warnings`,
  `judged_model`, `threads`, `library_versions`; the calibration table's `oof_loss`.
- The `stage2/` copy: its own version and frozen columns (guide 2, A143).
- `list_runs(cfg, entity, env)`, `show_run(cfg, entity, env, run)` and `find_run`'s second
  return value (guide 2, A145).

## 4. What was run
| Check | Result |
|---|---|
| Spark batch after the fix round: every Training, Evaluation, card, compare and acceptance test | 678 passed, 3 failed (one new Training test, guide 2 A140; rerun passed) |
| Full suite with the slow tests | 1343 passed, none failed, 32 min 36 s (`-m "slow or not slow"`). After it, two small edits (a docstring wrap in `training/search.py`, the per-stage wording of the missing-`run`-entry message in `config/audit_log.py`); their test files rerun: 105 passed |
| Canonical data, Evaluation of the run trained in guide 2 | 125 s by its laps (scoring 11, tables 69, explanation 45); test AUC 0.805 (0.791 to 0.816), validation 0.800, validation on test clients 0.790; observed to expected 0.97 and 1.00; no warning; numbers in guide 2 §6 |
| Notebook `05_evaluation` as a scratch copy | 17 of 17 code cells, no error, on the run notebook 04 had just written (`dev` preset) |
| The run folder's contract on the run the suite writes (`tests/test_run_contract.py`; the stored golden folder was dropped on 2026-11-24 until 1.0) | 19 tests (the contract, 18 damaged copies refused by name) |

**The reviews of this round.** Two code reviews, the silent-failure audit and the
compatibility check on Opus, the ML audit on Fable; none had a blocking finding. On
Evaluation's side:
- **ML audit:** sound on the null-target rows (no path to a metric, a baseline, an interval, a
  sample or the score edges), on permutation importance (label-free hash, test rows, cluster
  members moved together), on `score_in_sample` (read by views and the meta only) and on the
  interval logic. The slice guard's place was unproven: moved (A151).
- **Compatibility:** the Evaluation stage format had changed under version 1: now 2; the drift
  reference 2; the card's copied records got explicit key lists.
- **Silent failures:** a null score in the drift counts is refused; `effect_table` takes a
  feature's kind from the ledger and fails loud on a numeric without edges; the runs `find_run`
  passed over are stored as a warning, not only printed.
- **Code review:** the scale note read the evaluating config's objective (A159); two card
  assertions could not fail; the assembly of `evaluation.json` moved out of the orchestrator.

**Measured.** Binned minus row values for binary, on 1 to 2 million simulated rows (the first
build's table, unchanged): average precision within 0.0015 from a 0.05% to a 5% rate, the
calibration slope within 0.0003; the calibration intercept up to about 0.0025 on a
miscalibrated score at a 0.05% rate. Regression capture against the row list: the tolerance
table in `evaluation.md` → Score cells (0.03 to 0.045 relative at a 0.05% slice, where the row
list's own bootstrap error is 0.1).

## 5. What to read, in this order, and what "right" looks like
1. **Notebook `05_evaluation.ipynb`, run right after `04_training`** (35 cells, 17 of them
   code). Read its guide cells as code, then `report.html` section by section. **Right:** a
   person who ran 04 can evaluate, read every view, compare and sign off without opening a doc.
   New in this round: the summary's sentence on the validation headline and its warnings, the
   `note` on a narrow slice, the permutation sample, the sampled rows behind the importance
   views.
2. **`evaluation/run.py`** (410; `scores.py` 106 and `meta.py` 147 with it). **Right:** it only
   orchestrates; `_open_run` holds every refusal before Spark; every metric input goes through
   `KNOWN_TARGET`; it scores once, writes first and reads the scores back. **With suspicion:**
   any read of test or validation that feeds a choice.
3. **The cells and the client bootstrap:** `statistics/score_cells.py` (103),
   `evaluation/cells.py` (440), `statistics/bootstrap.py` (102). **Right:** every sum is per
   row in Spark; the score edges use no label and no null-target row; a client's rows share one
   weight per replicate. **With suspicion:** `quantile_passes` and the tail pass,
   `reference_score_counts`.
4. **`statistics/metrics.py`** (428) **and `evaluation/slices.py`** (211). **Right:** each
   metric is a function of one replicate's cells; a NaN is decided from the cells, never by
   catching; a slice below `MIN_SLICE_BINS` is refused with its share. **With suspicion:**
   `slice_metrics`, with the cut bin split in proportion.
5. **`evaluation/tables.py`** (329) and **`evaluation/baselines.py`** (383). **Right:** nothing
   is chosen on test or validation; `compare_baselines` writes no "passed".
6. **`evaluation/explain.py`** (354) **with `permutation.py`** (142) **and `effects.py`**
   (201). **Right:** one collect gives both samples in hash order; the statistics read the
   sampled rows only; "not available" is decided before any permutation. **With suspicion:**
   the label parsing in `effects.py` (A126).
7. **Views and the page, skim:** `views.py` (327), `views_summary.py` (184),
   `views_explain.py` (237), `report.py` (144), `reporting/model_charts.py` (243).
8. **`evaluation/card.py`** (352) **with `reporting/card.py`** (97); **`compare.py`** (480);
   **`drift_reference.py`** (141).

**On a first pass, skip** items 7 and 8: the page is the evidence for the views, and nothing
reads the drift reference until Monitoring exists.

**Two tests to read:**
- `tests/test_modelling_acceptance.py`, the oracle bound: the model's validation AUC is above
  the single-feature baseline's and never above the oracle's by more than two standard errors;
  with a leak kept it does exceed it.
- `tests/test_evaluation_tables.py::test_spark_null_target_rows_change_no_cell_and_count_in_the_reference`.

## 6. Reviewing steps 2 and 3 in one sitting
1. **Both "decide first" lists:** guide 2 §1 (A136 to A150), then §1 here, then the two older
   lists (guide 2 §3, §2 here).
2. **The questions:** guide 2 §2 (Q687 to Q693).
3. **The notebooks back to back on one run:** 04, then 05 on the run 04 just wrote; record the
   sign-off in 05's step 12.
4. **Levels 1 and 2** of `training.md`, then of `evaluation.md`; `model_bundle.md` → "The run
   folder's contract".
5. **The code** in guide 2's order, then §5 here.
6. **Judge these contracts once, for both steps:** the run folder and its contract check;
   `training.json`'s keys and tables; the sign-off table and view; the scores table, which now
   holds null-target test rows.

## 7. Open risks, and what is unverified
- **Inside the bank:** Spark scoring through `mapInPandas` on the executors; two quantile
  passes per scorer for both tasks now; the cells collected to the driver (more for regression
  than before); `frames.rows` computed several times per run; the page's size in JupyterLab.
- **The scores table's write assumes a local filesystem** (the audit's item 32): with M2.4's
  transport.
- **Rerun determinism** is to the binning's tolerance by design (A156); not checked on a
  cluster, where partitions differ from run to run.
- **Binary capture near its guard** (0.012%) and **average precision below a 0.05% rate** are
  not measured.
- **The view names are config contract** through `skip_views` (A129).
- **One run can be evaluated on several validation periods:** disclosed by
  `earlier_validations`, not enforced.
- **The drift reference's scores are test clients only,** null targets now included; an
  overfitted model still starts Monitoring with a score PSI above zero against train clients.
