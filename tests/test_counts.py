"""The counts passes on real local Spark (D-135): the cells against a pandas groupby on the
collected rows, the lagged cells against a shift by client, the client-constant shares, the
population counts against Target Factory's summary, the compared periods with and without a
validation period, the `eda.bins: null` guard over both passes and exactness, the edges rule
through the `Bucketizer` (T25) on the eligible rows, `-0.0`, null and NaN in the null bin, the
level pooling and its ceiling, reserved level names, the refusals and the kinds from the Spark
schema.

The unit preset gives the real frames once; the lag and client-constant semantics, the level
pooling and the Bucketizer corner cases run on hand-made frames, so each case is visible in the
test.
"""

from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd
import pytest
from pyspark.ml.feature import Bucketizer
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from core_modelling.config import UseCaseConfig
from core_modelling.dataset import Frames, build_frames, counts
from core_modelling.dataset.counts import (
    CELL_COLUMNS,
    LEVEL_CAP,
    NEW,
    NULL_BIN,
    OTHER,
    bin_edges,
    client_constant_shares,
    compared_periods,
    count_cells,
    count_lagged_cells,
    estimate_cells,
    population_counts,
    window_levels,
)
from core_modelling.dataset.frames import detect_kinds
from core_modelling.dataset.panel import build_panel
from core_modelling.environment import EnvironmentConfig
from core_modelling.periods import PERIODS
from core_modelling.statistics.distributions import bin_labels, quantile_edges
from core_modelling.target_factory import run_target_factory
from core_modelling.tasks import TASK_SPECS

ENTITY = "entity_a"
MONTH = PERIODS["month"]
FEATURES = ["age", "segment", "income"]  # a numeric, a categorical, a numeric with nulls
MONTHS = [MONTH.from_index(MONTH.index(date(2025, 1, 31)) + i) for i in range(4)]  # Jan … Apr
ROWS_SCHEMA = "unit_id string, period date, x double, target double"  # a double 0/1 flag


@pytest.fixture(scope="module")
def cfg(variant: Callable[..., UseCaseConfig]) -> UseCaseConfig:
    """The skeleton's config without a model input."""
    return variant(data={"model_input": None})


@pytest.fixture(scope="module")
def frames(spark: SparkSession, unit_env: EnvironmentConfig, cfg: UseCaseConfig) -> Frames:
    """EDA's frames on the unit preset, built once."""
    return build_frames(cfg, ENTITY, unit_env, spark, "eda")


@pytest.fixture(scope="module")
def window(cfg: UseCaseConfig) -> list[date]:
    """The window periods as dates."""
    first, last = cfg.time.observation_window.first, cfg.time.observation_window.last
    return [MONTH.from_index(i) for i in range(MONTH.index(first), MONTH.index(last) + 1)]


@pytest.fixture(scope="module")
def edges(frames: Frames, cfg: UseCaseConfig) -> dict[str, np.ndarray | None]:
    """The two numerics' edges at the config's bins, from the snapshot."""
    kinds = {name: frames.meta["kinds"][name] for name in FEATURES}
    return bin_edges(frames.snapshot, kinds, cfg.eda.bins)


@pytest.fixture(scope="module")
def levels(frames: Frames, window: list[date]) -> dict[str, list[str]]:
    """The categorical's window levels (far below the ceiling)."""
    levels, over_ceiling = window_levels(frames.rows, ["segment"], window)
    assert over_ceiling == []
    return levels


@pytest.fixture(scope="module")
def collected(frames: Frames) -> pd.DataFrame:
    """The three features' rows of every compared period, collected for the pandas oracle (the
    unit preset's eligible rows are small)."""
    return frames.rows.select("unit_id", "period", *FEATURES, "target").toPandas()


