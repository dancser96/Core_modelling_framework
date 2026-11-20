"""The metrics on score cells (statistics/metrics.py, score_cells.py) against scikit-learn on the
rows the cells were built from: exact for the sums, within the binning's tolerance for the
ranks, the average precision and the calibration line."""

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest
from scipy.special import expit, logit
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    mean_poisson_deviance,
    mean_tweedie_deviance,
    r2_score,
    roc_auc_score,
    root_mean_squared_error,
)

from core_modelling.config.schema import Slices
from core_modelling.statistics.calibration import UNPENALISED
from core_modelling.statistics.losses import row_concordance
from core_modelling.statistics.metrics import (
    binary_metrics,
    distribution_table,
    regression_metrics,
    reliability_table,
    slice_metrics,
    slice_rates,
    threshold_table,
)
from core_modelling.statistics.score_cells import STRATA_STEP, bin_quantiles, cells_from_rows
from core_modelling.tasks import TARGET_BINS, TASK_SPECS


def _binary_rows(slope: float = 1.0, intercept: float = 0.0, n: int = 40_000) -> pd.DataFrame:
    """Rows of one part over four periods: a score whose logit is normal around a 6% rate, and a
    target drawn at `expit(intercept + slope · logit(score))`, so (slope, intercept) is the
    calibration line's truth."""
    rng = np.random.default_rng(7)
    score = expit(rng.normal(-3.2, 1.1, n))
    y = (rng.random(n) < expit(intercept + slope * logit(score))).astype(float)
    return pd.DataFrame({"part": "test", "period": rng.integers(0, 4, n).astype(str),
                         "target": y, "score": score, "weight": 1})  # fmt: skip


def _binned(rows: pd.DataFrame, task: str, target_bin: np.ndarray | None = None) -> pd.DataFrame:
    """The rows with `score_bin`s cut at the task's `bin_quantiles` (dense at the top, as the
    Spark aggregate cuts them) and a `target_bin` (the target itself by default)."""
    edges = np.quantile(rows["score"], bin_quantiles(task))
    binned = np.searchsorted(edges, rows["score"], side="right")
    labels = rows["target"].astype(int) if target_bin is None else target_bin
    return rows.assign(score_bin=binned, target_bin=labels)


def _binary_cells(rows: pd.DataFrame, loss: str | None = "log_loss") -> pd.DataFrame:
    """One replicate's cells of binary rows at the task's score bins."""
    return cells_from_rows(_binned(rows, "binary"), [], loss)


def test_the_bins_narrow_towards_the_top_and_coarsen_to_the_strata_grid() -> None:
    """Binary's 380 bins: 100 of 0.9%, 90 of 0.1%, 90 of 0.01% and 100 of 0.001% of the rows,
    every fourth edge the strata's; regression's 50: 25 of 3.6% and 25 of 0.4%, all of them
    the strata's."""
    widths = np.diff([0.0, *bin_quantiles("binary"), 1.0])
    for width, bins in ((0.009, 100), (0.001, 90), (1e-4, 90), (1e-5, 100)):
        assert np.isclose(widths, width, rtol=1e-6, atol=0).sum() == bins
    assert widths.size == 380 and widths.size // STRATA_STEP["binary"] == 95
    widths = np.diff([0.0, *bin_quantiles("regression"), 1.0])
    assert widths.size == 50 and np.isclose(widths, 0.004, rtol=1e-6, atol=0).sum() == 25


