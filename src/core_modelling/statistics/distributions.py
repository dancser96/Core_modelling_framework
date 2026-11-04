"""How a numeric is binned and how two distributions are compared (T25, D-135).

`quantile_edges` gives the split points the counts table bins a numeric on: the mass points
(values holding at least `1 / bins` of the rows, such as 0) each get a singleton bin and the
quantile edges are taken over the remaining values, so no bin but a singleton holds more than
about `2 / bins` of the rows. Plain quantile edges collapse on a zero-inflated or discrete column
(ninety of a hundred edges land on 0 and one bucket takes the rest), and fixed-width edges put a
skewed column into its first bucket (T25). `bin_labels` names the bins the edges define, and is
the `bin` column of the counts table. `merge_bins` merges cells into the groups a chart shows,
by cumulative row share, a mass point its own group (chart rule 4). `psi`, `new_level_share`
and `standardised_difference` compare two periods' distributions for Feature Checks. Everything
is pure: numpy and pandas in, numbers and frames out, no Spark.

A bin is `(-inf, e_1)`, `[e_i, e_{i+1})` or `[e_m, +inf)` over the interior edges `e_1 < … <
e_m`, exactly what `pyspark.ml.feature.Bucketizer` does with `splits = [-inf, *edges, +inf]`
and what `numpy.digitize(values, edges)` returns. A singleton bin for `v` is `[v, next)` with
`next = np.nextafter(v, np.inf)`, so the edges alone say which bins are singletons.
"""

import numpy as np
import pandas as pd

PSI_FLOOR = 1e-4  # a share below this is raised to it before the log, so an empty bin stays finite


def quantile_edges(values: np.ndarray, bins: int) -> np.ndarray:
    """The interior split points that cut the non-null `values` into about `bins` bins.

    Every mass point (a value holding at least `1 / bins` of the values) gets a singleton bin and
    the remaining values are cut into `bins - n_mass` equal-share bins by quantiles; with at most
    `bins` distinct values every value is a singleton. ±inf take no edge and land in the outer
    bins.
    """
    if bins < 1:
        raise ValueError(f"quantile_edges: bins must be at least 1, got {bins}")
    values = np.asarray(values, dtype=float)
    if np.isnan(values).any():
        raise ValueError("quantile_edges: values hold NaN; drop the nulls first")
    values = values[np.isfinite(values)] + 0.0  # -0.0 becomes 0.0, so no bin reads "= -0"
    if values.size == 0:
        return np.array([], dtype=float)
    distinct, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
    if distinct.size <= bins:
        return np.unique(_singleton_edges(distinct))
    is_mass = counts >= values.size / bins
    mass = distinct[is_mass]
    quantiles = _interior_quantiles(values[~is_mass[inverse]], bins - mass.size)
    return np.unique(np.concatenate([_singleton_edges(mass), quantiles]))


def _singleton_edges(points: np.ndarray) -> np.ndarray:
    """Two edges per point, `v` and the next float up, so `[v, next)` holds exactly `v`."""
    return np.concatenate([points, np.nextafter(points, np.inf)])


def _interior_quantiles(values: np.ndarray, bins: int) -> np.ndarray:
    """The `bins - 1` quantile edges that cut `values` into `bins` equal-share bins; none when
    fewer than two bins are asked or there are no values."""
    if bins < 2 or values.size == 0:
        return np.array([], dtype=float)
    return np.quantile(values, np.arange(1, bins) / bins)


def bin_labels(edges: np.ndarray) -> list[str]:
    """One label per bin, `len(edges) + 1` of them in bin order: `< e_1`, `[e_i, e_{i+1})` and
    `≥ e_m`; a singleton reads `= v` and the bin above it `(v, e)` or `> v`."""
    edges = np.asarray(edges, dtype=float)
    if edges.size == 0:
        return ["all"]
    closes = np.zeros(edges.size, dtype=bool)  # edge i closes the singleton that edge i-1 opens
    closes[1:] = edges[1:] == np.nextafter(edges[:-1], np.inf)
    text = _format_numbers(np.where(closes, np.roll(edges, 1), edges))
    labels = [f"< {text[0]}"]
    for i in range(1, edges.size):  # bin i is [edges[i - 1], edges[i])
        if closes[i]:
            labels.append(f"= {text[i - 1]}")
        elif closes[i - 1]:
            labels.append(f"({text[i - 1]}, {text[i]})")
        else:
            labels.append(f"[{text[i - 1]}, {text[i]})")
    last = edges.size - 1
    labels.append(f"> {text[last]}" if closes[last] else f"≥ {text[last]}")
    return labels


def _format_numbers(numbers: np.ndarray) -> list[str]:
    """Six significant digits, or the shortest exact text when six digits would make two
    distinct numbers read alike (integer codes above 999,999)."""
    short = [f"{x:.6g}" for x in numbers]
    if len(set(short)) == np.unique(numbers).size:
        return short
    return [repr(float(x)) for x in numbers]


