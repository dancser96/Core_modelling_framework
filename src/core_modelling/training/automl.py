"""FLAML's side of Training's search: everything that touches FLAML's API (D-140; training.md →
"The search").

`search.py` decides what is searched and checks the result; this module turns that into one
FLAML run per family and reads it back. `fold_splitter` hands FLAML the dataset's client folds
as its splitter, `build_search_space` and `flaml_settings` give it the space and the fixed
switches, `search_metric` the decision's metric by FLAML's name or as a custom metric,
`SEARCH_FRAMES` the frame each family's FLAML wrapper needs, `search_family` runs the search
and returns FLAML's log, and `read_trials` reads the log into the trials table, refusing a trial
fitted with other parameters than the framework's own fits take.

What reaches FLAML how is measured on the pinned versions (training.md → "The encoder and the
families", item 7): the fixed parameters as constants of the space, three of them otherwise
(`FIT_ARGUMENTS`, the thread count, CatBoost's categoricals as `category` columns).
"""

import json
import tempfile
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd
from flaml import AutoML, tune

from core_modelling.config import UseCaseConfig
from core_modelling.model.family_inputs import declared_categoricals
from core_modelling.statistics.losses import LOSSES
from core_modelling.tasks import TASK_SPECS
from core_modelling.training.search_space import FLAML_SWITCHES, fit_parameters

FLAML_METRICS = ("log_loss", "roc_auc", "ap", "rmse", "mae", "r2")  # FLAML's own, by name (T9)
# Fixed parameters FLAML takes as arguments of the library's `fit`, never as constants
FIT_ARGUMENTS = ("categorical_feature", "use_best_model")
# Fixed parameters that are no constants of the space: the fit arguments, the thread count
# (`AutoML.fit(n_jobs=)`) and CatBoost's categoricals (FLAML reads them off `category` columns)
NOT_CONSTANTS = (*FIT_ARGUMENTS, "n_jobs", "cat_features")
# The parameters that set a model's size: FLAML's local search steps from each one's cheapest
# value, and a space given through `custom_hp` replaces FLAML's own, so the start is named as it
SIZE_PARAMETERS = ("n_estimators", "num_leaves", "max_leaves", "max_depth", "depth")
TRIAL_COLUMNS = ["family", "trial", "fold_loss", "seconds", "improving", "configuration"]


class ClientFolds:
    """The dataset's client folds as a scikit-learn splitter, which is what FLAML takes: per
    dealing (a fold column) and fold, the positions of the rows outside the fold and of the rows
    in it. A class because the splitter protocol is two methods on one object."""

    shuffle = False  # without it FLAML permutes each fold's training rows (T42)

    def __init__(self, folds: pd.DataFrame) -> None:
        """`folds`: the frame's fold columns, one per dealing, on the rows FLAML is given."""
        self.dealings = [folds[column].to_numpy() for column in folds.columns]

    def get_n_splits(self, X: object = None, y: object = None, groups: object = None) -> int:
        """R × K: every dealing's folds."""
        return sum(len(np.unique(dealing)) for dealing in self.dealings)

    def split(
        self, X: object = None, y: object = None, groups: object = None
    ) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """`(train positions, validation positions)` per dealing and fold, in that order."""
        for dealing in self.dealings:
            for fold in np.unique(dealing):
                yield np.flatnonzero(dealing != fold), np.flatnonzero(dealing == fold)


def fold_splitter(folds: pd.DataFrame) -> ClientFolds:
    """The splitter FLAML cross-validates every trial on: the frame's fold columns, so a trial
    is fitted R × K times and no client's rows are on both sides of a fit (`CLAUDE.md` §4.11).
    A row without a fold, or a dealing with one fold, fails loud."""
    unfolded = int(folds.isna().any(axis=1).sum())
    if unfolded:
        raise ValueError(
            f"{unfolded:,} of {len(folds):,} train rows have a null fold: every train row needs "
            "its client's fold in every dealing"
        )
    single = [column for column in folds.columns if folds[column].nunique() < 2]
    if single:
        raise ValueError(f"the dealings {single} hold one fold: no trial could be validated")
    return ClientFolds(folds)


def search_metric(metric: str) -> str | Callable:
    """What FLAML minimises for the decision's `metric`: its own metric by name, or for the two
    deviances, which it lacks, a custom metric on the trial model's predictions."""
    return metric if metric in FLAML_METRICS else partial(_custom_metric, metric)


def _custom_metric(
    metric: str, X_val: pd.DataFrame, y_val: np.ndarray, estimator: object, *unused: object
) -> tuple[float, dict]:
    """A `LOSSES` entry in the form FLAML calls a custom metric (the validation frame, its
    target, the trial's fitted estimator and eight arguments unused here) and reads its result
    (the loss and a dict to log). `estimator.predict` is in the target's units: the mean under a
    log link. A prediction the deviance refuses raises and stops the search."""
    loss = LOSSES[metric](np.asarray(y_val), np.asarray(estimator.predict(X_val)))
    return loss, {metric: loss}


def build_search_space(space: dict[str, dict], fixed: dict) -> dict:
    """FLAML's `custom_hp` entry of one family, from its `family_space` and its fixed
    parameters: a ranged leaf as a domain with its start (`init_value`; a space without starts
    searches nothing, T39), and every other value of `fit_parameters` but `NOT_CONSTANTS` as a
    one-value domain, so a trial is fitted with what the framework's own fits take."""
    entries = {
        name: {"domain": value}
        for name, value in fit_parameters(fixed, space).items()
        if name not in NOT_CONSTANTS
    }
    for name, leaf in space.items():
        if "start" in leaf:
            entries[name] = {"domain": _domain(leaf), "init_value": leaf["start"]}
            if name in SIZE_PARAMETERS:
                entries[name]["low_cost_init_value"] = leaf["start"]
    return entries


