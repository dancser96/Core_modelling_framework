"""The client bootstrap's intervals, read from the replicates' score cells (D-141 (c)).

Rows are not independent: a client sits in up to six test periods and is positive in up to `w`
of them, so a formula that counts rows gives too narrow an interval, and none exists for lift,
average precision or the skill scores. Each client carries one Poisson(1) weight per replicate,
drawn in Spark from a hash of its id (`client_weights`), so its rows move together; the score
cells sum them per replicate (`score_cells.py`). `bootstrap_intervals` runs one metric function
of `metrics.py` on each replicate's cells and keeps the middle `level` share of each metric's
values (the percentile interval). A metric's values are keyed by any hashable: its name, or a
tuple such as `(period, name)` when one call returns several groups' values. Pure pandas and
numpy.
"""

from collections.abc import Callable, Hashable

import numpy as np
import pandas as pd

from core_modelling.statistics.metrics import NAN

Values = dict[Hashable, float]  # one replicate's metric values, by name or by a tuple key


def _metric_values(
    replicate_cells: pd.DataFrame,
    metric: Callable[[pd.DataFrame], Values],
    replicates: int,
) -> tuple[list[Hashable], np.ndarray]:
    """The metric's keys, and one row per replicate 1 … `replicates` with one column per key:
    `metric` on that replicate's cells, sorted once and sliced, or NaN throughout for a
    replicate without cells (none of the group's clients drawn)."""
    numbers = replicate_cells["replicate"].to_numpy()
    if ((numbers < 1) | (numbers > replicates)).any():
        raise ValueError(
            f"bootstrap_intervals: replicates run from 1 to {replicates}; got "
            f"{sorted(set(numbers[(numbers < 1) | (numbers > replicates)].tolist()))[:5]} "
            "(replicate 0, the rows as they are, gives the value, not the interval)"
        )
    order = np.argsort(numbers, kind="stable")
    ordered = replicate_cells.iloc[order]
    bounds = np.searchsorted(numbers[order], np.arange(1, replicates + 2))
    values = [
        metric(ordered.iloc[start:stop]) if stop > start else {}
        for start, stop in zip(bounds[:-1], bounds[1:], strict=True)
    ]
    names = next((list(value) for value in values if value), None)
    if names is None:
        raise ValueError("bootstrap_intervals: no replicate holds any cells")
    if any(value and list(value) != names for value in values):
        raise ValueError("bootstrap_intervals: the metric returned different names by replicate")
    table = [[value[name] for name in names] if value else [NAN] * len(names) for value in values]
    return names, np.array(table, dtype=float)


def bootstrap_intervals(
    replicate_cells: pd.DataFrame,
    metric: Callable[[pd.DataFrame], Values],
    level: float,
    replicates: int,
) -> dict[Hashable, tuple[float, float]]:
    """Each metric's percentile interval over the client bootstrap's replicates.

    `replicate_cells` is the long frame of one group's cells (one part; pooled periods, one
    period or one stratum level) for the replicates 1 … `replicates`, with `replicate`; `metric`
    returns one replicate's values by key from its cells (`binary_metrics` with its base bound,
    say). Returns, per key, the `(1 − level) / 2` and `(1 + level) / 2` quantiles of its
    values.

    An undefined replicate never narrows an interval: a metric that is NaN in any replicate (no
    event drawn, say), or a replicate without cells, gives that metric (NaN, NaN), "not
    available". Keeping only the replicates where it exists would leave the draws that happened
    to hold events, an interval too narrow and shifted.
    """
    if not 0 < level < 1:
        raise ValueError(f"bootstrap_intervals: level must lie in (0, 1), got {level}")
    names, values = _metric_values(replicate_cells, metric, replicates)
    low, high = np.quantile(values, [(1 - level) / 2, (1 + level) / 2], axis=0)
    defined = np.isfinite(values).all(axis=0)
    return {
        name: (float(low[i]), float(high[i])) if defined[i] else (NAN, NAN)
        for i, name in enumerate(names)
    }


def replicate_values(
    cells: pd.DataFrame,
    metric: Callable[[pd.DataFrame], Values],
    level: float,
    replicates: int,
) -> tuple[Values, dict[Hashable, tuple[float, float]]]:
    """Each metric's value and its interval from one group's cells over every replicate.

    `cells` holds replicate 0 (the rows as they are) and the replicates 1 … `replicates`, with
    `replicate`. Returns `metric` on replicate 0's cells, and the percentile intervals of
    `bootstrap_intervals` over the others, both by the metric's keys. No replicate-0 cells fails
    loud.
    """
    replicate = cells["replicate"].to_numpy()
    if not (replicate == 0).any():
        raise ValueError("replicate_values: no replicate-0 cells, so no value to report")
    bounds = bootstrap_intervals(cells.loc[replicate > 0], metric, level, replicates)
    return metric(cells.loc[replicate == 0]), bounds
