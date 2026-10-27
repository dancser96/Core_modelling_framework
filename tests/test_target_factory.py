"""Target Factory: the forward window, the null rules, the source checks and the oracle (§4.1).

Hand-made panels check each rule month by month: the window is t+1 … t+w (t never in it, T8),
w comes from config (T13), the rule compares the value at t with the window's values, a null is
ignored unless nothing can be compared (SQL semantics), `null_as` fills the nulls first, and the
target is null where the unit lacks a month of the window (the panel edge, a leaver, a gap).
Hand-made sources written to parquet check what `load_targets` refuses: a target column of the
wrong type or values, a `null_as` the task can't read, and months missing from the target source.
On the unit preset, the built flag targets equal the oracle's `realised_target` on the rows the
oracle deems eligible, nulls included.
"""

import calendar
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from core_modelling.config import UseCaseConfig
from core_modelling.environment import EnvironmentConfig, Roots, Source
from core_modelling.target_factory import (
    build_targets,
    load_targets,
    run_target_factory,
    target_lineage,
)
from core_modelling.tasks import TASK_SPECS
from synthetic.truth.oracle import realised_target

MISSING = "no row"  # the unit has no row that month
FIRST = (2024, 11)  # hand-made panels start here, so they cross a year end
# With w = 3, the hand-made target source must have FIRST … 2025-06: eight months.
SHORT_TIME = {
    "train_months": {"first": date(2024, 11, 1), "last": date(2024, 12, 1)},
    "validation_month": date(2025, 3, 1),
}
UPSTREAM_TRAP = "cc_acquire_next_3_months_flag_trap_upstream_target"  # null in the last 3 months
TARGET_COLUMNS = ["unit_id", "month", "target", "null_in_window"]


def _month(position: int) -> date:
    """The last day of the month `position` months after `FIRST`."""
    year, month = divmod(FIRST[0] * 12 + FIRST[1] - 1 + position, 12)
    return date(year, month + 1, calendar.monthrange(year, month + 1)[1])


def _position(month: date) -> int:
    """How many months `month` is after `FIRST`."""
    return month.year * 12 + month.month - (FIRST[0] * 12 + FIRST[1])


def _panel(spark: SparkSession, values: dict[str, list], column_type: str = "int") -> DataFrame:
    """A keyed frame: each unit's `value` from `FIRST` on, month by month (`MISSING`: no row)."""
    rows = [
        (unit, _month(position), value)
        for unit, series in values.items()
        for position, value in enumerate(series)
        if value != MISSING
    ]
    return spark.createDataFrame(rows, f"unit_id string, month date, value {column_type}")


def _targets(targets: DataFrame, column: str = "target") -> dict[str, list]:
    """The built `column` laid out like `_panel`'s input: per unit, month by month."""
    rows = targets.collect()
    length = max(_position(row.month) for row in rows) + 1
    out = {}
    for row in rows:
        out.setdefault(row.unit_id, [MISSING] * length)[_position(row.month)] = row[column]
    return {unit: _trim(series) for unit, series in out.items()}


def _trim(series: list) -> list:
    """`series` without its trailing `MISSING` months (a unit that left early)."""
    while series and series[-1] == MISSING:
        series = series[:-1]
    return series


def _env_of(spark: SparkSession, tmp_path: Path, panels: dict[str, DataFrame]) -> EnvironmentConfig:
    """An environment whose `entity_a` sources are the keyed panels written to parquet under the
    config's key names."""
    sources = {}
    for name, panel in panels.items():
        path = str(tmp_path / name)
        raw = panel.withColumnRenamed("unit_id", "client_id")
        raw.withColumnRenamed("month", "snapshot_month").write.parquet(path)
        sources[name] = Source(format="parquet", path=path)
    return EnvironmentConfig(
        schema_version=1, roots=Roots(data=str(tmp_path)), sources={"entity_a": sources}
    )


def _variant(
    cfg: UseCaseConfig,
    task: str = "binary",
    w: int = 3,
    targets: str | None = "retail_holdings",
    time: dict | None = None,
    **target: object,
) -> UseCaseConfig:
    """`cfg` with another task, window, target source, months and target fields, re-validated."""
    data = cfg.model_dump()
    data["task"] = task
    data["time"] = {**data["time"], **(time or {}), "target_window_months": w}
    data["entities"]["entity_a"]["sources"]["targets"] = targets
    data["data"]["target"] = {**data["data"]["target"], **target}
    return UseCaseConfig.model_validate(data)


