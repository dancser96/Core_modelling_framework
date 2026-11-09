# Reporting and model card
**Status:** built in part 2026-11-04 (Stage 2 major step 2: the renderer, the five primitives and `side_by_side`, the blocks and the theme, built with the EDA report; reviews 2 and 3 applied 2026-11-05/06; the Feature Checks report and `formats.py` built 2026-11-06, major step 3); the model card comes in M2.3/M2.4 · **Legacy:** `src/card.py`, `src/analysis.py` plotting helpers
**Related:** [EDA](eda.md) · [feature checks](feature_checks.md) · [feature ledger](feature_ledger.md) ·
[evaluation](evaluation.md) · [monitoring](monitoring.md) · [lifecycle](lifecycle.md) ·
[config](config.md) (template explanations, audit log) · [environment](environment.md) (theme) ·
D-012, D-020, D-031, D-032, D-036, D-052, D-083, D-136, D-137 · OD-12

Read it in three levels: Level 1 gives the essentials, Level 2 how the parts connect, Level 3
every detail.

## Level 1: Summary
One shared renderer turns any stage's results into a **self-contained HTML report**: pandas Styler
tables and plotly charts, plotly.js embedded once per file so a report opens offline inside the
bank. Every report has the same four parts: **summary → core → extended → appendix** (D-036).
Stage 2 builds the renderer, the chart primitives, the shared blocks and a neutral theme
(`src/core_modelling/reporting/`, built 2026-11-04 with the EDA report), and two reports with
them: `eda/report.html` and `feature_checks/report.html` (both built), each beside its stage's
artifacts (D-136). Every figure is
pre-aggregated, there is no cap on figures, and a report regenerates from the resolved config.
Notebooks display the same objects (`StageResult.views`) and never assemble a report. The
versioned model card (requirement 4) is M2.3/M2.4's.

## Level 2: How it fits together

### The renderer and what a stage hands it
1. A stage computes its tables, then builds its **views**: Styler tables and plotly figures made
   with the chart primitives and the blocks.
2. It groups the views into sections under the four parts and calls `render_report`, which
   returns one HTML page: a table of contents from the headings, an anchor per section,
   plotly.js once, each figure as a fragment, the theme's CSS.
3. It writes the page as `report.html` with its other artifacts (`artifacts.write_stage`'s
   `texts`), so the folder's rename commits the report with the tables, and a render error (a
   Styler fails only when rendered) leaves the previous run's folder.
4. It returns `StageResult(tables, ledger, log, meta, paths, views, frame, config)`; `views` holds
   the same Stylers and figures the report embeds, so the notebook shows what the report shows.

### The two Stage 2 reports
Each stage is standalone and writes its own file (Q457); the Feature Checks summary repeats EDA's
headline numbers from `eda.json` so its reader knows the population.
- **EDA:** summary (choices, how to read, headline numbers, numbered warnings, one events
  warning) → core (funnel, sources per period, target per period, target by stratum, univariate
  ranking, the key features at the decision's slices, key-feature deep dives with their strata
  pivots) → extended (reference groups, correlation overview, value profile) → appendix.
- **Feature Checks:** summary (choices, how to read, EDA's headline, warnings, flags and notes,
  held features) → core (findings per step, proposed decisions, ledger with decisions) →
  extended (per-period concordance and PSI for every candidate) → appendix.

Every report opens with the one **`CHOICES` table** in three columns, Choice, Value and
Alternatives; when to move to an alternative is the config template's and the component docs' to
explain, not the report's (D-032).

### Modules and main functions
`src/core_modelling/reporting/`:
- `html.py`: `render_report(title, sections) -> str`, `paragraph(text)`,
  `preformatted(text)`, `figure_html(fig, div_id) -> str`, `table_html(styler, uuid) -> str`,
  `style_table(df, formats, lift, greyed, bar, caption, bar_min) -> Styler`;
- `charts.py`: `bar_with_intervals`, `lift_chart`, `box_from_quartiles`, `grouped_lines`,
  `heatmap`, each returning a plotly figure with the chart rules applied, and `side_by_side`,
  which sets two of them as one figure of two panels (details under "The chart primitives");