def test_binary_metrics_match_scikit_learn_on_the_rows() -> None:
    """Exact: the log loss, the skill scores against the train rate and observed to expected.
    Binned at the 380 score bins, dense at the top: AUC within 1e-4 of the rows' and of
    Training's row concordance, the average precision within 0.002 (the rare rates:
    `test_the_average_precision_holds_at_a_rare_rate`)."""
    rows = _binary_rows()
    y, score, base = rows["target"], rows["score"], 0.055
    metrics = binary_metrics(_binary_cells(rows), base)
    constant = np.full(len(y), base)
    assert metrics["rows"] == len(y) and metrics["events"] == y.sum()
    assert metrics["log_loss"] == pytest.approx(log_loss(y, score), rel=1e-12)
    skill = 1 - log_loss(y, score) / log_loss(y, constant)
    assert metrics["log_loss_skill"] == pytest.approx(skill, rel=1e-9)
    brier = 1 - brier_score_loss(y, score) / brier_score_loss(y, constant)
    assert metrics["brier_skill"] == pytest.approx(brier, rel=1e-9)
    assert metrics["observed_to_expected"] == pytest.approx(y.sum() / score.sum(), rel=1e-12)
    assert metrics["roc_auc"] == pytest.approx(roc_auc_score(y, score), abs=1e-4)
    assert metrics["roc_auc"] == pytest.approx(row_concordance(y, score), abs=1e-4)
    assert metrics["ap"] == pytest.approx(average_precision_score(y, score), abs=0.002)


def test_the_average_precision_holds_at_a_rare_rate() -> None:
    """At a 0.1% rate on a million rows, a score whose logit is normal with a heavy right tail
    (3% of the rows pushed up, as a propensity model's top), the cells' average precision is
    within 0.002 of scikit-learn's on the rows and the calibration line within 0.002 of the row
    fit; the former 200 bins (none below 0.1% of the rows) read the AP 0.16 low (43%) here."""
    rng = np.random.default_rng(13)
    n = 1_000_000
    margin = rng.normal(0, 1.2, n) + 1.8 * (rng.random(n) < 0.03) * rng.exponential(1.0, n)
    score = expit(margin - 8.48)  # about a 0.1% rate
    y = (rng.random(n) < score).astype(float)
    rows = pd.DataFrame({"part": "test", "period": "p", "target": y, "score": score, "weight": 1})
    metrics = binary_metrics(_binary_cells(rows), 0.001)
    assert metrics["ap"] == pytest.approx(average_precision_score(y, score), abs=0.002)
    fit = LogisticRegression(**UNPENALISED).fit(logit(score)[:, None], y)
    assert metrics["calibration_slope"] == pytest.approx(fit.coef_[0, 0], abs=0.002)
    assert metrics["calibration_intercept"] == pytest.approx(fit.intercept_[0], abs=0.002)


@pytest.mark.parametrize(("slope", "intercept"), [(1.0, 0.0), (0.6, -0.5), (1.5, 0.8)])
def test_the_calibration_line_recovers_simulated_miscalibration(
    slope: float, intercept: float
) -> None:
    """The fit on cells is scikit-learn's on the rows' logits within 0.002 (a cell's logit is
    its mean), and lands on the simulated line within its sampling error."""
    rows = _binary_rows(slope, intercept)
    metrics = binary_metrics(_binary_cells(rows), 0.06)
    fit = LogisticRegression(**UNPENALISED).fit(logit(rows[["score"]]), rows["target"])
    assert metrics["calibration_slope"] == pytest.approx(fit.coef_[0, 0], abs=0.002)
    assert metrics["calibration_intercept"] == pytest.approx(fit.intercept_[0], abs=0.002)
    assert metrics["calibration_slope"] == pytest.approx(slope, abs=0.1)
    assert metrics["calibration_intercept"] == pytest.approx(intercept, abs=0.3)


def test_a_score_of_exactly_0_or_1_keeps_the_log_loss_finite() -> None:
    """A float64 sigmoid at an extreme margin returns exactly 0 or 1: the clip keeps the loss and
    the logit finite, and a wrong certain score costs `−ln 1e-15`."""
    rows = pd.DataFrame({"part": "test", "period": "p", "score_bin": [0, 0, 1, 1],
                         "target_bin": [0, 1, 0, 1], "target": [0.0, 1.0, 0.0, 1.0],
                         "score": [0.0, 0.0, 1.0, 1.0], "weight": 1})  # fmt: skip
    cells = cells_from_rows(rows, [], "log_loss")
    assert np.isfinite(cells[["loss_sum", "link_sum"]].to_numpy()).all()
    low, high = 1e-15, 1 - 1e-15  # the clipped 0 and 1
    expected = -(np.log1p(-low) + np.log(low) + np.log1p(-high) + np.log(high)) / 4
    assert binary_metrics(cells, 0.5)["log_loss"] == pytest.approx(expected, rel=1e-6)


