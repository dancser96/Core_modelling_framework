"""LightGBM as a model family (`lgbm`): the functions `FAMILIES["lgbm"]` holds (`families.py`).

`fit` mirrors FLAML 2.7's `LGBMEstimator` (`flaml/automl/model.py`), so that a fit from FLAML's
best configuration is FLAML's own model: the scikit-learn estimator, FLAML's `log_max_bin`
turned into `max_bin`, silent logging, and the declared categoricals as a fit argument (among
the estimator's parameters LightGBM refuses them). It returns LightGBM's own `Booster`, which is
also what `load` reads back from the text model.

LightGBM scores a frame in the wrong column order without a word, so every scoring call
reorders the frame to the booster's own feature names and passes float64 values. The saved text
model leaves out its thread-count line, so it repeats byte for byte at any thread count.
"""

import lightgbm as lgb
import numpy as np
import pandas as pd

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

FAMILY = "lgbm"
FILE_NAME = "model.txt"
MODEL_CLASSES = {"binary": lgb.LGBMClassifier, "regression": lgb.LGBMRegressor}
OBJECTIVES = {  # the config's objective names in LightGBM's words
    "binary": {"log_loss": {"objective": "binary"}},
    "regression": {
        "squared_error": {"objective": "regression"},
        "tweedie": {"objective": "tweedie"},
        "poisson": {"objective": "poisson"},
        "absolute_error": {"objective": "regression_l1"},
        "huber": {"objective": "huber", "alpha": 1.0},  # `alpha` is Huber's delta here
    },
}
# The text model records the training thread count in one parameter line. It is left out so
# that one model has one file and one `model_hash`, on a laptop and inside the bank alike: the
# trees do not depend on it, and LightGBM reads the file back without it.
THREADS_LINE = "[num_threads: "
EXTRA_PARAMS = (  # what is passed beside the estimators' own parameters, and by whom
    "monotone_constraints",  # fixed_params: the declared constraints
    "monotone_constraints_method",  # fixed_params: `basic`; `intermediate` may be searched
    "tweedie_variance_power",  # fixed_params, under Tweedie
    "alpha",  # fixed_params: Huber's delta
    "categorical_feature",  # fixed_params: the declared categoricals, a fit argument
    "log_max_bin",  # FLAML's search space: the bin count on a log2 scale
    "max_bin",  # what FLAML's `config2params` makes of it, also settable as a constant
    "verbose",  # fit's silence, as FLAML's
    "colsample_bynode",  # a searchable column share per node (refused beside `intermediate`)
)
# LGBMClassifier and LGBMRegressor share LGBMModel's parameters
ALLOWED_PARAMS = allowed_params(set(lgb.LGBMModel().get_params()), EXTRA_PARAMS)
# Every name `fixed_params` can return but the constraint method, with what sets it: the search
# may not set them (`families.check_searched`), or the bundle would describe another model
OWNED_PARAMS = {
    "objective": "training.objective",
    "tweedie_variance_power": "training.tweedie_variance_power",
    "alpha": "training.objective (Huber's delta, fixed at 1.0)",
    "random_state": "training.seed",
    "n_jobs": "the run's thread count",
    "monotone_constraints": "training.monotone",
    "categorical_feature": "the encoder's declared categoricals",
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
    """The constants every LightGBM fit of a run shares, trials and final fit alike: the
    objective (with the variance power under Tweedie; Huber's delta is fixed at 1.0), the seed,
    the threads, the declared categoricals (a fit argument), the monotone constraints as a comma
    string in the encoder's order (a bracketed string loses its first entry), and the `basic`
    constraint method."""
    check_encoder(encoder)
    params = {
        **objective_params(FAMILY, task, objective, OBJECTIVES),
        "random_state": seed,
        "n_jobs": threads,
        "monotone_constraints_method": "basic",
    }
    if params["objective"] == "tweedie":
        params["tweedie_variance_power"] = tweedie_power(FAMILY, tweedie_variance_power)
    directions = monotone_directions(FAMILY, encoder, monotone)
    if monotone:
        params["monotone_constraints"] = ",".join(str(direction) for direction in directions)
    categoricals = declared_categoricals(encoder)
    if categoricals:
        params["categorical_feature"] = categoricals
    return params


def fit(X: pd.DataFrame, y: np.ndarray, params: dict, task: str) -> lgb.Booster:
    """The booster fitted on the frame `encode_frame` returned, which the caller checks once
    with `check_order` before the search and before the framework's own fits (`fit` has no
    encoder to check against), with every parameter in `params` (the searched ones merged over
    `fixed_params`), checked by name and translated as FLAML translates them."""
    check_known_params(FAMILY, params, ALLOWED_PARAMS)
    check_vector_lengths(FAMILY, params, X)
    library = dict(params)
    categorical = library.pop("categorical_feature", "auto")
    if "log_max_bin" in library:  # FLAML searches the bin count on a log2 scale
        library["max_bin"] = (1 << library.pop("log_max_bin")) - 1
    library.setdefault("verbose", -1)
    model = MODEL_CLASSES[task](**library)
    return model.fit(X, y, categorical_feature=categorical).booster_


def predict(booster: lgb.Booster, X: pd.DataFrame, threads: int | None = None) -> np.ndarray:
    """The margin from every tree: log-odds for binary, the raw output for regression (the log
    scale under Tweedie and Poisson). `threads` caps LightGBM's threads (None: its default,
    every core); the margins are the same at any count."""
    extra = {} if threads is None else {"num_threads": threads}
    return booster.predict(
        _values(booster, X), raw_score=True, num_iteration=booster.current_iteration(), **extra
    )


def contributions(booster: lgb.Booster, X: pd.DataFrame, threads: int | None = None) -> np.ndarray:
    """LightGBM's own per-feature contributions to the margin (SHAP's tree values), one column
    per feature in the booster's order and the base value last; a row sums to its margin.
    `threads` as in `predict`."""
    extra = {} if threads is None else {"num_threads": threads}
    return booster.predict(
        _values(booster, X), pred_contrib=True, num_iteration=booster.current_iteration(), **extra
    )


def describe(booster: lgb.Booster) -> dict:
    """What the model file records, the same for a fitted and a reloaded booster: the tree
    count, the features in order, the total split gain and the split count per feature, and the
    parameters the text model keeps."""
    names = booster.feature_name()
    gain = booster.feature_importance(importance_type="gain")
    splits = booster.feature_importance(importance_type="split")
    return {
        "trees": booster.num_trees(),
        "features": names,
        "gain": dict(zip(names, gain.tolist(), strict=True)),
        "gain_type": "gain",
        "splits": dict(zip(names, splits.tolist(), strict=True)),
        # a fitted booster holds only the parameters it was given, and a booster built from a
        # text keeps none, so LightGBM's own reader (what its `model_file` path calls) reads them;
        # `_get_loaded_param` is private, checked on the pinned LightGBM 4.6.0
        "parameters": lgb.Booster(model_str=_model_text(booster))._get_loaded_param(),
    }


def save(booster: lgb.Booster, path: str) -> None:
    """The model as LightGBM's text file, every tree in it and no thread count."""
    with open(path, "w", encoding="utf-8", newline="") as file:
        file.write(_model_text(booster))


def load(data: bytes) -> lgb.Booster:
    """The booster read back from its text file's bytes, as `save` wrote them (the bytes the
    bundle verified are the bytes that score, and no executor writes a file)."""
    return lgb.Booster(model_str=data.decode("utf-8"))


def _model_text(booster: lgb.Booster) -> str:
    """The text model with every tree, without its thread-count line (`THREADS_LINE`)."""
    lines = booster.model_to_string(num_iteration=-1).splitlines(keepends=True)
    return "".join(line for line in lines if not line.startswith(THREADS_LINE))


def _values(booster: lgb.Booster, X: pd.DataFrame) -> np.ndarray:
    """`X`'s values in the booster's column order, as float64 (LightGBM shifts on float32)."""
    return order_frame(FAMILY, X, booster.feature_name()).to_numpy(np.float64, na_value=np.nan)
