# EDA additions from the 2026-11-06 brainstorm: the build spec
_Status: approved direction, 2026-11-06 (the SDS's answers to Q525–Q530, recorded verbatim in
§0.2). Written for the implementer in the review-3 chat, to be merged with the SDS's review-3
remarks into one build; the SDS reads it as a design to veto. Decisions the spec makes without the
SDS are numbered V55 onwards (§5); when merged, they continue `plan.md` §9 and the questions move
into `answers.md`. Nothing here is built._

## 0. How to work
1. Read first: this file whole; `docs/components/eda.md` (Levels 1–2, "The views", "Interface",
   "Code map"); `docs/components/reporting.md` ("Chart rules", "The chart primitives");
   `docs/components/target_factory.md` Level 2; `docs/components/feature_ledger.md` Level 2; then
   each step's modules before touching them. `review2_spec.md` beside this file shows the format
   of the previous build and its step reports.
2. Rules that bind here: `CLAUDE.md` §1 (code-light; functions ≤ ~50 lines; a docstring and type
   hints on every function, private ones included, checked by `tests/test_code_rules.py`), §2
   (artifact versions: the model input's sidecar and the ledger change here), §7 (lean tests, real
   local Spark, no mocks), §8 (owner docs in the same change), §9 (never commit; no new
   dependency); D-035 (whatever cannot be computed or drawn is decided before, never caught);
   D-050 (every task-specific choice is a `TASK_SPECS` entry, never `if task == "binary"` in a
   view); D-135 (every statistic over the window comes from the cells; the snapshot is the one
   collected frame).
3. Minor steps A–F (§3). A, B, C and D touch disjoint files and run in parallel; E needs A–D; F
   needs E. After each step: the tests of the touched modules and `ruff check` on the touched
   files, then the `code-reviewer` subagent and the `simplicity-review` skill; `compat-guardian`
   on C and D (artifact versions, a public return type); `ml-correctness-auditor` on A (it reads
   labels). The full suite runs once at the end, on the main thread in the background (D-072 (m)).
4. Verify on the pinned versions before relying on it (§6).
5. Step report every time: what changed, tests run and result, reviewer findings and what was
   done with each, open risks.

### 0.1 Where this came from
An independent look at EDA (2026-11-06, `worknotes/log.md`): the report lists the declared
decision and computes nothing with it; the value ranges of the candidates are shown for the ten
key features only (the legacy `univariate_summary` had them for every numeric and the drop was
never recorded); the ledger does not say which source a column comes from and the sources'
matched rows per period sit in the join log and never in the report; two sentences describe a
twenty-group histogram nothing draws.

### 0.2 The questions and the SDS's answers (verbatim, 2026-11-06)
The SDS's remarks on the shortlist: "Decision view: I like it a lot to break it down for top
decile (or similar view)" · "Value profile: Put it in the Extended section of the report, but I
didn't find it extremely valuable in the crunch" · "Population's time dimension: unlikely that by
any strata value population composition would shift meaningfully, probably could be skipped" ·
"source in the ledger: I agree, it should be there".
- **Q525.** Add the decision view: a headline line and, per key feature, capture and lift at
  `n / eligible rows` for top_n, else at 1, 5, 10 and 20%? Order by value in the window's
  direction, the cross-fitted order for categoricals. [yes] — **Answer:** "These views should
  follow evaluation slices." → **Outcome:** the slices are `evaluation.slices` (§2.1), not a
  fixed list.
- **Q526.** The value profile as ledger columns and an appendix table, no flag? [yes] —
  **Answer:** "Answered above" → **Outcome:** built, lean, in the report's Extended part, not in
  the ledger (§2.2).
- **Q527.** The time dimension: (a) strata by compared period, (b) the stored counts for the gap
  and latest periods, (c) entries and exits, (d) unlabelled rows per period. [(a), (b), (d)] —
  **Answer:** "Answered above, skip" → **Outcome:** left out, all four.
- **Q528.** The source column and the coverage table? [yes] — **Answer:** "Yes" → §2.3.
- **Q529.** The histogram wording: delete the two sentences, or build the chart? [delete] —
  **Answer:** "Default" → §2.5.
- **Q530.** The event-offset view: Target Factory's summary, echoed by EDA only for
  framework-built targets? [yes, Target Factory first] — **Answer:** "Yes" → §2.4, **with a
  correction**: the offset distribution is flat by construction and is replaced by the
  occurrences per period (V63). The EDA echo waits.

