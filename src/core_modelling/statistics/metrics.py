"""A scorer's metrics and curve tables, read from its score cells (A92, A95, A96, A102).

Every function reads one replicate's cells of one part (`score_cells.py`): pooled over periods or
one period, one stratum level or all, so the client bootstrap (`bootstrap.py`) calls the same
function on each replicate's weighted cells. The cells are summed per score bin, or onto the
score bin × target bin grid, with numpy alone, which keeps 200 replicates of a run's metric table
to seconds. AUC and the regression concordance both come from that grid through
`concordance_from_table`, comparable with Training's `row_concordance` up to the binning; the log
loss, the Brier score, the errors and the deviance are exact sums. A metric the numbers leave
undefined (no event, a scorer that is no probability) is NaN, decided from the cells and never by
catching an error. `tasks.TASK_SPECS` imports this module, so a task's choices arrive as
arguments (`roc`, `target_class`). Pure pandas and numpy.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from scipy.special import expit

from core_modelling.statistics.concordance import concordance_from_table
from core_modelling.statistics.score_cells import CELL_SUMS

if TYPE_CHECKING:
    from core_modelling.config.schema import Slices

NAN = float("nan")
NEWTON_STEPS = 50  # the calibration line's iterations: a fit not converged by then has no maximum
STEP_TOLERANCE = 1e-10  # Newton's step on the coefficients at which the fit has converged
SLICE_COUNTS = ["rows", "target", "part_rows", "part_target"]  # what adds up over periods


def _check_cells(cells: pd.DataFrame) -> None:
    """Fail loud on cells without rows or of several parts: a metric reads one part's cells."""
    if cells.empty:
        raise ValueError("the score cells hold no rows")
    part = cells["part"].to_numpy()
    if (part != part[0]).any():
        raise ValueError(f"the score cells hold the parts {sorted(set(part))}; pass one part")


def _totals(cells: pd.DataFrame) -> dict[str, float]:
    """`CELL_SUMS` summed over the cells; a null loss or link sum gives NaN."""
    _check_cells(cells)
    return dict(zip(CELL_SUMS, cells[CELL_SUMS].to_numpy(dtype=float).sum(axis=0), strict=True))


def _by_score_bin(cells: pd.DataFrame, columns: list[str]) -> dict[str, np.ndarray]:
    """The cells' `columns` summed per score bin, bins ascending, with the bins as `score_bin`."""
    _check_cells(cells)
    bins, at = np.unique(cells["score_bin"].to_numpy(), return_inverse=True)
    sums = {name: np.bincount(at, cells[name].to_numpy(dtype=float), bins.size) for name in columns}
    return {"score_bin": bins, **sums}


def _grid(cells: pd.DataFrame, columns: list[str]) -> dict[str, np.ndarray]:
    """The cells' `columns` summed onto the score bin × target bin grid: one (score bins ×
    target bins) array per column, score bins ascending (their labels as `score_bin`), target
    bins in the order of their mean target (binary 0 then 1; regression its quantile bins)."""
    _check_cells(cells)
    bins, score_at = np.unique(cells["score_bin"].to_numpy(), return_inverse=True)
    targets, target_at = np.unique(cells["target_bin"].to_numpy(), return_inverse=True)
    target_sum = np.bincount(target_at, cells["target_sum"].to_numpy(dtype=float))
    mean = target_sum / np.bincount(target_at, cells["rows"].to_numpy(dtype=float))
    rank = np.empty(targets.size, dtype=np.intp)
    rank[np.argsort(mean, kind="stable")] = np.arange(targets.size)
    flat = score_at * targets.size + rank[target_at]
    size, shape = bins.size * targets.size, (bins.size, targets.size)
    sums = {name: np.bincount(flat, cells[name].to_numpy(dtype=float), size).reshape(shape)
            for name in columns}  # fmt: skip
    return {"score_bin": bins, **sums}


def _ratio(numerator: float, denominator: float) -> float:
    """`numerator / denominator`, NaN when the denominator is 0."""
    return float(numerator / denominator) if denominator != 0 else NAN


