# Stage 2 (M2.2 Understanding): the build plan
_Written 2026-11-02 for the SDS's approval, revised 2026-11-03 after their remarks (the routing
budget, the notebooks' guides, `lagged_signal_drop`, the edges rule, V13–V15; V16–V17 added by the build, 2026-11-03; V18–V28 by major step 2, 2026-11-04; V29–V54 by its review-2 build and stage-3 review, 2026-11-05; V55–V73 by review 3 and the gaps spec, 2026-11-06; V74–V91 by major step 3, 2026-11-07; V92–V97 by its review 1 and V98–V102 by its answers, 2026-11-09) · from the spec in `docs/components/eda.md`,
`feature_checks.md`, `feature_ledger.md`, `reporting.md`, `config.md`, `dataset.md` and the decision
rows D-134–D-137 · the design record is `answers.md` beside this file · nothing is coded before the
SDS approves this plan (`CLAUDE.md` §1 step 1) · the holistic review's outcomes are folded in (§9, with the
decisions the spec step and the build made without the SDS, V1–V73, to veto by number)_

**Where it stands (2026-11-03): the design is settled and specified; this plan, revised after the
SDS's remarks, is waiting for approval.** Three major steps, each ending in the SDS's review with a
review guide; sixteen minor steps, each ending in the review subagents; one routing table that
keeps Fable on the main thread (the plan, the briefs, reading every diff, the integration, the
ML-correctness audit, the reports to the SDS) and on the four architecturally hardest code pieces,
between a third and half of the stage's tokens, and sends the rest to Opus and Sonnet at the effort
the cost of a wrong answer warrants (D-072 (l), extended 2026-11-03).

## 1. What is built, and what is deliberately left out
**Built (version 0.3.0 at the end):** the Stage 2 config fields and the audit-log changes; the
snapshot frame and the two Spark counts passes; the statistics engine on cells; the artifacts and
the ledger; the reporting primitives; EDA with its report and notebook 02; Feature Checks with its
report and notebook 03; the per-task spec's regression entries; the tests of `CLAUDE.md` §7
including the trap acceptance test; the docs in the same change.

**Left out, on purpose (each has an owner milestone or decision):** the HDFS transport for
artifacts and the `init` command (M2.4, Q471, Q487); the model card and the ledger's per-run part
(M2.3); grouped importance and the cluster rule for automated selection (M2.3); the `unstable`
synthetic trap kind (M4, D-064); the theme file in `conf/local/` (M4); the time-alignment screen on
the eligibility `define` columns (a known limit, `feature_checks.md`); readable labels and the
source per feature (Q452); any migration (no bumps in 0.x, D-136); any sampling of the analysis
population (D-135); `psi_gap`; chart sampling (no chart draws clients: every chart comes from cells
or quartiles, [reporting](../../docs/components/reporting.md) requirement 5); a `08_reporting` copy
of the reports; exact
row-level statistics outside the tests (D-135); the bank-side timing (unverified until the
pre-release).

## 2. The major steps and their minor steps
Every minor step: its goal, the files it owns, the functions with their signatures, the tests,
what it leaves out, and its agent (type · model · effort; the table in §3 says why). Within a
major step the minor steps marked ∥ run in parallel on disjoint files; the others wait for what
they list. Each minor step ends with its tests and `ruff check` on its files, then the review
subagents (§4); each major step ends with the full suite (main thread, background), the review
guide and the SDS's review.

### Major step 1: foundations (the config, the audit log, the frames and counts, the statistics engine, the artifacts and the ledger)
What the SDS reviews at the end: the config template and the audit-log entries, the counts table
on the synthetic data, the statistics against their oracles, the ledger's hold-out rule.

**m1.0 Spike: the facts on the pinned versions** (first, alone: it informs m1.3 and m2.1) ·
`general-purpose` · Sonnet · high
- Goal: measure the library behaviour the design assumes, on the dev machine, and report evidence.
- Owns: nothing in the repo; a scratch script per item; the results go to `worknotes/log.md` (by
  the main thread) and, where a trap, to `docs/context/lessons.md`.
- Items: `Bucketizer(splitsArray=…, inputCols=…, outputCols=…, handleInvalid="keep")` over 150
  columns on PySpark 3.4.3 (null and NaN in the extra bucket; `np.nextafter` singleton splits
  accepted); the explode + `groupBy` pass on the canonical window (585,000 rows × 150 features)
  under `driver_memory: 2g`: runtime and the partial aggregate in the plan; the client-sorted pass
  (`F.lag` for 150 columns, `min == max`); the concordance from a two-way table against
  `roc_auc_score` on rows (equal with values as bins; within 0.005 at 100 quantile bins on the
  synthetic snapshot) and the regression τ-b from the table against `kendalltau`; the Arrow
  collect of the snapshot under the default `maxResultSize`; `DataFrame.corr(method="spearman")`
  versus rank-once-then-Pearson at 160 columns × 200,000 rows; `association(method="cramer")` on
  an empty row or column; JupyterLab's "Trust HTML" and an `IFrame` of a 5 MB file; `go.Box` on a
  log axis with a zero quartile; the plotly fragment size and `div_id` uniqueness; Styler
  `background_gradient` needing matplotlib; parquet list columns on pyarrow 19.0.1; `binomtest`
  timing against the closed-form Wilson; `lstsq` on exact identities; `DataFrame.query` with
  bank-style names; `linkage` with missing pairs; `rank` with nulls; the edges rule
  (`quantile_edges` with mass points, T25) over every numeric of the canonical snapshot: the
  bin-count distribution and the largest non-singleton bin's share, so the one-bucket symptom the
  SDS saw in earlier plot code cannot recur unnoticed.
- Acceptance: a table item → result → consequence; one Spark job at a time (the 8 GB Mac).
- Leaves out: any code in `src/`.

**m1.1 ∥ The config schema's Stage 2 fields** · `general-purpose` · Opus · xhigh (same agent as m1.2)
- Owns: `src/core_modelling/config/schema.py`, `levels.py`, `conf/base/TEMPLATE.yml`,
  `cc_acquisition.yml`, `td_acquisition.yml`, `tests/test_config_schema.py`.
- Functions and models: `Eda(snapshot: Literal["last"] | date = "last", bins: int | None = 100,
  key_features: KeyFeatures)`, `KeyFeatures(top_n: int = 10, include: list[str] = [],
  max_correlation: float = 0.9)`; `Features(candidates, kinds: dict[str, Literal["numeric",
  "categorical"]] = {}, excluded, kept, held)` (the last three replay-written, refused in a file);
  `Time.validation_period: date | None`; `FeatureChecks(quality: Quality | None, leakage: Leakage |
  None, time_alignment: TimeAlignment | None, stability: Stability | None, redundancy: Redundancy |
  None)` with one model per step holding every parameter of `feature_checks.md`'s table with its
  default, the section default running every step, an unknown parameter failing loud;
  `snapshot_period(cfg) -> date` (resolves `last`; a period outside the window fails at load);
  `top_n` leaves `LEVEL_DEFAULTS`; the template shows every field with a one-line explanation
  (the template test already checks display; the explanation is checked by review).
- Tests: every new field round-trips; `eda.snapshot` outside the window refused; `eda.bins: null`
  accepted; a step left out of a present mapping is `None`, the section left out runs all five; an
  unknown step parameter refused; `features.kinds` naming a non-candidate refused at load;
  `validation_period: null` accepted; a file carrying `features.held` or `kept` refused.
- Leaves out: the audit-log operations (m1.2).

**m1.2 The audit log: `keep`, `flag`, `run`, the held set, the paths** (after m1.1, same agent) ·
Opus · xhigh
- Owns: `config/replay.py`, `config/audit_log.py`, `config/__init__.py`, `__main__.py`,
  `environment.py` (the paths), `tests/test_audit_log.py`, `tests/test_environment.py`.
