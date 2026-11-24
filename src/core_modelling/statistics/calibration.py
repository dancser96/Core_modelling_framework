"""The calibration statistics: the numbers Training fits on the fold models' out-of-fold margins.

Training fits them inside train (`CLAUDE.md` §4.7; `docs/components/training.md` → "Fold models
and calibration") and `model/calibration.py` applies them. Platt and beta are unpenalised
logistic regressions, on the margin and on the two logs of p = sigmoid(m); the logs come from
the margin through `log_expit`, as `apply_calibration` forms them, so the fit and the
application agree bit for bit. The prior-shift offset undoes negative downsampling. The level
factor sets a regression model's level, with a client bootstrap interval whose weights come
from a hash of the client, so a client's rows move together and a rerun draws the same
interval. Pure numpy, scipy, pandas and scikit-learn: no config, no Spark.
"""

import warnings

import numpy as np
import pandas as pd
from scipy.special import log_expit, logit
from scipy.stats import poisson
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

# C = 1e12 is unpenalised in float64 and warning-free: 1.8.0 warns on `C=np.inf` and on `penalty`.
# Newton to 1e-10 lands on the maximum likelihood (to ~1e-12); the default tol stops ~2e-4 off.
UNPENALISED = {"C": 1e12, "solver": "newton-cholesky", "tol": 1e-10, "max_iter": 100}
BOOTSTRAP_REPLICATES = 200
BOOTSTRAP_SALT = "level_factor"  # part of the hashed text: another use of the hash draws anew
# Poisson(1)'s CDF, 1.0 in float64 from 18 on: searching it inverts the CDF as `poisson.ppf`
# does, about twenty times faster on a replicate's clients.
POISSON_CDF = poisson.cdf(np.arange(30), 1.0)


def fit_platt(margin: np.ndarray, y: np.ndarray) -> dict:
    """Platt's `{a, b}`: the unpenalised logistic regression of the 0/1 `y` on the margin, so
    `score = sigmoid(a·m + b)`; a calibrated margin gives a ≈ 1, b ≈ 0."""
    m = np.asarray(margin, dtype=np.float64)
    _check_not_separated(m, y)
    (a,), b = _fit_logistic(m[:, None], y, "platt")
    return {"a": a, "b": b}


def fit_beta(margin: np.ndarray, y: np.ndarray) -> dict:
    """Beta calibration's `{a, b, c}` on p = sigmoid(m) [Kull17]: the unpenalised logistic
    regression of `y` on `ln(p)` and `−ln(1 − p)`, so `score = sigmoid(a·ln(p) − b·ln(1 − p) + c)`.

    A negative `a` (else a negative `b`) is refitted without its term, which is then 0, so the
    map stays increasing; a coefficient still negative after the refit is returned as fitted,
    for Training to refuse."""
    m = np.asarray(margin, dtype=np.float64)
    _check_not_separated(m, y)  # both logs rise with the margin, so they separate the labels too
    logs = np.column_stack([log_expit(m), -log_expit(-m)])  # ln(p), −ln(1 − p)
    (a, b), c = _fit_logistic(logs, y, "beta")
    if a < 0:
        (b,), c = _fit_logistic(logs[:, [1]], y, "beta")
        a = 0.0
    elif b < 0:
        (a,), c = _fit_logistic(logs[:, [0]], y, "beta")
        b = 0.0
    return {"a": a, "b": b, "c": c}


def _check_not_separated(margin: np.ndarray, y: np.ndarray) -> None:
    """Fail loud when the margin separates the labels (every 1 above every 0): no
    maximum-likelihood fit exists then, and the solver would return a large slope without a
    word."""
    y = np.asarray(y)
    zeros, ones = margin[y == 0], margin[y == 1]
    if zeros.size and ones.size and zeros.max() < ones.min():
        raise ValueError(
            f"the out-of-fold margins separate the labels (every 1 above {zeros.max():.4g}, every "
            "0 below it), so no calibration can be fitted; out of fold this means a leaking "
            "feature"
        )