def test_a_scorer_without_a_loss_is_declared_up_front() -> None:
    """A raw feature as the score, declared without loss sums (`loss=False`): AUC and AP exist,
    the probability metrics are NaN. Declared with them, the null sums fail loud; a regression
    scorer without a deviance alike."""
    rows = _binary_rows(n=5_000)
    cells = _binary_cells(rows.assign(score=rows["score"] * 1e4), None)
    metrics = binary_metrics(cells, 0.06, loss=False)
    assert np.isfinite([metrics["roc_auc"], metrics["ap"]]).all()
    for name in ("log_loss", "log_loss_skill", "brier_skill", "observed_to_expected",
                 "calibration_slope", "calibration_intercept"):  # fmt: skip
        assert np.isnan(metrics[name]), name
    with pytest.raises(ValueError, match="`loss_sum` is null"):
        binary_metrics(cells, 0.06)
    amounts = cells_from_rows(_regression_rows(), [], None)
    assert np.isnan(regression_metrics(amounts, 0.0, loss=False)["deviance"])
    with pytest.raises(ValueError, match="loss=False"):
        regression_metrics(amounts, 0.0)


def _regression_rows(n: int = 30_000) -> pd.DataFrame:
    """A zero-inflated amount (70% zeros) with a positive prediction that ranks it, with the
    target bins EDA's counts table cuts (`tasks.TARGET_BINS`, zero its own bin)."""
    rng = np.random.default_rng(3)
    signal = rng.normal(size=n)
    y = np.where(rng.random(n) < expit(signal - 1), rng.gamma(2, 50 * np.exp(signal / 2)), 0.0)
    rows = pd.DataFrame(
        {
            "part": "test",
            "period": "p",
            "target": y,
            "score": 40 * np.exp(0.7 * signal + rng.normal(0, 0.5, n)),
            "weight": 1,
        }
    )
    edges = TASK_SPECS["regression"]["target_bins"](y, exact=False)
    return _binned(rows, "regression", np.searchsorted(edges, y, side="right"))


@pytest.mark.parametrize(
    ("loss", "deviance"),
    [("tweedie_deviance", lambda y, s: mean_tweedie_deviance(y, s, power=1.5)),
     ("poisson_deviance", mean_poisson_deviance)],
)  # fmt: skip
def test_regression_metrics_match_scikit_learn_on_the_rows(
    loss: str, deviance: Callable[[pd.Series, pd.Series], float]
) -> None:
    """Exact: RMSE, MAE, R², the deviance (Tweedie at the constant 1.5) and predicted to
    observed. The concordance against 20 target bins within 0.003 of Training's row concordance
    (measured 0.0015; pairs inside a target bin count as ties)."""
    rows = _regression_rows()
    y, score = rows["target"], rows["score"]
    metrics = regression_metrics(cells_from_rows(rows, [], loss), base=float(y.mean()))
    assert TARGET_BINS == 20 and metrics["events"] == (y != 0).sum()
    assert metrics["rmse"] == pytest.approx(root_mean_squared_error(y, score), rel=1e-9)
    assert metrics["mae"] == pytest.approx(mean_absolute_error(y, score), rel=1e-9)
    assert metrics["r2"] == pytest.approx(r2_score(y, score), rel=1e-9)
    assert metrics["deviance"] == pytest.approx(deviance(y, score), rel=1e-9)
    assert metrics["predicted_to_observed"] == pytest.approx(score.sum() / y.sum(), rel=1e-12)
    assert metrics["concordance"] == pytest.approx(row_concordance(y, score), abs=0.003)


