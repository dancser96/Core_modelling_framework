# CLAUDE.md — core_modelling

**What this is.** `core_modelling` is how the unit builds, ships and maintains models: a versioned
Python library driven by one config file per use case, used through guided notebooks, a CLI and a
Python API. It replaces months of bespoke work with a registered candidate in days to a few weeks of
DS effort (D-023); production follows through the change-request calendar. It sets one standard for every stage of the data
science lifecycle: correctness, reproducibility, maintainability, a shared vocabulary and an overview
of every live model. Where we start from and where we want to reach: `docs/context/project.md`.

- **Lifecycle:** Target Factory (optional) → EDA → Feature Checks → Training → Evaluation → register →
  promote → deploy → Inference → Monitoring. Every stage runs alone from a config. Model tiers are
  local → registered → production, and a data scientist's session never writes to production.
- **Intermediate outputs:** every stage writes its own artifacts. EDA and Feature Checks together
  are a product within the product: a data-analysis report in its own right (plus the feature
  ledger), not just notebook output. The other reports: model performance, model card, monitoring.
- **Coverage:** panel tasks (one row per unit per period) first: binary and regression in Phase 2
  (D-020). Series tasks (forecasting) come later. Any domain (retail, SME, corporate) and any
  entity (subsidiary) is handled through configuration.
- **Model types:** AutoML (FLAML) in Phase 2; predefined model families tuned with Optuna in
  Phase 3 (D-020); both behind one model interface.
- **Integrations (first release):** the feature store upstream and the data observability
  framework downstream. LLM-assisted modelling comes in Phase 3 (D-021).
- **Current state:** Phase 2, design baseline done; the package is still a skeleton. The crunch
  implementation in `legacy/propensity_crunch/` is reference only. Status: `docs/UPDATES.md`. Plan
  and open decisions: `docs/roadmap.md`. Vocabulary: `docs/glossary.md`. Reading order and the
  stage → component map: `docs/README.md`.

## 0. Start of every session

1. Read `docs/UPDATES.md`: current state and what was done last.
2. Planning, prioritising or "what next": read `docs/roadmap.md` (milestones, backlog, open decisions).
3. New to the repo, or the task touches scope or goals: read `docs/context/project.md` and
   `docs/glossary.md`.
4. Working on a component: find it in the stage map in `docs/README.md`, then read
   `docs/components/<component>.md`, the docs in its **Related** line, and its legacy reference.
5. Touching IO, dependencies or anything environment-specific: read `docs/context/environment.md`.
6. Before designing anything: check `docs/decisions.md` so you don't re-litigate settled decisions.
7. **Don't read `worknotes/` unless asked.** `/resume <topic>` loads a handover; `/brief` (or "what
   happened recently?") reads the sync page.

---

## 1. Prime directive: code-light, no slop

Every line you write will be read and reviewed by a human. The failure mode this repo exists to avoid
is the huge AI-generated pipeline nobody understands. Readable, boring, small code wins over clever,
complete or "future-proof" code. When in doubt, write less.

**Rules**

1. **Simplest thing that works.** Build what the current task needs; nothing speculative.
2. **Functions first.** Functions are the default. A class is fine when state and behaviour genuinely
   travel together across calls. Examples:
   - Pydantic config models and small dataclasses;
   - scikit-learn-compatible estimator/transformer wrappers (subclassing `BaseEstimator`, which
     pickling, SHAP and pipelines need);
   - a small `Protocol` shared by interchangeable parts, e.g. the AutoML and predefined-model paths
     (from Phase 3, D-100).

   Inherit only from library base classes, or one shallow level of your own, and say why in the
   step summary. Still no ABC hierarchies, metaclasses, decorator registries, dependency-injection
   frameworks or "manager"/"factory"/"engine" classes.
