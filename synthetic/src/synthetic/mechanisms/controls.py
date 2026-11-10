"""The monthly control columns (test_harness.md, "Trap summary"; D-064).

Five trap columns drawn fresh each month from the `controls` stream, each the trap of one check
and a control close to the threshold of others: an honest score and a score delivered every
other month (both noisy readings of this month's oracle score, so they add no mechanism and the
oracle stays the ceiling), a one-value column with random nulls, a wait time whose level steps up
inside the example window, and a contact channel whose mix shifts moderately and gains a level
later. They read this month only: no look-ahead, no per-client state. Their names, kinds and types
live with the other traps' in `traps`; dates are "YYYY-MM" months of the spec row.
"""

import numpy as np

from synthetic.mechanisms.traps import (
    CONTACT_CHANNEL,
    HONEST_SCORE,
    STATEMENT_FORMAT,
    SUPPORT_WAIT,
    VENDOR_SCORE,
    trap_record,
)


def control_columns(
    spec: dict, scores: dict[str, np.ndarray], month: np.datetime64, rng: np.random.Generator
) -> dict[str, object]:
    """The month's control columns, in the mart's order.

    `scores` are the month's oracle values (`score_<product>` is read), `month` the panel month.
    Draws, one per client each, in this order: the honest score's normal, the vendor score's
    normal, the statement format's null and new-level uniforms, the support wait's null uniform
    and normal, the contact channel's level and new-level uniforms.
    """
    product = trap_record(spec, "honest", HONEST_SCORE)["product"]
    n = len(scores[f"score_{product}"])
    honest_noise, vendor_noise = rng.standard_normal(n), rng.standard_normal(n)
    format_null, format_new = rng.random(n), rng.random(n)
    wait_null, wait_noise = rng.random(n), rng.standard_normal(n)
    channel_level, channel_new = rng.random(n), rng.random(n)
    return {
        HONEST_SCORE: _honest_score(spec, scores, month, honest_noise),
        VENDOR_SCORE: _vendor_score(spec, scores, month, vendor_noise),
        STATEMENT_FORMAT: _statement_format(spec, month, format_null, format_new),
        SUPPORT_WAIT: _support_wait(spec, month, wait_null, wait_noise),
        CONTACT_CHANNEL: _contact_channel(spec, month, channel_level, channel_new),
    }


def _honest_score(
    spec: dict, scores: dict[str, np.ndarray], month: np.datetime64, noise: np.ndarray
) -> np.ndarray:
    """round(centre + scale · (loading · z + σ · noise) / √(loading² + σ²)), z the product's
    score standardised over the month's clients, σ `sigma["even"]` in even calendar months and
    `sigma["odd"]` in odd ones: a strong score whose power swings a little from month to month
    while its spread stays the same."""
    record = trap_record(spec, "honest", HONEST_SCORE)
    p = record["parameters"]
    z = _standard_score(scores[f"score_{record['product']}"])
    sigma = p["sigma"]["even" if _even_month(month) else "odd"]
    signal = (p["loading"] * z + sigma * noise) / np.hypot(p["loading"], sigma)
    return np.round(p["centre"] + p["scale"] * signal).astype("int64")


def _vendor_score(
    spec: dict, scores: dict[str, np.ndarray], month: np.datetime64, noise: np.ndarray
) -> np.ndarray:
    """round(centre + scale · (loading · z + noise) / √(loading² + 1)) in even calendar months,
    round(centre + scale · noise) in odd ones: a score delivered every other month, noise in
    between, with the same spread in both."""
    record = trap_record(spec, "unstable", VENDOR_SCORE)
    p = record["parameters"]
    loading = p["loading"] if _even_month(month) else 0.0
    z = _standard_score(scores[f"score_{record['product']}"])
    signal = (loading * z + noise) / np.hypot(loading, 1.0)
    return np.round(p["centre"] + p["scale"] * signal).astype("int64")


def _statement_format(
    spec: dict, month: np.datetime64, null_u: np.ndarray, new_u: np.ndarray
) -> np.ndarray:
    """One value for every client, None at random on `null_share` of the rows; from
    `new_level_month` the new level on `new_level_share` of the filled rows."""
    p = trap_record(spec, "one_value", STATEMENT_FORMAT)["parameters"]
    new = _dated(month, p["new_level_month"]) & (new_u < p["new_level_share"])
    value = np.where(new, p["new_level"], p["value"]).astype(object)
    return np.where(null_u < p["null_share"], None, value)


def _support_wait(
    spec: dict, month: np.datetime64, null_u: np.ndarray, noise: np.ndarray
) -> np.ndarray:
    """A lognormal wait in minutes to 0.1 (log-scale sd `sigma`) around `median`, the median ×
    `factor` from `step_month` on; NaN at random on `null_share` of the rows (no call this
    month), so the nulls stand for 0 and a value is never 0."""
    p = trap_record(spec, "drift_window", SUPPORT_WAIT)["parameters"]
    median = p["median"] * (p["factor"] if _dated(month, p["step_month"]) else 1.0)
    wait = np.round(median * np.exp(p["sigma"] * noise), 1)
    return np.where(null_u < p["null_share"], np.nan, wait)


def _contact_channel(
    spec: dict, month: np.datetime64, level_u: np.ndarray, new_u: np.ndarray
) -> np.ndarray:
    """A level drawn with the month's shares (`_level_shares`); from `new_level_month` the new
    level on `new_level_share` of the rows, taken from the others in proportion."""
    p = trap_record(spec, "drift_moderate", CONTACT_CHANNEL)["parameters"]
    levels = np.array(p["levels"], dtype=object)
    channel = levels[np.searchsorted(np.cumsum(_level_shares(p, month))[:-1], level_u, "right")]
    new = _dated(month, p["new_level_month"]) & (new_u < p["new_level_share"])
    return np.where(new, p["new_level"], channel)


def _level_shares(p: dict, month: np.datetime64) -> list[float]:
    """The level shares in force in `month` of the parameters `p`: `before` until `step_month`,
    `after` from it; each list must sum to 1."""
    shares = p["after"] if _dated(month, p["step_month"]) else p["before"]
    if not np.isclose(sum(shares), 1):
        raise ValueError(f"level shares {shares} do not sum to 1")
    return shares


def _standard_score(values: np.ndarray) -> np.ndarray:
    """`values` standardised over the month's clients (mean 0, sd 1)."""
    return (values - values.mean()) / values.std()


def _even_month(month: np.datetime64) -> bool:
    """Whether `month` is an even calendar month (February, April, …)."""
    return bool((month.astype("datetime64[M]").astype(int) % 12 + 1) % 2 == 0)


def _dated(month: np.datetime64, iso_month: str) -> bool:
    """Whether `month` is `iso_month` ("YYYY-MM") or later."""
    return bool(month.astype("datetime64[M]") >= np.datetime64(iso_month, "M"))
