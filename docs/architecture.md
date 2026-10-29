# Target architecture (Phase 2)

**Status:** target design. **Nothing below is built yet** unless `docs/UPDATES.md` says so. This file
is the map. When code diverges from it, update this file (`CLAUDE.md` §8). Why the framework exists
and what it aims for: `docs/context/project.md`. Terms: `docs/glossary.md`.

**Verdict:** a versioned Python library of plain functions, driven by one config file per use case.
- Each stage runs alone, from guided notebooks, the CLI or the Python API, and writes its own
  artifacts. EDA and Feature Checks together are a product within the product: a data-analysis
  report in its own right; the other reports are model performance, the model card and monitoring.
- An environment adapter isolates everything bank-specific.
- A three-tier lifecycle (local → registered → production) keeps a large estate of models
  maintainable.

## 1. Framework vs use case

- **Framework** (versioned library, pinned per use case):
  - `src/core_modelling/`: plain functions;
  - guided notebooks: interface + learning;
  - CLI + Python API: automated / production runs.
- **Use case** (one modelling problem):
  - one config file (the intent, per-entity instances inside) and its decision audit log (D-006);
    a repo may hold several similar use cases (which repos: OD-02);
  - extension functions, only at named points (mostly Target Factory), in the repo that holds the
    use case;
  - its own copies of the guided notebooks, to explore in.

There is no service layer (D-024). Each use case pins the framework version it runs with, upgrades
at its own pace, and scores its models with that version (D-047). Many versions therefore write to
the same shared tables at once, so a new version must not break use cases or those tables
(`CLAUDE.md` §2). The package ships in the base image through Nexus, so the image a use case starts
on sets its default version, which the use case pins and may raise within the image's year
(D-024). Still open: where use cases live (OD-02) and the release mechanics (OD-04).

## 2. Stages

Every stage can be called alone from a config and writes its own artifacts. An end-to-end run calls
them in order (D-028).

| Stage | Consumes | Produces | Doc |
|---|---|---|---|
| **target_factory** (optional) | The target source (or a feature source's column) | Targets + target lineage, passed on in memory or saved with the joined sources as the model input, one table for one or several use cases (D-131); labels for scored periods, for monitoring (M4) | [target_factory](components/target_factory.md) |
| **eda** | Data definition (entity, sources, eligibility, target spec, observation window, candidates) | EDA report; ledger columns (univariate ranking, key features) | [eda](components/eda.md) |
| **feature_checks** | Same + EDA ledger | Check log, flags, proposed decisions, ledger columns, report | [feature_checks](components/feature_checks.md) |
| **training** | Resolved features + train split | Local-tier run: model bundle, selection in the ledger, training metadata, drift reference (no refit on more data in Phase 2, D-052) | [training](components/training.md) |
| **evaluation** | Model + test + OOT validation + baselines | Metrics (overall and stratified), views, comparisons, card sections, report | [evaluation](components/evaluation.md) |
| **register** | Local run + the feature sign-off (its one gate, D-033) | Registered version (immutable, hashed) | [lifecycle](components/lifecycle.md) |
| **promote** | Registered version + approved PR | Promotion record + verified deployment bundle | [lifecycle](components/lifecycle.md) |
| **deploy** | Promoted bundle, run by the change-request process | Production copy (by default retrained on the same data definition before it scores, D-052) + production record | [lifecycle](components/lifecycle.md) |
| **inference** | Production (or pinned registered) model + a period | Batch-scoped scores + manifest | [inference](components/inference.md) |
| **monitoring** | Scores, inputs, drift reference, matured labels, baselines | Monitoring tables + report, fed to the data observability framework (D-021) | [monitoring](components/monitoring.md) |

**Cross-cutting pieces:**
- [config](components/config.md)
- [dataset](components/dataset.md): observation window, frames, the model input, splits, sampling
- [feature ledger](components/feature_ledger.md)
- [reporting](components/reporting.md)
- [environment adapter](components/environment.md)
- [run modes](components/run_modes.md)
- [synthetic data](components/test_harness.md) (dev only)

**Due-diligence gate (§4.13):** training requires EDA and Feature Checks artifacts for the same
data-definition hash. The `autonomous` level runs them automatically (D-031). A person signs off
the final feature list after training and before any model is registered: one gate, at every
automation level (D-031).

**Integrations (first release, D-021):** the feature store upstream, limited in Phase 2 to Stage 1
(M2.1 Foundation), where a use case's data comes in, so no later stage knows about it (alone or with other sources,
OD-26), and the data observability framework downstream, whose needs shape the monitoring tables
only once we have seen it in use (OD-13); both thin.

