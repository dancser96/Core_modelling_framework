# Reporting and model card
**Status:** built in part 2026-11-04 (Stage 2 major step 2: the renderer, the five primitives and `side_by_side`, the blocks and the theme, built with the EDA report; reviews 2 and 3 applied 2026-11-05/06; the Feature Checks report and `formats.py` built 2026-11-06, major step 3); the four explanation charts built 2026-11-16 (M2.3 major step 2); the model results report, the model charts, `effect_chart`, `pdp_ice_chart` and the model card built 2026-11-17 (M2.3 major step 3) · **Legacy:** `src/card.py`, `src/analysis.py` plotting helpers
**Related:** [EDA](eda.md) · [feature checks](feature_checks.md) · [feature ledger](feature_ledger.md) ·
[evaluation](evaluation.md) (the tables behind the model results report) · [training](training.md)
(the sign-off and search views) · [model bundle](model_bundle.md) (the run folder the card reads) ·
[monitoring](monitoring.md) · [lifecycle](lifecycle.md) · [config](config.md) (template
explanations, audit log, `evaluation.skip_views`) · [environment](environment.md) (theme) ·
D-012, D-020, D-031, D-032, D-035, D-036, D-052, D-083, D-136, D-137, D-141 · OD-12 is settled
for every report (Evaluation's views by D-141)

Read it in three levels: Level 1 gives the essentials, Level 2 how the parts connect, Level 3
every detail.

## Level 1: Summary
One shared renderer turns any stage's results into a **self-contained HTML report**: pandas Styler
tables and plotly charts, plotly.js embedded once per file so a report opens offline inside the
bank. Every report has the same four parts: **summary → core → extended → appendix** (D-036).
Stage 2 builds the renderer, the chart primitives, the shared blocks and a neutral theme
(`src/core_modelling/reporting/`, built 2026-11-04 with the EDA report), and two reports with
them: `eda/report.html` and `feature_checks/report.html`, each beside its stage's
artifacts (D-136). Every figure is
pre-aggregated except four capped explanation charts, there is no cap on figures, and a report
regenerates from the resolved config.
Notebooks display the same objects (`StageResult.views`) and never assemble a report. M2.3 adds
the **model results report** (`evaluation/report.html`; its views are listed under "The model
results report" and counted in [evaluation](evaluation.md)), its seven model charts and the
SHAP-style charts in plotly, and the generated **model card**
(`model_card.json`, versioned, and a tables-only `model_card.html` without plotly.js).

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
Each stage is standalone and writes its own file; the Feature Checks summary repeats EDA's
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

### The model results report and the model card
- **The report** is Evaluation's: summary (the headline, the choices, the model beside each
  baseline, how to read, what these numbers cannot say, the warnings) → core (metrics per
  period, curves, capture, reliability, score distribution, strata, the importance bar, the
  beeswarm, effects, waterfalls, Training's sign-off and search views) → extended (thresholds,
  permutation importance per cluster, PDP and ICE, validation on test clients only) → appendix.
  Each view is one row of Evaluation's `VIEWS` table (`evaluation/report.py`: its title, its
  section and the view function, or per task the function or the reason the task cannot produce
  it); the names are the ones `evaluation.skip_views` takes. A view a task cannot produce reads
  "Not available: reason." (D-035); every view but the summary can be skipped. Training's warnings
  show in the summary's warnings under "From Training"; the card's considerations do not carry
  them (Open questions).
- A run builds the views once (`report_views`, kept in `StageResult.views`) and renders them
  with `render_views`; a page renders again from the stored tables, so from `evaluation/`
  without Spark.
- **The model card** is built by `evaluation/card.py` from the run folder, Evaluation's tables
  and meta and the resolved config, and rendered by `reporting/card.py`: generated facts, no
  free text.
- The charts behind them: `model_charts.py` (curves and distributions from Evaluation's
  tables) and `explain_charts.py` (the SHAP-style charts, `effect_chart` and `pdp_ice_chart`),
  one figure for the notebook and the report.

### Modules and main functions
`src/core_modelling/reporting/`:
- `html.py`: `render_report(title, sections, plotly=True) -> str`, `paragraph(text)`,
  `preformatted(text)`, `figure_html(fig, div_id) -> str`, `table_html(styler, uuid) -> str`,
  `style_table(df, formats, lift, greyed, bar, caption, bar_min) -> Styler`;
- `charts.py`: `bar_with_intervals`, `lift_chart`, `box_from_quartiles`, `grouped_lines`,
  `heatmap`, each returning a plotly figure with the chart rules applied, and `side_by_side`,
  which sets two of them as one figure of two panels (details under "The chart primitives");
