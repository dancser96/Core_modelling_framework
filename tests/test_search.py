"""The search on a small constructed frame (no Spark; `lgbm`): the budget's split, the space
FLAML receives, our client folds as its splitter, the constraint and the categoricals in every
trial fit, the search's best loss against the framework's own fold fits, and the refusals of a
search that did not run as declared (D-140; `docs/context/lessons.md` T39, T42).
"""

import json
from collections.abc import Callable

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest
from conftest import REGRESSION
from scipy.special import expit
from sklearn.metrics import log_loss, mean_tweedie_deviance

from core_modelling.config import UseCaseConfig
from core_modelling.model.encoder import encode_frame, fit_encoder
from core_modelling.model.families import FAMILIES
from core_modelling.training.search import (
    NOT_CONSTANTS,
    TRIAL_COLUMNS,
    Search,
    build_search_space,
    check_judged_model,
    check_search,
    check_spaces,
    fold_splitter,
    read_trials,
    search_families,
    split_budget,
)
from core_modelling.training.search_space import RANGES, family_space

CLIENTS, FOLDS, TRIALS, SEED = 900, 3, 6, 7
FEATURES = ["x1", "x2", "x3", "grade", "region"]
KINDS = {"x1": "numeric", "x2": "numeric", "x3": "numeric", "grade": "categorical",
         "region": "categorical"}  # fmt: skip
GRADES = ["A", "B", "C", "D", "E"]
MONOTONE = {"x1": "increasing", "grade": "increasing"}
FOLD_COLUMNS = ["cv_fold", "cv_fold_2"]
STARTS = {name: leaf["start"] for name, leaf in RANGES["lgbm"].items()}


def _panel() -> pd.DataFrame:
    """Three to six rows per client: three numerics (`x1` with nulls), an ordered grade and an
    unordered region, a binary target near 12%, a zero-heavy amount, and two dealings of
    `FOLDS` client folds."""
    rng = np.random.default_rng(0)
    periods = rng.integers(3, 7, CLIENTS)
    unit = np.repeat(np.arange(CLIENTS), periods)
    n = unit.size
    x1, x2, x3 = rng.normal(size=n), rng.normal(size=n), rng.normal(size=n)
    grade = np.clip(np.round(x3 + 2 + rng.normal(scale=0.7, size=n)), 0, 4).astype(int)
    region = rng.integers(0, 6, n)
    effect = np.array([0.0, 0.4, -0.3, 0.6, -0.5, 0.2])[region]
    signal = 0.8 * x1 + 0.35 * grade + effect + 0.3 * x2
    frame = pd.DataFrame({"unit_id": unit, "x1": x1, "x2": x2, "x3": x3})
    frame["grade"] = np.array(GRADES)[grade]
    frame["region"] = np.array([f"r{i}" for i in range(6)])[region]
    frame.loc[rng.random(n) < 0.05, "x1"] = np.nan
    frame["target"] = rng.binomial(1, expit(signal - 3.2))
    frame["amount"] = rng.binomial(1, expit(signal - 1.5)) * np.exp(1 + 0.4 * signal)
    frame["cv_fold"] = rng.permutation(CLIENTS)[unit] % FOLDS
    frame["cv_fold_2"] = rng.permutation(CLIENTS)[unit] % FOLDS
    return frame


@pytest.fixture(scope="module")
def data() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """The panel, its encoded frame and the encoder (levels kept from ten clients)."""
    train = _panel()
    encoder = fit_encoder(train, FEATURES, KINDS, {"grade": GRADES}, 10, "native")
    return train, encode_frame(train, encoder)[0], encoder


@pytest.fixture(scope="module")
def cfg(variant: Callable[..., UseCaseConfig]) -> UseCaseConfig:
    """The card config searching `lgbm` alone for `TRIALS` trials on two dealings, judged by the
    log loss, with the two constraints."""
    training = {"estimator_list": ["lgbm"], "max_iter": TRIALS, "fold_repeats": 2,
                "folds": FOLDS, "seed": SEED, "monotone": MONOTONE}  # fmt: skip
    return variant(training=training)


def _recorded_search(data: tuple, cfg: UseCaseConfig) -> tuple[Search, list[dict]]:
    """One search of the panel under `cfg`, with every LightGBM fit FLAML made recorded: the
    rows it received in their order, its constraints with their method, and its declared
    categoricals."""
    train, X, encoder = data
    fits: list[dict] = []
    library_fit = lgb.LGBMClassifier.fit

    def recording_fit(
        self: lgb.LGBMClassifier, X_fit: pd.DataFrame, y_fit: np.ndarray, **arguments: object
    ) -> lgb.LGBMClassifier:
        """LightGBM's fit, recording what it received."""
        fits.append({
            "rows": X_fit.index.to_numpy(),
            "constraints": self.get_params().get("monotone_constraints"),
            "method": self.get_params().get("monotone_constraints_method"),
            "categoricals": arguments.get("categorical_feature"),
        })  # fmt: skip
        return library_fit(self, X_fit, y_fit, **arguments)

    folds = train[FOLD_COLUMNS[: cfg.training.fold_repeats]]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(lgb.LGBMClassifier, "fit", recording_fit)
        search = search_families(X, train["target"].to_numpy(), folds, encoder, MONOTONE, cfg, 1)
    return search, fits


