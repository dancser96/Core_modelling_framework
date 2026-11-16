"""Scoring: the calibration's arithmetic against hand computations, its refusals, `score_frame`'s
output shape, and `score_spark` against `score_frame` in real local Spark (the one Spark test,
run by the main thread with the other Spark tests). The bundles come from `test_bundle.py`'s
helpers.
"""

from dataclasses import replace
from datetime import date
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pyspark.sql import SparkSession
from test_bundle import IDENTITY, raw_frame, trained

from core_modelling.model import (
    apply_calibration,
    load_bundle,
    score_frame,
    score_spark,
    write_bundle,
)
from core_modelling.model.bundle import OUTPUT_COLUMNS
from core_modelling.model.scoring import _check_library_versions

MARGINS = np.array([-40.0, -5.0, -1.0, -0.25, 0.0, 0.5, 2.0, 7.0, 40.0])
MODERATE = MARGINS[1:-1]  # where the hand formulas, which form 1 − p, stay accurate


def _logit(method: str, parameters: dict, offset: float = 0.0) -> dict:
    """A binary calibration of `method`."""
    return {"link": "logit", "method": method, "parameters": parameters, "offset": offset}


def _regression(link: str, method: str, parameters: dict) -> dict:
    """A regression calibration on `link`, its offset zero."""
    return {"link": link, "method": method, "parameters": parameters, "offset": 0.0}


def _sigmoid(x: np.ndarray) -> np.ndarray:
    """The sigmoid written out, independent of scipy."""
    return 1 / (1 + np.exp(-x))


def test_platt_at_one_and_zero_is_none_and_the_offset_shifts_the_log_odds() -> None:
    """`score_raw` is the plain sigmoid; Platt's family holds "leave as is" exactly; the
    prior-shift offset is added on the log-odds scale and never touches `score_raw`."""
    raw, none = apply_calibration(MARGINS, _logit("none", {}), "binary")
    np.testing.assert_allclose(raw, _sigmoid(MARGINS), rtol=1e-12)
    assert raw.dtype == none.dtype == np.float64 and np.array_equal(none, raw)
    _, platt = apply_calibration(MARGINS, _logit("platt", {"a": 1.0, "b": 0.0}), "binary")
    assert np.array_equal(platt, none)
    raw_shifted, shifted = apply_calibration(MARGINS, _logit("none", {}, 0.7), "binary")
    assert np.array_equal(raw_shifted, raw)
    np.testing.assert_allclose(shifted, _sigmoid(MARGINS + 0.7), rtol=1e-12)
    _, general = apply_calibration(MARGINS, _logit("platt", {"a": 0.5, "b": -1.0}, 0.7), "binary")
    np.testing.assert_allclose(general, _sigmoid(0.5 * MARGINS - 1.0 + 0.7), rtol=1e-12)


def test_beta_at_one_one_zero_is_none_and_stays_finite() -> None:
    """Beta's ln(p) − ln(1 − p) is the margin again, computed without forming 1 − p, so a
    margin of ±40 (where 1 − p rounds to 0) scores finitely; its general form matches the
    formula written out."""
    _, none = apply_calibration(MARGINS, _logit("none", {}), "binary")
    beta_one = _logit("beta", {"a": 1.0, "b": 1.0, "c": 0.0})
    _, beta = apply_calibration(MARGINS, beta_one, "binary")
    assert np.isfinite(beta).all()
    np.testing.assert_allclose(beta, none, rtol=1e-12)
    a, b, c, offset = 0.8, 1.3, 0.2, 0.4
    p = _sigmoid(MODERATE)
    beta_general = _logit("beta", {"a": a, "b": b, "c": c}, offset)
    _, general = apply_calibration(MODERATE, beta_general, "binary")
    hand = _sigmoid(a * np.log(p) - b * np.log(1 - p) + c + offset)
    np.testing.assert_allclose(general, hand, rtol=1e-9)


