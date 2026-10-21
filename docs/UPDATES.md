# Updates — state and major changes

**Read this first each session.** Keep it short. The status table is the source of truth for "where
are we"; the log records only major changes (one line each, newest first). Plan, milestones and open
decisions live in `docs/roadmap.md`. Reading order: `docs/README.md`. The day-to-day sync page for
the Lead DS and the verbose log: `worknotes/`.

## Status

Status values: `legacy-only` (exists only in legacy) · `designing` · `stub` (interface only) ·
`built` · `tested` · `blocked`. Target depth per component: `docs/roadmap.md` (OD-01).

| Item | Status | Notes |
|---|---|---|
| Repo bootstrap (docs, skills, agents, requirements, package skeleton) | built | |
| Design baseline (docs rebuilt after three review rounds + Lead DS notes) | built | 2026-10-12; milestone M0 |
| Environment adapter (Spark session, compat shim, transport, paths, sources) | built | Partial: compat shim + local Spark session (M1 step 0, D-057); transport, paths, sources in M2. Traps T1–T5, T18 |
| Config spine (single file, profiles, decision, entities, data-definition hash, migrations) | designing | `components/config.md`. Settled 2026-10-20: YAML (D-086), two automation levels (D-087), identities with a worked example (D-088), the shared-table rule (D-089), extension code in use-case repos (D-090). Still open before M2.1: the audit log's Phase 2 scope (OD-10), the level mapping (OD-25) |
| Synthetic data (`synthetic/`, ~100k × 24 months) + local-Spark harness | tested | M1: steps 0–7 built (2026-10-17); the SDS's review round 1 applied (2026-10-19): role folders, slimmer `truth.json`, two new traps, exit rates, top-down spec with a code map. Feature mart (147 columns), traps on two products, oracle and `truth.json`, CLI, source mapping; every independent check row passes at 100k; approved by the SDS (2026-10-19), with the LDS for review (`synthetic/REVIEW.md`). D-056, D-064–D-070 |
| Target Factory (targets only, optional) | legacy-only | Renamed from Data Creation (D-029) |
| Dataset: observation window, client-grouped split, OOT validation, sampling | designing | Big-ticket item (D-030); sampling choice OD-17 |
| EDA (worth running first; low-prevalence aware) | legacy-only | Major rethink |
| Feature Checks (correctness and quality only) | legacy-only | Major rethink; selection moved to Training (D-028) |
| Feature ledger | designing | Sketch awaiting review (OD-11) |
| Training (FLAML path; predefined + Optuna in Phase 3; selection, encoding, calibration) | legacy-only | FLAML only in Phase 2, predefined + Optuna in Phase 3 (D-080); no pickle, lossless formats per family (D-078); M2 offers `lgbm`, `xgboost` and `catboost` (D-093); own encoding before FLAML, the calibration chain and `model_hash` over parts (D-094) |
| Evaluation (stratified metrics, compatibility table, comparison) | legacy-only | Core views OD-12 |
| Reporting (self-contained HTML, plotly, chart rules) + model card | legacy-only | D-036 |
| Lifecycle: register / promote / deploy, registry tables, inventory | designing | Evolves as built (D-073); "registered" settled (D-095); `recipe_hash` and the refit as production retraining (D-096); OD-06–OD-08, OD-14; retraining in production OD-27; who builds it OD-23, with the platform / MLOps team (D-079) |
| Inference (batch-scoped, manifest, reinference) | legacy-only | Output columns / layout OD-18 |
| Monitoring (operational + drift deep; performance + impact thin) | designing | Renamed from Tracking (D-040); the data observability integration OD-13; tooling and dashboards are the platform / MLOps team's (D-079); downstream design still largely open |
| Feature store integration (upstream) | designing | First release (D-075); a work stream to learn the feature store comes first (OD-26) |
| Data observability integration (monitoring) | designing | First release (D-075); a work stream to learn the framework comes first (OD-13) |
| CLI / Python API / guided notebooks / experiment sweeps | designing | D-024, D-039 |
| Second task type: regression | designing | D-080; its per-task spec is designed in M1 (D-060, D-050) |
| LLM-assisted modelling branch | designing | Phase 3 (D-075) |
| Full test coverage + CI/Sonar readiness | designing | Before migration (M5) |

## Open questions

All open decisions are tracked as OD-nn rows in [`docs/roadmap.md`](roadmap.md#open-decisions),
together with the topics to raise with the Chief DS.

## Log (major changes only, newest first)

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
  table (`worknotes/holistic_review.md`, `holistic_review_questions.md`, `timeline_proposal.md`).
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