## 1. Goal and scope
EDA gains three things and Target Factory one; two docs lose a sentence:
- **the decision view:** what one key feature achieves at the evaluation slices (capture, the
  slice's rate or mean, lift), the number a model will have to beat, in Core after the ranking;
- **the value profile:** every supported candidate's value range, in Extended, last;
- **the sources:** each column's source in the ledger and the kinds table, and the sources'
  matched share per compared period in Core after the funnel;
- **Target Factory:** the occurrences per period beside the per-period summary (binary: the
  conversions that happen in each period; regression: the amount per period);
- the twenty-group histogram wording deleted.

Left out, deliberately: the population's time dimension (Q527: strata by period, the gap and
latest periods' counts in the report, entries and exits, the unlabelled rows per period); an
events-per-candidate line; EDA echoing Target Factory's occurrences (later, framework-built
targets only); repeat conversions of one unit (a view waits for a use case that asks); WoE/IV; a
quick multivariate model (it would fit on test clients, §4.4); window twins of the slices (the
snapshot alone, one row per client); any change to the ranking's columns or the key-feature rule;
Feature Checks (major step 3 reads nothing new: the slices and the profile are EDA's views only).

## 2. The target state

### 2.1 The decision view: "At the decision's slices" (Core, between the ranking and the deep dives)
**What it answers.** If a list were built from this one feature alone, what would the top slice
capture, and at what rate? Concordance says how well a feature orders clients; the slice says what
that is worth at the operating point, and it is the pre-model number a model has to beat. A
feature that captures far more than the others, or nearly everything, is a leak candidate before
any model exists. Descriptive only: the decision stays declared before any result (§4.3); nothing
here chooses a baseline or a metric.

**The slices** (`eda/slices.py::slice_shares`): the resolved `evaluation.slices.top_pct` (the
level default fills a null: `autonomous` [0.01, 0.1], `assisted` [0.01, 0.05, 0.1]) and
`evaluation.slices.top_n`, each count as a share of the snapshot's labelled rows (eligible rows
with a known target), a count above the rows skipped and said in the caption (the crunch's rule,
`lessons.md`); for a `top_n` decision, `decision.n` is added first as its own slice unless the
same count is listed (V55). Labels: `top 1%`, `top 10%`, `n = 10,000`, `decision n = 10,000`.

**The population and the order.** The snapshot period's current cells of each key feature,
labelled rows only, one row per client (the deep dives' population). The list order is the
one-feature rule a person could apply (V56):
- a numeric: by value, best first, in the raw sign of the snapshot's concordance (sign of
  `concordance − 0.5`; 0 reads `+`), so a non-monotone feature's list takes one end only, which
  the caption says;
- a categorical: its levels ordered by their target rate on the window periods other than the
  snapshot (`pool_periods` over `window − {snapshot}`), out of sample for the snapshot; a level
  without a row there comes after the ordered levels; with a one-period window the feature is
  "not available: one window period gives no out-of-sample level order" (decided up front,
  D-035);
- the null bin last, whatever the kind: a one-feature list cannot rank what it does not know.

**The numbers per slice** (`capture_table`), from the ordered bins' cumulative `n`, `sum_y`,
`sum_y2` and support, cut at the slice's share with linear interpolation inside the boundary bin
(V57): `slice`, `share`, `rows`, `support` (the task's: positives, or units with a non-zero
target, the rule `shares` uses for `events`), `estimate`, `low`, `high` (the task's
`period_estimate` on the cumulative counts: a rate with its Wilson interval, a mean with its
t-interval), `lift` (estimate / the snapshot's base, `meta["snapshot_base"]`, only when
`lift_available(base)`), `capture` (cumulative `sum_y` / total `sum_y`: the share of positives,
or of the total amount; for an amount only when `lift_available`), `insufficient` (support below
`MIN_BIN_SUPPORT`, greyed), `unavailable` (the reason, else empty). `sum_y` is the capture
numerator for both tasks (a 0/1 target sums to its positives); the per-task spec gains
`capture_noun` (`positives` / `amount`) for the captions and axis titles.

**The curve** (`capture_curve`): the same cumulative capture at a 1% grid of shares (1% … 100%)
per key feature, plus a `random` group whose capture equals the share (the diagonal). Drawn with
`grouped_lines` on a numeric x axis (V65), one line per key feature in rank order, y "Share of
<capture_noun> captured", x "Share of rows (best first)".

