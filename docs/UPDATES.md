# Updates — state and major changes

**Read this first each session.** Keep it short. The status table is the source of truth for
"where are we"; the log records only major changes (one line each, newest first).

## Status

Status values: `legacy-only` (exists only in legacy) · `designing` · `stub` (interface only) ·
`built` · `tested` · `blocked`.

| Item | Status | Notes |
|---|---|---|
| Repo bootstrap (docs, skills, agents, requirements, package skeleton) | built | This kit |
| Environment adapter (Spark session, compat shim, transport, paths) | legacy-only | Traps T1–T5 |
| Config spine (`schema_version`, `task`, base/local merge, stepwise sections, migrations) | legacy-only | Two feature views come from legacy |
| Synthetic panel + local-Spark e2e test harness | designing | Replaces stub-based smoke test (T15) |
| Data Creation | legacy-only | Light-touch; upstream integration TBD |
| EDA (standalone, analyst-grade reports) | legacy-only | Major rethink; more input pending from the user |
| Feature Checks (standalone, stepwise traceable) | legacy-only | Major rethink; more input pending from the user |
| Training (engine wrapper, sampling, calibration) | legacy-only | Runtime and positive-rate handling |
| Evaluation (task-dispatched metrics, slices, baselines, explainability) | legacy-only | Add segment-stratified metrics |
| Reporting (shared report writer, model card) | legacy-only | |
| Lifecycle: promotion / registry / deployment | designing | Separate from inference |
| Inference (batch-scoped, manifest, reinference) | legacy-only | |
| Tracking (baselines, impact, drift) | designing | |
| CLI / Python API run modes | designing | |
| LLM-assisted modelling branch | designing | After internalisation |
| Full test coverage + CI/Sonar readiness | designing | Before migration |

## Open questions

- EDA and Feature Checks detailed requirements (the user will provide more input).
- Bank-side folder layout for registered/production tiers (evolving).
- Distribution model: service vs forkable template.

## Log (major changes only, newest first)

- 2026-09-30 — Repo bootstrapped for Phase 2: `CLAUDE.md`, docs tree, component docs, skills,
  subagents, requirements pinned to bank parity, empty `core_modelling` package, crunch code moved to
  `legacy/propensity_crunch/`.
