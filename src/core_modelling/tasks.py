"""The per-task spec: every task-specific choice, by `task`, in one dict (D-050).

A stage that does something differently for binary and regression looks the choice up in
`TASK_SPECS[cfg.task]` instead of branching on the task. Stage 1 holds the target rules, the
target column check and the target summary (Target Factory) and the contract checks (the
dataset).

A target rule compares a unit's value at period t with its values in periods t+1 … t+w and
returns the target at t as a Column. It gets the target column and the forward window over
those periods (`target_factory.build_targets` builds it, so the time separation of §4.1 lives in
one place); `build_targets` nulls the target where the unit lacks any of the w periods. Nulls
follow SQL semantics: a null is ignored, never an event, and the target is null only when nothing
can be compared; a source that codes zeros as nulls fills them upstream. Stage 1 has a flag rule
only; the count and amount rules (`count_goes_up`, thresholds) are separate rules for M4 (D-091).
A column check refuses a target column whose type or values the task can't read, before any
target is built. A summary turns the targets frame into a small pandas table: one row per
period (labelled by the period spec) plus an `all` row, from one Spark aggregate, with label
rates for the observation window only. A
contract check runs on the eligible rows of the observation window before any sampling (§4.8),
returns its log entry and raises with its numbers when the window can't be modelled.

Stage 2 adds what EDA and Feature Checks read (D-050, A28, A29): the target bins of the counts
table, the group summary (binary: positive events, the rate with its Wilson interval; regression:
units with a non-zero target, the mean with its t-interval and the median, the non-zero share),
the rare effect (a rate or mean ratio), the concordance's standard error, the events warning, the
support's name, the target's headline (`base_rate_views`), the shrinkage of the level encoding
and whether a lift exists: a ratio to a mean needs a positive mean, so a regression target whose
mean is not positive shows "not available: mean not positive", decided before anything runs
(D-035, V8). Both tasks share one rule where the formula is the same (the lift test).
"""

from functools import partial

import numpy as np
import pandas as pd
from pyspark.sql import Column, DataFrame, WindowSpec
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType, DoubleType, FloatType, NumericType

from core_modelling.config import UseCaseConfig
from core_modelling.periods import label_by_period, period_spec
from core_modelling.statistics.concordance import concordance_se, kendall_null_se
from core_modelling.statistics.distributions import quantile_edges
from core_modelling.statistics.intervals import t_interval, wilson_interval

SHOWN_VALUES = 3  # bad target values named in the error
WINDOW_TARGET = "window_target"  # the summary's target in the observation window, else null
TARGET_BINS = 20  # quantile bins of a regression target in the counts table
EVENTS_WARNING = 500  # fewer events (units with a non-zero target) in the snapshot: a warning
BINARY_SUPPORT = "positive events"  # what the concordance's support counts, per task
REGRESSION_SUPPORT = "units with a non-zero target"


def _flag_goes_up(value: Column, forward: WindowSpec) -> Column:
    """1 when the flag is 1 in some period t+1 … t+w and 0 at t (D-029 (c)), else 0, a holder at
    t included; null when the flag at t is null or no forward flag is known."""
    return (F.max(value).over(forward) > value).cast("int")


def _forward_sum(value: Column, forward: WindowSpec) -> Column:
    """The sum over periods t+1 … t+w, nulls skipped; null when none of them is known."""
    return F.sum(value).over(forward)


def _check_flag_column(source: DataFrame, column: str, name: str) -> None:
    """A 0/1 flag: boolean, or numeric holding only 0, 1 and nulls (NaN refused)."""
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


def _check_amount_column(source: DataFrame, column: str, name: str) -> None:
    """An amount: numeric, and no NaN in a float or double column."""
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


def _summarise(targets: DataFrame, cfg: UseCaseConfig, extra: dict[str, Column]) -> pd.DataFrame:
    """Per period (labelled by the period spec) plus an `all` row, from one rollup: rows, the
    null share and, among the complete windows, the share of rows whose window held a null in
    the target column (`null_in_window`, label-free) of every period; the mean target and the
    `extra` label aggregates (over `WINDOW_TARGET`) for the observation window's periods only,
    the `all` row's over those periods too, so a later period's label rate, the validation
    period's among them, is never shown (§4.4, D-030)."""
    window = cfg.time.observation_window
    in_window = F.col("period").between(window.first, window.last)
    shown = F.max(in_window)  # the group holds a window period: false for a later period
    labels = {"mean_target": F.avg(F.col(WINDOW_TARGET).cast("double")), **extra}
    table = (
        targets.withColumn(WINDOW_TARGET, F.when(in_window, F.col("target")))
        .rollup("period")
        .agg(
            F.grouping("period").alias("_all"),
            F.count(F.lit(1)).alias("rows"),
            (1 - F.count("target") / F.count(F.lit(1))).alias("null_share"),
            F.avg(F.col("null_in_window").cast("double")).alias("null_value_share"),
            *[F.when(shown, aggregate).alias(name) for name, aggregate in labels.items()],
        )
        .orderBy("_all", "period")
        .toPandas()
    )
    is_all = table.pop("_all") == 1
    label = period_spec(cfg).label
    table["period"] = table["period"].map(label, na_action="ignore").where(~is_all, "all")
    return table


