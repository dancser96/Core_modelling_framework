---
name: holistic-review
description: Cross-component review of a proposed design or change against the project's goals, architecture, every component doc and the decision log — catches tunnel vision, knock-on effects on other stages, contradictions between docs, and gaps. Use at every major step (new component, config section, public API, dependency, or anything the user calls a significant redesign or extension), before finalising a plan that touches more than one stage, and whenever the user says "holistic review", "big picture", "what else does this affect" or "are we tunnelling".
---

# Holistic review

This project's failure mode is tunnel vision: extending one component (or porting legacy code) while
the whole drifts away from the goals. A change can be clean locally and still break another stage,
contradict a decision, or miss the point of the project. This review looks across everything. Run it
before the plan is written, and again before a big step is called done.

## Inputs

Read these in order. Skim what is clearly unaffected; read closely what is affected.
1. `docs/context/project.md`: does the change move us along the "where we start → where we want to
   reach" table, or against it?
2. `docs/roadmap.md`: the phase, depth targets, and the open decisions this touches.
3. `docs/architecture.md`: stage order, tiers, config, time model, package layout.
4. **Every** `docs/components/*.md`, not only the one being changed.
5. `docs/decisions.md`: settled decisions. Don't re-litigate them; flag real conflicts.
6. `docs/glossary.md`: are terms used consistently?
7. The change itself: the proposal text or `git diff`.

## Questions to answer

1. **Goals.** Which from → to rows does this advance? Does it work against any (speed,
   reproducibility, maintainability, generality, guidance, overview)?
2. **Knock-on effects.** Walk the stage chain (Target Factory → EDA → Feature Checks → Training →
   Evaluation → register → promote → deploy → Inference → Monitoring) and the cross-cutting pieces
   (config, dataset/splits, feature ledger, reporting, environment adapter, run modes, synthetic
   data). For each, say affected or not, and how.
3. **Shapes.** Does it bake in binary, single-month, single-entity, single-source or retail
   assumptions? Does it change a config schema, an artifact format or a public function? If so,
   apply `CLAUDE.md` §2 and run compat-guardian.
4. **Invariants.** Is any `CLAUDE.md` §4 invariant touched? If so, run ml-correctness-auditor.
5. **Consistency.** Do docs contradict each other or a decision? Is any term used in two senses?
6. **Gaps.** What does this make necessary that nobody has planned (tests, docs, migrations,
   synthetic-data features, report views, notebook guidance)?
7. **Simpler alternative.** Is there a smaller change that gets most of the value?

## Output

```
Holistic review — <change in one line>
Goals: advances <rows>; works against <rows or none>
Knock-on effects:
- <stage/component> — <effect> — <needed action>
Shape / compatibility risks: …
Invariants touched: …
Contradictions: <doc A vs doc B, or vs D-nnn>
Gaps: …
Simpler alternative: …
Verdict: proceed | proceed with changes (<list>) | rethink
```

Record agreed outcomes in `docs/decisions.md` and the affected docs, and add new open questions as
OD rows in `docs/roadmap.md`. Don't write a separate review document.
