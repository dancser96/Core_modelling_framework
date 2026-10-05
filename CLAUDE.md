# CLAUDE.md — retail.core_modelling

A config-driven modelling framework. Low- and medium-value use cases are meant to be delivered
through it in ~3–4 weeks instead of ~3–4 months of bespoke work. Package: `src/core_modelling/`.
**Current state:** Phase 2 has just started. The package is an empty skeleton; the working crunch
implementation lives in `legacy/propensity_crunch/` as reference only.

## 0. Start of every session

1. Read `docs/UPDATES.md` — current state, open items, what was done last.
2. New to the repo or the task touches scope/goals: read `docs/context/project.md`.
3. Working on a component: read `docs/components/<component>.md` and its legacy reference.
4. Touching IO, dependencies or anything environment-specific: read `docs/context/environment.md`.
5. Before designing anything: check `docs/decisions.md` so you don't re-litigate settled decisions.

---

## 1. Prime directive: code-light, no slop

Every line you write will be read and reviewed by a human. The failure mode this repo exists to
avoid is the huge AI-generated pipeline nobody understands. Readable, boring, small code wins over
clever, complete or "future-proof" code. When in doubt, write less.

**Rules**

1. **Simplest thing that works.** Build what the current task needs; nothing speculative.
2. **Functions first.** Use classes only for data that travels together (Pydantic config models,
   small dataclasses). No inheritance hierarchies, ABCs, metaclasses, registries built from
   decorators, dependency-injection frameworks or "manager"/"factory"/"engine" classes.
3. **One function, one job.** Aim for ≤ ~40 lines. If it grows, split it into well-named helpers.
4. **Names say what things do.** Functions are `verb_noun` (`load_snapshot`, `compute_psi`,
   `promote_model`). Only standard abbreviations (`df`, `cfg`, `auc`, `oot`, `psi`). No `utils.py`
   / `helpers.py` dumping grounds — a module is named for its one concept.
5. **Files by responsibility.** One module ≈ one concept, roughly ≤ 300 lines. If you can't name the
   module in two words, it is doing too much.
6. **No abstraction before a second real use.** The exception is §3 "shapes must be task-agnostic":
   config and data *shapes* stay general, *implementations* stay concrete.
7. **Extension points are plain dicts** mapping names to functions
   (`METRICS_BY_TASK = {"binary": binary_metrics}`). No plugin frameworks.
8. **Fail loud.** Never swallow exceptions. Validate at boundaries (config load, data contract) with
   clear messages; catch only what you can actually handle.
9. **Comments say why, not what.** Docstrings are one summary line, plus arguments only when not
   obvious. No commented-out code, no dead code, no TODOs without a row in `docs/UPDATES.md`.
10. **Type hints on public functions**, kept simple (`pd.DataFrame`, `dict[str, float]`).
11. **Use the library.** Prefer pandas / PySpark / scikit-learn built-ins over hand-rolled versions.
12. **No new dependency without asking.** It must also be installable inside the bank (see §5).
13. **Small, reviewable steps.** One logical change per step, roughly ≤ 200 changed lines unless
    agreed. Stop, summarise, let the user review.

**Workflow for any non-trivial task**
1. Propose a plan first: files to touch, function names + signatures, what is deliberately left out.
   Wait for approval.
2. Implement in small steps. Run `pytest` and `ruff check .` after each.
3. Before calling it done, run the **code-reviewer** subagent on the diff (plus the specialised
   subagents in §10 when their trigger applies). Fix or explicitly justify every finding.
4. Update docs per §8. Report: what changed, why, what to review first, open risks.

---

## 2. Where simplicity does NOT win: forward compatibility

The framework will push updates into every use case built on it, so breaking changes are expensive.
Simplicity never justifies a silent breaking change.

- **Public API** = the functions listed in `docs/architecture.md` §Public API. Everything else is
  private (`_name`) and can change freely.
- **Every config carries `schema_version`.** A schema change means: bump the version, write a small
  migration function old → new, add a test that loads an old config. Old configs keep loading and
  emit a deprecation warning.
- **Artifact formats are versioned the same way:** model card, manifest, scores schema, registry
  entries.
- **Deprecate before removing** — keep the deprecated path for at least one minor version.
- **Semantic versioning** via `__version__` in `src/core_modelling/__init__.py`.
- Run the **compat-guardian** subagent whenever you touch config schemas, public functions or
  artifact formats.

---

