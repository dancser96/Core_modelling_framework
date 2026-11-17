"""The decision's metric as a loss on rows, and the row concordance (statistics/losses.py)."""

import numpy as np
import pytest
from sklearn.exceptions import UndefinedMetricWarning
from sklearn.metrics import log_loss, roc_auc_score

from core_modelling.statistics.losses import (
    LOSSES,
    mean_fold_loss,
    metric_loss,
    metric_value,
    row_concordance,
)


def _rows(seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """A 0/1 target and a prediction rounded to one decimal, so many predictions tie."""
    rng = np.random.default_rng(seed)
    y = (rng.random(3000) < 0.1).astype(float)
    return y, np.round(rng.normal(size=3000) + y, 1)


def _pair_concordance(y: np.ndarray, prediction: np.ndarray) -> float:
    """The concordance by counting pairs: over the pairs with different targets, the share the
    prediction orders as the target does, a tied prediction counting half."""
    target = np.sign(y[:, None] - y[None, :])
    predicted = np.sign(prediction[:, None] - prediction[None, :])
    untied = target != 0
    return float((0.5 * (target * predicted + 1))[untied].mean())


def test_the_row_concordance_is_the_auc_for_a_binary_target() -> None:
    """With ties in the prediction it equals scikit-learn's AUC, which counts a tie half."""
    y, prediction = _rows()
    assert row_concordance(y, prediction) == pytest.approx(roc_auc_score(y, prediction), abs=1e-12)


def test_the_row_concordance_counts_pairs_for_an_amount() -> None:
    """A zero-inflated amount with ties in both: the value equals the pair count's; a constant
    prediction orders nothing (0.5), and a target with one value fails loud."""
    rng = np.random.default_rng(1)
    y = np.where(rng.random(400) < 0.5, 0.0, np.round(rng.gamma(2.0, size=400), 1))
    prediction = np.round(0.5 * y + rng.normal(size=400), 1)
    assert row_concordance(y, prediction) == pytest.approx(_pair_concordance(y, prediction))
    assert row_concordance(y, np.zeros(400)) == 0.5
    with pytest.raises(ValueError, match="two different target values"):
        row_concordance(np.ones(10), prediction[:10])


def test_the_row_concordance_refuses_a_non_finite_prediction() -> None:
    """A NaN or an infinite prediction fails loud instead of ranking as a tie or a maximum."""
    y, prediction = _rows()
    for bad in (np.nan, np.inf):
        with pytest.raises(ValueError, match="finite targets and predictions"):
            row_concordance(y, np.where(np.arange(len(y)) == 0, bad, prediction))


def test_a_loss_is_lower_is_better_and_reads_back_as_its_metric() -> None:
    """`1 − AUC` reads back as the AUC, the log loss as itself; the fold loss is the mean of
    the folds' losses; an unknown metric and a non-finite loss fail loud."""
    y, prediction = _rows()
    probability = 1 / (1 + np.exp(-prediction))
    assert metric_value("roc_auc", metric_loss("roc_auc", y, probability)) == pytest.approx(
        roc_auc_score(y, probability)
    )
    assert metric_loss("log_loss", y, probability) == pytest.approx(log_loss(y, probability))
    fold = np.arange(len(y)) % 3
    by_fold = [LOSSES["log_loss"](y[fold == k], probability[fold == k]) for k in range(3)]
    assert mean_fold_loss("log_loss", y, probability, fold) == pytest.approx(np.mean(by_fold))
    with pytest.raises(ValueError, match="no loss for the metric 'accuracy'"):
        metric_loss("accuracy", y, probability)
    with pytest.warns(UndefinedMetricWarning), pytest.raises(ValueError, match="must be finite"):
        metric_loss("roc_auc", np.zeros(20), probability[:20])  # one class: NaN in scikit-learn
