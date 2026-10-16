"""Statistics for the check families: samples of one row per client, estimators and check rows.

A statistical row compares an estimate with the spec within `Z_TOL` analytical standard errors.
Those standard errors assume independent rows, so the families take one row per client: one month
of the panel (`first_month`), or one pair of months (`pair_rows`). Rows here: a mean or a median of
log ratios, a ratio of two means (delta method), a correlation (Fisher z), and one-sided rules on a
statistic (`side_row`: a gap that must be positive). A one-sided row records its bound as
`expected` and NaN as `tolerance`, so it is never mistaken for a tolerance-0 rule, which the fast
suite runs on the small preset. Estimators shared with the later families: the Hill tail index,
the AUC with its Hanley–McNeil standard error, and the population stability index.
"""

from datetime import date

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from synthetic.check_table import Z_TOL, row
from synthetic.holding_events import build_panel

MEDIAN_SE = 1.2533  # a median's standard error is 1.2533 · sd / √n for normal data
RANK_SE = 1.06  # a rank correlation's Fisher-z variance is about 1.06 / (n − 3)
PSI_FLOOR = 1e-6  # share given to an empty bin, so the PSI's log stays finite


def sorted_panel(spec: dict, mart: pd.DataFrame, oracle: pd.DataFrame) -> pd.DataFrame:
    """Mart and oracle side by side in client and month order (`holding_events.build_panel`).

    The inputs may come in any order; rows whose keys don't match raise.
    """
    keys = ["client_id", "snapshot_month"]
    mart, oracle = (df.sort_values(keys, ignore_index=True) for df in (mart, oracle))
    return build_panel(spec, mart, oracle)


def month_number(months: pd.Series) -> np.ndarray:
    """Months since year 0, so consecutive months differ by 1."""
    stamps = pd.to_datetime(months)
    return (stamps.dt.year * 12 + stamps.dt.month - 1).to_numpy()


