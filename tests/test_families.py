"""The four model families on a small constructed frame (no Spark): what each one pins, measured
on the pinned library versions. The frame's first feature and one after its unordered
categorical act in a U shape, so a constraint lost from the first position (LightGBM reads a
bracketed string's first entry as 0) or a vector in the wrong positions shows in the margins.
"""

import hashlib
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest
import xgboost as xgb

# flaml needs core_modelling's np.NaN shim, which conftest's imports apply before this module
from flaml.automl.model import (
    CatBoostEstimator,
    LGBMEstimator,
    XGBoostLimitDepthEstimator,
    XGBoostSklearnEstimator,
)

from core_modelling.model.catboost_family import RUN_METADATA_KEYS
from core_modelling.model.families import FAMILIES, check_monotone, check_params, check_searched
from core_modelling.model.family_inputs import check_order

ROWS = 2500
TREES = 30
SEED = 7
SEARCHED = {  # one small configuration per family, in FLAML's own parameter names
    "lgbm": {"n_estimators": TREES, "num_leaves": 8, "log_max_bin": 8, "learning_rate": 0.1},
    "xgboost": {"n_estimators": TREES, "max_leaves": 8, "learning_rate": 0.1},
    "xgb_limitdepth": {"n_estimators": TREES, "max_depth": 4, "learning_rate": 0.1},
    "catboost": {"n_estimators": TREES, "learning_rate": 0.1},
}
TASKS = ("binary", "regression")
DEFAULT_OBJECTIVES = {"binary": "log_loss", "regression": "squared_error"}
LIBRARY_NAMES = {  # each library's names for the objective and the seed, with their config field
    "lgbm": {"objective": "training.objective", "random_state": "training.seed"},
    "xgboost": {"objective": "training.objective", "random_state": "training.seed"},
    "xgb_limitdepth": {"objective": "training.objective", "random_state": "training.seed"},
    "catboost": {"loss_function": "training.objective", "random_seed": "training.seed"},
}
XGBOOST_WEIGHTS = ("scale_pos_weight", "class_weight")
CLASS_WEIGHTS = {  # each library's class-weight names, aliases included
    "lgbm": ("class_weight", "is_unbalance", "unbalance", "unbalanced_sets", "scale_pos_weight"),
    "xgboost": XGBOOST_WEIGHTS,
    "xgb_limitdepth": XGBOOST_WEIGHTS,
    "catboost": ("class_weights", "auto_class_weights", "scale_pos_weight"),
}
FLAML_LEARNERS = {
    "lgbm": LGBMEstimator,
    "xgboost": XGBoostSklearnEstimator,
    "xgb_limitdepth": XGBoostLimitDepthEstimator,
    "catboost": CatBoostEstimator,
}
REGRESSION_OBJECTIVES = ("squared_error", "tweedie", "poisson", "absolute_error", "huber")
LOG_LINK = ("tweedie", "poisson")


def _encoder(unordered: str = "native") -> dict:
    """The test frame's encoder, built by hand in the encoder's plain-data shape."""
    return {
        "schema_version": 1,
        "unordered": unordered,
        "min_level_client_count": 50,
        "features": [
            {"name": "u", "kind": "numeric"},
            {"name": "channel", "kind": "unordered", "levels": ["branch", "online"], "pooled": []},
            {"name": "rating", "kind": "ordered", "levels": ["C", "B", "A"]},
            {"name": "income", "kind": "numeric"},
            {"name": "w", "kind": "numeric"},
            {"name": "age", "kind": "numeric"},
        ],
    }


