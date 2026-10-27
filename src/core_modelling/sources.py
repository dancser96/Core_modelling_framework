"""Keyed sources: a logical source read with its keys renamed and its months at their last day.

Every stage that reads a use case's data reads it through `read_keyed_source`: Target Factory,
the dataset's join and, later, Inference. Reading every source the same way is what lets a source
tagged on a month's first day join one tagged on its last (D-129): the `data.keys` columns become
`unit_id` and `month`, and `month` moves to its month's last day, the framework's one month
convention. A source whose month is not a date or timestamp, whose timestamp months are not at
midnight in the session time zone (they may shift a month), or whose keys repeat after the move,
fails loud here, before any target or join is built on it. The log says how the source tagged its
months, for the join log (docs/components/dataset.md, "Sources and joins").
"""

import calendar
from datetime import date

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DateType, TimestampNTZType, TimestampType

from core_modelling.config import UseCaseConfig
from core_modelling.environment import EnvironmentConfig, read_source

MONTH_TYPES = (DateType, TimestampType, TimestampNTZType)
SHOWN_KEYS = 5  # duplicate keys named in the error


def read_keyed_source(
    cfg: UseCaseConfig, entity: str, name: str, env: EnvironmentConfig, spark: SparkSession
) -> tuple[DataFrame, dict]:
    """The source `name` of `entity` with its keys as `unit_id` and `month` (the month's last day),
    and its log: the source, its distinct months and how it tagged them."""
    raw = read_source(spark, env, entity, name)
    unit_column, month_column = cfg.data.keys.unit_id, cfg.data.keys.month
    _check_key_columns(raw, name, unit_column, month_column)
    _check_midnight(raw, name, month_column)
    log = _month_log(raw, name, month_column)
    keyed = (
        raw.withColumnRenamed(unit_column, "unit_id")
        .withColumnRenamed(month_column, "month")
        .withColumn("month", F.last_day("month"))
    )
    _check_unique_keys(keyed, name)
    return keyed, log


def _check_key_columns(raw: DataFrame, name: str, unit_column: str, month_column: str) -> None:
    """Both key columns present, the month a date or timestamp, and no other column already
    called `unit_id` or `month` (the rename would make two)."""
    missing = [column for column in (unit_column, month_column) if column not in raw.columns]
    if missing:
        raise ValueError(f"source {name!r} has no key column {missing}; its columns: {raw.columns}")
    month_type = raw.schema[month_column].dataType
    if not isinstance(month_type, MONTH_TYPES):
        # e.g. a 'YYYY-MM' string or a 202406 integer: a format setting comes when a real
        # source needs one (D-129).
        raise TypeError(
            f"source {name!r}: the month column {month_column!r} is {month_type.simpleString()}, "
            "not a date or timestamp"
        )
    keys = (unit_column, month_column)
    clashes = [c for c in ("unit_id", "month") if c in raw.columns and c not in keys]
    if clashes:
        raise ValueError(
            f"source {name!r} already has a column {clashes} besides its keys "
            f"{unit_column!r}, {month_column!r}; rename it upstream"
        )


def _check_midnight(raw: DataFrame, name: str, month_column: str) -> None:
    """A timestamp month (an instant) is at 00:00 in the session time zone: one written at
    midnight in another zone shows another hour here and may land in the previous or next month.
    A date or a timestamp without time zone has no such shift."""
    if not isinstance(raw.schema[month_column].dataType, TimestampType):
        return
    month = F.col(month_column)
    # As a string, so the value is shown in the session time zone, not in Python's local one.
    not_midnight = raw.where(F.date_trunc("day", month) != month).select(month.cast("string"))
    off = not_midnight.limit(1).collect()
    if off:
        zone = raw.sparkSession.conf.get("spark.sql.session.timeZone")
        raise ValueError(
            f"source {name!r}: the timestamp month {month_column!r} holds {off[0][0]}, not at "
            f"00:00 in the session time zone {zone}, so its month may be wrong; store the month "
            "as a date or set the session time zone the source was written in"
        )


def _month_log(raw: DataFrame, name: str, month_column: str) -> dict:
    """The source's distinct months (at their last day) and how it tagged them, from its distinct
    raw days (a small collect)."""
    days = [row[0] for row in raw.select(F.to_date(month_column)).distinct().collect()]
    if not days:
        raise ValueError(f"source {name!r} is empty")
    if None in days:
        raise ValueError(f"source {name!r} has rows with a null month; every row needs one")
    if all(day.day == 1 for day in days):
        tag = "first day"
    elif all(day == _last_day(day) for day in days):
        tag = "last day"
    else:
        tag = "other days"
    return {"source": name, "months": sorted({_last_day(day) for day in days}), "month_tag": tag}


def _last_day(day: date) -> date:
    """The last day of `day`'s month."""
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def _check_unique_keys(keyed: DataFrame, name: str) -> None:
    """No null `unit_id` (the forward window would take every such row for one unit) and no
    `(unit_id, month)` twice after the month move, so a source carrying both a first-day and a
    last-day row for one client-month fails too."""
    repeated = (
        keyed.groupBy("unit_id", "month")
        .count()
        .filter("unit_id IS NULL OR count > 1")
        .orderBy(F.asc_nulls_first("unit_id"))  # a null unit id is named before any duplicate
        .limit(SHOWN_KEYS)
        .collect()
    )
    if any(row.unit_id is None for row in repeated):
        raise ValueError(f"source {name!r} has rows with a null unit id; every row needs one")
    if repeated:
        shown = ", ".join(f"({row.unit_id}, {row.month})" for row in repeated)
        raise ValueError(
            f"source {name!r} has duplicate (unit_id, month) keys after moving months to their "
            f"last day, e.g. {shown}"
        )
