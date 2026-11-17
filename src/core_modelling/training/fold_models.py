"""The fold models: K models of one configuration, each scoring the fold it never saw (D-094 (b)).

Every out-of-fold number of a run comes from here: the pruning's contribution shares and loss,
the calibration's margins, the out-of-fold metric and the sign-off view's contributions. The
folds are the dataset's client folds of the first dealing (`cv_fold`, D-106), so no client's
rows are on both sides of a fit (`CLAUDE.md` §4.4, §4.11). The models are fitted through
`FAMILIES` like every model the framework keeps, and are discarded: only the final model, fitted
on every train row, goes into the bundle (A11).
"""

import numpy as np
import pandas as pd

from core_modelling.model.families import FAMILIES

FOLD_COLUMN = "cv_fold"  # the first dealing: the one fold assignment behind out-of-fold numbers


def fit_fold_models(
    X: pd.DataFrame, y: np.ndarray, folds: pd.DataFrame, family: str, params: dict, task: str
) -> tuple[np.ndarray, np.ndarray]:
    """The out-of-fold margins and contributions of `family` at `params` (the fixed parameters
    with the configuration merged over them).

    Receives the encoded train frame `X` (one row per client and period, the columns in the
    encoder's order, checked by the caller with `check_order`), its target `y` and `folds`, the
    frame's fold columns on the same rows. Returns `(margins, contributions)`: one margin per
    row, and one row of contributions per row with a column per feature in `X`'s order and the
    base value last, each from the model fitted without that row's fold. A non-finite margin
    fails loud, as `score_frame` refuses one.
    """
    if not (len(X) == len(y) == len(folds)):
        raise ValueError(
            f"the frame, the target and the folds differ in rows: {len(X)}, {len(y)}, {len(folds)}"
        )
    unfolded = int(folds[FOLD_COLUMN].isna().sum())
    if unfolded:
        raise ValueError(
            f"{unfolded:,} of {len(folds):,} rows have a null {FOLD_COLUMN}: no fold model would "
            "score them; every train row needs its client's fold"
        )
    functions = FAMILIES[family]
    y, fold = np.asarray(y), folds[FOLD_COLUMN].to_numpy()
    margins = np.full(len(X), np.nan)
    parts = np.full((len(X), X.shape[1] + 1), np.nan)
    for k in np.unique(fold):
        held = fold == k
        booster = functions.fit(X[~held], y[~held], params, task)
        margins[held] = functions.predict(booster, X[held])
        parts[held] = functions.contributions(booster, X[held])
    bad = int((~np.isfinite(margins)).sum())
    if bad:
        raise ValueError(
            f"{family}: {bad:,} of {len(margins):,} out-of-fold margins are not finite; the "
            "fold models cannot be calibrated or judged"
        )
    return margins, parts
