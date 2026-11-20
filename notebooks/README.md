# notebooks — guided interface

The framework ships one **guided** notebook per stage. It is the interactive interface to the
package functions and a way to learn how things work under the hood (D-039,
`docs/components/run_modes.md`).

**Hard rules for the framework's notebooks**
- No function or class definitions. Logic lives in `src/core_modelling/`.
- The shipped notebooks call only the Public API (D-024: stage functions, `run`, the config schema,
  the decision audit log's functions and the adapter's Spark-session function; the table in
  `docs/architecture.md`). A small test checks it.
  Exception: `00_modelling_helper` is a code-reading aid, dev only like `00_synthetic_data`: it
  calls internal functions to show what each one returns, is not shipped, and is not in
  the test's list. It still defines nothing and is committed without outputs.
- One notebook per stage, **never** one per use case. To work on another use case, change the config
  path in the first cell and rerun.
- A notebook is rewritten in place. No copy of the old version or its outputs is kept anywhere
  unless the EDS asks: outputs come back by rerunning, and git has the committed version.
- Every notebook has the same shape:
  1. **Guide cell:** what this stage is for, what to look at, which decisions to record in the
     decision audit log (`record_decision`, D-125), and links to the docs. Written as
     instructions, not commentary. The guide text is the notebook's main deliverable (the EDS,
     2026-11-03): before every step a short markdown cell says what the step does, what to look
     at in its output, how to read each number, which decision to take and how to record it, at
     both automation levels; concise, but nothing a first-time user needs is left out. Guide
     cells cite no decision (D-nnn), trap (T-nn) or worknotes: the reader is a data scientist new
     to the framework, not its maintainer. After writing, one re-read for conciseness (cut what a
     first-time user does not need, one or two sentences per bullet) before the notebook is done.
     Text lives in the markdown cells: a code cell displays tables, charts and at most a Markdown
     heading per item, never a paragraph rendered as an HTML output, and no machine-specific
     numbers (budgets, run times).
  2. **Setup cell:** environment adapter (compat shim + Spark) and config load.
  3. **One call per step:** `run_<stage>(cfg)` or another Public API function, each preceded by a
     short markdown cell saying what to check in its output.
  4. **Display cells** that render the artifacts the functions produced.
