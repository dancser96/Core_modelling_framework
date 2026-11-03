# Stage 2 (M2.2 Understanding): the build plan
_Written 2026-11-02 for the SDS's approval, revised 2026-11-03 after their remarks (the routing
budget, the notebooks' guides, `lagged_signal_drop`, the edges rule, V13–V15) · from the spec in `docs/components/eda.md`,
`feature_checks.md`, `feature_ledger.md`, `reporting.md`, `config.md`, `dataset.md` and the decision
rows D-134–D-137 · the design record is `answers.md` beside this file · nothing is coded before the
SDS approves this plan (`CLAUDE.md` §1 step 1) · the holistic review's outcomes are folded in (§9, with the
decisions the spec step made without the SDS, V1–V15, to veto by number)_

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
  `audit_log_dir` → `<root>/<use_case>/04_feature/<ddh>/decisions`; `stage_dir(env, cfg, entity,
  stage) -> str`.
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
  categoricals) -> dict[str, list[str]]`; `count_cells(rows, edges, levels, target_edges,
  window_periods) -> pd.DataFrame`; `count_lagged_cells(rows, edges, levels, target_edges,
  window_periods) -> pd.DataFrame` (lag by period index); `client_constant_shares(rows, features,
  window_periods) -> pd.DataFrame`; `population_counts(panel, cfg) -> pd.DataFrame` (per compared
  period; the labelled counts inside the window only); `estimate_cells(rows, kinds, bins) -> int`
  (`approx_count_distinct` per column; with `eda.bins: null` more than `MAX_CELLS = 50_000_000` fails
  loud naming `eda.bins`). The pooled categorical bins are the reserved `__other__` and `__new__`.
- Tests (unit preset, real local Spark): the cells equal a pandas `groupby` on the collected
  rows for three features and two periods; the cell estimate refuses a planted `MAX_CELLS` of 10; no label outside the window and no validation row in
  `rows`; `eda.bins: null` gives one cell per distinct value; the lagged cells null for the first
  window period and for a missing previous period; the client-constant share of a static column
  is 1; the population counts equal Target Factory's summary where both exist; `Bucketizer` on
  the edges of a 90%-zero column gives the zero bin plus at least `bins / 2` non-empty bins.
- Leaves out: any statistic (m1.4).

**m1.4 ∥ The statistics engine and the regression entries** · `general-purpose` · Fable · xhigh
- Owns: new `src/core_modelling/statistics/` (`cells.py`, `concordance.py`, `distributions.py`,
  `intervals.py`, `association.py`), `tasks.py` (the new entries), new `tests/test_statistics.py`,
  `tests/test_target_factory.py` only where the spec's keys change.
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
  rare effect read "not available: mean not positive", D-035). `ranking_value(plain, best_order) ->
  float` returns the best-order value only when it beats the plain one by 0.03 (`non_monotone`).
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
  `lift_chart(...)`, `box_from_quartiles(df, ...)`, `per_period_lines(df, ...)`, `heatmap(matrix,
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
  view, no config for the loan target, off by default), the rule that an unlisted pair fails; the
  false-positive bound: at most two non-trap candidates held on the card config, named on failure; assertions on the `*_window` ledger columns; the null
  controls below 0.55; the D-088 counts compared from `eda.json`; the term-deposit config without
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

## 3. The routing table (D-072 (l), extended 2026-11-03)
Fable keeps what needs the whole picture and the pieces whose architecture is hardest to get right
the first time: this plan, each brief, reading every diff and test output, the integration fixes,
the `ml-correctness-auditor`, the review guides, the log entries, the reports to the SDS, and four
code pieces (the counts passes, the statistics engine, the two stage functions that integrate
everything). The SDS's budget (2026-11-03): Fable between a third and half of the stage's tokens,
spent on architecting properly rather than on rewrites; `xhigh` effort on every model wherever a
wrong answer is costly. A Sonnet piece that fails once is escalated to Opus, never retried on the
same model. Fable agents are spawned as `general-purpose` with `model: fable`, never as forks: a
fresh context reads the brief and the docs, not this chat.

