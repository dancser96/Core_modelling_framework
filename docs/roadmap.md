# Roadmap

**Verdict:** Phase 2 builds a first usable version of every part except the LLM branch, on synthetic
data, then moves it into the bank (target ≈ December 2026, no hard deadline). The build order is a
walking skeleton first, then 2–3 deepening rounds. This file holds the plan and the **open
decisions**. Current status lives in `docs/UPDATES.md`; settled decisions in `docs/decisions.md`.

Roles and the daily Lead DS sync: `docs/context/project.md` → People and rhythm. Sync preparation:
`/brief`.

## Phases

| Phase | Ends when | Status |
|---|---|---|
| Original plan, Phases 0–1 (`docs/reference/`) | — | Overtaken by the crunch |
| Crunch | First products scored end to end | Done (`legacy/propensity_crunch/`) |
| **Phase 2** | The definition of done below is met and the code is moved into the bank | **In progress** |
| Phase 3+ | — | Backlog below |

**Phase 2 definition of done:** owned by `docs/context/project.md` → Scope (D-021). In short: new
use case → production scores with only a config and the guided notebooks; every component at least
thin; only the LLM branch missing.

## Depth levels (D-022)

| Level | Meaning |
|---|---|
| **Full** | Every planned capability; per-function tests; documented; ready for the bank's CI/Sonar |
| **Deep** | The main capabilities built and tested on synthetic data; known gaps listed in the component doc |
| **Thin** | Works end to end with minimal features; real interface, config section and artifacts |
| **Stub** | Config section, artifact schema and interface exist; the body does the minimum or raises a clear "not implemented" |

These are proposed wordings; confirm them together with the depth table (OD-01).

## Phase 2 milestones

| # | Milestone | Content | Status |
|---|---|---|---|
| M0 | Design baseline | Docs rebuilt from three review rounds and the Lead DS notes | Done 2026-10-12 |
| M1 | Synthetic data + local Spark harness | `synthetic/` package (~100k × 24 months, sticky holdings and usage, traps, ground truth); generated dataset in `data/01_raw/`; Spark fixtures; generator validation tests; the second task type chosen (OD-15, D-050) | Next |
| M2 | Walking skeleton | Every stage thin, end to end, on synthetic data, binary task: config spine → environment adapter → dataset → Target Factory → EDA → Feature Checks → ledger → Training (AutoML) → Evaluation → reporting → register / promote / deploy → Inference → Monitoring; CLI / API; guided notebooks | — |
| M3 | Deepening round 1 | Priorities to agree at the time. Candidates: EDA usefulness, observation window and sampling, predefined path + Optuna + trade-off chart, compatibility table, stratified reporting | — |
| M4 | Deepening round 2 (and 3 if needed) | Remaining depth targets (OD-01); second task type end to end; monitoring layers 1–2 deep; registry tables; window ablation | — |
| M5 | Migration readiness | Bank-parity check, tests and CI/Sonar readiness per the depth table, release checklist, first move into the bank | — |

At most 2–3 deepening rounds will happen in a phase; don't plan for more.

## Backlog

**Phase 2** (milestone in brackets; detail lives in the component docs):
- Synthetic data: sticky holdings and usage, 24 months, traps, oracle (M1) — `test_harness.md`
- Dataset: observation window, client-grouped split, OOT validation, Spark-side sampling, row
  budget (M2 thin, M3 deep) — `dataset.md`
- Sampling comparison: the three sampling options vs the synthetic oracle (bias, calibration, AUC),
  to settle OD-17's default (M3) — `dataset.md`, `test_harness.md`
- Window ablation, "does a multi-month window beat a single month?" (M3/M4) — design in `dataset.md`
- Feature ledger (M2 thin) — `feature_ledger.md`
- EDA worth running first, with low-prevalence charts and pivot functions (M2 thin, M3 deep) — `eda.md`
- Feature Checks: correctness and quality, stability within the window (M2 thin, M3 deep) —
  `feature_checks.md`
