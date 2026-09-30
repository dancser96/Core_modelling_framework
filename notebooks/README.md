# notebooks — interface only

Notebooks are a thin interface to package functions, for manual runs and inspection.

**Hard rules**
- No function or class definitions. Logic lives in `src/core_modelling/`.
- One notebook per stage, **never** one per use case. To work on another use case, change the
  config path in the first cell and rerun.
- Every notebook follows the same shape:
  1. Setup cell: environment adapter (compat shim + Spark) and config load.
  2. One call per step: `run_<stage>(cfg)` or finer-grained public functions.
  3. Display cells that render the artifacts the functions produced.
- Reports are produced by package functions from the frozen config, not assembled here.
- Clear outputs before committing (they may contain data).

Planned notebooks (created as their stages are built): `01_data_creation`, `02_eda`,
`03_feature_checks`, `04_training`, `05_evaluation`, `06_promotion`, `07_inference`, `08_tracking`.
