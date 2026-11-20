# Handover: m2-3-evaluation
_Checkpoint written: 2026-11-17 (wave 1 running) · branch: main · last commit: 3ea567b (step 2 is committed, `c02c423`)_

## Goal
Build Stage 3 (M2.3 Modelling) major step 3, Evaluation, from
`worknotes/m2_3_modelling/plan.md` → "Major step 3: Evaluation" (m3.1 to m3.11). The EDS's
word (2026-11-17): build it with the plan, this handover and all requirements; keep Fable's
relative usage contained; update all guides, knowing the EDS reviews steps 2 and 3 together
when there is time. The step ends in the ML audit of the whole chain, `compat-guardian`, one
fix round, the Spark batch, the full suite with the acceptance and slow tests, review guide 3,
the docs, version 0.4.0, and a stop for the EDS. Commit only on the EDS's word.

## What the EDS decided (2026-11-17)
- Steps 2 and 3 are reviewed together; step 3 builds on step 2's contracts as built. A contract
  the joint review changes is fixed in both.
- Step 2's review stays open: review guide 2 (`worknotes/m2_3_modelling/review_guide.md`), the
  defaults A82 to A91, the floor's optimism on a non-monotone feature (A88), the budgets of 60
  and 200 (`docs/components/training.md` → Open questions). Close none of them.
- Q667 to Q673 are answered at their defaults (`worknotes/m2_3_modelling/answers.md`).

## This chat (Fable main thread, kept small)
- Fable orchestrates only: briefs by reference, Spark batches, the checkpoint, the final
  report. Every code or test piece is a `builder`, every doc piece a `doc-writer`, fixes go
  back to the builder that wrote the code (`SendMessage`; find the agents with `ListAgents`).
  The one Fable subagent is the ML audit of the whole chain at the close.
- **Settled at the start** (the "to settle" list): `plan.md` → "Settled at the start of step
  3", A92 to A102 (the score cells' long shape and names, the bins, `client_weights` as an
  array column, `bootstrap_intervals` returning every metric's interval, the slices on cells,
  the frames' `carry` and `meta["population"]`, the signatures of `metric_tables`,
  `encoding_shares`, `feature_table`, `read_stage2`, the run parameter, the scores written
  first, the chart tables' columns, the pandas mirror `statistics/score_cells.py`, m3.3 split
  in two). All are defaults for veto and go first in review guide 3.
- `src/core_modelling/evaluation/__init__.py` exists with a docstring only (m3.4 fills it).

## The waves (Spark runs only at the sync points, when no agent runs pytest)
1. **Wave 1, running:** m3.1 metrics and bootstrap (Opus, xhigh); m3.2 model charts (Sonnet,
   high); m3.3a scoring, cells, frames plumbing, `read_stage2`, prediction threads (Opus,
   xhigh); m3.6 explanation tables (Opus, high).
