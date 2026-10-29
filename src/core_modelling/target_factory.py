"""Target Factory: the target at each unit and period, from the unit's later periods (§4.1).

The target source (`entities.<e>.sources.targets`, else the spine) is read keyed
(`sources.read_keyed_source`) and checked before any target is built: the target column exists
and its type and values suit the task (`TASK_SPECS`), and the source has every period from the
observation window's first to the validation period + w. With `data.target.rule` set, the task's
rule compares the value at t with the forward window t+1 … t+w of the same unit, counted by the
period spec's index (`periods.py`: a month, a week or a day, never `add_months`, T19), the
current period never in it (T8) and `w` from config only (T13); the target is null wherever the
unit lacks any of the w periods (the panel edge, a leaver, a gap; D-029 (c)); a null value
follows SQL semantics (never an event; a null target when nothing can be compared) and is the
source's business to fill, while `null_in_window` says whether the raw column held one at t or
in the window, and is null where the window is incomplete, so its average is the share among
complete windows. Without a rule, the upstream `column` is the target, refused when it has
values in the source's last w periods, where no such target can be known yet. Targets are built
over every row of the source, lazily in Spark, so every period with a complete window carries
its label; the dataset selects the eligible rows and joins them
(docs/components/target_factory.md). The lineage, the columns the target was built from, is
excluded from the candidates (T12).
"""

import pandas as pd
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType

from core_modelling.config import UseCaseConfig
from core_modelling.environment import EnvironmentConfig
from core_modelling.periods import period_spec
from core_modelling.sources import check_periods_covered, read_keyed_source
from core_modelling.tasks import TASK_SPECS


def build_targets(source: DataFrame, cfg: UseCaseConfig) -> DataFrame:
    """The target of every row of a keyed source by the task's rule, lazily: exactly `unit_id`,
    `period`, `target`, `null_in_window` (for a complete window: the raw column had a null at t or
    in the window; null where the window is incomplete)."""
    rule, column = cfg.data.target.rule, cfg.data.target.column
    rules = TASK_SPECS[cfg.task]["target_rules"]
    if rule not in rules:
        raise ValueError(
            f"unknown target rule {rule!r} for task {cfg.task!r}; its rules: {sorted(rules)}"
        )
    w = cfg.time.target_window
    # Consecutive periods as consecutive integers: a period the unit has no row for is a gap,
    # never skipped.
    period_index = period_spec(cfg).spark_index(F.col("period"))
    forward = Window.partitionBy("unit_id").orderBy(period_index).rangeBetween(1, w)
    value = F.col(column)
    complete = F.count(F.lit(1)).over(forward) == w  # rows: a leaver or a gap gives null
    target = F.when(complete, rules[rule](value, forward))
    known_in_window = F.count(value).over(forward)
    null_in_window = F.when(complete, value.isNull() | (known_in_window < w))
    return source.select(
        "unit_id", "period", target.alias("target"), null_in_window.alias("null_in_window")
    )


def _check_target_column(source: DataFrame, cfg: UseCaseConfig, name: str) -> None:
    """The target column is in the source and the task can read it (a 0/1 flag, an amount)."""
    column = cfg.data.target.column
    if column not in source.columns:
        raise ValueError(
            f"target source {name!r} has no target column {column!r}; its columns: {source.columns}"
        )
    TASK_SPECS[cfg.task]["check_target_column"](source, column, name)


def _check_upstream_tail(source: DataFrame, cfg: UseCaseConfig, log: dict) -> None:
    """An upstream target has no value in the source's last w periods, where a target over
    t+1 … t+w can't be known yet, and some value in the period before them, where it is (§4.1
    can't be checked on an upstream target otherwise; a longer upstream window would overlap the
    validation period's, §4.2)."""
    spec = period_spec(cfg)
    column, w = cfg.data.target.column, cfg.time.target_window
    end = spec.index(log["periods"][-1])
    tail = [period for period in log["periods"] if spec.index(period) > end - w]
    known = F.col(column).isNotNull()
    if source.where(F.col("period").isin(tail) & known).limit(1).count():
        raise ValueError(
            f"upstream target {column!r} of {log['source']!r} has values in the source's last "
            f"{w} periods ({spec.label(tail[0])} … {spec.label(tail[-1])}), where a target over "
            f"t+1 … t+{w} can't be known yet: upstream either fills immature labels or uses "
            f"another window than time.target_window ({w})"
        )
    before_tail = spec.from_index(end - w)  # by index: a gap after v + w is allowed
    if not source.where((F.col("period") == before_tail) & known).limit(1).count():
        raise ValueError(
            f"upstream target {column!r} of {log['source']!r} has no value in "
            f"{spec.label(before_tail)}, the last period where a target over t+1 … t+{w} is "
            f"known: the upstream window seems longer than time.target_window ({w})"
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
    # Every period up to v + w: a gap nulls the w targets before it, a source ending earlier
    # leaves the validation period's labels immature (one unbroken range; real panels have it).
    spec, time = period_spec(cfg), cfg.time
    matured = spec.from_index(spec.index(time.validation_period) + time.target_window)
    check_periods_covered(log, time.observation_window.first, matured, "target source",
                          "time.validation_period + target_window", spec)  # fmt: skip
    if cfg.data.target.rule is None:
        _check_upstream_tail(source, cfg, log)
        column = F.col(cfg.data.target.column)
        if isinstance(source.schema[cfg.data.target.column].dataType, BooleanType):
            column = column.cast("int")  # a boolean flag as 0/1, like a built target
        upstream = column.alias("target")
        unknown = F.lit(None).cast("boolean").alias("null_in_window")  # upstream built it
        return source.select("unit_id", "period", upstream, unknown), log
    return build_targets(source, cfg), log


def target_lineage(cfg: UseCaseConfig) -> list[str]:
    """The columns the target is built from, excluded from the candidates: `column`, then the
    config's `lineage`, without repeats."""
    return list(dict.fromkeys([cfg.data.target.column, *cfg.data.target.lineage]))


def run_target_factory(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession
) -> pd.DataFrame:
    """The task's target summary over every period of the target source, printed and returned;
    writes nothing (the model input is saved by `save_model_input`)."""
    targets, log = load_targets(cfg, entity, env, spark)
    summary = TASK_SPECS[cfg.task]["summarise_targets"](targets, cfg)
    print(
        f"the targets of every row of {log['source']}, null where the forward window is "
        "incomplete; label columns for the observation window only; before eligibility, which "
        "the dataset applies; null_value_share: rows whose window held a null in the target "
        "column, among the complete windows (unknown for an upstream target)"
    )
    print(summary.to_string(index=False))
    return summary
