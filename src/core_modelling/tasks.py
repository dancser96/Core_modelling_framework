"""The per-task spec: every task-specific choice, by `task`, in one dict (D-050).

A stage that does something differently for binary and regression looks the choice up in
`TASK_SPECS[cfg.task]` instead of branching on the task; both tasks share one function where the
formula is the same (the lift test). Target Factory and the dataset read the target rules, the
target column check, the target summary and occurrences and the contract checks. EDA and Feature
Checks read the rest (A28, A29): the counts table's target bins, the group summary and the
per-period estimate with their intervals, the rare effect, the concordance from cells and its
SE, the support in effective clients and its name, the events warning, the headline, the level
encoding's shrinkage, whether a lift exists, the target class and how an estimate is printed
and named.

A target rule compares a unit's value at period t with its values in t+1 … t+w and returns the
target at t as a Column, from the target column and the forward window that
`target_factory.build_targets` builds (so §4.1's time separation lives in one place; it nulls
the target where the unit lacks any of the w periods). Nulls follow SQL semantics: a null is
ignored, never an event, and the target is null only when nothing can be compared; a source that
codes zeros as nulls fills them upstream. The count and amount-threshold rules (`count_goes_up`,
thresholds) are separate rules for M4 (D-091). A column check refuses a target column whose type
or values the task cannot read, before any target is built. A contract check runs on the
eligible rows of the observation window before any sampling (§4.8), returns its log entry and
raises with its numbers when the window cannot be modelled. A lift is a ratio to the base, so a
regression target whose mean is not positive shows "not available: mean not positive", decided
before anything runs (D-035, V8).
"""

from collections.abc import Callable
from functools import partial

import numpy as np
import pandas as pd
from pyspark.sql import Column, DataFrame, Window, WindowSpec
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType, DoubleType, FloatType, NumericType

from core_modelling.config import UseCaseConfig
from core_modelling.periods import label_by_period, period_spec
from core_modelling.statistics.cells import two_way_table
from core_modelling.statistics.concordance import (
    concordance_exact,
    concordance_from_table,
    concordance_se,
    effective_count,
    kendall_null_se,
)
from core_modelling.statistics.distributions import (
    cohens_d,
    cohens_h,
    d_unavailable,
    h_unavailable,
    quantile_edges,
    variance_from_sums,
)
from core_modelling.statistics.intervals import t_interval, wilson_interval

SHOWN_VALUES = 3  # bad target values named in the error
TARGET_BINS = 20  # quantile bins of a regression target in the counts table
EVENTS_WARNING = 500  # fewer events (units with a non-zero target) in the snapshot: a warning
BINARY_SUPPORT = "positive events"  # what the concordance's support counts, per task
REGRESSION_SUPPORT = "units with a non-zero target"
# A group table's summary columns every task shares; `summary_columns` per task adds its own, so
# a table keeps its schema whatever the data (an empty one included).
SUMMARY_COLUMNS = ["rows", "support", "estimate", "low", "high", "lift", "insufficient"]
AMOUNT_SUMMARY_COLUMNS = [*SUMMARY_COLUMNS, "median", "nonzero_share", "nonzero_low",
                          "nonzero_high", "nonzero_mean", "nonzero_median"]  # fmt: skip


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


def _label_aggregates(
    target: Column, extra: Callable[[Column], dict[str, Column]]
) -> dict[str, Column]:
    """The mean target and the task's `extra` label aggregates over `target`."""
    return {"mean_target": F.avg(target.cast("double")), **extra(target)}