def _frame(unordered: str = "native") -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """An encoded frame of `ROWS` rows, a binary target and an amount with 20% zeros. Income
    and rating raise both, age lowers them, `u` and `w` act in a U shape, channel's code 2
    raises the rate. Channel holds 0 (null), 1 and 2 (the kept levels); 3, `__other__`, never
    occurs."""
    rng = np.random.default_rng(0)
    income = np.where(rng.random(ROWS) < 0.05, np.nan, rng.normal(size=ROWS))
    channel = rng.integers(0, 3, ROWS)
    rating = np.where(rng.random(ROWS) < 0.05, np.nan, rng.integers(0, 3, ROWS))
    u, w, age = rng.uniform(-2, 2, ROWS), rng.uniform(-2, 2, ROWS), rng.normal(size=ROWS)
    X = pd.DataFrame(
        {
            "u": u,
            "channel": channel.astype("int64" if unordered == "native" else "float64"),
            "rating": rating,
            "income": income,
            "w": w,
            "age": age,
        }
    )
    signal = np.nan_to_num(income) + 0.4 * np.nan_to_num(rating) + 0.8 * (channel == 2)
    signal = signal + 1.2 * (u**2 + w**2) - 3.5 - 0.5 * age
    y = (rng.random(ROWS) < 1 / (1 + np.exp(-signal))).astype(np.int64)
    amount = np.where(rng.random(ROWS) < 0.2, 0.0, np.exp(1 + 0.3 * signal) * rng.gamma(2, 1, ROWS))
    return X, y, amount


def _fit(
    family: str,
    task: str = "binary",
    objective: str | None = None,
    monotone: dict[str, str] | None = None,
    threads: int = 1,
    unordered: str = "native",
    tweedie_variance_power: float | None = 1.5,
) -> object:
    """A booster fitted as Training will fit one: the searched configuration merged over the
    family's fixed parameters, the task's default objective unless one is given."""
    X, y, amount = _frame(unordered)
    encoder = _encoder(unordered)
    fixed = FAMILIES[family].fixed_params(
        task,
        objective or DEFAULT_OBJECTIVES[task],
        encoder,
        monotone or {},
        SEED,
        threads,
        tweedie_variance_power,
    )
    target = y if task == "binary" else amount
    return FAMILIES[family].fit(X, target, {**fixed, **SEARCHED[family]}, task)


def _reloaded(family: str, booster: object, folder: str) -> object:
    """`booster` saved to its native file in `folder` and loaded from the file's bytes, as the
    bundle and scoring in Spark load it."""
    path = Path(folder) / FAMILIES[family].file_name
    FAMILIES[family].save(booster, str(path))
    return FAMILIES[family].load(path.read_bytes())


ROUND_TRIPS = [(family, task, "native") for family in FAMILIES for task in TASKS] + [
    (family, "binary", "codes") for family in FAMILIES
]


@pytest.mark.parametrize(("family", "task", "unordered"), ROUND_TRIPS)
def test_a_reloaded_booster_scores_and_describes_the_same(
    family: str, task: str, unordered: str, tmp_path: Path
) -> None:
    """The bundle holds the native file only (D-051): what it reads back must give identical
    float64 margins and the same plain-data description, declared categoricals or codes."""
    X, _, _ = _frame(unordered)
    booster = _fit(family, task, unordered=unordered)
    loaded = _reloaded(family, booster, str(tmp_path))
    margin = FAMILIES[family].predict(loaded, X)
    assert margin.dtype == np.float64
    assert np.array_equal(margin, FAMILIES[family].predict(booster, X))
    contributions = FAMILIES[family].contributions
    assert np.array_equal(contributions(loaded, X), contributions(booster, X))
    if family.startswith("xgb"):  # a buffer keeps the names, the types and every round
        assert (loaded.feature_names, loaded.feature_types) == (
            booster.feature_names,
            booster.feature_types,
        )
        assert loaded.num_boosted_rounds() == TREES
    description = FAMILIES[family].describe(loaded)
    assert description == FAMILIES[family].describe(booster)
    assert description["features"] == list(X.columns)
    assert description["trees"] == TREES
    assert bool(description["parameters"]) == (family != "catboost")  # CatBoost's are deleted
    json.dumps(description, allow_nan=False)


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("unordered", ["native", "codes"])
def test_native_declares_the_unordered_feature_and_codes_declares_none(
    family: str, unordered: str
) -> None:
    """Each library is told in its own way (Q609), and a declaration in the wrong place is
    lost or refused, so the booster itself must hold channel as its only categorical under
    `native` and none under `codes`."""
    booster = _fit(family, unordered=unordered)
    expected = ["channel"] if unordered == "native" else []
    assert _library_categoricals(family, booster) == expected


