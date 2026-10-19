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

Every component doc reads **top-down in three levels**, so a reader can stop early and still know
most of it (D-072):
- **Level 1: Summary**, about 4% of the doc. It gives the key things, roughly two thirds of what
  there is to know.
- **Level 2: How it fits together.** With Level 1, about 20% of the doc and 80% of what there is
  to know. It covers the main relationships and connections:
  - what drives what, and how the parts depend on each other;
  - how one run flows;
  - the function structure in brief;
  - how it is checked.
- **Level 3: Details**, the rest. Every number, rule and requirement, the full code map, the
  interface and the maths, in Level 2's order.

**No flowcharts or ASCII diagrams**, because they don't wrap on small screens. Use a numbered list
for a flow, nested bullets for a tree and a narrow table for a mapping. History stays out: it
belongs in `docs/UPDATES.md` and `docs/decisions.md`. `test_harness.md` is the worked example.

```markdown
# <Component>
**Status:** designing | stub | built | tested · **Legacy:** <files or "none">
**Related:** <links to the docs this depends on and that depend on it> · D-nnn · OD-nn

Read it in three levels: Level 1 gives the essentials, Level 2 how the parts connect, Level 3
every detail.

## Level 1: Summary
About 4% of the doc. What it does and why it is a standalone unit, what goes in and what comes
out, who uses it, the key numbers, how to run it.

## Level 2: How it fits together
With Level 1, about 20% of the doc. One ### per area:
- the main relationships (what drives what, how the parts depend on each other);
- how one run flows (a numbered list);
- the function structure in brief (folders, main functions);
- how it is checked.

## Level 3: Details
### Requirements and design constraints
Numbered, testable requirements; invariants (CLAUDE.md §4), task-agnostic shapes, simplicity notes.

### <One section per area, in Level 2's order>
The details: every number and rule.

### Code map
Each module's one job and main functions (nested bullets, not a tree drawing), the call flow of
one run, and a reading order for review. For a design: the planned layout.

### Interface
Public functions, CLI and config section (signatures; fill in when built).

### Lessons from the crunch
Links to docs/context/lessons.md entries (T#).

## Open questions
Component-only questions here; cross-cutting ones as OD rows in docs/roadmap.md.
```
