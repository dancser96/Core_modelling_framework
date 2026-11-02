# Stage 2 (M2.2 Understanding): design questions
_Written 2026-10-30 for the SDS · Q418–Q462 · cited decisions are summarised in brackets
(D-072 (k)) · outcomes go to `docs/` and to `plan.md` beside this file; the folder is deleted when
the stage is done · answers in chat, by number; a question stays until answered_

**Where it stands (2026-10-30): round 1, every question open.** Stage 2 is M2.2 Understanding:
EDA, Feature Checks, the feature ledger and Reporting, with their two notebooks and the trap
acceptance test. The plan sized it at four days (11-03 – 11-06) and "thin" (D-022 (the Phase 2
plan: skeleton first, two deepening rounds)). You asked for something between thin and deep with
every key component in, and for every check and every view to be named explicitly. Section 0
is that catalogue; the questions follow it top-down: scope and time, then the shape of the code,
then the statistics, then each stage's content, then the ledger, reporting, notebooks and tests.
Every question has a default; "default" means what the plan assumes if you say nothing.

**What the research found** (four surveys, 2026-10-30; details in `worknotes/log.md`):
- The crunch's EDA and checks (legacy survey): every statistic skipped categoricals (VIF, MI,
  AUC and PSI alike, T10); every statistic ran after median imputation, so missingness leaked
  into the signal; the univariate AUC was implemented twice; no cardinality check, no automatic
  lineage exclusion (a hand-typed list, T12), no T11 check (VIF silently dropped constant
  columns); every threshold was a code or notebook literal (0.95, 0.03, 0.25, 0.98, 0.5, 0.9);
  signal persistence used the OOT month's labels for a feature decision; charts had fixed 0–1
  ranges and raw-count overlays (T16); the model card recorded a feature count only.
- The synthetic traps (trap survey, measured on the `dev` dataset): the two `leak` columns have
  AUC 0.97 and 0.87 against an oracle ceiling of 0.84; the `missing_leak` column's fill
  indicator has AUC 0.89; **the `shifted` and `process_leak` columns have AUC 1.00 and 0.90
  against a one-month target but only 0.70 and 0.67 against the three-month target**, i.e.
  below the oracle, so a "too strong" screen cannot catch them under `w = 3` and the
  time-alignment step must; the `redundant` column has Spearman 0.99997 with its source;
  `high_cardinality` has 300 levels; the null controls sit at AUC 0.50 ± 0.01; under the card
  eligibility (`cc_flag = 0`) eleven card columns are exactly constant and one all null (T11).
- The package after Stage 1 (interface survey): nothing distinguishes numeric from categorical
  columns yet; `run` hands stages the raw config (no replay) and writes no resolved config;
  `period` reaches pandas as `datetime.date`; there is no helper for the gap periods or the
  latest period; `features.excluded` is validated but not applied anywhere (by design: EDA and
  Feature Checks work on the candidates); the `flag`, `dropped`, `run` and `sign_off` operations
  exist in the entry schema with no writer.
