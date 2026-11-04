# EDA
**Status:** designing (spec settled 2026-11-02; built in Stage 2, M2.2) · **Legacy:**
`src/feature_stats.py`, `src/plots.py`, `notebooks/EDA.ipynb`
**Related:** [dataset](dataset.md) (the frames) · [feature checks](feature_checks.md) (reads
EDA's artifacts; owns the flag and hold-out rule) · [feature ledger](feature_ledger.md) (the
ledger's columns) · [reporting](reporting.md) (the writer, chart rules) · [config](config.md)
(fields, audit-log mechanics) · [test harness](test_harness.md) (the traps) · D-023, D-029,
D-030, D-031, D-032, D-036, D-050, D-082, D-088, D-125, D-132, D-133, D-134, D-135, D-136, D-137 ·
OD-12 is settled for EDA by this spec

Read it in three levels: Level 1 gives the essentials, Level 2 how the parts connect, Level 3
every detail.

## Level 1: Summary
**What it does.** The first stage after the target exists, and it has to be worth running first:
a fast, readable picture of the population, the target and the features that matter, built for
low prevalence. It informs decisions and never changes data. **Design:** one period, the
**snapshot** (default the window's last period), is collected whole to pandas for everything that
needs rows; every statistic comes from one **counts table** (the cells: rows and target sums per
feature, period, bin and target bin) that Spark aggregates over the **compared periods**, so the
window is never collected (D-135).
- **In:** the data definition (sources, eligibility, target, period, window); `eda.*`,
  `strata.*`, `features.kinds`.
- **Out:** `eda/` (`eda.json`, the counts table and the other tables, `resolved_config.yml`,
  `report.html`), the ledger's EDA columns, a `StageResult` for the notebook.
- **Who uses it:** the DS (report, notebook 02, `pivot_target`); Feature Checks (reads only EDA's
  artifacts); Training (the ledger; the D-088 counts).
- **Key numbers:** N = 10 key features; `eda.bins` = 100 quantile bins (`null` = exact); a warning
  below 500 events in the snapshot; `MIN_BIN_SUPPORT = 20` events per bin.
- **Run it:** `run_eda(cfg, entity, env, spark)`, `python -m core_modelling run <config> --stages
  eda`, or `notebooks/02_eda.ipynb`.

## Level 2: How it fits together
### What drives what
- **Two data shapes, one engine.** The snapshot (`Frames.snapshot`, pandas, every row after the
  analysis filters) serves what needs rows: kinds, bin edges, the correlation matrix, quartiles,
  strata tables, reference groups. `Frames.rows` (Spark, never collected: the eligible rows of the
  compared periods) feeds two Spark passes that write the counts table. Every per-feature
  statistic, the snapshot's included, is a sum over cells: the snapshot's value is the snapshot
  period's cells, the `*_window` twin the window periods' cells (D-135).
- **What belongs where.** EDA *understands*: population, target, key features, strata. Feature
  Checks *gates*: findings, flags and notes, the hold-out ([feature checks](feature_checks.md)).
  Training *selects*, on the train split only, recomputing its own statistics (D-030).
- **What later stages reuse.** Feature Checks reads the counts table, the client-constant table,
  the correlation table, the ledger and `eda.json`; it collects nothing and refuses to run when
  EDA's settings digest differs from the current resolved config. Training reads the ledger
  (`kind`, `levels`, both concordances) and compares its per-period counts with `eda.json`
  (D-088). An EDA rerun removes Feature Checks' folder and ledger columns.
- **The per-task spec** (`tasks.py`, D-050) supplies every task-specific piece: the target bins,
  the group summary (rate or mean, interval, lift), the rare effect, the standard error, the
  events warning and the base-rate views. Binary and regression share every shape.

### How one run flows
1. Resolve the config (audit log replayed, D-125); check the strata and `include` names.
2. Build the frames (`build_frames(..., stage="eda")`): the snapshot collected with the D-133
   printout; `Frames.rows` left in Spark; the funnel and population counts from Spark.
3. Read the kinds from the frames' meta (Spark schema plus `features.kinds`).
4. From the snapshot: the bin edges per numeric, the levels per categorical, the target bins.
5. Spark pass 1: bucket, explode, aggregate: the cells. Spark pass 2: lagged cells and the
   client-constant table.
6. Collect the cells (a few MB) and fit the level encoding on the pooled window cells.
7. Compute every statistic per feature from the cells: snapshot and window twins.
8. Compute the association matrix on the snapshot (capped at 50,000 rows).
9. Rank; choose the key features with the correlation skip.
10. Deep dives for the key features; the population views (funnel, target per period, by
    stratum, reference groups, strata pivots).
11. Write the ledger's EDA columns; write `eda/` through a temporary folder; render the report.

### Function structure in brief
`core_modelling/eda/` only orchestrates: `population.py` (headline, funnel, target views,
reference groups), `ranking.py` (ranking, key features), `deep_dives.py` (deep dives, strata
pivots, `pivot_target`), `run.py` (`run_eda`). It imports the statistics from `statistics/`, the
Spark passes from `dataset/counts.py`, the frames from `dataset/frames.py`, the report pieces from
`reporting/`, the folder handling from `artifacts.py` and the ledger from `ledger.py` (D-137).

### How it is checked
- **Statistics against exact oracles:** `roc_auc_score`, `kendalltau`; the binned value within
  0.005 of the exact one on the synthetic snapshot, equal for discrete and categorical features;
  `eda.bins: null` equal to the exact value; a 300-level random code below 0.52 on the canonical
  window and a 50-level one near 0.50 at 190 events per period with the encoding cross-fitted by
  client fold, also on a panel where the same clients and persistent labels sit in every period
  (in sample they read 0.54–0.60, by period still 0.57 on the panel: 2026-11-03/04); a null
  numeric at 500 events is marked `non_monotone` in at most 1 of 50 seeds with the SE-scaled
  margin (24 of 50 with a fixed 0.03); η = |Spearman|
  for two levels; a unit test on an inverted-U column built in the test (the loan target, which
  carries the synthetic inverted-U age, has no acceptance config): best-order concordance ≥ plain
  + 0.05; a null control's below 0.55.
- **The counts passes:** no label on gap and latest rows, no validation-period row.
- **Artifacts and report:** temporary folder renamed on success; plotly.js embedded once; unique
  `div_id`s; the notebook imports the Public API only.
- **The trap acceptance test** (`dev` preset, D-064): EDA's part is the `*_window` columns the
  findings cite, null controls below 0.55 and never key features, lineage excluded, and the D-088
  population counts, read from `eda.json`. A unit test checks that they equal Target Factory's
  summary where both exist; Target Factory counts every row before eligibility, so only the
  rows-after-filters figure compares.

## Level 3: Details
### Requirements and design constraints
1. **Standalone.** Runs alone from a config and writes its report through
   [reporting](reporting.md) (D-036). `autonomous` runs it automatically with the default
   content (D-031, D-132 (1)). Training refuses without EDA's artifacts for the same
   data-definition hash (`CLAUDE.md` §4.13).
2. **Population and target** (base-rate views from the per-task spec, D-050):
   - the funnel per window period: the analysis filters' drops and, per modelling filter, the
     rows it tags (D-129);
   - **reference groups:** each modelling tag's rows compared with the modelling population,
     label-free (a tag that is the rule's own precondition has a rate of 0 by construction);
   - the base rate per period over the whole window, whatever the snapshot, with positive rows
     beside positive events (D-082);
   - the population counts per compared period saved in `eda.json` (D-088): the rows after the
     analysis filters and the eligible rows for every compared period, the labelled counts inside
     the window only; a later run on the same data definition thus shows a restated source period
     (`CLAUDE.md` §4.10);
   - the base rate by each stratum variable.
3. **Populations** (`CLAUDE.md` §4.4, D-030). The snapshot holds every row after the analysis
   filters, labels included; every label statistic uses the eligible rows only. The train/test
   split happens after Feature Checks; the report states that feature decisions taken from it
   have seen test clients' labels.
4. **Time discipline.** Outside the window the label is dropped before any aggregation; the
   validation period is never read. A test asserts that no label and no validation row reaches
   the passes.
5. **Univariate ranking** of every supported candidate (lineage and unsupported columns excluded
   automatically), snapshot and window twins, written to the ledger.
6. **Key features:** the top `eda.key_features.top_n` (10, both levels, D-132 (2)) with the
   correlation skip, plus the listed ones; each gets a deep dive.
7. **Low prevalence by design:** rates as lift vs base rate with intervals and counts; support
   rules from the statistics section; a cell below support is greyed as "insufficient", its
   interval still drawn, never hidden; the chart rules of [reporting](reporting.md) (T16).
8. **Iterative analysis:** `pivot_target` gives styled pivots by any dimensions with any filter;
   the report itself stays tight.
9. **Fast at bank size:** the window is never collected; the passes use Spark SQL and JVM
   transformers only (no pandas UDFs); only result tables come to pandas; timings in `eda.json`.
10. **Task-agnostic:** one counts-table shape, one statistics engine; every task-specific choice
    from `tasks.py`; no binary assumption in a table or column name.
11. **Exact for small populations:** `eda.bins: null` makes every statistic exact.
12. **Strata validation** (before the frames are built): a stratum naming a framework column
    (`unit_id`, `period`, `target`, `split`, `eligible`) is refused with the `source_<name>`
    hint; a name that is not a frame column fails naming the columns; a numeric stratum with more
    than `strata.max_levels` distinct values is refused ("bin it upstream or list the levels");
    every `eda.key_features.include` name must be a candidate. The modelling tags are strata
    automatically (D-129), never listed.
13. **Kinds** shown, validated and overridable (`features.kinds`); an override of a
    non-candidate fails loud.
14. **Reproducible:** every number follows from the resolved config and the data-definition
    hash; `eda.json` carries the hashes and the settings digest; a rerun rewrites `eda/` whole.
15. **Informs only:** EDA drops no row and no feature and writes no audit-log entry.

Design constraints: report content comes from functions, notebooks display `StageResult.views`
and never assemble a report; no mutual information; no row-level chart: every chart is drawn from cells or quartiles, so no
client is ever plotted and nothing needs sampling ([reporting](reporting.md) requirement 5).

### The snapshot and the compared periods
- **`eda.snapshot`:** `last` (default, the window's last period: the most recent features with
  matured labels) or a period date inside the observation window, checked at load. Frames:
  [dataset](dataset.md).
- **The snapshot's columns:** the keys, `period_label`, `target`, `eligible` (0/1), the
  modelling tag columns, the strata columns and the supported candidates. Lineage and
  unsupported columns are dropped before the collect. The D-133 printout and budget callout apply;
  the callout names `training.sampling` for the training frames only.
- **The compared periods** (`Frames.rows`, eligible rows only): every window period, the gap
  periods between the window and the validation period, and the latest period the data holds;
  never the validation period. With `time.validation_period: null` there is no gap: the window
  periods and the latest period. The latest period is included only when it lies after the
  validation period; without one the two latest-period notes (`psi_latest`, `new_levels`) are
  "not available: no period after the validation period" (D-035).
- **Sizing:** the Mac's 100,000-client canonical snapshot (about 0.2 GB in pandas, 0.4 GB at the
  conversion peak) stands for the bank's full retail snapshot.

### The counts table
**Columns:** `feature, period, lagged (bool), bin (str), bin_order (int), is_null (bool),
target_bin (str|null), n (long), sum_y (double)`; one row per cell.

**Edges and levels** (from the snapshot's eligible rows):
- **Numeric** (`quantile_edges(values, bins)`, T25): first the **mass points**, the non-null
  values whose share is at least `1 / bins` (0 and the dominant value among them whenever they
  reach it), each a singleton bin; 0 is a singleton bin whenever it occurs at all, so `zero_share`
  is read from the `= 0` cell; then the remaining values are cut into `bins − n_mass` equal-share
  bins (quantile edges, deduplicated), so a continuous column gets exactly `bins` bins (`bins` is
  a target, a column may get one or two more). ±infinity is a value: it takes no edge and lands in
  the outer bins (N2). Plain quantile edges collapse on a zero-inflated or discrete column (90% zeros
  put ninety edges on 0 and leave one bucket for the rest, the legacy symptom), and fixed-width
  edges put a skewed column into its first bucket; the rule guarantees that no bin except a
  singleton holds more than about `2 / bins` of the non-null rows. A numeric with at most
  `eda.bins` distinct values uses its values as bins. `eda.bins: null` turns the binning off:
  every distinct value is a bin. A test asserts the bin count on constructed columns and the
  acceptance test on every numeric candidate of the synthetic data. The setting is meant for small populations: before the pass EDA
  estimates the cell count (a cell is one row of the counts table) from `approx_count_distinct`
  per column over `rows` and fails loud above `MAX_CELLS = 50_000_000`, naming `eda.bins`.
- **Categorical:** the levels seen in any window period, the 50 most frequent kept
  (`LEVEL_CAP = 50`), the rest `__other__`; a level unseen in the window is `__new__`; null is a
  level (a NaN in a numeric column declared categorical is null too). `window_levels` returns the
  levels per categorical and the categoricals with more than `POOLED_LEVEL_CAP = 10_000` window
  levels: for those only the kept levels are listed, every other level is `__other__` and
  `new_levels` is "not available: more than 10,000 window levels", decided up front. A real level
  named like a reserved bin (`null`, `__other__`, `__new__`) is quoted in its label (`'null'`).
- **Target bins:** binary, the two values; regression, 20 quantile bins of the snapshot's known
  targets with 0 its own bin (with `eda.bins: null` the target keeps its values); null where the
  label is dropped (gap and latest periods) or the target is null.

**Pass 1:** every numeric bucketed by one `pyspark.ml.feature.Bucketizer` over all columns
(`handleInvalid="keep"`: a NaN lands in the extra bucket, a null input gives a null bucket, and the
pass maps both to the one null bin, `is_null`, T26; `-0.0` is normalised to `0.0` first); then
`explode(array(struct(feature, bin)))` and `groupBy(feature, period, bin, target_bin).agg(count, sum(target))`. Spark's partial
aggregation collapses the exploded rows inside each partition, so the shuffle carries at most
features × bins × target bins rows per partition.

**Pass 2:** the same rows over `Window.partitionBy(unit_id).orderBy(period)`: `F.lag` values on
the same edges become `lagged = true` cells with the current period's target; `min == max` per
client and feature gives the **client-constant table** (`feature, constant_share, clients`: the
share of clients with at least two non-null values whose values never change; a NaN counts as
null, N2; the aggregates run in chunks of 50 columns, T27).

**Population counts per period** (Spark, on the panel after the analysis filters; D-088): rows,
eligible rows, eligible rows with a known target, positive rows, positive events (distinct units
with a positive label; regression: with a non-zero target), non-event units. The label counts
exist for window periods only.

**Sizes:** under 600,000 cells for a binary task on the synthetic canonical data (150 features ×
9 compared periods × ~102 bins × 2 target bins, lagged included); about twenty times that for
regression; a few MB of parquet; the passes shuffle kilobytes. Local timing is measured in the
plan's first spike; bank timing is unverified.

### The statistics
Every statistical calculation lives in `core_modelling/statistics/` and works on cells: a
statistic is a function of one feature's cells over a set of periods (the snapshot period, the
window pooled, one period, the lagged cells), computed by summing cells. This section owns the
definitions; Feature Checks uses the ones marked FC.

| Statistic | Definition |
|---|---|
| `missing_share` | null rows / rows |
| `zero_share` | rows equal to 0 / non-null rows (the `= 0` bin's rows: exact when 0 is its own bin) |
| `dominant_share`, `dominant_value` | the most common value's share, null counting as a value |
| `levels` | distinct non-null values on the snapshot rows, before the level cap (not from the cells) |
| `concordance` | Somers' D rescaled to [0.5, 1], direction taken out |
| `direction` | `+`, `-`, or none below 0.5 + 2 SE |
| `null_concordance` | the null indicator's concordance; missing share in [0.005, 0.995] |
| `concordance_best_order` | bins merged to ten, ordered by shrunk rate, then the concordance; not computed for categoricals (equal to the plain value by definition) |
| `non_monotone` | best-order ≥ plain + max(0.03, 4 · SE) |

- **Concordance** (`concordance_from_table(table, sign=None)` on `two_way_table(cells,
  order=None)`: bins in `bin_order`, or a categorical's levels in the order given, × target bins
  ordered by their mean target `sum_y / n`, null excluded; `pool_periods(cells, periods,
  lagged=False)` sums the periods first). D = (concordant − discordant) / pairs in different
  target bins; concordance = (1 + |D|) / 2, direction = sign of D
  (`direction_from_table(table, se)`); with `sign` (the window's direction) a per-period or
  lagged value is read in that direction, `(1 + sign · D) / 2`, so a flip reads below 0.5. For a
  0/1 target this is exactly the AUC of the binned feature (pairs inside one bin count half); for
  a binned regression target the pairs tied on the target bin are left out (exact on the binned
  rows, about 0.01 from the raw rows' value against the 20 target bins, T32); with `eda.bins:
  null` and a regression target `concordance_exact(cells)` expands the cells and computes Somers'
  D from Kendall's τ-b and the tie counts (`scipy.stats.kendalltau`, Q427), equal to the table's
  value without the dense table.
- **The binning, stated honestly:** at 100 quantile bins a continuous feature's concordance is
  pulled towards 0.5 by at most 1% of its distance from 0.5 (a true 0.70 reads no lower than
  0.698), usually far less; it is exact for numerics with at most 100 distinct values, for
  categoricals and with `eda.bins: null`. The singleton bins hold real ties only.
- **Standard error:** `concordance_se(value, events, non_events)`, Hanley–McNeil in events
  (D-082): SE² = [A(1 − A) + (n₁ − 1)(A/(2 − A) − A²) + (n₀ − 1)(2A²/(1 + A) − A²)] / (n₁n₀).
  It is the sampling noise of the concordance; near 0.5 with far more non-events than events it
  is about 1/√(12 n₁): 0.013 at 500 events, 0.009 at 1,000. Regression: `kendall_null_se(units)`
  = √(2(2n + 5) / (9n(n − 1))), halved for the concordance scale (A29). The SE is floored at
  `SE_FLOOR = 0.005` (a concordance of 1 would otherwise get an infinite weight in Cochran's Q).
  A single period has one row per client, so its events are its rows; a window's are not: the
  same client is labelled in every period, mostly with the same label under overlapping target
  windows, so every window SE (the direction, the margin below, the null concordance) takes its
  support in effective clients: `concordance_se(value, *client_support(events, non_events,
  clients))` with `TASK_SPECS[task]["client_support"]`, the pooled counts scaled by the
  effective clients per labelled row (`clients` from `counts.window_clients`: Kish's `(Σ m)² /
  Σ m²` over the clients' row counts `m`, the clients themselves when each has as many rows;
  binary by class, regression by the window's one ratio, since a regression target need not
  take 0), never below one row's worth. One ratio per run errs both ways for a feature filled on
  a subset of clients: conservative when they are present in few periods, about 1.3× too small
  an SE when they are the ones present throughout while half the others come and go. On the
  rows' count a null numeric on a panel was marked `non_monotone` 12–18% of the time, on the
  clients' none (2026-11-04).
- **Level encoding** (`encode_levels(cells, k_rows)`, Micci-Barreca): a level's value is
  (sum_y + k × base) / (n + k), shrinkage in pseudo-events: `k_rows = strata.min_events /
  base_rate` (regression: `strata.min_events` rows), null excluded. Read on the rows it was fitted
  on, the order flatters noise: a null 20–50-level code reads 0.53–0.57 at about 190 events a
  period, above Training's floor, and 0.60 on a panel where the same clients keep their labels.
  Fitting it on the other periods does not help on a panel (0.57): they hold the same clients.
  So a categorical's concordance is **cross-fitted by client fold**
  (`cross_fitted_concordance(cells, periods, k_rows, read=None, lagged=False)`): the counts
  table gives a categorical's cells the client's fold (`ENCODING_FOLDS = 5`, a hash of
  `unit_id`), each fold's levels are ordered by the encoding fitted on the other folds' current
  cells over the window (a level unseen there scores their base), and Somers' D sums the pairs
  inside each fold only, read in the encoding's direction (sign +1), so no client informs its
  own order. The window's value reads every window period; the snapshot's and each period's
  value is `read=[that period]`; the lagged value `lagged=True`, against the same encoding. A
  null 50-level code then reads 0.50 on average, a predictive one loses under 0.01. Its spread
  under no signal is about 1.35–1.5× its SE even on effective clients (SD 0.020 against 0.013 on
  a panel with about 500 event clients), because each fold's order is fitted partly on the other
  folds' noise, which the SE (noise for a fixed order) leaves out: a null code cleared 0.5 + 2
  SE, the line below which `direction` reads none, in about 12% of runs instead of 2% (measured
  2026-11-04; 1.3–1.4× on independent rows). So a cross-fitted value's SE is the task's SE on
  the same support times `CROSS_FIT_SE_INFLATION = 1.5`, the measured upper end (the SDS,
  2026-11-04). A fixed factor is an approximation; a permutation null per feature is on the
  Phase 3 wishlist. The best-order value is not computed for a categorical: in its encoding order it
  equals the plain value by definition.
- **Best-order concordance** (`best_order_concordance(cells, k_rows)`): the non-null bins merged
  into ten groups by `merge_bins` (a mass point its own group), ordered by their shrunk target
  mean, then the concordance: what a ten-leaf tree on the feature would reach, so an inverted U
  ranks where its information puts it. The merge to ten keeps the in-sample gain of ordering by
  the data small, but a null control still gains about 2 SE on average (0.014 at 2,000 events,
  0.028 at 500), so a fixed margin marks many of them at small sizes (0.03 marked 24 of 50 null
  numerics at 500 events). The margin scales with the SE: `is_non_monotone(plain, best_order,
  se)` and `ranking_value(plain, best_order, se)` mark a feature when best-order ≥ plain +
  max(`NON_MONOTONE_MARGIN` = 0.03, `NON_MONOTONE_SE_MULTIPLE` = 4 × SE), `se` the feature's
  window SE on effective clients (above); that marks 0–2% of null numerics at every size, on a
  panel too, and every inverted U of the tests. The margin is 4·SE at under about 1,500 event
  clients (0.052 at 500) and 0.03 above. More groups would not help: the noise gain grows with
  the groups the data may reorder (at 100 bins it is the in-sample encoding's problem). Not
  computed for a categorical.
- **Twins:** `concordance_window`, `missing_share_window`, `null_concordance_window`,
  `zero_share_window`, `dominant_share_window` are the same functions on the window periods' cells.
- **Per-period and heterogeneity (FC):** per-period concordances only for periods whose support
  reaches `strata.min_events`; `cochran_q(values, ses) -> p`, weights 1/SE², χ² with k − 1 degrees
  of freedom, none with fewer than two supported periods.
- **Distributions:** `quantile_edges(values, bins)` (the edges rule above), `merge_bins(cells,
  groups)` (one feature's cells, one row per `bin_order` summed over periods and target bins, merged
  in `bin_order` by cumulative row share into about `groups` groups; a bin whose share reaches
  `1 / groups` stays its own group, never widened into a neighbour, so an interior mass point adds
  a group; only `n` and `sum_y` are summed, any other numeric column is refused); `psi(
  expected_shares, actual_shares)` (FC) over ten bins merged from the cells plus the null bin
  (categoricals: the window's levels with `__other__`), each share floored at 1e-4 before the log, the
  0.10 / 0.25 bands as labels, not tests; `new_level_share(cells, window_levels, period)` (FC);
  `standardised_difference(a, b)`: Cohen's d on non-null values, (mean_a − mean_b) /
  √((sd_a² + sd_b²) / 2); for a categorical the largest level-share difference
  (`level_share_difference(a_cells, b_cells)`, null a level). `group_shares(cells, groups)` reads
  one period's shares over the groups `merge_bins` cut on another (by `bin_order` range, the null
  bin last), so the two PSI vectors align bin for bin. A chart that shows a distribution from the
  cells merges them to twenty groups by the same rule. `shares(cells)` gives `rows`,
  `missing_share`, `zero_share`, `dominant_share`, `dominant_value`, `bins` (the non-null bins
  holding rows; the ledger's `levels` come from the snapshot) and the concordance's support,
  `events` and `non_events` (labelled non-null rows; a zero target bin is the one whose target
  sums to 0). The `= 0` bin is found by the label `bin_labels` gives the 0 singleton, in both its
  number formats (`= 0`, and `= 0.0` when six digits read two edges alike). `pool_periods` keeps
  an unlabelled cell's `sum_y` null.
- **Intervals:** `wilson_interval(k, n)` (closed form, 95%, vectorised); `t_interval(mean, sd,
  n)`.
- **Association** (on the snapshot's eligible rows, a seeded cap of 50,000 rows for the pairwise
  matrix only, stated in the report): `spearman_matrix(frame)` (the exact pairwise-complete
  Spearman: columns grouped by null mask, ranked once inside a group and once per group pair
  across groups, T28; at least 500 shared rows else "not compared", NaN), `cramers_v(a, b)`
  (plain, null a level, "not compared" with one level, T29), `correlation_ratio(numeric,
  categorical)` (η on ranks over the numeric's filled rows, null a level);
  `association_table(frame, kinds, seed)` → long table `a, b, statistic, method (spearman |
  cramers_v | eta), rows` (a mixed pair has its numeric as `a`); `cluster_features(table,
  max_assoc)` (average linkage on 1 − |statistic|, a "not compared" pair at distance 1, members
  of clusters of two or more only) and `explained_by_others(table, members)` (FC): per member
  the R² on the other numeric members from their Spearman pairs alone, by least squares so an
  exact identity reads 1. NaN, "not available", for a member without a Spearman pair among the
  members ("mixed kinds": a categorical, or the one numeric of a mixed cluster) and for every
  member when a Spearman pair among them is not compared (NaN in the table), decided before
  solving; the caller names the reason from the pairs' methods. An R² beyond 1e-9 of [0, 1]
  (pairwise-complete correlations, each on its own rows, need not form a positive
  semi-definite matrix) is refused, not clipped.
- **Support rules:** `strata.min_events` for strata tables and every per-period statistic (events
  for binary, units with a non-zero target for regression); `MIN_BIN_SUPPORT = 20` for bins and
  levels in the deep dives.
- **Per-task spec entries:** `target_bins(known, exact)` (binary: none, the two values are the
  bins; regression: the edges of 20 quantile bins, every value with `eda.bins: null`, 0 always
  its own bin); `summarise_group(target, base)` on a group's known targets (binary: support =
  positive events, estimate = rate, Wilson interval, lift = rate / base rate; regression: support
  = units with a non-zero target, estimate = mean, t-interval, lift = mean / overall mean, median
  beside it, and the non-zero share with a Wilson interval and the mean and median of the
  non-zero values); `rare_effect(cell, rest)` (rate ratio / mean ratio; a positive cell over a
  zero rest is infinite; the regression mean ratio refuses a rest whose mean is not positive,
  so the caller decides "not available" before calling). The regression lift and
  `rare_effect` are mean ratios and are computed only when the overall mean is positive; for a
  signed or zero-mean amount they are "not available: mean not positive" (D-035), decided by the
  per-task spec before running (`lift_available(base)`; `summarise_group` leaves `lift` out then);
  `concordance_se(value, events, non_events)`; `events_warning(events)` and `support_name`
  (one support name per task, used by both);
  `base_rate_views(target)` (the headline: binary rows, positives, rate and Wilson interval;
  regression rows, mean, median, p10, p90, zero share, units with a non-zero target);
  `shrinkage_rows(min_events, base)` (the level encoding's `k_rows`).

### The views
Report order (A25 in the record; structure owned by [reporting](reporting.md)): summary → core →
extended → appendix. Snapshot views use the snapshot period's cells and rows; window views (the
funnel, the target per period) the whole window. Every chart is pre-aggregated; plotly.js is
embedded once.

**Summary**
- The choices block and the warnings (next section but one).
- **Headline:** the snapshot's eligible rows, clients, eligible share, positive events and base
  rate with its Wilson interval (regression: mean, median, p10, p90, zero share); the window's
  rows, positive rows, positive events and rows per event (at most `w`).

**Core**
- **Funnel per window period** (from `Frames.log`): spine rows → after each analysis filter →
  tagged per modelling filter → eligible; one column per step, plus `all`.
- **Target per period** (whole window): rows, positive rows, positive events, rate with Wilson
  interval, plus the pooled window; chart: the rate per period with error bars, events as bars on
  a second axis. Gap and latest periods carry no label and are not shown.
- **Target by stratum** (snapshot, per variable): the top `strata.max_levels` levels by rows, the
  rest `__other__`, `null` a level; rate, lift, interval, insufficient greyed; chart: rate by level
  with intervals, one colour per level across the report.
- **Ranking table**, one row per candidate: `concordance`, `concordance_se`, `direction`,
  `concordance_best_order`, `non_monotone`, `concordance_window`, `missing_share`,
  `missing_share_window`, `null_concordance`, `null_concordance_window`, `zero_share`,
  `zero_share_window`, `dominant_share`, `dominant_share_window`, `levels`, `kind`, `rank`,
  `key_feature` (`top_n | listed | ''`), `represented_by`. Ordered by the ranking value: the plain
  `concordance`, or `concordance_best_order` when the feature is marked `non_monotone`
  (best-order ≥ plain + max(0.03, 4 · SE)), so a noise feature never gains from the best-order's small
  in-sample optimism; M2.3's floor uses the same rule; ties by name; a bar on the concordance; lineage and
  unsupported columns listed underneath as excluded.
- **Key features:** walk the ranking (by the ranking value above); skip a candidate whose |association| with an already chosen
  key feature exceeds `eda.key_features.max_correlation` (0.9) and list it with `represented_by`;
  stop at `top_n`. The `include` features are chosen first, never skipped, and come on top of N. A
  pair "not compared" never skips.
- **Deep dive** per key feature (snapshot cells and rows):
  - lift vs base rate across ten groups merged from the cells (`merge_bins`; a mass point such
    as 0 stays its own bar), Wilson intervals as error bars,
    events as labels, the `null` bin last as its own bar, the y axis from the data; a numeric with
    at most `strata.max_levels` distinct values, or a categorical, gets a level table (rows,
    events, rate, lift, interval) and a bar chart of lift by level instead (the kind is kept);
  - the distribution by target class as box plots from quartiles, a log axis when the skew is
    above 2;
  - the per-period concordance line over the window, insufficient periods greyed;
  - regression: the mean per bin with its t-interval and the median, and the target's
    distribution per bin as box plots.

**Extended**
- **Reference groups**, per modelling tag, label-free: sizes per period tagged vs not with the
  share (from the funnel); composition per stratum side by side; per key feature the median, p10,
  p90 and non-null share on each side and the standardised mean difference, sorted by its absolute
  value, |SMD| ≥ 0.25 marked "differs" (a description, not a test).
- **Strata pivots** for the top five key features × each stratum variable: rate and lift by
  feature bin (ten) × stratum level, coloured by lift, cells below `strata.min_events` greyed.
- **Correlation overview:** the association matrix of the candidates with its method per pair;
  the redundancy reading (clusters with concordance and `explained_by_others`) is Feature Checks'.

**Appendix:** the kinds table with the overrides; the ledger; the resolved config with the origin
of every entry-written field; the collect log; timings; the how-to-read notes, whose wording
(the concordance in two sentences, here and in notebook 02's guide cell) is owned by
[reporting](reporting.md) requirement 8.

**Kinds** (decided in the dataset from the Spark schema, frames' meta): `numeric` (any numeric
type, decimals included), `categorical` (string, boolean), `unsupported` (date, timestamp, array,
map, struct, binary: excluded automatically like lineage, listed in the report, ledger column
`unsupported`). `features.kinds` overrides named candidates. The kinds summary is printed and
shown in the choices block.

**`pivot_target(result, rows, columns=None, where=None)`:** over `result.frame` with the task and
`strata.*` read from `result.config`; the group summary (rate or mean, lift,
counts, interval) by the `rows` dimensions, optionally against `columns`, after a
`DataFrame.query` filter (bank-style names need backticks); a numeric dimension is cut into ten
quantile bins, a categorical capped at `strata.max_levels`; styled by lift, insufficient cells
greyed. It works on the stage result's frame.

### Nulls
The rules EDA owns (the null-value register in the record, N-numbers):
1. The framework never fills a null; every statistic treats null as a state of its own (N1).
2. A Spark null and a float NaN are the same null bin; ±infinity is a value (N2).
3. The empty and whitespace-only strings are levels, shown as `''`; nothing is trimmed (N3).
4. Shares are over all eligible rows; `dominant_share` counts null as a value (N4).
5. Null is its own bin for every feature, so PSI includes it (N5).
6. Every concordance uses the non-null rows, its support counts those rows only; the nulls'
   information is `null_concordance` (N6).
7. The level encoding is fitted without the null level; the null bin takes no place in the best
   order (N7).
8. Null is a level for Cramér's V and η; Spearman is pairwise-complete with at least 500 shared
   rows, else "not compared" (N8).
9. Standardised mean differences use non-null values, the null share beside them (N9).
10. Kinds detection counts distinct values without null and never reads the pandas dtype (N13).
11. Bin edges come from the non-null snapshot values; the null bin is never merged (N14).
12. `nulls_may_be_zeros` reads `missing_share` over all rows and `zero_share` over non-null rows;
    `nulls_informative` and `missingness_leak` read `null_concordance` (N15; thresholds in
    [feature checks](feature_checks.md)).
13. Every per-feature table shows `missing_share` beside the statistic; a chart shows `null` as
    its own bar; a level table lists `null` (N16).
14. With `eda.bins: null` the null bin stays its own cell and the concordance still excludes it
    (N19).

### The choices block and the warnings
**Choices** (one `CHOICES` table: label, value, alternatives, when to move; D-032): automation
level; task, decision and derived metric; the period, the observation window, `w`, the validation
period (shown, never used); the eligibility steps with kind and reason; the candidate count and
patterns; the kinds summary and overrides; the snapshot period; `eda.bins`; the key-feature rule
(`top_n`, `max_correlation`, `include`); the strata variables; the pairwise cap; `replayed_to`
and the hashes.

**Warnings**, numbered, each a rule:
1. Events: fewer than 500 positive events in the snapshot (regression: units with a non-zero
   target); the concordance's third decimal is noise. The only events warning.
2. A window period below `strata.min_events`: its per-period statistics are insufficient.
3. A stratum level below `strata.min_events`.
4. The contract's null callout: a share of target windows held a null.
5. The snapshot collect above the budget (D-133).
6. All-client EDA (D-030): feature decisions taken from this report have seen test clients'
   labels.

### Code map
Planned layout; the build plan fixes the final names.
- `eda/run.py`: `run_eda(cfg, entity, env, spark) -> StageResult`: resolve, check strata, frames,
  counts, statistics, views, ledger, artifacts, report.
- `eda/population.py`: the headline, funnel, target per period, target by stratum and reference
  groups, from `Frames.log`, the population counts and the snapshot.
- `eda/ranking.py`: the ranking table from the cells; `choose_key_features(ranking, association,
  top_n, include, max_correlation)`.
- `eda/deep_dives.py`: one deep dive per key feature; the strata pivots; `pivot_target`.
- Imported: `dataset/frames.py` (`build_frames`), `dataset/counts.py` (edges and levels, the two
  passes, the population counts), `statistics/` (`cells.py`, `concordance.py`,
  `distributions.py`, `intervals.py`, `association.py`), `tasks.py`, `reporting/` (`html.py`,
  `charts.py`, `blocks.py`, `theme.py`), `artifacts.py`, `ledger.py`.

Call flow: Level 2's numbered list. Reading order for review: `statistics/concordance.py` →
`statistics/cells.py` → `dataset/counts.py` → `eda/ranking.py` → `eda/run.py` →
`eda/deep_dives.py` → `eda/population.py`.

### Interface
- **Public:** `run_eda(cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark:
  SparkSession) -> StageResult` (resolves the config itself); `pivot_target(result: StageResult,
  rows: str | list[str], columns: str | None = None, where: str | None = None) -> Styler`;
  `StageResult` (D-137).
- **CLI:** `python -m core_modelling run <config> [<config> …] --stages eda feature_checks`.
- **`StageResult(tables, ledger, log, meta, paths, views, frame, config)`:** `views` the Stylers
  and figures the report embeds; `frame` the collected snapshot; `config` the resolved config.
- **Config** (fields owned by [config](config.md); every field loggable at stage `eda`, outside
  the data-definition hash):

| Field | Default | Meaning |
|---|---|---|
| `eda.snapshot` | `last` | the window's last period, or a window period date |
| `eda.bins` | `100` | quantile bins per numeric; `null` = every value a bin (exact) |
| `eda.key_features.top_n` | `10` | key features from the ranking, both levels |
| `eda.key_features.include` | `[]` | candidates always deep-dived, on top of N |
| `eda.key_features.max_correlation` | `0.9` | the skip threshold on \|association\| |
| `features.kinds` | `{}` | `{column: numeric \| categorical}` overrides |

  EDA also reads `strata.variables`, `strata.max_levels` and `strata.min_events`.
- **Artifacts** under `<use_case>/04_feature/<ddh>/eda/` (`environment.feature_dir(env, cfg,
  entity, "eda")`, D-136), written by `artifacts.write_stage` to a temporary folder renamed on
  success (leftover `.tmp-*` / `.old-*` siblings from a crash make it fail loud). The ledger is
  saved first (`save_ledger(ledger, folder, {"stage": "eda", "data_definition_hash": ddh,
  "settings_digest": …})`) and the stage folder last, so `eda.json` is the commit marker:
  - `eda.json` (`schema_version: 1`, `stage`, `tables`): framework version, when, the hashes,
    `replayed_to`, the settings digest and the digested values (`artifacts.settings_meta(resolved,
    ["features.kinds", "strata", "eda"])`), the snapshot period, the compared periods, the
    population counts per period, the key features and why, the warnings, timings; `log.json`
    beside it holds the run's log entries;
  - `tables/*.parquet`: `cells`, `client_constant`, `population`, `ranking`, `correlation`,
    `bins`, `levels`, `quartiles`, `strata`, `reference_groups` (the clusters are Feature Checks',
    cut at its `redundancy.correlation_max`);
  - `resolved_config.yml`, `report.html`;
  - beside it, `ledger.parquet` + `_ledger.json`, created by EDA ([feature
    ledger](feature_ledger.md)).

### Lessons from the crunch
- Charts that showed nothing at low prevalence (T16): lift, intervals, axes from the data.
- Mutual information was useless at 0.04–0.2% prevalence and took 30–40 min
  ([lessons](../context/lessons.md), statistical lessons): not built; concordance instead.
- The 30–40 min runtime: Spark aggregates and one collected period; timings recorded.
- Notebooks copied per product: one config-driven notebook, shipped in the wheel (M2.4).
- EDA was run last because it gave no insight: the content is fixed, not the order.
- Sampling the analysis population would have made the statistics approximate (T24).

## Open questions
- **Unverified:** the bank-side timing of the two Spark passes (CPU in proportion to rows ×
  features); measure at the December pre-release.
- Whether the per-feature pandas work (quartiles, strata pivots, reference groups) at 300 features
  × a 5M-row snapshot needs a cap beyond the 50,000-row pairwise cap: measure in the bank.
- The theme file from `conf/local/` (M4).
