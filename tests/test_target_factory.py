"""Target Factory: the forward window, the null rules, the source checks and the oracle (§4.1).

Hand-made monthly panels check each rule period by period: the window is t+1 … t+w (t never in
it, T8), w comes from config (T13), the rule compares the value at t with the window's values, a
null is ignored unless nothing can be compared (SQL semantics), and the target is null where the
unit lacks a period of the window (the panel edge, a leaver, a gap). A weekly and a daily panel
with explicit dates check that the window counts the config's period, a missing one a gap.
Hand-made sources written to parquet check what `load_targets` refuses: a target column of the
wrong type or values, and periods missing from the target source.
On the unit preset, the built flag targets equal the oracle's `realised_target` on the rows the
oracle deems eligible, nulls included.
"""

import calendar
from collections.abc import Callable
from datetime import date

import pandas as pd
import pytest
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from core_modelling.config import UseCaseConfig
from core_modelling.environment import EnvironmentConfig
from core_modelling.periods import period_spec
from core_modelling.target_factory import (
    build_targets,
    load_targets,
    run_target_factory,
    target_lineage,
)
from core_modelling.tasks import TASK_SPECS
from synthetic.truth.oracle import realised_target

MISSING = "no row"  # the unit has no row that period
FIRST = (2024, 11)  # hand-made panels start here, so they cross a year end
# With w = 3, the hand-made target source must have FIRST … 2025-06: eight months.
SHORT_TIME = {
    "observation_window": {"first": date(2024, 11, 1), "last": date(2024, 12, 1)},
    "validation_period": date(2025, 3, 1),
}
UPSTREAM_TRAP = "cc_acquire_next_3_months_flag_trap_upstream_target"  # null in the last 3 months
TARGET_COLUMNS = ["unit_id", "period", "target", "null_in_window"]
# Explicit dates for the weekly and the daily window, crossing a year end: the third period
# (W02, 01-01) is the gap.
WEEKS = [date(2024, 12, 29), date(2025, 1, 5), date(2025, 1, 12), date(2025, 1, 19)]  # Sundays
DAYS = [date(2024, 12, 30), date(2024, 12, 31), date(2025, 1, 1), date(2025, 1, 2)]


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
    return spark.createDataFrame(rows, f"unit_id string, period date, value {column_type}")


def _targets(targets: DataFrame, column: str = "target") -> dict[str, list]:
    """The built `column` laid out like `_panel`'s input: per unit, month by month."""
    rows = targets.collect()
    length = max(_position(row.period) for row in rows) + 1
    out = {}
    for row in rows:
        out.setdefault(row.unit_id, [MISSING] * length)[_position(row.period)] = row[column]
    return {unit: _trim(series) for unit, series in out.items()}


def _trim(series: list) -> list:
    """`series` without its trailing `MISSING` months (a unit that left early)."""
    while series and series[-1] == MISSING:
        series = series[:-1]
    return series


def _variant(
    cfg: UseCaseConfig,
    task: str = "binary",
    w: int = 3,
    targets: str | None = "retail_holdings",
    time: dict | None = None,
    **target: object,
) -> UseCaseConfig:
    """`cfg` with another task, window, target source, time fields and target fields,
    re-validated."""
    data = cfg.model_dump()
    data["task"] = task
    data["time"] = {**data["time"], **(time or {}), "target_window": w}
    data["entities"]["entity_a"]["sources"]["targets"] = targets
    data["data"]["target"] = {**data["data"]["target"], **target}
    return UseCaseConfig.model_validate(data)


def test_flag_window_runs_from_t_plus_1_to_t_plus_w(
    spark: SparkSession, cc_config: UseCaseConfig
) -> None:
    """An event at t+1 and at t+w counts, at t+w+1 not; a holder at t gets 0; the last w periods
    are null."""
    cfg = _variant(cc_config, rule="flag_goes_up", column="value")
    targets = build_targets(_panel(spark, {"a": [0, 0, 0, 0, 1, 0, 0, 0]}), cfg)
    assert targets.columns == TARGET_COLUMNS
    # t=0: the event is at t+4 = t+w+1; t=1: at t+w; t=3: at t+1; t=4: a holder at t.
    assert _targets(targets) == {"a": [0, 1, 1, 1, 0, None, None, None]}


def test_flag_window_length_comes_from_config(
    spark: SparkSession, cc_config: UseCaseConfig
) -> None:
    """With w = 2 the same unit's window is t+1 … t+2 and only the last two periods are null."""
    cfg = _variant(cc_config, w=2, rule="flag_goes_up", column="value")
    targets = build_targets(_panel(spark, {"a": [0, 0, 0, 0, 1, 0, 0, 0]}), cfg)
    assert _targets(targets) == {"a": [0, 0, 1, 1, 0, 0, None, None]}


