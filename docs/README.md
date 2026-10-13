# Docs guide

**Verdict:** the front door to the docs. It owns two things: the order in which to read them for the
full, current picture, and the map from canonical stages to component docs. Keep it current
(`CLAUDE.md` §8): a doc added, renamed or deleted means updating this page.

## 1. Reading order

| # | Doc | Read it for | When |
|---|---|---|---|
| 1 | [UPDATES.md](UPDATES.md) | Where things stand: status per item, log of major changes | Every time |
| 2 | [context/project.md](context/project.md) | Why the framework exists, where we start → where we want to reach, goals, scope, entities, roles | First read; scope questions |
| 3 | [glossary.md](glossary.md) | One meaning per term (entity vs domain vs segment, train/test/validation, register/promote/deploy) | First read; any unfamiliar term |
| 4 | [roadmap.md](roadmap.md) | Phases, milestones, depth levels, backlog, **open decisions (OD-nn)**, Chief DS topics | Planning; "what's next / what's undecided" |
| 5 | [architecture.md](architecture.md) | The map: stages, config, time model, lifecycle, package layout, Public API | Before structural work |
| 6 | [decisions.md](decisions.md) | Why things are the way they are (D-nnn) | Before designing; when something looks odd |
| 7 | Component docs (map below) | Requirements, interface and open questions per stage | When working on that stage |
| 8 | [context/lessons.md](context/lessons.md), [context/environment.md](context/environment.md) | Traps (T-nn), crunch lessons, bank versions and behaviour | Before related code, IO or dependencies |
| 9 | [guides/](guides/) | Machine setup, the Claude Code workflow, skills and agents | Setting up; changing how we work |
| — | [`../worknotes/sync.md`](../worknotes/sync.md) | What the Lead DS should review now, open questions for both of us | Before each daily sync |
| — | [reference/](reference/) | The original roadmap and spine reference (historical) | Background only |

**Shortest path for a newcomer:** 2 → 3 → 5 → the stage map below → 4. Then [UPDATES.md](UPDATES.md)
for current status. Working rules for code and docs are in [`../CLAUDE.md`](../CLAUDE.md).

## 2. Stages → components

Canonical stage order (D-028). Each stage has one main doc; the cross-cutting docs it relies on are
listed alongside.

| # | Stage | Main doc | Also uses | Status |
|---|---|---|---|---|
| 1 | Target Factory (optional) | [target_factory](components/target_factory.md) | config, dataset | legacy-only |
| 2 | EDA | [eda](components/eda.md) | dataset, feature ledger, reporting | legacy-only |
| 3 | Feature Checks | [feature_checks](components/feature_checks.md) | feature ledger, dataset, reporting | legacy-only |
| 4 | Training | [training](components/training.md) | dataset, feature ledger, config | legacy-only |
| 5 | Evaluation | [evaluation](components/evaluation.md) | reporting, dataset | legacy-only |
| 6 | register → promote → deploy | [lifecycle](components/lifecycle.md) | reporting (model card), environment | designing |
| 7 | Inference | [inference](components/inference.md) | lifecycle, environment | legacy-only |
| 8 | Monitoring | [monitoring](components/monitoring.md) | reporting, inference, dataset | designing |

**Cross-cutting docs** (used by several stages):

| Doc | Owns | Used by |
|---|---|---|
| [config](components/config.md) | The single-file use-case definition: profiles, decision, entities, sections | Every stage |
| [dataset](components/dataset.md) | Observation window, train/test/validation split, sampling | Target Factory, EDA, Feature Checks, Training, Evaluation, Monitoring |
| [feature_ledger](components/feature_ledger.md) | The per-feature trail from candidates to model | EDA, Feature Checks, Training, Evaluation |
| [reporting](components/reporting.md) | HTML reports, chart rules, model card | EDA, Feature Checks, Evaluation, lifecycle, Monitoring |
| [environment](components/environment.md) | Spark, transport, paths, source resolution | Every stage |
| [run_modes](components/run_modes.md) | CLI, Python API, guided notebooks, experiment sweeps | Every stage |
| [test_harness](components/test_harness.md) | Synthetic data and the local-Spark test harness (dev only) | Every stage, outside the bank |
| [llm_assist](components/llm_assist.md) | The later LLM-assisted modelling branch | Drives the stages through config + sweeps |

The doc index with the template for new component docs: [components/README.md](components/README.md).
Status values come from [UPDATES.md](UPDATES.md), which wins if the two disagree.
