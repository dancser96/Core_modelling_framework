"""CatBoost as a model family (`catboost`): the functions `FAMILIES["catboost"]` holds
(`families.py`).

`fit` mirrors FLAML 2.7's `CatBoostEstimator` (`flaml/automl/model.py`) under the settled tree
rule (Q607): the tree count is a searched parameter, `use_best_model` is off and no rows are
held out, so the scikit-learn estimator trains exactly the given count on every row; FLAML's
`n_jobs` becomes `thread_count`, logging is silent and no file is written (T5). The model it
returns, like the one `load` reads, is CatBoost's own; `predict` gives its raw formula value.

CatBoost reads columns by position, never by name, and refuses float codes or nulls in a
declared categorical, so scoring reorders the frame to the booster's feature names and passes
those columns as int64. Its `.cbm` bytes differ on every fit through run-specific metadata,
deleted before saving (`RUN_METADATA_KEYS`), after which one model has one file hash across
runs and thread counts (Q619).
"""

import inspect

import numpy as np
import pandas as pd
from catboost import CatBoost, CatBoostClassifier, CatBoostRegressor, Pool

from core_modelling.model.encoder import check_encoder
from core_modelling.model.family_inputs import (
    allowed_params,
    check_known_params,
    check_vector_lengths,
    declared_categoricals,
    monotone_directions,
    objective_params,
    order_frame,
    tweedie_power,
)

FAMILY = "catboost"
FILE_NAME = "model.cbm"
MODEL_CLASSES = {"binary": CatBoostClassifier, "regression": CatBoostRegressor}
OBJECTIVES = {  # Q639's names in CatBoost's words; Tweedie's power is added in `fixed_params`
    "binary": {"log_loss": {"loss_function": "Logloss"}},
    "regression": {
        "squared_error": {"loss_function": "RMSE"},
        "tweedie": {"loss_function": "Tweedie"},
        "poisson": {"loss_function": "Poisson"},
        "absolute_error": {"loss_function": "MAE"},
        "huber": {"loss_function": "Huber:delta=1.0"},
    },
}
# Deleted before saving (Q619). Measured on two fits of one model: the id differs on every fit,
# the finish time with the clock, `params` with the thread count, `output_options` with the
# training folder (FLAML names it after the clock); `training`, the learn-metric history, is a
# log of the fit, not part of the model. Scoring needs none of them.
RUN_METADATA_KEYS = ("model_guid", "train_finish_time", "params", "output_options", "training")
EXTRA_PARAMS = (  # what is passed beside the estimators' own parameters, and by whom
    "n_jobs",  # fixed_params and FLAML: the thread count, which `fit` turns into `thread_count`
)
# CatBoost's `get_params()` lists only the parameters set, so the constructors' signatures name
# them all (the classifier's and the regressor's differ in the class settings)
ALLOWED_PARAMS = allowed_params(
    {name for model in MODEL_CLASSES.values() for name in inspect.signature(model).parameters},
    EXTRA_PARAMS,
)
# Every name `fixed_params` can return, with what sets it: the search may not set them
# (`families.check_searched`), or the bundle would describe another model
OWNED_PARAMS = {
    "loss_function": "training.objective and training.tweedie_variance_power",
    "random_seed": "training.seed",
    "n_jobs": "the run's thread count",
    "allow_writing_files": "the framework (A7: CatBoost writes no file)",
    "use_best_model": "the framework (Q607: the tree count is searched)",
    "monotone_constraints": "training.monotone",
    "cat_features": "the encoder's declared categoricals",
}


def fixed_params(
    task: str,
    objective: str,
    encoder: dict,
    monotone: dict[str, str],
    seed: int,
    threads: int,
    tweedie_variance_power: float | None,
) -> dict:
    """The constants every CatBoost fit of a run shares, trials and final fit alike (A55): the
    loss (with the variance power under Tweedie; Huber's delta is fixed at 1.0), the seed, the
    threads, no files written (A7), no best-model shrinking (Q607), the declared categoricals,
    and the monotone constraints as a bracketed string (a tuple is refused)."""
    check_encoder(encoder)
    params = {
        **objective_params(FAMILY, task, objective, OBJECTIVES),
        "random_seed": seed,
        "n_jobs": threads,
        "allow_writing_files": False,
        "use_best_model": False,
    }
    if params["loss_function"] == "Tweedie":
        power = tweedie_power(FAMILY, tweedie_variance_power)
        params["loss_function"] = f"Tweedie:variance_power={power}"
    directions = monotone_directions(FAMILY, encoder, monotone)
    if monotone:
        params["monotone_constraints"] = f"({','.join(str(d) for d in directions)})"
    categoricals = declared_categoricals(encoder)
    if categoricals:
        params["cat_features"] = categoricals
    return params


