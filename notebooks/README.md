# notebooks — guided interface

The framework ships one **guided** notebook per stage. It is the manual interface to the package
functions and a way to learn how things work under the hood (D-039, `docs/components/run_modes.md`).

**Hard rules for the framework's notebooks**
- No function or class definitions. Logic lives in `src/core_modelling/`.
- The shipped notebooks call only the Public API (D-024: stage functions, `run`, the config schema
  and the decision audit log's functions; the table in `docs/architecture.md`). A small test
  checks it.
- One notebook per stage, **never** one per use case. To work on another use case, change the config
  path in the first cell and rerun.
- Every notebook has the same shape:
  1. **Guide cell:** what this stage is for, what to look at, which decisions to record in the
     decision audit log (`record_decision`, D-125), and links to the docs. Written as
     instructions, not commentary.
  2. **Setup cell:** environment adapter (compat shim + Spark) and config load.
  3. **One call per step:** `run_<stage>(cfg)` or another Public API function, each preceded by a
     short markdown cell saying what to check in its output.
  4. **Display cells** that render the artifacts the functions produced.
- Reports are produced by package functions from the frozen config, not assembled here.
- Clear outputs before committing (they may contain data). Exception: `00_synthetic_data` is
  committed with its outputs, since it only ever shows synthetic data (D-064).

**Exploring in your own copy is encouraged.** Copy a notebook and play: pivots, filters, extra
charts. But nothing a production run, registered model or report depends on may live in a notebook.
Anything worth keeping moves into the config, a decision-log entry or the package.

**Release examples:** the same notebooks, run end to end on the synthetic dataset, outputs included.

Notebooks: `00_synthetic_data` (exists; dev only and temporary: a visual tour of the synthetic data,
with its checks in an appendix, see `docs/components/test_harness.md`; not a guided stage
notebook). Planned,
created as their stages are built: `01_target_factory`, `02_eda`, `03_feature_checks`,
`04_training`, `05_evaluation`, `06_register_promote`, `07_inference`, `08_monitoring`. No notebook
deploys: the change-request process runs `deploy` (D-033). The feature sign-off is recorded from
`03_feature_checks` in manual runs, or after training in hands-off runs (D-031).
