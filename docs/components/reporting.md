# Reporting and model card
**Status:** designing (spec settled 2026-11-02; the writer, charts and blocks built in Stage 2 with the EDA and Feature Checks reports; the model card in M2.3/M2.4) · **Legacy:** `src/card.py`, `src/analysis.py` plotting helpers
**Related:** [EDA](eda.md) · [feature checks](feature_checks.md) · [feature ledger](feature_ledger.md) ·
[evaluation](evaluation.md) · [monitoring](monitoring.md) · [lifecycle](lifecycle.md) ·
[config](config.md) (template explanations, audit log) · [environment](environment.md) (theme) ·
D-012, D-020, D-031, D-032, D-036, D-052, D-083, D-136, D-137 · OD-12

Read it in three levels: Level 1 gives the essentials, Level 2 how the parts connect, Level 3
every detail.

## Level 1: Summary
One shared writer turns any stage's results into a **self-contained HTML report**: pandas Styler
tables and plotly charts, plotly.js embedded once per file so a report opens offline inside the
bank. Every report has the same four parts: **summary → core → extended → appendix** (D-036).
Stage 2 builds the writer, the chart primitives, the shared blocks and a neutral theme
(`src/core_modelling/reporting/`), and two reports with them: `eda/report.html` and
`feature_checks/report.html`, each beside its stage's artifacts (D-136). Every figure is
pre-aggregated, there is no cap on figures, and a report regenerates from the resolved config.
Notebooks display the same objects (`StageResult.views`) and never assemble a report. The
versioned model card (requirement 4) is M2.3/M2.4's.

## Level 2: How it fits together

### The writer and what a stage hands it
1. A stage computes its tables, then builds its **views**: Styler tables and plotly figures made
   with the chart primitives and the blocks.
2. It groups the views into sections under the four parts and calls `write_report`, which writes
   one HTML file: a table of contents from the headings, an anchor per section, plotly.js once,
   each figure as a fragment, the theme's CSS.
3. It returns `StageResult(tables, ledger, log, meta, paths, views, frame, config)`; `views` holds
   the same Stylers and figures the report embeds, so the notebook shows what the report shows.

### The two Stage 2 reports
Each stage is standalone and writes its own file (Q457); the Feature Checks summary repeats EDA's
headline numbers from `eda.json` so its reader knows the population.
- **EDA:** summary (choices, headline numbers, numbered warnings, one events warning) → core
  (funnel and target per period, target by stratum, univariate ranking, key-feature deep dives) →
  extended (reference groups, strata pivots, correlation overview) → appendix.
- **Feature Checks:** summary (EDA's headline, choices, flags and notes per step, held features)
  → core (findings per step, proposed decisions, ledger with decisions) → extended (per-period
  concordance and PSI for every candidate, redundancy clusters) → appendix.

Every report opens with the one **`CHOICES` table**: what was chosen, the alternatives and when to
move, reusing the config template's explanations (D-032).

### Modules and main functions
`src/core_modelling/reporting/`:
- `html.py`: `write_report(title, sections, path) -> str`, `figure_html(fig, div_id) -> str`,
  `table_html(styler) -> str`, `style_table(df, ...) -> Styler`;
- `charts.py`: `bar_with_intervals`, `lift_chart`, `box_from_quartiles`, `per_period_lines`,
  `heatmap`, each returning a plotly figure with the chart rules applied;
- `blocks.py`: `CHOICES`, `choices_block(resolved, choices) -> Styler`, `headline(numbers)`,
  `warnings_block(items)` (numbered), `appendix(...)`;
- `theme.py`: `THEME`, the neutral palette, fonts and colour sequence as a dict.

### How it is checked
Light tests: plotly.js appears exactly once in a written file; every `div_id` is unique;
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
      rows that apply, with their values from the resolved config), the headline numbers and
      numbered rule-based warnings (e.g. few positive events, a choice among variants made on test
      metrics, D-083); one events warning, not two.
   2. **Core** views.
   3. **Extended** views, or "not available: reason" where a view is declared incompatible up
      front (`CLAUDE.md` §1 rule 8).
   4. **Appendix:** the resolved config with the origin of every entry-written field, the run's
      housekeeping (collect log, timings) and the how-to-read notes.
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
   from the group tables, box plots from precomputed quartiles. A 20-bar fragment is about 8 KB,
   so 50 figures add about 0.5 MB. No chart draws clients, so none needs sampling, while the
   statistics behind every chart use the whole population (D-135). Should a row-level chart ever
   be added, it draws a seeded sample of at most 10,000 rows and says so in its caption.
