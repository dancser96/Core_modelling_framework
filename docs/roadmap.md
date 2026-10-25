# Roadmap

**Verdict:** Phase 2 builds a first usable version of every part, on synthetic data, then moves it
into the bank. The working assumption (D-022, under review with the LDS and stakeholders): a
walking skeleton, then two deepening rounds, each followed by a run-through; a pre-release into
the bank's internal repo by 2026-12-18, and release 1.0 (the definition of done) by 2027-02-19,
submitted as the first change request (D-021). It is
milestones with dates per stage, not a task board (D-022). Release 1.0 also integrates, thinly,
with the feature store and the data observability framework; LLM-assisted modelling comes in
Phase 3 (D-021). This file holds the plan and the **open decisions**. Current status lives in `docs/UPDATES.md`; settled decisions in `docs/decisions.md`.

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
thin, plus the integrations of D-021; LLM-assisted modelling comes in Phase 3.

## Depth levels (D-022)

| Level | Meaning |
|---|---|
| **Full** | Every planned capability; documented |
| **Deep** | The main capabilities built and working on synthetic data; known gaps listed in the component doc |
| **Thin** | Works end to end with minimal features; real interface, config section and artifacts |
| **Stub** | Config section, artifact schema and interface exist; the body does the minimum or raises a clear "not implemented" |

Tests are a milestone criterion, not part of a level: light at the pre-release, every function and
CI / Sonar by release 1.0 (D-014).

These are proposed wordings; confirm them together with the depth table (OD-01).

## Phase 2 milestones
Working assumption (D-022), still under the LDS's review and needing stakeholder buy-in; the full
plan (dates, M2's stages, depth per component) is in `worknotes/timeline_proposal.md` and moves
here once agreed (OD-01).

| # | Milestone | Dates (working assumption) | Status |
|---|---|---|---|
| M0 | Design baseline | to 10-12 | Done 2026-10-12 |
| M1 | Synthetic data + local Spark harness | 10-13 – 10-21 | Done: accepted by the LDS 2026-10-21, three future to-dos (backlog); regression chosen (D-020), its per-task spec still to design (D-050) |
| M2 | Round 1a: walking skeleton, stages M2.1–M2.4 | 10-26 – 11-20 | — |
| M3 | Round 1b: exit points and calibration | 11-23 – 12-08 | — |
| M5a | Run-through 1 → pre-release (internal repo, not production) | 12-09 – 12-18 | — |
| M4 | Round 2: depth and integrations | 01-04 – 02-05 | — |
| M5b | Run-through 2 → release 1.0, the first change request (D-021) | 02-08 – 02-19 | — |

## Backlog

**Phase 2** (milestone in brackets; detail lives in the component docs):
- Synthetic data: sticky holdings and usage, 24 months, traps, oracle (M1) — `test_harness.md`.
  Future to-dos from the LDS's review (2026-10-21), before Feature Checks goes deep: more noise
  columns of several kinds, columns with very low fill rates, each named for what it is like the
  traps (`_trap_<kind>`)
- Dataset: observation window, client-grouped split, OOT validation, Spark-side sampling, row
  budget (M2 thin, M4 deep) — `dataset.md`
- Window ablation, "does a multi-month window beat a single month?" (a nice to have in M4) —
  design in `dataset.md`
- Target Factory: one binary rule family with lineage (M2 thin), the other rule families and
  labels for scored months (M4) (D-091) — `target_factory.md`
- Feature ledger (M2 thin) — `feature_ledger.md`
- EDA worth running first, with low-prevalence charts and pivot functions (M2 thin, M3 report
  presentable, M4 deep) — `eda.md`
- Feature Checks: correctness and quality, stability within the window (M2 thin, M4 deep) —
  `feature_checks.md`
- Training: AutoML path with all three families and their non-pickle round trips, the framework's
  categorical encoder and the drift reference (M2), the calibration chain right (M3), automated
  selection and richer categorical handling (M4); production retraining on the same data
  definition is the default deploy path (D-052) — `training.md`
- Evaluation: metrics from the per-task spec, the per-month-first test view, the stratified table
  and a one-method compatibility dict (M2 thin); view slots and comparison reports (M4) —
  `evaluation.md`
- Reporting: HTML writer, plotly, chart rules, choices block, model card (M2 thin, M4 deep) —
  `reporting.md`
- Lifecycle: register / promote / deploy, registry tables (M2 thin, M4) — `lifecycle.md`
- MLflow for the registry and experiment tracking, the Phase 2 goal: M2.4's own records map
  one-to-one onto MLflow; MLflow goes in with the other integrations (M4) once the platform / MLOps
  team confirms it is available, with `production.json` kept as the pointer through major version 1
  (D-111, OD-08) — `lifecycle.md`
- Inference: batch scoring into the master layer with the scores table and manifest shapes final
  (M2 thin), reinference (M4) — `inference.md`
- Monitoring: the frame in M2, deep by M4 with light content (D-040) — `monitoring.md`
- Regression end to end (M4) — D-020
- Guided notebooks and release examples (M2 thin, M3 guidance with the LDS as proxy user, M4 deep)
  — `run_modes.md`
- Feature store work stream: learn how it works (alongside M2), design it in the slowdown, then
  integrate it (M4): limited to Stage 1 (M2.1 Foundation), where a use case's data comes in,
  shown by one use case config in three source settings (the feature store, other sources, both), two of them commented out until inside
  the bank (D-021) — OD-26, `environment.md`
- Data observability work stream: learn the framework (alongside M2–M3), then integrate
  monitoring with it (M4) (D-021) — OD-13, `monitoring.md`
- What shapes the build (D-021): the feature store doesn't (it is limited to Stage 1, M2.1
  Foundation; feedback mechanisms are Phase 3); the data observability framework shapes the monitoring tables only once
  we have seen it in use; MLflow shapes the registry build if it is integrated in Phase 2