def _summarise(
    targets: DataFrame, cfg: UseCaseConfig, extra: Callable[[Column], dict[str, Column]]
) -> pd.DataFrame:
    """The target summary from one Spark rollup over `targets` (one row per unit and period,
    with `target` and `null_in_window`): one row per period in order, labelled by the period
    spec, then an `all` row.

    Columns: `period`, `rows`, `null_share` (no known target), `null_value_share` (among the
    complete windows, the rows whose window held a null in the target column; label-free), then
    `mean_target` and the `extra` label aggregates. The labels are filled up to the observation
    window's last period (the periods before the window are training-time history) and null
    after it, since a gap period's target window reaches into the validation period's outcomes
    (§4.2, §4.4, D-030); the `all` row's are over the window's periods, the population the later
    stages read.
    """
    window = cfg.time.observation_window
    labelled = F.col("period") <= window.last
    in_window = labelled & (F.col("period") >= window.first)
    by_period = _label_aggregates(F.when(labelled, F.col("target")), extra)
    over_window = _label_aggregates(F.when(in_window, F.col("target")), extra)
    is_all, shown = F.grouping("period") == 1, F.max(labelled)  # shown: false after the window
    table = (
        targets.rollup("period")
        .agg(
            F.grouping("period").alias("_all"),
            F.count(F.lit(1)).alias("rows"),
            (1 - F.count("target") / F.count(F.lit(1))).alias("null_share"),
            F.avg(F.col("null_in_window").cast("double")).alias("null_value_share"),
            *[
                F.when(is_all, over_window[name]).when(shown, by_period[name]).alias(name)
                for name in by_period
            ],
        )
        .orderBy("_all", "period")
        .toPandas()
    )
    is_all = table.pop("_all") == 1
    label = period_spec(cfg).label
    table["period"] = table["period"].map(label, na_action="ignore").where(~is_all, "all")
    return table


def _binary_labels(target: Column) -> dict[str, Column]:
    """The positive rows and the positive events: the distinct units with a positive target,
    equal to the positive rows in one period and fewer over several, since one conversion is
    positive in up to w consecutive periods (D-082)."""
    positive = target == 1
    return {
        "positive_rows": F.count(F.when(positive, True)),
        "positive_events": F.countDistinct(F.when(positive, F.col("unit_id"))),
    }


def _binary_summary(targets: DataFrame, cfg: UseCaseConfig) -> pd.DataFrame:
    """The summary (rows, null shares, the mean target) with the positive rows and events."""
    return _summarise(targets, cfg, _binary_labels)


def _regression_summary(targets: DataFrame, cfg: UseCaseConfig) -> pd.DataFrame:
    """The summary: rows, the null share, the null-value share and the mean target."""
    return _summarise(targets, cfg, lambda target: {})


def _occurrences(
    source: DataFrame, cfg: UseCaseConfig, aggregates: dict[str, Column]
) -> pd.DataFrame:
    """One row per period of `source`, in period order, labelled by the period spec, with the
    outcome `aggregates` as columns: filled up to the window's last period + w (the outcomes the
    window's labels measure), null after (later labels' outcomes, the validation period's among
    them, §4.4)."""
    spec = period_spec(cfg)
    last = spec.index(cfg.time.observation_window.last) + cfg.time.target_window
    measured = F.max(spec.spark_index(F.col("period"))) <= last  # one period per group
    table = (
        source.groupBy("period")
        .agg(*[F.when(measured, aggregate).alias(name) for name, aggregate in aggregates.items()])
        .orderBy("period")
        .toPandas()
    )
    table["period"] = table["period"].map(spec.label)
    return table


def _binary_occurrences(source: DataFrame, cfg: UseCaseConfig) -> pd.DataFrame:
    """Per period of the target source, before eligibility and label-free: the `conversions`,
    rows whose flag is 1 while it was 0 at the unit's previous consecutive period (a unit's
    first row and a row after a gap have none, so never count; null in the source's first
    period, where no unit has one), and the `flag_rows`."""
    flag = F.col(cfg.data.target.column).cast("int")  # a boolean flag as 0/1
    index = period_spec(cfg).spark_index(F.col("period"))
    # a frame of one period: that period's flag, null without a row there (one window pass)
    previous = Window.partitionBy("unit_id").orderBy(index).rangeBetween(-1, -1)
    flags = source.select("period", flag.alias("flag"), F.max(flag).over(previous).alias("prev"))
    converted, held = (F.col("flag") == 1) & (F.col("prev") == 0), F.col("flag") == 1
    aggregates = {"conversions": F.count(F.when(converted, True)),
                  "flag_rows": F.count(F.when(held, True))}  # fmt: skip
    table = _occurrences(flags, cfg, aggregates)
    table["conversions"] = table["conversions"].where(table.index > 0)  # rows in period order
    return table