- `formats.py`: how numbers read in a table, shared by every report: `format_of(name, task)`
  (a column's format by name, from the shared column lists `CONCORDANCES`, `SHARES`,
  `THREE_DECIMALS`, `PLAIN`, `P_VALUES`, `ESTIMATES` and the prefixes; the one place a name gets
  its format, a pivot's cells included), `column_formats(df, task)` (`format_of` per column),
  `plain_number(x)` and `p_value(x)`;
- `blocks.py`: `CHOICES` (31 rows), `choices_block(resolved, names, values) -> Styler`,
  `identity_values(meta)`, `headline(numbers, formats)`, `warnings_block(items)` (numbered),
  `not_available(reason)` and `appendix(resolved, decisions, seconds, caption)`, the resolved
  config, the audit log and the timings every report ends with; a stage adds its own appendix
  parts beside them;
- `model_charts.py`: `roc_chart`, `pr_chart`, `capture_chart`, `reliability_chart`,
  `score_distribution`, `metric_lines`, `predicted_vs_observed`, each from a table;
- `explain_charts.py`: `importance_bar`, `beeswarm`, `waterfall`, `dependence`, `effect_chart`,
  `pdp_ice_chart`, and `group_means` (the mean contribution per group, which Evaluation's
  effects table also uses);
- `card.py`: `render_card(card) -> str`, which refuses a card of another version, and the two
  constants it owns, `CARD_SCHEMA_VERSION` and `CARD_SECTIONS`; the card's content is
  `evaluation/card.py::build_card`;
- `theme.py`: `THEME`, the neutral palette, fonts, the colour sequence and the heatmap scales as a
  dict.

### How it is checked
Light tests: plotly.js appears exactly once in a rendered page; every `div_id` is unique;
`choices_block` reads its values from the resolved config; the chart rules asserted where testable
(axis ranges from the data, the null bar present, insufficient bins greyed, no WebGL trace). The
file size and the open time of both reports are measured locally on the canonical synthetic data
and recorded in the log. For M2.3: each model and explanation chart builds from a
constructed table; the beeswarm draws at most 1,500 seeded clients per feature and a missing
value grey; the package imports no `shap`; the report renders from stored tables with every
view, a skipped one left out and the summary never; the card is valid JSON of its schema
version, refuses pieces of another run or config, and its page embeds no plotly.js. Measured
locally: the model results report is 5.9 MB (binary) and 5.6 MB (regression), plotly.js most
of it.

## Level 3: Details

### Requirements and design constraints
1. **Self-contained HTML.** Styled tables (pandas Styler) and interactive plotly charts, plotly.js
   embedded once per file (no CDN, `CLAUDE.md` §5). That is about 4.8 MB per report before the
   figures; the size isn't optimised in Phase 2 (D-036).
2. **Every report has the same structure:**
   1. **Summary**, one page for business and governance readers: the choices block (the `CHOICES`
      rows that apply, with their values from the resolved config), the how-to-read notes, the
      headline numbers and numbered rule-based warnings (e.g. few positive events, a choice
      among variants made on test metrics, D-083). EDA has one events warning, with two
      thresholds: below 100 converting clients or 200 events ([EDA](eda.md)).
   2. **Core** views.
   3. **Extended** views, or "Not available: reason." where a view is declared incompatible up
      front (`CLAUDE.md` §1 rule 8).
   4. **Appendix:** the resolved config, the audit log and the run's housekeeping (collect log,
      entries written, timings). The origin of every entry-written value is the header
      `resolve_config(save_to=…)` writes into a saved `resolved_config.yml`, not the report's.
3. **Theme:** neutral in the repo (`THEME`); a theme file in `conf/local/` (palette, fonts, logo
   path) is read in M4, when the bank's theme is known. Nothing in the repo names a brand.
4. **Model card = generated facts only**, with a versioned schema (`CLAUDE.md` §2): written by
   Evaluation from the run folder, its own tables and meta and the resolved config, never typed
   by hand ("The model card" below). It is designed so a later generator can map it onto the
   internal model documentation standard.
5. **Every figure is pre-aggregated.** No row-level chart and no raw arrays in the HTML: bars come
   from the group tables, box plots from precomputed quartiles. Figures use plotly's `template="none"`, which keeps
   a 20-bar fragment at about 3.7 KB; the EDA report on the unit preset (161 candidates, 35
   figures) is 5.6 MB, of which plotly.js is 4.83 MB. The statistics behind every chart use the
   whole population (D-135). **Four named exceptions** draw clients, each capped, from the
   explanation sample, a missing value in grey:
   - the beeswarm: at most 1,500 seeded clients per feature (about 0.5 MB in the report);
   - the dependence scatter: at most 1,500 seeded clients per feature;
   - the waterfall: one client per chart, three charts;
   - the ICE lines of `pdp_ice_chart`: 50 sample rows spaced evenly through the sample, each a
     line over the feature's grid of at most 20 points, beneath the partial dependence line.

   Any other row-level chart would be a new named exception, drawn on a seeded sample of at most
   10,000 rows that its caption states.