def shift_month(month: date, k: int) -> date:
    """The first of the month `k` months after `month` (before, for negative `k`)."""
    index = month.year * 12 + month.month - 1 + k
    return date(index // 12, index % 12 + 1, 1)


def first_month(panel: pd.DataFrame, month_of_year: int, history: int = 1) -> date:
    """The panel's first month in `month_of_year` with at least `history` panel months before it."""
    months = sorted(panel["snapshot_month"].unique())
    found = [m for m in months[history:] if m.month == month_of_year]
    if not found:
        raise ValueError(f"the panel has no month {month_of_year} after {history} months")
    return found[0]


def pair_rows(panel: pd.DataFrame, first: date, second: date, columns: list[str]) -> pd.DataFrame:
    """One row per client present in both months: `columns` at `first` (suffix `_0`) and at
    `second` (suffix `_1`)."""
    months = panel["snapshot_month"]
    for month in (first, second):
        if not (months == month).any():
            raise ValueError(f"month {month} is not in the panel")
    a = panel.loc[months == first, ["client_id", *columns]]
    b = panel.loc[months == second, ["client_id", *columns]]
    return a.merge(b, on="client_id", suffixes=("_0", "_1"))


def mean_row(check: str, stratum: str, values: np.ndarray, expected: float) -> dict:
    """A mean (one value per client) against the spec, within Z_TOL standard errors sd/√n."""
    x = np.asarray(values, dtype=float)
    if len(x) < 2:
        return row(check, stratum, len(x), expected, np.nan, np.nan)
    tolerance = Z_TOL * x.std(ddof=1) / np.sqrt(len(x))
    return row(check, stratum, len(x), expected, float(x.mean()), tolerance)


def median_ratio_row(check: str, stratum: str, log_ratio: np.ndarray, expected: float) -> dict:
    """The median of log ratios (one per client) against the spec, within Z_TOL standard errors
    1.2533 · sd / √n."""
    x = np.asarray(log_ratio, dtype=float)
    if len(x) < 2:
        return row(check, stratum, len(x), expected, np.nan, np.nan)
    tolerance = Z_TOL * MEDIAN_SE * x.std(ddof=1) / np.sqrt(len(x))
    return row(check, stratum, len(x), expected, float(np.median(x)), tolerance)


def mean_ratio_row(
    check: str, stratum: str, num: np.ndarray, den: np.ndarray, expected: float, paired: bool
) -> dict:
    """mean(num) / mean(den) against the spec, with the delta-method standard error.

    Paired: one (num, den) pair per client. Otherwise two samples of one row per client each, taken
    as independent; when they share clients whose values correlate positively, that overstates the
    standard error (a conservative tolerance).
    """
    num, den = np.asarray(num, dtype=float), np.asarray(den, dtype=float)
    n = len(num) if paired else len(num) + len(den)
    if min(len(num), len(den)) < 2:
        return row(check, stratum, n, expected, np.nan, np.nan)
    mean_num, mean_den = num.mean(), den.mean()
    var = num.var(ddof=1) / (len(num) * mean_num**2) + den.var(ddof=1) / (len(den) * mean_den**2)
    if paired:
        var -= 2 * np.cov(num, den)[0, 1] / (len(num) * mean_num * mean_den)
    ratio = mean_num / mean_den
    return row(check, stratum, n, expected, float(ratio), Z_TOL * ratio * np.sqrt(var))


def fisher_tolerance(n: int, expected: float = 0.0, rank: bool = False) -> float:
    """Z_TOL standard errors of a correlation near `expected`: Fisher's z has variance 1 / (n − 3)
    (1.06 / (n − 3) for a rank correlation), mapped back to the correlation scale."""
    return Z_TOL * (1 - expected**2) * np.sqrt((RANK_SE if rank else 1.0) / (n - 3))


def fisher_row(
    check: str, stratum: str, n: int, expected: float, realised: float, rank: bool = False
) -> dict:
    """A correlation against the spec, within Z_TOL Fisher-z standard errors."""
    return row(check, stratum, n, expected, realised, fisher_tolerance(n, expected, rank))


def side_row(
    check: str, stratum: str, n: int, bound: float, realised: float, above: bool = True
) -> dict:
    """A one-sided rule on a statistic: `realised` above `bound` (below, if not `above`).

    The bound goes in `expected` and the tolerance is NaN: a one-sided rule has no ± band.
    """
    holds = realised > bound if above else realised < bound
    return {**row(check, stratum, n, bound, realised, np.nan), "passed": bool(holds)}


def hill_estimate(values: np.ndarray, top_share: float) -> tuple[float, int]:
    """The Hill estimate of the tail index from the largest `top_share` of positive values, and the
    number k of values it uses: k / Σ log(x_(i) / x_(k+1)) over the k largest."""
    x = np.sort(np.asarray(values, dtype=float))[::-1]
    k = int(top_share * len(x))
    if k < 2:
        return np.nan, k
    return float(k / np.log(x[:k] / x[k]).sum()), k


def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """The Mann–Whitney AUC of `scores` for 0/1 `labels`; ties count one half (average ranks)."""
    labels = np.asarray(labels, dtype=bool)
    n_pos, n_neg = labels.sum(), (~labels).sum()
    ranks = rankdata(np.asarray(scores, dtype=float))
    return float((ranks[labels].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def hanley_se(area: float, n_pos: int, n_neg: int) -> float:
    """The Hanley–McNeil (1982) standard error of an AUC `area`."""
    q1, q2 = area / (2 - area), 2 * area**2 / (1 + area)
    var = area * (1 - area) + (n_pos - 1) * (q1 - area**2) + (n_neg - 1) * (q2 - area**2)
    return float(np.sqrt(var / (n_pos * n_neg)))


def psi(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """The population stability index of `current` against `reference`, on the reference's
    quantile bins. Tied quantiles (counts) merge bins; an empty bin counts as a share of 1e-6."""
    reference, current = np.asarray(reference, dtype=float), np.asarray(current, dtype=float)
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)[1:-1]))
    shares = [
        np.bincount(np.searchsorted(edges, x, side="right"), minlength=len(edges) + 1) / len(x)
        for x in (reference, current)
    ]
    ref, cur = (np.maximum(s, PSI_FLOOR) for s in shares)
    return float(np.sum((cur - ref) * np.log(cur / ref)))
