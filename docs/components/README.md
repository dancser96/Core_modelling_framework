# Components

One doc per component or versioned artifact. Each describes the **current state** and the **Phase 2
target**, and is updated in the same change as the code (`CLAUDE.md` §8). Which doc belongs to which
stage, and the order to read the docs in: [`docs/README.md`](../README.md). Status values:
`docs/UPDATES.md`.

## Index

[config](config.md) · [dataset](dataset.md) · [environment](environment.md) ·
[eda](eda.md) · [evaluation](evaluation.md) · [feature_checks](feature_checks.md) ·
[feature_ledger](feature_ledger.md) · [inference](inference.md) · [lifecycle](lifecycle.md) ·
[llm_assist](llm_assist.md) · [monitoring](monitoring.md) · [reporting](reporting.md) ·
[run_modes](run_modes.md) · [target_factory](target_factory.md) · [test_harness](test_harness.md) ·
[training](training.md)

## Template for a new component doc

Use the **new-component** skill. When to create a new doc at all: `CLAUDE.md` §8. A new, renamed or
deleted component doc also updates the stage map in `docs/README.md`.

```markdown
# <Component>
**Status:** designing | stub | built | tested · **Legacy:** <files or "none">
**Related:** <links to the docs this depends on and that depend on it> · D-nnn · OD-nn

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
Component-only questions here; cross-cutting ones as OD rows in docs/roadmap.md.
```
