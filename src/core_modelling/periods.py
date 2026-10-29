"""The unit of analysis: one row per unit per period, where a period is a month, a week or a day.

`time.period` names the period; `PERIODS` holds, per period, the one set of arithmetic every stage
goes through: a date's period index (consecutive periods are consecutive integers, so stepping
periods is adding to the index, never `add_months` or adding days, T19), the period's start and
end, the same in Spark, the period's label and which days a config may write it as. A period is
held as its last day, the framework's one convention (D-129). This module imports no config, so
the config schema can import it.
"""

import calendar
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from pyspark.sql import Column, Row
from pyspark.sql import functions as F

if TYPE_CHECKING:
    from core_modelling.config.schema import UseCaseConfig

DAY_EPOCH = date(1970, 1, 1)
WEEK_EPOCH = date(1970, 1, 5)  # a Monday: ISO weeks run Monday to Sunday


@dataclass(frozen=True)
class Period:
    """One unit of analysis: a date's period index and its period's start and end, in Python
    and in Spark, how a period is written and which dates a config may write it as."""

    index: Callable[[date], int]  # consecutive periods → consecutive integers
    from_index: Callable[[int], date]  # the inverse, as the period's end
    start: Callable[[date], date]  # the period's first day
    end: Callable[[date], date]  # the period's last day
    spark_index: Callable[[Column], Column]
    spark_end: Callable[[Column], Column]
    label: Callable[[date], str]  # 2025-06 · 2025-W23 · 2025-06-15
    accept: Callable[[date], bool]  # the typo rule at config load


def _month_index(day: date) -> int:
    """`day`'s month as an integer, consecutive months consecutive."""
    return day.year * 12 + day.month - 1


def _month_end(day: date) -> date:
    """The last day of `day`'s month."""
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def _month_from_index(index: int) -> date:
    """The month `index` stands for, as its last day."""
    year, month = divmod(index, 12)
    return _month_end(date(year, month + 1, 1))


def _month_accept(day: date) -> bool:
    """A month is written as its first or its last day; any other day is a likely typo."""
    return day.day in (1, _month_end(day).day)


def _week_index(day: date) -> int:
    """`day`'s ISO week as an integer, consecutive weeks consecutive."""
    return (day - WEEK_EPOCH).days // 7


def _week_from_index(index: int) -> date:
    """The week `index` stands for, as its Sunday."""
    return WEEK_EPOCH + timedelta(days=index * 7 + 6)


def _week_start(day: date) -> date:
    """The Monday of `day`'s week."""
    return day - timedelta(days=day.weekday())


def _week_end(day: date) -> date:
    """The Sunday of `day`'s week."""
    return day + timedelta(days=6 - day.weekday())


def _spark_week_index(column: Column) -> Column:
    """`_week_index` in Spark."""
    return F.floor(F.datediff(column, F.lit(WEEK_EPOCH)) / 7)


def _spark_week_end(column: Column) -> Column:
    """`_week_end` in Spark: `dayofweek` is 1 on Sunday, so `(dayofweek + 5) % 7` is 0 on Monday."""
    return F.date_add(column, 6 - ((F.dayofweek(column) + 5) % 7))


def _day_index(day: date) -> int:
    """`day` as an integer, consecutive days consecutive."""
    return (day - DAY_EPOCH).days


def _day_from_index(index: int) -> date:
    """The day `index` stands for."""
    return DAY_EPOCH + timedelta(days=index)


def _same(value: date | Column) -> date | Column:
    """A day is its own start and end."""
    return value


def _any_day(day: date) -> bool:
    """A week or a day may be written as any of its days."""
    return True


PERIODS: dict[str, Period] = {
    "month": Period(
        index=_month_index,
        from_index=_month_from_index,
        start=lambda day: day.replace(day=1),
        end=_month_end,
        spark_index=lambda column: F.year(column) * 12 + F.month(column) - 1,
        spark_end=F.last_day,
        label=lambda day: f"{day:%Y-%m}",
        accept=_month_accept,
    ),
    "week": Period(
        index=_week_index,
        from_index=_week_from_index,
        start=_week_start,
        end=_week_end,
        spark_index=_spark_week_index,
        spark_end=_spark_week_end,
        label=lambda day: f"{day:%G-W%V}",
        accept=_any_day,
    ),
    "day": Period(
        index=_day_index,
        from_index=_day_from_index,
        start=_same,
        end=_same,
        spark_index=lambda column: F.datediff(column, F.lit(DAY_EPOCH)),
        spark_end=_same,
        label=lambda day: f"{day:%Y-%m-%d}",
        accept=_any_day,
    ),
}


def period_spec(cfg: "UseCaseConfig") -> Period:
    """The config's unit of analysis, `PERIODS[cfg.time.period]`."""
    return PERIODS[cfg.time.period]


def period_labels(first: date, last: date, spec: Period) -> list[str]:
    """The labels of every period from `first` to `last`."""
    return [spec.label(spec.from_index(n)) for n in range(spec.index(first), spec.index(last) + 1)]


def label_by_period(rows: Iterable[Row], field: str, spec: Period) -> dict[str, object]:
    """The per-period dict every log entry uses: each row's `field`, keyed by its period's label."""
    return {spec.label(row.period): row[field] for row in rows}
