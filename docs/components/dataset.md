# Dataset: observation window, frames, splits, sampling
**Status:** built thin (M2.1, 2026-10-27; for the SDS's review with Target Factory) · **Legacy:** `src/io.py` (load + prune in Spark), `src/dataset.py` (labelled frames, downsampling)
**Related:** [config](config.md) (the `data` and `time` sections) · [environment](environment.md) (sources, the collect budget) ·
[target factory](target_factory.md) · [training](training.md) · [evaluation](evaluation.md) ·
[feature checks](feature_checks.md) · [EDA](eda.md) · [test harness](test_harness.md) · D-030, D-049, D-052, D-054,
D-082, D-083, D-088, D-091, D-098, D-106, D-117, D-129, D-130, D-131, D-133 · OD-17

## Purpose
Builds the frames every stage works on, from one data definition: the governing spine and the
other sources joined, eligibility applied, the target attached, the client split assigned, then
collected from Spark with a printout of what is about to leave it. Eligibility has two kinds of
filter (D-129): `before: eda` drops its rows; `before: model` keeps them, tagged by the step's
name, so EDA can compare the excluded group (e.g. current holders) with the modelling
population, and drops them before modelling. Two frame shapes come from the same definition
(D-030): the **window frame** (every unit-month in the observation window after the pre-EDA
filters, the pre-model tags as columns, every client, labels included) for EDA and Feature
Checks, and **train / test / validation** (eligible rows only) from Training on. The frames can be built in memory on every call or read from the
saved **model input** that Target Factory's notebook writes (D-131). Training on a window of
months instead of a single month is a Phase 2 big-ticket item (D-030). This doc owns its
downstream effects.

## Time model

The periods, earliest to latest:

1. **Backward windows**: the history upstream rollup features look back over, reaching before
   `t1`. The framework doesn't check them: features come from upstream (D-129).
2. **Observation window `t1 … tk`**: train + test, every eligible unit-month in it, split by
   client.
3. **Target windows**: the forward months the window's targets look into; the last one ends at
   `tk + w`.
4. **Validation month `v ≥ tk + w`** (OOT): its target window (`v+1 … v+w`) starts after the last
   training target window ends (`tk + w`).
5. **Inference**: later months, after `v`.

- Features are as-of each observation month; targets look forward `(1, w)` (§4.1).
- The observation window (`time.train_months`), `w` (`time.target_window_months`, one number
  shared by the target builder and the time checks) and the validation month are set in the
  config (D-129). The validation month sits outside the data-definition hash (EDA never reads it;
  Feature Checks reads it only to leave it out of its comparisons and records the months it
  compared). Moving it changes the config hash before the config freezes and the resolved-input
  hash after (an audit-log entry), never the data-definition hash. The inference month is a run
  argument. Changing the validation month after the config freezes is an audit-log entry, refused
  when any Feature Checks run compared that month (D-088). A Phase 2 production retrain keeps the
  window and the clients; only the inference month moves, since inference always runs on the
  latest month (D-088, D-052).
- Checked at load: `first ≤ last`, `v ≥ tk + w`, and the window and `v + w` inside the sources'
  months (D-129; [config](config.md) req. 8).
- Default window: 6 months with `w = 3`, in the examples and as level defaults (D-091).
- Validation is a single month for panel tasks. Series tasks will need rolling validation (later).
- Example on the 24-month synthetic panel with 6-month upstream rollups, `w = 3` (an illustration:
  the window is chosen per use case, and the synthetic data is built for none in particular, D-064):
  - window = months 6–11;
  - validation month = 14, labels mature by 17;
  - months 18–21 are free to test scoring plus monitoring with matured labels.

## Frames (D-030, D-131)
`Frames(window, train, test, validation, log, meta)`, built by `build_frames(cfg, entity, env,
spark, stage)`, which collects only what the stage asks for:
- `window`: every unit-month in the observation window after the pre-EDA filters, with
  `target`, the pre-model tag columns and `eligible` (every pre-model filter passed), for EDA and
  Feature Checks (`stage` `eda` / `feature_checks`). Every client, labels included (D-030); EDA's
  population views use every row and the tags as strata, Feature Checks the eligible rows.
- `train` and `test`: the window split by client; `validation`: every eligible unit at `v`, with
  the `split` column so Evaluation can also show test clients only (`stage` `training` /
  `evaluation`). Rows with a null target are dropped from these modelling frames, with the share
  logged per month. `train` is sampled when the config declares sampling (req. 6).
- `log`: the join, eligibility, null-target, contract and sampling logs, in order.
- `meta`: the hashes, the lineage, the candidates, the tags, the sampling record and the
  collect estimate and measured size per frame (D-133); the per-month rows, positive rows and
  positive events (D-082) are Target Factory's summary.

Feature Checks also reads the gap months and the latest month, label-free, from the model input
(or the in-memory panel), which runs from the window's first month to the spine's last.

## Sources and joins (D-129)
- `entities.<e>.sources.features` is an ordered list; the first source is the **governing spine**
  and the others are left-joined to it on the keys. `sources.targets` is one source, left-joined,
  contributing only the target; when it is omitted the target is a column of a feature source.
- The keys are renamed to `unit_id` and `month` at load from `data.keys`; in Phase 2 one naming
  serves every source of a use case.
- On reading, each source's month column moves to its month's last day (`last_day`), the
  framework's one month convention, so a source tagged on the first day joins one tagged on the
  last. A month column that is not a date or timestamp fails loud naming its type (a format
  setting waits for a real source that needs one). The join log says how each source tagged its
  months (D-129). Every source is read this way through `read_keyed_source` (`sources.py`, built
  with Target Factory), which also refuses a null unit id and a repeated key.
- Duplicate keys in any source fail loud, naming the source and a few keys; the check runs after
  the month move, so a source carrying both tags for one month fails it. A non-key column
  present in two feature sources fails loud (renamed upstream, or by a per-source alias later).
- The join log prints, per source, its distinct units per month and the share of spine rows it
  matches.
- Months run from `train_months.first` to the spine's last month.

## Model input (D-131)
One saved table per instance, named in the config by logical name (`data.model_input`) and mapped
to a path or table by the environment file. It holds the governing spine's rows from the window's
first month to the spine's last, the candidate columns of every feature source, `target` (known
in the observation window and at the validation month only: the gap months and the later ones,
which Feature Checks reads label-free, carry none, §4.4) and `split`, the pre-EDA filters applied, one 0/1 column per pre-model filter (named after the step)
plus `eligible`, and the `define` columns dropped. In the same folder, `_model_input.json`
holds the data-definition and target-spec hashes with their `hash_version`, the lineage, the
resolved candidates, the tags, `data.split`, the join, eligibility and contract logs, the
framework version and when it was built. Its path is local until the M2.4 transport.
- `save_model_input` writes it, from the Target Factory notebook or `run --stages
  target_factory`. Saving is the moment the config freezes (D-125).
