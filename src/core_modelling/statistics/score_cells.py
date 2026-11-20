"""The score cells: the one aggregate of a scorer's scores that every Evaluation metric reads (A92).

A scorer's cells hold one row per part, period, the columns of `by`, score bin and target bin,
with the sums the metrics need, each row weighted by its client's weight (1 at replicate 0, a
Poisson draw in a bootstrap replicate, A94). The Spark aggregate (`evaluation/cells.py`) builds
them over every scored row, with a `replicate` column; `cells_from_rows` is its pandas mirror for
one replicate, on rows already binned: the oracle the Spark aggregate is tested against and the
cells the metric tests build. `pool_cells` sums a `by` column's levels away (the `all` cells
from the `split` ones). Score bins are quantile bins of the scorer's column, cut once per
scorer over every scored row at `bin_quantiles` (`SCORE_GRID`; every `STRATA_STEP`-th edge for
the strata's cells), narrowing towards the top rows, where the average precision and the top
slices are read. A regression target's bins are EDA's (`tasks.TARGET_BINS`, zero its own bin).

The sums are taken per row, so the log loss, the Brier score, the errors and the deviance are
exact, and only the rank metrics, the slices, the curves and the calibration slope carry the
binning's tolerance. `loss_sum` is the sum of one of `ROW_LOSSES`, named by the caller, and
`link_sum` the clipped score's logit, filled for the log loss only (a probability): both are
null for a scorer without such a loss. Pure pandas and numpy.
"""

import numpy as np
import pandas as pd
from scipy.special import logit, xlogy

from core_modelling.statistics.losses import TWEEDIE_METRIC_POWER

PARTS = ("test", "validation")  # the values of `part`, as `build_frames(…, "evaluation")` gives
POOLED = "pooled"  # the period of a row over all of its part's periods (the tables, the charts)
MEAN = "mean"  # the period of the row holding the plain mean of the periods' values
# The cell's keys; the columns of `by` follow `period`, and the Spark frame adds `replicate`.
CELL_KEYS = ["part", "period", "score_bin", "target_bin"]
# Weighted sums (A92): `sq_error_sum` is the Brier sum of a binary target.
CELL_SUMS = ["rows", "target_sum", "score_sum", "sq_error_sum", "abs_error_sum", "loss_sum",
             "target_sq_sum", "link_sum"]  # fmt: skip
CELL_EXTREMES = ["score_min", "score_max"]  # the cell's unweighted extremes (the drift edges)
# A task's score grid (A93): `(upper, bins)` segments from the lowest score, each `bins` bins of
# equal rows up to the cumulative share `upper` of the rows. Binary's bins narrow towards the
# top, where the average precision, the top slices and the calibration intercept are read:
# 100 of 0.9% up to 0.9, 90 of 0.1%, 90 of 0.01% and 100 of 0.001% (380 bins). Regression's
# 50 (25 of 3.6%, 25 of 0.4%) meet its 20 target bins, near binary's cell count.
SCORE_GRID = {
    "binary": [(0.9, 100), (0.99, 90), (0.999, 90), (1.0, 100)],
    "regression": [(0.9, 25), (1.0, 25)],
}
STRATA_STEP = {"binary": 4, "regression": 1}  # a stratum's bin: this many score bins
# Where a task's tail starts: the rows above it are cut by a quantile pass of their own
# (`evaluation/cells.py::score_edges`), since its narrowest bins are below one pass's rank error
TAIL_START = {"binary": 0.99}
PROBABILITY_CLIP = 1e-15  # the log loss and the logit read the score clipped to [c, 1 − c]


def bin_quantiles(task: str) -> np.ndarray:
    """The interior cumulative probabilities, ascending, at which a scorer's column is cut:
    `SCORE_GRID[task]`'s segments, each split into its equal bins.

    Binned on binary's, on 1 to 2 million simulated rows at base rates from 0.05% to 5%, the
    average precision lay within 0.0015 of the rows' (at most 4% of it low, a weak score at
    0.05%), the calibration slope within 0.0003 and the intercept within 0.0015 of the row fit;
    the former 200 bins (none below 0.1%) read it up to 5% low at 1% and up to 61% low below.
    Every `STRATA_STEP[task]`-th edge is the strata's grid, binary's 95 bins: a stratum's
    average precision 0.0007 low at a 2.9% rate, where 50 bins read it 0.010 (4%) low.
    """
    cuts, lower = [], 0.0
    for upper, bins in SCORE_GRID[task]:
        cuts.append(np.linspace(lower, upper, bins + 1)[1:])
        lower = upper
    return np.concatenate(cuts)[:-1]


