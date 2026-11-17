"""The fold models on a small constructed frame (no Spark): each model is fitted without the
fold it scores, every row gets exactly one out-of-fold margin from the model that never saw
it, the contributions add up to that margin in every family, and a non-finite margin stops
the run (`CLAUDE.md` §4.4, §4.11; D-094 (b)).
"""

import dataclasses

import numpy as np
import pandas as pd
import pytest
from scipy.special import expit

from core_modelling.model.families import FAMILIES
from core_modelling.training.fold_models import FOLD_COLUMN, fit_fold_models

ROWS, FOLDS, ROWS_PER_CLIENT, TREES, SEED = 1200, 4, 3, 20, 7
FEATURES = ["x1", "x2", "x3"]
SEARCHED = {  # one small configuration per family, in FLAML's own parameter names
    "lgbm": {"n_estimators": TREES, "num_leaves": 8, "learning_rate": 0.1},
    "xgboost": {"n_estimators": TREES, "max_leaves": 8, "learning_rate": 0.1},
    "xgb_limitdepth": {"n_estimators": TREES, "max_depth": 4, "learning_rate": 0.1},
    "catboost": {"n_estimators": TREES, "learning_rate": 0.1},
}


def _frame() -> tuple[pd.DataFrame, np.ndarray, pd.DataFrame]:
    """Three numeric features, a binary target driven by two of them, and the client folds:
    `ROWS_PER_CLIENT` rows per client, each client's rows in one fold."""
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(ROWS, len(FEATURES))), columns=FEATURES)
    y = (rng.random(ROWS) < expit(X["x1"] - 0.5 * X["x2"] - 1.0)).to_numpy(np.int64)
    clients = np.arange(ROWS) // ROWS_PER_CLIENT
    return X, y, pd.DataFrame({FOLD_COLUMN: clients % FOLDS})


def _params(family: str) -> dict:
    """The family's fixed binary parameters for the numeric frame, with its small configuration
    merged over them."""
    encoder = {
        "schema_version": 1,
        "unordered": "native",
        "min_level_client_count": 50,
        "features": [{"name": name, "kind": "numeric"} for name in FEATURES],
    }
    fixed = FAMILIES[family].fixed_params("binary", "log_loss", encoder, {}, SEED, 1, None)
    return {**fixed, **SEARCHED[family]}


def test_no_fold_model_sees_its_fold_and_each_row_gets_one_margin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fold model fitted on a row it scores would make every out-of-fold number in-sample:
    each fit must receive exactly the other folds' rows with their own targets, and each row's
    margin must be the prediction of the one model that did not see it."""
    X, y, folds = _frame()
    lgbm = FAMILIES["lgbm"]
    fitted, scored = [], []

    def recording_fit(X_fit: pd.DataFrame, y_fit: np.ndarray, params: dict, task: str) -> object:
        """LightGBM's fit, recording the rows and the targets it received."""
        fitted.append((X_fit.index.to_numpy(), np.asarray(y_fit)))
        return lgbm.fit(X_fit, y_fit, params, task)

    def recording_predict(booster: object, X_held: pd.DataFrame) -> np.ndarray:
        """LightGBM's predict, recording the rows it scored and the margins it gave."""
        margin = lgbm.predict(booster, X_held)
        scored.append((X_held.index.to_numpy(), margin.copy()))
        return margin

    replaced = dataclasses.replace(lgbm, fit=recording_fit, predict=recording_predict)
    monkeypatch.setitem(FAMILIES, "lgbm", replaced)
    margins, _ = fit_fold_models(X, y, folds, "lgbm", _params("lgbm"), "binary")
    assert len(fitted) == len(scored) == FOLDS
    for (seen, seen_y), (held, held_margin) in zip(fitted, scored, strict=True):
        assert set(seen).isdisjoint(held)
        assert set(seen) | set(held) == set(range(ROWS))
        assert folds.loc[held, FOLD_COLUMN].nunique() == 1
        assert np.array_equal(seen_y, y[seen])
        assert np.array_equal(margins[held], held_margin)
    assert sorted(np.concatenate([held for held, _ in scored])) == list(range(ROWS))


@pytest.mark.parametrize("family", FAMILIES)
def test_the_contributions_sum_to_the_out_of_fold_margin(family: str) -> None:
    """The sign-off view reads the fold models' contributions beside their margins: one column
    per feature and the base value last, each row adding up to its margin (float32 rounding for
    XGBoost)."""
    X, y, folds = _frame()
    margins, contributions = fit_fold_models(X, y, folds, family, _params(family), "binary")
    assert contributions.shape == (ROWS, len(FEATURES) + 1)
    np.testing.assert_allclose(contributions.sum(axis=1), margins, rtol=1e-5, atol=1e-5)


def test_a_non_finite_margin_fails_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    """A NaN or infinite margin would give a NaN calibration and NaN scores: the run stops,
    counting the margins."""
    X, y, folds = _frame()
    lgbm = FAMILIES["lgbm"]

    def broken_predict(booster: object, X_held: pd.DataFrame) -> np.ndarray:
        """LightGBM's predict with one NaN and one infinite margin in each fold."""
        margin = lgbm.predict(booster, X_held)
        margin[:2] = [np.nan, np.inf]
        return margin

    monkeypatch.setitem(FAMILIES, "lgbm", dataclasses.replace(lgbm, predict=broken_predict))
    with pytest.raises(ValueError, match=r"^lgbm: 8 of 1,200 out-of-fold margins are not finite"):
        fit_fold_models(X, y, folds, "lgbm", _params("lgbm"), "binary")


def test_a_row_without_a_fold_fails_loud() -> None:
    """A null fold would keep its row out of every held-out fold, so no model would score it:
    the run stops, naming the column, before any fit."""
    X, y, folds = _frame()
    folds = folds.astype("float64")
    folds.loc[5, FOLD_COLUMN] = np.nan
    with pytest.raises(ValueError, match=f"1 of 1,200 rows have a null {FOLD_COLUMN}"):
        fit_fold_models(X, y, folds, "lgbm", _params("lgbm"), "binary")