def _domain(leaf: dict) -> object:
    """A range `{low, high, log, integer}` as FLAML's sampling domain, both ends included: an
    integer domain's upper bound is exclusive in FLAML, so it gets `high + 1`."""
    low, high = leaf["low"], leaf["high"]
    if leaf["integer"]:
        return (tune.lograndint if leaf["log"] else tune.randint)(low, high + 1)
    return (tune.loguniform if leaf["log"] else tune.uniform)(low, high)


def flaml_settings(
    family: str, space: dict[str, dict], fixed: dict, cfg: UseCaseConfig, budget: int, threads: int
) -> dict:
    """Every argument of FLAML's `fit` for one family's search but the data, the splitter and
    the log's path: the task, the metric, the family alone on its trial budget, cross-validation,
    the space, the fit arguments, the threads, the seed and the fixed switches. A time budget
    (`training.time_budget_s`, per family) is added when set."""
    training = cfg.training
    settings = {
        "task": TASK_SPECS[cfg.task]["flaml_task"],
        "metric": search_metric(cfg.decision.metric),
        "estimator_list": [family],
        "max_iter": budget,
        "eval_method": "cv",
        "custom_hp": {family: build_search_space(space, fixed)},
        "fit_kwargs_by_estimator": {
            family: {name: fixed[name] for name in FIT_ARGUMENTS if name in fixed}
        },
        "n_jobs": threads,
        "seed": training.seed,
        "verbose": 0,
        **FLAML_SWITCHES,
    }
    if training.time_budget_s is not None:
        settings["time_budget"] = training.time_budget_s
    return settings


def _as_encoded(X: pd.DataFrame, encoder: dict) -> pd.DataFrame:
    """The encoded frame unchanged: LightGBM's and XGBoost's wrappers take the integer codes,
    declared through the fixed parameters."""
    return X


def _with_categories(X: pd.DataFrame, encoder: dict) -> pd.DataFrame:
    """Each declared categorical as a pandas `category` over all its codes (0 for null … K + 1
    for `__other__`), the only way FLAML's CatBoost wrapper declares one. The model is the same
    either way (measured)."""
    levels = {e["name"]: e["levels"] for e in encoder["features"] if e["kind"] == "unordered"}
    return X.assign(
        **{
            name: pd.Categorical(X[name], categories=range(len(levels[name]) + 2))
            for name in declared_categoricals(encoder)
        }
    )


# The encoded frame as each family's FLAML wrapper needs it: (X, encoder) -> frame
SEARCH_FRAMES: dict[str, Callable[[pd.DataFrame, dict], pd.DataFrame]] = {
    "lgbm": _as_encoded,
    "xgboost": _as_encoded,
    "xgb_limitdepth": _as_encoded,
    "catboost": _with_categories,
}


def search_family(X: pd.DataFrame, y: np.ndarray, splitter: ClientFolds, settings: dict) -> str:
    """Run FLAML's search with `settings` (`flaml_settings`) on the frame of one family
    (`SEARCH_FRAMES`) and return its log's text: one JSON line per trial, then one naming the
    best record. The log goes through a temporary folder; Training saves the text."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "flaml.log"
        AutoML().fit(X_train=X, y_train=y, split_type=splitter, log_file_name=str(path), **settings)
        if not path.is_file():
            raise FileNotFoundError(
                f"FLAML wrote no log for {settings['estimator_list']}: the trials cannot be read"
            )
        return path.read_text()


def read_trials(family: str, log: str, searched: list[str], constants: dict) -> pd.DataFrame:
    """One family's trials from FLAML's log text (`TRIAL_COLUMNS`): the trial's number from 1,
    its mean fold loss, its seconds, whether it is a new best, and its values of the `searched`
    parameters as JSON text. FLAML's `config_history` holds improving trials only (T14).

    A trial whose other values are not `constants` (what the framework's own fits take beside
    the searched ones; FLAML leaves a None out) fails loud: the search would have judged another
    model than the one that is kept, or searched a parameter the space does not name."""
    records = [json.loads(line) for line in log.splitlines() if line.strip()]
    records = [record for record in records if "validation_loss" in record]
    expected = {name: value for name, value in constants.items() if value is not None}
    for record in records:
        logged = {k: v for k, v in record["config"].items() if k not in searched}
        if logged != expected:
            differing = sorted(
                name
                for name in set(logged) | set(expected)
                if logged.get(name) != expected.get(name)
            )
            raise ValueError(
                f"trial {record['record_id'] + 1} of {family} was not fitted with the "
                f"framework's parameters: {differing} differ (FLAML's "
                f"{ {n: logged.get(n) for n in differing} }, the framework's "
                f"{ {n: expected.get(n) for n in differing} }); the kept model would not be the "
                "one the search judged"
            )
    rows = [
        {
            "family": family,
            "trial": record["record_id"] + 1,
            "fold_loss": float(record["validation_loss"]),
            "seconds": float(record["trial_time"]),
            "configuration": json.dumps(
                {name: record["config"][name] for name in searched}, sort_keys=True
            ),
        }
        for record in records
    ]
    trials = pd.DataFrame(rows, columns=TRIAL_COLUMNS).astype({"fold_loss": "float64"})
    best_before = trials["fold_loss"].cummin().shift(fill_value=np.inf)
    return trials.assign(improving=trials["fold_loss"] < best_before)
