"""EDA's counts table, the Spark side (D-135).

Two passes over `Frames.rows` (the eligible rows of the compared periods, the label kept in the
window only) leave Spark as result tables, never as rows. Pass 1 (`count_cells`) counts every
feature's rows, target sum (`sum_y`) and target sum of squares (`sum_y2`, for a regression
mean's interval) per period, bin and target bin; pass 2 (`count_lagged_cells`) the
same for each feature's value one period back, against the current period's target. A numeric is
bucketed by one `Bucketizer` on the edges `bin_edges` takes from the collected snapshot's
eligible rows (`statistics.distributions.quantile_edges`, T25), a categorical mapped to the
window's levels (`window_levels`: the `LEVEL_CAP` most frequent kept, the rest `OTHER`, a level
unseen in the window `NEW`; past `POOLED_LEVEL_CAP` window levels every level not kept is
`OTHER`), null and a float NaN always the null bin (N2, N5). A categorical's window cells also
carry the client's `fold` (`ENCODING_FOLDS` folds by a hash of `unit_id`), so its level
encoding can be fitted on other clients than the ones it orders
(`concordance.cross_fitted_concordance`): the same client sits in every period, so leaving a
period out leaves the client in (V16). Then one
`explode(array(struct(...)))` and one `groupBy`, whose partial aggregation collapses the exploded
rows inside each partition, so the shuffle carries cells, not rows (the plan's spike: 15–18 s
and a 3 MB shuffle over the six-month canonical window; a per-feature loop was 4.5× slower, so
there is no fallback).
`client_constant_shares`, `population_counts` and `window_clients` are the other tables,
`compared_periods` picks the periods the passes compare and `estimate_cells` guards `eda.bins:
null`. Spark SQL and JVM transformers only, no pandas UDF: nothing Python-side runs on the
bank's executors. What the statistics read from the cells is `docs/components/eda.md`'s.
"""

from datetime import date

import numpy as np
import pandas as pd
from pyspark.ml.feature import Bucketizer
from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, FloatType

from core_modelling.config import UseCaseConfig
from core_modelling.periods import Period, period_spec
from core_modelling.statistics.distributions import bin_labels, quantile_edges

LEVEL_CAP = 50  # categorical levels kept per feature, by window frequency; the rest pooled
POOLED_LEVEL_CAP = 10_000  # window levels listed per feature; past it, every level not kept pools
MAX_CELLS = 50_000_000  # `eda.bins: null` is refused above this estimate (V3)
OTHER = "__other__"  # a window level beyond the cap
NEW = "__new__"  # a level unseen in the window
NULL_BIN = "null"  # a Spark null or a NaN (N2)
RESERVED_BINS = (NULL_BIN, OTHER, NEW)  # a real level of these names is quoted: `'null'`
# … and so is a blank one, `''` or `' '` (N3: never trimmed); Java's `\s`, ASCII only
BLANK_LEVEL = r"^[ \t\n\x0B\f\r]*$"
CONSTANT_CHUNK = 50  # columns per client-constant job: one job over 139 filled the 2 GB heap
ENCODING_FOLDS = 5  # client folds on a categorical's cells, for the cross-fitted encoding (V16)
CELL_COLUMNS = ["feature", "period", "lagged", "fold", "bin", "bin_order", "is_null",
                "target_bin", "n", "sum_y", "sum_y2"]  # fmt: skip


def compared_periods(cfg: UseCaseConfig, available: list[date]) -> dict[str, list[date]]:
    """The periods EDA compares, by group, from the periods the panel holds: `window` (inside
    the observation window), `gap` (after it and before the validation period; none without
    one) and `latest` (the latest period after the validation period, or after the window when
    there is none; at most one); the validation period itself never appears. A window period
    the panel lacks is simply absent (T19: the caller notes it)."""
    spec, window = period_spec(cfg), cfg.time.observation_window
    index = {period: spec.index(period) for period in sorted(available)}
    first, last = spec.index(window.first), spec.index(window.last)
    v = cfg.time.validation_period
    bound = last if v is None else spec.index(v)
    after = [period for period, i in index.items() if i > bound]
    return {
        "window": [period for period, i in index.items() if first <= i <= last],
        "gap": [period for period, i in index.items() if last < i < bound],
        "latest": after[-1:],
    }