6. **No cap on figures**; the size and the open time are measured instead (Q455).
7. **Reports regenerate from the resolved config** and the stage's artifacts, never from a
   notebook (D-039). Decisions are read from the audit log when the report is written, never
   stored ([feature ledger](feature_ledger.md)).
8. **How-to-read lines.** Every report that shows a concordance explains it in two sentences:
   "Concordance says how well a feature orders clients by the target: 0.5 is no better than
   chance, 1 a perfect ordering, whichever way round (the direction column says which). For a
   yes/no target it is the AUC of that feature alone." Below it, "on 100 quantile bins; pairs
   inside one bin count half", with the number from `eda.bins`; no such line when `eda.bins` is
   null (every statistic exact).
9. **Task-agnostic views.** What a group shows dispatches on `task` through the per-task spec
   (D-050): binary, the rate with a Wilson interval and lift = rate / base rate; regression, the
   mean with a t-interval, lift = mean / overall mean, the median beside it. The statistics are
   [EDA](eda.md)'s.

### The EDA report

| Section | Views | Source table |
|---|---|---|
| Summary | choices block; headline numbers; numbered warnings; events warning | resolved config; `eda.json` |
| Core: funnel per period | table | `population` |
| Core: target per period (the whole window) | rows, positive rows, positive events, rate with Wilson interval; `per_period_lines` | `population` |
| Core: target by stratum | table; `bar_with_intervals` | `strata` |
| Core: univariate ranking | table ("optimistic (in-sample encoding)" above 20 levels) | `ranking` |
| Core: key-feature deep dives | `lift_chart` (or a level table); `box_from_quartiles` by target class; null bar; `per_period_lines` of the concordance | `bins`, `levels`, `cells`; quartiles from the snapshot |
| Extended: reference groups | standardised mean differences table | `reference_groups` |
| Extended: strata pivots (top five key features) | pivot tables | `strata` |
| Extended: correlation overview | `heatmap` | `correlation` |
| Appendix | kinds with overrides; the ledger (identity, EDA); resolved config; collect log; timings; how to read | ledger; `resolved_config.yml`; `eda.json` |

### The Feature Checks report

| Section | Views | Source table |
|---|---|---|
| Summary | EDA's headline; choices block; flags and notes per step; held features | `eda.json`; `feature_checks.json`; `findings` |
| Core: findings per step (fixed order) | one table per step | `findings` |
| Core: proposed decisions | grouped flags with the `record_decision` call text | `proposed_decisions` |
| Core: ledger with decisions | table | ledger + `render_decisions` |
| Extended: per-period concordance and PSI, every candidate | table; `per_period_lines` | `per_period` |
| Extended: redundancy clusters | one table per cluster, sorted by concordance | `clusters`; ledger |
| Appendix | resolved config; timings; how to read | `resolved_config.yml`; `feature_checks.json` |

The report never suggests dropping a feature (Q472) or a verb for a flag (Q449).

### The writer
- A section is `(heading, blocks)`; a block is a Styler, a plotly figure, a paragraph or a
  key-value list. The four parts are the top-level sections.
- plotly.js is embedded once from `plotly.offline.get_plotlyjs()` in one `<script>`; each figure
  is rendered with `include_plotlyjs=False, full_html=False` and its own `div_id`
  (`figure_html`). `include_plotlyjs=False` with `full_html=True` gives a broken page.
- Tables go through `Styler.to_html()`; Styler raises above `styler.render.max_elements` =
  262,144 cells (the ledger is far below).
- No templating beyond what Styler needs: string building plus plotly, and a CSS block from
  `THEME`.