- `formats.py`: how numbers read in a table, shared by every report: `column_formats(df, task)`
  (each known column's format by name, from the shared column lists `CONCORDANCES`, `SHARES`,
  `THREE_DECIMALS`, `PLAIN`, `P_VALUES`, `ESTIMATES` and the prefixes), `plain_number(x)` and
  `p_value(x)`;
- `blocks.py`: `CHOICES` (31 rows), `choices_block(resolved, choices) -> Styler`,
  `headline(numbers)`, `warnings_block(items)` (numbered), `how_to_read(bins, estimate_noun,
  support_name, group_support)`; there is no `appendix` function: a stage composes its appendix
  from these blocks;
- `theme.py`: `THEME`, the neutral palette, fonts, the colour sequence and the heatmap scales as a
  dict.

### How it is checked
Light tests: plotly.js appears exactly once in a rendered page; every `div_id` is unique;
`choices_block` reads its values from the resolved config; the chart rules asserted where testable
(axis ranges from the data, the null bar present, insufficient bins greyed, no WebGL trace). The
file size and the open time of both reports are measured locally on the canonical synthetic data
and recorded in the log (Q455).

## Level 3: Details

### Requirements and design constraints
1. **Self-contained HTML.** Styled tables (pandas Styler) and interactive plotly charts, plotly.js
   embedded once per file (no CDN, `CLAUDE.md` §5). That is about 4.8 MB per report before the
   figures; the size isn't optimised in Phase 2 (D-036).
2. **Every report has the same structure:**
   1. **Summary**, one page for business and governance readers: the choices block (the `CHOICES`
      rows that apply, with their values from the resolved config), the how-to-read notes, the
      headline numbers and numbered rule-based warnings (e.g. few positive events, a choice
      among variants made on test metrics, D-083); one events warning, not two.
   2. **Core** views.
   3. **Extended** views, or "not available: reason" where a view is declared incompatible up
      front (`CLAUDE.md` §1 rule 8).
   4. **Appendix:** the resolved config, the audit log and the run's housekeeping (collect log,
      entries written, timings). The origin of every entry-written value is the header
      `resolve_config(save_to=…)` writes into a saved `resolved_config.yml`, not the report's.
3. **Theme:** neutral in the repo (`THEME`); a theme file in `conf/local/` (palette, fonts, logo
   path) is read in M4, when the bank's theme is known. Nothing in the repo names a brand.
4. **Model card = structured facts only**, with a versioned schema (§2). It covers:
   - config summary, data definition and lineage, dates, eligibility;
   - sampling, calibration (prior shift and any calibration step);
   - modelling path and best config;
   - metrics vs baselines (overall and stratified), importance;
   - unresolved flags, human decisions and the feature sign-off (D-031);
   - for a refit: the parent run and its evaluation metrics (D-052).

   It is designed so a later generator can map it onto the internal model documentation standard.
5. **Every figure is pre-aggregated.** No row-level chart and no raw arrays in the HTML: bars come
   from the group tables, box plots from precomputed quartiles. Figures use plotly's `template="none"`, which keeps
   a 20-bar fragment at about 3.7 KB; the EDA report on the unit preset (161 candidates, 35
   figures) is 5.6 MB, of which plotly.js is 4.83 MB. No chart draws clients, so none needs sampling, while the
   statistics behind every chart use the whole population (D-135). Should a row-level chart ever
   be added, it draws a seeded sample of at most 10,000 rows and says so in its caption.
6. **No cap on figures**; the size and the open time are measured instead (Q455).
7. **Reports regenerate from the resolved config** and the stage's artifacts, never from a
   notebook (D-039). Decisions are read from the audit log when the report is written, never
   stored ([feature ledger](feature_ledger.md)).
