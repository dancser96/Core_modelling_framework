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

Every component doc reads **top-down**: a reader first gets the whole picture (summary, how it works,
code map), then dives into the segments. History stays out: it belongs in `docs/UPDATES.md` and
`docs/decisions.md`. `test_harness.md` is the worked example.

```markdown
# <Component>
**Status:** designing | stub | built | tested · **Legacy:** <files or "none">
**Related:** <links to the docs this depends on and that depend on it> · D-nnn · OD-nn

## Summary
A few lines a newcomer reads first: what it does, why it is a standalone unit, what goes in and
what comes out, who uses it.

## How it works
One page: the flow in steps (a small diagram helps), what it writes, how it is checked.

## Code map
The folder tree with each module's one job and main functions, the call flow of one run, and a
reading order for review. For a design: the planned layout.

## Interface
Public functions, CLI and config section (signatures; fill in when built).

## Requirements and design constraints
Numbered, testable requirements; invariants (CLAUDE.md §4), task-agnostic shapes, simplicity notes.

## <One section per area>
The details, in the order the summary introduces them.

## Lessons from the crunch
Links to docs/context/lessons.md entries (T#).

## Open questions
Component-only questions here; cross-cutting ones as OD rows in docs/roadmap.md.
```
