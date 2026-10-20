# Target architecture (Phase 2)

**Status:** target design. **Nothing below is built yet** unless `docs/UPDATES.md` says so. This file
is the map. When code diverges from it, update this file (`CLAUDE.md` §8). Why the framework exists
and what it aims for: `docs/context/project.md`. Terms: `docs/glossary.md`.

**Verdict:** a versioned Python library of plain functions, driven by one config file per use case.
- Each stage runs alone, from guided notebooks, the CLI or the Python API, and writes its own
  artifacts and HTML report.
- An environment adapter isolates everything bank-specific.
- A three-tier lifecycle (local → registered → production) keeps a large estate of models
  maintainable.

## 1. Framework vs use case

- **Framework** (versioned library, pinned per use case):
  - `src/core_modelling/`: plain functions;
  - guided notebooks: interface + learning;
  - CLI + Python API: automated / production runs.
- **Use case** (one modelling problem):
  - one config file: the whole definition, per-entity instances inside;
  - extension functions, only at named points (mostly Target Factory);
  - its own copies of the guided notebooks, to explore in.

There is no service layer (D-024). Each use case pins the framework version it runs with, upgrades
at its own pace, and scores its models with that version (D-047). Many versions therefore write to
the same shared tables at once, so a new version must not break use cases or those tables
(`CLAUDE.md` §2). The package ships in the base image through Nexus, so the image a use case starts
on pins its version (D-074). Still open: where use cases live (OD-02) and the release mechanics
(OD-04).

## 2. Stages

Every stage can be called alone from a config and writes its own artifacts. An end-to-end run calls
them in order (D-028).

| Stage | Consumes | Produces | Doc |
|---|---|---|---|
| **target_factory** (optional) | Source table(s) or the feature store | Targets + target lineage (saved, or passed on in memory); labels for scored months, for monitoring | [target_factory](components/target_factory.md) |
| **eda** | Data definition (entity, source, eligibility, target, time, candidates) | EDA report; ledger columns (univariate ranking, key features) | [eda](components/eda.md) |
| **feature_checks** | Same + EDA ledger | Check log, flags, proposed decisions, ledger columns, report | [feature_checks](components/feature_checks.md) |
| **training** | Resolved features + train split | Local-tier run: model bundle, selection in the ledger, training metadata, drift reference; optionally a refit linked to it (D-052) | [training](components/training.md) |
| **evaluation** | Model + test + OOT validation + baselines | Metrics (overall and stratified), views, comparisons, card sections, report | [evaluation](components/evaluation.md) |
| **register** | Local run + gates | Registered version (immutable, hashed) | [lifecycle](components/lifecycle.md) |
| **promote** | Registered version + approved PR | Promotion record + verified deployment bundle | [lifecycle](components/lifecycle.md) |
| **deploy** | Bundle, run by the change-request process | Production copy + production record | [lifecycle](components/lifecycle.md) |
| **inference** | Production (or pinned registered) model + a month | Batch-scoped scores + manifest | [inference](components/inference.md) |
| **monitoring** | Scores, inputs, drift reference, matured labels, baselines | Monitoring tables + report, fed to the data observability framework (D-075) | [monitoring](components/monitoring.md) |

**Cross-cutting pieces:**
- [config](components/config.md)
- [dataset](components/dataset.md): observation window, splits, sampling
- [feature ledger](components/feature_ledger.md)
- [reporting](components/reporting.md)
- [environment adapter](components/environment.md)
- [run modes](components/run_modes.md)
- [synthetic data](components/test_harness.md) (dev only)

**Due-diligence gate (§4.13):** training requires EDA and Feature Checks artifacts for the same
data-definition hash. Hands-off profiles run them automatically (D-031). A person signs off the
feature list before any model is registered, at every automation level (D-076).

**Integrations (first release, D-075):** the feature store upstream (alone or with other sources,
OD-26) and the data observability framework downstream (OD-13), both thin.