- Every later stage reads it when the config names it and fails loud when its data-definition
  hash, its `data.split` or its schema or hash version differs from the config's ("the model
  input was built from another data definition; rebuild it with `save_model_input`"). Without
  the field the same frames are built in memory, with the same logs. The audit log's feature
  decisions check a name against its candidate list once it is saved ([config](config.md)).
- No separate targets table: the model input carries the target. Labels for scored months (M4)
  build their own.
- Inference reads the **sources**, never the model input, and applies the model's own eligibility,
  both kinds, to the inference month (§4.9): it scores the eligible units.

## Phase 2 requirements
1. Eligibility (ordered config steps, each a `define` or a `filter` in Spark SQL, D-129) is
   applied identically to every month of train/test, validation and inference (§4.9). A
   `before: eda` filter drops its rows and logs rows in → out per month with its reason; a
   `before: model` filter keeps its rows, adds a 0/1 column named after the step (1 = the row
   passes) and logs how many it would drop per month; `eligible` is 1 where every pre-model
   filter passes, and the contract checks, Feature Checks, Training, Evaluation and Inference use
   those rows only. A `define` adds a named boolean column for later steps and is dropped before
   the candidates are resolved; a null condition counts as false. A step named like a source
   column, or like one the dataset adds (`target`, `split`, `eligible`, `null_in_window`),
   fails loud. A condition may reference the sources' columns and earlier define names only:
   the keys, `target`, `split`, `eligible` and another filter's tag are refused, and so are a
   star in a call, a subquery and a window function, since eligibility SQL is a leakage surface
   outside the screens. The log counts, per month, the rows whose condition was null.
