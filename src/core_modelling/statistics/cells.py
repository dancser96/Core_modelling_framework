"""One feature's cells summed into the shapes the statistics read (D-135).

The counts table holds one row per feature, period, lagged flag, bin and target bin: `feature,
period, lagged, bin, bin_order, is_null, target_bin, n, sum_y, sum_y2`. A statistic of one
feature over some periods is a sum over its cells: `pool_periods` sums the periods wanted;
`two_way_table` and `null_table` give the count tables the concordance reads and
`target_shares` the table's target bins' shares, which its SE reads; `shares` gives the shares
and counts the ledger and the quality findings read; `group_shares` and
`level_share_difference` compare two distributions. Rows without a label (`target_bin` null:
the gap and latest periods, unknown targets) count in the shares only (N4, N6).

Target bins are ordered by their mean target, `sum_y / n`: they are disjoint intervals of the
target, so their means order them exactly (binary: `0` then `1`; regression: the quantile bins,
0 its own) without parsing a label. For the same reason a zero target bin is the one whose
target sums to 0. Pure pandas and numpy; no Spark.
"""

import numpy as np
import pandas as pd

from core_modelling.statistics.distributions import bin_labels

_ZERO_SINGLETON = np.array([0.0, np.nextafter(0.0, np.inf)])
# The 0 singleton's label as `bin_labels` writes it, in its two number formats: the short one,
# and the exact text it falls back to when six digits read two non-integral edges alike
ZERO_LABELS = (
    bin_labels(_ZERO_SINGLETON)[1],
    bin_labels(np.append(_ZERO_SINGLETON, [1e6 + 0.001, 1e6 + 0.002]))[1],
)
BIN_KEYS = ["bin", "bin_order", "is_null", "target_bin"]


def pool_periods(cells: pd.DataFrame, periods: list[str], lagged: bool = False) -> pd.DataFrame:
    """One feature's current (or lagged) cells over `periods`, summed per bin and target bin.

    Columns: `bin, bin_order, is_null, target_bin, n, sum_y, sum_y2`; an unlabelled target bin
    stays null and so do its `sum_y` and `sum_y2`.
    """
    _check_one_feature(cells, "pool_periods")
    chosen = cells.loc[cells["lagged"] == lagged]
    missing = sorted(set(periods) - set(chosen["period"]))
    if missing:
        kind = "lagged" if lagged else "current"
        raise ValueError(
            f"pool_periods: no {kind} cells for period(s) {missing}; periods are the counts "
            "table's labels"
        )
    chosen = chosen.loc[chosen["period"].isin(periods)]
    pooled = chosen.groupby(BIN_KEYS, dropna=False, as_index=False)
    return pooled[["n", "sum_y", "sum_y2"]].sum(min_count=1)  # min_count: a null sum stays null


def two_way_table(cells: pd.DataFrame, order: list[str] | None = None) -> np.ndarray:
    """The labelled non-null rows as counts: feature bins (in `bin_order`, or in `order`, a list
    of bin labels such as the levels sorted by their encoding) × target bins in target order."""
    labelled = _labelled(cells, "two_way_table")
    values = labelled.loc[~labelled["is_null"]]
    if order is None:
        order = list(values.sort_values("bin_order")["bin"].drop_duplicates())
    elif len(set(order)) < len(order):
        raise ValueError("two_way_table: `order` names a bin twice")
    unplaced = sorted(set(values["bin"]) - set(order))
    if unplaced:
        raise ValueError(f"two_way_table: bins {unplaced[:5]} are not in `order`")
    table = values.pivot(index="bin", columns="target_bin", values="n")
    columns = _target_order(labelled)
    return table.reindex(index=order, columns=columns).fillna(0).to_numpy(dtype=float)


def target_shares(cells: pd.DataFrame) -> np.ndarray:
    """The labelled non-null rows' share in each target bin: `two_way_table`'s column sums over
    their total, without the dense table (`eda.bins: null` can mean many bins on both sides)."""
    labelled = _labelled(cells, "target_shares")
    counts = labelled.loc[~labelled["is_null"]].groupby("target_bin")["n"].sum()
    return (counts / counts.sum()).to_numpy(dtype=float)


def null_table(cells: pd.DataFrame) -> np.ndarray:
    """The labelled rows as counts: two rows (non-null, null) × target bins in target order."""
    labelled = _labelled(cells, "null_table")
    counts = labelled.groupby(["is_null", "target_bin"])["n"].sum().unstack(fill_value=0)
    counts = counts.reindex(index=[False, True], columns=_target_order(labelled), fill_value=0)
    return counts.to_numpy(dtype=float)


