"""The model families: one small set of plain functions per boosting library, behind `FAMILIES`.

Every later step fits, scores, saves and explains a model through `FAMILIES[name]`, keyed by
FLAML's learner names, so the search's trials, the fold models, the final fit, the bundle and
scoring in Spark treat a model one way (Q617, A55). A family reads the encoder as plain data
(`encoder.py` writes it) and saves the library's native file, never a pickle (D-051).

What every family pins, from the Stage 3 measurements on the pinned versions: the frame in the
booster's own column order with numerics as float64 (LightGBM scores a wrong order silently),
every tree at scoring, declared categoricals as integer codes, monotone constraints in the
library's own form (each library fails silently on another's), and a saved file whose bytes
repeat for a repeated fit at any thread count. The input checks the families share live in
`family_inputs.py`; `check_monotone` sweeps a fitted model against its declared constraints.
"""

from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType

import numpy as np
import pandas as pd

from core_modelling.model import catboost_family, lgbm_family, xgb_family
from core_modelling.model.family_inputs import DIRECTIONS, check_known_params

GRID_POINTS = 40  # check_monotone's sweep: this many quantiles of the feature's observed values
# Rounding is monotone, so a held constraint shows no wrong step in float64; XGBoost's margins
# are float32 (about 7 significant digits), so a step of 1e-6 of the margins' size is rounding,
# while a broken constraint moves the margin by a whole leaf value.
TOLERANCE = 1e-6


@dataclass(frozen=True)
class Family:
    """One boosting library's functions, the name of its native model file in a bundle, the
    parameter names its `fit` takes and the ones `fixed_params` owns (with what sets each)."""

    fit: Callable[[pd.DataFrame, np.ndarray, dict, str], object]
    predict: Callable[[object, pd.DataFrame], np.ndarray]
    describe: Callable[[object], dict]
    save: Callable[[object, str], None]
    load: Callable[[bytes], object]  # the bytes of the file `save` wrote
    contributions: Callable[[object, pd.DataFrame], np.ndarray]
    # (task, objective, encoder, monotone, seed, threads, tweedie_variance_power) -> dict
    fixed_params: Callable[..., dict]
    file_name: str
    allowed_params: frozenset[str]
    owned_params: dict[str, str]


def _family(module: ModuleType) -> Family:
    """A family module's seven functions, its file name and its parameter names."""
    return Family(
        fit=module.fit,
        predict=module.predict,
        describe=module.describe,
        save=module.save,
        load=module.load,
        contributions=module.contributions,
        fixed_params=module.fixed_params,
        file_name=module.FILE_NAME,
        allowed_params=module.ALLOWED_PARAMS,
        owned_params=module.OWNED_PARAMS,
    )


FAMILIES = {
    "lgbm": _family(lgbm_family),
    # One booster for both: FLAML's `xgboost` space has no `max_depth`, which `fit` reads as
    # leaf-wise growth, while `xgb_limitdepth` searches the depth (Q651).
    "xgboost": _family(xgb_family),
    "xgb_limitdepth": _family(xgb_family),
    "catboost": _family(catboost_family),
}


def check_params(family: str, params: dict) -> None:
    """Fail on a parameter name the family's `fit` would refuse, so that the search can check
    its space before the first trial."""
    check_known_params(family, params, FAMILIES[family].allowed_params)


def check_searched(family: str, searched: dict) -> None:
    """Fail on a searched name that `fixed_params` owns: a searched objective would train
    another link than the bundle records, a searched seed would replace `training.seed`."""
    owned = FAMILIES[family].owned_params
    taken = sorted(set(searched) & set(owned))
    if taken:
        sources = "; ".join(f"`{name}` comes from {owned[name]}" for name in taken)
        raise ValueError(f"{family}: the search may not set {taken}: {sources}")


def check_monotone(
    family: str, booster: object, X: pd.DataFrame, monotone: dict[str, str], rows: int = 200
) -> None:
    """Fail unless the margin follows every declared constraint. Each constrained feature is
    swept over about `GRID_POINTS` quantiles of its observed values in `X`, on the first `rows`
    rows with the other columns held, and a step against the direction fails (Q650's check).
    A constant feature is not tested: its grid holds one value and no step."""
    sample = X.head(rows)
    for name, direction in monotone.items():
        if X[name].isna().all():
            raise ValueError(
                f"{family}: the constrained feature {name!r} is null on every row given, so "
                "its constraint cannot be checked"
            )
        grid = _sweep_grid(X[name])
        swept = pd.concat([sample.assign(**{name: value}) for value in grid], ignore_index=True)
        margins = FAMILIES[family].predict(booster, swept).reshape(len(grid), len(sample))
        steps = np.diff(margins, axis=0) * DIRECTIONS[direction]
        wrong = int((steps < -TOLERANCE * max(1.0, np.abs(margins).max())).sum())
        if wrong:
            raise ValueError(
                f"{family}: the margin moves against the declared {direction} constraint on "
                f"{name!r} in {wrong} of {steps.size} steps ({len(sample)} rows, "
                f"{len(grid)} values)"
            )


def _sweep_grid(values: pd.Series) -> np.ndarray:
    """About `GRID_POINTS` distinct observed values of a feature, at its quantiles, null left out
    (the null branch is free under a constraint in LightGBM and XGBoost, Q650)."""
    observed = values.dropna().to_numpy(dtype=np.float64)
    return np.unique(np.quantile(observed, np.linspace(0, 1, GRID_POINTS), method="nearest"))
