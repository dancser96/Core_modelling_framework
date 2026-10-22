# Run modes: CLI, Python API, guided notebooks
**Status:** designing · **Legacy:** `run_product.py`, `notebooks/`
**Related:** [config](config.md) · [environment](environment.md) · [dataset](dataset.md) (experiment sweeps) ·
`notebooks/README.md` · D-024, D-039, D-047, D-074, D-083, D-090, D-097, D-114 · OD-02, OD-04

## Purpose
The same functions, used two ways: guided notebooks for manual work and learning, and a CLI / Python
API for automated and production runs. The framework is a versioned library, not a service (D-024),
so users can see and debug what happens under the hood.

## Phase 2 requirements
1. **CLI:** `python -m core_modelling run <config> [--stages …] [--profile …] [--entity …]`, plus
   separate `register`, `promote` and `deploy` commands. They are gated steps run by different
   actors: the change-request process runs `deploy`. The feature sign-off (D-076; how it is
   recorded: OD-10) needs an entry point.
2. **Python API:** one function per stage, plus `run(config, stages=...)` taking a config path or a
   loaded config.
3. **Experiment sweeps:** a function that runs one config with a single field varied (e.g. the
   observation window) and compares the variants on the same validation set ([dataset](dataset.md)
   window ablation, whose design that doc owns). Each variant changes only that field (same
   eligibility, candidates, budget, seeds, sampling rule). The comparison report comes from
   [evaluation](evaluation.md). A sweep that picks a variant picks on train and test metrics,
   weighted; the validation month is reported, never chosen on (D-083). The name is still to be
   decided.
4. **Guided notebooks, one per stage.** Each opens with what the stage is for, what to look at, which
   decisions to record in the config or the decision audit log (OD-10), and links to the docs.
   Then: load config → call the stage → display the artifacts. Written as instructions, not
   commentary. Thin in M2 (load, call, display); the guidance text is written in M3 with the LDS
   reviewing as the proxy user (D-097).
5. **Example notebooks on release** = the guided notebooks run end to end on the synthetic dataset,
   outputs included.
6. **Users may copy the notebooks and explore.** Production runs, registered models and reports never
   depend on notebook code (D-039).
7. Entry points apply the environment adapter first (compat shim, Spark session).

## Design constraints
- No logic in `__main__.py` beyond parsing arguments and calling the API.
- No HTTP / scheduler layer. Scheduling, if any, calls the CLI.

## Open questions
- Where use cases live and how users get the notebooks (OD-02). Leaning: one repo per entity ×
  domain, with a use case branching into its own repo as it grows; not one shared repo with code
  folders.
- The package ships in the base image through Nexus, which pins each use case's framework version
  (D-074, D-047). A use case can also take a newer framework version within its base image's
  year, as a newer package in the same image (D-114). Still open: the release mechanics (OD-04).
  Extension code lives in the use case's repo, never in the framework (D-090).