def _library_categoricals(family: str, booster: object) -> list[str]:
    """The features the booster treats as categorical, read from the library itself."""
    if family == "lgbm":  # a categorical's feature info lists its categories, a numeric's none
        infos = booster.dump_model()["feature_infos"]
        return [name for name, info in infos.items() if info["values"]]
    if family == "catboost":
        return [booster.feature_names_[index] for index in booster.get_cat_feature_indices()]
    kinds = zip(booster.feature_names, booster.feature_types, strict=True)
    return [name for name, kind in kinds if kind == "c"]


@pytest.mark.parametrize("family", FAMILIES)
def test_the_frame_is_matched_to_the_booster_by_name(family: str) -> None:
    """LightGBM and CatBoost read columns by position: a shuffled frame must score the same,
    and a frame without a feature or with an extra column must fail rather than score."""
    X, _, _ = _frame()
    booster = _fit(family)
    predict = FAMILIES[family].predict
    assert np.array_equal(predict(booster, X[X.columns[::-1]]), predict(booster, X))
    with pytest.raises(ValueError, match=r"missing \['age'\]"):
        predict(booster, X.drop(columns="age"))
    with pytest.raises(ValueError, match=r"extra \['spare'\]"):
        predict(booster, X.assign(spare=1.0))


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("task", TASKS)
def test_contributions_sum_to_the_margin(family: str, task: str, tmp_path: Path) -> None:
    """The explanation views read the libraries' own contributions (no `shap`): on a reloaded
    booster with a declared categorical, one column per feature and the base value last, each
    row summing to its margin (float32 rounding for XGBoost)."""
    X, _, _ = _frame()
    loaded = _reloaded(family, _fit(family, task), str(tmp_path))
    values = FAMILIES[family].contributions(loaded, X)
    assert values.shape == (ROWS, X.shape[1] + 1)
    margin = FAMILIES[family].predict(loaded, X)
    np.testing.assert_allclose(values.sum(axis=1), margin, rtol=1e-5, atol=1e-5)


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("task", TASKS)
def test_fits_of_one_configuration_give_one_file_hash(
    family: str, task: str, tmp_path: Path
) -> None:
    """`model_hash` is taken over the file (Q619), one per model on a laptop and inside the bank:
    fits of one configuration, repeated and at another thread count, must write the same bytes
    (CatBoost's run metadata and LightGBM's thread line left out)."""
    hashes = set()
    for run, threads in enumerate((1, 1, 2)):
        path = tmp_path / f"{run}_{FAMILIES[family].file_name}"
        FAMILIES[family].save(_fit(family, task, threads=threads), str(path))
        hashes.add(hashlib.sha256(path.read_bytes()).hexdigest())
    assert len(hashes) == 1


@pytest.mark.parametrize("family", FAMILIES)
def test_one_and_two_threads_give_the_same_margins(family: str) -> None:
    """The thread count is a run setting, not part of the model (Q608)."""
    X, _, _ = _frame()
    one, two = (FAMILIES[family].predict(_fit(family, threads=threads), X) for threads in (1, 2))
    assert np.array_equal(one, two)


@pytest.mark.parametrize("family", FAMILIES)
def test_an_unseen_code_scores(family: str) -> None:
    """Code 3 (`__other__`) never occurs in train and code 7 lies beyond every code: each family
    scores and explains both (a "none of these" branch, or CatBoost's prior) instead of failing."""
    X, _, _ = _frame()
    booster = _fit(family)
    unseen = X.head(4).assign(channel=[3, 7, 3, 7])
    margin = FAMILIES[family].predict(booster, unseen)
    assert np.isfinite(margin).all()
    values = FAMILIES[family].contributions(booster, unseen)
    np.testing.assert_allclose(values.sum(axis=1), margin, rtol=1e-5, atol=1e-5)


