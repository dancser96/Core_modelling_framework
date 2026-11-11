"""The concordance, its standard errors, the level encoding and the best order, from cells
(D-082, D-135).

The concordance is the one ranking statistic of both tasks (Q427): Somers' D of the feature with
respect to the target, rescaled to [0.5, 1] after the direction is taken out; for a 0/1 target
it is the AUC of the binned feature. `concordance_from_table` reads it from a two-way table
(`cells.two_way_table`): exact on the binned data, within 0.0001 of the raw AUC at 100 bins and
about 0.01 from the raw rows' value against a 20-bin regression target (T32).
`concordance_exact` is the `eda.bins: null` regression path, without the dense table. The SEs
follow D-082, a window's support counted in effective clients (`effective_count`), since the
same client is labelled in every period, mostly with the same label (T33); `cochran_q` tests
whether per-period values differ.

A categorical has no order: `encode_levels` scores its levels by their shrunk target mean, and
its concordance is cross-fitted by client fold (`cross_fitted_concordance`, `fold_encodings`,
which EDA's slices order a categorical's list by too), since an order read on the rows or the
clients it was fitted on flatters noise (T33). `best_order_concordance` is what a ten-leaf tree
on a numeric would reach, and `ranking_value` takes it only past `is_non_monotone`'s margin (V2).
"""

import math

import numpy as np
import pandas as pd
from scipy import stats

from core_modelling.statistics.cells import group_of_bins, pool_periods, two_way_table
from core_modelling.statistics.distributions import merge_bins

SE_FLOOR = 0.005  # a concordance of 1 would otherwise get an infinite weight in Cochran's Q
NON_MONOTONE_MARGIN = 0.03  # best-order must beat the plain concordance by this much (V2) …
# … and by 4 SE: a null numeric's best-order gain averages about 2 SE, so the fixed 0.03 marked
# 42% of null numerics at 500 events and 2 SE about as many; 4 SE marks 0–2% at every size
NON_MONOTONE_SE_MULTIPLE = 4
# A cross-fitted categorical's spread under no signal is 1.35–1.5× its Hanley–McNeil SE, even on
# effective clients: each fold's order is fitted partly on the other folds' level noise, so the
# five folds' values move together, which the SE (noise for a fixed order) leaves out. Measured
# 2026-11-04 (SD 0.020 against 0.013 on a 500-event-client panel; 1.3–1.4× on independent rows);
# the upper end, so a null code clears 0.5 + 2 SE about as rarely as a numeric does (the EDS).
CROSS_FIT_SE_INFLATION = 1.5
BEST_ORDER_GROUPS = 10  # the leaves of the tree the best-order concordance stands for


def concordance_from_table(table: np.ndarray, sign: int | None = None) -> float:
    """The concordance of a two-way table (feature bins × target bins, both in order),
    `(1 + |D|) / 2` with D Somers' D; with `sign` (±1, the window's direction)
    `(1 + sign · D) / 2`, so a flipped period reads below 0.5."""
    return _rescale(_somers_d(table), sign)


def concordance_se(value: float, events: float, non_events: float) -> float:
    """The Hanley–McNeil standard error of a concordance from its events and non-events (D-082),
    floored at `SE_FLOOR`; a window's support in effective clients (`client_support`)."""
    if events < 1 or non_events < 1:
        raise ValueError(
            f"concordance_se: needs events and non-events, got {events} and {non_events}"
        )
    if not 0 <= value <= 1:
        raise ValueError(f"concordance_se: the concordance {value} is outside [0, 1]")
    a = value
    q1, q2 = a / (2 - a), 2 * a**2 / (1 + a)
    variance = (a * (1 - a) + (events - 1) * (q1 - a**2) + (non_events - 1) * (q2 - a**2)) / (
        events * non_events
    )
    return max(math.sqrt(max(variance, 0.0)), SE_FLOOR)  # max(…, 0): rounding at a = 1 only


def effective_count(count: float, rows: float, effective: float) -> float:
    """`count` of a window's labelled rows in effective clients, `count · effective / rows` (the
    class's ratio from `counts.window_clients`), never below `min(count, 1)`.

    Known limit: one ratio per run, so a feature filled only on clients present in few periods
    gets too small a count (a conservative SE), one filled only on clients present in every
    period while others come and go too large (about 1.3× too small an SE with half the clients
    in one period of six).
    """
    if rows < 1:
        raise ValueError(f"effective_count: the window has no labelled rows of this class: {rows}")
    return max(count * effective / rows, min(count, 1.0))


