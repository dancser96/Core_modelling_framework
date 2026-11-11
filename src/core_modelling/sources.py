"""Keyed sources: a logical source read with its keys renamed and its periods at their last day.

Every stage that reads a use case's data reads it through `read_keyed_source` (Target Factory,
the dataset's join and, later, Inference), which is what lets a source tagged on a period's
first day join one tagged on its last (D-129). The key columns become `unit_id` (cast to
string, so a draw on it survives an upstream change of the id column's type) and `period`,
moved to its period's last day, the framework's one convention, through the period spec
(`periods.py`). A source names its key columns as in `data.keys`, or, written as
`{source, keys}` in `entities.<e>.sources`, its own (`source_keys`); the spine always uses
`data.keys`. A period that is not a date or timestamp, a timestamp period not at midnight in
the session time zone (it may shift a period), or keys that repeat after the move fail loud
here, before any target or join is built on the source. A non-key column named like a key is
read as `source_<name>` (`rename_reserved`); one named like a column the dataset adds keeps its
name here and is handled on the read side (`dataset/panel.py`), so `data.target.column` names
an upstream column as the source does. The log feeds the join log (docs/components/dataset.md,
"Sources and joins"), and `check_periods_covered` is the one check that a source has every
period a caller needs: the spine up to the validation period, the target source up to the
validation period + w (the window's last period stands in for a null
`time.validation_period`, an EDA-only config).
"""

from datetime import date

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DateType, TimestampNTZType, TimestampType

from core_modelling.config import UseCaseConfig
from core_modelling.config.schema import Keys, SourceEntry
from core_modelling.environment import EnvironmentConfig, read_source
from core_modelling.periods import Period, period_labels, period_spec

# The keys every keyed source and the dataset carry; a source's other column of that name is read
# as `source_<name>`.
KEYS = ["unit_id", "period"]
# The columns the dataset adds; a source column of that name is renamed `source_<name>` on the
# read side (`panel.read_side_columns`).
HELPER_COLUMNS = ["target", "split", "eligible"]
PERIOD_TYPES = (DateType, TimestampType, TimestampNTZType)
SHOWN_KEYS = 5  # duplicate keys named in the error


def source_name(entry: str | SourceEntry) -> str:
    """The logical name of a source entry (a plain name, or `{source, keys}`)."""
    return entry if isinstance(entry, str) else entry.source


def source_keys(entry: str | SourceEntry, keys: Keys) -> Keys:
    """The entry's key columns: its own `keys`, each one left out named as in `keys`."""
    if isinstance(entry, str):
        return keys
    own = entry.keys
    return Keys(
        unit_id=keys.unit_id if own.unit_id is None else own.unit_id,
        period=keys.period if own.period is None else own.period,
    )


def feature_source_names(cfg: UseCaseConfig, entity: str) -> list[str]:
    """The logical names of `entity`'s feature sources, the spine first."""
    return [source_name(entry) for entry in cfg.entities[entity].sources.features]


def feature_sources_dump(cfg: UseCaseConfig, entity: str) -> list:
    """`entity`'s feature sources as plain data, a name or `{source, keys}`: what the panel's
    meta and the model input's sidecar record and compare."""
    return cfg.entities[entity].sources.model_dump(mode="json")["features"]


def read_keyed_source(
    cfg: UseCaseConfig,
    entity: str,
    entry: str | SourceEntry,
    env: EnvironmentConfig,
    spark: SparkSession,
) -> tuple[DataFrame, dict]:
    """The source `entry` (a name, or `{source, keys}`) of `entity`, lazily, one row per source
    row and unique on the keys: `unit_id` (a string), `period` (the period's last day) and every
    other column, one named like a key as `source_<name>`. Its log: the source, its distinct
    periods (a small collect), how it tagged them, the raw id's type, the keys of a
    `{source, keys}` entry, the renames and its non-key columns after them (`columns`)."""
    name = source_name(entry)
    raw = read_source(spark, env, entity, name)
    spec = period_spec(cfg)
    keys = source_keys(entry, cfg.data.keys)
    unit_column, period_column = keys.unit_id, keys.period
    _check_key_columns(raw, name, unit_column, period_column)
    _check_midnight(raw, name, period_column)
    log = _period_log(raw, name, period_column, spec)
    log["id_type"] = raw.schema[unit_column].dataType.simpleString()  # before the string cast
    if not isinstance(entry, str):  # which columns became the keys, a fallback included
        log["keys"] = keys.model_dump()
    # Checked against every column, so a key column named `source_unit_id` is a clash too.
    own = (unit_column.lower(), period_column.lower())
    reserved = [key for key in KEYS if key not in own]
    if not isinstance(entry, str):  # the spine's key names here would be a second id or period
        spine = (cfg.data.keys.unit_id, cfg.data.keys.period)
        reserved += [key for key in spine if key.lower() not in own]
    log["renamed"] = rename_reserved(raw.columns, reserved, f"source {name!r}")
    for old, new in log["renamed"].items():
        print(f"source {name!r}: column {old!r} read as {new!r} (the framework names its key "
              f"{old.lower()!r}, or the spine's key column is so named)")  # fmt: skip
    keyed = (
        raw.withColumnsRenamed(log["renamed"])
        .withColumnRenamed(unit_column, "unit_id")
        .withColumnRenamed(period_column, "period")
        .withColumn("unit_id", F.col("unit_id").cast("string"))
        .withColumn("period", spec.spark_end(F.to_date("period")))
    )
    _check_unique_keys(keyed, name, log["period_tag"])
    log["columns"] = [column for column in keyed.columns if column not in KEYS]
    return keyed, log