@pytest.mark.parametrize("family", FAMILIES)
def test_a_constraint_holds_and_a_broken_one_is_caught(family: str) -> None:
    """`u` (the first feature) and `w` (after the categorical) act in a U shape, so a model
    fitted without constraints breaks `increasing` on both and `check_monotone` must say so;
    fitted with them, a vector that lost its first entry or sat in the wrong positions would
    still break one, so the model must follow all four on the grid."""
    X, _, _ = _frame()
    monotone = {"u": "increasing", "rating": "increasing", "w": "increasing", "age": "decreasing"}
    check_monotone(family, _fit(family, monotone=monotone), X, monotone)
    for name in ("u", "w"):
        with pytest.raises(ValueError, match=f"^{family}: .* increasing constraint on '{name}'"):
            check_monotone(family, _fit(family), X, {name: "increasing"})


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize(
    ("monotone", "message"),
    [({"channel": "increasing"}, "an unordered categorical"), ({"incme": "up"}, "not a model")],
)
def test_a_constraint_on_an_unordered_or_unknown_feature_is_refused(
    family: str, monotone: dict[str, str], message: str
) -> None:
    """LightGBM aborts the process on a constrained categorical and XGBoost ignores it (Q650);
    a misspelt name would constrain nothing. Both fail before any library is called, naming the
    entry (both XGBoost entries share one module)."""
    named = "xgboost / xgb_limitdepth" if family.startswith("xgb") else family
    with pytest.raises(ValueError, match=f"^{named}: .*{message}"):
        FAMILIES[family].fixed_params("binary", "log_loss", _encoder(), monotone, SEED, 1, None)


@pytest.mark.parametrize("family", FAMILIES)
def test_fixed_params_refuses_another_binary_objective_and_an_unknown_kind(family: str) -> None:
    """Binary trains the log loss only, so another name is a config mistake rather than a
    choice to ignore; an encoder kind this version cannot read must not pass as numeric."""
    with pytest.raises(ValueError, match="binary takes the objectives"):
        FAMILIES[family].fixed_params("binary", "tweedie", _encoder(), {}, SEED, 1, None)
    encoder = _encoder()
    encoder["features"][0]["kind"] = "nominal"
    with pytest.raises(ValueError, match="unknown kinds"):
        FAMILIES[family].fixed_params("binary", "log_loss", encoder, {}, SEED, 1, None)


@pytest.mark.parametrize("family", FAMILIES)
def test_a_misspelt_parameter_is_refused(family: str) -> None:
    """LightGBM and XGBoost run silent, so a misspelt name would train on the library default
    without a word: the search's check and `fit` both refuse it, naming the key."""
    X, y, _ = _frame()
    fixed = FAMILIES[family].fixed_params("binary", "log_loss", _encoder(), {}, SEED, 1, None)
    misspelt = {**fixed, **SEARCHED[family], "learning_rat": 0.1}
    with pytest.raises(ValueError, match=rf"^{family}: the parameters \['learning_rat'\]"):
        check_params(family, misspelt)
    named = "xgboost / xgb_limitdepth" if family.startswith("xgb") else family
    with pytest.raises(ValueError, match=rf"^{named}: the parameters \['learning_rat'\]"):
        FAMILIES[family].fit(X, y, misspelt, "binary")


@pytest.mark.parametrize("family", FAMILIES)
def test_fit_refuses_every_class_weight_name(family: str) -> None:
    """A class weight changes the class balance without the calibration knowing, and every
    score comes out skewed (A4): `fit` refuses each name and its aliases, saying why."""
    X, y, _ = _frame()
    params = {
        **FAMILIES[family].fixed_params("binary", "log_loss", _encoder(), {}, SEED, 1, None),
        **SEARCHED[family],
    }
    for name in CLASS_WEIGHTS[family]:
        with pytest.raises(ValueError, match="change the class balance"):
            FAMILIES[family].fit(X, y, {**params, name: True}, "binary")


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("task", TASKS)
def test_every_parameter_flaml_or_fixed_params_passes_is_allowed(family: str, task: str) -> None:
    """The allowed names must not refuse a search FLAML would run: every key of FLAML 2.7's
    own space for the learner, and every key `fixed_params` returns for each objective."""
    space = FLAML_LEARNERS[family].search_space(data_size=(ROWS, 6), task=task)
    objectives = ("log_loss",) if task == "binary" else REGRESSION_OBJECTIVES
    for objective in objectives:
        fixed = FAMILIES[family].fixed_params(
            task, objective, _encoder(), {"u": "increasing"}, SEED, 1, 1.5
        )
        check_params(family, {**fixed, **space})
    check_searched(family, space)


