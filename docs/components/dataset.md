# Dataset: observation window, splits, sampling
**Status:** designing · **Legacy:** `src/io.py` (load + prune in Spark), `src/dataset.py` (labelled frames, downsampling)
**Related:** [config](config.md) (time and data sections) · [training](training.md) · [evaluation](evaluation.md) ·
[feature checks](feature_checks.md) · [EDA](eda.md) · [test harness](test_harness.md) · D-030, D-049, D-052, D-054, D-082, D-083, D-088, D-091, D-098, D-106, D-117 · OD-17

## Purpose
Builds the frames every stage works on, from one definition. That means the eligible population over
an observation window, with targets attached, split into train / test / validation, pruned and
sampled in Spark, then collected. Training on a window of months instead of a single month is a
Phase 2 big-ticket item (D-030). This doc owns its downstream effects.

## Time model

The periods, earliest to latest:

1. **Backward windows** (≤ 6 months): the history features look back over, reaching before `t1`.
2. **Observation window `t1 … tk`**: train + test, every eligible unit-month in it, split by
   client.
3. **Target windows**: the forward months the window's targets look into; the last one ends at
   `tk + w`.
4. **Validation month `v ≥ tk + w`** (OOT): its target window (`v+1 … v+w`) starts after the last
   training target window ends (`tk + w`).
5. **Inference**: later months, after `v`.

- Features are as-of each observation month; targets look forward `(1, w)` (§4.1).
- The observation window (train months) and the validation month are set in the config. The
  validation month sits outside the data-definition hash (EDA never reads it; Feature Checks reads it only to leave it out of its comparisons and records the months it compared).
  Moving it changes the config hash before the config freezes and the resolved-input hash after
  (an audit-log entry), never the data-definition hash. The inference month is a run
  argument. Changing the validation month after the config freezes is an audit-log entry, refused
  when any Feature Checks run compared that month (D-088). A Phase 2 production retrain keeps the window
  and the clients; only the inference month moves, since inference always runs on the latest month
  (D-088, D-052).
- Default window: 6 months with `w = 3`, in the examples and as level defaults (D-091).
- Backward windows default to ≤ 6 months, because some sources won't have more than 24 months of
  history.
- Validation is a single month for panel tasks. Series tasks will need rolling validation (later).
- Example on the 24-month synthetic panel with 6-month backward windows, `w = 3` (an illustration:
  the window is chosen per use case, and the synthetic data is built for none in particular, D-064):
  - window = months 6–11;
  - validation month = 14, labels mature by 17;
  - months 18–21 are free to test scoring plus monitoring with matured labels.

## Phase 2 requirements
1. Eligibility (ordered config steps) is applied identically to every month of train/test, validation
   and inference (§4.9). Each step logs rows in → out.
2. Keep every eligible unit-month row in the window. Report both **positive rows** and **positive
   events**, because one conversion is positive in up to `w` consecutive months. Every rule that
   uses a count of positives as evidence (minimum support per stratum, standard errors, the AUC
   floor, per-month statistics) counts events, and bootstraps and CV folds resample clients
   (D-082). The model itself keeps every row: correlated rows cost variance, not bias (below).
3. Split train/test by client (§4.11). Each client is assigned by a seeded hash of its id, so the
   assignment is stable across months and reruns. Any CV inside train is grouped by client, as the
   calibration step's out-of-fold predictions are (D-094), and FLAML's trial selection gets the
   client groups, so no fold mixes a client's rows ([training](training.md), D-106).
   EDA and Feature Checks use every client in the window, labels included; the split happens after
   Feature Checks, and from Training on fitting, automated selection, calibration and every choice
   use train-split clients only (D-030).
4. Validation is the OOT month, scored by models trained on train only. It never informs selection
   or tuning (§4.4).
5. Prune columns and rows in Spark, and sample in Spark before collecting. Estimate the collected
   size first and fail loud if it exceeds the row/memory budget, *before* calling `toPandas`.
6. Sampling happens only when the config declares it: a person's choice, made for a rare target or
   for the row budget alike; the framework never samples on its own (D-117). It is train-only,
   recorded, and happens after the client split. Phase 2 keeps it simple (D-117); the options, with
   when-to-use guidance (guidance, not automatic triggers):
   - **uniform negative downsampling.** Suits rare binary targets. Keeps every positive row and one
     keep fraction of the negative rows for the whole window, without stratifying by month: months
     are large, similar slices, and one fraction keeps one prior-shift offset valid for every
     month (D-117). The offset corrects the class balance.
   - **client-level random sampling** (all rows of the sampled clients). Suits common targets and
     regression. The offset comes out ≈ 0.
   - **no sampling,** whenever the config declares none.

   When the training rows exceed the row budget and the config declares no sampling, the dataset
   step fails loud, naming the row count, the budget and the two options with their guidance
   (D-117).

   Outcome-stratified client sampling with weights, downsampling low-value rows and smarter
   downsampling in general are on the Phase 3 wishlist (D-117).

   Whatever the option, the prior-shift offset uses the effective training rate (D-049): in
   Phase 2, with no sample weights, the sampled rate; once weights arrive (Phase 3), the weighted
   rate, since the unweighted rate would correct twice.