- No WebGL traces (browsers allow 8–16 WebGL contexts per page): bars, box plots and markers are
  SVG. No static images (kaleido needs a browser, not in the bank).

### Chart rules (a living rule set: extend it whenever a chart is reviewed)
1. **Axes follow the data.** For rates use `(0, 1.25 × max plotted value)`. Zoom reliability curves to
   the score range, with the diagonal clipped to it. Never use a fixed (0, 1) range at low prevalence
   (T16).
2. **Where absolute rates are tiny, show lift vs base rate,** always with counts and intervals:
   Wilson intervals for rates, t-intervals for means.
3. **Grey out, never hide,** bins and cells with too little support, and say so: bins and levels
   below `MIN_BIN_SUPPORT = 20` in the deep dives, periods below `strata.min_events` in
   per-period lines. The interval is still drawn.
4. **Quantile groups** for numeric features, merged from the cells by cumulative row share
   (`merge_bins`: about ten groups for lift, twenty for histograms); a bin holding at least
   `1 / groups` of the rows (0 and the dominant value whenever they reach it) stays its own bar,
   never widened into a neighbour, so the count can exceed the target by such interior bars;
   never equal-width bins (T25). A group's label joins its first and last bin labels (`< e`,
   `[e, e)`, `≥ e`, `= v`, `(v, e)`, `> v`; six significant digits). **Log axes** for heavy
   tails, never with a zero quartile or a zero bar on them (T30): offset, linear axis or a
   separate zero share.
5. **No chart whose bars are all near zero.** Switch to lift, a log axis or a table.
6. **One colour per target class, segment or model** across a whole report; comparisons overlay
   on shared axes.
7. **The null bin is its own bar, labelled `null`;** a level table lists `null` as a level. Nulls
   never vanish from a chart.
8. **Distributions are box plots from quartiles**, never raw points or raw histograms.
9. **Per-period lines** mark every compared period; the label-free periods show no label-based
   value.

### Theme
`THEME` is a dict: the neutral palette, the fonts and the categorical colour sequence. The path
`environment.theme` exists in the environment config and is read in M4.

### Dependencies
- plotly 6.3.1 (pinned), bundling plotly.js 3.1.1: 4.83 MB embedded per report (measured locally).
- pandas Styler needs jinja2 3.1.6 (in the devcontainer; pinned on first use, D-012): the
  plan's dependency step.

### Code map
- `src/core_modelling/reporting/html.py`: the writer (`write_report`, `figure_html`,
  `style_table`).
- `reporting/charts.py`: the five primitives, each one function returning a figure.
- `reporting/blocks.py`: `CHOICES` (plain data: label, config path, alternatives, when to move),
  `choices_block`, `headline`, `warnings`, `appendix`.
- `reporting/theme.py`: `THEME`.
- Each stage builds its own sections from its tables ([EDA](eda.md),
  [feature checks](feature_checks.md)).
- Reading order for review: `write_report`, then one chart primitive against the chart rules, then
  `choices_block`.

### Interface
No public reporting function in Stage 2: reports are written by `run_eda` and
`run_feature_checks`, and notebooks display `StageResult.views` (D-137).

```python
def write_report(title: str, sections: list[tuple[str, list]], path: str) -> str: ...
def figure_html(fig: go.Figure, div_id: str) -> str: ...
def style_table(df: pd.DataFrame, ...) -> Styler: ...
def choices_block(resolved: UseCaseConfig, choices: list[dict]) -> Styler: ...
```

`write_report` returns the written file's path.

### Lessons from the crunch
- T16: fixed chart ranges at low prevalence showed nothing (chart rules 1, 2, 5).
- T17: decide view × model-family compatibility up front, never wrap a view in try/except
  (requirement 2.3).

## Open questions
- OD-12 (the core views per task): this spec fixes them for the EDA and Feature Checks reports;
  Evaluation's are decided in M2.3.
- Unverified until the plan's spike: JupyterLab's "Trust HTML" behaviour and showing a 5 MB file
  in an IFrame from a notebook.
- Unverified: whether plotly renders in the bank's JupyterLab and how fast a report opens there;
  both show in the SDS's JupyterLab test inside the bank (D-036).