def test_a_frame_out_of_the_encoders_order_is_refused() -> None:
    """`fixed_params` builds positional vectors in the encoder's order: fitted on reversed
    columns, a constraint would land on another feature without a word."""
    X, _, _ = _frame()
    check_order(X, _encoder())
    with pytest.raises(ValueError, match="position 0 holds 'age' where the encoder has 'u'"):
        check_order(X[X.columns[::-1]], _encoder())


def test_xgboost_without_a_size_limit_is_refused() -> None:
    """An `xgb_limitdepth` configuration that lost its depth would grow unlimited leaf-wise
    trees."""
    X, y, _ = _frame()
    fixed = FAMILIES["xgb_limitdepth"].fixed_params(
        "binary", "log_loss", _encoder(), {}, SEED, 1, None
    )
    with pytest.raises(ValueError, match="neither a positive max_depth nor max_leaves"):
        FAMILIES["xgb_limitdepth"].fit(X, y, {**fixed, "n_estimators": TREES}, "binary")


@pytest.mark.parametrize("family", FAMILIES)
def test_the_search_may_not_set_what_fixed_params_owns(family: str) -> None:
    """A searched objective trains another link than the bundle records, a searched seed
    replaces `training.seed`, a searched constraint replaces `training.monotone`: each is
    refused, naming the field that sets it. LightGBM's constraint method stays searchable."""
    check_searched(family, SEARCHED[family])
    owned = {**LIBRARY_NAMES[family], "monotone_constraints": "training.monotone"}
    for name, field in owned.items():
        with pytest.raises(ValueError, match=f"`{name}` comes from {field}"):
            check_searched(family, {**SEARCHED[family], name: "poisson"})
    if family == "lgbm":
        check_searched(family, {"monotone_constraints_method": "intermediate"})


@pytest.mark.parametrize("family", FAMILIES)
def test_owned_params_name_every_fixed_parameter(family: str) -> None:
    """A name `fixed_params` returns but `OWNED_PARAMS` lacks could be overridden by the search
    without a word, so the two must list the same names (LightGBM's constraint method aside)."""
    returned = set()
    for task in TASKS:
        for objective in ("log_loss",) if task == "binary" else REGRESSION_OBJECTIVES:
            returned |= set(
                FAMILIES[family].fixed_params(
                    task, objective, _encoder(), {"u": "increasing"}, SEED, 1, 1.5
                )
            )
    assert returned - {"monotone_constraints_method"} == set(FAMILIES[family].owned_params)


def test_xgboost_refuses_a_missing_value_marker() -> None:
    """`missing` would make the fit read a value as null that scoring reads as a value."""
    for family in ("xgboost", "xgb_limitdepth"):
        with pytest.raises(ValueError, match=r"\['missing'\]"):
            check_params(family, {"missing": 0})


@pytest.mark.parametrize("family", FAMILIES)
def test_fit_refuses_a_vector_of_another_length(family: str) -> None:
    """XGBoost and CatBoost take a constraint vector shorter than the frame without a word,
    so `fit` checks every positional vector against the frame it is given."""
    X, y, _ = _frame()
    fixed = FAMILIES[family].fixed_params(
        "binary", "log_loss", _encoder(), {"u": "increasing"}, SEED, 1, None
    )
    with pytest.raises(ValueError, match="holds 6 entries for a frame of 4 columns"):
        FAMILIES[family].fit(
            X.drop(columns=["w", "age"]), y, {**fixed, **SEARCHED[family]}, "binary"
        )


