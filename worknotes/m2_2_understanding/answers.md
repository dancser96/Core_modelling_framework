# Stage 2 (M2.2 Understanding): the record of questions and answers
_Round 1 (Q418–Q462 and Q447b): written 2026-10-30, answered 2026-11-02 · rounds 2 (Q466–Q476),
3 (Q477–Q489, A19–A36) and 4 (Q490–Q493): written and answered 2026-11-02, recorded in order after
round 1 · the null-value assumptions register (N1 onwards) follows round 3 · every question verbatim as
asked, each followed by the SDS's answer verbatim and the outcome for the plan · the record the
build plan is written from, kept complete through context compaction (the SDS, 2026-11-02) · no
round is open · cited decisions are summarised in brackets (D-072 (k))
· the folder is deleted when the stage is done_

**Where it stands (2026-11-10): Stage 2 is built (0.3.0). The record runs to Q547 and R58, every
question answered; the plan was approved on 2026-11-03 and its decisions to veto are `plan.md`
§9 (V74–V103 still open, for the Feature Checks code review).** Stage 2 is M2.2 Understanding:
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

## The SDS's generic remarks (2026-11-02), and where they went
1. **"What does the feature ledger exactly do?"** Explained in round 2's preamble (`questions.md`
   → "What the feature ledger does"); the shape stays as in Q450.