- Training: AutoML path (M2), predefined path + Optuna + trade-off chart, automated selection,
  categorical handling, the general calibration step, optional refit, drift reference (M3) —
  `training.md`
- Evaluation: compatibility table and view slots, comparison reports, stratified metrics (M3) —
  `evaluation.md`
- Reporting: HTML writer, plotly, chart rules, choices block, model card (M2 thin, M3/M4 deep) —
  `reporting.md`
- Lifecycle: register / promote / deploy, registry tables (M2 thin, M4) — `lifecycle.md`
- Monitoring: operational and drift deep, performance and impact thin (M2 stub, M4) —
  `monitoring.md`
- Second task type end to end (M4) — OD-15
- Guided notebooks and release examples (M2 thin, M5) — `run_modes.md`

**Phase 3+:**
- Model documentation generator aligned with the internal documentation standard (only possible
  after a model is trained and persisted; checks that the necessary inputs exist — what the Lead DS
  means by "necessary inputs" is still to be asked).
- Sign-off log in the registry, pulling PR approvers.
- Framework-made pooled vs per-segment modelling decisions (uses the reserved `split` in the model
  key).
- Shadow challenger scoring (if OD-07 agrees).
- MLflow integration (if OD-13 agrees); alerting; retrain automation (the policy is recorded in
  Phase 2).
- Series task family (forecasting, rolling validation).
- Spark-native training engine, only if a use case needs it (`dataset.md`).
- Selection month for experiment sweeps that pick a variant, built with the LLM branch (D-053).
- LLM-assisted modelling, after internalisation (`llm_assist.md`).
- Corporate report theme, after internalisation (`reporting.md`).
- Repo rename to a domain-neutral name (D-001).

## Open decisions

Each row records who or what decides it. When one is settled, add a D-entry to `docs/decisions.md`
and delete the row here.

