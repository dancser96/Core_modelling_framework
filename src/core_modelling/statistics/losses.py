"""The decision's metric as a loss on rows: what Training minimises out of fold (D-140 (d)).

One function per metric name of `TASK_CHOICES` (FLAML's names, T9), each lower-is-better and
defined as FLAML defines its own (`1 − AUC`, `1 − AP`, `1 − R²`), so the framework's fold loss
of a configuration is the number FLAML's search reported for it. The pruning's comparison, the
fold models' out-of-fold metric and the search's two deviance metrics all read `LOSSES`.
`concordance` is no decision metric: it is the rank metric Training stores beside every
headline (the AUC for a binary target), out of fold and in sample (D-106).
`prediction` is always `score_raw` (`model/calibration.py`): the probability for a binary
task, the prediction in the target's units for regression. The Tweedie deviance is taken at a
fixed variance power, whatever the objective's, so a training setting cannot move the yardstick
(A67). Evaluation's metrics are computed on score cells (`metrics.py`, M2.3 step 3); these row
forms are their oracle in the tests.
"""

from collections.abc import Callable

import numpy as np
from scipy.stats import kendalltau
from sklearn.metrics import (
    average_precision_score,
    log_loss,
    mean_absolute_error,
    mean_poisson_deviance,
    mean_tweedie_deviance,
    r2_score,
    roc_auc_score,
    root_mean_squared_error,
)

TWEEDIE_METRIC_POWER = 1.5  # the yardstick's variance power, never the objective's (A67)


def _binary_log_loss(y: np.ndarray, prediction: np.ndarray) -> float:
    """The mean log loss of a 0/1 target; scikit-learn clips a probability of exactly 0 or 1."""
    return float(log_loss(y, prediction, labels=[0, 1]))


def _tweedie_deviance(y: np.ndarray, prediction: np.ndarray) -> float:
    """The mean Tweedie deviance at `TWEEDIE_METRIC_POWER`; a prediction at or below zero fails."""
    return float(mean_tweedie_deviance(y, prediction, power=TWEEDIE_METRIC_POWER))


def row_concordance(y: np.ndarray, prediction: np.ndarray) -> float:
    """The share of row pairs with different targets that `prediction` orders as the target
    does, a tied prediction counting half: the AUC for a 0/1 target, the concordance for an
    amount. It is `(D + 1) / 2` with Somers' D of the prediction given the target, taken from
    Kendall's tau-b and the two tie counts (`D = tau_b · √(untied in prediction / untied in
    target)`), so it costs n log n. A target with one value, or a non-finite entry, fails loud."""
    y, prediction = np.asarray(y, dtype=np.float64), np.asarray(prediction, dtype=np.float64)
    if not (np.isfinite(y).all() and np.isfinite(prediction).all()):
        raise ValueError("the concordance needs finite targets and predictions on every row")
    pairs = len(y) * (len(y) - 1) / 2
    untied_target = pairs - _tied_pairs(y)
    untied_prediction = pairs - _tied_pairs(prediction)
    if untied_target == 0:
        raise ValueError(
            f"the concordance needs two different target values; the {len(y):,} rows hold one"
        )
    if untied_prediction == 0:  # a constant prediction orders nothing; tau is undefined there
        return 0.5
    tau = kendalltau(prediction, y, variant="b").statistic
    return float((tau * np.sqrt(untied_prediction / untied_target) + 1) / 2)


def _tied_pairs(values: np.ndarray) -> float:
    """The number of row pairs that share a value: `Σ t(t − 1) / 2` over the distinct values."""
    counts = np.unique(values, return_counts=True)[1].astype(np.float64)
    return float((counts * (counts - 1) / 2).sum())


LOSSES: dict[str, Callable[[np.ndarray, np.ndarray], float]] = {
    "concordance": lambda y, prediction: 1.0 - row_concordance(y, prediction),
    "log_loss": _binary_log_loss,
    "roc_auc": lambda y, prediction: 1.0 - float(roc_auc_score(y, prediction)),
    "ap": lambda y, prediction: 1.0 - float(average_precision_score(y, prediction)),
    "rmse": lambda y, prediction: float(root_mean_squared_error(y, prediction)),
    "mae": lambda y, prediction: float(mean_absolute_error(y, prediction)),
    "r2": lambda y, prediction: 1.0 - float(r2_score(y, prediction)),
    "tweedie_deviance": _tweedie_deviance,
    "poisson_deviance": lambda y, prediction: float(mean_poisson_deviance(y, prediction)),
}


# stored as `1 − metric`; every other loss is the metric
ONE_MINUS = ("concordance", "roc_auc", "ap", "r2")


def metric_value(metric: str, loss: float) -> float:
    """A loss read back as its metric, for display: `1 − loss` for AUC, AP and R², else the
    loss itself (log loss, RMSE, MAE and the deviances are already lower-is-better)."""
    return 1.0 - loss if metric in ONE_MINUS else loss


def metric_loss(metric: str, y: np.ndarray, prediction: np.ndarray) -> float:
    """`metric` as a loss on the rows given; an unknown name or a non-finite loss fails loud (a
    rank metric on rows of one class is NaN with a warning in scikit-learn 1.8, refused here)."""
    if metric not in LOSSES:
        raise ValueError(f"no loss for the metric {metric!r}; known: {sorted(LOSSES)}")
    loss = LOSSES[metric](np.asarray(y), np.asarray(prediction, dtype=np.float64))
    if not np.isfinite(loss):
        raise ValueError(f"the {metric} loss is {loss} on {len(y):,} rows; it must be finite")
    return loss


def mean_fold_loss(metric: str, y: np.ndarray, prediction: np.ndarray, fold: np.ndarray) -> float:
    """The mean over the folds of `metric_loss` on each fold's rows, as the search averages a
    trial's folds: `y`, `prediction` and `fold` are aligned, one entry per row."""
    y, prediction, fold = np.asarray(y), np.asarray(prediction), np.asarray(fold)
    losses = [metric_loss(metric, y[fold == k], prediction[fold == k]) for k in np.unique(fold)]
    return float(np.mean(losses))
