"""The per-task spec: every task-specific choice, by `task`, in one dict (D-050).

A stage that does something differently for binary and regression looks the choice up in
`TASK_SPECS[cfg.task]` instead of branching on the task. Stage 1 holds the target rules, the
target column check and the target summary (Target Factory) and the contract checks (the
dataset).

A target rule compares a unit's value at month t with its values in months t+1 … t+w and
returns the target at t as a Column. It gets the value (the target column, `null_as` already
applied) and the forward window over those months (`target_factory.build_targets` builds it, so
the time separation of §4.1 lives in one place); `build_targets` nulls the target where the
unit lacks any of the w months. Nulls follow SQL semantics: a null is ignored, never an event, and
the target is null only when nothing can be compared. Stage 1 has a flag rule only; the count and
amount rules (`count_goes_up`, thresholds) are separate rules for M4 (D-091). A column check
refuses a target column whose type or values the task can't read, before any target is built. A
summary turns the targets frame into a small pandas table: one row per month plus an `all` row,
from one Spark aggregate, with label rates for the observation window only. A contract check
runs on the eligible rows of the observation window before any sampling (§4.8), returns its log
entry and raises with its numbers when the window can't be modelled.
"""

from datetime import date

import pandas as pd
from pyspark.sql import Column, DataFrame, WindowSpec
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType, DoubleType, FloatType, NumericType

from core_modelling.config import UseCaseConfig

SHOWN_VALUES = 3  # bad target values named in the error
WINDOW_TARGET = "window_target"  # the summary's target in the observation window, else null


def _flag_goes_up(value: Column, forward: WindowSpec) -> Column:
    """1 when the flag is 1 in some month t+1 … t+w and 0 at t (D-029 (c)), else 0, a holder at t
    included; null when the flag at t is null or no forward flag is known."""
    return (F.max(value).over(forward) > value).cast("int")


def _forward_sum(value: Column, forward: WindowSpec) -> Column:
    """The sum over months t+1 … t+w, nulls skipped; null when none of them is known."""
    return F.sum(value).over(forward)


def _check_flag_column(
    source: DataFrame, column: str, name: str, null_as: int | float | None
) -> None:
    """A 0/1 flag: boolean, or numeric holding only 0, 1 and nulls (NaN refused); a null reads as
    0 or 1 at most."""
    if null_as not in (None, 0, 1):
        raise ValueError(
            f"data.target.null_as {null_as!r} is not a flag value; a null in {column!r} reads as "
            "0, 1 or stays null"
        )
    column_type = source.schema[column].dataType
    if isinstance(column_type, BooleanType):
        return
    if not isinstance(column_type, NumericType):
        raise TypeError(
            f"source {name!r}: the target column {column!r} is {column_type.simpleString()}, "
            "not a 0/1 flag (boolean or numeric)"
        )
    value = F.col(column)
    bad = source.where(value.isNotNull() & ~value.isin(0, 1)).select(column).distinct()
    shown = [row[0] for row in bad.limit(SHOWN_VALUES).collect()]
    if shown:
        raise ValueError(
            f"source {name!r}: the target column {column!r} must hold only 0, 1 and nulls; "
            f"it also holds e.g. {shown}"
        )


def _check_amount_column(
    source: DataFrame, column: str, name: str, null_as: int | float | None
) -> None:
    """An amount: numeric, and no NaN in a float or double column; a null reads as any number."""
    column_type = source.schema[column].dataType
    if not isinstance(column_type, NumericType):
        raise TypeError(
            f"source {name!r}: the target column {column!r} is {column_type.simpleString()}, "
            "not numeric"
        )
    if isinstance(column_type, FloatType | DoubleType):
        if source.where(F.isnan(column)).limit(1).count():
            raise ValueError(
                f"source {name!r}: the target column {column!r} holds NaN; a missing amount "
                "must be null"
            )


