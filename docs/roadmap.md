# Roadmap

**Verdict:** Phase 2 builds a first usable version of every part, on synthetic data, then moves it
into the bank. The plan (D-022, agreed 2026-11-10): a walking skeleton, then two deepening
rounds, each followed by a run-through; a pre-release into the bank's internal repo by
2026-12-18, and release 1.0 (the definition of done) by 2027-02-19, submitted as the first change
request (D-021). It is milestones with dates per stage, not a task board (D-022). Release 1.0 also integrates, thinly,
with the feature store, and a production model's source tables are pointed to the data
observability framework at deploy; LLM-assisted modelling comes in Phase 3 (D-021). This file holds the plan and the **open decisions**. Current status lives in `docs/UPDATES.md`; settled decisions in `docs/decisions.md`.

Roles and the daily Lead DS sync: `docs/context/project.md` → People and rhythm. Sync preparation:
`/brief`.

## Phases

| Phase | Ends when | Status |
|---|---|---|
| Original plan, Phases 0–1 | — | Overtaken by the crunch |
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

## Phase 2 plan
Agreed 2026-11-10 (D-022). Two build rounds, each followed by a short run-through:
1. **Round 1** (M2 + M3, 10-26 – 12-11): every component end to end, then the exit points close
   to final and calibration right.
2. **Run-through 1** (M5a, 12-14 – 12-18): a real run as a user would make it, fixes only, then
   the code moves into the bank's internal repo, committed and demonstrated: **the December
   pre-release**. Not production: the year-end change freeze (D-021).
3. **Round 2** (M4, 01-04 – 02-05): depth where the pre-release showed it matters, both
   integrations, regression end to end, tests to every function.
4. **Run-through 2** (M5b, 02-08 – 02-19): the same procedure, ending in **release 1.0**,
   submitted as the first change request; production follows once it clears.

Why this shape:
- The skeleton comes first inside round 1: every stage thin before anything deepens, so problems
  between stages surface early, not in the run-through.
- Shapes final, contents thin: round 1 brings the exit points (`glossary.md`) close to final
  (the scores table and manifest, the model bundle, registry records, monitoring tables, the model
  card). The downstream teams plan on them, and from release 1.0 they only grow (D-007).
  December's two purposes (D-022) need a working run and these shapes, not depth everywhere.
- The run-through is mirrored before release 1.0, so the release checklist is tested once in
  December. Two deepening rounds; don't plan for more.

**Calendar.** Stage 2 took one week more than first planned: it ends 11-13, built to its design's
full scope (Q418–Q419) and reviewed twice. The fortnight 11-23 – 12-06 counts as one working week
(the EDS's leave and National Day). 12-21 – 01-01 is a slowdown, about six slower days (2–3 days'
leave plus 01-01), for fixes, the integration designs and the pre-release's buffer.

| # | Milestone | Dates | Done when | Status |
|---|---|---|---|---|
| M0 | Design baseline | to 10-12 | Docs rebuilt from three review rounds and the LDS's notes | Done 2026-10-12 |
| M1 | Synthetic data + local Spark harness | 10-13 – 10-21 | `synthetic/` (~100k × 24 months, traps, oracle) generated into `data/01_raw/`; Spark fixtures; the second task chosen | Done: accepted by the LDS 2026-10-21; its to-dos built in M2.1 (0.5.0), the `unstable` kind in M2.2 (0.6.0); regression chosen (D-020); its per-task spec entries for EDA and Feature Checks designed with Stage 2 (D-050, 2026-11-02), Training's and Evaluation's with M2.3 |
| M2 | Round 1a: walking skeleton, stages M2.1–M2.4 below | 10-26 – 12-04 | `run` end to end on synthetic data, binary task; `deploy` to a production-tier path and inference from it; nothing the crunch did is missing (D-037) | In progress (stages below) |
| M3 | Round 1b: exit points and calibration | 12-07 – 12-11 | The LDS has reviewed the exit-point shapes; calibrated scores match the oracle's probabilities on synthetic data (D-049). Its third goal, a presentable EDA + Feature Checks report, was built in M2.2 | — |
| M5a | Run-through 1 → pre-release (internal repo, not production) | 12-14 – 12-18 | The code runs inside the bank to a local model: a smoke run on a real mart, the reports to show, a demo | — |
| M4 | Round 2: depth and integrations | 01-04 – 02-05 | Each item reviewed by the LDS | — |
| M5b | Run-through 2 → release 1.0, the first change request (D-021) | 02-08 – 02-19 | The definition of done (D-021), plus CI / Sonar; aimed at 02-12; shared formats freeze from its first row in the bank (D-007) | — |