## 3. Config

- **One file per use case** (the goal, D-043), validated by Pydantic v2. YAML for now; Python
  files are under study (OD-24). It carries
  `schema_version`, `task`, `profile` and `decision`. Shared sections (entities, data, time,
  features) plus one section per stage. Details: [config](components/config.md).
- **`conf/base/`** is committed and holds framework defaults and generic use-case configs.
  **`conf/local/`** is gitignored and holds environment-specific values (tables, paths, Spark, theme).
  They merge base → local at load.
- **Profiles** (`quick` / `standard` / `thorough`) set defaults for every stage (D-023); they are
  to become automation levels, from fully autonomous to fully manual (D-077, OD-25). The
  **decision** drives the metric, the gates and what reports emphasise (D-032).
- **Stepwise sections:** eligibility and feature checks are ordered lists of named steps, and each
  step logs rows/columns in → out and the reason. The feature ledger carries the per-feature trail.
- **Frozen config:** the fully resolved config saved with every artifact, as plain data, with a
  housekeeping block (framework and library versions, time, identities). Reports and reproduction
  use only frozen configs. The config is never edited after the fact: decisions taken downstream go
  to a decision audit log (direction, OD-10).
- Breaking a schema follows `CLAUDE.md` §2 (version bump + migration + test).

## 4. Time model and splits

