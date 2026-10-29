# Dataset: observation window, frames, splits, sampling
**Status:** built thin (M2.1, 2026-10-27; for the SDS's review with Target Factory) · **Legacy:** `src/io.py` (load + prune in Spark), `src/dataset.py` (labelled frames, downsampling)
**Related:** [config](config.md) (the `data` and `time` sections) · [environment](environment.md) (sources, the collect budget) ·
[target factory](target_factory.md) · [training](training.md) · [evaluation](evaluation.md) ·
[feature checks](feature_checks.md) · [EDA](eda.md) · [test harness](test_harness.md) · D-030, D-049, D-052, D-054,
D-082, D-083, D-088, D-091, D-098, D-106, D-117, D-129, D-130, D-131, D-133 · OD-17

## Purpose
Builds the frames every stage works on, from one data definition: the governing spine and the
other sources joined, eligibility applied, the target attached, the client split assigned, then
collected from Spark with a printout of what is about to leave it. Eligibility is two ordered
lists (D-129): an **analysis filter** drops its rows before EDA; a **modelling filter** keeps
them for EDA, tagged by the step's name, so EDA can compare the excluded group (e.g. current
holders) with the modelling population, and drops them before Feature Checks. Two frame shapes
come from the same definition (D-030): the **window frame** (every unit-period in the observation
window after the analysis filters, the modelling tags as columns, every client, labels included)
for EDA, its eligible rows for Feature Checks, and **train / test / validation** (eligible rows
only) from Training on. The frames can be built in memory on every call or read from the
saved **model input** that Target Factory's notebook writes, one table for one or several use
cases (D-131). The unit of analysis is a **period** (`time.period`: month, week or day; one row
per unit per period, held as its last day, D-129). Training on a window of periods instead of a
single one is a Phase 2 big-ticket item (D-030). This doc owns its downstream effects.

## Time model

The unit of analysis is the **period** set by `time.period` (`month`, `week` or `day`): one row
per unit per period, every period held as its last day (a month's last day, a week's Sunday, the
day itself), every step between periods taken on a period index, never `add_months` or added days
(T19), through one dict of period specs (`periods.PERIODS`: the index, the start and the end, in
Python and in Spark, the label, and which dates a config may write; D-129). The spans, earliest
to latest:

1. **Backward windows**: the history upstream rollup features look back over, reaching before
   `t1`. The framework doesn't check them: features come from upstream (D-129).
2. **Observation window `t1 … tk`**: train + test, every eligible unit-period in it, split by
   client.
3. **Target windows**: the forward periods the window's targets look into; the last one ends at
   `tk + w`.
4. **Validation period `v ≥ tk + w`** (OOT): its target window (`v+1 … v+w`) starts after the
   last training target window ends (`tk + w`).
5. **Inference**: later periods, after `v`.

- Features are as-of each observation period; targets look forward `(1, w)` (§4.1).
- The observation window (`time.observation_window`), `w` (`time.target_window`, in periods, one
  number shared by the target builder and the time checks) and the validation period
  (`time.validation_period`) are set in the config (D-129). The validation period sits outside
  the data-definition hash (EDA never reads it; Feature Checks reads it only to leave it out of
  its comparisons and records the periods it compared). Moving it changes the config hash before
  the config freezes and the resolved-input hash after (an audit-log entry), never the
  data-definition hash. The inference period is a run argument. Changing the validation period
  after the config freezes is an audit-log entry, refused when any Feature Checks run compared
  that period (D-088). A Phase 2 production retrain keeps the window and the clients; only the
  inference period moves, since inference always runs on the latest period (D-088, D-052).
- Checked at load: `first ≤ last` and `v ≥ tk + w` by period index; checked when the panel is
  built, by one function (`check_periods_covered`, `sources.py`): the spine has every period
  from the window's first to `v`, the target source to `v + w` (D-129; [config](config.md)
  req. 8).
- Default window: 6 periods with `w = 3`, in the examples and as level defaults (D-091).
- Validation is a single period for panel tasks. Series tasks will need rolling validation
  (later).
- Example on the 24-month synthetic panel (monthly, so period = month) with 6-month upstream
  rollups, `w = 3` (an illustration: the window is chosen per use case, and the synthetic data
  is built for none in particular, D-064):
  - window = months 6–11;
  - validation month = 14, labels mature by 17;
  - months 18–21 are free to test scoring plus monitoring with matured labels.

## Frames (D-030, D-131)
`Frames(window, train, test, validation, log, meta)`, built by `build_frames(cfg, entity, env,
spark, stage)`, which collects only what the stage asks for:
- `window`: every unit-period in the observation window after the analysis filters, with
  `target`, the modelling tag columns and `eligible` (every modelling filter passed), for EDA
  (`stage` `eda`): every client, labels included, so EDA's population and reference-group views
  use every row and the tags as strata (D-030). For Feature Checks (`stage` `feature_checks`)
  the same frame's eligible rows only (`eligible = 1`): every eligible client, labels included,
  no split yet.
- `train` and `test`: the window split by client; `validation`: every eligible unit at `v`, with
  the `split` column so Evaluation can also show test clients only (`stage` `training` /
  `evaluation`). Rows with a null target are dropped from these modelling frames, with the share
  logged per period. `train` is sampled when the config declares sampling (req. 6).