2. Keep every eligible unit-month row in the window. Report both **positive rows** and **positive
   events**, because one conversion is positive in up to `w` consecutive months. Every rule that
   uses a count of positives as evidence (minimum support per stratum, standard errors, the AUC
   floor, per-month statistics) counts events, and bootstraps and CV folds resample clients
   (D-082). The model itself keeps every row: correlated rows cost variance, not bias (below).
3. Split train/test by client (§4.11): `pmod(xxhash64('split', unit_id, seed), 1000) < 1000 ×
   test_share` puts a client in test, with `test_share` 0.3 at both levels (D-091) and the seed
   from `data.split.seed`, so the assignment is stable across months, reruns and machines (across
   machines unverified; Spark's own XXH64 is expected to match). The sampling hashes carry the
   salt `'sample'` instead, so equal seeds never make the sample a slice of the split (T20). Any
   CV inside train is grouped by client, as the calibration step's out-of-fold predictions are
   (D-094), and FLAML's trial selection gets the client groups, so no fold mixes a client's rows
   ([training](training.md),
   D-106). EDA and Feature Checks use every client in the window, labels included; the split
   applies from Training on, where fitting, automated selection, calibration and every choice use
   train-split clients only (D-030).
4. Validation is the OOT month, scored by models trained on train only. It never informs selection
   or tuning (§4.4).
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
     negatives with `pmod(xxhash64(unit_id, month, salt), 1_000_000) < keep_fraction × 1e6`, one
     keep fraction for the whole window, without stratifying by month: months are large, similar
     slices, and one fraction keeps one prior-shift offset valid for every month (D-117). The
     offset corrects the class balance.
   - **`client_sample`.** Suits common targets and regression. Keeps all rows of the clients with
     `pmod(xxhash64(unit_id, salt), 1000) < share × 1000`. The offset comes out ≈ 0.
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
   the target window, panel-edge rows) is reported per month and per scoring batch; probabilities
   are conditional on staying through the target window.
9. **Contract checks** on the eligible population before any sampling (§4.8): three shared
   checks and the task's own from the per-task spec (D-050); a failure raises with the numbers.
   Shared: every window month and the validation month has eligible rows, a unique
   `(unit_id, month)`, and the **null callout**, never a stop: the share of rows whose
   target window held a null in the target column and, above 0 without `data.target.null_as`, a
   callout that the nulls may hide negatives, which the modelling frames drop. Binary: both
   classes present, and the window's pooled positive rate at or below `data.rate_band.max` (0.5
   in the example; no floor), reported per month. Regression: a finite, non-constant target.
10. No refit frames in the sandpit in Phase 2 (D-052): the production retrain builds its frames on
    the same data definition: same window, same clients; only the inference month moves (D-088).
    Frames on moved or extended data (later months, all clients, a longer window) come later
    (D-052).

## Downstream effects of the window