- Config spine: YAML, two automation levels, identities and the shared-table rule are settled
  (D-007, D-023, D-043, D-088), and so is the decision audit log (D-125); still open before M2.1: the
  level-by-decision-point mapping (OD-25) — `config.md`
- Artifact inventory: one table in `architecture.md` (artifact, owner doc, version field, writer,
  readers, compatibility rule) at M2.1 (D-007)
- A `dev` preset of about 20k clients in `synthetic/` for daily work on the skeleton (M2.1) —
  D-091, `test_harness.md`
- Lossless non-pickle model formats for what is promoted, researched per model family before it is
  offered (D-051): `lgbm`, `xgboost` and `catboost` all verified in M2 (D-037; spike 2, due
  11-09) — `training.md`
- Retraining in production: research (M4) — OD-27, `lifecycle.md`
- Learn sessions with the platform / MLOps team, the feature store team and the data observability
  team, booked by the LDS by 11-06; the data observability one before M3, so that its needs can
  shape the monitoring tables; the platform one also covers MLflow's availability — OD-08, OD-13,
  OD-23, OD-26
- The first change request (release 1.0, D-021): start its first-time steps (security review of
  the saved formats, the deployment path) when the freeze lifts, if the bank allows; unverified

## Phase 3 wishlist
Long-term targets, not planned into Phase 2 (D-072). Each item names where it came from.
- Predefined modelling path tuned with Optuna, with the trade-off chart (D-020; the chart weighs
  train and test metrics, never validation, D-083).
- An own client-grouped CV loop around the tuner (D-106, option D of the question on validation
  inside training).
- Advanced sampling (D-117): outcome-stratified client sampling with weights and the
  weight-aware statistics it needs; downsampling low-value rows with weights that calibrate back
  (the SDS rates it highest; closest known method: local case-control sampling, Fithian and
  Hastie, 2014); smart downsampling as a framework asset, researched in a literature round; the
  comparison of every option against the synthetic oracle, with no sampling as the reference.
- Recency weighting of older months, revisited if the window ablation shows that older months
  hurt (D-117).