3. **One function, one job.** Aim for ≤ ~50 lines. If it grows, split it into well-named helpers.
4. **Names say what things do.** Functions are `verb_noun` (`load_snapshot`, `compute_psi`,
   `promote_model`). Only standard abbreviations (`df`, `cfg`, `auc`, `oot`, `psi`). No `utils.py` /
   `helpers.py` dumping grounds — a module is named for its one concept. Terms follow
   `docs/glossary.md`.
5. **Files by responsibility.** One module ≈ one concept, roughly ≤ 300 lines, but functions tied
   together stay in one module even past that. If you can't name the module in two words, it is
   doing too much. A package with more than a handful of modules splits them into role subfolders
   (rules as plain data, functions, checks), never dozens side by side (D-003).
6. **No abstraction before a second real use.** The exception is §3 "shapes must be task-agnostic":
   config and data *shapes* stay general, *implementations* stay concrete.
7. **Extension points are plain dicts** mapping names to functions
   (`METRICS_BY_TASK = {"binary": binary_metrics}`). No plugin frameworks.
8. **Fail loud.** Never swallow exceptions. Validate at boundaries (config load, data contract) with
   clear messages; catch only what you can actually handle. Anything that *should* work and doesn't
   is an error. The one exception is an output declared incompatible *up front*, e.g. a view a model
   family can't produce according to the compatibility table. It is skipped and shown as "not
   available: reason". That is decided before running, never by catching an error (D-035).
9. **Comments say why, not what.** A module docstring explains what the module is for and how it
   fits (a short paragraph). A function docstring is one summary line, plus arguments only when
   not obvious. No commented-out code, no dead code, no TODOs without a row in `docs/UPDATES.md`
   or `docs/roadmap.md`.
10. **Every function has type hints and a docstring**: public, private and test functions alike.
    Hints stay simple (`pd.DataFrame`, `dict[str, float]`). Enforced by ruff (`ANN`, `D1`) and,
    for private functions, by `tests/test_code_rules.py`.
11. **Use the library.** Prefer pandas / PySpark / scikit-learn / scipy built-ins over hand-rolled
    versions.
12. **No new dependency without asking.** It must also be installable inside the bank (see §5).
13. **Small, reviewable steps.** One logical change per step, roughly ≤ 300–400 changed lines
    unless agreed. Stop, summarise, let the user review. A larger agreed build ships with a review
    guide that says what to read, in which order, and what "right" looks like (D-003).

**Workflow for any non-trivial task**

**Parallel by default** (D-072): split the work into independent pieces and run them at the same
time, using subagents as much as possible. The `delegation` skill is the procedure (the split,
which model takes which piece, the brief template, integration); in short:
- delegate research, reviews and audits, and independent code, test or doc pieces, to subagents;
- run long jobs (data generation, slow tests) in the background meanwhile;
- give each subagent a complete brief (goal, files, constraints, what to report), since it starts
  with no context, and give parallel agents disjoint files;
