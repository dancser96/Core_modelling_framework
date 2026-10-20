# Roadmap

**Verdict:** Phase 2 builds a first usable version of every part, on synthetic data, then moves it
into the bank (target ≈ December 2026, no hard deadline). The first release also integrates, thinly, with the
feature store and the data observability framework; LLM-assisted modelling comes in Phase 3 (D-075). The build order is a
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
thin, plus the integrations of D-075; LLM-assisted modelling comes in Phase 3.

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
| M1 | Synthetic data + local Spark harness | `synthetic/` package (~100k × 24 months, sticky holdings and usage, traps, ground truth); generated dataset in `data/01_raw/`; Spark fixtures; generator validation tests; the second task type chosen (D-050) | Generator done 2026-10-19 (with the LDS for review); second task chosen 2026-10-20: regression (D-080); its per-task spec still to design (D-060) |
| M2 | Walking skeleton | Every stage thin, end to end, on synthetic data, binary task: config spine → environment adapter → dataset → Target Factory → EDA → Feature Checks → ledger → Training (AutoML) → Evaluation → reporting → register / promote / deploy → Inference → Monitoring; CLI / API; guided notebooks | — |
| M3 | Deepening round 1 | Priorities to agree at the time. Candidates: EDA usefulness, observation window and sampling, compatibility table, stratified reporting, feature store integration (OD-26) | — |
| M4 | Deepening round 2 (and 3 if needed) | Remaining depth targets (OD-01); second task type end to end; monitoring layers 1–2 deep and integrated with the data observability framework (OD-13); registry tables; window ablation | — |
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
- Training: AutoML path (M2), automated selection,
  categorical handling, the general calibration step, optional refit, drift reference (M3) —
  `training.md`
- Evaluation: compatibility table and view slots, comparison reports, stratified metrics (M3) —
  `evaluation.md`
- Reporting: HTML writer, plotly, chart rules, choices block, model card (M2 thin, M3/M4 deep) —
  `reporting.md`
- Lifecycle: register / promote / deploy, registry tables (M2 thin, M4) — `lifecycle.md`
- Monitoring: operational and drift deep, performance and impact thin (M2 stub, M4) —
  `monitoring.md`
- Regression end to end (M4) — D-080
- Guided notebooks and release examples (M2 thin, M5) — `run_modes.md`
- Feature store work stream: learn how it works (near future, alongside M2), then integrate it
  (M3), with worked examples on the feature store, other sources and both (D-075) — OD-26,
  `environment.md`
- Data observability work stream: learn the framework (alongside M2–M3), then integrate
  monitoring with it (M4) (D-075) — OD-13, `monitoring.md`
- Config research before the config spine (M2): YAML or Python files (OD-24), the decision audit
  log (OD-10), automation levels (OD-25) — `config.md`
- Lossless non-pickle model formats, researched per model family before it is offered (D-078):
  at least one family verified before M2's training, the rest ongoing — `training.md`
- Retraining in production: research (M4) — OD-27, `lifecycle.md`

**Phase 3+:**
- Predefined modelling path tuned with Optuna, with the trade-off chart (D-080, OD-22).
- Model documentation generated from the model card in the internal documentation standard (only
  after a model is trained and saved; checks that the necessary inputs exist — what the Lead DS
  means by "necessary inputs" is still to be asked).
- Sign-off log in the registry, pulling PR approvers.
- Framework-made pooled vs per-segment modelling decisions (uses the reserved `split` in the model
  key).
- Shadow challenger scoring (if OD-07 agrees).
- MLflow for the registry and experiment tracking (if OD-08 and OD-13 agree); alerting outputs (acted on by the platform / MLOps team, D-079); retrain automation (the policy is recorded in
  Phase 2).
- Series task family (forecasting, rolling validation).
- Spark-native training engine, only if a use case needs it (`dataset.md`).
- Selection month for experiment sweeps that pick a variant, built with the LLM branch (D-053).
- LLM-assisted modelling (the CDS is keen; D-075, `llm_assist.md`).
- Corporate report theme, after internalisation (`reporting.md`).
- Repo rename to a domain-neutral name (D-001).

## Open decisions

