"""Digital logins: mobile and online counts, and the days since the last login.

An active digital user logs in a profile's number of times a month (fewer in Private, most in
Mass: half of the Simpson's-reversal trap), × exp(loading × digital deviation); the mobile share
rises with the digital trait and falls with age. Mobile and online counts are each overdispersed,
an active month has at least one login, and from the app relaunch on mobile logins are × the drift
factor (the monitoring trap). Dormant or unregistered clients have no logins. The days since the
last login at month end are a uniform day of the month after a login; dormant months add the days
in the month; a client who never logged in has none (NaN here, null in the mart). Starting-book
clients registered but dormant are taken to have logged in a while before (test_harness.md "FX and
logins").
"""

import numpy as np
import pandas as pd
from scipy.special import expit

from synthetic.mechanisms.seasons import login_drift
from synthetic.mechanisms.variation import draw_counts
from synthetic.spec.presets import LATENTS


def draw_logins(
    spec: dict,
    profiles: np.ndarray,
    channel_factor: np.ndarray,
    digital_dev: np.ndarray,
    age: np.ndarray,
    active: np.ndarray,
    month: np.datetime64,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Mobile and online logins of the month (0 unless active; at least one login if active).

    Draws: mobile counts, online counts, then which channel gets the one login of an active month
    whose counts both came out 0.
    """
    cfg = spec["levels"]["logins"]
    mobile_cfg = cfg["mobile_share"]
    total = (
        np.asarray(cfg["per_month"])[profiles]
        * channel_factor
        * np.exp(cfg["digital_loading"] * digital_dev)
    )
    share = expit(
        mobile_cfg["intercept"]
        + mobile_cfg["digital"] * digital_dev
        + mobile_cfg["age_per_decade"] * (age - mobile_cfg["age_centre"]) / 10
    )
    mobile = draw_counts(rng, total * share * login_drift(spec, month), cfg["gamma_shape"])
    online = draw_counts(rng, total * (1 - share), cfg["gamma_shape"])
    none = (mobile + online) == 0
    on_mobile = rng.random(len(total)) < share
    mobile = mobile + (none & on_mobile)
    online = online + (none & ~on_mobile)
    return np.where(active, mobile, 0), np.where(active, online, 0)


def login_amounts(
    spec: dict,
    last_days: np.ndarray,
    profiles: np.ndarray,
    clients: pd.DataFrame,
    holdings: dict[str, np.ndarray],
    dz: np.ndarray,
    age: np.ndarray,
    month: np.datetime64,
    rng: np.random.Generator,
) -> tuple[np.ndarray, dict[str, object]]:
    """One month of logins: (days since the last login, NaN = never; mart columns, the days as a
    nullable integer)."""
    active = holdings["digital_active"]
    digital_dev = dz[:, LATENTS.index("digital")]
    factor = clients["onboarding_channel"].map(spec["levels"]["logins"]["channel_factor"])
    mobile, online = draw_logins(
        spec, profiles, factor.to_numpy(dtype=float), digital_dev, age, active, month, rng
    )
    days = step_days_since_login(last_days, (mobile + online) > 0, days_in_month(month), rng)
    columns = {
        "login_digital_mobile_cnt": mobile,
        "login_digital_online_cnt": online,
        "days_since_last_login_digital": pd.Series(days).astype("Int64").array,
    }
    return days, columns


def start_days_since_login(
    spec: dict,
    registered: np.ndarray,
    active: np.ndarray,
    month: np.datetime64,
    rng: np.random.Generator,
) -> np.ndarray:
    """Days since the last login for clients drawn now: a day of this month if active, the spec's
    uniform range if registered but dormant, NaN (never logged in) otherwise."""
    low, high = spec["levels"]["logins"]["dormant_start_days"]
    this_month = rng.integers(0, days_in_month(month), len(active))
    before = rng.integers(low, high + 1, len(active))
    days = np.where(active, this_month, np.where(registered, before, np.nan))
    return days.astype(float)


def step_days_since_login(
    last_days: np.ndarray, logged_in: np.ndarray, month_days: int, rng: np.random.Generator
) -> np.ndarray:
    """Days since the last login at month end: a uniform day of the month after a login, else
    last month's + the `month_days` of this month (NaN stays NaN: never logged in)."""
    day = rng.integers(0, month_days, len(last_days))
    return np.where(logged_in, day, last_days + month_days)


def days_in_month(month: np.datetime64) -> int:
    """Number of days in a numpy month."""
    return int(((month + 1).astype("datetime64[D]") - month.astype("datetime64[D]")).astype(int))