def test_leaver_and_gap_give_null(spark: SparkSession, cc_config: UseCaseConfig) -> None:
    """A period missing from the window nulls the target, even with an event in the periods
    seen."""
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


@pytest.mark.parametrize("period, dates", [("week", WEEKS), ("day", DAYS)], ids=["weekly", "daily"])
def test_window_counts_the_config_period(
    spark: SparkSession, cc_config: UseCaseConfig, period: str, dates: list[date]
) -> None:
    """On weekly or daily data with w = 2, the window is the next two periods of that length: a
    unit with periods 1, 2, 4 has a gap at 3, so periods 1 and 2 get null; a unit with 1, 2, 3
    labels period 1 from 2 and 3 (an event at 3, two periods ahead)."""
    cfg = _variant(cc_config, w=2, time={"period": period}, rule="flag_goes_up", column="value")
    rows = [("gap", dates[0], 0), ("gap", dates[1], 0), ("gap", dates[3], 1)]
    rows += [("full", dates[0], 0), ("full", dates[1], 0), ("full", dates[2], 1)]
    source = spark.createDataFrame(rows, "unit_id string, period date, value int")
    built = {(r.unit_id, r.period): r.target for r in build_targets(source, cfg).collect()}
    assert built == {
        ("gap", dates[0]): None, ("gap", dates[1]): None, ("gap", dates[3]): None,
        ("full", dates[0]): 1, ("full", dates[1]): None, ("full", dates[2]): None,
    }  # fmt: skip


@pytest.mark.parametrize(
    "series, target, held_null",
    [
        ([0, 0, 1, 1], 1, False),
        ([1, 1, 1, 1], 0, False),
        ([1, 0, 1, 1], 0, False),  # a rise compared with t, not period on period
        ([0, None, 1, 1], 1, True),  # a null beside a 1 is ignored
        ([0, None, None, None], None, True),  # nothing to compare with
        ([None, 0, 1, 1], None, True),  # nothing at t to compare
    ],
    ids=["rise", "holder", "drop then rise", "null beside 1", "all null", "null at t"],
)  # fmt: skip
def test_flag_goes_up_compares_t_with_the_window(
    spark: SparkSession,
    cc_config: UseCaseConfig,
    series: list,
    target: int | None,
    held_null: bool,
) -> None:
    """The target at t from the values t … t+3 with w = 3: 1 when some window flag exceeds t's,
    0 otherwise, null only when nothing can be compared; `null_in_window` marks a raw null."""
    cfg = _variant(cc_config, rule="flag_goes_up", column="value")
    targets = build_targets(_panel(spark, {"a": series}), cfg)
    assert _targets(targets) == {"a": [target, None, None, None]}
    assert _targets(targets, "null_in_window") == {"a": [held_null, None, None, None]}


def test_forward_sum_skips_nulls(spark: SparkSession, cc_config: UseCaseConfig) -> None:
    """The sum over t+1 … t+w, nulls skipped, null when the whole window is; t's own never
    enters."""
    cfg = _variant(cc_config, task="regression", rule="forward_sum", column="value")
    panel = {"a": [100.0, 1.0, None, 2.0], "b": [0.0, None, None, None]}
    targets = build_targets(_panel(spark, panel, "double"), cfg)
    assert _targets(targets) == {"a": [3.0, None, None, None], "b": [None, None, None, None]}
    assert _targets(targets, "null_in_window") == {"a": [True, None, None, None],
                                                   "b": [True, None, None, None]}  # fmt: skip


def test_null_in_window_is_null_where_the_window_is_incomplete(
    spark: SparkSession, cc_config: UseCaseConfig
) -> None:
    """A boolean for every complete window (true where the raw column had a null at t or in it:
    a's null at month 1 is in t=0's window and at t=1's own t), null at the panel edge and
    before a gap, whatever the raw values there."""
    cfg = _variant(cc_config, rule="flag_goes_up", column="value")
    panel = {"a": [0, None, 1, 1, 0], "b": [0, 0, 0, 0, 0], "gap": [0, MISSING, 0, 0, 0]}
    assert _targets(build_targets(_panel(spark, panel), cfg), "null_in_window") == {
        "a": [True, True, None, None, None],
        "b": [False, False, None, None, None],
        "gap": [None, MISSING, None, None, None],
    }


