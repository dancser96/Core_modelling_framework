"""The keyed source: keys renamed, the id cast to string, periods moved to their last day by the
period spec, bad periods, keys and reserved columns refused; the period arithmetic round-trips in
Python and Spark.

Hand-made sources are written to parquet with real local Spark; one test reads the unit preset's
mart and holdings, which tag their months differently, and checks they key alike.
"""

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DataType,
    DateType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampNTZType,
    TimestampType,
)

from core_modelling.config import UseCaseConfig
from core_modelling.environment import EnvironmentConfig, Roots, Source
from core_modelling.periods import PERIODS
from core_modelling.sources import check_periods_covered, missing_periods, read_keyed_source

WEEKLY = {
    "period": "week",
    "observation_window": {"first": "2024-02-05", "last": "2024-02-26"},
    "validation_period": "2024-03-18",
}
DAILY = {
    "period": "day",
    "observation_window": {"first": "2024-02-01", "last": "2024-02-10"},
    "validation_period": "2024-02-13",
}


def _env_with(
    spark: SparkSession,
    tmp_path: Path,
    sources: dict[str, tuple[list, DataType]],
    period_column: str = "snapshot_month",
) -> EnvironmentConfig:
    """An environment whose `entity_a` sources are `(client_id, <period_column>)` rows written to
    parquet, each source's period of the given type."""
    paths = {}
    for name, (rows, period_type) in sources.items():
        schema = StructType(
            [StructField("client_id", IntegerType()), StructField(period_column, period_type)]
        )
        paths[name] = str(tmp_path / name)
        spark.createDataFrame(rows, schema).write.parquet(paths[name])
    return EnvironmentConfig(
        schema_version=1,
        roots=Roots(data=str(tmp_path)),
        sources={"entity_a": {n: Source(format="parquet", path=p) for n, p in paths.items()}},
    )


def _keys(keyed: DataFrame) -> list[tuple]:
    """The frame's `(unit_id, period)` keys, sorted."""
    return sorted((row.unit_id, row.period) for row in keyed.select("unit_id", "period").collect())


def _as_keys(rows: list[tuple[int, date]]) -> list[tuple[str, date]]:
    """Hand-made `(client_id, day)` rows as the keys they read back as: the id a string."""
    return sorted((str(unit), day) for unit, day in rows)


def test_first_and_last_day_tags_read_alike_and_join(
    spark: SparkSession, tmp_path: Path, cc_config: UseCaseConfig
) -> None:
    """A first-day and a last-day source read as the same last-day keys and join on them."""
    first = [(1, date(2024, 2, 1)), (1, date(2024, 3, 1)), (2, date(2024, 2, 1))]
    last = [(1, date(2024, 2, 29)), (1, date(2024, 3, 31)), (2, date(2024, 2, 29))]
    env = _env_with(spark, tmp_path, {"first": (first, DateType()), "last": (last, DateType())})
    first_keyed, first_log = read_keyed_source(cc_config, "entity_a", "first", env, spark)
    last_keyed, last_log = read_keyed_source(cc_config, "entity_a", "last", env, spark)
    assert _keys(first_keyed) == _keys(last_keyed) == _as_keys(last)
    assert first_keyed.join(last_keyed, ["unit_id", "period"]).count() == 3
    assert first_log == {
        "source": "first",
        "periods": [date(2024, 2, 29), date(2024, 3, 31)],
        "period_tag": "period start",
        "id_type": "int",
    }
    assert last_log["period_tag"] == "period end"


def test_integer_unit_id_reads_back_as_a_string(
    spark: SparkSession, tmp_path: Path, cc_config: UseCaseConfig
) -> None:
    """The id is cast to string, so a draw on it survives an upstream change of the id's type."""
    env = _env_with(spark, tmp_path, {"ints": ([(12345, date(2024, 2, 1))], DateType())})
    keyed, log = read_keyed_source(cc_config, "entity_a", "ints", env, spark)
    assert isinstance(keyed.schema["unit_id"].dataType, StringType)
    assert _keys(keyed) == [("12345", date(2024, 2, 29))]
    assert log["id_type"] == "int"  # the raw type, before the cast


