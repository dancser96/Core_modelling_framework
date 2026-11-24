"""The score cells from rows in pandas: the tests' oracle for the Spark aggregate.

`cells_from_rows` sums one replicate's rows, already binned, into the cells
`evaluation/cells.py::score_cells` collects from Spark, with the same row losses written in
numpy. The Spark mirror test holds the two together, and the metric tests build their cells
here; `test_metrics.py` ties each row loss's mean to scikit-learn's metric of that name.
"""

import numpy as np
import pandas as pd
from scipy.special import logit, xlogy

from core_modelling.statistics.losses import TWEEDIE_METRIC_POWER
from core_modelling.statistics.score_cells import CELL_SUMS, PROBABILITY_CLIP


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


# The oracle's row losses, by the names `evaluation/cells.py::ROW_LOSSES` gives them
ORACLE_LOSSES = {
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
    if loss is not None and loss not in ORACLE_LOSSES:
        raise ValueError(f"cells_from_rows: unknown loss {loss!r}; known: {sorted(ORACLE_LOSSES)}")
    for column in ("target", "score", "weight"):
        if not np.isfinite(rows[column].to_numpy(dtype=float)).all():
            raise ValueError(f"cells_from_rows: `{column}` must be finite on every row")
    if (rows["weight"] < 0).any():
        raise ValueError("cells_from_rows: a client weight is negative")


def cells_from_rows(rows: pd.DataFrame, by: list[str], loss: str | None) -> pd.DataFrame:
    """One replicate's score cells from binned rows, as the Spark aggregate sums them.

    Receives one row per scored row with `part, period, *by, score_bin, target_bin, target,
    score, weight` (the client's weight in this replicate, 1 at replicate 0). A row of weight 0
    is not drawn and counts nowhere, so only non-empty cells are rows and the extremes are the
    drawn rows'. `loss` names the row loss `loss_sum` adds up: `log_loss` for a probability,
    which also fills `link_sum`, `tweedie_deviance` or `poisson_deviance`, or None (those sums
    are then null).

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
        "loss_sum": weight * ORACLE_LOSSES[loss](target, score) if loss else null,
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