**M2's stages,** sized by weight (working days; the fortnight 11-23 – 12-06 holds five: M2.3's
last and M2.4's four):

| Stage | Dates | Days | Goal | Status |
|---|---|---|---|---|
| M2.1 Foundation | 10-26 – 11-02 | 6 | One config gives the train, test and validation frames, with eligibility and split logs | Built (0.2.0), reviewed and closed by the EDS |
| M2.2 Understanding | 11-03 – 11-13 | 9 | The traps are flagged, the EDA + Feature Checks report opens offline and reads well, the ledger shows each feature's trail | Built (0.3.0; D-134–D-138), reviewed with a codebase review and closed by the EDS on 2026-11-11; the LDS tries it with `worknotes/lds_run_guide.md`; the questions it raised: `docs/guides/eda_fc_faq.md` |
| M2.3 Modelling | 11-16 – 11-24 | 6 | A calibrated model beats the baselines and never the oracle; three families round-trip without pickle; no CV fold mixes a client's rows (D-106) | — |
| M2.4 Operations | 11-25 – 12-04 | 4 | Register, promote, deploy, score and monitor from the CLI and the notebooks | — |

M3 and M4 deepen across stages rather than stage by stage.

### Depth per component
Levels as in [Depth levels](#depth-levels-d-022). "Shape final": the output's schema is close to
final (an exit point) while its content is thin. "Nice to have": done only if the round has room;
the first cut. Stage 5 (integrations and release) runs in M4 and both run-throughs.

| Stage | Component | Pre-release (Dec) | Release 1.0 (Feb) | Nice to have |
|---|---|---|---|---|
| 1 | Config spine (YAML, levels, identities, decision audit log) | deep | deep | A command showing where each resolved value came from |
| 1 | Environment adapter | deep (bank-verified) | deep | — |
| 1 | Dataset (window, split, sampling) | thin (uniform negative downsampling, D-117) | deep (simple sampling: options 1, 2 or none, D-117) | — |
| 1 | Target Factory | thin (one binary rule family, lineage) | deep (other rule families, labels for scored months) | Incremental builds |
| 2 | EDA | as built in M2.2 (Q418: every view of `eda.md`); report presentable | deep (what the pre-release shows is missing) | Pivot functions |
| 2 | Feature Checks | as built in M2.2: all five steps, stability included | deep | — |
| 2 | Feature ledger | thin | deep (joined with the audit log) | — |
| 2 | Reporting | thin (HTML, embedded plotly, styled tables) | deep (theme file) | — |
| 2 | Synthetic data | as accepted (M1) plus the LDS's noise, constant, redundant and very-low-fill columns (0.5.0) and a trap and a control for every Feature Checks finding, the `unstable` kind included (0.6.0) | as the pre-release | — |
| 3 | Training (FLAML) | thin; client groups (D-106); calibration chain right (D-049); bundle shape final | deep (categoricals, automated selection; retraining keeps the data definition, D-052) | — |
| 3 | Evaluation | thin (core views, reliability among them) | deep (comparison, stratified) | Window ablation and the sweep function |
| 3 | Model card | shape final | deep | — |
| 4 | Lifecycle (register / promote / deploy) | thin; records shape final (D-111) | deep (registry tables, inventory) | — |
| 4 | Inference | thin; scores table and manifest shape final | deep (reinference) | — |
| 4 | Monitoring | frame in place: four layers, tables with flags, shape final | frame deep, content light (D-040) | — |
| 4 | CLI and Python API | thin | deep | — |
| 4 | Guided notebooks | thin | deep (guidance reviewed by the LDS) | — |
| 5 | Feature store integration | — (learn session; design in the slowdown) | thin | — |
| 5 | Data observability (a deploy step, nothing built; D-021) | — | the step in the deploy docs | — |
| 5 | MLflow (registry, experiment tracking; if confirmed available, D-111) | — (M2.4's records map onto it) | thin | — |
| 5 | Regression | shapes (per-task spec entries) | end to end | — |
| 5 | Tests | invariants, migrations, bundle round trip, e2e on `unit` | every function; CI / Sonar | — |
| — | LLM-assisted modelling | — | — (Phase 3) | — |

### Work streams beside the critical path
- **Spikes** (the EDS runs them, Claude reminds; due before M2.3, 11-16): (1) FLAML 2.7's group
  split on the synthetic data (D-106 needs it, or its fallback; no sample weights in Phase 2,
  D-117); (2) non-pickle round trips for `lgbm`, `xgboost`, `catboost`; (3) Arrow `toPandas`
  with date columns; (5) plotly in the bank's JupyterLab, opening time included (the EDS, inside,
  later). Spike 4 is dropped (D-036).
- **Learn sessions, booked by the LDS, by 11-06:** platform / MLOps (change-request steps and the
  freeze, MLflow's availability OD-08, the registry owner OD-23, Sonar's quality gate,
  scheduling); the feature store team (OD-26: how a use case reads from it; its design is written
  in the slowdown). The data observability team only needs to show how a source table is pointed
  to their framework, before a model's first deploy (D-021).
- **The first change request** (release 1.0, the framework only, D-021): if the bank allows,
  start its first-time steps (security review of the saved formats, the deployment path) when the
  freeze lifts in January, using the pre-release as material, so only the final submission waits
  for 1.0 (unverified: the freeze's dates and the process are unknown).

### Assumptions and how each block ends
- The EDS works on the framework about 6 hours a day with Claude and reviews every line; the LDS
  reads 30–60 minutes a day. Review time, about 40% of build time, is inside each block.
- The year-end change freeze is long and its dates are unknown; nothing in the plan needs a change
  request before release 1.0. External teams are unavailable until a session is booked, and
  nothing on the critical path depends on them before round 2.
- One memory-heavy job at a time on the 8 GB Mac; the WSL2 PC takes round 2's heavy comparisons.
- Each stage M2.1–M2.4 and round 1b ends in the EDS's review with a review guide (D-003) and the
  LDS's review (D-072 (i): the design docs, the ML-critical code, the functionality and the
  notebooks); the EDS decides (D-072 (n)) and asks the LDS's view on the short-term open decisions below. A
  fresh-context holistic review closes each round, before its run-through.
- A run-through: the EDS takes one use case from config to scores through the guided notebooks and
  the CLI, on the canonical synthetic data, as a user would; the LDS reads the reports and the exit
  points. Findings become a fix list; nothing new is built.

### Risks to these dates

| Risk | Trigger | Response |
|---|---|---|
| Review backlog grows | More than five items on the sync page's review list for a week | The LDS reviews designs and ML-critical code only; the EDS reviews with review guides |
| Round 1a slips (M2.2 took nine days against four) | M2.3 not done by 11-24, or M2.4 by 12-04 | Round 1b keeps the exit points; calibration depth moves to round 2 |
| Round 1b is short | Five days, 12-07 – 12-11 | The exit points first, then calibration; the slowdown's first days are the pre-release's buffer |
| An exit point's shape changes after the pre-release | A downstream team needs a different shape | Cheap until release 1.0's first shared row (D-007); collect the changes in run-through 1 |
| Round 2 is too full | Behind plan in its third week | Cut the nice to haves, then depth in EDA and Evaluation. The integrations, regression and tests stay (D-021, D-022) unless the CDS agrees otherwise |
| A spike fails | Any spike result before 11-16 | A family whose round trip fails is fixed in M2.3 rather than dropped (D-037); a failed group split falls back to a client-grouped holdout (D-106) |
| External teams not available | No session booked by 11-06 | The feature-store settings of the release example stay commented out (D-021); a flat monitoring export stands in; the integrations stay in round 2 |
| Memory on the 8 GB Mac | An out-of-memory error in M2.3 or round 2 | The `dev` preset of about 20k clients for daily work; the WSL2 PC for comparisons |
| The first change request is slow | Its first-time steps can't start before 1.0 is final | Release 1.0 is ready by 02-19 but reaches production later (March or after); tell the CDS early |

## Backlog

**Phase 2** (milestone in brackets; detail lives in the component docs):
- Feature Checks: run `client_constant` on time-varying features only, from the feature store's
  static/time-varying metadata once it exists (the EDS, 2026-11-04) — `feature_checks.md`
- Synthetic data: sticky holdings and usage, 24 months, traps, oracle (M1) — `test_harness.md`.
  The LDS's to-dos (2026-10-21: noise columns of several kinds, very-low-fill columns, each named
  like the traps) are built in M2.1 (2026-10-25, version 0.5.0). Built 2026-10-30 (0.5.3): a
  feature-store extract stand-in that the primary example joins, and mistake tests for every
  source guardrail ([merges and mistake tests](components/test_harness.md#merges-and-mistake-tests)).
  Built 2026-11-10 (0.6.0): a trap and a control for every Feature Checks finding, the `unstable`
  kind included ([trap summary](components/test_harness.md#trap-summary))
- Dataset: observation window, client-grouped split, OOT validation, Spark-side sampling, row
  budget (M2 thin, M4 deep) — `dataset.md`
- A migration hook for the model input's sidecar (`_model_input.json`), like the config's
  `migrate`, once a saved model input must outlive a framework version inside the bank; until
  then its migration is a rebuild from the sources (M5a at the earliest) — `dataset.md`
- A saved model input does not notice new source columns (its hashes see logical names, D-131):
  compare the saved table's columns with the sources' at read and print the difference
  (candidate; seen with synthetic 0.6.0, 2026-11-10) — `dataset.md`
- Identities before anything is kept inside the bank (by M5a, the pre-release): whether hashes
  leave out values at their schema default, so an added optional field doesn't change every
  digest, and a `definition.json` beside each audit-log folder so a recipe change can re-key it
  (the EDS, Q390, 2026-10-26) — `config.md` → Open questions
- Window ablation, "does a multi-month window beat a single month?" (a nice to have in M4) —
  design in `dataset.md`
- Target Factory: one binary rule family with lineage (M2 thin), the other rule families and
  labels for scored months (M4) (D-091) — `target_factory.md`
- Feature ledger (M2 thin; the per-data-definition part built in M2.2, the per-run part in M2.3) — `feature_ledger.md`
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
- Data observability (D-021): nothing to build; the deploy change request points a production
  model's source tables at that framework (written into the deploy docs with M2.4; done inside
  the bank at a model's first deploy) — `lifecycle.md`
- What shapes the build (D-021): the feature store doesn't (it is limited to Stage 1, M2.1
  Foundation; feedback mechanisms are Phase 3); nor does the data observability framework, which
  watches source tables; MLflow shapes the registry build if it is integrated in Phase 2
- Config spine: YAML, two automation levels, identities and the shared-table rule are settled
  (D-007, D-023, D-043, D-088), and so are the decision audit log (D-125), the level mapping (D-132), the
  layout, the environment file and the model input (D-129–D-131); built in M2.1 — `config.md`
- Config spine (M4): the replay flags the person entries that cite a superseded rule or stage
  entry; `show_decisions`' default view hides run outputs and resolved flags and filters by
  stage and by who decided — `config.md`
- Artifact inventory: one table in `architecture.md` (artifact, owner doc, version field, writer,
  readers, compatibility rule) at M2.1 (D-007)
- A `dev` preset of 20k clients in `synthetic/` for daily work on the skeleton: built (M2.1,
  2026-10-25), written to `data/01_raw/synthetic_dev/` — D-091, `test_harness.md`
- Lossless non-pickle model formats for what is promoted, researched per model family before it is
  offered (D-051): `lgbm`, `xgboost` and `catboost` all verified in M2 (D-037; spike 2, due
  11-16) — `training.md`
- Retraining in production: research (M4) — OD-27, `lifecycle.md`
- The learn sessions and the first change request: [Work streams](#work-streams-beside-the-critical-path)

## Phase 3 wishlist
Long-term targets, not planned into Phase 2 (D-072). Each item names where it came from.
- Predefined modelling path tuned with Optuna, with the trade-off chart (D-020; the chart weighs
  train and test metrics, never validation, D-083).
- An own client-grouped CV loop around the tuner (D-106, option D of the question on validation
  inside training).
- Advanced sampling (D-117): outcome-stratified client sampling with weights and the
  weight-aware statistics it needs; downsampling low-value rows with weights that calibrate back
  (the EDS rates it highest; closest known method: local case-control sampling, Fithian and
  Hastie, 2014); smart downsampling as a framework asset, researched in a literature round; the
  comparison of every option against the synthetic oracle, with no sampling as the reference.
- The cross-fitted categorical's SE from the data: check `CROSS_FIT_SE_INFLATION = 1.5` against
  more level counts, sizes and panel shapes, and possibly replace it with a permutation null
  (the level labels permuted within each client fold about 50 times, the SE the larger of the
  Hanley–McNeil SE and the permutations' spread), which adapts to each feature at about 50
  encodings per categorical (`eda.md` → Level encoding; the EDS, 2026-11-04).
- Sources with missing periods handled automatically. Phase 2 expects full coverage: the spine
  must have every period from the window's first to the validation period and the target
  source every period to the validation period + w, else the run is refused naming the
  missing periods (`dataset.md` → Time model). How a gap is filled or carried is designed then
  (EDS, 2026-10-29).
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
  after a model is trained and saved; checks that the necessary inputs exist).
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
- Further panel tasks in D-081's order: multiclass, time-to-event. They keep the concordance's
  scale and thresholds: ordinal multiclass uses the formula unchanged, nominal multiclass the
  mean one-vs-rest concordance, time-to-event Harrell's C (the same pair counting over the
  pairs censoring leaves comparable). A series task defines its own ranking statistic (D-050).
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
The CDS leaves the design to the EDS and LDS (D-073), so a row is promoted to short-term when its
milestone comes up, and added to [Chief DS topics](#chief-ds-topics) when it changes scope or
direction or needs people outside the team.

### Short-term

| ID | Question | Current leaning / proposal | Decided by / forum | Detail |
|---|---|---|---|---|
| OD-06 | **Lifecycle:** folder layout per entity × domain: are storage permissions actually separate per entity, and do the registered and production roots need their own structure? The sandpit data root is settled (D-136: the root is the entity's area, then use case, then layer; `roots.registered` and `roots.production` follow the same shape in M2.4) | Production paths are separate from the sandpit (D-033, D-051), and permissions are the platform's, not the framework's (D-079); the question is only how the framework lays out its own outputs per entity × domain. Ours to decide (D-073) | EDS + LDS; permission facts from the platform / MLOps team | `components/lifecycle.md` |
| OD-08 | **Lifecycle:** MLflow for the registry and experiment tracking in Phase 2: is it available inside the bank? | The shape is settled (D-111): M2.4's own records map one-to-one onto MLflow; MLflow goes in with the other integrations in M4 once confirmed; `production.json` stays the pointer through major version 1, MLflow a store beside the own records. Its default flavors pickle, which is fine in the sandpit but not for what is promoted (D-051). Confirm availability at the platform learn session (by 11-06). MLflow fits the registry and experiment tracking better than monitoring (OD-13) | EDS + LDS, with the platform / MLOps team (D-079, OD-23) | `components/lifecycle.md` |
| OD-12 | **Reporting:** the mandatory "core" views per task of the Evaluation report | The structure is shared by the three reports (summary page + core + extended, D-036). EDA's and Feature Checks' core views are settled with Stage 2's design (2026-11-02; `eda.md`, `feature_checks.md`, D-135); Evaluation's are needed when it is built (M2.3); proposal for binary in `evaluation.md` → Open questions | EDS + LDS | `components/evaluation.md` |
| OD-18 | **Inference:** separate manifests from score files? | The format part is settled (D-016): the framework writes its own traceable scores table, the master layer, and consumable tables are built outside it. Still open: whether manifests sit beside or inside the score files; leaning: separate them, since manifests beside the score files break a Hive table over the scores (`inference.md`), with the layout from the LDS; designed with Inference (round 1a) | EDS + LDS | `components/inference.md` |
| OD-23 | **Lifecycle:** who builds the registry and deployment, and at what point they join the project | The CDS routes downstream questions to the platform / MLOps team (D-079); to agree with that team whether they build these or advise. Until then, register / promote / deploy are thin but real (D-033). The original plan had a part-time ML engineering lane for registration, the deployment path and drift alerting | EDS + LDS, with the platform / MLOps team | `components/lifecycle.md` |

### Medium-term

| ID | Question | Current leaning / proposal | Decided by / forum | Detail |
|---|---|---|---|---|
| OD-02 | **Distribution:** where a use case lives (repo per use case / per domain / other) and how users get the guided notebooks | CDS hint: one repo per entity × domain would be good but may be idealistic; as the framework, or a use case in it, expands it may branch off, so likely something between that and today's repo per use case. Leaning: one repo per entity × domain by default, and a use case branches into its own repo when it grows. Either way a repo may hold several similar use cases, each a config and its audit log (D-006). That needs standardised upstream data per entity and domain, which the feature store may provide (OD-26). Not one shared repo with code folders; the notebooks would come with the package in the base image (leaning, unverified) and users copy them. Doesn't block M2: the walking skeleton's use cases live in this repo's `conf/base/` | EDS + LDS | `components/run_modes.md` |
| OD-04 | **Distribution:** release mechanics: zip → internal repo → internal CI → Nexus → base image. Who publishes; what must pass first (CI/Sonar); how often images are cut | Channel settled: the base image through Nexus (D-024). A use case can probably take a newer framework version within its image's year (D-047, soft); compatibility is about outputs (D-007). The first change request is release 1.0, the framework only (D-021) | EDS, with the platform / MLOps team (M5) | `components/run_modes.md` |
| OD-13 | **Monitoring:** tooling: what monitoring uses, what is shown and where dashboards live | Tooling and dashboards are the platform / MLOps team's (D-079). MLflow suits the registry and experiment tracking (OD-08), not tracking decay over time. The data observability part is settled: that framework watches a production model's source tables, pointed to it at deploy, and doesn't shape the monitoring tables (D-021, D-040; the EDS, 2026-10-30) | EDS, with the platform / MLOps team | `components/monitoring.md` |
| OD-14 | **Lifecycle:** model inventory design | In scope, possibly richer than registry tables | EDS + LDS | `components/lifecycle.md` |
| OD-17 | **Dataset:** the window ablation design | Sampling is settled for Phase 2 (D-117: only when the config declares it, for a rare target or the row budget; uniform negative downsampling or a random sample of clients; no sample weights); advanced sampling is on the Phase 3 wishlist. Ablation, now a nice to have at release 1.0: paired bootstrap on one validation month, plus a row-count-matched control and per-month models; the choice weighs train and test (D-083) | EDS | `components/dataset.md` |
| OD-19 | **Features:** whether the Phase 3 LLM loop needs a feature-aggregation spec | Phase 2: features come from upstream, including the feature store (OD-26); only the spec's shape is kept in mind. If the feature store holds feature definitions, the loop may write those instead of a framework spec. The aggregation list agreed as a starting point for such a spec: sum / mean / max / min / std over windows, count of non-zero months, months since last non-zero, ratios between windows, and trend | EDS | Phase 3; no owner doc until then |
| OD-20 | **Docs:** documentation approach for users (generated docs, pages, wiki…), and the glossary's reach | Parked: too early. The framework's own docs are written with Claude in our current documentation structure (D-021) | EDS + LDS | — |
| OD-26 | **Upstream:** feature store integration (D-021): how a use case reads from the feature store, alone or with other sources (point-in-time reads; how its entities and features map onto the data definition and its hash); how the work splits with the feature store team | Leaning (the EDS, 2026-10-30; an update may follow): little build outside the bank. Inside the bank the EDS adds an example notebook that loads features from the feature store, applies the format fixes and saves them as a dataset, which the environment file maps like any other source (a path or a table) and Target Factory joins to the others; the adapter then needs no `feature_store` format (refused at load today), and the outside-bank example's merge runs on a synthetic stand-in ([merges and mistake tests](components/test_harness.md#merges-and-mistake-tests)). Still to settle: (i) point in time: one row per unit per period holding the values as of that period, never today's values stamped on history (`CLAUDE.md` §4.1); (ii) production: inference reads the sources for every scored period, so the extract is refreshed by a job, not a notebook (`CLAUDE.md` §3), with the same fixes as for training (§4.9); leaning: the feature store team or an upstream job writes it as a table, read like any other, else a small framework function does the read and the fixes for both the notebook and inference; the notebook's instructions require one row per unit per period, as of that period; (iii) a saved period never changes afterwards, since the hashes see logical names, not contents (§4.10, D-079); (iv) which fixes the framework makes: the id cast, period tags and per-source key names (D-129, 2026-10-30); clashing columns are renamed in the extract. Limited to Stage 1 in Phase 2; feedback into the feature store stays on the Phase 3 wishlist (D-021) | EDS after the work stream, with the feature store team | `components/environment.md` |
| OD-27 | **Lifecycle:** retraining in production. The CDS prefers models retrained in production rather than moved there | Shape settled (D-052): the bundle carries the recipe (`recipe_hash`); production refits it on the same window and clients, only the inference month moving, and passes a check against its evaluated parent (label-free agreement on the inference month, its own test-split AUC and calibration per window month, rows and positive events per month against the parent's EDA artifact, tolerances declared beforehand, never the validation month) before it scores. Retraining is the Phase 2 default, and deploying the fitted model without a retrain is also allowed (D-033). Still open, with the platform / MLOps team in M4: whether production has the data and compute to train; determinism; what "deployed" then records | EDS + LDS, with the platform / MLOps team (M4) | `components/lifecycle.md` |
| OD-28 | **Inference:** a rank score beside the calibrated probability? Scores are compared across products downstream (D-049); in the long run a rank or normalised score may serve that comparison better than probabilities alone | Not before release 1.0; probabilities with correct calibration until then | EDS + LDS | `components/inference.md` |

## Chief DS topics

The CDS leaves the design to the EDS and LDS (D-073); the design meeting of 2026-10-15 is recorded
in D-021, D-023, D-024, D-031, D-051, D-073, D-079. A topic is raised with him when it changes scope or direction, needs people outside
the team, or he asked to see it. Results are shown at check-ins.

| Topic | Raise when | Related |
|---|---|---|
| Feature store integration: a use case on the feature store, on other sources, and on both | The work stream has a design | D-021, OD-26 |
| Data observability: reduced to pointing a production model's source tables at it at deploy, since it checks tables and consumes no model outputs (information item) | Next check-in | D-021 |
| Retraining in production; models without pickle | Research results per model family | OD-27, D-051 |
| The Phase 2 plan, agreed 2026-11-10: the December pre-release and release 1.0 keep their dates; M2.3 – M3 moved by a week (information item) | Next check-in | D-022, [Phase 2 plan](#phase-2-plan) |
| Automation levels (two in Phase 2), and how a use case moves between them | The config spine is built (M2.1); the mapping is D-132 | D-023, D-132 |
| Config format: YAML, and the decision audit log, both decided (information items, with the reasoning) | Next check-in | D-043, D-125 |
| Who builds and runs the downstream (platform / MLOps team) | If that team can't take it on | D-079, OD-23 |
| LLM-assisted modelling (he is keen) | Planning Phase 3 | D-021, `components/llm_assist.md` |