def test_check_monotone_refuses_an_all_null_feature() -> None:
    """A constraint that cannot be swept must say so rather than fail on an empty grid."""
    X, _, _ = _frame()
    with pytest.raises(ValueError, match="'u' is null on every row given"):
        check_monotone("lgbm", _fit("lgbm"), X.assign(u=np.nan), {"u": "increasing"})


@pytest.mark.parametrize("family", FAMILIES)
def test_the_tweedie_power_reaches_the_booster(family: str, tmp_path: Path) -> None:
    """`training.tweedie_variance_power` reaches each library in its own words, and a power
    missing or outside (1, 2) is refused before any library sees it (no silent 1.5)."""
    booster = _fit(family, "regression", "tweedie", tweedie_variance_power=1.2)
    power = _library_tweedie_power(family, booster, str(tmp_path / "model.txt"))
    assert power == pytest.approx(1.2, abs=1e-6)
    for wrong in (2.0, None):
        with pytest.raises(ValueError, match=r"needs `training.tweedie_variance_power` in"):
            FAMILIES[family].fixed_params("regression", "tweedie", _encoder(), {}, SEED, 1, wrong)


def _library_tweedie_power(family: str, booster: object, path: str) -> float:
    """The Tweedie variance power the booster trained with, read from the library itself
    (LightGBM's through its own file at `path`; XGBoost keeps it as float32)."""
    if family == "lgbm":
        booster.save_model(path)
        return lgb.Booster(model_file=path).params["tweedie_variance_power"]
    if family == "catboost":
        return float(booster.get_all_params()["loss_function"].split("=")[1])
    objective = json.loads(booster.save_config())["learner"]["objective"]
    return float(objective["tweedie_regression_param"]["tweedie_variance_power"])


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("objective", REGRESSION_OBJECTIVES)
def test_the_margin_is_the_libraries_raw_output(family: str, objective: str) -> None:
    """Every regression objective of Q639 trains under its library name, and the margin is the
    library's raw output: its exponential is the library's own prediction under a log link
    (A42), the prediction itself otherwise."""
    X, _, _ = _frame()
    booster = _fit(family, "regression", objective)
    margin = FAMILIES[family].predict(booster, X)
    expected = _library_prediction(family, booster, X)
    np.testing.assert_allclose(
        np.exp(margin) if objective in LOG_LINK else margin, expected, rtol=1e-5
    )


def _library_prediction(family: str, booster: object, X: pd.DataFrame) -> np.ndarray:
    """The library's own prediction on the target's scale for the frame it was fitted on,
    computed without the family's code."""
    if family == "lgbm":
        return booster.predict(X.to_numpy(np.float64))
    if family == "catboost":
        return booster.predict(X)
    matrix = xgb.DMatrix(X, feature_types=booster.feature_types, enable_categorical=True)
    return booster.predict(matrix).astype(np.float64)


def test_catboost_writes_no_file_and_needs_no_run_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CatBoost writes `catboost_info/` into the working directory unless told not to (T5, A7),
    and its saved file lacks the run-specific metadata, which scoring must not need; saving
    leaves the fitted model whole."""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    X, _, _ = _frame()
    family = FAMILIES["catboost"]
    booster = _fit("catboost")
    loaded = _reloaded("catboost", booster, str(tmp_path))
    family.contributions(loaded, X)
    assert np.array_equal(family.predict(loaded, X), family.predict(booster, X))
    assert not set(RUN_METADATA_KEYS) & set(loaded.get_metadata().keys())
    assert set(RUN_METADATA_KEYS) <= set(booster.get_metadata().keys())
    assert list(work.iterdir()) == []


def test_catboost_takes_whole_codes_that_arrive_as_floats() -> None:
    """A code column can arrive as float64 (pandas holds a nullable integer column from Spark
    as float64, `environment.md`): CatBoost refuses float codes, so the family casts whole
    numbers and refuses anything else."""
    X, _, _ = _frame()
    booster = _fit("catboost")
    predict = FAMILIES["catboost"].predict
    assert np.array_equal(predict(booster, X.astype({"channel": "float64"})), predict(booster, X))
    with pytest.raises(ValueError, match="whole-number codes"):
        predict(booster, X.assign(channel=X["channel"] + 0.5))