## 3. Architecture rules (details: `docs/architecture.md`)

- **Logic lives only in `src/core_modelling/`.** Production runs use `.py` only:
  `python -m core_modelling run <config>` plus an importable Python API.
- **Notebooks are an interface, never a workspace.** They import, call, display. They define no
  functions and are never duplicated per product — switch the config and rerun. Reports come from
  frozen configs, not from hand-edited notebooks.
- **A use case = configs (+ the standard notebooks).** Custom code only through the named extension
  points (mostly Data Creation). Any use case with free-form code reverts to the bespoke 3-month
  pattern this framework replaces.
- **Environment-specific things live only in the environment adapter + `conf/local/`**
  (gitignored): Spark session, HDFS transport, paths, table names, compat shims. **No bank names,
  paths, table names or people's names anywhere in the repo.**
- **Task-agnostic shapes.** Configs carry `task` (only `binary` is built now; `regression`,
  `multiclass`, `time_to_event` and `forecasting` come later). Metric/evaluation/calibration choices
  dispatch on `task` through plain dicts. Never bake binary assumptions into data contracts,
  artifact schemas or output tables (e.g. an output column is `score`, not `propensity`).
- **Segment-agnostic.** No retail-specific names in framework code; retail is configuration.
- **Standalone units.** Data Creation, EDA, Feature Checks, Training, Evaluation, Promotion,
  Inference and Tracking each run on their own from a config and write their own artifacts.
- **Stepwise traceability.** Filters and selections are declared as ordered steps in config, and
  each step logs what it removed and why.
- **Lifecycle tiers: local → registered → production.** Promotion (local → registered) and
  deployment (registered → production) are explicit, gated steps, separate from inference.
  Inference consumes registered/production models only (local models only in dev mode).

---

## 4. ML correctness invariants (non-negotiable)

1. **Time separation.** Features are as-of the observation month; the target is strictly after it.
   Forward windows exclude the current month; backward windows include it.
2. **Out-of-time evaluation** on a later period whose target window does not overlap training's.
3. **Baseline and metric are declared in config before any result is seen.**
4. **Fit and select inside the training split only.** No feature selection or fitted transform
   ever sees evaluation data.
5. **Checks wrap the engine.** The AutoML engine sees only the vetted feature set; OOT evaluation
   runs outside the engine.
6. **Leakage screens flag, never auto-drop.** Columns used to build the target are excluded
   automatically (lineage), not by memory.
7. **Downsampling is train-only**, and calibration is applied only when downsampling happened.
8. **Contract checks run on the true population**, before any downsampling.
9. **Eligibility is applied identically** to train, OOT and inference.
10. **Everything is reproducible:** frozen config + config hash + feature signature + model hash.
    Every score can be traced to its model and config.

Run the **ml-correctness-auditor** subagent whenever you touch data creation, splits, features,
training, evaluation, calibration or inference.

---

## 5. Environment and bank parity (details: `docs/context/environment.md`)

- **Code flows one way:** zip → copied into an internal repo. **Real data never exists outside the
  bank** — develop and test only on synthetic data with local Spark.
- `requirements.txt` holds the bank-parity pins (Python 3.11, PySpark 3.4.3, Java 11). Don't upgrade
  or add packages without asking.
- **Known traps** (full list: `docs/context/lessons.md`):
  - PySpark 3.4 + numpy 2 needs the `np.NaN` compat shim *before* importing pyspark/flaml.
  - Never pass `hdfs://` URIs through `pathlib`. `pathlib` and `pickle` cannot read HDFS.
  - Prune columns and rows in Spark before `toPandas()`.
  - No cwd-relative paths — roots come from config.
  - FLAML metric names are its own (`ap`, not `average_precision`).
  - FLAML 2.7 + xgboost 3.2 compatibility is **unverified**.
- Use the **bank-parity-check** skill when adding imports/dependencies or touching IO.

---

## 6. Legacy code policy

`legacy/propensity_crunch/` is the working implementation from the 2–3 week crunch that preceded Phase 2.
It is **reference, not a constraint**: pull ideas and proven logic from it, and rewrite freely.
Never import from it. Don't edit it. Its lessons are in `docs/context/lessons.md`. Some changes made inside the bank never came back out (see `legacy/README.md`);
treat legacy as close to, but not exactly, the internal state.

---

## 7. Testing (Phase 2 build-out)

- **Now:** light tests. Write them for the correctness invariants (§4), the config/schema migration
  paths (§2), plus one end-to-end test on a synthetic panel with real local Spark.