def kendall_null_se(units: float, target_shares: np.ndarray) -> float:
    """The null SE of a regression concordance over `units` (D-082): Kendall's
    `sqrt(2(2n + 5) / (9n(n − 1))) / 2` times `sqrt(1 − Σp³) / (1 − Σp²)` for the target's ties
    (`p`: `cells.target_shares`), floored at `SE_FLOOR`.

    The feature's ties are left out, so the SE errs large.
    """
    p = np.asarray(target_shares, dtype=float)
    if (p < 0).any() or (p > 0).sum() < 2 or not math.isclose(p.sum(), 1.0):
        raise ValueError(
            "kendall_null_se: the target shares must be non-negative, fill two bins or more and "
            f"sum to 1; got {p.size} shares summing to {p.sum()}"
        )
    if units < 2:
        raise ValueError(f"kendall_null_se: needs at least two units, got {units}")
    tau_se = math.sqrt(2 * (2 * units + 5) / (9 * units * (units - 1))) / 2
    ties = math.sqrt(1 - (p**3).sum()) / float(1 - (p**2).sum())
    return max(tau_se * ties, SE_FLOOR)


def cochran_q(values: np.ndarray, ses: np.ndarray) -> float:
    """The p-value of Cochran's Q that the values differ, `Q = Σ (v − v̄)² / se²` around the
    `1 / se²`-weighted mean, against χ² with k − 1 degrees of freedom. Fewer than two values are
    refused; the caller reports "not available"."""
    values, ses = np.asarray(values, dtype=float), np.asarray(ses, dtype=float)
    if values.size < 2 or values.shape != ses.shape:
        raise ValueError(
            f"cochran_q: needs at least two values with one SE each, got {values.size} values "
            f"and {ses.size} SEs"
        )
    if not (np.isfinite(values).all() and np.isfinite(ses).all() and (ses > 0).all()):
        raise ValueError("cochran_q: values and SEs must be finite and every SE positive")
    weights = 1 / ses**2
    pooled = (weights * values).sum() / weights.sum()
    q = (weights * (values - pooled) ** 2).sum()
    return float(stats.chi2.sf(q, values.size - 1))


def encode_levels(cells: pd.DataFrame, k_rows: float) -> dict[str, float]:
    """Level → shrunk target mean (Micci-Barreca) for every non-null level of one feature's
    pooled cells, `(sum_y + k · base) / (n + k)` over the labelled rows, `base` their mean and
    `k` = `k_rows` (the task's `shrinkage_rows`). The null level is left out (N7); a level
    without labelled rows scores `base`."""
    if k_rows <= 0:
        raise ValueError(f"encode_levels: k_rows must be positive, got {k_rows}")
    values = cells.loc[~cells["is_null"]]
    labelled = values.loc[values["target_bin"].notna()]
    if labelled["n"].sum() == 0:
        raise ValueError("encode_levels: no labelled non-null rows to fit the encoding on")
    levels = values["bin"].unique()
    sums = labelled.groupby("bin")[["n", "sum_y"]].sum().reindex(levels, fill_value=0)
    base = sums["sum_y"].sum() / sums["n"].sum()
    return _shrunk(sums["n"], sums["sum_y"], k_rows, base).to_dict()


def fold_encodings(
    cells: pd.DataFrame, periods: list[str], k_rows: float
) -> dict[int, tuple[dict[str, float], float]]:
    """Fold → (level encoding, base) per client fold of one feature's `cells`, in fold order:
    `encode_levels` fitted on the other folds' current cells over `periods`, and that fit's
    labelled non-null mean, which a level unseen there scores.

    Every fold the cells hold is fitted, so a fold whose clients sit only in periods outside
    `periods` gets the fit on all of them. Refused for cells without a fold (a numeric's, or
    outside the window) or with fewer than two folds.
    """
    if "fold" not in cells or cells["fold"].isna().any():
        raise ValueError(
            "fold_encodings: every cell needs a client fold; a numeric's cells and the cells "
            "outside the window have none"
        )
    folds = sorted(cells["fold"].unique())
    if len(folds) < 2:
        raise ValueError(f"fold_encodings: needs two client folds, got {folds}")
    encodings = {}
    for fold in folds:
        fit = pool_periods(cells.loc[cells["fold"] != fold], periods)
        fitted = _labelled_values(fit)
        encodings[fold] = (encode_levels(fit, k_rows), fitted["sum_y"].sum() / fitted["n"].sum())
    return encodings