def bin_edges(
    snapshot: pd.DataFrame, kinds: dict[str, str], bins: int | None
) -> dict[str, np.ndarray | None]:
    """Per numeric candidate, the interior edges the `Bucketizer` splits on, from the non-null
    values of the snapshot's ELIGIBLE rows (`eligible == 1`: the cells count eligible rows, so
    the mass points and the `2 / bins` guarantee are cut on them) through `quantile_edges`
    (`bins` None: every distinct value its own bin), with 0 its own singleton bin whenever it
    occurs, since the zero share is read from the `= 0` cell (`quantile_edges` makes it one
    above `1 / bins` only); None for a column without a non-null eligible value (every row in
    the null bin)."""
    eligible = snapshot[snapshot["eligible"] == 1]
    zero = np.array([0.0, np.nextafter(0.0, np.inf)])
    edges = {}
    for name, kind in kinds.items():
        if kind != "numeric":
            continue
        values = eligible[name].dropna().to_numpy(dtype=float)
        if values.size == 0:
            edges[name] = None
            continue
        cut = quantile_edges(values, np.unique(values).size if bins is None else bins)
        edges[name] = np.unique(np.concatenate([cut, zero])) if (values == 0).any() else cut
    return edges


def window_levels(
    rows: DataFrame, categoricals: list[str], window_periods: list[date]
) -> tuple[dict[str, list[str]], list[str]]:
    """Per categorical, the non-null levels seen in any window period as their bin labels
    (`_level`: strings, a real level named like a reserved bin quoted), the most frequent first:
    the first `LEVEL_CAP` are kept and the passes pool the rest as `OTHER`; null is always its
    own bin and takes no place here. Second, the categoricals with more than `POOLED_LEVEL_CAP`
    window levels: each lists its kept levels only, and the passes count every other level of it
    as `OTHER`, never `NEW`, since seen and unseen can't be told apart without the full list.
    One exploded pass, ranked in Spark, so at most `POOLED_LEVEL_CAP` levels per feature leave
    it."""
    _require_window(window_periods)
    levels: dict[str, list[str]] = {name: [] for name in categoricals}
    if not categoricals:
        return levels, []
    pairs = [
        F.struct(F.lit(name).alias("feature"), _level(rows, name).alias("level"))
        for name in categoricals
    ]
    counted = (
        rows.where(F.col("period").isin(window_periods))
        .select(F.explode(F.array(*pairs)).alias("pair"))
        .where(F.col("pair.level").isNotNull())
        .groupBy(F.col("pair.feature").alias("feature"), F.col("pair.level").alias("level"))
        .count()
    )
    by_count = Window.partitionBy("feature").orderBy(F.desc("count"), "level")
    ranked = counted.select(
        "feature",
        "level",
        F.row_number().over(by_count).alias("rank"),
        F.count(F.lit(1)).over(Window.partitionBy("feature")).alias("levels"),
    )
    listed = ranked.where((F.col("rank") <= LEVEL_CAP) | (F.col("levels") <= POOLED_LEVEL_CAP))
    collected = listed.orderBy("feature", "rank").collect()
    for row in collected:
        levels[row.feature].append(row.level)
    over = {row.feature for row in collected if row.levels > POOLED_LEVEL_CAP}
    return levels, [name for name in categoricals if name in over]


def count_cells(
    rows: DataFrame,
    edges: dict[str, np.ndarray | None],
    levels: dict[str, list[str]],
    over_ceiling: list[str],
    target_edges: np.ndarray | None,
    window_periods: list[date],
    spec: Period,
) -> pd.DataFrame:
    """Pass 1: the counts table of `rows` (`CELL_COLUMNS`, `lagged` false, `fold` null for a
    numeric), every numeric of `edges` bucketed by one `Bucketizer`, every categorical of
    `levels` mapped to its level (`over_ceiling`: `window_levels`' second list), the target to
    its value (`target_edges` None, a binary target) or its bucket's label, read for the window
    periods only; `period` as its label."""
    _require_window(window_periods)
    return _aggregate_cells(
        rows, edges, levels, over_ceiling, target_edges, window_periods, spec, lagged=False
    )


