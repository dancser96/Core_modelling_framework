"""Training's calibration on simulated margins with a known answer (no Spark).

An error here makes every score silently wrong, so each number is checked against what the
simulation planted or against an independent maximum-likelihood fit: Platt recovers a known
pair and leaves a calibrated margin alone, beta drops a negative term and refits, the offset
follows the method of sampling, the level factor's interval is a client bootstrap that a rerun
draws again and that warns when a few rows decide the level, every allowed method of each task
gives a calibration the bundle accepts, and an anti-predictive model stops Training. Training's
own step that fits the fold models and calibrates is run on a small frame too: its calibration
is the fit on the fold models' out-of-fold margins of the train rows, never on in-sample ones.
"""

import json
from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest
from conftest import REGRESSION
from scipy.optimize import minimize
from scipy.special import expit, log_expit, logit

from core_modelling.config import UseCaseConfig
from core_modelling.config.schema import TASK_CHOICES
from core_modelling.dataset import Frames
from core_modelling.model.calibration import check_calibration, check_order_kept
from core_modelling.model.families import FAMILIES
from core_modelling.run_artifacts import CALIBRATION_COLUMNS
from core_modelling.statistics.calibration import (
    UNPENALISED,
    _client_weights,
    _half_total_rows,
    fit_beta,
    fit_platt,
    level_factor,
    prior_shift_offset,
)
from core_modelling.statistics.losses import metric_loss
from core_modelling.training.calibrate import calibrate
from core_modelling.training.fold_models import (
    FOLD_COLUMN,
    every_dealing_loss,
    fit_final_model,
    fit_fold_models,
)
from core_modelling.training.run import Opened, _fit_out_of_fold
from core_modelling.training.search import Search
from core_modelling.training.train_data import TrainData

ROWS = 20_000
ROWS_PER_CLIENT = 4
NO_SAMPLING = {"method": None}
# A LightGBM that overfits 1,200 rows: deep trees on few rows each, at a high rate
OVERFIT = {"n_estimators": 60, "num_leaves": 16, "learning_rate": 0.2, "min_child_samples": 5}


