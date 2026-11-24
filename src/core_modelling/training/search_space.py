"""Training's search space as plain data (D-140 (b), (c); training.md → "The search").

`RANGES` holds the bounded ranges each family is searched on, four or five dimensions with a
start each, and `CONSTANTS` every other parameter FLAML would search on its own, held at the
library's default: at 15 to 50 trials a wide space is noise. `FLAML_SWITCHES` are the settings
of FLAML's `fit` the framework fixes, each because, left free, it would break a promise
(training.md has the table). `family_space` merges a config's `training.search_space` entry over
a family's defaults, leaf by leaf, and gives every ranged leaf a start: FLAML drops its own
start for a parameter the space overrides, and a space without starts searches nothing (T39).
The result is plain data, stored in `training.json` as the space the family searched;
`automl.py` turns it into FLAML's domains. `fit_parameters` is the one rule that gives a
configuration's parameters, to FLAML's trials and to every framework fit alike.
"""

from core_modelling.config.schema import SearchRange, SearchValue

# A leaf is a range `{low, high, log, integer, start}` or a constant `{value}`, as in the config.
# Starts are FLAML 2.7.0's own (`flaml/automl/model.py`) clipped into the range; CatBoost's
# depth and L2 penalty, which FLAML does not search, start at the library's defaults.
_LEARNING_RATE = {"low": 0.01, "high": 0.3, "log": True, "integer": False}
_TREES = {"low": 50, "high": 2000, "log": True, "integer": True, "start": 50}
_COLUMN_SHARE = {"low": 0.4, "high": 1.0, "log": False, "integer": False, "start": 1.0}
_CHILD_WEIGHT = {"low": 0.5, "high": 20.0, "log": True, "integer": False, "start": 1.0}
RANGES: dict[str, dict[str, dict]] = {
    "lgbm": {
        "learning_rate": {**_LEARNING_RATE, "start": 0.1},
        "n_estimators": _TREES,
        "num_leaves": {"low": 4, "high": 255, "log": True, "integer": True, "start": 4},
        "min_child_samples": {"low": 5, "high": 500, "log": True, "integer": True, "start": 20},
        "colsample_bytree": _COLUMN_SHARE,
    },
    "xgboost": {  # leaf-wise: no depth limit
        "learning_rate": {**_LEARNING_RATE, "start": 0.1},
        "n_estimators": _TREES,
        "max_leaves": {"low": 4, "high": 255, "log": True, "integer": True, "start": 4},
        "min_child_weight": _CHILD_WEIGHT,
        "colsample_bytree": _COLUMN_SHARE,
    },
    "xgb_limitdepth": {  # depth-wise
        "learning_rate": {**_LEARNING_RATE, "start": 0.3},
        "n_estimators": _TREES,
        "max_depth": {"low": 3, "high": 10, "log": False, "integer": True, "start": 6},
        "min_child_weight": _CHILD_WEIGHT,
        "colsample_bytree": _COLUMN_SHARE,
    },
    "catboost": {
        "learning_rate": {**_LEARNING_RATE, "start": 0.1},
        "n_estimators": _TREES,  # FLAML holds 8,192 unsearched; here it is tuned on the folds
        "depth": {"low": 4, "high": 8, "log": False, "integer": True, "start": 6},
        "l2_leaf_reg": {"low": 1.0, "high": 10.0, "log": True, "integer": False, "start": 3.0},
    },
}
# What FLAML would also search, held at the library's default (`log_max_bin` 8 is LightGBM's 255
# bins). A config may turn one into a range, with a `start`.
_XGB_CONSTANTS = {"subsample": 1.0, "colsample_bylevel": 1.0, "reg_alpha": 0.0, "reg_lambda": 1.0}
CONSTANTS: dict[str, dict[str, object]] = {
    "lgbm": {"log_max_bin": 8, "reg_alpha": 0.0, "reg_lambda": 0.0},
    "xgboost": _XGB_CONSTANTS,
    "xgb_limitdepth": _XGB_CONSTANTS,
    # FLAML searches CatBoost's `early_stopping_rounds`; a None constant takes that range out
    # (FLAML skips a None), so no trial is spent on a parameter without effect: the fixed
    # `use_best_model: False` already trains the searched tree count on every row
    "catboost": {"early_stopping_rounds": None},
}
FLAML_SWITCHES = {  # training.md → "The search", item 5
    "auto_augment": False,  # would copy rows of a rare class behind the calibration's back
    "ensemble": False,  # the bundle holds one booster in one native file (D-051)
    "early_stop": False,  # a trial budget means that many trials
    "sample": False,  # no subsampled early trials, whatever the evaluation method
    "log_type": "all",  # the trials table needs every trial
    "skip_transform": True,  # FLAML's hidden imputation and recoding never run (T38)
}


def family_space(family: str, overrides: dict[str, SearchRange | SearchValue]) -> dict[str, dict]:
    """The leaves `family` is searched on: its default ranges and constants with the config's
    `training.search_space[family]` entries (`overrides`) replacing them one leaf at a time.
    Every ranged leaf comes out with a start: the config's, else the family's default start (or
    default constant) clipped into the range. A new ranged parameter without one fails loud."""
    leaves = {name: dict(leaf) for name, leaf in RANGES[family].items()}
    leaves.update({name: {"value": value} for name, value in CONSTANTS[family].items()})
    for name, override in overrides.items():
        leaf = override.model_dump()
        if isinstance(override, SearchRange) and leaf["start"] is None:
            leaf["start"] = _default_start(family, name, leaves.get(name), leaf)
        leaves[name] = leaf
    return leaves


def _default_start(family: str, name: str, default: dict | None, leaf: dict) -> int | float:
    """A range's start when the config gives none: the default leaf's start or constant, clipped
    into the range (T39). A boolean or text constant is no start; neither is a missing default."""
    start = None if default is None else default.get("start", default.get("value"))
    if isinstance(start, bool) or not isinstance(start, int | float):
        raise ValueError(
            f"training.search_space.{family}.{name} is a range without a start, and the family "
            "has no default to start from: add `start`, the first trial's value (a search space "
            "without starts runs no search)"
        )
    clipped = min(max(start, leaf["low"]), leaf["high"])
    return int(round(clipped)) if leaf["integer"] else float(clipped)


def start_configuration(space: dict[str, dict]) -> dict:
    """The first trial's configuration of a `family_space`: every ranged leaf at its start and
    every constant at its value."""
    return {name: leaf.get("start", leaf.get("value")) for name, leaf in space.items()}


def fit_parameters(fixed: dict, space: dict[str, dict], searched: dict | None = None) -> dict:
    """One configuration's parameters as every fit takes them, the search's trials and the
    framework's own alike: the fixed parameters, the space's values over them (a constant, or a
    ranged leaf's start), then the `searched` values. The space wins over a fixed parameter: it
    may name LightGBM's constraint method, the one fixed name a config may set."""
    return {**fixed, **start_configuration(space), **(searched or {})}