- Production retrains on moved or extended data: later months, all clients (train + test) or a
  longer window (D-052).
- Feedback mechanisms into the feature store, e.g. enrolling Target Factory's targets (D-021,
  OD-26).
- A probe that detects a model scoring differently after a library upgrade: a small fixed table
  scored at save and again at every load (D-051).
- A question: should `register` re-score the stored test split with each model's plain-data copy
  and fail loud on any difference? The format is verified once per model family, so one model
  exporting differently in a case the family's round trip didn't cover would go unnoticed
  (whether that can happen on the pinned versions is unverified). Phase 2 relies on the
  per-family check alone (D-051).
- A rank score beside the calibrated probability, for comparing scores across products (OD-28).
- Model documentation generated from the model card in the internal documentation standard (only
  after a model is trained and saved; checks that the necessary inputs exist — what the Lead DS
  means by "necessary inputs" is still to be asked).
- A question: which source of people logs (who signs off, who approves a model) should the
  framework build in? Phase 2 builds none; approvals stay in the PR and the change request (D-033).
- A question: do we want to gate data to prevent the validation month's use, e.g. computing the
  validation metric only for a signed-off run, refusing to move the validation month once it was
  shown unless it moves by at least `w`, and listing every validation month a model was scored on
  on its card? Phase 2 shows it everywhere and trusts people (D-083).
- Framework-made pooled vs per-segment modelling decisions (uses the reserved `split` in the model
  key).
- Shadow challenger scoring (D-111).
- A third automation level, `manual` (D-023).
- MLflow for the registry and experiment tracking, only if it isn't integrated in Phase 2 (OD-08); alerting outputs
  (acted on by the platform / MLOps team, D-079); richer monitoring content (D-040); retrain
  automation (the policy is recorded in Phase 2).
- Further panel tasks in D-081's order: multiclass, time-to-event.
- Series task family (forecasting, rolling validation).
- Spark-native training engine, only if a use case needs it (`dataset.md`).
- LLM-assisted modelling (the CDS is keen; D-017, `llm_assist.md`).
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
| OD-01 | **Scope:** the Phase 2 plan: dates, M2's stages and the depth per component (full / deep / thin / stub) at the pre-release and release 1.0; level wording to review | Working assumption D-022 (`worknotes/timeline_proposal.md`): build on it now; the LDS is still reviewing, and stakeholder buy-in comes next week | SDS + LDS, then stakeholders | `worknotes/timeline_proposal.md` |
| OD-06 | **Lifecycle:** folder layout per entity × domain: keep the current folder structure that emulates the permission barriers (separate parent folders), or not? Are storage permissions actually separate per entity? | Production paths are separate from the sandpit (D-033, D-051), and permissions are the platform's, not the framework's (D-079); the question is only how the framework lays out its own outputs per entity × domain. Ours to decide (D-073) | SDS + LDS; permission facts from the platform / MLOps team | `components/lifecycle.md` |
| OD-08 | **Lifecycle:** MLflow for the registry and experiment tracking in Phase 2: is it available inside the bank? | The shape is settled (D-111): M2.4's own records map one-to-one onto MLflow; MLflow goes in with the other integrations in M4 once confirmed; `production.json` stays the pointer through major version 1, MLflow a store beside the own records. Its default flavors pickle, which is fine in the sandpit but not for what is promoted (D-051). Confirm availability at the platform learn session (by 11-06). MLflow fits the registry and experiment tracking better than monitoring (OD-13) | SDS + LDS, with the platform / MLOps team (D-079, OD-23) | `components/lifecycle.md` |
| OD-11 | **Features:** feature ledger: review the sketch | Not urgent; decided when the ledger is built (M2.2). Leaning: two parts, one per data definition keyed by the data-definition hash (EDA + checks) and one per run keyed by `run_id` (selection + use), joined on feature name; human decisions are the audit-log entries the run replayed (D-125) | SDS | `components/feature_ledger.md` |
| OD-12 | **Reporting:** the mandatory "core" views per task of the EDA, Feature Checks and Evaluation reports | Structure agreed and shared by the three reports (summary page + core + extended, D-036). Needed when EDA (M2.2) and Evaluation (M2.3) are built; proposal for binary in `evaluation.md` → Open questions | SDS + LDS | `components/evaluation.md`, `components/eda.md` |
| OD-18 | **Inference:** separate manifests from score files? | The format part is settled (D-016): the framework writes its own traceable scores table, the master layer, and consumable tables are built outside it. Still open: whether manifests sit beside or inside the score files; leaning: separate them, since manifests beside the score files break a Hive table over the scores (`inference.md`), with the layout from the LDS; designed with Inference (round 1a) | SDS + LDS | `components/inference.md` |
| OD-23 | **Lifecycle:** who builds the registry and deployment, and at what point they join the project | The CDS routes downstream questions to the platform / MLOps team (D-079); to agree with that team whether they build these or advise. Until then, register / promote / deploy are thin but real (D-033). The original plan had a part-time ML engineering lane for registration, the deployment path and drift alerting (`docs/reference/`) | SDS + LDS, with the platform / MLOps team | `components/lifecycle.md` |
| OD-25 | **Config:** automation levels (D-023): what `autonomous` and `assisted` each decide by rule and by a person at each decision point of `config.md`'s inventory, and how a move to another level is recorded (after the config freezes, an audit-log entry, which needs `automation_level` on `LOGGABLE_SETTINGS` and a rule for which stages rerun) | The mapping is written when the config spine is built (M2.1); budgets are separate fields with defaults per level, and a move is a config edit or an audit-log entry, never a CLI override (D-023) | SDS + LDS | `components/config.md` |

