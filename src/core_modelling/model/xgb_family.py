"""XGBoost as a model family: the functions both `FAMILIES["xgboost"]` (leaf-wise growth) and
`FAMILIES["xgb_limitdepth"]` (depth-wise) hold (`families.py`); they grow one kind of booster.

`fit` mirrors FLAML 2.7's `XGBoostSklearnEstimator` (`flaml/automl/model.py`), so that a fit
from FLAML's best configuration is FLAML's own model: the scikit-learn estimator; `max_depth` 0
when the configuration has none (FLAML's `xgboost` space), which means leaf-wise growth on the
histogram method; silent logging. It returns XGBoost's own `Booster`, whose JSON file keeps the
feature names and types and the categorical splits.

Scoring builds the matrix from the frame in the booster's column order with the booster's own
feature types, and uses every tree by an explicit range. XGBoost's margins are float32 and are
returned as float64. Its JSON file repeats byte for byte across runs and thread counts.
"""

import json

import numpy as np
import pandas as pd
import xgboost as xgb

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

FAMILY = "xgboost / xgb_limitdepth"  # one module serves both entries, so messages name both
FILE_NAME = "model.json"
MODEL_CLASSES = {"binary": xgb.XGBClassifier, "regression": xgb.XGBRegressor}
OBJECTIVES = {  # Q639's names in XGBoost's words
    "binary": {"log_loss": {"objective": "binary:logistic"}},
    "regression": {
        "squared_error": {"objective": "reg:squarederror"},
        "tweedie": {"objective": "reg:tweedie"},
        "poisson": {"objective": "count:poisson"},
        "absolute_error": {"objective": "reg:absoluteerror"},
        "huber": {"objective": "reg:pseudohubererror", "huber_slope": 1.0},  # its only Huber
    },
}
EXTRA_PARAMS = (  # what is passed beside the estimators' own parameters, and by whom
    "tweedie_variance_power",  # fixed_params, under Tweedie
    "huber_slope",  # fixed_params: pseudo-Huber's delta
)
# XGBClassifier and XGBRegressor share XGBModel's parameters; `missing` is left out, since it
# would make the fit read a value as null that scoring (`_matrix`) reads as a value
ALLOWED_PARAMS = allowed_params(set(xgb.XGBModel().get_params()) - {"missing"}, EXTRA_PARAMS)
# Every name `fixed_params` can return, with what sets it: the search may not set them
# (`families.check_searched`), or the bundle would describe another model
OWNED_PARAMS = {
    "objective": "training.objective",
    "tweedie_variance_power": "training.tweedie_variance_power",
    "huber_slope": "training.objective (Huber's delta, fixed at 1.0)",
    "random_state": "training.seed",
    "n_jobs": "the run's thread count",
    "monotone_constraints": "training.monotone",
    "enable_categorical": "the encoder's declared categoricals",
    "feature_types": "the encoder's declared categoricals",
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
    """The constants every XGBoost fit of a run shares, trials and final fit alike (A55): the
    objective (with the variance power under Tweedie; Huber, pseudo-Huber here, has its delta
    fixed at 1.0), the seed, the threads, the declared categoricals as feature types, and the
    monotone constraints as a bracketed string over every feature (a short tuple is padded)."""
    check_encoder(encoder)
    params = {
        **objective_params(FAMILY, task, objective, OBJECTIVES),
        "random_state": seed,
        "n_jobs": threads,
    }
    if params["objective"] == "reg:tweedie":
        params["tweedie_variance_power"] = tweedie_power(FAMILY, tweedie_variance_power)
    directions = monotone_directions(FAMILY, encoder, monotone)
    if monotone:
        params["monotone_constraints"] = f"({','.join(str(d) for d in directions)})"
    categoricals = declared_categoricals(encoder)
    if categoricals:
        params["enable_categorical"] = True
        params["feature_types"] = [
            "c" if feature["name"] in categoricals else "float" for feature in encoder["features"]
        ]
    return params


def fit(X: pd.DataFrame, y: np.ndarray, params: dict, task: str) -> xgb.Booster:
    """The booster fitted on the frame `encode_frame` returned, which the caller checks once
    with `check_order` before the search and before the framework's own fits (`fit` has no
    encoder to check against), with every parameter in `params` (the searched ones merged over
    `fixed_params`), checked by name and translated as FLAML translates them. A configuration
    with neither a positive `max_depth` nor `max_leaves` fails: its trees would grow unlimited."""
    check_known_params(FAMILY, params, ALLOWED_PARAMS)
    check_vector_lengths(FAMILY, params, X)
    library = dict(params)
    library["max_depth"] = library.get("max_depth", 0)
    if library["max_depth"] <= 0 and library.get("max_leaves", 0) <= 0:
        raise ValueError(
            f"{FAMILY}: the configuration has neither a positive max_depth nor max_leaves, so "
            "its trees would grow without limit"
        )
    if library["max_depth"] == 0:  # no depth limit: grow leaf by leaf, as FLAML's `xgboost`
        library.setdefault("grow_policy", "lossguide")
        library.setdefault("tree_method", "hist")
    library["verbosity"] = 0
    return MODEL_CLASSES[task](**library).fit(X, y).get_booster()


def predict(booster: xgb.Booster, X: pd.DataFrame) -> np.ndarray:
    """The margin from every tree: log-odds for binary, the raw output for regression (the log
    scale under Tweedie and Poisson, A42)."""
    margin = booster.predict(
        _matrix(booster, X), output_margin=True, iteration_range=_every_tree(booster)
    )
    return margin.astype(np.float64)


def contributions(booster: xgb.Booster, X: pd.DataFrame) -> np.ndarray:
    """XGBoost's own per-feature contributions to the margin (SHAP's tree values), one column
    per feature in the booster's order and the base value last; a row sums to its margin."""
    values = booster.predict(
        _matrix(booster, X), pred_contribs=True, iteration_range=_every_tree(booster)
    )
    return values.astype(np.float64)


def describe(booster: xgb.Booster) -> dict:
    """What the model file records, the same for a fitted and a reloaded booster: the tree
    count, the features in order, the total split gain and the split count per feature, and the
    objective and model parameters the JSON file keeps (it keeps no training parameters)."""
    names = booster.feature_names
    gain = booster.get_score(importance_type="total_gain")
    splits = booster.get_score(importance_type="weight")
    learner = json.loads(booster.save_raw("json"))["learner"]
    return {
        "trees": booster.num_boosted_rounds(),
        "features": names,
        "gain": {name: float(gain.get(name, 0.0)) for name in names},
        "gain_type": "total_gain",
        "splits": {name: int(splits.get(name, 0)) for name in names},
        "parameters": {"objective": learner["objective"], "model": learner["learner_model_param"]},
    }


def save(booster: xgb.Booster, path: str) -> None:
    """The model as XGBoost's JSON file (the format follows the path's `.json`)."""
    booster.save_model(path)


def load(data: bytes) -> xgb.Booster:
    """The booster read back from its JSON file's bytes, as `save` wrote them (the bytes the
    bundle verified are the bytes that score, and no executor writes a file); the feature
    names, types and every round come with them."""
    booster = xgb.Booster()
    booster.load_model(bytearray(data))
    return booster


def _matrix(booster: xgb.Booster, X: pd.DataFrame) -> xgb.DMatrix:
    """`X` as XGBoost's matrix: float64 values in the booster's column order, with the
    booster's own feature names and types. XGBoost 3.2 scores the same without the types (a
    categorical split lives in its tree); they are passed so the matrix matches the booster."""
    names = booster.feature_names
    values = order_frame(FAMILY, X, names).to_numpy(np.float64, na_value=np.nan)
    return xgb.DMatrix(
        values, feature_names=names, feature_types=booster.feature_types, enable_categorical=True
    )


def _every_tree(booster: xgb.Booster) -> tuple[int, int]:
    """The explicit range of every boosting round: a reloaded booster uses the range it is
    given, so scoring never depends on the library's default."""
    return (0, booster.num_boosted_rounds())