def _binary_summary(targets: DataFrame, cfg: UseCaseConfig) -> pd.DataFrame:
    """The summary (rows, null shares, the mean target) with the positive rows and the positive
    events: the distinct units with a positive target, equal to the positive rows in one period
    and fewer over several, since one conversion is positive in up to w consecutive periods
    (D-082)."""
    positive = F.col(WINDOW_TARGET) == 1
    extra = {
        "positive_rows": F.count(F.when(positive, True)),
        "positive_events": F.countDistinct(F.when(positive, F.col("unit_id"))),
    }
    return _summarise(targets, cfg, extra)


def _regression_summary(targets: DataFrame, cfg: UseCaseConfig) -> pd.DataFrame:
    """The summary: rows, the null share, the null-value share and the mean target."""
    return _summarise(targets, cfg, {})


def _check_flag_target(eligible: DataFrame, cfg: UseCaseConfig) -> dict:
    """Both classes present, and the pooled positive rate at or below `data.rate_band.max`,
    reported per period (rows, as a prevalence, null without a known target; the events are in
    the target summary, D-082)."""
    by_period = (
        eligible.groupBy("period")
        .agg(
            F.count("target").alias("known"),
            F.sum("target").alias("positives"),
            F.avg("target").alias("rate"),  # null in a period without a known target
        )
        .orderBy("period")
        .collect()
    )
    known = sum(row.known for row in by_period)
    positives = sum(row.positives or 0 for row in by_period)
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
    per_period = label_by_period(by_period, "rate", period_spec(cfg))
    return {"check": "positive_rate", "rate": rate, "max": ceiling, "positive_rows": positives,
            "known": known, "per_period": per_period}  # fmt: skip


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


def _binary_target_bins(known: np.ndarray, exact: bool) -> None:
    """None: a 0/1 target's two values are its bins (`"0"`, `"1"`)."""
    return None


def _regression_target_bins(known: np.ndarray, exact: bool) -> np.ndarray:
    """The edges of `TARGET_BINS` quantile bins of the known targets (every value a bin when
    `exact`), 0 always its own bin, so the units with a non-zero target are a sum of cells."""
    known = np.asarray(known, dtype=float)
    edges = quantile_edges(known, np.unique(known).size if exact else TARGET_BINS)
    return np.unique(np.concatenate([edges, [0.0, np.nextafter(0.0, np.inf)]]))


def _known_values(target: pd.Series) -> np.ndarray:
    """The targets as floats: at least one, none null."""
    if target.empty or target.isna().any():
        raise ValueError("expected known targets: no nulls, not empty")
    return target.to_numpy(dtype=float)


def _lift_available(base: float) -> bool:
    """A lift (a ratio to the base) exists only over a positive base rate or mean (V8)."""
    return base > 0


def _with_lift(summary: dict[str, float], base: float) -> dict[str, float]:
    """The summary with `lift = estimate / base` when the base allows it, else without."""
    if _lift_available(base):
        summary["lift"] = summary["estimate"] / base
    return summary


def _binary_group(target: pd.Series, base: float) -> dict[str, float]:
    """Rows, support (positive rows: the events on a one-period snapshot), the rate with its
    Wilson interval, and the lift."""
    values = _known_values(target)
    rows, positives = values.size, float(values.sum())
    low, high = wilson_interval(positives, rows)
    summary = {"rows": rows, "support": positives, "estimate": positives / rows}
    return _with_lift({**summary, "low": low, "high": high}, base)