- `log`: the join, eligibility, contract, null-target, sampling and collect logs, in order.
- `meta`: the hashes, the lineage, the candidates, the tags, the sampling record and the
  collect estimate and measured size per frame (D-133); the per-period rows, positive rows and
  positive events (D-082) are Target Factory's summary.

Whether the panel is read from the model input or built in memory, the frames are the same: the
saved table holds only the sources joined plus the target columns, and everything the config
derives from them (eligibility, the candidates, the contract checks, the split) is computed on
read by the same functions (D-131, the section below).

Feature Checks also reads the gap periods and the latest period, label-free, from the model
input (or the in-memory panel), which runs from the window's first period to the spine's last.
Those periods carry `target` wherever the forward window was complete, like every other period
of the panel (an upstream target would too): the reads are label-free by discipline (D-030), not
because the labels are absent.

## Sources and joins (D-129)
- `entities.<e>.sources.features` is an ordered list; the first source is the **governing spine**
  and the others are left-joined to it on the keys. `sources.targets` is one source, left-joined,
  contributing only the target; when it is omitted the target is a column of a feature source.
- The keys are renamed to `unit_id` and `period` at load from `data.keys` (`sources.KEYS`), and
  `unit_id` is cast to string, so an upstream change of the id column's type cannot move every
  client's split (the hash draw is over the column's bytes, T22); the source's raw id type goes
  into its log as `id_type`. A non-key source column named `unit_id` or `period` would clash
  with the renamed keys, so the reader reads it as `source_unit_id` / `source_period`, prints it
  and records it in the source log's `renamed`. A source column named like one the dataset adds
  (`sources.HELPER_COLUMNS`: `target`, `split`, `eligible`) keeps its name at the reader, so the
  target spec names an upstream column as the data scientist knows it (`data.target.column:
  target` works); the read side renames whatever of them remains ([model
  input](#model-input-d-131)). One helper, `sources.rename_reserved`, makes the `source_<name>`
  in both places, and a `source_<name>` that is already a column fails loud naming both. In
  Phase 2 one naming serves every source of a use case.
- On reading, each source's period column moves to the period's end for `time.period` (a month
  to its last day, a week to its Sunday, a day stays), the framework's one period convention, so
  a source tagged on the first day joins one tagged on the last. A period column that is not a
  date or timestamp fails loud naming its type (a format setting waits for a real source that
  needs one). The join log says how each source tagged its periods (`period start`, `period
  end` or `other days`; D-129). Every source is read this way through `read_keyed_source`
  (`sources.py`, built with Target Factory), which also refuses a null unit id and a repeated key.
- Duplicate keys in any source fail loud, naming the source and a few keys; the check runs after
  the period move, so a source carrying both tags for one period fails it. A non-key column
  present in two feature sources fails loud (renamed upstream, or by a per-source alias later).
- The join log prints, per source, its distinct units per period and the share of spine rows it
  matches. A feature source that matches no spine row at all is refused, naming the source and
  both raw id types: the ids are compared as strings, so an empty match means two id systems,
  never a type mismatch.
- Periods run from `observation_window.first` (the earliest, when several configs share a model
  input) to the spine's last period. One function, `check_periods_covered` (`sources.py`),
  checks that a source has every period a caller needs, naming the missing ones by label: the
  spine every period from the window's first to the validation period (a gap would drop a
  period of rows quietly, and the validation period must exist to be scored), the target source
  every period to the validation period + `w` ([target factory](target_factory.md)).

## Model input (D-131)
One saved table per name (`data.model_input`, a logical name the environment file maps to a path
or table), for one or several use cases that share the entity's feature sources, `data.keys` and
`time.period`; their names must differ ignoring case (Spark compares column names that way), and
a target column uses the name's lower-case form, `target_cc_acquisition`. A source column named
like one the framework adds is matched ignoring case too (`Target` is read as `source_Target`).
The examples: `cc_acquisition` and `td_acquisition` share `retail_acquisition_input`, and the
Target Factory notebook saves both in one table. It holds the **sources joined plus one target column per use case, nothing
else**: the governing spine's rows from the earliest observation window's first period to the
spine's last, every column of every feature source, and `target_<use_case>` per use case (every
period Target Factory could build it: wherever the forward window is complete, so the gap periods
and the periods after the validation period are labelled too, as an upstream target would be;
null only at the panel edge, for leavers and across gaps). Everything config-driven after the
join is **derived on read** from the reader's config, deterministic SQL and a hash draw
recomputed exactly: eligibility (the analysis filters, the modelling tags, `eligible`), the
candidates, the contract checks and the client split. A single config is the one-element list:
one shape, whether one use case or several share the table.