def test_flag_window_runs_from_t_plus_1_to_t_plus_w(
    spark: SparkSession, cc_config: UseCaseConfig
) -> None:
    """An event at t+1 and at t+w counts, at t+w+1 not; a holder at t gets 0; the last w months
    are null."""
    cfg = _variant(cc_config, rule="flag_goes_up", column="value")
    targets = build_targets(_panel(spark, {"a": [0, 0, 0, 0, 1, 0, 0, 0]}), cfg)
    assert targets.columns == TARGET_COLUMNS
    # t=0: the event is at t+4 = t+w+1; t=1: at t+w; t=3: at t+1; t=4: a holder at t.
    assert _targets(targets) == {"a": [0, 1, 1, 1, 0, None, None, None]}


def test_flag_window_length_comes_from_config(
    spark: SparkSession, cc_config: UseCaseConfig
) -> None:
    """With w = 2 the same unit's window is t+1 … t+2 and only the last two months are null."""
    cfg = _variant(cc_config, w=2, rule="flag_goes_up", column="value")
    targets = build_targets(_panel(spark, {"a": [0, 0, 0, 0, 1, 0, 0, 0]}), cfg)
    assert _targets(targets) == {"a": [0, 0, 1, 1, 0, 0, None, None]}


def test_leaver_and_gap_give_null(spark: SparkSession, cc_config: UseCaseConfig) -> None:
    """A month missing from the window nulls the target, even with an event in the months seen."""
    cfg = _variant(cc_config, rule="flag_goes_up", column="value")
    panel = {
        "stays": [0, 0, 0, 0, 0, 0, 0, 0],
        "leaves": [0, 0, 0, 1],  # its last row is month 3: t=1's window needs month 4
        "gap": [0, 1, MISSING, 0, 0, 0, 0, 0],  # no row in month 2
    }
    assert _targets(build_targets(_panel(spark, panel), cfg)) == {
        "stays": [0, 0, 0, 0, 0, None, None, None],
        "leaves": [1, None, None, None],
        "gap": [None, None, MISSING, 0, 0, None, None, None],
    }


@pytest.mark.parametrize(
    "series, null_as, target, held_null",
    [
        ([0, 0, 1, 1], None, 1, False),
        ([1, 1, 1, 1], None, 0, False),
        ([1, 0, 1, 1], None, 0, False),  # a rise compared with t, not month on month
        ([0, None, 1, 1], None, 1, True),  # a null beside a 1 is ignored
        ([0, None, None, None], None, None, True),  # nothing to compare with
        ([None, 0, 1, 1], None, None, True),  # nothing at t to compare
        ([None, 0, 1, 1], 0, 1, True),  # null_as fills t …
        ([0, None, None, None], 0, 0, True),  # … and the window; the raw null is still noted
    ],
    ids=["rise", "holder", "drop then rise", "null beside 1", "all null", "null at t",
         "null at t as 0", "all null as 0"],
)  # fmt: skip
def test_flag_goes_up_compares_t_with_the_window(
    spark: SparkSession,
    cc_config: UseCaseConfig,
    series: list,
    null_as: int | None,
    target: int | None,
    held_null: bool,
) -> None:
    """The target at t from the values t … t+3 with w = 3: 1 when some window flag exceeds t's,
    0 otherwise, null only when nothing can be compared; `null_in_window` marks a raw null."""
    cfg = _variant(cc_config, rule="flag_goes_up", column="value", null_as=null_as)
    targets = build_targets(_panel(spark, {"a": series}), cfg)
    assert _targets(targets) == {"a": [target, None, None, None]}
    assert _targets(targets, "null_in_window") == {"a": [held_null, False, False, False]}


def test_forward_sum_skips_nulls(spark: SparkSession, cc_config: UseCaseConfig) -> None:
    """The sum over t+1 … t+w, nulls skipped, null when the whole window is; t's own never
    enters."""
    cfg = _variant(cc_config, task="regression", rule="forward_sum", column="value")
    panel = {"a": [100.0, 1.0, None, 2.0], "b": [0.0, None, None, None]}
    targets = build_targets(_panel(spark, panel, "double"), cfg)
    assert _targets(targets) == {"a": [3.0, None, None, None], "b": [None, None, None, None]}
    assert _targets(targets, "null_in_window") == {"a": [True, False, False, False],
                                                   "b": [True, False, False, False]}  # fmt: skip