def merge_bins(cells: pd.DataFrame, groups: int) -> pd.DataFrame:
    """One feature's pooled non-null cells merged in `bin_order` into about `groups` groups.

    The cells hold one row per `bin_order` with `bin`, `n` and optionally `sum_y`, the only
    columns that add up; any other numeric column is refused. A bin holding at least
    `1 / groups` of the rows (a mass point) is its own group and the other bins are cut by
    cumulative row share into the groups left; with at most `groups` bins each bin is a group. A
    mass point inside a run of other bins splits that run, which can add a group. Columns:
    `group`, `bin_order_first`, `bin_order_last`, `label`, `n` and `sum_y` when given.
    """
    if groups < 1:
        raise ValueError(f"merge_bins: groups must be at least 1, got {groups}")
    if cells["bin_order"].duplicated().any():
        raise ValueError(
            "merge_bins: one row per bin_order expected: sum over periods and target bins first"
        )
    summed = ["n", "sum_y"] if "sum_y" in cells else ["n"]
    stray = [c for c in cells.select_dtypes("number").columns if c not in ["bin_order", *summed]]
    if stray:
        raise ValueError(
            f"merge_bins: numeric column(s) {stray} cannot be summed; only n and sum_y add up, "
            "drop the others first"
        )
    ordered = cells.sort_values("bin_order").reset_index(drop=True)
    if len(ordered) <= groups:
        ordered["group"] = np.arange(len(ordered))
    else:
        ordered["group"] = _group_keys(ordered["n"].to_numpy(dtype=float), groups)
    by = ordered.groupby("group")
    merged = by.agg(
        bin_order_first=("bin_order", "min"),
        bin_order_last=("bin_order", "max"),
        first=("bin", "first"),
        last=("bin", "last"),
    )
    single = merged["first"] == merged["last"]
    merged["label"] = merged["first"].where(single, merged["first"] + " – " + merged["last"])
    merged = merged.drop(columns=["first", "last"]).join(by[summed].sum()).reset_index()
    return merged[["group", "bin_order_first", "bin_order_last", "label", *summed]]


def _group_keys(n: np.ndarray, groups: int) -> np.ndarray:
    """The 0-based group of every bin, in bin order: a mass point alone, the other bins cut by
    the cumulative share of their own total (taken at each bin's middle) into the groups the
    mass points leave."""
    is_mass = n >= n.sum() / groups
    rest = np.where(is_mass, 0.0, n)
    rest_groups = max(groups - int(is_mass.sum()), 1)
    target = rest.sum() / rest_groups
    middle = np.cumsum(rest) - rest / 2  # a bin joins the group most of its rows fall in
    if target > 0:
        key = np.minimum(np.floor(middle / target), rest_groups - 1)
    else:  # every non-mass bin is empty: no share to cut by, so only the mass points split
        key = np.zeros_like(middle)
    starts = np.ones(n.size, dtype=bool)
    starts[1:] = is_mass[1:] | is_mass[:-1] | (key[1:] != key[:-1])
    return np.cumsum(starts) - 1


def psi(expected_shares: np.ndarray, actual_shares: np.ndarray) -> float:
    """The population stability index over aligned bins, `sum((a − e) · ln(a / e))`, each share
    floored at `PSI_FLOOR` before the log and not renormalised."""
    expected = np.asarray(expected_shares, dtype=float)
    actual = np.asarray(actual_shares, dtype=float)
    if expected.shape != actual.shape:
        raise ValueError(
            f"psi: expected has shape {expected.shape} and actual {actual.shape}; align the bins"
        )
    shares = np.concatenate([expected, actual])
    if not np.isfinite(shares).all():
        raise ValueError("psi: every share must be finite")
    if ((shares < 0) | (shares > 1)).any():
        raise ValueError("psi: every share must lie in [0, 1]; pass shares, not counts")
    expected = np.maximum(expected, PSI_FLOOR)
    actual = np.maximum(actual, PSI_FLOOR)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def new_level_share(cells: pd.DataFrame, window_levels: list[str], period: str) -> float:
    """The share of `period`'s rows, null rows included, whose `bin` is not among `window_levels`.

    The cells are one feature's; only the period's current-period cells count (`lagged == False`
    when the column is there), summed over target bins. A `__new__` bin is unseen by definition.
    """
    rows = cells.loc[cells["period"] == period]
    if "lagged" in rows:
        rows = rows.loc[~rows["lagged"]]
    total = rows["n"].sum()
    if total == 0:
        raise ValueError(
            f"new_level_share: period {period!r} has no rows (no current cells, or n sums to 0)"
        )
    unseen = rows.loc[~rows["bin"].isin(window_levels), "n"].sum()
    return float(unseen / total)


def standardised_difference(a: np.ndarray, b: np.ndarray) -> float:
    """Cohen's d of `a` against `b` on their non-null values; never NaN.

    `(mean_a − mean_b) / sqrt((sd_a² + sd_b²) / 2)` with sample standard deviations. When both
    sides are constant it is 0 for equal constants and ±inf (the sign of the difference) for
    different ones, so a report can say "differs".
    """
    a, b = _validated_sample(a, "a"), _validated_sample(b, "b")
    if a.min() == a.max() and b.min() == b.max():
        return 0.0 if a[0] == b[0] else float(np.copysign(np.inf, a[0] - b[0]))
    spread = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
    return float((a.mean() - b.mean()) / spread)


def _validated_sample(values: np.ndarray, name: str) -> np.ndarray:
    """`values` as floats without NaN: at least two of them, all finite, or a ValueError."""
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    if values.size < 2:
        raise ValueError(
            f"standardised_difference: {name} needs at least two non-null values, got {values.size}"
        )
    if not np.isfinite(values).all():
        raise ValueError(f"standardised_difference: {name} holds infinite values")
    return values