def count_lagged_cells(
    rows: DataFrame,
    edges: dict[str, np.ndarray | None],
    levels: dict[str, list[str]],
    over_ceiling: list[str],
    target_edges: np.ndarray | None,
    window_periods: list[date],
    spec: Period,
) -> pd.DataFrame:
    """Pass 2: each feature's value one period back by period index (the client's previous row
    in `rows`, the eligible rows, counts only when its index is the current one minus one, else
    the value is null), binned on the same edges and levels and counted against the current
    period's target as `lagged` cells of the window periods; the window's first period has no
    previous row in `rows`, so its lagged cells are null (N11)."""
    _require_window(window_periods)
    index = spec.spark_index(F.col("period"))
    by_client = Window.partitionBy("unit_id").orderBy(index)
    adjacent = F.lag(index).over(by_client) == index - 1
    previous = [
        F.when(adjacent, F.lag(F.col(name)).over(by_client)).alias(name)
        for name in (*edges, *levels)
    ]
    window = rows.where(F.col("period").isin(window_periods))
    lagged = window.select("unit_id", "period", "target", *previous)
    return _aggregate_cells(
        lagged, edges, levels, over_ceiling, target_edges, window_periods, spec, lagged=True
    )


def _require_window(window_periods: list[date]) -> None:
    """Fail loud on an empty `window_periods`: the levels and the labels come from the window."""
    if not window_periods:
        raise ValueError(
            "window_periods is empty: the counts passes read the levels and the labels from the "
            "observation window's periods (compared_periods(...)['window'])"
        )


def _aggregate_cells(
    frame: DataFrame,
    edges: dict[str, np.ndarray | None],
    levels: dict[str, list[str]],
    over_ceiling: list[str],
    target_edges: np.ndarray | None,
    window_periods: list[date],
    spec: Period,
    lagged: bool,
) -> pd.DataFrame:
    """One pass: the label kept for the window periods only (§4.4), the numerics and a binned
    target bucketed together, every feature's cell exploded, one `groupBy` right after it (so
    the partial aggregation collapses the rows), the labels joined in pandas; a binary target's
    bins checked."""
    if not edges and not levels:
        raise ValueError("nothing to count: `edges` and `levels` name no feature")
    label = F.when(F.col("period").isin(window_periods), F.col("target"))
    frame = frame.withColumn("target", label)
    splits = {name: e for name, e in edges.items() if e is not None and e.size}
    if target_edges is not None:
        splits["target"] = target_edges
    bucketed = _bucketize(frame, splits)
    cells = [_numeric_cell(name, e) for name, e in edges.items()]
    fold = F.when(  # only the window's cells: the encoding is fitted and read there
        F.col("period").isin(window_periods),
        F.pmod(F.xxhash64(F.col("unit_id")), F.lit(ENCODING_FOLDS)),
    )
    cells += [
        _categorical_cell(frame, name, levels[name], name in over_ceiling, fold) for name in levels
    ]
    aggregated = (
        bucketed.select(
            "period",
            "target",
            _target_bin(target_edges).alias("target_bin"),
            F.explode(F.array(*cells)).alias("cell"),
        )
        .groupBy(
            "cell.feature",
            "period",
            "cell.fold",
            "cell.bin",
            "cell.bin_order",
            "cell.is_null",
            "target_bin",
        )
        .agg(
            F.count(F.lit(1)).alias("n"),
            F.sum(F.col("target").cast("double")).alias("sum_y"),
            F.sum(F.col("target").cast("double") * F.col("target").cast("double")).alias("sum_y2"),
        )
        .toPandas()
    )
    if target_edges is None:
        _check_binary_bins(aggregated)
    return _label_cells(aggregated, edges, spec, lagged)


def _bucketize(frame: DataFrame, splits: dict[str, np.ndarray]) -> DataFrame:
    """`frame` with `<name>__bucket` per column of `splits` (its interior edges) from one
    `Bucketizer` with `handleInvalid="keep"`: bucket `i` is `[e_i, e_{i+1})` over `[-inf, *edges,
    inf]`, a NaN lands in the extra bucket `len(edges) + 1` and a null gives a null bucket
    (measured on 3.4.3). The values are normalised with `+ 0.0` first: Java orders `-0.0` below
    `0.0`, so it would miss the `= 0` singleton (measured), and a decimal or integer becomes a
    double."""
    if not splits:
        return frame
    names = list(splits)
    values = [(F.col(name) + 0.0).alias(f"{name}__value") for name in names]
    bucketizer = Bucketizer(
        splitsArray=[[-np.inf, *map(float, splits[name]), np.inf] for name in names],
        inputCols=[f"{name}__value" for name in names],
        outputCols=[f"{name}__bucket" for name in names],
        handleInvalid="keep",
    )
    bucketed = bucketizer.transform(frame.select("*", *values))
    return bucketed.drop(*[f"{name}__value" for name in names])


