# Target Factory
**Status:** building (M2.1, from 2026-10-26) · **Legacy:** `src/rollups.py`, `notebooks/Data_Creation.ipynb` (crunch name: Data Creation)
**Related:** [config](config.md) (the target spec) · [dataset](dataset.md) (frames, the model input) ·
[environment](environment.md) (source resolution) · [feature checks](feature_checks.md) (lineage exclusion, the
leakage screen) · [monitoring](monitoring.md) (labels) · D-020, D-021, D-029, D-050, D-054, D-091, D-129, D-131,
D-133 · OD-26

## Purpose
Builds targets. This is the one piece of data work the framework keeps: it links upstream data
engineering with modelling, and target construction is where time leakage starts. The stage is
**optional**: if a target already exists upstream, the use case points at that column and skips it.
It is designed together with the [dataset](dataset.md), though: the target is built from the
target source (or read from a feature source), features come from the governing spine and the
other feature sources (the feature store, a mart, or both, D-021), and the dataset joins them on
unit and month (D-129). Showing how a use case reads several sources this way is a Stage 1
deliverable. The stage asks nothing extra of upstream (D-029). In Phase 2 the feature store
integration is limited to Stage 1 (M2.1 Foundation), where a use case's data comes in; no later
stage knows about it. The framework only **reads** from the feature store, as one more source
behind the environment adapter; nothing is written back (D-021, OD-26).

## Phase 2 requirements
1. **One declarative target spec** in config (D-129): `data.target` with `rule` (the builder in
   the per-task spec), `column` (the column the rule reads, excluded from the candidates as
   lineage) and `leavers`; or, for a target built upstream, `column` alone with an optional
   `lineage` list. The keys come from `data.keys`, the target source from
   `entities.<e>.sources.targets` (the spine when omitted), and the forward window `w` from
   `time.target_window_months`, one number shared with the time checks, required for both
   variants since an upstream target also looks some months ahead. One function builds the
   targets lazily in Spark; saving is a separate call.
2. **Two modes from the same spec** (D-029, D-131):
   - **Notebook mode:** build, inspect (the target rate per month, the lineage, the logs), then
     `save_model_input`, which writes the model input that later stages read and freezes the
     config (D-125). The model input carries the target: there is no separate targets table.
   - **Config mode:** build and hand the result straight to the next stage in memory. The spec's
     hash is recorded, so the run stays reproducible without a saved table.
3. **Target builders by `task`** through the per-task spec (D-050):
   - binary is a rule on a forward window (e.g. adoption, activation, reactivation): a threshold on
     a forward sum, or a flag or count going up. "Going up" means in any month of the window (a
     flag 1 in any forward month for a non-holder; any month-on-month count rise), not only at its
     end: end-of-window rules miss events that reverse inside the window and, for loans, openings
     hidden by a maturity. Acquisition is one target whether the client never held the product or
     churned (D-041); build it from the flag, not the status column, so lineage exclusion keeps the
     status's churned signal. Stage 1 builds this flag rule (`flag_in_window`) with lineage; the
     other rule families (count rises, thresholds on sums, leavers as negatives) follow by release
     1.0 (M4, D-091);
   - regression is the second task in Phase 2 (D-020). Stage 1 builds its forward-sum rule
     (`forward_sum` over `t+1 … t+w`) beside the flag rule, so the per-task dispatch is real from
     day one; the rest of regression waits for M4 (D-091).
4. Forward windows exclude the current month `(1, w)` (T8). Windows come only from config (T13).
5. **Panel-edge guard:** the target is null where the full forward window is missing, per client:
   also where the client left inside the window (default). The alternative, `leavers: negative`,
   must be declared in the spec and mirrored by the oracle; until M4 it fails loud as not
   implemented (D-091). This is derived from the window, never hardcoded. A target already
   decided at the observation month (e.g. a loan closing, set by its maturity: the target equals an
   as-of column row for row) is useless, and the template says so with the loan example; the
   framework doesn't check it here, since Target Factory never looks at the candidates. The
   leakage screen in Feature Checks flags the column that decides it, and a person decides
   (D-133, `CLAUDE.md` §4.6).
6. **Target lineage recorded:** the columns used to build each target are written to metadata, so
   Feature Checks excludes them automatically (T12). For targets built upstream, no lineage list is
   required: a target is almost never built from more than one column, and a DS knows the data
   (D-029). The DS can still list lineage columns in config; this asks nothing of upstream.
7. **Partial and incremental builds** (later, M4): build per source, per entity and per month
   without touching other sources' or months' outputs (partitioned, idempotent writes). Domains
   arrive at different times with different schemas, and the spec names columns per source.
8. **The sanctioned extension point** for custom target builders.
9. **Labels for scored months** (D-054, M4): once a scored month's forward window has matured,
   build its targets from the model's frozen target spec, so monitoring can join them to the
   scores. Use cases with upstream targets skip this; monitoring reads the upstream target column.

## Design constraints
- Spark only (no `toPandas`). One read, one write per build.
- Owns invariant §4.1 (time separation) for targets.
- Eligibility is not materialised here. It is an ordered config step applied when the dataset is built
  ([dataset](dataset.md)). Targets are therefore built over every row of the target source (the
  forward window reads a client's later months whatever their eligibility), and the dataset
  selects the eligible rows afterwards.

## Lessons from the crunch
T8, T11, T12, T13.

## Interface
Planned (Stage 1, in `core_modelling/target_factory.py` and `core_modelling/tasks.py`; plan in
`worknotes/m2_1_foundation/plan.md` until the stage is done); nothing is built yet.
- `TASK_SPECS` (`tasks.py`): the per-task spec dict; in Stage 1 `binary` holds `target_rules:
  {flag_in_window}` and `regression` `target_rules: {forward_sum}`, plus the contract checks
  ([dataset](dataset.md)).
- `build_targets(source: DataFrame, cfg: UseCaseConfig) -> DataFrame`: keys renamed to `unit_id`,
  `month`; the rule from `TASK_SPECS[cfg.task]` over the forward window `(1, w)`; null where fewer
  than `w` later months exist (panel edge, leavers). Columns: `unit_id`, `month`, `target`.
- `target_lineage(cfg) -> list[str]`: `[column]` plus the config's `lineage`.
- `run_target_factory(cfg, entity, env, spark) -> pd.DataFrame` (public, D-024): builds on the
  target source (nothing to build for an upstream target), returns and prints per month the
  rows, positive rows, positive events (D-082) and the null share; writes nothing. The notebook
  `01_target_factory` calls it, then `save_model_input` ([dataset](dataset.md)).

## Open questions
- How a use case reads from the feature store, and how that work splits with the feature store
  team (OD-26).
