"""Training's search: one FLAML search per family on the dataset's client folds (D-140;
training.md → "The search").

FLAML only searches. `search_families` gives each listed family its trial budget
(`split_budget`), the run's fixed parameters and its bounded space with a start per ranged leaf
(`search_space.py`), and runs FLAML's local search with our folds as the splitter
(`fold_splitter`): every trial is fitted once per dealing and fold and judged by the decision's
metric (`search_metric`). The trials are read from FLAML's log, one row per trial, and
`check_search` refuses a search that did not run as declared. The best family is the one whose
best trial has the lowest mean fold loss. Its configuration, merged over the fixed parameters,
is what every later fit of the run uses through `model.FAMILIES`; no model FLAML fitted is kept
(D-140 (a)), and `check_judged_model` compares the framework's own fold models with the loss
FLAML reported for that trial.

What reaches FLAML how is measured on the pinned versions (training.md → "The encoder and the
families", item 7): the fixed parameters as constants of the space, three of them otherwise
(`FIT_ARGUMENTS`, the thread count, CatBoost's categoricals as `category` columns).
"""

import json
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd
from flaml import AutoML, tune

from core_modelling.config import UseCaseConfig
from core_modelling.model.families import FAMILIES, check_params, check_searched
from core_modelling.model.family_inputs import declared_categoricals
from core_modelling.statistics.losses import LOSSES, metric_value
from core_modelling.tasks import TASK_SPECS
from core_modelling.training.search_space import (
    FLAML_SWITCHES,
    family_space,
    start_configuration,
)

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
# XGBoost's float32 margins move a fold loss by about 1e-10; a trial FLAML cut short by far more
LOSS_TOLERANCE = 1e-6


@dataclass
class Search:
    """A run's search: the best family, its parameters for every later fit (the fixed ones, the
    space's constants and the best trial's searched values; python scalars, the thread count
    included), the trials of every family (`TRIAL_COLUMNS`), the space each family searched
    (`family_space`) and FLAML's log text per family, by file name."""

    family: str
    parameters: dict
    trials: pd.DataFrame
    spaces: dict[str, dict]
    logs: dict[str, str]


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


def split_budget(cfg: UseCaseConfig) -> dict[str, int]:
    """Each listed family's trial budget, in the list's order: `training.trials` when given,
    else `training.max_iter` in equal shares with the remainder, one trial each, to the first
    families (62 over four is 16, 16, 15, 15). A family left without a trial fails loud."""
    training = cfg.training
    if training.trials is not None:
        return {family: training.trials[family] for family in training.estimator_list}
    share, remainder = divmod(training.max_iter, len(training.estimator_list))
    if share == 0:
        raise ValueError(
            f"training.max_iter {training.max_iter} leaves some of the "
            f"{len(training.estimator_list)} listed families without a trial: raise it, list "
            "fewer families in training.estimator_list, or give each family its count in "
            "training.trials"
        )
    return {
        family: share + (position < remainder)
        for position, family in enumerate(training.estimator_list)
    }


def checked_space(family: str, cfg: UseCaseConfig) -> dict[str, dict]:
    """The family's space (`family_space` under the config's `training.search_space`), its
    names checked: none that the framework sets itself, none the family's `fit` refuses."""
    space = family_space(family, cfg.training.search_space.get(family, {}))
    check_searched(family, space)
    check_params(family, start_configuration(space))
    return space


def check_spaces(cfg: UseCaseConfig) -> None:
    """Fail loud on what would otherwise stop the search after the work before it: a family
    left without a trial, or a name in a family's space that is misspelt or the framework's own.
    Training runs it first, so a run refused for it takes no run number."""
    for family in split_budget(cfg):
        checked_space(family, cfg)


def fit_parameters(fixed: dict, space: dict[str, dict], searched: dict | None = None) -> dict:
    """One configuration's parameters as every fit takes them, the search's trials and the
    framework's own alike: the fixed parameters, the space's values over them (a constant, or a
    ranged leaf's start), then the `searched` values. The space wins over a fixed parameter: it
    may name LightGBM's constraint method, the one fixed name a config may set."""
    return {**fixed, **start_configuration(space), **(searched or {})}


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


def search_frame(family: str, X: pd.DataFrame, encoder: dict) -> pd.DataFrame:
    """The encoded frame as FLAML's wrapper of `family` needs it: unchanged for LightGBM and
    XGBoost (integer codes, declared through the fixed parameters); for CatBoost each declared
    categorical as a pandas `category` over all its codes (0 for null … K + 1 for `__other__`),
    which is the only way FLAML's CatBoost wrapper declares one. The model is the same either
    way (measured)."""
    if family != "catboost":
        return X
    levels = {e["name"]: e["levels"] for e in encoder["features"] if e["kind"] == "unordered"}
    return X.assign(
        **{
            name: pd.Categorical(X[name], categories=range(len(levels[name]) + 2))
            for name in declared_categoricals(encoder)
        }
    )