def _numeric_cell(name: str, edges: np.ndarray | None) -> Column:
    """A numeric's cell: the bucket index as `bin_order` (its label joins in pandas), the null
    bin (a null or a NaN) with `is_null` and the last order; without edges (no non-null value in
    the snapshot) one `all` bin for every value and the null bin."""
    if edges is None or edges.size == 0:
        value = F.col(name) + 0.0
        is_null = value.isNull() | F.isnan(value)
        return _cell(name, F.lit(None), F.when(is_null, 1).otherwise(0), is_null, F.lit(None))
    bucket = F.col(f"{name}__bucket")
    null_order = edges.size + 1  # the extra bucket; a null bucket joins it
    is_null = bucket.isNull() | (bucket == null_order)
    order = F.when(is_null, null_order).otherwise(bucket)
    return _cell(name, F.lit(None), order, is_null, F.lit(None))


def _categorical_cell(
    frame: DataFrame, name: str, levels: list[str], over_ceiling: bool, fold: Column
) -> Column:
    """A categorical's cell: a kept level is its own bin at its window frequency rank, a pooled
    level `OTHER` after the kept ones, a level unseen in the window `NEW` after that (over the
    level ceiling, every level not kept is `OTHER`), null (a NaN too) the null bin last; `fold`
    the client's, `pmod(xxhash64(unit_id), ENCODING_FOLDS)` in the window (the same in every
    run), null elsewhere."""
    level = _level(frame, name)
    kept, pooled = levels[:LEVEL_CAP], levels[LEVEL_CAP:]
    lookup = [F.lit(x) for rank, kept_level in enumerate(kept) for x in (kept_level, rank)]
    kept_rank = F.create_map(*lookup)[level] if kept else F.lit(None).cast("int")
    if over_ceiling:  # seen and unseen can't be told apart without the full list
        is_pooled = F.lit(True)
    else:
        is_pooled = level.isin(pooled) if pooled else F.lit(False)
    n = len(kept)
    bin_label = (
        F.when(level.isNull(), NULL_BIN).when(kept_rank.isNotNull(), level)
        .when(is_pooled, OTHER).otherwise(NEW)
    )  # fmt: skip
    order = (
        F.when(level.isNull(), n + 2).when(kept_rank.isNotNull(), kept_rank)
        .when(is_pooled, n).otherwise(n + 1)
    )  # fmt: skip
    return _cell(name, bin_label, order, level.isNull(), fold)


def _level(frame: DataFrame, name: str) -> Column:
    """A categorical's value as its bin label: a string, a float NaN null (N2), and a real level
    named like a reserved bin (`RESERVED_BINS`) or blank (`BLANK_LEVEL`) quoted (`'null'`, `''`),
    so every label is distinct and visible."""
    value = _nan_as_null(frame, name).cast("string")
    quoted = F.concat(F.lit("'"), value, F.lit("'"))
    return F.when(value.isin(*RESERVED_BINS) | value.rlike(BLANK_LEVEL), quoted).otherwise(value)


def _nan_as_null(frame: DataFrame, name: str) -> Column:
    """The column with a float NaN as null (N2); any other type as it is: NaN exists for floats
    only, and Spark's NaN functions cast a string to a double first (`isnan('NaN')` is true,
    measured on 3.4.3)."""
    column = F.col(name)
    if isinstance(frame.schema[name].dataType, FloatType | DoubleType):
        return F.nanvl(column, F.lit(None))
    return column


def _cell(name: str, bin_label: Column, bin_order: Column, is_null: Column, fold: Column) -> Column:
    """The struct the pass explodes: `feature`, `fold` (int; null for a numeric and outside
    the window), `bin` (a
    string, null for a numeric until the labels join), `bin_order` (int), `is_null`."""
    return F.struct(
        F.lit(name).alias("feature"),
        fold.cast("int").alias("fold"),
        bin_label.cast("string").alias("bin"),
        bin_order.cast("int").alias("bin_order"),
        is_null.alias("is_null"),
    )


def _target_bin(target_edges: np.ndarray | None) -> Column:
    """The target's bin as a string: for a binary target (no `target_edges`) `"0"` or `"1"` (a 0
    or 1 read as an int first, so a double flag never reads `"1.0"`; any other value as it is,
    which the pass refuses), else the label of its bucket on them; null where the label is."""
    target = F.col("target")
    if target_edges is None:
        flag = target.cast("int").cast("string")
        return F.when(target.isin(0, 1), flag).otherwise(target.cast("string"))
    labels = F.array(*[F.lit(label) for label in bin_labels(target_edges)])
    return labels[F.col("target__bucket").cast("int")]


