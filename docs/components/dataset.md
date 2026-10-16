# Dataset: observation window, splits, sampling
**Status:** designing · **Legacy:** `src/io.py` (load + prune in Spark), `src/dataset.py` (labelled frames, downsampling)
**Related:** [config](config.md) (time and data sections) · [training](training.md) · [evaluation](evaluation.md) ·
[feature checks](feature_checks.md) · [EDA](eda.md) · [test harness](test_harness.md) · D-030, D-048, D-049, D-052, D-054 · OD-17

## Purpose
Builds the frames every stage works on, from one definition. That means the eligible population over
an observation window, with targets attached, split into train / test / validation, pruned and
sampled in Spark, then collected. Training on a window of months instead of a single month is a
Phase 2 big-ticket item (D-030). This doc owns its downstream effects.

## Time model

```
months  …─[backward windows ≤ 6m]─┤ observation window t1 … tk ├─ target windows ─┤ v ├─ … ─┤ inference ├
train + test   every eligible unit-month in t1 … tk, split by client
validation     the OOT month v ≥ tk + w: its target window (v+1 … v+w) starts after the last
               training target window ends (tk + w)
```

- Features are as-of each observation month; targets look forward `(1, w)` (§4.1).
- Backward windows default to ≤ 6 months, because some sources won't have more than 24 months of
  history.
- Validation is a single month for panel tasks. Series tasks will need rolling validation (later).
- Example on the 24-month synthetic panel with 6-month backward windows, `w = 3` (an illustration:
  the window is chosen per use case, and the synthetic data is built for none in particular, D-068):
  - window = months 6–11;
  - validation month = 14, labels mature by 17;
  - months 18–21 are free to test scoring plus monitoring with matured labels.

## Phase 2 requirements
1. Eligibility (ordered config steps) is applied identically to every month of train/test, validation
   and inference (§4.9). Each step logs rows in → out.
2. Keep every eligible unit-month row in the window. Report both **positive rows** and **positive
   events**, because one conversion is positive in up to `w` consecutive months.
3. Split train/test by client (§4.11). Each client is assigned by a seeded hash of its id, so the
   assignment is stable across months and reruns. Any CV inside train is grouped by client.
   Label-using checks in EDA and Feature Checks apply the same assignment first and use train-split
   clients only (D-048).
4. Validation is the OOT month, scored by models trained on train only. It never informs selection
   or tuning (§4.4).
5. Prune columns and rows in Spark, and sample in Spark before collecting. Estimate the collected
   size first and fail loud if it exceeds the row/memory budget, *before* calling `toPandas`.
6. Sampling is train-only, recorded, and happens after the client split. The options, with
   when-to-use guidance (default: OD-17):
   - **row-level negative sampling, stratified by month.** For rare binary targets. Keeps all
     positives; the prior-shift offset corrects the class balance.
   - **client-level random sampling** (all rows of the sampled clients). For common targets and
     other tasks. The offset comes out ≈ 0.
   - **outcome-stratified client sampling with inverse-probability weights.** Keeps every
     converting client's full history. The weights restore the true rate, so the offset is 0.

   Whatever the option, the prior-shift offset uses the effective (weighted) training rate (D-049);
   computed from the unweighted rate it would correct twice.
7. Optional recency weighting through sample weights, off by default.
8. Contract checks on the true population before any sampling (§4.8): unique unit per month,
   non-degenerate target, plausible rate band. This doc owns them; which checks apply comes from
   the per-task spec (D-050).
9. Window ablation: the same config with only the window changed produces comparable runs, scored
   on the identical validation set (see below).
10. Refit frames (D-052): all clients (train + test) of the window, or an extended window moved to
    the latest months whose labels have matured. They are built by the same function.

## Downstream effects of the window

| Area | Effect |
|---|---|
| EDA | Feature–target views on train-split clients in the window; base rate per month (population level, for seasonality) over every month up to the window's end, because later months' target windows overlap the validation month's (D-048) |
| Feature Checks | Stability across the window's months on train-split clients (per-month AUC range, PSI); label-free PSI against the gap months between window and `v` and the latest month, never `v` |
| Training | CV grouped by client; sample weights (sampling option 3, recency); row budget |
| Calibration | Prior shift from the effective (weighted) training rate to the window's true rate; per-month base rates reported (seasonality); optional general calibration step out-of-fold inside train (D-049) |
| Evaluation | Test (unseen clients, same months) vs validation (OOT): the gap separates overfitting from decay over time. Optional: validation on test clients only (unseen clients and an unseen month) |
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
  the budget and score the same validation set. If the curve is still rising, raise the budget or
  change the sampling.

### Is automatic downsampling safe when a client's rows are correlated?
- Random negative sampling (independent of the features, within each class) is unbiased. It keeps
  each class's feature distribution and only shifts the class balance, which the prior-shift offset
  undoes. Correlation between a client's rows doesn't bias it. The rows simply carry less independent
  information than their count suggests, so dropping some costs less than it looks.
- **Converting clients** matter. A client who converts in month `m` is positive at observation months
  `m−w … m−1` and negative before, with nearly identical features at `m−w−1` and `m−w`. Those
  pre-conversion negatives are the most informative negatives, and random row sampling keeps only a
  fraction of them.
  - That is lost variance, not bias.
  - It is mostly about timing, which is inherently hard to learn. Regularisation and client-grouped
    CV stop the model from memorising individual clients.
- **What would bias the model:** sampling based on a client's outcomes across months (e.g. keep every
  converting client's full history plus a sample of the rest) *without weights*. With
  inverse-probability weights it is unbiased again; that is sampling option 3.
- **Two practical traps:**
  - Sample *after* assigning clients to train/test, so no client straddles both.
  - Stratify by month, so the window's month mix isn't distorted.
- Recommendation: default to option 1, offer options 2 and 3 with guidance, and compare all three on
  synthetic data. There the oracle shows which comes closest to the truth.

### Does a multi-month window actually beat a single month?
This is answered by a built-in **window ablation**:
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
- No second validation month: it would push the training window further into the past. The choice
  weighs test and validation performance equally; train performance only shows the overfitting gap,
  since it is in-sample and weighting it would reward overfitting (D-062).
- The mechanism (vary one config field, compare on a fixed validation set) is also the bounded-axis
  loop the original roadmap planned for the LLM branch. It is built once in Phase 2 as an
  experiment-sweep function (name to be decided; see [run modes](run_modes.md)); the LLM drives it
  later. This section owns the ablation design. A sweep that *picks* a window for a use case labels
  the winner's validation result as optimistic (D-053).

## Design constraints
- Spark does every row and column reduction. `toPandas` runs only on the pruned, sampled frame
  (`CLAUDE.md` §5; a full-width `toPandas` was the crunch's main OOM risk, see
  `docs/context/environment.md`).
- One function builds each frame from the config; stages never assemble their own.

## Interface
*(fill when built)*

## Open questions
- The default sampling option and its parameters; the window ablation details (OD-17). Proposed:
  option 1 as the default, settled by the synthetic-data comparison (backlog in `docs/roadmap.md`).
- Default window length per profile.
- FLAML grouped CV on 2.7 (`split_type="group"` with `groups`): unverified.