**The views** (`report.py::_slices_views`, key `slices`: `[paragraph, Styler, Figure]`):
1. The decision paragraph: for a `top_n` decision "Decision top_n: n = 10,000, 10.5% of the
   snapshot's 95,210 labelled rows. 2,790 positives: a perfect list captures all of them at 27.9%
   precision; a random list captures 10.5% at the base rate 2.93%." (the perfect-list sentence
   from a per-task entry `perfect_list(n, rows, support) -> str | None`, binary only; an amount
   has none, decided up front); for the other decision types "Decision <type>: no fixed list
   size; the evaluation slices stand in."
2. The table: key features in rank order × slices, columns `slice`, `capture`, `estimate`, `lift`,
   `support`; coloured by lift, insufficient greyed, a feature's unavailable rows say why. Caption:
   the slices' source, the one-feature order rule in a sentence, the skipped counts.
3. The curve chart. The first thing to drop if the step runs long (V58): the table is the view
   the SDS asked for.

Notebook 02 displays `result.views["slices"]` in step 5 after the ranking. The choices table gains
one row `slices` (label "Decision slices", path `evaluation.slices` + `decision.n`, alternatives
"any shares in (0, 1] and list sizes"); `eda.json` gains `slices` (label → share). EDA's settings
digest (`SETTINGS_PATHS`) does not change: Feature Checks reads neither table.

**Stored:** `tables/slices.parquet` (`feature` + the columns above) and
`tables/capture_curve.parquet` (`feature`, `share`, `capture`), both keeping their columns when
empty (no key feature).

### 2.2 The value profile (Extended, after the correlation overview)
One table, every supported candidate in rank order (`eda/profile.py::value_profile`): `feature`,
`kind`, `rank`, `rows`, `missing_share` (from the ranking), `min`, `p1`, `median`, `p99`, `max`
(a numeric's finite non-null values on the snapshot's eligible rows; one vectorised `quantile`
call over the numerics, never a per-column loop), `inf_share` (±infinity over all rows),
`top_levels` (a categorical: its three largest levels on the snapshot's cells with their shares,
as text, blank levels quoted as in N3: `"'': 12.0% · A: 40.1% · B: 31.5%"`; a numeric: empty).
Numbers in the `VALUE` format, shares as percentages. Caption: what the columns are and that a
sentinel (−1, 999, 9 999 999) shows as a mass point at `min` or `max`. Not in the ledger (V59):
it describes values, not a feature's path. Stored as `tables/profile.parquet`.

### 2.3 The sources
1. **The read log** (`sources.read_keyed_source`): the log gains `columns`, the source's non-key
   columns as the panel carries them (after `renamed`).
2. **The join entry** (`panel._join_entry`) copies `columns` for every source, the spine and the
   targets' sources included. The model input's sidecar stores the log, so a saved input carries
   it: `MODEL_INPUT_SCHEMA_VERSION` 3 → 4 (V61); an older input is refused by the existing
   version check, which names `save_model_input`, and is rebuilt (0.x, D-007 (c)).
3. **The frames' meta** gains `sources: dict[str, str]`, column → source name, for every
   candidate and lineage column, built from the join entries (`dataset/frames.py::_column_sources
   (log) -> dict[str, str]`); a candidate in no entry fails loud naming it (the column-clash check
   makes the mapping unique).
4. **The ledger** gains the identity column `source` (`create_ledger(candidates, kinds, lineage,
   unsupported, sources)`, `COLUMNS_BY_STAGE["identity"]`), `LEDGER_SCHEMA_VERSION` 1 → 2: an
   older ledger is refused by `read_ledger` and EDA reruns. The kinds table in the appendix shows
   `source` beside `kind`.
5. **"Sources per period"** (Core, after the funnel; `population.sources_per_period(log, periods)
   -> pd.DataFrame`): one row per compared period (window, gap, latest, then `all` over those
   periods, V62), one column per joined feature source with the share of the spine's rows it
   matched (`matched[period] / rows[period]` from the entries); the spine's rows as the first
   column. "Not available: the spine is the only source" when nothing is joined. Caption: a share
   well below 1 means that source's columns are null for the rest, and a drop in the latest
   periods means a source that arrives late. Stored as `tables/sources.parquet`; view key
   `sources`.

