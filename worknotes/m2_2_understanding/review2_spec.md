# Review 2 of major step 2: the build spec (the EDA report, notebook 02, the exploration functions)
_Status: approved design, 2026-11-05 (the SDS's remarks R10–R28 and the answers to Q501–Q522 in
`answers.md`). Written for an Opus implementer who starts with no context beyond `CLAUDE.md`. The
build is stage 2 of the SDS's review; stage 3 is a comprehensive review of the whole major step 2
code (§4). Decisions the implementer has to make on the way are numbered V29 onwards in `plan.md`
§9, for the SDS to veto._

## 0. How to work
1. Read first: this file whole; `docs/components/eda.md` (Levels 1–2, then "The views",
   "Interface", "Code map"); `docs/components/reporting.md` ("Chart rules", "The chart
   primitives", "Code map"); `notebooks/README.md`; then each step's modules before touching them.
2. Rules that bind here: `CLAUDE.md` §1 (code-light; functions ≤ ~50 lines; a docstring and type
   hints on every function, private ones included, checked by `tests/test_code_rules.py`), §7
   (lean tests: one assertion set per behaviour, real local Spark, no mocks), §8 (docs in the same
   change), §9 (never commit; no new dependency); D-035 (whatever cannot be drawn or computed is
   decided before drawing, never caught); D-050 (every task-specific choice goes through
   `TASK_SPECS`, never an `if task == "binary"` in a view).
3. Minor steps A–G (§3). A, B and C touch disjoint files and run in parallel (three builders); D
   needs A–C; E needs D; F and G need D and E. After each step: the tests of the touched modules
   and `ruff check` on the touched files, then the `code-reviewer` subagent plus the
   `simplicity-review` skill; fix or justify every finding in the step report. The full suite
   (`pytest`, about 10 minutes) runs once at the end, on the main thread in the background, never
   from a subagent (D-072 (m)) and never while a notebook runs: the dev machine runs one Spark job
   at a time.
4. Verify library behaviour on the pinned versions before relying on it (plotly 6.3.1 bundling
   plotly.js 3.1.1, pandas 2.2.3, PySpark 3.4.3): §5 lists what to check first.
5. The step report, every time: what changed, the tests run and their result, the reviewer's
   findings and what was done with each, open risks. The final report adds the token split per
   model.

## 1. Goal and scope
The SDS reviewed major step 2 through notebook 02. The statistics, the stage's flow, the artifacts'
schemas (`eda.json`, the ledger) and the config stay. What changes:
- how the report and the notebook are organised: how-to-read up front, a three-column choices
  table, the deep dives as rows of paired charts that include the key features against the
  strata, the correlation overview on the key features;
- what tables show: fewer standard errors and intervals, a lean ranking view with the bar on the
  value the table is ordered by;
- how charts and tables look: centred short titles, axis titles, nothing clipped, readable in a
  dark and a light notebook, range labels on merged bins;
- three exploration functions beside `pivot_target`, in a new module;
- the guide text of notebooks 01 and 02, and both notebooks run on the 100k synthetic dataset;
- four small fixes: the collected frames sorted in Spark, the cells' sum of squares for a
  regression mean's interval, the strata-name check folded, the encoding prior renamed;
- then a simplicity pass over the stage modules.

Left out, deliberately: Feature Checks (major step 3); any new dependency; a plotly template change
(`simple_white` was declined, Q512: "keep it simple, just better organized"); row-level charts; the
theme file from `conf/local/` (M4); Target Factory's two modes (Q521: both stay); the ledger's
columns and `eda.json`'s keys; intervals on the strata charts; an inline report in the notebook
(V28 holds); the Feature Checks report (it reuses the primitives when it is built).

## 2. The target state

### 2.1 The report (`report.html`), four parts in this order
1. **Summary:** Choices (columns Choice, Value, Alternatives) → How to read (five short
   paragraphs) → Headline → Warnings.
2. **Core:** Funnel per window period → Target per period (table with `low`/`high`; chart) →
   Target by stratum (table with `low`/`high`; chart) → Univariate ranking (the lean view, then
   Excluded automatically) → Key features (one subsection per key feature in rank order, §2.3).
3. **Extended:** Reference groups → Correlation overview.
4. **Appendix:** Kinds, Feature ledger, Resolved config, Decisions, Collect log, Timings.

Gone from where they were: "How to read" (now in the summary), "Strata pivots" (now inside each
deep dive).

### 2.2 Notebook 02
Steps: 1 Run EDA · 2 The choices · 3 How to read, the headline, the warnings · 4 The population
and the target · 5 The ranking · 6 The key features · 7 Your own views (`pivot_target`,
`lift_by_group`, `compare_sides`, `rate_by_period`, one example each) · 8 The report file (and
what the report holds that the notebook does not show: the reference groups, the correlation
overview, the appendix) · 9 What to decide and how to record it. The notebook displays
`result.views` and never assembles a report.

### 2.3 One deep dive (per key feature, in the report and in step 6 of the notebook)
1. The group table, only for a categorical, a numeric with at most `strata.max_levels` distinct
   values (`by_level`), or an amount target: columns `group, rows, support, estimate, lift`, plus
   `median` and `nonzero_share` for regression. No `low`/`high` (Q505).
2. Chart rows. A row of two charts is one figure with two panels (`side_by_side`, step C5); a
   lone chart is a plain figure:
   - `charts = [group chart] + [one strata chart per strata.variables, in config order]`, paired
     in order two per row, the odd last one alone; the group chart is the lift chart, or the
     estimate's bars when no lift exists (a non-positive base, decided up front as today);
   - then a numeric's boxes by target class beside the per-period concordance; a categorical's
     per-period concordance alone;
   - regression: the target's boxes per group, alone, full width.
3. The pivot tables, one per stratum variable: the feature's groups down, the stratum's levels
   across, the estimate coloured by lift, insufficient cells greyed (kept per Q509: "the styled
   pivots display numbers much better than the hover").

### 2.4 The look (Q512: simple, better organised; Q513: readable on both backgrounds)
- Every chart: a short centred title (the feature or view name; details go to axis titles and
  captions), an explicit x title and y title, `automargin` on both axes, bar text placed by
  plotly so it is never clipped, category x axes padded half a slot at both ends, the "grey =
  insufficient support" note top-right as today.
- Figures keep a white background (a white card in a dark notebook): plotly cannot follow the
  page's text colour, and the report page is white.
- Tables: the in-cell bar and the lift colours are translucent, so dark text on a light page and
  light text on a dark page both read.

## 3. Minor steps

### Step A: the data layer (the cells' sum of squares, the Spark sort, the task spec)
Files: `src/core_modelling/dataset/counts.py`, `dataset/frames.py`, `statistics/cells.py`,
`tasks.py`, `eda/population.py` (`target_per_period` only); tests `tests/test_counts.py`,
`tests/test_frames.py`, `tests/test_statistics.py`, `tests/test_eda_modules.py`
(`test_target_per_period_pools_the_window`, `test_a_regression_target_runs_through_the_same_tables`).

- A1. `counts.py`: `CELL_COLUMNS` gains `"sum_y2"` right after `"sum_y"`. In `_aggregate_cells`
  the `.agg(...)` adds `F.sum(F.col("target").cast("double") * F.col("target").cast("double"))
  .alias("sum_y2")` (null where the target is null, like `sum_y`). `_label_cells` already orders
  by `CELL_COLUMNS`; both passes use `_aggregate_cells`. The module docstring names the column.
- A2. `statistics/cells.py` `pool_periods` sums `["n", "sum_y", "sum_y2"]` (`min_count=1`);
  its docstring lists `sum_y2`. No other function in `cells.py` reads it.
- A3. `tasks.py`:
  - `period_estimate` takes `(known, positive_rows, sum_y, sum_y2)` for both tasks. Binary:
    unchanged but for the argument. Regression: `estimate = sum_y / known`; where `known >= 2`,
    `variance = max((sum_y2 - sum_y**2 / known) / (known - 1), 0)` and `low, high =
    t_interval(estimate, sqrt(variance), known)` (`t_interval` refuses `n < 2`: compute on the
    mask, NaN elsewhere); `nonzero_share`, `nonzero_low`, `nonzero_high` stay.
  - Delete the `period_interval` entries and every reader (step D removes the report's branch).
  - Add `"estimate_noun"`: binary `"rate"`, regression `"mean"`. It gives the y titles ("Target
    rate", "Target mean") and the how-to-read wording; step D removes `report.py`'s `TARGET`.
- A4. `population.py` `target_per_period`: `sums` groups `["n", "sum_y", "sum_y2"]`; the table
  carries `sum_y2`; the `all` row sums it; the effective-client scale applies to all four
  arrays (`rows, positive_rows, sum_y, sum_y2`); `period_estimate(*arrays)`; both sum columns
  dropped before `assign`. Docstring: regression's mean comes with its t-interval from the cells'
  sum of squares, the pooled row's on effective clients.
- A5. `frames.py` `collect_frame`: `collected = frame.orderBy("unit_id", "period").toPandas()`
  (no pandas sort, so no second copy at the peak); the comment keeps T34's reason.
- A6. Tests: `test_cells_equal_a_pandas_groupby_on_the_collected_rows` also checks `sum_y2`
  (binary: equal to `sum_y`); `test_pool_periods_and_shares` covers `sum_y2`; the regression
  test in `test_eda_modules.py` asserts `low < estimate < high` on the regression's target per
  period and NaN only where `rows < 2`; `test_binary_group_summary_and_the_task_entries` checks
  `estimate_noun` and that `period_interval` is gone;
  `test_collected_snapshot_is_sorted_by_the_keys_with_a_fresh_index` stays green unchanged.

### Step B: range labels (Q511)
Files: `statistics/distributions.py`, `eda/deep_dives.py` (the callers of `merge_bins`);
tests `tests/test_statistics.py`, `tests/test_eda_modules.py::test_bin_table_groups_match_the_merged_cells`.

- B1. `range_label(edges: np.ndarray, first: int, last: int) -> str`: the label of buckets
  `first..last` (0-based over `[-inf, *edges, inf]`): lower = `edges[first - 1]` or −inf, upper
  = `edges[last]` or +inf. A singleton is detected as `bin_labels` does today (`edges[i] ==
  np.nextafter(edges[i - 1], np.inf)` closes the singleton `edges[i - 1]` opens). Cases: one
  singleton bucket → `= v`; lower −inf → `< upper`, or `≤ v` when the last bucket is v's
  singleton; upper +inf → `≥ lower`, or `> v` when the first bucket is the one just above v's
  singleton; otherwise `[lower, upper)`, written `[lower, v]` when the last bucket is v's
  singleton and `(v, upper)` when the first bucket follows v's singleton. `bin_labels(edges)`
  becomes `[range_label(edges, i, i) for i in range(edges.size + 1)]` (one implementation; the
  single-bucket labels stay exactly as today, which the existing tests check; no edges → `["all"]`).
- B2. `_format_numbers`: an integral value prints `f"{int(x):,}"`, any other `f"{x:,.6g}"`; the
  collision fallback (`repr`) stays.
- B3. `merge_bins(cells, groups, edges: np.ndarray | None)`: a group's `label` is
  `range_label(edges, bin_order_first, bin_order_last)`; `edges` None or empty → `"all"`. The
  `first`/`last` join goes. `deep_dives._merged(per_bin, groups, edges)` passes the edges;
  `_numeric_groups` and `bin_table` pass theirs. Docstrings: "a group's label is its outer range".
- B4. Tests: on constructed edges, three merged singletons 13, 14, 15 read `[13, 15]`; the run
  `[374, 379.51) … [415, 419)` reads `[374, 419)`; the lowest group `< 50`; the highest `≥ 900`;
  a group ending in the zero singleton `[-5, 0]`; a group starting above it `(0, 7)`.
  `test_bin_table_groups_match_the_merged_cells` follows the new labels.

### Step C: the reporting primitives and blocks
Files: `reporting/theme.py`, `reporting/charts.py`, `reporting/blocks.py`; tests
`tests/test_reporting.py`.

- C1. `theme.py`: `"bar": "rgba(47, 111, 159, 0.45)"` (Q513). The lift colours are already
  translucent (`MAX_LIFT_COLOUR` 0.55): unchanged.
- C2. `charts.py` `_apply_theme(fig, title, x_title, y_title, height)`: the title centred
  (`x: 0.5, xanchor: "center"`); margins `l=70, r=40, t=70, b=70`; `automargin=True` on both
  axes. Every primitive gains `x_title: str = ""` after `title` and passes it. `_interval_bars`:
  bar text `textposition="auto"` (plotly puts it inside when it fits), no `cliponaxis=False`;
  `tickangle=-30` when any category label has more than 12 characters. Every primitive sets
  `fig.layout.meta = {"reference": <the reference or None>, "insufficient": <bool: any greyed
  element>}` so `side_by_side` can rebuild the reference line and the note.
- C3. `lift_chart`'s default `y_title` becomes `"Lift vs base rate (1 = base)"`.
- C4. `per_period_lines` is renamed `grouped_lines(df, x, y, group=None, low=None, high=None,
  support=None, insufficient="insufficient", reference=None, from_zero=True, title="",
  x_title="", y_title="", support_title="Support", legend_title=None)`: lines over an ordered
  category axis (periods, or a feature's groups), one per `group`; the axis order is the data's
  order (`categoryorder="array"`, `categoryarray=list(pd.unique(labels))`), padded with
  `range=[-0.5, n - 0.5]`; `legend_title` on the legend; `_period_labels` becomes `_axis_labels`
  (a datetime column as `%Y-%m-%d`, anything else as text). Behaviour otherwise unchanged
  (support bars for a single line only; a NaN shows no point).
- C5. `side_by_side(left: go.Figure, right: go.Figure, height: int = 380) -> go.Figure`: two
  primitives' figures as one figure with two panels. `make_subplots(rows=1, cols=2,
  specs=[[{"secondary_y": a}, {"secondary_y": b}]], subplot_titles=(left's title, right's
  title), horizontal_spacing=0.1)` where `a`, `b` are true when any trace of that source has
  `yaxis == "y2"`; `_apply_theme(fig, "", "", "", height)` first (it titles every axis); then per
  panel: `fig.add_trace(trace, row=1, col=col, secondary_y=(trace.yaxis == "y2"))` for each
  trace; the source's `xaxis`, `yaxis` and, when present, `yaxis2` settings copied through
  `to_plotly_json()` minus `anchor`, `domain`, `overlaying`, `side`, `position`, applied with
  `update_xaxes` / `update_yaxes(..., row=1, col=col[, secondary_y=True])`; the reference line
  re-added from `source.layout.meta["reference"]` with `fig.add_hline(y=…, line_dash="dash",
  line_color=THEME["muted"], row=1, col=col)`; one `_note_insufficient` when either meta says so;
  `showlegend` when a source shows one, its legend title kept. The result's `meta` merges the
  two. A source that is itself a subplot figure (more than one x axis) is refused with a
  ValueError. ~50 lines; §5 lists the plotly facts to check first.
- C6. `blocks.py`: the `CHOICES` rows lose the `when` key; `choices_block` emits `Choice`,
  `Value`, `Alternatives` (docstring: the config template and the component docs own the
  guidance). `how_to_read(bins: int | None, estimate_noun: str) -> list[str]`: five
  paragraphs, in this order and roughly these words:
  1. "Concordance says how well a feature orders clients by the target: 0.5 is no better than
     chance, 1 a perfect ordering, whichever way round (the direction column says which). For a
     yes/no target it is the AUC of that feature alone." Plus, when `bins` is not None: "Numerics
     are read on {bins} quantile bins; pairs inside one bin count half."
  2. "Lift is a group's {noun} divided by the snapshot's base {noun}: 1 is the base, 2 twice as
     likely{ or twice the amount, for a mean}."
  3. "Intervals are 95%: Wilson for a rate, Student t for a mean. On charts they are the error
     bars."
  4. "Grey means too little support, still shown: fewer than strata.min_events events (20 in a
     key feature's groups). Read the interval, not the point."
  5. "null is the clients without a value: their own bar or level, always last."
  `headline(numbers)` adds inline layout styles (each stat `display: inline-block; margin: 4px
  16px 4px 0`; the value and the label on two lines; no colours) so it reads in a notebook
  without the report's CSS.
- C7. Tests: `test_choices_block_reads_config_and_caller_values` (three columns); a
  `side_by_side` test: a `lift_chart` with a greyed row beside a `grouped_lines` with support
  bars → trace count is the sum, the right panel's bar trace is on a secondary axis, two subplot
  titles, a dashed line per panel that had a reference, exactly one insufficient note, the axis
  titles kept; a `grouped_lines` test over a feature's groups with a `legend_title`; the centred
  title (`fig.layout.title.x == 0.5`) on one primitive; `test_text_blocks` covers the five
  how-to-read paragraphs and the headline's inline style; the renamed function everywhere.

### Step D: the EDA stage (the views, the exploration functions, the small fixes)
Files: `eda/run.py`, `eda/ranking.py`, `eda/report.py`, `eda/deep_dives.py`, new
`eda/explore.py`, `eda/__init__.py`; tests `tests/test_eda.py`, `tests/test_eda_modules.py`,
`tests/test_run.py` (`PUBLIC_API`).

- D1. `ranking.py`: rename `window_k_rows` → `encoding_prior_rows`, docstring "The level
  encoding's prior weight in rows: `strata.min_events` pseudo-events at the window's base rate
  (regression: `min_events` rows), through `TASK_SPECS[task]["shrinkage_rows"]`; a level's rate
  is `(events + prior · base) / (rows + prior)`". Add `SIGNS = {text: sign for sign, text in
  DIRECTIONS.items() if text is not None}` beside `DIRECTIONS`; `run.py` imports it and drops
  its own. The `k_rows` names inside `eda/` become `prior_rows`; `statistics/` keeps `k_rows`
  (the encoder's parameter).
- D2. `run.py`: delete `_check_strata_names`; `_check_frame_names` refuses a stratum that is not
  a snapshot column or is in `FRAMEWORK_COLUMNS`, one message naming the offending names, the
  `source_<name>` hint and the snapshot's non-framework columns (Q518). `strata_pivots` runs
  over every key feature (`keys`, not `keys[:PIVOT_FEATURES]`; the constant goes). The views
  read `TASK_SPECS[resolved.task]["estimate_noun"]` themselves; `build_views`' signature is
  unchanged.
- D3. `report.py`:
  - The module docstring lists the views as built: `how_to_read` (summary), no `strata_pivots`
    key, `deep_dives` as §2.3.
  - `_summary_views` also returns `"how_to_read": blocks.how_to_read(resolved.eda.bins, noun)`.
  - `_target_views`: no interval branch (the mean now has one); the chart
    `charts.grouped_lines(..., x_title="Period", y_title=f"Target {noun}", support=...)`; the
    caption "with its 95% interval; the pooled row's on effective clients".
  - `_stratum_views`: `bar_with_intervals(..., x_title=variable, y_title=f"Target {noun}",
    by_level=True)`; its table keeps `low`/`high`: `_group_table(part, task, caption,
    interval=True)`.
  - `_group_table(groups, task, caption, interval: bool = False)`: shows `rows, support,
    estimate, lift`, plus `median` and `nonzero_share` when present, plus `low, high` only with
    `interval`. The lift colouring and greying as today.
  - `_ranking_views`: the view frame has `concordance` = `ranking_value`, `concordance_plain` =
    the plain `concordance` where `non_monotone`, else NaN; `RANKING_VIEW = ["rank", "feature",
    "kind", "concordance", "concordance_plain", "direction", "concordance_window",
    "missing_share", "null_concordance", "zero_share", "dominant_share", "levels",
    "key_feature", "represented_by", "unavailable"]`; the bar on `concordance` from 0.5; the
    caption "ordered by concordance: the best order's for a non-monotone feature, whose plain
    value shows in concordance_plain; every column is in tables/ranking and the ledger".
  - Public chart builders (used by `explore.py` too): `group_chart(groups, name, base, task)`
    (was `_group_chart`; `x_title=name`); `strata_chart(part, name, variable, base, task)`:
    `grouped_lines(part, x="feature_group", y="lift" if lift_available(base) else "estimate",
    group="level", reference=1.0 or None, from_zero=True, title=f"{name} by {variable}",
    x_title=name, y_title="Lift vs base rate (1 = base)" or f"Target {noun}",
    legend_title=variable)`, the rows in group then level order as the table gives them, no
    error bars; `boxes(quartiles, group, title, x_title, y_title)` (was `_boxes`, same log rule);
    `pivot_table(part, name, variable, task, min_events) -> Styler` (was the body of
    `_pivot_views`, for one feature × variable).
  - `_paired(charts: list[go.Figure]) -> list[go.Figure]`: `side_by_side` of each pair in order,
    the odd last one as it is.
  - `_deep_dive(name, dive, row, base, task, strata_rows, strata) -> list` builds §2.3: the
    table (when `by_level` or `target_distribution`), `_paired([group chart, *strata charts])`,
    the boxes beside the per-period concordance (or the per-period alone), the regression target
    boxes, then one `pivot_table` per `strata.variables`. `build_views` passes each feature's
    rows of `tables["strata"]` (`feature == name`) and `resolved.strata` (its `variables` and
    `min_events`).
  - `_correlation_view`: `names` = the key features and the candidates they represent, always;
    `compared` = those with at least one non-null statistic against another name; the rest are
    left out and counted; the subtitle "on a seeded cap of N snapshot rows; the key features and
    the candidates they represent: k shown, m without a compared pair left out; blank: not
    compared"; `HEATMAP_MAX` goes; fewer than two compared → the "Not available" paragraph.
  - `_appendix_views` without `how_to_read`; `report_sections` in §2.1's order.
- D4. New `eda/explore.py` ("the functions a reader calls on a stage result; they read `result`
  only and change nothing"): `pivot_target`, `_dimension`, `_styled_pivot` and `PIVOT_BINS` move
  here from `deep_dives.py` (the long form shows `rows, support, estimate, lift`; Q505), and:
  - `lift_by_group(result: StageResult, feature: str, by: str | None = None) -> go.Figure`:
    on the snapshot's eligible rows with a known target (`known_rows(result.frame)`), the
    base their target mean; the feature's groups from `_groups_of` (below); without `by`,
    `summarise_groups(target, groups.to_frame("group"), task, base, MIN_BIN_SUPPORT)` →
    `group_chart`; with `by`, the `by` labels from `_groups_of` too, `summarise_groups` over
    `{"feature_group": groups, "level": by_labels}` with `strata.min_events` → `strata_chart`.
  - `compare_sides(result: StageResult, feature: str, tag: str) -> go.Figure`: `tag` must be a
    modelling tag (`result.tables["reference_groups"]["tag"].unique()`; otherwise a ValueError
    naming them); the sides on every snapshot row, as `reference_groups` defines them: `excluded`
    = `frame[tag] == 0`, `eligible` = `frame["eligible"] == 1`. A numeric feature → `boxes` of
    the two sides' quartiles (`_box` from `deep_dives`, the skew rule), `x_title="side"`,
    `y_title=feature`; a categorical → `grouped_lines` of each level's share of rows per side
    (`cap_levels` at `strata.max_levels`, `null` last), x the level, one line per side,
    `y_title="Share of rows"`, `legend_title=tag`.
  - `rate_by_period(result: StageResult, feature: str) -> go.Figure`: the target by the
    feature's groups per window period from `result.tables["cells"]` (the window stays
    uncollected). `feature` must be a candidate with cells (else a ValueError naming the
    candidates); the window periods from `result.meta["compared_periods"]["window"]`; the
    current, labelled cells of the feature. Numeric: the groups are `merge_bins` over the
    snapshot period's pooled cells with the stage's edges (recomputed:
    `bin_edges(result.frame, {feature: "numeric"}, result.config.eda.bins)[feature]`, the same
    eligible rows, so the same edges) into `DEEP_DIVE_GROUPS`; every cell's `bin_order` maps to
    its group by `searchsorted` on `bin_order_first` (as `_assign_groups` does for rows); null
    cells are the group `null`. Categorical: the snapshot period's top `strata.max_levels` levels
    by rows, the rest (`__other__` and `__new__` included) pooled as `__other__`, `null` last.
    Per period and group: `n`, `events` (the rows whose `target_bin` is not a zero-target bin,
    `statistics.cells.zero_target_bins`, made public from today's `_zero_target_bins`),
    `estimate = sum_y / n`, `insufficient = events <
    MIN_BIN_SUPPORT`. Chart: `grouped_lines(x="period", y="estimate", group="group",
    insufficient=..., from_zero=True, title=f"{feature}: target per window period",
    x_title="Period", y_title=f"Target {noun}", legend_title=feature)`.
  - Private helpers: `_groups_of(result, name) -> pd.Series` (a snapshot column's group labels
    on `result.frame`: a candidate's kind from `result.ledger`, any other column's from its dtype
    as `_dimension` decides; numeric → `_numeric_groups(values, edges, DEEP_DIVE_GROUPS)` with
    the stage's edges as above; categorical → `cap_levels(values, strata.max_levels)`),
    `_check_columns(result, names)` (a ValueError naming the snapshot's columns). What
    `explore.py` imports from `deep_dives.py` becomes public there (`numeric_groups`,
    `box_summary`, or similar short names): no private cross-module imports.
  - `eda/__init__.py` exports `run_eda, pivot_target, lift_by_group, compare_sides,
    rate_by_period`; `PUBLIC_API["core_modelling.eda"]` in `tests/test_run.py` lists the five.
- D5. `deep_dives.py` loses `pivot_target` and its helpers; `strata_pivots`' docstring says
  every key feature. `DIVE_COLUMNS` and the stored tables are unchanged.
- D6. Tests: `test_a_stratum_named_like_a_framework_column_is_refused` (the error now comes
  after the collect, same hint); `test_the_report_has_plotly_once_and_every_section` ("How to
  read" in the summary, no "Strata pivots", "Correlation overview" present); a views test on
  `result`: a by-level feature's first block is a Styler and a binned numeric's is a figure; the
  two-panel figures are present; the pivot Stylers per feature count `len(strata.variables)`; the
  ranking view's columns equal `RANKING_VIEW` and `concordance_plain` is filled exactly on the
  non-monotone rows; a hand-made correlation table in `test_eda_modules.py` where one key
  feature has no compared pair → left out and counted in the subtitle; `lift_by_group` on a key
  feature gives the deep dive's group labels; `compare_sides` numeric → two boxes, categorical →
  two lines; `rate_by_period` → one line per group, the x labels the window periods, a numeric's
  group labels the deep dive's; a ValueError for an unknown column, a non-candidate in
  `rate_by_period` and an unknown tag; `test_pivot_target_with_a_backticked_filter_and_columns`
  follows the lean long form.

### Step E: the notebooks and the 100k data
Files: `notebooks/02_eda.ipynb`, `notebooks/01_target_factory.ipynb`, `notebooks/README.md`,
`conf/local/environment.yml` (gitignored, this laptop), `conf/base/environment.example.yml`
(one comment).

- E1. The data: point the three source paths in `conf/local/environment.yml` at
  `data/01_raw/synthetic_canonical/{mart,holdings,fs_extract}` (100,000 clients; the folder
  exists); run notebook 01's code cells (saves the model input for both use cases, replacing the
  dev one), then notebook 02's, each as a script through `.venv/bin/ipython` (nbclient is not
  installed), one at a time, nothing else on Spark meanwhile; record `run_eda`'s seconds and the
  report's size. The example file's comment names both presets (dev for tests of ideas, canonical
  for the notebooks).
- E2. Notebook 02 follows §2.2. Every code cell calls the Public API only
  (`test_notebook_calls_only_the_public_api`). The guide cells follow `notebooks/README.md`'s
  rule (before every step: what it does, what to look at, how to read each number, which
  decision to take and how to record it, both automation levels) and these corrections from the
  review: no decision (D-nnn), trap (T-nn) or worknotes reference anywhere; no "read in this
  order"; the top cell's concordance explanation is two sentences (the how-to-read view carries
  the rest); the runtime line from E1 ("about N minutes on a laptop, 100,000 clients"); step 7
  shows one call per exploration function with a one-line reading of what it answers; step 8
  names what the report holds beyond the notebook. Outputs cleared before saving.
- E3. Notebook 01: the same rules (its decision references removed; the top cell shortened; the
  description of the saved table stays: one table, one `target_<use_case>` column per use case).
- E4. The conciseness pass (Q515): after both notebooks are written, re-read every guide cell
  once with the single aim of cutting what a first-time user does not need, one or two sentences
  per bullet, and report the word counts before and after (information for the SDS, not a
  target). `notebooks/README.md`'s guide-cell rule gains two sentences: no decision or trap
  references (the reader is a data scientist new to the framework, not its maintainer); after
  writing, one re-read for conciseness before the notebook is done. Its 02 description names the
  views shown, the four exploration functions and the report-only sections.

### Step F: docs and worknotes (CLAUDE.md §8; run the `doc-sync` skill)
One owner per fact; edit in place; verdict first; no flowcharts.
- `docs/components/eda.md`: "The views" (§2.1 and §2.3 here, the lean ranking view and
  `concordance_plain`, the correlation overview rule, how-to-read in the summary, the pivots per
  deep dive over every key feature); "Interface" (the five public functions with signatures and
  one line each; the `views` keys; the cells' `sum_y2`; `encoding_prior_rows`); requirement 12
  (one strata check after the collect); "Code map" and "Function structure in brief"
  (`eda/explore.py`); the notebook paragraph (what the notebook shows and does not); the range
  labels under the counts table / deep dives.
- `docs/components/reporting.md`: "The EDA report" table (summary gains How to read; the deep
  dive row as §2.3; the strata pivots row goes; the correlation row); "Chart rules": a new rule
  10, "Titles and axes: a short centred title, every axis titled, the details in the caption,
  nothing clipped (automargin, bar text placed by plotly); two related charts share one figure of
  two panels (`side_by_side`)", and rule 9 renamed for `grouped_lines`; "The chart primitives"
  (`grouped_lines`, `side_by_side`, `x_title`, the meta); "Code map" and "Interface"
  (`choices_block` three columns, `how_to_read(bins, estimate_noun)`); "Theme" (the translucent
  bar; readable on both backgrounds); the open question on notebook display updated.
- `docs/components/dataset.md`: the counts table's columns (`sum_y2`); `collect_frame` sorts in
  Spark (`orderBy`) before the collect.
- `docs/context/lessons.md` T34: the fix column says the sort is Spark's `orderBy` before
  `toPandas`.
- `docs/architecture.md`: the Public API row for `core_modelling.eda` (the five functions, "0.3.0,
  review 2 applied <the build's date>"); the package layout gains `eda/explore.py`.
- `docs/glossary.md`: add **Lift** (a group's rate or mean divided by the base; 1 the base);
  update **Deep dive** (its content as §2.3).
- `docs/decisions.md`: extend D-135 in place (the cells carry `sum_y2`, so a regression mean has
  its interval from the counts; the collected frames sorted in Spark); extend D-137 in place
  (`eda/explore.py`: the exploration functions read the stage result only; the report's views
  as composed in `report.py`). No new row unless a genuinely new decision appears (then the
  low-impact table).
- `docs/UPDATES.md`: the EDA and Reporting status rows (review 2 applied, date); one dated log
  line. `docs/roadmap.md`: the M2 row (major step 2 review 2 applied; major step 3 next).
- `notebooks/README.md`: as E4.
- Worknotes: `plan.md` §9 gains V29+ (every decision the implementer took, one line each);
  `review_guide.md` is rewritten for review 3 (what to read, in which order, what right looks
  like; at most two "read this test"; the decisions to veto; the measured numbers on the 100k
  run); `worknotes/log.md` gets the entry (newest first); `questions.md` stays as it is unless a
  question for the SDS arises (then Q523 onwards, with a default).

### Step G: the simplicity pass (Q520)
Over `eda/run.py`, `eda/deep_dives.py`, `eda/population.py` with the `simplicity-review` skill:
about 20% fewer lines, no behaviour change (the tests are the oracle; no table's columns change).
Candidates: `_deep_dives` and `_dive_tables`; `strata_tables` and `strata_pivots` sharing one
summariser; `_record` in `ranking.py`; duplicated "eligible rows / known rows" slices. Report the
line counts before and after.

## 4. Verification and the review (stage 3)
1. After every step: the touched modules' tests, `ruff check` on the touched files, the
   `code-reviewer` subagent and `simplicity-review`; `tests/test_code_rules.py` whenever a
   private function was added.
2. After E: both notebooks run end to end on the canonical data with no cell error; the report
   opened once in a browser (size, the sections, one deep dive's two-panel figures, the pivot
   tables); the three exploration functions tried on a key feature in the notebook.
3. After G: the full suite once on the main thread in the background (`pytest`; expect about 10
   minutes; the 9 slow tests stay deselected), then `ruff check .`. Nothing else runs on Spark
   meanwhile.
4. The comprehensive review of the whole major step 2 code (the SDS's stage 3; routing to be
   decided by the SDS, Q522): `code-reviewer` per module (`reporting/*`, `eda/*`, the touched
   `dataset/*`, `statistics/*`, `tasks.py`), the `ml-correctness-auditor` on `eda/*`,
   `statistics/*`, `dataset/counts.py` and `tasks.py`, the `silent-failure-hunter` on
   `reporting/*`, `eda/report.py`, `eda/explore.py` and `eda/run.py`'s write path, the
   `compat-guardian` on the cells' columns and the public functions; every finding verified
   before it is fixed (a second reader confirms or refutes it); one fix round; the review guide
   written last.
5. Done means: every test green; `ruff` clean; the notebooks run on the 100k data; the docs of
   step F synced; the review guide and the V-list current; nothing committed; the final report
   with the token split per model.

## 5. Facts to verify first (plotly 6.3.1, pandas 2.2.3), before step C5 is written
1. `fig.add_trace(trace, row=1, col=2, secondary_y=True)` on `make_subplots(rows=1, cols=2,
   specs=[[{}, {"secondary_y": True}]])` lands the trace on the second panel's secondary axis,
   and `fig.update_yaxes(..., row=1, col=2, secondary_y=True)` addresses that axis.
2. `fig.add_hline(y=..., row=1, col=c)` draws in that panel only.
3. `fig.update_xaxes(<dict>, row=1, col=c)` accepts a patch dict holding `type="category"`,
   `categoryorder`, `categoryarray`, `range` and `title`.
4. A bar's `textposition="auto"` places the text inside when it fits (and shrinks it,
   `constraintext` default "both").
5. `automargin=True` grows the margin for rotated tick labels and the axis title.
6. pandas `Styler.bar(color="rgba(47, 111, 159, 0.45)")` renders the colour in its gradient.
If 1–3 fail on the pinned version, stop and report before changing the design: the fallback is to
draw the per-period panel's support bars without a secondary axis, which changes the chart's
meaning and needs the SDS's go.

## 6. Suggested split (the `delegation` skill applies)
- Builders: A, B, C in parallel (Opus; C at `xhigh`, since `side_by_side` and the look are
  where a wrong answer costs a rewrite); then D (Opus `xhigh`, one builder: `report.py` and
  `explore.py` are tied); then E (Opus `xhigh`: the guide text is the main deliverable; a second,
  fresh agent for the conciseness pass); F (one doc agent, Opus `high`, with this file and the
  step reports as its brief) and G (Opus `high`) in parallel after E.
- Reviews: one `code-reviewer` per step; stage 3 as §4.4.
- The main thread keeps the integration, the facts check (§5), the full suite and the final
  report. One Spark job at a time on this machine.