def _concordance(table: np.ndarray) -> float:
    """The concordance of a score bin × target bin table, read in the score's direction (AUC for
    a 0/1 target); NaN when fewer than two target bins hold rows."""
    if (table.sum(axis=0) > 0).sum() < 2:
        return NAN
    return concordance_from_table(table, sign=1)


def _average_precision(rows: np.ndarray, events: np.ndarray) -> float:
    """The area under the precision–recall curve, a bin's events spread evenly over its rows
    (Davis and Goadrich's interpolation); NaN without events.

    Inside a bin of `r` rows and `e` events below `R` rows and `E` events, precision runs along
    `(E + t·e) / (R + t·r)`, t from 0 to 1, whose mean is `e/r + (E·r − e·R) / r² · ln(1 + r/R)`
    (`e/r` in the top bin). Scikit-learn's on the binned scores gives every event of a bin the
    bin's last precision, further below the rows' value.
    """
    total = events.sum()
    if not total > 0:
        return NAN
    r, e = rows[::-1], events[::-1]  # from the top score bin
    filled = r > 0
    r, e, above_r, above_e = (v[filled] for v in (r, e, np.cumsum(r) - r, np.cumsum(e) - e))
    growth = np.divide(r, above_r, out=np.zeros(r.size), where=above_r > 0)  # 0: the top bin
    precision = e / r + (above_e * r - e * above_r) / r**2 * np.log1p(growth)
    return float((e * precision).sum() / total)


def _log_likelihood(beta: np.ndarray, x: np.ndarray, n: np.ndarray, k: np.ndarray) -> float:
    """The binomial log-likelihood of `k` events in `n` rows at logit `beta[0] + beta[1]·x`."""
    eta = beta[0] + beta[1] * x
    return float((k * eta - n * np.logaddexp(0, eta)).sum())


def _newton_step(beta: np.ndarray, x: np.ndarray, n: np.ndarray, k: np.ndarray) -> np.ndarray:
    """Newton's step on (intercept, slope): the 2 × 2 information matrix solved for the score."""
    p = expit(beta[0] + beta[1] * x)
    w, residual = n * p * (1 - p), k - n * p
    h00, h01, h11 = w.sum(), (w * x).sum(), (w * x * x).sum()
    g0, g1 = residual.sum(), (residual * x).sum()
    determinant = h00 * h11 - h01**2
    if not determinant > 0:
        return np.array([NAN, NAN])
    return np.array([h11 * g0 - h01 * g1, h00 * g1 - h01 * g0]) / determinant


def _calibration_line(x: np.ndarray, n: np.ndarray, k: np.ndarray) -> tuple[float, float]:
    """The slope and intercept of the logistic regression of the target on the score's logit,
    fitted on cells: `n` rows at the mean logit `x`, `k` of them events.

    Newton's method from the calibrated line (slope 1, intercept 0), a step halved while it
    lowers the likelihood. NaN when no maximum exists: one class or one logit only, or labels the
    logit separates (no convergence within `NEWTON_STEPS`).
    """
    if not 0 < k.sum() < n.sum() or np.ptp(x) == 0:
        return NAN, NAN
    beta = np.array([0.0, 1.0])
    likelihood = _log_likelihood(beta, x, n, k)
    for _ in range(NEWTON_STEPS):
        step = _newton_step(beta, x, n, k)
        if not np.isfinite(step).all():
            return NAN, NAN
        moved = _log_likelihood(beta + step, x, n, k)
        while not moved >= likelihood and np.abs(step).max() > STEP_TOLERANCE:
            step = step / 2
            moved = _log_likelihood(beta + step, x, n, k)
        beta, likelihood = beta + step, moved
        if np.abs(step).max() <= STEP_TOLERANCE:
            return float(beta[1]), float(beta[0])
    return NAN, NAN


def _require_sums(total: dict[str, float], columns: list[str]) -> None:
    """Fail loud when a loss sum the caller declared present (`loss=True`) is null in a cell."""
    for column in columns:
        if np.isnan(total[column]):
            raise ValueError(
                f"the score cells' `{column}` is null in some cell, yet loss=True declared the "
                "scorer's loss sums present; pass loss=False for a scorer without them"
            )


