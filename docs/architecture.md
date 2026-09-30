# Target architecture (Phase 2)

**Status:** target design — **nothing below is built yet** unless `docs/UPDATES.md` says so. This
file is the map. When code diverges from it, update this file (see `CLAUDE.md` §8).

**Verdict:** a small installable package of plain functions, driven by versioned configs.
- It runs as standalone stages, from notebooks or the CLI.
- An environment adapter isolates everything bank-specific.
- A three-tier model lifecycle makes 50–100 live models maintainable.

## 1. Framework vs use case

```
framework (this package, updated centrally)         use case (per modelling problem)
─────────────────────────────────────────          ─────────────────────────────────
src/core_modelling/  plain functions                conf/…/<use_case>.yaml  (the whole definition)
standard notebooks   thin interface                 extension functions — only where allowed
CLI + Python API     automated runs                 (mostly Data Creation)
```

A use case contains configs and, rarely, a small extension function registered at a named
extension point. This split is what makes central updates possible, whether distribution ends up as
a service or a forkable template.

## 2. Stages (standalone units)

Each stage is callable alone from a config and writes its own artifacts. The end-to-end run just
calls them in order.

| Stage | Consumes | Produces |
|---|---|---|
| **data_creation** | Raw monthly panel | Enriched panel with targets and rollup features (one table, many use cases) |
| **eda** | Panel slice for the use case | Analyst-grade profile and report (tables + plots + narrative sections) |
| **feature_checks** | Panel slice + candidates | Stepwise screening log, flag tables, proposed exclusions |
| **training** | Vetted features + training month | Model + training artifacts in the **local** tier |
| **evaluation** | Model + OOT month + baselines | Metrics, slices, stability, explainability, model card sections |
| **promotion** | Local run + gates | **Registered** model (immutable, hashed) |
| **deployment** | Registered model | **Production** pointer (what scheduled inference uses) |
| **inference** | Registered/production model + a month/table | Batch-scoped scores + manifest |
| **tracking** | Scores + matured labels + baselines | Realised performance and impact vs baselines; drift |

## 3. Config

- YAML validated by Pydantic v2. Every config has **`schema_version`** and **`task`**.
- **`conf/base/`** is committed: framework defaults and use-case configs with placeholders.
  **`conf/local/`** is gitignored: environment-specific values (paths, tables, Spark settings).
  They merge base → local at load.
- **Stepwise sections.** Filtering and selection are ordered lists of named steps. Each step
  records rows/columns in, rows/columns out, and the reason. That becomes the traceable decision log
  for EDA, Feature Checks and eligibility.
- **Frozen config:** the fully resolved config saved with every artifact. Reports and reproduction
  use only frozen configs.
- Breaking a schema follows `CLAUDE.md` §2 (version bump + migration + test).

## 4. Model lifecycle

```
training ──► LOCAL (many experimental runs, cheap, disposable)
               │  promotion: gates = complete card, OOT pass vs declared baseline, contract ok
               ▼
            REGISTERED (immutable, content-hashed, on HDFS inside the bank)
               │  deployment: explicit, recorded, reversible
               ▼
            PRODUCTION (pointer per use case → one registered model)
inference: reads REGISTERED/PRODUCTION only; writes <outputs>/<scoring_batch_id>/{scores, manifest}
```

- **Identities:**
  - `run_id` = config hash + timestamp
  - `model_hash` = content hash of the model file
  - `feature_signature` = hash of the feature list
  - `scoring_batch_id` = timestamp
- **Manifests** link a scoring batch to the registered models (by `run_id` + `model_hash`).
  Reproduction verifies the hash before loading.
- The folder layout inside the bank is still evolving. Keep path construction in one place (the
  environment adapter) so the layout can change without touching logic.

## 5. Baselines and tracking

- Baselines are declared in config before results:
  - `population_base_rate` — the default, and the standard for business reporting.
  - `previous_model` — the prior registered model's scores.
  - `historic_predicted_rate` — historic baselining.
- Tracking joins scores to matured labels later (propensity outcomes mature over weeks or months).
  It reports realised lift/precision in the targeted slices against the baselines, plus input drift
  meanwhile.

## 6. Run modes

- **Manual:** standard notebooks per stage. Import, call one function per step, display. Switch the
  config and rerun.
- **Automated:** `python -m core_modelling run <config> [--stages …]` and the equivalent Python API.
- **Service-style** (HTTP/scheduler) comes later, as a thin layer over the same API.

## 7. Generality without frameworks

- **Task:** metrics, calibration and output schemas dispatch through plain dicts keyed by `task`.
  Only `binary` has implementations; others fail with a clear "not implemented" message.
- **Scale:** population size and positive rate drive defaults (sampling, top-k slices, CV folds)
  through explicit config, not magic.
- **Segment:** no segment names in code. Segments are configs and data.

## 8. Environment adapter

One module owns:
- the Spark session
- the compat shim
- the transport (filesystem vs `hdfs dfs`)
- path construction
- table resolution

Framework code calls only its functions. See `docs/context/environment.md`.

## 9. Proposed package layout (to confirm as components get built)

```
src/core_modelling/
  __init__.py        version
  __main__.py        CLI entry (run <config>)
  config/            schema, loading (base+local merge), migrations
  environment.py     Spark session, compat shim, transport, paths
  data_creation/     rollups, target builders (extension point)
  eda/               profiling, report assembly
  feature_checks/    screening steps, stability, lineage guard
  training/          engine wrapper (FLAML), sampling, calibration
  evaluation/        metrics by task, slices, baselines, explainability
  lifecycle/         promotion, deployment, registry records
  inference/         scoring, batch outputs, manifests
  tracking/          outcome joins, drift, impact vs baselines
  reporting/         shared report writer (markdown/HTML) used by eda/evaluation/cards
```

A folder becomes a single module file when it only needs one. Don't create empty sub-packages
ahead of need.

## Public API

Filled in as it is built. Only functions listed here are public and covered by `CLAUDE.md` §2.

| Function | Module | Since |
|---|---|---|
| *(none yet)* | | |

## Data folders

`data/` keeps the Kedro-style numbered layers as a naming convention (no Kedro dependency). See
`data/README.md`.