6. **No cap on figures**; the size and the open time are measured instead.
7. **Reports regenerate from the resolved config** and the stage's artifacts, never from a
   notebook (D-039). Decisions are read from the audit log when the report is written, never
   stored ([feature ledger](feature_ledger.md)).
8. **How-to-read notes,** in the summary of every report that shows a concordance, five short
   paragraphs. EDA's (`_how_to_read`, beside its report) are below; the Feature Checks report writes
   its own five (concordance read in the window's direction, a flag, a note, grey, `null`; [feature
   checks](feature_checks.md) "The report"), and so does the model results report ("The model
   results report" below):
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
the skipped steps and the compared periods. The report never suggests a verb for a flag;
for near-duplicates it names the trade-off and leaves the choice to a person. Each view's
columns and wording: [feature checks](feature_checks.md) "The report".

### The model results report
Written by Evaluation as `evaluation/report.html`, from the tables of [evaluation](evaluation.md)
alone: Training's tables the report draws are stored among them (`training_signoff`,
`training_trials` and `training_explanation_sample`), so the page renders again from
`evaluation/` without Spark. Every view renders by default; `evaluation.skip_views` leaves any
of them out by its `VIEWS` name, except the summary, and a name that is no view is refused
before anything is scored (`check_skip_views`). The table's order is the page's: the summary,
the core views, the extended views, then the appendix. Every metric shows test and validation, each cell as
"value (low to high)" with its client-bootstrap interval (`views.py::interval_text`): a value
the data leave undefined reads `undefined`, and a value whose metric was undefined in at least
one bootstrap replicate reads "value (no interval)" (D-083: validation is shown everywhere,
never chosen on). A regression's `deviance` is named by the run's row loss (`meta["row_loss"]`,
e.g. `tweedie_deviance`) and left out when the run has none (`labelled_metrics`), in views 1, 2
and 17. A view the task cannot produce reads "Not available: reason." (D-035); the table stores the
reason bare and `not_available` adds the prefix and the full stop. The views are in `evaluation/views_summary.py` (1), `evaluation/views.py` (2–7, 12–14,
17) and `evaluation/views_explain.py` (8–11, 15, 16).

| # | Name | What it shows | Regression |
|---|---|---|---|
| 1 | `summary` | the run, its model and what it was scored on; the headline (the run, its training date and, per part, `decision.metric` and AUC with their intervals); the choices block and the settings it has no row for (the baselines, the single feature chosen, the intervals, the explanation cut); the model beside each baseline per part and metric, a reason where a baseline cannot fill a cell, no "passed" or "failed"; how to read; what these numbers cannot say; the warnings, Evaluation's first, then Training's under "From Training" | the concordance for AUC |
| 2 | `metrics` | every metric per part and period with its interval: test's periods, the validation period, test pooled, the periods' mean last; `metric_lines` of `decision.metric` per period; a period below `strata.min_events` greyed | the regression metrics |
| 3 | `curves` | ROC and precision–recall, one line per part, on all of the part's rows | not available: no classes |
| 4 | `capture` | the capture curve per part; the slice table: the declared slices, then the depths 1, 2, 5, 10, 20, 30 and 50%, each cut inside each period and added up over the part's periods, with capture, rate and lift each with its interval; an unavailable slice leaves them empty beside its reason | the capture of the amount, the mean for the rate |
| 5 | `reliability` | `score` against the observed rate in 10 quantile groups of the score (T16); observed to expected, the calibration slope and intercept pooled per part beside it; a note on a part under 200 events | predicted against observed in 20 groups of the prediction (`predicted_vs_observed`), predicted to observed beside it |
| 6 | `score_distribution` | per class, its share in a score bin over the bin's share of all rows (1 is chance) against the score's percentile, one panel per part | not available: no classes |
| 7 | `strata` | per stratum variable, part and level: support, AUC and observed to expected, then at the decision's slice the level's share of the population, its share of the list and the capture inside it; greyed below `strata.min_events` positive rows (`TASK_SPECS[task]["events_noun"]`); a note that no test runs across levels and that a level's metrics use coarser score bins than the pooled ones (binary: every fourth edge, `STRATA_STEP`), so its ordering metrics read slightly lower | RMSE, MAE and predicted to observed per level, greyed below `strata.min_events` rows with a non-zero target; the levels keep the full score grid |
| 8 | `importance` | `importance_bar`: contribution shares, test beside train out of fold | the same |
| 9 | `beeswarm` | the top 15 features, at most 1,500 seeded test rows, the same for every feature | the same |
| 10 | `effects` | per effect feature (the model's ten largest by Training's out-of-fold contribution share plus EDA's key features it uses, twenty at most): `effect_chart` from the effects table, the mean contribution per EDA group beside EDA's lift, a count of the sample rows no group covers, and a level table for a categorical; the `dependence` scatter with the reason from the feature's `unavailable` cell in the effects table (not one of EDA's key features, or EDA's base is not positive) | the same |
| 11 | `waterfalls` | three rows: the highest score of test, the row at the decision's cut, a typical row (the sample's median score); labels read `feature = value` | the same |
| 12 | `sign_off` | Training's sign-off view, train-only: the final list by out-of-fold contribution, the held and the excluded features with their reasons, the wrong-sign warnings | the same |
| 13 | `search` | `search_table` per family and the best fold metric so far against cumulative seconds, one line per family ([training](training.md)); Training's seconds per step | the same |
| 14 | `thresholds` | per part, at the score threshold where the list first reaches each capture depth: the threshold, depth, rows, target captured, capture, rate, lift and false positive rate | not available: no classes |
| 15 | `permutation_importance` | per redundancy cluster, the loss change when its members are permuted together on the permutation sample, up to 50,000 seeded test rows, of which the first 5,000 are the explanation sample (the mean of five seeded permutations) with its standard deviation (`loss_change_sd`; a change within it is noise), beside its contribution share and rank; Spearman's rank correlation of the two orders; the three largest rank gaps marked; "Not available: reason." when `meta["unavailable"]` names it: fewer than `strata.min_events` events in the sample (the count is shown), a target of one value, or a deviance metric under an objective without a log link ([evaluation](evaluation.md#the-explanation-tables)) | the same |
| 16 | `pdp_ice` | `pdp_ice_chart` for view 10's features | the same |
| 17 | `validation_test_clients` | the validation period's metrics on all of its clients beside its test-split clients only: unseen clients and an unseen period | the same |