- integrate and verify every result yourself;
- keep on the main thread only what needs the whole picture or must happen in order;
- run at most one memory-heavy job at a time (the dev machine's memory is the limit).

0. **Major steps start wide.** A major step is a new component, config section, public function or
   dependency, or anything the user calls a significant redesign or extension. Before the plan:
   - Use `brainstorming`: research current best practice (web search allowed; cite sources) and
     critique the user's ideas as openly as your own.
   - Run `holistic-review`, so the effects on every other component are on the table.

   **Never tunnel:** no component, and no legacy port, is extended in isolation. Outcomes go to
   `docs/decisions.md` with sources; there is no research folder.
1. Propose a plan in two tiers (D-072):
   - **major steps**, each ending in the SDS's review;
   - **minor steps** inside them, each ending in the review skills and subagents of step 3.

   Per step: the files to touch, the function names and signatures, and what is deliberately left
   out. Wait for approval.
2. Implement minor step by minor step. Run `pytest` and `ruff check .` after each, then step 3's
   reviews. Stop for the SDS at the end of each major step.
3. Run the **code-reviewer** subagent on each minor step's diff, plus the specialised subagents in
   §10 when their trigger applies (and `simplicity-review` on code). Fix or explicitly justify every
   finding.
4. Update docs per §8, including `worknotes/sync.md` and `worknotes/log.md`. Report: what changed, why, what to review
   first, open risks.

---

## 2. Where simplicity does NOT win: forward compatibility

Each use case pins the framework version it runs with and upgrades at its own pace (D-047). Many
versions therefore run at once and write to the same shared tables, and every upgrade must keep a
use case and its production model working. Simplicity never justifies a silent breaking change, and
pinning doesn't relax this. The promise is about outputs (D-007): what a version writes or saves
(shared tables, configs, bundles, artifacts) stays similar and readable; internals change freely.
The 0.x pre-release promises nothing; shared formats freeze from release 1.0's first row in the bank.

- **Public API** = the functions listed in `docs/architecture.md` §Public API. Everything else is
  private (`_name`) and can change freely.
- **Every config carries `schema_version`.** A schema change means: bump the version, write a small
  migration function old → new, add a test that loads an old config. Old configs keep loading and
  emit a deprecation warning.
- **Artifact formats are versioned the same way:** model bundle (D-051; never pickle once promoted),
  model card, manifest, scores schema, feature ledger, drift reference, registry records,
  monitoring tables.
- **Deprecate before removing:** keep the deprecated path for at least one minor version.
- **Semantic versioning** via `__version__` in `src/core_modelling/__init__.py`.
- Run the **compat-guardian** subagent whenever you touch config schemas, public functions or
  artifact formats.

---

## 3. Architecture rules (details: `docs/architecture.md`)

- **Logic lives only in `src/core_modelling/`.** Production runs use `.py` only:
  `python -m core_modelling run <config>` plus an importable Python API. There is no service layer
  (D-024).
- **Notebooks are an interface for production work.** The framework's guided notebooks import, call
  and display; they define no functions and carry well-written instructions. Users may copy them and
  explore freely, but nothing a production run, registered model or report depends on may live in a
  notebook. Reports come from resolved configs (D-039).
- **A use case = one config file and its audit log** (+ its notebook copies); several similar use
  cases may share a repo (D-006). Custom code goes only through the named
  extension points (mostly Target Factory). A use case with free-form code reverts to the bespoke,
  months-long pattern this framework replaces.
- **Environment-specific things live only in the environment adapter + `conf/local/`** (gitignored):
  Spark session, HDFS transport, paths, table names, compat shims, report theme. **No bank names,
  paths, table names or people's names anywhere in the repo**; use roles instead.
- **Task-agnostic shapes.** Configs carry `task`. Panel tasks come first (binary and regression in
  Phase 2, D-020); series tasks come later. Every task-specific choice (target builder,
  EDA ranking, leakage screen, selection rule, contract checks, baselines, metrics, views,
  calibration, output columns…) dispatches on `task` through one per-task spec dict (D-050). Never
  bake binary or single-month assumptions into
  data contracts, artifact schemas or output tables (an output column is `score`, not `propensity`).
- **Domain- and entity-agnostic.** Domains (retail, SME, corporate) and entities (subsidiaries) are
  configuration, never names in code. Data is never merged across entities, and a use case lists the
  entities it applies to (D-034).
- **Standalone stages.** Target Factory, EDA, Feature Checks, Training, Evaluation, register /
  promote / deploy, Inference and Monitoring each run on their own from a config and write their own
  artifacts; EDA, Feature Checks, Evaluation and Monitoring also write a report (D-036).
- **Stepwise traceability.** Filters and selections are ordered steps in config, and each step logs
  what it removed or flagged and why. Every candidate feature's path (checks, human decisions,
  automated selection, use in the model) is recorded in the feature ledger.
- **Guided, not guessed.** Every non-trivial choice (decision/metric, split, sampling, modelling path)
  has documented options with when-to-use guidance. Automation levels set the defaults, and reports open by
  stating what was chosen (D-032).