def test_weekly_source_moves_days_to_their_sunday(
    spark: SparkSession, tmp_path: Path, variant: Callable[..., UseCaseConfig]
) -> None:
    """Under a weekly config a Wednesday and a Monday read as their week's Sunday; a source of
    Mondays is tagged "period start", one of Sundays "period end", mixed days "other days"."""
    mixed = [(1, date(2024, 2, 7)), (1, date(2024, 2, 12)), (2, date(2024, 12, 30))]
    mondays = [(1, date(2024, 2, 5)), (1, date(2024, 2, 12))]
    sundays = [(1, date(2024, 2, 11)), (1, date(2024, 2, 18))]
    env = _env_with(
        spark,
        tmp_path,
        {"mixed": (mixed, DateType()), "mon": (mondays, DateType()), "sun": (sundays, DateType())},
    )
    cfg = variant(time=WEEKLY)
    keyed, log = read_keyed_source(cfg, "entity_a", "mixed", env, spark)
    assert _keys(keyed) == [
        ("1", date(2024, 2, 11)),
        ("1", date(2024, 2, 18)),
        ("2", date(2025, 1, 5)),  # a week across the year end
    ]
    assert log["periods"] == [date(2024, 2, 11), date(2024, 2, 18), date(2025, 1, 5)]
    assert log["period_tag"] == "other days"
    assert read_keyed_source(cfg, "entity_a", "mon", env, spark)[1]["period_tag"] == "period start"
    assert read_keyed_source(cfg, "entity_a", "sun", env, spark)[1]["period_tag"] == "period end"


def test_daily_source_keeps_its_days(
    spark: SparkSession, tmp_path: Path, variant: Callable[..., UseCaseConfig]
) -> None:
    """Under a daily config every day is its own period end, also from a timestamp."""
    rows = [(1, datetime(2024, 2, 7, 9)), (1, datetime(2024, 2, 8, 0))]
    env = _env_with(spark, tmp_path, {"days": (rows, TimestampNTZType())})
    keyed, log = read_keyed_source(variant(time=DAILY), "entity_a", "days", env, spark)
    assert isinstance(keyed.schema["period"].dataType, DateType)
    assert _keys(keyed) == [("1", date(2024, 2, 7)), ("1", date(2024, 2, 8))]
    assert log == {
        "source": "days",
        "periods": [date(2024, 2, 7), date(2024, 2, 8)],
        "period_tag": "period end",
        "id_type": "int",
    }


@pytest.mark.parametrize("period", list(PERIODS))
def test_period_index_round_trips_in_python_and_spark(spark: SparkSession, period: str) -> None:
    """`from_index` inverts `index` at the period's end, around month and year ends and a leap
    day; the Spark index and end agree with the Python ones on the same days; consecutive
    periods have consecutive indices."""
    spec = PERIODS[period]
    days = [
        date(2024, 2, 29),
        date(2024, 12, 30),  # a Monday of ISO week 2025-W01
        date(2025, 1, 1),
        date(2025, 1, 15),
        date(2025, 11, 1),
        date(2025, 12, 31),
    ]
    for day in days:
        end = spec.end(day)
        assert spec.start(day) <= day <= end
        assert spec.from_index(spec.index(day)) == end
        assert spec.index(spec.from_index(spec.index(day) + 1)) == spec.index(day) + 1
        assert spec.end(spec.start(day)) == end
    frame = spark.createDataFrame([(day,) for day in days], "day date")
    day = F.col("day")
    rows = frame.select(spec.spark_index(day).alias("i"), spec.spark_end(day).alias("e"))
    assert [(row.i, row.e) for row in rows.collect()] == [
        (spec.index(day), spec.end(day)) for day in days
    ]


def test_period_labels() -> None:
    """A month as `YYYY-MM`, a week as its ISO `YYYY-Www`, a day as `YYYY-MM-DD`."""
    day = date(2024, 12, 30)  # the Monday of ISO week 2025-W01
    assert PERIODS["month"].label(day) == "2024-12"
    assert PERIODS["week"].label(day) == "2025-W01"
    assert PERIODS["day"].label(day) == "2024-12-30"