def _regression_occurrences(source: DataFrame, cfg: UseCaseConfig) -> pd.DataFrame:
    """Per period of the target source, before eligibility and label-free: the `total_amount`
    (the target column's sum, nulls skipped) and the `nonzero_rows`."""
    amount = F.col(cfg.data.target.column)
    aggregates = {"total_amount": F.sum(amount), "nonzero_rows": F.count(F.when(amount != 0, True))}
    return _occurrences(source, cfg, aggregates)


def _check_flag_target(eligible: DataFrame, cfg: UseCaseConfig) -> dict:
    """Both classes present, and the pooled positive rate at or below `data.rate_band.max`;
    returns the log entry (`check`, `rate`, `max`, `positive_rows`, `known`, `per_period`: the
    rate per period in rows, as a prevalence, null without a known target; the events are in the
    target summary, D-082)."""
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
    """A finite, non-constant target; returns the log entry (`check`, `known`, `min`, `max`)."""
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


def _binary_se(value: float, events: float, non_events: float, target_shares: np.ndarray) -> float:
    """Hanley–McNeil's standard error (D-082); the target shares go unread, since it conditions
    on the split into events and non-events already."""
    return concordance_se(value, events, non_events)


def _regression_se(
    value: float, events: float, non_events: float, target_shares: np.ndarray
) -> float:
    """Kendall's null standard error over every unit, halved and scaled for the ties on the
    target (A29, D-082)."""
    return kendall_null_se(events + non_events, target_shares)


def _binary_client_support(
    events: float, non_events: float, clients: dict[str, float]
) -> tuple[float, float]:
    """A window's events and non-events in effective clients, each class by its own ratio (a
    client's events and non-events are different rows of it)."""
    return (
        effective_count(events, clients["event_rows"], clients["event_effective"]),
        effective_count(non_events, clients["non_event_rows"], clients["non_event_effective"]),
    )


def _regression_client_support(
    events: float, non_events: float, clients: dict[str, float]
) -> tuple[float, float]:
    """A window's units with a non-zero and a zero target in effective clients, both by the
    window's one ratio: Kendall's SE counts units whatever their target, and a target need not
    take the value 0.

    The total is scaled once, floored at two units (at the rows when fewer), and split by the
    classes' shares: flooring each class at one row instead gave a strictly positive target over
    few rows a single unit, which Kendall's SE refuses.
    """
    total = events + non_events
    units = max(effective_count(total, clients["rows"], clients["effective"]), min(total, 2.0))
    return units * events / total, units * non_events / total


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


def _table_concordance(cells: pd.DataFrame, exact: bool, sign: int | None) -> float:
    """One feature's pooled cells' concordance from the two-way table; a 0/1 target has two
    target bins, so the table stays small whatever the feature's bins (`exact` changes nothing)."""
    return concordance_from_table(two_way_table(cells), sign)


def _regression_concordance(cells: pd.DataFrame, exact: bool, sign: int | None) -> float:
    """The table's concordance, or with `exact` (`eda.bins: null`, every target value a bin)
    Kendall's τ on the rows the cells expand to, without the dense table."""
    return concordance_exact(cells, sign) if exact else _table_concordance(cells, exact, sign)


def _binary_period_estimate(
    known: np.ndarray, positive_rows: np.ndarray, sum_y: np.ndarray, sum_y2: np.ndarray
) -> dict[str, np.ndarray]:
    """Per period, the rate (positive rows / rows with a known target) with its Wilson interval."""
    low, high = wilson_interval(positive_rows, known)
    return {"estimate": positive_rows / known, "low": low, "high": high}


def _regression_period_estimate(
    known: np.ndarray, positive_rows: np.ndarray, sum_y: np.ndarray, sum_y2: np.ndarray
) -> dict[str, np.ndarray]:
    """Per period, the mean (`sum_y` / rows with a known target) with its t-interval from the
    sum of squares (`variance_from_sums`; NaN under two rows), and the non-zero share with its
    Wilson interval."""
    estimate = sum_y / known
    low, high = np.full(np.shape(known), np.nan), np.full(np.shape(known), np.nan)
    enough = known >= 2  # `t_interval` refuses fewer rows
    n, y, y2 = known[enough], sum_y[enough], sum_y2[enough]
    sd = np.sqrt(variance_from_sums(n[None], y[None], y2[None]))  # each period its own sample
    low[enough], high[enough] = t_interval(estimate[enough], sd, known[enough])
    nonzero_low, nonzero_high = wilson_interval(positive_rows, known)
    return {"estimate": estimate, "low": low, "high": high,
            "nonzero_share": positive_rows / known, "nonzero_low": nonzero_low,
            "nonzero_high": nonzero_high}  # fmt: skip