## 3. Config

- **One config file per use case** (unless it bloats, D-043), plus its decision audit log (D-006),
  written in YAML and validated by Pydantic v2; the Pydantic model is the programmatic API. It
  carries `schema_version`, `task`, `automation_level` and `decision`. Shared sections
  (`decision`, `entities`, `data`, `time`, `features`, `strata`) plus one section per stage, every
  section validated from Stage 1 with the level's defaults (D-129). Details:
  [config](components/config.md).
- **Shared tables** (registry, scores, monitoring, model cards, labels) are written and read by
  many pinned versions at once (D-047), so they follow one rule (D-007): every row carries
  `schema_version` and `framework_version`; within a major version columns are only added
  (nullable), never renamed, retyped or removed; readers select columns by name and ignore
  unknown ones; removal only at a major bump, which keeps old readers for one image lifetime.
  The promise is about outputs (D-007): what a version writes or saves (shared tables, configs,
  bundles, other artifacts) stays similar and readable, while internals change freely. The 0.x
  pre-release writes only to sandpit and local paths; shared formats freeze from the first row
  release 1.0 writes inside the bank.
- **`conf/base/`** is committed and holds the use-case configs, the template and the environment
  file's example. **`conf/local/environment.yml`** is gitignored and holds the environment facts
  only, under its own schema (Spark settings, roots, the physical sources per entity, the collect
  budget, the theme). It is loaded beside the config, never merged into it, and sits outside every
  hash (D-130; [environment](components/environment.md)).
