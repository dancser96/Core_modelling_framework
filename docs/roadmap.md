# Roadmap

**Verdict:** Phase 2 builds a first usable version of every part, on synthetic data, then moves it
into the bank: a pre-release in December 2026, and release 1.0 (the definition of done) early in
2027; the dates are being agreed with the LDS (D-097; proposal in `worknotes/timeline_proposal.md`,
no hard deadline). The plan is milestones with dates per stage, not a task board (D-109). Release 1.0 also integrates, thinly, with the
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
| Phase 3+ | — | [Phase 3 wishlist](#phase-3-wishlist) below |

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
| M1 | Synthetic data + local Spark harness | `synthetic/` package (~100k × 24 months, sticky holdings and usage, traps, ground truth); generated dataset in `data/01_raw/`; Spark fixtures; generator validation tests; the second task type chosen (D-050) | Generator done 2026-10-19; reviewed and accepted by the LDS 2026-10-21, with three future to-dos (backlog); second task chosen 2026-10-20: regression (D-080); its per-task spec still to design (D-060) |
| M2 | Walking skeleton | Every stage thin (Monitoring a stub), end to end, on synthetic data, binary task: config spine → environment adapter → dataset → Target Factory → EDA → Feature Checks → ledger → Training (AutoML) → Evaluation → reporting → register / promote / deploy → Inference → Monitoring; CLI / API; guided notebooks. Never lesser than the crunch output (D-093) | Proposed as round 1a, 10-26 – 11-20, four stages of 4–6 days (`worknotes/timeline_proposal.md`) |
| M3 | Deepening round 1 | Priorities to agree at the time. Candidates: EDA usefulness, observation window and sampling, compatibility table, stratified reporting, feature store integration (OD-26) | Proposed as round 1b, 11-23 – 12-08 (the week of 11-30 mostly lost): exit points close to final, calibration (D-104, D-109) |
| M4 | Deepening round 2 (and 3 if needed) | Remaining depth targets (OD-01); second task type end to end; monitoring layers 1–2 deep and integrated with the data observability framework (OD-13); registry tables; window ablation | Proposed as round 2, 01-04 – 02-05 |
| M5 | Migration readiness | Bank-parity check, tests and CI/Sonar readiness per the depth table, release checklist, first move into the bank | Proposed as two run-throughs: 12-09 – 12-18 (the pre-release: into the internal repo, not production) and 02-08 – 02-19 (release 1.0, the first change request, D-115) |

At most 2–3 deepening rounds will happen in a phase; don't plan for more.

## Backlog

**Phase 2** (milestone in brackets; detail lives in the component docs):
_The tags follow M2–M5 until the reshaped plan is agreed (Q218); it maps M2 to round 1a, M3 to
round 1b, M4 to round 2 and M5 to the two run-throughs, and moves most M3 depth to round 2._
- Synthetic data: sticky holdings and usage, 24 months, traps, oracle (M1) — `test_harness.md`.
  Future to-dos from the LDS's review (2026-10-21), before Feature Checks goes deep: more noise
  columns of several kinds, columns with very low fill rates, each named for what it is like the
  traps (`_trap_<kind>`)
- Dataset: observation window, client-grouped split, OOT validation, Spark-side sampling, row
  budget (M2 thin, M3 deep) — `dataset.md`
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
- Both integrations: how they plug in (the seams) is designed only when the code moves toward the
  bank; until then they don't shape the build, and the downstream schema won't change (the SDS,
  2026-10-21)
- Config spine: YAML, two automation levels, identities and the shared-table rule are settled
  (D-086–D-089); still open before M2.1: the audit log's Phase 2 scope (OD-10) and the
  level-by-decision-point mapping (OD-25) — `config.md`
- Artifact inventory: one table in `architecture.md` (artifact, owner doc, version field, writer,
  readers, compatibility rule) at S1 (D-119)
- A `dev` preset of about 20k clients in `synthetic/` for daily work on the skeleton (M2.1) —
  D-091, `test_harness.md`
- Lossless non-pickle model formats, researched per model family before it is offered (D-078):
  at least one family verified before M2's training, the rest ongoing — `training.md`
- Retraining in production: research (M4) — OD-27, `lifecycle.md`

## Phase 3 wishlist
Long-term targets, not planned into Phase 2 (D-121). Each item names where it came from.
- Predefined modelling path tuned with Optuna, with the trade-off chart (D-080; the chart weighs
  train and test metrics, never validation, D-083).
- An own client-grouped CV loop around the tuner (D-106, option D of the question on validation
  inside training).
- Advanced sampling (D-123): outcome-stratified client sampling with weights and the
  weight-aware statistics it needs; downsampling low-value rows with weights that calibrate back
  (the SDS rates it highest; closest known method: local case-control sampling, Fithian and
  Hastie, 2014); smart downsampling as a framework asset, researched in a literature round; the
  comparison of every option against the synthetic oracle, with no sampling as the reference.
- Recency weighting of older months, revisited if the window ablation shows that older months
  hurt (D-117).
- A probe that detects a model scoring differently after a library upgrade: a small fixed table
  scored at save and again at every load (D-121).
- A rank score beside the calibrated probability, for comparing scores across products (OD-28).
- Model documentation generated from the model card in the internal documentation standard (only
  after a model is trained and saved; checks that the necessary inputs exist — what the Lead DS
  means by "necessary inputs" is still to be asked).
- Sign-off log in the registry, pulling PR approvers.
- Framework-made pooled vs per-segment modelling decisions (uses the reserved `split` in the model
  key).
- Shadow challenger scoring (D-111).
- A third automation level, `manual` (D-087).
- MLflow for the registry and experiment tracking (if OD-08 and OD-13 agree); alerting outputs
  (acted on by the platform / MLOps team, D-079); richer monitoring content (D-112); retrain
  automation (the policy is recorded in Phase 2).
- Further panel tasks in D-081's order: multiclass, time-to-event.
- Series task family (forecasting, rolling validation).
- Spark-native training engine, only if a use case needs it (`dataset.md`).
- LLM-assisted modelling (the CDS is keen; D-075, `llm_assist.md`).
- Corporate report theme content, after internalisation; the theme-file mechanism is Phase 2
  (`reporting.md`).
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
| OD-01 | **Scope:** depth per component per phase (full / deep / thin / stub), and what the December pre-release contains (D-097); level wording to review | Reshaped 2026-10-21 (D-109): one plan table in `worknotes/timeline_proposal.md`, components grouped into five stages with depth at the pre-release and at release 1.0, goals, optional additions and dates; two build rounds, each followed by a short run-through (Q218), awaiting the LDS. Every major component is at least thin by December (monitoring layers 1–2 deep by release 1.0, D-040); the feature store and data observability integrations, both thin, one worked example each, at release 1.0 (D-075) | SDS, with the LDS | this file |
| OD-06 | **Lifecycle:** folder layout per entity × domain: keep the current folder structure that emulates the permission barriers (separate parent folders), or not? Are storage permissions actually separate per entity? | — (not answered by the CDS; ours to decide, D-073). Permissions themselves are the platform's, not the framework's (D-108); the question is only how the framework lays out its own outputs | SDS + LDS; permission facts from the platform / MLOps team | `components/lifecycle.md` |
| OD-08 | **Lifecycle:** registry storage after Phase 2: MLflow or our own records? | Phase 2 is settled (D-111, soft): append-only event records with derived tables and a `production.json` per model key. MLflow fits the registry and experiment tracking better than monitoring (OD-13) | SDS + LDS, with the platform / MLOps team (D-079, OD-23) | `components/lifecycle.md` |
| OD-10 | **Config:** the config lifecycle and the decision audit log. The config is the starting point and never changes; decisions taken downstream, automated and human, go to an audit log (CDS direction). How is it built? | The SDS's framing (2026-10-21): the config is set once Target Factory has run; every later decision is logged in an audit trail; loading config + log always gives one obvious final input for the modelling step. A proposal on that basis, for the SDS and the LDS, with a worked example of the log in use so its usability can be reviewed: Q241 in `worknotes/holistic_review_questions.md`. If accepted, human keep / exclude lists move from the config to the log (amends D-043) and the run's identity uses the replayed input (amends D-088) | SDS + LDS | `components/config.md`, `components/feature_ledger.md` |
| OD-11 | **Features:** feature ledger: review the sketch | Not urgent; decided when the ledger is built (M2.2). Leaning: two parts, one per data definition keyed by the data-definition hash (EDA + checks) and one per run keyed by `run_id` (selection + use), joined on feature name; human decisions read from the frozen config at training time | SDS | `components/feature_ledger.md` |
| OD-18 | **Inference:** separate manifests from score files? | The format part is settled (D-103): the framework writes its own traceable scores table, the master layer, and consumable tables are built outside it. Still open: whether manifests sit beside or inside the score files; designed with Inference (round 1a) | SDS + LDS | `components/inference.md` |
| OD-23 | **Lifecycle:** who builds the registry and deployment, and at what point they join the project | The CDS routes downstream questions to the platform / MLOps team (D-079); to agree with that team whether they build these or advise. Until then, register / promote / deploy are thin but real (D-059). The original plan had a part-time ML engineering lane for registration, the deployment path and drift alerting (`docs/reference/`) | SDS + LDS, with the platform / MLOps team | `components/lifecycle.md` |
| OD-25 | **Config:** automation levels (D-087): what `autonomous` and `assisted` each decide by rule and by a person at each decision point of `config.md`'s inventory; whether depth (budgets, trials) stays a separate knob; how a use case moves to another level and how the move is recorded | Budgets stay separate fields with defaults per level; the mapping is written when the config spine is built (M2.1) | SDS + LDS | `components/config.md` |

### Medium-term

| ID | Question | Current leaning / proposal | Decided by / forum | Detail |
|---|---|---|---|---|
| OD-02 | **Distribution:** where a use case lives (repo per use case / per domain / other) and how users get the guided notebooks | CDS hint: one repo per entity × domain would be good but may be idealistic; as the framework, or a use case in it, expands it may branch off, so likely something between that and today's repo per use case. Leaning: one repo per entity × domain by default, and a use case branches into its own repo when it grows. That needs standardised upstream data per entity and domain, which the feature store may provide (OD-26). Not one shared repo with code folders; the notebooks would come with the package in the base image (leaning, unverified) and users copy them. Doesn't block M2: the walking skeleton's use cases live in this repo's `conf/base/` | SDS + LDS | `components/run_modes.md` |
| OD-04 | **Distribution:** release mechanics: zip → internal repo → internal CI → Nexus → base image. Who publishes; what must pass first (CI/Sonar); how often images are cut | Channel settled: the base image through Nexus (D-074). A use case can probably take a newer framework version within its image's year (D-114, soft); compatibility is about outputs (D-107). The first change request is release 1.0, the framework only (D-115) | SDS, with the platform / MLOps team (M5) | `components/run_modes.md` |
| OD-12 | **Evaluation:** the mandatory "core" report views per task | Structure agreed (summary page + core + extended). A to-do for when Evaluation is built (M2.3); proposal for binary in `evaluation.md` → Open questions | SDS + LDS | `components/evaluation.md` |
| OD-13 | **Monitoring:** tooling and the data observability integration: what monitoring uses, what is shown and where dashboards live; how monitoring outputs feed the data observability framework (D-075) | Tooling and dashboards are the platform / MLOps team's (D-079); the integration is ours (D-075). A work stream to learn the data observability framework comes first. MLflow suits the registry and experiment tracking (OD-08), not tracking decay over time. Until then, quick registry tables (Lead DS) | SDS after the work stream, with the data observability team; tooling: the platform / MLOps team | `components/monitoring.md` |
| OD-14 | **Lifecycle:** model inventory design | In scope, possibly richer than registry tables | SDS + LDS | `components/lifecycle.md` |
| OD-17 | **Dataset:** the window ablation design | Sampling is settled for Phase 2 (D-123: uniform negative downsampling for rare binary targets, a random sample of clients for common targets and regression, no sampling when the rows fit the budget); advanced sampling is on the Phase 3 wishlist. Ablation, now a nice to have at release 1.0: paired bootstrap on one validation month, plus a row-count-matched control and per-month models; the choice weighs train and test (D-083) | SDS | `components/dataset.md` |
| OD-19 | **Features:** whether the Phase 3 LLM loop needs a feature-aggregation spec | Phase 2: features come from upstream, including the feature store (OD-26); only the spec's shape is kept in mind. If the feature store holds feature definitions, the loop may write those instead of a framework spec | SDS | `components/target_factory.md` |
| OD-20 | **Docs:** documentation approach for users (generated docs, pages, wiki…), and the glossary's reach | Parked: too early. The framework's own docs are written with Claude in our current documentation structure (D-075) | SDS + LDS | — |
| OD-26 | **Upstream:** feature store integration (D-075): how a use case reads from the feature store, alone or with other sources (point-in-time reads; how its entities and features map onto the data definition and its hash); whether Target Factory's targets are enrolled in it; how the work splits with the feature store team | A work stream to learn how the feature store works comes first, in the near future. The environment adapter's source resolution is the seam (a logical source → a table or the feature store). Short-term slice: the config spine allows several sources per entity from v1, joined on unit and month (`config.md`). Outside the bank the worked examples need a stand-in, e.g. the synthetic mart split into a "feature store" table and a second source | SDS after the work stream, with the feature store team | `components/environment.md` |
| OD-27 | **Lifecycle:** retraining in production. The CDS prefers models retrained in production rather than moved there | Shape settled (D-096): the bundle carries the recipe (`recipe_hash`), production runs the refit (D-052) with a label-free agreement check against the parent before it scores. Still open, with the platform / MLOps team in M4: whether production has the data and compute to train; determinism; what "deployed" then records | SDS + LDS, with the platform / MLOps team (M4) | `components/lifecycle.md` |
| OD-28 | **Inference:** a rank score beside the calibrated probability? Scores are compared across products downstream (D-104); in the long run a rank or normalised score may serve that comparison better than probabilities alone | Not before release 1.0; probabilities with correct calibration until then | SDS + LDS | `components/inference.md` |

## Chief DS topics

The CDS leaves the design to the SDS and LDS (D-073); the design meeting of 2026-10-15 is recorded
in D-073–D-079. A topic is raised with him when it changes scope or direction, needs people outside
the team, or he asked to see it. Results are shown at check-ins.

| Topic | Raise when | Related |
|---|---|---|
| Feature store integration: a use case on the feature store, on other sources, and on both | The work stream has a design | D-075, OD-26 |
| Data observability integration | The work stream has a design | D-075, OD-13 |
| Retraining in production; models without pickle | Research results per model family | OD-27, D-078 |
| The Phase 2 plan: the December pre-release, release 1.0 and the dates | Once agreed with the LDS | D-097, `worknotes/timeline_proposal.md` |
| Automation levels (two in Phase 2), and how a use case moves between them | The config spine is designed (M2) | D-077, D-087, OD-25 |
| Config format: YAML, decided (information item, with the reasoning); the decision audit log | Next check-in | D-086, OD-10 |
| Who builds and runs the downstream (platform / MLOps team) | If that team can't take it on | D-079, OD-23 |
| LLM-assisted modelling (he is keen) | Planning Phase 3 | D-075, `components/llm_assist.md` |