Train and test are all eligible unit-months in the observation window `t1 … tk`, split by client.
Validation is the OOT month `v ≥ tk + w`, so its target window never overlaps a training target
window. Inference months come after `v`. The full timeline, period by period, is owned by
[dataset](components/dataset.md#time-model).

Features are as-of each observation month; targets look forward `(1, w)`. Validation is a single
month for panel tasks (series tasks will need rolling validation). Checks that use labels see
train-split clients within the window only; label-free comparisons may use later months except `v`
(D-048). The window's effects on every
stage are tabulated in [dataset](components/dataset.md).

## 5. Model lifecycle

`training → LOCAL → register → REGISTERED → promote → deploy → PRODUCTION`. Inference reads
production (or a pinned registered version); local models only in dev mode. Gates, sign-off, the
change-request path and the open questions are owned by [lifecycle](components/lifecycle.md).

- **Identities:**
  - `run_id` = config hash + timestamp
  - `model_hash` = content hash of the model file
  - `feature_signature` = hash of the final feature list
  - `data_definition_hash` (see [config](components/config.md))
  - model key = (entity, domain, use case, split), with split = `all` in Phase 2
  - `scoring_batch_id`
  - code version = framework version + use-case repo commit
- **The model bundle is a versioned artifact:** every part as plain data, JSON where possible,
  never pickle (D-051, D-078).
- **Retraining in production** (promote the recipe, production retrains it) is under study
  (OD-27).
- **A DS session never writes to production** (D-033).
- **Manifests** link a scoring batch to the models that produced it (`run_id` + `model_hash`).
  Reproduction verifies the hash before loading.
- The bank-side layout is still evolving (OD-06), so path construction stays in the environment
  adapter.

## 6. Baselines and monitoring

- Baselines are declared in config before results: `population_base_rate` (default; the standard for
  business reporting), `previous_model`, `historic_predicted_rate`.
- Training saves a **drift reference** computed on the true population, and Target Factory builds
  labels for scored months (D-054).
- Monitoring has four layers (D-040):
  - operational health and input/score drift: deep in Phase 2;
  - realised performance against baselines and business impact: thin in Phase 2, built so they work
    as soon as outcomes exist.

  Monitoring outputs feed the data observability framework (D-075); tooling and dashboards are the
  platform / MLOps team's (D-079). Details: [monitoring](components/monitoring.md).

## 7. Run modes

- **Manual:** guided notebooks, one per stage. They load the config, call the stage and display its
  artifacts. Users may copy them and explore; production never depends on notebook code (D-039).
- **Automated / production:** `python -m core_modelling run <config> [--stages …]` and the matching
  Python API, plus separate `register`, `promote` and `deploy` commands, and an entry point for the
  feature sign-off (D-076; how it is recorded: OD-10). Scheduling, if any, calls
  the CLI.
- **Experiment sweeps:** run one config with a single field varied (e.g. the observation window) and
  compare the variants on the same validation set. A sweep that picks a variant labels the winner's
  validation result as optimistic (D-053). The same mechanism is what the LLM branch will later
  drive. Details: [run modes](components/run_modes.md), [dataset](components/dataset.md).

## 8. Generality without frameworks

- **Task:** every task-specific hook (target builder, EDA ranking, leakage screen, selection rule,
  contract checks, baselines, metrics, views, calibration, output columns…) lives in one per-task
  spec dict keyed by `task` (D-050). Panel tasks come first: binary and regression in Phase 2 (D-080). Unbuilt tasks fail with a
  clear "not implemented".
- **Domains, entities, sources:** configuration only; never names in code; no data merged across
  entities (D-034).
- **Scale:** Spark prunes and samples, training is single-node on the collected sample, and scoring
  runs in Spark ([dataset](components/dataset.md) explains when that stops being enough).
- **Defaults:** profiles and the declared decision drive defaults explicitly; population size and
  positive rate inform them, with no hidden magic.

## 9. Reports

Every stage renders through one shared writer as self-contained HTML (pandas Styler tables + plotly
with embedded plotly.js). Each report has a summary page with a choices block, then core views,
extended views ("not available: reason" where a view is incompatible) and an appendix. Chart axes
follow the data. Details: [reporting](components/reporting.md), [evaluation](components/evaluation.md).

## 10. Environment adapter

One module owns:
- the Spark session
- the compat shim
- the transport (filesystem vs `hdfs dfs`)
- path construction, per tier and entity
- table resolution (logical source → physical table, or the feature store: OD-26)
- the report theme location

Framework code calls only its functions. On a laptop, `conf/local/` points the logical sources at the
synthetic dataset. See [environment](components/environment.md) and
[`docs/context/environment.md`](context/environment.md).

## 11. Proposed package layout (to confirm as components get built)

- `src/core_modelling/`
  - `__init__.py`: version
  - `__main__.py`: CLI entry (`run <config>`)
  - `config/`: schema, loading (base+local merge), profiles, migrations
  - `_compat.py`: numpy/PySpark compat shim, imported first by `__init__.py` (T1)
  - `environment.py`: Spark session, transport, paths, sources
  - `dataset.py`: observation window, eligibility, splits, sampling, collection
  - `target_factory/`: target builders by task (extension point), lineage
  - `eda/`: population/target profile, univariate ranking, key features, pivots
  - `feature_checks/`: check steps, stability, lineage guard
  - `ledger.py`: feature ledger (create, append, resolve the final feature list)
  - `training/`: model interface, AutoML path (FLAML), predefined path (Optuna, Phase 3), automated
    selection, categorical encoding, calibration
  - `evaluation/`: metrics by task, stratified metrics, baselines, view slots, comparison
  - `lifecycle/`: register, promote, deploy, registry records
  - `inference/`: scoring, batch outputs, manifests
  - `monitoring/`: health, drift, outcome joins, impact vs baselines
  - `reporting/`: HTML writer, plotly charts, styled tables, model card, themes
- `synthetic/`: dev-only synthetic data package (top level; not part of `core_modelling`)

A folder becomes a single module file when it only needs one. Don't create empty sub-packages ahead
of need.

## Public API

Filled in as it is built. Only functions listed here are public and covered by `CLAUDE.md` §2.

| Function | Module | Since |
|---|---|---|
| *(none yet)* | | |

## Data folders

`data/` keeps the Kedro-style numbered layers as a naming convention (no Kedro dependency). See
`data/README.md`.
