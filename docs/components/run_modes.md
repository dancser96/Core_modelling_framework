# Run modes: CLI, Python API, guided notebooks
**Status:** designing · **Legacy:** `run_product.py`, `notebooks/`
**Related:** [config](config.md) · [environment](environment.md) · [dataset](dataset.md) (experiment sweeps) ·
`notebooks/README.md` · D-024, D-039, D-047, D-053 · OD-02, OD-04, OD-05

## Purpose
The same functions, used two ways: guided notebooks for manual work and learning, and a CLI / Python
API for automated and production runs. The framework is a versioned library, not a service (D-024),
so users can see and debug what happens under the hood.

## Phase 2 requirements
1. **CLI:** `python -m core_modelling run <config> [--stages …] [--profile …] [--entity …]`, plus
   separate `register`, `promote` and `deploy` commands. They are gated steps run by different
   actors: the change-request process runs `deploy`.
2. **Python API:** one function per stage, plus `run(config, stages=...)` taking a config path or a
   loaded config.
3. **Experiment sweeps:** a function that runs one config with a single field varied (e.g. the
   observation window) and compares the variants on the same validation set ([dataset](dataset.md)
   window ablation, whose design that doc owns). Each variant changes only that field (same
   eligibility, candidates, budget, seeds, sampling rule). The comparison report comes from
   [evaluation](evaluation.md). A sweep that picks a variant labels the winner's validation result
   as optimistic; a separate selection month comes with the LLM branch (D-053). The name is still
   to be decided.
4. **Guided notebooks, one per stage.** Each opens with what the stage is for, what to look at, which
   decisions to record in config, and links to the docs. Then: load config → call the stage →
   display the artifacts. Written as instructions, not commentary.
5. **Example notebooks on release** = the guided notebooks run end to end on the synthetic dataset,
   outputs included.
6. **Users may copy the notebooks and explore.** Production runs, registered models and reports never
   depend on notebook code (D-039).
7. Entry points apply the environment adapter first (compat shim, Spark session).

## Design constraints
- No logic in `__main__.py` beyond parsing arguments and calling the API.
- No HTTP / scheduler layer. Scheduling, if any, calls the CLI.

## Open questions
- Where use cases live and how users get the notebooks (OD-02). Not one shared repo with code
  folders.
- Distribution channel and release path (OD-04); where extension code lives (OD-05). Each use case
  pins its framework version (D-047).
