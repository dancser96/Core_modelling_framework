---
name: new-component
description: Add a new framework component (a stage, lifecycle unit or versioned artifact such as a new screening stage, monitoring job or reporting unit) in the repo's standard way — holistic review, doc first, then config section, then minimal code and tests. Use this whenever the user asks to add, create or scaffold a new component, stage, module or unit, or when a planned component in docs/components moves from designing to building.
---

# New component

Components must be standalone units (runnable alone from a config, writing their own artifacts),
consistent with each other, and small. Writing the doc first forces the design to be agreed before
any code exists. A new component is a **major step** (`CLAUDE.md` §1 workflow step 0).

## Steps

0. **Start wide.** Use `brainstorming` (research + critique) and run `holistic-review`. A new
   component changes its neighbours.
1. **Doc first.** Create or complete `docs/components/<name>.md` from the template in
   `docs/components/README.md`. It reads top-down in three levels, the overview before any detail,
   with no flowcharts or ASCII diagrams:
   - Status and **Related** lines (link both ways)
   - Level 1, the summary: about 4% of the doc, the key things
   - Level 2, how it fits together: with Level 1 about 20% of the doc; the main relationships, how
     one run flows, the function structure in brief, how it is checked
   - Level 3, the details: requirements (numbered, testable) and design constraints, one section
     per area, the code map (planned modules and main functions; the call flow), the interface
     (planned function signatures)
   - Open questions (cross-cutting ones as OD rows in `docs/roadmap.md`)

   **Stop and get user approval.**
2. **Config section.** Add the section to the config schema with `schema_version` handling (new
   optional fields with defaults are non-breaking). Add an example in `conf/base/`, with when-to-use
   guidance for every option.
3. **Code.** One module (or a folder only if it genuinely needs several files) under
   `src/core_modelling/`. Plain functions, and one public entry function per stage
   (`run_<stage>(cfg, ...)`). Environment access only through the environment adapter.
4. **Tests.** Tests for the invariants this component owns, plus wiring into the end-to-end test on
   the synthetic data.
5. **Register.**
   - the `docs/components/README.md` index and the stage → component map in `docs/README.md`;
   - the item in `docs/UPDATES.md` and in the `docs/roadmap.md` backlog;
   - public functions in `docs/architecture.md` → Public API;
   - new terms in `docs/glossary.md`;
   - a guided notebook section if users run it interactively.
6. Run the `simplicity-review` skill, the `code-reviewer` subagent, and `ml-correctness-auditor` if
   the component touches targets, data, features, training, evaluation or scoring.

## Consistency rules

- Entry point naming: `run_<stage>`. Artifacts go under the paths the environment adapter provides.
- Results are structured data (dicts / DataFrames) first. Reports are rendered from them through the
  reporting component (self-contained HTML, chart rules in `docs/components/reporting.md`).
- Task-agnostic signatures: pass `cfg`; dispatch on `cfg.task` via a dict when behaviour differs.
- Domain- and entity-agnostic: no domain or entity names in code; never combine entities' data.