def _binary_class(target: pd.Series) -> pd.Series:
    """The target class of each known 0/1 target: `"0"` or `"1"`."""
    return target.astype(int).astype(str)


def _regression_class(target: pd.Series) -> pd.Series:
    """The target class of each known amount: `"zero"` or `"non-zero"` (the support's split)."""
    return pd.Series(np.where(target != 0, "non-zero", "zero"), index=target.index)


def _binary_perfect_list(n: int, support: int) -> str:
    """What a perfect list of `n` rows achieves over `support` positives: all of them at their
    precision, or as many as fit at 100%."""
    if support <= n:
        return f"a perfect list captures all {support:,} positives at {support / n:.1%} precision"
    return f"a perfect list captures {n:,} of the {support:,} positives at 100% precision"


def _no_perfect_list(n: int, support: int) -> None:
    """None: an amount's perfect list depends on the amounts' spread, which the counts lack."""
    return None


TASK_SPECS = {
    "binary": {
        "target_rules": {"flag_goes_up": _flag_goes_up},
        "check_target_column": _check_flag_column,
        "summarise_targets": _binary_summary,
        "summarise_occurrences": _binary_occurrences,
        "contract_checks": [_check_flag_target],
        "target_bins": _binary_target_bins,
        "summarise_group": _binary_group,
        "summary_columns": SUMMARY_COLUMNS,  # the columns of a group table
        "rare_effect": cohens_h,  # (minority, dominant, effective sizes) -> (effect, SE)
        "rare_effect_unavailable": h_unavailable,  # why the effect cannot exist, or ''
        "rare_effect_name": "Cohen's h",
        "concordance_se": _binary_se,
        "client_support": _binary_client_support,
        "events_warning": partial(_events_warning, support=BINARY_SUPPORT),
        "support_name": BINARY_SUPPORT,
        "base_rate_views": _binary_headline,
        "shrinkage_rows": _binary_shrinkage_rows,
        "lift_available": _lift_available,
        # Cochran's Q weighs a period by Hanley–McNeil at the window's value on the period's rows
        "period_se_at_window_value": True,
        "cells_concordance": _table_concordance,
        "period_estimate": _binary_period_estimate,
        "target_class": _binary_class,
        "estimate_format": "{:.2%}",
        "axis_format": ".1%",  # a rate axis' and hover's d3 format, read like the tables
        "estimate_noun": "rate",  # the y titles ("Target rate") and the how-to-read wording
        "target_distribution": False,  # a 0/1 target has no distribution to show per group
        "capture_noun": "positives",  # what a slice captures: the share of `sum_y`
        "perfect_list": _binary_perfect_list,
    },
    "regression": {
        "target_rules": {"forward_sum": _forward_sum},
        "check_target_column": _check_amount_column,
        "summarise_targets": _regression_summary,
        "summarise_occurrences": _regression_occurrences,
        "contract_checks": [_check_amount_target],
        "target_bins": _regression_target_bins,
        "summarise_group": _regression_group,
        "summary_columns": AMOUNT_SUMMARY_COLUMNS,
        "rare_effect": cohens_d,
        "rare_effect_unavailable": d_unavailable,
        "rare_effect_name": "Cohen's d",
        "concordance_se": _regression_se,
        "client_support": _regression_client_support,
        "events_warning": partial(_events_warning, support=REGRESSION_SUPPORT),
        "support_name": REGRESSION_SUPPORT,
        "base_rate_views": _regression_headline,
        "shrinkage_rows": _regression_shrinkage_rows,
        "lift_available": _lift_available,
        "period_se_at_window_value": False,  # Kendall's null SE does not depend on the value
        "cells_concordance": _regression_concordance,
        "period_estimate": _regression_period_estimate,
        "target_class": _regression_class,
        "estimate_format": "{:,.2f}",  # an amount: separators, never scientific notation
        "axis_format": None,  # plotly's default
        "estimate_noun": "mean",
        "target_distribution": True,  # an amount's quartiles per group and its group table
        "capture_noun": "amount",
        "perfect_list": _no_perfect_list,
    },
}
