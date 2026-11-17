"""Training's row tables and train-side metrics (training.md → "What Training writes").

`oof_table` is the `oof` table: every train row's out-of-fold margin and scores, which the
calibration was fitted on and which Evaluation reads beside test. `explanation_sample` is a
seeded sample of train rows with their raw feature values and out-of-fold contributions, which
the explanation charts draw from. `train_metrics` are the run's numbers on train: the decision's
metric out of fold and the concordance out of fold and in sample. All of it is train-only
evidence (D-031) and optimistic: the features and the configuration were chosen on these folds.
"""

import numpy as np
import pandas as pd

from core_modelling.model.bundle import OUTPUT_COLUMNS
from core_modelling.model.calibration import apply_calibration
from core_modelling.sources import KEYS
from core_modelling.statistics.losses import mean_fold_loss, metric_value, row_concordance
from core_modelling.training.fold_models import FOLD_COLUMN

EXPLANATION_ROWS = 5000  # the explanation sample: this many seeded train rows, or every row
CONTRIBUTION_SUFFIX = "__contribution"  # a feature's contribution column in the sample
BASE_COLUMN = (
    "base_value"  # the contributions' base value: a row's contributions and it sum to its margin
)


# Stored with the train-side numbers, so nobody reads them as a test result
OPTIMISM_NOTE = (
    "Train-side numbers on the first dealing's folds, optimistic: selection, the search and "
    "the calibration were chosen or fitted on these rows. The test split's are Evaluation's."
)


def oof_table(
    train: pd.DataFrame, margins: np.ndarray, calibration: dict, task: str
) -> pd.DataFrame:
    """One row per train row as trained: the keys, `cv_fold`, `target` and the out-of-fold
    `margin`, `score_raw` and `score` under the bundle's `calibration`. `margins` is aligned
    with `train`. A non-finite score fails loud, as `score_frame` refuses one."""
    score_raw, score = apply_calibration(margins, calibration, task)
    table = train[[*KEYS, FOLD_COLUMN, "target"]].assign(
        margin=margins, score_raw=score_raw, score=score
    )
    for name in OUTPUT_COLUMNS:
        count = int((~np.isfinite(table[name])).sum())
        if count:
            raise ValueError(
                f"{count} of {len(table):,} out-of-fold rows have a non-finite {name}; a score is "
                "always a finite number"
            )
    return table


def explanation_sample(train: pd.DataFrame, contributions: pd.DataFrame, seed: int) -> pd.DataFrame:
    """`EXPLANATION_ROWS` seeded train rows (every row when train has fewer), in row order: the
    keys, the final features' raw values, each feature's out-of-fold contribution
    (`<feature>__contribution`) and `base_value`. `contributions` holds one row per train row,
    aligned with `train`: a column per final feature, then `base_value`."""
    rows = len(train)
    chosen = np.arange(rows)
    if rows > EXPLANATION_ROWS:
        chosen = np.sort(np.random.default_rng(seed).choice(rows, EXPLANATION_ROWS, replace=False))
    features = [name for name in contributions.columns if name != BASE_COLUMN]
    sampled = contributions.iloc[chosen]
    parts = [
        train.iloc[chosen][[*KEYS, *features]],
        sampled[features].add_suffix(CONTRIBUTION_SUFFIX),
        sampled[[BASE_COLUMN]],
    ]
    return pd.concat(parts, axis=1).reset_index(drop=True)


def sample_contributions(sample: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """The explanation sample's contributions under the features' own names, one column per
    feature: the shape the explanation charts take beside `sample[features]`, the raw values."""
    columns = [f"{name}{CONTRIBUTION_SUFFIX}" for name in features]
    return sample[columns].set_axis(features, axis=1)


def train_metrics(
    metric: str,
    task: str,
    y: np.ndarray,
    fold: np.ndarray,
    margins: np.ndarray,
    calibration: dict,
    in_sample: np.ndarray,
) -> dict:
    """The run's train-side numbers, from aligned arrays (one entry per train row: the target,
    its fold of the first dealing, its out-of-fold margin, and `in_sample`, the final model's
    margin on the row it was fitted on).

    `out_of_fold` is the decision's `metric` on the calibrated score, the mean over the folds,
    taken without the offset: the rows are at the sampled rate, the offset moves a score to the
    true one. The concordance (the AUC for a binary target) is given out of fold, the mean over
    the folds, and in sample, for the train–test gap Evaluation shows (D-106).
    """
    _, score = apply_calibration(margins, {**calibration, "offset": 0.0}, task)
    concordance = mean_fold_loss("concordance", y, margins, fold)
    return {
        "metric": metric,
        "out_of_fold": metric_value(metric, mean_fold_loss(metric, y, score, fold)),
        "out_of_fold_concordance": metric_value("concordance", concordance),
        "in_sample_concordance": row_concordance(y, in_sample),
        "note": OPTIMISM_NOTE,
    }