def binary_metrics(cells: pd.DataFrame, base: float, loss: bool = True) -> dict[str, float]:
    """A 0/1 target's metrics on one replicate's cells of one part.

    `base` is the unsampled train split's rate, the forecast of no skill. `loss` says, decided
    up front, whether the cells carry the scorer's loss sums, `loss_sum` and `link_sum` (the
    scorer is a probability: a model, not a raw feature as a baseline); without them the
    probability metrics are NaN, and declared but null fails loud. Keys: `rows`, `events`,
    `base_rate` (the part's), `roc_auc`, `ap`, `log_loss`, `log_loss_skill` and `brier_skill`
    (`1 − loss / loss of the constant forecast base`), `observed_to_expected` (events over the
    summed score) and `calibration_slope` and `calibration_intercept` (the logistic regression of
    the target on the score's logit, 1 and 0 when calibrated). The ranks are the binned scores';
    the logit is a cell's mean.
    """
    if not 0 < base < 1:
        raise ValueError(f"binary_metrics: the base rate must lie in (0, 1), got {base}")
    total = _totals(cells)
    grid = _grid(cells, ["rows", "target_sum", "link_sum"])
    rows, events = total["rows"], total["target_sum"]
    rate = events / rows
    base_log_loss = -(rate * np.log(base) + (1 - rate) * np.log1p(-base))
    base_brier = rate * (1 - 2 * base) + base**2  # the mean of (y − base)² for a 0/1 y
    slope, intercept, log_loss = NAN, NAN, NAN
    if loss:
        _require_sums(total, ["loss_sum", "link_sum"])
        filled = grid["rows"] > 0
        n, k = grid["rows"][filled], grid["target_sum"][filled]
        slope, intercept = _calibration_line(grid["link_sum"][filled] / n, n, k)
        log_loss = total["loss_sum"] / rows
    return {
        "rows": rows, "events": events, "base_rate": rate,
        "roc_auc": _concordance(grid["rows"]),
        "ap": _average_precision(grid["rows"].sum(axis=1), grid["target_sum"].sum(axis=1)),
        "log_loss": log_loss, "log_loss_skill": 1 - log_loss / base_log_loss,
        "brier_skill": 1 - total["sq_error_sum"] / rows / base_brier if loss else NAN,
        "observed_to_expected": _ratio(events, total["score_sum"]) if loss else NAN,
        "calibration_slope": slope, "calibration_intercept": intercept,
    }  # fmt: skip


def regression_metrics(cells: pd.DataFrame, base: float, loss: bool = True) -> dict[str, float]:
    """An amount's metrics on one replicate's cells of one part.

    `loss` says, decided up front, whether the cells carry the scorer's loss sum, a deviance in
    `loss_sum` (the objective or the decision names one); without it `deviance` is NaN, and
    declared but null fails loud.
    Keys: `rows`, `events` (rows with a non-zero target: a cell whose target sums to 0, EDA's
    zero bin rule), `mean`, `rmse`, `mae`, `r2` (against the part's own mean), `deviance` (the
    mean of the cells' row loss), `concordance` (EDA's scale, from
    the score bin × target bin table) and `predicted_to_observed` (the mean score over the mean
    target). `base` goes unread: it is in the signature every task's `cell_metrics` shares.
    """
    total = _totals(cells)
    if loss:
        _require_sums(total, ["loss_sum"])
    grid = _grid(cells, ["rows"])
    rows, target = total["rows"], total["target_sum"]
    nonzero = cells["target_sum"].to_numpy(dtype=float) != 0
    spread = total["target_sq_sum"] - target**2 / rows  # Σ(y − mean)²
    return {
        "rows": rows,
        "events": float(cells["rows"].to_numpy(dtype=float)[nonzero].sum()),
        "mean": target / rows,
        "rmse": float(np.sqrt(total["sq_error_sum"] / rows)),
        "mae": total["abs_error_sum"] / rows,
        "r2": 1 - total["sq_error_sum"] / spread if spread > 0 else NAN,
        "deviance": total["loss_sum"] / rows if loss else NAN,
        "concordance": _concordance(grid["rows"]),
        "predicted_to_observed": _ratio(total["score_sum"], target),
    }