### Medium-term

| ID | Question | Current leaning / proposal | Decided by / forum | Detail |
|---|---|---|---|---|
| OD-02 | **Distribution:** where a use case lives (repo per use case / per domain / other) and how users get the guided notebooks | CDS hint: one repo per entity × domain would be good but may be idealistic; as the framework, or a use case in it, expands it may branch off, so likely something between that and today's repo per use case. Leaning: one repo per entity × domain by default, and a use case branches into its own repo when it grows. Either way a repo may hold several similar use cases, each a config and its audit log (D-006). That needs standardised upstream data per entity and domain, which the feature store may provide (OD-26). Not one shared repo with code folders; the notebooks would come with the package in the base image (leaning, unverified) and users copy them. Doesn't block M2: the walking skeleton's use cases live in this repo's `conf/base/` | SDS + LDS | `components/run_modes.md` |
| OD-04 | **Distribution:** release mechanics: zip → internal repo → internal CI → Nexus → base image. Who publishes; what must pass first (CI/Sonar); how often images are cut | Channel settled: the base image through Nexus (D-024). A use case can probably take a newer framework version within its image's year (D-047, soft); compatibility is about outputs (D-007). The first change request is release 1.0, the framework only (D-021) | SDS, with the platform / MLOps team (M5) | `components/run_modes.md` |
| OD-13 | **Monitoring:** tooling and the data observability integration: what monitoring uses, what is shown and where dashboards live; how monitoring outputs feed the data observability framework (D-021) | Tooling and dashboards are the platform / MLOps team's (D-079); the integration is ours (D-021). A work stream to learn the data observability framework comes first. MLflow suits the registry and experiment tracking (OD-08), not tracking decay over time. The framework's needs shape the monitoring tables only once we have seen it in use (D-040) | SDS after the work stream, with the data observability team; tooling: the platform / MLOps team | `components/monitoring.md` |
| OD-14 | **Lifecycle:** model inventory design | In scope, possibly richer than registry tables | SDS + LDS | `components/lifecycle.md` |
| OD-17 | **Dataset:** the window ablation design | Sampling is settled for Phase 2 (D-117: only when the config declares it, for a rare target or the row budget; uniform negative downsampling or a random sample of clients; no sample weights); advanced sampling is on the Phase 3 wishlist. Ablation, now a nice to have at release 1.0: paired bootstrap on one validation month, plus a row-count-matched control and per-month models; the choice weighs train and test (D-083) | SDS | `components/dataset.md` |
| OD-19 | **Features:** whether the Phase 3 LLM loop needs a feature-aggregation spec | Phase 2: features come from upstream, including the feature store (OD-26); only the spec's shape is kept in mind. If the feature store holds feature definitions, the loop may write those instead of a framework spec. The aggregation list agreed as a starting point for such a spec: sum / mean / max / min / std over windows, count of non-zero months, months since last non-zero, ratios between windows, and trend | SDS | Phase 3; no owner doc until then |
| OD-20 | **Docs:** documentation approach for users (generated docs, pages, wiki…), and the glossary's reach | Parked: too early. The framework's own docs are written with Claude in our current documentation structure (D-021) | SDS + LDS | — |
| OD-26 | **Upstream:** feature store integration (D-021): how a use case reads from the feature store, alone or with other sources (point-in-time reads; how its entities and features map onto the data definition and its hash); how the work splits with the feature store team | In Phase 2 the integration is limited to Stage 1 (M2.1 Foundation), where a use case's data comes in, and doesn't shape the build; feedback mechanisms, such as enrolling Target Factory's targets, are on the Phase 3 wishlist (D-021). A work stream to learn how the feature store works comes first, in the near future. The environment adapter's source resolution is the seam (a logical source → a table or the feature store). Short-term slice: the config spine allows several sources per entity from v1, joined on unit and month (`config.md`). The worked example is one use case config in three source settings; outside the bank only the other-sources setting runs, on synthetic data, and the two feature-store settings ship commented out | SDS after the work stream, with the feature store team | `components/environment.md` |
| OD-27 | **Lifecycle:** retraining in production. The CDS prefers models retrained in production rather than moved there | Shape settled (D-052): the bundle carries the recipe (`recipe_hash`); production refits it on the same window and clients, only the inference month moving, and passes a check against its evaluated parent (label-free agreement on the inference month, its own test-split AUC and calibration per window month, rows and positive events per month against the parent's EDA artifact, tolerances declared beforehand, never the validation month) before it scores. Retraining is the Phase 2 default, and deploying the fitted model without a retrain is also allowed (D-033). Still open, with the platform / MLOps team in M4: whether production has the data and compute to train; determinism; what "deployed" then records | SDS + LDS, with the platform / MLOps team (M4) | `components/lifecycle.md` |
| OD-28 | **Inference:** a rank score beside the calibrated probability? Scores are compared across products downstream (D-049); in the long run a rank or normalised score may serve that comparison better than probabilities alone | Not before release 1.0; probabilities with correct calibration until then | SDS + LDS | `components/inference.md` |

## Chief DS topics

The CDS leaves the design to the SDS and LDS (D-073); the design meeting of 2026-10-15 is recorded
in D-021, D-023, D-024, D-031, D-051, D-073, D-079. A topic is raised with him when it changes scope or direction, needs people outside
the team, or he asked to see it. Results are shown at check-ins.

| Topic | Raise when | Related |
|---|---|---|
| Feature store integration: a use case on the feature store, on other sources, and on both | The work stream has a design | D-021, OD-26 |
| Data observability integration | The work stream has a design | D-021, OD-13 |
| Retraining in production; models without pickle | Research results per model family | OD-27, D-051 |
| The Phase 2 plan: the December pre-release, release 1.0 and the dates | After the LDS's review and the stakeholder buy-in next week | D-022, `worknotes/timeline_proposal.md` |
| Automation levels (two in Phase 2), and how a use case moves between them | The config spine is designed (M2) | D-023, OD-25 |
| Config format: YAML, and the decision audit log, both decided (information items, with the reasoning) | Next check-in | D-043, D-125 |
| Who builds and runs the downstream (platform / MLOps team) | If that team can't take it on | D-079, OD-23 |
| LLM-assisted modelling (he is keen) | Planning Phase 3 | D-021, `components/llm_assist.md` |
