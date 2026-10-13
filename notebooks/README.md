# notebooks — guided interface

The framework ships one **guided** notebook per stage. It is the manual interface to the package
functions and a way to learn how things work under the hood (D-039, `docs/components/run_modes.md`).

**Hard rules for the framework's notebooks**
- No function or class definitions. Logic lives in `src/core_modelling/`.
- One notebook per stage, **never** one per use case. To work on another use case, change the config
  path in the first cell and rerun.
- Every notebook has the same shape:
  1. **Guide cell:** what this stage is for, what to look at, which decisions to record in the config,
     and links to the docs. Written as instructions, not commentary.
  2. **Setup cell:** environment adapter (compat shim + Spark) and config load.
  3. **One call per step:** `run_<stage>(cfg)` or finer-grained public functions, each preceded by a
     short markdown cell saying what to check in its output.
  4. **Display cells** that render the artifacts the functions produced.
- Reports are produced by package functions from the frozen config, not assembled here.
- Clear outputs before committing (they may contain data).

**Exploring in your own copy is encouraged.** Copy a notebook and play: pivots, filters, extra
charts. But nothing a production run, registered model or report depends on may live in a notebook.
Anything worth keeping moves into a config decision or the package.

**Release examples:** the same notebooks, run end to end on the synthetic dataset, outputs included.

Planned notebooks (created as their stages are built): `00_synthetic_data` (dev only),
`01_target_factory`, `02_eda`, `03_feature_checks`, `04_training`, `05_evaluation`,
`06_register_promote`, `07_inference`, `08_monitoring`.