| Area | Effect |
|---|---|
| EDA | Feature–target views on every client in the window (D-030); base rate per month (population level, for seasonality) over every month up to the window's end, because later months' target windows overlap the validation month's (D-030) |
| Feature Checks | Stability across the window's months on every client (per-month AUC range, PSI; D-030); the months it compared are recorded (D-088); label-free PSI against the gap months between window and `v` and the latest month, never `v` |
| Training | Train/test client split, after Feature Checks (D-030); calibration folds grouped by client; FLAML's trial selection grouped by client (D-106); the collect printout and declared sampling |
| Calibration | Prior shift from the effective training rate (the sampled rate in Phase 2, D-049) to the unsampled train split's true rate (D-098); per-month base rates reported (seasonality); optional general calibration step out-of-fold inside train (D-049) |
| Evaluation | Test (unseen clients, same months) vs validation (OOT): for a run nothing was picked on, the gap separates overfitting from decay over time, apart from the cost of EDA and Feature Checks on every client (D-030); a sweep's winner states that its gap mixes overfitting with selection (D-083). Optional: validation on test clients only (unseen clients and an unseen month) |
| Inference | Unchanged: one month at a time, from the sources, never the model input (D-131) |
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
  3. Keep the training grain monthly and aggregate weekly or transactional data to it upstream.
     Modelling raw transactions is a different problem (sequence models) and outside the panel
     family.
  4. Only then, a Spark-native engine (e.g. XGBoost's PySpark estimator) as another entry behind
     the model interface. Unverified on the bank cluster and not built in Phase 2.
- Scoring has no such ceiling: inference runs in Spark.
- **To tell whether sampling costs accuracy,** run a learning-curve check: train on 25 / 50 / 100%
  of the sampled rows and score the same test split. If the curve is still rising, raise the
  budget or change the sampling. The choice is made on test, never on the validation month (D-083).

### Is downsampling safe when a client's rows are correlated?
- Random negative sampling (independent of the features, within each class) is unbiased. It keeps
  each class's feature distribution and only shifts the class balance, which the prior-shift offset
  undoes. Correlation between a client's rows doesn't bias it. The rows simply carry less independent
  information than their count suggests, so dropping some costs less than it looks.
- **Converting clients** matter. A client who converts in month `m` is positive at observation months
  `m−w … m−1` and negative before, with nearly identical features at `m−w−1` and `m−w`. Those
  pre-conversion negatives are the most informative negatives, and random row sampling keeps only a
  fraction of them.
  - That is lost variance, not bias.
  - It is mostly about timing, which is inherently hard to learn. Regularisation stops the model
    from memorising individual clients, and the test split on unseen clients shows when it does
    (FLAML's trial selection is grouped by client too, D-106).
- **What would bias the model:** sampling based on a client's outcomes across months (e.g. keep every
  converting client's full history plus a sample of the rest) *without weights*. With
  inverse-probability weights it is unbiased again; that option comes later (D-117).
- **Two practical traps:**
  - Sample *after* assigning clients to train/test, so no client straddles both.
  - Use one keep fraction for the whole window, so the window's month mix isn't distorted and one
    prior-shift offset holds for every month (D-117).
- Phase 2 (D-117): sampling only when the config declares it; `negative_downsampling` suits rare
  binary targets, `client_sample` common targets and regression. A check against the synthetic
  oracle (reliability curves) is planned to show whether the downsampling offset brings scores
  back to the true level ([training](training.md) Open questions); comparing every option against
  the oracle comes later.
- The LDS dislikes sampling because it distorts distributions, so Phase 2 samples only when the
  config declares it (D-117).

### Does a multi-month window actually beat a single month?
This is answered by a **window ablation**, a nice to have in M4, not a Phase 2 requirement
(OD-17):
- Train the same config with windows of 1, 3, 6… months, all ending in the same month. Keep
  everything else fixed (eligibility, candidates, budget, seeds, sampling rule), and score all of
  them on the identical validation month.
- Compare them with a **paired bootstrap** over validation clients (mechanics owned by
  [evaluation](evaluation.md)).
- **Separate volume from variety.** Add a k-month run subsampled to the single month's row count. If
  it still wins, the gain comes from variety across months (robustness to month-specific
  conditions), not just from more rows.
- **Show month-to-month luck.** Train single-month models on each month of the window and score them
  on the same validation month.
- No second validation month: it would push the training window further into the past (D-083).
  The choice weighs train and test metrics, e.g. the test metric penalised by the train–test gap;
  the validation month is reported for every variant and never chooses (D-083).
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
Package: `core_modelling/dataset/` (`panel.py`, `split.py`, `contract.py`, `frames.py`,
`model_input.py`); the contract checks' task-specific functions sit in the per-task spec
(`tasks.py`, D-050).
- `build_frames(cfg, entity, env, spark, stage: str) -> Frames` (public, D-024): `stage` is
  `eda` / `feature_checks` (the window frame) or `training` / `evaluation` (train, test,
  validation); anything else fails naming the four. With `data.model_input` set the panel is the
  saved model input (checked, below), else it is built in memory (`panel.build_panel`):
  `load_panel` → `apply_eligibility` → the candidates → `check_contract` → `assign_split` → the
  targets outside the window and the validation month nulled. The
  window frame is every row of the window after the pre-EDA filters. The modelling frames are
  the eligible rows (`eligible = 1`) with a known target, the null-target share per month logged
  and printed; train (sampled when declared) and test are the window's rows by `split`,
  validation the validation month's. Each frame leaves Spark through `collect_frame`.
- `@dataclass Frames(window, train, test, validation, log, meta)`: pandas frames, `None` when
  the stage didn't ask for them, all with the same columns: `unit_id`, `month` (a date), the
  candidates, the pre-model tags, `eligible`, `target`, `split`; a future frame goes last, since
  the fields are positional. `log` is the list of entries in order, each with a fixed `step`:
  `join` (one per source: the spine's rows per month, or the rows a source matched per month and
  the share), `eligibility` (one per filter: its `name`, `before`, the reason, rows per month
  and the rows out or tagged 1), `contract` (one per check), then `null_target`, `sampling` and
  `collect` for the modelling frames. Per-month values are dicts keyed by `YYYY-MM` strings. `meta`: the data-definition and target-spec hashes with `hash_version`, the
  lineage, the candidates, the tags, the sampling record and the collect entries. The per-month
  label counts are Target Factory's summary, not repeated here.
- `save_model_input(cfg, entity, env, spark) -> str` (public, `model_input.py`): the same
  panel written to the path the environment file maps for `data.model_input` (a parquet source
  with a local path until the M2.4 transport), partitioned by `month`, the folder rewritten
  whole so a rerun never leaves months of an earlier definition behind, with
  `_model_input.json` in the same folder (`schema_version`, the framework version and time, the
  use case, the entity, the hashes, the lineage, the candidates, the tags, `data.split`, the
  columns and the join, eligibility and contract logs). The file's name starts with `_` so
  Spark's listing skips it, and never with `_metadata`, which Spark reads as a parquet summary
  (T21). Prints the path and returns it. `MODEL_INPUT_SCHEMA_VERSION` is bumped when the
  sidecar's keys or the `Split` fields change; until release 1.0 the migration of a model input
  is its rebuild from the sources (the same hashes), which `read_model_input_metadata` asks for,
  and `record_decision` refuses feature decisions until it is rebuilt (the artifact inventory in
  [architecture](../architecture.md#artifact-inventory)).
- `panel.py`: `build_panel(cfg, entity, env, spark) -> tuple[DataFrame, list[dict], dict]`
  (the steps above; the meta's keys are `PANEL_META_KEYS`); `load_panel(cfg, entity, env,
  spark) -> tuple[DataFrame, list[dict]]` (every
  source through `read_keyed_source`; the spine must have every month from the window's first to
  the validation month; a non-key column in two feature sources, a window month with no known
  target, or a name in `features.excluded` / `kept_despite_flags` that is not a column fail
  loud; months from the window's first to the spine's last; the join log from one rollup);
  `apply_eligibility(panel, steps) -> tuple[DataFrame, list[dict]]` (a condition is resolved
  against the sources' columns and earlier defines only, may hold no star in a call, subquery
  or window function (`UNSAFE_SQL`), must be boolean, and a step named like a column or like
  `target`, `split`, `eligible` or `null_in_window` fails; a null condition counts as false and
  is counted per month; the defines are dropped at the end);
  `pre_model_tags(cfg)`; `resolve_candidates(columns, cfg, lineage) -> list[str]` (`fnmatch`
  include then exclude, minus the keys, `target`, `null_in_window`, `split`, `eligible`, the
  lineage and the steps' names; none left fails loud).
- `split.py`: `assign_split(panel, cfg) -> DataFrame` (`pmod(xxhash64('split', unit_id, seed),
  1000) < 1000 × test_share` → `test`, else `train`); `sample_train(train, cfg) ->
  tuple[DataFrame, dict]` (`negative_downsampling`: every positive row and the negatives with
  `pmod(xxhash64('sample', unit_id, month, seed), 10⁶) < keep_fraction × 10⁶`; `client_sample`:
  the clients with `pmod(xxhash64('sample', unit_id, seed), 10⁶) < share × 10⁶`; an empty
  train split after sampling fails loud; the record:
  the method, its parameter, the seed, the rows and the target's mean before and after, the true
  and the sampled rate of D-049; without sampling the identity, recorded as `method: None`).
- `contract.py`: `check_contract(panel, cfg) -> list[dict]` on the eligible rows: every window
  month and the validation month has some (shared), then on the window's: unique keys (shared),
  the task's checks (binary: both classes and the pooled positive rate ≤ `data.rate_band.max`,
  `positive_rows` and the rate per month in the entry; regression: a finite, non-constant
  target), then the null callout (shared): the share of rows whose window held a null in the target column and,
  above 0 without `null_as`, the callout text; `None` with a note for an upstream target. A
  failing check raises with its numbers; each entry prints one line.
- `frames.py`: `estimate_collect(frame, name) -> dict` (the exact rows, bytes per row from a
  10,000-row sample's `memory_usage(deep=True)`, the estimate at twice the product; an empty
  frame fails loud naming it); `collect_frame(frame, name, env) -> tuple[pd.DataFrame, dict]`
  (the printout, the callout above the budget, the collect, the measured size).
- `model_input.py`: `read_model_input_metadata(cfg, entity, env) -> dict` (refuses a missing table, another
  `schema_version` or `hash_version`, another data definition and another `data.split`, each
  naming `save_model_input`); the saved table's `month` is cast to a date on read, so a session
  without Spark's partition type inference gives the same frames; `saved_candidates(cfg, entity, env) -> list[str] | None` for the
  audit log's feature decisions (`None` when the config names no model input or none is saved
  yet; a mapping the environment lacks fails loud); `read_model_input(cfg, entity, env, spark)
  -> tuple[DataFrame, list[dict], dict]`, the panel with the logs and the meta it was saved
  with.
- Tested on the unit preset end to end (the window frame with the holders tagged, the modelling
  frames split by client, the model input round trip equal to the frames built in memory, the
  stale-input refusals, the callout above a tiny budget, regression with client sampling) and on
  hand-made panels for the join, every eligibility rule, the split and sampling statistics, and
  each contract refusal.

## Open questions
- The contract runs when the panel is built or saved; `data.rate_band`, outside the
  data-definition hash, is not re-checked when the model input is read, so a band tightened
  after saving is checked at the next rebuild (the ML audit of Stage 1, a hardening item).
- Performance on real sizes: the panel is a lazy plan over the sources, so every action
  (the join log, each filter's counts, each contract check, each collect) recomputes the joins
  and the target's window function. On the unit preset a stage's frames take about ten seconds;
  whether to persist the panel inside the bank is decided when a real source is read (M2.4).
- `month` reaches pandas as `datetime.date` objects (Spark's `DateType` through Arrow); whether
  EDA wants `datetime64` is settled when EDA is built (M2.2).
- The window ablation details (OD-17; a nice to have in M4). Sampling is settled for Phase 2
  (D-117); smarter downsampling, including low-value rows with weights that calibrate back, comes
  later.
- Whether FLAML's group split runs as expected (spike 1, unverified on 2.7; no sample weights in
  Phase 2, D-117); the fallback is in [training](training.md) (D-106).