def cross_fitted_concordance(
    cells: pd.DataFrame,
    periods: list[str],
    k_rows: float,
    read: list[str] | None = None,
    lagged: bool = False,
) -> float:
    """A categorical's concordance with its levels ordered by an encoding its own clients never
    informed: per client fold, `fold_encodings` fitted on the other folds' current cells over
    `periods`, applied to the fold's cells over `read` (`periods` by default; the lagged cells
    with `lagged`).

    Somers' D sums the pairs inside each fold only (two folds' orders come from different fits)
    and is read in the encoding's direction, so below 0.5 means the order does not carry over.
    `cells` are one feature's, with the counts table's `fold`. A fold without labelled rows in
    `read` is skipped. The snapshot reads `read=[snapshot period]`, a period `read=[period]`,
    the lagged value `lagged=True`, always with the window as `periods`. Known limit: the
    prior's weight `k_rows` comes from every fold's base rate (simulated, it moves a null code's
    concordance by nothing). Its SE is the task's times `CROSS_FIT_SE_INFLATION`.
    """
    read = list(periods) if read is None else read
    if not read:
        raise ValueError("cross_fitted_concordance: `read` names no period")
    cells = cells.loc[cells["period"].isin([*periods, *read])]
    difference = untied = 0.0
    for fold, (encoding, base) in fold_encodings(cells, periods, k_rows).items():
        held_out = cells["fold"] == fold
        read_cells = cells.loc[held_out & (cells["lagged"] == lagged) & cells["period"].isin(read)]
        if read_cells.empty:  # none of the fold's clients is in the read periods
            continue
        present = sorted(read_cells["period"].unique())
        rows = _labelled_values(pool_periods(read_cells, present, lagged))
        if rows.empty:
            continue
        table = _table_by_score(rows.assign(score=rows["bin"].map(encoding).fillna(base)))
        fold_difference, fold_untied = _somers_parts(table)
        difference, untied = difference + fold_difference, untied + fold_untied
    if untied == 0:
        raise ValueError("cross_fitted_concordance: needs labelled rows in two target bins")
    return _rescale(difference / untied, sign=1)


def best_order_concordance(cells: pd.DataFrame, k_rows: float) -> float:
    """The concordance of a numeric's labelled non-null bins merged into `BEST_ORDER_GROUPS`
    groups (`merge_bins`, a mass point its own group) and ordered by their shrunk target mean:
    what a ten-leaf tree would reach.

    Merging first keeps the order from rewarding a hundred bins' noise; a null control still
    gains about 2 SE, hence `is_non_monotone`'s SE-scaled margin. A categorical needs none: in
    its encoding order its best order is its plain value.
    """
    values = _labelled_values(cells)
    if values["n"].sum() == 0:
        raise ValueError("best_order_concordance: no labelled non-null rows")
    per_bin = values.groupby(["bin_order", "bin"], as_index=False)[["n", "sum_y"]].sum()
    groups = merge_bins(per_bin, BEST_ORDER_GROUPS, None)  # no edges: the labels go unread
    base = per_bin["sum_y"].sum() / per_bin["n"].sum()
    score = _shrunk(groups["n"], groups["sum_y"], k_rows, base).to_numpy()
    group = group_of_bins(groups["bin_order_first"], values["bin_order"])  # its own bins: no outer
    return concordance_from_table(_table_by_score(values.assign(score=score[group])))


def is_non_monotone(plain: float, best_order: float, se: float) -> bool:
    """Whether the best-order concordance beats the plain one by `max(NON_MONOTONE_MARGIN,
    NON_MONOTONE_SE_MULTIPLE · se)`, `se` the feature's `concordance_se` on the same cells, a
    window's support in effective clients (`client_support`, V2)."""
    if not se >= 0:
        raise ValueError(f"is_non_monotone: se must be a non-negative number, got {se}")
    return best_order >= plain + max(NON_MONOTONE_MARGIN, NON_MONOTONE_SE_MULTIPLE * se)