- Functions: `Entry` gains `finding: str | None` and `findings: list[str] | None`, `periods:
  list[str] | None`; operations `keep` (renamed from `keep_despite_flag`), `flag` (stage-written,
  empty `features` allowed only here; it changes the input through `features.held`, so the
  resolved-input hash moves with it), `run` with `periods`; `open_flags(entries: list[Entry]) ->
  dict[str, list[str]]` and `held_features(entries) -> list[str]` in `replay.py`; `replay` writes
  `features.excluded`, `features.kept` and `features.held`; `_set_fields` refuses
  `time.validation_period` when any `run` entry (reverted or not) lists that period;
  `LOGGABLE_SETTINGS` gains `features.kinds`, `eda.snapshot`, `eda.bins`,
  `eda.key_features.max_correlation` (stage `eda`) and every `feature_checks.<step>.<param>` leaf
  (stage `feature_checks`), loses `eda.chart_sample_share` and `feature_checks.steps`;
  `record_decision(..., keep: list[str] | None = None, findings: list[str] | None = None, ...)`;
  CLI `decide --keep … --findings …`; `data_path(env, use_case, layer, *parts) -> str` and
  `audit_log_dir(env, cfg, entity)` → `<root>/<use_case>/04_feature/<ddh>/decisions`;
  `feature_dir(env, cfg, entity, *parts) -> str` (`04_feature/<ddh>`, the ledger's folder; with a
  stage name the stage folder; built instead of the planned `stage_dir`, 2026-11-03).