Views 8–11 open with a line on the margin's scale the contributions are on: the log-odds, the
log scale of a Tweedie or Poisson objective, or the prediction's own scale. The objective is
the run's own (`meta["choices"]["objective"]`), since a named run may have been trained under
another config.

**How to read** (the summary's five notes, requirement 8):
- concordance: how well the score orders clients by the target, 0.5 no better than chance and 1
  a perfect ordering; for a yes/no target it is the AUC;
- lift: a slice's rate (regression: mean) divided by its part's, 1 the part's level;
- intervals: the level and the replicates of the client bootstrap (a client's rows move
  together), written after each value as "value (low to high)" and drawn as error bars;
  `undefined` where the data leave a metric without a value, "(no interval)" where it was
  undefined in at least one replicate;
- grey: fewer than `strata.min_events` positive rows (regression: rows with a non-zero
  target) in a period or a level, still shown; an outcome counts once in every period whose
  target window holds it, so a pooled row can count it up to the window's length; read the
  interval, not the point;
- null: a missing feature value, grey in the explanation charts and its own group, last.

**What these numbers cannot say** is a list in the summary; its statements and why each holds
are in [evaluation](evaluation.md) → "What the report states".

**The appendix:** the resolved config, the audit log's entries, the frames collected (one
row per `collect` step of the stage's log: the frame, its rows and columns, the estimated and
measured bytes, the budget) and the seconds per phase.

### The model card
Built by `evaluation/card.py::build_card(run_folder, tables, meta, resolved)` and rendered by
`reporting/card.py::render_card(card)`. Evaluation writes both files in the same `write_stage`
call as the rest of `evaluation/` (texts `model_card.json` and `model_card.html`), so they are
rewritten with it; a written run folder rebuilds the card from `read_stage`'s tables and meta
under the config Evaluation ran with.
- `model_card.json`: generated facts, never typed by hand: every value is read from the run
  folder (`run.json`, the bundle, `training/`, the per-run ledger, the `stage2/` copy),
  Evaluation's tables and meta, or the resolved config, and the card writes no sentence and
  parses none. It opens with `schema_version` (`CARD_SCHEMA_VERSION`, owned by
  `reporting/card.py` with `CARD_SECTIONS`, `CLAUDE.md` §2), then the sections in `CARD_SECTIONS`
  order; `render_card` refuses a card of another version. A missing value (None, NaN) is JSON `null`; an
  infinite one fails. The version is 2: `data.rows_per_period` holds the per-period rows only, with
  `rows_pooled` and `rows_validation_test_clients` beside it, and `framework_versions.card` is the
  framework version that wrote the card ([evaluation](evaluation.md)). What the card copies is
  declared in `evaluation/card.py`, never derived from another module's list: the metric rows'
  columns (`CARD_METRIC_COLUMNS`), the keys of each `folds` and `search` record and the
  calibration table's columns (`CARD_FOLD_KEYS`, `CARD_SEARCH_KEYS`,
  `CARD_CALIBRATION_COLUMNS`), and the score's column (`SCORE_COLUMN`, the literal `"score"`).
  A new Training column therefore cannot enter the card unannounced.
