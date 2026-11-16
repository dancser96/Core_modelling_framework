"""The calibration: the plain numbers that turn a model's margin into its score, applied one way.

Training fits the numbers on out-of-fold margins inside train (`CLAUDE.md` §4.7) and writes them
into `bundle.json` as `{link, method, parameters, offset}`, one shape for both tasks
(`docs/components/model_bundle.md` → "The calibration and the output columns"). Every scoring
(Training's self-check, Evaluation, Inference, in pandas or inside Spark) applies them through
`apply_calibration`, so a score never depends on who computed it; `write_bundle` refuses a
calibration `check_calibration` refuses before it writes anything. The link follows the
objective: `logit` for binary, `log` for Tweedie and Poisson, `identity` for the other
regression objectives. The sigmoid and the logs are scipy's stable forms, so a margin of ±40
gives a finite score and the beta map never forms `1 − p`.
"""

import math
from numbers import Real

import numpy as np
from scipy.special import expit, log_expit

CALIBRATION_KEYS = ("link", "method", "parameters", "offset")
LINKS_BY_TASK = {"binary": ("logit",), "regression": ("identity", "log")}
METHODS_BY_LINK = {
    "logit": ("none", "platt", "beta"),
    "identity": ("none", "mean"),
    "log": ("none", "mean"),
}
PARAMETERS_BY_METHOD = {
    "none": (),
    "platt": ("a", "b"),
    "beta": ("a", "b", "c"),
    "mean": ("factor",),
}


def apply_calibration(
    margin: np.ndarray, calibration: dict, task: str
) -> tuple[np.ndarray, np.ndarray]:
    """`(score_raw, score)` for the margins `m`, float64, by the bundle's calibration:
    - `logit`: `score_raw = sigmoid(m)`; `score = sigmoid(z + offset)` with `z` = `m` (`none`),
      `a·m + b` (`platt`) or `a·ln(p) − b·ln(1 − p) + c` with `p = sigmoid(m)` (`beta`);
    - `identity`: `score_raw = m`; `score = m × factor`;
    - `log`: `score_raw = exp(m)`; `score = exp(m) × factor`; the factor is 1 under `none`."""
    check_calibration(calibration, task)
    m = np.array(margin, dtype=np.float64)  # a copy: `score_raw` never aliases the caller's array
    link, method, parameters = calibration["link"], calibration["method"], calibration["parameters"]
    if link == "logit":
        return expit(m), expit(_logit_input(m, method, parameters) + calibration["offset"])
    score_raw = m if link == "identity" else np.exp(m)
    return score_raw, score_raw * parameters.get("factor", 1.0)


def _logit_input(m: np.ndarray, method: str, parameters: dict) -> np.ndarray:
    """The calibrated log-odds before the offset; `ln(p)` and `ln(1 − p)` come from the margin
    itself (`log_expit(m)`, `log_expit(−m)`), so neither underflows to `ln(0)`."""
    if method == "none":
        return m
    if method == "platt":
        return parameters["a"] * m + parameters["b"]
    a, b, c = parameters["a"], parameters["b"], parameters["c"]
    return a * log_expit(m) - b * log_expit(-m) + c


def check_calibration(calibration: dict, task: str) -> None:
    """Fail loud unless `calibration` has exactly `CALIBRATION_KEYS`, a link the task takes, a
    method the link takes with exactly its parameters, finite numbers that keep the model's
    order (`_check_order_kept`), and a zero offset for a regression link (the prior-shift offset
    exists for binary only, §4.7)."""
    keys = sorted(calibration)
    if keys != sorted(CALIBRATION_KEYS):
        raise ValueError(
            f"the calibration has the keys {keys}; it must have {list(CALIBRATION_KEYS)}"
        )
    if task not in LINKS_BY_TASK:
        raise ValueError(
            f"the task is {task!r}; a calibration is defined for {list(LINKS_BY_TASK)}"
        )
    link, method = calibration["link"], calibration["method"]
    if link not in LINKS_BY_TASK[task]:
        raise ValueError(
            f"the calibration's link is {link!r}, which a {task} model does not have; "
            f"{task} takes {list(LINKS_BY_TASK[task])}"
        )
    if method not in METHODS_BY_LINK[link]:
        raise ValueError(
            f"the calibration's method {method!r} does not apply to the {link} link; it takes "
            f"{list(METHODS_BY_LINK[link])}"
        )
    names = sorted(calibration["parameters"])
    if names != sorted(PARAMETERS_BY_METHOD[method]):
        raise ValueError(
            f"the {method} calibration has the parameters {names}; it takes exactly "
            f"{list(PARAMETERS_BY_METHOD[method])}"
        )
    for name, value in [*calibration["parameters"].items(), ("offset", calibration["offset"])]:
        _check_number(value, name)
    _check_order_kept(method, calibration["parameters"])
    if link != "logit" and calibration["offset"] != 0:
        raise ValueError(
            f"the calibration's offset is {calibration['offset']} on the {link} link; the "
            "prior-shift offset is always zero for regression"
        )


def _check_order_kept(method: str, parameters: dict) -> None:
    """Fail loud unless the map from margin to score is strictly increasing, so the score ranks
    as the margin does: Platt `a > 0`; beta `a ≥ 0` and `b ≥ 0`, not both zero (its slope in the
    margin is `a·(1 − p) + b·p`); a factor `> 0`."""
    a, b = parameters.get("a"), parameters.get("b")
    reverses = (
        (method == "platt" and a <= 0)
        or (method == "beta" and (a < 0 or b < 0 or a == b == 0))
        or (method == "mean" and parameters["factor"] <= 0)
    )
    if reverses:
        raise ValueError(
            f"the fitted {method} calibration {parameters} reverses or flattens the model's "
            "order; the fit must be looked at, not applied"
        )


def _check_number(value: object, name: str) -> None:
    """Fail loud unless a calibration number is a finite real number (never a boolean)."""
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"the calibration's {name} is {value!r}; it must be a finite number")