def test_null_value_share_counts_windows_with_a_raw_null(
    spark: SparkSession, cc_config: UseCaseConfig
) -> None:
    """The summary's `null_value_share` is the share of rows whose raw window held a null, even
    when `null_as` gave them a target; `null_share` stays the targets' own."""
    cfg = _variant(cc_config, rule="flag_goes_up", column="value", null_as=0)
    targets = build_targets(_panel(spark, {"a": [0, None, 1, 1], "b": [0, 0, 1, 1]}), cfg)
    summary = TASK_SPECS["binary"]["summarise_targets"](targets, _month(0), _month(3))
    # a's window at t=0 held a null: 1 of 2 rows that month, 1 of 8 rows in all (the incomplete
    # windows of months 1 … 3 count as false)
    assert summary["null_value_share"].tolist() == [0.5, 0, 0, 0, 0.125]
    assert summary["null_share"].tolist() == [0, 1, 1, 1, 0.75]


def test_leavers_negative_is_not_implemented(spark: SparkSession, cc_config: UseCaseConfig) -> None:
    """`leavers: negative` is refused until M4 (D-091), never silently treated as null."""
    cfg = _variant(cc_config, rule="flag_goes_up", column="value", leavers="negative")
    with pytest.raises(NotImplementedError, match="M4.*D-091"):
        build_targets(_panel(spark, {"a": [0, 0, 0, 0]}), cfg)


@pytest.mark.parametrize(
    "task, rule, known", [("binary", "forward_sum", "flag_goes_up"), ("regression", "x", "sum")]
)
def test_unknown_rule_fails_naming_the_task_rules(
    spark: SparkSession, cc_config: UseCaseConfig, task: str, rule: str, known: str
) -> None:
    """A rule the task's spec doesn't hold fails naming the task and its rules."""
    cfg = _variant(cc_config, task=task, rule=rule, column="value")
    with pytest.raises(ValueError, match=f"{rule!r} for task {task!r}; its rules: .*{known}"):
        build_targets(_panel(spark, {"a": [0, 0, 0, 0]}), cfg)


def test_target_lineage_is_the_column_then_the_listed_ones(cc_config: UseCaseConfig) -> None:
    """The rule's column first, then the config's lineage in order, without repeats."""
    assert target_lineage(cc_config) == ["cc_flag"]
    cfg = _variant(cc_config, lineage=["cc_status", "cc_flag", "cc_limit"])
    assert target_lineage(cfg) == ["cc_flag", "cc_status", "cc_limit"]


def test_boolean_flag_reads_as_0_1(
    spark: SparkSession, tmp_path: Path, cc_config: UseCaseConfig
) -> None:
    """A boolean flag passes the column check and builds the same targets as a 0/1 one; `null_as`
    fills its nulls too."""
    flags = [False, None, True, False, False, False, False, False]
    env = _env_of(spark, tmp_path, {"retail_holdings": _panel(spark, {"a": flags}, "boolean")})
    cfg = _variant(cc_config, time=SHORT_TIME, rule="flag_goes_up", column="value", null_as=0)
    targets, _ = load_targets(cfg, "entity_a", env, spark)
    assert _targets(targets) == {"a": [1, 1, 0, 0, 0, None, None, None]}


def test_flag_null_as_must_be_a_flag_value(
    spark: SparkSession, tmp_path: Path, cc_config: UseCaseConfig
) -> None:
    """A null in a flag reads as 0 or 1 at most; any other `null_as` is refused with the flag."""
    env = _env_of(spark, tmp_path, {"retail_holdings": _panel(spark, {"a": [0, 0, 1, 1]})})
    cfg = _variant(cc_config, time=SHORT_TIME, rule="flag_goes_up", column="value", null_as=2)
    with pytest.raises(ValueError, match="null_as 2 is not a flag value"):
        load_targets(cfg, "entity_a", env, spark)


