"""Training's search: one FLAML search per family on the dataset's client folds (D-140;
training.md → "The search").

FLAML only searches. This module holds the search's contract and `automl.py` FLAML's side of
it. `search_families` gives each listed family its trial budget (`split_budget`), the run's
fixed parameters and its bounded space with a start per ranged leaf (`search_space.py`), and
has FLAML search it with our folds as the splitter: every trial is fitted once per dealing and
fold and judged by the decision's metric. `check_search` refuses a search that did not run as
declared. The best family is the one whose best trial has the lowest mean fold loss. Its
configuration, merged over the fixed parameters, is what every later fit of the run uses through
`model.FAMILIES`; no model FLAML fitted is kept (D-140 (a)), and `check_judged_model` compares
the framework's own fold models, at every dealing, with the loss FLAML reported for that trial.
"""

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.config.schema import split_budget
from core_modelling.model.bundle import THREAD_PARAMS
from core_modelling.model.families import FAMILIES, check_params, check_searched
from core_modelling.statistics.losses import metric_value
from core_modelling.training.automl import (
    NOT_CONSTANTS,
    SEARCH_FRAMES,
    ClientFolds,
    flaml_settings,
    fold_splitter,
    read_trials,
    search_family,
)
from core_modelling.training.search_space import family_space, fit_parameters, start_configuration

# XGBoost's float32 margins move a fold loss by about 1e-10; a trial FLAML cut short by far more
LOSS_TOLERANCE = 1e-6


@dataclass
class Search:
    """A run's search: the best family, its parameters for every later fit (the fixed ones, the
    space's constants and the best trial's searched values; python scalars, the thread count
    included), the trials of every family (`automl.TRIAL_COLUMNS`), the space each family
    searched (`family_space`) and FLAML's log text per family, by file name."""

    family: str
    parameters: dict
    trials: pd.DataFrame
    spaces: dict[str, dict]
    logs: dict[str, str]

    @property
    def recorded_parameters(self) -> dict:
        """The best parameters as the bundle's recipe and `training.json` record them: without
        the thread count, a run setting no model depends on."""
        return {k: v for k, v in self.parameters.items() if k not in THREAD_PARAMS}


def checked_space(family: str, cfg: UseCaseConfig) -> dict[str, dict]:
    """The family's space (`family_space` under the config's `training.search_space`), its
    names checked: none that the framework sets itself, none the family's `fit` refuses."""
    space = family_space(family, cfg.training.search_space.get(family, {}))
    check_searched(family, space)
    check_params(family, start_configuration(space))
    return space


def check_spaces(cfg: UseCaseConfig) -> None:
    """Fail loud on what would otherwise stop the search after the work before it: a family
    left with fewer than two trials, or a name in a family's space that is misspelt or the
    framework's own. Training runs it first, so a run refused for it takes no run number."""
    for family in split_budget(cfg):
        checked_space(family, cfg)


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
    splitter = fold_splitter(folds)
    tables, spaces, logs, parameters = [], {}, {}, {}
    for family, budget in split_budget(cfg).items():
        trials, parameters[family], spaces[family], logs[f"flaml_{family}.log"] = _search_one(
            family, budget, X, y, splitter, encoder, monotone, cfg, threads
        )
        tables.append(trials)
    trials = pd.concat(tables, ignore_index=True)
    family = trials.loc[trials["fold_loss"].idxmin(), "family"]  # the first lowest: list order
    return Search(family, parameters[family], trials, spaces, logs)


def _search_one(
    family: str,
    budget: int,
    X: pd.DataFrame,
    y: np.ndarray,
    splitter: ClientFolds,
    encoder: dict,
    monotone: dict[str, str],
    cfg: UseCaseConfig,
    threads: int,
) -> tuple[pd.DataFrame, dict, dict, str]:
    """One family's search on its trial `budget`: `(its trials, the parameters of its best
    trial merged over the fixed ones, its space, FLAML's log text)`. `splitter` is the run's
    `fold_splitter`; the other arguments are `search_families`'."""
    training = cfg.training
    fixed = FAMILIES[family].fixed_params(
        cfg.task, training.objective, encoder, monotone, training.seed, threads,
        training.tweedie_variance_power,
    )  # fmt: skip
    space = checked_space(family, cfg)
    starts = {name: leaf["start"] for name, leaf in space.items() if "start" in leaf}
    at_start = fit_parameters(fixed, space)
    check_params(family, at_start)
    settings = flaml_settings(family, space, fixed, cfg, budget, threads)
    log = search_family(SEARCH_FRAMES[family](X, encoder), y, splitter, settings)
    constants = {
        name: value
        for name, value in at_start.items()
        if name not in starts and name not in NOT_CONSTANTS
    }
    trials = read_trials(family, log, list(starts), constants)
    check_search(family, trials, starts, budget if training.time_budget_s is None else None)
    best = trials.loc[trials["fold_loss"].idxmin()]
    print(
        f"search {family}: {len(trials)} trials in {trials['seconds'].sum():.0f} s, best "
        f"fold {cfg.decision.metric} "
        f"{metric_value(cfg.decision.metric, best['fold_loss']):.6f} at trial {best['trial']}"
    )
    return trials, fit_parameters(fixed, space, json.loads(best["configuration"])), space, log


def check_judged_model(
    search: Search, own_loss: float, timed: bool, dealings: int
) -> tuple[dict, list[str]]:
    """Whether the framework's own fold models reproduce the loss FLAML reported for the best
    trial: `own_loss` is their mean fold loss on the uncalibrated score over the same `dealings`
    of folds, as FLAML averages a trial. Returns `training.json`'s `judged_model` record (the
    dealings, both losses, whether they agree) and the warnings. A different loss means the
    search judged another model than the one that is kept, which fails loud under a trial
    budget. Under a time budget (`timed`) FLAML stops adding LightGBM's and XGBoost's trees at
    its deadline while its log keeps the configured count, so there it is a warning with both
    numbers."""
    family = search.family
    judged = float(search.trials.loc[search.trials["family"] == family, "fold_loss"].min())
    agrees = abs(own_loss - judged) <= LOSS_TOLERANCE * max(1.0, abs(judged))
    record = {"dealings": dealings, "search_loss": judged, "fold_models_loss": own_loss,
              "agrees": bool(agrees)}  # fmt: skip
    if agrees:
        return record, []
    difference = (
        f"the search judged the best trial of {family} at a fold loss of {judged:.6f}; the "
        f"framework's own fold models at that configuration give {own_loss:.6f} over the same "
        f"{dealings} dealings"
    )
    if not timed:
        raise ValueError(
            f"{difference}: the search judged another model than the one that would be kept"
        )
    return record, [
        f"{difference}. Under training.time_budget_s FLAML stops adding trees at its deadline, "
        "so a trial can be judged on fewer trees than its configuration names, and the choice "
        "of this configuration is not the search's as logged. Every number of this run is the "
        "framework's own; a trial budget (training.max_iter) avoids it"
    ]