def search_family(X: pd.DataFrame, y: np.ndarray, splitter: ClientFolds, settings: dict) -> str:
    """Run FLAML's search with `settings` (`flaml_settings`) on the frame of one family
    (`search_frame`) and return its log's text: one JSON line per trial, then one naming the
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


def check_search(family: str, trials: pd.DataFrame, starts: dict, budget: int | None) -> None:
    """Fail loud unless one family's search ran as declared: it logged a trial, every fold loss
    is finite (FLAML goes on past a NaN or an infinity without a word), a trial budget ran that
    many trials (`budget` is None under a time budget), trial 1 is at the `starts` and, with more
    than one trial, the configurations differ (T39)."""
    if trials.empty:
        raise ValueError(
            f"the search of {family} logged no trial, so there is no configuration to fit; "
            "FLAML's own messages above say why"
        )
    bad = int((~np.isfinite(trials["fold_loss"])).sum())
    if bad:
        raise ValueError(
            f"{bad} of {len(trials)} trials of {family} have a non-finite fold loss: the "
            "metric is not defined on a validation fold (one without a positive, under roc_auc "
            "or ap); FLAML searches on past it without a word, so the search is not trusted"
        )
    if budget is not None and len(trials) != budget:
        raise ValueError(
            f"the search of {family} ran {len(trials)} trials on a budget of {budget}: a trial "
            "budget means that many trials"
        )
    first = json.loads(trials["configuration"].iloc[0])
    moved = {
        name: first[name] for name, start in starts.items() if not np.isclose(first[name], start)
    }
    if moved:
        raise ValueError(
            f"trial 1 of {family} is not at the starts: {moved} against {starts}; FLAML dropped "
            "them, so the space was not searched as declared (T39)"
        )
    if len(trials) > 1 and trials["configuration"].nunique() == 1:
        raise ValueError(
            f"the {len(trials)} trials of {family} ran one configuration: the search did not "
            "move (T39); a family whose every parameter is a constant takes one trial, through "
            "training.trials"
        )


def search_families(
    X: pd.DataFrame,
    y: np.ndarray,
    folds: pd.DataFrame,
    encoder: dict,
    monotone: dict[str, str],
    cfg: UseCaseConfig,
    threads: int,
) -> Search:
    """Search every listed family on its budget and pick the best.

    Receives the encoded train frame of the final features (one row per client and period, the
    columns in the encoder's order, checked by the caller with `check_order`), its target, its
    fold columns (one per dealing), the final features' encoder and constraints, the resolved
    config and the thread count. Every parameter name is checked before a family's first trial.
    The best family is the one with the lowest mean fold loss over every family's trials, the
    list's order deciding a tie.
    """
    if not folds.index.equals(X.index) or len(y) != len(X):
        raise ValueError(
            f"the frame ({len(X):,} rows), its target ({len(y):,}) and its folds "
            f"({len(folds):,}) must hold the same rows in the same order: the folds are read by "
            "position"
        )
    training, splitter = cfg.training, fold_splitter(folds)
    tables, spaces, logs, parameters = [], {}, {}, {}
    for family, budget in split_budget(cfg).items():
        fixed = FAMILIES[family].fixed_params(
            cfg.task, training.objective, encoder, monotone, training.seed, threads,
            training.tweedie_variance_power,
        )  # fmt: skip
        space = checked_space(family, cfg)
        starts = {name: leaf["start"] for name, leaf in space.items() if "start" in leaf}
        at_start = fit_parameters(fixed, space)
        check_params(family, at_start)
        settings = flaml_settings(family, space, fixed, cfg, budget, threads)
        logs[f"flaml_{family}.log"] = search_family(
            search_frame(family, X, encoder), y, splitter, settings
        )
        constants = {
            name: value
            for name, value in at_start.items()
            if name not in starts and name not in NOT_CONSTANTS
        }
        trials = read_trials(family, logs[f"flaml_{family}.log"], list(starts), constants)
        check_search(family, trials, starts, budget if training.time_budget_s is None else None)
        best = trials.loc[trials["fold_loss"].idxmin()]
        parameters[family] = fit_parameters(fixed, space, json.loads(best["configuration"]))
        tables.append(trials)
        spaces[family] = space
        print(
            f"search {family}: {len(trials)} trials in {trials['seconds'].sum():.0f} s, best "
            f"fold {cfg.decision.metric} "
            f"{metric_value(cfg.decision.metric, best['fold_loss']):.6f} at trial {best['trial']}"
        )
    trials = pd.concat(tables, ignore_index=True)
    family = trials.loc[trials["fold_loss"].idxmin(), "family"]  # the first lowest: list order
    return Search(family, parameters[family], trials, spaces, logs)


def check_judged_model(search: Search, own_loss: float, timed: bool) -> list[str]:
    """Whether the framework's own fold models reproduce the loss FLAML reported for the best
    trial: `own_loss` is their mean fold loss on the uncalibrated score, on the same folds (one
    dealing). A different loss means the search judged another model than the one that is
    kept, which fails loud under a trial budget. Under a time budget (`timed`) FLAML stops
    adding LightGBM's and XGBoost's trees at its deadline while its log keeps the configured
    count, so there it is returned as the run's warning, with both numbers."""
    family = search.family
    judged = float(search.trials.loc[search.trials["family"] == family, "fold_loss"].min())
    if abs(own_loss - judged) <= LOSS_TOLERANCE * max(1.0, abs(judged)):
        return []
    difference = (
        f"the search judged the best trial of {family} at a fold loss of {judged:.6f}; the "
        f"framework's own fold models at that configuration give {own_loss:.6f}"
    )
    if not timed:
        raise ValueError(
            f"{difference}: the search judged another model than the one that would be kept"
        )
    return [
        f"{difference}. Under training.time_budget_s FLAML stops adding trees at its deadline, "
        "so a trial can be judged on fewer trees than its configuration names, and the choice "
        "of this configuration is not the search's as logged. Every number of this run is the "
        "framework's own; a trial budget (training.max_iter) avoids it"
    ]
