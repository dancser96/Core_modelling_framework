# Run modes: notebooks, CLI, Python API
**Status:** designing · **Legacy:** `run_product.py`, `notebooks/`

## Purpose
The same functions are usable in two ways: manually through the standard notebooks, and
automatically through a CLI / Python API, which is the "as a service" path.

## Phase 2 requirements
1. CLI: `python -m core_modelling run <config> [--stages eda,feature_checks,...]`.
2. Python API: one function per stage plus `run(config, stages=...)`, taking a config path or a
   loaded config.
3. Standard notebooks, one per stage. Each follows the same pattern:
   - load config
   - call the stage
   - display its artifacts

   Switching use case = switching config. No function definitions, no copies.
4. Entry points apply the environment adapter first (compat shim, Spark session).

## Design constraints
- No logic in `__main__.py` beyond parsing arguments and calling the API.
- An HTTP / scheduler layer comes later, as a thin wrapper over the same API.
