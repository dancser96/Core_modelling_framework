"""The fold models on a small constructed frame (no Spark): each model is fitted without the
fold it scores, every row gets exactly one out-of-fold margin from the model that never saw
it, the contributions add up to that margin in every family, a non-finite margin stops
the run (`CLAUDE.md` §4.4, §4.11; D-094 (b)), the loss over every dealing is each dealing's own
fold loss averaged, and the final model gives its in-sample margins. Each holds for a binary
target and for a zero-heavy amount, under regression's default objective and under Tweedie.
"""

import dataclasses
from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest
from conftest import REGRESSION
from scipy.special import expit

from core_modelling.config import UseCaseConfig
from core_modelling.model.calibration import uncalibrated
from core_modelling.model.families import FAMILIES
from core_modelling.training.fold_models import (
    FOLD_COLUMN,
    every_dealing_loss,
    fit_final_model,
    fit_fold_models,
    out_of_fold_loss,
)

ROWS, FOLDS, ROWS_PER_CLIENT, TREES, SEED = 1200, 4, 3, 20, 7
FEATURES = ["x1", "x2", "x3"]
TASK_OF = {"log_loss": "binary", "squared_error": "regression", "tweedie": "regression"}
OBJECTIVES = list(TASK_OF)  # binary's, regression's default and one deviance objective
TWEEDIE_POWER = 1.5
SEARCHED = {  # one small configuration per family, in FLAML's own parameter names
    "lgbm": {"n_estimators": TREES, "num_leaves": 8, "learning_rate": 0.1},
    "xgboost": {"n_estimators": TREES, "max_leaves": 8, "learning_rate": 0.1},
    "xgb_limitdepth": {"n_estimators": TREES, "max_depth": 4, "learning_rate": 0.1},
    "catboost": {"n_estimators": TREES, "learning_rate": 0.1},
}


def _frame(task: str = "binary") -> tuple[pd.DataFrame, np.ndarray, pd.DataFrame]:
    """Three numeric features, a target driven by two of them, and the client folds:
    `ROWS_PER_CLIENT` rows per client, each client's rows in one fold. The binary target is
    0/1; the regression target an amount, zero on about seven rows in ten, else lognormal with
    a level that rises with the same signal."""
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(ROWS, len(FEATURES))), columns=FEATURES)
    signal = (X["x1"] - 0.5 * X["x2"]).to_numpy()
    y = (rng.random(ROWS) < expit(signal - 1.0)).astype(np.int64)
    if task == "regression":
        y = y * np.exp(1.0 + 0.4 * signal + rng.normal(scale=0.3, size=ROWS))
    clients = np.arange(ROWS) // ROWS_PER_CLIENT
    return X, y, pd.DataFrame({FOLD_COLUMN: clients % FOLDS})


def _params(family: str, objective: str = "log_loss") -> dict:
    """The family's fixed parameters at `objective` for the numeric frame, with its small
    configuration merged over them."""
    encoder = {
        "schema_version": 1,
        "unordered": "native",
        "min_level_client_count": 50,
        "features": [{"name": name, "kind": "numeric"} for name in FEATURES],
    }
    task, power = TASK_OF[objective], TWEEDIE_POWER if objective == "tweedie" else None
    fixed = FAMILIES[family].fixed_params(task, objective, encoder, {}, SEED, 1, power)
    return {**fixed, **SEARCHED[family]}