- **Before migration into the bank (later):** every function tested, internal CI/CD and Sonar
  checks passing. Don't build that yet — just don't write code that makes it hard.
- Tests follow the same code-light rules. No mocks where real local Spark or real small data works.

---

## 8. Documentation rules — what to update when

Docs describe the **current state**. History goes to `docs/UPDATES.md` and `docs/decisions.md`.
Update docs **in the same change** as the code.

| Trigger | Update |
|---|---|
| A component's behaviour or interface changes | `docs/components/<component>.md` (Status, Interface, Current state) |
| A config field is added, changed or removed | `docs/components/config.md` + example in `conf/base/`; §2 procedure if breaking |
| A decision is made (pattern, dependency, lifecycle, naming) | New entry in `docs/decisions.md`; `docs/architecture.md` if structure changes |
| Work item started / finished / blocked | `docs/UPDATES.md` status table; dated log line if major |
| A new bug class or trap is found | `docs/context/lessons.md` → Known traps |
| An environment fact changes (versions, bank behaviour) | `docs/context/environment.md` + `requirements.txt` |
| A new component | New `docs/components/<component>.md` from the template + index + UPDATES row (use **new-component**) |
| A new skill or agent | Inventory in `docs/guides/skills_and_agents.md` |
| Scope, goals or priorities change | `docs/context/project.md` |

Style: verdict first, concise, integrated (edit the existing text, don't append sections). Flag
anything unverified as such. Run the **doc-sync** skill at the end of every task.

---

## 9. Working with the user

- **Ask first** before: a new dependency, a public API or schema change, a large refactor, deleting
  anything, or anything that touches the lifecycle tiers.
- **Verify, don't assume.** Check library behaviour against the pinned version. Say when something
  is opinion or unverified.
- **Push back** when a request leads to over-engineering or a correctness risk — explain why and
  offer the simpler option. Ruthless-mentor tone, not adversarial.
- **No people's names** in docs or code.

---

## 10. Skills and subagents (in this repo)

| Kind | Name | Use when |
|---|---|---|
| Skill | `simplicity-review` | Reviewing any diff against §1 before presenting it |
| Skill | `doc-sync` | End of every task — applies §8 |
| Skill | `new-component` | Adding a new spine/lifecycle component |
| Skill | `bank-parity-check` | New imports/deps, IO code, anything that must run inside the bank |
| Skill | `brainstorming` | New or unsettled design, before the §1 plan |
| Skill | `systematic-debugging` | Any bug, test failure or unexpected behaviour, before proposing a fix |
| Skill | `verification-before-completion` | Before claiming anything is done, fixed or passing |
| Skill | `claude-md-improver` / `/revise-claude-md` | Auditing CLAUDE.md or capturing session learnings |
| Subagent | `code-reviewer` | Before declaring any code change done (fresh-context review) |
| Subagent | `silent-failure-hunter` | Changes to error handling, fallbacks, coercion, IO or validation |
| Subagent | `ml-correctness-auditor` | Changes to data, splits, features, training, evaluation, calibration, inference |
| Subagent | `compat-guardian` | Changes to config schemas, public API or artifact formats |

Vendored items and their sources: `.claude/skills/SOURCES.md`. How to add more:
`docs/guides/skills_and_agents.md`.

---

## 11. Commands

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt          # bank-parity deps + editable package + dev tools
pytest                                       # tests (tests/ only; legacy is excluded)
ruff check . && ruff format <changed files>  # lint; format only files you touched
```

## 12. Repo map

```
CLAUDE.md                  this file (always loaded)
src/core_modelling/        the package (currently a skeleton)
conf/base/                 committed configs and examples
conf/local/                gitignored: environment-specific paths/tables (bank side)
data/                      gitignored: Kedro-style layered data folders (see data/README.md)
notebooks/                 thin interface notebooks (rules: notebooks/README.md)
tests/                     light tests (policy: tests/README.md)
legacy/propensity_crunch/  crunch implementation — reference only
docs/UPDATES.md            state + major changes (read first)
docs/context/              project.md, environment.md, lessons.md
docs/architecture.md       target design
docs/decisions.md          decision log
docs/components/           one doc per component
docs/guides/               setup (WSL2 / macOS), Claude Code workflow, skills & agents
docs/reference/            original roadmap + spine/governance reference (historical)
.claude/skills/, .claude/agents/   project skills and subagents
```