- **Lifecycle tiers: local → registered → production.** register, promote and deploy are explicit,
  gated steps, separate from inference. A DS session never writes to production: deploy runs through
  the change-request process (D-033). Inference consumes registered/production models only (local
  models only in dev mode).

---

## 4. ML correctness invariants (non-negotiable)

1. **Time separation.** Features are as-of the observation month; the target is strictly after it.
   Forward windows exclude the current month; backward windows include it.
2. **Out-of-time validation.** The validation (OOT) month comes after the observation window, and its
   target window does not overlap any training target window (`v ≥ tk + w`).
3. **Baseline and metric (or the decision they derive from) are declared in config before any result
   is seen.**
4. **Fit and select on the train split only.** No fitted transform or label-using automated selection ever sees
   test or validation data, and the validation (OOT) month never informs any choice. A choice among
   variants or tuning trials (window, sweep, trade-off point) weighs train and test metrics only
   (D-083). EDA and Feature Checks use every client in the observation window, labels included; the
   train/test client split happens after Feature Checks, and from Training on everything fits and
   selects on train-split clients only. People's feature decisions in EDA and Feature Checks have
   therefore seen test labels, which the model results report states (D-030). Label-free
   comparisons (e.g. PSI) may use later months, except the validation month (D-030).
5. **Checks wrap the engine.** The modelling engine sees only the vetted feature set; validation runs
   outside the engine.
6. **Leakage screens flag, never auto-drop.** Columns used to build the target are excluded
   automatically (lineage), not by memory.
7. **Downsampling is train-only.** Whenever sampling happened, a prior-shift offset is applied,
   computed from the true rate and the effective (weighted) training rate, so it is zero when sampling
   didn't change the class balance. A separate calibration step (e.g. Platt or isotonic) is fitted on
   out-of-fold predictions inside train, never on test or validation (D-049).
8. **Contract checks run on the true population**, before any downsampling.
9. **Eligibility is applied identically** to every month of train/test, validation and inference.
10. **Everything is reproducible:** resolved config + config hash + data-definition hash + feature
    signature + model hash + code version. Every score can be traced to its model and config. This
    assumes a source month never changes after it has been loaded.
11. **Train and test are split by client.** They share the observation window, so no client appears in
    both, and any CV inside train is grouped by client too.
12. **Sampling depends on outcomes only through the row's own label, with one keep fraction for the
    whole train split**, which the prior-shift offset undoes (D-049, D-117); any other
    outcome-dependent sampling needs weights. It happens after the client split.
13. **No model without data knowledge.** Training requires EDA and Feature Checks artifacts for the
    same data-definition hash; the `autonomous` level runs them automatically (D-031). A person signs off
    every feature, in one gate after training and before the model is registered, at every
    automation level; an LLM never passes this gate (D-031).

Run the **ml-correctness-auditor** subagent whenever you touch Target Factory, the dataset/splits,
features, training, evaluation, calibration or inference.

---

## 5. Environment and bank parity (details: `docs/context/environment.md`)

- **Code flows one way:** zip → copied into an internal repo. **Real data never exists outside the
  bank**: develop and test only on synthetic data with local Spark.
- `requirements.txt` holds the bank-parity pins (Python 3.11, PySpark 3.4.3, Java 11). Don't upgrade
  or add packages without asking.
- Also in the devcontainer, and usable (pin on first use): scipy, statsmodels, seaborn, plotly,
  jinja2. Optuna is installed on top, like FLAML. Versions are in `docs/context/environment.md`.