### 2.4 Target Factory: the occurrences per period
**Why not the event offset.** Under `flag_goes_up` a unit converting in period m is positive at
m−1 (offset 1), m−2 (offset 2) … m−w (offset w): every conversion puts one positive row at every
offset, so the offset distribution is flat except at the source's edges and gaps. The same holds
for an amount under `forward_sum`. The view that carries information is **when the events
happen**: conversions per period, which the per-period positive counts smooth over w periods and
which is the volume a list competes to capture (V63).

**The table** (per-task entry `summarise_occurrences(source, cfg) -> pd.DataFrame`, over the
target source's whole span, before eligibility, label-free, so every period may show):
- binary: `period`, `conversions` (rows whose flag is 1 while the flag at the previous
  consecutive period, `rangeBetween(-1, -1)` over the period index, is 0; a unit's first row
  never counts: no previous period), `flag_rows` (rows with the flag 1);
- regression: `period`, `total_amount` (the sum of the target column), `nonzero_rows`.

`run_target_factory` prints it after the per-period summary and returns
`TargetSummary(per_period: pd.DataFrame, occurrences: pd.DataFrame)`, a frozen dataclass in
`target_factory.py` (a public return type change, V63; `architecture.md` Public API). The target
source is read once: `load_targets` splits into the keyed read and `build_targets`, so the
occurrences read the same frame. The panel and the model input do not change. Notebook 01 shows
both tables with a guide paragraph: a spike in conversions is a campaign or a data change, which
the per-period rate shows only as a blur over w periods; compare with the positive events.

### 2.5 The histogram wording
Delete "twenty for histograms" from `reporting.md` chart rule 4 and the sentence "A chart that
shows a distribution from the cells merges them to twenty groups by the same rule" from `eda.md`
"The statistics"; rule 8 (box plots from quartiles) stands (V64).

## 3. Minor steps
Each step names its files, functions and tests. Signatures are the target; a builder who finds a
simpler shape says so in the step report.

**A. The decision view's data** — `src/core_modelling/eda/slices.py` (new), `tasks.py`,
`statistics/cells.py`.
- `tasks.py`: `capture_noun` (`"positives"` / `"amount"`), `perfect_list(n: int, rows: int,
  support: int) -> str | None` (binary the sentence; regression `None`).
- `cells.py`: `support_by_bin(pooled: pd.DataFrame) -> pd.Series` (labelled rows outside the
  zero target bin per `bin`, the rule `shares` uses).
- `slices.py`: `SLICE_GRID`; `slice_shares(resolved: UseCaseConfig, rows: int) -> dict[str,
  float]`; `ordered_bins(cells: pd.DataFrame, kind: str, sign: int, snapshot: str, window:
  list[str]) -> pd.DataFrame | None` (one feature's snapshot bins pooled over target bins with
  `n`, `sum_y`, `sum_y2`, `support`, in list order; `None` = not available); `capture_table
  (ordered: pd.DataFrame, shares: dict[str, float], base: float, task: str) -> pd.DataFrame`;
  `capture_curve(ordered: pd.DataFrame, grid: np.ndarray) -> pd.DataFrame`; `slice_tables(cells:
  pd.DataFrame, ranking: pd.DataFrame, meta: dict, resolved: UseCaseConfig, window: list[str])
  -> tuple[pd.DataFrame, pd.DataFrame]` (the stacked `slices` and `capture_curve` over the key
  features; a feature not available gets one `slices` row with `unavailable` filled).
- Tests (`tests/test_eda_modules.py`): a feature whose top bins hold every positive captures
  `min(1, share / base)` at each share; a feature independent of the target gives a curve within
  noise of the diagonal; `sign = -1` reverses the order; a categorical on a one-period window is
  not available; a count above the rows is skipped; `decision.n` is added once; capture at 100%
  is 1 for both tasks; the regression capture is unavailable when the mean is not positive.

**B. The value profile** — `src/core_modelling/eda/profile.py` (new).
- `PROFILE_COLUMNS`; `value_profile(snapshot: pd.DataFrame, kinds: dict[str, str], ranking:
  pd.DataFrame, cells: pd.DataFrame, snapshot_period: str) -> pd.DataFrame`.
- Tests: on a toy frame with nulls, ±infinity and a sentinel the ranges equal pandas on the
  finite values and `inf_share` counts the infinities; `top_levels` matches the snapshot's level
  table; the columns hold when there is no categorical, and when no numeric.

**C. The sources** — `sources.py`, `dataset/panel.py`, `dataset/model_input.py`,
`dataset/frames.py`, `ledger.py`.
- `read_keyed_source`: `log["columns"]`; `_join_entry`: copies it; `MODEL_INPUT_SCHEMA_VERSION =
  4`; `frames._column_sources(log: list[dict]) -> dict[str, str]` into `meta["sources"]`;
  `create_ledger(..., sources: dict[str, str])`, `COLUMNS_BY_STAGE["identity"]` + `source`,
  `LEDGER_SCHEMA_VERSION = 2`.
- `eda/population.py`: `sources_per_period(log: list[dict], periods: list[str]) ->
  pd.DataFrame`.
- Tests: the join entry lists the source's columns after the rename (`tests/test_dataset.py` or
  `test_sources.py`); a sidecar at version 3 is refused naming `save_model_input`; every candidate
  of the example use case maps to a source (`tests/test_frames.py`); the ledger carries `source`
  and a version-1 ledger is refused (`tests/test_ledger.py`); the sources table's shares equal
  the entries' (`tests/test_eda_modules.py`). The saved example model inputs and the `dev`
  acceptance data are rebuilt by the tests' fixtures or by notebook 01, as after 10-28.