def _expected_cells(frame: pd.DataFrame, edges: dict, levels: dict, lagged: bool) -> pd.DataFrame:
    """The counts table by pandas: per feature the bin of every row (a numeric by `np.digitize`
    on the edges, the Bucketizer's buckets; a categorical by kept level, `OTHER`, `NEW`; null its
    own bin last), then a groupby with the target's value as the target bin."""
    target_bin = frame["target"].map(lambda t: None if pd.isna(t) else str(int(t)))
    parts = []
    for feature, feature_edges in edges.items():
        labels = bin_labels(feature_edges)
        values = frame[feature].to_numpy(dtype=float)
        is_null = frame[feature].isna().to_numpy()
        order = np.where(is_null, len(feature_edges) + 1, np.digitize(values, feature_edges))
        bins = [NULL_BIN if n else labels[o] for n, o in zip(is_null, order, strict=True)]
        parts.append(_cells_of(frame, feature, bins, order, is_null, target_bin))
    for feature, feature_levels in levels.items():
        kept, pooled = feature_levels[:LEVEL_CAP], feature_levels[LEVEL_CAP:]
        value = frame[feature]
        is_null, rank = value.isna(), value.map({level: i for i, level in enumerate(kept)})
        cases = [is_null, rank.notna(), value.isin(pooled)]
        bins = np.select(cases, [NULL_BIN, value, OTHER], NEW)
        order = np.select(cases, [len(kept) + 2, rank, len(kept)], len(kept) + 1)
        parts.append(_cells_of(frame, feature, bins, order, is_null.to_numpy(), target_bin))
    cells = pd.concat(parts)
    key = ["feature", "period", "bin", "bin_order", "is_null", "target_bin"]
    grouped = cells.groupby(key, dropna=False).agg(
        n=("target", "size"), sum_y=("target", lambda s: s.sum(min_count=1))
    )
    grouped = grouped.reset_index()
    grouped["period"] = grouped["period"].map(MONTH.label)
    grouped["lagged"] = lagged
    grouped["bin_order"] = grouped["bin_order"].astype(int)
    return grouped[CELL_COLUMNS]


def _cells_of(
    frame: pd.DataFrame,
    feature: str,
    bins: list | np.ndarray,
    order: np.ndarray,
    is_null: np.ndarray,
    target_bin: pd.Series,
) -> pd.DataFrame:
    """One feature's row-level cells."""
    return pd.DataFrame(
        {
            "feature": feature,
            "period": frame["period"].to_numpy(),
            "bin": bins,
            "bin_order": order,
            "is_null": is_null,
            "target_bin": target_bin.to_numpy(),
            "target": frame["target"].to_numpy(dtype=float),
        }
    )


def _same_cells(actual: pd.DataFrame, expected: pd.DataFrame) -> None:
    """Both tables equal, cell by cell, in one order (a null target bin as one text on both
    sides, since Spark gives None and the pandas groupby NaN)."""
    key = ["feature", "period", "bin", "target_bin"]
    tables = []
    for table in (actual, expected):
        table = table.assign(target_bin=table["target_bin"].fillna("<null>"))
        tables.append(table.sort_values(key).reset_index(drop=True)[CELL_COLUMNS])
    pd.testing.assert_frame_equal(tables[0], tables[1], check_dtype=False)


def test_cells_equal_a_pandas_groupby_on_the_collected_rows(
    frames: Frames, window: list[date], edges: dict, levels: dict, collected: pd.DataFrame
) -> None:
    """Pass 1 on three features (a numeric, a categorical, one with nulls) over the window's
    first and the latest period, `n` and `sum_y` alike, equals the pandas groupby on the same
    rows: the Bucketizer's buckets are `np.digitize`'s, the levels the window's, the null bin its
    own, the target bin null in the latest period."""
    periods = [window[0], collected["period"].max()]
    rows = frames.rows.select("unit_id", "period", *FEATURES, "target")
    cells = count_cells(
        rows.where(F.col("period").isin(periods)), edges, levels, [], None, window, MONTH
    )
    oracle = collected[collected["period"].isin(periods)]
    _same_cells(cells, _expected_cells(oracle, edges, levels, lagged=False))
    assert cells.columns.tolist() == CELL_COLUMNS and not cells["lagged"].any()
    assert cells["is_null"].dtype == bool and cells["lagged"].dtype == bool
    assert cells["period"].map(type).eq(str).all() and cells["sum_y"].dtype == float
    assert (cells.loc[cells["is_null"], "bin"] == NULL_BIN).all()
    assert cells.loc[cells["feature"] == "income", "is_null"].any()
    latest = cells[cells["period"] == MONTH.label(periods[1])]
    assert latest["target_bin"].isna().all() and latest["sum_y"].isna().all()
    first = cells[cells["period"] == MONTH.label(window[0])]
    assert {"0", "1"} <= set(first["target_bin"])  # plus null: leavers inside the window (N10)


