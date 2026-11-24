"""The framework's own fits of one configuration: the K fold models, each scoring the fold it
never saw (D-094 (b)), and the final model on every train row.

Every out-of-fold number of a run comes from here: the pruning's contribution shares and loss,
the calibration's margins, the out-of-fold metric and the sign-off view's contributions. The
folds are the dataset's client folds of the first dealing (`cv_fold`, D-106), so no client's
rows are on both sides of a fit (`CLAUDE.md` §4.4, §4.11). `every_dealing_loss` fits the
further dealings too, so the judged-model check compares the loss FLAML averaged over every
dealing with the framework's own. The models are fitted through `FAMILIES` like every model the
framework keeps; the fold models are discarded, and only the final model goes into the bundle.
`out_of_fold_loss` is the one place the margins become the loss the search and the pruning
compare.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.model.calibration import apply_calibration, uncalibrated
from core_modelling.model.families import FAMILIES
from core_modelling.statistics.losses import mean_fold_loss

FOLD_COLUMN = "cv_fold"  # the first dealing: the one fold assignment behind out-of-fold numbers


@dataclass
class FinalModel:
    """The model the bundle holds: the booster, its `describe` and its margins on the train
    rows it was fitted on, in their order (the in-sample predict)."""

    booster: object
    description: dict
    margins: np.ndarray


def fit_fold_models(
    X: pd.DataFrame,
    y: np.ndarray,
    folds: pd.DataFrame,
    family: str,
    params: dict,
    task: str,
    threads: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """The out-of-fold margins and contributions of `family` at `params` (the fixed parameters
    with the configuration merged over them) on the first dealing's folds.

    Receives the encoded train frame `X` (one row per client and period, the columns in the
    encoder's order, checked by the caller with `check_order`), its target `y` and `folds`, the
    frame's fold columns on the same rows. Returns `(margins, contributions)`: one margin per
    row, and one row of contributions per row with a column per feature in `X`'s order and the
    base value last, each from the model fitted without that row's fold, predicted on `threads`.
    A non-finite margin fails loud, as `score_frame` refuses one.
    """
    if not (len(X) == len(y) == len(folds)):
        raise ValueError(
            f"the frame, the target and the folds differ in rows: {len(X)}, {len(y)}, {len(folds)}"
        )
    return _fit_folds(X, np.asarray(y), folds[FOLD_COLUMN], family, params, task, threads, True)


def every_dealing_loss(
    X: pd.DataFrame,
    y: np.ndarray,
    folds: pd.DataFrame,
    margins: np.ndarray,
    family: str,
    params: dict,
    cfg: UseCaseConfig,
    threads: int | None = None,
) -> float:
    """The decision's metric as a loss on the uncalibrated score, the mean over every dealing's
    folds, as FLAML averages a trial. `margins` are the first dealing's out-of-fold margins
    (`fit_fold_models`); each further dealing's K fold models are fitted here, for their
    margins only. `X`, `y`, `folds` and `margins` hold the same rows in the same order."""
    y, losses = np.asarray(y), []
    calibration = uncalibrated(cfg.training.objective)  # the score the search judged
    for column in folds.columns:
        dealing = margins
        if column != FOLD_COLUMN:
            dealing, _ = _fit_folds(X, y, folds[column], family, params, cfg.task, threads, False)
        fold = folds[column].to_numpy()
        losses.append(
            out_of_fold_loss(cfg.decision.metric, y, dealing, fold, calibration, cfg.task)
        )
    return float(np.mean(losses))


def fit_final_model(
    X: pd.DataFrame, y: np.ndarray, family: str, params: dict, task: str, threads: int | None
) -> FinalModel:
    """The family's own `fit` on every train row as trained (`X` checked by the caller with
    `check_order`), at `params`, with its margins on those rows predicted on `threads`. A
    booster whose feature names are not `X`'s columns fails loud (D-094 (a))."""
    booster = FAMILIES[family].fit(X, y, params, task)
    description = FAMILIES[family].describe(booster)
    names = list(description["features"])
    if names != list(X.columns):
        raise ValueError(
            f"the fitted {family} model names its features {names}, the final list is "
            f"{list(X.columns)}: the model would score another frame than the bundle records"
        )
    return FinalModel(booster, description, FAMILIES[family].predict(booster, X, threads))


def _fit_folds(
    X: pd.DataFrame,
    y: np.ndarray,
    fold: pd.Series,
    family: str,
    params: dict,
    task: str,
    threads: int | None,
    explain: bool,
) -> tuple[np.ndarray, np.ndarray | None]:
    """One dealing's fold models (`fold`, the dealing's column): the out-of-fold margins and,
    when `explain`, the contributions (else None). A row without a fold, or a non-finite
    margin, fails loud."""
    unfolded = int(fold.isna().sum())
    if unfolded:
        raise ValueError(
            f"{unfolded:,} of {len(fold):,} rows have a null {fold.name}: no fold model would "
            "score them; every train row needs its client's fold"
        )
    functions, fold = FAMILIES[family], fold.to_numpy()
    margins = np.full(len(X), np.nan)
    parts = np.full((len(X), X.shape[1] + 1), np.nan) if explain else None
    for k in np.unique(fold):
        held = fold == k
        booster = functions.fit(X[~held], y[~held], params, task)
        margins[held] = functions.predict(booster, X[held], threads)
        if explain:
            parts[held] = functions.contributions(booster, X[held], threads)
    bad = int((~np.isfinite(margins)).sum())
    if bad:
        raise ValueError(
            f"{family}: {bad:,} of {len(margins):,} out-of-fold margins are not finite; the "
            "fold models cannot be calibrated or judged"
        )
    return margins, parts


def out_of_fold_loss(
    metric: str,
    y: np.ndarray,
    margins: np.ndarray,
    fold: np.ndarray,
    calibration: dict,
    task: str,
) -> float:
    """The decision's `metric` as a loss on the `score` that `calibration` gives the out-of-fold
    `margins`, the mean over the folds (`mean_fold_loss`); `uncalibrated(objective)` gives the
    score the search judged a trial on. `y`, `margins` and `fold` are aligned, one per row."""
    _, score = apply_calibration(margins, calibration, task)
    return mean_fold_loss(metric, y, score, fold)
