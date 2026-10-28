# Updates — state and major changes

**Read this first each session.** Keep it short. The status table is the source of truth for "where
are we"; the log records only major changes (one line each, newest first). Plan, milestones and open
decisions live in `docs/roadmap.md`. Reading order: `docs/README.md`. The day-to-day sync page for
the Lead DS and the verbose log: `worknotes/`.

## Status

Status values: `legacy-only` (exists only in legacy) · `designing` · `stub` (interface only) ·
`built` · `tested` · `blocked`. Target depth per component: `worknotes/timeline_proposal.md` until agreed (OD-01, D-022).

| Item | Status | Notes |
|---|---|---|
| Repo bootstrap (docs, skills, agents, requirements, package skeleton) | built | |
| Design baseline (docs rebuilt after three review rounds + Lead DS notes) | built | 2026-10-12; milestone M0 |
| Environment adapter (Spark session, compat shim, transport, paths, sources) | built (partial) | Stage 1 (2026-10-26): the environment file, `load_environment`, `get_spark_session`, sources per entity, local paths; the `hdfs dfs` transport and the tier roots in M2.4. Traps T1–T5, T18 |
| Config spine (single file, automation levels, decision, entities, data-definition hash, migrations) | built | `components/config.md`. Settled 2026-10-20: YAML (D-043), two automation levels in the `automation_level` field (D-023), identities with a worked example (D-088), the shared-table rule (D-007), extension code in use-case repos (D-006); the decision audit log (D-125, 2026-10-22). Stage 1 (D-129–D-133) built 2026-10-26: the schema and template, levels, migrations machinery, hashes, the audit log with `decide`; reviewed by the SDS on 10-26 (Q388–Q390 applied). A feature decision checks its names against the saved model input's candidates (10-27) |
| Synthetic data (`synthetic/`, ~100k × 24 months) + local-Spark harness | tested | M1: steps 0–7 built (2026-10-17); the SDS's review round 1 applied (2026-10-19): role folders, slimmer `truth.json`, two new traps, exit rates, top-down spec with a code map. Feature mart (157 columns from 0.5.0), traps on two products, oracle and `truth.json`, CLI, source mapping; every independent check row passes at 100k; approved by the SDS (2026-10-19); reviewed and accepted by the LDS (2026-10-21). Its to-dos (noise and very-low-fill columns, named like the traps) became 0.5.0's ten trap columns (2026-10-25, Stage 1; `unstable` waits for M4); the `dev` (20k) and canonical datasets and the notebook are at 0.5.0, all 1,309 check rows passing at 100k; the package goes into the bank as code, never as data (D-041). D-003, D-029, D-041, D-064 |
| Target Factory (targets only, optional) | built (thin) | Stage 1 major step 2 (2026-10-26; reworked after the SDS's review on 10-27, for the second review with the dataset): `flag_goes_up` and `forward_sum` through the per-task spec (the rule compares t with the forward months; nulls under SQL semantics, `null_as`), the keyed source reader (months at their last day, D-129), the target-column and month-coverage checks, `run_target_factory`; tested against the oracle on the `unit` preset. `components/target_factory.md` |
| Dataset: observation window, client-grouped split, OOT validation, sampling | built (thin) | Stage 1 major step 3 (2026-10-27, for the SDS's review): the panel (sources joined, eligibility in two kinds, the candidates), the client split and the two sampling options, the contract checks with the null callout, the frames with the collect printout, the model input saved and read back with its hash checks (D-131, D-133). Advanced sampling in Phase 3 (D-117); window ablation OD-17. `components/dataset.md` |
| EDA (worth running first; low-prevalence aware) | designing | Major rethink; EDA and Feature Checks use all clients, the client split comes after (D-030) |
| Feature Checks (correctness and quality only) | designing | Major rethink; selection moved to Training (D-028) |
| Feature ledger | designing | Sketch awaiting review (OD-11) |
| Training (FLAML path; predefined + Optuna in Phase 3; selection, encoding, calibration) | designing | FLAML only in Phase 2, predefined + Optuna in Phase 3 (D-020); no pickle for what is promoted, lossless formats per family (D-051); M2 builds `lgbm`, `xgboost` and `catboost` with their round trips (D-037); own encoding before FLAML, the calibration chain and `model_hash` over parts (D-094) |
| Evaluation (stratified metrics, compatibility table, comparison) | designing | Core views OD-12 |
| Reporting (self-contained HTML, plotly, chart rules) + model card | designing | Reports from EDA, Feature Checks, Evaluation and Monitoring, plus the model card (D-036) |
| Lifecycle: register / promote / deploy, registry tables, inventory | designing | Evolves as built (D-073); "registered" settled (D-033); `recipe_hash`, and production retraining on the same data definition as the default deploy path (D-052); MLflow in Phase 2 is the goal (OD-08); OD-06, OD-14; retraining in production OD-27; who builds it OD-23, with the platform / MLOps team (D-079) |
| Inference (batch-scoped, manifest, reinference) | designing | Output ends at the framework's own scores table, the master layer; consumable tables are built outside (D-016); calibration a release requirement (D-049); path layout OD-18 |
| Monitoring (four layers: frame deep, content light) | designing | Renamed from Tracking; frame vs content (D-040); the data observability integration OD-13; tooling and dashboards are the platform / MLOps team's (D-079); downstream design still largely open |
| Feature store integration (upstream) | designing | First release, limited to Stage 1 (M2.1 Foundation) in Phase 2 (D-021); a work stream to learn the feature store comes first (OD-26) |
| Data observability integration (monitoring) | designing | First release (D-021); a work stream to learn the framework comes first (OD-13) |
| CLI / Python API / guided notebooks / experiment sweeps | built (thin) | Stage 1 (2026-10-27): `run` with its one stage, the CLI `run` and `decide`, the guided notebook `01_target_factory`; experiment sweeps later. D-024, D-039 |
| Second task type: regression | designing | D-020; its per-task spec (shapes only) was planned for M1 and is still to design, before EDA and Feature Checks are built (D-050) |
| LLM-assisted modelling branch | designing | Phase 3 (D-017) |
| Full test coverage + CI/Sonar readiness | designing | By release 1.0 (M5b, D-014) |

## Open questions

All open decisions are tracked as OD-nn rows in [`docs/roadmap.md`](roadmap.md#open-decisions),
together with the topics to raise with the Chief DS.

## Log (major changes only, newest first)

- 2026-10-27 — Stage 1 built end to end (version 0.2.0), for the SDS's review of major steps 2
  and 3 together: the dataset (the panel from the joined sources with eligibility in two kinds,
  the client split and declared sampling, the contract checks with the null callout, the frames
  with the collect printout, the model input saved and read back, D-131, D-133), `run` with the
  CLI `run`, and the guided notebook `01_target_factory`. Two traps found and ruled (T20, T21).
- 2026-10-26 — Stage 1, major step 2 built and reviewed: Target Factory (the flag and forward-sum
  rules, the target summary), one keyed reader for every source that holds months at their last
  day (D-129, from the SDS's review of step 1), and the synthetic holdings on last-day months
  (0.5.2, both datasets regenerated). Four reviewers found label risks (a holder at t, nulls in
  the window, label rates after the window, bad column types, time-zone shifts), all fixed.
  Also from the SDS's review: more settings loggable (D-125), D-088's pre-release carve-out.
- 2026-10-26 — Stage 1, major step 1 built: the config spine (schema, template, levels,
  migrations, hashes, the decision audit log, `decide`) and the environment adapter (the
  environment file, `get_spark_session`, sources per entity, local paths), reviewed by three
  reviewers and fixed; the synthetic package writes a slim `holdings` table (0.5.1). Under the
  SDS's review; the plan is `worknotes/m2_1_foundation/plan.md`.
- 2026-10-26 — Stage 1 (M2.1 Foundation) design settled and the build started: the config layout,
  the environment file, the model input, the automation-level mapping (OD-25 closed) and the collect
  printout (D-129–D-133); the plan in three major steps is `worknotes/m2_1_foundation/plan.md`.
- 2026-10-25 — Synthetic data 0.5.0: the LDS's to-dos built as ten trap columns, on in every
  preset (a random flag, a 300-level code, two constants, a redundant tenure column, two low-fill
  columns, a leak through missingness, card twins of the shifted and process-leak kinds), with
  every existing column byte-identical at the same seed; a code rule keeps `_trap_` names out of
  the framework; the `unstable` kind waits for M4 (D-064). A 20k `dev` preset; the datasets and
  the notebook regenerated, every check row passing at 100k. The package goes into the bank as
  code, never as data: tests generate their data from a seed (D-041, closes OD-29).
- 2026-10-23 — Second round of answers closes the inconsistency questions: EDA and Feature Checks
  use all clients and the client split comes after them (D-030, `CLAUDE.md` §4.4 changed); a Phase 2
  production retrain keeps the window and clients, only the inference month moves, and passes a
  check against its parent (D-052); no sign-off log in Phase 2 (D-033); validation shown everywhere,
  people trusted (D-083); register always writes the plain-data model (D-051); MLflow's shape
  settled, in M4 once confirmed (D-111). Two Phase 3 wishlist questions added. The review's one
  question (Q374) was answered on 10-25: Phase 2 relies on the per-family check of the plain-data
  model, a per-model check is a Phase 3 question (D-051); the questions file is deleted.
- 2026-10-23 — The SDS answered the inconsistency questions; the rest took their defaults. Main
  changes: production retraining on the same data definition is the default deploy path, not
  retraining is allowed (D-033, D-052); the sandpit may hold any format, pickle only matters for the
  move to production (D-051); all three FLAML families in M2 (D-037); one sign-off gate after
  training (D-031); sampling only when the config declares it (D-117); no sample weights in Phase 2;
  MLflow in Phase 2 is the goal (D-111, OD-08); the validation month moves into the config (D-088);
  `automation_level` from M2.1 (D-023); "resolved config" replaces "frozen config" (D-125); docs
  stay live (D-072); `CLAUDE.md` §4.12 tightened after the ML-correctness review. Twelve questions
  remained (five restated, seven new: Q342–Q348).
- 2026-10-22 — Decision log compacted from 128 to 58 rows, in a high-impact and a low-impact table;
  a superseding decision now replaces the original row in place (D-072 (g)); about 1,000 references
  remapped across the current-state docs. **D-numbers in the entries below this line predate the
  compaction**; the old → new mapping is in `worknotes/log.md` (entry of 2026-10-22). The
  inconsistency sweep that followed was answered on 10-23 and 10-25 (its file deleted); the LDS's reading
  list of the twenty most impactful decisions is `worknotes/decisions_LDS_review.md`.
- 2026-10-22 — The planning thread is closed: the Phase 2 plan is the working assumption (D-124;
  OD-01 open until the LDS's review and stakeholder buy-in); the decision audit log is designed into `config.md`
  (D-125; OD-10 closed); Phase 2 retraining keeps clients and window (D-126); the Public API
  list (D-127); product and activity from the use case's name (D-128).
  `worknotes/holistic_review.md` deleted; the questions file closed.
- 2026-10-22 — Fourth round of answers: D-111–D-123 (Phase 2 registry records; monitoring's frame
  deep, content light; the first change request is release 1.0, framework only; simple sampling,
  with advanced sampling and recency weighting moved to Phase 3; FLAML gets the client groups; a
  Phase 3 wishlist in the roadmap). OD-07 closed, OD-17 narrowed to the window ablation. Timeline
  adjusted for the lost week of 11-30 and the year-end slowdown.
- 2026-10-21 — Third round of answers (the SDS and the LDS): D-103–D-109 (scores end at the
  master layer; calibration a release requirement; reports self-contained; the train/test client
  split as Phase 2's validation inside training; compatibility is about outputs, `CLAUDE.md` §2;
  upstream data facts aren't ours; the plan is milestones per stage, December a pre-release).
  Timeline reshaped into two build rounds with a run-through after each (pre-release by 12-18,
  release 1.0 by 02-19), awaiting the LDS. Synthetic data accepted by the LDS (M1). OD-28 opened.
- 2026-10-21 — The SDS's second answers: D-098–D-102 (test metrics per month first and named
  denominators; reproducible runs on a trial budget; the M2 engineering shape; pickle only for
  saved and moved artifacts; doc upkeep). One doc-hygiene pass across `docs/`, `CLAUDE.md`,
  `conf/base/` and `notebooks/README.md` fixed the review's inconsistencies and glossary gaps.
  Questions round 3 in `worknotes/holistic_review_questions.md`.
- 2026-10-20 — The SDS answered the holistic review: D-082–D-097 (positive events; choices weigh
  train and test only and `CLAUDE.md` §4.4 is reworded; working rules round 3; the speed claim;
  YAML; two automation levels; identities; the shared-table rule; extension code in use-case
  repos; M2 defaults; the sign-off view; M2 never lesser than the crunch; training under FLAML;
  "registered"; `recipe_hash`; the plan shape with release 1.0 as the definition of done). OD-05,
  OD-09, OD-22, OD-24 closed. Questions round 2 in `worknotes/holistic_review_questions.md`.
- 2026-10-20 — Holistic review of the whole design before the planning session with the LDS:
  verdict, ranked risks, Q217–Q265 with defaults, and a timeline proposal with the OD-01 depth
  table (`worknotes/holistic_review.md`, deleted 2026-10-22; `holistic_review_questions.md`,
  `timeline_proposal.md`).
  Dates and depth go to `docs/roadmap.md` once agreed.
- 2026-10-20 — Phase 2 modelling scope settled: binary and regression, FLAML only; the predefined
  path + Optuna moves to Phase 3 (D-080). Task order after the first release (D-081).
- 2026-10-20 — Chief DS design meeting (2026-10-15) outcomes integrated, D-073–D-079: the CDS
  leaves the design to the SDS and LDS; the package ships in the base image; the first release
  adds feature store and data observability integration (no LLM until Phase 3); a person signs off every feature; profiles become
  automation levels (soft); no pickle; downstream operations go to the platform / MLOps team.
  Research questions opened: OD-24–OD-27, OD-10 widened. Meeting folder removed.
- 2026-10-19 — Synthetic data generator approved by the SDS and passed to the LDS for review
  (`synthetic/REVIEW.md`); M1 still needs OD-15.
- 2026-10-19 — Synthetic data, the SDS's review round 1 applied (D-070): code in role folders
  (`spec/`, `mechanisms/`, `truth/`, `checks/`; 46 modules → 32), relevance rankings and the
  `separation` knob cut, `truth.json` 234 → 55 KB, a moderate leak and a shifted column added,
  exits 0.7–1.1% a month, the starting book's tenure from the turnover's steady state;
  `test_harness.md` rewritten top-down with a code map, and the component-doc template with it.
  Work runs in parallel with subagents by default (D-071).
- 2026-10-17 — Synthetic data generator built (steps 3–7 in one go, stages A–F with independent
  checks and reviews); canonical dataset in `data/01_raw/`; review guide `synthetic/REVIEW.md`.
- 2026-10-16 — Code size rules relaxed: functions ≤ ~50 lines, steps ≤ ~300–400 changed lines,
  larger agreed builds ship with a review guide (D-067). Synthetic data spec completed (D-068,
  D-069); steps 3–7 built in one go.
- 2026-10-13 — Holistic review of the baseline, decisions D-047–D-055:
  - each use case pins its framework version (OD-03 settled);
  - `CLAUDE.md` §4.4 (label checks on train-split clients) and §4.7 (prior shift from the weighted
    rate, plus a general calibration step) reworded;
  - per-task spec; versioned model bundle; optional refit; sweeps that pick are labelled optimistic;
    drift reference and monitoring labels; definition-of-done wording;
  - OD-22 opened (trade-off chart on test vs CV).
- 2026-10-12 — Worknotes committed and shared with the Lead DS (sync page + log + handovers, D-044);
  `docs/README.md` reading guide with the stage → component map (D-045).
- 2026-10-12 — Design baseline:
  - CLAUDE.md, project.md and architecture rebuilt from three review rounds and the Lead DS notes;
    new roadmap, glossary, dataset and feature-ledger docs;
  - Data Creation → Target Factory, Tracking → Monitoring; decisions D-020–D-043;
  - doc rules (owner docs, triggers, creation rules) in CLAUDE.md §8;
  - `worknotes/` with `/brief`, `/handover` and `/resume`; `holistic-review` skill.
- 2026-10-05 — Vendored and adapted `silent-failure-hunter`, `brainstorming`, `systematic-debugging`,
  `verification-before-completion`, `claude-md-improver` + `/revise-claude-md`; enabled the
  `pyright-lsp` plugin (D-019).
- 2026-09-30 — Repo bootstrapped for Phase 2: `CLAUDE.md`, docs tree, component docs, skills,
  subagents, requirements pinned to bank parity, empty `core_modelling` package, crunch code moved to
  `legacy/propensity_crunch/`.
