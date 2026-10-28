"""Target Factory: the target at each unit and month, from the unit's later months (§4.1).

The target source (`entities.<e>.sources.targets`, else the spine) is read keyed
(`sources.read_keyed_source`) and checked before any target is built: the target column exists
and its type and values suit the task (`TASK_SPECS`), and the source has every month from the
observation window's first to the validation month + w. With `data.target.rule` set, the task's
rule compares the value at t with the forward window t+1 … t+w of the same unit, the current
month never in it (T8) and `w` from config only (T13), a null read as `data.target.null_as` when
set; the target is null wherever the unit lacks any of the w months (the panel edge, a leaver, a
gap; D-029 (c)), and `null_in_window` says whether the raw column held a null at t or in the
window. Without a rule, the upstream `column` is the target, refused when it has values in the
source's last w months, where no such target can be known yet. Targets are built over every row
of the source, lazily in Spark; the dataset selects the eligible rows and joins them
(docs/components/target_factory.md). The lineage, the columns the target was built from, is
excluded from the candidates (T12).
"""

from datetime import timedelta

import pandas as pd
from pyspark.sql import Column, DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType, DataType

from core_modelling.config import UseCaseConfig
from core_modelling.environment import EnvironmentConfig
from core_modelling.sources import missing_months, month_number, read_keyed_source
from core_modelling.tasks import TASK_SPECS


def _month_index() -> Column:
    """Consecutive months as consecutive integers, so the forward window counts calendar months:
    a month the unit has no row for is a gap, never skipped. Never `add_months` (T19)."""
    return F.year("month") * 12 + F.month("month")


def _literal_like(null_as: int | float, column_type: DataType) -> Column:
    """`null_as` as a literal `coalesce` accepts beside the column: cast for a boolean flag (0 / 1
    as false / true); a numeric column widens on its own, so no cast can truncate a value."""
    literal = F.lit(null_as)
    return literal.cast("boolean") if isinstance(column_type, BooleanType) else literal


def build_targets(source: DataFrame, cfg: UseCaseConfig) -> DataFrame:
    """The target of every row of a keyed source by the task's rule, lazily: exactly `unit_id`,
    `month`, `target`, `null_in_window` (for a complete window: the raw column had a null at t or
    in the window; false where the window is incomplete)."""
    spec = cfg.data.target
    if spec.leavers == "negative":
        raise NotImplementedError(
            "data.target.leavers 'negative' is not implemented until M4 (D-091); leave it null "
            "so leavers get a null target"
        )
    rules = TASK_SPECS[cfg.task]["target_rules"]
    if spec.rule not in rules:
        raise ValueError(
            f"unknown target rule {spec.rule!r} for task {cfg.task!r}; its rules: {sorted(rules)}"
        )
    w = cfg.time.target_window_months
    forward = Window.partitionBy("unit_id").orderBy(_month_index()).rangeBetween(1, w)
    raw = F.col(spec.column)
    value = raw
    if spec.null_as is not None:
        value = F.coalesce(raw, _literal_like(spec.null_as, source.schema[spec.column].dataType))
    complete = F.count(F.lit(1)).over(forward) == w  # rows: a leaver or a gap gives null
    target = F.when(complete, rules[spec.rule](value, forward))
    known_in_window = F.count(raw).over(forward)
    null_in_window = complete & (raw.isNull() | (known_in_window < w))
    return source.select(
        "unit_id", "month", target.alias("target"), null_in_window.alias("null_in_window")
    )


def _check_target_column(source: DataFrame, cfg: UseCaseConfig, name: str) -> None:
    """The target column is in the source and the task can read it (a 0/1 flag, an amount)."""
    column = cfg.data.target.column
    if column not in source.columns:
        raise ValueError(
            f"target source {name!r} has no target column {column!r}; its columns: {source.columns}"
        )
    TASK_SPECS[cfg.task]["check_target_column"](source, column, name, cfg.data.target.null_as)