2. **A correlation-based view that weighs correlation against predictiveness, keeps both when
   both are strong, and shows second-order effects (how replaceable a feature's signal is).**
   Round 2, Q472: redundancy clusters with each member's concordance and its share explained by
   the other members; the model-based part (grouped permutation importance) belongs to
   Training / Evaluation (M2.3) and is noted there.
3. **EDA on one snapshot, normally the window's last period; the whole window the exception;
   EDA on the latest available data when nobody intends to model.** Round 2, Q466 (`eda.snapshot`)
   and Q476 (EDA-only configs without a validation period). The per-period target evolution
   stays on the whole window (Q433).
4. **The 0.5.3 look-ahead trap `holding_cnt_trap_lookahead` in `fs_extract`** (the client's
   last-month holding count stamped on every month; AUC 0.81, below the oracle; constant per
   client, so neither the leakage screen nor a backward check sees it). Round 2, Q475: a
   look-ahead finding, or the kind accepted as uncaught.

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


**Answer (the SDS, 2026-11-02):** Option (A), I am fine with the additional timeline requirements, coming from a “flashy” and “demo” perspective this is important to prioritize getting good now.

**Outcome for the plan:** (A): section 0 is the target; the reports are where the depth goes.
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


**Answer (the SDS, 2026-11-02):** Accepting the change.

**Outcome for the plan:** (A): Stage 2 about 11-03 to 11-11; M2.3 from 11-12, M2.4 to about 11-25; the synthetic to-do and per-source keys (landed 11-02, commit 2803fcb) run beside major step 1; `worknotes/timeline_proposal.md` gets the dates with the plan.
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


**Answer (the SDS, 2026-11-02):** Default (A).

**Outcome for the plan:** (A): real regression functions, tested on a test-only variant config.
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


**Answer (the SDS, 2026-11-02):** I’d rather have a statistics subfolder, which contains all statistical calculations (potentially in a few files) to be imported in EDA, Feature Checks, Modelling and Model reporting and keep the modules focused only on their steps. This also enforces you to write reusable functions, which I highlighted as an issue before. The same applies to reporting subfolder, the reusable functions for reporting at all steps shall be bunched there.

**Outcome for the plan:** `core_modelling/statistics/` (a few modules: concordance, intervals, distributions, association) holds every statistical calculation; `core_modelling/reporting/` every reusable reporting function; `eda/` and `feature_checks/` only orchestrate their steps and import from both. The plan lists each statistics function once with every stage that uses it.
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


**Answer (the SDS, 2026-11-02):** Default (A).

**Outcome for the plan:** (A): the stage function resolves the config itself.
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


**Answer (the SDS, 2026-11-02):** Default (A).

**Outcome for the plan:** (A): one `StageResult`.
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


**Answer (the SDS, 2026-11-02):** I don’t have a problem with your proposed structure, but I have an issue/question with the upstream folder order. First of all, I don’t know, what <ddh> means. Second of all, at least in HDFS, <entity> will be resolved before the kedro-like data structure and also because the use-case name will be in the config, that should be the “upstream driving force”. So in effect, in my opinion, the actual HDFS folder will be something like <hdfs://xyz>, where xyz already contains entity, then /<usecase> and then /<0X_stage> which has the kedro-like stages from <01_raw> to <08_reporting>.

**Outcome for the plan:** The folder contents stand (`eda/`, `feature_checks/`, the ledger, beside `decisions/`). `<ddh>` is the short data-definition hash (12 characters), the key of everything EDA and Feature Checks write (D-088). The order becomes root (per entity) → use case → layer: round 2, Q470.
### Q425. Public API additions
**Context.** D-024: the shipped notebooks call only public functions, which a test checks.

**The proposal:** `run_eda`, `run_feature_checks` (stage functions), `StageResult`, and
`pivot_target` (the notebook tool of Q439). `write_report`, the ledger and the statistics stay
private. `run` gains the stages `eda` and `feature_checks` (`run --stages eda feature_checks`),
run in order; Feature Checks refuses to run without an EDA artifact for the same
data-definition hash (Q447).

*Default:* as proposed.


**Answer (the SDS, 2026-11-02):** I’ll probably accept the default, but have one maybe stupid, but important question here: If this repo will be imported through Nexus as a package, how does anyone open notebooks? Will they have to manually copy from the main repo or is there a way to automatically duplicate all package notebooks into the notebooks section?

**Outcome for the plan:** Default accepted. How users get the notebooks: round 2, Q471 (shipped inside the package, copied out by a CLI command).
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


**Answer (the SDS, 2026-11-02):** I support option (A) as creating a default, but this has to be displayed, validated and checked with the user (in the manual/assisted mode) and user should have the ability to reassess. Especially with integer score examples, a 0-10 range would potentially be casted as categorical by default, but that would lose ordinality.

**Outcome for the plan:** (A) as the default. Note: a numeric with few values keeps the numeric kind (its order is used by the statistic); only its display is a level table. The kinds are shown, validated and overridable: round 2, Q469.
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


**Answer (the SDS, 2026-11-02):** I like the idea of one measure meaning the same, my question is twofold: First, I’m not that familiar with Kendall’s tau, can you explain why that maps to the same as univariate AUC? Second, as we’ll move along the proposed order of modelling types to be included, will this be sustainable?

**Outcome for the plan:** (A) stands, with the statistic defined as Somers' D of the feature with respect to the target, rescaled to [0.5, 1] after the direction: exactly the AUC for a 0/1 target, the share of concordant row pairs for a continuous one; computed from Kendall's τ-b and the tie counts (scipy, O(n log n)). The explanation and the task-by-task sustainability are in round 2's preamble.
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


**Answer (the SDS, 2026-11-02):** Default (A).

**Outcome for the plan:** (A): shrunk level encoding, then the task's concordance.
### Q429. Missingness: never imputed into the statistic
**Context.** The crunch median-imputed before every statistic, mixing the missingness pattern into
the signal (legacy survey). The missing-leak trap carries its whole signal in *whether* the value
is filled.

**The proposal.** The concordance is computed on the non-null rows only. Missingness gets its own
two numbers: `missing_share`, and `null_concordance`, the task's concordance of the null
indicator (0/1) against the target, computed when the missing share lies in [0.005, 0.995].
The leakage step reads the second (Q441). Bins and level tables show nulls as their own bin.

*Default:* as proposed.


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** As proposed: no imputation; `missing_share` and `null_concordance` beside the statistic.
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


**Answer (the SDS, 2026-11-02):** Default (A).

**Outcome for the plan:** (A): `strata.min_events` for strata and periods; 20 events for bins.
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


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** As proposed: one PSI with a null bin and fixed reference bins.
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


**Answer (the SDS, 2026-11-02):** Accepting the default, but see my generic comment on EDA.

**Outcome for the plan:** As proposed; the choices block names the EDA snapshot once Q466 is answered.
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


**Answer (the SDS, 2026-11-02):** Agreed with most defaults. I’d add here that obviously looking at target count evolution across the training window is useful independent to what my generic comment on EDA was.

**Outcome for the plan:** As proposed; the target-per-period table and chart (rows, positive rows, positive events, rate with interval) always cover the whole window, whatever the EDA snapshot (Q466).
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


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** (A): the label-free reference-group comparison with standardised mean differences.
### Q435. The univariate ranking table
**The proposal.** One row per candidate, on the eligible rows: `feature`, `kind`,
`missing_share`, `levels` (distinct non-null values), `dominant_share` (the share of the most
common value), `concordance`, `direction`, `null_concordance`, `rank` (by concordance, ties by
name), `key_feature` (`top_n` / `listed` / empty). Styled with a bar on the concordance, the
key features marked, the lineage columns listed underneath as auto-excluded. Core. Written to
the ledger (Q450).

*Default:* as proposed.


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** As proposed.
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


**Answer (the SDS, 2026-11-02):** Accepting default per feature deep dives as a start, but I only want N=10 for both autonomous and assisted and if not too much extra code, I want an additional filter: Going down in AUC order, if the next “key feature” selection is highly correlated (with some parametrizable default like 0.9) with any of the previous features which have been analyzed on, that feature should be skipped (and not counting towards N). This would ensure that we don’t get effectively same prints on the same raw feature with different aggregation windows or printing the “inflow”, “outflow”, “total flow” of the same underlying data which three will obviously be very similar.

**Outcome for the plan:** (A) for the deep dives' content; N = 10 at both levels (D-132's point (2) changes: the levels differ only by the person's list) and a correlation skip while walking the ranking: round 2, Q467.
### Q437. Strata pivots: extended views
**The proposal.** For the top five key features and each stratum variable: the rate (lift) by
feature bin × stratum level as one styled table, colour by lift, insufficient cells greyed. The
extended section; everything else by stratum is left to `pivot_target` in the notebook.

*Default:* as proposed (five features; name another number if you want).


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** As proposed: pivots for the top five key features.
### Q438. Chart sampling
**Context.** `eda.chart_sample_share` exists in the schema with no code. The counts and rates
never sample; only the raw-value distribution charts (ii of Q436) need it.

**The proposal.** When set, the distribution charts draw a seeded pandas sample of that share of
the eligible rows; the report states it on each affected chart and in the choices block. Nothing
else samples.

*Default:* as proposed.


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** As proposed.
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


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** As proposed: `pivot_target`, public.
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


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** As proposed; `eligibility_constant` folds into `quality`; a `nulls_may_be_zeros` finding joins in round 2 (Q468).
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


**Answer (the SDS, 2026-11-02):** Can you explain what missingness_leak would mean here? Might or might not be connected, but one thing that came to my mind here is the following check: Assuming we have 80% missingness but otherwise non-zero values, upstream that did not get filled in but somehow it’s fairly clear missingness would actually mean zero values for this feature, how would that be captured and suggested to be changed? Especially important when we are talking about regression or any model type which requires imputation for missing values, how that imputation works is a key component for results.

**Outcome for the plan:** As proposed, with the explanation in round 2's preamble (`missingness_leak`: whether the value is filled predicts the target, whatever the value). The nulls-mean-zero case becomes a quality finding and the framework's no-imputation stance is stated: round 2, Q468.
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


**Answer (the SDS, 2026-11-02):** Default (A).

**Outcome for the plan:** (A): the lag check; D-029 (d)'s wording changes with the decision row.
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


**Answer (the SDS, 2026-11-02):** Default (A).

**Outcome for the plan:** (A): `psi_max` 0.10 and Cochran's Q.
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


**Answer (the SDS, 2026-11-02):** I don’t fully understand the question, why do we need reimporting label-free? Why isn’t it just an automatic feature exclusion from config which already contains what the target will be?

**Outcome for the plan:** (A) stands; the misunderstanding is explained in round 2's preamble: this is about the rows of later periods the drift comparison needs, not about the target column as a feature (the lineage already excludes that). The frame is renamed `Frames.drift` (the eligible rows of the gap periods and the latest period, label dropped), which says what it is for.
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


**Answer (the SDS, 2026-11-02):** Accepting defaults, but look into general comments about VIF and correlation for this.

**Outcome for the plan:** The pairwise findings stand; the primary view becomes the redundancy clusters with concordance and the explained-by-others share: round 2, Q472.
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


**Answer (the SDS, 2026-11-02):** Default. One important note here is that these default values (all default values which are not immediately obvious for a DS what they would be) have to be filled in the template as well; never assume the user has very deep knowledge, you’d be surprised.

**Outcome for the plan:** As proposed, and a rule for the stage: every default of every new parameter appears in `TEMPLATE.yml` with a plain one-line explanation of what it measures and when to move it (the Stage 1 template test already checks that every schema field is on display; the plan adds the explanation requirement to the review guide).
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


**Answer (the SDS, 2026-11-02):** Default (A).

**Outcome for the plan:** (A): Feature Checks requires EDA's artifact.
### Q447b. The standard-error lesson is corrected
**Context.** `lessons.md` ("Univariate AUC floor") and D-082 reason with "SE ≈ 0.5 / √events".
The exact null SE of an AUC is √((n₊ + n₋ + 1) / (12 n₊ n₋)) ≈ 1/√(12·n₊) ≈ 0.29/√n₊ (the
research survey's simulation at 800 events: 0.0105 measured, 0.0102 by the formula, 0.0177 by
the lesson's rule). The conclusion of the lesson ("with ~800 events the third decimal is noise")
stands; the constant is wrong by 1.7×, which matters for Q443's test and for Training's floor
later (0.515 is about 1.5 SE at 800 events, not 0.85 SE).

*Default:* `lessons.md` and D-082 are corrected in this stage; every SE the framework shows is
Hanley–McNeil's (the null form where the concordance is 0.5), computed in `statistics.py`.


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** The SE lesson and D-082 are corrected; Hanley–McNeil SEs everywhere.
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


**Answer (the SDS, 2026-11-02):** Some questions: If I go with option (A), does that mean that if the user does not specify keep_despite_flag on the columns, they will get dropped? Another question is that with the more strict thresholds from above, are those being enforced by the autonomous run then?

**Outcome for the plan:** (A) stands. Answers (also in round 2's preamble): no, a flag never drops anything, at any level: a flagged feature stays a candidate and reaches training unless a person excludes it; `keep` only closes the flag and protects the feature from automated pruning; an open flag blocks `register`, not training (D-031). The thresholds are not enforced at either level: they only decide what is flagged; `autonomous` differs from `assisted` only in not waiting for the flag review before training (D-132). The verbs are simplified in round 2, Q473.
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


**Answer (the SDS, 2026-11-02):** Look at my answer for Q448, I’m already confused how the flag + exclude + keep_despite_flag will work, please explain and also simplify, I don’t see the reason why we should complicate decision recording with runes like exclude for leakage and time-alignment findings, keep_despite_flag for quality, stability and redundancy.

**Outcome for the plan:** (B): the grouping and the call text, no suggested operation. The model is three verbs: the framework flags; a person excludes or keeps; round 2, Q473 (with the rename of `keep_despite_flag` to `keep`).
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


**Answer (the SDS, 2026-11-02):** I agree with the wide format, but as in the general comment, would like to understand what exactly the feature ledger will do.

**Outcome for the plan:** (A) wide; what the ledger does is explained in round 2's preamble (one row per candidate that accumulates the evidence and the decisions of every stage: the per-feature view of the audit log plus the statistics; it decides nothing).
### Q451. Who writes which columns, and when
**The proposal.** EDA creates the ledger (identity + EDA) and rewrites it whole on a rerun;
Feature Checks reads it, adds its columns and rewrites the file, refusing a ledger whose EDA
columns are missing (Q447). A Feature Checks rerun replaces its own columns. The ledger is
rendered in both reports (EDA: identity + EDA; Feature Checks: everything plus the decisions).

*Default:* as proposed.


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** As proposed.
### Q452. Readable labels and the source per feature
**Context.** The sketch lists an optional readable label and the source column (D-046: no
per-source catalogue). The frames don't carry which logical source a column came from.

*Default:* neither in Stage 2. A `source` column joins when the join log records columns per
source (cheap, with Inference's needs in M2.4).


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** Neither in Stage 2.
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


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** As proposed.
### Q454. The chart primitives and the chart rules
**The proposal.** `reporting/charts.py`, each a function returning a plotly figure, each obeying
the chart rules of `reporting.md` (axes from the data, lift where rates are tiny, counts and
intervals always, log axis for heavy tails, one colour per level across a report):
`lift_by_bin` (bars with error bars and event labels), `distribution_by_class` (box plots, log
axis by skew), `rate_per_period` (markers with error bars, events as bars on a second axis),
`lift_by_level` (bars with error bars), `psi_by_period`, `concordance_by_period`. Each chart
reviewed in Stage 2 extends the rule set in `reporting.md`.

*Default:* as proposed.


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** As proposed.
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


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** (A): no cap, pre-aggregated figures, size and open time measured.
### Q456. The theme
*Default:* `reporting/theme.py` holds the neutral palette, fonts and the categorical colour
sequence as a dict; `environment.theme` (a path, exists since Stage 1) is read in M4, when the
bank's theme is known. Nothing in the repo names a brand.


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** The neutral theme dict; the theme file in M4.
### Q457. Two reports, each stage standalone
**Context.** D-036 lists EDA and Feature Checks as two report writers; the roadmap's M2.2 goal
says "the EDA + Feature Checks report". The two stages are standalone (D-036) and may be rerun
separately.

*Default:* two files, `eda/report.html` and `feature_checks/report.html`; the Feature Checks
summary repeats the EDA headline numbers (from `eda.json`) so a reader of the second report
knows the population.


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** Two reports.
## H. Notebooks, tests, docs

### Q458. Notebooks: one per stage, first-draft guidance
**The proposal.** `notebooks/02_eda.ipynb` (setup; `run_eda`; the report path; the headline,
funnel, ranking and one deep dive displayed inline from `result.tables`; `pivot_target`
examples; what to look at and what to record) and `notebooks/03_feature_checks.ipynb` (setup;
`run_feature_checks`; the flags grouped per feature; the proposed decisions; a commented
`record_decision` cell; `show_decisions`; the ledger). Guidance cells written now as a first
draft; D-022 (e): the LDS reviews the guidance in M3 as the proxy user.

*Default:* as proposed.


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** Two notebooks with first-draft guidance.
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


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** As proposed; the look-ahead trap's mapping joins from Q475.
### Q460. Period labels in pandas
**Context.** `period` arrives as `datetime.date` objects (`dataset.md` open question).

*Default:* no dtype change in the frames; EDA and Feature Checks add `period_label` through
`period_spec(cfg).label` (the same labels the logs use) and group by it; charts use the labels
on the x axis.


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** `period_label` through the period spec; no dtype change.
### Q461. Strata validation and the framework-column trap
**Context.** `eda.md` open question (the 10-29 silent-failure audit): `strata.variables` naming a
key or a framework column (`unit_id`, `period`, `target`, `split`, `eligible`) would silently
use the framework's column, since a source column of that name is read as `source_<name>`.

*Default:* `run_eda` (and `run_feature_checks`) check the strata first: a framework name is
refused with the `source_<name>` hint; a name that is not a frame column fails naming the
columns; a numeric stratum with more than `strata.max_levels` distinct values is refused ("bin
it upstream or list the levels"); `eda.key_features.include` names must be candidates. The
modelling tags are strata automatically (D-129), never listed.


**Answer (the SDS, 2026-11-02):** Default.

**Outcome for the plan:** As proposed.
### Q462. Another use case's label as a candidate
**Context.** `dataset.md` open question (the 10-29 ML audit): a label column known to the DS but
not shared in the model input is an ordinary candidate; whether a use case should declare other
labels it knows about (`data.exclude_labels`).

*Default:* no new field. `features.candidates.exclude` already takes patterns for columns the DS
knows to be labels, and `leakage.too_strong` flags the rest (the `upstream_target` trap scores
1.0). The open question closes with that answer.


**Answer (the SDS, 2026-11-02):** If the default means that other use case’s labels can be model inputs, then I agree.

**Outcome for the plan:** Agreed with a caveat the SDS should see: an upstream forward-looking column (another use case's label) is a time-separation violation (§4.1) whether or not a screen flags it, so the template's guidance and an optional name-pattern flag are round 2's Q474.
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
- `sklearn.metrics.roc_auc_score` with a constant score column returns 0.5 on sklearn 1.8
  (measured 2026-11-02 by the gap analysis; round 1's note that it raises was wrong), which the
  concordance function's 0.5 for a constant feature matches.
- `pandas.io.formats.style.Styler.to_html()` on 2.2.3 with jinja2 3.1.6 once it is installed.
- Spark `DecimalType` arrives in pandas as `object` holding `Decimal` through Arrow, or as
  float64: which, on 3.4.3 (the mart's `cc_limit` is `decimal(18,2)`).
- A pandas `groupby` on `datetime.date` objects vs on the label strings: speed on 600,000 rows.

**Assumptions A1–A12:** none vetoed in round 1; they hold for the plan.

---

# Round 2: questions and answers
_Round 2: written 2026-11-02, answered by the SDS 2026-11-02 · Q466–Q476, every question verbatim as
asked, each followed by the SDS's answer verbatim and the outcome for the plan · the SDS's remarks on
the round-2 explanations come first, the explanations themselves are kept at the end of this section_

## The SDS's remarks on round 2 (2026-11-02), and where they went

- **Concordance (Q427's explanation):** "Thanks for the explanation, I'd go with this then. One note
  though: if I didn't know how this works, most people won't either, so at least in the notebook
  explain this with a quick summary as it's very valuable but not obvious." → **Outcome:** the
  statistic stands. Notebook 02 opens its ranking section with a short markdown explanation (pairs
  of rows; exactly the AUC for a 0/1 target; the share of correctly ordered pairs for an amount;
  0.5 means no information, 1 perfect ordering); the EDA report's ranking section carries the same
  in two sentences as a "how to read" line; the glossary gets `concordance`. The explanation as
  written for the SDS is kept below, under "Explanations given in round 2".
- **Q448–Q449:** "What's the point of flagging if for an autonomous run, they are not getting
  excluded? What you are saying with this is that for an autonomous run, feature checks
  'essentially' do nothing." → **Outcome:** accepted as a design change. The flags must act: round
  3's Q477 proposes that an open flag holds the feature out of training until a person keeps or
  excludes it, at both levels, with the decision rows (D-031, D-132 (3), `CLAUDE.md` §4.6) reworded.
- **`missingness_leak`:** "If the definition is 'Whether the value is filled predicts the target',
  but in a weak-ish way (not super high AUC), is that a leak or should that be just a guide on how
  to impute values (to min instead of median etc)?" → **Outcome:** both, from one statistic: a
  strong null concordance is the leak flag (the filling process depends on the outcome: ask how
  the field gets filled); a weak one is informative missingness, a `quality` note that says the
  nulls carry information and must stay their own group (Phase 2's tree families take nulls
  natively; a family that imputes later must impute outside the value range, never the median).
  The two thresholds are round 3's Q478.
- **A14 (mixed-kind pairs):** "How much extra work/code would it be to include mixed pairs
  computation already?" → **Outcome:** about ten lines plus a test (the correlation ratio on the
  ranks of the numeric by the categorical's levels, on the same 0–1 scale); costed in round 3's
  Q481 with the default to include it. A14 is withdrawn.

## Round 2 questions

### Q466. EDA's rows: one snapshot by default
**Context.** Your remark: EDA is normally a single-snapshot analysis, preferably the window's last
period; the whole window is the exception for small data. D-030 (EDA uses every client of the
window after the analysis filters, labels included) was decided for "every client, not the train
split", and the window scope came with it. Statistically: one conversion is positive in up to `w`
consecutive rows, so the window's positive rows overstate the evidence (D-082), while a single
snapshot's positive rows are its events; the window pools about two to three times the events
of one snapshot for a six-month window with `w = 3`, which matters for rare targets.

**The proposal.** `eda.snapshot: last | window | <period>`, default `last` (the window's last
period: the most recent features, labels matured). Snapshot views: the headline, the strata
tables, the reference groups, the ranking, the key features and their deep dives, the pivots'
default rows. Window views, whatever the snapshot: the funnel per period and the target per
period (your Q433 point), and Feature Checks entirely (stability needs the periods; leakage and
quality run on every eligible row, for the events). A warning when the snapshot holds fewer than
500 events: "set `eda.snapshot: window`". The frames don't change (the window is collected; the
snapshot is a pandas filter), the choices block names the snapshot, and D-030's EDA clause is
reworded to "every client of the snapshot (default the window's last period) or of the window".

**Options.**
- (A) As proposed, default `last`.
- (B) Default `window` (round 1's design), `last` as the option.

*Default:* (A).

**Answer (the SDS, 2026-11-02):** Option (A), as proposed now

**Outcome for the plan:** (A): `eda.snapshot: last | window | <period>`, default `last`; the snapshot views and the window views as listed; the warning below 500 events; D-030's EDA clause is reworded with the decision row.

### Q467. Key features: N = 10 at both levels, with a correlation skip (Q436)
**The proposal.** `eda.key_features.top_n` defaults to 10 at both levels (D-132's point (2)
becomes: the levels differ only by the person's list at `assisted`). A new field
`eda.key_features.max_correlation: 0.9`: walking down the ranking, a candidate whose absolute
Spearman correlation with any already chosen key feature is at or above it (categorical pairs:
Cramér's V) is skipped, does not count towards N, and is listed in the ranking table under
`represented_by` with the feature that covers it; listed (`include`) features are never
skipped. The correlation matrix among the candidates is computed once in EDA
(`statistics/association.py`, on the snapshot's eligible rows with a seeded cap of 200,000 rows,
stated in the report) and saved as a table that Feature Checks' redundancy step reuses (Q472).

**Options.**
- (A) As proposed: Spearman for numeric pairs, Cramér's V for categorical pairs, mixed pairs not
  compared.
- (B) Numeric pairs only.

*Default:* (A).

**Answer (the SDS, 2026-11-02):** Option (A), as proposed now

**Outcome for the plan:** (A): N = 10 at both levels, `eda.key_features.max_correlation: 0.9`, the `represented_by` column, the correlation matrix computed once in EDA and saved for Feature Checks. Mixed pairs join it if round 3's Q481 is accepted (the SDS asked for the cost; A14 is withdrawn).

### Q468. Nulls that mean zero, and the no-imputation stance (Q441)
**Context.** Your case: 80% missing, the non-null values never zero, and the nulls clearly stand
for zeros that nobody filled upstream. D-029 (c): a source that codes a value as null fills it
upstream; the framework never does.

**The proposal.**
- A `quality` finding `nulls_may_be_zeros`: a numeric with missing share ≥
  `nulls_may_be_zeros_missing_min` (0.2) whose non-null values hold no zeros (zero share ≤
  0.005), i.e. a count or amount with nulls but never a zero. The flag's text: "if a null means 0
  here, fill it upstream; the framework never imputes". The ranking table shows `zero_share` for
  every numeric beside `missing_share`, so the pattern is visible for every feature.
- The stance, written into `training.md` and the template: Phase 2's three families (LightGBM,
  XGBoost, CatBoost) take nulls natively (each learns a default branch for a missing value), so
  the framework imputes nothing and a null stays a value the model sees, for binary and
  regression alike. A family that needs imputation (Phase 3's predefined path with linear
  models) declares its imputation policy in its own family entry then; nothing is built now.

**Options.**
- (A) The finding and the stance.
- (B) The stance only; the `zero_share` column shows the pattern.

*Default:* (A).

**Answer (the SDS, 2026-11-02):** It’s a good point you brought up from D-029 (c); for this reason, I actually only want the quality finding, user should review from there. In addition, combining this with the comment on missingness_leak, there should be a quality finding on both this (nulls may be zeros) or nulls convey info

**Outcome for the plan:** The findings only, no doctrine: D-029 (c) already says the framework never fills a null, so nothing new is written about imputation beyond each finding's own text. Two `quality` findings, both **notes** (they never hold a feature out, round 3's Q477): `nulls_may_be_zeros` (missing share ≥ 0.2, no zeros among the non-null values: "if a null means 0 here, fill it upstream") and `nulls_informative` (the null indicator's concordance between 0.55 and the leak threshold: "nulls carry information; keep them as their own group"); the ranking table shows `zero_share` and `null_concordance` for every feature. The thresholds and the split against `leakage.missingness_leak` are round 3's Q478.

### Q469. Column kinds: shown, validated, overridable (Q426)
**Context.** Your condition: the schema-derived kind is a default that is displayed, validated and
reassessable. Note on your example: a 0–10 integer score keeps the numeric kind under round 1's
rule; only its deep dive is a level table, and the statistic uses its order. The case that needs
an override is the reverse: an integer that is a code (a branch number), or a string that is
really ordered ("low / mid / high"; an ordered-categorical kind belongs to Training's encoder,
M2.3, and is noted there).

**The proposal.** `features.kinds: {<column>: numeric | categorical}` overrides the default for
named columns; it is loggable (`set features.kinds`, stage `eda`: a reassessment reruns from EDA)
and sits outside the data-definition hash (it changes how a column is read, not which rows or
columns). EDA prints a kinds summary (numerics, categoricals, unsupported, the discrete numerics
by name, the overrides) and the report's choices block shows the same; a `kinds` table is saved.
An override naming a column that is not a candidate fails loud; a `categorical` override on a
numeric column with more than `quality.max_levels` distinct values gets the `high_cardinality`
flag like any categorical.

**Options.**
- (A) As proposed, loggable, outside the hash.
- (B) In the data definition (hashed): a change needs a new config and reruns everything.

*Default:* (A).

**Answer (the SDS, 2026-11-02):** Default (A)

**Outcome for the plan:** (A): `features.kinds: {<column>: numeric | categorical}`, loggable (`set`, stage `eda`), outside the data-definition hash; the kinds summary printed, in the choices block and saved as a table; an override of a non-candidate fails loud.

### Q470. The folder order: root per entity → use case → layer (Q424)
**Context.** Your points: `<ddh>` was unexplained (it is the short data-definition hash, 12
characters, D-088 (the hash of task, entity, sources, eligibility, target spec, period, window,
candidates), which keys everything EDA and Feature Checks write, so two data definitions of one
use case never overwrite each other); in HDFS the entity's area comes first and the use case
should drive the structure below it, with the layers inside.

**The proposal.** `roots.data` in the environment file becomes a mapping entity → root (the
laptop: `entity_a: /…/data/entity_a`; the bank: the entity's HDFS area). Under a root:
`<use_case>/<layer>/…` for the framework's **own outputs**: `04_feature/<ddh>/{decisions/,
eda/, feature_checks/, ledger.parquet}`, `06_models/<run_id>/` (M2.3), `07_model_output/`
(M2.4); reports live beside their artifacts, so `08_reporting` goes. The **inputs** stay
environment-mapped by logical name, wherever they physically are: the sources (`01_raw` on the
laptop), any intermediate table, and the model input (`05_model_input`), which several use cases
share (`retail_acquisition_input` serves `cc_acquisition` and `td_acquisition`) and therefore
cannot sit under one use case. The audit log's path changes from Stage 1's
`04_feature/<use_case>/<entity>/<ddh>/decisions/` (0.x, no migration, D-007 (c)); `data/README.md`
is rewritten; `roots.registered` and `roots.production` follow the same per-entity shape in M2.4.

**Options.**
- (A) As proposed.
- (B) Keep one `roots.data` with the entity appended by the framework (`<root>/<entity>/<use
  case>/<layer>`): one less mapping, but the bank's per-entity areas can't be expressed.

*Default:* (A).

**Answer (the SDS, 2026-11-02):** In my previous answer I said that in hdfs configs, entity will be baked into upstream, so I don’t know why either of your proposals would work

**Outcome for the plan:** Open; restated as round 3's Q479. The misunderstanding: the root the environment file holds **is already the entity's area** (inside the bank `hdfs://xyz` names the entity), so the framework must neither map entities to roots (option A) nor append an entity segment (option B). The restated proposal: one `roots.data` as today, and under it `<use_case>/<layer>/…` with no entity anywhere in the path; two entities under one laptop root are kept apart by the data-definition hash, which contains the entity (D-088).

### Q471. How users get the notebooks from a Nexus package (Q425)
**Context.** The package ships in the base image through Nexus (D-024); a use case lives in its
own repo (OD-02). Nothing today puts the guided notebooks or the config template in front of a
user who installed the package.

**The proposal.** The notebooks and the templates ship **inside the wheel** as package data
(`core_modelling/notebooks/*.ipynb`, `core_modelling/conf/TEMPLATE.yml`,
`environment.example.yml`), and one CLI command copies them out: `python -m core_modelling init
<folder>` creates a use-case folder with the notebooks, the template config and the environment
example, refusing to overwrite. The repo's `notebooks/` and `conf/base/` move under the package
(the test that notebooks import the Public API only follows them). Decided now; built in M2.4
with the other CLI commands, so Stage 2's two notebooks are written where they are today.

**Options.**
- (A) As proposed (`init`, M2.4).
- (B) Manual copy from the framework repo (the status quo, written into the setup guide).

*Default:* (A).

**Answer (the SDS, 2026-11-02):** Default (A)

**Outcome for the plan:** (A): notebooks and templates ship inside the wheel; `python -m core_modelling init <folder>` copies them out, refusing to overwrite; built in M2.4 with the other CLI commands. Stage 2's notebooks are written where they are today.

### Q472. The redundancy view: clusters, concordance, replaceability (your second remark, Q445)
**Context.** You want a view that weighs features' correlation against their predictiveness,
doesn't push to drop either of two strong features, and shows second-order effects (how
replaceable a feature's signal is given the others). Pairwise lists don't give that; VIF needs
imputation and hides constants (round 1).

**The proposal.** In Feature Checks' `redundancy` step, on the correlation matrix EDA saved (Q467):
- **Clusters:** average-linkage clustering on 1 − |Spearman| (numerics; scipy `linkage` /
  `fcluster`), cut at 1 − `correlation_max`; categoricals likewise on 1 − Cramér's V. A cluster
  with two or more members is a redundancy group; the pairwise finding `correlated_pair` stays
  as the flag, the cluster is how it is shown.
- **Per cluster, one table sorted by concordance:** feature, concordance, missing share, |ρ| with
  the cluster's best feature, and `explained_by_others`: the R² of the feature's ranks regressed
  on the other members' ranks (complete rows, numpy least squares), i.e. how much of this feature
  the rest of its cluster already carries. That is a within-cluster VIF (VIF = 1 / (1 − R²))
  without the imputation, the constants problem or the global O(p³). A member whose concordance
  is within 0.01 of the best is marked "both strong: keep both unless one is needed for
  explainability"; the report never suggests dropping.
- **Ledger columns:** `cluster`, `explained_by_others`, `partners`.
- **The model-based second order** (how much target signal is lost when a feature leaves, given
  the others) needs a fitted model: Evaluation (M2.3) computes permutation importance **per
  cluster** (grouped permutation importance) beside the per-feature one, so importance isn't
  split among near-duplicates; and Training's automated selection may use the clusters as a
  rule ("the top feature per cluster unless a person kept the others"). Both are noted for
  M2.3's questions, not built now.

**Options.**
- (A) As proposed.
- (B) Pairs only (round 1's default), clusters in M4.

*Default:* (A).

**Answer (the SDS, 2026-11-02):** Default (A)

**Outcome for the plan:** (A): the redundancy clusters (average linkage on 1 − |association|, cut at 1 − `correlation_max`), the per-cluster table sorted by concordance with |ρ| to the best member and `explained_by_others` (within-cluster R² on ranks), the ledger columns `cluster`, `explained_by_others`, `partners`; the report never suggests dropping; grouped permutation importance and the cluster rule for automated selection go to M2.3's questions.

### Q473. The decision verbs, simplified (Q448, Q449)
**The proposal.** Three verbs and no more: the framework **flags**; a person **excludes** or
**keeps** (plus `include` to reverse an exclude, and `set`, `revert`, unchanged). `keep_despite_flag`
is renamed `keep` everywhere (`record_decision(keep=[…])`, `decide --keep`, the entry's `op`,
`features.kept_despite_flags` → `features.kept`; 0.x, no migration: the only existing log folders
are local and are re-recorded). The `proposed_decisions` table groups the flagged features by
identical findings and shows: the features, the findings with their values, the concordance, and
one `record_as` call text with the verb left to the person (`exclude=[…]` or `keep=[…]`), plus a
one-line explanation of each finding, never a suggested verb (Q449's (B)).

**Options.**
- (A) As proposed, with the rename.
- (B) The table only; the operation keeps its Stage 1 name.

*Default:* (A).

**Answer (the SDS, 2026-11-02):** I like this proposal’s direction, but combine it with regards to my latest remark on Q448-Q449 and come with an updated proposal

**Outcome for the plan:** Direction accepted: three verbs (`flag` by the framework, `exclude` and `keep` by a person), `keep_despite_flag` renamed `keep`, the `proposed_decisions` table without a suggested verb. Combined with the Q448–Q449 remark into round 3's Q477: an open flag **holds the feature out of training** until a person keeps or excludes it, at both levels; the sign-off and `register` need every flag settled. D-031, D-132 (3) and `CLAUDE.md` §4.6 are reworded with the decision row once Q477 is answered.

### Q474. Another use case's label as a candidate: the §4.1 caveat (Q462)
**Context.** You agreed that another use case's label may be a model input. The caveat: an
upstream column that **looks forward** from the observation period (another product's "acquires
within the next 3 months" flag) is a time-separation violation as a feature (`CLAUDE.md` §4.1:
features are as-of the period), whether or not a screen flags it. Against a different target its
concordance may be modest, and the lag check only looks at features with concordance ≥ 0.6, so
such a column can pass unflagged and leak the future into production scores.

**Options.**
- (A) Guidance only: the template's `features.candidates.exclude` comment says "list every
  upstream column that looks forward from the period (other use cases' targets, 'next N
  months' flags)"; the EDA report's choices block shows the candidate patterns.
- (B) (A) plus a `leakage` finding `forward_name`: candidates whose names match the step's
  `forward_name_patterns` (default `["*next*", "*forward*", "*fwd*", "*future*"]`, a config
  list) are flagged "the name suggests a column built from later periods: confirm it is as-of
  the period". A name heuristic is brittle and only a nudge, which is what a flag is; the
  patterns are the DS's domain knowledge in config, like the candidate patterns, so the
  framework stays name-blind to the synthetic traps (D-064).

*Default:* (B).

**Answer (the SDS, 2026-11-02):** Sorry, for me the “label” meant something like “fd_activation” noting that client picked up fixed deposits this month and that this information could be used to predict whether she will also pick up credit cards; quite obviously “target” is not allowed to be used as per basic rules we already set

**Outcome for the plan:** Resolved as a misunderstanding: the SDS meant a **backward-looking** event flag from another use case ("picked up fixed deposits this month"), which is an ordinary candidate and needs nothing; a forward-looking target column is out by `CLAUDE.md` §4.1 and the DS's `features.candidates.exclude` patterns, as every forward-looking column is. Whether the cheap name-pattern note stays is round 3's Q480 (default: guidance only).

### Q475. The 0.5.3 look-ahead trap (your fourth remark)
**Context.** `holding_cnt_trap_lookahead` in `fs_extract` is the client's last-month holding count
stamped on every month: AUC 0.81 against card acquisition (below the oracle's 0.86), constant per
client while the holdings move. The ML audit expects neither the leakage screen nor a
forward-vs-backward check to see it; the lag check won't either, since the lagged value equals
the current one.

**Options.**
- (A) A `time_alignment` finding `client_constant`: a feature that never changes within a client
  across the window (for at least 99% of the clients with two or more rows) **and** has
  concordance ≥ 0.6. Text: "a static attribute, or a value from one date stamped onto every
  period: confirm it is as-of the period". Static legitimate attributes with signal (segment,
  onboarding channel) are flagged once and kept by a person; most sit below 0.6 anyway. Cost: a
  groupby-nunique on the window rows. The test harness's mapping gets `lookahead ←
  time_alignment.client_constant`.
- (B) Accept the kind as uncaught; the test harness remaps it to "uncaught by design".

*Default:* (A).

**Answer (the SDS, 2026-11-02):** Default (A)

**Outcome for the plan:** (A): the `time_alignment.client_constant` finding (constant within the client for ≥ 99% of the clients with two or more rows, concordance ≥ 0.6); the test harness maps `lookahead ← time_alignment.client_constant`.

### Q476. EDA-only configs: a validation period that may be null (your third remark)
**Context.** "A user who doesn't want to model but wants the EDA on the last available data."
Today `time.validation_period` is required, must lie `w` periods after the window and must exist
in the data with its labels matured, so the window can never end later than `latest − 2w`.

**The proposal.** `time.validation_period: null` is allowed: the config then says "no model is
trained from this config". The coverage check requires the spine to reach the window's last
period and the target source `w` periods beyond it; EDA runs (`eda.snapshot` picks any labelled
period, the latest labelled one being `latest − w`); Feature Checks runs with the drift
comparison against the latest period only (there is no gap); Training refuses, naming the field;
setting the period later is a `set` entry (it sits outside the data-definition hash, D-088) or a
new config.

**Options.**
- (A) As proposed.
- (B) Keep it required; an EDA-only user must leave `2w` periods of slack.

*Default:* (A).

**Answer (the SDS, 2026-11-02):** Default (A)

**Outcome for the plan:** (A): `time.validation_period: null` allowed; the coverage check reaches the window's last period plus `w`; EDA's snapshot is any window period (round 3 A32 corrects "any labelled period"); Feature Checks compares with the latest period only; Training refuses, naming the field; a later `set` or a new config adds it.

### Assumptions of round 2, and their status
- A13 (EDA collects the window frame and filters the snapshot in pandas): holds; collecting at a
  real size is round 3's Q482.
- A14 (mixed pairs wait): withdrawn by the SDS's remark; round 3's Q481.
- A15 (the model input's sidecar, schema 3, unchanged): holds. The rename of the audit-log
  operation `keep_despite_flag` → `keep` touches the **entry** schema, not the sidecar: round 3's Q483.

### Explanations given in round 2

#### What the feature ledger does (Q450, your first remark)
One table, one row per candidate feature (and one per target-lineage column), that accumulates
what every stage learned or decided about that feature. It decides nothing and holds no rule: the
config holds the candidates and the rules; the decision audit log holds every decision as an
entry (D-125 (every later decision is an append-only entry replayed into the resolved config));
the ledger is the per-feature read of both, plus the statistics. Its columns, by who writes them:
- **EDA:** kind, missing share, levels, concordance and direction, rank, key feature (and why).
- **Feature Checks:** the flags (`step.finding`), the statistics behind them (lagged
  concordance, per-period heterogeneity, PSI against the window, the gap and the latest period,
  the redundancy cluster and partners), the verdict (`pass` / `flagged` / `auto_excluded`).
- **The person** (read from the audit log when the report is rendered, never copied in):
  "excluded by #6: set after the offer", "kept by #7: digital adoption trend".
- **Training, M2.3:** what automated selection did and by which rule (the train-split
  statistic), whether the model used the feature, its importance and rank.

What it is used for: the Feature Checks report's one-row-per-feature view; the sign-off view
(M2.3: the model's features sorted by importance, flags grouped, D-031); the model card's
feature summary; the question "what happened to feature X, and why"; the question "initial vs
final features" (candidates − lineage − excluded − dropped = the feature signature); a DS
filtering it in a notebook. Stored as `ledger.parquet` beside the artifacts, versioned
(`ledger_schema_version`); the per-run part joins in M2.3, keyed by `run_id`.

#### Concordance: why one number serves both tasks (Q427)
The univariate AUC is a statement about **pairs of rows**: take one positive and one negative
row at random; the AUC is the probability that the feature is higher on the positive one (a tie
counts half). Written over all pairs whose targets differ: AUC = (concordant pairs + ½ tied) /
(pairs with different targets), where a pair is concordant when the feature orders the two rows
the same way the target does.

That sentence makes no use of the target being 0/1. For an amount, take every pair of rows with
different target values; the pair is concordant when the row with the larger amount also has the
larger feature value. The same ratio is then the probability that the feature orders two clients
the way their amounts do. That quantity is **Somers' D** (rescaled to [0, 1]); Kendall's τ is its
symmetric cousin, (concordant − discordant) over *all* pairs, and scipy computes τ-b in
O(n log n). From τ-b and the tie counts (one `value_counts` per column) we recover
concordant − discordant and divide by the pairs whose targets differ. So one function,
`concordance(x, y)`, gives: for a 0/1 target **exactly** the AUC (the pairs whose targets differ
are precisely the positive–negative pairs; the plan's test asserts equality with
`roc_auc_score`); for a continuous target the share of correctly ordered pairs. Direction is
taken out the same way for both (max(c, 1 − c), the sign reported beside it), so 0.5 means no
ordering information and 1 means perfect ordering, whatever the task.

Sustainability along D-081's order (binary → regression → multiclass → time-to-event →
forecasting): ordinal multiclass (a 1–5 grade) is the same formula unchanged; nominal multiclass
has no order, so its per-task entry is the mean one-vs-rest concordance (each class's indicator
against the feature); time-to-event is Harrell's C, the same pair counting restricted to pairs
the censoring leaves comparable, a drop-in; forecasting is a series task with no row-pair notion,
so its family defines its own ranking statistic in its spec entry, as D-050 (the per-task spec
holds every task-specific choice) intends. Every panel task therefore shares the scale and the
thresholds; the series family will not, by design.

#### Flag, exclude, keep: how the three verbs work (Q448, Q449)
- **The framework flags.** Every check runs identically at both levels with the same
  thresholds (D-023). A flag is a finding attached to a feature; it never removes the feature
  from anything (`CLAUDE.md` §4.6). A flagged feature stays a candidate and reaches training.
- **A person excludes or keeps.** `exclude` takes the feature out of the candidates for every
  later run (it stays in the ledger as excluded, with the entry's reason). `keep` closes the
  flag and protects the feature from Training's automated pruning. Both are audit-log entries
  with a reason, one entry per group of features (D-125). `include` reverses a person's exclude.
- **An open flag blocks `register`, not training** (D-031). At `assisted` the notebook ends
  Feature Checks with the open flags and the person records entries before training, as a
  convention; at `autonomous` training runs with the flagged features still in, the open flags
  travel to the sign-off view and the model card, and `register` refuses while any is open. So
  the thresholds enforce nothing at either level; they decide what a person must look at, and
  "low thresholds" means more to look at, never more dropped.
- **Training's automated selection (M2.3) is the only thing that drops by rule** (the
  concordance floor, the importance floor, on the train split), recorded as `dropped` entries;
  `keep` protects from it. A constant or all-null feature flagged by `quality` falls out there,
  with a record, without anyone having to decide.

Your two questions, in one line each: without a `keep`, a flagged feature is **not** dropped; the
thresholds are **not** enforced at `autonomous`, they flag exactly as at `assisted`. The
simplification is Q473: three verbs, `keep` renamed from `keep_despite_flag`, and the
proposed-decisions table no longer suggests a verb.

#### The drift frame, formerly "label-free" (Q444)
This is about **rows**, not columns. The target column is already out of the candidates by its
lineage (D-029 (d)); nothing here re-excludes it. The stability step compares each feature's
distribution in the window with the periods **after** it: the gap periods between the window and
the validation period, and the latest period the data holds, which is what production will
score next. Those rows live in the panel with a `target` column of their own, because Target
Factory labels every period it can (D-131). D-030 forbids using labels after the window (their
target windows overlap the validation period's), so when Feature Checks collects those rows it
drops `target` before the collect and leaves the validation period's rows out entirely, and a
test asserts both. The frame is renamed `Frames.drift` (the eligible rows of the gap periods and
the latest period, for distribution comparisons only), which says what it is for.

#### What `missingness_leak` means (Q441)
Whether the value is **filled** predicts the target, whatever the value is. The synthetic offer
code is a random code for 80% of the clients who take the card within three months and for 1% of
the others: its values mean nothing, but "is filled" has a concordance of 0.89. A legitimate
feature with informative missingness (no income recorded → a lower propensity) shows a smaller
null concordance, around 0.52–0.58. The threshold 0.60 is a prompt to ask when the field gets
filled. Your nulls-mean-zero case is a different finding: Q468.

---

# Round 3: questions and answers
_Round 3: written 2026-11-02, answered by the SDS 2026-11-02 · Q477–Q489 and the plan defaults A19–A36,
every question verbatim as asked, each followed by the SDS's answer verbatim and the outcome for the
plan · the SDS's three remarks come first · what the round left open (the Q477 confirmation, the
window-without-pandas design, the drift periods, Q489 explained) is round 4 in `questions.md`_

## The SDS's remarks on round 3 (2026-11-02), and where they went

- **A31 (nulls in each statistic):** "Okay, but keep track of all the assumptions you make with
  regards to null values." → **Outcome:** accepted with the condition. A **null-value assumptions
  register** (N1 onwards) is kept at the end of this file from now on; every assumption about
  nulls, made or inherited, is a numbered row with its source and status, added the moment it is
  made; the spec step moves the register into the owning component docs (a "Nulls" section in
  `eda.md` and `feature_checks.md`) and the register here points there.
- **The facts to check:** "Do I have to check these or will you?" → **Outcome:** I do. They are
  library-behaviour checks on the pinned versions, run in the plan's first minor step (a spike on
  the dev machine) and during the build; each result becomes a test or a `lessons.md` trap, and
  the list in `questions.md` carries their status. Nothing for the SDS to do.
- **Scope of the turn:** "For now, only record answers and let's solve the remaining few open
  questions." → round 4 holds only the open points: the Q477 confirmation, the window-without-
  pandas design (Q490, Q491), the drift periods (Q493) and Q489 explained (Q492). No spec, no plan.

## Round 3 questions

### Q477. An open flag holds the feature out of training, at both levels
**Context.** Your remark: "What's the point of flagging if for an autonomous run, they are not
getting excluded? ... for an autonomous run, feature checks 'essentially' do nothing." Round 2's
model (flags informational; `register` blocked while a flag is open) rests on D-031 (sensitive
thresholds so borderline cases reach a person; flags never drop a feature; `assisted` ends the
stage in a flag review; one sign-off gate after training, at every level), D-132 (3) (`autonomous`
does not wait: open flags go to the sign-off view and the model card) and `CLAUDE.md` §4.6
(screens flag, never auto-drop). Under it an `autonomous` run trains on leaking features and the
flags only surface afterwards; you are right.

**The proposal.** The verbs of round 2 stay (the framework **flags**; a person **excludes** or
**keeps**; `include` reverses an exclude; `keep_despite_flag` is renamed `keep`). What changes is
what a flag does:
- **Two kinds of findings.** A **flag** says "this feature should not enter a model as it is". A
  **note** says "look at this"; it never affects training. Which finding is which is one table
  (Q478), the same at both levels.
- **An open flag holds the feature out of training**, at both levels. Training's feature set is
  candidates − lineage − unsupported − excluded − held, where held = the features with an open
  flag. Nothing is dropped: a held feature stays a candidate, in the ledger, in every report, in
  Training's log, in the sign-off view and on the model card ("held: 7 features with open flags:
  …"). That is the difference from a drop: visible everywhere, reversible by one entry.
- **A person settles a flag** with `keep` (the finding is accepted; the feature returns to the
  next training run and is protected from Training's automated pruning) or `exclude` (the
  person's decision; the feature is out of every later run). A `keep` entry carries the findings
  it settles (`features` plus a new `findings` field, defaulting to every flag open on those
  features at the time): a **different** finding raised by a later run opens again; the same
  finding with new values does not.
- **The levels differ only in when the review happens.** `assisted` ends Feature Checks with the
  review (the notebook shows `proposed_decisions`, the person records entries, then trains);
  `autonomous` trains at once without the held features. Both reach the one sign-off gate
  (D-031). **`register` needs the sign-off and no open flag on a feature of the model's final
  list**, which holds none by construction; held features are listed on the model card and in
  the sign-off view and may stay held, undecided: forcing an entry for every held feature (a
  dozen PSI flags on features the model never used) would be rubber-stamping, which D-031 avoids.
- **Thresholds stay the same at both levels** (D-132). D-031's sensitive thresholds now mean the
  `autonomous` model is the conservative one (fewer features); a person brings features back at
  the review or the sign-off, never the other way round.
- **How the log carries it** (settled by the gap analysis, A19–A21 below): one `flag` entry per
  finding per run, written only when the finding's feature set changed; an empty set is allowed
  for `flag` only and closes the finding (today `replay.py` refuses an empty feature list for
  every feature operation, so a fixed upstream column would stay held forever); notes are never
  entries; the ledger stores statistics and flags, and `held / kept / excluded` is read from the
  log when a report or the sign-off view is rendered, never stored (a stored verdict is stale the
  moment a person records an entry).
- **Wording that changes**, in one decision row (D-134): `CLAUDE.md` §4.6 "Leakage screens flag,
  never auto-drop" becomes "Screens flag; a flag never removes a feature from the candidates: it
  holds the feature out of training until a person keeps or excludes it"; D-031's "Flags still
  never drop a feature" likewise; D-132 (3) becomes "both levels hold flagged features out of
  training; `assisted` reviews the flags before training, `autonomous` at the sign-off".

**Options.**
- (A) As proposed: the hold-out at both levels; `register` needs the sign-off and a clean final
  list; held features may stay held.
- (B) As (A), but `register` also requires every open flag settled, held features included.
- (C) The hold-out at `autonomous` only; at `assisted`, Training refuses to start while any flag
  is open ("settle the flags first").

*Default:* (A). (B) forces decisions on features the model never used; (C) turns a convention
into a refusal and costs an entry per flag before any training run, even a throwaway one.

**Answer (the SDS, 2026-11-02):** _(not listed in the SDS's round-3 answers)_

**Outcome for the plan:** **Taken as (A) by the round's rule** (an unanswered number takes its default), with a one-line confirmation asked in round 4 because it is the stage's main design change: an open flag holds the feature out of training at both levels until a person keeps or excludes it; findings are flags or notes; `register` needs the sign-off and no open flag on the model's final list, held features may stay held; thresholds the same at both levels; the log mechanics of A19–A21; `CLAUDE.md` §4.6, D-031 and D-132 (3) reworded in D-134.

### Q478. Which findings are flags, which are notes, and the two missingness thresholds
**Context.** Round 1 settled the steps, findings and thresholds (Q440–Q446); round 2 added
`nulls_may_be_zeros`, `client_constant` and the clusters. With Q477 every finding needs its
kind, and three things change on the way: (1) your `missingness_leak` remark splits the null
indicator's concordance into a flag and a note; (2) a drift flag at PSI 0.10 would hold every
trending legitimate feature (growing balances, the login roll-ups after the synthetic relaunch)
out of an `autonomous` model, and drift is Monitoring's concern, not a correctness one, so the
stability findings default to notes; (3) a significance test on a large sample flags almost
everything, so `concordance_unstable` gets an effect-size condition beside its p-value.

**The table.** Step → finding → kind → default → what it says (the template carries the same
explanation beside each default):
- `quality.all_null` → flag → no threshold → "every value is null".
- `quality.constant` → flag → no threshold → "one value only (null counts as a value, so a 1/null
  flag is not constant: its null indicator carries its signal, see `nulls_informative`)".
- `quality.near_constant` → flag → `dominant_share_max: 0.99` → "one value covers ≥ 99% of rows".
- `quality.high_missing` → flag → `missing_share_max: 0.95` → "≥ 95% null".
- `quality.high_cardinality` → flag → `max_levels: 50` → "a categorical with more than 50 levels:
  codes or free text? held until you confirm the levels are meaningful".
- **Unsupported types are not a finding** but an automatic exclusion like lineage (ledger
  `lineage` column's sibling `unsupported`), listed in the report: dates, timestamps, arrays,
  maps, structs, binary. A person's `keep` on a date would send it to an encoder that cannot
  take it; `decimal` is read as numeric.
- `quality.nulls_may_be_zeros` → **note** → `nulls_may_be_zeros: {missing_min: 0.2, zero_share_max:
  0.005}` → "many nulls and never a zero among the values: if a null means 0 here, fill it
  upstream (D-029 (c)); the framework never imputes".
- `quality.nulls_informative` → **note** → `nulls_informative_min: 0.55` (the null indicator's
  concordance, with at least 20 nulls and 20 non-nulls) → "whether the value is filled carries
  information about the target; keep the nulls as their own group (Phase 2's tree families do
  this natively); a family that imputes must impute outside the value range, never the median".
- `leakage.too_strong` → flag → `concordance_max: 0.80` → "a single feature this strong is
  usually the target under another name or a consequence of it".
- `leakage.missingness_leak` → flag → `null_concordance_max: 0.70` (raised from round 1's 0.60:
  the synthetic trap scores 0.89, legitimate informative missingness 0.52–0.58, and real data
  has product-dependent nulls in between) → "whether the value is filled predicts the target this
  strongly: ask how and when the field gets filled".
- `leakage.rare_value_leak` → flag → `rare_effect_max: 5` → "a rare value with a target rate 5×
  the rest (regression: 5× the mean): a code set after the outcome?".
- `time_alignment.lag_drop` → flag → `signal_kept_min: 0.5` → "the feature loses more than half
  its signal when lagged one period: its value may be stamped after the period".
- `time_alignment.client_constant` → flag → `constant_clients_min: 0.99`, `concordance_min: 0.6`
  → "constant within the client across the window and predictive: a static attribute, or one
  date's value stamped onto every period".
- `stability.concordance_unstable` → flag → `heterogeneity_p_max: 0.01` **and**
  `concordance_range_min: 0.05` → "the feature's power differs across the window's periods".
- `stability.psi_window`, `psi_gap`, `psi_latest` → **note** → `psi_max: 0.10` → "the distribution
  moved (within the window / into the gap / by the latest period): expect Monitoring to see it".
- `stability.new_levels` → **note** → `new_level_share_max: 0.01` → "levels unseen in the window
  cover more than 1% of later rows".
- `redundancy.correlated_pair`, `associated_pair` → **note** → `correlation_max: 0.90`,
  `association_max: 0.90` → "near-duplicates; the cluster table shows which carries the signal";
  the cluster view is how they are shown (Q472).

**Options.**
- (A) The table as proposed.
- (B) As (A), but PSI is also a flag at a second band, `psi_flag: 0.25` (the conventional
  "significant shift"), if drift should hold a feature out.
- (C) Every finding a flag except `redundancy`.

*Default:* (A). Move any row by number if you disagree with its kind or default.

**Answer (the SDS, 2026-11-02):** Default

**Outcome for the plan:** (A): the finding table as proposed, every default an explained template leaf (Q488): the five quality flags, unsupported types as an automatic exclusion, the two quality notes, the three leakage flags (`missingness_leak` at 0.70), the two time-alignment flags, `concordance_unstable` as a flag with the effect-size condition, PSI and new levels as notes, the redundancy pairs as notes. Round 4's Q490 changes how the per-period and window statistics are computed (from a counts table), not a threshold; Q493 trims which periods the PSI notes compare.

### Q479. The folder order, restated: the root is the entity's area
**Context.** Your Q424 and Q470 answers: inside the bank the HDFS root (`hdfs://xyz`) already
names the entity; below it the use case drives the structure, then the kedro-like layers. Round
2's two options both put the entity in the framework's hands (a mapping entity → root, or an
appended `<entity>` segment), which is why neither fit. Today Stage 1 writes the audit log to
`<roots.data>/04_feature/<use_case>/<entity>/<ddh>/decisions/`; the environment file has one
`roots.data` and the sources keyed by entity, and one environment file may serve several
entities (the tests run `entity_a` and `entity_b` on one root).

**The proposal.** `roots.data` stays **one path and is one entity's area** (the bank's
`hdfs://xyz`; on the laptop `data/`). The framework adds no entity segment anywhere. Under the
root, use case first, then the layer:
- `<use_case>/04_feature/<ddh>/{decisions/, eda/, feature_checks/, ledger.parquet}` (`<ddh>` the
  12-character data-definition hash, D-088 (task, entity, sources, eligibility, target spec,
  period, windows, candidates)); the hash carries the entity, so several entities under one root
  (the laptop, the tests) never collide, and every artifact's json names its entity;
- `<use_case>/06_models/<run_id>/` (M2.3), `<use_case>/07_model_output/` (M2.4);
- reports live beside their artifacts; `08_reporting` goes.
The **inputs** are the environment's `sources` as today, wherever they physically are: on the
laptop `data/01_raw/...` and `data/05_model_input/...` beside the use-case folders; inside the
bank Hive tables or HDFS paths. `data/README.md` is rewritten to say exactly this. The audit
log's path changes (0.x, no migration, D-007 (c) (the pre-release promises nothing)).
`roots.registered` and `roots.production` follow the same shape in M2.4.

**Options.**
- (A) As restated.
- (B) As restated, but `roots.data` may also be a mapping entity → root for an environment file
  that must serve two entities from two areas (none exists today).

*Default:* (A).

**Answer (the SDS, 2026-11-02):** Default

**Outcome for the plan:** (A): `roots.data` is one path and one entity's area; under it `<use_case>/04_feature/<ddh>/{decisions/, eda/, feature_checks/, ledger.parquet}`, `<use_case>/06_models/<run_id>/` (M2.3), `<use_case>/07_model_output/` (M2.4); `08_reporting` goes; reports beside their artifacts; inputs stay the environment's `sources`; `data/README.md` rewritten; the audit log's path changes in place (no migration: Q483).

### Q480. Another use case's backward-looking flag is an ordinary candidate
**Context.** The caveat in Q474 came from reading "label" as a forward-looking target column;
you meant an event flag as of the period ("picked up fixed deposits this month"), which is a
feature like any other and needs nothing. A forward-looking column from another use case is out
by `CLAUDE.md` §4.1 and the DS's `features.candidates.exclude` patterns, like every forward-looking
column. What is left to decide is only whether the cheap name nudge stays.

**Options.**
- (A) Guidance only: the template's comment on `features.candidates.exclude` says "list every
  column that looks forward from the period (other use cases' targets, 'next N months' flags,
  §4.1)"; nothing is computed.
- (B) (A) plus a `leakage.forward_name` **note** (never a flag) on candidates matching
  `forward_name_patterns` (default `["*next*", "*forward*", "*fwd*", "*future*"]`).

*Default:* (A).

**Answer (the SDS, 2026-11-02):** Option (A)

**Outcome for the plan:** (A): guidance only, in the template's comment on `features.candidates.exclude`; nothing computed.

### Q481. Mixed-kind pairs in the correlation matrix: include them now (A14)
**Context.** You asked what it costs. Round 2 computes Spearman for numeric pairs and Cramér's V
for categorical pairs, leaving numeric × categorical pairs empty, so the redundancy clusters
(Q472) would run as two separate clusterings and a categorical that duplicates a numeric (a
binned income beside income) would never be seen.

**The proposal.** The **correlation ratio on ranks**: rank the numeric, split the ranks by the
categorical's levels (null a level of its own), η² = the between-level share of the ranks'
variance, reported as η ∈ [0, 1]. For a two-level categorical it equals |Spearman ρ| with the 0/1
indicator, which is the unit test. One function of about ten lines in `statistics/association.py`,
a third branch in the matrix assembler, the pair's statistic named in the report (`spearman |
cramers_v | eta`), and one clustering over all candidates instead of two. About half a day with
tests and review.

**Options.**
- (A) Include now.
- (B) Wait (A14 as it was).

*Default:* (A).

**Answer (the SDS, 2026-11-02):** Option (A), include now

**Outcome for the plan:** (A): the correlation ratio on ranks (η) for mixed pairs, null a level, the two-level test against |Spearman|, one clustering over all candidates. With Q490 the pairwise matrix is computed on the collected snapshot (a seeded 200,000-row cap for the matrix only).

### Q482. The collected frame at a real size: a client sample for EDA and Feature Checks
**Context.** A13: EDA collects the window frame to pandas. Measured by the gap analysis: the
`dev` preset's window (20,000 clients) is 117,000 rows × 160 columns, about 0.5 GB at the
conversion peak; the canonical window (100,000 clients, about 585,000 rows) extrapolates to
about 2.3 GB, above the default `collect_budget_gb: 1.5` and Spark's default `maxResultSize`
of 1 GB. Inside the bank a window over one to five million clients and 200–400 columns is 10–50
GB. Today the budget only prints a callout and collects anyway (D-133), and the callout tells
EDA users to declare `training.sampling`, which never applies to their frames. The December
pre-release runs inside the bank.

**The proposal.** `eda.sample_share: null | <share>` (default null: every client). A share keeps
the clients whose seeded hash of the unit id falls below it (the `client_sample` mechanics with
its own salt, `analysis`, so it is independent of the split), applied **before** the collect to
every analysis frame: EDA's, Feature Checks' and the drift frame, so the same clients are seen
throughout. It is loggable at stage `eda` (a change reruns from EDA) and sits outside the
data-definition hash. The **population counts stay exact**: the funnel per period, the target per
period and the strata counts are Spark aggregations on the full population before the sample, so
the report's counts are the true ones and only the statistics (ranking, deep dives, checks) run on
the sample; the choices block says "statistics on a sample of n clients (m rows)"; the intervals
use the sample's events. Unsupported and lineage columns are dropped before the collect. The
callout names `eda.sample_share` for the analysis frames and `training.sampling` for the training
frames. About forty lines (one filter in `frames.py`, the Spark counts the funnel needs anyway,
the callout text).

**Daily work on the Mac:** the `dev` preset for daily runs and the acceptance test (Q486); the
canonical window only with `eda.sample_share` or with `maxResultSize` raised in `conf/local`.

**Options.**
- (A) Now, as proposed.
- (B) In M2.4 with the bank-side work; until then everything is collected (`dev` fits).

*Default:* (A): the Spark-side counts are needed for the funnel in any case, and the pre-release
cannot ship without a way to run EDA on real sizes.

**Answer (the SDS, 2026-11-02):** I don’t agree with sampled EDA, that defeats the purpose of some reports. Optimally, you should be able to calculate all window-needing features without exporting it to Pandas (export just the aggregated result tables) and for all the snapshot analysis (which should be most of the EDA), you should use all clients. Unless you see a problem with this approach, this should be implemented as exporting window table for retail clients to pandas will be more than the bank’s spark can hold, so in that relative sense the 100k data frame on Mac is scalable to what the full retail data frame can do in bank’s spark

**Outcome for the plan:** **Rejected: no sampled EDA.** `eda.sample_share` is dropped and the window is never collected. The SDS's rule becomes the sizing rule of the spec: the window's statistics are computed in Spark and only aggregated tables come to pandas; the snapshot analysis (most of the EDA) runs on every client in pandas; the Mac's 100,000-client snapshot stands for the bank's full retail snapshot. The redesign is round 4's Q490 (one counts table from Spark per feature, period, bin and target bin; the snapshot collected whole; `Frames.drift` and `eda.snapshot: window` go) with the one problem I see stated there (binned statistics for a continuous feature) and the follow-ups Q491 (one statistics engine on counts) and Q493 (which periods the drift notes compare). The callout's text fix (it named `training.sampling` to EDA users) stays.

### Q483. Schema bumps: config schema 2 and log schema 2, each with a small migration
**Context.** `CLAUDE.md` §2: a schema change means a version bump, a migration and a test that
loads an old file; D-007 (c): the 0.x pre-release promises nothing. Stage 1 has
`CURRENT_SCHEMA_VERSION = 1` with the migration machinery and `LOG_SCHEMA_VERSION = 1` for the
audit-log entries (a different version is refused). The gap analysis corrected round 2's view of
what breaks: a config file can never contain `kept_despite_flags` (the loader refuses the
replayed lists, D-125), so that rename needs no config migration. What does break is the
**`feature_checks` shape**: today a list of steps with untyped `params`, with
`eligibility_constant` and `psi_max: 0.25` in the defaults, both example configs and the
template; Q488 proposes a mapping with typed parameters. `eda.chart_sample_share` goes (A33).

**The proposal.** Config schema 2 with a migration that converts the `feature_checks.steps` list
into Q488's mapping (dropping `eligibility_constant`, which folded into `quality`, and keeping any
threshold a config set), removes `eda.chart_sample_share`, and a test that loads a schema-1
config. Log schema 2 with the same `migrate` machinery on read: operation `keep_despite_flag` →
`keep`, the new `findings` field on `keep`, the empty `flag` entry that closes a finding, and
the `periods` field on Feature Checks' stage `run` entries (A23); a test reads a schema-1 entry.
The template and both example configs move to `schema_version: 2`. About forty lines with tests.

**Options.**
- (A) As proposed.
- (B) No bumps in 0.x: rewrite the local configs and logs by hand (round 2's Q473 line).

*Default:* (A): it keeps §2 honoured from the first change and exercises the machinery before 1.0.

**Answer (the SDS, 2026-11-02):** For now, no bumps; when some user testing is properly underway, we might bump a version, but for now nobody ever saw an output with version 1

**Outcome for the plan:** **(B), no bumps in 0.x:** `schema_version: 1` stays for configs and `LOG_SCHEMA_VERSION = 1` for the audit log; the `feature_checks` shape (Q488), the `keep` rename, the `findings` field, the empty `flag` entry and the `periods` field on run entries change in place; the committed configs, the template, the fixtures and the tests are rewritten by hand; no migration and no old-file test. The first bump comes when user testing is under way (the SDS); D-007 (c) (the pre-release promises nothing) covers it until then, and `CLAUDE.md` §2's procedure applies from that first bump.

### Q484. Withdrawn: the regression variant is settled
The gap analysis caught a false premise: the forward-looking regression target exists
(`forward_sum`, Stage 1, with end-to-end tests), and Q420 (A) already fixed the variant: task
`regression`, rule `forward_sum` on `spend_cc_vol`, eligibility `cc_flag = 1`, through the
`variant` fixture. Nothing to decide; the regression specifics the plan still needed are A28–A29.

**Answer (the SDS, 2026-11-02):** _(withdrawn in round 3; no answer needed)_

**Outcome for the plan:** Withdrawn; the regression variant is Q420 (A) (`forward_sum` on `spend_cc_vol`, eligibility `cc_flag = 1`, the `variant` fixture); the regression specifics are A28–A29.

### Q485. Snapshot statistics and window statistics: both, computed once in EDA
**Context.** Q466 put EDA's ranking on the snapshot while Feature Checks runs on the window;
Q447 says Feature Checks reuses EDA's statistics and computes only what EDA didn't; Q467 built the
correlation matrix on the snapshot while Q472 clusters it in Feature Checks. As written, Feature
Checks' flags would cite snapshot numbers from a frame it never saw, or recompute everything.

**The proposal.** EDA holds the window frame anyway, so it computes each per-feature statistic
**twice in one pass**: on the snapshot (`concordance`, `direction`, `missing_share`,
`dominant_share`, `null_concordance`, `zero_share`: the ranking, the key features, the deep
dives) and on the window (`concordance_window`, `missing_share_window`, `dominant_share_window`,
`null_concordance_window`). Both sets are ledger columns. Every Feature Checks finding cites the
window value; Feature Checks adds only what EDA cannot (the lagged and per-period concordance,
PSI, the clusters). The correlation matrix is computed once, on the window's eligible rows with
the seeded 200,000-row cap, and serves both the key-feature skip (Q467) and the clusters
(Q472). The person's `include` list at `assisted` comes on top of N (D-132).

**Options.**
- (A) As proposed.
- (B) EDA computes the snapshot set only; Feature Checks recomputes the window set on its own
  frame (one pass more, the ledger the same).

*Default:* (A).

**Answer (the SDS, 2026-11-02):** See my comment on Q482, what would be your proposal to solve the memory issue? But also, shouldn’t most of these drifts just be measured between specific months, not all?

**Outcome for the plan:** **Superseded in part by Q490.** The twin columns stay (`concordance`, `concordance_window` and the others), but both are read from one counts table, so they differ by data, not by method (Q491); the memory issue is solved by never collecting the window (the SDS's first question); the second question (drift between specific months) is round 4's Q493: the two PSI notes compare two named periods each (the window's first and last; the snapshot and the latest), only `concordance_unstable` uses every window period, and the per-period table is shown because it costs nothing.

### Q486. The trap acceptance test: preset, assertions and scope
**Context.** Q459 settled the test and its mapping. The gap analysis measured the risk: on the
`unit` preset (5,000 clients) the card has about 95 positive rows per period at `w = 3`, so a
snapshot concordance has a null standard error of about 0.03, and "null controls below 0.55" is
only 1.7 standard errors away; the look-ahead trap scores 0.81 against `concordance_max` 0.80,
so asserting `leakage.too_strong` on it would flap; the term-deposit target has about 35 events
per period, so no per-period statistic runs for it. Scope: `truth.json` 0.5.3 lists 34 trap rows
and the Q459 mapping covers about half; the rest are EDA views (`simpson`, `onboarding`,
`null_income_eligibility`), loan-target rows with no config, kinds off by default (`dirty`,
`extra`), and four unmapped kinds (`eligibility_defining` → `quality.constant`, `collinearity` →
redundancy, `drift` → `psi_latest`, `decimal_type` → kind numeric).

**The proposal.** The test runs on the **`dev` preset** (20,000 clients; about 380 positive rows
per period; the window collects in about 0.5 GB), asserts on the **window statistics** (Q485's
`*_window` columns, about 1,100 positive rows: standard error about 0.015), asserts only
`time_alignment.client_constant` for the look-ahead trap, asserts no per-period finding for the
term-deposit config, maps the four unmapped kinds as above, and keeps an explicit `NOT_CHECKS`
dict (kind → reason: "an EDA view", "no config", "off by default") so that **any trap kind that
is neither mapped nor listed fails the test**. The D-088 counts the test compares come from
`eda.json` (A34), not from Target Factory's summary, which covers every row before eligibility.

**Options.**
- (A) As proposed (`dev`, window statistics, the explicit scope dict).
- (B) The `unit` preset with looser assertions (null controls below 0.60).

*Default:* (A): about a minute of runtime buys assertions that mean something.

**Answer (the SDS, 2026-11-02):** Default

**Outcome for the plan:** (A): the trap acceptance test on the `dev` preset, asserting on the window statistics (now the window periods' cells of the counts table, Q490), only `client_constant` for the look-ahead trap, no per-period finding for the term deposit, the four kinds mapped, the explicit `NOT_CHECKS` dict so an unlisted trap kind fails the test, the D-088 counts from `eda.json`.

### Q487. Artifact transport in Stage 2: local paths until M2.4
**Context.** Stage 1's audit log writes local paths only and refuses an `hdfs://` root (the HDFS
transport is M2.4's, with register and promote). Stage 2's artifacts (`eda/`, `feature_checks/`,
the ledger, the reports) follow the same writer. That means the December pre-release runs EDA
and Feature Checks inside the bank with `roots.data` on the DS's local workspace (the edge node),
while the sources are read from Hive and HDFS as today.

**Options.**
- (A) Local paths only in Stage 2; the HDFS transport arrives in M2.4 for every artifact at once.
- (B) Stage 2 adds the HDFS transport for its own artifacts now (a week more; the bank's
  transport is unverified outside the bank).

*Default:* (A).

**Answer (the SDS, 2026-11-02):** Default

**Outcome for the plan:** (A): local artifact paths in Stage 2; the HDFS transport arrives in M2.4 for every artifact.

### Q488. The `feature_checks` config shape: a mapping with typed parameters, every threshold a leaf
**Context.** Today `feature_checks.steps` is a list of `{name, params}` with `params` an untyped
dict and `name` an unchecked string; a misspelt parameter passes validation, and Q446's "a
missing parameter fails loud" would force every config to restate every threshold. A `set`
through the audit log addresses one loggable path, and `feature_checks.steps` is one path, so a
person changing one threshold would restate the whole list, against D-125's leaves.

**The proposal.** An ordered mapping, one Pydantic model per step with a default for every
parameter, YAML order = run order, a step left out = not run (stated in the choices block):
```yaml
feature_checks:
  quality:        {dominant_share_max: 0.99, missing_share_max: 0.95, max_levels: 50,
                   nulls_may_be_zeros: {missing_min: 0.2, zero_share_max: 0.005}, nulls_informative_min: 0.55}
  leakage:        {concordance_max: 0.80, null_concordance_max: 0.70, rare_effect_max: 5}
  time_alignment: {signal_kept_min: 0.5, constant_clients_min: 0.99, concordance_min: 0.6}
  stability:      {psi_max: 0.10, heterogeneity_p_max: 0.01, concordance_range_min: 0.05, new_level_share_max: 0.01}
  redundancy:     {correlation_max: 0.90, association_max: 0.90}
```
Each threshold is a loggable leaf (`set feature_checks.leakage.concordance_max`, stage
`feature_checks`); the template carries every default with its one-line explanation (Q446's rule);
an unknown parameter fails loud at load.

**Options.**
- (A) The mapping with typed parameters.
- (B) Keep the list of steps; fill the defaults per step name; parameters stay an untyped dict.

*Default:* (A).

**Answer (the SDS, 2026-11-02):** Default

**Outcome for the plan:** (A): `feature_checks` as an ordered mapping with one typed Pydantic model per step, a default for every parameter, YAML order = run order, a step left out = not run, each threshold a loggable leaf, an unknown parameter failing loud; the template carries every default with its explanation. Changed in place, no schema bump (Q483).

### Q489. Non-monotone signal: a binned concordance beside the plain one
**Context.** The rank concordance measures monotone ordering. The synthetic `age` trap is an
inverted U (Spearman ≈ 0), so it scores near 0.5, never becomes a key feature, and Training's
floor (M2.3) would drop it, although a tree model uses it. Round 1 did not cover this.

**The proposal.** A second column, `binned_concordance`: the numeric is cut into ten quantile bins
(a numeric with ten or fewer distinct values uses its values), each bin takes the shrunk level
encoding (A30), and the concordance of the encoded feature with the target is computed like a
categorical's. A feature is marked `non_monotone` when the binned value beats the plain one by at
least 0.03. The ranking orders by the **larger** of the two, so a non-monotone feature can be a
key feature and its deep dive shows the shape; Training's floor (M2.3) uses the larger too. For a
categorical the two coincide. About fifteen lines over A30's encoder.

**Options.**
- (A) Include: both columns, the marker, ranking by the larger.
- (B) Plain concordance only; non-monotone signal is accepted as uncaught in the ranking.

*Default:* (A).

**Answer (the SDS, 2026-11-02):** I don’t understand the proposal, what would we achieve here?

**Outcome for the plan:** **Not decided:** re-explained in round 4's Q492 in plain words (what it achieves for the synthetic inverted-U age, what it costs, what the risk is). With Q491 every concordance is computed on bins, so the statistic is renamed `concordance_best_order` (the bins ordered by their shrunk target rate instead of by value).

### Plan defaults A19–A36 as listed in round 3 (verbatim)
_The list as the SDS saw it; the status of each item after the answers follows the list._
- A19. **Flag entries:** one `flag` entry per finding per run, written only when the finding's
  feature set differs from its latest entry; an empty set is allowed for `flag` only and closes
  the finding; notes are never entries (they live in the `findings` table). **No lineage entry**
  (round 1's Q448 (A) had one): the candidate resolution already drops the lineage and an
  upstream target's label is dropped on read, so a lineage `exclude` would duplicate it and fail
  the named-feature check; the ledger's `lineage` column comes from the resolution.
- A20. **`keep` carries `findings`** (a new entry field; `decide --keep … --findings …`),
  defaulting to every flag open on those features at the time.
- A21. **The ledger stores statistics and flags only.** `held / kept / excluded` is read from the
  log at render time, as the decisions already are (Q450).
- A22. **Staleness between stages:** each stage's json carries `replayed_to`, the resolved-input
  hash, a digest of that stage's loggable settings (`features.kinds`, `strata.*`, `eda.snapshot`,
  `eda.sample_share`, the thresholds) and the framework version; Feature Checks refuses to run
  when EDA's digest differs from the current resolved config; an EDA run removes `feature_checks/`
  and Feature Checks' ledger columns; Training applies the same check; a stage writes to a
  temporary folder renamed on success, so a crash never leaves a half-written one.
- A23. **Compared periods live in the audit log**, not in a folder a rerun rewrites: Feature
  Checks writes one stage `run` entry per run (`by: stage feature_checks`) with a `periods`
  field; `set time.validation_period` is refused when any run entry, reverted or not, lists that
  period (D-088). `compared_periods.json` (Q424) goes.
- A24. **Artifact files:** versioned, `eda.json` and `feature_checks.json` (`schema_version: 1`),
  `ledger.parquet` + `_ledger.json` (`ledger_schema_version: 1`); private and regenerable,
  `tables/*.parquet` in long form keyed by feature (`bins`, `levels`, `per_period`, `psi`,
  `findings`, `clusters`, `correlation` with `a, b, statistic, method, rows`); the per-run ledger
  part is a separate file under `06_models/<run_id>/` joined on `feature` (M2.3), so Training
  never rewrites Stage 2's file.
- A25. **Report order:** EDA: summary (choices, headline, warnings) → core (funnel, target per
  period and by stratum, ranking, deep dives) → extended (reference groups, strata pivots,
  correlation overview) → appendix (kinds, ledger, resolved config with entry origins, collect
  log, timings). Feature Checks: summary (EDA's headline, choices, flags and notes per step, held
  features) → core (findings per step in run order, proposed decisions, ledger with decisions) →
  extended (per-period concordance and PSI for every candidate, clusters) → appendix. One
  `CHOICES` table (label, value from the resolved config, alternatives, when to move) reusing the
  template's explanations (D-032, `reporting.md` req. 2.1); numbered warnings; one events warning
  (the snapshot's), not two.
- A26. **Notebooks display through the Public API:** `StageResult` gains `views` (the Stylers and
  figures the report embeds), `frame` (the collected frame, for `pivot_target`) and `config` (the
  resolved config); the `record_as` call text uses a `CONFIG` placeholder the setup cell defines;
  no commented-out `record_decision` cell (`CLAUDE.md` §1 rule 9): the call text and a markdown cell.
- A27. **CLI:** `run` loops EDA and Feature Checks over the configs in order ("all built stages"
  as documented); `decide` gains `--keep` and `--findings`.
- A28. **Regression specifics:** the rare-value effect is the mean ratio with the one
  `rare_effect_max`; support is counted in distinct units with a non-zero target (the analogue of
  events, D-082); deep dives of zero-inflated amounts show the non-zero share (Wilson) and the
  mean and median of the non-zero values per bin; the headline warns below 500 units with a
  non-zero target.
- A29. **Standard errors:** binary, Hanley–McNeil in events (round 1); regression, Kendall's null
  standard error in distinct units, rescaled to the concordance scale (halved); guards for a
  single supported period (Cochran's Q with no degrees of freedom) and a concordance of 1 (a zero
  standard error, an infinite weight).
- A30. **Level encoding, concretely:** shrinkage in pseudo-**events**, `k_rows = min_events /
  base_rate` (50 pseudo-events, 10,000 rows at a 0.5% rate; regression: `min_support` rows), not
  pseudo-rows (with 50 pseudo-rows a 300-level random code scores well above 0.5); null excluded
  (its signal is `null_concordance`); fitted once on the pooled window and applied per period and
  to the lagged values; the test: a 300-level random code scores below 0.55.
- A31. **Nulls in each statistic:** constant, near-constant and dominant share over all rows with
  null as a value; null is a level for Cramér's V and η; Spearman pairwise-complete with at least
  1,000 shared rows, otherwise "not compared"; standardised mean differences on non-null rows.
- A32. **`eda.snapshot` is a window period**, checked at load, loggable at stage `eda`; Q476's
  "any labelled period" is corrected in the record.
- A33. **`eda.chart_sample_share` is dropped:** Q455 (A) pre-aggregates every chart (box plots
  from quantiles), so Q438's sampling has nothing left to sample.
- A34. **The D-088 counts per period in `eda.json`,** on the full population (Q482): rows after
  the analysis filters, eligible rows, eligible rows with a known target, positive rows,
  positive events; the acceptance test and Training's count check read these.
- A35. **Ledger columns Training needs, written now:** `kind` after overrides and `levels` (the
  encoder), `cluster` (grouped importance, a top-per-cluster rule), `lineage`, `unsupported`.
- A36. **Docs on the old design are rewritten in the spec step:** D-029 (d) and `feature_checks.md`
  req. 3 (forward vs backward), `feature_checks.md`'s `label_free_periods` and `dataset.md`'s
  frame list, `test_harness.md`'s planned mapping, D-030's window ranking, `feature_ledger.md`,
  `notebooks/README.md`, `run_modes.md` and `run.py`'s docstring ("`run` resolves the config"; each
  stage does, Q422), `config.md`'s worked example and the audit-log tests that still encode
  quality rule excludes. `environment.md`'s "the collect fails loud" was corrected today (D-133:
  it proceeds with a callout).

### Status of A19–A36 after the round-3 answers
- Hold unchanged: A19, A20, A21, A23, A25, A26, A27, A28, A29, A32, A33, A35, A36.
- A22 (staleness digests): holds without `eda.sample_share`, which is dropped (Q482).
- A24 (artifact files): the private `bins`, `levels`, `per_period` and `psi` tables become **one
  counts table** (`feature, period, bin, target_bin, lagged, n, sum_y`) plus the `client_constant`
  shares; the other files as listed (round 4's Q490).
- A30 (level encoding): holds; the pooled window counts it is fitted on are the window periods'
  cells of the counts table.
- A31 (nulls): holds with the SDS's condition: the register below.
- A34 (D-088 counts in `eda.json`): holds; computed on the full population by Spark, as before.
- From round 2: A13 (EDA collects the window frame) is **superseded** by Q490; A15 holds.


---

# Null-value assumptions (register, kept current)
_Opened 2026-11-02 at the SDS's request (A31): every assumption about null values the design or the
code makes, numbered N1 onwards, with its source and status. "Decision" = already settled in
`docs/decisions.md` or an answered question; "assumption" = mine, open to the SDS's veto. **Moved
into the owner docs** (the spec step, 2026-11-02; N10 and N17 on 2026-11-03 after the SDS asked,
R1): `eda.md` "Nulls" owns N1–N9, N13–N16 and N19; `feature_checks.md` "Nulls" repeats the ones
it relies on (N4–N6, N11, N12, N15, N18); `dataset.md` owns N10 (the population counts) and N11
(the lag pass); `training.md` owns N17 (the predefined path's imputation rule). This table stays
the numbered index until the folder is deleted at the stage's sign-off; a new assumption is added
here and in its owner doc the moment it is made._

| # | Assumption | Source | Status |
|---|---|---|---|
| N1 | The framework never fills a null. Every statistic treats null as a state of its own, never as 0, the mean or the median; a null that means a value is filled upstream (the `nulls_may_be_zeros` note says so). | D-029 (c), Q468 | decision |
| N2 | Numeric: a Spark null and a float NaN are the same thing (the collect turns null into NaN; the counts table buckets both as the null bin). ±infinity is a value, not a null. | A13/Q490 | assumption |
| N3 | Strings: the empty string and whitespace-only strings are values (levels), not nulls; the framework trims and recodes nothing. The level table shows them as `''`. | quality upstream (D-029 (c)) | assumption |
| N4 | Shares are over all eligible rows of the period(s): `missing_share` = null rows / rows; `dominant_share` and `constant` count null as a value, so a column of one value plus nulls has two values (not constant; its null indicator may carry its signal), a column of one value and no nulls is `constant`, an all-null column is `all_null`. | Q478, A31 | decision |
| N5 | In the counts table null is its own bin for every feature, numeric or categorical. PSI therefore includes the null bin; a null share that appears in a later period but not in the window is a `new_levels` case (a field stopped being filled). | Q490 | assumption |
| N6 | Concordance (snapshot, window, per period, lagged, best-order) is computed on the non-null rows of the feature; its support (events, units) counts those rows only. The nulls' own information is `null_concordance` (the null indicator against the target), which drives `nulls_informative` and `missingness_leak`. | Q427, Q441, Q478 | decision |
| N7 | The level encoding (A30) is fitted without the null level; the null bin takes no position in the best-order concordance (it is out, as in N6). | A30 | assumption |
| N8 | Pairwise statistics: null is a level for Cramér's V and η, so two features that are null together look associated (co-missingness is redundancy information, intended); Spearman is pairwise-complete and needs at least 1,000 shared non-null rows, otherwise the pair is "not compared" (distance 1 in the clustering, never linked). | A31, Q481 | decision |
| N9 | Standardised mean differences and the reference-group comparisons use the non-null values; the null share is shown beside them. | A31 | decision |
| N10 | A row whose target is null (the forward window not matured, or the client gone before it closed: `null_in_window`) is in the population counts (eligible rows; eligible rows with a known target) and out of every labelled statistic. The gap and latest periods are label-free by construction: their label is dropped before the aggregation (D-030) and a test asserts it. | D-131, D-030, A34 | decision |
| N11 | Lag check: the lagged value is null when the client has no row in the previous period or that value was null; both are "no lagged value", such rows are out of the lagged concordance and their share is shown with the finding. | Q442 | assumption |
| N12 | `client_constant`: Spark's `min` and `max` ignore nulls, so a client whose values for the feature are all null is left out of that feature's share, and a client with one non-null value among nulls counts as constant; the denominator is the clients with at least two non-null values. | Q475 | assumption |
| N13 | Kinds detection counts distinct values without null; `features.kinds` overrides it. Because Arrow collects a nullable integer column as float, kinds are decided by the distinct count, never by the pandas dtype. | Q469, Q490 | assumption |
| N14 | Bin edges come from the non-null snapshot values (`eda.bins` = 100 quantile edges plus singleton bins for 0 and the dominant value); a numeric with at most `eda.bins` distinct non-null values uses its values as bins; with `eda.bins: null` every numeric uses its values. The null bin is separate and never merged. | Q490 | decision |
| N15 | `nulls_may_be_zeros`: missing share (over all rows) ≥ 0.2 and zero share among the non-null values ≤ 0.005. `nulls_informative`: 0.55 ≤ `null_concordance` < 0.70 with at least 20 null rows and 20 non-null rows. `missingness_leak`: `null_concordance` ≥ 0.70. | Q478 | decision |
| N16 | Reports: every per-feature table shows `missing_share` beside the statistic; a histogram shows the null bin as its own bar labelled `null`; a level table lists `null` as a level. Nulls never silently vanish from a chart. | Q455, reporting.md | assumption |
| N17 | Phase 2's tree families take nulls natively, which is what the `nulls_informative` note's advice ("keep them as their own group") relies on; a family that imputes (M2.3's predefined families) must impute outside the value range with a missing indicator, never the median. Recorded here as M2.3's dependency, decided there. | Q468 outcome | assumption, M2.3 |
| N18 | Rows are never dropped for nulls in a feature. `high_missing` (≥ 95% null) is a flag like any other; a person keeps or excludes. | Q477, Q478 | decision |
| N19 | With `eda.bins: null` (binning off) nothing changes for nulls: the null bin stays its own cell, the concordance still excludes it, and the exact statistics are computed on the non-null cells. | Q490 | assumption |

---

# Round 4: questions and answers
_Round 4: written 2026-11-02, answered by the SDS 2026-11-02 · Q490–Q493 and the Q477 confirmation ·
every question verbatim as asked, each followed by the SDS's answer verbatim and the outcome for the
plan · with this round the design is settled: the spec goes into the component docs, then the
holistic review and `plan.md` (the SDS, 2026-11-02: "record answers, then write specs into
component docs, run the holistic review, and build the plan")_

## The Q477 confirmation

**Q477, a confirmation.** It was not in your round-3 list, so it took its default (A): an open flag
holds the feature out of training at both levels until a person keeps or excludes it; `register`
needs the sign-off and no open flag on the model's final list, held features may stay held. It is
the stage's main design change, so: say "Q477 no" if that was not intended; silence confirms it.

**Answer (the SDS, 2026-11-02):** _(not mentioned; silence confirms, as the round said)_

**Outcome for the plan:** Q477 (A) is confirmed: the hold-out at both levels, decision row D-134.

## Round 4 questions

### Q490. One counts table from Spark; the snapshot collected whole
**Context.** What needs the window in the design as answered: the window twins of each statistic
(Q485), the per-period concordance for `concordance_unstable`, PSI and `new_levels`, the lag check,
`client_constant`, the level encoding fitted on the pooled window (A30), the D-088 counts (A34,
Spark already) and the correlation matrix (Q485 put it on the window). The legacy crunch never ran
Python on the executors (no pandas UDFs), so the bank has proven Spark SQL and JVM-side
transformers only; the aggregation below uses nothing else.

**The proposal.**
1. **Frames.** EDA and Feature Checks collect **one period**: the snapshot (`eda.snapshot`, default
   the window's last period), its eligible rows, the supported candidate columns only (lineage and
   unsupported columns dropped before the collect). `Frames.window` becomes `Frames.snapshot`;
   `Frames.drift` (Q444) goes, the gap and latest periods are only ever aggregated;
   `eda.snapshot: window` goes (Q466's choices become `last | <period>`), since the pooled window is
   never in pandas. The collect budget and its callout (D-133) stay for the snapshot and the
   training frames; the callout names `training.sampling` for the training frames only.
2. **One counts table from Spark.** Over the eligible rows of the window periods, the gap periods
   and the latest period, one pass: every numeric is bucketed with `Bucketizer` (JVM, every column
   in one transformer; `handleInvalid="keep"` gives null its own bucket) at edges taken from the
   snapshot (50 quantile edges plus singleton bins for 0 and the dominant value, so the zero share
   and the dominant share are cells; a numeric with 50 or fewer distinct values uses its values);
   every categorical keeps its level (the levels seen in any window period; anything else `new`;
   null a level). Then `explode(array(struct(feature, bin)))` and `groupBy(feature, period, bin,
   target_bin).agg(count, sum(target))`. Spark's partial aggregation collapses the exploded rows
   inside each partition before the shuffle, so the shuffle carries at most features × bins ×
   target bins rows per partition, whatever the row count. The target bin is the two values for a
   binary task and 20 quantile bins of the snapshot's known targets for regression (0 its own bin);
   it is null for the gap and latest rows, whose label is dropped before the pass (D-030 (the
   validation period never informs a choice; later labels overlap it); a test asserts the drop).
   A second pass over the same rows sorted by client adds the **lagged** values (`F.lag` over the
   client window, the same edges, `lagged = true` cells) and the **`client_constant`** shares
   (`min == max` per client and feature). Size: under 300,000 rows for a binary task on the
   synthetic data (150 features × 9 compared periods × 52 bins × 2 target bins, lagged included),
   twenty times that for regression; a few MB of parquet.
3. **Statistics from counts**, one function each, per (feature, period) and pooled over any set of
   periods by summing cells: concordance from the two-way table of a feature's bins against the
   target bins (Somers' D rescaled: for a 0/1 target exactly the AUC of the binned feature, pairs
   inside one bin counting half), its standard error from the events (A29); the direction; the
   missing, zero and dominant shares; the null concordance; the per-period concordances and
   Cochran's Q; PSI on deciles merged from the quantile bins plus the null bin; new levels; the
   lagged concordance; the level encoding from the window periods' cells (A30, unchanged). The
   snapshot's statistics are the snapshot period's cells, the window twins the window periods'
   cells: one function, different rows of one table.
4. **The snapshot's pandas rows serve what needs rows:** the correlation matrix, Cramér's V and η
   (on a seeded 200,000-row cap of the snapshot, a named constant rather than config: a
   correlation's standard error at that size is 0.002, more than a 0.90 threshold needs; every
   other snapshot view uses all rows), kinds detection, the quantile edges, the strata pivots and
   reference groups, the row-level deep-dive views (quartiles for the box plots, the median of the
   non-zero values per bin, A28).
5. **Sizes.** Mac, canonical preset: the snapshot is 100,000 × 160, about 0.2 GB in pandas (0.4 GB
   at the conversion peak, from the gap analysis's measurement), inside the 1.5 GB budget and the
   1 GB `maxResultSize`; the two passes shuffle kilobytes and sort 585,000 rows by client once:
   local Spark needs seconds to a couple of minutes, measured in the plan's first spike. Bank: the
   full retail snapshot in pandas is your premise; the passes cost Spark CPU in proportion to rows
   × features (unverified timing, no new primitive).

**The problem I see.** The window's statistics are **binned**. A continuous feature's concordance
from 50 quantile bins counts the pairs inside one bin as ties, which pulls it towards 0.5 by at
most 2% of its distance from 0.5 (a true 0.70 reads no lower than 0.696), usually far less; it is
exact for 50 or fewer distinct values and for every categorical; the regression τ-b loses the
pairs tied inside one target bin (one in twenty), a loss of precision, not a bias. Where the
snapshot's own value comes from is Q491. Everything else keeps its meaning; two things go
(`eda.sample_share`, `eda.snapshot: window`); the compared periods are Q493.

**Options.**
- (A) As proposed: one counts table, every window statistic from it.
- (B) Exact window concordances through Spark ranking (one global sort per feature and period
  set, about 150 of them, then the AUC from the ranks), the counts table for everything else:
  exact, at a long runtime and two code paths for one statistic.

*Default:* (A).

**Answer (the SDS, 2026-11-02):** Agree with default, but make 100 bins and also add a parameter which can turn this whole binning off (for subsegments or SME/Corporate data this would not be required)

**Outcome for the plan:** (A) with two changes. **100 quantile bins** instead of 50 (the pull towards 0.5 of a continuous feature's concordance is then at most 1% of its distance from 0.5). **A switch that turns the binning off:** `eda.bins: 100 | null`; with `null` every distinct value of a numeric is its own bin, so every statistic read from the counts table is exact (the regression target then also keeps its values and its concordance is Kendall's τ-b on the expanded cells); meant for small populations (a subsegment, SME, corporate), where the table is still small; loggable at stage `eda`, outside the data-definition hash; the template explains both settings. PSI and the histograms always use ten (PSI) or twenty (charts) bins merged from the cells on the snapshot's quantile edges, whatever `eda.bins`. One deviation from Q488's wording, made in the spec: the five steps run in a fixed order (quality, leakage, time_alignment, stability, redundancy) rather than in YAML order, because Pydantic does not see the YAML order and the steps are independent; a step is skipped by leaving it out of a `feature_checks` mapping that is present (the section left out runs every step with its defaults, the config's general rule).

### Q491. One statistics engine on counts: the snapshot's statistics from the same table
**Context.** Q485 computed the snapshot's statistics exactly on rows (`roc_auc_score`,
`kendalltau`) and Q490 computes the window's from counts, so the twin columns `concordance` and
`concordance_window` would differ by method as well as by data, and the ledger would carry two
implementations of one statistic.

**The proposal.** Every per-feature statistic, the snapshot's included, comes from the counts
table: the snapshot is one period's cells. The exact row-level values appear only in the tests as
the oracle (the binned value within 0.005 of the exact one on the synthetic snapshot; equal for
discrete and categorical features). The glossary entry and the report's "how to read" line say
"computed on 50 quantile bins; pairs inside one bin count half". Nothing in pandas bins or ranks a
feature against the target; the pandas snapshot does only item 4 of Q490.

**Options.**
- (A) One engine on counts, as proposed.
- (B) Exact on the snapshot rows, counts for the window; the `_window` columns documented as
  binned; two implementations.

*Default:* (A): one implementation, one documented approximation, and the snapshot–window
comparison compares data, not methods.

**Answer (the SDS, 2026-11-02):** Default

**Outcome for the plan:** (A): one statistics engine on counts; the snapshot's statistics are the snapshot period's cells; the exact row-level values live only in the tests as the oracle; the glossary and the reports' how-to-read line state the binning (none when `eda.bins` is null).

### Q492. Q489 explained: what the best-order concordance buys (renamed from `binned_concordance`)
**In plain words.** The concordance says how well a feature **orders** clients by the target when
"higher means more" (or less: the sign is the direction). The synthetic `age` column is an
inverted U for personal loans: clients around 35 open most, the young and the old less. Ordering
by age puts low-propensity clients at both ends, so its rank correlation is about 0 and its
concordance about 0.50: age ranks beside the null controls, never becomes a key feature, and
M2.3's concordance floor would drop it before the model ever saw it. A tree model (Phase 2's
families) uses it well: it splits age into bands. The best-order concordance imitates that: it
takes the feature's bins (Q490's, merged to ten), orders them by their **shrunk target rate**
instead of by value, and asks how well that ordering separates the target: the concordance a
ten-leaf tree on this one feature would reach. For age that is well above 0.50 instead of 0.50.
For a monotone feature the two coincide (the order by rate is the order by value); for a
categorical they coincide by construction (its levels are already ordered by rate, A30).

**What we achieve.** (1) A non-monotone feature ranks where its information puts it (the ranking
orders by the larger of the two). (2) The ledger marks `non_monotone` when the best order beats the
value order by at least 0.03: the DS learns the shape matters (a scorecard or a monotone constraint
would lose it; the deep dive shows the bins). (3) M2.3's floor uses the larger, so the model keeps
it. **Cost:** about five lines over the counts table (reorder the bins, then the same concordance
function). **Risk:** ordering bins by their own rate always helps a little by chance; the shrinkage
(A30, 50 pseudo-events per bin) and the 0.03 margin keep a null control from being marked, and the
test asserts a null control's best-order value below 0.55 and the synthetic age's at least 0.05
above its plain value. The trap acceptance test does not cover it (the loan target has no config,
Q486's `NOT_CHECKS`); a unit test on the synthetic column does.

**Options.**
- (A) Include: `concordance_best_order` beside `concordance`, the `non_monotone` marker, ranking
  and M2.3's floor by the larger.
- (B) Leave it out: non-monotone features rank by the plain concordance and the DS must find the
  shape in the deep dives; M2.3's floor would need its own answer for them.

*Default:* (A).

**Answer (the SDS, 2026-11-02):** Default (A), I like this one, good job

**Outcome for the plan:** (A): `concordance_best_order` beside `concordance`, the `non_monotone` marker at a 0.03 margin, the ranking and M2.3's floor by the larger; a unit test on the synthetic inverted-U age and on a null control.

### Q493. Which periods the drift notes compare: two named periods each
**Context.** Your Q485 question: "shouldn't most of these drifts just be measured between specific
months, not all?" Round 1 (Q443) compared every window period with the pooled window
(`psi_window` = the maximum), the pooled gap with the pooled window (`psi_gap`), and the latest
period with the pooled window (`psi_latest`). With the counts table every comparison is free, so
the question is which ones mean something to a DS reading a note.

**The proposal.** Two notes, each between two named periods:
- `psi_window` = PSI(the window's first period, the window's last): did the feature's distribution
  move while the model's data was collected;
- `psi_latest` = PSI(the snapshot, the latest period the data holds): will production score a
  different distribution from the one the model saw;
- `psi_gap` goes (the gap sits between the two, and Evaluation shows what it did to the metrics);
- `new_levels` = the share, in the latest period, of levels unseen in any window period.
The per-period table (every compared period against the snapshot: PSI, missing share,
concordance where labelled) is shown in the report's extended section for every candidate, as
information, since it costs nothing. `concordance_unstable` keeps **every window period**: a signal
present in one period only is exactly what it looks for, and Cochran's Q needs the per-period
values. The compared periods are the stage `run` entry's `periods` field (A23).

**Options.**
- (A) As proposed: two PSI notes between named periods; `psi_gap` goes.
- (B) Round 1's three comparisons against the pooled window.
- (C) (A) plus `psi_gap` as PSI(the window's last period, the last gap period).

*Default:* (A).

**Answer (the SDS, 2026-11-02):** Default

**Outcome for the plan:** (A): two PSI notes between named periods (`psi_window`: the window's first and last period; `psi_latest`: the snapshot and the latest period), `psi_gap` dropped, `new_levels` on the latest period against every window period, `concordance_unstable` over every window period, the per-period table in the extended section; the compared periods in the stage run entry.

## The SDS's instruction for what follows (2026-11-02)

"Now record answers, then write specs into component docs, run the holistic review, and build the
plan with its major and minor steps and the routing table. In the plan, I would want you to already
be very specific what kinds of models you will use for which items, because as mentioned before, I
want to be able to keep the main thread on Fable without running out of Fable (but not of other
model) token allowance." → the plan's routing table names the agent type, model and effort for
every minor step and every review (D-072 (l)).

---

# Remarks round (2026-11-03): R1–R9
_The SDS's remarks on the plan and the spec, 2026-11-03, each verbatim with what was done · no new
question was asked; the decisions made in response are V13–V15 in `plan.md` §9, open to veto · the
SDS: "Make changes with regards to my points above, don't start the build yet"_

**R1.** "The things in answers.md which have to be recorded in some other documents (like Null value
assumptions), when are you going to do it?"

**Done:** it was done in the spec step for 17 of the 19 assumptions (`eda.md` and
`feature_checks.md` have a "Nulls" section each, `dataset.md` N11) and two had no owner: N10 (a row
with a null target is in the population counts and out of every labelled statistic) is now in
`dataset.md`'s population counts, N17 (a family that imputes must impute outside the value range
with a missing indicator) in `training.md`'s predefined path. The register's intro now lists the
owner of every number. Everything else in this record that the docs must carry (the answers'
outcomes) went into the docs in the spec step; the record itself is history and is deleted with the
folder when the stage is done.

**R2.** "You are allowed to use extra high effort for Opus and all other models as well if needed, and
also between a third and half of the tokens can be Fable, so you are allowed to reallocate some of
the more creative/complex bits to that. I would rather have you use a bit more tokens on properly
architecting code rather than needing multiple rewrites"

**Done:** `plan.md` §3 rewritten. Fable takes four code pieces besides the main thread: m1.3 (the
frames and counts passes), m1.4 (the statistics engine), m2.3 (the EDA stage and report) and m3.2
(the decisions and the Feature Checks stage): the architecture the stage stands on and the two
integrations. Every §4 code path on Opus runs at `xhigh`, so do `code-reviewer` on those steps and
`silent-failure-hunter`; the notebooks move to Opus `xhigh` (R8). Expected balance Fable 40%, Opus
45%, Sonnet 15%; if Fable runs ahead of a half after major step 1, m3.2 moves to Opus. D-072 (l)
and `CLAUDE.md` §1 carry the budget.

**R3.** "Rename lag_drop to lagged_signal_drop"

**Done:** `feature_checks.md` (the finding table, the compared periods, the step → finding map, the
nulls section) and `test_harness.md` (the acceptance mapping). The earlier rounds of this record keep
the old name verbatim.

**R4.** "Does psi_latest check last training window snapshot versus the last data snapshot?"

**Answer:** yes, by default: the snapshot defaults to the window's last period, and the latest
period is the most recent period the data holds (counted only when it lies after the validation
period). Pinned by rule now (V13): `psi_latest` always compares the window's last period with the
latest period, whatever `eda.snapshot` is set to, so the note means the same thing in every run.
`feature_checks.md`, `feature_ledger.md` and D-135 say so.

**R5.** "One question on the Bucketizer: Might be irrelevant, but in your EDA plot code, quite a few
numeric columns ended up not properly bucketized (it was just one bucket for the whole data), how
will you ensure that does not repeat?"

**Answer and change (V14, T25):** relevant. The symptom comes from quantile edges on a zero-inflated
or discrete column (90% zeros put ninety of a hundred edges on 0; `pd.qcut(duplicates="drop")`
then leaves one bucket for everything else), or from fixed-width edges on a skewed column (nearly
every row in the first bucket). The counts table's edges rule now is: the mass points (values
holding at least `1 / bins` of the non-null rows; 0 and the dominant value whenever they reach it)
are singleton bins, and the `bins − n_mass` quantile edges are taken over the remaining values,
deduplicated, so no bin but a singleton holds more than about `2 / bins` of the rows. Charts merge
cells by cumulative row share (a mass point stays its own bar), never by equal width. Three guards:
unit tests on constructed columns (90% zeros with a long tail, Poisson counts, continuous), the
m1.0 spike reports the bin-count distribution over every canonical numeric, and the acceptance test
asserts on every numeric candidate of the synthetic data that a column with at least `bins`
distinct values gets at least `bins / 2` bins and no non-singleton bin above 5%.

**R6.** "I don't understand why chart sampling has been left out; I have said that I want the EDA to
run on the whole population but obviously for any charts that is client-level I don't want you to
plot all of the points"

**Answer (V15):** there is no client-level chart in the design: every chart is drawn from the cells
(bars, lift, PSI, per-period lines) or from precomputed quartiles (the box plots), so no client is
ever plotted and nothing needs sampling, while every statistic uses the whole population. That is
why the config field went. `reporting.md` requirement 5 now says this, and adds the rule for a
row-level chart should one ever be added: a seeded sample of at most 10,000 rows, stated in the
caption. `pivot_target` returns a table, not points.

**R7.** "Generic additional note that while I try to look at the actual code as much as possible (you
do see I've had remarks before on it), I won't really look at the tests unless you specifically say
that checking out this test is very important"

**Done:** `plan.md` §4 item 6: the review guide lists code to read in order; it names a test only
when reading it matters, marked "read this test", at most two per major step (the hold-out test in
step 1, the trap acceptance test in step 3). Kept as a working preference.

**R8.** "The guide part of notebooks is very important, allocate resources to concisely but thoroughly
explain steps"

**Done:** `notebooks/README.md`'s guide-cell rule extended (before every step: what it does, what
to look at, how to read each number, which decision to take and how to record it, at both
automation levels; concise, nothing a first-time user needs left out); m2.4 and m3.4 moved to Opus
`xhigh` with the guide text as the deliverable and the brief carrying the outline per cell; the main
thread reads every guide line in the integration; the done criteria (§6) name it.

**R9.** "V1: I agree with this, but make sure you include in the notebook/docs that in effect of
training, a held feature acts as an excluded feature without a final decision"

**Done:** the sentence is in `feature_checks.md` (the hold-out), `feature_ledger.md` (the `held`
column), `training.md` (the feature set), the glossary (held), `notebooks/README.md`, D-134 and the
plan's notebook 03 content (m3.4) and done criteria; the report, Training's log and the ledger's
`held` column carry it in the build.

# Review 2 (2026-11-05): Q494–Q500 answered, remarks R10–R28
_The SDS reviewed major step 2 through notebook 02 first (the Python files follow after the
redesign); the review runs in three stages: (1) remarks and a brainstorming round (Q501–Q522 in
`questions.md`), (2) an exact build plan from the answers, (3) the build and a comprehensive review
of the major step 2 code. Unanswered questions take their default._

**Q494** (simplicity pass): "Yes, there will be a big major review now" → the pass is part of the
redesign (Q520). **Q497** (sort in pandas or Spark): "Do the orderBy in pandas, unnecessary double
spike" → read as the Spark `orderBy` before `toPandas`, confirmed by Q516. **Q498** (regression
intervals): "Yes, solve it now, we are building towards regression too" → the cells gain `sum_y2`
(Q517). **Q495, Q496, Q499, Q500**: unanswered, the defaults hold (the CLI test keeps EDA; a binary
numeric's deep dive shows the lift chart; `pivot_target`'s lift against the base before the filter;
pre-V21 `eda.json` files are stale, rerun EDA).

**R10.** "Can you remind me why we need to refuse strata column which the framework creates?"
*Answer:* the frames add `unit_id`, `period`, `eligible`, `target`, `split` and the tag columns, and
a source column so named is read as `source_<name>`; a stratum called `period` would stratify by
the framework's column. A guard for a rare clash → Q518 folds it into the snapshot-column check.

**R11.** "What is this DIRECTIONS dictionary preset at the top of many python files?" *Answer:* one
dict in `eda/ranking.py` mapping a concordance's sign (+1, −1, 0) to the ledger's `direction` text
(`+`, `-`, null); its inverse `SIGNS` sits in `eda/run.py`. The simplicity pass puts both in one
module.

**R12.** "What does shrinkage in rows mean? I don't understand the return row of window_k_rows"
*Answer:* the level encoding's prior weight: a level's rate is `(events + k · base) / (rows + k)`
with `k = min_events / base` rows, so the prior weighs 50 pseudo-events → Q519 renames it.

**R13.** "As scope_statistics is optimized to compute on a window ... if the 'compaction' parameter
is turned off ... do you transform the data into a cell-like table?" *Answer:* the parameter is
`eda.bins`; with `null` every distinct value is its own bin and the counts pass still writes cells,
one per feature × period × value × target bin; the statistics code is unchanged; the cell count is
estimated first and refused above 50 million. Every ranking statistic reads cells; only the
quartiles, the level counts and the pivots read the snapshot rows.

**R14.** "If a window is never collected, how will the notebook user be able to build anything on
top of the pre-orchestrated plots/outputs?" *Answer:* the snapshot (`result.frame`) and every table
(`result.tables`, the cells included) are in pandas; the window is reachable through the cells, not
through rows → Q514 adds `rate_by_period`, `lift_by_group`, `compare_sides`.

**R15.** "Make the notebooks run on the whole 100k data please" → done in the build: the local
environment file points at `synthetic_canonical`, notebooks 01 and 02 rerun on it.

**R16.** "cut the 'read in this order' ... halve the length of concordance explanation ... be more
concise ... AI sloppy elaborate" → Q515. **R17.** "No references to decisions" → Q515.
**R18.** "Where are you taking the 'When to move' column from?" *Answer:* hard-coded in
`reporting/blocks.py` `CHOICES`, echoing the template's comments → Q504.
**R19.** "The plots just simply don't look that great; title should be centered, x and y axis better
describing, label values are being cut off, there is no margin at the edges" → Q512.
**R20.** "concordance bar makes the value invisible in dark mode ... what is the table ordered on?"
*Answer:* ordered by the ranking value (best order when `non_monotone`), the bar on the plain
concordance → Q507; the bar colour → Q513.
**R21.** "What is 'Lift' in section 6? You literally display it everywhere but give no explanation"
*Answer:* the group's rate divided by the snapshot's base rate; defined in the guide cells of steps
4 and 6 but nowhere in the report or on the charts → Q503.
**R22.** "Reevaluate how important displaying standard errors all the time ... displaying low-value
data is a net negative" → Q505.
**R23.** "Key features should be plotted against strata, and the 'do your own things' section
should include more views, including this and holders vs non-holders" → Q509, Q514.
**R24.** "why do we have buckets like [374, 379.51) – [415, 419) ... = 13 – = 37 looks horrible"
*Answer:* a merged group's label joins its first and last bin's labels → Q511.
**R25.** "It looks pretty bad if the correlation overview includes features which are not compared
to any other features; shouldn't that overview have the same selection method as key_features?"
→ Q508.
**R26.** "Why is the 'How to read' at the end of the notebook?" *Answer:* the design (A25) put it in
the appendix → Q503 moves it up front.
**R27.** "Score by target class and concordance window should be plotted next to each other" →
Q502, Q510.
**R28.** "in the target factory notebook if you start from a 'pooled retail data', you create all
targets and then effectively save N data frames with only one feature difference ... walk me
through how this would work in the autonomous way in production" *Answer:* one table is saved,
with one `target_<use_case>` column per use case; each stage reads it and keeps its own target on
read (a projection, nothing written). The target source is read twice in a run by design (summary,
then save) and the notebook's step 3 builds every use case's frames in memory to compare them.
Autonomous flow: `run a.yml b.yml` runs the built stages in order; Target Factory builds the target
when `data.target.rule` is set (an upstream `column` alone is only checked), saves when
`data.model_input` is named, else every stage rebuilds the panel lazily in Spark → Q521 asks
whether to keep both modes. Production scoring needs no target; monitoring reuses the rule when
labels mature (D-054, designed not built); scheduling is the platform team's (D-079).

## The brainstorming round answered (2026-11-05): Q501–Q522
_Verbatim; "Default" takes the default stated in the question (recorded in `questions.md` of
2026-11-05, kept in git). Outcome: the review-2 build spec, `review2_spec.md` beside this file._

- Q501. Default → the notebook shows the summary, population and target, ranking, key features
  and your-own-views; reference groups, correlation and the appendix in the report only.
- Q502. Default → two rows of two charts per key feature; the level table only for a categorical or
  a few-valued numeric; every key feature.
- Q503. Default → how to read right after the choices (five lines), the appendix copy goes, lift
  axes titled "Lift vs base rate (1 = base)", two sentences on concordance in the top cell.
- Q504. "Drop When to move, the other three columns are sufficient"
- Q505. Default → intervals on charts; `low`/`high` only in target per period and target by
  stratum; `concordance_se` and `se` leave the views, stay in the tables and the ledger.
- Q506. Default → the lean ranking view (about 14 columns).
- Q507. Default → one `concordance` column holds the ranking value with the bar;
  `concordance_plain` beside it only on non-monotone rows.
- Q508. Default → the heatmap on the key features and the candidates they represent, always; a
  feature without a compared pair dropped and counted in the subtitle.
- Q509. "All key features, but don't drop the pivots, the styled pivots display numbers much better
  than the hover" → the strata chart and the pivot table per key feature × stratum variable.
- Q510. Default → one plotly figure with two panels through a `side_by_side` helper.
- Q511. "Keep the half-open brackets, that should be understood" → a merged group's label is its
  outer range `[374, 419)`, a single value `= 13`.
- Q512. "For now, let's keep it simple, just better organized" → no template change: centred
  titles, axis titles, margins, no clipped labels.
- Q513. "Should be readable on both, some people run notebooks on dark VSCode, some in Jupyter lab,
  you can't prescribe them how to do it"
- Q514. Default → `lift_by_group`, `compare_sides`, `rate_by_period` beside `pivot_target`.
- Q515. "Default, but don't set hardcoded target on word counts rather implement a mandatory
  reevaluation after writing a guide with the aim to make it more concise"
- Q516. "Spark" → `orderBy` before `toPandas`.
- Q517. Default → the cells gain `sum_y2`; regression means get t-intervals per period and bin.
- Q518. Default → the framework-name check folds into the snapshot-column check.
- Q519. Default → `window_k_rows` becomes `encoding_prior_rows`, one sentence in the guide.
- Q520. Default → the simplicity pass over `run.py`, `deep_dives.py`, `population.py` after the
  redesign.
- Q521. Default → both Target Factory modes stay.
- Q522. "Dependent on time and Fable capacity, main thread might be ran on Opus too, it's to be
  decided" → the spec is written for an Opus implementer.

# Review 3 (2026-11-06): remarks R29–R37, Q523–Q524 answered; the gaps spec merged
The SDS's review of the review-2 build, verbatim, with the outcome of each. Built together with
`eda_gaps_spec.md` (its questions Q525–Q530 and their answers are recorded verbatim in that
file's §0.2 and below).
- R29 (V46). "As said, I don't want to enforce any hardcoded rule on how much code has to be cut,
  for as long as the result is efficient. If you do a good job at the first go, there wouldn't
  be anything to cut" → no line-count targets for simplicity passes; code is written lean the
  first time and a pass only removes what is genuinely redundant.
- R30 (V47). "I don't have a problem with the fix, but can you explain what exactly happened
  here?" → explained in chat (Somers' D drops the pairs tied on the target; the SE did not).
- R31. "In the target factory notebook stage 1 summaries show only the observation window having
  mean_target, positive_rows and positive_events non-null; I thought we agreed that every period
  which is not in the last w period should be filled, why isn't it the case?" → by design since
  M2.1 the summary showed label statistics for the observation window only, to keep the
  validation period's label rate out of sight; the labels themselves are filled wherever the
  forward window is complete. Outcome: the summary shows them for every period up to the
  window's last; the periods after it stay blank, since their target windows reach into the
  validation period's outcomes (§4.2, §4.4).
- R32. "In printouts and comments in notebooks, don't have any reference to what the budget
  should be for a laptop, it's not generic info. Snapshot size is, that's good, budgets etc is
  not" → the collect printout drops "(budget … GB)", notebook 02 drops the laptop runtime line.
- R33. "In part 3, concordance, lift, intervals etc comments are printed in their own rows
  instead of being part of the description cell, why is it like that?" → they were the report's
  how-to-read view displayed as five outputs; the notebook now carries them in step 3's
  description cell and no longer displays the view (the report keeps it).
- R34. "In the pivots with integer numericals, get rid of the = sign if you can (so groups aren't
  = 0, = 1, = 2, rather 0, 1, 2)" → a numeric shown by level reads its values (`0`, `1`, `2`);
  ranges and a mass point among ranges keep their brackets and `= v`.
- R35. "What does the double star in a row like **_summary_views(meta, resolved) mean?" →
  explained in chat (dict unpacking: the returned dict's keys merged into the enclosing dict).
- R36. "I don't think you should define a function exactly called pivot_table, as that's
  literally a pandas function" → renamed `_stratum_pivot` (private).
- R37. "You say that in the correlation view, you display "the candidates they represent", but I
  still only see just a bunch of very correlated features with the only improvement being that
  you dropped the feature which has no correlation computed with others" → the heatmap shows the
  key features only (the same selection: no pair above `max_correlation`); the candidates each
  represents are listed in a short table beneath it.
- Q523. "Yes, but do it now" → a per-task axis format: rate axes in percent.
- Q524. "Option b), supported lines set the axis" → a line chart's axis follows its supported
  points; a grey point may run off the top, its number in the table or pivot.

# Review 4 (2026-11-06): remarks R38–R41, Q531 answered
The SDS's review of the review-3 build, verbatim, with the outcome of each. EDA then goes to the
LDS's review (`review_guide.md`, rewritten for the LDS) while Feature Checks starts in another
chat (`worknotes/handovers/m2-2-major-step-3.md`).
- R38. "Generally, unless I specifically tell you to do so, don't save the pre-cleared notebooks
  anywhere, just rewrite it" → a notebook is rewritten in place; no copy of its old outputs is
  kept (the review-3 copy deleted).
- R39. "The new parts in decision slices print multiple separate HTML pieces; try to avoid that
  and be in markdown cells as it's not great for readability" → the decision paragraph is its
  own view (`decision_note`), which the report opens the slices with; notebook 02 says it in step 5's
  markdown and displays only the table and the curve.
- R40. "Same comment in section 6" → the key features' headings (and the strata's in step 4) are
  displayed as Markdown, not raw HTML; section 6 prints no other text.
- R41. "Issue with the grey dots not setting limits: Looks very stupid with many grey dots; lift
  chart max should be decided by min(all_dots, colored_dots * 2)" → a line chart's top is the
  lower of every point (as a bar chart: the supported points' intervals, not the grey ones') and
  twice the highest supported point, with the usual 1.25 headroom on top; a grey point far above
  runs off. Bars are unchanged.
- Q531. "Do not split report.py, might be revisited based on LDS feedback." → `eda/report.py`
  stays one module.

# Feature Checks review 1 (2026-11-09): remarks R42–R55, Q532–Q538 answered
The SDS's first review of the Feature Checks build (major step 3), verbatim, with the outcome of
each. The SDS read the notebook, the report, the questions and the vetoes, not yet the code. The
follow-up questions are Q539–Q545 in `feature_checks_questions.md`.
- R42. "Note that in the first review round, I have only looked at the notebook, the report, the
  questions and vetoes, have not reviewed the code yet, mind this in the review guide updates." →
  the review guide for round 2 leads with the code, then what this round changed.
- R43. "Is it possible that the above-table tdescription HTML blocks be a bit larger font and
  left-aligned, so that it looks better in the notebook and doesn't blend it with everything
  else? I see that it works well in the report but looks weird in the notebook. On the other
  hand, major segment names (leakage, stability etc) are not big enough and capitalized in the
  report" → a table's caption is styled inside the table itself (top, left, bold, 1.1 times the
  table's font, muted), so notebooks 02 and 03 show it as the report does; the report's step
  headings read "Quality", "Leakage", "Time alignment", "Stability", "Redundancy", and its third-
  and fourth-level headings are larger.
- R44. "Step 2 concordance_window displayed is the higher or standard and non-monotone one,
  right?" → answered in chat: the standard (plain) concordance, its bins in their order, pooled
  over the window's periods; the best-order (non-monotone) value exists on the snapshot only and
  enters the ledger's `concordance` when a feature is marked non-monotone. Follow-up: Q541
  (`too_strong` sees only the monotone value).
- R45. "In the step 2 held features, is it possible/would it add value to have one more column
  which displays in a dictionary format what the problematic value was? So if it's like
  leakage.too_strong then it would be {'concordance': 0.95}. If there are checks where this view
  would be too reductionist, let me know" → the held table's `flag_values`: per open flag, its
  statistic and this run's value (`not raised`: open from an earlier run). Reductionist, said in
  chat: `rare_value_leak` (a ratio without the two rates and the minority's size: the detail has
  them), `concordance_unstable` (a p-value without the range), `client_constant` (no number tells
  a static attribute from a look-ahead).
- R46. "One thing a DS will need on the spot for any assisted workflow is quick data access to
  check on any findings; make sure that in notebooks this is available" → notebook 03's step 1
  loads the frames (`build_frames`: the snapshot in pandas, every compared period's eligible rows
  in Spark), and a new step 8 shows three checks on them: a feature's target by value, a few
  clients' values across the periods, a feature's distribution per compared period.
- R47. "Why are there so many nulls_informative columns on all sorts of different raw inputs (but
  with the almost exact same concordance), what is happening there?" → answered in chat: a
  roll-up is null while the client has fewer months on the book than it spans (the generator's
  rule), so the 37 six-month roll-ups share one null set (6.8% of the window's rows) and the 17
  three-month roll-ups another (3.1%): two facts, "a new client", repeated per column. Follow-up:
  Q543.
- R48. "In time-alignment view, for client_constant finding the concordance appears three times
  (concordance_window, detail and additional table),can you compact the info?" → the finding's
  detail is empty and the separate table is gone: the concordance shows once, in
  `concordance_window`.
- R49. "I think for Stability, PSI between 0.1-0.25 should be a not, but PSI above 0.25 should be
  a flag" → two tiers: the notes `stability.psi_window` and `stability.psi_latest` from
  `stability.psi_note_min` (0.10), the new flags `stability.psi_window_large` and
  `stability.psi_latest_large` from `stability.psi_max` (now 0.25), which hold the feature.
  Measured on the canonical card data: six more holds (46 in all), the four login roll-ups of the
  drift trap (0.43–0.50), the shifted loan trap column and one ratio
  (`inflow_casa_vol_0_2_vs_3_5_months_ratio`, window PSI 0.26).
- R50. "For concordance_unstable, why is there a 0.05 minimum difference, what does it want to
  achieve? Generally I have a bit of a problem with preset numeric thresholds as for a “strong” vs
  “weak” model they actually behave very differently, but at least the ones where it’s an input in
  the config, one could argue the DS should have an idea of what she faces. However, this baked-in
  inflexible thresholds are just not good really." → answered in chat: the 0.05 is a config leaf
  (`stability.concordance_range_min`), the effect-size floor beside Cochran's Q, which on a large
  population makes a tiny wobble significant. Follow-up: Q544 (the range relative to the
  feature's signal; the constants outside config).
- R51. "Redundancy findings: First, I want to see a table with clusters only, one row per cluster,
  feature is the highest-concordance feature with the target, a column with features list in the
  cluster and then thee computed cluster statistics you have; Afterwards, the feature-granularity
  table, but also in that the ordering should be finding type first, but then cluster and and
  values only afterwards. Also, wording on “no decisions should be made” is a bit strong for me,
  surely you want to consider dropping some features if they are the same thing?" → the
  redundancy step shows the cluster summary first (one row per cluster: its best member, that
  member's concordance, the size, the members, the lowest association with the best, the highest
  `explained_by_others`), then the feature table sorted by finding, cluster, then value; the
  wording now says to consider excluding the near-duplicates that add nothing.
- R52. "Two major questions for part 8, proposing decisions: First, why would the user give
  findings parameter for keeping something but not for excluding? Also, what if a user wants to
  keep half of the features and exclude the other half based on a finding’s review? Your examples
  suggest it’s all or nothing having the same features copied into both keep and exclude
  examples." → answered in chat: a `keep` is scoped (it settles only the findings it names, so a
  later, different flag holds the feature again), an `exclude` is not (out of training whatever
  its flags), so `findings` would change nothing on an exclude; the proposed exclude call now
  names its finding in `evidence`, for the trail. Each call takes any subset: the calls' header
  and step 9's guide say so, and the walk-through splits one finding (keeps three static
  attributes, excludes the look-ahead column).
- R53. "Why is concordance per period in Feature Checks’s report and not in EDA’s?" → answered in
  chat. Follow-up: Q542.
- R54. "For V88: shouldn’t those calculations be based on absolute values? It’s probably
  edge-case, but if a concordance moves from 0.65 to 0.48 that should be flagged, isn’t it? And in
  addition, if a feature would move from 0.65 to 0.35 (so the opposite of 0.5) , that’s suspicious
  for entirely new reasons, isn’t it?" → answered in chat: the window concordance carries no
  direction (at least 0.5) and the lagged one is read in the window's direction, so 0.65 → 0.48
  gives `signal_kept` −0.13 and 0.65 → 0.35 gives −1.0, both flagged `lagged_signal_drop`;
  absolute values would pass the second. Naming a flip in the detail needs the lagged value's SE:
  part of Q540.
- R55. "V91 (and Q534). When did I say you can hold at most two of the non-trap candidates? I
  don’t remember such hard constraint, and if I did, I was wrong to do so." → you did not: the
  plan's V7 (2026-11-03) introduced it in answer to a plan review, and Q534 wrongly called it
  yours. The count bound and `EXPECTED_HOLDS` are removed; the false-positive check is the null
  controls, which are never flagged.
- R56 (the build time). "Extra note: I know I said no hurry, but why did you take 26-28 hours to
  complete this stage? Based on previous times, I expected 3-4 hours of build time, this was
  almost 10 times that" → answered in chat from the session's timestamps; T36 (a background test
  run needs a deadline).
- Q532. "Shouldn’t the rare_effect_max be scaled not just as a linear multiplier to probabilities
  but rather a non-linear scalar? 0.002 -> 0.01 feels like a very different jump for me than 0.05
  -> 0.25" → follow-up Q539 (Cohen's h and d).
- Q533. "Yes" → categoricals stay in the rare-value rule.
- Q534 → R55.
- Q535. "Note my earlier PSI comment" → with R49 the example configs take the template's PSI
  defaults (`stability: {}`), and the acceptance test asserts the flag `psi_latest_large` on the
  login column or its roll-ups.
- Q536. "Default" → D-088 as worded: only Feature Checks' look at drift makes a period
  unavailable as the validation period, per data definition.
- Q537. "General question here with regards to the support guard anywhere: Assuming a smaller
  effective training base or rare positive rate (low count of events), wouldn’t a lot of “skipped
  tests” be a problem? My skeptical assumption of a user is that if you just tell I have skipped
  checks due to low events, any possible issues with the data will just be skipped because the
  user is often lazy and will just confuse “no tests” claim with “no issues” claim. Besides this, I
  agree with the D-031 reference, although statistical non-significance should be noted somewhere
  with any results (in detail prssibly)" → follow-up Q540; no 2-SE condition on
  `lagged_signal_drop` (a false hold errs the D-031 way).
- Q538. "Default" → `check_inputs` and one `steps.py`, as built.

# Feature Checks review 1, answers (2026-11-09): Q539–Q545 answered, remarks R57–R58
The SDS's answers to review 1's follow-up questions, verbatim, with the outcome of each.
- R57. "Note: Both for me for code review and a user who wants to better understand where
  calculations are referenced from, seeing the shape/examples of tables that are often referenced
  (like ledger). Can you create a 00_eda_fc_helper notebook where all you do is to load these
  relevant tables and display it for better understanding? The idea is that as I go through the
  code (for both EDA and Feature checks), I have a reference to compare things to; I expected the
  notebooks to be like that, but (and this is not a critique) they are wrapped up one level
  higher, therefore it’s really hard to review code at this point." → `notebooks/00_eda_fc_helper`:
  it loads EDA's and Feature Checks' stored artifacts (the ledger, every table, the two jsons, the
  audit log) read-only and shows each one's shape, columns and example rows, with what reads it.
- R58. "Delete the extra note about the 3-4 hour time, just keep the parallelism, tight loops and
  managed fix rounds; again, no set targets on timing, I just want efficient and quality work; I’m
  trying to manage review and prompting timing so that I don’t spend too much of my workday just
  waiting around." → the memory keeps parallelism, tight loops and managed fix rounds, with no
  time target.
- Q539. "Option (B)" → Cohen's h for a binary target, Cohen's d for a regression one, through the
  per-task spec; `rare_effect_max` 0.8.
- Q540. "Option (B) for now, it might be a bit risky with too many flags as an outcome but I’d
  rather start with too many flags and adjust based on takeaways from real data" → no check skips
  for support; each detail states the support in effective events and whether the value is more
  than 2 SE past its threshold; a statistic that cannot exist stays "not available".
- Q541. "Option (C), and make the change now, the LDS will not catch these small bits therefore a
  “freeze” is not required" → EDA computes the best-order concordance on the window too, and
  `too_strong` reads the higher of the two.
- Q542. "As above, build it now" → EDA computes, stores and shows the window's concordance per
  period; Feature Checks reads it; PSI per period stays in Feature Checks.
- Q543. "Option (B); this note is actually useful as can influence (triggering a restart) minimum
  relationship length filters too as we would generally want to model “new” and “established”
  clients separately" → the note's detail names the features sharing its null rows, the step
  table sorts them together, and the guide says a shared null set often marks a population (new
  clients) worth a filter or a model of its own.
- Q544. "Default" → `concordance_range_min` relative to the window's signal (default 0.5);
  `DOMINANT_SHARE` becomes `leakage.dominant_share_min` (0.90).
- Q545. "Option (B), but create a work note todo note for a synthetic data extension which I will
  do today whereas there must be trap and check columns for every single test" → the count-free
  guard in the trap test; a note listed, per finding, the trap column that must fire and the
  control column that must not, and it was built as synthetic 0.6.0 (2026-11-10).

# Feature Checks review 1, last answers (2026-11-10): Q546–Q547; the plan agreed
The SDS's answers, verbatim, with the outcome of each.
- Q546. "Option (A)" → `steps.py` stays one module, as built. (Since the codebase review of
  2026-11-10, Q568: the five checks stay one module, their input gathering is
  `feature_checks/inputs.py` and the finding-row builders are in `findings.py`.)
- Q547. "Option (B)" → the leaf `stability.concordance_range_floor` (default 0.05):
  `concordance_unstable` needs a range of at least max(floor, `concordance_range_min` ×
  |`concordance_window` − 0.5|). On the canonical term-deposit config the two signal-less digital
  flags (ranges 0.043 and 0.046) no longer fire: 26 held instead of 28 (read from the stored
  outputs, not re-run).
- The plan. "as the timeline_proposal is accepted, please combine that with the roadmap factoring
  in the extra week I’m spending now with Stage 2, the fact that I’ll be out of office for a few
  days and there’s the national day, so treat the two weeks from Nov 23 to Dec 6 as one week
  essentially." → `docs/roadmap.md` → Phase 2 plan owns the dates and the depth per component;
  `worknotes/timeline_proposal.md` is deleted, OD-01 closed into D-022. Stage 2 ends 11-13; M2.3
  11-16 – 11-24, M2.4 11-25 – 12-04, M3 12-07 – 12-11; the pre-release (12-18) and release 1.0
  (02-19) keep their dates.
- The full-codebase review. "Before I try to go through the Stage 2 code (again) properly using
  the helper notebook, I’ll want the best Fable model to do one full review of the codebase to
  suggest improvements and refactoring. For this, I’d like to clean up markdowns a bit to ensure
  optimal token usage and guidance, what can I delete?" → a list of deletion candidates in chat,
  for the SDS to pick.
