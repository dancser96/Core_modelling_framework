# notebooks — guided interface

The framework ships one **guided** notebook per stage. It is the interactive interface to the
package functions and a way to learn how things work under the hood (D-039,
`docs/components/run_modes.md`).

**Hard rules for the framework's notebooks**
- No function or class definitions. Logic lives in `src/core_modelling/`.
- The shipped notebooks call only the Public API (D-024: stage functions, `run`, the config schema,
  the decision audit log's functions and the adapter's Spark-session function; the table in
  `docs/architecture.md`). A small test checks it.
- One notebook per stage, **never** one per use case. To work on another use case, change the config
  path in the first cell and rerun.
- Every notebook has the same shape:
  1. **Guide cell:** what this stage is for, what to look at, which decisions to record in the
     decision audit log (`record_decision`, D-125), and links to the docs. Written as
     instructions, not commentary. The guide text is the notebook's main deliverable (the SDS,
     2026-11-03): before every step a short markdown cell says what the step does, what to look
     at in its output, how to read each number, which decision to take and how to record it, at
     both automation levels; concise, but nothing a first-time user needs is left out.
  2. **Setup cell:** environment adapter (compat shim + Spark) and config load.
  3. **One call per step:** `run_<stage>(cfg)` or another Public API function, each preceded by a
     short markdown cell saying what to check in its output.
  4. **Display cells** that render the artifacts the functions produced.
- Reports are produced by package functions from the resolved config, not assembled here.
- Clear outputs before committing (they may contain data). Exception: `00_synthetic_data` is
  committed with its outputs, since it only ever shows synthetic data (D-064).

**Exploring in your own copy is encouraged.** Copy a notebook and play: pivots, filters, extra
charts. But nothing a production run, registered model or report depends on may live in a notebook.
Anything worth keeping moves into the config, an audit-log entry or the package.

**Release examples:** the same notebooks, run end to end on the synthetic dataset, outputs included.

Notebooks: `00_synthetic_data` (exists; dev only and temporary: a visual tour of the synthetic data,
with its checks in an appendix, see `docs/components/test_harness.md`; not a guided stage notebook).
`01_target_factory` (built with Stage 1: the targets, the model input saved, the frames).
`02_eda` and `03_feature_checks` are built with Stage 2. In `02_eda` the guide cell explains
concordance in plain words, then `run_eda`, the views and `pivot_target`. In `03_feature_checks`:
`run_feature_checks`, the findings, and the proposed decisions with the `record_decision` call
text, using a `CONFIG` placeholder the setup cell defines (no commented-out cell). Planned,
created as their stages are built: `04_training`, `05_evaluation`, `06_register_promote`,
`07_inference`, `08_monitoring`. No notebook deploys: the change-request process runs `deploy`
(D-033). The feature sign-off is recorded after training and before register, at every automation
level. At the `assisted` level the review's `keep` / `exclude` entries precede training; at
`autonomous` the held features (open flags) stay out of training until the sign-off (D-031,
D-134); notebook 03's guide says in words that, for Training, a held feature acts as an excluded
feature without a final decision. The notebooks ship inside the wheel, and `python -m core_modelling init <folder>` copies
them out (M2.4, D-137).
