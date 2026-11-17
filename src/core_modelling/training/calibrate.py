"""Training's calibration: the run's rule applied to the fold models' out-of-fold margins.

The calibration is fitted on the train rows' out-of-fold margins only, never on test or
validation rows (`CLAUDE.md` §4.7). The method is the config's (`training.calibration.method`,
filled at load from the decision or the objective, D-049), never chosen from the evidence;
every method the task allows is fitted anyway (`TASK_SPECS[task]["calibration_fits"]`) and
written to Training's `calibration` table with its evidence, so the cost of the choice is
visible. The offset follows the method of sampling. The bundle takes the calibration as
`{link, method, parameters, offset}` (`docs/components/model_bundle.md` → "The calibration and
the output columns"); `apply_calibration` is the one code that applies it.
"""

import json
import math

import numpy as np
import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.model.calibration import LINK_BY_OBJECTIVE, apply_calibration, uncalibrated
from core_modelling.statistics.calibration import prior_shift_offset
from core_modelling.statistics.losses import metric_loss
from core_modelling.tasks import TASK_SPECS

# Training's `calibration` table: one row per method the task fits, one schema for both tasks,
# null where a column does not apply; `parameters` is JSON text, so the table writes to parquet.
CALIBRATION_COLUMNS = {
    "method": "object",
    "chosen": "bool",
    "parameters": "object",
    "oof_log_loss": "float64",
    "true_rate": "float64",
    "sampled_rate": "float64",
    "offset": "float64",
    "factor": "float64",
    "factor_low": "float64",
    "factor_high": "float64",
    "half_total_rows": "Int64",
}
SAMPLING_METHODS = (None, "negative_downsampling", "client_sample")


def calibrate(
    margins: np.ndarray, y: np.ndarray, clients: np.ndarray, cfg: UseCaseConfig, sampling: dict
) -> tuple[dict, pd.DataFrame, list[str]]:
    """The bundle's calibration for the run's method, Training's `calibration` table and the
    warnings.

    Receives the train rows' out-of-fold margins as trained (at the sampled rate under
    sampling), their target and their `unit_id`, aligned, and the frames' sampling record.
    Constant margins, or a fit that would reverse or flatten the model's order, fail loud. A
    binary method's out-of-fold log loss is taken on its score without the offset, at the rows'
    own rate.
    """
    if not len(margins) == len(y) == len(clients):
        raise ValueError(
            f"the margins, the target and the clients differ in rows: {len(margins)}, {len(y)}, "
            f"{len(clients)}"
        )
    if np.ptp(margins) == 0:
        raise ValueError("the out-of-fold margins are constant: the fold models learned nothing")
    task, objective, spec = cfg.task, cfg.training.objective, TASK_SPECS[cfg.task]
    chosen = cfg.training.calibration.method
    score_raw, _ = apply_calibration(margins, uncalibrated(objective), task)
    fits, evidence, warnings = spec["calibration_fits"](margins, score_raw, y, clients)
    _check_order(fits, chosen)
    offset = _offset(sampling)
    calibrations = {
        method: {"link": LINK_BY_OBJECTIVE[objective], "method": method,
                 "parameters": parameters, "offset": offset}
        for method, parameters in fits.items()
    }  # fmt: skip
    losses = {
        method: _oof_loss(spec["calibration_loss"], margins, y, calibration, task)
        for method, calibration in calibrations.items()
    }
    table = _calibration_table(calibrations, losses, evidence, sampling, chosen)
    return calibrations[chosen], table, warnings


def _check_order(fits: dict[str, dict], chosen: str) -> None:
    """Fail loud on a fit that would reverse or flatten the model's order: a Platt slope at or
    below zero, or a beta fit with neither coefficient positive, means the model is
    anti-predictive out of fold, whatever the method; a level factor must be positive and
    finite when `mean` is `chosen`, so the bundle would hold it (under `none` the regression
    fits warn instead)."""
    platt, beta, mean = fits.get("platt"), fits.get("beta"), fits.get("mean")
    if (platt and platt["a"] <= 0) or (beta and beta["a"] <= 0 and beta["b"] <= 0):
        raise ValueError(
            f"the model is anti-predictive out of fold: Platt {platt} and beta {beta}, fitted on "
            "its out-of-fold margins, reverse or flatten its order; look at the features and the "
            "target before training again"
        )
    if chosen == "mean" and not (math.isfinite(mean["factor"]) and mean["factor"] > 0):
        raise ValueError(
            f"the level factor (the target's total over the predictions' total, out of fold) is "
            f"{mean['factor']}; it must be positive and finite, so the out-of-fold predictions "
            "miss the target's level entirely"
        )


def _offset(sampling: dict) -> float:
    """The prior-shift offset of the sampling record: `logit(true) − logit(sampled)` under
    `negative_downsampling`; 0.0 without sampling and under `client_sample` by rule, never from
    the record's two rates, which differ there by sampling noise only."""
    method = sampling["method"]
    if method not in SAMPLING_METHODS:
        raise ValueError(f"the sampling record's method is {method!r}; known: {SAMPLING_METHODS}")
    if method == "negative_downsampling":
        return prior_shift_offset(sampling["true_rate"], sampling["sampled_rate"])
    return 0.0


def _oof_loss(
    metric: str | None, margins: np.ndarray, y: np.ndarray, calibration: dict, task: str
) -> float | None:
    """`metric` on the calibrated out-of-fold scores without the offset (the rows are at the
    sampled rate, the offset moves them to the true one), or None when the task shows no loss."""
    if metric is None:
        return None
    _, score = apply_calibration(margins, {**calibration, "offset": 0.0}, task)
    return metric_loss(metric, y, score)


def _calibration_table(
    calibrations: dict[str, dict], losses: dict, evidence: dict, sampling: dict, chosen: str
) -> pd.DataFrame:
    """Training's `calibration` table, one row per fitted method in `CALIBRATION_COLUMNS`: the
    method, whether the bundle holds it, its parameters as JSON text, its out-of-fold loss, the
    sampling record's two rates (its target means before and after sampling: rates for a binary
    target), the offset, and the task's evidence (the level factor with its interval and
    `half_total_rows` for regression); null where a column does not apply."""
    rows = [
        {
            "method": method,
            "chosen": method == chosen,
            "parameters": _parameters_json(calibration["parameters"]),
            "oof_log_loss": losses[method],
            "true_rate": sampling.get("true_rate"),
            "sampled_rate": sampling.get("sampled_rate"),
            "offset": calibration["offset"],
            **evidence,
        }
        for method, calibration in calibrations.items()
    ]
    return pd.DataFrame(rows, columns=list(CALIBRATION_COLUMNS)).astype(CALIBRATION_COLUMNS)


def _parameters_json(parameters: dict[str, float]) -> str:
    """A method's parameters as JSON text, a non-finite one as null: `NaN` and `Infinity` are no
    JSON, and only a method the run did not choose can hold one (`_check_order`)."""
    return json.dumps(
        {name: value if math.isfinite(value) else None for name, value in parameters.items()},
        sort_keys=True,
    )