@pytest.mark.parametrize("objective", OBJECTIVES)
def test_no_fold_model_sees_its_fold_and_each_row_gets_one_margin(
    objective: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fold model fitted on a row it scores would make every out-of-fold number in-sample:
    each fit must receive exactly the other folds' rows with their own targets, and each row's
    margin must be the prediction of the one model that did not see it."""
    task = TASK_OF[objective]
    X, y, folds = _frame(task)
    lgbm = FAMILIES["lgbm"]
    fitted, scored = [], []

    def recording_fit(X_fit: pd.DataFrame, y_fit: np.ndarray, params: dict, task: str) -> object:
        """LightGBM's fit, recording the rows and the targets it received."""
        fitted.append((X_fit.index.to_numpy(), np.asarray(y_fit)))
        return lgbm.fit(X_fit, y_fit, params, task)

    def recording_predict(
        booster: object, X_held: pd.DataFrame, threads: int | None = None
    ) -> np.ndarray:
        """LightGBM's predict, recording the rows it scored and the margins it gave."""
        margin = lgbm.predict(booster, X_held, threads)
        scored.append((X_held.index.to_numpy(), margin.copy()))
        return margin

    replaced = dataclasses.replace(lgbm, fit=recording_fit, predict=recording_predict)
    monkeypatch.setitem(FAMILIES, "lgbm", replaced)
    margins, _ = fit_fold_models(X, y, folds, "lgbm", _params("lgbm", objective), task)
    assert len(fitted) == len(scored) == FOLDS
    for (seen, seen_y), (held, held_margin) in zip(fitted, scored, strict=True):
        assert set(seen).isdisjoint(held)
        assert set(seen) | set(held) == set(range(ROWS))
        assert folds.loc[held, FOLD_COLUMN].nunique() == 1
        assert np.array_equal(seen_y, y[seen])
        assert np.array_equal(margins[held], held_margin)
    assert sorted(np.concatenate([held for held, _ in scored])) == list(range(ROWS))


@pytest.mark.parametrize("objective", OBJECTIVES)
@pytest.mark.parametrize("family", FAMILIES)
def test_the_contributions_sum_to_the_out_of_fold_margin(family: str, objective: str) -> None:
    """The sign-off view reads the fold models' contributions beside their margins: one column
    per feature and the base value last, each row adding up to its margin (float32 rounding for
    XGBoost), on the log scale under Tweedie."""
    task = TASK_OF[objective]
    X, y, folds = _frame(task)
    margins, contributions = fit_fold_models(X, y, folds, family, _params(family, objective), task)
    assert contributions.shape == (ROWS, len(FEATURES) + 1)
    np.testing.assert_allclose(contributions.sum(axis=1), margins, rtol=1e-5, atol=1e-5)


def test_a_non_finite_margin_fails_loud() -> None:
    """A NaN or infinite margin would give a NaN calibration and NaN scores: the run stops,
    counting the margins. Real data produces them: amounts at both ends of float32's range
    overflow XGBoost's float32 arithmetic, while the library accepts the labels and fits
    without a word."""
    X, _, folds = _frame()
    edge = float(np.finfo(np.float32).max)
    y = np.where(np.arange(ROWS) % 2 == 0, edge, -edge)
    params = _params("xgboost", "squared_error")
    with (
        np.errstate(over="ignore", invalid="ignore"),
        pytest.raises(ValueError, match=r"^xgboost: 1,200 of 1,200 out-of-fold margins are not"),
    ):
        fit_fold_models(X, y, folds, "xgboost", params, "regression")


def test_a_row_without_a_fold_fails_loud() -> None:
    """A null fold would keep its row out of every held-out fold, so no model would score it:
    the run stops, naming the column, before any fit."""
    X, y, folds = _frame()
    folds = folds.astype("float64")
    folds.loc[5, FOLD_COLUMN] = np.nan
    with pytest.raises(ValueError, match=f"1 of 1,200 rows have a null {FOLD_COLUMN}"):
        fit_fold_models(X, y, folds, "lgbm", _params("lgbm"), "binary")


@pytest.mark.parametrize("objective", OBJECTIVES)
def test_the_loss_over_every_dealing_is_the_mean_of_each_dealings_own(
    objective: str, variant: Callable[..., UseCaseConfig]
) -> None:
    """FLAML averages a trial over every dealing's folds, so the framework's check must too:
    the first dealing's margins are reused and each further dealing is fitted on its own folds,
    and the result is the mean of the dealings' fold losses (the log loss, the RMSE, or the
    Tweedie deviance under Tweedie)."""
    task = TASK_OF[objective]
    X, y, folds = _frame(task)
    clients = np.arange(ROWS) // ROWS_PER_CLIENT
    dealt = np.random.default_rng(1).permutation(clients.max() + 1) % FOLDS  # a second dealing
    folds["cv_fold_2"] = dealt[clients]
    training = {"fold_repeats": 2, "folds": FOLDS, "objective": objective}
    if task == "binary":
        cfg = variant(training=training)
    else:
        metric = "tweedie_deviance" if objective == "tweedie" else "rmse"
        training["tweedie_variance_power"] = TWEEDIE_POWER if objective == "tweedie" else None
        cfg = variant(**REGRESSION, decision={"metric": metric}, training=training)
    params, calibration = _params("lgbm", objective), uncalibrated(cfg.training.objective)
    first, _ = fit_fold_models(X, y, folds, "lgbm", params, task)
    second, _ = fit_fold_models(
        X, y, folds[["cv_fold_2"]].set_axis([FOLD_COLUMN], axis=1), "lgbm", params, task
    )
    losses = [
        out_of_fold_loss(
            cfg.decision.metric, y, margins, folds[column].to_numpy(), calibration, task
        )
        for margins, column in ((first, FOLD_COLUMN), (second, "cv_fold_2"))
    ]
    assert losses[0] != losses[1]
    loss = every_dealing_loss(X, y, folds, first, "lgbm", params, cfg)
    assert loss == pytest.approx(np.mean(losses), rel=1e-12)
    one = every_dealing_loss(X, y, folds[[FOLD_COLUMN]], first, "lgbm", params, cfg)
    assert one == pytest.approx(losses[0], rel=1e-12)


@pytest.mark.parametrize("objective", OBJECTIVES)
def test_the_final_model_gives_its_in_sample_margins(objective: str) -> None:
    """The final model's margins are its own predictions on every train row it was fitted on,
    in their order, and its description names the frame's features."""
    task = TASK_OF[objective]
    X, y, _ = _frame(task)
    final = fit_final_model(X, y, "lgbm", _params("lgbm", objective), task, 1)
    assert final.description["features"] == FEATURES
    np.testing.assert_array_equal(final.margins, FAMILIES["lgbm"].predict(final.booster, X))