@pytest.mark.parametrize(
    "task, column, values, column_type, error, message",
    [
        ("binary", "value", ["N", "Y"], "string", TypeError, "'value' is string, not a 0/1 flag"),
        ("binary", "value", [1, 2, 2, 2], "int", ValueError, r"only 0, 1 and nulls.*e\.g\. \[2\]"),
        ("binary", "value", [0.0, float("nan")], "double", ValueError, r"e\.g\. \[nan\]"),
        ("regression", "value", ["1.5"], "string", TypeError, "'value' is string, not numeric"),
        ("regression", "value", [1.5, float("nan")], "double", ValueError, "'value' holds NaN"),
        ("binary", "other", [0, 1], "int", ValueError, r"no target column 'other'; its columns: "
         r"\['unit_id', 'month', 'value'\]"),
    ],
    ids=["string flag", "flag 2", "NaN flag", "string amount", "NaN amount", "missing column"],
)  # fmt: skip
def test_target_column_the_task_cannot_read_is_refused(
    spark: SparkSession,
    tmp_path: Path,
    cc_config: UseCaseConfig,
    task: str,
    column: str,
    values: list,
    column_type: str,
    error: type[Exception],
    message: str,
) -> None:
    """A target column of the wrong type or values fails naming the source and the column, before
    any target is built."""
    env = _env_of(spark, tmp_path, {"retail_holdings": _panel(spark, {"a": values}, column_type)})
    rule = {"binary": "flag_goes_up", "regression": "forward_sum"}[task]
    cfg = _variant(cc_config, task=task, time=SHORT_TIME, rule=rule, column=column)
    with pytest.raises(error, match=f"'retail_holdings'.*{message}"):
        load_targets(cfg, "entity_a", env, spark)


@pytest.mark.parametrize(
    "series, missing",
    [([0, 0, 0, MISSING, 0, 0, 0, 0], "2025-02"), ([0] * 7, "2025-06")],
    ids=["gap", "ends before v + w"],
)
def test_target_source_missing_a_month_is_refused(
    spark: SparkSession, tmp_path: Path, cc_config: UseCaseConfig, series: list, missing: str
) -> None:
    """A month missing between the window's first and the validation month + w fails naming it."""
    panel = _panel(spark, {"a": series, "b": series})
    env = _env_of(spark, tmp_path, {"retail_holdings": panel})
    cfg = _variant(cc_config, time=SHORT_TIME, rule="flag_goes_up", column="value")
    with pytest.raises(ValueError, match=f"'retail_holdings' lacks the months \\['{missing}'\\]"):
        load_targets(cfg, "entity_a", env, spark)


def _compare_with_oracle(
    targets: DataFrame, mart: pd.DataFrame, oracle_target: str, w: int, eligible: pd.Series
) -> None:
    """Assert the built targets equal the oracle's realised target on the `eligible` mart rows,
    nulls included; the oracle's first-day months are moved to their last day to match."""
    expected = pd.DataFrame(
        {
            "unit_id": mart["client_id"],
            "month": pd.to_datetime(mart["snapshot_month"]) + pd.offsets.MonthEnd(0),
            "expected": realised_target(mart, oracle_target, w),
        }
    )[eligible]
    built = targets.toPandas()
    assert len(built) == len(mart)
    built["month"] = pd.to_datetime(built["month"])
    both = expected.merge(built, on=["unit_id", "month"], validate="one_to_one")
    assert len(both) == len(expected)
    assert both["expected"].notna().any() and both["expected"].isna().any()
    assert (both["target"] > 0).any()  # positives (a 1, a spend) among the compared rows
    pd.testing.assert_series_equal(
        both["target"].astype(float), both["expected"], check_names=False
    )


def test_flag_goes_up_matches_the_oracle(
    spark: SparkSession,
    unit: tuple[pd.DataFrame, pd.DataFrame, dict],
    unit_env: EnvironmentConfig,
    cc_config: UseCaseConfig,
) -> None:
    """The skeleton's target from the holdings equals the oracle's `cc_acquire` on the non-holders
    at t (the oracle nulls holders by its own eligibility; the rule gives them 0)."""
    mart = unit[0]
    targets, _ = load_targets(cc_config, "entity_a", unit_env, spark)
    w = cc_config.time.target_window_months
    _compare_with_oracle(targets, mart, "cc_acquire", w, mart["cc_flag"] == 0)


def test_forward_sum_matches_the_oracle(
    spark: SparkSession,
    unit: tuple[pd.DataFrame, pd.DataFrame, dict],
    unit_env: EnvironmentConfig,
    cc_config: UseCaseConfig,
) -> None:
    """Card spend summed from the spine equals the oracle's next-3-month spend for card holders."""
    mart = unit[0]
    cfg = _variant(
        cc_config, task="regression", targets=None, rule="forward_sum", column="spend_cc_vol"
    )
    targets, log = load_targets(cfg, "entity_a", unit_env, spark)
    assert log["source"] == "retail_mart"
    w = cfg.time.target_window_months
    _compare_with_oracle(targets, mart, "spend_cc_next_3_months", w, mart["cc_flag"] == 1)