**D. Target Factory** — `target_factory.py`, `tasks.py`, `notebooks/01_target_factory.ipynb`.
- `tasks.py`: `summarise_occurrences(source: DataFrame, cfg: UseCaseConfig) -> pd.DataFrame` per
  task (`_binary_occurrences`, `_regression_occurrences`).
- `target_factory.py`: `TargetSummary`; `_read_target_source(cfg, entity, env, spark) ->
  tuple[DataFrame, dict]` split out of `load_targets`; `run_target_factory` returns
  `TargetSummary`. Check that `save_model_input` and `_join_sources` still select only `target`
  and `null_in_window` from the targets frame.
- Tests (`tests/test_target_factory.py`): on a toy source with known 0→1 transitions the
  conversions per period equal the transitions and a unit's first row never counts; a gap before
  a 1 counts no conversion (no previous consecutive period); the regression totals equal the
  column's sums; on the `unit` preset the conversions summed over the window periods equal the
  oracle's acquisitions there (**read this test**: it is the one that ties the view to the truth).
- Notebook 01: `summary.per_period`, `summary.occurrences`, the guide paragraph of §2.4.

**E. The views, the stage and notebook 02** — `eda/report.py`, `eda/run.py`,
`reporting/charts.py`, `reporting/blocks.py`, `notebooks/02_eda.ipynb`.
- `charts.grouped_lines(..., x_numeric: bool = False)`: a linear x axis in [0, 1] shown as
  percentages, no category padding (V65).
- `report.py`: `_slices_views(tables, meta, resolved) -> dict`; `_profile_view(profile, task) ->
  Styler`; `_sources_view(sources) -> Styler`; `report_sections`: Core = Funnel → Sources per
  period → Target per period → Target by stratum → Univariate ranking → At the decision's
  slices → Key features; Extended = Reference groups → Correlation overview → Value profile;
  `_appendix_views` kinds with `source`; `CHOICE_NAMES` + `slices`; the module docstring's key
  list gains `sources`, `slices`, `profile`.
- `blocks.CHOICES["slices"]`.
- `run.py`: the three tables computed after `_rank` (the profile timed inside `tables`);
  `_stage_meta` + `slices`; `_ledger` passes `meta["sources"]`; `DIVE_COLUMNS`-style empty
  schemas for `slices` and `capture_curve`.