def _check_months_covered(log: dict, cfg: UseCaseConfig) -> None:
    """The target source has every month from the window's first to the validation month + w: a
    gap nulls the targets of the w months before it, and a source ending before v + w leaves the
    validation month's targets immature. The months between tk + w and v are required too,
    though no target needs them: one unbroken range is simpler, and real panels have them."""
    time = cfg.time
    last = time.validation_month.replace(day=1)
    for _ in range(time.target_window_months):  # v + w, month by month (never add_months, T19)
        last = (last.replace(day=28) + timedelta(days=4)).replace(day=1)
    missing = missing_months(log["months"], time.train_months.first, last)
    if missing:
        raise ValueError(
            f"target source {log['source']!r} lacks the months {missing}; it must have every "
            f"month from time.train_months.first ({time.train_months.first:%Y-%m}) to "
            f"time.validation_month + target_window_months"
        )


def _check_upstream_tail(source: DataFrame, cfg: UseCaseConfig, log: dict) -> None:
    """An upstream target has no value in the source's last w months, where a target over
    t+1 … t+w can't be known yet, and some value in the month before them, where it is (§4.1
    can't be checked on an upstream target otherwise; a longer upstream window would overlap the
    validation month's, §4.2)."""
    column, w = cfg.data.target.column, cfg.time.target_window_months
    end = month_number(log["months"][-1])
    tail = [month for month in log["months"] if month_number(month) > end - w]
    known = F.col(column).isNotNull()
    if source.where(F.col("month").isin(tail) & known).limit(1).count():
        raise ValueError(
            f"upstream target {column!r} of {log['source']!r} has values in the source's last "
            f"{w} months ({tail[0]} … {tail[-1]}), where a target over t+1 … t+{w} can't be "
            "known yet: upstream either fills immature labels or uses another window than "
            f"time.target_window_months ({w})"
        )
    before_tail = log["months"][-w - 1]
    if not source.where((F.col("month") == before_tail) & known).limit(1).count():
        raise ValueError(
            f"upstream target {column!r} of {log['source']!r} has no value in {before_tail}, the "
            f"last month where a target over t+1 … t+{w} is known: the upstream window seems "
            f"longer than time.target_window_months ({w})"
        )


def load_targets(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession
) -> tuple[DataFrame, dict]:
    """The targets of `entity`'s target source (the spine when `targets` is omitted), built by the
    rule or taken from the upstream column, with the source's log."""
    if entity not in cfg.entities:
        raise ValueError(f"unknown entity {entity!r}: the config has {sorted(cfg.entities)}")
    sources = cfg.entities[entity].sources
    name = sources.targets or sources.features[0]  # the first feature source is the spine (D-129)
    source, log = read_keyed_source(cfg, entity, name, env, spark)
    _check_target_column(source, cfg, name)
    _check_months_covered(log, cfg)
    if cfg.data.target.rule is None:
        _check_upstream_tail(source, cfg, log)
        column = F.col(cfg.data.target.column)
        if isinstance(source.schema[cfg.data.target.column].dataType, BooleanType):
            column = column.cast("int")  # a boolean flag as 0/1, like a built target
        upstream = column.alias("target")
        unknown = F.lit(None).cast("boolean").alias("null_in_window")  # upstream built it
        return source.select("unit_id", "month", upstream, unknown), log
    return build_targets(source, cfg), log


def target_lineage(cfg: UseCaseConfig) -> list[str]:
    """The columns the target is built from, excluded from the candidates: `column`, then the
    config's `lineage`, without repeats."""
    return list(dict.fromkeys([cfg.data.target.column, *cfg.data.target.lineage]))


def run_target_factory(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession
) -> pd.DataFrame:
    """The task's target summary over every month of the target source, printed and returned;
    writes nothing (the model input is saved by `save_model_input`)."""
    targets, log = load_targets(cfg, entity, env, spark)
    window = cfg.time.train_months
    summary = TASK_SPECS[cfg.task]["summarise_targets"](targets, window.first, window.last)
    print(
        f"the targets of every row of {log['source']}; label columns for the observation window "
        "only; before eligibility, which the dataset applies; null_value_share: rows whose window "
        "held a null in the target column (unknown for an upstream target)"
    )
    print(summary.to_string(index=False))
    return summary