- `model_card.html`: the same facts as tables only, through `render_report(..., plotly=False)`,
  a small page without a script: per section a table of its single facts (a nested key
  dotted) and one table per list of records, a missing value blank; the schema version opens
  the details. An integer prints as it is (a seed is no quantity), a float through
  `plain_number`.
- **The card refuses** pieces that do not belong together, naming the fix. The run folder's
  part is `check_card_inputs(run_folder, resolved)`, which returns what it read as a
  `RunFolder`; Evaluation calls it before anything is scored and hands the result to
  `build_card`, which otherwise reads it itself, before it checks Evaluation's meta and tables:
  another run id
  across `run.json`, the manifest, `training.json` and Evaluation's meta; Evaluation's
  `model_hash` not the bundle's; Training's final features not the bundle's; a resolved config
  whose `config_hash` is not the one Evaluation ran with; another `run_schema_version`; a
  missing file, key or table; a warning without a code, from a run evaluated before the
  structured warnings ("evaluate it again").
- **Its shape follows the config schema:** `intended_use`, `data.split` and
  `performance.intervals` hold config sections as the resolved config dumps them, and
  `training.path` and a time budget are read from `training.json`'s settings under the dotted
  path `training`; a config schema change to those sections is a card schema change.
- **Sections** (`CARD_SECTIONS`):
  - `details`: the model key (None until `register`), the use case, domain, entity, task and
    run; the parent run and its metrics (None until a refit, M2.4, D-052); the family, the
    library versions and the framework versions (Training's and the card's); the hashes
    (`model_hash`, `recipe_hash`, `feature_signature`, `config_hash`, `data_definition_hash`,
    `resolved_input_hash`, `hash_version` and the evaluation's `config_hash`); the Stage 2 runs;
    the dates (run started, trained, card written). Who started the run is not in the card.
  - `intended_use`: the decision, the slices, the population (each eligibility step with its
    list), the target with its window and period, and the score: its column, what it estimates
    and that it is conditional on staying through the target window.
  - `data`: the logical sources (features, target, model input), the period, the observation
    window, the validation period, the eligible rows per period, each part's rows and events per
    period, the split, the sampling and the train folds.
  - `features`: the final list from Training's sign-off table (kind, source, out-of-fold and
    test contribution share, the model's and EDA's direction, the monotone constraint), the held
    with their open flags, the excluded with the `exclude` entry and its reason, the kept with
    Feature Checks' flags and whether the model uses them.
  - `training`: the path, each family's search, the train-side metrics (the out-of-fold metric,
    the out-of-fold and in-sample concordance), the recipe without the encoder and the features
    (the recipe hash covers them), the calibration fitted, each calibration method compared, and
    what the run reproduces to.
  - `performance`: the headline metrics' names, the intervals' level and replicates, the long
    metric rows (`CARD_METRIC_COLUMNS`: metric, part, period, stratum, level, value, low, high,
    rows, events, insufficient) and the
    baselines comparison (scorer, part, metric, value, low, high, `available`); no gates.
  - `considerations`: codes with their values, no text: Evaluation's warnings
    (`meta["warnings"]` without their `text`), then those the recorded facts raise:
    `validation_period_moved` (earlier Evaluation runs scored another validation period),
    `reproducible_to_recipe` (a time budget), `monotone_against_eda`, `pruning_undone`.
  - `sign_off` and `lifecycle`: empty (`{}`) until `decide` and `register` fill them in M2.4.

### The renderer
- A section is `(heading, blocks)`; a block is a Styler, a plotly figure, a str (an HTML
  fragment, inserted as is: `paragraph`, `preformatted`, `headline`, `warnings_block`,
  `not_available`) or a `(heading, blocks)` tuple, a subsection with its own anchor; anything
  else, a views dict passed unconverted among them, fails naming its type. The four parts are
  the top-level sections.
- plotly.js is embedded once from `plotly.offline.get_plotlyjs()` in one `<script>`
  (`plotly=False` embeds none, for a page of tables only: the model card); each figure
  is rendered with `include_plotlyjs=False, full_html=False` and its own `div_id`
  (`figure_html`). `include_plotlyjs=False` with `full_html=True` gives a broken page.