def test_the_regression_links_and_the_mean_factor() -> None:
    """`identity`: the margin itself, times the factor; `log` (Tweedie, Poisson): its
    exponential, times the factor; `none` leaves the factor at 1."""
    raw, score = apply_calibration(MODERATE, _regression("identity", "none", {}), "regression")
    assert np.array_equal(raw, MODERATE) and np.array_equal(score, MODERATE)
    mean = _regression("identity", "mean", {"factor": 1.25})
    _, scaled = apply_calibration(MODERATE, mean, "regression")
    assert np.array_equal(scaled, MODERATE * 1.25)
    raw, score = apply_calibration(MODERATE, _regression("log", "none", {}), "regression")
    assert np.array_equal(raw, np.exp(MODERATE)) and np.array_equal(score, raw)
    log_mean = _regression("log", "mean", {"factor": 0.8})
    _, scaled = apply_calibration(MODERATE, log_mean, "regression")
    assert np.array_equal(scaled, np.exp(MODERATE) * 0.8)


REFUSALS = [
    ("binary", _logit("mean", {"factor": 1.0}), "does not apply to the logit link"),
    ("regression", _regression("identity", "platt", {"a": 1.0, "b": 0.0}), "the identity link"),
    ("regression", _regression("log", "beta", {"a": 1.0, "b": 1.0, "c": 0.0}), "the log link"),
    ("binary", _logit("platt", {"a": 1.0}), r"has the parameters \['a'\]"),
    ("binary", _logit("none", {"factor": 1.0}), r"has the parameters \['factor'\]"),
    ("binary", _logit("beta", {"a": 1.0, "b": 1.0, "c": float("nan")}), "c is nan"),
    ("binary", _logit("none", {}, float("inf")), "offset is inf"),
    ("regression", {**_regression("log", "none", {}), "offset": 0.1}, "offset is 0.1 on the log"),
    ("binary", _regression("identity", "none", {}), "a binary model does not have"),
    ("regression", _logit("none", {}), "a regression model does not have"),
    ("survival", _logit("none", {}), "the task is 'survival'"),
    ("binary", {"link": "logit", "method": "none", "parameters": {}}, "has the keys"),
]


@pytest.mark.parametrize(("task", "calibration", "message"), REFUSALS)
def test_apply_calibration_refuses_what_the_spec_does_not_define(
    task: str, calibration: dict, message: str
) -> None:
    """A method the link does not take, a missing or extra parameter, a number that is not
    finite, an offset on a regression link, a task that disagrees with the link, and a missing
    key are refused, never scored."""
    with pytest.raises(ValueError, match=message):
        apply_calibration(MODERATE, calibration, task)


ORDER_BREAKING = [  # each map from margin to score falls or stays flat somewhere
    ("binary", _logit("platt", {"a": -1.0, "b": 0.0})),
    ("binary", _logit("platt", {"a": 0.0, "b": 0.3})),
    ("binary", _logit("beta", {"a": -1.0, "b": -1.0, "c": 0.0})),
    ("binary", _logit("beta", {"a": -0.5, "b": 1.0, "c": 0.0})),
    ("binary", _logit("beta", {"a": 1.0, "b": -0.5, "c": 0.0})),
    ("binary", _logit("beta", {"a": 0.0, "b": 0.0, "c": 0.2})),
    ("regression", _regression("identity", "mean", {"factor": -2.0})),
    ("regression", _regression("log", "mean", {"factor": 0.0})),
]


@pytest.mark.parametrize(("task", "calibration"), ORDER_BREAKING)
def test_a_calibration_that_reverses_or_flattens_the_order_is_refused(
    task: str, calibration: dict
) -> None:
    """A fitted calibration must keep the model's ranking (every rank metric and every top-N
    list read the score): Platt `a ≤ 0`, a negative beta term or both zero, and a factor
    `≤ 0` are refused, so the fit is looked at instead of applied."""
    with pytest.raises(ValueError, match="reverses or flattens the model's order"):
        apply_calibration(MODERATE, calibration, task)