In the same folder, `_model_input.json` (sidecar schema 3) holds `schema_version`, the framework
version and when it was built, the entity, the name, the use cases in order, the shared
definition (`hash_version`, the feature sources, the keys, the period, the periods covered as
labels), per use case its target column, target-spec hash, lineage, target source, observation
window, target window, validation period, the target source's last period (`target_last`),
whether the target is read from an upstream column (`upstream`) and the share of the target
source's rows in the window with a complete target window, before eligibility, that held a
null (`null_in_window_share`), the columns and the join log. It is keyed by the shared sources,
keys and period plus each use case's target-spec hash, never by the data-definition hash (D-088).
Its path is local until the M2.4 transport.
- `save_model_input(cfgs)` writes it, for one config or a list, from the Target Factory notebook
  or `run a.yml b.yml --stages target_factory`. Saving freezes each config's data part (sources,
  keys, period, target spec, target window; D-125).
- The read side (`prepare_panel`, on the saved table and in memory alike), where the dataset adds
  its own `target`, `split` and `eligible`, in order:
  1. drops the other use cases' target columns and their **upstream** target columns (a use case
     with `rule: null`), forward-looking, never candidates, by construction;
  2. drops the use case's **own upstream target column** too: its values are exactly
     `target`'s and it is the label, so it is never a candidate and no eligibility condition can
     name it. An upstream label (own or another's) is dropped only when its target source is
     one of the feature sources, so the label itself is in the panel; with a separate
     `sources.targets`, a spine column of the same name is an ordinary column (still kept out
     of the candidates by the lineage, by name). The drops are printed and logged as one
     `drop` entry, each column with its reason;
  3. reads any remaining source column named `target`, `split` or `eligible` as
     `source_<name>`, printed and logged as one `rename` entry (for `target`, the printout adds
     "if it is a label, list it in data.target.lineage"); the lineage follows the renames, so a
     built target over a column named `target` keeps it excluded as `source_target`;
  4. keeps its own `target_<use_case>` as `target`.

  After the join a data scientist names a renamed column `source_<name>` everywhere: eligibility
  SQL, candidate patterns, strata, decisions. The saved table itself is the sources joined: a
  `target`, `split` or `eligible` column keeps its name there. One pure function,
  `panel.read_side_columns`, owns this plan, for `prepare_panel`, `saved_candidates` and
  `save_model_input` alike: the save runs it for every config before writing, so a clash (a
  `target` beside a `source_target`) fails at save, not at every later read. A name the
  framework uses is refused where a data scientist would mean the source's column: in
  `data.target.column` or `lineage` a key name (`unit_id`, `period`), in `features.excluded` or
  `kept_despite_flags` a key or helper name; each message names the `source_<name>` to write.
- A reader is refused, naming `save_model_input`, on: no table or
  sidecar; another schema or hash version; other feature sources, keys or period; a use case the
  table lacks; another target-spec hash for its use case; periods that don't cover
  `observation_window.first … validation_period`; a `validation_period + target_window` that
  reaches beyond the saved target source's last period (`target_last`), since a later
  validation period would leave the validation frame or a window period unlabelled. A changed
  eligibility, observation window, split or candidate list is **not** refused: that is the
  point, the table outlives those choices, and a new config with one of them changed reruns EDA
  onwards on the same table. Two configs on one table get independent client splits, each from
  its own `data.split`; nothing downstream assumes they match. Without the field the same
  frames are built in memory, with the same logs. The audit log's feature decisions check a
  name against its candidate list once it is saved ([config](config.md)).
- No separate targets table: the model input carries the targets. Labels for scored periods
  (M4) build their own.
- Inference reads the **sources**, never the model input, and applies the model's own
  eligibility, both lists, to the inference period (§4.9): it scores the eligible units.

## Phase 2 requirements
1. Eligibility (two ordered lists of config steps, `analysis` then `modelling`, each step a
   `define` or a `filter` in Spark SQL, D-129) is applied identically to every period of
   train/test, validation and inference (§4.9), on read from the model input as in memory. An
   analysis filter drops its rows and logs rows in → out per period with its reason; a modelling
   filter keeps its rows, adds a 0/1 column named after the step (1 = the row passes) and logs
   how many it tagged 1 per period; `eligible` is 1 where every modelling filter passes, and the
   contract checks, Feature Checks, Training, Evaluation and Inference use those rows only. A
   `define` may sit in either list, adds a named boolean column for the steps after it and is
   dropped before the candidates are resolved; a null condition counts as false. Step names are
   unique across both lists; a step named like a source column, or like one the dataset adds
   (`target`, `split`, `eligible`), fails loud. A condition may reference the sources' columns
   (a renamed one as `source_<name>`) and earlier define names only: the keys, `target`,
   `split`, `eligible` and another filter's tag are refused, and so are a star in a call, a
   subquery, a window function and a non-deterministic function (`rand`, `current_date`, …,
   which would change the population between two reads of the model input), since eligibility
   SQL is a leakage surface outside the screens. The use case's own upstream target column is
   gone by then: it is the label, dropped on the read side. The log counts, per period, the
   rows whose condition was null.
2. Keep every eligible unit-period row in the window. Report both **positive rows** and
   **positive events**, because one conversion is positive in up to `w` consecutive periods.
   Every rule that uses a count of positives as evidence (minimum support per stratum, standard
   errors, the AUC floor, per-period statistics) counts events, and bootstraps and CV folds
   resample clients (D-082). The model itself keeps every row: correlated rows cost variance,
   not bias (below).
3. Split train/test by client (§4.11): a client goes to `test` when its draw is below
   `test_share`, the draw being a number in [0, 1) hashed from `unit_id` with the salt `'split'`
   and `data.split.seed` (`pmod(xxhash64(…), 10⁶) / 10⁶`, Interface); `test_share` is 0.3 at
   both levels (D-091), and the assignment is stable across periods, reruns and machines (across
   machines unverified; Spark's own XXH64 is expected to match); `unit_id` is a string by the
   time it is hashed, so the draw survives an upstream change of the id's type (T22). The
   sampling draws carry the salt `'sample'` instead, so equal seeds never make the sample a
   slice of the split (T20). Any
   CV inside train is grouped by client, as the calibration step's out-of-fold predictions are
   (D-094), and FLAML's trial selection gets the client groups, so no fold mixes a client's rows
   ([training](training.md),
   D-106). EDA uses every client of the window after the analysis filters and Feature Checks
   every eligible client, labels included; the split applies from Training on, where fitting,
   automated selection, calibration and every choice use train-split clients only (D-030).
4. Validation is the OOT period, scored by models trained on train only. It never informs
   selection or tuning (§4.4).
5. **The collect printout** (D-133). Prune columns and rows, and sample, in Spark before
   collecting. Before a frame leaves Spark the dataset counts its rows exactly, measures bytes per
   row on a 10,000-row sample (`memory_usage(deep=True)`), doubles the product for the
   conversion peak, and prints rows, columns, the estimate and `collect_budget_gb` from the
   environment file, in a notebook and from a function call alike. Above the budget the printout
   becomes a **callout**: declare sampling (`negative_downsampling` for rare binary targets,
   `client_sample` for common targets and regression) or raise the budget and the Spark settings
   (`spark.driver.maxResultSize`, which caps the Arrow collect, and the driver memory). The collect
   proceeds; there is no fail-loud on the budget, since inside the bank one simply raises the
   Spark settings. The estimate and the measured size both go into `meta`, so every run checks the
   estimate. The adapter does not derive `maxResultSize` from the budget.
6. Sampling happens only when the config declares it (`training.sampling`): a person's choice,
   made for a rare target or for the collect budget alike; the framework never samples on its own
   (D-117). It is train-only, recorded with the true (unsampled train) and the sampled rate, and
   happens after the client split. The options, with when-to-use guidance (guidance, not
   automatic triggers):
   - **`negative_downsampling`.** Suits rare binary targets. Keeps every positive row and the
     negatives whose draw (on `unit_id, period`, salt `'sample'`) is below `keep_fraction`, one
     keep fraction for the whole window, without stratifying by period: periods are large,
     similar slices, and one fraction keeps one prior-shift offset valid for every period
     (D-117). The offset corrects the class balance.
   - **`client_sample`.** Suits common targets and regression. Keeps all rows of the clients
     whose draw (on `unit_id`, salt `'sample'`) is below `share`. The offset comes out ≈ 0.
   - **no sampling,** whenever the config declares none.

   Outcome-stratified client sampling with weights, downsampling low-value rows and smarter
   downsampling in general come later (D-117).

   Whatever the option, the prior-shift offset uses the effective training rate (D-049): in
   Phase 2, with no sample weights, the sampled rate; once weights arrive, the weighted rate, since
   the unweighted rate would correct twice.
7. **No sample weights in Phase 2** (D-117). They arrive with outcome-stratified sampling, together
   with the per-task spec's list of statistics that must take them.
8. **Denominators** (D-098): the "true population" is the eligible rows regardless of label (the
   drift reference and the contract band use it); the prior-shift true rate comes from the
   unsampled train split, never train plus test; the null-label share (clients who leave inside
   the target window, panel-edge rows) is reported per period and per scoring batch;
   probabilities are conditional on staying through the target window.
9. **Contract checks** on the eligible population before any sampling (§4.8), run on every read
   of the model input as on an in-memory build: three shared checks and the task's own from the
   per-task spec (D-050); a failure raises with the numbers. Shared: every window period and the
   validation period has eligible rows, a unique `(unit_id, period)`, and the **null callout**,
   never a stop: the share of the target source's rows in the window with a complete target
   window, **before eligibility**, that held a null in the target column (the log entry names
   that `population`), computed by Target Factory and stored per use case in the model input's
   sidecar (no `null_in_window` column reaches the panel) and, above 0, a callout starting "x%
   of the target source's rows in the window with a complete target window (before
   eligibility) had a null in …": a null never counts as an event, so the nulls may hide
   negatives, which the modelling frames drop; a source that
   codes a value as null (0 for a non-holder) fills it upstream, the framework does not. Binary:
   both classes present, and the window's pooled positive rate at or below `data.rate_band.max`
   (0.5 in the example; no floor), reported per period. Regression: a finite, non-constant
   target.
10. No refit frames in the sandpit in Phase 2 (D-052): the production retrain builds its frames on
    the same data definition: same window, same clients; only the inference period moves (D-088).
    Frames on moved or extended data (later periods, all clients, a longer window) come later
    (D-052).

## Downstream effects of the window

| Area | Effect |
|---|---|
| EDA | Population and reference-group views on every client of the window after the analysis filters; the univariate ranking and the label statistics that feed a choice on its eligible rows (D-030); base rate per period (population level, for seasonality) over every period up to the window's end, because later periods' target windows overlap the validation period's (D-030) |
| Feature Checks | Runs on the window's eligible rows, every eligible client, labels included (D-030); stability across the window's periods (per-period AUC range, PSI); the periods it compared are recorded (D-088); label-free PSI against the gap periods between window and `v` and the latest period, never `v` |
| Training | Train/test client split, after Feature Checks (D-030); calibration folds grouped by client; FLAML's trial selection grouped by client (D-106); the collect printout and declared sampling |
| Calibration | Prior shift from the effective training rate (the sampled rate in Phase 2, D-049) to the unsampled train split's true rate (D-098); per-period base rates reported (seasonality); optional general calibration step out-of-fold inside train (D-049) |
| Evaluation | Test (unseen clients, same periods) vs validation (OOT): for a run nothing was picked on, the gap separates overfitting from decay over time, apart from the cost of EDA and Feature Checks on every client (D-030); a sweep's winner states that its gap mixes overfitting with selection (D-083). Optional: validation on test clients only (unseen clients and an unseen period) |
| Inference | Unchanged: one period at a time, from the sources, never the model input (D-131) |
| Monitoring | Drift baselines = the drift reference saved at training, computed on the true population, not the sample (D-054) |
| Synthetic data | 24 months, so window + validation + inference + label maturation all fit |

## Design analysis (questions raised in review)

### Why train in pandas, and when that stops being enough
- Every engine in scope (FLAML, LightGBM, XGBoost, CatBoost, scikit-learn) trains in memory on one
  machine, and so do the explainers and the calibration. Spark's job is to prune and sample before
  anything is collected.
- For rare binary targets this costs little. Almost all the information sits in the positives, and
  once every positive is kept, negatives beyond a few tens per positive add little (the
  case-control sampling argument). Example: 24M client-months at 0.1% positives is ~24k positive
  rows; 20 negatives per positive gives ~500k rows, which fits comfortably.
- It stops being enough when:
  - (a) the target is common or continuous, so there is no minority class to keep whole;
  - (b) the grain gets finer: weekly data has ~4.3× the rows of monthly, and consecutive weeks are
    even more correlated, so the real information grows much more slowly than the row count;
  - (c) the feature set is very wide (~400 columns).

  The collect printout measures the frame (D-133); the engine builds its own structures on top,
  roughly 2–4× the frame at peak.
- Responses, in this order:
  1. Prune features first (Feature Checks).
  2. Sample clients rather than rows.
  3. Keep the training grain as coarse as the use case allows (`time.period`, monthly where it
     can be) and aggregate finer or transactional data to it upstream. Modelling raw
     transactions is a different problem (sequence models) and outside the panel family.
  4. Only then, a Spark-native engine (e.g. XGBoost's PySpark estimator) as another entry behind
     the model interface. Unverified on the bank cluster and not built in Phase 2.
- Scoring has no such ceiling: inference runs in Spark.
- **To tell whether sampling costs accuracy,** run a learning-curve check: train on 25 / 50 / 100%
  of the sampled rows and score the same test split. If the curve is still rising, raise the
  budget or change the sampling. The choice is made on test, never on the validation period
  (D-083).

### Is downsampling safe when a client's rows are correlated?
- Random negative sampling (independent of the features, within each class) is unbiased. It keeps
  each class's feature distribution and only shifts the class balance, which the prior-shift offset
  undoes. Correlation between a client's rows doesn't bias it. The rows simply carry less independent
  information than their count suggests, so dropping some costs less than it looks.
- **Converting clients** matter. A client who converts in period `m` is positive at observation
  periods `m−w … m−1` and negative before, with nearly identical features at `m−w−1` and `m−w`. Those
  pre-conversion negatives are the most informative negatives, and random row sampling keeps only a
  fraction of them.
  - That is lost variance, not bias.
  - It is mostly about timing, which is inherently hard to learn. Regularisation stops the model
    from memorising individual clients, and the test split on unseen clients shows when it does
    (FLAML's trial selection is grouped by client too, D-106).
- **What would bias the model:** sampling based on a client's outcomes across periods (e.g. keep every
  converting client's full history plus a sample of the rest) *without weights*. With
  inverse-probability weights it is unbiased again; that option comes later (D-117).
- **Two practical traps:**
  - Sample *after* assigning clients to train/test, so no client straddles both.
  - Use one keep fraction for the whole window, so the window's period mix isn't distorted and
    one prior-shift offset holds for every period (D-117).
- Phase 2 (D-117): sampling only when the config declares it; `negative_downsampling` suits rare
  binary targets, `client_sample` common targets and regression. A check against the synthetic
  oracle (reliability curves) is planned to show whether the downsampling offset brings scores
  back to the true level ([training](training.md) Open questions); comparing every option against
  the oracle comes later.
- The LDS dislikes sampling because it distorts distributions, so Phase 2 samples only when the
  config declares it (D-117).

### Does a multi-period window actually beat a single period?
This is answered by a **window ablation**, a nice to have in M4, not a Phase 2 requirement
(OD-17):
- Train the same config with windows of 1, 3, 6… periods, all ending in the same period. Keep
  everything else fixed (eligibility, candidates, budget, seeds, sampling rule), and score all of
  them on the identical validation period.
- Compare them with a **paired bootstrap** over validation clients (mechanics owned by
  [evaluation](evaluation.md)).
- **Separate volume from variety.** Add a k-period run subsampled to the single period's row
  count. If it still wins, the gain comes from variety across periods (robustness to
  period-specific conditions), not just from more rows.
- **Show period-to-period luck.** Train single-period models on each period of the window and
  score them on the same validation period.
- No second validation period: it would push the training window further into the past (D-083).
  The choice weighs train and test metrics, e.g. the test metric penalised by the train–test gap;
  the validation period is reported for every variant and never chooses (D-083).
- The mechanism (vary one config field, compare on a fixed validation set) is also the bounded-axis
  loop the original roadmap planned for the LLM branch. It is built once in Phase 2 as an
  experiment-sweep function (name to be decided; see [run modes](run_modes.md)); the LLM drives it
  later. This section owns the ablation design. A sweep that *picks* a window for a use case picks
  the same way: on train and test, never on validation (D-083).

## Design constraints
- Spark does every row and column reduction. `toPandas` runs only on the pruned, sampled frame
  (`CLAUDE.md` §5; a full-width `toPandas` was the crunch's main OOM risk, see
  `docs/context/environment.md`), and never without the collect printout (D-133).
- One function builds each frame from the config; stages never assemble their own.
- The framework never samples on its own (D-117).

## Interface
Built in Stage 1's major step 3 (2026-10-27; for the SDS's review together with Target Factory).
Package: `core_modelling/dataset/` (`panel.py`, `eligibility.py`, `split.py`, `contract.py`,
`frames.py`, `model_input.py`); the keys and the helper columns are `sources.py`'s; the
contract checks' task-specific functions sit in the per-task spec (`tasks.py`, D-050).
- `build_frames(cfg, entity, env, spark, stage: str) -> Frames` (public, D-024): `stage` is
  `eda` (the window frame), `feature_checks` (its eligible rows) or `training` / `evaluation`
  (train, test, validation); anything else fails naming the four. With `data.model_input` set
  the panel is the saved model input read through `read_model_input` (checked, below), else it
  is built in memory (`panel.build_panel`); either way the derived part is `prepare_panel`:
  `apply_eligibility` → the candidates → `check_contract` → `assign_split`; `target` stays
  wherever Target Factory could build it. The window frame is every row of the window after the
  analysis filters; Feature Checks gets its rows with `eligible = 1`. The modelling frames are
  the eligible rows with a known target, the null-target share per period logged and printed;
  train (sampled when declared) and test are the window's rows by `split`, validation the
  validation period's. Each frame leaves Spark through `collect_frame`.
- `@dataclass Frames(window, train, test, validation, log, meta)`: pandas frames, `None` when
  the stage didn't ask for them, all with the same columns: `unit_id` (a string), `period` (a
  date, the period's last day), the candidates, the modelling tags, `eligible`, `target`,
  `split`; a future frame goes last, since the fields are positional. `log` is the list of
  entries in order, each with a fixed `step`: `join` (one per source: the spine's rows per
  period, or the rows a source matched per period and the share; plus, per target column, the
  null share with its `population`: the target source's rows in the window with a complete
  target window, before eligibility), `rename` (one per source column read as `source_<name>`
  on the read side), `eligibility` (one per filter: its `name`,
  `kind` (`analysis` / `modelling`), the reason, rows per period, the rows whose condition was
  null and the rows out or tagged 1), `contract` (one per check), then `null_target`,
  `sampling` and `collect` for the modelling frames (`frame`: `window` for EDA,
  `eligible_window` for Feature Checks, `train`, `test`, `validation`). Per-period values are
  dicts keyed by the period's label (`2025-06`, `2025-W23` or `2025-06-15`, by `time.period`),
  built by `periods.label_by_period(rows, field, spec)` and `periods.period_labels(first, last,
  spec)`, the two functions every log entry uses.
  `meta`: the data-definition and target-spec hashes with `hash_version`, the lineage, the
  candidates, the tags, the sampling record and the collect entries. The per-period label
  counts are Target Factory's summary, not repeated here.
- `save_model_input(cfgs: UseCaseConfig | list[UseCaseConfig], entity, env, spark) -> str`
  (public, `model_input.py`): one config is the one-element list, an empty list is refused;
  the panel of `load_panel` (the sources joined plus the target columns) written to the path
  the environment file maps for `data.model_input` (a parquet source with a local path until
  the M2.4 transport),
  partitioned by `period`, the folder rewritten whole so a rerun never leaves periods of an
  earlier definition behind, with `_model_input.json` in the same folder (`schema_version`,
  `framework_version`, `built_at`, `entity`, `model_input`, `use_cases` in order, the meta of
  `load_panel`, `columns`, `log`: the join log). The file's name starts with `_` so Spark's
  listing skips it, and never with `_metadata`, which Spark reads as a parquet summary (T21).
  Prints the path and returns it. `MODEL_INPUT_SCHEMA_VERSION` (3 since 2026-10-28: one table
  for several use cases, the target columns `target_<use_case>`, the derived columns moved to
  the read side, the sidecar keyed by the shared definition and the target-spec hashes; 2 was
  the log entries' `kind`, labels in every period with a complete window, the draw in [0, 1))
  is bumped when the sidecar's keys, the log entries' keys, a column's meaning or the split's
  draw change, so an older table is refused by name; until release 1.0 the migration of a model
  input is its rebuild from the sources, which `read_model_input_metadata` asks for, and
  `record_decision` refuses feature decisions until it is rebuilt (the artifact inventory in
  [architecture](../architecture.md#artifact-inventory)).
- `sources.py`: `KEYS = ["unit_id", "period"]` and `HELPER_COLUMNS = ["target", "split",
  "eligible"]`; `rename_reserved(columns, reserved, where)` gives each of `columns` in
  `reserved` the name `source_<name>`, failing loud naming both when `source_<name>` is already
  among `columns` (`where` places the clash in the message); `read_keyed_source` names the keys
  and reads a non-key column named `unit_id` or `period` through it, printed and in the log's
  `renamed`, and leaves `target`, `split` and `eligible` as they are ([target
  factory](target_factory.md)).
- `panel.py`: `target_column(use_case) -> str` (`target_<use_case>`).
  `read_side_columns(columns, targets, use_case, features) -> tuple[dict[str, str],
  dict[str, str]]`, pure, the read-side plan ([model input](#model-input-d-131)): the columns
  dropped with their reason (`DROP_REASONS`: every use case's target column but the own one;
  every upstream label, the own one included, when its target source is among `features`) and
  the renames, in order (a remaining `target`, `split` or `eligible` → `source_<name>` through
  `rename_reserved`; then `target_<use_case>` → `target`).
  `load_panel(cfgs: list[UseCaseConfig], entity, env, spark) -> tuple[DataFrame, list[dict],
  dict]`, the build side: the use cases must be distinct and every config declare the same
  `entities.<entity>.sources.features`, `data.keys`, `data.model_input` and `time.period`
  (else a `ValueError` naming the two use cases and the field); the spine from the first
  config, checked to cover the earliest `observation_window.first` to the latest
  `validation_period` (`check_periods_covered`, `sources.py`); every source through
  `read_keyed_source`, each joined one held as a frozen `JoinedSource(log, marker, role,
  use_case)`; a non-key column in two feature sources fails loud; a feature source that
  matches no spine row is refused, naming the source and both raw id types (the source log's
  `id_type`); per config `load_targets`, its column `target_<use_case>` (a source column of
  that name fails loud) left-joined as the use case's target; rows from the earliest window's
  first period to the spine's last; a window period with no known value in a use case's target
  column fails loud naming it; returns the panel (the keys, every feature column, the target
  columns), the join log (one rollup per period, with the null share per target and its
  `population`) and the meta: `hash_version`, the feature sources, the keys, the period, the
  periods covered (first and last, as labels) and per use case its column, target-spec hash,
  lineage, source, `upstream`, observation window, target window, validation period,
  `target_last` and `null_in_window_share`.
  `prepare_panel(panel, cfg, entity, targets: dict) -> tuple[DataFrame, list[dict], dict]`,
  the read side: applies `read_side_columns` (a `cfg.use_case` missing from `targets` fails
  naming the saved use cases), the drops and the `source_<name>` renames printed and logged
  as one `drop` and one `rename` entry (each only when non-empty),
  then `apply_eligibility`, `resolve_candidates` with the
  lineage from `targets` under its read names, the named-feature check (a name in
  `features.excluded` / `kept_despite_flags` that is not a column, or is a key or helper name,
  fails loud), `modelling_tags`, `check_contract`
  with the use case's null share, `assign_split`, and the select `[*KEYS, *candidates, *tags,
  "eligible", "target", "split"]`; the meta's keys are `PANEL_META_KEYS`
  (`data_definition_hash`, `target_spec_hash`, `hash_version`, `lineage` under the read
  names, `candidates`, `tags`). `build_panel(cfg, entity, env, spark) -> tuple[DataFrame, list[dict], dict]` =
  `load_panel([cfg], …)` then `prepare_panel`: the in-memory one-config path, its return shape
  unchanged.
- `eligibility.py`, who is in: `apply_eligibility(panel, eligibility: Eligibility) ->
  tuple[DataFrame, list[dict]]` (the `analysis` steps then the `modelling` steps, every period
  alike; a condition (`_condition`) is resolved against the sources' columns and earlier
  defines only, may hold no star in a call, subquery or window function (`UNSAFE_SQL`) and no
  non-deterministic function (`NON_DETERMINISTIC`: `rand`, `current_date`, …), must be
  boolean, and a step named like a column or like `target`, `split` or `eligible` fails; a
  null condition counts as false and is counted per period (`_rows_per_period`); the defines
  are dropped at the end); `modelling_tags(cfg)` (one tag per modelling filter, named after
  the step); `step_names(cfg)` (both lists' names); `resolve_candidates(columns, cfg,
  lineage) -> list[str]` (`fnmatch` include then exclude, minus the keys, `target`, `split`,
  `eligible`, the lineage and both lists' step names; none left fails loud).
- `split.py`: `_hash_uniform(columns, salt, seed) -> Column`, a number in [0, 1) that is a fixed
  function of the columns, the salt and the seed, `pmod(xxhash64(salt, columns…, seed), 10⁶) /
  10⁶`, the same on every machine, rerun and partition (the pinned draw: unit id `'12345'`,
  salt `split`, seed 42 → 0.322993); `assign_split(panel, cfg) -> DataFrame` (`test` for the
  clients whose draw on `unit_id` with the salt `'split'` is below `test_share`, else `train`,
  every period of a client alike); `sample_train(train, cfg) -> tuple[DataFrame, dict]`
  (`negative_downsampling`: every positive row and the negatives whose draw on `unit_id,
  period` with the salt `'sample'` is below `keep_fraction`; `client_sample`:
  the clients whose draw on `unit_id` with the salt `'sample'` is below `share`; the salts keep
  the two draws apart (T20); an empty train split after sampling fails loud; the record:
  the method, its parameter, the seed, the rows and the target's mean before and after, the true
  and the sampled rate of D-049; without sampling the identity, recorded as `method: None`).
- `contract.py`: `check_contract(panel, cfg, null_in_window_share: float | None) ->
  list[dict]` on the eligible rows: every window period and the validation period has some
  (shared), then on the window's: unique keys (shared), the task's checks (binary: both classes
  and the pooled positive rate ≤ `data.rate_band.max`, `positive_rows` and the rate per period
  in the entry; regression: a finite, non-constant target), then the null callout (shared) from
  the share it is given, no column scan: above 0, the callout text (a null never counts as an
  event; fill nulls that mean a value upstream); `None` with a note for an upstream target. A
  failing check raises with its numbers; each entry prints one line.
- `frames.py`: `estimate_collect(frame, name) -> dict` (the exact rows, bytes per row from a
  10,000-row sample's `memory_usage(deep=True)`, the estimate at twice the product; an empty
  frame fails loud naming it); `collect_frame(frame, name, env) -> tuple[pd.DataFrame, dict]`
  (the printout, the callout above the budget, the collect, the measured size).
- `model_input.py`: `read_model_input_metadata(cfg, entity, env) -> dict` (refuses, in order
  and each naming `save_model_input`: no table or sidecar; another `schema_version`, with the
  version note; another `hash_version`; other feature sources, keys or period; a use case the
  sidecar's `targets` lacks; another `target_spec_hash` for it; `periods` not covering
  `observation_window.first … validation_period`; a `validation_period + target_window` beyond
  the use case's saved `target_last`; never a changed eligibility, window, split or candidate
  list); `read_model_input(cfg, entity, env, spark) -> tuple[DataFrame, list[dict],
  dict]` (the saved table's `period` cast to a date on read, so a session without Spark's
  partition type inference gives the same frames; the saved columns selected; then
  `prepare_panel` with the sidecar's `targets`: returns the prepared panel, the join log plus
  the preparation's log, and the preparation's meta); `saved_candidates(cfg, entity, env) ->
  list[str] | None` for the audit log's feature decisions (`resolve_candidates` over the
  sidecar's columns after `read_side_columns`, so the names match the frames', with the
  sidecar's lineage, no Spark; `None` when
  the config names no model input or none is saved yet; a mapping the environment lacks fails
  loud).
- Tested on the unit preset end to end (the window frame with the holders tagged, the Feature
  Checks frame as its eligible rows, the modelling frames split by client, the model input round
  trip equal to the frames built in memory, the stale-input refusals, the callout above a tiny
  budget, regression with client sampling) and on
  hand-made panels for the join, every eligibility rule, the split and sampling statistics, and
  each contract refusal.

## Open questions
- Performance on real sizes: the in-memory panel is a lazy plan over the sources, so every
  action (the join log, each filter's counts, each contract check, each collect) recomputes the
  joins and the target's window function; a read of the model input recomputes the derived
  part (eligibility, contract, split) on every read. On the unit preset a stage's frames take
  about ten seconds; whether to persist the panel inside the bank is decided when a real source
  is read (M2.4).
- Another use case's label is dropped on read only when that use case shares the model input;
  built alone, the same column is an ordinary candidate, and its leak is left to Feature Checks'
  leakage screen (§4.6: screens flag). So under one data-definition hash the candidate list can
  depend on which use cases were saved together. Whether a use case should declare other
  labels it knows about (e.g. a `data.exclude_labels` list) is decided with Feature Checks
  (M2.2; found in the 10-29 ML audit).
- `period` reaches pandas as `datetime.date` objects (Spark's `DateType` through Arrow); whether
  EDA wants `datetime64` is settled when EDA is built (M2.2).
- The window ablation details (OD-17; a nice to have in M4). Sampling is settled for Phase 2
  (D-117); smarter downsampling, including low-value rows with weights that calibrate back, comes
  later.
- Whether FLAML's group split runs as expected (spike 1, unverified on 2.7; no sample weights in
  Phase 2, D-117); the fallback is in [training](training.md) (D-106).