- Tables go through `Styler.to_html(table_uuid=…)`, which renders a copy: the caller's Styler, which
  a notebook also displays, keeps its own uuid and CSS ids. Styler raises above
  `styler.render.max_elements` = 262,144 cells (the ledger is far below). Numbers read by
  `formats.format_of`: a value column (quantiles, medians, a finding's value and threshold) prints
  through `plain_number`, with thousands separators from 1,000 and four significant digits below,
  never in scientific notation; a p-value below 0.0001 reads "< 0.0001". The headline reads like the
  tables below it: each number takes the format its table column uses, passed by the caller (the
  task's estimate format for a rate or a mean, the share format for a share; EDA's headline through
  `eda.population.headline_formats`), and a number without a format fails.
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
   concordance around 0.5) uses the data's span (`from_zero=False`). A reliability chart takes one
   range on both axes, from zero to 1.25 × its highest predicted or observed value, the diagonal
   clipped to it. Never use a fixed (0, 1) range at low prevalence (T16); the ROC and capture
   charts keep [0, 1] because they are read against the diagonal, not as rates.
2. **Where absolute rates are tiny, show lift vs base rate,** always with counts and intervals:
   Wilson intervals for rates, t-intervals for means.
3. **Grey out, never hide,** bins and cells with too little support, and say so: bins and levels
   below `MIN_BIN_SUPPORT = 20` in the deep dives, periods below `strata.min_events` in
   per-period lines. The interval is still drawn.
4. **Quantile groups** for numeric features, merged from the cells by cumulative row share
   (`merge_bins`: about `strata.max_levels` groups in a deep dive, 10 by default); a bin holding at least
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
8. **Distributions are box plots from quartiles**, never raw points or raw histograms. The
   exceptions are requirement 5's: the beeswarm and the dependence scatter draw capped seeded
   clients. A score distribution is drawn per class as its ratio to chance (the class's share in
   a score bin over the bin's share of all rows) against the score's percentile, so a rare class
   reads on the same scale as a common one; unequal score bins would make raw shares step.
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

### The model charts
`reporting/model_charts.py`, each taking one of Evaluation's tables (`pd.DataFrame`) and
returning a `go.Figure` with the chart rules applied; none reads rows. Each part keeps one
colour in every chart (test, then validation, then any other part), present or not; a missing
column fails naming the chart.
- `roc_chart`: capture (the true positive rate) against the false positive rate, one line per
  part, the random diagonal dashed; both axes [0, 1].
- `pr_chart`: precision against recall, one line per part, each part's base rate a dashed
  line; the y axis follows the data from zero (rule 1).
- `capture_chart`: capture of the target (events, or the amount) against depth per part, the
  random diagonal dashed and muted (rule 9).
- `reliability_chart(reliability, axis_format=".1%")`: observed against predicted per group,
  one line per part, the diagonal clipped to the shared range (rule 1); it greys no group.
- `predicted_vs_observed`: regression, mean observed against mean predicted in 20 groups of the
  prediction, the same frame as the reliability chart.
- `score_distribution`: per class its ratio to chance against the score's percentile, a dashed
  line at 1, one panel per part (rule 8); the bin's mean score in the hover. The panels share
  one y axis, so only the first carries its title.
- `metric_lines(metrics, from_zero=False, y_format=None, reference=None)`: one metric by period
  with its interval, one line per part, the validation period a period of its own part; the
  pooled row left out, an insufficient period greyed; a table of two metrics is refused.

### The explanation charts
`reporting/explain_charts.py`: the four familiar SHAP-style charts, `effect_chart` and
`pdp_ice_chart`, drawn in plotly from the
libraries' own contributions (D-141 (f)), one implementation for the notebook and the report;
the package imports no `shap`. They take `shap`'s colours, so a DS recognises them at once (red
raises, blue lowers; blue to red for a low to high feature value), and the house fonts, titles
and margins. A missing value is `null` and grey in every one of them. Every axis is titled, a
feature value in a label or a hover never reads in scientific notation (labels through
`plain_number`, hovers in d3's `,.4~r`: four significant digits, thousands separators, no
trailing zeros; 123,456 reads 123,500 there), and a waterfall step keeps its size
(`+0.0001234`, never `+0.00`).
- `importance_bar`: each feature's share of the mean absolute contribution, the `top` (15)
  largest and the rest summed in one bar; the y axis is titled "Feature". With `compare` (train
  out of fold beside test) each feature gets a second bar, its shares from its own frame, in the
  part colours of the model charts (`part_colour`: test the first sequence colour, validation's place
  kept, train out of fold the third), so no bar takes the red that means "raises the score". A
  frame of only zero contributions fails loud.
- `beeswarm`: one point per sampled row and feature, coloured by the feature's value; at most
  1,500 seeded rows (`ROW_CAP`), the same rows for every feature; the y axis is titled
  "Feature". A `clients` outside 1…1,500 is refused.