def test_lagged_cells_equal_a_shift_by_client(
    frames: Frames, window: list[date], edges: dict, levels: dict, collected: pd.DataFrame
) -> None:
    """Pass 2 equals the pandas shift by client on the same rows: the previous row's value where
    its period index is the current one minus one, binned alike and counted against the current
    period's target in the window periods; the window's first period has only null lagged cells."""
    rows = frames.rows.select("unit_id", "period", *FEATURES, "target")
    cells = count_lagged_cells(rows, edges, levels, [], None, window, MONTH)
    ordered = collected.sort_values(["unit_id", "period"]).reset_index(drop=True)
    index = ordered["period"].map(MONTH.index)
    adjacent = ordered["unit_id"].eq(ordered["unit_id"].shift()) & index.eq(index.shift() + 1)
    shifted = ordered[FEATURES].shift().where(adjacent)
    oracle = pd.concat([ordered[["unit_id", "period", "target"]], shifted], axis=1)
    _same_cells(cells, _expected_cells(oracle[oracle["period"].isin(window)], edges, levels, True))
    assert cells["lagged"].all()
    assert cells.loc[cells["period"] == MONTH.label(window[0]), "is_null"].all()
    assert not cells.loc[cells["period"] == MONTH.label(window[1]), "is_null"].all()


def test_lag_by_period_index_and_client_constant_shares(spark: SparkSession) -> None:
    """On a hand-made frame: the window's first period has null lagged cells; a client missing
    the previous period gets a null lagged value, not the one two periods back; a static column's
    constant share is 1 (a NaN counts as null, N2, so it changes nothing) and a changing one's
    below 1, among clients with two or more values."""
    m0, m1, m2 = MONTHS[:3]
    rows = [
        ("u1", m0, 1.0, 5.0, 0), ("u1", m1, 2.0, float("nan"), 1), ("u1", m2, 3.0, 5.0, 0),
        ("u2", m0, 1.0, 7.0, 0), ("u2", m2, 3.0, 7.0, 1),  # m1 missing
        ("u3", m0, 5.0, 9.0, 0), ("u3", m1, 5.0, 9.0, 0), ("u3", m2, 5.0, 9.0, 0),
        ("u4", m1, 8.0, 1.0, 1),  # one row: fewer than two values
    ]  # fmt: skip
    frame = spark.createDataFrame(
        rows, "unit_id string, period date, x double, y double, target int"
    )
    edges = {"x": quantile_edges(np.array([1.0, 2.0, 3.0, 5.0, 8.0]), 10)}  # every value a bin
    lagged = count_lagged_cells(frame, edges, {}, [], None, MONTHS[:3], MONTH)
    by_bin = lagged.groupby(["period", "bin"])["n"].sum()
    assert by_bin[MONTH.label(m0)].to_dict() == {NULL_BIN: 3}
    assert by_bin[MONTH.label(m1)].to_dict() == {"= 1": 1, "= 5": 1, NULL_BIN: 1}
    assert by_bin[MONTH.label(m2)].to_dict() == {"= 2": 1, "= 5": 1, NULL_BIN: 1}
    constant = client_constant_shares(frame, ["x", "y"], MONTHS[:3]).set_index("feature")
    assert constant.loc["y", "constant_share"] == 1.0 and constant.loc["y", "clients"] == 3
    assert constant.loc["x", "constant_share"] == pytest.approx(1 / 3)
    assert constant.loc["x", "clients"] == 3