def shares(cells: pd.DataFrame) -> dict:
    """The shares and counts of one feature's cells (one period, or pooled).

    `rows` (every row, labelled or not); `missing_share` (null rows / rows); `zero_share` (the
    `= 0` bin's rows / non-null rows, NaN when every row is null; exact whenever 0 occurs in the
    snapshot's eligible rows, since `counts.bin_edges` gives it its own bin; a 0 seen only in
    other periods shares a quantile bin there and reads 0); `dominant_share` and
    `dominant_value` (the largest bin, null counting as a value: a value whenever its share
    reaches `1 / bins`); `bins` (the non-null bins holding rows; the ledger's `levels`, distinct
    values before the level cap, come from the snapshot instead); `events` and `non_events` (the
    labelled non-null rows with a non-zero and a zero target: the concordance's support, N6;
    rows, so events only within one period).
    """
    _check_one_distribution(cells, "shares")
    rows = cells["n"].sum()
    if rows == 0:
        raise ValueError("shares: the cells hold no rows")
    by_bin = cells.groupby(["bin_order", "is_null", "bin"])["n"].sum()
    values = cells.loc[~cells["is_null"]]
    non_null = values["n"].sum()
    zero_rows = values.loc[values["bin"].isin(ZERO_LABELS), "n"].sum()
    labelled = values.loc[values["target_bin"].notna()]
    zero_target = labelled["target_bin"].isin(zero_target_bins(cells))
    return {
        "rows": int(rows),
        "missing_share": float(1 - non_null / rows),
        "zero_share": float(zero_rows / non_null) if non_null else float("nan"),
        "dominant_share": float(by_bin.max() / rows),
        "dominant_value": str(by_bin.idxmax()[2]),
        "bins": int((values.groupby("bin_order")["n"].sum() > 0).sum()),
        "events": int(labelled.loc[~zero_target, "n"].sum()),
        "non_events": int(labelled.loc[zero_target, "n"].sum()),
    }


def group_shares(cells: pd.DataFrame, groups: pd.DataFrame) -> np.ndarray:
    """The share of the cells' rows in each group `merge_bins` returned (by `bin_order_first`;
    a bin below the first or above the last group joins the outer group), the null bin last."""
    _check_one_distribution(cells, "group_shares")
    firsts = groups["bin_order_first"].to_numpy()
    if firsts.size == 0 or (np.diff(firsts) <= 0).any():
        raise ValueError("group_shares: groups must be non-empty and in bin order")
    total = cells["n"].sum()
    if total == 0:
        raise ValueError("group_shares: the cells hold no rows")
    values = cells.loc[~cells["is_null"]]
    group = np.searchsorted(firsts, values["bin_order"].to_numpy(), side="right") - 1
    group = np.clip(group, 0, firsts.size - 1)
    counts = np.bincount(group, weights=values["n"].to_numpy(dtype=float), minlength=firsts.size)
    return np.append(counts, cells.loc[cells["is_null"], "n"].sum()) / total


def level_share_difference(a_cells: pd.DataFrame, b_cells: pd.DataFrame) -> float:
    """The largest |share in a − share in b| over the bins of two distributions, null a level."""
    shares_by_side = []
    for side, side_cells in (("a", a_cells), ("b", b_cells)):
        _check_one_distribution(side_cells, "level_share_difference")
        counts = side_cells.groupby("bin_order")["n"].sum()
        if counts.sum() == 0:
            raise ValueError(f"level_share_difference: {side}_cells hold no rows")
        shares_by_side.append(counts / counts.sum())
    return float(shares_by_side[0].sub(shares_by_side[1], fill_value=0).abs().max())


def _labelled(cells: pd.DataFrame, name: str) -> pd.DataFrame:
    """The cells with a label; refused when a bin and target bin repeat (not pooled yet)."""
    labelled = cells.loc[cells["target_bin"].notna()]
    if labelled.duplicated(["bin_order", "is_null", "target_bin"]).any():
        raise ValueError(
            f"{name}: one cell per bin and target bin expected; pool the periods first "
            "(pool_periods)"
        )
    return labelled


def _target_order(labelled: pd.DataFrame) -> list:
    """The target bins sorted by their mean target."""
    sums = labelled.groupby("target_bin")[["n", "sum_y"]].sum()
    return list((sums["sum_y"] / sums["n"]).sort_values(kind="stable").index)


def zero_target_bins(cells: pd.DataFrame) -> list:
    """The target bins whose target sums to 0: binary `0`, the regression zero bin."""
    sums = cells.loc[cells["target_bin"].notna()].groupby("target_bin")["sum_y"].sum()
    return list(sums.index[sums == 0])


def _check_one_feature(cells: pd.DataFrame, name: str) -> None:
    """Refuse cells of several features."""
    if "feature" in cells and cells["feature"].nunique() > 1:
        raise ValueError(f"{name}: the cells hold {cells['feature'].nunique()} features; pass one")


def _check_one_distribution(cells: pd.DataFrame, name: str) -> None:
    """Refuse cells of several features, or current and lagged cells mixed."""
    _check_one_feature(cells, name)
    if "lagged" in cells and cells["lagged"].nunique() > 1:
        raise ValueError(f"{name}: current and lagged cells are mixed; pool_periods picks one")