def quantile_passes(task: str) -> tuple[np.ndarray, np.ndarray]:
    """`bin_quantiles(task)` as Spark takes them: the body's over every row, ending at
    `TAIL_START[task]`, and the tail's over the rows at or above that edge, as shares of those
    rows (empty for a task without a tail)."""
    cuts = bin_quantiles(task)
    start = TAIL_START.get(task)
    if start is None:
        return cuts, np.array([])
    if start not in cuts:
        raise ValueError(f"quantile_passes: {task}'s tail start {start} is no edge of its grid")
    in_tail = cuts > start
    return cuts[~in_tail], (cuts[in_tail] - start) / (1 - start)


def _clipped(score: np.ndarray) -> np.ndarray:
    """The score clipped to [`PROBABILITY_CLIP`, 1 − `PROBABILITY_CLIP`]: a score of exactly 0
    or 1 (a float64 sigmoid at an extreme margin) keeps the log finite."""
    return np.clip(score, PROBABILITY_CLIP, 1 - PROBABILITY_CLIP)


def _log_loss(target: np.ndarray, score: np.ndarray) -> np.ndarray:
    """Per row, `−(y·ln p + (1 − y)·ln(1 − p))` on the clipped score `p`; a 0/1 target and a
    score in [0, 1] only."""
    if not (np.isin(target, (0, 1)).all() and ((score >= 0) & (score <= 1)).all()):
        raise ValueError("the log loss needs a 0/1 target and a score in [0, 1] on every row")
    p = _clipped(score)
    return -(target * np.log(p) + (1 - target) * np.log1p(-p))


def _check_deviance(target: np.ndarray, score: np.ndarray, name: str) -> None:
    """A deviance needs a target at or above 0 and a score above 0 on every row."""
    if (target < 0).any() or (score <= 0).any():
        raise ValueError(
            f"the {name} needs targets >= 0 and scores > 0; got {(target < 0).sum():,} negative "
            f"targets and {(score <= 0).sum():,} scores <= 0"
        )


def _tweedie_deviance(target: np.ndarray, score: np.ndarray) -> np.ndarray:
    """Per row, the unit Tweedie deviance at `TWEEDIE_METRIC_POWER` p (1 < p < 2):
    `2·(y^(2−p) / ((1−p)(2−p)) − y·μ^(1−p) / (1−p) + μ^(2−p) / (2−p))`, scikit-learn's form."""
    _check_deviance(target, score, "Tweedie deviance")
    p = TWEEDIE_METRIC_POWER
    return 2 * (
        target ** (2 - p) / ((1 - p) * (2 - p))
        - target * score ** (1 - p) / (1 - p)
        + score ** (2 - p) / (2 - p)
    )


def _poisson_deviance(target: np.ndarray, score: np.ndarray) -> np.ndarray:
    """Per row, the unit Poisson deviance `2·(y·ln(y / μ) − y + μ)`, `y·ln(y / μ)` 0 at y = 0."""
    _check_deviance(target, score, "Poisson deviance")
    return 2 * (xlogy(target, target / score) - target + score)


# The losses `loss_sum` can hold; their mean over the rows is scikit-learn's metric of that name.
ROW_LOSSES = {
    "log_loss": _log_loss,
    "tweedie_deviance": _tweedie_deviance,
    "poisson_deviance": _poisson_deviance,
}