def test_client_constant_shares_on_the_unit_preset(frames: Frames, window: list[date]) -> None:
    """A static attribute reads 1, a balance below 1, every eligible client counted."""
    table = client_constant_shares(frames.rows, ["salary_transfer_flag", "casa_bal"], window)
    shares = table.set_index("feature")["constant_share"]
    assert shares["salary_transfer_flag"] == 1.0 and shares["casa_bal"] < 1.0
    assert (table["clients"] > 0).all()


def test_population_counts_equal_target_factorys_summary_where_both_exist(
    spark: SparkSession, unit_env: EnvironmentConfig, variant: Callable[..., UseCaseConfig]
) -> None:
    """On a config without eligibility steps whose spine is the target source: per window
    period the rows, positive rows and positive events equal Target Factory's summary; the
    labelled counts are null for the gap and latest periods (N10); eligible rows equal rows."""
    plain = variant(
        data={"model_input": None, "eligibility": {"analysis": [], "modelling": []}},
        entities={ENTITY: {"sources": {"features": ["retail_mart"], "targets": None}}},
    )
    panel, _, _ = build_panel(plain, ENTITY, unit_env, spark)
    available = sorted(row.period for row in panel.select("period").distinct().collect())
    periods = compared_periods(plain, available)
    table = population_counts(panel, plain, periods).set_index("period")
    summary = run_target_factory(plain, ENTITY, unit_env, spark).set_index("period")
    window = [MONTH.label(period) for period in periods["window"]]
    for column in ("rows", "positive_rows", "positive_events"):
        assert table.loc[window, column].tolist() == summary.loc[window, column].tolist()
    assert (table["eligible_rows"] == table["rows"]).all()
    labelled = ["known_target", "positive_rows", "positive_events", "non_event_units"]
    outside = [MONTH.label(period) for period in [*periods["gap"], *periods["latest"]]]
    assert outside and table.loc[outside, labelled].isna().all().all()
    events = table.loc[window, "positive_events"] + table.loc[window, "non_event_units"]
    assert (table.loc[window, "known_target"] == events).all()


def test_compared_periods_with_and_without_a_validation_period(
    cfg: UseCaseConfig, variant: Callable[..., UseCaseConfig]
) -> None:
    """Window 2025-03 … 2025-08, v 2025-11: the gap is 2025-09 and 2025-10, the latest the last
    period after v, never v itself and none when no period lies after v; with a null v no gap
    and the latest after the window; a window period the panel lacks is simply absent."""
    months = [MONTH.from_index(MONTH.index(date(2025, 1, 31)) + i) for i in range(14)]
    labels = {g: [MONTH.label(p) for p in ps] for g, ps in compared_periods(cfg, months).items()}
    assert labels == {
        "window": ["2025-03", "2025-04", "2025-05", "2025-06", "2025-07", "2025-08"],
        "gap": ["2025-09", "2025-10"],
        "latest": ["2026-02"],
    }
    v = cfg.time.validation_period
    up_to_v = compared_periods(cfg, [month for month in months if month <= v])
    assert up_to_v["latest"] == [] and v not in [p for group in up_to_v.values() for p in group]
    eda_only = compared_periods(variant(time={"validation_period": None}), months)
    assert eda_only == {"window": months[2:8], "gap": [], "latest": [months[-1]]}
    lacking = compared_periods(cfg, [month for month in months if month != months[4]])
    assert lacking["window"] == [months[i] for i in (2, 3, 5, 6, 7)]


