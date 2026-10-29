# Target Factory
**Status:** built thin (M2.1, 2026-10-26; for the SDS's review with the dataset) · **Legacy:** `src/rollups.py`, `notebooks/Data_Creation.ipynb` (crunch name: Data Creation)
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
unit and period (D-129). Showing how a use case reads several sources this way is a Stage 1
deliverable. The stage asks nothing extra of upstream (D-029). In Phase 2 the feature store
integration is limited to Stage 1 (M2.1 Foundation), where a use case's data comes in; no later
stage knows about it. The framework only **reads** from the feature store, as one more source
behind the environment adapter; nothing is written back (D-021, OD-26).

## Phase 2 requirements
1. **One declarative target spec** in config (D-129): `data.target` with `rule` (the builder in
   the per-task spec) and `column` (the column the rule reads, excluded from the candidates as
   lineage); or, for a target built upstream, `column` alone with an optional
   `lineage` list. The keys come from `data.keys`, the target source from
   `entities.<e>.sources.targets` (the spine when omitted), and the forward window `w` from
   `time.target_window`, in periods (`time.period`: month, week or day), one number shared with
   the time checks, required for both variants since an upstream target also looks some periods
   ahead. One function builds the targets lazily in Spark; saving is a separate call.
2. **Two modes from the same spec** (D-029, D-131):
   - **Notebook mode:** build, inspect (the target rate per period, the lineage, the logs), then
     `save_model_input`, which writes the model input that later stages read, for one or
     several use cases that share the sources, keys and period, and freezes each config's data
     part (D-125). The model input carries one target column per use case: there is no
     separate targets table.
   - **Config mode:** build and hand the result straight to the next stage in memory. The spec's
     hash is recorded, so the run stays reproducible without a saved table.
3. **Target builders by `task`** through the per-task spec (D-050):
   - binary is a rule on a forward window (e.g. adoption, activation, reactivation): a flag or a
     count going up, or a threshold on a forward sum. "Going up" compares the observation period
     with the forward periods: some value in t+1 … t+w exceeds the value at t (D-029 (c)), in
     any period of the window, not only at its end: end-of-window rules miss events that reverse
     inside the window and, for loans, openings hidden by a maturity. Who is in the population
     (e.g. non-holders only) is an eligibility criterion, never the rule's: a holder at t gets a
     0 from the flag rule. Acquisition is one target whether the client never held the product
     or churned, since a churned client is a non-holder at t; build it from the flag, not the
     status column, so lineage exclusion keeps the status's churned signal. Stage 1 builds the
     flag rule (`flag_goes_up`, a 0/1 column) with lineage; the count rule (`count_goes_up`),
     the amount rules and the thresholds on sums are separate rules by release 1.0 (M4,
     D-091);
   - regression is the second task in Phase 2 (D-020). Stage 1 builds its forward-sum rule
     (`forward_sum` over `t+1 … t+w`) beside the flag rule, so the per-task dispatch is real from
     day one; the rest of regression waits for M4 (D-091).
4. Forward windows exclude the current period `(1, w)` (T8). Windows come only from config
   (T13), and the window steps on the period index of `periods.PERIODS`, never `add_months` or
   added days (T19), so one rule serves month, week and day data.
5. **Panel-edge guard:** the target is null where the full forward window is missing, per client:
   at the panel edge, where the client left inside the window and across gaps; derived from the
   window, never hardcoded. Null **values** follow SQL semantics (D-029 (c)): a null never counts
   as an event, and the target is null only when nothing can be compared (the value at t, or
   every forward value, null); `null_in_window` is null where the window is incomplete, so its
   average is the share of the target source's rows in the window with a complete target
   window, before eligibility, that held a null: the summary shows it (`null_value_share`), the
   model input's sidecar stores it per use case, and the dataset's contract check calls it out
   above 0, naming that population. A source that codes a value as null (0 for a
   non-holder) fills it upstream; the framework does not. A
   target already decided at the observation period (e.g. a loan closing, set by its maturity:
   the target equals an as-of column row for row) is useless, and the template says so with the
   loan example; the framework doesn't check it here, since Target Factory never looks at the
   candidates. The leakage screen in Feature Checks flags the column that decides it, and a
   person decides (D-133, `CLAUDE.md` §4.6).
6. **Target lineage recorded:** the columns used to build each target are written to metadata, so
   Feature Checks excludes them automatically (T12). For targets built upstream, no lineage list is
   required: a target is almost never built from more than one column, and a DS knows the data
   (D-029). The DS can still list lineage columns in config; this asks nothing of upstream.
7. **Partial and incremental builds** (later, M4): build per source, per entity and per period
   without touching other sources' or periods' outputs (partitioned, idempotent writes). Domains
   arrive at different times with different schemas, and the spec names columns per source.
8. **The sanctioned extension point** for custom target builders.
9. **Labels for scored periods** (D-054, M4): once a scored period's forward window has matured,
   build its targets from the model's frozen target spec, so monitoring can join them to the
   scores. Use cases with upstream targets skip this; monitoring reads the upstream target column.

## Design constraints
- Spark only (no `toPandas`). One read, one write per build.
- Owns invariant §4.1 (time separation) for **built** targets. An upstream target can't be
  checked for it; Target Factory refuses one that has values in the source's last `w` periods,
  where a target over t+1 … t+w can't be known yet.
- Eligibility is not materialised here. It is an ordered config step applied when the dataset is
  built or read ([dataset](dataset.md)). Targets are therefore built over every row of the
  target source (the forward window reads a client's later periods whatever their eligibility),
  and the dataset selects the eligible rows afterwards.

## Lessons from the crunch
T8, T11, T12, T13, T19, T22.

## Interface
Built in Stage 1's major step 2 (2026-10-26; under the SDS's review), in
`core_modelling/target_factory.py`, `core_modelling/tasks.py` and `core_modelling/sources.py`.
- `TASK_SPECS` (`tasks.py`): the per-task spec dict; per task a rule, a target-column check
  (`(source, column, name)`, the source's name for the error) and a summary; the contract checks
  join with the dataset ([dataset](dataset.md)). A rule gets the target column and the forward
  window t+1 … t+w and returns the target as a Column; it compares the value at t with the
  forward values and never counts t as the event:
  - binary, `flag_goes_up` (D-029 (c)): 1 if some flag in t+1 … t+w exceeds the flag at t
    (0 at t, 1 later), else 0; a holder at t gets 0. Null when the flag at t is null or no
    forward flag is known (SQL semantics: a null never counts). The column must be boolean, or
    numeric with only 0, 1 and nulls;
  - regression, `forward_sum`: the sum of the known values over t+1 … t+w; null when none is
    known. The column must be numeric, without NaN.
- `periods.PERIODS` (`periods.py`, one plain dict, no config import): per `time.period` a
  `Period` spec with the period index (consecutive periods → consecutive integers) and its
  inverse (as the period's end), the start and the end, the same two in Spark, the label
  (`2025-06`, `2025-W23`, `2025-06-15`) and which dates a config may write (the typo rule).
  Month: `year × 12 + month − 1`, the last day; week: ISO, Monday to Sunday, held as the
  Sunday; day: itself. `period_spec(cfg)` picks the config's. Every step between periods goes
  through the index, never `add_months` or added days (T19). `label_by_period(rows, field,
  spec)` and `period_labels(first, last, spec)` build the per-period dicts, keyed by label,
  that every log entry uses.
- `read_keyed_source(cfg, entity, name, env, spark) -> tuple[DataFrame, dict]` (`sources.py`,
  which owns `KEYS = ["unit_id", "period"]` and `HELPER_COLUMNS = ["target", "split",
  "eligible"]`): the source with its keys as `unit_id` and `period`, `unit_id` cast to string
  (T22), the period moved to its end. Refused: a period column that is not a date or timestamp,
  a timestamp not at 00:00 in the session time zone (it may land in another period), an empty
  source, a null period, a null unit id, a repeated key, and a source column named like a key
  or a helper column (`target`, `split`, `eligible`), naming the column and the source. The
  log names the source, its periods (as labels), the raw type of its id column (`id_type`, so
  a join that matches nothing can name both sides' types) and how it tagged its periods:
  `period start`, `period end` or `other days` (D-129).
- `check_periods_covered(log, first, last, role, until, spec)` (`sources.py`): the one check
  that a read source has every period from `first` to `last`, failing with the source's `role`
  and the missing periods (`missing_periods(periods, first, last, spec) -> list[str]`, labels),
  the message naming `time.observation_window.first` and `until` (`last` in the config's
  terms); the dataset calls it for the spine (to the validation period) and Target Factory for
  the target source (to the validation period + `w`).
- `build_targets(source: DataFrame, cfg: UseCaseConfig) -> DataFrame`: on a keyed source, lazily;
  the forward window t+1 … t+w over the spec's period index in Spark, so a missing period is a
  gap, never skipped; null unless all `w` periods are present (panel edge, leavers, gaps); an
  unknown rule fails naming the task's rules. Columns: `unit_id`, `period`, `target`,
  `null_in_window` (null where the window is incomplete; for a complete window, whether the raw
  column was null at t or in the window; its share goes to the summary and the model input's
  sidecar, and the dataset's contract check calls it out above 0; the column itself never
  reaches the panel).
- `load_targets(cfg, entity, env, spark) -> tuple[DataFrame, dict]`: the target source (the spine
  when `targets` is omitted) read keyed and checked before anything is built: the target column
  exists and passes the task's check, and the source has every period from
  `observation_window.first` to the validation period + `w` by index (`check_periods_covered`,
  `until` = `time.validation_period + target_window`; a gap would null w targets; a short
  source would leave the validation labels immature). Then the rule is built, or the upstream
  `column` taken as `target`, refused when it has values in the source's last `w` periods
  (immature labels filled, or a shorter window than `w`) or none in the period before them (a
  longer window than `w`, whose target windows would overlap the validation period's, §4.2).
  Returns the targets and the source's log; the dataset joins them, per use case, as
  `target_<use_case>` (D-131).
- `target_lineage(cfg) -> list[str]`: `column`, then the config's `lineage`, without repeats.
- `run_target_factory(cfg, entity, env, spark) -> pd.DataFrame` (public, D-024), per config:
  the task's summary per period (labelled by the spec) plus an `all` row, printed and returned:
  rows and the null share for every period, with `null_value_share` (the share of the target
  source's rows in the window with a complete target window, before eligibility, that held a
  null in the target column; unknown for an upstream target); the mean
  target and, for binary, the positive rows and the positive events (distinct units, D-082) for
  the observation window's periods only, so no later period's label rate, the validation
  period's among them, is shown (`CLAUDE.md` §4.4). It covers every row of the target source
  before eligibility, and says so. Writes nothing. The notebook `01_target_factory` and
  `run a.yml b.yml --stages target_factory` call it per config, then `save_model_input` once
  for every config that names the model input ([dataset](dataset.md), [run modes](run_modes.md)).
- Tested against the oracle on the `unit` preset: `flag_goes_up` on the holdings equals the
  oracle's `cc_acquire` on the non-holders at t (the oracle's own eligibility), nulls included,
  and `forward_sum` on the mart equals its next-3-month card spend for holders. Hand-made
  sources (monthly) cover the window bounds, gaps, leavers, the null semantics, every column
  refusal, the period coverage, the upstream tail and session time zones east and west of UTC;
  one weekly and one daily forward-window test (a missing period is a gap), the end-of-period
  move for a week and a day, the index round trip for all three periods, `missing_periods`
  across a year end for weeks, and the id cast (an integer id reads back as a string). The
  synthetic flags are never null, so the null semantics are tested on hand-made panels only.

## Open questions
- How a use case reads from the feature store, and how that work splits with the feature store
  team (OD-26).
