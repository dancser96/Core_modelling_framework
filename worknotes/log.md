# Log
Verbose trail behind `worknotes/sync.md`, newest first. Template: `worknotes/README.md`.

### 2026-10-13 — Holistic review outcomes recorded
- What:
  - decisions D-047 (framework pinned per use case; settles OD-03), D-048 (§4.4: label checks on
    train-split clients, label-free checks never on the validation month), D-049 (§4.7: prior
    shift from the weighted rate + a general calibration step), D-050 (per-task spec; OD-15 by end
    of M1), D-051 (versioned model bundle), D-052 (optional refit), D-053 (sweeps that pick are
    labelled optimistic; selection month with the LLM branch), D-054 (drift reference + labels for
    monitoring), D-055 (definition-of-done production step, soft);
  - status notes on D-020, D-021, D-030, D-037;
  - roadmap: OD-03 deleted, OD-22 added (trade-off chart: test metric vs CV), OD-10/11/15/18
    extended, backlog and Chief DS topics (b), (e) updated;
  - `CLAUDE.md` §2 (pinning, bundle + drift reference versioned), §3 (per-task spec), §4.4, §4.7,
    §4.10 (source months assumed immutable);
  - compat-guardian and ml-correctness-auditor aligned with the new rules;
  - component docs: config (identity issues as open questions), dataset (calibration wording,
    refit frames, owns contract checks and the ablation design), training (calibration, bundle,
    drift reference, refit, OD-22), target factory (labels for scored months), EDA and Feature
    Checks (train-split clients, comparison months), ledger (two keying issues), evaluation
    (optional validation on test clients), reporting, lifecycle, inference (pinned version),
    monitoring, run modes (lifecycle commands, entity selector), LLM assist (selection month gate);
  - architecture, project, glossary (gap months, refit, per-task spec, sweep/variant, model bundle,
    drift reference, framework pin), environment (two unverified items), tests README, UPDATES;
  - sync page rewritten with a summary of the whole uncommitted baseline.
- Why: the builder's answers to the holistic review (Q56–Q75).
- Deviation to check: EDA's population base rate per month now stops at the window's end (not
  "before the validation month"), because the gap months' target windows overlap the validation
  month's.
- Decisions / open decisions: D-047–D-055; OD-03 (settled), OD-10, OD-11, OD-15, OD-18, OD-22.
- Still open: OD-22 with the Lead DS; D-055 at the Chief DS meeting (e); hashes, ledger keying and
  scores format to specify later.

### 2026-10-12 — Holistic review of the design baseline (M0)
- What: a cross-component review of the whole uncommitted baseline. The mechanical checks are
  clean: no broken links, no dangling D/OD/T ids, renames complete. Findings, pending the builder's
  decisions (Q56–Q65):
  - §4.4 conflicts: the trade-off chart may choose on the test metric (D-037); EDA and Feature
    Checks label views run on the *window*, which includes test clients; label-free PSI against
    the validation month; sweeps and the LLM loop choose variants on the validation month;
  - shapes: the model bundle is not a versioned artifact (it matters under OD-03); binary-only hooks
    outside D-020's five dicts; the scores schema has no domain, split or batch id; config and
    data-definition hashes are under-specified (conf/local values, validation and inference months);
    the run id is not unique per entity; the ledger is keyed by `run_id` before a run exists;
  - D-031 × OD-10: resolving a flag after training changes the config hash, which forces a retrain
    before registration; D-031 also partly pre-decides OD-09;
  - gaps: final-fit policy; calibration of models without downsampling (§4.7 wording); drift
    reference on the true population; labels for monitoring; lifecycle CLI commands; Phase 2
    definition of done depends on the bank's change-request process;
  - simpler: a v0 synthetic generator for M1; registry tables serve as the Phase 2 inventory.
- Why: the builder ran `/holistic-review` on the baseline before committing it.
- Decisions / open decisions: none yet. Touches D-020, D-031, D-037; OD-03, OD-09, OD-10, OD-11,
  OD-15, OD-18; `CLAUDE.md` §2, §4.4, §4.7.
- Still open: Q56–Q65.

### 2026-10-12 — Review pass: unrecorded inputs added
- What:
  - sync page: questions for the Lead DS (example notebooks, "necessary inputs" for model docs,
    monitoring in Phase 2 vs Phase 3, sandpit vs production paths); lifecycle design urgency added;
  - lifecycle.md: sandpit-path note, "designs needed soon", unknown CR steps;
  - roadmap: OD-01 (monitoring/entity handling Phase 3 suggestion), OD-04 (Nexus with version pins),
    OD-13 (MLflow lead time), OD-15 (quantile-loss regression idea), "necessary inputs" note;
  - target_factory.md: agreed aggregation starting list; evaluation.md: "widest practical set";
  - decisions: D-046 (no per-source column catalogue for now).
- Why: the builder asked for a full review of their inputs before compacting.
- Decisions / open decisions: D-046; OD-01, OD-04, OD-13, OD-15.

### 2026-10-12 — Shared worknotes, reading guide, review answers recorded
- What:
  - worknotes are committed, for the builder and the Lead DS: `sync.md` (review todos, shared open
    questions), `log.md` (this file), `handovers/` (D-044);
  - new `docs/README.md` with the reading order and the stage → component map; components index
    trimmed to link to it (D-045);
  - sampling (review Q12b) and window ablation (Q12c) answers added as notes/todos to the dataset,
    training, evaluation, run-modes and synthetic-data docs, and to roadmap OD-17 and the backlog;
  - confirmations: D-033 lifecycle vocabulary and D-037 (trade-off chart on in-time data only) are
    now decided; the depth-level wording stays proposed (OD-01).
- Why: the builder's answers to round-4 questions 53–55 and confirmations 1–3.
- Files: `.gitignore`, `worknotes/*`, `docs/README.md`, `docs/components/README.md`, `CLAUDE.md`,
  `README.md`, `docs/decisions.md`, `docs/roadmap.md`, component docs, commands, `doc-sync`,
  `new-component`, workflow guide, glossary, UPDATES.
- Decisions / open decisions: D-033, D-037, D-044, D-045; OD-01, OD-17.
- Still open: the Chief DS meeting pre-read.

### 2026-10-12 — Design baseline after three review rounds
- What:
  - rewrote CLAUDE.md (ambitious summary, classes rule, "major steps start wide", invariants
    §4.11–13, doc map + update triggers + creation rules), project.md (from → to table, goals, scope,
    Phase 2 definition, entities/domains, roles), architecture.md, UPDATES.md;
  - decisions D-020–D-043;
  - new roadmap.md (milestones, depth levels, backlog, OD-01–OD-21, Chief DS topics), glossary.md,
    components/dataset.md, components/feature_ledger.md;
  - rewrote every component doc; renamed data_creation → target_factory and tracking → monitoring;
  - updated lessons (T16, T17), environment (devcontainer libraries, Optuna, offline plotly), READMEs,
    guides, skills and agents; added the `holistic-review` skill and `/brief`, `/handover`, `/resume`.
- Why: review rounds 1–3 (Q1–Q52) and the Lead DS notes changed scope, structure and way of working.
- Decisions / open decisions: D-020–D-043; OD-01–OD-21.
- Still open: Chief DS meeting prep.

### Earlier
- 2026-10-05 — Vendored and adapted review/debugging skills and agents (D-019).
- 2026-09-30 — Repo bootstrapped for Phase 2.
