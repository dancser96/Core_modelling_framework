"""The keyed source: keys renamed, months moved to their last day, bad months and keys refused.

Hand-made sources are written to parquet with real local Spark; the last test reads the unit
preset's mart and holdings, which tag their months differently, and checks they key alike.
"""

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
from core_modelling.sources import read_keyed_source


def _env_with(
    spark: SparkSession,
    tmp_path: Path,
    sources: dict[str, tuple[list, DataType]],
    month_column: str = "snapshot_month",
) -> EnvironmentConfig:
    """An environment whose `entity_a` sources are `(client_id, <month_column>)` rows written to
    parquet, each source's month of the given type."""
    paths = {}
    for name, (rows, month_type) in sources.items():
        schema = StructType(
            [StructField("client_id", IntegerType()), StructField(month_column, month_type)]
        )
        paths[name] = str(tmp_path / name)
        spark.createDataFrame(rows, schema).write.parquet(paths[name])
    return EnvironmentConfig(
        schema_version=1,
        roots=Roots(data=str(tmp_path)),
        sources={"entity_a": {n: Source(format="parquet", path=p) for n, p in paths.items()}},
    )


def _keys(keyed: DataFrame) -> list[tuple]:
    """The frame's `(unit_id, month)` keys, sorted."""
    return sorted((row.unit_id, row.month) for row in keyed.select("unit_id", "month").collect())


def test_first_and_last_day_tags_read_alike_and_join(
    spark: SparkSession, tmp_path: Path, cc_config: UseCaseConfig
) -> None:
    """A first-day and a last-day source read as the same last-day keys and join on them."""
    first = [(1, date(2024, 2, 1)), (1, date(2024, 3, 1)), (2, date(2024, 2, 1))]
    last = [(1, date(2024, 2, 29)), (1, date(2024, 3, 31)), (2, date(2024, 2, 29))]
    env = _env_with(spark, tmp_path, {"first": (first, DateType()), "last": (last, DateType())})
    first_keyed, first_log = read_keyed_source(cc_config, "entity_a", "first", env, spark)
    last_keyed, last_log = read_keyed_source(cc_config, "entity_a", "last", env, spark)
    assert _keys(first_keyed) == _keys(last_keyed) == sorted(last)
    assert first_keyed.join(last_keyed, ["unit_id", "month"]).count() == 3
    assert first_log == {
        "source": "first",
        "months": [date(2024, 2, 29), date(2024, 3, 31)],
        "month_tag": "first day",
    }
    assert last_log["month_tag"] == "last day"


def _session_midnight(spark: SparkSession, day: date) -> datetime:
    """Midnight of `day` in the session time zone, as an aware datetime (a naive one would be read
    in Python's local time zone)."""
    zone = ZoneInfo(spark.conf.get("spark.sql.session.timeZone"))
    return datetime(day.year, day.month, day.day, tzinfo=zone)


@pytest.mark.parametrize("month_type", [TimestampType(), TimestampNTZType()])
def test_timestamp_month_reads_as_last_day_date(
    spark: SparkSession, tmp_path: Path, cc_config: UseCaseConfig, month_type: DataType
) -> None:
    """A timestamp month, mid-month here, reads as its month's last day, typed as a date; a
    time-zone-free one may carry any hour, an instant is at midnight in the session time zone."""
    if isinstance(month_type, TimestampType):
        stamp = _session_midnight(spark, date(2024, 4, 15))
    else:
        stamp = datetime(2024, 4, 15, 12)
    env = _env_with(spark, tmp_path, {"stamped": ([(1, stamp)], month_type)})
    keyed, log = read_keyed_source(cc_config, "entity_a", "stamped", env, spark)
    assert isinstance(keyed.schema["month"].dataType, DateType)
    assert _keys(keyed) == [(1, date(2024, 4, 30))]
    assert log["month_tag"] == "other days"


@pytest.mark.parametrize(
    "zone, shown",
    [("Asia/Dubai", "2024-04-01 04:00:00"), ("America/New_York", "2024-03-31 20:00:00")],
)
def test_timestamp_month_off_midnight_in_the_session_zone_fails(
    spark: SparkSession, tmp_path: Path, cc_config: UseCaseConfig, zone: str, shown: str
) -> None:
    """A timestamp month written at midnight UTC fails when read in another zone, naming the
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
    "month, month_type, shown",
    [("2024-04", StringType(), "string"), (202404, IntegerType(), "int")],
)
def test_month_that_is_not_a_date_fails_naming_its_type(
    spark: SparkSession,
    tmp_path: Path,
    cc_config: UseCaseConfig,
    month: object,
    month_type: DataType,
    shown: str,
) -> None:
    """A string or an integer month fails naming the source, the column and its type."""
    env = _env_with(spark, tmp_path, {"coded": ([(1, month)], month_type)})
    with pytest.raises(TypeError, match=f"'coded'.*'snapshot_month' is {shown},"):
        read_keyed_source(cc_config, "entity_a", "coded", env, spark)


def test_missing_key_column_fails_naming_the_columns(
    spark: SparkSession, tmp_path: Path, cc_config: UseCaseConfig
) -> None:
    """A source without the configured month key fails naming the source and its columns."""
    rows = [(1, date(2024, 4, 1))]
    env = _env_with(spark, tmp_path, {"renamed": (rows, DateType())}, month_column="month_id")
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
    mart_keys, holdings_keys = mart.select("unit_id", "month"), holdings.select("unit_id", "month")
    assert mart_keys.count() == holdings_keys.count()
    assert mart_keys.exceptAll(holdings_keys).count() == 0
    for keyed in (mart, holdings):
        assert keyed.filter(F.col("month") != F.last_day("month")).count() == 0
    assert mart_log["month_tag"] == "first day"
    assert mart_log["months"] == holdings_log["months"]
    assert all((month + timedelta(days=1)).day == 1 for month in mart_log["months"])