def ranking_value(plain: float, best_order: float, se: float) -> float:
    """The value a feature is ranked by: best-order when non-monotone, else plain (V2)."""
    return best_order if is_non_monotone(plain, best_order, se) else plain


def concordance_exact(cells: pd.DataFrame, sign: int | None = None) -> float:
    """The concordance of pooled cells whose bins are the values (`eda.bins: null`), from
    Kendall's τ-b on the expanded rows and the tie counts: equal to `concordance_from_table` on
    the same cells, without the dense table. `sign` as in `concordance_from_table`."""
    values = _labelled_values(cells)
    by_target = values.groupby("target_bin")[["n", "sum_y"]].transform("sum")
    target_mean = (by_target["sum_y"] / by_target["n"]).to_numpy()  # orders the target bins
    n = values["n"].to_numpy(dtype=np.int64)
    untied_target = _untied_pairs(values.groupby("target_bin")["n"].sum())
    if untied_target == 0:
        raise ValueError("concordance_exact: needs labelled rows in at least two target bins")
    untied_feature = _untied_pairs(values.groupby("bin_order")["n"].sum())
    if untied_feature == 0:  # one feature bin: no pair is ordered, D = 0
        return _rescale(0.0, sign)
    x = np.repeat(values["bin_order"].to_numpy(), n)
    y = np.repeat(target_mean, n)
    tau_b = stats.kendalltau(x, y).statistic
    return _rescale(tau_b * math.sqrt(untied_feature / untied_target), sign)


def _labelled_values(cells: pd.DataFrame) -> pd.DataFrame:
    """The labelled non-null cells: what a concordance and an encoding are fitted on."""
    return cells.loc[~cells["is_null"] & cells["target_bin"].notna()]


def _table_by_score(rows: pd.DataFrame) -> np.ndarray:
    """The two-way table of labelled non-null cells ordered by their `score`, cells with equal
    scores sharing a row."""
    place = stats.rankdata(rows["score"], method="dense")
    regrouped = (
        rows.assign(bin_order=place)
        .groupby(["bin_order", "target_bin"], as_index=False)[["n", "sum_y"]]
        .sum()
        .assign(is_null=False)
    )
    regrouped["bin"] = regrouped["bin_order"].astype(str)
    return two_way_table(regrouped)


def _somers_d(table: np.ndarray) -> float:
    """Somers' D of the rows with respect to the columns: (concordant − discordant) pairs over
    the pairs in different columns."""
    difference, untied_target = _somers_parts(table)
    if untied_target == 0:
        raise ValueError("concordance: needs labelled rows in at least two target bins")
    return difference / untied_target


def _somers_parts(table: np.ndarray) -> tuple[float, float]:
    """Somers' D's numerator and denominator: concordant − discordant pairs, and the pairs in
    different columns, which sum over separate tables."""
    table = np.asarray(table, dtype=float)
    if table.ndim != 2 or not np.isfinite(table).all() or (table < 0).any():
        raise ValueError("concordance: the table must be 2-D with finite non-negative counts")
    later = np.cumsum(table[::-1], axis=0)[::-1] - table  # the rows below, per column
    lower = np.cumsum(later, axis=1) - later  # … in a lower target bin
    higher = later.sum(axis=1, keepdims=True) - np.cumsum(later, axis=1)  # … in a higher one
    total = table.sum()
    untied_target = (total**2 - (table.sum(axis=0) ** 2).sum()) / 2
    return float((table * higher).sum() - (table * lower).sum()), float(untied_target)


def _rescale(d: float, sign: int | None) -> float:
    """Somers' D on the concordance scale: direction taken out, or read in `sign`'s direction."""
    if sign is None:
        return (1 + abs(d)) / 2
    if sign not in (1, -1):
        raise ValueError(f"concordance: sign must be +1, -1 or None, got {sign}")
    return (1 + sign * d) / 2


def _untied_pairs(counts: pd.Series) -> float:
    """The pairs of rows in different groups, from the rows per group."""
    counts = counts.to_numpy(dtype=float)
    return (counts.sum() ** 2 - (counts**2).sum()) / 2


def _shrunk(n: pd.Series, sum_y: pd.Series, k_rows: float, base: float) -> pd.Series:
    """The shrunk mean `(sum_y + k · base) / (n + k)`."""
    return (sum_y + k_rows * base) / (n + k_rows)
