"""What every model family checks in its inputs before a library sees them: the objective and
Tweedie's power, the categoricals the encoder declares, the monotone constraints, the parameter
names, and the frame's columns against the encoder's and the booster's. The family modules
(`lgbm_family.py`, `xgb_family.py`, `catboost_family.py`) share these helpers and translate the
checked inputs into their library's own form; the encoder itself is checked by `encoder.py`'s
`check_encoder`. This module imports no family module, so `families.py` can import them all.
"""

from itertools import zip_longest

import pandas as pd

DIRECTIONS = {"increasing": 1, "decreasing": -1}
# A class weight makes a model believe positives are more common than they are, and the
# calibration undoes only the declared sampling (A4): the config refuses these names, and no
# family takes one either, whatever its estimator lists. Compared as given: the libraries are
# case-sensitive, so a mixed-case name is outside every allowed set anyway.
REWEIGHTING_PARAMS = (
    "scale_pos_weight",  # LightGBM, XGBoost, CatBoost
    "is_unbalance",  # LightGBM, with its aliases `unbalance` and `unbalanced_sets`
    "unbalance",
    "unbalanced_sets",
    "class_weight",  # LightGBM's scikit-learn estimator
    "class_weights",  # CatBoost
    "auto_class_weights",  # CatBoost
)
# Parameters that hold one entry per feature, in the encoder's order
POSITIONAL_PARAMS = ("monotone_constraints", "feature_types")


def objective_params(family: str, task: str, objective: str, objectives: dict) -> dict:
    """A family's parameters for the objective, from its table `{task: {name: parameters}}`:
    binary takes `log_loss` only, regression one of Q639's names."""
    if task not in objectives:
        raise ValueError(f"{family}: unknown task {task!r}; expected one of {sorted(objectives)}")
    if objective not in objectives[task]:
        raise ValueError(
            f"{family}: {task} takes the objectives {sorted(objectives[task])}, not {objective!r}"
        )
    return dict(objectives[task][objective])


def tweedie_power(family: str, power: float | None) -> float:
    """Tweedie's variance power, checked: given, and strictly between 1 (Poisson) and 2
    (gamma), the range of a mass at zero and a skewed positive part (Q639)."""
    if power is None or not 1 < power < 2:
        raise ValueError(
            f"{family}: the Tweedie objective needs `training.tweedie_variance_power` in (1, 2); "
            f"it is {power!r}"
        )
    return power


def declared_categoricals(encoder: dict) -> list[str]:
    """The unordered features a family declares categorical to its library: all of them under
    `native`, none under `codes`, where their codes are plain numbers (Q609)."""
    if encoder["unordered"] == "codes":
        return []
    return [feature["name"] for feature in encoder["features"] if feature["kind"] == "unordered"]


def monotone_directions(family: str, encoder: dict, monotone: dict[str, str]) -> list[int]:
    """The constraint per encoder feature, in the encoder's order: 1 increasing, -1 decreasing,
    0 free. A constraint on an unordered categorical or on a name the encoder lacks fails here,
    before any library sees it (LightGBM would abort the process, XGBoost ignore it, Q650)."""
    kinds = {feature["name"]: feature["kind"] for feature in encoder["features"]}
    for name, direction in monotone.items():
        if name not in kinds:
            raise ValueError(f"{family}: a monotone constraint on {name!r}, not a model feature")
        if kinds[name] == "unordered":
            raise ValueError(
                f"{family}: a monotone constraint on {name!r}, an unordered categorical; "
                "constraints apply to numeric and ordered features only"
            )
        if direction not in DIRECTIONS:
            raise ValueError(
                f"{family}: {name!r} is constrained {direction!r}; expected one of "
                f"{sorted(DIRECTIONS)}"
            )
    return [DIRECTIONS[monotone[name]] if name in monotone else 0 for name in kinds]


def allowed_params(estimator_params: set[str], extras: tuple[str, ...]) -> frozenset[str]:
    """The parameter names a family takes: its estimator's own and the named extras, never a
    class weight."""
    return frozenset((estimator_params | set(extras)) - set(REWEIGHTING_PARAMS))


def check_known_params(family: str, params: dict, allowed: frozenset[str]) -> None:
    """Fail on a parameter the family does not take: LightGBM and XGBoost run silent, so a
    misspelt name would train on the library's default without a word, and a class weight
    would skew every score."""
    unknown = sorted(set(params) - allowed)
    if not unknown:
        return
    weights = [name for name in unknown if name in REWEIGHTING_PARAMS]
    why = (
        f"; {weights} are class weights, which change the class balance without the "
        "calibration knowing: use `training.sampling: negative_downsampling`"
        if weights
        else ""
    )
    raise ValueError(
        f"{family}: the parameters {unknown} are not taken{why}; an unknown parameter that is "
        "really wanted goes into `EXTRA_PARAMS` of its family module (`lgbm_family.py`, "
        "`xgb_family.py` or `catboost_family.py`)"
    )


def check_vector_lengths(family: str, params: dict, X: pd.DataFrame) -> None:
    """Fail unless every positional vector in `params` (a monotone constraint string,
    XGBoost's feature types) holds one entry per column of `X`: XGBoost and CatBoost take a
    short vector without a word. The backstop inside `fit` when `check_order` was not run."""
    for name in POSITIONAL_PARAMS:
        if name not in params:
            continue
        value = params[name]
        length = len(value.strip("()").split(",")) if isinstance(value, str) else len(value)
        if length != X.shape[1]:
            raise ValueError(
                f"{family}: `{name}` holds {length} entries for a frame of {X.shape[1]} "
                "columns; it is built in the encoder's order for the encoded frame"
            )


def check_order(X: pd.DataFrame, encoder: dict) -> None:
    """Fail unless `X`'s columns are the encoder's features in the encoder's order, which
    `fixed_params` builds its positional vectors in (the constraints, XGBoost's feature types).
    The caller runs it once on the frame `encode_frame` returned, before the search and before
    the framework's own fits; `fit` has no encoder to check against."""
    names = [feature["name"] for feature in encoder["features"]]
    for position, (column, name) in enumerate(zip_longest(X.columns, names)):
        if column != name:
            raise ValueError(
                f"the frame's columns are not the encoder's features in order: position "
                f"{position} holds {column!r} where the encoder has {name!r}"
            )


def order_frame(family: str, X: pd.DataFrame, names: list[str]) -> pd.DataFrame:
    """`X`'s columns in the booster's order `names`. A missing column fails, and so does an
    extra one: the encoded frame holds exactly the model's features, so an extra column means
    the wrong frame or the wrong model."""
    missing = [name for name in names if name not in X.columns]
    extra = [name for name in X.columns if name not in names]
    if missing or extra:
        raise ValueError(
            f"{family}: the frame does not hold the model's features: missing {missing}, "
            f"extra {extra}"
        )
    return X[names]