def test_estimate_cells_refuses_bins_null_above_the_cap(
    frames: Frames, window: list[date], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The estimate is a positive count that grows with the lagged pass's window periods; with
    `eda.bins: null` above a planted `MAX_CELLS` of 10 it fails naming `eda.bins`."""
    rows = frames.rows.select("unit_id", "period", *FEATURES, "target")
    kinds = {name: frames.meta["kinds"][name] for name in FEATURES}
    both_passes = estimate_cells(rows, kinds, 100, window)
    assert both_passes > estimate_cells(rows, kinds, 100, []) > 0
    monkeypatch.setattr(counts, "MAX_CELLS", 10)
    with pytest.raises(ValueError, match=r"eda.bins: null would give about [\d,]+ cells over"):
        estimate_cells(rows, kinds, None, window)


def test_bins_null_gives_one_bin_per_distinct_value(frames: Frames, window: list[date]) -> None:
    """`eda.bins: null` on `product_cnt` (eight values): every value its own `= v` bin, the
    snapshot period's cells exactly the values its eligible rows hold, no other bin."""
    edges = bin_edges(frames.snapshot, {"product_cnt": "numeric"}, None)
    rows = frames.rows.select("unit_id", "period", "product_cnt", "target")
    cells = count_cells(
        rows.where(F.col("period") == window[-1]), edges, {}, [], None, window, MONTH
    )
    eligible = frames.snapshot[frames.snapshot["eligible"] == 1]
    assert set(cells["bin"]) == {f"= {value:g}" for value in eligible["product_cnt"].unique()}
    assert cells.groupby("bin")["n"].sum().sum() == len(eligible)


def test_zero_inflated_column_keeps_its_tail_bins_through_the_bucketizer(
    spark: SparkSession,
) -> None:
    """The edges rule on a 90%-zero column (T25): the zero bin holds the zeros and at least
    `bins / 2` other bins are non-empty after the Bucketizer."""
    rng = np.random.default_rng(0)
    values = np.concatenate([np.zeros(9_000), rng.lognormal(8, 1, 1_000)])
    edges = bin_edges(pd.DataFrame({"x": values, "eligible": 1}), {"x": "numeric"}, 20)
    rows = [(str(i), MONTHS[0], float(value), 0.0) for i, value in enumerate(values)]
    cells = count_cells(
        spark.createDataFrame(rows, ROWS_SCHEMA), edges, {}, [], None, MONTHS[:1], MONTH
    )
    by_bin = cells.groupby("bin")["n"].sum()
    assert by_bin["= 0"] == 9_000 and (by_bin > 0).sum() >= 1 + 10
    assert not cells["is_null"].any()


def test_a_rare_zero_still_gets_its_own_bin(spark: SparkSession) -> None:
    """One zero among a thousand values is no mass point, yet `bin_edges` gives it the `= 0`
    singleton (the zero share is read from that cell) and the edges stay strictly increasing;
    a column without a zero gets none."""
    values = np.concatenate([[0.0], np.linspace(1, 1000, 999)])
    snapshot = pd.DataFrame({"x": values, "y": values + 1, "eligible": 1})
    edges = bin_edges(snapshot, {"x": "numeric", "y": "numeric"}, 10)
    assert (np.diff(edges["x"]) > 0).all() and "= 0" in bin_labels(edges["x"])
    assert "= 0" not in bin_labels(edges["y"])
    rows = [(str(i), MONTHS[0], float(value), 1.0) for i, value in enumerate(values)]
    frame = spark.createDataFrame(rows, ROWS_SCHEMA)
    cells = count_cells(frame, {"x": edges["x"]}, {}, [], None, MONTHS[:1], MONTH)
    by_bin = cells.groupby("bin")["n"].sum()
    assert by_bin["= 0"] == 1 and by_bin.sum() == len(values) and (by_bin > 0).sum() >= 10


def test_minus_zero_null_and_nan_land_where_they_belong(spark: SparkSession) -> None:
    """Unnormalised, `-0.0` lands in the bucket below the `= 0` singleton (Java orders it below
    `0.0`; measured here through the Bucketizer directly); the pass normalises the values, so it
    counts in `= 0`; a null and a NaN in the null bin (N2) with the last order, a double flag's
    value as the target bin `"0"` / `"1"`, `sum_y` null where the label is."""
    m0 = MONTHS[0]
    edges = {"x": quantile_edges(np.array([0.0, 0.0, 1.5]), 10)}
    splits = [-np.inf, *map(float, edges["x"]), np.inf]
    raw = Bucketizer(splits=splits, inputCol="x", outputCol="bucket", handleInvalid="keep")
    measured = raw.transform(spark.createDataFrame([(-0.0,), (0.0,)], "x double")).collect()
    zero = bin_labels(edges["x"]).index("= 0")
    assert [row.bucket for row in measured] == [zero - 1, zero]
    rows = [("a", m0, -0.0, 0.0), ("b", m0, 0.0, 1.0), ("c", m0, 1.5, 1.0), ("d", m0, None, 0.0),
            ("e", m0, float("nan"), None)]  # fmt: skip
    frame = spark.createDataFrame(rows, ROWS_SCHEMA)
    cells = count_cells(frame, edges, {}, [], None, [m0], MONTH)
    by_cell = cells.groupby(["bin", "target_bin"], dropna=False)["n"].sum()
    assert by_cell["= 0", "0"] == 1 and by_cell["= 0", "1"] == 1 and by_cell["= 1.5", "1"] == 1
    null_bin = cells[cells["bin"] == NULL_BIN]
    assert null_bin["n"].sum() == 2 and null_bin["is_null"].all()
    assert (null_bin["bin_order"] == len(edges["x"]) + 1).all()
    assert cells.loc[cells["target_bin"].isna(), "sum_y"].isna().all()
    assert cells.loc[cells["target_bin"] == "1", "sum_y"].sum() == 2


def test_regression_target_bins_through_the_target_edges(spark: SparkSession) -> None:
    """A regression target binned on the edges the task spec builds (0 its own bin): the target
    bin is the bucket's label, `sum_y` the summed amounts."""
    amounts = [0.0] * 5 + [10.0, 20.0, 30.0, 40.0]
    target_edges = TASK_SPECS["regression"]["target_bins"](np.array(amounts), exact=False)
    rows = [(str(i), MONTHS[0], float(i), amount) for i, amount in enumerate(amounts)]
    schema = "unit_id string, period date, x double, target double"
    edges = {"x": quantile_edges(np.arange(9, dtype=float), 3)}
    frame = spark.createDataFrame(rows, schema)
    cells = count_cells(frame, edges, {}, [], target_edges, MONTHS[:1], MONTH)
    assert set(cells["target_bin"]) <= set(bin_labels(target_edges))
    assert cells.loc[cells["target_bin"] == "= 0", "n"].sum() == 5
    assert cells["sum_y"].sum() == sum(amounts) and cells["n"].sum() == len(amounts)


def test_window_levels_rank_pool_and_mark_unseen_levels(
    spark: SparkSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The window's levels by frequency; with the cap planted at 2 the third level pools as
    `__other__` after the kept ones, a level seen only after the window is `__new__`, null its
    own bin last; no label outside the window. With the ceiling planted at 3, `d` (four window
    levels) lists its two kept levels only and is named over the ceiling: every other level of
    it, seen in the window or not, is `__other__`, never `__new__`."""
    monkeypatch.setattr(counts, "LEVEL_CAP", 2)
    monkeypatch.setattr(counts, "POOLED_LEVEL_CAP", 3)
    m0, m1, later = MONTHS[:3]
    values = [(m0, "a", "p"), (m0, "a", "p"), (m0, "b", "q"), (m0, "c", "r"), (m1, "a", "s"),
              (m1, "b", "p"), (m1, None, "q"), (later, "c", "s"), (later, "z", "t"),
              (later, None, None)]  # fmt: skip
    rows = [(f"u{i}", period, c, d, 1) for i, (period, c, d) in enumerate(values)]
    schema = "unit_id string, period date, c string, d string, target int"
    frame = spark.createDataFrame(rows, schema)
    levels, over_ceiling = window_levels(frame, ["c", "d"], [m0, m1])
    assert levels == {"c": ["a", "b", "c"], "d": ["p", "q"]} and over_ceiling == ["d"]
    cells = count_cells(frame, {}, levels, over_ceiling, None, [m0, m1], MONTH)
    by_feature = {name: cells[cells["feature"] == name] for name in ("c", "d")}
    first = by_feature["c"][by_feature["c"]["period"] == MONTH.label(m0)].set_index("bin")
    assert first["bin_order"].to_dict() == {"a": 0, "b": 1, OTHER: 2}
    assert first["n"].to_dict() == {"a": 2, "b": 1, OTHER: 1}
    after = by_feature["c"][by_feature["c"]["period"] == MONTH.label(later)].set_index("bin")
    assert after["bin_order"].to_dict() == {OTHER: 2, NEW: 3, NULL_BIN: 4}
    assert after["is_null"].to_dict() == {OTHER: False, NEW: False, NULL_BIN: True}
    assert after["target_bin"].isna().all() and not first["target_bin"].isna().any()
    capped = by_feature["d"].groupby(["period", "bin"])["n"].sum()
    assert capped[MONTH.label(m0)].to_dict() == {"p": 2, "q": 1, OTHER: 1}
    assert capped[MONTH.label(later)].to_dict() == {OTHER: 2, NULL_BIN: 1}
    assert NEW not in set(by_feature["d"]["bin"])
    assert window_levels(frame, [], [m0]) == ({}, [])


def test_reserved_level_names_are_quoted_and_a_nan_level_is_the_null_bin(
    spark: SparkSession,
) -> None:
    """A real level `"null"` or `"__other__"` is quoted in the level list and its bin (`'null'`),
    so it never merges with the null bin or the pooled bin; a float column counted as a
    categorical puts a NaN in the null bin with the nulls (N2), never a `NaN` level."""
    m0 = MONTHS[0]
    rows = [("u1", m0, "null", 1.5, 1), ("u2", m0, None, float("nan"), 0),
            ("u3", m0, "__other__", None, 0), ("u4", m0, "a", 1.5, 1)]  # fmt: skip
    frame = spark.createDataFrame(
        rows, "unit_id string, period date, c string, f double, target int"
    )
    levels, over_ceiling = window_levels(frame, ["c", "f"], [m0])
    assert levels == {"c": ["'__other__'", "'null'", "a"], "f": ["1.5"]} and over_ceiling == []
    cells = count_cells(frame, {}, levels, [], None, [m0], MONTH)
    by_bin = cells.groupby(["feature", "bin"])["n"].sum()
    assert by_bin["c"].to_dict() == {"'__other__'": 1, "'null'": 1, "a": 1, NULL_BIN: 1}
    assert by_bin["f"].to_dict() == {"1.5": 2, NULL_BIN: 2}
    assert cells.loc[cells["bin"] == "'null'", "is_null"].eq(False).all()
    assert cells.loc[cells["bin"] == NULL_BIN, "is_null"].all()


def test_passes_refuse_an_empty_window_nothing_to_count_and_a_non_binary_flag(
    spark: SparkSession,
) -> None:
    """An empty `window_periods` fails loud in `window_levels` and both passes; so do passes with
    no feature, and a binary pass whose target holds a value other than 0 and 1."""
    m0 = MONTHS[0]
    rows = [("u1", m0, 1.0, 0), ("u2", m0, 2.0, 2)]
    frame = spark.createDataFrame(rows, "unit_id string, period date, x double, target int")
    edges = {"x": quantile_edges(np.array([1.0, 2.0]), 10)}
    with pytest.raises(ValueError, match="window_periods is empty"):
        window_levels(frame, ["x"], [])
    for count in (count_cells, count_lagged_cells):
        with pytest.raises(ValueError, match="window_periods is empty"):
            count(frame, edges, {}, [], None, [], MONTH)
        with pytest.raises(ValueError, match="nothing to count"):
            count(frame, {}, {}, [], None, [m0], MONTH)
    with pytest.raises(ValueError, match=r"the binary target holds the values \['2'\]"):
        count_cells(frame, edges, {}, [], None, [m0], MONTH)


def test_all_null_column_has_no_edges_and_one_all_bin(spark: SparkSession) -> None:
    """The edges come from the snapshot's eligible rows only: a numeric without a non-null
    eligible value gets `None` edges (an ineligible row's value counts for nothing), its rows
    fall in the null bin, and a value seen later in one `all` bin."""
    snapshot = pd.DataFrame({"x": [None, None, 7.0], "y": [1.0, 2.0, 99.0], "eligible": [1, 1, 0]})
    edges = bin_edges(snapshot, {"x": "numeric", "y": "numeric", "z": "categorical"}, 100)
    assert edges["x"] is None and edges["y"].size == 4 and "z" not in edges
    rows = [("u1", MONTHS[0], None, 1.0, 0), ("u2", MONTHS[0], 3.0, 2.0, 1)]
    frame = spark.createDataFrame(
        rows, "unit_id string, period date, x double, y double, target int"
    )
    cells = count_cells(frame, edges, {}, [], None, MONTHS[:1], MONTH)
    cells = cells.set_index(["feature", "bin"])
    assert cells.loc[("x", NULL_BIN), "n"] == 1 and cells.loc[("x", "all"), "n"] == 1
    assert (
        cells.loc[("x", NULL_BIN), "bin_order"] == 1 and cells.loc[("x", "all"), "bin_order"] == 0
    )


def test_kinds_come_from_the_spark_schema_with_overrides(
    spark: SparkSession, unit_env: EnvironmentConfig
) -> None:
    """On the feature-store extract's schema: a bigint is numeric, a string categorical, a date
    unsupported; an override to categorical holds; an override naming no candidate, one turning
    a string numeric and one on an unsupported column are refused by name; the mart's decimal
    is numeric."""
    schema = spark.read.parquet(unit_env.sources[ENTITY]["retail_fs_extract"].path).schema
    candidates = ["bureau_score", "preferred_channel", "as_of_date", "travel_spend_share"]
    assert detect_kinds(schema, candidates, {}) == {
        "bureau_score": "numeric",
        "preferred_channel": "categorical",
        "as_of_date": "unsupported",
        "travel_spend_share": "numeric",
    }
    overridden = detect_kinds(schema, candidates, {"bureau_score": "categorical"})
    assert overridden["bureau_score"] == "categorical"
    with pytest.raises(ValueError, match=r"features.kinds names \['no_such'\]"):
        detect_kinds(schema, candidates, {"no_such": "numeric"})
    with pytest.raises(ValueError, match="'preferred_channel' to numeric, but it is a string"):
        detect_kinds(schema, candidates, {"preferred_channel": "numeric"})
    with pytest.raises(ValueError, match="'as_of_date' to 'categorical', but its type date"):
        detect_kinds(schema, candidates, {"as_of_date": "categorical"})
    mart = spark.read.parquet(unit_env.sources[ENTITY]["retail_mart"].path).schema
    assert detect_kinds(mart, ["cc_limit", "segment", "casa_flag"], {}) == {
        "cc_limit": "numeric",
        "segment": "categorical",
        "casa_flag": "numeric",
    }


def test_frames_rows_is_a_spark_frame(frames: Frames) -> None:
    """`rows` never leaves Spark: a DataFrame with the keys, the supported candidates and the
    target."""
    assert isinstance(frames.rows, DataFrame)
    assert frames.rows.columns == ["unit_id", "period", *frames.meta["kinds"], "target"]