def test_null_value_share_counts_windows_with_a_raw_null(
    spark: SparkSession, cc_config: UseCaseConfig
) -> None:
    """The summary's `null_value_share` is the share of complete windows whose raw window held a
    null, even where the target could still be built; `null_share` stays the targets' own."""
    cfg = _variant(cc_config, time=SHORT_TIME, rule="flag_goes_up", column="value")
    targets = build_targets(_panel(spark, {"a": [0, None, 1, 1], "b": [0, 0, 1, 1]}), cfg)
    summary = TASK_SPECS["binary"]["summarise_targets"](targets, cfg)
    # a's window at t=0 held a null: 1 of the 2 complete windows, in month 0 and in all; the
    # incomplete windows of months 1 … 3 are null, so their share is unknown
    assert summary["period"].tolist() == ["2024-11", "2024-12", "2025-01", "2025-02", "all"]
    assert summary["null_value_share"].fillna(-1).tolist() == [0.5, -1, -1, -1, 0.5]
    assert summary["null_share"].tolist() == [0, 1, 1, 1, 0.75]


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
    spark: SparkSession, write_sources: Callable[..., EnvironmentConfig], cc_config: UseCaseConfig
) -> None:
    """A boolean flag passes the column check and builds the same targets as a 0/1 one, a null
    at t giving a null target."""
    flags = [False, None, True, False, False, False, False, False]
    env = write_sources({"retail_holdings": _panel(spark, {"a": flags}, "boolean")})
    cfg = _variant(cc_config, time=SHORT_TIME, rule="flag_goes_up", column="value")
    targets, _ = load_targets(cfg, "entity_a", env, spark)
    assert _targets(targets) == {"a": [1, None, 0, 0, 0, None, None, None]}


@pytest.mark.parametrize(
    "task, column, values, column_type, error, message",
    [
        ("binary", "value", ["N", "Y"], "string", TypeError, "'value' is string, not a 0/1 flag"),
        ("binary", "value", [1, 2, 2, 2], "int", ValueError, r"only 0, 1 and nulls.*e\.g\. \[2\]"),
        ("binary", "value", [0.0, float("nan")], "double", ValueError, r"e\.g\. \[nan\]"),
        ("regression", "value", ["1.5"], "string", TypeError, "'value' is string, not numeric"),
        ("regression", "value", [1.5, float("nan")], "double", ValueError, "'value' holds NaN"),
        ("binary", "other", [0, 1], "int", ValueError, r"no target column 'other'; its columns: "
         r"\['unit_id', 'period', 'value'\]"),
    ],
    ids=["string flag", "flag 2", "NaN flag", "string amount", "NaN amount", "missing column"],
)  # fmt: skip
def test_target_column_the_task_cannot_read_is_refused(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
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
    env = write_sources({"retail_holdings": _panel(spark, {"a": values}, column_type)})
    rule = {"binary": "flag_goes_up", "regression": "forward_sum"}[task]
    cfg = _variant(cc_config, task=task, time=SHORT_TIME, rule=rule, column=column)
    with pytest.raises(error, match=f"'retail_holdings'.*{message}"):
        load_targets(cfg, "entity_a", env, spark)


@pytest.mark.parametrize(
    "series, missing",
    [([0, 0, 0, MISSING, 0, 0, 0, 0], "2025-02"), ([0] * 7, "2025-06")],
    ids=["gap", "ends before v + w"],
)
def test_target_source_missing_a_period_is_refused(
    spark: SparkSession,
    write_sources: Callable[..., EnvironmentConfig],
    cc_config: UseCaseConfig,
    series: list,
    missing: str,
) -> None:
    """A period missing between the window's first and the validation period + w fails naming it
    and the two config bounds."""
    env = write_sources({"retail_holdings": _panel(spark, {"a": series, "b": series})})
    cfg = _variant(cc_config, time=SHORT_TIME, rule="flag_goes_up", column="value")
    with pytest.raises(
        ValueError,
        match=rf"'retail_holdings' lacks the periods \['{missing}'\].*from 2024-11 "
        r"\(time\.observation_window\.first\) to 2025-06 "
        r"\(time\.validation_period \+ target_window\)",
    ):
        load_targets(cfg, "entity_a", env, spark)


def _compare_with_oracle(
    targets: DataFrame, mart: pd.DataFrame, oracle_target: str, w: int, eligible: pd.Series
) -> None:
    """Assert the built targets equal the oracle's realised target on the `eligible` mart rows,
    nulls included; the oracle's integer ids and first-day months are moved to the string ids
    and last-day periods of the keyed source to match."""
    expected = pd.DataFrame(
        {
            "unit_id": mart["client_id"].astype(str),
            "period": pd.to_datetime(mart["snapshot_month"]) + pd.offsets.MonthEnd(0),
            "expected": realised_target(mart, oracle_target, w),
        }
    )[eligible]
    built = targets.toPandas()
    assert len(built) == len(mart)
    built["period"] = pd.to_datetime(built["period"])
    both = expected.merge(built, on=["unit_id", "period"], validate="one_to_one")
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
    w = cc_config.time.target_window
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
    w = cfg.time.target_window
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
        F.col("client_id").cast("string").alias("unit_id"),
        F.last_day("snapshot_month").alias("period"),
        F.col(UPSTREAM_TRAP).alias("target"),
        F.lit(None).cast("boolean").alias("null_in_window"),
    )
    assert log["source"] == "retail_mart"
    assert targets.columns == TARGET_COLUMNS
    assert targets.count() == expected.count()
    assert targets.exceptAll(expected).count() == expected.exceptAll(targets).count() == 0