def _check_binary_bins(cells: pd.DataFrame) -> None:
    """Fail loud when a binary target's bins hold anything but `"0"`, `"1"` and null."""
    odd = sorted(set(cells["target_bin"].dropna()) - {"0", "1"})
    if odd:
        raise ValueError(
            f"the binary target holds the values {odd}; a binary target is 0 or 1 (null where "
            "unknown): check data.target"
        )


def _label_cells(
    cells: pd.DataFrame, edges: dict[str, np.ndarray | None], spec: Period, lagged: bool
) -> pd.DataFrame:
    """The collected cells as the counts table: `period` as its label, `lagged`, a numeric's
    `bin` from `bin_labels` by its bucket index (`NULL_BIN` for the null bin), the columns in
    `CELL_COLUMNS` order, sorted."""
    cells["period"] = cells["period"].map(spec.label)
    cells["lagged"] = lagged
    cells["fold"] = cells["fold"].astype("Int64")  # null for a numeric and outside the window
    labels = {name: bin_labels(e if e is not None else np.array([])) for name, e in edges.items()}
    numeric = cells["feature"].isin(edges)
    if numeric.any():
        cells.loc[numeric, "bin"] = [
            NULL_BIN if is_null else labels[feature][order]
            for feature, order, is_null in cells.loc[
                numeric, ["feature", "bin_order", "is_null"]
            ].itertuples(index=False)
        ]
    ordered = cells.sort_values(
        ["feature", "period", "fold", "bin_order", "target_bin"], na_position="last"
    )
    return ordered[CELL_COLUMNS].reset_index(drop=True)


def client_constant_shares(
    rows: DataFrame, features: list[str], window_periods: list[date]
) -> pd.DataFrame:
    """Per feature, the share of clients whose value never changes over the window periods,
    among the clients with at least two non-null values (a float NaN counts as null, N2), with
    that client count: `feature, constant_share, clients`. A `groupBy(unit_id)` with min, max
    and count per column, in chunks of `CONSTANT_CHUNK` columns: one job over every column
    spills and fills the heap (the spike), so the cost grows as one job per 50 columns."""
    window = rows.where(F.col("period").isin(window_periods))
    records = []
    for start in range(0, len(features), CONSTANT_CHUNK):
        chunk = features[start : start + CONSTANT_CHUNK]
        values = {name: _nan_as_null(rows, name) for name in chunk}
        per_client = window.groupBy("unit_id").agg(
            *[F.min(values[name]).alias(f"{name}__min") for name in chunk],
            *[F.max(values[name]).alias(f"{name}__max") for name in chunk],
            *[F.count(values[name]).alias(f"{name}__n") for name in chunk],
        )
        shares = per_client.agg(*[agg for name in chunk for agg in _constant_aggregates(name)])
        row = shares.collect()[0]
        for name in chunk:
            share, clients = row[f"{name}__share"], row[f"{name}__clients"]
            records.append({"feature": name, "constant_share": share, "clients": clients})
    return pd.DataFrame(records, columns=["feature", "constant_share", "clients"])


def _constant_aggregates(name: str) -> list[Column]:
    """One feature's share of clients with an unchanged value and their count, over the
    per-client min, max and non-null count, among clients with at least two values."""
    two_values = F.col(f"{name}__n") >= 2
    constant = (F.col(f"{name}__min") == F.col(f"{name}__max")).cast("double")
    return [
        F.avg(F.when(two_values, constant)).alias(f"{name}__share"),
        F.count(F.when(two_values, True)).alias(f"{name}__clients"),
    ]


