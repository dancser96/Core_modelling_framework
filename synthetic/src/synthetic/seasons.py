"""Time effects of the synthetic book: what changes with the calendar, differently per profile.

Values live in `levels.SEASONS`; the bonus trigger lives in `products.HOLDING_RULES`. This part
shifts products' log-odds scores (test_harness.md maths §3, `time_k,p(t)` and `after_bonus`): FX
wake-ups rise in summer, digital wake-ups trend up from the first panel month (a drift trap), and
a bonus raises term-deposit and wealth adoption odds in the months after it. `hazards.time_terms`
adds them to monthly adoption and wake-up log-odds only: lapses, the starting book and the
calibration leave them out, so shares wobble slightly with the season. On amounts (maths §6): the
seasonal factors per measure and profile (summer dip in balances, summer travel and FX, December
card spend), the chance of a card travel month, the school fees and bonuses due in a month, and the
app relaunch's factor on mobile logins (the drift trap). Functions taking `profiles` (PROFILE_ORDER
codes) work on arrays of any shape, as the regression oracle needs.
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


def season_factor(
    spec: dict, measure: str, profiles: np.ndarray, month: np.datetime64
) -> np.ndarray:
    """A measure's seasonal factor per profile in `month` (1 outside its months).

    Measures are the keys of the spec's seasonal tables: `casa_bal`, `fx_vol` and `travel_spend`
    in summer, `card_other_spend` in December; a measure in no table raises `KeyError` (a typo
    would otherwise mean no season at all).
    """
    seasons, out = spec["seasons"], np.ones(np.shape(profiles))
    tables = [(seasons["summer_months"], seasons["summer"]), (seasons["december"]["months"],
              seasons["december"])]  # fmt: skip
    if not any(measure in table for _, table in tables):
        raise KeyError(f"no seasonal table holds the measure {measure!r}")
    for months, table in tables:
        if month_of_year(month) in months and measure in table:
            out = out * np.asarray(table[measure])[profiles]
    return out


def travel_chance(
    spec: dict, profiles: np.ndarray, crossborder_dev: np.ndarray, month: np.datetime64
) -> np.ndarray:
    """Chance that a month is a card travel month: the profile's base, × 2 in summer,
    × exp(loading × cross-border deviation), capped."""
    cfg = spec["levels"]["subcategories"]["travel_months"]
    chance = np.asarray(cfg["chance"])[profiles]
    if month_of_year(month) in spec["seasons"]["summer_months"]:
        chance = chance * spec["seasons"]["summer"]["travel_chance"]
    return np.minimum(cfg["cap"], chance * np.exp(cfg["crossborder"] * crossborder_dev))


def school_fee_due(spec: dict, clients: pd.DataFrame, month: np.datetime64) -> np.ndarray:
    """School fees paid in `month`: the term's share of each payer's annual fee (0 for others)."""
    share = spec["seasons"]["school_fees"]["terms"].get(month_of_year(month), 0.0)
    return clients["school_fee"].to_numpy(dtype=float) * share


def bonus_due(spec: dict, clients: pd.DataFrame, month: np.datetime64) -> np.ndarray:
    """Bonus paid in `month`: bonus factor × true income in the client's bonus month, else 0."""
    in_month = clients["bonus_month"].to_numpy() == month_of_year(month)
    income = clients["true_income"].to_numpy(dtype=float)
    return np.where(in_month, clients["bonus_factor"].to_numpy(dtype=float) * income, 0.0)


def login_drift(spec: dict, month: np.datetime64) -> float:
    """Factor on mobile logins: the app relaunch's from its month on, 1 before."""
    drift = spec["seasons"]["drift"]
    relaunched = month >= np.datetime64(drift["app_relaunch_month"], "M")
    return drift["mobile_login_factor"] if relaunched else 1.0