def slice_labels(slices: "Slices") -> list[str]:
    """Each slice's label in config order, as the `slices` tables name it: a `top_pct` as
    `top 5%`, a `top_n` as `top 10,000`."""
    return [f"top {share * 100:g}%" for share in slices.top_pct] + [
        f"top {n:,}" for n in slices.top_n
    ]


def _slice_shares(slices: "Slices", population: int) -> tuple[list[str], np.ndarray]:
    """Each slice's label and the share of the part's rows it cuts: a `top_pct` as given, a
    `top_n` as `n / population`, NaN above the population (not available)."""
    if not population > 0:
        raise ValueError(f"slice_metrics: the population must be positive, got {population}")
    shares = [*slices.top_pct, *(n / population if n <= population else NAN for n in slices.top_n)]
    return slice_labels(slices), np.array(shares, dtype=float)


def slice_metrics(cells: pd.DataFrame, slices: "Slices", population: int) -> pd.DataFrame:
    """One period's slices of one part, cut from the top of the score as additive counts.

    A `top_pct` is a share of the part's rows in the period; a `top_n` is read as the share
    `n / population` of the period's eligible rows over both splits and cut at that share inside
    the part, and above the population it is not available. The cut bin is split in proportion
    to its rows. Returns one row per slice in config order: `slice` (`top 5%`, `top 10,000`),
    `rows`, `target` (the events or the amount inside), `part_rows`, `part_target` and
    `unavailable` (the reason, '' when available; the counts are then null). `slice_rates` adds
    the periods and derives capture, rate and lift.
    """
    _check_cells(cells)
    period = cells["period"].to_numpy()
    if (period != period[0]).any():
        raise ValueError("slice_metrics: the cells hold several periods; slices are cut per period")
    sums = _by_score_bin(cells, ["rows", "target_sum"])
    depth = np.concatenate([[0.0], np.cumsum(sums["rows"][::-1])])  # from the top score bin
    reached = np.concatenate([[0.0], np.cumsum(sums["target_sum"][::-1])])
    labels, shares = _slice_shares(slices, population)
    rows = shares * depth[-1]
    target = np.where(np.isnan(rows), NAN, np.interp(np.nan_to_num(rows), depth, reached))
    reason = np.where(
        np.isnan(shares), f"not available: above the population of {population:,}", ""
    )
    return pd.DataFrame({
        "slice": labels, "rows": rows, "target": target, "part_rows": depth[-1],
        "part_target": reached[-1], "unavailable": reason,
    })  # fmt: skip


def slice_rates(counts: pd.DataFrame) -> pd.DataFrame:
    """Each slice's capture, rate and lift from `slice_metrics`' counts of one part, its
    periods' tables stacked and added up first (one period's table works alike).

    A slice not available in one period is not available in the sum: its reason is kept and its
    numbers are null, so no period drops out silently. Adds `capture` (the share of the part's
    events or amount; NaN when that total is not positive), `rate` (the precision or the mean
    inside) and `lift` (the rate over the part's; NaN when the part's is not positive).
    """
    if "part" in counts and counts["part"].nunique() > 1:
        raise ValueError("slice_rates: the counts hold several parts; pass one part's periods")
    grouped = counts.groupby("slice", sort=False)
    added = grouped[SLICE_COUNTS].sum().join(grouped["unavailable"].max()).reset_index()
    added.loc[added["unavailable"] != "", ["rows", "target"]] = NAN  # '' sorts below a reason
    part_rate = added["part_target"] / added["part_rows"]
    return added.assign(
        capture=added["target"] / added["part_target"].where(added["part_target"] > 0),
        rate=added["target"] / added["rows"],
        lift=added["target"] / added["rows"] / part_rate.where(part_rate > 0),
    )