@pytest.fixture(scope="module")
def searched(data: tuple, cfg: UseCaseConfig) -> tuple[Search, list[dict]]:
    """The panel's search under `cfg`, with its recorded fits."""
    return _recorded_search(data, cfg)


def test_the_budget_is_split_in_the_lists_order(variant: Callable[..., UseCaseConfig]) -> None:
    """62 trials over four families are 16, 16, 15, 15; `training.trials` replaces the split;
    a budget that leaves a family without a trial fails loud."""
    families = ["lgbm", "xgboost", "xgb_limitdepth", "catboost"]
    assert split_budget(variant(training={"max_iter": 62})) == dict(
        zip(families, [16, 16, 15, 15], strict=True)
    )
    counts = {"lgbm": 3, "xgboost": 1, "xgb_limitdepth": 7, "catboost": 2}
    assert split_budget(variant(training={"max_iter": 62, "trials": counts})) == counts
    with pytest.raises(ValueError, match="training.max_iter 3 leaves some of the 4 listed"):
        split_budget(variant(training={"max_iter": 3}))


def test_a_bad_space_or_budget_is_refused_before_any_work(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """`check_spaces` is what Training runs first, so a refused run takes no number: a budget
    below the number of families, and a misspelt parameter in a family's space, which LightGBM
    would ignore without a word."""
    check_spaces(variant(training={"max_iter": 8}))
    with pytest.raises(ValueError, match="leaves some of the 4 listed families without a trial"):
        check_spaces(variant(training={"max_iter": 3}))
    misspelt = {"lgbm": {"num_leafs": {"value": 8}}}
    with pytest.raises(ValueError, match=r"lgbm: the parameters \['num_leafs'\] are not taken"):
        check_spaces(variant(training={"search_space": misspelt}))


def test_a_constraint_method_in_the_space_reaches_the_trials_and_the_fits(
    data: tuple, variant: Callable[..., UseCaseConfig]
) -> None:
    """The one fixed name a config may set. With `intermediate` in the space, FLAML's trials
    and the parameters of every later fit both take it (the trials once ran `basic` while the
    kept model ran `intermediate`), and a trial logged with another value than the framework
    fits with is refused."""
    space = {"lgbm": {"monotone_constraints_method": {"value": "intermediate"}}}
    training = {"estimator_list": ["lgbm"], "max_iter": 2, "folds": FOLDS, "monotone": MONOTONE,
                "search_space": space}  # fmt: skip
    search, fits = _recorded_search(data, variant(training=training))
    assert {fit["method"] for fit in fits} == {"intermediate"}
    assert search.parameters["monotone_constraints_method"] == "intermediate"
    log, searched_names = search.logs["flaml_lgbm.log"], list(STARTS)
    constants = {k: v for k, v in search.parameters.items() if k not in [*STARTS, *NOT_CONSTANTS]}
    assert len(read_trials("lgbm", log, searched_names, constants)) == 2
    with pytest.raises(ValueError, match=r"trial 1 of lgbm was not fitted .* differ"):
        read_trials("lgbm", log, searched_names, {**constants, "reg_lambda": 1.0})


@pytest.mark.parametrize("family", list(RANGES))
def test_every_ranged_leaf_reaches_flaml_with_its_start(family: str, data: tuple) -> None:
    """A space without starts searches nothing (T39): every ranged leaf is a domain over its
    range, both ends included, with its start; a constant and a fixed parameter are plain
    values; the fit arguments, the thread count and CatBoost's categoricals are left out."""
    encoder = data[2]
    space = family_space(family, {})
    fixed = FAMILIES[family].fixed_params("binary", "log_loss", encoder, MONOTONE, SEED, 2, None)
    entries = build_search_space(space, fixed)
    for name, leaf in RANGES[family].items():
        domain = entries[name]["domain"]
        assert (domain.lower, domain.upper) == (leaf["low"], leaf["high"] + leaf["integer"])
        assert entries[name]["init_value"] == leaf["start"]
    constants = {name: leaf["value"] for name, leaf in space.items() if "value" in leaf}
    passed = {name: value for name, value in fixed.items() if name not in NOT_CONSTANTS}
    assert passed and not set(entries) & set(NOT_CONSTANTS)
    for name, value in {**constants, **passed}.items():
        assert entries[name] == {"domain": value}
    assert set(entries) == set(RANGES[family]) | set(constants) | set(passed)


def test_a_trial_budget_runs_that_many_trials_from_the_starts(
    searched: tuple[Search, list[dict]], cfg: UseCaseConfig
) -> None:
    """The trials table holds the budget's trials, numbered from 1, the first at the starts and
    improving; the parameters are the fixed ones with the best trial's values merged over them."""
    search, _ = searched
    trials = search.trials
    assert list(trials.columns) == TRIAL_COLUMNS and trials["trial"].tolist() == [1, 2, 3, 4, 5, 6]
    assert json.loads(trials["configuration"].iloc[0]) == STARTS
    assert trials["improving"].iloc[0] and trials["configuration"].nunique() == TRIALS
    best = trials.loc[trials["fold_loss"].idxmin()]
    assert trials.loc[trials["improving"], "fold_loss"].min() == best["fold_loss"]
    assert search.family == "lgbm" and list(search.logs) == ["flaml_lgbm.log"]
    assert search.spaces == {"lgbm": family_space("lgbm", {})}
    searched_values = json.loads(best["configuration"])
    assert {name: search.parameters[name] for name in STARTS} == searched_values
    assert search.parameters["monotone_constraints"] == "1,0,0,1,0"
    assert search.parameters["random_state"] == SEED and search.parameters["log_max_bin"] == 8


def test_every_trial_is_fitted_on_our_folds_unshuffled(
    searched: tuple[Search, list[dict]], data: tuple
) -> None:
    """FLAML fits a trial once per dealing and fold, on exactly the rows outside that fold in
    the frame's own order (T42: it permutes them unless the splitter says `shuffle = False`),
    so no client is on both sides of a fit. Its one fit on every row is its own refit of the
    best trial at the end, which cross-validation cannot switch off and Training never reads."""
    _, fits = searched
    train = data[0]
    splits = list(fold_splitter(train[FOLD_COLUMNS]).split())
    assert len(splits) == 2 * FOLDS and len(fits) == TRIALS * len(splits) + 1
    assert len(fits[-1]["rows"]) == len(train)
    for position, fit in enumerate(fits[:-1]):
        fitted, held = splits[position % len(splits)]
        assert np.array_equal(fit["rows"], fitted)
        assert not set(train["unit_id"].to_numpy()[fitted]) & set(train["unit_id"].to_numpy()[held])


def test_the_constraints_and_the_categoricals_reach_every_trial_fit(
    searched: tuple[Search, list[dict]],
) -> None:
    """A trial judged without the run's constraints, or with the region as a number, would be
    another model than the framework fits."""
    _, fits = searched
    assert {fit["constraints"] for fit in fits} == {"1,0,0,1,0"}
    assert all(fit["categoricals"] == ["region"] for fit in fits)


def test_the_best_trials_loss_is_the_frameworks_own_fold_loss(
    searched: tuple[Search, list[dict]], data: tuple
) -> None:
    """FLAML only searches: the framework's own fits at the best parameters, on the same
    splits, give the loss FLAML reported for that trial, so the model that is kept is the model
    that was judged."""
    search, _ = searched
    train, X, _ = data
    y = train["target"].to_numpy()
    losses = []
    for fitted, held in fold_splitter(train[FOLD_COLUMNS]).split():
        booster = FAMILIES["lgbm"].fit(X.iloc[fitted], y[fitted], search.parameters, "binary")
        margin = FAMILIES["lgbm"].predict(booster, X.iloc[held])
        losses.append(log_loss(y[held], expit(margin), labels=[0, 1]))
    assert np.mean(losses) == pytest.approx(search.trials["fold_loss"].min(), abs=1e-12)


def test_a_deviance_is_searched_through_a_custom_metric(
    data: tuple, variant: Callable[..., UseCaseConfig]
) -> None:
    """FLAML has no Tweedie deviance: the custom metric gives each trial the mean over the
    splits of the deviance at power 1.5 on the predicted mean, as the framework's own fits do."""
    train, X, encoder = data
    training = {"estimator_list": ["lgbm"], "max_iter": 3, "fold_repeats": 2, "folds": FOLDS,
                "objective": "tweedie", "monotone": MONOTONE}  # fmt: skip
    cfg = variant(**REGRESSION, decision={"metric": "tweedie_deviance"}, training=training)
    y = train["amount"].to_numpy()
    search = search_families(X, y, train[FOLD_COLUMNS], encoder, MONOTONE, cfg, 1)
    losses = []
    for fitted, held in fold_splitter(train[FOLD_COLUMNS]).split():
        booster = FAMILIES["lgbm"].fit(X.iloc[fitted], y[fitted], search.parameters, "regression")
        mean = np.exp(FAMILIES["lgbm"].predict(booster, X.iloc[held]))
        losses.append(mean_tweedie_deviance(y[held], mean, power=1.5))
    assert len(search.trials) == 3
    assert np.mean(losses) == pytest.approx(search.trials["fold_loss"].min(), abs=1e-12)


def test_a_kept_model_the_search_did_not_judge_is_refused(
    searched: tuple[Search, list[dict]],
) -> None:
    """The framework's fold models must give the best trial's loss. Another loss stops a run on
    a trial budget; under a time budget, where FLAML may cut a trial's trees at its deadline, it
    is the run's warning with both numbers."""
    search = searched[0]
    judged = search.trials["fold_loss"].min()
    assert check_judged_model(search, judged + 1e-10, timed=False) == []
    with pytest.raises(ValueError, match="judged another model than the one that would be kept"):
        check_judged_model(search, judged + 1e-3, timed=False)
    (warning,) = check_judged_model(search, judged + 1e-3, timed=True)
    assert f"{judged:.6f}" in warning and "training.time_budget_s" in warning


def test_a_time_budget_caps_the_search_without_promising_a_count(
    data: tuple, variant: Callable[..., UseCaseConfig]
) -> None:
    """`training.time_budget_s` reaches FLAML per family beside the trial budget: a generous one
    changes nothing but the promise, so the trials still start at the starts and none is asked
    for by count."""
    train, X, encoder = data
    training = {"estimator_list": ["lgbm"], "max_iter": 3, "folds": FOLDS, "time_budget_s": 600}
    search = search_families(
        X,
        train["target"].to_numpy(),
        train[["cv_fold"]],
        encoder,
        {},
        variant(training=training),
        1,
    )
    assert 1 <= len(search.trials) <= 3
    assert json.loads(search.trials["configuration"].iloc[0]) == STARTS


def test_a_fold_the_metric_is_not_defined_on_stops_the_search(
    data: tuple, variant: Callable[..., UseCaseConfig]
) -> None:
    """A validation fold without a positive has no AUC; FLAML then logs a NaN loss for every
    trial and raises nothing, so the search fails loud. A row without a fold is refused before
    any trial."""
    train, X, encoder = data
    y = train["target"].to_numpy()
    folds = train[["cv_fold"]].copy()
    folds.loc[(folds["cv_fold"] == 0) & (y == 1), "cv_fold"] = 1
    training = {"estimator_list": ["lgbm"], "max_iter": 2, "folds": FOLDS}
    cfg = variant(decision={"type": "ranking", "metric": "roc_auc"}, training=training)
    with pytest.warns(UserWarning), pytest.raises(ValueError, match="2 of 2 trials of lgbm"):
        search_families(X, y, folds, encoder, {}, cfg, 1)
    with pytest.raises(ValueError, match="have a null fold"):
        fold_splitter(train[["cv_fold"]].where(train["x2"] > -2))
    with pytest.raises(ValueError, match="must hold the same rows in the same order"):
        search_families(X, y, folds.iloc[::-1], encoder, {}, cfg, 1)


def test_check_search_refuses_a_search_that_did_not_run_as_declared(
    searched: tuple[Search, list[dict]],
) -> None:
    """The real search passes; a non-finite loss, a trial count off the budget, a first trial
    away from the starts and trials that never moved each fail loud."""
    trials = searched[0].trials
    check_search("lgbm", trials, STARTS, TRIALS)
    check_search("lgbm", trials.head(3), STARTS, None)  # a time budget promises no count
    for loss in (np.nan, np.inf):
        broken = trials.assign(fold_loss=trials["fold_loss"].where(trials["trial"] != 2, loss))
        with pytest.raises(ValueError, match="1 of 6 trials of lgbm have a non-finite fold loss"):
            check_search("lgbm", broken, STARTS, TRIALS)
    with pytest.raises(ValueError, match="ran 6 trials on a budget of 8"):
        check_search("lgbm", trials, STARTS, 8)
    with pytest.raises(ValueError, match="trial 1 of lgbm is not at the starts: {'num_leaves': 4}"):
        check_search("lgbm", trials, {**STARTS, "num_leaves": 31}, TRIALS)
    stuck = trials.assign(configuration=trials["configuration"].iloc[0])
    with pytest.raises(ValueError, match="ran one configuration: the search did not move"):
        check_search("lgbm", stuck, STARTS, TRIALS)
    with pytest.raises(ValueError, match="logged no trial"):
        check_search("lgbm", trials.head(0), STARTS, TRIALS)