- `waterfall`: one row from the base value to its margin, on the margin's scale for both tasks:
  the `shown` (9) largest contributions and the rest as one bar, labelled `feature = value`; the
  y axis is titled "Feature = value".
- `dependence`: a scatter of the contribution against the raw value for at most 1,500 seeded
  rows, coloured by a second feature when `colour` is given; a missing value sits in its own
  `null` strip, drawn only when a sampled value is missing. There is no background histogram and
  no lift mode: a feature with EDA groups is `effect_chart`'s.
- `effect_chart(table)`: one feature's mean contribution per group with its 95% interval (a
  group under 20 sample rows greyed) beside EDA's lift by the same groups, two panels
  (`side_by_side`). It takes one feature's rows of Evaluation's effects table
  (`evaluation/effects.py`), which assigns each sample row its EDA group
  (`statistics/distributions.py::bin_orders`, the counts table's bucket) and computes the means
  with `group_means`, the function `dependence` uses too.
- `pdp_ice_chart(table, y_format=None)`: one feature's partial dependence (the mean score over
  the sample at each grid point) as a thick line over its ICE lines (each sampled row's scores),
  thin and muted; a categorical as points per level in grid order. It takes one feature's rows
  of Evaluation's `partial_dependence` table; the y axis follows the data's span, in the task's
  `axis_format`.

A DS who wants `shap`'s own pictures builds a `shap.Explanation` from the stored contributions in
three lines; the helper notebook shows how.

### Theme
`THEME` is a dict: the neutral palette, the fonts, the categorical colour sequence and the
colours of the target classes, `null`, insufficient support, lift, the heatmaps and the
contribution pair (raises and lowers, and the low-to-high value scale). Tables read on
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
  `side_by_side`. `apply_theme` (the shared theme and layout) and `axis_range` (the axis that
  follows the data, rule 1) are public names inside `reporting/`, since three modules use them;
  they are not part of the package's Public API.
- `reporting/blocks.py`: `CHOICES` (plain data: label, config path, alternatives),
  `choices_block` (the "metric" row shows `decision.metric`, filled at load from the task and
  `decision.type` when the config leaves it null), `identity_values`, `headline`, `warnings_block`, `not_available`,
  `appendix`.
- `reporting/formats.py`: `format_of`, `column_formats`, `plain_number`, `p_value` and the shared
  column lists.
- `reporting/theme.py`: `THEME`.
- `reporting/model_charts.py`: the seven model charts, each one function from a table.
- `reporting/explain_charts.py`: the four SHAP-style charts, `effect_chart`, `pdp_ice_chart`
  and `group_means`.
- `reporting/card.py`: `render_card`, `CARD_SCHEMA_VERSION`, `CARD_SECTIONS`.
- `reporting/training_views.py`: `search_table(trials, metric)` and the sign-off view, shared by
  the Training and the model results reports.
- Each stage builds its own sections from its tables ([EDA](eda.md),
  [feature checks](feature_checks.md), [evaluation](evaluation.md)). The model results report:
  - `evaluation/report.py`: `VIEWS` (one row per view: its title, its section and its function,
    or per task the function or the reason it is not available), `check_skip_views`,
    `report_views`, `render_views` (the four parts and the appendix);
  - `evaluation/views_summary.py`: `summary_view`, `baseline_table`;
  - `evaluation/views.py`: the core and extended views of the metrics, `CALIBRATION_CHARTS` (per
    task the calibration chart; the calibration metrics, the events note's floor, the strata
    metrics and the summary's task statement are `TASK_SPECS` entries), `interval_text`,
    `wide_metrics`;
  - `evaluation/views_explain.py`: the six explanation views;
  - `evaluation/card.py`: `check_card_inputs`, `build_card`; the `RunFolder` they pass is
    `run_artifacts.py`'s.
- Reading order for review: `render_report`, then one chart primitive against the chart rules, then
  `choices_block`; for M2.3, `report_views` and `render_views`, then `summary_view`, then
  `build_card` with its refusals.

### Interface
No public reporting function: reports are written by `run_eda`, `run_feature_checks` and
`run_evaluation`, notebooks display `StageResult.views` (D-137), and EDA's exploration
functions draw with these primitives ([EDA](eda.md) "Interface").

```python
def render_report(title: str, sections: list[tuple[str, list]], plotly: bool = True) -> str: ...
def figure_html(fig: go.Figure, div_id: str) -> str: ...
def table_html(styler: Styler, uuid: str) -> str: ...
def style_table(df, formats=None, lift=None, greyed=None, bar=None, caption=None,
                bar_min=0.0) -> Styler: ...
def choices_block(resolved: UseCaseConfig, names: list[str],
                  values: dict[str, object]) -> Styler: ...
def identity_values(meta: dict) -> dict[str, object]: ...
def headline(numbers: dict[str, object],
             formats: dict[str, str | Callable[[float], str]]) -> str: ...
def not_available(reason: str) -> str: ...
def appendix(resolved: UseCaseConfig, decisions: pd.DataFrame, seconds: dict[str, float],
             caption: str) -> dict[str, str | Styler]: ...
def side_by_side(left: go.Figure, right: go.Figure, height: int = 380) -> go.Figure: ...
def format_of(name: str, task: str) -> str | Callable[[float], str] | None: ...
def column_formats(df: pd.DataFrame, task: str) -> dict[str, str | Callable[[float], str]]: ...
def plain_number(x: float) -> str: ...
def p_value(x: float) -> str: ...

# model_charts.py: roc_chart, pr_chart, capture_chart, score_distribution, each
# (pd.DataFrame) -> go.Figure
def predicted_vs_observed(reliability: pd.DataFrame, *, groups: int) -> go.Figure: ...
# groups: the task's reliability_groups, named on the x axis
def reliability_chart(reliability: pd.DataFrame, axis_format: str | None = ".1%") -> go.Figure: ...
def metric_lines(metrics: pd.DataFrame, from_zero: bool = False, y_format: str | None = None,
                 reference: float | None = None) -> go.Figure: ...
def importance_bar(contributions: pd.DataFrame, compare: pd.DataFrame | None = None,
                   top: int = 15) -> go.Figure: ...
def beeswarm(contributions: pd.DataFrame, values: pd.DataFrame, top: int = 15,
             clients: int = 1500, seed: int = 0) -> go.Figure: ...
def waterfall(contributions: pd.Series, base: float, values: pd.Series,
              shown: int = 9) -> go.Figure: ...
def dependence(contributions: pd.Series, values: pd.Series,
               colour: pd.Series | None = None) -> go.Figure: ...
def effect_chart(table: pd.DataFrame) -> go.Figure: ...
def group_means(contributions: pd.Series, groups: pd.Series, order: list[str]) -> pd.DataFrame: ...
def pdp_ice_chart(table: pd.DataFrame, y_format: str | None = None) -> go.Figure: ...
def render_card(card: dict) -> str: ...                            # reporting/card.py

# evaluation/report.py and evaluation/card.py
def check_skip_views(cfg: UseCaseConfig) -> None: ...
def report_views(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> dict: ...
def render_views(views: dict[str, list], meta: dict, resolved: UseCaseConfig, log: list[dict],
                 decisions: pd.DataFrame) -> str: ...
def check_card_inputs(run_folder: str, resolved: UseCaseConfig) -> RunFolder: ...
def build_card(run_folder: str, tables: dict[str, pd.DataFrame], meta: dict,
               resolved: UseCaseConfig, read: RunFolder | None = None) -> dict: ...
```

`render_report` returns the page; the stage writes it with `artifacts.write_stage(result,
folder, name, texts={"report.html": page})`. Evaluation's texts are `report.html`
(`render_views` of the views the run built, with its log and `show_decisions`' table),
`model_card.json` (`json.dumps(card, indent=2, allow_nan=False)`) and `model_card.html`.

### Lessons from the crunch
- T16: fixed chart ranges at low prevalence showed nothing (chart rules 1, 2, 5).
- T17: decide view × model-family compatibility up front, never wrap a view in try/except
  (requirement 2.3); SHAP failed across the crunch's estimators, so the explanation charts draw
  the libraries' own contributions.

## Open questions
- Unverified: the explanation charts' hover text, and how they look in the bank's JupyterLab
  (spike 5). The waterfall's bars are rectangles with a small arrow head, not `shap`'s arrows.
- The card's considerations carry Evaluation's warnings and the facts above, not Training's
  warnings, which `training.json` stores as sentences (the report shows them under "From
  Training"); storing them as codes with values is a Training artifact change for the EDS's
  review.
- The effects table finds a numeric's EDA group by parsing the group label's opening bound;
  EDA storing each group's first bin and the lift's interval in `bins` and `levels` (an EDA
  schema change) would retire the parsing. For the EDS's review.
- Decided for notebook 02: the notebook displays `StageResult.views`, which read on a light and
  a dark page ("Theme"); the report opens in a browser, not inline: the notebook shows the
  report's path and how to open it ("Trust HTML" in JupyterLab, or an `IFrame` with `srcdoc`;
  the report is about 6 MB, so no live cell duplicates it in a shipped notebook).
  Unverified in the bank's JupyterLab: whether the charts run under "Trust HTML" or in `srcdoc`.
- Unverified: whether plotly renders in the bank's JupyterLab and how fast a report opens there;
  both show in the EDS's JupyterLab test inside the bank (D-036).