def threshold_table(cells: pd.DataFrame, roc: bool) -> pd.DataFrame:
    """The curves' table of one part: one row per score bin from the top, cumulative.

    Columns: `score_bin`; `threshold` (the bin's lowest score: the rows at or above it are in);
    `rows` and `target` (the events or the amount) so far; `depth` and `capture`, their shares
    of the part's; `rate` (the precision or the mean so far); `lift` (the rate over the part's);
    `false_positive_rate` (the non-events so far over all, the ROC's x) with `roc` (a 0/1
    target, the task's `roc_curve`), else null. ROC, precision–recall and capture are its
    columns.
    """
    sums = _by_score_bin(cells, ["rows", "target_sum"])
    lowest = cells.groupby("score_bin")["score_min"].min().to_numpy()  # bins ascending, as sums
    rows, target = np.cumsum(sums["rows"][::-1]), np.cumsum(sums["target_sum"][::-1])
    part_rows, part_target = rows[-1], target[-1]
    part_rate = part_target / part_rows
    false_positive_rate = np.full(rows.size, NAN)
    if roc and part_rows > part_target:
        false_positive_rate = (rows - target) / (part_rows - part_target)
    return pd.DataFrame({
        "score_bin": sums["score_bin"][::-1], "threshold": lowest[::-1], "rows": rows,
        "target": target, "depth": rows / part_rows,
        "capture": target / part_target if part_target > 0 else NAN, "rate": target / rows,
        "lift": target / rows / part_rate if part_rate > 0 else NAN,
        "false_positive_rate": false_positive_rate,
    })  # fmt: skip


def reliability_table(cells: pd.DataFrame, groups: int = 10) -> pd.DataFrame:
    """The mean score beside the mean target in `groups` groups of about equal rows, cut on the
    score bins (a bin joins the group its middle row falls in), lowest scores first.

    Columns: `group` (0 the lowest; an empty group is left out), `rows`, `predicted` (the mean
    score) and `observed` (the mean target). Regression's predicted-to-observed chart reads it at
    20 groups; over its 50 bins, dense at the top, a lower group holds one or two bins (3.6% or
    7.2% of the rows), not 5%.
    """
    sums = _by_score_bin(cells, ["rows", "score_sum", "target_sum"])
    middle = np.cumsum(sums["rows"]) - sums["rows"] / 2
    group = np.minimum((middle / sums["rows"].sum() * groups).astype(int), groups - 1)
    rows, score, target = (np.bincount(group, sums[name], groups)
                           for name in ("rows", "score_sum", "target_sum"))  # fmt: skip
    kept = rows > 0
    return pd.DataFrame({
        "group": np.arange(groups)[kept], "rows": rows[kept],
        "predicted": score[kept] / rows[kept], "observed": target[kept] / rows[kept],
    })  # fmt: skip


def distribution_table(
    cells: pd.DataFrame, target_class: Callable[[pd.Series], pd.Series]
) -> pd.DataFrame:
    """The score's distribution per target class of one part: one row per score bin and class.

    `target_class` is the task's (`TASK_SPECS[task]["target_class"]`), applied to each target
    bin's mean target: `0` and `1`, or `zero` and `non-zero`. Columns: `score_bin`, `score` (the
    bin's mean score over every class), `percentile` (the share of all rows up to and including
    the bin, from the lowest score), `class` (in target order), `rows`, `share` (of the class's
    rows; 0 in a bin without the class) and `ratio` (`share` over the bin's share of all rows: 1
    is chance). The bins hold unequal rows (`bin_quantiles`), so a class is read by its
    `ratio` against `percentile`, never by `share` per bin.
    """
    grid = _grid(cells, ["rows", "score_sum", "target_sum"])
    by_bin = grid["rows"].sum(axis=1)
    bin_share = by_bin / by_bin.sum()
    score = grid["score_sum"].sum(axis=1) / by_bin
    classes = target_class(pd.Series(grid["target_sum"].sum(axis=0) / grid["rows"].sum(axis=0)))
    frames = []
    for name in pd.unique(classes):
        rows = grid["rows"][:, (classes == name).to_numpy()].sum(axis=1)
        share = rows / rows.sum()
        frames.append(pd.DataFrame({
            "score_bin": grid["score_bin"], "score": score, "percentile": np.cumsum(bin_share),
            "class": name, "rows": rows, "share": share, "ratio": share / bin_share,
        }))  # fmt: skip
    return pd.concat(frames, ignore_index=True)