- Notebook 02: step 4 (the sources table: what a low share means), step 5 (the slices: read the
  top decile first; a one-feature list; what a model must beat; too good is a leak; "the slices
  are `evaluation.slices`, a `set` changes them"), step 8 (the value profile in Extended).
- Tests (`tests/test_eda.py`): `run_eda` on the `dev` preset writes the three tables, `eda.json`
  carries `slices`, the report holds the three sections; the exploration functions untouched.
  `tests/test_reporting.py`: `grouped_lines(x_numeric=True)` draws a numeric axis and the
  `random` diagonal.

**F. Docs and the review guide** — §4.

## 4. Docs to update (owner docs, same change)
- `docs/components/eda.md`: Level 1 "Out" (the new tables); "The views" (Sources per period, At
  the decision's slices, Value profile); "The statistics" (the histogram sentence out; `sum_y` as
  the capture numerator); "Code map" (`slices.py`, `profile.py`, `sources_per_period`);
  "Interface" (reads `evaluation.slices` and `decision`; `eda.json` `slices`; the tables);
  "Lessons" (the offset distribution is flat by construction).
- `docs/components/reporting.md`: chart rule 4 wording; "The EDA report" (the sections' order);
  "The chart primitives" (`grouped_lines` `x_numeric`).
- `docs/components/feature_ledger.md`: the `source` identity row; `ledger_schema_version` 2 in
  every mention; Status.
- `docs/components/dataset.md`: the join entry's `columns`; `meta["sources"]`; the sidecar at
  schema 4 and what an older input gets.
- `docs/components/target_factory.md`: the occurrences, `TargetSummary`, why not the offset.
- `docs/components/config.md` and `conf/base/TEMPLATE.yml`: `evaluation.slices` is read by EDA
  too (one comment); `decision.n` as a slice.
- `docs/architecture.md`: Public API (`run_target_factory -> TargetSummary`); the artifact
  inventory (sidecar 4, ledger 2, EDA's new tables).
- `docs/glossary.md`: **Slice** (a top share or list size of the ranking at which metrics are
  read) and **Capture** (the share of positives, or of the total amount, inside a slice).
- `docs/decisions.md`: one new row (the next free D-number; re-read the last row right before
  numbering): EDA shows the key features at the evaluation slices (a view, never a baseline;
  `decision.n` joins them); the value profile lives in Extended, not the ledger; a column's
  source is ledger identity and the sources' matched share a Core view; Target Factory reports
  occurrences per period, since an offset distribution under a forward-window label is flat by
  construction. Sources: the brainstorm's log entry; the per-feature slice reading follows the
  crunch's top-k rule (`lessons.md`).
- `docs/context/lessons.md`, statistical lessons: the flat-offset fact, one bullet.
- `docs/UPDATES.md`: the EDA, feature ledger, dataset and Target Factory rows; one log line.
- `worknotes/m2_2_understanding/review_guide.md`: reading-order items for the slices table and
  `slices.py`, the sources table, `TargetSummary`; the one **read this test** of step D.
- `worknotes/log.md`: the build's entry.

## 5. Decisions to veto (V55 onwards; renumber if the merge needs it)
- **V55** For a `top_n` decision `decision.n` joins the evaluation slices as the first slice;
  the other decision types take the evaluation slices alone.
- **V56** The one-feature order: a numeric by value in the raw sign of its snapshot concordance;
  a categorical by its level rate on the other window periods (out of sample for the snapshot),
  not available on a one-period window; the null bin last.
- **V57** Linear interpolation inside the boundary bin; the curve on a 1% grid; `random` as the
  diagonal group.
- **V58** The slices view sits in Core between the ranking and the deep dives; the curve chart
  is the first piece to drop if the step runs long.
- **V59** The value profile: ranges from one vectorised pandas call on finite values,
  `top_levels` from the cells; not a ledger column; Extended, last.
- **V60** Two small modules, `slices.py` and `profile.py`, rather than growing `ranking.py`.
- **V61** `columns` in the join entry; the sidecar at schema 4 and the ledger at schema 2, older
  files refused and rebuilt (0.x, D-007 (c)).
- **V62** The sources table runs over the compared periods, with `all` over those periods.
- **V63** Target Factory reports the occurrences per period instead of the offset distribution;
  `run_target_factory` returns a `TargetSummary` dataclass (a public return type change).
- **V64** The two histogram sentences are deleted; chart rule 8 is unchanged.
- **V65** `grouped_lines` gains `x_numeric` rather than a sixth chart primitive.

## 6. Verify first, on the pinned versions
- plotly 6.3.1: a linear x axis with `tickformat=".0%"` and the existing `_add_line` on numeric
  x; the interval and support paths are not used by the curve.
- pandas 2.2.3: `DataFrame.quantile([0, .01, .5, .99, 1])` over numeric columns after
  `replace([inf, -inf], nan)`, and its cost on the 100k snapshot (expect well under a second).
- PySpark 3.4.3: `F.max(value).over(Window.partitionBy("unit_id").orderBy(period_index)
  .rangeBetween(-1, -1))` as the previous consecutive period's flag (null for a unit's first
  row or after a gap), and that the occurrences aggregate adds one pass, not a shuffle per
  period.