def test_upstream_target_known_in_the_last_w_periods_is_refused(
    spark: SparkSession, unit_env: EnvironmentConfig, cc_config: UseCaseConfig
) -> None:
    """An upstream column with values in the source's last w periods, where no target over
    t+1 … t+w can be known yet, is refused: here the holding flag itself."""
    cfg = _variant(cc_config, rule=None, column="cc_flag")
    with pytest.raises(
        ValueError,
        match=r"'cc_flag' of 'retail_holdings' has values in the source's last 3 periods "
        r"\(2026-07 … 2026-09\).*fills immature labels or uses another window",
    ):
        load_targets(cfg, "entity_a", unit_env, spark)


def test_upstream_target_with_a_longer_window_is_refused(
    spark: SparkSession, write_sources: Callable[..., EnvironmentConfig], cc_config: UseCaseConfig
) -> None:
    """An upstream column null in the last w + 1 periods was built with a longer window than
    `w`: its target windows would overlap the validation period's (§4.2)."""
    upstream = _panel(spark, {"a": [0, 0, 0, 0, None, None, None, None]})
    env = write_sources({"retail_holdings": upstream})
    cfg = _variant(cc_config, time=SHORT_TIME, rule=None, column="value")
    with pytest.raises(ValueError, match=r"no value in 2025-03, the last period.*seems longer"):
        load_targets(cfg, "entity_a", env, spark)


def test_upstream_value_in_the_first_of_the_last_w_periods_is_refused(
    spark: SparkSession, write_sources: Callable[..., EnvironmentConfig], cc_config: UseCaseConfig
) -> None:
    """The tail is all w last periods: a value at period end - w + 1 is refused even when the
    last w - 1 periods are null (a tail one period short would let it through)."""
    upstream = _panel(spark, {"a": [0, 0, 0, 0, 0, 1, None, None]})
    env = write_sources({"retail_holdings": upstream})
    cfg = _variant(cc_config, time=SHORT_TIME, rule=None, column="value")
    with pytest.raises(ValueError, match=r"has values in the source's last 3 periods"):
        load_targets(cfg, "entity_a", env, spark)


def test_run_target_factory_summary(
    spark: SparkSession,
    unit: tuple[pd.DataFrame, pd.DataFrame, dict],
    unit_env: EnvironmentConfig,
    cc_config: UseCaseConfig,
    capsys: pytest.CaptureFixture,
) -> None:
    """One row per period plus `all`; rows add up; the last w periods are null, their null-value
    share unknown; no complete window held a null (the synthetic flags have none); the label
    columns only for the observation window's periods, the `all` row's over them; events ≤
    rows."""
    mart, w = unit[0], cc_config.time.target_window
    summary = run_target_factory(cc_config, "entity_a", unit_env, spark)
    periods, total = summary.iloc[:-1], summary.iloc[-1]
    assert total["period"] == "all" and len(periods) == mart["snapshot_month"].nunique()
    assert periods["rows"].sum() == total["rows"] == len(mart)
    assert (periods["null_share"].iloc[-w:] == 1).all()
    assert (periods["null_share"].iloc[:-w] < 1).all()
    assert (periods["null_value_share"].iloc[:-w] == 0).all()
    assert periods["null_value_share"].iloc[-w:].isna().all() and total["null_value_share"] == 0
    window, label = cc_config.time.observation_window, period_spec(cc_config).label
    shown = periods["period"].between(label(window.first), label(window.last))
    labels = ["mean_target", "positive_rows", "positive_events"]
    assert shown.sum() == 6
    assert periods.loc[shown, labels].notna().all().all()
    assert periods.loc[~shown, labels].isna().all().all()  # the validation period among them
    assert total["positive_rows"] == periods["positive_rows"].sum()
    in_window = periods[shown]
    assert (in_window["positive_events"] == in_window["positive_rows"]).all()
    assert 0 < total["positive_events"] < total["positive_rows"]
    out = capsys.readouterr().out
    assert "label columns for the observation window only" in out
    assert "null_value_share: rows whose window held a null" in out