def _check_rows(rows: pd.DataFrame, by: list[str], loss: str | None) -> None:
    """Fail loud on a missing column, no rows, an unknown loss, a non-finite target or score,
    or a negative or non-finite weight."""
    needed = ["part", "period", *by, "score_bin", "target_bin", "target", "score", "weight"]
    missing = [column for column in needed if column not in rows]
    if missing:
        raise ValueError(f"cells_from_rows: the rows lack the columns {missing}")
    if rows.empty:
        raise ValueError("cells_from_rows: no rows to aggregate")
    if loss is not None and loss not in ROW_LOSSES:
        raise ValueError(f"cells_from_rows: unknown loss {loss!r}; known: {sorted(ROW_LOSSES)}")
    for column in ("target", "score", "weight"):
        if not np.isfinite(rows[column].to_numpy(dtype=float)).all():
            raise ValueError(f"cells_from_rows: `{column}` must be finite on every row")
    if (rows["weight"] < 0).any():
        raise ValueError("cells_from_rows: a client weight is negative")


def cells_from_rows(rows: pd.DataFrame, by: list[str], loss: str | None) -> pd.DataFrame:
    """One replicate's score cells from binned rows: the pandas mirror of the Spark aggregate.

    Receives one row per scored row with `part, period, *by, score_bin, target_bin, target,
    score, weight` (the client's weight in this replicate, 1 at replicate 0). A row of weight 0
    is not drawn and counts nowhere, so only non-empty cells are rows and the extremes are the
    drawn rows'. `loss` names the row loss `loss_sum` adds up (`ROW_LOSSES`): `log_loss` for a
    probability, which also fills `link_sum`, `tweedie_deviance` or `poisson_deviance` for a
    regression scorer whose objective or decision names one, None for a scorer without (a raw
    feature, a squared-error model): those sums are then null.

    Returns one row per cell (`CELL_KEYS` with `by`'s columns after `period`, sorted by them)
    with `CELL_SUMS` and `CELL_EXTREMES`; a null in a `by` column is a level of its own.
    """
    _check_rows(rows, by, loss)
    drawn = rows.loc[rows["weight"] > 0]
    target, score = drawn["target"].to_numpy(dtype=float), drawn["score"].to_numpy(dtype=float)
    weight = drawn["weight"].to_numpy()
    error, null = target - score, np.full(len(drawn), np.nan)
    terms = {
        "rows": weight,
        "target_sum": weight * target,
        "score_sum": weight * score,
        "sq_error_sum": weight * error**2,
        "abs_error_sum": weight * np.abs(error),
        "loss_sum": weight * ROW_LOSSES[loss](target, score) if loss else null,
        "target_sq_sum": weight * target**2,
        "link_sum": weight * logit(_clipped(score)) if loss == "log_loss" else null,
        "score_min": score,
        "score_max": score,
    }
    keys = ["part", "period", *by, "score_bin", "target_bin"]
    grouped = drawn[keys].assign(**terms).groupby(keys, dropna=False, sort=True)
    sums = grouped[CELL_SUMS].sum(min_count=1)  # min_count: a null loss or link stays null
    extremes = grouped.agg(score_min=("score_min", "min"), score_max=("score_max", "max"))
    return sums.join(extremes).reset_index()


def pool_cells(cells: pd.DataFrame, over: str) -> pd.DataFrame:
    """The cells with the levels of `over` pooled: the `split` cells summed over `split` are the
    `all` cells, so Spark sums them once per scorer.

    Receives cells (`CELL_KEYS` with `by`'s columns, `replicate` when there, `CELL_SUMS`,
    `CELL_EXTREMES`); returns one row per remaining key, the columns in the same order without
    `over`, sorted by the keys: the sums added (a null sum stays null), the extremes their min
    and max. An `over` that is no `by` column of the cells fails loud.
    """
    measures = [*CELL_SUMS, *CELL_EXTREMES]
    if over not in cells.columns or over in [*CELL_KEYS, "replicate", *measures]:
        raise ValueError(f"pool_cells: {over!r} is no `by` column of the cells")
    keys = [column for column in cells.columns if column not in [*measures, over]]
    grouped = cells.groupby(keys, dropna=False, sort=True)
    sums = grouped[CELL_SUMS].sum(min_count=1)
    extremes = grouped.agg(score_min=("score_min", "min"), score_max=("score_max", "max"))
    return sums.join(extremes).reset_index()