| Piece | Agent type | Model · effort | Why |
|---|---|---|---|
| m1.0 the facts spike | `general-purpose` | Sonnet · high | one fact per item against the pinned version; a number or a test checks each |
| m1.1 + m1.2 the schema and the audit log | `general-purpose` | Opus · xhigh | a §2 surface and the held set that feeds §4.6, fully specified; compat-guardian reviews it |
| m1.3 the frames and counts passes | `general-purpose` | Fable · xhigh | the Spark architecture the whole stage stands on (two passes, the edges rule, the lag by period index): the piece a rewrite would cost most |
| m1.4 the statistics engine and the regression entries | `general-purpose` | Fable · xhigh | the numbers every later stage trusts; the cell algebra and the shrunk encoding are design as much as code |
| m1.5 the artifacts and the ledger | `general-purpose` | Opus · xhigh | IO and the hold-out read (§4.6), fully specified; silent-failure-hunter reviews it |
| m2.1 the reporting primitives | `general-purpose` | Sonnet · high | a complete brief with signatures; not a §4 path; code-reviewer on Opus checks it |
| m2.2 the EDA modules | `general-purpose` | Opus · xhigh | the ranking and the key features feed choices (D-030); specified column by column |
| m2.3 the EDA stage, report and `run` | `general-purpose` | Fable · xhigh | integrates frames, counts, statistics, ledger, artifacts and reporting: the whole picture |
| m2.4, m3.4 the notebooks | `general-purpose` | Opus · xhigh | the guide cells are the notebooks' main deliverable (the SDS, 2026-11-03); Fable reads every guide line in the integration |
| m3.1 the five steps | `general-purpose` | Opus · xhigh | §4.6: what gets flagged; the rules are a table |
| m3.2 the decisions and the stage | `general-purpose` | Fable · xhigh | the hold-out mechanics (flag entries, the held set, the hash) and the stage integration |
| m3.3 the trap acceptance test | `general-purpose` | Opus · xhigh | a §4 invariant test from a given mapping |
| m3.5 the doc propagation | `general-purpose` | Sonnet · high | text whose substance is settled |
| `code-reviewer` (every minor step) | that agent | Opus · xhigh on the §4 paths (m1.1–m1.5, m2.2, m2.3, m3.1–m3.3), high elsewhere | fresh-context review |
| `silent-failure-hunter` (m1.2, m1.3, m1.5, m2.3, m3.2) | that agent | Opus · xhigh | IO, validation, fallbacks |
| `compat-guardian` (m1.1, m1.2, m1.5, m2.3, m3.2, m3.5) | that agent | Opus · high | schema, artifacts, Public API |
| `ml-correctness-auditor` (m1.3, m1.4, m2.2, m2.3, m3.1, m3.2, m3.3; the whole stage at the end) | that agent | Fable · xhigh | the review Fable keeps (D-072 (l)) |
| `simplicity-review` on every diff | skill, main thread | Fable | reading the diff is the integration anyway |
| the briefs, the integration, the review guides, the SDS reports | main thread | Fable | needs the whole picture |

Every `Agent` call passes `model` and `effort` explicitly. Expected balance: Fable about 40% of
the stage's tokens (the main thread, the four code pieces, the audits), Opus about 45%, Sonnet the
rest. If Fable's share runs ahead of a half after major step 1, m3.2 moves to Opus · xhigh.

## 4. How each minor step is checked
1. The agent runs its own files' tests and `ruff check` on them and reports the output (never the
   full suite, D-072 (m)).
2. The main thread reads the whole diff (`simplicity-review`), fixes or sends back once.
3. `code-reviewer`, plus `silent-failure-hunter`, `compat-guardian` and `ml-correctness-auditor`
   where §3's table says so, in one message; every finding fixed or justified in `log.md`.
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
  (best-order ≥ plain + 0.03); only then the best-order value is used, and M2.3's floor follows
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
  exists in M4); instead the acceptance test gains a false-positive bound: at most two non-trap
  candidates may be held on the `dev` card config, named on failure, so the flag is checked against
  legitimate features too.
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
