"""Time effects of the synthetic book: what changes with the calendar, differently per profile.

Values live in `levels.SEASONS`; the bonus trigger lives in `products.HOLDING_RULES`. This part
shifts products' log-odds scores (test_harness.md maths §3, `time_k,p(t)` and `after_bonus`): FX
wake-ups rise in summer, digital wake-ups trend up from the first panel month (a drift trap), and
a bonus raises term-deposit and wealth adoption odds in the months after it. `hazards.time_terms`
adds them to monthly adoption and wake-up log-odds only: lapses, the starting book and the
calibration leave them out, so shares wobble slightly with the season. Build stage B adds the
seasonal factors on amounts, school fees and bonuses due, and the login drift.
"""

import numpy as np
import pandas as pd

from synthetic.population import profile_values


def month_of_year(month: np.datetime64) -> int:
    """Calendar month (1–12) of a numpy month."""
    return int(month.astype(int) % 12 + 1)


def wake_shift(spec: dict, key: str, clients: pd.DataFrame, month: np.datetime64) -> np.ndarray:
    """Calendar shift on a product's log-odds score: seasonal wake-ups and the uptake trend.

    A seasonal shift applies to moves into its months, per profile (FX in July and August). The
    trend adds log(odds per year) × the years since the spec's first month, 0 before it.
    """
    seasons, out = spec["seasons"], np.zeros(len(clients))
    shifts = seasons["wake_shifts"].get(key)
    if shifts and month_of_year(month) in shifts["months"]:
        out = out + profile_values(clients, shifts["shift"])
    drift = seasons["drift"]
    if key == drift["trend_product"]:
        months_since = int((month - np.datetime64(spec["first_month"], "M")).astype(int))
        out = out + np.log(drift["wake_odds_per_year"]) * max(months_since, 0) / 12
    return out


def after_bonus(spec: dict, key: str, clients: pd.DataFrame, month: np.datetime64) -> np.ndarray:
    """log(odds) of the bonus trigger in the months right after each client's bonus month.

    Only for the trigger's products and clients with a bonus (`bonus_month` 0 means none).
    """
    trigger = spec["holding_rules"]["bonus_trigger"]
    if key not in trigger["products"]:
        return np.zeros(len(clients))
    bonus_month = clients["bonus_month"].to_numpy()
    since = (month_of_year(month) - bonus_month) % 12
    after = (bonus_month > 0) & (since >= 1) & (since <= trigger["months_after"])
    return np.log(trigger["odds"]) * after