def _fit_logistic(features: np.ndarray, y: np.ndarray, method: str) -> tuple[list[float], float]:
    """The coefficients and the intercept, as floats, of the unpenalised logistic regression of
    the 0/1 `y` on the columns of `features`; the solver's convergence warning becomes an error
    naming `method` and the rows. Separation is the caller's check."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        try:
            model = LogisticRegression(**UNPENALISED).fit(features, np.asarray(y))
        except ConvergenceWarning as error:
            raise ValueError(
                f"the {method} calibration did not converge on {len(features):,} rows, so its "
                "numbers are no maximum-likelihood fit; margins that nearly separate the labels "
                "are the usual cause, out of fold a leaking feature"
            ) from error
    return [float(value) for value in model.coef_[0]], float(model.intercept_[0])


def prior_shift_offset(true_rate: float, sampled_rate: float) -> float:
    """`logit(true_rate) − logit(sampled_rate)`: what a model fitted at the sampled rate is off
    by in log-odds at the true rate [KZ01]; `ln(keep fraction)` when negative downsampling hit
    its expected rate. A rate outside (0, 1) fails loud."""
    for name, rate in (("true", true_rate), ("sampled", sampled_rate)):
        if not 0 < rate < 1:
            raise ValueError(
                f"the {name} rate is {rate}; the prior-shift offset needs both rates strictly "
                "between 0 and 1"
            )
    return float(logit(true_rate) - logit(sampled_rate))


def level_factor(
    predicted: np.ndarray,
    y: np.ndarray,
    clients: np.ndarray,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> dict:
    """The level factor `Σy / Σpredicted`, never winsorised (capping the target moved the level
    further than no correction did), with its 95% client bootstrap interval and the rows that
    decide it.

    Receives one entry per row, aligned: the prediction in the target's units, the target and
    the client, never null. Returns `factor`, `low` and `high` (the 2.5% and 97.5% quantiles of
    the factor over `replicates` replicates, each client's rows weighted together by
    `_client_weights`), `half_total_rows` (`_half_total_rows`) and `zero_replicates`, the
    replicates whose weighted predictions total 0: with any, the factor is undefined there and
    `low` and `high` are NaN.
    """
    rows = pd.DataFrame(
        {
            "client": np.asarray(clients),
            "y": np.asarray(y, dtype=np.float64),
            "predicted": np.asarray(predicted, dtype=np.float64),
        }
    )
    nulls = int(rows["client"].isna().sum())
    if nulls:
        raise ValueError(
            f"{nulls:,} of {len(rows):,} rows have a null client; the bootstrap weighs each "
            "client's rows together, so every row needs its client"
        )
    totals = rows.groupby("client", sort=True)[["y", "predicted"]].sum()
    text = pd.Series(totals.index).astype(str)  # once: a replicate only appends its number
    y_totals, predicted_totals = totals["y"].to_numpy(), totals["predicted"].to_numpy()
    observed, predicted = np.empty(replicates), np.empty(replicates)
    for replicate in range(replicates):
        weights = _client_weights(text, replicate)
        observed[replicate], predicted[replicate] = weights @ y_totals, weights @ predicted_totals
    zero = int((predicted == 0).sum())
    low = high = np.nan
    if not zero:
        low, high = np.quantile(observed / predicted, [0.025, 0.975])
    return {
        "factor": float(rows["y"].sum() / rows["predicted"].sum()),
        "low": float(low),
        "high": float(high),
        "half_total_rows": _half_total_rows(rows["y"].to_numpy()),
        "zero_replicates": zero,
    }


def _client_weights(clients: pd.Series, replicate: int) -> np.ndarray:
    """One Poisson(1) weight per entry of `clients` (the client ids as text) in bootstrap
    `replicate`: pandas' fixed hash of the text `client:replicate:salt`, its top 53 bits as a
    uniform in (0, 1), through Poisson's inverse CDF. A weight depends on its client and
    replicate alone, so a client's rows share it and a rerun on any set of clients draws it
    again."""
    text = clients + f":{replicate}:{BOOTSTRAP_SALT}"
    hashed = pd.util.hash_pandas_object(text, index=False).to_numpy()
    uniform = ((hashed >> np.uint64(11)).astype(np.float64) + 0.5) / 2.0**53
    return np.searchsorted(POISSON_CDF, uniform).astype(np.float64)


def _half_total_rows(y: np.ndarray) -> int | None:
    """The smallest number of rows whose targets sum to half of the total, the largest first;
    None when the total is not positive, which has no such half."""
    cumulative = np.cumsum(np.sort(y)[::-1])
    if not cumulative[-1] > 0:
        return None
    return int(np.argmax(cumulative >= cumulative[-1] / 2)) + 1