- **Known traps** (full list: `docs/context/lessons.md`):
  - PySpark 3.4 + numpy 2 needs the `np.NaN` compat shim *before* importing pyspark/flaml.
  - Never pass `hdfs://` URIs through `pathlib`. `pathlib` and `pickle` cannot read HDFS.
  - Prune columns and rows (and sample) in Spark before `toPandas()`.
  - No cwd-relative paths — roots come from config.
  - FLAML metric names are its own (`ap`, not `average_precision`).
  - FLAML 2.7's `estimator_list` + `custom_hp` and its transformer behaviour are verified (D-020,
    D-094); its group split (spike 1), the non-pickle round trips (spike 2, D-051), xgboost 3.2
    under FLAML and the Optuna 5.0 API are **unverified**.
  - Assume no internet inside the bank: reports embed plotly.js, never load it from a CDN.
- Use the **bank-parity-check** skill when adding imports/dependencies or touching IO.

---

## 6. Legacy code policy

`legacy/propensity_crunch/` is the working implementation from the 2–3 week crunch that preceded
Phase 2. It is **reference, not a constraint**: pull ideas and proven logic from it, and rewrite
freely. Never import from it. Don't edit it. Its lessons are in `docs/context/lessons.md`. Some
changes made inside the bank never came back out (see `legacy/README.md`), so treat legacy as close
to, but not exactly, the internal state. Crunch names differ: Data Creation → Target Factory.

---

## 7. Testing (Phase 2 build-out)

- **Now:** light tests. Write them for the correctness invariants (§4), the config/schema migration
  paths (§2), plus one end-to-end test on synthetic data with real local Spark.
- **Synthetic data** (`synthetic/`, dev-only) is the shared dataset for tests, notebooks and demos.
  It is generated once into `data/01_raw/` and read through `conf/local/` exactly like real data
  (`docs/components/test_harness.md`).
- **By release 1.0:** every function tested, internal CI/CD and Sonar checks passing; the December
  pre-release moves into the bank with the light suite (D-014). Don't build that yet — just don't
  write code that makes it hard.
- Tests follow the same code-light rules. No mocks where real local Spark or real small data works.

---

## 8. Documentation: what lives where, when to update, when to create

Docs describe the **current state**. History goes to the `docs/UPDATES.md` log and to
`docs/decisions.md`. Update docs **in the same change** as the code or decision that triggers them.
Each fact has **one owner doc**; every other doc links to it instead of repeating it.

**Doc map**

| Doc | Owns | Git | Read |
|---|---|---|---|
| `CLAUDE.md` | Working rules for this repo | committed | Always (auto-loaded) |
| `docs/README.md` | Reading order + stage → component map | committed | Finding your way; after adding/renaming docs |
| `docs/UPDATES.md` | Status table + log of major changes | committed | Every session start |
| `docs/roadmap.md` | Phases, milestones, depth levels, backlog, Phase 3 wishlist, **open decisions (OD-nn)**, Chief DS topics | committed | Planning, "what next", sync prep |
| `docs/context/project.md` | Why, where we start → where we want to reach, goals, scope, roles | committed | New to the repo; scope questions |
| `docs/glossary.md` | Vocabulary | committed | Naming anything; unfamiliar term |
| `docs/architecture.md` | Target design, stage map, package layout, Public API | committed | Structural work |
| `docs/decisions.md` | Decision log (D-nnn) | committed | Before designing |
| `docs/components/<c>.md` | One component or versioned artifact, in three levels: summary (≈ 4%), how it fits together (with the summary ≈ 20%), details; template in `docs/components/README.md` | committed | Working on it |
| `docs/context/lessons.md` | Traps (T-nn) and lessons | committed | Before related code |
| `docs/context/environment.md` | Versions and bank behaviour | committed | IO / dependencies |
| `docs/guides/*.md` | How-tos: setup, Claude Code workflow, skills & agents | committed | As needed |
| `worknotes/sync.md` | Sync page for the builder and the Lead DS: what to review, open questions for both, recent developments | committed | Before each sync; `/brief` |
| `worknotes/log.md` | Verbose trail behind the sync page | committed | When detail is needed |
| `worknotes/handovers/<topic>.md` | One chat handover per topic (several in parallel) | committed | Only via `/resume <topic>` |