def fit(X: pd.DataFrame, y: np.ndarray, params: dict, task: str) -> CatBoost:
    """The model fitted on the frame `encode_frame` returned, which the caller checks once with
    `check_order` before the search and before the framework's own fits (`fit` has no encoder
    to check against), with every parameter in `params` (the searched ones merged over
    `fixed_params`), checked by name and translated as FLAML translates them."""
    check_known_params(FAMILY, params, ALLOWED_PARAMS)
    check_vector_lengths(FAMILY, params, X)
    library = dict(params)
    if "n_jobs" in library:
        library["thread_count"] = library.pop("n_jobs")
    library.setdefault("verbose", False)
    return MODEL_CLASSES[task](**library).fit(X, y)


def predict(booster: CatBoost, X: pd.DataFrame) -> np.ndarray:
    """The margin from every tree, CatBoost's raw formula value: log-odds for binary, the raw
    output for regression (the log scale under Tweedie and Poisson, A42)."""
    return booster.predict(_frame(booster, X), prediction_type="RawFormulaVal")


def contributions(booster: CatBoost, X: pd.DataFrame) -> np.ndarray:
    """CatBoost's own per-feature contributions to the margin (SHAP's tree values), one column
    per feature in the booster's order and the base value last; a row sums to its margin."""
    pool = Pool(_frame(booster, X), cat_features=booster.get_cat_feature_indices())
    return booster.get_feature_importance(pool, type="ShapValues")


def describe(booster: CatBoost) -> dict:
    """What the model file records, the same for a fitted and a reloaded model: the tree count,
    the features in order and CatBoost's own importance per feature (the prediction values
    change, its counterpart of gain). It keeps no split counts and, once saved, no parameters."""
    names = booster.feature_names_
    gain = booster.get_feature_importance(type="PredictionValuesChange")
    return {
        "trees": booster.tree_count_,
        "features": names,
        "gain": dict(zip(names, gain.tolist(), strict=True)),
        "gain_type": "PredictionValuesChange",
        # a split on a categorical is a split on a combination of features, so no per-feature
        # count exists; the parameters are deleted before saving and live in the recipe
        "splits": None,
        "parameters": {},
    }


def save(booster: CatBoost, path: str) -> None:
    """The model as CatBoost's `.cbm` file without its run-specific metadata, so that one model
    has one file hash; `booster` itself keeps its metadata."""
    model = booster.copy()
    metadata = model.get_metadata()
    for key in RUN_METADATA_KEYS:
        if key in metadata.keys():  # a reloaded model lacks most of them already
            del metadata[key]
    model.save_model(path, format="cbm")


def load(data: bytes) -> CatBoost:
    """The model read back from its `.cbm` file's bytes, as `save` wrote them (the bytes the
    bundle verified are the bytes that score, and no executor writes a file)."""
    return CatBoost().load_model(blob=data)


def _frame(booster: CatBoost, X: pd.DataFrame) -> pd.DataFrame:
    """`X` in the booster's column order: the declared categoricals as int64 codes, the rest
    as float64."""
    names = booster.feature_names_
    frame = order_frame(FAMILY, X, names)
    categorical = [names[index] for index in booster.get_cat_feature_indices()]
    for name in categorical:
        _check_codes(name, frame[name])
    return frame.astype({name: "int64" if name in categorical else "float64" for name in names})


def _check_codes(name: str, column: pd.Series) -> None:
    """Fail unless a declared categorical holds whole-number codes without nulls, which is all
    CatBoost takes there (a code that arrives as a float is cast, its value kept)."""
    if column.isna().any() or (column % 1 != 0).any():
        raise ValueError(
            f"{FAMILY}: the declared categorical {name!r} must hold whole-number codes, no nulls"
        )
