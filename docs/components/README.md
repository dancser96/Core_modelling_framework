# Components

One doc per component. Each doc describes the **current state** and the **Phase 2 target**. Update
it in the same change as the code (`CLAUDE.md` §8). Status values match `docs/UPDATES.md`.

| Component | Doc | Status |
|---|---|---|
| Environment adapter | [environment.md](environment.md) | legacy-only |
| Config spine | [config.md](config.md) | legacy-only |
| Test harness (synthetic panel, local Spark) | [test_harness.md](test_harness.md) | designing |
| Data Creation | [data_creation.md](data_creation.md) | legacy-only |
| EDA | [eda.md](eda.md) | legacy-only |
| Feature Checks | [feature_checks.md](feature_checks.md) | legacy-only |
| Training | [training.md](training.md) | legacy-only |
| Evaluation | [evaluation.md](evaluation.md) | legacy-only |
| Reporting & model card | [reporting.md](reporting.md) | legacy-only |
| Lifecycle (promotion, registry, deployment) | [lifecycle.md](lifecycle.md) | designing |
| Inference | [inference.md](inference.md) | legacy-only |
| Tracking (baselines, impact, drift) | [tracking.md](tracking.md) | designing |
| Run modes (notebooks, CLI, Python API) | [run_modes.md](run_modes.md) | designing |
| LLM-assisted modelling | [llm_assist.md](llm_assist.md) | designing |

## Template for a new component doc

```markdown
# <Component>
**Status:** designing | stub | built | tested · **Legacy:** <files or "none">

## Purpose
One paragraph: what it does and why it is a standalone unit.

## Phase 2 requirements
Numbered, testable statements.

## Design constraints
Invariants (CLAUDE.md §4), task-agnostic shapes, simplicity notes.

## Lessons from the crunch
Links to docs/context/lessons.md entries (T#).

## Interface
Public functions and config section (fill in when built).

## Open questions
```