**Update triggers**

| Trigger | Update |
|---|---|
| Any turn that changed files, settled something or produced a finding | Refresh `worknotes/sync.md` (rules: `worknotes/README.md` → "Writing `sync.md` for the LDS") and append to `worknotes/log.md`. Every time, not only for big changes. Both are read by the Lead DS: keep them clear and short |
| A component's behaviour, interface or design changes | `docs/components/<component>.md` (Status, requirements, Interface, Open questions) |
| A config field is added, changed or removed | `docs/components/config.md` + example in `conf/base/`; §2 procedure if breaking |
| An artifact format changes (card, manifest, scores, ledger, registry, monitoring tables) | The owning component doc + the §2 procedure; run compat-guardian |
| A public function is added or changed | `docs/architecture.md` → Public API |
| A decision is made (pattern, dependency, lifecycle, naming) | `docs/decisions.md`: extend the set row it is heavily adjacent to, else a new row in the high-impact or the low-impact table; a superseding decision replaces the original row in place (same ID; no superseded rows are kept); the log holds every active decision in as few rows as reasonable. `docs/architecture.md` if structure changes |
| A question is opened, answered or parked | `docs/roadmap.md` → Open decisions (add, update or delete the OD row, in the short-term or medium-term table); component-only questions go in that doc's Open questions |
| Work item started / finished / blocked | `docs/UPDATES.md` status table (dated log line if major); milestone/backlog in `docs/roadmap.md` |
| A new term, or a term changes meaning | `docs/glossary.md` first, then use it consistently |
| A new bug class, trap or chart-design lesson | `docs/context/lessons.md` (next T-number); chart rules in `docs/components/reporting.md` |
| An environment fact changes (versions, bank behaviour) | `docs/context/environment.md` + `requirements.txt` |
| A doc is added, renamed or deleted | `docs/README.md` (reading order and/or stage → component map) + `docs/components/README.md` index |
| A new component | New doc from the template via **new-component** + components index + stage map in `docs/README.md` + UPDATES row + roadmap backlog |
| A new skill, agent or command | §10 + `docs/guides/skills_and_agents.md` |
| Scope, goals, priorities or roles change | `docs/context/project.md` (+ `docs/roadmap.md` if phasing changes) |

**When to create a new doc.** Only when the content has a reader and a lifecycle no existing doc owns:
- a new component or versioned artifact → `docs/components/<name>.md` from the template;
- a how-to people will follow → `docs/guides/<name>.md`;
- a cross-cutting design topic that three or more components depend on → a component-style doc,
  linked from `docs/architecture.md`.

Otherwise extend the owning doc. **Never** create per-task summaries, research notes, meeting notes or
copies of a decision: those go to `worknotes/log.md`, `docs/decisions.md` or the owning doc.

**How to create, rename or delete one.**
- Start with a verdict or status line and a **Related** line.
- Link both ways: the new doc links what it depends on, and the docs that rely on it link back.
- Register it: `docs/README.md` (reading order or stage map), `docs/components/README.md` for
  component docs, the doc map above if it's a new kind of doc.
- When renaming or deleting, grep for every reference and fix them in the same change.

**References.** Relative paths; D-nnn (decisions), OD-nn (open decisions), T-nn (traps), §n (this
file).

**Style.** Verdict first, concise, integrated: edit text in place, don't append "update" sections.
Flag anything unverified. No flowcharts or ASCII diagrams: they don't wrap on small screens. Use a
numbered list for a flow, nested bullets for a tree and a narrow table for a mapping (D-072). No people's names (roles only) and no bank identifiers, including in
`worknotes/`. Run the **doc-sync** skill at the end of every task.

---

## 9. Working with the user