- **The model input:** one saved table per name (`data.model_input`), written from Target
  Factory's notebook or `run a.yml b.yml --stages target_factory` for one or several use cases
  that share the entity's feature sources, keys and period: the sources joined plus one target
  column per use case, nothing else; eligibility, the candidates, the contract checks and the
  client split are derived on read from each reader's config, so a change to them keeps the
  table. Its sidecar is keyed by the shared sources, keys and period plus each use case's
  target-spec hash, never by the data-definition hash; without the field the frames are built
  in memory (D-131; [dataset](components/dataset.md#model-input-d-131)).
- **Automation levels** (`autonomous` / `assisted`; `manual` later) set defaults for every
  stage (D-023); a level changes through a config edit or an audit-log entry, never a CLI
  override; what each level decides by rule and by a person is D-132 (the table in
  [config](components/config.md)). The **decision** drives the metric, the gates and what reports
  emphasise (D-032).
- **Stepwise sections:** eligibility and feature checks are ordered lists of named steps, and each
  step logs rows/columns in → out and the reason. The feature ledger carries the per-feature trail.
- **Resolved config:** the config with the audit-log entries replayed, saved with every artifact
  and report as plain data, with a housekeeping block (framework and library versions, time,
  identities). Reports and reproduction use only resolved configs, and `recipe_hash` covers it.
  The config itself (the intent) freezes in its data part (sources, keys, period, target spec,
  target window) once the model input is saved, or at the first EDA run when the frames are
  built in memory; eligibility, the observation window and the candidates change only by a new
  config, which reruns EDA onwards but keeps the saved table. Every later decision, by a person
  or a rule, is an append-only entry in the decision audit log (a `revert` entry goes back to
  an earlier state without deleting anything), and replaying the config plus entries 1–n gives
  a run's resolved input; the log never changes the data definition
  (D-125; design in [config](components/config.md#decision-audit-log-d-125)).
- Breaking a schema follows `CLAUDE.md` §2 (version bump + migration + test).

## 4. Time model and splits

The unit of analysis is a **period** (`time.period`: month, week or day; one row per unit per
period, held as its last day, D-129). Train and test are all eligible unit-periods in the
observation window `t1 … tk`, split by client. Validation is the OOT period `v ≥ tk + w`, so its
target window never overlaps a training target window. Inference periods come after `v`. The
full timeline, span by span, is owned by [dataset](components/dataset.md#time-model).

Features are as-of each observation period; targets look forward `(1, w)` periods. Validation is
a single period for panel tasks (series tasks will need rolling validation). EDA uses every
client of the window after the analysis filters and Feature Checks every eligible client, labels
included, and label-based views never show periods after it; the
train/test client split happens after Feature Checks, and from Training on, fitting, automated
selection, calibration and every choice use train-split clients only. Label-free comparisons may
use later periods except `v` (D-030). The cost, stated in the model results report: feature
decisions in EDA and Feature Checks have seen test clients' labels, so `v` stays the one honest
number. The window's effects on every
stage are tabulated in [dataset](components/dataset.md).

## 5. Model lifecycle

`training → LOCAL → register → REGISTERED → promote → deploy → PRODUCTION`. Inference reads
production (or a pinned registered version); local models only in dev mode. Gates, sign-off, the
change-request path and the open questions are owned by [lifecycle](components/lifecycle.md).

- **Identities** (D-052, D-088, D-094; the worked example is in [config](components/config.md)):
  - config hash = the use-case definition after level resolution, without the environment file
    and the housekeeping block; decisions in the audit log leave it unchanged
  - `data_definition_hash` = `task`, entity, sources, eligibility, target spec, the period, the
    observation window, the target window and candidates (the target-spec hash carries `task`
    too, so an upstream column read as binary and as regression never shares a digest); the
    validation period is set in the
    config but sits outside this hash, and changing it after the config freezes is an audit-log
    entry, refused when Feature Checks compared that period; the inference period is a run
    argument (D-088)
  - resolved-input hash = the config plus entries 1–n of the audit log, resolved (D-125)
  - `run_id` = resolved-input hash + entity + timestamp (one per instance)
  - `feature_signature` = hash of the final feature list
  - `recipe_hash` = resolved config + features + hyperparameters + encoder levels + calibration spec
  - `model_hash` = a hash over the bundle's per-part hashes (encoder, model, calibration with the
    prior-shift offset, metadata); a retrain in production is one more fit of a recipe, linked to
    its evaluated parent by `parent_run_id`
  - model key = (entity, domain, use case, split), with split = `all` in Phase 2
  - `scoring_batch_id`
  - code version = framework version + use-case repo commit
  - every hash is computed on the migrated canonical form and stored with a `hash_version`
- **The model bundle is a versioned artifact:** every part as plain data, JSON where possible;
  what is promoted is never pickle, while the sandpit (the local and registered tiers) may save any
  format. `register` always writes the lossless plain-data model too, so every registered version
  stays promotable without unpickling, and `promote` takes it (D-051).
- **Retraining in production is the default deploy path in Phase 2** (D-033, D-052): `promote`
  carries the recipe, and production refits it on the same data definition (neither more clients
  nor a longer window) before it scores, so the parameters differ only because production data
  differs from sandpit data; deploying the fitted model without a retrain is also allowed. A
  Phase 2 production retrain keeps the window and the clients; only the inference period moves,
  since inference always runs on the latest period. Before it scores, it passes the production
  retrain check against its evaluated parent (label-free agreement on the inference period, its
  test-split AUC and calibration per window period, and per-period rows and positive events
  against the parent's EDA artifact, within tolerances declared in the config, never on the
  validation period); failing
  keeps whatever production model is current and is recorded, and at a first deploy the deploy
  fails loud. There is no refit command in the
  sandpit. Retraining on moved or extended data (later periods, all clients, a longer window)
  comes later (D-052). Whether production has the data and compute, determinism and what
  "deployed" records stay open with the platform / MLOps team in M4 (OD-27).
- **A DS session never writes to production** (D-033).
- **Manifests** link a scoring batch to the models that produced it (`run_id` + `model_hash`).
  Reproduction verifies the hash before loading.
- Production paths are separate from the sandpit (D-033, D-051); the folder layout per entity ×
  domain is open (OD-06), so path construction stays in the environment adapter.

## 6. Baselines and monitoring

- Baselines are declared in config before results: `population_base_rate` (default; the standard for
  business reporting), `previous_model`, `historic_predicted_rate`.
- Training saves a **drift reference** computed on the true population, and Target Factory builds
  labels for scored periods (D-054).
- Monitoring has four layers (D-040). Phase 2 builds their frame properly and keeps the content
  light (D-040):
  - operational health and input/score drift: a deep frame, a few measures with flags;
  - realised performance against baselines: thin, built so it works as soon as outcomes exist;
  - business impact: a stub.

  Monitoring outputs feed the data observability framework (D-021); tooling and dashboards are the
  platform / MLOps team's (D-079). Details: [monitoring](components/monitoring.md).

## 7. Run modes

- **Interactive:** guided notebooks, one per stage. They load the config, call the stage and display
  its artifacts. Users may copy them and explore; production never depends on notebook code (D-039).
- **Automated / production:** `python -m core_modelling run <config> [<config> …] [--stages …]`
  (several configs share one model input, D-131; an empty list is refused, and without an
  entity argument so are configs whose entity lists differ) and the matching Python API, plus
  separate `register`, `promote` and `deploy` commands, and `decide`, which records a person's
  decision,
  the feature sign-off (D-031) and a `revert` included, as an audit-log entry (D-125).
  Scheduling, if any, calls the CLI.
- **Experiment sweeps:** run one config with a single field varied (e.g. the observation window) and
  compare the variants on the same validation set. A sweep that picks a variant picks on train and
  test metrics, weighted; the validation period is reported, never chosen on (D-083): in Phase 2
  reports show it everywhere, sweep tables included, and people are trusted not to choose on it.
  The same mechanism is what the LLM branch will later drive. Details: [run modes](components/run_modes.md),
  [dataset](components/dataset.md).

## 8. Generality without frameworks

- **Task:** every task-specific hook (target builder, EDA ranking, leakage screen, selection rule,
  contract checks, baselines, metrics, views, calibration, output columns…) lives in one per-task
  spec dict keyed by `task` (D-050). Panel tasks come first: binary and regression in Phase 2 (D-020). Unbuilt tasks fail with a
  clear "not implemented".
- **Domains, entities, sources:** configuration only; never names in code; no data merged across
  entities (D-034).
- **Scale:** Spark prunes and samples, training is single-node on the collected sample, and scoring
  runs in Spark ([dataset](components/dataset.md) explains when that stops being enough).
- **Defaults:** the automation level and the declared decision drive defaults explicitly;
  population size and positive rate inform them, with no hidden magic.

## 9. Reports

The stages that write reports (EDA, Feature Checks, the model results in Evaluation and Monitoring,
plus the model card; D-036) render through one shared writer as self-contained HTML (pandas Styler
tables + plotly with embedded plotly.js). Each report has a summary page with a choices block, then
core views, extended views ("not available: reason" where a view is incompatible) and an appendix;
the core views per task of the EDA, Feature Checks and Evaluation reports are OD-12. Chart axes
follow the data. Details: [reporting](components/reporting.md), [evaluation](components/evaluation.md).

## 10. Environment adapter

One module owns:
- the Spark session
- the compat shim
- the transport (filesystem vs `hdfs dfs`; M2.4)
- path construction, per tier and entity
- source resolution per entity (logical source → a parquet path or table, or the feature store:
  OD-26)
- the report theme location

Everything it needs comes from the environment file, `conf/local/environment.yml`, loaded beside
the config under its own schema (D-130). Framework code calls only its functions. On a laptop the
environment file points the logical sources at the synthetic dataset. See
[environment](components/environment.md) and
[`docs/context/environment.md`](context/environment.md).

## 11. Package layout

Stage 1 (M2.1) builds the first part; the rest is proposed and confirmed as each component is
built.

- `src/core_modelling/`
  - `__init__.py`: version
  - `__main__.py`: CLI entry: `run` and `decide` (Stage 1); `register`, `promote`, `deploy` later
    (§7; [run modes](components/run_modes.md) owns the list)
  - `_compat.py`: numpy/PySpark compat shim, imported first by `__init__.py` (T1)
  - `environment.py`: the environment file's schema, `get_spark_session`, source reading, paths
  - `config/`: `schema.py` (the Pydantic models, one per section), `levels.py` (`LEVEL_DEFAULTS`),
    `migrations.py`, `identities.py` (the hashes), `replay.py` (the entry model, the
    operations, replay), `audit_log.py` (storage, `record_decision`, `show_decisions`,
    `resolve_config`)
  - `periods.py`: `PERIODS`, the unit of analysis (month, week, day: index, start, end, label);
    `label_by_period` and `period_labels`, the per-period dicts every log entry uses
  - `tasks.py`: `TASK_SPECS`, the per-task spec (the target rules, the target-column check, the
    target summary and the contract checks in Stage 1)
  - `sources.py`: `KEYS` and `HELPER_COLUMNS` (`target`, `split`, `eligible`);
    `read_keyed_source`, a logical source with its keys renamed (`unit_id` as a string, a
    non-key column named like a key read as `source_<name>`) and its periods at their end;
    `rename_reserved`, the one naming rule for such clashes; Target Factory, the dataset and
    Inference all read through it (D-129)
  - `target_factory.py`: `build_targets`, `load_targets`, `target_lineage`, `run_target_factory`
  - `dataset/`: `panel.py` (the build side: sources joined, one target column per use case; the
    read side, `prepare_panel`: eligibility, candidates, contract, split), `eligibility.py`
    (who is in: the eligibility steps, the modelling tags, the candidates), `split.py` (the
    client split and sampling), `contract.py` (the contract checks), `frames.py` (`Frames`, the
    collect with its printout), `model_input.py` (the model input saved and read)
  - `run.py`: `run`, `STAGES`
  - `eda/`: population/target profile, univariate ranking, key features, pivots
  - `feature_checks/`: check steps, stability, lineage guard
  - `ledger.py`: feature ledger (create, append, resolve the final feature list)
  - `training/`: model interface, AutoML path (FLAML), automated selection, categorical encoding,
    calibration; the predefined path (Optuna) later
  - `evaluation/`: metrics by task, stratified metrics, baselines, view slots, comparison
  - `lifecycle/`: register, promote, deploy, registry records
  - `inference/`: scoring, batch outputs, manifests
  - `monitoring/`: health, drift, outcome joins, impact vs baselines
  - `reporting/`: HTML writer, plotly charts, styled tables, model card, themes
- `conf/base/`: `cc_acquisition.yml`, `TEMPLATE.yml`, `environment.example.yml`
- `synthetic/`: dev-only synthetic data package (top level; not part of `core_modelling`)

A folder becomes a single module file when it only needs one. Don't create empty sub-packages ahead
of need. A package with more than a handful of modules splits them into role subfolders (rules as
plain data, functions, checks), as `synthetic/` does (`CLAUDE.md` §1 rule 5, D-003).

## Public API

Public = the stage functions, `run`, the CLI commands, the config schema, the decision audit log's
functions and the environment adapter's Spark-session function (D-024). The shipped notebooks call
only these, which a small test checks against the table below. Everything else is
private (`_name`). Only what is listed here is public and covered by `CLAUDE.md` §2: from release
1.0 a public function's signature and return shape change only after one minor version of
deprecation; in 0.x they change freely (D-007 (c)). The table is filled in as it is built.

Stage 1 (M2.1) makes these public (D-024): `load_config`, `load_environment`,
`get_spark_session`, `run_target_factory`, `build_frames`, `save_model_input`,
`record_decision`, `show_decisions`, `resolve_config`, `read_resolved_config` and `run`, plus the
CLI commands `run` and `decide`; the table lists them all (Stage 1 is built, 2026-10-27). Planned beyond Stage 1: one function per later stage and the CLI
commands `register`, `promote` and `deploy`. Signatures: [config](components/config.md#interface),
[environment](components/environment.md#interface),
[target factory](components/target_factory.md#interface), [dataset](components/dataset.md#interface).
The frames and the model input are what a DS explores in a notebook copy, which is why
`build_frames` and `save_model_input` are public.

| Function | Module | Since |
|---|---|---|
| `load_config`, `UseCaseConfig` | `core_modelling.config` | 0.2.0 (Stage 1) |
| `load_environment`, `get_spark_session` | `core_modelling.environment` | 0.2.0 (Stage 1) |
| `record_decision` (`revert_to` as the fifth operation), `show_decisions`, `resolve_config`, `read_resolved_config` | `core_modelling.config.audit_log` | 0.2.0 (Stage 1) |
| CLI `decide` (`--revert-to N`) | `python -m core_modelling decide` | 0.2.0 (Stage 1) |
| `run_target_factory` (per config) | `core_modelling.target_factory` | 0.2.0 (Stage 1) |
| `build_frames`, `save_model_input` (one config or a list), `Frames` | `core_modelling.dataset` | 0.2.0 (Stage 1) |
| `run` (one or several config paths) | `core_modelling.run` | 0.2.0 (Stage 1) |
| CLI `run` (one or several configs) | `python -m core_modelling run` | 0.2.0 (Stage 1) |

## Artifact inventory

Every artifact a version writes, with its version field, who writes and reads it and the
compatibility rule (D-007 (d)); each carries its version field from its first version. Built
rows are Stage 1's; the rest join as their stages are built (the formats are in their owner
docs).

| Artifact | Owner doc | Version field | Written by | Read by | Rule |
|---|---|---|---|---|---|
| Use-case config | [config](components/config.md) | `schema_version` | the DS | every stage | migrated `dict → dict` at load; an older version loads with a warning, a newer one fails loud |
| Environment file | [environment](components/environment.md) | `schema_version` | the platform / the DS | every stage | as the config |
| Audit log entry | [config](components/config.md) | `log_schema_version`, `hash_version` | `record_decision`, later the stages | `resolve_config`, `show_decisions` | append-only; another version fails naming the file; an entry under another data definition fails |
| Resolved config | [config](components/config.md) | `schema_version` (the config's) + `housekeeping.hash_version` | `resolve_config` | every stage after Target Factory, the reports | read back as is through `read_resolved_config` |
| Model input (`_model_input.json` + the parquet table) | [dataset](components/dataset.md) | `schema_version` (`MODEL_INPUT_SCHEMA_VERSION`, 3), `hash_version` | `save_model_input` (Target Factory), for one or several use cases (an empty list refused) | every later stage, the audit log's feature decisions | refused on another schema or hash version, other sources, keys or period, a use case the table lacks, another target spec, uncovered periods or a validation period whose target window reaches beyond the saved target source's last period: rebuild with `save_model_input` (the migration until 1.0); not refused on a changed eligibility, window, split or candidate list, which are derived on read (D-131) |
| Model bundle, model card, manifest, scores, feature ledger, drift reference, registry records, monitoring tables | their owner docs | `schema_version` (+ `framework_version` on shared-table rows) | their stages (M2.2–M2.4, M4) | later stages, monitoring | D-007 (b): rows only gain nullable columns within a major version |

## Data folders

`data/` keeps the Kedro-style numbered layers as a naming convention (no Kedro dependency). See
`data/README.md`.
