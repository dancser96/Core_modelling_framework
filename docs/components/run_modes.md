# Run modes: CLI, Python API, guided notebooks
**Status:** built thin (Stage 1, 2026-10-27: `run` with its one stage, the CLI `run` and `decide`, the first guided notebook) · **Legacy:** `run_product.py`, `notebooks/`
**Related:** [config](config.md) · [environment](environment.md) · [dataset](dataset.md) (experiment sweeps) ·
`notebooks/README.md` · D-006, D-022, D-024, D-039, D-047, D-083, D-125 · OD-02, OD-04

## Purpose
The same functions, used two ways: guided notebooks for interactive work and learning, and a CLI / Python
API for automated and production runs. The framework is a versioned library, not a service (D-024),
so users can see and debug what happens under the hood.

## Phase 2 requirements
1. **CLI:** `python -m core_modelling run <config>… [--stages …] [--entity …]` (several configs save one model input; an empty list or configs listing different entities are refused), plus
   separate `register`, `promote` and `deploy` commands. They are gated steps run by different
   actors: the change-request process runs `deploy`. `decide` records a person's decision, the
   feature sign-off (D-031) included, as an entry in the decision audit log; it is the CLI form of
   `record_decision` (D-125, [config](config.md#decision-audit-log-d-125)). There is no
   automation-level override: a level changes through a config edit or an audit-log entry (D-023).
2. **Python API:** one function per stage, plus `run(config, stages=...)` taking a config path or a
   loaded config. These, the CLI commands, the config schema, the audit log's functions
   (`record_decision`, `show_decisions`, `resolve_config`) and the adapter's Spark-session function
   (public from M2.1, [environment](environment.md)) are the Public API (D-024, the table in
   [architecture](../architecture.md#public-api)); the shipped
   notebooks call only them, which a small test checks. Everything else is private.
3. **Experiment sweeps:** a function that runs one config with a single field varied (e.g. the
   observation window) and compares the variants on the same validation set ([dataset](dataset.md)
   window ablation, whose design that doc owns). Each variant changes only that field (same
   eligibility, candidates, budget, seeds, sampling rule). The comparison report comes from
   [evaluation](evaluation.md). A sweep that picks a variant picks on train and test metrics,
   weighted; the validation period is reported, never chosen on (D-083). The reports,
   sweep tables included, show the validation metric and people are trusted not to choose on it.
   The name is still to be decided.
4. **Guided notebooks, one per stage.** Each opens with what the stage is for, what to look at, which
   decisions to record in the decision audit log (`record_decision`, D-125), and links to the
   docs. Then: load config → call the stage → display the artifacts. Written as instructions, not
   commentary. Thin in M2 (load, call, display); the guidance text is written in M3 with the LDS
   reviewing as the proxy user (D-022).
5. **Example notebooks on release** = the guided notebooks run end to end on the synthetic dataset,
   outputs included.
6. **Users may copy the notebooks and explore.** Production runs, registered models and reports never
   depend on notebook code (D-039).
7. Entry points apply the environment adapter first (compat shim, Spark session).

## Design constraints
- No logic in `__main__.py` beyond parsing arguments and calling the API.
- No HTTP / scheduler layer. Scheduling, if any, calls the CLI.

## Interface
Built in Stage 1 (2026-10-27), in `core_modelling/run.py`, `core_modelling/__main__.py` and
`notebooks/01_target_factory.ipynb`.
- `run(config_path, env_path=None, stages=None, entity=None) -> dict` (public, D-024): the
  stages (default: every built one, in `STAGES` order) for the entities of the config (default:
  all it lists); per entity and stage what the stage returned. An unknown stage or entity fails
  before anything runs. `STAGES` is the dict stage name → function `(cfg, entity, env, spark)`;
  Stage 1 holds `target_factory`: `run_target_factory`, then `save_model_input` when the config
  names a model input (D-131). The later stages take the resolved config (D-125) and join as they
  are built.
- CLI: `python -m core_modelling run <config>… [--stages …] [--entity …] [--env …]` and `decide`
  ([config](config.md)); `__main__` parses and calls.
- `notebooks/01_target_factory.ipynb`: the guide cell, the setup cell (`load_environment`,
  `get_spark_session`, `load_config`), `run_target_factory`, `save_model_input`,
  `build_frames(stage="eda")` with the funnel and the frame's head. `tests/test_run.py` checks
  it imports from the Public API only and defines nothing.

## Open questions
- Where use cases live and how users get the notebooks (OD-02). Leaning: one repo per entity ×
  domain, with a use case branching into its own repo as it grows; not one shared repo with code
  folders.
- The package ships in the base image through Nexus, which sets each use case's default framework
  version; the use case pins it (D-024, D-047). A use case can also take a newer framework version within its base image's
  year, as a newer package in the same image (D-047). Still open: the release mechanics (OD-04).
  A use case is one config and its audit log; a repo may hold several similar use cases, each with
  its own, and extension code lives in the repo that holds the use case, never in the framework
  (D-006).