def _regression_group(target: pd.Series, base: float) -> dict[str, float]:
    """Rows, support (units with a non-zero target), the mean with its t-interval (none from one
    row) and the median, the lift, and the non-zero share (Wilson) with the non-zero mean and
    median (NaN when every target is 0)."""
    values = _known_values(target)
    nonzero = values[values != 0]
    nan = float("nan")
    low, high = (nan, nan)
    if values.size > 1:
        low, high = t_interval(values.mean(), values.std(ddof=1), values.size)
    share_low, share_high = wilson_interval(nonzero.size, values.size)
    summary = {
        "rows": values.size, "support": nonzero.size, "estimate": float(values.mean()),
        "low": low, "high": high, "median": float(np.median(values)),
        "nonzero_share": nonzero.size / values.size, "nonzero_low": share_low,
        "nonzero_high": share_high,
        "nonzero_mean": float(nonzero.mean()) if nonzero.size else nan,
        "nonzero_median": float(np.median(nonzero)) if nonzero.size else nan,
    }  # fmt: skip
    return _with_lift(summary, base)


def _rate_ratio(cell: float, rest: float) -> float:
    """The rare effect: a cell's rate over the rest's; a positive cell over a zero rest is
    infinite and nothing over nothing is 1 (no difference). Call only when `lift_available`."""
    if rest != 0:
        return cell / rest
    return 1.0 if cell == 0 else float(np.inf)


def _mean_ratio(cell: float, rest: float) -> float:
    """The rare effect: a cell's mean over the rest's. Call only when `lift_available(base)` and
    the rest's mean is positive; the caller decides "not available" up front (D-035)."""
    if not rest > 0:
        raise ValueError(
            f"rare_effect: the rest's mean {rest} is not positive, so no mean ratio exists; "
            'decide "not available" before calling'
        )
    return cell / rest


def _regression_se(value: float, events: float, non_events: float) -> float:
    """Kendall's null standard error over every unit, halved (A29)."""
    return kendall_null_se(events + non_events)


def _events_warning(events: int, support: str) -> str | None:
    """The snapshot's events warning, or None when it holds `EVENTS_WARNING` events or more."""
    if events >= EVENTS_WARNING:
        return None
    return (
        f"{events} {support} in the snapshot, fewer than {EVENTS_WARNING}: the concordance's "
        "third decimal is noise"
    )


def _binary_headline(target: pd.Series) -> dict[str, float]:
    """The snapshot's rows, positive rows and base rate with its Wilson interval."""
    values = _known_values(target)
    positives = float(values.sum())
    low, high = wilson_interval(positives, values.size)
    return {"rows": values.size, "positives": positives, "rate": positives / values.size,
            "low": low, "high": high}  # fmt: skip


def _regression_headline(target: pd.Series) -> dict[str, float]:
    """The snapshot's rows, mean, median, p10, p90, zero share and units with a non-zero target."""
    values = _known_values(target)
    p10, median, p90 = np.quantile(values, [0.1, 0.5, 0.9])
    zeros = int((values == 0).sum())
    return {"rows": values.size, "mean": float(values.mean()), "median": float(median),
            "p10": float(p10), "p90": float(p90), "zero_share": zeros / values.size,
            "nonzero_units": values.size - zeros}  # fmt: skip


def _binary_shrinkage_rows(min_events: int, base: float) -> float:
    """`strata.min_events / base_rate`: the prior weighs `min_events` pseudo-events (A30)."""
    if base <= 0:
        raise ValueError(f"shrinkage_rows: the base rate must be positive, got {base}")
    return min_events / base


def _regression_shrinkage_rows(min_events: int, base: float) -> float:
    """`strata.min_events` rows (A30)."""
    return float(min_events)


TASK_SPECS = {
    "binary": {
        "target_rules": {"flag_goes_up": _flag_goes_up},
        "check_target_column": _check_flag_column,
        "summarise_targets": _binary_summary,
        "contract_checks": [_check_flag_target],
        "target_bins": _binary_target_bins,
        "summarise_group": _binary_group,
        "rare_effect": _rate_ratio,
        "concordance_se": concordance_se,
        "events_warning": partial(_events_warning, support=BINARY_SUPPORT),
        "support_name": BINARY_SUPPORT,
        "base_rate_views": _binary_headline,
        "shrinkage_rows": _binary_shrinkage_rows,
        "lift_available": _lift_available,
    },
    "regression": {
        "target_rules": {"forward_sum": _forward_sum},
        "check_target_column": _check_amount_column,
        "summarise_targets": _regression_summary,
        "contract_checks": [_check_amount_target],
        "target_bins": _regression_target_bins,
        "summarise_group": _regression_group,
        "rare_effect": _mean_ratio,
        "concordance_se": _regression_se,
        "events_warning": partial(_events_warning, support=REGRESSION_SUPPORT),
        "support_name": REGRESSION_SUPPORT,
        "base_rate_views": _regression_headline,
        "shrinkage_rows": _regression_shrinkage_rows,
        "lift_available": _lift_available,
    },
}