def _summarise(
    targets: DataFrame, first: date, last: date, extra: dict[str, Column]
) -> pd.DataFrame:
    """Per month plus an `all` row, from one rollup: rows, the null share and the share of rows
    whose window held a null in the target column (`null_in_window`, label-free) of every month;
    the mean target and the `extra` label aggregates (over `WINDOW_TARGET`) for the months `first`
    … `last` only, the `all` row's over those months too, so a later month's label rate, the
    validation month's among them, is never shown (§4.4, D-030)."""
    in_window = F.col("month").between(first, last)
    shown = F.max(in_window)  # the group holds a window month: false for a later month
    labels = {"mean_target": F.avg(F.col(WINDOW_TARGET).cast("double")), **extra}
    table = (
        targets.withColumn(WINDOW_TARGET, F.when(in_window, F.col("target")))
        .rollup("month")
        .agg(
            F.grouping("month").alias("_all"),
            F.count(F.lit(1)).alias("rows"),
            (1 - F.count("target") / F.count(F.lit(1))).alias("null_share"),
            F.avg(F.col("null_in_window").cast("double")).alias("null_value_share"),
            *[F.when(shown, aggregate).alias(name) for name, aggregate in labels.items()],
        )
        .orderBy("_all", "month")
        .toPandas()
    )
    is_all = table.pop("_all") == 1
    table["month"] = table["month"].astype(str).where(~is_all, "all")
    return table


def _binary_summary(targets: DataFrame, first: date, last: date) -> pd.DataFrame:
    """The summary (rows, null shares, the mean target) with the positive rows and the positive
    events: the distinct units with a positive target, equal to the positive rows in one month and
    fewer over several, since one conversion is positive in up to w consecutive months (D-082)."""
    positive = F.col(WINDOW_TARGET) == 1
    extra = {
        "positive_rows": F.count(F.when(positive, True)),
        "positive_events": F.countDistinct(F.when(positive, F.col("unit_id"))),
    }
    return _summarise(targets, first, last, extra)


def _regression_summary(targets: DataFrame, first: date, last: date) -> pd.DataFrame:
    """The summary: rows, the null share, the null-value share and the mean target."""
    return _summarise(targets, first, last, {})


def _check_flag_target(eligible: DataFrame, cfg: UseCaseConfig) -> dict:
    """Both classes present, and the pooled positive rate at or below `data.rate_band.max`,
    reported per month (rows, as a prevalence; the events are in the target summary, D-082)."""
    by_month = (
        eligible.groupBy("month")
        .agg(F.count("target").alias("known"), F.sum("target").alias("positives"))
        .orderBy("month")
        .collect()
    )
    known = sum(row.known for row in by_month)
    positives = sum(row.positives or 0 for row in by_month)
    if known == 0 or positives in (0, known):
        raise ValueError(
            f"the target is constant on the eligible window: {positives} positive rows in "
            f"{known} known rows; both classes are needed"
        )
    rate, ceiling = positives / known, cfg.data.rate_band.max
    if rate > ceiling:
        raise ValueError(
            f"the eligible window's positive rate {rate:.4f} is above data.rate_band.max "
            f"{ceiling}: {positives} positive rows in {known} known rows"
        )
    per_month = {f"{r.month:%Y-%m}": (r.positives or 0) / r.known for r in by_month if r.known}
    return {"check": "positive_rate", "rate": rate, "max": ceiling, "positive_rows": positives,
            "known": known, "per_month": per_month}  # fmt: skip


def _check_amount_target(eligible: DataFrame, cfg: UseCaseConfig) -> dict:
    """A finite, non-constant target."""
    target = F.col("target").cast("double")
    not_finite = F.isnan(target) | (F.abs(target) == float("inf"))
    stats = eligible.agg(
        F.count("target").alias("known"),
        F.count(F.when(not_finite, True)).alias("not_finite"),
        F.min(target).alias("min"),
        F.max(target).alias("max"),
    ).collect()[0]
    if stats.not_finite:
        raise ValueError(
            f"the target holds {stats.not_finite} NaN or infinite values on the eligible window"
        )
    if stats.known == 0 or stats.min == stats.max:
        raise ValueError(
            f"the target is constant ({stats.min}) on the eligible window's {stats.known} known "
            "rows"
        )
    return {"check": "target_range", "known": stats.known, "min": stats.min, "max": stats.max}


TASK_SPECS = {
    "binary": {
        "target_rules": {"flag_goes_up": _flag_goes_up},
        "check_target_column": _check_flag_column,
        "summarise_targets": _binary_summary,
        "contract_checks": [_check_flag_target],
    },
    "regression": {
        "target_rules": {"forward_sum": _forward_sum},
        "check_target_column": _check_amount_column,
        "summarise_targets": _regression_summary,
        "contract_checks": [_check_amount_target],
    },
}