- Tests: `keep` with explicit and default `findings`; a `flag` entry opens, a later empty one
  closes; a different finding reopens, the same finding with new values does not; `features.held`
  appears in the resolved config and moves the resolved-input hash; the refusal of
  `set time.validation_period` on a compared period; the new paths; the golden hashes re-pinned
  only where the canonical form changed (D-088's carve-out).
- Leaves out: writing `flag` entries from a stage (m3.2).

**m1.3 ∥ The frames and the counts passes** · `general-purpose` · Fable · xhigh
- Owns: `dataset/frames.py`, new `dataset/counts.py`, `dataset/__init__.py`, `tests/test_frames.py`,
  new `tests/test_counts.py`.
- Functions: `Frames(snapshot, rows, train, test, validation, log, meta)`; `build_frames(...,
  stage="eda")` collects the snapshot (the supported candidates only) and leaves `rows` in Spark
  (the compared periods' eligible rows, `target` set to null outside the window); `STAGE_FRAMES`
  without `feature_checks`; the collect callout per frame kind. In `counts.py`: `LEVEL_CAP = 50`;
  `compared_periods(cfg, available: list[date]) -> dict[str, list[date]]` (`window`, `gap`,
  `latest`; the validation period never inside); `bin_edges(snapshot, kinds, bins: int | None) ->
  dict[str, np.ndarray | None]` (through `statistics.quantile_edges`: mass points as singleton
  bins, quantile edges over the rest, T25); `window_levels(rows,
  categoricals, window_periods) -> tuple[dict[str, list[str]], list[str]]` (the levels and the
  categoricals over the 10,000-level ceiling; as built); `count_cells(rows, edges, levels,
  over_ceiling, target_edges, window_periods, spec) -> pd.DataFrame`; `count_lagged_cells(same)`
  (lag by period index); `client_constant_shares(rows, features, window_periods) -> pd.DataFrame`;
  `population_counts(panel, cfg, periods) -> pd.DataFrame` (per compared period; the labelled counts
  inside the window only; called inside `build_frames(eda)` into `Frames.meta["population"]`);
  `estimate_cells(rows, kinds, bins, window_periods) -> int` (`approx_count_distinct` per column,
  both passes; with `eda.bins: null` more than `MAX_CELLS = 50_000_000` fails loud naming
  `eda.bins`). The pooled categorical bins are the reserved `__other__` and `__new__`.
- Tests (unit preset, real local Spark): the cells equal a pandas `groupby` on the collected
  rows for three features and two periods; the cell estimate refuses a planted `MAX_CELLS` of 10; no label outside the window and no validation row in
  `rows`; `eda.bins: null` gives one cell per distinct value; the lagged cells null for the first
  window period and for a missing previous period; the client-constant share of a static column
  is 1; the population counts equal Target Factory's summary where both exist; `Bucketizer` on
  the edges of a 90%-zero column gives the zero bin plus at least `bins / 2` non-empty bins.
- Leaves out: any statistic (m1.4).

**m1.4 ∥ The statistics engine and the regression entries** · `general-purpose` · Fable · xhigh
- Owns: new `src/core_modelling/statistics/` (`cells.py`, `concordance.py`, `distributions.py`,
  `intervals.py`, `association.py`), `tasks.py` (the new entries), new `tests/test_statistics.py`
  (built as `tests/test_statistics_distributions.py` for m1.4a and `tests/test_statistics.py` for
  m1.4b), `tests/test_target_factory.py` only where the spec's keys change. Built in two halves
  (2026-11-03): m1.4a `distributions.py` first, so the counts passes could import `quantile_edges`.
- Functions: `pool_periods(cells, periods, lagged=False)`, `two_way_table(cells, order=None) ->
  np.ndarray`, `null_table(cells)`, `shares(cells) -> dict`; `concordance_from_table(table) ->
  float`, `direction_from_table(table) -> int`, `concordance_se(value, events, non_events)`,
  `kendall_null_se(units)`, `SE_FLOOR = 0.005`, `best_order_concordance(table, k_rows, base_rate)`,
  `cochran_q(values, ses) -> float`, `encode_levels(level_table, levels, k_rows) -> dict[str,
  float]`, `concordance_exact(cells) -> float` (the `eda.bins: null` regression path through
  `kendalltau` on expanded cells); `quantile_edges(values, bins) -> np.ndarray` (the mass points,
  values holding ≥ `1 / bins` of the rows, as singleton bins, `bins − n_mass` quantile edges over
  the remaining values, deduplicated; T25), `bin_labels(edges)`, `merge_bins(cells, groups) ->
  pd.DataFrame` (by cumulative row share in `bin_order`; a mass point stays its own group),
  `psi(expected, actual)`, `new_level_share(cells,
  window_levels, period)`, `standardised_difference(a, b)`; `wilson_interval(k, n)`,
  `t_interval(mean, sd, n)`; `PAIRWISE_ROWS = 200_000`, `MIN_SHARED_ROWS = 1_000`,
  `spearman_matrix(frame)`, `cramers_v(a, b)`, `correlation_ratio(numeric, categorical)`,
  `association_table(frame, kinds, seed) -> pd.DataFrame`, `cluster_features(table, max_assoc) ->
  dict[str, int]`, `explained_by_others(table, members) -> dict[str, float]` (from the correlation
  submatrix with a small ridge). `TASK_SPECS` entries for both tasks: `target_bins`,
  `summarise_group`, `rare_effect`, `concordance_se`, `events_warning`, `support_name`,
  `base_rate_views`, `lift_available` (regression: the overall mean is positive; else lift and the
  rare effect read "not available: mean not positive", D-035). `ranking_value(plain, best_order, se)
  -> float` returns the best-order value only when it beats the plain one by max(0.03, 4 · SE)
  (`is_non_monotone`; built 2026-11-03 after the audit measured the fixed margin's false marks).
- Tests (no Spark): the table concordance equals `roc_auc_score` with values as bins and lies
  within 0.005 of it at 100 bins on a synthetic snapshot column; the regression table τ-b against
  `kendalltau`; a 300-level random code encodes below 0.55; no null control is marked `non_monotone`; `correlation_ratio` equals |Spearman|
  for two levels; `psi` on known shares; `wilson_interval` against `binomtest`; `cochran_q` against
  `scipy.stats.chi2`; the best-order value of an inverted-U column beats its plain value by ≥
  0.05 and a null control's stays below 0.55; `explained_by_others` reads 1 on an exact identity;
  the regression `summarise_group` on the variant fixture; `quantile_edges` on three constructed
  columns (90% zeros with a long tail, Poisson counts, continuous): at least `bins / 2` bins and no
  non-singleton bin above `2 / bins` where the distinct count allows; `merge_bins` keeps a 90% mass
  point as one group and splits the rest into the other nine.
- Leaves out: anything that reads a frame or a file.

**m1.5 ∥ The artifacts and the ledger** · `general-purpose` · Opus · xhigh
- Owns: new `src/core_modelling/artifacts.py`, new `ledger.py`, new `tests/test_artifacts.py`,
  new `tests/test_ledger.py`.
- Functions: `StageResult(tables, ledger, log, meta, paths, views, frame, config)`;
  `write_stage(result, folder, name) -> dict[str, str]` (a temporary folder renamed on success;
  `tables/*.parquet`, `<name>.json` with `schema_version: 1`, `resolved_config.yml`);
  `read_stage(folder, name) -> tuple[dict, dict[str, pd.DataFrame]]`; `settings_digest(resolved,
  paths: list[str]) -> str`; `check_upstream(meta, resolved, paths) -> None` (fails loud naming the
  changed path); `remove_stage(folder)`. `LEDGER_SCHEMA_VERSION = 1`; `create_ledger(candidates,
  kinds, lineage, unsupported)`; `add_columns(ledger, columns, stage)` (`COLUMNS_BY_STAGE`);
  `save_ledger(ledger, folder)`; `read_ledger(folder)`; `render_decisions(ledger, resolved,
  entries)`; `resolve_features(ledger, resolved) -> list[str]`.
- Tests: the temporary folder never leaves a half-written stage (an exception mid-write); the
  digest refusal names the path; the parquet round trip of list columns; `add_columns` refuses
  another stage's column; `resolve_features` against hand-built resolved configs; a derived
  column refused by `save_ledger`; a newer `ledger_schema_version` refused.
- Leaves out: who writes the entries (m3.2).

**End of major step 1:** the full suite (main thread, background); the review guide
(`worknotes/m2_2_understanding/review_guide.md`: what to read, in which order, what right looks
like); the SDS's review. Estimated size: about 1,100 lines of code and 800 of tests.

### Major step 2: EDA (the reporting primitives, the EDA stage, notebook 02)
What the SDS reviews at the end: the EDA report on the synthetic card and term-deposit configs,
notebook 02, the ranking against the trap list by eye.

**m2.1 ∥ The reporting primitives** · `general-purpose` · Sonnet · high
- Owns: new `src/core_modelling/reporting/` (`html.py`, `charts.py`, `blocks.py`, `theme.py`), new
  `tests/test_reporting.py`, `requirements.txt` (`jinja2==3.1.6`, pinned on first use, D-137;
  asked of the SDS in this plan: it is already in the devcontainer).
- Functions: `write_report(title, sections: list[dict], path) -> str` (plotly.js embedded once,
  `div_id`s unique); `figure_html(fig, div_id) -> str`; `table_html(styler) -> str`;
  `style_table(df, ...) -> Styler`; `bar_with_intervals(df, x, y, low, high, counts, title)`,
  `lift_chart(...)`, `box_from_quartiles(df, ...)`, `grouped_lines(df, ...)`, `heatmap(matrix,
  ...)`, `apply_rules(fig, kind)` (axes from the data, the null bar, greyed insufficient cells);
  `choices_block(resolved, choices: list[dict]) -> Styler`; `headline(numbers) -> str`;
  `warnings_block(items) -> str`; `appendix(parts) -> list[dict]`; `THEME`.
- Tests: plotly.js appears once; ids unique over sixty figures; the rate axis range is
  `(0, 1.25 × max)`; a null bar is labelled `null`; the report opens as a file (size reported).
- Leaves out: any stage content.

**m2.2 ∥ The EDA modules** · `general-purpose` · Opus · xhigh
- Owns: new `src/core_modelling/eda/` (`population.py`, `ranking.py`, `deep_dives.py`), new
  `tests/test_eda_modules.py`.
- Functions: `detect_kinds(schema, overrides, candidates) -> dict[str, str]`;
  `feature_statistics(cells, counts, kinds, task, snapshot_period, window_periods) -> pd.DataFrame`
  (every ranking column of `eda.md`); `rank_features(stats) -> pd.DataFrame`;
  `select_key_features(ranking, association, cfg) -> pd.DataFrame` (the correlation skip,
  `represented_by`, the `include` list first; ordered by `ranking_value`); `funnel_per_period(log)`;
  `target_per_period(population_counts, task)`; `strata_tables(snapshot, cfg, task)`;
  `reference_groups(snapshot, tags, key_features, strata)`; `bin_table(cells, feature, periods,
  edges, task)`; `level_table(...)`; `quartiles_by_target(snapshot, feature)`;
  `per_period_concordance(cells, feature, task)`; `strata_pivots(snapshot, features, cfg)`;
  `pivot_target(result, rows, columns=None, where=None) -> Styler` (public).
- Tests: on cells built in the test from the unit preset's collected rows: the ranking's
  columns and order; the skip and `represented_by`; the kinds with an override; `pivot_target`
  with a backticked name; the greyed cells below `MIN_BIN_SUPPORT`.
- Leaves out: the stage function and the report (m2.3).

**m2.3 The EDA stage, its report and `run`** (after m2.1 and m2.2) · `general-purpose` · Fable · xhigh
- Owns: new `eda/run.py`, `eda/__init__.py`, `run.py`, new `tests/test_eda.py`, `tests/test_run.py`.
- Functions: `run_eda(cfg, entity, env, spark) -> StageResult` (the flow of `eda.md` Level 2);
  `_views(tables, resolved) -> dict`; `_sections(result) -> list[dict]` (summary → core → extended
  → appendix); `_warnings(tables, resolved) -> list[str]`; `STAGES["eda"]`.
- Tests: end to end on the unit preset for the card config and the variant (regression):
  `eda/` holds every file, `eda.json` the population counts and the digest, the ledger the EDA
  columns, the report opens; a rerun removes a planted `feature_checks/` folder; `run --stages
  eda` on two configs.
- Leaves out: Feature Checks.

**m2.4 Notebook 02** (after m2.3) · `general-purpose` · Opus · xhigh
- Owns: new `notebooks/02_eda.ipynb`, `notebooks/README.md` (the line), the Public API test's
  notebook list.
- Content: the guide cell (what the stage is for, what to look at, the concordance in plain words,
  the decisions to record and how), the setup cell (`CONFIG`), `run_eda`, the display cells over
  `result.views`, `pivot_target`. **The guide text is the deliverable** (the SDS, 2026-11-03;
  `notebooks/README.md`): before every step a short markdown cell says what the step does, what to
  look at in its output, how to read each number (the ranking columns, the intervals, the greyed
  cells, the warnings), which decision to take and how to record it, at both automation levels;
  concise, nothing a first-time user needs left out. The brief carries the outline per cell; the
  main thread reads every guide line in the integration and rewrites what is vague.
- Tests: the existing notebook test (imports the Public API only, defines nothing); the notebook
  is run end to end on the `dev` preset in JupyterLab during the review (no runner dependency).

**End of major step 2:** the full suite, the review guide extended, the SDS's review (the report
and notebook 02 are what the SDS tries). Estimated size: about 1,000 lines of code and 500 of tests.

**Review 2 (2026-11-05).** The SDS reviewed major step 2 through notebook 02 (remarks R10–R28, the brainstorming round Q501–Q522: `answers.md`). The redesign is specified in `review2_spec.md` beside this file (steps A–G: the data layer, range labels, the reporting primitives, the EDA views and exploration functions, the notebooks on the 100k data, docs, a simplicity pass), built on 2026-11-05 and followed by the comprehensive review of the major step 2 code (seven reviewers, every finding checked by a second reader, one fix round); decisions taken on the way are V29–V54 in §9, the review guide is rewritten for review 3.

### Major step 3: Feature Checks (the steps, the decisions, the stage, notebook 03, the acceptance test)
What the SDS reviews at the end: the findings on the synthetic traps, the held set, the proposed
decisions and the `keep` round trip, the acceptance test's mapping, the two reports side by side.

**m3.1 ∥ The five steps** · `general-purpose` · Opus · xhigh
- Owns: new `src/core_modelling/feature_checks/steps.py`, new `tests/test_feature_checks_steps.py`.
- Functions: `FINDING_COLUMNS`, `FINDING_KINDS` (finding → `flag | note`), `STEPS` (name →
  function, in the fixed order); `check_quality(ledger, tables, params, task) -> pd.DataFrame`,
  `check_leakage(...)`, `check_time_alignment(...)`, `check_stability(...)`,
  `check_redundancy(...)` (the clusters from EDA's correlation table, written as `tables/clusters`,
  `explained_by_others` from the correlation submatrix);
  every rule as in `feature_checks.md`'s finding table.
- Tests: hand-built ledgers and cells for every finding: fires at the threshold, silent one step
  below; the exclusive quality findings; the two PSI notes on named periods; Cochran's Q with one
  supported period (no test, no crash); the regression variant's `rare_effect`.
- Leaves out: the entries and the stage.

**m3.2 ∥ The decisions and the stage** · `general-purpose` · Fable · xhigh (the stage after m3.1)
- Owns: new `feature_checks/decisions.py`, new `feature_checks/run.py`, `feature_checks/__init__.py`,
  `run.py` (the stage), new `tests/test_feature_checks.py`.
- Functions: `flag_entries(findings, entries) -> list[dict]` (one per finding when the set
  changed; empty closes); `proposed_decisions(findings, open_flags, entity) -> pd.DataFrame` (the
  call texts); `held_summary(ledger, resolved) -> pd.DataFrame`; `run_feature_checks(cfg, entity,
  env, spark) -> StageResult` (the flow of `feature_checks.md` Level 2: read EDA's artifacts,
  `check_upstream`, the steps, the entries through `record_decision` with `by: stage`, the run
  entry with `periods`, the ledger columns, the report).
- Tests: end to end on the unit preset after `run_eda`: the flag entries written once and not
  rewritten on an unchanged rerun; a `keep` entry removes the feature from `features.held` and
  the proposed decisions; the refusal without an EDA artifact and on a digest mismatch; the
  report opens; `run --stages eda feature_checks`.

**m3.3 The trap acceptance test** (after m2.3 and m3.2) · `general-purpose` · Opus · xhigh
- Owns: new `tests/test_traps.py`, `tests/conftest.py` (a session fixture generating the `dev`
  preset into a temporary folder), `tests/README.md`.
- Content: the mapping of `test_harness.md` keyed by trap kind and target (kind → step.finding for
  the card, the term deposit and the "any product" rows), `NOT_CHECKS` ((kind, target) → reason: an EDA
  view, no config for the loan target, off by default), the rule that an unlisted pair fails; assertions on the `*_window` ledger
  columns; the null controls below 0.55 and never flagged (the false-positive check, V91); the D-088 counts compared from `eda.json`; the term-deposit config without
  per-period findings; only `client_constant` for the look-ahead trap; the bin-count assertion on
  every numeric candidate (at least `eda.bins / 2` bins where the distinct count allows, no
  non-singleton bin above 5%; T25).
- Tests: itself; runtime reported (about a minute expected, Q486).

**m3.4 Notebook 03** (after m3.2) ∥ with m3.3 · `general-purpose` · Opus · xhigh
- Owns: new `notebooks/03_feature_checks.ipynb`, the notebook list.
- Content: the guide cell, the setup cell, `run_feature_checks`, the findings and held features,
  the proposed decisions with the `record_decision` call text (the `CONFIG` placeholder; no
  commented-out cell), a markdown cell on what to do at each level. The guide rules of m2.4 apply;
  the guide says in words that, for Training, a held feature acts as an excluded feature without a
  final decision: the model is built without it until the person keeps or excludes it (V1, the
  SDS's condition of 2026-11-03), and walks through one `keep` and one `exclude` on the synthetic
  traps.

**m3.5 Docs, version and the review guide** (last) · Sonnet · high for the propagation; the
main thread for `decisions.md`, `UPDATES.md`, `roadmap.md`, `log.md`, the review guide
- Owns: every doc whose Status or Interface changes from "planned" to "built"; `__version__` →
  `0.3.0`; `docs/architecture.md`'s Public API table; the `doc-sync` skill at the end.

**End of major step 3:** the full suite, the `ml-correctness-auditor` on the whole stage, the
`compat-guardian` on every artifact and the Public API, the review guide, the SDS's review.
Estimated size: about 800 lines of code and 600 of tests.

## 3. The routing table (D-072 (l), reset 2026-11-04)
Major step 1 ran Fable on the main thread, two builders and three audits: about 40% of the output
tokens, and most of the weekly Fable allowance. The SDS's reset (2026-11-04): Fable at 25–30% of a
stage in general, and almost none for the rest of Stage 2. So the main thread runs on Opus, every
builder on Opus or Sonnet, and Fable does one thing: the whole-stage ML audit at the end of major
step 3, where step 1's audits earned their cost (the margin and the encoding). `xhigh` only on the
two pieces where a wrong answer is costliest (m2.3, m3.2); `high` elsewhere, `medium` for
mechanical text. Reviews are folded: one combined review per minor step, one fix round per major
step (step 1 ran 15 reviews and seven fix rounds).

| Piece | Model · effort | Why |
|---|---|---|
| main thread (briefs, integration, review guides, reports) | Opus | the whole picture; the SDS switched it 2026-11-04 |
| m2.1 the reporting primitives | Sonnet · high | a complete brief with signatures; not a §4 path |
| m2.2 the EDA modules | Opus · high | specified column by column on the built engine |
| m2.3 the EDA stage, report and `run` | Opus · xhigh | integrates everything step 1 built; the call sequence is written |
| m2.4, m3.4 the notebooks | Opus · high | the guide cells are the main deliverable (the SDS, 2026-11-03) |
| m3.1 the five steps | Opus · high | the rules are a table |
| m3.2 the decisions and the stage | Opus · xhigh | the hold-out mechanics (§4.6) |
| m3.3 the trap acceptance test | Opus · high | a §4 invariant test from a given mapping |
| m3.5 the doc propagation | Sonnet · medium | text whose substance is settled |
| one review per minor step: `code-reviewer` briefed with the silent-failure and §2 lenses where they apply | Opus · high | one fresh read instead of two to four |
| `ml-correctness-auditor` on m2.2 + m2.3 together, on m3.1 + m3.2 together | Opus · high | the §4 paths, once per major step |
| `ml-correctness-auditor`, the whole stage at the end | Fable · xhigh | the only Fable piece |

Every `Agent` call passes `model` and `effort` explicitly. Expected balance: Fable under 10% of the
remaining stage, Opus about 75%, Sonnet the rest.

## 4. How each minor step is checked
1. The agent runs its own files' tests and `ruff check` on them and reports the output (never the
   full suite, D-072 (m)).
2. The main thread reads the whole diff (`simplicity-review`), fixes or sends back once.
3. The combined review of §3's table; the ML audit once per major step; the findings fixed in
   one round per major step, every one fixed or justified.
4. The docs of the touched components updated in the same change (`CLAUDE.md` §8); `log.md`
   appended.
5. At a major step's end: the full suite in the background on the main thread; the review guide;
   the SDS's review; the fixes from it before the next major step starts.
6. The review guide lists the code to read, in order, and what right looks like. It names a test
   only when reading it matters, marked "read this test" (at most two per major step: the hold-out
   test in step 1, the trap acceptance test in step 3); the SDS reads code, not tests (2026-11-03).
   The notebooks' guide cells are listed as code to read.

## 5. Order and parallelism
1. m1.0 alone (it uses local Spark on the canonical window; one memory-heavy job at a time).
2. m1.1→m1.2 (one agent), m1.3, m1.4, m1.5 in parallel: disjoint files (m1.3's tests use Spark on
   the unit preset, small). m1.3 codes against `Time.validation_period: date | None` before m1.1
   lands; the integration run reconciles.
3. SDS review 1.
4. m2.1 and m2.2 in parallel; then m2.3; then m2.4.
5. SDS review 2.
6. m3.1 and m3.2's `decisions.py` in parallel; then m3.2's stage; then m3.3 and m3.4 in parallel;
   then m3.5.
7. SDS review 3; version 0.3.0.

## 6. What "done" means for Stage 2
- `pytest` green, the trap acceptance test included; `ruff check .` clean.
- `python -m core_modelling run conf/base/cc_acquisition.yml --stages eda feature_checks` writes
  `eda/`, `feature_checks/`, the ledger and both reports under `<root>/cc_acquisition/04_feature/
  <ddh>/`; the same for `td_acquisition.yml` and the regression variant in the tests.
- Notebooks 02 and 03 run end to end on the `dev` preset and import the Public API only.
- The synthetic traps: every mapped kind flagged on the `dev` preset's card config; the null
  controls unflagged; the look-ahead trap caught by `client_constant`.
- A `keep` entry recorded from notebook 03 brings the feature back into `resolve_features`.
- Notebooks 02 and 03 carry a guide cell before every step (what it does, what to look at, how to
  read the numbers, what to decide, how to record it, at both levels), and notebook 03 says in
  words that a held feature acts, for Training, as an excluded feature without a final decision.
- Every numeric candidate of the synthetic data is binned (the bin-count assertion, T25).
- The docs say "built" where it is built; D-134–D-137 unchanged or extended in place; `log.md`
  carries the trail; `sync.md` only through `/brief`.

## 7. Risks and fallbacks
- **The explode pass is slow on the Mac** (m1.0 measures): fallback a per-feature `groupBy` over a
  cached frame, the same table.
- **`Bucketizer` rejects singleton splits:** fallback `F.when` chains built from the edges.
- **A numeric lands in one bucket** (the symptom the SDS saw in earlier plot code: quantile edges
  collapse on a zero-inflated or discrete column, fixed-width edges on a skewed one): the edges
  rule (mass points as singleton bins, quantile edges over the rest; T25) is unit-tested on three
  constructed columns, m1.0 reports the bin-count distribution over every canonical numeric, and
  the acceptance test asserts it on the `dev` preset. If a real column still collapses, the rule
  iterates the mass-point extraction once more; a decision for the SDS if that is not enough.
- **The regression counts table is large** (20 target bins × 100 bins): read per feature with
  parquet filters; if still heavy, 10 target bins (a decision for the SDS).
- **The `dev` preset's generation time makes the suite slow:** mark `test_traps.py` with a pytest
  marker so the quick loop can skip it; the full suite keeps it.
- **JupyterLab blocks the report's scripts until "Trust HTML":** the notebook opens the report
  through an `IFrame` with `srcdoc` or tells the user to trust it (m1.0 decides).
- **Styler needs matplotlib for gradients:** use plain CSS classes (no new dependency).
- **The 200,000-row pairwise cap at 300 bank columns is still slow:** rank once then Pearson, the
  difference measured in m1.0.
- **`rare_value_leak` at 20 rows is noisy** (`feature_checks.md` open question): measured on the
  `dev` preset's null controls in m3.1; moved to events if it flags.

### 7a. What the facts spike settled (2026-11-03; details in `worknotes/log.md`)
- The explode pass is the design: 15–18 s on the canonical window (625,074 rows × 139 numerics →
  115,695 cells, 2.8 MB shuffle, 0.9 GB heap); the per-feature loop is 4.5× slower at the heap
  cap. The lag pass is 19 s; the wide `groupBy(unit_id)` spills 2.2 GB, so the client-constant
  shares run in column chunks or inside the lag window (T27).
- `Bucketizer`: singleton splits accepted, no casts; null is a null bucket, NaN the extra one
  (T26). The edges rule leaves no canonical numeric collapsed (39 of 139 columns under 50 bins,
  every one equal to its distinct count; the largest non-singleton bin 1.8%): the acceptance
  assertion is `bins ≥ min(distinct, 50)`, and `bins` is a target (up to +2).
- The table concordance equals the binned AUC to 1e-16 and the raw AUC within 0.0001; the
  regression τ-b is exact against binned rows and about 0.01 off raw (T32). Wilson closed form
  (20,000× faster than scipy); `lstsq` for `explained_by_others`.
- Spearman: the exact pairwise-complete form, columns grouped by null mask (T28); m1.4b measures
  the cost at 139 × 200,000.
- For m2.1: a repeated plotly `div_id` is not deduplicated (generate ids), a zero quartile on a
  log axis is clamped silently, a 20-bar fragment is 7.5 KB, plotly.js 4.8 MB once per report;
  `DataFrame.style` needs jinja2, which the venv lacks (the pin is asked of the SDS); a hand-written
  table with CSS classes is a third of a Styler table's size. JupyterLab's trust behaviour and
  the IFrame/`srcdoc` question stay unverified locally (m2.4 decides with `srcdoc`).
- For m1.5: parquet list columns read back as arrays, `datetime64` and NaN need explicit JSON
  handling (T31).

## 8. Timeline (estimate, working days)
- 11-03: the plan revised after the SDS's remarks; approval.
- 11-04: m1.0 (morning), m1.1–m1.5 spawned (afternoon).
- 11-05: integration, reviews, the full suite, review guide 1. SDS review 1 on 11-06 (morning).
- 11-06 to 11-09: m2.1–m2.4. SDS review 2 on 11-10 (morning).
- 11-10 to 11-11: m3.1–m3.5. SDS review 3 on 11-12.
- 11-13: buffer; M2.3 starts.

## 9. The holistic review's outcomes, and the decisions the spec step made (veto by number)
The review (Opus, fresh context, 2026-11-02; verdict "proceed with changes") found ten
contradictions between the freshly written docs, four knock-on effects on docs not updated, four
shape risks and four gaps. All are applied in the docs; the ones that needed a decision are listed
here for the SDS to veto by number, together with the decisions made while integrating the doc
writers' findings. Silence confirms them.
- **V1** The open flags' features enter the resolved config as `features.held` (beside `excluded`
  and `kept`, refused in a config file), so a `flag` entry changes the input and the run's
  resolved-input hash sees the held set; `resolve_features(ledger, resolved)` reads it there.
  Without it two Training runs with different held sets would share one hash (D-134 extended).
  **Confirmed by the SDS (2026-11-03)** with one condition, applied: the notebooks, the reports,
  Training's log and the docs say in words that, for Training, a held feature acts as an excluded
  feature without a final decision.
- **V2** The ranking value is the plain concordance unless the feature is marked `non_monotone`
  (best-order ≥ plain + max(0.03, 4 · SE); the fixed 0.03 alone marked 42% of null numerics at
  500 events, the SE-scaled margin 0–2% at every size while the inverted U stays marked, measured
  2026-11-03); only then the best-order value is used, and M2.3's floor follows
  the same rule. The review showed that "the larger of the two" would give every noise feature a
  small in-sample boost; the null controls now must not be marked `non_monotone` (D-135 refined).
- **V3** `eda.bins: null` gets a guard: the cell count is estimated from `approx_count_distinct`
  before the pass and more than 50 million cells fails loud naming `eda.bins`. With binning off the
  table is about rows × features (D-135 extended).
- **V4** The clusters are Feature Checks' table (`tables/clusters`), cut from EDA's `correlation`
  table at `redundancy.correlation_max`; `explained_by_others` is the multiple correlation from the
  correlation submatrix (a small ridge, so an exact identity reads 1), so no rows are needed.
- **V5** The pooled categorical bins are the reserved `__other__` and `__new__` (the encoder's
  `__other__` is the same idea; one glossary entry).
- **V6** The five steps run in a fixed order (quality, leakage, time_alignment, stability,
  redundancy) rather than in YAML order; a step is skipped by leaving it out of a present
  `feature_checks` mapping (Q488's wording changed; D-137).
- **V7** `concordance_unstable` stays a flag (the review proposed a note until the `unstable` trap
  exists in M4).
- **V8** The regression lift and rare effect are mean ratios computed only when the overall mean is
  positive; otherwise "not available: mean not positive", decided by the per-task spec before
  running (D-035, D-050).
- **V9** The latest period counts only when it lies after the validation period; without one the two
  latest-period notes read "not available: no period after the validation period".
- **V10** `pivot_target(result, rows, columns=None, where=None)` reads the frame, the task and the
  strata settings from the stage result; `render_decisions(ledger, resolved, entries)`;
  `SE_FLOOR = 0.005`; the lag is by period index and the window's first period has no lagged
  value; the ledger's `flags` column holds the flags the latest run raised (open or settled) and
  `key_feature` is `top_n | listed | ''`.
- **V11** The replayed field `features.kept_despite_flags` becomes `features.kept` with the
  operation's rename.
- **V12** Inside the bank one environment file serves one entity (the root names the entity's area);
  on the laptop one file may serve several entities under one root, kept apart by the hash (D-136).
- **V13** (2026-11-03) `psi_latest` compares the **window's last period**, not `eda.snapshot`, with
  the latest period. The SDS asked whether it checks the last training-window snapshot against the
  last data snapshot: yes by default, and now by rule, so setting `eda.snapshot` to an earlier
  period never changes the note's meaning (D-135).
- **V14** (2026-11-03) The edges rule: the mass points (values holding at least `1 / bins` of the
  rows; 0 and the dominant value when they reach it) are singleton bins and the quantile edges are
  taken over the remaining values, so no bin but a singleton holds more than about `2 / bins`;
  charts merge cells by cumulative row share and a mass point stays its own bar. This answers the
  SDS's `Bucketizer` question: the one-bucket symptom comes from quantile edges collapsing on ties
  (or fixed-width edges on skew), and the rule, three unit tests, the m1.0 measurement and the
  acceptance test's bin-count assertion close it (T25, D-135).
- **V15** (2026-11-03) Chart sampling stays out because no chart draws clients: every chart is
  drawn from cells or quartiles, so nothing needs sampling, while every statistic uses the whole
  population. Should a row-level chart ever be added, it draws a seeded sample of at most 10,000
  rows and says so in its caption (reporting requirement 5). The SDS's question ("why has chart
  sampling been left out") is answered by this, not by a config field.
- **V16** (2026-11-03; changed by the SDS's review 1, 2026-11-04) The level encoding is
  **cross-fitted by client fold**: a categorical's cells carry the client's fold (5, a hash of
  `unit_id`), each fold's levels are ordered by the encoding fitted on the other folds, and
  Somers' D sums the pairs inside each fold (`cross_fitted_concordance`). A30's "fitted once on
  the pooled window" reads a null 50-level code at 0.53–0.60; by period (the build's first fix)
  still 0.57 on a panel, since the other periods hold the same clients; by client fold 0.50. The
  window's SE counts effective clients (Kish, `TASK_SPECS[task]["client_support"]`), so the
  `non_monotone` margin holds on a panel too (D-135 changed in place).
- **V17** (2026-11-03) `explained_by_others` is computed over a cluster's Spearman members only and
  reads "not available" for a cluster with a not-compared pair, for non-numeric members, and when
  the pairwise-complete correlations are inconsistent (R² outside [0, 1]); the categorical level
  list is capped at 10,000 window levels, above which `new_levels` is "not available" for that
  feature; the edges are cut on the snapshot's eligible rows.
- **V18** (2026-11-04, major step 2) The views and the report's four parts live in a new
  `eda/report.py`, not in `run.py` (it would have passed 600 lines); `report.py` (≈450 lines,
  a view builder per section) and `run.py` (≈370, the orchestration) are kept whole as tied
  functions rather than split further.
- **V19** The ranking's snapshot columns (`concordance`, its SE, `direction`, the best order,
  `non_monotone`, `rank`) all come from the snapshot period's cells, the SE on its own rows (one
  per client): `is_non_monotone` gets plain, best order and SE from the same cells. eda.md had
  said "the window SE on effective clients" for the margin; the doc now follows the code.
- **V20** Target per period: the pooled `all` row's interval (both tasks) takes its support in
  effective clients, like every window SE (it was √periods too narrow). A regression mean's
  per-period t-interval comes from the cells' `sum_y2` since review 2 (Q498).
- **V21** EDA's settings digest gains `time.validation_period`: it decides which periods are gap
  and latest and is outside the data-definition hash, so a moved validation period forces an
  EDA rerun before Feature Checks reads the cells (the ML audit).
- **V22** Every collected frame is sorted by the keys (`collect_frame`, in Spark before the
  collect since review 2, Q516): Spark's collect order is not deterministic, so a seeded
  positional sample (the association cap) could differ between reruns (T34).
- **V23** Reference groups compare the rows a modelling tag excludes (tag = 0) with the eligible
  rows, label-free, with per-period sizes from the funnel; the tags get no target-by-stratum
  table (constant on the eligible rows); a categorical's "SMD" is its largest level-share gap.
- **V24** A categorical's `direction` is `+` when its cross-fitted value (in the encoding's
  order) reaches 0.5 + 2 SE, else null; its `concordance` may read below 0.5 (the order did not
  carry over), which the ledger doc now says. Its SE (like a flipped period's) is computed at
  `max(value, 1 − value)`: Hanley–McNeil is not symmetric.
- **V25** The regression deep dive is the lift chart (the t-interval in lift units), the group
  table (mean, interval, median, non-zero share) and the target's boxes per group; no separate
  bar chart of the mean, which would repeat the lift chart in currency units.
- **V26** The correlation heatmap always shows the key features and the candidates they
  represent (review 2, R25); the full association table is `tables/correlation`.
- **V27** Requirement 12: every strata check runs right after the snapshot is collected (one
  check since review 2, Q518): not a column or named like a framework column, a numeric stratum
  above `strata.max_levels`, an `include` that is not a candidate.
- **V28** Notebook 02 shows the views and the report's path, not the report inline (6 MB that
  the release example's outputs would carry twice); the report opens in a browser.

Review 2's build (2026-11-05, `review2_spec.md`) took these without the SDS:
- **V29** One label rule: `range_label` labels a run of buckets by its outer range, and
  `bin_labels` and `merge_bins` both go through it (the edges formatted once per feature, since
  `eda.bins: null` can mean many edges); every bucket reads `all`.
- **V30** Label numbers carry no thousands separator (`[1500, 2000)`: a comma inside a range
  reads like the bounds' separator) and an integral value prints whole; when two distinct values
  would read alike, even in two formats (`1e+06` beside `1000000`), the feature's labels fall back
  to exact text. The spec had separators (B2); the step's review found the collision.
- **V31** A merged group's label covers its occupied bins, so a bin empty at the snapshot lies in
  no label; `merge_bins(cells, groups, edges)` no longer reads `bin`.
- **V32** `zero_target_bins` is public; `ZERO_LABELS`' second probe uses non-integral edges, so
  the exact-text `= 0.0` still marks a regression target's zero bin.
- **V33** `side_by_side` refuses a subplot, a heatmap, a figure without the primitives' meta, and
  two figures that both show a legend; the grey note sits above the panel titles; panel titles
  are sized like a figure's title.
- **V34** A deep dive pairs the group chart with the first strata chart only; every further
  strata chart stands alone (one figure has one legend and one colour sequence, so two strata
  charts would mix their levels). The configs' two strata read [lift | segment], [channel].
- **V35** The how-to-read grey note names the task's support and the deep dive's threshold
  (`how_to_read(bins, estimate_noun, support_name, group_support)`); the lift note reads "2 twice
  the base" for both tasks.
- **V36** Bar text sits inside the bar at its base, clear of the error bar; the per-period table
  hides its `insufficient` column (the grey rows show it); the headline's values are bold.
- **V37** The exploration functions cut groups on the snapshot's eligible rows with the stage's
  edges and read every label statistic on the eligible rows with a known target, as the report.
- **V38** `rate_by_period` reads the window's labelled cells, grouped as the snapshot's deep
  dive; each numeric group is labelled by the buckets it receives across the window (the ML
  audit: a snapshot-only label read as drift), so it can read wider than the deep dive's; a
  categorical keeps the snapshot's `strata.max_levels` largest levels, the rest `__other__`;
  every group × period is drawn, a missing one as no point.
- **V39** Chart titles are short: "Target per period", "Lift by income", "income by segment",
  "income: concordance per period", "income by target class", "Association"; the detail moved
  to axis titles ("Concordance (window's direction)", "(log axis)") and captions; the deep
  dive's table caption quotes the ranking's `concordance`.
- **V40** The strata check matches names exactly: a framework name in another case is refused
  as "not a snapshot column" (its source column is read as `source_<Name>`).
- **V41** A key feature that is itself a stratum gets no strata chart or pivot against itself (a
  diagonal), found on the 100k report.
- **V42** `report.py` ends at about 476 lines (473 before the build) with the strata charts, the
  two-panel rows and four public chart builders; it stays one module of tied views.
- **V43** Notebook 02's step 7 examples use `income` (a key feature, not a trap) and
  `employment_status` (not a stratum): the top key features are the synthetic leak traps. Steps
  2, 4, 5 and 6 end with one "Decide:" line; the calls live in step 9. The inline-report recipe
  is gone (V28).
- **V44** The exploration functions cut groups by the deep dive's rules: a numeric through one
  group-count rule (`dive_group_count`: by level up to `strata.max_levels` values, else about
  ten); a categorical feature at `LEVEL_CAP` alone (like its level table) and at
  `strata.max_levels` with `by` (like the report's strata chart), the `by` column like a stratum;
  `rate_by_period` keeps `strata.max_levels` levels (one line each); `compare_sides` refuses a
  side without a finite value; `by` equal to the feature is refused.
- **V45** The deep-dive views read the stored tables per key feature (no parallel dict; "by
  level" means the feature is in `tables/levels`); the strata rows cut a numeric with the same
  group count as its group table.
- **V46** The simplicity passes cut `report.py` and `charts.py` by 15% and `run.py`,
  `deep_dives.py` and `population.py` by about 7%, short of the spec's ~20% there: the next cut
  (a numeric's groups from the rows instead of the cells) would break the one engine on the
  cells (D-135). Compact plotly calls sit under `# fmt: skip`, as `report.py` already did.
The stage-3 review's fix round (every finding confirmed by a second reader) added:
- **V47** The regression concordance's SE carries the target-tie factor √(1 − Σp³) / (1 − Σp²)
  over the target-bin shares, the 0.005 floor after it (D-082 amended): Somers' D drops pairs tied
  on the target, so on a 90%-zero target a null feature got a direction 44% of the time (5% now).
  The per-task `concordance_se` hook takes the shares (`cells.target_shares`, not the dense
  table); the feature's own ties stay out (errs wide, as Hanley–McNeil does).
- **V48** A label falls back to exact text also when rounding would put two bounds out of order;
  whole numbers print as integers below 1e15 only.
- **V49** The report is rendered before anything is removed or replaced and lands in `eda/` in
  the same rename as `eda.json` (`write_stage(..., texts)`; `write_report` became
  `render_report`): a render error leaves the previous `eda/` and ledger untouched.
- **V50** An axis from zero reaches below 0 when an estimate does (an amount target can be
  negative), and keeps a supported bar's interval bottom in view (chart rule 1).
- **V51** One colour per thing across the report: strata lines and pivot columns follow the
  stratum's level order, a `null` line or box takes the null colour, target-class colours only on
  boxes by target class; `side_by_side` takes a legend only on the right panel.
- **V52** The per-period concordance reads each period in the raw sign of the window's D
  (`raw_sign_window`, a new `tables/ranking` column: the window's direction where it has one, 0
  without a window concordance); with no direction it read every period ≥ 0.5, hiding a flip;
  every period unavailable reads "Not available" with the reasons.
- **V53** The group summary's columns are per task (`TASK_SPECS[task]["summary_columns"]`), so
  `tables/bins`, `levels` and `strata` keep the task's columns when empty.
- **V54** A modelling tag listed in `strata.variables` is refused; the association's seeded cap is
  one rule (`association.pairwise_sample`, `PAIRWISE_SEED`), drawn once in `run_eda`, and the
  timings' null-mask count reads that sample; `summarise_groups` refuses a summary whose columns
  differ from the task's list in either direction.
Review 3 and the gaps spec (2026-11-06; `eda_gaps_spec.md` V55–V65 as built, then V66 onwards):
- **V55** For a `top_n` decision `decision.n` joins the evaluation slices as the first slice (a
  listed twin is dropped); other decision types take the evaluation slices alone.
- **V56** The one-feature list order: a numeric by value in the snapshot's raw sign (`raw_sign`, a
  new `tables/ranking` column beside `raw_sign_window`); a categorical cross-fitted by client
  fold (the shrunk encoding fitted on the other folds, prior included, each fold cut at the share
  and the counts summed: the ML audit showed the spec's "other window periods" order lifting a
  null code to 1.3–1.6 on small populations); the null bin last. A one-period window works.
- **V57** Linear interpolation inside the boundary bin; the curve on a 1% grid with a `random`
  diagonal drawn dashed and muted; the capture axis stops at 100%.
- **V58** The slices view in Core between the ranking and the deep dives; it says it is in
  sample and descriptive, never a baseline (a model is judged against `decision.baselines`);
  capture and the curve are not available for a target that can be negative; skipped counts are
  named; the leak cue is "slices that capture far more than the other key features'".
- **V59** The value profile: one vectorised quantile call on finite values, top levels from the
  cells, not in the ledger; Extended, last; shown as two tables (numerics, categoricals) without
  the constant `rows` column.
- **V60** Two small modules, `eda/slices.py` and `eda/profile.py`.
- **V61** The join entries carry `columns`; the model input's sidecar at schema 4 and the ledger
  at schema 2, older files refused naming their writer and the fix; the frames' meta key is
  `column_sources` (`sources` already names the join definition).
- **V62** The sources table runs over the compared periods with `all`; a column found in a
  feature source and the target source maps to the feature source; a lineage column of an
  upstream target may have no source.
- **V63** Target Factory reports the occurrences per period instead of the offset distribution,
  `run_target_factory` returns `TargetSummary`; the outcome columns stop at the window's last + w
  (the ML audit: later ones are later labels', the validation period's among them); the first
  period's conversions are null (unknowable); an upstream target has none.
- **V64** The two histogram sentences are deleted; chart rule 8 is unchanged.
- **V65** `grouped_lines` gains `x_numeric` rather than a sixth chart primitive.
- **V66** Target Factory's summary fills the label columns for every period up to the window's
  last (the earlier periods included), null after it; the `all` row over the window (R31: "every
  period but the last w" would have shown the gap periods, whose target windows reach the
  validation period's outcomes).
- **V67** The collect printout names the budget only when a frame is above it; the notebooks
  carry no machine-specific numbers (R32).
- **V68** Notebook 02's step 3 holds the how-to-read notes as text and no longer displays the
  view (R33); the report keeps `blocks.how_to_read`, so the wording lives in two places.
- **V69** A numeric reads its values (`0`, `1`, `2`) only when every group is one value; a mass
  point among ranges keeps `= v`; `rate_by_period` labels a group by the occupied buckets it
  receives; `pivot_target`'s few-valued numeric dimensions follow (R34).
- **V70** The correlation heatmap shows the key features only; the candidates each represents
  sit in a short table beneath, with the signed association, in rank order (R37).
- **V71** Rate axes follow `TASK_SPECS[task]["axis_format"]` (binary `.1%`), the hover too, so a
  hover reads 2.9% where the table reads 2.93%; lift and concordance axes stay plain (Q523).
- **V72** A line chart counts its values only up to twice its highest supported point (the 1.25
  headroom on top), the SDS's rule of review 4 (R41) replacing Q524's supported points only;
  bars keep a greyed bar's height in range.
- **V73** Report value columns print large numbers with thousands separators, never scientific
  notation; a regression estimate (an amount) prints with two decimals (`{:,.2f}`).
- **V74** (2026-11-06, major step 3) `leakage.rare_value_leak` follows the rule the SDS approved
  (Q441, A28), not the spec text that had drifted to "a cell below 1% of the window's rows": one
  filled value on at least 90% of the filled window rows, the other values pooled as the minority,
  its rate (mean) against the dominant value's at least `rare_effect_max`, with `strata.min_events`
  effective events in the minority. Measured on the canonical data: the drifted rule held 51
  legitimate top quantile bins and missed the process leak (T35); the approved rule catches the
  card process leak (37×), the shifted column (57×) and the upstream target (inf) and holds four
  legitimate minorities (`segment` 7.9×, three travel-spend aggregates 5.6–6.2×), which a person
  keeps once. `near_constant`'s detail shows the same minority effect (Q440).
- **V75** (the support guards replaced 2026-11-09 by the SDS's Q540) No check skips for support;
  a finding with an SE states its support in effective clients (`client_support` on `eda.json`'s
  `clients`) and its SE, "not significant at this support" within 2 SE of its threshold; EDA
  stores no window SE, so `measures.effective_se` recomputes it as EDA's ranking does. Known
  limits: a best-order `too_strong` uses the plain SE (no selection gain), `signal_kept`'s SE
  leaves out the window's own noise. Below EDA's null-share range
  (0.5%), Feature Checks reads the null concordance itself from the same cells, so a field blanked
  on conversion at a low prevalence is still flagged `missingness_leak` (the whole-stage audit).
- **V76** The lagged pool leaves out the window's first period, whose lagged cells are null by
  construction (the "no lagged value" share read 18.6% instead of 2.4%).
- **V77** Feature Checks also reads `tables/ranking` (`raw_sign_window`, the window's direction for
  the per-period and lagged concordances): the ledger's `direction` is the snapshot's and null
  below 2 SE.
- **V78** The finding table is plain data (`feature_checks/findings.py`); a finding's text names no
  threshold (the findings' `threshold` column carries it), so a `flag` entry's reason is the text
  and does not move with a threshold; finding names are part of the audit-log format (§2).
- **V79** The findings table gains `detail` (the dominant value and both rates, a pair's partners,
  the share without a lagged value, the periods tested); the stage saves an `unavailable` table
  (feature, finding, "not available" or "not tested" with the reason, decided up front, D-035).
- **V80** Two modules beyond the plan's list: `measures.py` (the numbers EDA does not store: the
  lagged concordance, PSI between two periods, the per-period table) and `report.py` (as EDA's,
  V18); `steps.py` stays one module (about 700 lines: the five steps share the inputs and the row
  builders, and the finding table reads top to bottom in it).
- **V81** A step is `check_<step>(inputs: CheckInputs, params) -> StepResult(findings, columns,
  unavailable, tables)`; `check_inputs` builds the inputs once, the per-period table included.
- **V82** A cluster lists its members by the snapshot `concordance` (the association is measured
  on the snapshot).
- **V83** A skipped step's ledger columns are written as null, so readers always find the column
  set (Training reads `cluster`).
- **V84** The `run` entry carries the `replayed_to` and resolved-input hash of the config the run
  read; the result's config is resolved again after the run's entries (the held set Training
  sees).
- **V85** Feature Checks' settings digest covers EDA's paths plus `feature_checks`
  (`FEATURE_CHECKS_SETTINGS`), in `feature_checks.json` and the ledger's sidecar, for Training to
  check.
- **V86** The table formats moved to `reporting/formats.py` (`plain_number`, `p_value`,
  `column_formats`), not into `html.py`: one concept shared by both reports (an EDA file touched:
  `eda/report.py` imports them, a mechanical move).
- **V87** The per-task spec's `rare_effect(minority, dominant, sizes) -> (effect, se)` is Cohen's h
  (binary) or Cohen's d (regression, the pooled SD from `sum_y2`, "no spread" below 1e-12 of the
  mean square), with `rare_effect_unavailable` and `rare_effect_name` (D-050; the SDS's Q539).
- **V88** The time-alignment gate is `concordance_window ≥ concordance_min` and above 0.5, since a
  `concordance_min` of 0.5 would divide by zero.
- **V89** A run refuses while the log holds an open flag of a finding this version does not know,
  before writing, until a person settles it or a log migration renames it; and refuses a ledger
  whose `concordance_window` differs from `eda/`'s ranking (two EDA runs after a crash and a
  reverted setting).
- **V90** The proposed decisions' call texts carry `env_path=ENVIRONMENT` beside `CONFIG`, like
  notebook 02's, so a copied call writes to the log the notebook reads; notebook 03's walk-through
  ends with a `revert_to`, so its demo entries leave nothing in force and the notebook reruns.
- **V91** The trap acceptance test's false-positive check is the null controls (pure noise, never
  flagged); no bound counts the held non-trap candidates (the SDS, R55: an earlier V7 had added
  one, which Q534 wrongly called the SDS's). Drift is asserted as the flag `psi_latest_large` on
  the login column or one of its roll-ups; collinearity as the status ⇔ flag identity.
- **V92** (2026-11-09, review 1) The PSI tiers (R49): the notes `psi_window` and `psi_latest` from
  `stability.psi_note_min` (0.10), the flags `psi_window_large` and `psi_latest_large` from
  `stability.psi_max` (its default moved from 0.10 to 0.25), exclusive, so a feature raises one;
  the example configs take the defaults (`stability: {}`).
- **V93** The held table's `flag_values` is keyed by each finding's `measure`, a new field of the
  finding table (the name of what `value` holds); a view, not a stored table.
- **V94** The proposed exclude call names its finding in `evidence` (a keep names it in
  `findings`, which scopes it); the calls' header says each call takes any subset (R52).
- **V95** The cluster summary (R51) reads the stored `tables/clusters`, which keeps one row per
  member for Training: per cluster its size, the lowest association with the best member and the
  highest `explained_by_others`; the per-member columns join the redundancy feature table, and the
  report's extended "Redundancy clusters" section is gone.
- **V96** A table's caption is styled inside its Styler (both reports, both notebooks), and the
  report's third- and fourth-level headings are larger (R43).
- **V97** Notebook 03 loads the frames in step 1 (`build_frames` on `result.config`, the resolved
  config, so the rows are the data definition the run judged) and shows three checks in a new step
  8; the decisions move to step 9 and the report to 10; the walk-through splits `client_constant`
  (keeps the three static attributes, excludes the look-ahead column) and still reverts both.
- **V98** (2026-11-09, review 1's answers) Three existing readers become Public API as they are,
  for the helper notebook `00_eda_fc_helper` (R57): `environment.feature_dir`,
  `artifacts.read_stage`, `ledger.read_ledger`; the notebook runs nothing and writes nothing.
- **V99** A null set (Q543) is the `nulls_informative` features with the same null counts in
  every window period and target bin, numbered by size; grouped among the firing features only
  (identical null rows give an identical null concordance, so the grouping is the same).
- **V100** EDA's `concordance_per_period` (Q542) is computed after the ranking from the cells it
  holds, timed as its own phase; the key features' per-period dive reads its rows, so nothing is
  computed twice; Feature Checks refuses an EDA without it or without
  `concordance_best_order_window` (Q541), naming what is missing.
- **V101** The evidence phrase (Q540): "support N effective <events>, SE x", then "; not
  significant at this support" unless the value is more than 2 SE past its threshold; the window,
  null-indicator and lagged SEs come from `measures.effective_se`, EDA's formula repeated
  (`client_support`, the task's SE at max(v, 1 − v), a categorical's × 1.5). A best-order
  `too_strong` takes the SE at its own value, so its "significant" overstates a little (the best
  order gains about 2 SE on noise).
- **V102** `concordance_best_order_window` lives in `tables/ranking` only (not the ledger, not
  the ranking view); Feature Checks' `tables/per_period` is label-free (PSI per compared period),
  and its stability chart reads EDA's `concordance_per_period` (Q542).
- **V103** (the ML audit of the answers) Cochran's Q weights each period by the SE at the window's
  concordance on the period's own rows (EDA's per-period `se` sits at the period's own value and
  collapses to its floor on a thin period near 0 or 1: 3–4% false `concordance_unstable` in
  simulation); "not significant" is judged with the SE at the threshold (0.5 for a flip), a
  best-order `too_strong` needs 4 SE (EDA's non-monotone margin); a null set's key is every
  current null cell of the compared periods. Not built: a floor on the relative range (the SDS's
  call: as the signal nears 0.5, Cochran's Q alone decides).
Applied without a decision: `environment.md`'s paths and functions, `architecture.md` §4, §9, §10
and the stage table, `evaluation.md`'s support rule (`strata.min_events`) and OD-12 scope,
`monitoring.md`'s PSI pointer, `training.md`'s signature and the train-only ranking inside a
cluster, the OD-06 row, `config.md`'s three `flag` places and the replay table's hash, the
`clusters` table in Feature Checks' artifact list and out of the EDA report, the how-to-read owner
(`reporting.md`), the population counts per compared period, the unplaced loan-target trap kinds
in `NOT_CHECKS`, the inverted-U unit test on a synthetic column, the snapshot callout's note that a
smaller population changes the hash, `run_feature_checks` keeping `spark` for the one stage shape.
Routed to the build's reviews: the best-order optimism and the train-only cluster ranking to the
`ml-correctness-auditor` (m1.4, m2.2); the in-place schema and path changes to the
`compat-guardian` (m1.1, m1.2).