def test_slices_add_up_over_periods_and_a_top_n_above_the_population_is_not_available() -> None:
    """Cut inside each period, the periods' counts add up before the rates; a `top_n` above one
    period's population leaves the slice not available in the sum, never a partial count."""
    cells = _binary_cells(_binary_rows())
    slices = Slices(top_pct=[0.05], top_n=[2_000, 12_000])
    population = {"0": 11_000, "1": 20_000}
    per_period = [slice_metrics(cells.loc[cells["period"] == p], slices, population[p])
                  for p in population]  # fmt: skip
    added = slice_rates(pd.concat(per_period, ignore_index=True)).set_index("slice")
    first, second = (frame.set_index("slice") for frame in per_period)
    assert first.loc["top 12,000", "unavailable"].startswith("not available")
    assert added.loc["top 12,000", ["rows", "capture", "lift"]].isna().all()
    for name in ("top 5%", "top 2,000"):
        assert added.loc[name, "rows"] == pytest.approx(
            first.loc[name, "rows"] + second.loc[name, "rows"]
        )
        captured = (first.loc[name, "target"] + second.loc[name, "target"]) / added.loc[
            name, "part_target"
        ]
        assert added.loc[name, "capture"] == pytest.approx(captured)
    part_rows = first.loc["top 2,000", "part_rows"]
    assert first.loc["top 2,000", "rows"] == pytest.approx(
        2_000 / 11_000 * part_rows
    )  # n / population


def test_the_chart_tables_agree_with_the_metrics() -> None:
    """The threshold table's ROC has the cells' AUC as its area and ends at depth, capture and
    false positive rate 1; reliability groups hold every row; each class' shares sum to 1."""
    cells = _binary_cells(_binary_rows())
    curve = threshold_table(cells, roc=True)
    assert list(curve.columns) == ["score_bin", "threshold", "rows", "target", "depth", "capture",
                                   "rate", "lift", "false_positive_rate"]  # fmt: skip
    assert curve.iloc[-1][["depth", "capture", "false_positive_rate"]].tolist() == [1.0, 1.0, 1.0]
    x = np.concatenate([[0], curve["false_positive_rate"]])
    area = np.trapezoid(np.concatenate([[0], curve["capture"]]), x)
    assert area == pytest.approx(binary_metrics(cells, 0.06)["roc_auc"], abs=1e-9)
    assert threshold_table(cells, roc=False)["false_positive_rate"].isna().all()
    reliability = reliability_table(cells)
    assert list(reliability.columns) == ["group", "rows", "predicted", "observed"]
    assert len(reliability) == 10 and reliability["rows"].sum() == cells["rows"].sum()
    shown = distribution_table(cells, TASK_SPECS["binary"]["target_class"])
    columns = ["score_bin", "score", "percentile", "class", "rows", "share", "ratio"]
    assert list(shown.columns) == columns
    assert shown.groupby("class")["share"].sum().to_dict() == pytest.approx({"0": 1, "1": 1})


def test_a_class_independent_of_the_score_reads_chance_in_every_bin() -> None:
    """On bins dense at the top a class's share per bin drops ninefold at the 90th percentile
    (0.9% bins below, 0.1% above); its ratio to the bin's share of rows stays about 1, no step.
    Read on the bins of 100 rows or more: the top 1%'s bins hold one to ten rows here."""
    rows = _binary_rows(n=100_000)
    rows["target"] = (np.random.default_rng(2).random(len(rows)) < 0.5).astype(float)
    shown = distribution_table(_binary_cells(rows), TASK_SPECS["binary"]["target_class"])
    positive = shown.loc[shown["class"] == "1"]
    assert positive["percentile"].iloc[-1] == pytest.approx(1.0)
    positive = positive.loc[positive["percentile"] <= 0.99 + 1e-9]
    top = positive["percentile"] > 0.9 + 1e-9
    assert (positive["ratio"] - 1).abs().max() < 0.5
    assert positive.loc[top, "ratio"].mean() == pytest.approx(1, abs=0.05)
    assert positive.loc[~top, "ratio"].mean() == pytest.approx(1, abs=0.05)


def test_a_client_weight_counts_its_rows_that_many_times() -> None:
    """The mirror's weights: a row of weight 2 counts as two rows, one of weight 0 nowhere (no
    cell is left with only undrawn rows)."""
    rows = _binned(_binary_rows(n=2_000), "binary")
    weight = np.random.default_rng(1).integers(0, 3, len(rows))
    weighted = cells_from_rows(rows.assign(weight=weight), [], "log_loss")
    repeated = cells_from_rows(rows.loc[rows.index.repeat(weight)], [], "log_loss")
    pd.testing.assert_frame_equal(weighted, repeated, check_dtype=False)
    assert (weighted["rows"] > 0).all()