def _binary_rows(a: float, b: float, seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`ROWS` margins around a 15% rate, labels drawn at `sigmoid(a·m + b)`, and their clients."""
    rng = np.random.default_rng(seed)
    margin = rng.normal(-2.0, 1.5, ROWS)
    y = (rng.random(ROWS) < expit(a * margin + b)).astype(np.int64)
    return margin, y, np.arange(ROWS) // ROWS_PER_CLIENT


def _amounts(spikes: int = 0, seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`ROWS` positive predictions, a target 1.1 times their level with gamma noise, and their
    clients; `spikes` rows carry amounts that dwarf the rest of the total."""
    rng = np.random.default_rng(seed)
    predicted = rng.gamma(2.0, 50.0, ROWS)
    y = 1.1 * predicted * rng.gamma(4.0, 0.25, ROWS)
    y[:spikes] = 2.0 * y.sum()
    return predicted, y, np.arange(ROWS) // ROWS_PER_CLIENT


def _maximum_likelihood(features: np.ndarray, y: np.ndarray) -> np.ndarray:
    """The logistic regression's coefficients, then its intercept, by scipy's BFGS on the
    log-likelihood with its gradient: an oracle independent of scikit-learn."""
    design = np.column_stack([features, np.ones(len(y))])

    def loss(theta: np.ndarray) -> float:
        """The negative log-likelihood."""
        z = design @ theta
        return float(np.sum(np.logaddexp(0.0, z) - y * z))

    def gradient(theta: np.ndarray) -> np.ndarray:
        """Its gradient."""
        return design.T @ (expit(design @ theta) - y)

    start = np.zeros(design.shape[1])
    return minimize(loss, start, jac=gradient, method="BFGS", options={"gtol": 1e-9}).x


def _config(
    variant: Callable[..., UseCaseConfig], task: str, objective: str, method: str
) -> UseCaseConfig:
    """The skeleton's config (binary) or its regression variant, at `objective` and `method`."""
    sections = REGRESSION if task == "regression" else {}
    training = {"objective": objective, "calibration": {"method": method}}
    return variant(**sections, training=training)


def test_platt_recovers_a_known_pair_and_leaves_a_calibrated_margin_alone() -> None:
    """Simulated at a = 0.8, b = −0.3, the fit lands within sampling error of the pair and on
    the maximum likelihood itself; on calibrated margins it is a ≈ 1, b ≈ 0, and beta ≈
    (1, 1, 0), since sigmoid(ln p − ln(1 − p)) = p."""
    margin, y, _ = _binary_rows(0.8, -0.3)
    fitted = fit_platt(margin, y)
    assert fitted == pytest.approx({"a": 0.8, "b": -0.3}, abs=0.05)
    oracle = _maximum_likelihood(margin[:, None], y)
    assert [fitted["a"], fitted["b"]] == pytest.approx(oracle, abs=1e-6)
    margin, y, _ = _binary_rows(1.0, 0.0, seed=1)
    assert fit_platt(margin, y) == pytest.approx({"a": 1.0, "b": 0.0}, abs=0.05)
    assert fit_beta(margin, y) == pytest.approx({"a": 1.0, "b": 1.0, "c": 0.0}, abs=0.1)


def test_separating_or_unconverged_margins_fail_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    """Margins that separate the labels have no maximum-likelihood fit (the solver would return
    a slope of 44 without a word), and a solver that stops early returns its last step: both
    must stop, naming the method and the rows, not the solver's internals."""
    separated = (np.arange(10.0), (np.arange(10) > 4).astype(np.int64))
    for fit in (fit_platt, fit_beta):
        with pytest.raises(ValueError, match="separate the labels"):
            fit(*separated)
    margin, y, _ = _binary_rows(0.8, -0.3)
    monkeypatch.setitem(UNPENALISED, "max_iter", 1)
    with pytest.raises(ValueError, match="platt calibration did not converge on 20,000 rows"):
        fit_platt(margin, y)


@pytest.mark.parametrize(("a", "b", "dropped"), [(-0.5, 1.5, "a"), (1.5, -0.5, "b")])
def test_beta_refits_without_a_negative_term(a: float, b: float, dropped: str) -> None:
    """A planted map that falls over part of the range gives a negative coefficient: that
    term is set to 0 and the other two are the maximum likelihood without it, so the map
    stays increasing."""
    rng = np.random.default_rng(2)
    margin = rng.normal(-1.0, 2.0, ROWS)
    logs = np.column_stack([log_expit(margin), -log_expit(-margin)])  # ln(p), −ln(1 − p)
    y = (rng.random(ROWS) < expit(logs @ [a, b] + 0.2)).astype(np.int64)
    full = _maximum_likelihood(logs, y)
    assert full[["a", "b"].index(dropped)] < 0  # the planted term does come out negative
    fitted = fit_beta(margin, y)
    assert fitted[dropped] == 0.0
    kept = "b" if dropped == "a" else "a"
    oracle = _maximum_likelihood(logs[:, [["a", "b"].index(kept)]], y)
    assert [fitted[kept], fitted["c"]] == pytest.approx(oracle, abs=1e-6)


def test_the_offset_follows_the_method_of_sampling(cc_config: UseCaseConfig) -> None:
    """Zero without sampling and under `client_sample` whatever the record's two rates (they
    differ by noise); `logit(true) − logit(sampled)` under `negative_downsampling`, which is
    ln(keep fraction) at the expected sampled rate. The log loss stays on the margins as
    trained, without the offset."""
    margin, y, clients = _binary_rows(1.0, 0.0)
    true_rate, keep = 0.01, 0.1
    sampled_rate = true_rate / (true_rate + keep * (1 - true_rate))
    records = {
        "none": NO_SAMPLING,
        "client": {"method": "client_sample", "share": 0.5, "true_rate": 0.010,
                   "sampled_rate": 0.013},
        "negative": {"method": "negative_downsampling", "keep_fraction": keep,
                     "true_rate": true_rate, "sampled_rate": sampled_rate},
    }  # fmt: skip
    results = {
        name: calibrate(margin, y, clients, cc_config, record) for name, record in records.items()
    }
    assert results["none"][0]["offset"] == 0.0
    assert results["client"][0]["offset"] == 0.0
    assert results["negative"][0]["offset"] == pytest.approx(np.log(keep), rel=1e-12)
    assert prior_shift_offset(0.02, 0.2) == pytest.approx(logit(0.02) - logit(0.2), rel=1e-12)
    table = results["negative"][1]
    assert table["offset"].tolist() == [results["negative"][0]["offset"]] * 3
    assert table["sampled_rate"].tolist() == [sampled_rate] * 3
    none_loss = table.loc[table["method"] == "none", "oof_loss"].item()
    assert none_loss == metric_loss("log_loss", y, expit(margin))
    assert results["none"][1]["true_rate"].isna().all()
    with pytest.raises(ValueError, match="strictly between 0 and 1"):
        prior_shift_offset(0.0, 0.2)


def test_half_total_rows_counts_the_largest_rows_first() -> None:
    """Half of 20 is reached by the 10 alone; half of 10 needs two of the 3s; a total that is
    not positive has no half."""
    assert _half_total_rows(np.array([1.0, 10.0, 1.0, 1.0, 1.0, 1.0, 5.0])) == 1
    assert _half_total_rows(np.array([3.0, 1.0, 3.0, 3.0])) == 2
    assert _half_total_rows(np.array([-2.0, 1.0])) is None


def test_a_level_factor_on_a_spread_target_is_tight_and_quiet(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """The planted level of 1.1 is recovered, its interval holds it within ±5% and no warning
    is raised; `none` keeps a factor of 1 in the bundle while the table shows the factor."""
    predicted, y, clients = _amounts()
    level = level_factor(predicted, y, clients)
    assert level["factor"] == pytest.approx(y.sum() / predicted.sum(), rel=1e-12)
    assert level["factor"] == pytest.approx(1.1, abs=0.02)
    assert 0.95 * level["factor"] < level["low"] < level["factor"] < level["high"]
    assert level["high"] < 1.05 * level["factor"]
    cfg = _config(variant, "regression", "squared_error", "none")
    calibration, table, warnings = calibrate(predicted, y, clients, cfg, NO_SAMPLING)
    assert warnings == [] and calibration["parameters"] == {}
    assert table["factor"].tolist() == [level["factor"]] * 2
    assert table["oof_loss"].isna().all()


def test_a_level_decided_by_a_few_rows_warns(variant: Callable[..., UseCaseConfig]) -> None:
    """Three rows holding most of the total widen the interval past ±5%: the warning says so,
    the method stays `mean` and the factor is not winsorised."""
    predicted, y, clients = _amounts(spikes=3)
    cfg = _config(variant, "regression", "tweedie", "mean")
    calibration, table, warnings = calibrate(np.log(predicted), y, clients, cfg, NO_SAMPLING)
    assert len(warnings) == 1 and "decided by a few rows" in warnings[0]
    assert calibration["method"] == "mean"
    assert calibration["parameters"]["factor"] == pytest.approx(y.sum() / predicted.sum())
    assert table["half_total_rows"].tolist() == [2, 2]


def test_a_clients_rows_share_one_weight_and_a_rerun_draws_the_same_interval() -> None:
    """A client's rows move together in each replicate and its weight does not depend on the
    other clients, so a rerun, on any rows, gives the same interval; the weights are Poisson(1),
    and the interval is the one the rows give weighted row by row with their client's weight."""
    clients = pd.Series(["c1", "c1", "c2", "c3", "c3", "c3"])
    for replicate in range(20):
        weights = _client_weights(clients, replicate)
        assert weights[0] == weights[1] and weights[3] == weights[4] == weights[5]
        assert _client_weights(pd.Series(["c9", "c3"]), replicate)[1] == weights[3]
    many = _client_weights(pd.Series(np.arange(50_000)).astype(str), 0)
    assert many.mean() == pytest.approx(1.0, abs=0.02)
    assert many.var() == pytest.approx(1.0, abs=0.03)
    predicted, y, clients = _amounts(spikes=3)
    level = level_factor(predicted, y, clients)
    assert level == level_factor(predicted, y, clients)
    text, by_row = pd.Series(clients).astype(str), []
    for replicate in range(200):
        weights = _client_weights(text, replicate)
        by_row.append(weights @ y / (weights @ predicted))
    assert [level["low"], level["high"]] == pytest.approx(np.quantile(by_row, [0.025, 0.975]))
    with pytest.raises(ValueError, match="1 of 20,000 rows have a null client"):
        level_factor(predicted, y, np.where(np.arange(ROWS) == 7, None, clients))


CASES = [("binary", "log_loss", method) for method in TASK_CHOICES["binary"]["calibration_methods"]]
CASES += [
    ("regression", objective, method)
    for objective in ("squared_error", "tweedie")
    for method in TASK_CHOICES["regression"]["calibration_methods"]
]


@pytest.mark.parametrize(("task", "objective", "method"), CASES)
def test_every_allowed_method_gives_a_calibration_the_bundle_accepts(
    variant: Callable[..., UseCaseConfig], task: str, objective: str, method: str
) -> None:
    """The methods a task refuses are refused at config load, so every method a loaded config
    can hold must come back in a shape `check_calibration` accepts, on the objective's link,
    with the table marking it among every method the task fits."""
    cfg = _config(variant, task, objective, method)
    if task == "binary":
        margin, y, clients = _binary_rows(0.8, -0.3)
    else:
        predicted, y, clients = _amounts()
        margin = np.log(predicted) if objective == "tweedie" else predicted
    calibration, table, _ = calibrate(margin, y, clients, cfg, NO_SAMPLING)
    check_calibration(calibration, task)
    assert calibration["method"] == method
    assert list(table.columns) == list(CALIBRATION_COLUMNS)
    assert sorted(table["method"]) == sorted(TASK_CHOICES[task]["calibration_methods"])
    assert table.loc[table["chosen"], "method"].tolist() == [method]
    stored = table.loc[table["chosen"], "parameters"].item()
    assert json.loads(stored) == calibration["parameters"]
    assert table["oof_loss"].notna().all() == (task == "binary")


def test_an_anti_predictive_model_stops_training(
    cc_config: UseCaseConfig, variant: Callable[..., UseCaseConfig]
) -> None:
    """Reversed margins give a negative Platt slope, which stops Training whatever the method;
    constant margins mean the fold models learned nothing. Predictions of the wrong sign give a
    negative level factor: it stops Training when `mean` would put it in the bundle, and under
    `none` the run goes on with a warning that the factor is not defined."""
    margin, y, clients = _binary_rows(1.0, 0.0)
    for cfg in (cc_config, _config(variant, "binary", "log_loss", "none")):
        with pytest.raises(ValueError, match="anti-predictive out of fold"):
            calibrate(-margin, y, clients, cfg, NO_SAMPLING)
    with pytest.raises(ValueError, match="out-of-fold margins are constant"):
        calibrate(np.zeros(ROWS), y, clients, cc_config, NO_SAMPLING)
    predicted, y, clients = _amounts()
    cfg = _config(variant, "regression", "squared_error", "mean")
    with pytest.raises(ValueError, match="level factor .* must be positive and finite"):
        calibrate(-predicted, y, clients, cfg, NO_SAMPLING)
    cfg = _config(variant, "regression", "squared_error", "none")
    calibration, table, warnings = calibrate(-predicted, y, clients, cfg, NO_SAMPLING)
    assert calibration["parameters"] == {} and table["factor"].lt(0).all()
    assert warnings == [
        "the level factor is not defined for this target: its total, or the predictions' "
        "total, is not positive"
    ]
    cancelling = np.resize([1.0, -1.0], ROWS)  # predictions with a total of exactly zero
    with np.errstate(divide="ignore", invalid="ignore"):
        _, table, _ = calibrate(cancelling, y, clients, cfg, NO_SAMPLING)
    mean_row = table.set_index("method").loc["mean"]
    assert not np.isfinite(mean_row["factor"]) and mean_row["parameters"] == '{"factor": null}'


def test_training_refuses_a_fit_by_the_bundles_rule(
    cc_config: UseCaseConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Training checks every fitted method with the rule the bundle applies when it loads one,
    so a beta fit with one negative term is refused at Training, not only at the bundle's load,
    even when another method is chosen."""
    margin, y, clients = _binary_rows(1.0, 0.0)

    def negative_beta(margin: np.ndarray, y: np.ndarray) -> dict[str, float]:
        """A beta fit whose `a` is negative while `b` is positive."""
        return {"a": -0.1, "b": 0.5, "c": 0.0}

    monkeypatch.setattr("core_modelling.tasks.fit_beta", negative_beta)
    with pytest.raises(ValueError, match=r"the fitted beta calibration .* reverses or flattens"):
        calibrate(margin, y, clients, cc_config, NO_SAMPLING)


@pytest.mark.parametrize(
    ("method", "parameters"),
    [("platt", {"a": np.nan, "b": 0.0}), ("beta", {"a": np.inf, "b": 0.5, "c": 0.0}),
     ("beta", {"a": 0.5, "b": np.nan, "c": 0.0})],
)  # fmt: skip
def test_a_non_finite_parameter_never_passes_the_order_check(method: str, parameters: dict) -> None:
    """A NaN compares False, so `a <= 0` alone would let a NaN slope through: a non-finite
    parameter is refused before the order is judged."""
    with pytest.raises(ValueError, match="it must be a finite number"):
        check_order_kept(method, parameters)


def _small_train(task: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """1,200 train rows of 400 clients, three rows each, in four client folds: three numerics
    and a target driven by two of them, 0/1 for binary, else that times a lognormal amount.
    Returns the train frame (`unit_id`, `target`, `cv_fold`) and the encoded frame."""
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(1200, 3)), columns=["x1", "x2", "x3"])
    signal = (X["x1"] - 0.5 * X["x2"]).to_numpy()
    y = (rng.random(1200) < expit(signal - 1.0)).astype(np.int64)
    if task == "regression":
        y = y * np.exp(1.0 + 0.4 * signal)
    clients = np.arange(1200) // 3
    return X.assign(unit_id=clients, target=y, cv_fold=clients % 4), X


def _opened_step(
    cfg: UseCaseConfig,
    train: pd.DataFrame,
    X: pd.DataFrame,
    params: dict,
    judged_loss: float,
    collected: pd.DataFrame | None = None,
) -> tuple[Opened, TrainData, Search]:
    """What Training's fold-model step reads, with only the fields it uses filled: the run's
    config and its collected frame (`collected`, else `train`) without sampling, the encoded
    train rows with their target and folds, and a search whose best `lgbm` trial reported
    `judged_loss` at `params`."""
    collected = train if collected is None else collected
    meta = {"sampling": NO_SAMPLING}
    frames = Frames(snapshot=None, rows=None, train=collected, log=[], meta=meta)
    opened = Opened(
        resolved=cfg, entries=[], stage2=None, opening={},
        frames=frames, encoder={}, screened=None, run="run_001", log=[], warnings=[],
    )  # fmt: skip
    data = TrainData(
        X=X, y=train["target"].to_numpy(), folds=train[[FOLD_COLUMN]], encoder={}, monotone={},
        entered_encoder={}, shares=None, selection=None, statistics=None,
    )  # fmt: skip
    trials = pd.DataFrame({"family": ["lgbm"], "fold_loss": [judged_loss]})
    return opened, data, Search("lgbm", params, trials, {}, {})


@pytest.mark.parametrize(
    ("task", "objective", "method"),
    [("binary", "log_loss", "platt"), ("regression", "tweedie", "mean")],
)
def test_training_calibrates_on_its_own_out_of_fold_margins(
    variant: Callable[..., UseCaseConfig], task: str, objective: str, method: str
) -> None:
    """Training's step 6 fits the fold models and calibrates on their margins. On an
    overfitting model the in-sample margins call for a very different calibration (a Platt
    slope several times the out-of-fold one; a level factor far from it), so the step's
    calibration being the fit on the out-of-fold margins, to the last digits, shows it never
    read in-sample margins. The step reads the train rows alone: a train frame holding rows
    without a margin, test rows say, fails loud instead of entering the fit."""
    cfg = _config(variant, task, objective, method)
    train, X = _small_train(task)
    y, clients, folds = train["target"].to_numpy(), train["unit_id"].to_numpy(), train[["cv_fold"]]
    encoder = {"schema_version": 1, "unordered": "native", "min_level_client_count": 50,
               "features": [{"name": name, "kind": "numeric"} for name in X.columns]}  # fmt: skip
    power = cfg.training.tweedie_variance_power
    fixed = FAMILIES["lgbm"].fixed_params(task, objective, encoder, {}, 7, 1, power)
    params = {**fixed, **OVERFIT}
    margins, _ = fit_fold_models(X, y, folds, "lgbm", params, task, 1)
    judged = every_dealing_loss(X, y, folds, margins, "lgbm", params, cfg, 1)
    out = _fit_out_of_fold(*_opened_step(cfg, train, X, params, judged), threads=1)
    in_sample = fit_final_model(X, y, "lgbm", params, task, 1).margins
    np.testing.assert_array_equal(out.margins, margins)
    assert out.calibration["method"] == method
    if task == "binary":
        out_of_fold, in_fit = fit_platt(margins, y), fit_platt(in_sample, y)
        assert out.calibration["parameters"] == pytest.approx(out_of_fold, rel=1e-12)
        assert in_fit["a"] > 3 * out_of_fold["a"]
    else:
        out_of_fold = level_factor(np.exp(margins), y, clients)["factor"]
        in_fit = level_factor(np.exp(in_sample), y, clients)["factor"]
        assert out.calibration["parameters"]["factor"] == pytest.approx(out_of_fold, rel=1e-12)
        assert abs(in_fit - out_of_fold) > 0.2
    test_rows = train.assign(unit_id=train["unit_id"] + 10_000)  # other clients, no margins
    collected = pd.concat([train, test_rows])
    opened, data, search = _opened_step(cfg, train, X, params, judged, collected)
    with pytest.raises(ValueError, match="the margins, the target and the clients differ in rows"):
        _fit_out_of_fold(opened, data, search, 1)