8. **How-to-read notes,** in the summary of every report that shows a concordance, five short
   paragraphs. EDA's (`how_to_read`) are below; the Feature Checks report writes its own five
   (concordance read in the window's direction, a flag, a note, grey, `null`;
   [feature checks](feature_checks.md) "The report"):
   - concordance: "Concordance says how well a feature orders clients by the target: 0.5 is no
     better than chance, 1 a perfect ordering, whichever way round (the direction column says
     which). For a yes/no target it is the AUC of that feature alone.", then "Numerics are read
     on 100 quantile bins; pairs inside one bin count half." with the number from `eda.bins`
     (left out when `eda.bins` is null: every statistic exact);
   - lift: a group's rate (or mean) divided by the snapshot's base, 1 the base;
   - intervals: 95%, Wilson for a rate, Student t for a mean, the error bars on charts;
   - grey: too little support, still shown (`strata.min_events`, and `MIN_BIN_SUPPORT` in a key
     feature's groups); read the interval, not the point;
   - null: the clients without a value, their own bar or level, always last.
9. **Task-agnostic views.** What a group shows dispatches on `task` through the per-task spec
   (D-050): binary, the rate with a Wilson interval and lift = rate / base rate; regression, the
   mean with a t-interval, lift = mean / overall mean, the median beside it. The statistics are
   [EDA](eda.md)'s.

### The EDA report

| Section | Views | Source table |
|---|---|---|
| Summary | choices block (Choice, Value, Alternatives); how to read (five notes); headline numbers; numbered warnings, one events warning | resolved config; `eda.json` |
| Core: funnel per period | table | `funnel` |
| Core: sources per period | the spine's rows and each joined feature source's matched share per compared period and `all` ("Not available" when the spine is the only source) | `sources` |
| Core: target per period (the whole window) | rows, positive rows, positive events, the estimate with its 95% interval (binary: the rate, Wilson; regression: the mean, t-interval from the cells' sum of squares, and the non-zero share, Wilson); `grouped_lines` with support bars | `target_per_period` |
| Core: target by stratum | table; `bar_with_intervals` (the modelling tags get none) | `strata` |
| Core: univariate ranking | the lean view, a bar on `concordance` (the ranking value) from 0.5; every column in the table; lineage and unsupported columns listed as excluded | `ranking` |
| Core: at the decision's slices | the decision paragraph; table of the key features × slices (capture, estimate coloured by lift, lift, support); the capture curve (`grouped_lines(..., x_numeric=True)`, the `random` diagonal dashed and muted) | `slices`, `capture_curve` |
| Core: key-feature deep dives ([EDA](eda.md) "The views") | group table for a by-level feature or an amount target; `lift_chart` (the estimate's bars when no lift exists) beside the first strata chart (`grouped_lines`, a line per level) in one `side_by_side` figure, further strata charts alone; `box_from_quartiles` by target class beside the per-period concordance (`grouped_lines`); regression: the target's boxes per group; one pivot table per stratum variable | `bins`, `levels`, `quartiles`, `per_period`, `target_quartiles`, `strata` |
| Extended: reference groups | per tag: rows kept and excluded per window period, then sizes, composition and key-feature SMDs | `funnel`, `reference_groups` |
| Extended: correlation overview | `heatmap` of the key features only (one without a compared pair left out, counted in the subtitle); beneath it, the candidates each represents | `correlation`, `ranking` |
| Extended: value profile | two tables in rank order: the numerics' range and ±infinity share, the categoricals' three largest levels | `profile` |
| Extended: concordance per period | one feature × window period table, every candidate in rank order, in the window's direction, greyed below `strata.min_events`, blank where not available | `concordance_per_period` |
| Appendix | kinds with overrides and sources; the ledger (identity, EDA); resolved config; decisions; collect log; timings (a table) | ledger; `resolved_config.yml`; `eda.json` |

### The Feature Checks report

| Section | Views | Source table |
|---|---|---|
| Summary | choices block; how to read (five notes); EDA's headline; numbered warnings (skipped steps, always the all-client one); flags and notes (per finding its kind and count, a flag's features named, a note's counted); held features with each open flag's value (`flag_values`; the hold-out sentence as the table's caption) | resolved config; `feature_checks.json` (with `eda_headline`); `findings` |
| Core: findings per step (fixed order, one subsection per step: "Quality" … "Redundancy") | per step the raised findings' texts (a table), one table (value, threshold, the ledger's statistics, detail), what it could not test; "Not run" when skipped; redundancy first shows one row per cluster, then its feature table | `findings`, `unavailable`, `clusters`; ledger |
| Core: proposed decisions | a table (per open flag finding its threshold and each feature's value) plus the two `record_decision` calls per finding in one code block | `proposed_decisions` |
| Core: ledger with decisions | table | ledger + `render_decisions` |
| Extended: per period, every candidate | a line pointing to EDA's report for the concordance per window period; one feature × period table of PSI against the snapshot per compared period (the caption names `psi_note_min` and `psi_max`); `grouped_lines` of the per-period concordance of the features `concordance_unstable` raised ("Not available" without one), greyed below `strata.min_events` | `per_period` (label-free); EDA's `concordance_per_period`; `findings` |
| Appendix | resolved config; decisions (the audit log); entries written; timings | resolved config; audit log; `feature_checks.json` |

Its choices block adds eight `CHOICES` rows to the shared ones: the support rule
(`strata.min_events`), the five steps' thresholds (each step's mapping, "not run" when skipped),
the skipped steps and the compared periods. The report never suggests a verb for a flag (Q449);
for near-duplicates it names the trade-off and leaves the choice to a person (Q472). Each view's
columns and wording: [feature checks](feature_checks.md) "The report".

### The renderer
- A section is `(heading, blocks)`; a block is a Styler, a plotly figure, a str (an HTML
  fragment, inserted as is: `paragraph`, `preformatted`, `headline`, `warnings_block`), a dict (a
  key-value list) or a `(heading, blocks)` tuple, a subsection with its own anchor. The four
  parts are the top-level sections.
- plotly.js is embedded once from `plotly.offline.get_plotlyjs()` in one `<script>`; each figure
  is rendered with `include_plotlyjs=False, full_html=False` and its own `div_id`
  (`figure_html`). `include_plotlyjs=False` with `full_html=True` gives a broken page.
- Tables go through `Styler.to_html()`; Styler raises above `styler.render.max_elements` =
  262,144 cells (the ledger is far below). Numbers read by `formats.column_formats`: a value
  column (quantiles, medians, a finding's value and threshold) prints through `plain_number`,
  with thousands separators from 1,000 and four significant digits below, never in scientific
  notation; a p-value below 0.0001 reads "< 0.0001".
- A table's caption is styled inside its Styler (`style_table`'s `caption`, `html.CAPTION_CSS`:
  top, left, bold, 1.1em, the theme's muted colour), so a notebook shows it as the report does.
  The page's headings step down from h1 1.6rem and h2 1.3rem to h3 1.2rem and h4 1.1rem, above
  the browser's defaults, so a subsection's heading (a Feature Checks step) reads larger than
  the captions beneath it.
- No templating beyond what Styler needs: string building plus plotly, and a CSS block from
  `THEME`.
- No WebGL traces (browsers allow 8–16 WebGL contexts per page): bars, box plots and markers are
  SVG. No static images (kaleido needs a browser, not in the bank).

### Chart rules (a living rule set: extend it whenever a chart is reviewed)
1. **Axes follow the data.** From zero (rates, means): `[min(0, 1.25 × the lowest), max(0,
   1.25 × the highest)]` over the plotted values, every estimate and the supported bars'
   interval ends (and a reference line), so a negative estimate (an amount target can be
   negative) and a supported interval's bottom stay in view, while an insufficient bar's
   interval may run past the axis. A line chart counts its values only up to twice its highest
   supported point (the 1.25 headroom comes on top), so a few grey points cannot flatten the
   lines and one far above runs off the top, its number in the table or pivot; when none is
   supported, every point and interval counts. An estimate's axis and hover take the task's `axis_format` (binary:
   percent); lift and concordance axes stay plain. A statistic around a reference (a
   concordance around 0.5) uses the data's span (`from_zero=False`). Zoom reliability curves to
   the score range, with the diagonal clipped to it. Never use a fixed (0, 1) range at low prevalence
   (T16).
2. **Where absolute rates are tiny, show lift vs base rate,** always with counts and intervals:
   Wilson intervals for rates, t-intervals for means.
3. **Grey out, never hide,** bins and cells with too little support, and say so: bins and levels
   below `MIN_BIN_SUPPORT = 20` in the deep dives, periods below `strata.min_events` in
   per-period lines. The interval is still drawn.
4. **Quantile groups** for numeric features, merged from the cells by cumulative row share
   (`merge_bins`: about ten groups); a bin holding at least
   `1 / groups` of the rows (0 and the dominant value whenever they reach it) stays its own bar,
   never widened into a neighbour, so the count can exceed the target by such interior bars;
   never equal-width bins (T25). A group is labelled by its outer range (`[374, 419)`, `= 0`,
   `≥ 900`; the rules: [EDA](eda.md) "The counts table"); a numeric shown by level reads its
   values (`0`, `1`, `2`), not `= 0`. **Log axes** for heavy
   tails, never with a zero quartile or a zero bar on them (T30): offset, linear axis or a
   separate zero share.
5. **No chart whose bars are all near zero.** Switch to lift, a log axis or a table.
6. **One colour per target class, segment or model** across a whole report; comparisons overlay
   on shared axes. A stratum's lines and pivot columns follow its own level order (its "Target
   by stratum" rows, `null` last), so a level keeps its colour.
7. **The null bin is its own bar, labelled `null`,** in the null colour (a `null` line or box
   too); a level table lists `null` as a level. Nulls
   never vanish from a chart.
8. **Distributions are box plots from quartiles**, never raw points or raw histograms.
9. **Lines over an ordered category axis** (`grouped_lines`: periods, or a feature's groups)
   mark every category in the data's order, padded half a slot at both ends; the label-free
   periods show no label-based value. A curve over a share of rows (`x_numeric`) uses a linear
   [0, 1] axis shown as percentages, lines without markers; a reference line among the groups
   (the capture curve's `random`) is dashed and muted; a capture axis stops at 100%.
10. **Titles and axes:** a short centred title, every axis titled, the details in the caption,
    nothing clipped (automargin, bar text placed by plotly); two related charts share one figure
    of two panels (`side_by_side`).

### The chart primitives
Every primitive takes `title`, `x_title` and `y_title` (rule 10), places bar text with plotly
(`textposition="auto"`, inside at the base when it fits) and records `layout.meta` (`reference`,
`insufficient`), since shapes and annotations do not move into a subplot.
- `bar_with_intervals(df, x, estimate, low, high, support, insufficient, title, x_title, y_title,
  by_level, y_format=None)`; `y_format` (a d3 format, the task's `axis_format`) formats the y
  axis and the hover; `by_level` colours bars by position, which suffices while each stratum variable has
  one chart.
- `lift_chart(df, x, lift, low, high, support, insufficient, title, x_title, y_title)`: `low` and
  `high` are in lift units (the caller divides the estimate's interval by the base); reference
  line at 1.
- `box_from_quartiles(df, group, q1, median, q3, lower, upper, title, x_title, y_title, log,
  by_target_class=False)`: a category x axis in the table's order, `null` last in the null
  colour; target-class colours only with `by_target_class` (boxes by target class), else
  colours by position; `log=True` refuses a non-positive value (T30); the caller decides up
  front.
- `grouped_lines(df, x, y, group, low, high, support, insufficient, reference, from_zero, title,
  x_title, y_title, support_title, legend_title, group_order=None, y_format=None,
  x_numeric=False)`: long format (one row per
  category and group); `group_order` sets the lines' order and so their colours (default the
  data's order; a group missing from it fails), a `null` line takes the null colour;
  support bars for a single line only, so `support` and `group` exclude each other; a label-free
  period carries NaN and shows no point, and the caller drops it before the call when it should
  show no support bar; `x_numeric` draws x as numbers on a linear [0, 1] axis and refuses
  support bars.
- `heatmap(matrix, hover, title, x_title, z_title)`: the matrix must be square with the same
  labels on both axes; sized from the label count and length, every label shown.
- `side_by_side(left, right, height=380)`: two primitives' figures as one figure of two panels,
  each keeping its title, axes and reference line (redrawn from `layout.meta`), the right one its
  legend, one insufficient note for both; refuses a subplot figure, a heatmap, a figure without
  the meta, and a left figure that shows a legend (the one legend sits right of the right
  panel).

### Theme
`THEME` is a dict: the neutral palette, the fonts, the categorical colour sequence and the
colours of the target classes, `null`, insufficient support, lift and the heatmaps. Tables read on
a light and a dark notebook page: the in-cell bar (`bar`, `rgba(47, 111, 159, 0.45)`) and the
lift colours (at most 55% opacity, `html.MAX_LIFT_COLOUR`) are translucent, so the page's text
colour reads over them. Figures keep a white background (a white card on a dark page): plotly
cannot follow the page's text colour, and the report page is white. The path
`environment.theme` exists in the environment config and is read in M4.

### Dependencies
- plotly 6.3.1 (pinned), bundling plotly.js 3.1.1: 4.83 MB embedded per report (measured locally).
- pandas Styler needs jinja2 3.1.6, pinned in `requirements.txt` (D-012).

### Code map
- `src/core_modelling/reporting/html.py`: the renderer (`render_report`, `paragraph`,
  `preformatted`, `figure_html`, `table_html`, `style_table`).
- `reporting/charts.py`: the five primitives, each one function returning a figure, and
  `side_by_side`.
- `reporting/blocks.py`: `CHOICES` (plain data: label, config path, alternatives),
  `choices_block` (the "metric" row shows `decision.metric`, or "derived from decision.type" until
  Training derives it, M2.3), `headline`, `warnings_block`, `how_to_read(bins, estimate_noun,
  support_name, group_support)`.
- `reporting/formats.py`: `column_formats`, `plain_number`, `p_value` and the shared column lists.
- `reporting/theme.py`: `THEME`.
- Each stage builds its own sections from its tables ([EDA](eda.md),
  [feature checks](feature_checks.md)).
- Reading order for review: `render_report`, then one chart primitive against the chart rules, then
  `choices_block`.

### Interface
No public reporting function in Stage 2: reports are written by `run_eda` and
`run_feature_checks`, notebooks display `StageResult.views` (D-137), and EDA's exploration
functions draw with these primitives ([EDA](eda.md) "Interface").

```python
def render_report(title: str, sections: list[tuple[str, list]]) -> str: ...
def figure_html(fig: go.Figure, div_id: str) -> str: ...
def table_html(styler: Styler, uuid: str) -> str: ...
def style_table(df, formats=None, lift=None, greyed=None, bar=None, caption=None,
                bar_min=0.0) -> Styler: ...
def choices_block(resolved: UseCaseConfig, choices: list[dict]) -> Styler: ...
def how_to_read(bins: int | None, estimate_noun: str, support_name: str,
                group_support: int) -> list[str]: ...
def side_by_side(left: go.Figure, right: go.Figure, height: int = 380) -> go.Figure: ...
def column_formats(df: pd.DataFrame, task: str) -> dict[str, str | Callable[[float], str]]: ...
def plain_number(x: float) -> str: ...
def p_value(x: float) -> str: ...
```

`render_report` returns the page; the stage writes it with `artifacts.write_stage(result,
folder, name, texts={"report.html": page})`.

### Lessons from the crunch
- T16: fixed chart ranges at low prevalence showed nothing (chart rules 1, 2, 5).
- T17: decide view × model-family compatibility up front, never wrap a view in try/except
  (requirement 2.3).

## Open questions
- OD-12 (the core views per task): this spec fixes them for the EDA and Feature Checks reports;
  Evaluation's are decided in M2.3.
- Decided for notebook 02: the notebook displays `StageResult.views`, which read on a light and
  a dark page ("Theme"); the report opens in a browser, not inline: the notebook shows the
  report's path and how to open it ("Trust HTML" in JupyterLab, or an `IFrame` with `srcdoc`;
  the report is about 6 MB, so no live cell duplicates it in a shipped notebook).
  Unverified in the bank's JupyterLab: whether the charts run under "Trust HTML" or in `srcdoc`.
- Unverified: whether plotly renders in the bank's JupyterLab and how fast a report opens there;
  both show in the SDS's JupyterLab test inside the bank (D-036).