- Best practice (research survey with web sources; the Evidence lines below cite them): no
  primary source gives numeric leakage thresholds (Kaufman et al. 2012: leakage is about *when*
  a value is known, so a strength screen misses some leaks; DataRobot flags a normalised
  univariate strength at 0.85); the PSI bands 0.10 / 0.25 are Lewis's 1994 constants, which
  ignore the sample size and the bin count (n·PSI is χ² under no shift); the common
  redundancy screen is |ρ| ≥ 0.9; scorecard practice drops above 95% missing; Wilson intervals
  come from `scipy.stats.binomtest(...).proportion_ci(method="wilson")`, no statsmodels needed;
  standardised mean differences (|SMD| 0.1 balanced, 0.25 the loose cut, Austin 2009) are the
  standard two-group comparison; no published per-feature audit schema exists (SR 11-7 asks
  for evidence and traceability, not fields). **Two corrections for us:** (i) the standard error
  of a univariate AUC at the null is 1/√(12·events) ≈ 0.29/√events, not the 0.5/√events in
  `lessons.md` (a simulation at 800 events: 0.0105 measured, 0.0102 by the formula, 0.0177 by
  the lesson's rule), so the lesson is corrected (Q447b); (ii) at 50 events per period the null
  SE is about 0.04, so six periods show a concordance range of about 0.10 **from noise alone**,
  which rules out a raw-range stability flag (Q443). Measured locally on plotly 6.3.1: plotly.js
  3.1.1 is 4.83 MB; a 20-bar chart fragment is 7.6 KB, a box plot of 20,000 raw values 271 KB,
  so every chart is pre-aggregated (Q455). `jinja2` (pandas Styler's HTML) is not in the local
  venv (A11).

## 0. The proposal in one table: what Stage 2 builds, explicitly

Depth words as in `docs/roadmap.md` (thin · deep). "S2" = built in this stage; "M3" / "M4" =
left for the rounds named in `worknotes/timeline_proposal.md`.

| Component | S2 builds | Left for later |
|---|---|---|
| Shared statistics (`statistics.py`) | concordance per task (binary: univariate AUC; regression: Kendall concordance), Wilson intervals, PSI with a null bin, quantile bins, level encoding for categoricals, Cramér's V, standardised mean difference | weight-aware versions (Phase 3, D-117) |
| Per-task spec entries (`tasks.py`) | `concordance`, `summarise_group` (rate / mean with interval and lift), `min_support` (events / rows), `rare_value_effect`, `headline`; both tasks real, regression tested on a variant config | regression example config and end-to-end run (M4) |
| Dataset additions | column kinds from the Spark schema in the frames' meta; the label-free frame (gap periods + latest period, no `target`); `period_label`; the strata check | persisting the panel inside the bank (M2.4) |
| EDA | choices block and headline; funnel per period; target per period, by stratum, by reference group; the univariate ranking of every candidate; key-feature deep dives (bins with lift and intervals, distributions, level tables); reference-group comparison (composition + standardised differences); strata pivots for the top key features; `pivot_target` for notebooks; artifacts + report | window-ablation views, comparison across data definitions, the theme file (M4) |
| Feature Checks | steps `quality`, `leakage`, `time_alignment`, `stability`, `redundancy` with the findings of Q440–Q446 and low thresholds; rule `flag` entries in the audit log; open flags; proposed decisions; the periods compared recorded and the D-088 refusal built; artifacts + report | the `unstable` trap kind and stability depth (M4); screens on eligibility defines and tags (M4) |
| Feature ledger | the per-data-definition part as a versioned parquet (identity + EDA + checks columns), rendered with the audit-log entries per feature | the per-run part: selection and use (M2.3) |
| Reporting | one HTML writer (plotly.js embedded once, Styler tables, neutral CSS), the four-part structure, the choices block, the chart primitives (rate-by-bin with intervals, distribution by class, rate per period, level bars) | the theme file from `conf/local/` (M4); the model card (M2.3) |
| Run modes | `run_eda`, `run_feature_checks`, `pivot_target` public; `run --stages eda feature_checks`; notebooks `02_eda`, `03_feature_checks` with first-draft guidance | the guidance text reviewed with the LDS (M3) |
| Tests | statistics on hand-made frames; the trap acceptance test on the `unit` preset (kind → step); null controls unflagged and low-ranked; the label-free frame carries no label and no validation row; the D-088 refusal; a regression variant through both stages; the report's HTML checks; the notebooks import the Public API only | every function (M5b) |

What is deliberately **not** built: mutual information (useless at low prevalence, `lessons.md`),
VIF (needs imputation, hides constants, O(p³)), Information Value / WoE binning (a second scale
next to the concordance), optimal binning (a dependency), static images (kaleido, a dependency),
a combined EDA + Feature Checks file (two reports, D-036), any check that drops a feature
(`CLAUDE.md` §4.6).

## A. Scope, depth and time

### Q418. The depth: the table in section 0 as the target
**Context.** The timeline said "thin" for all four components at the pre-release and "deep" at
release 1.0 (OD-01, the depth table). Section 0 is between the two: every view and check of the
docs' requirements exists, built on the real frames, with the extended views and the theme file
left out. Review time (yours and the LDS's) is spent mostly on these reports, as you said, so the
content is where the depth goes.

**Options.**
- (A) Section 0 as written.
- (B) Section 0 minus the reference-group comparison, the strata pivots and the redundancy step
  (the three items with the least crunch precedent), saving about a day.
- (C) Thin as the timeline said: ranking, a few quality and leakage findings, one report each.

*Default:* (A).

### Q419. The time: seven to eight working days instead of four
**Context.** Section 0 is about three times the thin scope. With reviews inside each block (the
timeline's 40%), I estimate 7–8 working days: 11-03 to about 11-11. M2.3 Modelling would start
11-12 instead of 11-09, and M2 Operations would end about 11-25 instead of 11-20, eating into
M3's first week (the week of 11-30 is mostly lost anyway). The spikes due before M2.3 (FLAML's
group split, the round trips, Arrow dates) are yours and are unaffected.

**Sequencing.** Your other chat scheduled the synthetic to-do (small extra feature tables, the
mistake tests) and per-source key names (`dataset.md` → Open questions) "before EDA's build".
Both touch `synthetic/`, `dataset/panel.py` and `sources.py`, none of Stage 2's files, so they
can run beside Stage 2's first major step (the shared statistics, the ledger, the writer) in
their own chat; EDA's own build (major step 2) starts after they land, so the primary example
already joins two sources when EDA first runs on it.

**Options.**
- (A) Accept the shift: M2.3 from 11-12, M2.4 to about 11-25; M3 re-plans at its start, as
  D-022 (c) already says ("priorities re-evaluated as we go"); the synthetic to-do runs beside
  Stage 2's first major step.
- (B) Keep 11-09 by cutting to (B) of Q418 and moving the strata pivots and the proposed
  decisions table to M3.

*Default:* (A); the timeline proposal gets the new dates once you decide.

### Q420. Regression: real functions behind the per-task spec, tested on a variant config
**Context.** D-050 (every task-specific choice lives in one per-task spec dict) says the
regression entries for EDA and Feature Checks are designed before these stages are built, shapes
at least. The regression target exists (`forward_sum`, Stage 1), and the synthetic data has a
regression truth (`spend_cc_next_3_months`). No regression example config exists in `conf/base/`.

**Options.**
- (A) Build the regression functions for real (they are small: a Kendall concordance, a mean with
  a t-interval, a Cohen's d) and test both stages on a **test-only variant** of `cc_acquisition`
  (task `regression`, rule `forward_sum` on `spend_cc_vol`, eligibility `cc_flag = 1`) through
  the `variant` fixture; no example config until M4's regression end to end.
- (B) Shapes only: the regression entries raise "not implemented" and the stages refuse a
  regression config.

*Default:* (A): the proof of extensibility (D-020) stays real and costs little.

## B. The shape: package, interfaces, artifacts

### Q421. Package layout for Stage 2
**Context.** `architecture.md` §11 proposes `eda/`, `feature_checks/`, `ledger.py`, `reporting/`.
The statistics are shared by EDA, Feature Checks and later Training's selection floor, Evaluation
and Monitoring (PSI), so they need one owner. `CLAUDE.md` §1 rule 5: one module one concept, role
subfolders above a handful of modules.

**The proposal.**
- `core_modelling/statistics.py`: the per-feature statistics shared across stages
  (`concordance`, `wilson_interval`, `psi`, `quantile_edges`, `bin_values`, `encode_levels`,
  `level_shares`, `cramers_v`, `standardised_difference`). Named for its one concept; about
  250 lines.
- `core_modelling/tasks.py`: the new per-task entries (Q427–Q431).
- `core_modelling/dataset/frames.py`: the label-free frame; `dataset/panel.py`: the column kinds.
- `core_modelling/eda/`: `population.py` (funnel, target per period, strata, reference groups),
  `ranking.py` (the univariate ranking, key features, the kinds rule), `deep_dives.py` (bins,
  level tables, pivots, `pivot_target`), `run.py` (`run_eda`: frames → tables → ledger →
  artifacts → report).
- `core_modelling/feature_checks/`: `steps.py` (the step dict and the five step functions),
  `stability.py` (per-period concordance, PSI across periods, new levels; the label-free
  comparisons), `decisions.py` (rule entries, open flags, proposed decisions, the periods
  compared), `run.py` (`run_feature_checks`).
- `core_modelling/ledger.py`: the ledger's schema, create, append, save, read.
- `core_modelling/reporting/`: `html.py` (the writer: sections, blocks, plotly.js once, Styler),
  `charts.py` (the chart primitives, the chart rules), `blocks.py` (the choices block, headline
  numbers, warnings, the appendix), `theme.py` (the neutral palette as a dict).
- `core_modelling/artifacts.py`: the stage artifact folder, saving tables as parquet, the meta
  JSON and the resolved config, reading them back (shared by every stage from here).

*Default:* as proposed. Flag anything you'd merge or split.

### Q422. The stage function: one shape, the config resolved inside
**Context.** `run` hands stages the raw config today, and EDA's and Feature Checks' settings
(`eda.*`, `strata.*`, `feature_checks.steps`) are loggable (D-125 (every later decision is an
audit-log entry replayed into the resolved config)). Notebooks call stage functions directly.

**Options.**
- (A) Each stage function takes the loaded config, calls `resolve_config(cfg, entity, env)`
  itself, runs on the resolved config and saves it with its artifacts. `run` stays as it is.
  One place resolves, whoever calls.
- (B) `run` resolves and passes resolved configs; a notebook must call `resolve_config` first.

*Default:* (A). Signatures: `run_eda(cfg: UseCaseConfig, entity: str, env: EnvironmentConfig,
spark: SparkSession) -> StageResult` and `run_feature_checks(...) -> StageResult`, both public
(D-024 (Public API = the stage functions, `run`, the CLI, the config schema, the audit log's
functions, the session function)).

### Q423. What a stage returns: one `StageResult` for every reporting stage
**Context.** Evaluation's requirement 8 says results are structured data first, rendered second.
EDA and Feature Checks return the same kind of thing: named tidy tables, a log, a meta, where
things were written. Evaluation and Monitoring will too. §1 rule 6 asks for a second real use
before an abstraction; here the second use is in the same stage.

**Options.**
- (A) `@dataclass StageResult(tables: dict[str, pd.DataFrame], ledger: pd.DataFrame | None,
  log: list[dict], meta: dict, paths: dict[str, str])` in `artifacts.py`; every table is saved
  as parquet under the stage folder and is what the report renders; `paths` names the folder,
  the report and the resolved config.
- (B) Two dataclasses, `EdaResult` and `ChecksResult`, with their own fields.

*Default:* (A).

### Q424. Where the artifacts go, and reruns
**Context.** `data/README.md` already says `04_feature/<use_case>/<entity>/<ddh>/` holds the
audit log and, from M2.2, the EDA and Feature Checks artifacts and the ledger; it also lists
`08_reporting` for HTML reports. The D-088 count check (training recomputes per-period counts
and compares them with the EDA artifact's) reads the EDA meta.

**The proposal.** Under `04_feature/<use_case>/<entity>/<ddh>/`, beside `decisions/`:
- `eda/`: `eda.json` (`schema_version`, framework version, when, the hashes, `replayed_to`, the
  periods, the per-period counts for D-088: rows after the analysis filters, eligible rows,
  positive rows, positive events; the key features and why; the warnings; timings),
  `tables/<name>.parquet`, `resolved_config.yml`, `report.html`;
- `feature_checks/`: `feature_checks.json` (the same housekeeping plus `periods_compared`, the
  flag summary, the entries written), `tables/`, `resolved_config.yml`, `report.html`, and
  `compared_periods.json`, a list that only grows across reruns (D-088 says *any* run that
  compared a period blocks it);
- `ledger.parquet` + `_ledger.json` (`ledger_schema_version`), at the hash level, written by
  EDA and extended by Feature Checks (Q450).
A rerun rewrites its own folder whole (the latest run per data definition is the one Training
reads; its resolved config says which entries it replayed). `08_reporting` is dropped from
`data/README.md`: a report lives with the artifacts it renders.

**Options.**
- (A) As proposed.
- (B) Reports additionally copied to `08_reporting/<use_case>/<entity>/<ddh>/<stage>.html` for
  browsing.

*Default:* (A).

### Q425. Public API additions
**Context.** D-024: the shipped notebooks call only public functions, which a test checks.

**The proposal:** `run_eda`, `run_feature_checks` (stage functions), `StageResult`, and
`pivot_target` (the notebook tool of Q439). `write_report`, the ledger and the statistics stay
private. `run` gains the stages `eda` and `feature_checks` (`run --stages eda feature_checks`),
run in order; Feature Checks refuses to run without an EDA artifact for the same
data-definition hash (Q447).

*Default:* as proposed.

### Q426. Column kinds: decided once, in the dataset, from the Spark schema
**Context.** Nothing in the package tells numeric from categorical. Pandas dtypes after Arrow are
lossy (an integer column with nulls arrives as float64; a string as `object`; a date as `object`
holding `datetime.date`). Training's encoder (M2.3) needs the same answer as EDA.

**Options.**
- (A) `prepare_panel` adds `kinds: dict[str, str]` to the frames' meta from the Spark schema:
  `numeric` (any `NumericType`, decimals included), `categorical` (`StringType`,
  `BooleanType`), `unsupported` (dates, timestamps, arrays, structs, binary: a date is not a
  feature, derive durations upstream). EDA's deep dives treat a numeric with at most
  `strata.max_levels` distinct non-null values as **discrete** (a level table instead of
  quantile bins: flags, small counts), without changing its kind.
- (B) Decide from pandas dtypes inside EDA.

*Default:* (A). Every unsupported column gets a `quality.unsupported_type` flag (Q440) and no
statistics.

## C. The shared statistics and the per-task spec

### Q427. One statistic on one scale for both tasks: concordance
**Context.** The binary ranking statistic is the direction-agnostic univariate AUC (`eda.md`
req. 3, D-030). Training's `univariate_floor: 0.515` and the leakage screen's "too strong" are
on that scale. Regression needs its own statistic (D-050), and if it lived on another scale
(Spearman in [−1, 1]) every threshold would need a regression twin.

**Options.**
- (A) **Concordance** as the one name and scale, in [0.5, 1] after the direction is taken out:
  binary = the univariate AUC = P(a positive row's value exceeds a negative row's); regression
  = (Kendall's τ-b + 1) / 2, the share of concordant pairs, computed with `scipy.stats.kendalltau`
  (O(n log n)). `direction` is reported beside it (+, −, or none when it is below 0.5 + two
  standard errors; binary SE ≈ 0.5 / √events, D-082 (counts of positives are counts of
  events)). Every threshold (`univariate_floor`, `concordance_max`, the stability range) then
  means the same thing for both tasks.
- (B) Binary AUC and regression |Spearman|, each with its own thresholds in the per-task spec and
  its own config fields.

*Default:* (A). The ledger column is `concordance`; the glossary gets the term, with "the
univariate AUC" as its binary name.

### Q428. Categoricals in the ranking: level encoding, then the task's statistic
**Context.** The crunch computed nothing for categoricals (T10). A categorical has no order, so
the concordance needs a score per level. The high-cardinality trap (300 levels) shows the risk:
an in-sample level encoding looks predictive and scores 0.5 held out.

**Options.**
- (A) Encode each level by its **shrunk target mean** (binary: its rate; regression: its mean),
  shrunk towards the overall mean with a prior weight of `strata.min_events` events (an
  empirical-Bayes shrinkage: `(events + k × base) / (rows + k)` in rate terms), then apply the
  task's concordance to the encoded column. Levels below the support behave like the base rate,
  so a 300-level noise column scores near 0.5. The ledger shows `levels` beside the concordance,
  and the report marks a concordance from more than 20 levels as "optimistic (in-sample
  encoding)". **Evidence:** the blend is Micci-Barreca's (2001) empirical-Bayes target encoding;
  scikit-learn 1.8 ships it cross-fitted as `TargetEncoder(smooth="auto")`, which is the
  heavier alternative (a fit per fold) for one statistic; the hand-written formula is one line.
- (B) Cramér's V for categoricals (no encoding, chi-square based), on its own scale, not ranked
  with the numerics.
- (C) Information Value with WoE bins for both kinds: the credit-scoring standard, a second scale,
  and WoE bins for numerics need a binning rule of their own.

*Default:* (A). The same encoding serves the leakage screen and Training's floor later, so one
function owns it.

### Q429. Missingness: never imputed into the statistic
**Context.** The crunch median-imputed before every statistic, mixing the missingness pattern into
the signal (legacy survey). The missing-leak trap carries its whole signal in *whether* the value
is filled.

**The proposal.** The concordance is computed on the non-null rows only. Missingness gets its own
two numbers: `missing_share`, and `null_concordance`, the task's concordance of the null
indicator (0/1) against the target, computed when the missing share lies in [0.005, 0.995].
The leakage step reads the second (Q441). Bins and level tables show nulls as their own bin.

*Default:* as proposed.

### Q430. Group summaries, support and low prevalence, per task
**Context.** Every rate shown per bin, level, period or stratum needs an interval and a support
rule (`CLAUDE.md` §4; D-038 (stratified reporting is mandatory: levels capped, a minimum number
of positives per stratum); D-082 (support counts events, not rows); D-091 (per-period
statistics only for periods with at least 50 positive events)).

**The proposal, as per-task spec entries.**
- `summarise_group(rows) -> {rows, support, estimate, low, high, lift}`: binary: `support` =
  positive events (distinct units with `target = 1` in the group), `estimate` = the positive
  rate (over rows), the **Wilson** 95% interval, `lift` = rate / base rate; regression:
  `support` = rows, `estimate` = the mean, a t-interval, `lift` = mean / overall mean, with the
  median beside it.
- `min_support`: `strata.min_events`, read as events for binary and as rows for regression (the
  field keeps its name; the template says so), for the strata tables and every per-period
  statistic (D-038, D-091). Below it a cell is shown greyed as "insufficient" with its interval
  still drawn, never hidden. **Bins and levels in the deep dives** use a lower code constant,
  `MIN_BIN_SUPPORT = 20` events (a 95% interval about ±44% of the rate; at 50 it is ±28%): a
  decile of a rare target would otherwise be greyed in every use case with fewer than 500
  events, and the interval already shows the uncertainty. No new config field.
- Bins: 10 quantile bins on the non-null values, duplicate edges merged (a heavy zero mass gives
  fewer bins), nulls as an eleventh bin labelled `null`; a discrete numeric (Q426) gets one bin
  per value.
- Levels: the top `strata.max_levels` by rows, the rest pooled as `other`, a `null` level when
  present.

**Evidence.** Wilson (or Jeffreys) is the interval recommended for binomial proportions at small
counts; Clopper–Pearson is wider and conservative (Brown, Cai and DasGupta 2001,
projecteuclid.org/euclid.ss/1009213286). `scipy.stats.binomtest(k, n).proportion_ci(
method="wilson")` gives it on the pinned scipy (verified locally). No standard exists for the
minimum positives per bin; the relative half-width ≈ 1.96/√k (k = 10: ±62%, 20: ±44%, 50: ±28%).

**Options.**
- (A) As proposed: `strata.min_events` for strata and periods, the constant 20 for bins.
- (B) `strata.min_events` everywhere (one rule, more greying at rare targets).

*Default:* (A).

### Q431. PSI: one definition for Feature Checks now and Monitoring later
**Context.** T10 (PSI on categoricals crashed); D-040 (monitoring's categorical drift is PSI on
level shares with `__other__`). The legacy PSI dropped NaNs first, so a shift in missingness was
invisible.

**The proposal.** `psi(expected_shares, actual_shares)` over a fixed set of bins: numerics use
the decile edges of the reference (the pooled window), with a `null` bin; categoricals use the
reference's levels with at least 1% share, the rest and every unseen level as `other`; each
share is floored at 1e-4 before the log. The reference is always the pooled window; the
compared side is a period or a pooled set of periods. The same function serves Monitoring with
the drift reference (D-054).

**Evidence.** The 0.10 / 0.25 bands are Lewis's constants (1994), carried into scorecard practice
(Siddiqi); they ignore the sample size and the number of bins, and n·PSI is χ²(B−1) under no
shift (Yurdakul 2018, scholarworks.wmich.edu/dissertations/3208; du Pisanie et al. 2023,
arxiv.org/abs/2303.01227). Jensen–Shannon distance is the bounded alternative drift tools use
(Evidently, NannyML). PSI is kept because monitoring already uses it (D-040) and the bank reads
it; the bands are labels, not tests, and the report says so. Not taken: Jensen–Shannon,
Wasserstein (unbounded, outlier-sensitive on amounts).

*Default:* as proposed.

## D. EDA: the views, one by one

The report follows D-036's structure: summary (choices block, headline, warnings), core views,
extended views, appendix. Everything label-based uses the eligible rows of the window; the
population views use every row after the analysis filters (D-030 (EDA uses every client of the
window after the analysis filters, labels included; label-based views never show later
periods)).

### Q432. The choices block and the rule-based warnings
**The proposal.** Choices: automation level; decision type and the derived metric; task; the
period, observation window, `w` and the validation period (shown, never used); the eligibility
steps with their kind and reason; the candidates count and the patterns; the key-feature rule
(top-N by the level, plus the listed ones); the strata variables; chart sampling if on; the
audit-log entries replayed (`replayed_to`) and the hashes. Warnings, each a rule with its number:
- fewer than 500 positive events in the window (binary; D-082: SE of an AUC ≈ 0.5 / √events, so
  the third decimal is noise below about 1,000);
- a window period with fewer than `strata.min_events` events (its per-period statistics are
  insufficient);
- a stratum level insufficient;
- the contract's null callout (a share of target windows held a null);
- a collect above the budget (from the frames' log);
- chart sampling on (which views it affects);
- the cost of all-client EDA (D-030): "feature decisions taken from this report have seen test
  clients' labels".

*Default:* as proposed; name any warning to add or drop.

### Q433. Population and target: the core tables and the one chart
**The proposal.**
1. **Headline** (eligible rows): rows, clients, periods, eligible share, positive rows, positive
   events, base rate with its Wilson interval; regression: mean, median, p10, p90, the share of
   zeros.
2. **Funnel per period** (from `Frames.log`, no new computation): spine rows → after each
   analysis filter → tagged per modelling filter → eligible, one column per step, rows per
   period plus `all`.
3. **Target per period** (eligible rows): rows, positive rows, positive events, rate with
   interval, per window period plus pooled; the chart: the rate per period with error bars and
   the events per period as bars on a second axis. Later periods are not shown (their target
   windows overlap the validation period's, D-030).
4. **Target by stratum**, per variable, pooled over the window: the level table of Q430 with
   lift, insufficient marked; the chart: rate by level with intervals, one colour per level
   kept across the report.
5. **Positive rows vs positive events** sits in table 3; the ratio (rows per event, at most `w`)
   is stated once in the headline.

*Default:* as proposed.

### Q434. Reference groups: a label-free comparison of the excluded rows
**Context.** A modelling filter tags its rows for EDA so the excluded group (current holders) can
be compared with the modelling population (D-129 (eligibility as two lists; a modelling tag is a
reference group and a stratum)). `eda.md` leaves "which views show tagged rows" to this stage.
For a tag that is the rule's own precondition (holders under `flag_goes_up`) the target rate on
tagged rows is 0 by construction, so a label comparison is meaningless there.

**The proposal, per modelling tag, label-free:**
- sizes per period: tagged vs not, with the share;
- composition: the share per level of each stratum variable, side by side;
- the key features (as ranked on the eligible rows): median, p10, p90 and the non-null share on
  each side, and the **standardised mean difference** (Cohen's d on the raw values; for
  categoricals the largest level-share difference), sorted by its absolute value, so the table
  answers "how different is the excluded group, and in what".
Label-based views never split by the tag. Tagged rows appear nowhere else.

**Evidence.** Standardised mean differences are the standard covariate-balance diagnostic
(Austin 2009, doi.org/10.1002/sim.3697: |SMD| < 0.1 balanced; 0.25 the looser cut of Rubin
2001 and Stuart 2010); the table marks |SMD| ≥ 0.25 as "differs". They describe the difference
and are not pass/fail here: the two groups are not meant to be comparable. Heavy tails dominate
an SMD on raw amounts, so the quantiles sit beside it.

**Options.**
- (A) As proposed.
- (B) Sizes and composition only; the key-feature comparison waits for M4.

*Default:* (A).

### Q435. The univariate ranking table
**The proposal.** One row per candidate, on the eligible rows: `feature`, `kind`,
`missing_share`, `levels` (distinct non-null values), `dominant_share` (the share of the most
common value), `concordance`, `direction`, `null_concordance`, `rank` (by concordance, ties by
name), `key_feature` (`top_n` / `listed` / empty). Styled with a bar on the concordance, the
key features marked, the lineage columns listed underneath as auto-excluded. Core. Written to
the ledger (Q450).

*Default:* as proposed.

### Q436. Key-feature deep dives: what each one shows
**Context.** D-132: N = 10 at `autonomous`, 20 at `assisted`, plus the person's list; each key
feature gets a deep dive (`eda.md` req. 4); charts obey the chart rules (T16).

**The proposal, per key feature:**
- **numeric:** (i) the group summary by quantile bin (Q430) as a chart: lift vs base rate per bin
  with the interval as error bars and the events as labels, the `null` bin last, the y axis
  from the data; (ii) the distribution by target class: box plots per class on a log axis when
  the skew is above 2 (the mart's balances have skew 50–80), drawn on the chart sample
  (Q438); plus the bin table;
- **discrete numeric or categorical:** the level table (rows, events, rate, lift, interval,
  insufficient marked) and one bar chart of lift by level with intervals;
- **regression:** (i) the mean target per bin with its interval and the median; (ii) the target's
  distribution per bin (box plots); the level table for categoricals.

**Options.**
- (A) Deep dives for every key feature (up to 20 + listed): about 40 figures.
- (B) Deep dives for the top 10 plus the listed ones; the rest of the top 20 get the bin table
  only.

*Default:* (A); the report size question is Q455.

### Q437. Strata pivots: extended views
**The proposal.** For the top five key features and each stratum variable: the rate (lift) by
feature bin × stratum level as one styled table, colour by lift, insufficient cells greyed. The
extended section; everything else by stratum is left to `pivot_target` in the notebook.

*Default:* as proposed (five features; name another number if you want).

### Q438. Chart sampling
**Context.** `eda.chart_sample_share` exists in the schema with no code. The counts and rates
never sample; only the raw-value distribution charts (ii of Q436) need it.

**The proposal.** When set, the distribution charts draw a seeded pandas sample of that share of
the eligible rows; the report states it on each affected chart and in the choices block. Nothing
else samples.

*Default:* as proposed.

### Q439. The notebook tool: `pivot_target`
**Context.** `eda.md` req. 7: styled pivots (rate / lift with counts and intervals) by any
dimensions with any filter, so analysts can explore without writing code; it must be public
(the notebooks call it).

**The proposal.** `pivot_target(frame: pd.DataFrame, by: str | list[str], cfg: UseCaseConfig,
columns: str | None = None, where: str | None = None) -> pd.io.formats.style.Styler`: the group
summary of Q430 by the `by` dimensions (a numeric is quantile-binned, a categorical capped at
`strata.max_levels`), optionally against `columns`, after a pandas `query` filter; styled by
lift, insufficient cells greyed, counts and intervals shown. It works on any frame with `target`
(the window frame, its eligible rows, later the test frame).

*Default:* as proposed; one function, no variants.

## E. Feature Checks: the steps, one by one

The steps run in the config's order on the eligible rows of the window (D-030), read EDA's
ledger for the statistics it already computed (Q447), and each writes its findings as flags
(Q448). Thresholds are low on purpose (D-031 (sensitive thresholds, so borderline cases reach
the person who signs off)) and the same at both levels (D-023). Every step logs features in →
flagged, the finding, the statistic and the threshold.

### Q440. `quality`: the findings
**The proposal.** Parameters in the template with their defaults; each finding names its rule.

| Finding | Rule (eligible rows) | Default | Catches |
|---|---|---|---|
| `all_null` | missing share = 1 | — | the `all_null` trap; T11 (`loan_personal_maturity_months` under a first-loan eligibility) |
| `constant` | one distinct non-null value | — | the two `constant` traps; T11 (eleven card columns exactly 0 under `cc_flag = 0`) |
| `near_constant` | dominant value share ≥ `dominant_share_max`; the minority rows' `rare_value_effect` (lift) is shown beside it, since a 99%-zero flag can carry real lift at low prevalence | 0.99 | `near_constant` (99.9% zeros); `repayment_cc_vol` under the card eligibility (99.4% zero) |
| `high_missing` | missing share ≥ `missing_share_max` | 0.95 | the two `low_fill` traps (1% and 0.3% filled) |
| `high_cardinality` | categorical with more than `max_levels` levels | 50 | `high_cardinality` (300 levels); also `nationality` (64 levels), a flag a person settles once |
| `unsupported_type` | kind `unsupported` (Q426) | — | dates, nested types |

**Evidence.** Scorecard practice drops above 95% missing (`scorecardpy` `missing_limit`); for
near-constants the scale-free rules are caret's `freqCut` 95/5 with `uniqueCut` and
`scorecard`'s `identical_limit` 0.95, so 0.99 is already lenient; ydata-profiling warns above
50 distinct values; `VarianceThreshold` is scale-dependent and not used.

`eligibility_constant` folds into `all_null` and `constant`: the frame is already the eligible
rows (`feature_checks.md` open question). It leaves the template's step list and the schema's
known names (0.x, no migration, D-007 (c) (0.x promises nothing)). The time-alignment screen on
the eligibility defines and the modelling tags (T11; `feature_checks.md` open question) waits
for M4: it needs the window frame and a design of its own.

*Default:* as proposed.

### Q441. `leakage`: the findings
**The proposal.**

| Finding | Rule | Default | Catches |
|---|---|---|---|
| `too_strong` | concordance ≥ `concordance_max` | 0.80 | `leak` (0.97, 0.87), `upstream_target` (1.0) |
| `missingness_leak` | `null_concordance` ≥ `null_concordance_max`, with the missing share in [0.005, 0.995] | 0.60 | `missing_leak` (0.89) |
| `rare_value_leak` | dominant share ≥ 0.9 and the `rare_value_effect` of the non-dominant rows ≥ `rare_effect_max`, with support ≥ `min_support`: binary = lift vs base rate; regression = Cohen's d of the target | 5 (lift) / 1 (d) | `process_leak` under `w = 3` (98.7% zeros; the non-zero rows convert at about 80%), "set after the offer" fields in general |

Why 0.80: the oracle's ceiling for card acquisition is 0.84 with every feature, so one feature
above 0.80 is either the outcome itself or a leak; the weaker leak sits at 0.87. The threshold is
a config parameter per use case.

**Evidence.** Kaufman et al. 2012 ("Leakage in data mining", doi.org/10.1145/2020408.2020496)
for the taxonomy and the warning that strength is not legitimacy (a leak is a value known
only after the observation period); Kapoor and Narayanan 2023 (L2 illegitimate features, L3
temporal leakage). Thresholds are practice, not literature: DataRobot flags a normalised
univariate strength at 0.85 and removes at 0.975, evalml at a correlation of 0.95, scorecards
treat IV > 0.5 as "suspicious". Missingness as the signal: Kaufman §2 (the INFORMS 2008 case).

*Default:* as proposed.

### Q442. `time_alignment`: a lag check instead of a backward label
**Context.** D-029 (d) words the step as "a feature's power to predict the target forward vs to
'predict' the same event backward". On the acquisition examples that backward label is
degenerate: the event in `t−w … t−1` means the client holds the product at `t`, and the modelling
filter removes holders, so on the eligible rows the backward label is almost always 0. On the
window frame (holders included) a legitimate holding feature (`cc_limit`) and its shifted twin
both predict the past acquisition perfectly, so the comparison separates nothing. The trap
survey shows what must be caught: a column shifted forward by one period, and a process column
set in the period before the outcome, both below the "too strong" line under `w = 3`.

**Options.**
- (A) **Lag check.** For every feature with concordance ≥ 0.60 (there must be signal to lose),
  compute the **lagged concordance**: the feature's value one period earlier (the same unit's
  row at `t−1`, from the frame itself; window periods 2 … k) against the target at `t`. Flag
  `lag_drop` when the lagged signal keeps less than `signal_kept_min` (default 0.5) of the
  contemporaneous one: `(lagged − 0.5) < 0.5 × (concordance − 0.5)`. A shifted column (next
  month's value) lagged once is the legitimate current value, which for a non-holder is 0, so
  its signal collapses; so does an application count whose card arrives the next month; a slow
  legitimate feature (tenure, income) keeps nearly all of it. Fast-moving legitimate features
  (last month's logins) may be flagged, and a person decides, as every flag. Rows whose unit has
  no row at `t−1` are left out and counted.
- (B) The backward label as worded in D-029 (d), computed on the window frame including the
  tagged rows: `target(t − w − 1)` as "the event happened in `t−w … t−1`". Degenerate on the
  acquisition examples, as explained.
- (C) Both, (A) as the finding and (B) as a reported statistic without a flag.

**Evidence.** No published method for the backward check exists; the nearest analogue is the
negative-control outcome of epidemiology (Lipsitch et al. 2010), and the research survey's own
caveat matches ours: sticky features predict both directions, so backward ≈ forward separates
nothing, and the signal worth a flag is a jump at the boundary, which the lag check measures.

*Default:* (A); D-029 (d)'s wording is updated to the mechanism chosen, the step keeps its name
and its intent (T12's forward-built columns).

### Q443. `stability`: the findings
**The proposal.** The reference is the pooled window; the periods compared are recorded (D-088
(moving the validation period to a period Feature Checks compared is refused)).

| Finding | Rule | Default | Catches |
|---|---|---|---|
| `concordance_unstable` | the per-period concordances (window periods with support ≥ `min_support`) differ more than their standard errors allow: Cochran's Q over the periods, each weighted by 1/SE² (Hanley–McNeil SE from that period's events and non-events), against χ²(k−1) at `heterogeneity_p_max`; the range is reported beside it | p 0.01 | a signal present in one period only (the `unstable` kind, M4); a direction that flips between periods |
| `psi_window` | max over window periods of PSI(period, pooled window) ≥ `psi_max` | 0.10 | a one-off period shift inside the window |
| `psi_gap` | PSI(pooled gap periods, pooled window) ≥ `psi_max`; label-free | 0.10 | drift between the window and the validation period |
| `psi_latest` | PSI(latest period, pooled window) ≥ `psi_max`; label-free | 0.10 | the login drift after the app relaunch (2026-01; the latest synthetic period is 2026-09): what production will score |
| `new_levels` | categorical: levels unseen in the window with share ≥ `new_level_share_max` in the gap or latest period | 0.01 | a recoded categorical |

The template's `psi_max: 0.25` becomes 0.10: a flag asks a person to look, and 0.25 is the
"significant shift" band while 0.10 is "investigate" in credit-scoring practice. The per-period
concordance table (periods with insufficient support marked, each with its SE) and the PSI
table are shown for every candidate.

Why a test and not a range: at the 50-event floor the null SE of a concordance is about 0.04,
so six periods show a range near 0.10 from noise alone (the research survey's computation),
and a raw-range rule would flag noise exactly where the data is thinnest. Cochran's Q is six
lines with `scipy.stats.chi2`.

**Evidence.** PSI bands: Lewis 1994 via Siddiqi (Q431). The null SE of an AUC is
√((n₊ + n₋ + 1) / (12 n₊ n₋)) ≈ 1/√(12·n₊); away from 0.5 the Hanley–McNeil 1982 formula
(math.ucdavis.edu/~saito/data/roc/hanley-mcneil-auc.pdf).

**Options.**
- (A) As proposed: `psi_max` 0.10 and Cochran's Q for the per-period concordance.
- (B) `psi_max` stays 0.25; the concordance rule as a raw range with `concordance_range_max`
  0.10 (flags noise at few events).

*Default:* (A).

### Q444. The label-free frame for the stability step
**Context.** The gap periods and the latest period carry labels in the panel (D-131 (labels in
every period Target Factory could build)); Feature Checks must read them without the label and
never the validation period (`feature_checks.md` open question: a helper with a test).

**Options.**
- (A) `build_frames(stage="feature_checks")` also fills a new last field `Frames.label_free`:
  the eligible rows of the gap periods (`tk+1 … v−1`) and the latest period (the spine's last,
  only when it lies after `v`), with `target` and `split` dropped before the collect, through
  `collect_frame` with its printout (entry name `label_free`); `meta["periods_compared"]` lists
  them. A test asserts no `target` column and no row at `v`. The frames' `Frames` gains the
  field at the end (positional, as the doc says).
- (B) Spark-side aggregation of the bin counts per period without a collect. Smaller in memory,
  more code (the edges must be computed first, then broadcast into Spark). M4 if a real size
  needs it.

*Default:* (A).

### Q445. `redundancy`: the findings
**The proposal.**

| Finding | Rule | Default | Catches |
|---|---|---|---|
| `correlated_pair` | numeric pairs with absolute Spearman ≥ `correlation_max`, on a seeded sample of at most 200,000 rows (stated in the log); both features flagged, each entry naming the partner and both concordances | 0.90 | `redundant` (0.99997 with `relationship_days`); 3- and 6-month rollups of one measure |
| `associated_pair` | categorical pairs with Cramér's V ≥ `association_max` (scipy's, without the Bergsma bias correction, which only matters at few rows) | 0.90 | status ⇔ flag pairs when both are categorical |

No VIF (imputation, hides constants, O(p³); legacy survey; O'Brien 2007: the 5 / 10 rules alone
don't justify dropping). Numeric-vs-categorical pairs are not compared in Stage 2. The flag
reads "keep both or drop one: a person decides" (D-031).

**Evidence.** |ρ| ≥ 0.9 is the default screen in ydata-profiling and caret's `findCorrelation`;
scorecard practice goes as low as 0.7–0.8; so 0.90 is the sensitive end of common practice.
Clustering on 1 − |ρ| (scipy, Ward) is the richer view (the scikit-learn multicollinearity
example); not taken in Stage 2. Collinearity costs boosted trees little accuracy but splits
their importance (`lessons.md`), which is why a person, not a rule, decides.

*Default:* as proposed.

### Q446. The default step list in the template
**The proposal.** `feature_checks.steps` in the template and the examples:
```yaml
feature_checks:
  steps:                                 # ordered; each flags and logs, never drops (§4.6); low thresholds (D-031)
    - {name: quality, params: {dominant_share_max: 0.99, missing_share_max: 0.95, max_levels: 50}}
    - {name: leakage, params: {concordance_max: 0.80, null_concordance_max: 0.60, rare_effect_max: 5}}
    - {name: time_alignment, params: {signal_kept_min: 0.5}}
    - {name: stability, params: {psi_max: 0.10, heterogeneity_p_max: 0.01, new_level_share_max: 0.01}}
    - {name: redundancy, params: {correlation_max: 0.90, association_max: 0.90}}
```
Each step's parameters are a Pydantic model (unknown or missing parameters fail loud at load);
a step left out of the list doesn't run and the report says so; `eligibility_constant` goes.

*Default:* as proposed.

### Q447. Feature Checks requires EDA's artifact
**Context.** The ranking's concordance, the kinds and the missing shares are EDA's; Feature
Checks shows "both features' AUCs side by side" (req. 7) and D-031 requires both artifacts
before training anyway.

**Options.**
- (A) `run_feature_checks` reads `eda.json` and the ledger for the same data-definition hash and
  fails loud naming `run_eda` when they are missing or carry another `replayed_to` data
  definition; it computes only what EDA didn't (per-period and lagged concordance, PSI, pairs).
- (B) Feature Checks recomputes everything it needs, so it runs alone.

*Default:* (A); `run --stages eda feature_checks` runs both in order, and at `autonomous`
Training will run both (M2.3).

### Q447b. The standard-error lesson is corrected
**Context.** `lessons.md` ("Univariate AUC floor") and D-082 reason with "SE ≈ 0.5 / √events".
The exact null SE of an AUC is √((n₊ + n₋ + 1) / (12 n₊ n₋)) ≈ 1/√(12·n₊) ≈ 0.29/√n₊ (the
research survey's simulation at 800 events: 0.0105 measured, 0.0102 by the formula, 0.0177 by
the lesson's rule). The conclusion of the lesson ("with ~800 events the third decimal is noise")
stands; the constant is wrong by 1.7×, which matters for Q443's test and for Training's floor
later (0.515 is about 1.5 SE at 800 events, not 0.85 SE).

*Default:* `lessons.md` and D-082 are corrected in this stage; every SE the framework shows is
Hanley–McNeil's (the null form where the concordance is 0.5), computed in `statistics.py`.

### Q448. Flags, rule entries and the rerun question
**Context.** D-125 (c): rule outcomes are audit-log entries; the worked example in `config.md`
writes rule `exclude` entries for `quality.all_null` and `quality.near_constant` and `flag`
entries for leakage and stability. `config.md`'s open question: how a rerun with a changed
threshold supersedes a step's earlier rule `exclude`, and whether a person may overrule a quality
rule for one feature. §4.6: screens flag, never drop.

**Options.**
- (A) **Every Feature Checks finding is a flag.** Only the lineage exclusion is a rule `exclude`
  (written once, as the stage's implicit first step, if the log has none yet). An all-null or
  constant column is flagged `quality.all_null` / `quality.constant`; Training's automated
  selection drops it anyway (a constant has concordance 0.5, below the floor) as a `dropped`
  entry. Then nothing ever has to supersede a rule's exclude, a person can keep any flagged
  feature with `keep_despite_flag`, and the two open questions close. Rule entries are
  **idempotent**: a step writes one `flag` entry per finding per run only when its feature set
  differs from the latest entry of that finding, so a rerun on unchanged data writes nothing
  and a changed threshold writes the new set; the latest entry per finding is the current flag
  set.
- (B) As the worked example: `all_null` and `constant` are rule excludes; a changed threshold
  writes a rule `include` for the features it no longer excludes; a person cannot overrule a
  rule's exclude for one feature.

*Default:* (A). `replay.py` gains `open_flags(entries) -> dict[str, list[str]]`: per feature,
the findings of the latest `flag` entries not yet settled by a later person's `keep_despite_flag`
or `exclude`; `audit_log.py` gains a writer for rule entries (`by.kind = rule`, `by.id =
<step>.<finding>`, stage `feature_checks`).

### Q449. The flag review: proposed decisions
**Context.** At `assisted` the stage ends in a review of its flags (D-132); `feature_checks.md`
req. 8: "proposed decisions ready to record". The person records entries with `record_decision`.

**The proposal.** A table `proposed_decisions`, one row per group of features sharing the same
set of findings: the features, the findings with their values, the EDA concordance, and a
`record_as` column holding the call text ready to copy, `record_decision("<config>",
entity="…", exclude=[…] | keep_despite_flag=[…], reason="<why>", evidence=["#n", "feature_checks
report: <step>"])`, with the operation suggested by the step (`exclude` for leakage and
time-alignment findings, `keep_despite_flag` for quality, stability and redundancy) and the
reason left to the person. Flags already settled by an entry are shown as settled.

**Options.**
- (A) As proposed, with the suggested operation.
- (B) The grouping and the call text, no suggested operation (the person chooses every time).

*Default:* (A); a suggestion is text in a table, never an entry.

## F. The feature ledger

### Q450. The ledger's shape (OD-11)
**Context.** OD-11's leaning: two parts, one per data definition keyed by the data-definition
hash (EDA + checks) and one per run keyed by `run_id` (selection + use), joined on feature name;
human decisions are the audit-log entries the run replayed, read at render time, never copied
in (D-125 (entries are append-only)).

**The proposal, the per-data-definition part** (`ledger.parquet` under the hash folder,
`_ledger.json` with `ledger_schema_version: 1`), one row per candidate **and per lineage
column**:

| Group | Columns | Written by |
|---|---|---|
| Identity | `feature`, `kind`, `lineage` (bool: a target-lineage column, auto-excluded) | EDA |
| EDA | `missing_share`, `levels`, `dominant_share`, `concordance`, `direction`, `null_concordance`, `rank`, `key_feature` | EDA |
| Checks | `flags` (a list of `step.finding`), `lagged_concordance`, `concordance_range`, `psi_window`, `psi_gap`, `psi_latest`, `partners` (a list of correlated features), `verdict` (`pass` / `flagged` / `auto_excluded`) | Feature Checks |

The findings' full detail (feature, step, finding, statistic, threshold, partner) is a separate
table `findings` in the Feature Checks artifacts; the ledger holds the summary columns. The
Decision group (what a person decided, the entry numbers) is rendered into the report by joining
the effective audit-log entries per feature, never stored. The per-run part arrives with
Training (M2.3): `selection`, `in_model`, `importance`, keyed by `run_id`, joined on `feature`.

**Options.**
- (A) Wide, as proposed.
- (B) Long: `(feature, stage, key, value)`, more flexible, harder to read as a table.

*Default:* (A); D-007: columns are only added within a major version.

### Q451. Who writes which columns, and when
**The proposal.** EDA creates the ledger (identity + EDA) and rewrites it whole on a rerun;
Feature Checks reads it, adds its columns and rewrites the file, refusing a ledger whose EDA
columns are missing (Q447). A Feature Checks rerun replaces its own columns. The ledger is
rendered in both reports (EDA: identity + EDA; Feature Checks: everything plus the decisions).

*Default:* as proposed.

### Q452. Readable labels and the source per feature
**Context.** The sketch lists an optional readable label and the source column (D-046: no
per-source catalogue). The frames don't carry which logical source a column came from.

*Default:* neither in Stage 2. A `source` column joins when the join log records columns per
source (cheap, with Inference's needs in M2.4).

## G. Reporting

### Q453. The writer
**The proposal.** `reporting/html.py`: `write_report(title, sections, path, theme) -> str`, where
a section is `(heading, blocks)` and a block is a Styler table, a plotly figure, a paragraph or
a key-value list; plotly.js is embedded **once** (`plotly.offline.get_plotlyjs()` in one
`<script>`), each figure rendered with `include_plotlyjs=False, full_html=False`; tables through
`Styler.to_html()` (pandas 2.2.3 needs jinja2, which is in the devcontainer: pinned on first
use, D-012); a neutral CSS block from `theme.py`; a table of contents from the section headings;
every section anchored so the notebook can link to it. The four parts of D-036 are the
top-level sections. No templating beyond that.

**Evidence** (measured locally on plotly 6.3.1): `get_plotlyjs()` is plotly.js 3.1.1 at 4.83 MB;
a page with one trivial figure is 4.84 MB; fragments with `include_plotlyjs=False,
full_html=False` are the documented pattern (plotly.com/python/interactive-html-export), and
`include_plotlyjs=False` with `full_html=True` gives a broken page. Styler raises above
`styler.render.max_elements` = 262,144 cells (the ledger of 157 × 15 is far below). Static
images would need kaleido plus a browser: not in the bank.

*Default:* as proposed.

### Q454. The chart primitives and the chart rules
**The proposal.** `reporting/charts.py`, each a function returning a plotly figure, each obeying
the chart rules of `reporting.md` (axes from the data, lift where rates are tiny, counts and
intervals always, log axis for heavy tails, one colour per level across a report):
`lift_by_bin` (bars with error bars and event labels), `distribution_by_class` (box plots, log
axis by skew), `rate_per_period` (markers with error bars, events as bars on a second axis),
`lift_by_level` (bars with error bars), `psi_by_period`, `concordance_by_period`. Each chart
reviewed in Stage 2 extends the rule set in `reporting.md`.

*Default:* as proposed.

### Q455. Report size and figure count
**Context.** plotly.js embedded once is about 4–5 MB (D-036: not optimised in Phase 2); each
figure adds its data as JSON. With (A) of Q436 the EDA report holds about 50 figures; the open
time in the bank's JupyterLab is spike 5, yours, later. Each deep dive's bin table carries at most
11 rows; the distribution box plots carry quantiles, not raw points.

**Evidence** (measured, research survey): a 20-bar chart fragment is 7.6 KB; a box plot of
20,000 raw values 271 KB; a histogram of 100,000 raw values 1.37 MB. Browsers allow 8–16 WebGL
contexts per page, so no WebGL traces (bars, box plots and markers are SVG). The open time of a
page with many figures is unmeasured anywhere.

**Options.**
- (A) No cap; every chart pre-aggregated (box plots from precomputed quantiles, bars from the
  group tables; no raw arrays in the HTML), so 50 figures add about 0.5 MB to the 4.8 MB of
  plotly.js; measure the file size and the open time locally and record them in the log.
- (B) Deep-dive charts for the top 10 key features only, tables for the rest (Q436 (B)).

*Default:* (A).

### Q456. The theme
*Default:* `reporting/theme.py` holds the neutral palette, fonts and the categorical colour
sequence as a dict; `environment.theme` (a path, exists since Stage 1) is read in M4, when the
bank's theme is known. Nothing in the repo names a brand.

### Q457. Two reports, each stage standalone
**Context.** D-036 lists EDA and Feature Checks as two report writers; the roadmap's M2.2 goal
says "the EDA + Feature Checks report". The two stages are standalone (D-036) and may be rerun
separately.

*Default:* two files, `eda/report.html` and `feature_checks/report.html`; the Feature Checks
summary repeats the EDA headline numbers (from `eda.json`) so a reader of the second report
knows the population.

## H. Notebooks, tests, docs

### Q458. Notebooks: one per stage, first-draft guidance
**The proposal.** `notebooks/02_eda.ipynb` (setup; `run_eda`; the report path; the headline,
funnel, ranking and one deep dive displayed inline from `result.tables`; `pivot_target`
examples; what to look at and what to record) and `notebooks/03_feature_checks.ipynb` (setup;
`run_feature_checks`; the flags grouped per feature; the proposed decisions; a commented
`record_decision` cell; `show_decisions`; the ledger). Guidance cells written now as a first
draft; D-022 (e): the LDS reviews the guidance in M3 as the proxy user.

*Default:* as proposed.

### Q459. The trap acceptance test (D-064)
**Context.** D-064: the trap list in `truth.json` is the acceptance list; a test maps each kind to
the step that must flag it, while the framework stays name-blind (`_trap_` never in `src/`).
The `unit` preset (5k clients, 24 months, about 17 s to generate) is the fixture.

**The proposal** (`tests/test_feature_checks_traps.py`, on `cc_acquisition` through the fixtures
of `conftest.py`):

| Trap kind | Must be flagged by | Also |
|---|---|---|
| `all_null`, `constant`, `near_constant`, `low_fill`, `high_cardinality` | `quality.<finding>` | |
| `leak`, `upstream_target` | `leakage.too_strong` | |
| `missing_leak` | `leakage.missingness_leak` | |
| `process_leak` | `leakage.rare_value_leak` or `time_alignment.lag_drop` | both expected |
| `shifted` | `time_alignment.lag_drop` | |
| `redundant` | `redundancy.correlated_pair`, partner = its source | |
| `null_control` (four columns) | **no** leakage, time-alignment or redundancy flag; concordance below 0.55; none is a key feature | |
| the login drift columns | `stability.psi_latest` (the latest synthetic period is after the relaunch) | |

Plus: the lineage column is `auto_excluded`; the per-period counts in `eda.json` equal Target
Factory's summary on the eligible rows; the label-free frame has no `target` and no validation
row; a `set time.validation_period` to a compared period is refused; the regression variant
(Q420) runs both stages; the notebooks import the Public API only. The events at unit size
(5k clients) decide which per-period statistics are insufficient; the test asserts the flags,
not the per-period numbers.

*Default:* as proposed; name any assertion to add.

### Q460. Period labels in pandas
**Context.** `period` arrives as `datetime.date` objects (`dataset.md` open question).

*Default:* no dtype change in the frames; EDA and Feature Checks add `period_label` through
`period_spec(cfg).label` (the same labels the logs use) and group by it; charts use the labels
on the x axis.

### Q461. Strata validation and the framework-column trap
**Context.** `eda.md` open question (the 10-29 silent-failure audit): `strata.variables` naming a
key or a framework column (`unit_id`, `period`, `target`, `split`, `eligible`) would silently
use the framework's column, since a source column of that name is read as `source_<name>`.

*Default:* `run_eda` (and `run_feature_checks`) check the strata first: a framework name is
refused with the `source_<name>` hint; a name that is not a frame column fails naming the
columns; a numeric stratum with more than `strata.max_levels` distinct values is refused ("bin
it upstream or list the levels"); `eda.key_features.include` names must be candidates. The
modelling tags are strata automatically (D-129), never listed.

### Q462. Another use case's label as a candidate
**Context.** `dataset.md` open question (the 10-29 ML audit): a label column known to the DS but
not shared in the model input is an ordinary candidate; whether a use case should declare other
labels it knows about (`data.exclude_labels`).

*Default:* no new field. `features.candidates.exclude` already takes patterns for columns the DS
knows to be labels, and `leakage.too_strong` flags the rest (the `upstream_target` trap scores
1.0). The open question closes with that answer.

## Assumptions you can veto
- A1. EDA never samples rows for statistics; only the distribution charts take
  `eda.chart_sample_share` (Q438).
- A2. The report's label-based views use the eligible rows of the window only; the population
  views every row after the analysis filters; nothing shows a period after the window (D-030).
- A3. The ranking statistic and the key features are computed on the eligible rows, labels
  included, before any split (D-030); the EDA report states the cost (Q432).
- A4. Every threshold of section E is a config parameter with a low default; none is a code
  literal (the crunch's failure).
- A5. One run per data definition per stage on disk (the latest); the resolved config saved
  with it names the entries it replayed.
- A6. EDA and Feature Checks read the frames from the model input when the config names one,
  else in memory, through `build_frames` only; neither assembles its own frame.
- A7. Reports embed plotly.js and load nothing from the network; plotly 6.3.1 / plotly.js 3.1.1
  as pinned.
- A8. The version becomes 0.3.0 at the end of Stage 2.
- A9. Decisions from D-134; re-read the last D-row before numbering (another chat may add rows).
- A10. Nothing here changes the data definition or the model input's sidecar (schema 3 stays).
- A11. `jinja2==3.1.6` (the devcontainer's version, needed by pandas Styler's HTML) is pinned in
  `requirements.txt` on first use (D-012 (devcontainer packages are pinned when first used));
  statsmodels is not needed (Wilson from scipy's `binomtest`, the t-interval from `scipy.stats.t`).
- A12. The regression concordance uses Kendall's τ-b from scipy (O(n log n)); for zero-inflated
  amounts a two-part screen (zero vs non-zero, then the non-zero rows) is a practitioner pattern
  noted for M4, not built now.

## Facts to check on the pinned versions before the build (fact-check agent, local runs)
Verified by the research survey (2026-10-30, local runs): `binomtest(...).proportion_ci(
method="wilson")` on scipy 1.16.2; `get_plotlyjs()` is plotly.js 3.1.1 (4.83 MB) and the
fragment pattern renders; `pandas.api.types.infer_dtype` reports mixed types; Styler's
`max_elements`. Still to check:
- `scipy.stats.kendalltau` on 600,000 rows with ties: runtime and the τ-b variant.
- `sklearn.metrics.roc_auc_score` with a constant score column raises; the concordance
  function must return 0.5 for a constant feature instead.
- `pandas.io.formats.style.Styler.to_html()` on 2.2.3 with jinja2 3.1.6 once it is installed.
- Spark `DecimalType` arrives in pandas as `object` holding `Decimal` through Arrow, or as
  float64: which, on 3.4.3 (the mart's `cc_limit` is `decimal(18,2)`).
- A pandas `groupby` on `datetime.date` objects vs on the label strings: speed on 600,000 rows.