- **Roles.** The user is the senior DS who builds the framework and owns every decision; all design
  flows through them. The Lead DS reviews in a daily ~1h sync (prepare with `/brief`). The Chief DS
  sets direction and leaves the design to the SDS and LDS; topics for the CDS go to
  `docs/roadmap.md` → Chief DS topics (D-073). Downstream operation questions go to the platform /
  MLOps team (D-079). Refer to people by role only.
- **Ask first** before: a new dependency, a public API or schema change, a large refactor, deleting
  anything, or anything that touches the lifecycle tiers.
- **Git.** Commit only when the SDS asks, even locally, and always with a message. Commits go
  straight to main (no branches); push only when asked (D-072).
- **Consult well.**
  - Ask numbered questions (continue the numbering across rounds), each with your proposed default.
    A question that cites a decision or open decision summarises it in brackets, e.g. "D-007
    (shared tables only grow within a major version)", so nobody has to switch files (D-072).
  - For genuine choices, lay out the options with when-to-use guidance and a recommendation.
  - Match the altitude to the phase: directions first, details when that component is designed.
- **Verify, don't assume.** Check library behaviour against the pinned version. Say when something is
  opinion or unverified.
- **Push back** when a request leads to over-engineering or a correctness risk: explain why and offer
  the simpler option. Ruthless-mentor tone, not adversarial.

---

## 10. Skills, subagents and commands (in this repo)

| Kind | Name | Use when |
|---|---|---|
| Skill | `simplicity-review` | Reviewing any diff against §1 before presenting it |
| Skill | `doc-sync` | End of every task — applies §8 |
| Skill | `holistic-review` | Every major step (§1 workflow step 0) and before finalising a plan touching more than one stage |
| Skill | `delegation` | Start of every non-trivial task and every review round: the split, model routing and briefs for subagents (D-072) |
| Skill | `new-component` | Adding a new stage, lifecycle unit or versioned artifact |
| Skill | `bank-parity-check` | New imports/deps, IO code, anything that must run inside the bank |
| Skill | `brainstorming` | New or unsettled design, before the §1 plan (includes research + critique) |
| Skill | `systematic-debugging` | Any bug, test failure or unexpected behaviour, before proposing a fix |
| Skill | `verification-before-completion` | Before claiming anything is done, fixed or passing |
| Skill | `claude-md-improver` / `/revise-claude-md` | Auditing CLAUDE.md or capturing session learnings |
| Command | `/brief` | Before the daily Lead DS sync, or "what happened recently?" |
| Command | `/handover <topic>` / `/resume <topic>` | Moving a long context to a new chat, per topic |
| Subagent | `code-reviewer` | Before declaring any code change done (fresh-context review) |
| Subagent | `silent-failure-hunter` | Changes to error handling, fallbacks, coercion, IO or validation |
| Subagent | `ml-correctness-auditor` | Changes to targets, dataset/splits, features, training, evaluation, calibration, inference |
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
synthetic/src/synthetic/   dev-only synthetic data package: spec/, mechanisms/, truth/, checks/ (not core_modelling)
conf/base/                 committed configs and examples
conf/local/                gitignored: environment-specific paths/tables/theme (bank side)
data/                      gitignored: Kedro-style layered data folders (see data/README.md)
notebooks/                 guided interface notebooks (rules: notebooks/README.md)
tests/                     light tests (policy: tests/README.md)
worknotes/                 sync page + log for the builder and the Lead DS, chat handovers
legacy/propensity_crunch/  crunch implementation — reference only
docs/README.md             reading order + stage → component map (the docs' front door)
docs/UPDATES.md            state + major changes (read first)
docs/roadmap.md            phases, milestones, backlog, open decisions
docs/glossary.md           vocabulary
docs/context/              project.md, environment.md, lessons.md
docs/architecture.md       target design
docs/decisions.md          decision log
docs/components/           one doc per component or versioned artifact
docs/guides/               setup (WSL2 / macOS), Claude Code workflow, skills & agents
docs/reference/            original roadmap + spine/governance reference (historical)
.claude/                   project skills, subagents and commands
```