| ID | Question | Current leaning / proposal | Decided by / forum | Detail |
|---|---|---|---|---|
| OD-01 | Depth per component per phase (full / deep / thin / stub); level wording to review | Not drafted yet. The Lead DS suggested moving tracking (now Monitoring) and entity handling to Phase 3; the builder wants at least a stub of every major component in Phase 2 (monitoring layers 1–2 deep, D-040). To discuss | Builder, with the Lead DS | this file |
| OD-02 | Where a use case lives (repo per use case / per domain / other) and how users get the guided notebooks | Not one shared repo with code folders; users get their own notebook copies to explore | Chief DS meeting (b) | `components/run_modes.md` |
| OD-04 | Release path: zip → internal repo → internal CI → package repository (e.g. Nexus, where users pin versions)? Who publishes; whether CI/Sonar must pass first; is git clone fine in Phase 2 | Lead DS suggested Nexus distribution with version pins | Chief DS meeting (b) | `components/run_modes.md` |
| OD-05 | Where use-case extension code lives (use-case repo, referenced by import path, vs upstreamed into the framework) | — | Builder | `components/config.md` |
| OD-06 | Folder layout per entity × domain (separate parent folders or not); are storage permissions separate per entity? | — | Lead DS + platform colleagues | `components/lifecycle.md` |
| OD-07 | Model versions per key; one production version per key; shadow challenger | Proposal in `lifecycle.md` | Above the builder: Lead DS / Chief DS (e) | `components/lifecycle.md` |
| OD-08 | Registry storage: append-only event records, tables on top, records shaped like MLflow's; code version | Proposal in `lifecycle.md` | Platform/MLE + Chief DS (e, f) | `components/lifecycle.md` |
| OD-09 | What "registered" means: any kept run, or a gated production candidate | — | Chief DS meeting (e) | `components/lifecycle.md` |
| OD-10 | Config lifecycle from Target Factory to promotion: how human *and* automated feature decisions persist across reruns without multiple config versions | Open, a big design question. Includes the flag case: a hands-off run can't be registered while a flag is unresolved, and writing the `keep` into the config changes the config hash, so the run's frozen config no longer matches and registering would need an identical retrain | Builder | `components/config.md`, `components/feature_ledger.md` |
| OD-11 | Feature ledger: review the sketch | Sketch written. To fix: EDA and Feature Checks write their columns before any `run_id` exists, and two runs on the same data share them (one part per data definition, one per run?); human decisions copied in at Feature Checks go stale when the config is edited later (record them at training time?) | Builder | `components/feature_ledger.md` |
| OD-12 | The mandatory "core" report views per task | Structure agreed (summary page + core + extended); content open | Builder + Lead DS | `components/evaluation.md` |
| OD-13 | Monitoring tooling: MLflow or not, what to expose, where dashboards live | After the Chief DS meeting. A non-local MLflow instance may take a while to stand up; until then, quick registry tables (Lead DS) | Chief DS meeting (f) | `components/monitoring.md` |
| OD-14 | Model inventory design | In scope, possibly richer than registry tables | Builder + Lead DS | `components/lifecycle.md` |
| OD-15 | Which second task type to build in Phase 2; chosen by the end of M1 (D-050) | Open; the goal is proving extensibility, not solving a specific problem. One idea raised: regression with an asymmetric (quantile) loss, e.g. CatBoost quantile regression (inspired by an earlier liquidity-forecasting project where under- and over-funding cost differently; some data may exist) | Builder | `context/project.md` |
| OD-16 | Synthetic data: product archetypes, ballpark rates, two entities with different schemas | Rates to come from the builder | Builder | `components/test_harness.md` |
| OD-17 | Sampling for multi-month training (row-level / client-level / outcome-stratified with weights) and the window ablation design | Default: row-level negative sampling, stratified by month, after the client split; options 2–3 offered with guidance. Settle after comparing all three against the oracle on synthetic data. Ablation: paired bootstrap on one validation month, plus a row-count-matched control and per-month models | Builder | `components/dataset.md` |
| OD-18 | Inference output: extra columns for the campaign system; separate manifests from score files; the exact format | Details to come from the Lead DS. Candidate columns to consider: `domain` and `split` (the rest of the model key), `scoring_batch_id`, and a date column named after the glossary's inference month | Lead DS | `components/inference.md` |
| OD-19 | Where engineered features come from long term; whether a feature-aggregation spec is needed (LLM loop) | Phase 2: features come from upstream; spec shape only | Builder | `components/target_factory.md` |
| OD-20 | Documentation approach for users (generated docs, pages, wiki…), and the glossary's reach | Parked: too early | Chief DS meeting (c) | — |
| OD-21 | Eventual task scope | Framing agreed (panel tasks vs series tasks; nearby problems not excluded); the list is open | Chief DS meeting (a) | `context/project.md` |
| OD-22 | Trade-off chart (D-037): may it use the test metric, or only client-grouped CV inside train? Choosing a trial on test data conflicts with `CLAUDE.md` §4.4, and the test-vs-validation gap only separates overfitting from decay if test never chose anything | Leaning: CV inside train only; test reported, never chosen on | Builder + Lead DS | `components/training.md` |

## Chief DS design meeting (week of 2026-10-12)

Preparation (a pre-read built from the rows above) is still pending. Topics and the open decisions
they settle:

| Topic | Related |
|---|---|
| (a) Scope: binary, regression, multiclass, churn, forecasting, time series… | OD-21, OD-15 |
| (b) Consumption: git clone, Nexus distribution, API (unlikely), other | D-024, D-047, OD-02, OD-04 |
| (c) Documentation: generated docs, pages, markdown, wiki | OD-20 |
| (d) Structure: domain/entity-agnostic; key steps | D-028 (verify), D-034, OD-06 |
| (e) Promotion / deployment / consumption; breakpoints between local, registered and production; the Phase 2 definition of done's production step | D-033, D-055, OD-07, OD-08, OD-09 |
| (f) Monitoring: MLflow, how, what to expose | D-040, OD-13, OD-14 |