def rename_reserved(columns: list[str], reserved: list[str], where: str) -> dict[str, str]:
    """`{column: "source_" + column}` for each column named like a reserved name ignoring case
    (Spark compares column names so), so the framework's own column of that name can sit beside
    it; a `source_<column>` already among them, in any case, fails naming both and `where` (a
    source, or the panel)."""
    lowered = {name.lower() for name in reserved}
    renamed = {column: f"source_{column}" for column in columns if column.lower() in lowered}
    present = {column.lower() for column in columns}
    taken = [(old, new) for old, new in renamed.items() if new.lower() in present]
    if taken:
        old, new = taken[0]
        raise ValueError(
            f"{where} has both {old!r} and {new!r}: the framework reads {old!r} as {new!r} "
            f"beside its own {old!r}; rename one of them upstream"
        )
    return renamed


def _check_key_columns(raw: DataFrame, name: str, unit_column: str, period_column: str) -> None:
    """Both key columns present and the period a date or timestamp."""
    missing = [column for column in (unit_column, period_column) if column not in raw.columns]
    if missing:
        raise ValueError(f"source {name!r} has no key column {missing}; its columns: {raw.columns}")
    period_type = raw.schema[period_column].dataType
    if not isinstance(period_type, PERIOD_TYPES):
        # e.g. a 'YYYY-MM' string or a 202406 integer: a format setting comes when a real
        # source needs one (D-129).
        raise TypeError(
            f"source {name!r}: the period column {period_column!r} is "
            f"{period_type.simpleString()}, not a date or timestamp"
        )


def _check_midnight(raw: DataFrame, name: str, period_column: str) -> None:
    """A timestamp period (an instant) is at 00:00 in the session time zone: one written at
    midnight in another zone shows another hour here and may land in the previous or next period.
    A date or a timestamp without time zone has no such shift."""
    if not isinstance(raw.schema[period_column].dataType, TimestampType):
        return
    period = F.col(period_column)
    # As a string, so the value is shown in the session time zone, not in Python's local one.
    not_midnight = raw.where(F.date_trunc("day", period) != period).select(period.cast("string"))
    off = not_midnight.limit(1).collect()
    if off:
        zone = raw.sparkSession.conf.get("spark.sql.session.timeZone")
        raise ValueError(
            f"source {name!r}: the timestamp period {period_column!r} holds {off[0][0]}, not at "
            f"00:00 in the session time zone {zone}, so its period may be wrong; store the period "
            "as a date or set the session time zone the source was written in"
        )


def _period_log(raw: DataFrame, name: str, period_column: str, spec: Period) -> dict:
    """The source's distinct periods (at their last day) and how it tagged them, from its
    distinct raw days (a small collect); the end is checked first, so a day period is always
    tagged "period end"."""
    days = [row[0] for row in raw.select(F.to_date(period_column)).distinct().collect()]
    if not days:
        raise ValueError(f"source {name!r} is empty")
    if None in days:
        raise ValueError(f"source {name!r} has rows with a null period; every row needs one")
    if all(day == spec.end(day) for day in days):
        tag = "period end"
    elif all(day == spec.start(day) for day in days):
        tag = "period start"
    elif all(day in (spec.start(day), spec.end(day)) for day in days):
        tag = "first and last days"
    else:
        tag = "other days"
    return {"source": name, "periods": sorted({spec.end(day) for day in days}), "period_tag": tag}


def missing_periods(periods: list[date], first: date, last: date, spec: Period) -> list[str]:
    """The periods from `first` to `last` (as labels) that `periods` lacks."""
    present = {spec.label(period) for period in periods}
    return [label for label in period_labels(first, last, spec) if label not in present]


def check_periods_covered(
    log: dict, first: date, last: date, role: str, until: str, spec: Period
) -> None:
    """A read source (its `log`) has every period from `first` to `last`, else it fails naming
    the source by its `role` and the missing periods; `until` says what `last` is in the config's
    terms."""
    missing = missing_periods(log["periods"], first, last, spec)
    if missing:
        raise ValueError(
            f"{role} {log['source']!r} lacks the periods {missing}; it must have every period "
            f"from {spec.label(first)} (time.observation_window.first) to {spec.label(last)} "
            f"({until})"
        )


def _check_unique_keys(keyed: DataFrame, name: str, period_tag: str) -> None:
    """No null `unit_id` (the forward window would take every such row for one unit) and no
    `(unit_id, period)` twice after the period move, so a source carrying both a first-day and a
    last-day row for one client-period fails too; a source tagged on other days than the
    period's first or last probably holds a finer period, which the error says."""
    repeated = (
        keyed.groupBy("unit_id", "period")
        .count()
        .filter("unit_id IS NULL OR count > 1")
        .orderBy(F.asc_nulls_first("unit_id"))  # a null unit id is named before any duplicate
        .limit(SHOWN_KEYS)
        .collect()
    )
    if any(row.unit_id is None for row in repeated):
        raise ValueError(f"source {name!r} has rows with a null unit id; every row needs one")
    if repeated:
        shown = ", ".join(f"({row.unit_id}, {row.period})" for row in repeated)
        hint = (
            "; its periods fall on other days than the period's first or last, so it probably "
            "holds a finer period than time.period (e.g. weekly rows on a monthly spine): "
            "aggregate it to time.period upstream"
        )
        raise ValueError(
            f"source {name!r} has duplicate (unit_id, period) keys after moving periods to their "
            f"last day, e.g. {shown}{hint if period_tag == 'other days' else ''}"
        )