- Reports are produced by package functions from the resolved config, not assembled here.
- Clear outputs before committing (they may contain data, a machine's name or a home path).
  Exception: `00_synthetic_data` is committed with its outputs, since it only ever shows
  synthetic data (D-064). `tests/test_code_rules.py` enforces both.

**Exploring in your own copy is encouraged.** Copy a notebook and play: pivots, filters, extra
charts. But nothing a production run, registered model or report depends on may live in a notebook.
Anything worth keeping moves into the config, an audit-log entry or the package.

**Release examples:** the same notebooks, run end to end on the synthetic dataset, outputs included.

Notebooks: `00_synthetic_data` (exists; dev only and temporary: a visual tour of the synthetic data,
with its checks in an appendix, see `docs/components/test_harness.md`; not a guided stage notebook).
`00_eda_fc_helper` (a reference while reading the EDA and Feature Checks code, not a stage: it reads both stages' stored artifacts read-only through `feature_dir`, `read_stage`, `read_ledger` and `show_decisions`, no Spark session and no entry, and shows each one's grain, columns, writers, readers and a few telling rows: `eda.json`, the counts table first, then `ranking`, `client_constant`, `correlation` and every other EDA table, the ledger, `feature_checks.json` and its five tables, the decision audit log; run `02_eda` and `03_feature_checks` first). `00_modelling_helper` (built in M2.3 step 1; dev only, a reference while reading the modelling code, not a stage: on the use case's own train rows it calls the functions Training will call and shows what each returns, with its grain, columns and what right looks like: the features in force, the training frame with the client folds, the encoder, the four families with their round trips, the bundle with its manifest and scoring in pandas and in Spark, the run record; everything it writes goes to a temporary folder; run `02_eda` and `03_feature_checks` first; sections 7 to 9, its Training section, read a trained run without writing: `training.json`, the six tables with checks that they agree with each other (each family's budget, the out-of-fold rows, the contributions adding up to the out-of-fold margin), the per-run ledger and `stage2/`; run `04_training` first; section 10, its Evaluation section, reads an evaluated run the same way: `evaluation.json`, its tables with the contributions adding up to the scored margin, and the scores table; run `05_evaluation` first). `01_target_factory` (built with Stage 1: the targets, the model input saved, the frames).
`02_eda` (built with Stage 2, nine steps: `run_eda` on one config; the report's views with how to
read each number: the choices, the headline and the warnings (the how-to-read notes in step 3's
text), the funnel, the sources per period, the target per period and by stratum, the ranking, the
key features at the decision's slices, each key feature's deep dive; one call each of the four
exploration functions `pivot_target`, `lift_by_group`, `compare_sides` and `rate_by_period`; the
report file and what only it holds (the reference groups, the correlation overview of the key
features, the value profile, the appendix); the decisions EDA can lead to as `record_decision`
text at both levels). `03_feature_checks` (built with Stage 2, ten steps: `run_feature_checks` on
one config, and the rows it judged (`build_frames`: the snapshot and every compared period's
eligible rows) to check a finding on the spot; the choices and the summary (the flags and notes per
finding, the held features with each open flag's value); one section per step in run order,
`quality`, `leakage`, `time_alignment`, `stability` (with the per-period chart) and `redundancy`
(the clusters first, one row each, then the features), each with its findings' rules and how to read
their numbers; three checks on the data (the target by value, a few clients across the periods, the
distribution per period); the proposed decisions with the `record_decision` call text, using the
`CONFIG` and `ENVIRONMENT` names the setup cell defines, each call taking any subset of a finding's
features, and a walk-through that splits one finding between a `keep` and an `exclude`, reruns the
stage and reverts the exclude; the report file and what only it holds (the per-period tables, the ledger
with decisions, the appendix); it ends with the `keep` of the three static attributes in force,
so the examples train with them). `04_training` (built in M2.3 step 2, nine steps:
`run_training` on one config, with the gate's refusals and their fixes and the run's summary;
the feature set in force and the warnings; what the search did (the table per family, the
progress chart, the chosen configuration); selection's three rules; the calibration with the
out-of-fold numbers and why they are optimistic; the explanation charts; the sign-off view,
which `05_evaluation` guides; the runs so far with `list_runs` and `show_run`; how to iterate
through `record_decision`: a `keep` or an `exclude`, a quick run then a main run's budget per
family through `training.trials`, other `training` settings). `05_evaluation` (built in M2.3 step 3,
twelve steps and a closing checklist: pick a run with `list_runs` and `run_evaluation`'s
default, the latest trained run of the data definition; `run_evaluation` and where
`report.html` is; the report view by view from `result.views` with how to read each: the
summary, the metrics per period, the curves, capture and slices, reliability and the score
distribution, the strata; the explanations: importance and the beeswarm, the effects beside
EDA's lift, the waterfalls, permutation importance and PDP with ICE, and a `shap.Explanation`
from the stored contributions for `shap`'s own plots; the search, thresholds and validation on
test clients only; the model card; `compare_runs`, differences on test only, validation
reported and never chosen on; the feature sign-off as `sign_off` and `exclude` call text, not
run; what must be true before the run is taken further).
Planned, created as their stages are built: `06_register_promote`, `07_inference`, `08_monitoring`. No notebook deploys: the change-request process runs `deploy`
(D-033). The feature sign-off is recorded after training and before register, at every automation
level. At the `assisted` level the review's `keep` / `exclude` entries precede training; at
`autonomous` the held features (open flags) stay out of training until the sign-off (D-031,
D-134); notebook 03's guide says in words that, for Training, a held feature acts as an excluded
feature without a final decision. The notebooks ship inside the wheel, and `python -m core_modelling init <folder>` copies
them out (M2.4, D-137).