def test_an_increasing_beta_with_one_term_zero_is_kept() -> None:
    """Beta with one coefficient zero is still strictly increasing (its slope is
    `a·(1 − p) + b·p`), so it scores in the margin's order."""
    _, score = apply_calibration(MODERATE, _logit("beta", {"a": 0.0, "b": 1.0, "c": 0.0}), "binary")
    assert (np.diff(score) > 0).all()


def test_an_executor_with_another_library_version_fails_loud() -> None:
    """Inside Spark a partition must score with the driver's model library: the check that
    each partition runs passes on the same version and names both versions otherwise."""
    installed = version("lightgbm")
    _check_library_versions({"lightgbm": installed})
    with pytest.raises(RuntimeError, match=f"executor has lightgbm {installed}, the driver 0.0.1"):
        _check_library_versions({"lightgbm": "0.0.1"})


def test_score_frame_keeps_the_index_and_fails_on_a_missing_feature(tmp_path: Path) -> None:
    """Three float64 columns on the input's index, whatever the column order or the extra
    columns; a frame without a model feature fails rather than scores."""
    folder = str(tmp_path / "bundle")
    write_bundle(folder, "lgbm", *trained(), IDENTITY)
    bundle = load_bundle(folder)
    frame = raw_frame(50, seed=2).assign(spare="x")
    frame.index = pd.Index([f"row{number}" for number in range(50)])
    scores = score_frame(bundle, frame)
    assert list(scores.columns) == OUTPUT_COLUMNS and scores.index.equals(frame.index)
    assert (scores.dtypes == np.float64).all()
    pd.testing.assert_frame_equal(score_frame(bundle, frame[frame.columns[::-1]]), scores)
    with pytest.raises(ValueError, match=r"lacks the columns \['age'\]"):
        score_frame(bundle, frame.drop(columns="age"))


@pytest.mark.filterwarnings("ignore:overflow encountered in multiply:RuntimeWarning")
def test_score_frame_refuses_a_non_finite_score(tmp_path: Path) -> None:
    """The `log` link can overflow to inf (here through a factor near the largest double): a
    score that is not a finite number fails, naming the column and the count, never scores."""
    folder = str(tmp_path / "bundle")
    write_bundle(folder, "lgbm", *trained("lgbm", "regression"), IDENTITY)
    bundle = load_bundle(folder)
    huge = {**bundle.calibration, "parameters": {"factor": 1e308}}
    with pytest.raises(ValueError, match=r"gives \d+ of 50 rows a non-finite score;"):
        score_frame(replace(bundle, calibration=huge), raw_frame(50, seed=2))


def test_score_spark_equals_score_frame_on_the_same_rows(
    spark: SparkSession, tmp_path: Path
) -> None:
    """One scoring path (A28): over several partitions, a binary and a regression bundle score
    every row inside Spark exactly as `score_frame` does, with the kept columns' own types; a
    `keep` naming a missing or a score column, or rows without a feature, fail before Spark
    runs."""
    period = date(2026, 6, 30)
    frame = raw_frame(600, seed=3).assign(period=period)
    rows = spark.createDataFrame(frame).repartition(3)
    for task in ("binary", "regression"):
        folder = str(tmp_path / task)
        write_bundle(folder, "lgbm", *trained("lgbm", task), IDENTITY)
        scored = score_spark(folder, rows, ["unit_id", "period"])
        types = [field.dataType.simpleString() for field in scored.schema]
        assert types == ["bigint", "date", "double", "double", "double"]
        found = scored.toPandas().sort_values("unit_id").set_index("unit_id")
        expected = score_frame(load_bundle(folder), frame.set_index("unit_id"))
        pd.testing.assert_frame_equal(found[OUTPUT_COLUMNS], expected, check_exact=True)
        assert (found["period"] == period).all()
    with pytest.raises(ValueError, match=r"keep names \['nope'\], which the rows lack"):
        score_spark(folder, rows, ["unit_id", "nope"])
    with pytest.raises(ValueError, match="the score columns are added"):
        score_spark(folder, rows, ["unit_id", "score"])
    with pytest.raises(ValueError, match=r"lack the features \['age'\]"):
        score_spark(folder, rows.drop("age"), ["unit_id"])