def test_missing_weeks_across_a_year_end_are_named_by_iso_label() -> None:
    """The coverage check names the weeks missing across a year end by their ISO label, with
    both bounds as labels and `time.observation_window.first` named."""
    spec = PERIODS["week"]
    first, last = date(2025, 12, 21), date(2026, 1, 11)  # Sundays of 2025-W51 and 2026-W02
    assert missing_periods([first, last], first, last, spec) == ["2025-W52", "2026-W01"]
    complete = [first, date(2025, 12, 28), date(2026, 1, 4), last]
    assert missing_periods(complete, first, last, spec) == []
    log = {"source": "s", "periods": [first, last]}
    with pytest.raises(
        ValueError,
        match=r"source 's' lacks the periods \['2025-W52', '2026-W01'\]; .* from 2025-W51 "
        r"\(time.observation_window.first\) to 2026-W02 \(v \+ w\)",
    ):
        check_periods_covered(log, first, last, "source", "v + w", spec)


def _session_midnight(spark: SparkSession, day: date) -> datetime:
    """Midnight of `day` in the session time zone, as an aware datetime (a naive one would be read
    in Python's local time zone)."""
    zone = ZoneInfo(spark.conf.get("spark.sql.session.timeZone"))
    return datetime(day.year, day.month, day.day, tzinfo=zone)


@pytest.mark.parametrize("period_type", [TimestampType(), TimestampNTZType()])
def test_timestamp_month_reads_as_last_day_date(
    spark: SparkSession, tmp_path: Path, cc_config: UseCaseConfig, period_type: DataType
) -> None:
    """A timestamp month, mid-month here, reads as its month's last day, typed as a date; a
    time-zone-free one may carry any hour, an instant is at midnight in the session time zone."""
    if isinstance(period_type, TimestampType):
        stamp = _session_midnight(spark, date(2024, 4, 15))
    else:
        stamp = datetime(2024, 4, 15, 12)
    env = _env_with(spark, tmp_path, {"stamped": ([(1, stamp)], period_type)})
    keyed, log = read_keyed_source(cc_config, "entity_a", "stamped", env, spark)
    assert isinstance(keyed.schema["period"].dataType, DateType)
    assert _keys(keyed) == [("1", date(2024, 4, 30))]
    assert log["period_tag"] == "other days"


@pytest.mark.parametrize(
    "zone, shown",
    [("Asia/Dubai", "2024-04-01 04:00:00"), ("America/New_York", "2024-03-31 20:00:00")],
)
def test_timestamp_period_off_midnight_in_the_session_zone_fails(
    spark: SparkSession, tmp_path: Path, cc_config: UseCaseConfig, zone: str, shown: str
) -> None:
    """A timestamp period written at midnight UTC fails when read in another zone, naming the
    source, the value and the zone; west of UTC it would land in the previous month."""
    stamp = datetime(2024, 4, 1, tzinfo=timezone.utc)
    env = _env_with(spark, tmp_path, {"zoned": ([(1, stamp)], TimestampType())})
    original = spark.conf.get("spark.sql.session.timeZone")
    try:
        spark.conf.set("spark.sql.session.timeZone", zone)
        with pytest.raises(ValueError, match=rf"'zoned'.*holds {shown}.*{zone}"):
            read_keyed_source(cc_config, "entity_a", "zoned", env, spark)
    finally:
        spark.conf.set("spark.sql.session.timeZone", original)


@pytest.mark.parametrize(
    "period, period_type, shown",
    [("2024-04", StringType(), "string"), (202404, IntegerType(), "int")],
)
def test_period_that_is_not_a_date_fails_naming_its_type(
    spark: SparkSession,
    tmp_path: Path,
    cc_config: UseCaseConfig,
    period: object,
    period_type: DataType,
    shown: str,
) -> None:
    """A string or an integer period fails naming the source, the column and its type."""
    env = _env_with(spark, tmp_path, {"coded": ([(1, period)], period_type)})
    with pytest.raises(TypeError, match=f"'coded'.*'snapshot_month' is {shown},"):
        read_keyed_source(cc_config, "entity_a", "coded", env, spark)


