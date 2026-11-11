# Lessons from the crunch and known traps

**Verdict:** the crunch proved the spine works end-to-end. The bugs that hurt were almost all
**environment and boundary bugs** (paths, versions, write modes, HDFS) that stubbed tests couldn't
catch, plus a few **silent statistical traps**. Phase 2 answers these with a real local-Spark test
harness, an environment adapter and explicit invariants. Legacy file references are to
`legacy/propensity_crunch/`.

## Known traps (check before writing related code)

| # | Trap | What happened | Rule now |
|---|---|---|---|
| T1 | numpy 2 vs PySpark 3.4 | `import flaml` → pandas-on-Spark → `np.NaN` → crash | Compat shim before any pyspark/flaml import (`src/core_modelling/_compat.py`) |
| T2 | `pathlib` on `hdfs://` | `Path("hdfs://x")/"y"` → `hdfs:/x/y`; `_is_hdfs` silently false | HDFS paths are strings joined with `/`; only local paths become `Path` |
| T3 | Reading HDFS in Python | `pickle` / `read_bytes` can't read HDFS | Fetch to a local temp dir via `hdfs dfs -get`, then load |
| T4 | `str / str` TypeError | A temp dir (str) was passed into a function using `/` | Local-I/O functions coerce `Path(x)` at their boundary |
| T5 | cwd-relative roots | `Path("artifacts")` resolved to the notebook's cwd; logs were read from the wrong place | All roots come from config; never cwd-relative |
| T6 | Overwrite inside a loop | Per-product `mode("overwrite")` kept only the last product's scores | Collect → union → write once; assert every "ok" product landed on disk |
| T7 | Overwrite-first-then-append across runs | Run 2 wiped run 1's batch | Batch-scoped outputs (`<root>/<batch_id>/…`) |
| T8 | Backward rollup off-by-one | `rangeBetween(-m, -1)` excluded the current month | Backward includes current: `(-(m-1), 0)`; forward excludes: `(1, m)` |
| T9 | FLAML metric names | `average_precision` isn't a FLAML metric | Use FLAML's own names (`roc_auc`, `ap`, `log_loss`, …) |
| T10 | PSI on categoricals | `np.quantile` on strings crashed | Numeric-only PSI; categoricals need their own stability measure |
| T11 | Eligibility × feature | Under `is_fx_active = 0`, FX-activity features were constant 0 | A feature built from the eligibility-defining activity is dead; flag automatically |
| T12 | Target-signal leakage | The raw forward column the target was built from sat next to it in the panel | Target lineage columns are auto-excluded, not remembered |
| T13 | Hardcoded window literals | The panel-edge guard hardcoded `3` | Windows come from config only |
| T14 | FLAML trial counting | Reading the search log gave wrong counts (path issue) | Use `automl.config_history` and `best_config_per_estimator` |
| T15 | Stubs hide environment bugs | The smoke test passed while T1–T7 were live | Real local Spark on a synthetic panel for the e2e test |
| T16 | Fixed chart ranges at low prevalence | Calibration curves drawn on (0, 1) and binned bar charts of tiny rates showed nothing; most chart fixes made inside the bank were range fixes | Axes follow the data (`(0, 1.25 × max)` for rates); show lift vs base rate with counts. Chart rules: `docs/components/reporting.md` |
| T17 | Explainer incompatibility | SHAP errored for most of the original estimator set and had to be disabled | Decide view × model-family compatibility up front (`docs/components/evaluation.md`); never wrap a view in try/except |
| T18 | Nanosecond timestamps in parquet | pandas `datetime64[ns]` written by pyarrow is `timestamp[ns]`; Spark 3.4 fails to read it ("Illegal Parquet type"). Found in M1 step 0, outside the crunch | Period columns are dates (the framework holds a period as its last day, D-129); write any real timestamp with `coerce_timestamps="us"` |
| T19 | Date arithmetic on period keys | Spark 3: `add_months(date'2024-02-29', 1)` is 2024-03-29 and `add_months(date'2024-04-30', 1)` is 2024-05-30 (checked on 3.4.3, 2026-10-26), so month arithmetic on month-end dates drifts off the month's end and equality on the period key stops matching; a last-day month also falls outside a first-day `BETWEEN` window, and adding 7 days to a week key or 1 day to a day key hides a gap in the data as one step. Found in Stage 1's review, before any code relied on it | Periods are held as their last day (D-129); every step between periods goes through the period index of `periods.PERIODS` (consecutive periods → consecutive integers, in Python and in Spark), never `add_months` or added days, so a missing period is a gap, never skipped |
| T20 | A sampling draw that shares the split's input | `client_sample` drawn from `xxhash64(unit_id, seed)` with the split drawn the same way and the same default seed would keep, among the train clients (a draw of 0.3 or more), only those below 0.5: 29% of them, not the 50% asked, and always the same slice of the split. Found in Stage 1's dataset build (2026-10-27), before any run relied on it | Every draw on the keys carries its own salt (`'split'`, `'sample'`) beside the seed (`split._hash_uniform`); a test checks the client sample's share with the two seeds equal |
| T21 | A sidecar file in a parquet folder | Spark's listing skips files whose name starts with `_` or `.`, except `_metadata` and `_common_metadata`, which it reads as parquet summaries: a `_metadata.json` beside the model input's partitions failed the read with "not a Parquet file". Found in Stage 1's dataset build (2026-10-27) | A sidecar in a table folder is named `_<something>.json`, never starting with `_metadata`; the model input's is `_model_input.json` |
| T22 | A hash draw on the id column's bytes | The split's draw (`xxhash64` over `unit_id`) hashes the column's bytes, so the same digits as a string (`'12345'`) and as a long (`12345`) draw differently: an upstream change of the id column's type would move every client between train and test, silently. Found by the hash check on structured ids (2026-10-28), before any run relied on it | `read_keyed_source` casts `unit_id` to string at load, so the draw is independent of the id's storage type for integer, long and string ids. A double or decimal id casts to `'12345.0'`, so an upstream move from integer to decimal still moves every client; the source log's `id_type` shows it. A test reads an integer id back as a string and the pinned draw (`'12345'`, salt `split`, seed 42 → 0.322993) is unchanged |
| T23 | A screen that flags without acting | At the `autonomous` level a flag that only annotated left leaking features in the model (Stage 2 design, 2026-11-02) | Flags hold a feature out of training until a person keeps or excludes it (D-134); every check states what it changes at `autonomous` |
| T24 | Sampling the analysis population | A client sample before the collect would have made the report's statistics approximate (Stage 2 design, Q482 rejected). Collecting the window instead does not fit: the `dev` window (117,000 rows × 160 columns) took about 0.5 GB at the conversion peak, the canonical one extrapolates to 2.3 GB, above Spark's default `maxResultSize` of 1 GB, and a bank window of 1–5 million clients × 200–400 columns to 10–50 GB | Window statistics are Spark aggregates (the counts table); the snapshot is collected whole; never sample the analysis population (D-135) |
| T26 | `Bucketizer` null vs NaN | With `handleInvalid="keep"` a NaN lands in the extra bucket but a NULL input gives a NULL output bucket, so "null and NaN in their own bucket" is half true; duplicate splits are refused with an unreadable message. Measured on PySpark 3.4.3 (the Stage 2 facts spike, 2026-11-03) | The counts pass maps both the null bucket and the extra bucket to the one null bin (`is_null`), deduplicates the splits (`quantile_edges` does) and builds singleton bins with `np.nextafter`; ints and decimals need no cast. `-0.0` sorts below `0.0` in Java's `binarySearch`, so the pass normalises `-0.0` before bucketing (measured: unnormalised it lands in the bucket below). `F.isnan` on a string column casts it to double first (`isnan('NaN')` is true), so NaN handling is gated on float and double types |
| T27 | Wide per-client aggregates and an ambiguous target | `groupBy(unit_id)` with min, max and count over 139 columns (417 aggregates) spills 2.2 GB and fills the 2 GB heap on the Mac, while the lag pass over the same columns is fine (19 s); `F.lag` of the target beside a same-named feature column makes `F.col("cc_flag")` an `AMBIGUOUS_REFERENCE`. Spike 2026-11-03 | The client-constant shares are computed in column chunks or inside the lag window; the target is always read as `target`, never as its source column |
| T28 | Rank-once is not the pairwise-complete Spearman | Ranking every column once over its non-null rows and taking Pearson on the ranks differs from the pairwise-complete Spearman by up to 0.23 when the two columns' null masks differ; pandas' own `corr(method="spearman")` with nulls takes 123 s at 139 × 200,000. Spike 2026-11-03 | Group the columns by their null mask: rank once inside a group (exact there), rank per pair across groups; `na_option="keep"` only (`top`/`bottom` tie the nulls into ranks) |
| T29 | `association(method="cramer")` on empty marginals | scipy raises `ValueError` on a table with an all-zero row or column and needs an integer table; a one-row table returns NaN with a warning. Spike 2026-11-03 | Drop empty marginals up front and return "not compared" below 2 × 2; never catch the error (§1.8) |
| T30 | plotly ids, log axes and the Styler's dependency | A `div_id` given twice is kept twice (no deduplication); a zero quartile on a log axis is clamped to the axis floor with no warning; `DataFrame.style` needs jinja2, which the venv lacked although matplotlib was pinned. Spike 2026-11-03 | The report writer generates every id itself; a distribution with zeros never goes on a log axis without an offset or a separate zero share; jinja2 3.1.6 is pinned before the Styler path (asked of the EDS) |
| T31 | Parquet and JSON round trips of artifact values | A parquet list column reads back as numpy arrays (not lists) and an all-empty list column is written as `list<null>`; `np.datetime64.tolist()` is nanoseconds since the epoch, so a date written through the generic numpy branch becomes an integer; `json.dumps` writes NaN as a bare `NaN` token (invalid JSON) by default. Spike and m1.5's review, 2026-11-03 | `read_parquet` turns list cells back into lists; `datetime64` goes through `pd.Timestamp(...).isoformat()`; `json.dumps(..., allow_nan=False)` so a NaN fails loud and the stage writes `None` |
| T32 | Table statistics against their row oracles | The concordance from the two-way table equals the AUC of the binned values to 1e-16 and is within 0.0001 of the raw AUC at 100 bins, but the regression τ-b against a 20-bin target differs from `kendalltau` on raw rows by up to 0.009; `numpy.linalg.lstsq` on exactly collinear columns returns R² = 1 while `inv`/`solve` raise `LinAlgError`. Spike 2026-11-03 | Tests compare table statistics with the oracle on the BINNED rows (exact) and state the raw tolerance; `explained_by_others` uses `lstsq` or a 1e-6 ridge, never `inv`, capped at 1 |
| T33 | A target encoding fitted in sample flatters noise | Ordering a categorical's levels by their shrunk target rate on the same rows made a null 20–50-level code read 0.53–0.57 at ~190 events per period (shrinkage never reorders equal-sized levels, so it removes none of the optimism); a fixed best-order margin of 0.03 marked 42% of null numerics `non_monotone` at 500 events, because ordering ten groups by their own rates gains about 2 SE on noise. On a panel the same clients sit in every period with persistent labels: an encoding fitted on the other periods still read 0.57, and a window SE counted in rows marked a null numeric 12–18% of the time, and the cross-fitted value spreads about 1.4× its SE. Measured 2026-11-03 and 2026-11-04 | The level encoding is cross-fitted by client fold (each fold's levels ordered by the other folds' clients, pairs inside a fold only); the best-order margin is max(0.03, 4 SE) with every window SE on effective clients (Kish, the per-task `client_support`) |
| T34 | A collected frame's row order | `toPandas()` after joins and shuffles returns rows in no guaranteed order, so a positional seeded sample (`DataFrame.sample(n, random_state=0)`, the association's 50,000-row cap) can pick other rows on a rerun of the same data, and a FLAML fit on such a frame need not repeat. Found by the ML audit of Stage 2 major step 2, 2026-11-04 (not measured: the unit preset is below the cap) | `collect_frame` sorts every collected frame by the keys in Spark (`orderBy("unit_id", "period")` before `toPandas()`, so pandas holds no second copy at the peak), so a seed alone fixes a sample (`CLAUDE.md` §4.10) |
| T35 | A "rare cell" read on quantile bins | Every bin of a numeric cut into `eda.bins` = 100 quantile bins holds about 1% of the rows by construction, so a rule "a cell below 1% of the window's rows whose rate is 5× the rest's" read every bin as rare and flagged the top bin of 51 legitimate monotone numerics on the canonical data (balances, income: 13–46% against 2.5%), while it missed the process-leak trap whose leaking value holds 1.34%. Found by measuring the build's first `rare_value_leak` on the 100k artifacts, 2026-11-06 | Rarity is judged against a dominant value, as the approved design had it (Q441): one filled value on at least 90% of the filled rows, the other values pooled, their rate against the dominant value's (Cohen's h since 2026-11-09, Q539); a rule on a binned statistic is measured on the real artifacts before it ships |
| T36 | A background test run that hangs for hours | A background `pytest` whose Spark JVM died under memory pressure (the 8 GB Mac, with the EDS's Jupyter JVMs beside it) waited on the dead gateway without failing; nothing watched it, and 5 h 45 min passed before anyone looked (Feature Checks' build, 2026-11-07) | Every background Spark test or job runs under a deadline of about twice its expected time (macOS has no `timeout`: `perl -e 'alarm shift; exec @ARGV' <seconds> <command>`), and a run past its expected time is looked at, never waited on |
| T37 | A standard error read at the estimate collapses at the edges | Hanley–McNeil's SE of a concordance taken at its own value goes to its floor (0.005) as the value nears 0 or 1, so on a thin period (2 events) a chance 1.0 reads as precise: it dominated Cochran's Q (3–4% false `concordance_unstable` on a homogeneous feature in simulation) and passed as "significant" against a threshold. Found by the ML audit of Feature Checks' Q540 build, 2026-11-09, once support guards no longer kept thin periods out | A weight or a significance test uses the SE at the reference value on the observation's own support: the pooled value for a heterogeneity test, the threshold for "past the threshold", 0.5 for a flip; the SE at the estimate is for display only |
| T25 | Quantile bins that collapse into one bucket | `pd.qcut(..., duplicates="drop")` on a zero-inflated or discrete column puts most quantile edges on one value and leaves one bucket for everything else; fixed-width `pd.cut` on a skewed column puts nearly every row into the first bucket. Seen in EDA plot code (the EDS, 2026-11-03), before the counts table was built | The edges rule: values holding at least `1 / bins` of the rows (mass points) are singleton bins and the quantile edges are taken over the remaining values; charts merge cells by cumulative row share, never by equal width; a test asserts the bin count on constructed columns and on every synthetic numeric (`docs/components/eda.md`, D-135) |

## Statistical lessons

- **Mutual information is useless at very low prevalence.** At 0.04–0.2% positives, the kNN MI
  estimator returned near-identical values across different targets and took 30–40 min.
  Rank features with univariate AUC (base-rate agnostic) and read direction from target-rate
  deciles. Don't compute MI on downsampled data: it silently changes the joint distribution.
- **Univariate AUC floor.** Direction-agnostic AUC < ~0.515 is a drop candidate. Treat this mainly
  as a speed lever (more FLAML trials per budget). Its standard error is the
  Hanley–McNeil formula in positive events (distinct converting clients, not rows, D-082). At
  the null it is `1 / sqrt(12 · events)`, about `0.29 / sqrt(events)`: a simulation at 800 events
  measured 0.0105. The crunch's `0.5 / sqrt(events)` rule overstated it 1.7 times, so the 0.515
  floor sits about 1.5 SE above 0.5 at 800 events.
- **Downsampling.** Keep all positives; the negative:positive ratio is mostly a compute lever that
  barely moves ranking. The positive *count* is the real ceiling (e.g. ~800 for a 0.04% product
  is low-confidence at any ratio). Set the ratio per use case. Stratified negative sampling is the
  upgrade if negatives prove heterogeneous.
- **Calibration (`prior_shift`).** A log-odds offset `logit(true_rate) − logit(sampled_rate)`.
  Apply it only after downsampling. Rank metrics are unchanged. It does **not** fix a model that is
  miscalibrated in itself — check the reliability curve.
- **Contract checks before downsampling.** A base-rate floor produced false alarms on legitimately
  rare products. The real "degenerate target" guard is `nunique > 1`; the band only catches
  implausible *high* rates.
- **The event offset under a forward-window label is flat by construction.** Under
  `flag_goes_up` a unit converting in period m is positive at m−1 … m−w, one row at every offset
  1 … w (an amount under `forward_sum` alike), so the offset's distribution is flat except at
  the source's edges and gaps. When the events happen is the view that carries information:
  Target Factory reports the occurrences per period (`docs/components/target_factory.md`).
- **PR-AUC is not comparable across products.** Its floor is the base rate. Compare products on
  ROC-AUC and top-k lift.
- **Pooled AUC is inflated.** 0.85–0.95 on a heterogeneous base is not within-segment skill. Report
  segment-stratified metrics.
- **Single training month** bakes in that month's seasonality. Phase 2 trains on an observation
  window (D-030; `docs/components/dataset.md`); the model card records the window and per-period
  base rates.
- **Importance.** Permutation importance splits credit across correlated features. Native
  importance doesn't align with raw-string categoricals (FLAML encodes them internally). SHAP via
  `PermutationExplainer` works for any model but is slow — sample it. Per-level categorical tables
  are the reliable categorical view.
- **A range across periods flags noise.** At 50 events per period a concordance's null SE is
  about 0.04, so six periods show a range near 0.10 from noise alone. A range rule flags exactly
  where the data is thinnest; stability is a test weighted by 1/SE² (Cochran's Q) with a floor on
  the relative range.
- **A forward-against-backward label check separates nothing on acquisition targets.** On the
  eligible rows (non-holders) the backward label is almost always 0. With holders included, a
  legitimate holding feature and its shifted twin both predict the past event perfectly. The
  signal worth a flag is a jump at the boundary, which the lagged concordance measures.
- **The crunch's statistics, beyond T10–T16.** Every statistic ran after median imputation, so
  missingness leaked into the signal. Its PSI dropped nulls first, so a missingness shift was
  invisible. VIF silently dropped constant columns, which hid T11. Signal persistence used the
  OOT month's labels for a feature decision. The univariate AUC was implemented twice. Every
  threshold was a literal in code or a notebook. Phase 2's answers: a null is a bin of its own
  (D-029 (c)), `CLAUDE.md` §4.4, one statistics package, every threshold a config leaf.
- **FLAML search.** It is time-budgeted and cost-frugal. With large data, the cheapest improving
  learner (LightGBM) eats the budget. For a fair comparison, run learners in isolation or raise the
  budget. `sample=True` means early trials run on subsamples.

## Design lessons (kept for Phase 2)

- **Two feature views of one config.** Exploration reads the candidates; the model reads the
  survivors (candidates − exclusions). One file, and excluded features stay inspectable. Phase 2
  keeps the candidates and the rules in the config, records people's keep / exclude decisions as
  audit-log entries the run replays (D-125), and adds the feature ledger as the per-feature view.
- **EDA has to earn its place first.** In the crunch, EDA gave so little insight (and its charts
  showed nothing at low prevalence) that the notebooks were run in reverse order, checks first.
  Phase 2 keeps EDA first but changes its content, and draws clear lines: EDA understands, Feature
  Checks gates, Training selects (D-028).
- **Config-driven top-k metrics:** percentile slices plus absolute-count slices (a count larger than
  the population is skipped). Full-population stats are always reported.
- **The config saved with every run + hashes** (config hash, feature signature, model content hash)
  made every score traceable; Phase 2 saves the resolved config (D-125). The manifest linked
  scoring batches to the exact models; verify the hash before reproducing.
- **Per-use-case run pinning** as a dict `{use_case: run_id}`, never a positional list.
- **Reinference** from registered models + manifest (a new month or table with the same schema)
  worked without the local scratch runs. This is the value of a registry tier.
- **Promote-on-inference was a crunch shortcut.** Phase 2 separates promotion from inference.
- **The model card holds structured facts only** (calibration, downsampling, selected model,
  `best_config`) — no hardcoded prose caveats.
- **Notebooks as interface worked.** One notebook per stage; switch the product and rerun. Phase 2
  makes them guided (instructions on what to look at and decide) and lets users copy them to explore
  (D-039).

## Build-process lessons (Stage 2)

- **Measure the load-bearing facts before the build.** A facts spike on the pinned versions
  settled the counts design before any module was written: one explode pass over every numeric
  runs 4.5 times faster than a per-feature loop, `Bucketizer` keeps a null and a NaN in different
  buckets, the table concordance equals its row oracle. Its outcomes are T26–T32.
- **Fable on every piece spends the allowance in one step.** Major step 1 ran Fable on the main
  thread, two builders and three audits: about 40% of the output tokens and most of the weekly
  allowance. What worked after: the main thread and the builders on Opus or Sonnet, `xhigh` only
  on the two pieces where a wrong answer costs most, and Fable for one whole-stage ML audit at the
  end, where its audits had earned their cost (D-072 (l)).
- **Fold the reviews.** Major step 1 ran 15 reviews and seven fix rounds. One combined review per
  minor step (the code reviewer briefed with the silent-failure and compatibility lenses where
  they apply), the ML audit once per major step and one fix round per major step found as much.
- **A review guide lists code, not tests.** The EDS reads code. A guide names at most two tests
  per major step, marked "read this test" (Stage 2: the hold-out test and the trap acceptance
  test), and lists the notebooks' guide cells as code to read.
- **Tests that read the shipped examples break when someone tries a setting.** Trying a filter
  and three key features in an example config failed six tests. The tests now read frozen
  copies in `tests/conf/`, and one cheap test loads every example in `conf/base/`.
- **A stale-file scan walks the gitignored folders too.** A 120 MB model input that nothing read
  sat in `data/` for two weeks because the scan covered tracked files only.
- **Simplifications the codebase review tried and dropped** (2026-11-10), so nobody retries them:
  fitting a categorical's fold encodings once per feature (needs a parameter with no caller); one
  dotted-path walk shared by `levels.py` and `replay.py` (an import cycle); a refusal on the
  look-ahead buffer (it could never fire); persisting the joined panel (measured: slower).
- **A stage's working notes close with the stage.** Each answer is recorded verbatim before the
  chat is compacted, and the record is deleted when the EDS closes the stage. The docs must then
  stand without the Q-numbers they cite (`CLAUDE.md` §8, References); the questions worth keeping
  go to a stage FAQ (`docs/guides/eda_fc_faq.md`).

## Legacy map (where to look)

| Concern | Legacy file(s) |
|---|---|
| Config schema, validation, two feature views | `configs/_schema.py`, `configs/_TEMPLATE.yaml` |
| Rollups / target building (now Target Factory) | `src/rollups.py`, `notebooks/Data_Creation.ipynb` |
| Spark IO, labelled frames, downsampling (now the dataset component) | `src/io.py`, `src/dataset.py` |
| Contract checks, leakage screen | `src/contract.py`, `src/leakage.py` |
| EDA / feature statistics / plots | `src/feature_stats.py`, `src/plots.py`, `notebooks/EDA.ipynb` |
| Training orchestration | `src/run.py` |
| Calibration | `src/calibration.py` |
| OOT metrics | `src/evaluate.py` |
| Importance and analysis suite | `src/importance.py`, `src/analysis.py` |
| Model card | `src/card.py` |
| Inference, promotion, manifest, HDFS transport | `src/inference.py`, `notebooks/Inference.ipynb` |
| Compat shim | `src/_compat.py` |
| Offline smoke test (stub-based) | `tests/smoke_test.py` |
