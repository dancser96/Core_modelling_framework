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
| Config spine (single file, profiles, decision, entities, data-definition hash, migrations) | designing | `components/config.md` |
| Synthetic data (`synthetic/`, ~100k × 24 months) + local-Spark harness | designing | M1 in progress: spec settled 2026-10-14 (D-056); steps 0–2 (Spark harness, population, holdings and states) done (D-065, D-066); steps 3–7 to be built in one go after one question round, with one review at the end; replaces the stub-based smoke test (T15) |
| Target Factory (targets only, optional) | legacy-only | Renamed from Data Creation (D-029) |
| Dataset: observation window, client-grouped split, OOT validation, sampling | designing | Big-ticket item (D-030); sampling choice OD-17 |
| EDA (worth running first; low-prevalence aware) | legacy-only | Major rethink |
| Feature Checks (correctness and quality only) | legacy-only | Major rethink; selection moved to Training (D-028) |
| Feature ledger | designing | Sketch awaiting review (OD-11) |
| Training (AutoML + predefined/Optuna paths, selection, encoding, calibration) | legacy-only | D-037; FLAML only under review (OD-15) |
| Evaluation (stratified metrics, compatibility table, comparison) | legacy-only | Core views OD-12 |
| Reporting (self-contained HTML, plotly, chart rules) + model card | legacy-only | D-036 |
| Lifecycle: register / promote / deploy, registry tables, inventory | designing | OD-06–OD-09, OD-14; needs Chief DS + MLE/MLOps input, who builds it OD-23 |
| Inference (batch-scoped, manifest, reinference) | legacy-only | Output columns / layout OD-18 |
| Monitoring (operational + drift deep; performance + impact thin) | designing | Renamed from Tracking (D-040); tooling OD-13; downstream design still largely open |
| CLI / Python API / guided notebooks / experiment sweeps | designing | D-024, D-039 |
| Second task type | designing | Whether and which: OD-15 (Chief DS), chosen by the end of M1; per-task spec D-050 |
| LLM-assisted modelling branch | designing | After internalisation |
| Full test coverage + CI/Sonar readiness | designing | Before migration (M5) |

## Open questions

All open decisions are tracked as OD-nn rows in [`docs/roadmap.md`](roadmap.md#open-decisions),
together with the topics for the Chief DS design meeting (week of 2026-10-12).

## Log (major changes only, newest first)

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