@pytest.mark.parametrize("reserved", ["target", "split", "eligible", "period"])
def test_reserved_column_fails_naming_it(
    spark: SparkSession, tmp_path: Path, cc_config: UseCaseConfig, reserved: str
) -> None:
    """A source carrying a column the dataset adds, or a key name beside its own keys, fails
    naming the column, before the rename could make two of it."""
    rows, schema = [(1, date(2024, 4, 1), 0)], f"client_id int, snapshot_month date, {reserved} int"
    path = str(tmp_path / "clash")
    spark.createDataFrame(rows, schema).write.parquet(path)
    env = EnvironmentConfig(
        schema_version=1,
        roots=Roots(data=str(tmp_path)),
        sources={"entity_a": {"clash": Source(format="parquet", path=path)}},
    )
    message = rf"'clash' has a column \['{reserved}'\] that the framework reserves"
    with pytest.raises(ValueError, match=message):
        read_keyed_source(cc_config, "entity_a", "clash", env, spark)


def test_missing_key_column_fails_naming_the_columns(
    spark: SparkSession, tmp_path: Path, cc_config: UseCaseConfig
) -> None:
    """A source without the configured period key fails naming the source and its columns."""
    rows = [(1, date(2024, 4, 1))]
    env = _env_with(spark, tmp_path, {"renamed": (rows, DateType())}, period_column="month_id")
    with pytest.raises(
        ValueError,
        match=r"'renamed' has no key column \['snapshot_month'\]; its "
        r"columns: \['client_id', 'month_id'\]",
    ):
        read_keyed_source(cc_config, "entity_a", "renamed", env, spark)


@pytest.mark.parametrize(
    "rows",
    [
        [(1, date(2024, 3, 1)), (1, date(2024, 3, 1)), (2, date(2024, 3, 1))],
        [(1, date(2024, 3, 1)), (1, date(2024, 3, 31))],
    ],
    ids=["repeated", "both tags"],
)
def test_duplicate_keys_fail_naming_the_source_and_key(
    spark: SparkSession, tmp_path: Path, cc_config: UseCaseConfig, rows: list
) -> None:
    """A repeated client-month fails, also when one month carries both its first and last day."""
    env = _env_with(spark, tmp_path, {"doubled": (rows, DateType())})
    with pytest.raises(ValueError, match=r"'doubled' has duplicate .* \(1, 2024-03-31\)$"):
        read_keyed_source(cc_config, "entity_a", "doubled", env, spark)


def test_null_unit_id_fails_naming_the_source(
    spark: SparkSession, tmp_path: Path, cc_config: UseCaseConfig
) -> None:
    """A row without a unit id fails before any target is built on it, also beside a duplicate."""
    duplicates = [(unit, date(2024, 3, 1)) for unit in range(2, 200) for _ in range(2)]
    rows = [*duplicates, (None, date(2024, 3, 1))]  # more duplicate keys than the error names
    env = _env_with(spark, tmp_path, {"unkeyed": (rows, DateType())})
    with pytest.raises(ValueError, match="'unkeyed' has rows with a null unit id"):
        read_keyed_source(cc_config, "entity_a", "unkeyed", env, spark)


def test_unit_mart_and_holdings_key_alike(
    spark: SparkSession, unit_env: EnvironmentConfig, cc_config: UseCaseConfig
) -> None:
    """The unit preset's mart and holdings read with the same keys, every month at its last day."""
    mart, mart_log = read_keyed_source(cc_config, "entity_a", "retail_mart", unit_env, spark)
    holdings, holdings_log = read_keyed_source(
        cc_config, "entity_a", "retail_holdings", unit_env, spark
    )
    mart_keys = mart.select("unit_id", "period")
    holdings_keys = holdings.select("unit_id", "period")
    assert mart_keys.count() == holdings_keys.count()
    assert mart_keys.exceptAll(holdings_keys).count() == 0
    for keyed in (mart, holdings):
        assert keyed.filter(F.col("period") != F.last_day("period")).count() == 0
    assert mart_log["period_tag"] == "period start"
    assert mart_log["periods"] == holdings_log["periods"]
    assert all((month + timedelta(days=1)).day == 1 for month in mart_log["periods"])