def population_counts(
    panel: DataFrame, cfg: UseCaseConfig, periods: dict[str, list[date]]
) -> pd.DataFrame:
    """The D-088 counts per compared period on the panel after the analysis filters, before any
    sample: `period` (its label), `rows`, `eligible_rows`, `known_target`, `positive_rows`,
    `positive_events` (units), `non_event_units`; the labelled counts for the window periods
    only, null elsewhere (N10: a row with a null target is in `eligible_rows` and out of
    `known_target`). Positive is a non-zero label, for a flag and an amount alike."""
    compared = [period for group in periods.values() for period in group]
    eligible = F.col("eligible") == 1
    label = F.when(eligible & F.col("period").isin(periods["window"]), F.col("target"))
    positive = label != 0
    unit = F.col("unit_id")
    # One row per unit and period (read_keyed_source refuses a repeated key; the unique_keys
    # contract), so within a period a count of rows is a count of distinct units.
    table = (
        panel.where(F.col("period").isin(compared))
        .groupBy("period")
        .agg(
            F.count(F.lit(1)).alias("rows"),
            F.count(F.when(eligible, True)).alias("eligible_rows"),
            F.count(label).alias("known_target"),
            F.count(F.when(positive, True)).alias("positive_rows"),
            F.count(F.when(positive, unit)).alias("positive_events"),
            F.count(F.when(label.isNotNull() & ~positive, unit)).alias("non_event_units"),
        )
        .orderBy("period")
        .toPandas()
    )
    labelled = ["known_target", "positive_rows", "positive_events", "non_event_units"]
    in_window = table["period"].isin(periods["window"])
    table[labelled] = table[labelled].where(in_window).astype("Int64")  # 3042, never 3042.0
    table["period"] = table["period"].map(period_spec(cfg).label)
    return table


def window_clients(rows: DataFrame, window_periods: list[date]) -> dict[str, float]:
    """The window's labelled rows and their effective number of clients, per class and in all:
    `event_rows` and `event_effective` (a non-zero target), `non_event_rows` and
    `non_event_effective` (a zero one), `rows` and `effective`; and `event_clients`, the distinct
    clients with an event (the pooled window's positive events). The same client is labelled in
    every period, mostly with the same label under overlapping target windows, so its rows are
    near copies: the effective number is Kish's `(Σ m)² / Σ m²` over the clients' row counts
    `m`, the clients themselves when each has as many rows. The window's standard errors rest on
    it (`TASK_SPECS[task]["client_support"]`)."""
    _require_window(window_periods)
    labelled = rows.where(F.col("period").isin(window_periods) & F.col("target").isNotNull())
    event = F.col("target") != 0
    per_client = labelled.groupBy("unit_id").agg(
        F.count(F.when(event, True)).alias("event"),
        F.count(F.when(~event, True)).alias("non_event"),
        F.count(F.lit(1)).alias("all"),
    )
    sums = per_client.agg(
        *[F.sum(name).alias(f"{name}_rows") for name in ("event", "non_event", "all")],
        *[
            F.sum(F.col(name) ** 2).alias(f"{name}_squares")
            for name in ("event", "non_event", "all")
        ],
        F.count(F.when(F.col("event") > 0, True)).alias("event_clients"),
    ).collect()[0]
    sizes = {}
    for name, prefix in (("event", "event_"), ("non_event", "non_event_"), ("all", "")):
        total = sums[f"{name}_rows"] or 0  # Spark sums no rows to null
        squares = sums[f"{name}_squares"] or 0
        sizes[f"{prefix}rows"] = float(total)
        sizes[f"{prefix}effective"] = total**2 / squares if squares else 0.0
    sizes["event_clients"] = float(sums["event_clients"])
    return sizes


def estimate_cells(rows: DataFrame, kinds: dict[str, str], window_periods: list[date]) -> int:
    """The counts table's cells over both passes with `eda.bins: null` (every distinct value a
    bin), estimated from `approx_count_distinct` per candidate and for the target over `rows`: a
    numeric's distinct values, a categorical's capped at `LEVEL_CAP` (plus `OTHER` and `NEW`),
    each plus the null bin, times the target's distinct values plus null, times the periods of
    pass 1 plus the window periods of pass 2, a categorical's window periods `ENCODING_FOLDS`
    times. Above `MAX_CELLS` it fails loud naming `eda.bins` (V3). With bins set the cells are
    bounded and EDA does not call it."""
    distinct = rows.agg(
        F.countDistinct("period").alias("__periods"),
        *[F.approx_count_distinct(name).alias(name) for name in (*kinds, "target")],
    ).collect()[0]
    numeric = sum(distinct[n] + 1 for n, kind in kinds.items() if kind == "numeric")
    categorical = sum(
        min(distinct[n], LEVEL_CAP) + 3 for n, kind in kinds.items() if kind != "numeric"
    )
    periods = distinct["__periods"] + len(window_periods)
    folded = periods + 2 * len(window_periods) * (ENCODING_FOLDS - 1)  # both passes' window
    estimate = int((numeric * periods + categorical * folded) * (distinct["target"] + 1))
    if estimate > MAX_CELLS:
        raise ValueError(
            f"eda.bins: null would give about {estimate:,} cells over both passes, above "
            f"{MAX_CELLS:,}; set eda.bins (100 by default) or run EDA on a smaller population"
        )
    return estimate
