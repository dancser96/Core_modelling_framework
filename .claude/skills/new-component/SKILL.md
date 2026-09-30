---
name: new-component
description: Add a new framework component (a stage or lifecycle unit such as a new screening stage, tracking job or reporting unit) in the repo's standard way — doc first, then config section, then minimal code and tests. Use this whenever the user asks to add, create or scaffold a new component, stage, module or unit, or when a planned component in docs/components moves from designing to building.
---

# New component

Components must be standalone units (runnable alone from a config, writing their own artifacts),
consistent with each other, and small. Doing the doc first forces the design to be agreed before
any code exists.

## Steps

1. **Doc first.** Create or complete `docs/components/<name>.md` from the template in
   `docs/components/README.md`:
   - Purpose
   - Phase 2 requirements (numbered, testable)
   - Design constraints
   - Interface (planned function signatures)
   - Open questions

   **Stop and get user approval.**
2. **Config section.** Add the section to the config schema with `schema_version` handling (new
   optional fields with defaults are non-breaking). Add an example in `conf/base/`.
3. **Code.** One module (or a folder only if it genuinely needs several files) under
   `src/core_modelling/`. Plain functions, and one public entry function per stage
   (`run_<stage>(cfg, ...)`). Environment access only through the environment adapter.
4. **Tests.** Tests for the invariants this component owns, plus wiring into the e2e test on the
   synthetic panel.
5. **Register.** Add a row to the `docs/components/README.md` index, add the item to
   `docs/UPDATES.md`, and add public functions to `docs/architecture.md` → Public API.
6. Run the `simplicity-review` skill, the `code-reviewer` subagent, and `ml-correctness-auditor` if
   the component touches data, features, training, evaluation or scoring.

## Consistency rules

- Entry point naming: `run_<stage>`. Artifacts go under the paths the environment adapter provides.
- Results are structured data (dicts / DataFrames) first. Reports are rendered from them through
  the reporting component.
- Task-agnostic signatures: pass `cfg`; dispatch on `cfg.task` via a dict when behaviour differs.
