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
   - binary is a rule on a forward window (e.g. adoption, activation, reactivation): a flag or a
     count going up, or a threshold on a forward sum. "Going up" compares the observation month
     with the forward months: some value in t+1 … t+w exceeds the value at t (D-029 (c)), in any
     month of the window, not only at its end: end-of-window rules miss events that reverse
     inside the window and, for loans, openings hidden by a maturity. Who is in the population
     (e.g. non-holders only) is an eligibility criterion, never the rule's: a holder at t gets a
     0 from the flag rule. Acquisition is one target whether the client never held the product
     or churned, since a churned client is a non-holder at t; build it from the flag, not the
     status column, so lineage exclusion keeps the status's churned signal. Stage 1 builds the
     flag rule (`flag_goes_up`, a 0/1 column) with lineage; the count rule (`count_goes_up`),
     the amount rules and the thresholds on sums are separate rules, with leavers as negatives,
     by release 1.0 (M4, D-091);
   - regression is the second task in Phase 2 (D-020). Stage 1 builds its forward-sum rule
     (`forward_sum` over `t+1 … t+w`) beside the flag rule, so the per-task dispatch is real from
     day one; the rest of regression waits for M4 (D-091).
4. Forward windows exclude the current month `(1, w)` (T8). Windows come only from config (T13).
5. **Panel-edge guard:** the target is null where the full forward window is missing, per client:
   also where the client left inside the window (default). Null **values** follow SQL semantics
   (D-029 (c)): a null never counts as an event, and the target is null only when nothing can be
   compared (the value at t, or every forward value, null); the summary shows the share of rows
   whose window held a null, and `data.target.null_as` gives the value a null stands for when
   the source codes zeros as nulls. The alternative, `leavers: negative`,
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
- Owns invariant §4.1 (time separation) for **built** targets. An upstream target can't be
  checked for it; Target Factory refuses one that has values in the source's last `w` months,
  where a target over t+1 … t+w can't be known yet.
- Eligibility is not materialised here. It is an ordered config step applied when the dataset is built
  ([dataset](dataset.md)). Targets are therefore built over every row of the target source (the
  forward window reads a client's later months whatever their eligibility), and the dataset
  selects the eligible rows afterwards.

## Lessons from the crunch
T8, T11, T12, T13, T19.

## Interface
Built in Stage 1's major step 2 (2026-10-26; under the SDS's review), in
`core_modelling/target_factory.py`, `core_modelling/tasks.py` and `core_modelling/sources.py`.
- `TASK_SPECS` (`tasks.py`): the per-task spec dict; per task a rule, a target-column check and a
  summary; the contract checks join with the dataset ([dataset](dataset.md)). A rule gets the
  target column (with `null_as` applied), the forward window and `w` and returns the target as a
  Column; it compares the value at t with the forward values and never counts t as the event:
  - binary, `flag_goes_up` (D-029 (c)): 1 if some flag in t+1 … t+w exceeds the flag at t
    (0 at t, 1 later), else 0; a holder at t gets 0. Null when the flag at t is null or no
    forward flag is known (SQL semantics: a null never counts). The column must be boolean, or
    numeric with only 0, 1 and nulls; `null_as`, if set, 0 or 1;
  - regression, `forward_sum`: the sum of the known values over t+1 … t+w; null when none is
    known. The column must be numeric, without NaN.
- `read_keyed_source(cfg, entity, name, env, spark) -> tuple[DataFrame, dict]` (`sources.py`):
  the source with its keys as `unit_id` and `month`, the month at its last day. Refused: a month
  that is not a date or timestamp, a timestamp month not at 00:00 in the session time zone (it
  may land in another month), an empty source, a null month, a null unit id, a repeated key. The
  log names the source, its months and how it tagged them (D-129).
- `build_targets(source: DataFrame, cfg: UseCaseConfig) -> DataFrame`: on a keyed source, lazily;
  `data.target.null_as` applied to the column first; the forward window t+1 … t+w over a month
  index (`year × 12 + month`, never `add_months`, T19), so a missing month is a gap; null unless
  all `w` months are present (panel edge, leavers, gaps); an unknown rule fails naming the task's
  rules; `leavers: negative` raises until M4 (D-091). Columns: `unit_id`, `month`, `target`,
  `null_in_window` (for a complete window: the raw column was null at t or in the window; the
  dataset logs its share and drops it).
- `load_targets(cfg, entity, env, spark) -> tuple[DataFrame, dict]`: the target source (the spine
  when `targets` is omitted) read keyed and checked before anything is built: the target column
  exists and passes the task's check, and the source has every month from `train_months.first`
  to `validation_month + w` (a gap would null w targets; a short source would leave the
  validation labels immature). Then the rule is built, or the upstream `column` taken as
  `target`, refused when it has values in the source's last `w` months (immature labels filled,
  or a shorter window than `w`) or none in the month before them (a longer window than `w`,
  whose target windows would overlap the validation month's, §4.2). Returns the targets and
  the source's log; the dataset joins them (step 3).
- `target_lineage(cfg) -> list[str]`: `column`, then the config's `lineage`, without repeats.
- `run_target_factory(cfg, entity, env, spark) -> pd.DataFrame` (public, D-024): the task's
  summary per month plus an `all` row, printed and returned: rows and the null share for every
  month, with `null_value_share` (rows whose window held a null in the target column; unknown
  for an upstream target); the mean target and, for binary, the positive rows and the positive
  events (distinct units, D-082) for the observation window's months only, so no later month's
  label rate, the validation month's among them, is shown (`CLAUDE.md` §4.4). It covers every
  row of the target source before eligibility, and says so. Writes nothing. The notebook
  `01_target_factory` and `run --stages target_factory` call it, then `save_model_input`
  ([dataset](dataset.md), [run modes](run_modes.md)).
- Tested against the oracle on the `unit` preset: `flag_goes_up` on the holdings equals the
  oracle's `cc_acquire` on the non-holders at t (the oracle's own eligibility), nulls included,
  and `forward_sum` on the mart equals its next-3-month card spend for holders. Hand-made
  sources cover the window bounds, gaps, leavers, the null semantics with and without `null_as`,
  every column refusal, the month coverage, the upstream tail and session time zones east and
  west of UTC. The synthetic flags are never null, so the null semantics are tested on hand-made
  panels only.

## Open questions
- How a use case reads from the feature store, and how that work splits with the feature store
  team (OD-26).