Each row records who or what decides it. When one is settled, add a D-entry to `docs/decisions.md`
and delete the row here. **Short-term** rows must be settled to finish M1 or to build M2;
**medium-term** rows are needed only from M3 on, or are parked. Each question starts with its area.
The CDS leaves the design to the SDS and LDS (D-073), so a row is promoted to short-term when its
milestone comes up, and added to [Chief DS topics](#chief-ds-topics) when it changes scope or
direction or needs people outside the team.

### Short-term

| ID | Question | Current leaning / proposal | Decided by / forum | Detail |
|---|---|---|---|---|
| OD-01 | **Scope:** depth per component per phase (full / deep / thin / stub); level wording to review | Not drafted yet. The Lead DS suggested moving tracking (now Monitoring) and entity handling to Phase 3; the SDS wants at least a stub of every major component in Phase 2 (monitoring layers 1–2 deep, D-040). The first release also gains the feature store and data observability integrations, both thin, one worked example each (D-075) | SDS, with the LDS | this file |
| OD-05 | **Config:** where use-case extension code lives (use-case repo, referenced by import path, vs upstreamed into the framework) | — | SDS | `components/config.md` |
| OD-06 | **Lifecycle:** folder layout per entity × domain: keep the current folder structure that emulates the permission barriers (separate parent folders), or not? Are storage permissions actually separate per entity? | — (not answered by the CDS; ours to decide, D-073) | SDS + LDS; permission facts from the LDS and the platform / MLOps team | `components/lifecycle.md` |
| OD-07 | **Lifecycle:** model versions per key; one production version per key; shadow challenger | Straw man in `lifecycle.md`; it evolves as built (D-073) | SDS + LDS, with the platform / MLOps team (D-079) | `components/lifecycle.md` |
| OD-08 | **Lifecycle:** registry storage: append-only event records, tables on top, records shaped like MLflow's; code version | Straw man in `lifecycle.md`; thin records until then (D-059). MLflow fits the registry and experiment tracking better than monitoring (OD-13) | SDS + LDS, with the platform / MLOps team (D-079, OD-23) | `components/lifecycle.md` |
| OD-09 | **Lifecycle:** what "registered" means: any kept run, or a gated production candidate | Registration is gated either way: it needs the human feature sign-off (D-076). Still open: is a registered version a production candidate, or any defended model worth keeping? | SDS + LDS | `components/lifecycle.md` |
| OD-10 | **Config:** the config lifecycle and the decision audit log. The config is the starting point and never changes; decisions taken downstream, automated and human, go to an audit log (CDS direction, research). How is the log built and saved, covering every decision point? | Draft inventory of decision points in `config.md`. The SDS's idea: save each run's *pathway* of decisions, the way a path through a neural network lights up; the feature ledger is already that pathway for features. The log also removes the flag case: writing a `keep` into the config changed the config hash, so registering would have needed an identical retrain. Human decisions: grouped lists, one note per group; only a `keep` that resolves a flag needs a note (SDS leaning). Automated filters: D-058 | SDS | `components/config.md`, `components/feature_ledger.md` |
| OD-11 | **Features:** feature ledger: review the sketch | Sketch written. To fix: EDA and Feature Checks write their columns before any `run_id` exists, and two runs on the same data share them (one part per data definition, one per run?); human decisions copied in at Feature Checks go stale when the config is edited later (record them at training time?). It becomes the per-feature part of the decision audit log (OD-10) | SDS | `components/feature_ledger.md` |
| OD-18 | **Inference:** output: extra columns for the campaign system; separate manifests from score files; the exact format | Details to come from the Lead DS. Candidate columns to consider: `domain` and `split` (the rest of the model key), `scoring_batch_id`, and a date column named after the glossary's inference month | Lead DS | `components/inference.md` |
| OD-23 | **Lifecycle:** who builds the registry and deployment, and at what point they join the project | The CDS routes downstream questions to the platform / MLOps team (D-079); to agree with that team whether they build these or advise. Until then, register / promote / deploy are thin but real (D-059). The original plan had a part-time ML engineering lane for registration, the deployment path and drift alerting (`docs/reference/`) | SDS + LDS, with the platform / MLOps team | `components/lifecycle.md` |
| OD-24 | **Config:** config format: YAML or Python files? | The CDS prefers Python files; whether they are better for us is a research question for later. To weigh: readability for DS users; Pydantic validation either way; migrations as `dict → dict` functions (D-007); hashing and diffs; LLM drivability (Phase 3); safety: a Python config runs code when it is loaded, the same class of risk as pickle (D-078). Whatever the authoring format, the frozen config stays plain data | SDS, before the config spine is built (M2) | `components/config.md` |
| OD-25 | **Config:** automation levels (D-077): which levels; what each decides by rule and what by a person at each decision point; whether depth (budgets, trials) stays a separate knob; how a use case moves to another level and how the move is recorded | Proposal (Claude): three levels (e.g. autonomous, assisted, manual) that take over today's quick / standard / thorough defaults; the decision-point inventory (OD-10) says what each automates; budgets stay separate fields with defaults per level | SDS + LDS | `components/config.md` |

### Medium-term

| ID | Question | Current leaning / proposal | Decided by / forum | Detail |
|---|---|---|---|---|
| OD-02 | **Distribution:** where a use case lives (repo per use case / per domain / other) and how users get the guided notebooks | CDS hint: one repo per entity × domain would be good but may be idealistic; as the framework, or a use case in it, expands it may branch off, so likely something between that and today's repo per use case. Leaning: one repo per entity × domain by default, and a use case branches into its own repo when it grows. That needs standardised upstream data per entity and domain, which the feature store may provide (OD-26). Not one shared repo with code folders; the notebooks would come with the package in the base image (leaning, unverified) and users copy them. Doesn't block M2: the walking skeleton's use cases live in this repo's `conf/base/` | SDS + LDS | `components/run_modes.md` |
| OD-04 | **Distribution:** release mechanics: zip → internal repo → internal CI → Nexus → base image. Who publishes; what must pass first (CI/Sonar); how often images are cut; can a use case take a newer framework version within its image's year? | Channel settled: the base image through Nexus (D-074). Since an image lives a year, a use case may run a year-old version against the shared tables, so `CLAUDE.md` §2's "deprecate before removing" window (one minor version) may need to follow image support instead; decide at M5. The SDS expects the shared tables to be less of a problem than this suggests | SDS, with the platform / MLOps team (M5) | `components/run_modes.md` |
| OD-12 | **Evaluation:** the mandatory "core" report views per task | Structure agreed (summary page + core + extended); content open | SDS + LDS | `components/evaluation.md` |
| OD-13 | **Monitoring:** tooling and the data observability integration: what monitoring uses, what is shown and where dashboards live; how monitoring outputs feed the data observability framework (D-075) | Tooling and dashboards are the platform / MLOps team's (D-079); the integration is ours (D-075). A work stream to learn the data observability framework comes first. MLflow suits the registry and experiment tracking (OD-08), not tracking decay over time. Until then, quick registry tables (Lead DS) | SDS after the work stream, with the data observability team; tooling: the platform / MLOps team | `components/monitoring.md` |
| OD-14 | **Lifecycle:** model inventory design | In scope, possibly richer than registry tables | SDS + LDS | `components/lifecycle.md` |
| OD-17 | **Dataset:** sampling for multi-month training (row-level / client-level / outcome-stratified with weights) and the window ablation design | Default: row-level negative sampling, stratified by month, after the client split; options 2–3 offered with guidance. Settle after comparing all three against the oracle on synthetic data. Ablation: paired bootstrap on one validation month, plus a row-count-matched control and per-month models | SDS | `components/dataset.md` |
| OD-19 | **Features:** whether the Phase 3 LLM loop needs a feature-aggregation spec | Phase 2: features come from upstream, including the feature store (OD-26); only the spec's shape is kept in mind. If the feature store holds feature definitions, the loop may write those instead of a framework spec | SDS | `components/target_factory.md` |
| OD-20 | **Docs:** documentation approach for users (generated docs, pages, wiki…), and the glossary's reach | Parked: too early. The framework's own docs are written with Claude in our current documentation structure (D-075) | SDS + LDS | — |
| OD-22 | **Training:** trade-off chart (D-037): may it use the test metric, or only client-grouped CV inside train? Choosing a trial on test data conflicts with `CLAUDE.md` §4.4, and the test-vs-validation gap only separates overfitting from decay if test never chose anything | Leaning: CV inside train only; test reported, never chosen on. The chart comes with the predefined path in Phase 3 (D-080) | SDS + LDS | `components/training.md` |
| OD-26 | **Upstream:** feature store integration (D-075): how a use case reads from the feature store, alone or with other sources (point-in-time reads; how its entities and features map onto the data definition and its hash); whether Target Factory's targets are enrolled in it; how the work splits with the feature store team | A work stream to learn how the feature store works comes first, in the near future. The environment adapter's source resolution is the seam (a logical source → a table or the feature store). Short-term slice: the config spine allows several sources per entity from v1, joined on unit and month (`config.md`). Outside the bank the worked examples need a stand-in, e.g. the synthetic mart split into a "feature store" table and a second source | SDS after the work stream, with the feature store team | `components/environment.md` |
| OD-27 | **Lifecycle:** retraining in production. The CDS prefers models retrained in production rather than moved there. Promote and deploy would then move the recipe (frozen config, model family, hyperparameters, features, encoder levels) instead of a fitted model, and production retrains it | Research topic. Candidate mechanism: the refit (D-052) run in production: same features and hyperparameters, no search, calibration recomputed, the card shows the parent's evaluation. Open: a production-side check that the retrained model behaves like its parent before it scores; whether production has the data and compute to train; determinism; what "deployed" then records | SDS + LDS, with the platform / MLOps team (M4) | `components/lifecycle.md` |

## Chief DS topics

The CDS leaves the design to the SDS and LDS (D-073); the design meeting of 2026-10-15 is recorded
in D-073–D-079. A topic is raised with him when it changes scope or direction, needs people outside
the team, or he asked to see it. Results are shown at check-ins.

| Topic | Raise when | Related |
|---|---|---|
| Feature store integration: a use case on the feature store, on other sources, and on both | The work stream has a design | D-075, OD-26 |
| Data observability integration | The work stream has a design | D-075, OD-13 |
| Retraining in production; models without pickle | Research results per model family | OD-27, D-078 |
| Automation levels, and how a use case moves between them | The config spine is designed (M2) | D-077, OD-25 |
| Config format (Python or YAML) and the decision audit log | Research results | OD-24, OD-10 |
| Who builds and runs the downstream (platform / MLOps team) | If that team can't take it on | D-079, OD-23 |
| LLM-assisted modelling (he is keen) | Planning Phase 3 | D-075, `components/llm_assist.md` |