2. **Sync A:** the Spark tests wave 1 wrote (the builders' reports name the commands), as one
   background command, beside one combined `code-reviewer` (Opus, high) on wave 1's files.
   Failures and findings go back to their builders.
3. **Wave 2:** m3.3b `baselines.py`, `tables.py`, `drift_reference.py` (Opus, xhigh; appends
   to `tests/test_evaluation_tables.py`).
4. **Sync B:** its Spark tests, the review.
5. **Wave 3:** m3.4 as two builders, `evaluation/report.py` (Opus, high) and
   `evaluation/run.py` with `__init__.py`, `STAGES`, `run --run` (A100), the fixtures
   `evaluated_card` and `evaluated_regression`, `test_run.py`, `test_evaluation.py` (Opus,
   xhigh; it wires m3.6's tables and leaves one call each for the card and the explanation
   views); beside them m3.9 `compare_runs` (Opus, xhigh).
6. **Sync C:** Spark (`test_evaluation`, `test_run`, `test_compare`), the review; the
   orchestrator reads `evaluation/run.py`'s diff in full.
7. **Wave 4:** m3.5 acceptance tests (Opus, high); m3.7 explanation views (Opus, high; it
   touches `views_explain.py`, `report.py`'s `VIEWS`, `explain_charts.py` only); m3.8 the
   model card (Opus, high; `reporting/card.py` and one call in `evaluation/run.py`).
8. **Sync D:** Spark, the acceptance tests on `dev`, the review.
9. **Wave 5:** m3.10 notebook 05 and the helper's Evaluation section (Opus, high); the main
   thread runs the notebook on `dev`.
10. **The close (m3.11):** the ML audit of the whole chain (Fable, xhigh) and `compat-guardian`
    (Opus, high) at once; one fix round through the builders; the full suite with the
    acceptance and slow tests; the cells' seconds per replicate at the bank's size; version
    0.4.0; docs by `doc-writer`s (`evaluation.md` "built" with A92 to A102 carried in,
    `reporting.md`, `monitoring.md`, `model_bundle.md`, `dataset.md`, `config.md`,
    `architecture.md` Public API and inventory, `docs/README.md`, `glossary.md`,
    `UPDATES.md`, `roadmap.md`, `docs/guides/modelling_faq.md` with the research note of
    `questions.md`, the notebooks' README); review guide 3 (it opens with A92 to A102 and
    says how to read steps 2 and 3 together); `worknotes/log.md`; `/efficiency`; the final
    report.

## State after the first reports (2026-11-17, second checkpoint)
- **m3.1, m3.2, m3.6 are built** (their no-Spark tests pass by the builders' own runs: 17, 21
  and 8) and reviewed once (one combined `code-reviewer`: the statistics check out against
  scikit-learn in the reviewer's own runs; one blocking finding and seven small ones). The
  fixes are with the three builders now. m3.6's two Spark tests are not run yet
  (`pytest tests/test_explain.py -q -k spark`).
- **A93 changed shape** (the orchestrator, after m3.1's measurement: uniform bins put average
  precision 0.0086 low at a 2.8% rate): the bin counts stay, half of the bins cut the top tenth
  of the rows (`statistics/score_cells.py::bin_quantiles(bins)`). Measured at 200,000 rows,
  uniform to dense: AP bias −0.0057 to −0.0013 at 6%, −0.0086 to −0.0025 at 2.8%, −0.0078 to
  −0.0028 at 1%; AUC within 1e-4 on both; regression's capture error about ten times smaller,
  its concordance unchanged. Rarer rates than 1% are not measured: an open point for the guide.
- **Consequence, the blocking finding:** the score distribution drew a class's share per bin,
  which steps at the 90th percentile under unequal bins. `distribution_table` now gives
  `score_bin, score, percentile, class, rows, share, ratio` and the chart draws `ratio` (the
  class's share over the bin's share of all rows, 1 is chance) against `percentile`.
- **Accepted as built, to carry into the docs and review guide 3:**
  - `cells_from_rows(rows, by, loss)` (`loss`: `log_loss`, `tweedie_deviance`,
    `poisson_deviance` or None); weight-0 rows count nowhere in a replicate.
  - `binary_metrics(cells, base, probability=True)`, `regression_metrics(cells, base)`;
    the metric keys are the decision-metric names (`roc_auc`, `ap`, `log_loss`, `rmse`, `mae`,
    `r2`, `deviance`); `TASK_SPECS` entries `cell_metrics`, `roc_curve`, `target_class`.
  - `bootstrap_intervals(replicate_cells, metric, level, replicates)`; a metric undefined in
    any replicate has no interval.
  - Average precision is the area under the binned precision–recall curve; the calibration
    slope is a damped Newton fit in numpy (tested against scikit-learn).
  - `slice_metrics(cells, slices: Slices, population)` returns `slice, rows, target,
    part_rows, part_target, unavailable`; `slice_rates(counts)` derives capture, rate, lift.
  - `feature_table(contributions, shares, run_ledger)` takes no `stage2` (A98 is wrong there:
    train's null share is the per-run ledger's, the frame the model was fitted on);
    `collect_explanation_sample(rows, scores, cfg, env, cut)` returns the sample and the
    collect's log entry; `cut` is the score at the decision's slice.
  - The charts' optional arguments (`axis_format` on `reliability_chart`; `from_zero`,
    `y_format`, `reference` on `metric_lines`, which takes one metric); the reliability chart
    does not grey low-support groups.
- **For m3.4's brief:** what `run_evaluation` passes to the explanation functions is in
  m3.6's report (rows, the written scores read back, `cut`, the bundle, the contributions as
  the permutation sample, the `stage2` ledger's `feature, cluster`, `partial(metric_loss,
  cfg.decision.metric)`, `cfg.training.seed`, the per-run ledger); the source of EDA's key
  features for `effect_features` is not found yet. Two tests the reviewer marks as worth the
  EDS reading: `test_metrics.py::test_binary_metrics_match_scikit_learn_on_the_rows`,
  `test_explain.py::test_a_cluster_is_permuted_as_one_and_an_ignored_one_has_no_importance`.

## State at the first Spark batch (third checkpoint)
- **All of wave 1 and m3.3b are built**; the review fixes of m3.1, m3.2 and m3.6 are in
  (no-Spark tests by the builders' own runs: 18, 22, 8; m3.3a 14 and `test_artifacts` 24;
  m3.3b 8). **No Spark test had run before this batch.**
- **m3.3a as built** (`evaluation/scores.py`, 415 lines; a split into scoring and cells is a
  candidate cut for the EDS): `score_parts(bundle_folder, rows, cfg)`, `write_scores(scores,
  folder)`, `client_weights(client, replicates, salt)` (one `xxhash64` and a sum of 17
  comparisons per replicate), `scorer_loss(cfg)`, `score_edges(scores, cfg, column)` giving
  `{score, strata, target}`, `score_cells(scores, cfg, by, edges, *, loss, column)`,
  `stratum_labels`; `PARTS`, `BASELINE_PREFIX`, `WEIGHT_SALT`. Periods in the cells are string
  labels. Stratum levels are capped in Spark before the aggregate, counted on the scored rows.
  `build_frames(..., carry=)` and `meta["population"]` (null-target rows counted on purpose).
  `training/gate.py::read_stage2_copy(run_folder)` (the name `read_stage2` was taken).
  `write_stage(..., folders={"scores": staging})` in `artifacts.py` (additive; approved by the
  orchestrator; the three steps are in `write_scores`' docstring). The families'
  `predict(booster, X, threads=None)` and `score_frame(bundle, frame, threads=None)`;
  `score_spark` passes the task's cores. Measured: LightGBM 7.3 and XGBoost 5.9 cores by
  default; margins bit-identical at any thread count. `ROW_LOSSES` is not shared with Spark
  (numpy and scipy); the Spark-against-mirror test runs once per loss instead.
- **m3.3b as built:** `metric_tables(cells, cfg, base, population, *, loss)` returning
  `metrics`, `slices`, `curves`, `reliability`, `score_distribution`, `strata` (composition
  and support; the per-level metrics are in `metrics`), `pooling`; a part named
  `validation_test_clients`; `choose_single_feature(run_ledger, stage2_ledger, order)`,
  `carried_columns(cfg, run)`, `add_baselines(rows, cfg, run)`, `compare_baselines(metrics:
  dict, cfg, base)`; `build_drift_reference(run_folder, cells)` giving `features`, `edges`,
  `scores`. `metric_tables` takes 7.7 s at 200 replicates with three strata. The order
  `run_evaluation` calls things in is in m3.3b's report and goes into m3.4's brief: bundle;
  `run = {features, single_feature}`; `carried_columns` as `carry`; `add_baselines`;
  `score_parts`, `write_scores`; per scorer `score_edges` and `score_cells` (all, split, each
  stratum); `metric_tables` per scorer; `compare_baselines`; `build_drift_reference`.
- **Follow-ups owed to m3.3b after the review** (the orchestrator's decisions): the slices get
  intervals (at least the rows added over the periods); `RELIABILITY_GROUPS` and the ranking
  metric's name move into `TASK_SPECS`; an ordered categorical's level text comes from the
  encoder's own conversion; a null in a `previous_model` or historic column takes the lowest
  score for the ranking metrics, and its level metrics read "not available" with the null
  share, decided from one count up front.

## State after the second review (fourth checkpoint)
- **The first Spark batch passed: 282 passed, 4 deselected, 5 min** (the new evaluation tests
  with step 2's `test_training`, `test_scoring`, `test_families`, `test_bundle`,
  `test_artifacts`).
- **The review of m3.3a and m3.3b** (one blocking, ten small) is fixed by the two builders;
  their no-Spark tests pass by their own runs. What changed against the section above:
  - `evaluation/scores.py` is split: it keeps `BASELINE_PREFIX`, `SCORES_FOLDER`,
    `score_parts(bundle_folder, rows, cfg, baselines: list[str])`, `write_scores(scores,
    stage_folder) -> str` (refuses a stale `.scores-*` sibling, returns the staged path); the
    new `evaluation/cells.py` holds `client_weights` (one `F.transform` over
    `F.sequence(1, n)`), `scorer_loss`, `score_edges`, `score_cells`, `stratum_labels`,
    `WEIGHT_SALT`.
  - `statistics/score_cells.py` gains `PARTS`, `POOLED`, `pool_cells(cells, over)`: the caller
    asks Spark for the `split` cells only and derives `all` with `pool_cells(cells, "split")`.
  - A stratum's cells in regression carry the zero-bin edges only (target bins 0 negative,
    1 zero, 2 positive), so a level's `events` counts right and no level has a concordance
    (`TASK_SPECS[...]["strata_absent_metrics"]`). Automatic when `by` names a stratum.
  - The frames' meta key is `eligible_rows` (was `population`).
  - Baselines: `baseline_columns(cfg, run) -> {form: column}`, `describe_baseline_columns(rows,
    cfg) -> {form: {null_share, min, max}}` (one Spark aggregate, before `add_baselines`),
    `baseline_loss(form, cfg, facts) -> (loss | None, {metric: reason})`,
    `compare_baselines(metrics, cfg, base, facts)`; a null in a column baseline takes the
    lowest score and switches its level metrics off with the null share as the reason.
  - `build_drift_reference(run_folder, cells, features)` refuses a bundle feature without
    cells. The slices carry `capture_low/high`, `rate_low/high`, `lift_low/high`.
    `metric_tables` takes 11.1 s at 200 replicates with three strata.
  - `TASK_SPECS` gains `order_metrics`, `metric_keys`, `reliability_groups`,
    `prediction_range`, `strata_absent_metrics`. `Decision._check_baselines_named_once` at
    config load (a config naming one baseline form twice is now refused; `config.md` has the
    line; the round-trip test covers the two historic forms in two configs).
  - `xgb_family.predict` restores the booster's `nthread`.
- **The call order for `run_evaluation`** (m3.3b's report): `load_bundle`, build `run`;
  `build_frames(carry=carried_columns(cfg, run))`; `facts = describe_baseline_columns(rows,
  cfg)`; `add_baselines`; `score_parts(..., list(baseline_columns(cfg, run).values()))`;
  `write_scores`; per scorer `loss` (`scorer_loss(cfg)` for the model, `baseline_loss(...)[0]`
  for a baseline), `score_edges`, `score_cells` for `split` and each stratum, `pool_cells`;
  `metric_tables(..., loss=loss is not None)`; `compare_baselines(metrics, cfg, base, facts)`;
  `build_drift_reference(run_folder, model_all_cells, bundle.features)`; then the explanation
  tables as in m3.6's report; `write_stage(..., folders={"scores": staging})`.
- **For the fix round at the close:** `ZERO_BIN_EDGES` in `evaluation/cells.py` repeats the
  edges inside `tasks._regression_target_bins` (one shared constant).
- **For review guide 3 beyond A92 to A102:** `write_stage(folders=)` in `artifacts.py`; the
  families' `predict(..., threads=None)`; the scores/cells split; the stratum cap counted on
  the scored rows, not EDA's snapshot; `eligible_rows` counting null targets; the new config
  refusal; the dense-top grid with its measured table; AP below a 1% rate not measured; the
  score distribution drawn as the ratio to chance by percentile; a non-top_n decision uses
  the first configured slice for the list's composition; the reliability chart greys nothing.
  The tests worth reading: `test_metrics.py::test_binary_metrics_match_scikit_learn_on_the_rows`
  and `test_evaluation_tables.py::test_score_cells_equal_their_pandas_mirror_at_replicates_0_and_1`.

## The wave plan from here (changed: the report comes one wave after `run_evaluation`)
- **Wave 3:** m3.4-run (`evaluation/run.py`, `__init__.py`, `STAGES`, `run --run` (A100), the
  fixtures `evaluated_card` and `evaluated_regression`, `test_evaluation.py`, `test_run.py`;
  a minimal `evaluation/report.py` with `VIEWS` and `build_report` giving the summary only;
  Opus, xhigh) beside m3.9 `compare_runs` (Opus, xhigh). The tables of `evaluation/tables/`:
  `metrics`, `slices`, `curves`, `reliability`, `score_distribution`, `strata`, `pooling`,
  `baselines`, `contributions`, `features`, `permutation_importance`, `partial_dependence`,
  `cells`, the drift reference's three; the scores under `evaluation/scores/`.
- **Sync C:** Spark (`test_evaluation`, `test_run`, `test_compare`); the orchestrator reads
  `evaluation/run.py` in full; one evaluated run folder per task is left in the scratchpad
  (`runs/`), so the report builders render from stored tables without Spark; the review.
- **Wave 4:** m3.4-report (views 1 to 7, 12 to 14, 17; Opus, high); m3.7 explanation views
  (`views_explain.py` exporting its views by name, `pdp_ice_chart`; Opus, high); m3.8 the
  card (Opus, high); m3.5 the acceptance tests (Opus, high).
- **Sync D:** Spark, the acceptance tests on `dev`, the review. **Wave 5:** m3.10 the notebook.
  **The close:** as in "The waves" item 10.

## Running (fifth checkpoint: wave 3 launched)
- The Spark rerun after the review fixes: 224 passed, 1 failed, 3 min. The failure was a real
  bug in `baselines._single_feature_score` (Spark's `greatest`/`least` skip a null, so a null
  numeric took ±`CLIP`, the top score for a falling feature); fixed on the main thread with a
  `F.when(known.isNotNull(), …)`; the four baseline tests pass.
- **Wave 3, two builders (Opus, xhigh), no Spark by them:**
  - m3.4-run: `evaluation/run.py`, `evaluation/report.py` (minimal: `VIEWS` with the summary,
    `build_report(tables, meta, resolved)`), `evaluation/__init__.py`, `tests/test_evaluation.py`,
    its lines in `run.py`, `__main__.py`, `conftest.py` (`evaluated_card`,
    `evaluated_regression`, 20 replicates), `test_run.py`, `runs.py` (the summary's display).
    It may add one key to `training.json` for `base` and reports any audit-schema need.
  - m3.9: `evaluation/compare.py`, `tests/test_compare.py`; it may add one per-replicate
    function to `statistics/bootstrap.py`. The main thread adds `compare_runs` to
    `evaluation/__init__.py` afterwards.
- A `caffeinate` keeps the Mac awake for eight hours from the start (about 15:30).

## Sixth checkpoint: wave 3 is built and green, wave 4 is running
- **Wave 3 passed its Spark batch on the first run: 30 passed, 4.5 min** (`test_evaluation`,
  `test_run`, `test_compare`). `evaluation/__init__.py` exports `run_evaluation` and
  `compare_runs`. The orchestrator read `evaluation/run.py` in full: the call order is
  followed, the explanation cut comes from the test part, `evaluation/` is written in one
  `write_stage` call and the staged scores are removed on a failure.
- **Two evaluated run folders are kept for the builders** (no Spark needed to render):
  the scratchpad's `runs/r001` (binary card) and `runs/r002` (regression), copied from the
  test session's `trained_data0`.
- **What wave 3 settled** (for review guide 3):
  - The drift reference's tables are stored as `drift_features`, `drift_edges`,
    `drift_scores` (`features` is the feature table's name).
  - The explanation cut: the decision's slice on test, pooled (`top_n` gives `n`, else the
    first `top_pct`, else the first `top_n`); `top 10%` with a warning when none is available.
  - EDA's key features are the `stage2/` ledger's rows with a `key_feature` value.
  - `base` is `training.json`'s `sampling.true_rate` when Training sampled, else the mean
    target of `training/tables/oof.parquet`.
  - The audit entry uses the existing `Entry.validation_period`; no schema change.
  - Each baseline gets `all` cells only. `card_quick` and `regression_quick` set 20 replicates.
  - `compare_runs` returns `rows`, `metrics`, `differences` (test only), `validation`
    (`use` = "reported, never chosen on"), `features`, `importance`, `budgets`; only
    directional metrics get a difference; identical scores reuse run a's cells.
- **The fix round of wave 3 (owed, after the review reports):**
  - `run.py` (its builder): store replicate 0 only in `cells` (20 replicates on `unit` give
    53k rows; 200 would give a table no reader needs); `_decision_slice_label` repeats
    `tables._decision_slice` (one public function).
  - `compare.py` (its builder): `_train_base` repeats `run._train_level`, `_part_cells`
    repeats `tables._parts`, `DIRECTIONS` belongs in `tasks.TASK_SPECS`; the reuse of cells
    for identical scores is for the reviewer to judge.
  - **`evaluation/run.py` has one editor, its builder:** wave 4's builders report the wiring
    they need (the card's two texts, `check_skip_views` at the top, Training's and EDA's
    tables for views 8, 10, 12, 13, structured warnings for the card) and it goes to that
    builder in one message at sync D.
- **Running:** the combined `code-reviewer` on wave 3 (read-only); wave 4's four builders
  (Opus, high, no Spark): m3.4-report (`evaluation/report.py`, maybe `evaluation/views.py`,
  `tests/test_evaluation_report.py`), m3.7 (`evaluation/views_explain.py`, `pdp_ice_chart`,
  `tests/test_views_explain.py`), m3.8 (`reporting/card.py`, `tests/test_card.py`;
  `build_card(run_folder, tables, meta, resolved)`), m3.5
  (`tests/test_modelling_acceptance.py`, the `acceptance` marker, `dev_stage2`,
  `test_traps.py`, `tests/README.md`).
- **Next:** the review's findings and the items above to the two wave 3 builders (they run
  no Spark); when wave 4 reports, the wiring message; sync D's Spark batch (`test_evaluation`,
  `test_evaluation_report`, `test_card`, `test_compare`, `test_run`), then the acceptance
  tests on `dev` alone (close the four old `ipykernel` processes first is the EDS's call:
  say so, never kill them), one review of wave 4, then wave 5 (notebook 05) and the close.
- For "verify inside the bank": `frames.rows` is computed about six times in one Evaluation
  (the baseline facts, the scoring, the explanation sample up to three times, the encoding
  shares); time it on a full population before deciding whether to persist it.

## Seventh checkpoint: the wave 3 review is in, its fix round is running
- **The review: 3 blocking, 7 small; everything else checked right** (the call order, nothing
  chosen on validation, `base`, the write, the join and the shared weights, the runner).
- **Sent to the `run_evaluation` builder** (owns `run.py`, `scores.py`, `cells.py`'s
  `scorer_loss`, `tables.py`, `explain.py`, `metrics.py`'s slice label, `training/tables.py`):
  - `write_scores` removes its staged folder when the Spark write fails;
  - `scorer_loss(cfg, objective)` with **the run's** objective (a named run may have another
    objective than the current config);
  - `training/tables.py::train_level(run_folder)`; public `tables.decision_slice(cfg)`,
    `tables.part_cells(cells)`, `metrics.slice_labels(slices)`;
    `explain.explanation_cut(slices, curves, cfg)`, whose key `configured` becomes
    `available`; it falls back only when no slice is configured or the row says
    `unavailable`, and raises when a configured label has no row;
  - `cells` stores replicate 0 only; `assert earlier` in `test_evaluation`.
- **Sent to the `compare_runs` builder, part 1** (owns `compare.py`, `tasks.py`'s new entry,
  `bootstrap.py`'s new function): `TASK_SPECS[task]["metric_directions"]` with a test;
  `statistics/bootstrap.py::replicate_values`; the two-runs test asserts a real difference;
  one parquet read instead of `read_stage`; the verdict's limit stated.
- **Part 2 for the `compare_runs` builder (owed, after the other reports):** call
  `train_level`, `part_cells`, `scorer_loss(cfg, <each run's objective>)` (a loss metric is
  "not available" when the two runs' losses differ), drop `_headline_metrics`' copy, and make
  `tables.py`'s two places call `replicate_values`.
- **Sent to the report builder:** plain baseline text, a public way to render views already
  built (so a run builds them once), the cut's `available` key.
- **Then:** the Spark rerun of `test_evaluation`, `test_compare`, `test_metric_tables`,
  `test_evaluation_tables`, `test_explain`, `test_run` when no builder is running pytest.

## Eighth checkpoint: wave 4 is built (no Spark run yet), its review is running
- **All four wave 4 builders reported; their no-Spark tests and ruff pass by their own runs.**
  - m3.4-report: `evaluation/views.py` (the core views, `View`, `VIEWS_BY_TASK`,
    `TRAINING_SIGNOFF`, `TRAINING_TRIALS`), `evaluation/report.py` (`VIEWS`, `TITLES`,
    `check_skip_views(cfg)`, `report_views`, **`render_views(views, meta, resolved)`**,
    `build_report`), `tests/test_evaluation_report.py`. Pages: 5.9 MB binary, 5.6 MB
    regression (plotly.js is most of it).
  - m3.7: `evaluation/views_explain.py` (the six views; `TRAIN_SAMPLE`, `EDA_BINS`,
    `EDA_LEVELS`, `EDA_EDGES`), `pdp_ice_chart(table, y_format=None)`,
    `tests/test_views_explain.py`. Its riskiest piece: a sample row finds its EDA group by
    the group label's opening bound matched to the stored edges.
  - m3.8: `reporting/card.py` (`CARD_SCHEMA_VERSION = 1`, `build_card(run_folder, tables,
    meta, resolved)`, `render_card(card)`; its own page shell, since `render_report` always
    embeds plotly.js), `tests/test_card.py`. `model_key`, `parent_run`, `parent_metrics` are
    None until M2.4.
  - m3.5: `tests/test_modelling_acceptance.py` (three runs, 100 replicates, about 14 min
    alone, 9 beside `test_traps`), `dev_stage2` in `conftest.py`, the `acceptance` marker.
- **The wiring owed to the `run_evaluation` builder, in one message when its fix round
  reports** (it is the only editor of `evaluation/run.py`):
  - `check_skip_views(resolved)` before anything is scored;
  - the tables `training_signoff` (`trained["signoff"]`), `training_trials`
    (`trained["trials"]`), `training_explanation_sample` (`trained["explanation_sample"]`),
    and `eda_bins`, `eda_levels`, `eda_edges` (the `stage2/` copy's `bins`, `levels`,
    `edges`, filtered to the effect features), under the constants `views.py` and
    `views_explain.py` export; they are stored, so `evaluation/` renders alone (a default
    for review guide 3: copies of other stages' tables inside `evaluation/tables/`);
  - the meta's `trained_at` (`training["written_at"]`) and `training_seconds`
    (`training["timings"]["seconds"]`);
  - `_write`: `card = build_card(opened.folder, result.tables, result.meta, resolved)` and
    the texts `report.html` (`render_views(result.views, result.meta, resolved)`),
    `model_card.json` (`json.dumps(card, indent=2, allow_nan=False)`), `model_card.html`
    (`render_card(card)`);
  - `MEAN` moves from `evaluation/tables.py` to `statistics/score_cells.py` beside `POOLED`
    (else `reporting/card.py` → `evaluation.tables` → `evaluation/__init__` →
    `evaluation.run` → `reporting.card` is an import cycle); `card.py` imports it from there;
  - delete `test_evaluation.py::test_a_skipped_view_is_left_out_but_never_the_summary`
    (`test_evaluation_report.py` replaces it) and extend the test's table list.
- **Owed after that:** part 2 for the `compare_runs` builder (above); the wave 4 review's
  findings to their builders; then the Spark batch and the acceptance tests on `dev`.
- **For the close's fix round:** `render_report(plotly=False)` so `card.py` drops its own
  page shell; Training's `warnings` in `training.json` as codes with values, so the card's
  considerations carry them (they are sentences today; a step 2 artifact change).
- **Defaults for review guide 3 from wave 4:** `started_by` is in the card; test 1 of the
  acceptance tests is a plain `>`; test 4 asserts observed to expected on the test part
  only; the cells of the metric tables show "value (low to high)"; views 2 to 7 show test
  and validation, view 17 the validation period's test clients.
- **Running:** the `run_evaluation` builder's fix round; the combined `code-reviewer` on
  wave 4 (read-only).

## Ninth checkpoint: everything is wired and green; the wave 4 review's fix round is running
- **Spark batch after the wave 3 fixes and the wiring: 139 passed, 5 min** (`test_evaluation`,
  `test_card`, `test_evaluation_report`, `test_views_explain`, `test_compare`,
  `test_metric_tables`, `test_evaluation_tables`, `test_explain`, `test_run`,
  `test_artifacts`, `test_code_rules`). The acceptance tests have not run yet.
- **Done since the eighth checkpoint:** `scorer_loss(cfg, objective)` with the run's own
  objective (`baseline_loss` and `compare_baselines` take the objective too);
  `artifacts.read_stage_meta(folder, name)`; `compare_runs` gives a loss metric no
  difference when the two runs' losses differ (`reason` column); `_scope_rows` calls
  `bootstrap.replicate_values`; `MEAN` lives in `statistics/score_cells.py`; the report, the
  card and the six carried tables are wired in `run.py`; the main thread tightened two
  acceptance spots (the oracle's target has no null; the downsampled run uses 20 replicates).
- **The wave 4 review: 5 blocking, 12 small; sent out as follows (all no Spark):**
  - `run_evaluation` builder: `meta["warnings"]` as dicts `{code, values…, text}` (codes
    `single_feature_baseline_not_chosen`, `nulls_not_in_train` with `features`,
    `explanation_cut_not_at_decision_slice` with `slice`, `reason`); public
    `tables.pooled_metrics`, `tables.headline_names`, `tables.metric_key`; the curve-row
    helper of `explain.py` public.
  - card builder: NaN cells blank; the card refuses another `config_hash`; `build_card`
    moves to **`evaluation/card.py`**, `render_card` stays in `reporting/card.py`;
    `render_report(plotly=False)`; `started_by` leaves the card; considerations copy the
    structured warnings.
  - explanation-views builder: a numeric held by level is matched as a number; the group
    assignment moves to **`evaluation/effects.py`** (`effect_table`, stored as
    `tables["effects"]` in place of `eda_bins`, `eda_levels`, `eda_edges`); `bin_orders`
    moves to `statistics/distributions.py`.
  - report builder: the appendix (`render_views(views, meta, resolved, log)`), the
    how-to-read notes, the summary in **`evaluation/views_summary.py`**, the shared helpers.
- **Owed by the main thread when they report (a few lines in `evaluation/run.py`):** the
  import of `build_card` from `evaluation.card`; `tables["effects"] = effect_table(…)` in
  place of the three EDA copies (and `test_evaluation.py`'s table list); the `render_views`
  call with the log. Then: `compare.py` drops `_headline_metrics` for
  `tables.headline_names` / `metric_key` (its builder, one short message); the Spark batch
  again; **the acceptance tests on `dev` alone** (`pytest tests/test_modelling_acceptance.py
  tests/test_traps.py`, about 14 min); wave 5 (notebook 05); the close.
- **Deferred to the review (review guide 3):** EDA storing `bin_order_first` and the lift's
  interval in `bins` and `levels` (EDA schema 5 to 6), which would retire the label parsing
  in `effects.py`; Training's warnings as codes (the card under-reports them today).
- **Docs owed at the close beyond the plan's list:** reporting.md's requirement 5 names the
  ICE lines (50 sampled clients) as a row-level exception; `build_card`'s new signature and
  home; `pdp_ice_chart`; the `effects` table; `read_stage_meta`; the new `TASK_SPECS` keys
  (`metric_directions`, `undirected_metrics`).

## Tenth checkpoint: the wave 4 fixes are in and wired; the closing reviews and wave 5 run
- **All four wave 4 fix rounds reported and the main thread did the last wiring** in
  `evaluation/run.py` (it imports and lints; the Spark batch over it is running, output in
  the scratchpad's `spark_e.txt`):
  - `build_card` comes from `evaluation/card.py`, `render_card` from `reporting/card.py`
    (`render_report(..., plotly=False)`; `started_by` is out; a rebuild under another
    `config_hash` is refused; a run evaluated before the structured warnings is refused with
    "evaluate it again");
  - `tables["effects"] = effect_table(contributions, stage2 bins, levels, edges, effects)`
    (`evaluation/effects.py`) replaces `eda_bins`, `eda_levels`, `eda_edges`;
    `_carried_tables` is gone (`tables |= opened.trained`);
  - `render_views(result.views, result.meta, resolved, result.log, show_decisions(cfg,
    entity, env))`: the report has its appendix; `build_report` takes the same two more
    arguments;
  - `meta["warnings"]` is a list of `{code, values…, text}`; `tables.pooled_metrics`,
    `headline_names`, `metric_key` and `explain.curve_at_depths` are public and used by
    `run.py`, `baselines.py`, `views.py`, `compare.py`;
  - `views.py` 316 lines, `views_summary.py` 165, `report.py` 163, `views_explain.py` 220,
    `effects.py` 153, `evaluation/card.py` 327, `reporting/card.py` 86, `run.py` 452,
    `compare.py` 472; `training/views.py::search_table` is public; `bin_orders` lives in
    `statistics/distributions.py`.
- **Running now:**
  - the Spark batch (`spark_e.txt`): the evaluation, card, report, views, effects, compare,
    metric and explain tests with `test_run`;
  - the ML-correctness audit of the chain, Training through Evaluation (Fable, xhigh, the
    one Fable subagent), `compat-guardian`, `silent-failure-hunter`: all read-only;
  - wave 5: the notebook builder (`notebooks/05_evaluation.ipynb`, the helper's Evaluation
    section, `NOTEBOOKS` and `PUBLIC_API` in `test_run.py`; it runs nothing).
- **Next, in order:**
  1. The Spark batch green; then **the acceptance tests alone**: `pytest
     tests/test_modelling_acceptance.py tests/test_traps.py -q -p no:cacheprovider` (about
     14 min; no agent may run pytest meanwhile; the three reviewers and the notebook builder
     do not).
  2. One fix round from the audit, the compat check and the silent-failure hunt, through the
     builders that own the files (the ids are in the transcript; `ListAgents` shows them).
  3. The main thread runs notebook 05 on `dev` (after 01 to 04's outputs exist there; see
     how `tests/test_run.py` executes notebooks).
  4. The full suite once, in the background, with the acceptance and slow tests
     (`pytest -m "slow or not slow"` as `tests/README.md` says); version 0.4.0 in
     `src/core_modelling/__init__.py` and CLAUDE.md's "Current state".
  5. The docs by `doc-writer`s (after the fix round, so they are written once):
     `evaluation.md`, `reporting.md`, `config.md` with `conf/base/TEMPLATE.yml`,
     `monitoring.md` (the drift reference's three tables), `training.md`, `dataset.md`,
     `run_modes.md`, `test_harness.md`, `architecture.md` (Public API, the inventory),
     `glossary.md`, `lessons.md` (Spark's `greatest`/`least` skip nulls; a package
     `__init__` that imports its run module makes import cycles; the dense-top bins),
     `environment.md` (the "verify inside the bank" list above), the new
     `docs/guides/modelling_faq.md` (with "What the research found" from `questions.md`),
     `docs/README.md` and `docs/components/README.md`; the plan's settled block corrected.
     The main thread writes `decisions.md`, `UPDATES.md`, `roadmap.md`, `worknotes/log.md`.
  6. Review guide 3 (`worknotes/m2_3_modelling/review_guide_3.md`), opening with the
     defaults taken (A92 to A102 and every "for review guide 3" line in this file), written
     so steps 2 and 3 are read together; then `/efficiency`, the final report, and stop.
     Tell the EDS the four old `ipykernel` processes are still open (never kill them).

## Eleventh checkpoint (2026-11-17, 23:10): the Spark batch is green; the close is running
- **The Spark batch after the wave 4 fixes: 192 passed, lint and format clean.**
- The 5-hour limit stopped the three reviewers and the notebook builder mid-read (reset
  22:40). Restarted: the ML audit and the notebook builder were resumed (`SendMessage`);
  `compat-guardian` and `silent-failure-hunter` were started again **on Opus** (they had
  inherited Fable; their briefs are the scratchpad's `brief_compat.md`, `brief_silent.md`).
  Always pass `model: opus` to a review agent that is not the ML audit.
- **Running now:**
  - the acceptance tests alone (`test_modelling_acceptance.py`, `test_traps.py`; output in
    the scratchpad's `acceptance.txt`; no agent runs pytest);
  - the ML audit, `compat-guardian`, `silent-failure-hunter` (read-only), the notebook 05
    builder (runs nothing);
  - four doc-writers, started before the fix round to save wall time (each gets the fix
    round's changed facts by `SendMessage` afterwards): `evaluation.md` (Opus);
    `reporting.md`, `monitoring.md`, `model_bundle.md` (Opus); `config.md`,
    `run_modes.md`, `conf/base/` (Sonnet); the new `docs/guides/modelling_faq.md` with its
    registration in `docs/README.md` and CLAUDE.md's doc map and repo map (Opus). Each
    reports where the built code differs from the spec text: those lines go into review
    guide 3.
- **Still to launch:** after the fix round, one Sonnet doc-writer for the secondary docs
  (`architecture.md`, `glossary.md`, `training.md`, `dataset.md`, `test_harness.md`,
  `lessons.md`, `environment.md`, `docs/components/README.md`) and one Opus doc-writer for
  review guide 3 (from this file, the plan and the doc-writers' difference lists). The main
  thread writes `decisions.md`, `UPDATES.md`, `roadmap.md`, `worknotes/log.md`, the version
  and CLAUDE.md's "Current state".
- The keep-awake was renewed at 23:00 for eight hours.

## Twelfth checkpoint (2026-11-17, 23:30): two closing reviews are in; the fix round waits for the ML audit
- **`compat-guardian`: no break, minor bump (0.4.0).** No `schema_version` changed; step 2's
  run folders still load. Its doc lines went to the `evaluation.md` and
  `reporting.md`/`monitoring.md` writers. For the secondary-docs writer, `architecture.md`:
  Public API (`run_evaluation`, `compare_runs` at 0.4.0 with signatures; the default `run`
  includes `evaluation` and `run=` names one run; the CLI's `--run`; `build_frames(carry=)`
  and the `eligible_rows` key; the stale "refused until Evaluation is built" line) and the
  artifact inventory (the card: `CARD_SCHEMA_VERSION` in `model_card.json`; the drift
  reference: `drift_reference_schema_version` in `evaluation.json`; `list_runs` and
  `show_run` do not read `evaluation/` today). Notes for review guide 3: the scores table has
  no model key and no version of its own (fine inside `evaluation/`; Inference's shared table
  is another one); the view names became config contract through `skip_views`.
- **The config doc-writer is done** (`config.md`, `run_modes.md`, `TEMPLATE.yml`; no field
  and no version changed; one load refusal, a baseline form named twice).
- **`silent-failure-hunter`: 0 blocking, 4 should-fix, 4 notes. The triage for the fix
  round (one message per owning builder, sent with the ML audit's findings):**
  - report views builder (`views.py`, `views_summary.py`): a NaN value shows `undefined`, a
    NaN interval `(no interval)`, instead of a bare value or a blank cell;
  - card builder (`evaluation/card.py`): `insufficient` joins `CARD_METRIC_COLUMNS`; one
    public `check_card_inputs` holding the `_require` and `_check_same_run` calls that need
    no Evaluation output, for `_open_run` to call before anything is scored; the deferred
    item (Training's warnings as codes in the card) only if Training's side is done first;
  - `run_evaluation` builder (`run.py`, `scores.py`, `cells.py`, `tests/test_evaluation.py`):
    `_open_run` checks the `training.json` keys, Training's tables, the card inputs and the
    leftover `.tmp-*` / `.old-*` siblings before `build_frames`; `_discard` keeps the
    original error when its own `rmtree` fails (`add_note`); the docstring says what is left
    when the audit entry fails after the write; the `__other__` rows checked against the
    levels not kept, if it costs no Spark job; the test at `test_evaluation.py:141` that
    cannot fail replaced by one that fails after `write_scores` and finds no `.scores-*`;
    `ZERO_BIN_EDGES` (the duplicate of `tasks._regression_target_bins`);
  - `compare_runs` builder: a partial overlap of the scored rows is refused (same data
    definition and split, so differing rows mean a source period changed);
  - effects builder (`views_explain.py`): the view says which of the two reasons applies
    (not a key feature / EDA's base not positive) from what it already holds.
- **The acceptance and trap tests pass on `dev`: 20 passed, 6 min 45 s** (23:35).
- **`evaluation.md` is rewritten as built** (641 lines). Where the code differs from the
  spec, for review guide 3:
  - finding the run also matches the sources digest; a named run with another client split
    or sources, or with no `training/`, is refused;
  - the drift reference is three tables in `evaluation/tables/` with
    `drift_reference_schema_version` in the json, not a separate artifact keyed by
    `model_hash`;
  - the effect features are ranked by Training's out-of-fold contribution share, not test's;
  - `population_base_rate` and a historic rate number are compared on mean prediction
    beside an `observed` row; a column baseline with nulls, or outside [0, 1], fills only
    the order metrics;
  - strata carry every metric per level (regression drops the concordance); levels are
    capped on the scored rows;
  - `log_loss` is itself a metric; `mean_score` and `mean_target` are stored on every row;
  - the fixed depths are added to the configured slices; capture, rate and lift each carry
    an interval; a metric undefined in any replicate gets no interval;
  - `compare_runs`: two different row losses give no difference; another entity, an
    unevaluated run, a shared row with another target or split are refused;
  - the acceptance test asserts observed to expected on test only, at 100 replicates;
  - the stored `cells` hold replicate 0 only; the scores table stores the `baseline_<form>`
    columns but not the carried source columns (unless they are strata).
  - Not verified by the writer: whether a person's `include` reaches the `stage2/` ledger's
    `key_feature` column.
- **`reporting.md`, `monitoring.md` and `model_bundle.md` are written as built.** Where the
  code differs from the spec, for review guide 3:
  - the score distribution is drawn as each class's ratio to chance against the score's
    percentile, not as shares per class;
  - the reliability axes run from zero to 1.25 × the highest value and nothing is greyed;
  - view 5 also shows the calibration intercept; view 7 in regression shows RMSE, MAE and
    predicted to observed; view 17 puts all validation clients beside the test-split ones;
  - view 14 (thresholds) is built from the curves at the capture depths;
  - view 10 falls back to the dependence scatter when EDA has no groups for a feature;
  - `metric_lines` in view 2 plots `decision.metric`;
  - the names `skip_views` takes are `report.py::VIEWS` (`VIEWS_BY_TASK` holds per-task
    settings);
  - the card embeds config sections as dumped (decision, slices, eligibility, target, split,
    intervals) and reads `training.path` and the time budget, so its shape follows the config
    schema;
  - `predict` and `score_frame` take `threads`; `score_spark` scores on the Spark task's CPUs.
  The main thread made `evaluation.md` the one owner of "What these numbers cannot say"
  (`reporting.md` links to it).
- **Notebook 05 is built** (35 cells, 17 code; `00_modelling_helper` has its section 10;
  `tests/test_run.py` and `notebooks/README.md` updated; notebook 04's closing line fixed by
  the main thread). Defaults for review guide 3: there is no notebook helper module, so the
  run cell flattens `result.views` in one dict comprehension and each view cell is
  `display(*views[...])`; step 11 compares the run with itself as shipped; a view named in
  `skip_views` must be deleted from the notebook by hand (the guide cell says so).
- **Running (23:55):** one background command (the scratchpad's `nb/chain.txt`): the chain
  on `dev` for `conf/base/cc_acquisition.yml` under a scratch environment
  (`nb/environment.yml`), then notebook 05 and the helper executed as scratch copies
  (`nb/run_notebook.py`; the repo's notebooks keep no outputs), then `tests/test_run.py`.
  After the fix round the two notebooks run once more (the same two `run_notebook.py` lines).
- **`docs/guides/modelling_faq.md` is written** (824 lines: 34 questions in five groups and
  the research note in full with its sources) and registered in `docs/README.md` and
  CLAUDE.md's doc map and repo map. `questions.md` is untouched. Owed by the main thread:
  D-140's Sources pointer and `training.md`'s line on where the research note lives now
  point to the guide. Worknotes answers the built code overtook, for review guide 3:
  - ties at a slice cut: the cut bin is split in proportion to its rows, not by a seeded hash;
  - the drift reference's scores: 10 quantile groups of the pooled test scores, not 20 per
    period;
  - the acceptance test's lgbm runs 15 trials; the trials table holds `fold_loss` only;
  - Evaluation's ledger columns are a separate `features` table;
  - (step 2) folds reach FLAML as a splitter object; the search starts at FLAML's own start;
    the regression search metric comes from the decision; the out-of-fold metric is
    optimistic.
- **The `dev` chain and the notebooks ran clean before the fix round:** the chain exit 0;
  notebook 05 executed end to end (17 of 17 code cells, about a minute), the helper too (16
  of 16). They run once more after the fix round.

## Thirteenth checkpoint (2026-11-17, about 23:25): the ML audit is in; the one fix round is running
- **The ML audit (Training through Evaluation): no leak, no split or time violation; one
  blocking, eight should-fix, four notes.** Its evidence scripts are the scratchpad's
  `audit/check1.py` to `check4.py`.
  - **B1 (blocking): average precision from cells is far too low below a 1% base rate**
    (binned minus row AP, relative: 1% −3.5 to −4.7%; 0.3% −3 to −18%; 0.1% −5 to −44%;
    0.05% −34 to −63%), because binary's top bins hold 0.1% of the rows; the same bins bias
    the calibration intercept. Fix (verified by the audit): 0.01% bins inside the top 1% and
    0.001% bins inside the top 0.1%, about 390 bins; AP then within 0.002 of the row value.
    **Design taken:** `score_edges` adds one more `approxQuantile` on the rows at or above
    the body's 0.99 edge, same `QUANTILE_ERROR`; the strata take every fourth edge of the
    whole grid; regression's 50 bins stay.
  - S1 the single-feature baseline is chosen on non-null train rows and scored with nulls
    lowest: **default taken: a warning `single_feature_baseline_has_nulls` with the train
    null share, no threshold and no new choice rule** (an open point for the EDS);
  - S2 regression's train concordance is on rows, test's on cells (up to 0.01 higher): the
    sentence says so (**default; computing Training's on cells is the alternative**);
  - S3, S6: fixed by B1's grid;
  - S4 `events` are positive rows (a conversion counts in up to `w` pooled periods): the
    report's wording changes, the column name stays;
  - S5 permutation importance: five permutations averaged, `loss_change_sd` stored; no
    positive row in the explanation sample is decided up front (`evaluation.json` →
    `unavailable`);
  - S7 strata's coarser bins: one sentence in the strata note;
  - S8 the named-run path: `evaluation.json` gains `training_config_hash` and `row_loss`
    (the deviance's name);
  - notes for the docs: one run can be evaluated on several validation periods (disclosed
    by `earlier_validations`, not enforced); the score edges are cut over test plus
    validation rows (a discretisation: test rank metrics move in the fourth decimal with the
    validation period); the drift reference's scores are test clients only, production
    scores train clients too (`monitoring.md`);
  - **unconfirmed: rerun determinism of the binned rank metrics** (`approxQuantile` on
    re-read parquet): the main thread evaluates one run twice on the scratch `dev` data and
    diffs `evaluation/tables/metrics.parquet`, after the fix round;
  - verified right by the audit (for review guide 3): the Poisson weights, AUC from cells
    within 2e-4, O/E, RMSE, R² and the deviances equal to scikit-learn, the prior-shift
    offset under sampling (O/E 0.999 and 1.008 with it, 0.287 and 0.083 without), the rows,
    `v ≥ tk + w` at config load, train-only fits, label-free edges, `compare_runs` test-only.
- **The fix round (briefs in the scratchpad: `fix_cells.md`, `fix_run.md`, `fix_views.md`):**
  - a fresh Opus builder: the dense tail, `compare_runs` refusing a partial row overlap,
    the `__other__` check, `ZERO_BIN_EDGES` (`score_cells.py`, `cells.py`, `compare.py`,
    `metrics.py` docstrings, their tests);
  - the `run_evaluation` builder: the early input checks (`check_card_inputs` in
    `evaluation/card.py`, the leftover siblings), `_discard`, the test that cannot fail,
    S5, S1's warning, S8's two keys, `insufficient` in the card (`run.py`, `scores.py`,
    `explain.py`, `baselines.py`, `card.py`, `artifacts.py`, their tests);
  - the report views builder: `undefined` / `(no interval)`, S2, S4, S7's sentences, the
    deviance's label, the permutation view's sd and reason, the effects view's reason
    (`views.py`, `views_summary.py`, `report.py`, `views_explain.py`, `effects.py`, tests).
  - Not taken (stays an open question in `evaluation.md`): Training's warnings as codes with
    values, so the card could carry them (it changes step 2's `training.json`).
- **After the builders report:** the main thread checks the wiring across the three
  (`row_loss`, `unavailable`, `loss_change_sd`), runs the Spark batch (the list of batch E
  plus `test_run`), the two notebooks again, the determinism check, then the full suite with
  the acceptance and slow tests; one `code-reviewer` (Opus) on the fix round's diff; then the
  secondary-docs writer (Sonnet), review guide 3 (Opus), and the main thread's rows.
- `tests/test_run.py`: 10 passed (before the fix round).
- **Fix round, reported (their no-Spark tests pass; no Spark run yet):**
  - the report views builder: all seven items; `labelled_metrics(rows, row_loss)` names the
    deviance and drops it when `row_loss` is None; `VIEWS_BY_TASK` gains `events` and
    `gap_clause`; **the stored `effects` table gains `unavailable`** (a feature without a
    lift has one row holding the reason, `NOT_KEY` or `NO_BASE`);
  - the `run_evaluation` builder: all seven items; public
    `card.check_card_inputs(run_folder, resolved)` and `artifacts.check_siblings`, both
    called by `_open_run` before `build_frames`; `evaluation.json` gains `unavailable`,
    `training_config_hash`, `row_loss`; the permutation table gains `loss_change_sd`
    (`PERMUTATIONS = 5`); the warning `single_feature_baseline_has_nulls` (`feature`,
    `train_null_share`) takes the share from the **per-run ledger's `null_share`** (the
    encoder's, on the train frame), because `stage2/` holds no train share; the new Spark
    test `test_a_failure_after_scoring_leaves_no_staged_scores` is written, not run.
  - the dense-tail builder: `score_cells.py` has `SCORE_GRID`, `STRATA_STEP`
    (`{"binary": 4, "regression": 1}`), `TAIL_START`, `bin_quantiles(task)`,
    `quantile_passes(task)`; binary 380 bins (100 of 0.9%, 90 of 0.1%, 90 of 0.01%, 100 of
    0.001%), strata 95; `score_edges` makes a second `approxQuantile` over the rows at or
    above the 0.99 edge. **Measured (binned minus row, old / new grid):** AP at 1% −0.008 /
    −0.0002, at 0.1% −0.164 (−44%) / −0.0013, at 0.05% −0.399 (−61%) / −0.0014; calibration
    intercept at 0.1% −0.358 / +0.0009; slope within 0.0003; strata AP at 2.9% −0.0101 /
    −0.0007. Cells per replicate at 1M rows over 12 periods: per period 4,485 → 6,859,
    pooled 400 → 715. `compare._check_shared` refuses a partial overlap; `cells._check_other`
    checks the `__other__` rows. The main thread moved `ZERO_BIN_EDGES` to `tasks.py`
    (public; `cells.py` imports it) and made the strata note's coarser-bins sentence binary
    only (`VIEWS_BY_TASK[task]["strata_clause"]`).

## Fourteenth checkpoint (2026-11-17, about 00:10 on 11-18): the fix round is in; the final runs and docs are running
- `ruff check` and format pass on `src/`, `tests/`, `notebooks/` after the fix round; the
  package imports (380 binary bins, 50 regression).
- **Running:**
  - one background command (the scratchpad's `spark_f.txt`): the Spark batch (batch E's
    list), then notebook 05 as a scratch copy on the scratch `dev` data (`nb/`), a copy of
    its `evaluation/tables`, a second evaluation through the CLI, `nb/diff_metrics.py`
    over the two table folders (the rerun-determinism check the audit asked for), then the
    helper notebook;
  - `code-reviewer` (Opus) on the fix round's functions and the contracts across the three
    builders (`row_loss`, `unavailable`, `loss_change_sd`, the `effects` table's
    `unavailable`);
  - doc-writers: `evaluation.md` (the fix round's eleven facts and two more lines; resumed),
    the secondary docs (Sonnet: `architecture.md`, `glossary.md`, `training.md`,
    `dataset.md`, `test_harness.md`, `components/README.md`, `lessons.md`,
    `environment.md`, `tests/README.md`), review guide 3 (Opus:
    `worknotes/m2_3_modelling/review_guide_3.md`, with a "What was run" table whose `to
    fill` cells the main thread fills). `reporting.md` and `monitoring.md` have the fix
    round's facts; `config.md`'s `strata.min_events` line says Evaluation counts positive
    rows.
- **Then, in order:** the reviewer's findings fixed (small ones by the main thread); the
  full suite once with the acceptance, trap and slow tests (`pytest -m "slow or not slow"`,
  background, capped); `__version__` 0.4.0 and CLAUDE.md's "Current state"; the main thread's
  rows (`decisions.md` D-141 with the dense tail and D-140's research pointer to the FAQ,
  `UPDATES.md` status row and log line, `roadmap.md` milestone row and the two EDA open
  points, `worknotes/log.md`); the guide's `to fill` cells; `doc-sync` check;
  `/efficiency`; the final report; stop for the EDS (tell them the four old `ipykernel`
  processes are still open; commit nothing).
  - These facts go to the doc-writers after the Spark batch (`evaluation.md`: the three
    meta keys, the warning code, `loss_change_sd`, the `effects` table's `unavailable`,
    the early checks, the grid; `reporting.md`: `undefined` / `(no interval)`, the
    deviance's label; `config.md`: `strata.min_events` counts positive rows;
    `monitoring.md`: the drift reference's scores are test clients only).

## Fifteenth checkpoint (2026-11-17, late evening): everything is built and written; the full suite is running
- **After the fix round, all run by the main thread:** the Spark batch 201 passed (5 min
  49 s); notebook 05 as a scratch copy on `dev` 17 of 17 code cells, the helper 16 of 16; **one
  run evaluated twice: all 20 tables of `evaluation/tables/` identical** (the rerun
  determinism the ML audit left unconfirmed is confirmed on `dev`).
- **The code review of the fix round (Opus): 0 blocking, 4 should-fix, 4 nits.** Fixed by the
  `run_evaluation` builder: `check_siblings(folder, stage, tables, keys)` also refuses a
  killed run's staged `evaluation.scores-*` before any Spark work (the glob check in
  `scores.py` is gone); `permutation_unavailable(contributions)` refuses a sample whose target
  has one value (`ONE_TARGET_VALUE`: "not available: one target value in the explanation
  sample"); `card._read_run_folder` reads once for `check_card_inputs` and `build_card`; the
  failure test asserts the staged folder exists before it raises. By the main thread: the
  stale texts (`modelling_faq.md`'s bin sentence, the chart comment, `score_edges`' docstring
  on a tied block at the 0.99 edge, `evaluation.md`'s solved `ZERO_BIN_EDGES` question).
  Not taken: `compare_runs`' `rows` table still shows `rows_a`, `rows_b`, `shared` (always
  equal now).
- **Docs written:** `evaluation.md`, `reporting.md`, `monitoring.md`, `model_bundle.md`,
  `config.md`, `run_modes.md`, `TEMPLATE.yml`, `architecture.md`, `glossary.md`,
  `training.md`, `dataset.md`, `test_harness.md`, `tests/README.md`, `lessons.md` (T48 to
  T50), `environment.md`, `docs/README.md`, `docs/guides/modelling_faq.md` (new), CLAUDE.md
  (doc map, repo map, "Current state"), `decisions.md` (D-141 (b) and its status; D-140 and
  D-037's pointers to the FAQ), `UPDATES.md` (four status rows), `roadmap.md` (M2.3's row),
  the plan's A93. `__version__` is 0.4.0.
- **Review guide 3 is written** (`worknotes/m2_3_modelling/review_guide_3.md`, 385 lines; the
  main thread read it): 44 defaults A92 to A135, A103 to A108 first. Its `to fill` cells
  (§3's table, the code-reviewer line, §6's determinism line, line 11's version) wait for the
  full suite.

## Sixteenth checkpoint (2026-11-18, 00:30): the build is finished and with the EDS
- **Nothing is running and nothing is left to build.** No agent, no Spark, no pytest. Nothing
  is committed; commit only on the EDS's word.
- **The full suite ran once after the last code edit:** 1204 passed, 5 failed, 26 min 9 s.
  Both causes were outside the framework's code and are corrected:
  - a comment in `conf/base/TEMPLATE.yml` written as a placeholder (`baseline_<form>`) failed
    `test_filled_template_loads`; reworded, the config tests pass (138);
  - the four slow family tests shared `dev_env_file`'s data root with `dev_stage2`, whose EDA
    read the model input, so Training refused the artifacts ("read from other data"). They
    have `family_env_file` now (a data root of their own, `tests/test_training.py`). With the
    trap tests in one session: 156 passed, 1 failed (`lgbm`, the laptop's socket-buffer
    fault in a collect, T51); the four alone: 4 passed, 4 min 43 s.
- **Also after the last edit:** notebooks 05 (17 of 17 code cells) and the helper (16 of 16)
  as scratch copies; `ruff check .` and the format check pass; `__version__` prints 0.4.0.
- **Written at the close:** review guide 3 has no open cell; `docs/UPDATES.md`'s log line and
  `worknotes/log.md`'s entry (2026-11-17); `lessons.md` T51 and two build-process bullets
  (the full run with the slow tests, the template comment); `evaluation.md` links the FAQ;
  `doc-sync` done (links resolve, no names or machine paths).
- **Usage of this session** (`session_usage.py --session 40eb51cb`, list prices): 184 in
  all, Opus subagents 67%, Fable 32% (main thread 20%, Fable subagents 12%: the ML audit 7.91
  and two code reviews that inherited Fable, 12.25). 21 whole-context rewrites in subagents.
- **With the EDS:** the joint review of steps 2 and 3 (review guide 2 and review guide 3,
  A103 to A108 first); the two nits left; the open risks in review guide 3 §6; the four old
  `ipykernel` processes (28775, 28831, 28833, 28847) are still open and are the EDS's to close.
- **A next chat starts from:** `docs/UPDATES.md`, then review guide 3; this file is only the
  build's trail.

## Settled for wave 4 (in the briefs now)
- The card is written with `evaluation/` in the same `write_stage` call (`model_card.json`,
  `model_card.html` as texts), so `build_card` takes Evaluation's tables and meta in memory
  beside the run folder: `build_card(run_folder, tables, meta) -> dict`; the card builder owns
  its one call in `evaluation/run.py`.
- `report.py` (m3.4-report) imports the explanation views by name from `views_explain.py`
  (m3.7), so the two builders share no file; the names are fixed in both briefs.

## Next
1. When both builders report: add the `compare_runs` export; read `evaluation/run.py` in full;
   sync C's Spark batch (`test_evaluation`, `test_run`, `test_compare`, `test_metric_tables`,
   `test_training` if `training.json` changed); one combined `code-reviewer`; run Evaluation
   once per task into the scratchpad's `runs/` for wave 4's builders.
2. A failure goes back to its builder (m3.3a owns `scores.py`, `cells.py`, `frames.py`; m3.3b
   `baselines.py`, `tables.py`, `drift_reference.py`; m3.6 `explain.py`; m3.1
   `statistics/metrics.py`, `bootstrap.py`, `score_cells.py`), unless it is a two-line fix.
Rewrite this file at every sync point, as the last tool call.

## Gotchas
- Subagents run no Spark and never the full suite; one memory-heavy job at a time
  (`pgrep -fl "pytest|SparkSubmit|synthetic"` first); cap background runs with
  `perl -e 'alarm shift; exec @ARGV' <seconds> <command>`; never `-x` on a batch whose count
  is reported; output to a file in the scratchpad, read the tail.
- Four old `ipykernel` processes (pids 28775, 28831, 28833, 28847) still hold memory: the EDS
  was asked to close them; do not kill them.
- Scripts need `import core_modelling` first (the `np.NaN` shim, T1).
- `conf/local/cc_acquisition.yml` is the EDS's own variant: use `conf/base/` for the build.
- Never prune "What the research found" in `worknotes/m2_3_modelling/questions.md` before it
  has moved to `docs/guides/modelling_faq.md`; do not edit `worknotes/sync.md`.
- The rate limit stopped Opus agents before (11-13): resume them with `SendMessage` after the
  reset, never restart from nothing.