def test_upstream_column_is_the_target(
    spark: SparkSession, unit_env: EnvironmentConfig, cc_config: UseCaseConfig
) -> None:
    """Without a rule the target is the upstream column itself, row for row, nulls included, and
    whether its window held a null is unknown."""
    cfg = _variant(cc_config, targets=None, rule=None, column=UPSTREAM_TRAP)
    targets, log = load_targets(cfg, "entity_a", unit_env, spark)
    raw = spark.read.parquet(unit_env.sources["entity_a"]["retail_mart"].path)
    expected = raw.select(
        F.col("client_id").alias("unit_id"),
        F.last_day("snapshot_month").alias("month"),
        F.col(UPSTREAM_TRAP).alias("target"),
        F.lit(None).cast("boolean").alias("null_in_window"),
    )
    assert log["source"] == "retail_mart"
    assert targets.columns == TARGET_COLUMNS
    assert targets.count() == expected.count()
    assert targets.exceptAll(expected).count() == expected.exceptAll(targets).count() == 0


def test_upstream_target_known_in_the_last_w_months_is_refused(
    spark: SparkSession, unit_env: EnvironmentConfig, cc_config: UseCaseConfig
) -> None:
    """An upstream column with values in the source's last w months, where no target over
    t+1 … t+w can be known yet, is refused: here the holding flag itself."""
    cfg = _variant(cc_config, rule=None, column="cc_flag")
    with pytest.raises(
        ValueError,
        match=r"'cc_flag' of 'retail_holdings' has values in the source's last 3 months "
        r"\(2026-07-31 … 2026-09-30\).*fills immature labels or uses another window",
    ):
        load_targets(cfg, "entity_a", unit_env, spark)


def test_upstream_value_in_the_first_of_the_last_w_months_is_refused(
    spark: SparkSession, tmp_path: Path, cc_config: UseCaseConfig
) -> None:
    """The tail is all w last months: a value at month end - w + 1 is refused even when the last
    w - 1 months are null (a tail one month short would let it through)."""
    upstream = _panel(spark, {"a": [0, 0, 0, 0, 0, 1, None, None]})
    env = _env_of(spark, tmp_path, {"retail_holdings": upstream})
    cfg = _variant(cc_config, time=SHORT_TIME, rule=None, column="value")
    with pytest.raises(ValueError, match=r"has values in the source's last 3 months"):
        load_targets(cfg, "entity_a", env, spark)


def test_run_target_factory_summary(
    spark: SparkSession,
    unit: tuple[pd.DataFrame, pd.DataFrame, dict],
    unit_env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    capsys: pytest.CaptureFixture,
) -> None:
    """One row per month plus `all`; rows add up; the last w months are null; no window held a
    null (the synthetic flags have none); the label columns only for the observation window's
    months, the `all` row's over them; events ≤ rows."""
    mart, w = unit[0], cc_config.time.target_window_months
    summary = run_target_factory(cc_config, "entity_a", unit_env, spark)
    months, total = summary.iloc[:-1], summary.iloc[-1]
    assert total["month"] == "all" and len(months) == mart["snapshot_month"].nunique()
    assert months["rows"].sum() == total["rows"] == len(mart)
    assert (months["null_share"].iloc[-w:] == 1).all()
    assert (months["null_share"].iloc[:-w] < 1).all()
    assert (summary["null_value_share"] == 0).all()
    window = cc_config.time.train_months
    shown = pd.to_datetime(months["month"]).dt.date.between(window.first, window.last)
    labels = ["mean_target", "positive_rows", "positive_events"]
    assert shown.sum() == 6
    assert months.loc[shown, labels].notna().all().all()
    assert months.loc[~shown, labels].isna().all().all()  # the validation month among them
    assert total["positive_rows"] == months["positive_rows"].sum()
    in_window = months[shown]
    assert (in_window["positive_events"] == in_window["positive_rows"]).all()
    assert 0 < total["positive_events"] < total["positive_rows"]
    out = capsys.readouterr().out
    assert "label columns for the observation window only" in out
    assert "null_value_share: rows whose window held a null" in out