7. **No sample weights in Phase 2** (D-117). They arrive with outcome-stratified sampling in
   Phase 3, together with the per-task spec's list of statistics that must take them (D-117).
8. **Denominators** (D-098): the "true population" is the eligible rows regardless of label (the
   drift reference and the contract band use it); the prior-shift true rate comes from the
   unsampled train split, never train plus test; the null-label share (clients who leave inside
   the target window, panel-edge rows) is reported per month and per scoring batch; probabilities
   are conditional on staying through the target window.
9. Contract checks on the true population before any sampling (§4.8): unique unit per month,
   non-degenerate target, plausible rate band. This doc owns them; which checks apply comes from
   the per-task spec (D-050).
10. No refit frames in the sandpit in Phase 2 (D-052): the production retrain builds its frames on
    the same data definition: same window, same clients; only the inference month moves (D-088).
    Frames on moved or extended data (later months, all clients, a longer window) are on the
    Phase 3 wishlist (D-052).

## Downstream effects of the window

| Area | Effect |
|---|---|
| EDA | Feature–target views on every client in the window (D-030); base rate per month (population level, for seasonality) over every month up to the window's end, because later months' target windows overlap the validation month's (D-030) |
| Feature Checks | Stability across the window's months on every client (per-month AUC range, PSI; D-030); the months it compared are recorded (D-088); label-free PSI against the gap months between window and `v` and the latest month, never `v` |
| Training | Train/test client split, after Feature Checks (D-030); calibration folds grouped by client; FLAML's trial selection grouped by client (D-106); row budget |
| Calibration | Prior shift from the effective training rate (the sampled rate in Phase 2, D-049) to the unsampled train split's true rate (D-098); per-month base rates reported (seasonality); optional general calibration step out-of-fold inside train (D-049) |
| Evaluation | Test (unseen clients, same months) vs validation (OOT): for a run nothing was picked on, the gap separates overfitting from decay over time, apart from the cost of EDA and Feature Checks on every client (D-030); a sweep's winner states that its gap mixes overfitting with selection (D-083). Optional: validation on test clients only (unseen clients and an unseen month) |
| Inference | Unchanged: one month at a time |
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

  Rough cost: rows × columns × 8 bytes for the frame, and 2–4× that at peak while the engine builds
  its own structures.
- Responses, in this order:
  1. Prune features first (Feature Checks).
  2. Sample clients rather than rows.
  3. Keep the training grain monthly and aggregate weekly or transactional data to it upstream.
     Modelling raw transactions is a different problem (sequence models) and outside the panel
     family.
  4. Only then, a Spark-native engine (e.g. XGBoost's PySpark estimator) as another entry behind
     the model interface. Unverified on the bank cluster and not built in Phase 2.
- Scoring has no such ceiling: inference runs in Spark.
- **To tell whether the cap costs accuracy,** run a learning-curve check: train on 25 / 50 / 100% of
  the budget and score the same test split. If the curve is still rising, raise the budget or
  change the sampling. The choice is made on test, never on the validation month (D-083).

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
  inverse-probability weights it is unbiased again; that option is on the Phase 3 wishlist
  (D-117).
- **Two practical traps:**
  - Sample *after* assigning clients to train/test, so no client straddles both.
  - Use one keep fraction for the whole window, so the window's month mix isn't distorted and one
    prior-shift offset holds for every month (D-117).
- Phase 2 (D-117): sampling only when the config declares it; option 1 suits rare binary targets,
  option 2 common targets and regression. A check against the synthetic oracle (reliability
  curves) is planned to show whether option 1's offset brings scores back to the true level
  ([training](training.md) Open questions); comparing every option against the oracle is on the
  Phase 3 wishlist.
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
  `docs/context/environment.md`).
- One function builds each frame from the config; stages never assemble their own.

## Interface
*(fill when built)*

## Open questions
- The window ablation details (OD-17; a nice to have in M4). Sampling is settled for Phase 2
  (D-117); smarter downsampling, including low-value rows with weights that calibrate back, is on
  the Phase 3 wishlist.
- Whether FLAML's group split runs as expected (spike 1, unverified on 2.7; no sample weights in
  Phase 2, D-117); the fallback is in [training](training.md) (D-106).
