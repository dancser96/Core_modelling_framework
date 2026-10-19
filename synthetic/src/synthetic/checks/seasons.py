"""Time-effect checks: the summer dip, travel, December, school fees, FX wake-ups and drift.

Each effect is read as a ratio between two months for the same clients (one pair per client: the
month before the effect and a month it applies to), so a client's level and persistent variation
cancel and the ratio is the spec's factor per profile (test_harness.md "Time effects", maths §6).
Card spend is read for transactors below their limit, whose spend is the wanted spend (a
revolver's carried balance and the limit cap it). Months come from the spec's tables, at their
first occurrence in the panel; spring (March–May) carries no seasonal factor. Effects stated as a
direction (FX wake-ups by profile, the digital uptake trend) are one-sided rows.
"""

from datetime import date

import numpy as np
import pandas as pd

from synthetic.checks.events import before, build_panel
from synthetic.checks.table import (
    first_month,
    mean_ratio_row,
    mean_row,
    pair_rows,
    shift_month,
    side_row,
)
from synthetic.spec.presets import LATENTS
from synthetic.spec.products import PROFILE_ORDER

SPRING_MONTHS = (3, 4, 5)  # no seasonal factor, the travel spend's baseline
SCHOOL_MONTH = 9  # the term whose jump is checked (September)
FEE_JUMP_SHARE = 0.5  # payers' mean jump in bills: at least half the expected term fee
TREND_MONTHS = 6  # digital activation: the panel's first 6 months of moves against its last 6
MART_COLUMNS = [
    "client_id", "snapshot_month", "subsegment", "relationship_days",
    *[f"loan_{key}_maturity_months" for key in ("personal", "auto", "home")],
    "casa_active_flag", "cc_flag", "cc_active_flag", "fx_active_flag", "ebanking_flag",
    "digital_active_flag", "casa_bal", "outflow_casa_bills_vol", "cc_utilisation_ratio",
    "spend_cc_vol", "spend_cc_travel_vol", "login_digital_mobile_cnt",
]  # fmt: skip
ORACLE_COLUMNS = ["client_id", "snapshot_month", "school_payer_flag", "revolver_flag"]


def check_seasons(mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict) -> pd.DataFrame:
    """Summer dip, travel, December, school fees, FX wake-ups, drift."""
    spec = truth["spec"]
    panel = build_panel(spec, mart, oracle)
    uncapped = panel["cc_utilisation_ratio"] < 1  # null (no card) compares False
    panel["transactor"] = panel["cc_active_flag"] & ~panel["revolver_flag"] & uncapped
    rows = (
        _check_summer_dip(spec, panel)
        + _check_travel(spec, panel)
        + _check_december(spec, panel)
        + _check_school_fees(spec, panel)
        + _check_fx_wake(spec, panel)
        + _check_drift(spec, panel)
    )
    return pd.DataFrame(rows)


def _check_summer_dip(spec: dict, panel: pd.DataFrame) -> list[dict]:
    """Mean log ratio of casa_bal, July over June, active both months and past the ramp: the log
    of the profile's dip factor (the noise change averages 0)."""
    seasons, ramp = spec["seasons"], len(spec["levels"]["new_client_ramp"])
    july = first_month(panel, seasons["summer_months"][0])
    june = shift_month(july, -1)
    columns = ["profile", "casa_active_flag", "tenure_months", "casa_bal"]
    pairs = pair_rows(panel, june, july, columns)
    ok = (
        pairs["casa_active_flag_0"]
        & pairs["casa_active_flag_1"]
        & (pairs["tenure_months_0"] > ramp)
    )
    log_ratio = np.log(pairs["casa_bal_1"] / pairs["casa_bal_0"])
    rows = []
    for profile, factor in zip(PROFILE_ORDER, seasons["summer"]["casa_bal"], strict=True):
        values = log_ratio[ok & (pairs["profile_0"] == profile)].to_numpy()
        check = f"mean log casa_bal {july:%b} / {june:%b}"
        rows.append(mean_row(check, profile, values, float(np.log(factor))))
    return rows


def _check_travel(spec: dict, panel: pd.DataFrame) -> list[dict]:
    """Travel in summer against spring, per profile.

    Spend per travel month (each client's first travel month in each window, transactors below the
    limit): summer / spring is the summer factor. Share of active card holders with travel spend,
    July against May: the summer / spring ratio of the travel chance, restated from the spec.
    """
    seasons = spec["seasons"]
    july = first_month(panel, seasons["summer_months"][0], history=len(SPRING_MONTHS) + 1)
    summer = [date(july.year, m, 1) for m in seasons["summer_months"]]
    spring = [date(july.year, m, 1) for m in SPRING_MONTHS]
    months = panel["snapshot_month"]
    travelled = panel[panel["transactor"] & (panel["spend_cc_travel_vol"] > 0)]
    first = [
        travelled[travelled["snapshot_month"].isin(window)].drop_duplicates("client_id")
        for window in (summer, spring)
    ]
    held = panel["cc_flag"] & panel["cc_active_flag"]
    columns = ["profile", "spend_cc_travel_vol"]
    travel = [panel.loc[held & (months == m), columns] for m in (july, spring[-1])]
    rows = []
    for profile, factor in zip(PROFILE_ORDER, seasons["summer"]["travel_spend"], strict=True):
        a, b = (df.loc[df["profile"] == profile, "spend_cc_travel_vol"] for df in first)
        check = "mean travel spend per travel month, summer / spring"
        rows.append(mean_ratio_row(check, profile, a, b, factor, paired=False))
    for profile in PROFILE_ORDER:
        a, b = (df.loc[df["profile"] == profile, "spend_cc_travel_vol"] > 0 for df in travel)
        check = f"share of active card holders with travel spend, {july:%b} / {spring[-1]:%b}"
        expected = _travel_chance_ratio(spec, profile)
        rows.append(mean_ratio_row(check, profile, a, b, expected, paired=False))
    return rows


def _travel_chance_ratio(spec: dict, profile: str) -> float:
    """Summer over spring mean travel chance of a profile, restated from the spec: the monthly
    chance × exp(0.5 Δz_crossborder), doubled in summer, capped at 0.95, averaged over the
    profile's Δz ~ N(0, σ²) on a grid (the cap bends the ratio below 2 for travelling profiles)."""
    cfg = spec["levels"]["subcategories"]["travel_months"]
    chance = cfg["chance"][PROFILE_ORDER.index(profile)]
    sd = spec["profiles"][profile]["latent_scale"][LATENTS.index("crossborder")]
    z = np.linspace(-6, 6, 1201)
    weight, tilt = np.exp(-(z**2) / 2), np.exp(cfg["crossborder"] * sd * z)
    doubled = spec["seasons"]["summer"]["travel_chance"] * chance
    summer = np.minimum(cfg["cap"], doubled * tilt) @ weight
    spring = np.minimum(cfg["cap"], chance * tilt) @ weight
    return float(summer / spring)


def _check_december(spec: dict, panel: pd.DataFrame) -> list[dict]:
    """Mean log ratio of card spend other than travel, December over November, for transactors
    below the limit without travel in either month: the log of the profile's December factor."""
    december = spec["seasons"]["december"]
    dec = first_month(panel, december["months"][0])
    nov = shift_month(dec, -1)
    columns = ["profile", "transactor", "spend_cc_vol", "spend_cc_travel_vol"]
    pairs = pair_rows(panel, nov, dec, columns)
    other = [pairs[f"spend_cc_vol_{i}"] - pairs[f"spend_cc_travel_vol_{i}"] for i in (0, 1)]
    no_travel = (pairs["spend_cc_travel_vol_0"] == 0) & (pairs["spend_cc_travel_vol_1"] == 0)
    ok = pairs["transactor_0"] & pairs["transactor_1"] & no_travel & (other[0] > 0) & (other[1] > 0)
    rows = []
    for profile, factor in zip(PROFILE_ORDER, december["card_other_spend"], strict=True):
        mine = ok & (pairs["profile_0"] == profile)
        values = np.log(other[1][mine] / other[0][mine]).to_numpy()
        check = f"mean log card spend other than travel, {dec:%b} / {nov:%b}"
        rows.append(mean_row(check, profile, values, float(np.log(factor))))
    return rows


def _check_school_fees(spec: dict, panel: pd.DataFrame) -> list[dict]:
    """Bills from August to September, active both months: payers jump by at least half the
    expected term fee (the term's share of the profile's annual fee); non-payers' mean log ratio
    is 0."""
    fees = spec["seasons"]["school_fees"]
    share = {int(m): s for m, s in fees["terms"].items()}[SCHOOL_MONTH]  # JSON keys are strings
    sep = first_month(panel, SCHOOL_MONTH)
    aug = shift_month(sep, -1)
    columns = ["profile", "casa_active_flag", "school_payer_flag", "outflow_casa_bills_vol"]
    pairs = pair_rows(panel, aug, sep, columns)
    ok = pairs["casa_active_flag_0"] & pairs["casa_active_flag_1"]
    bills = [pairs[f"outflow_casa_bills_vol_{i}"] for i in (0, 1)]
    payer = pairs["school_payer_flag_0"]
    positive = (bills[0] > 0) & (bills[1] > 0)
    rows = []
    for profile, annual in zip(PROFILE_ORDER, fees["annual_fee"], strict=True):
        mine = ok & (pairs["profile_0"] == profile)
        jump = float((bills[1] - bills[0])[mine & payer].mean()) / (share * annual)
        check = f"payers' mean bills jump {sep:%b} − {aug:%b} / term fee > {FEE_JUMP_SHARE}"
        rows.append(side_row(check, profile, (mine & payer).sum(), FEE_JUMP_SHARE, jump))
        others = mine & ~payer & positive
        values = np.log(bills[1][others] / bills[0][others]).to_numpy()
        check = f"non-payers' mean log bills {sep:%b} / {aug:%b}"
        rows.append(mean_row(check, profile, values, 0.0))
    return rows


def _check_fx_wake(spec: dict, panel: pd.DataFrame) -> list[dict]:
    """The FX active share rises into the summer more for private than for mass clients, whose
    wake-up shift is smaller (the month before the shift against its last month)."""
    months = spec["seasons"]["wake_shifts"]["fx"]["months"]
    last = first_month(panel, max(months), history=len(months))
    start = shift_month(last, -len(months))
    pairs = pair_rows(panel, start, last, ["profile", "fx_active_flag"])
    moved = pairs["fx_active_flag_1"].astype(int) - pairs["fx_active_flag_0"].astype(int)
    rise = moved.groupby(pairs["profile_0"]).mean()
    check = f"FX active share rise {start:%b} → {last:%b}: private − mass > 0"
    gap = float(rise["private"] - rise["mass"])
    return [side_row(check, "private vs mass", len(pairs), 0.0, gap)]


def _check_drift(spec: dict, panel: pd.DataFrame) -> list[dict]:
    """The app relaunch multiplies mobile logins (active users both months, relaunch month over the
    month before); the digital uptake trend raises activation over the panel."""
    drift = spec["seasons"]["drift"]
    year, month = (int(part) for part in drift["app_relaunch_month"].split("-"))
    relaunch = date(year, month, 1)
    previous = shift_month(relaunch, -1)
    columns = ["digital_active_flag", "login_digital_mobile_cnt"]
    pairs = pair_rows(panel, previous, relaunch, columns)
    ok = pairs["digital_active_flag_0"] & pairs["digital_active_flag_1"]
    mobile = [pairs.loc[ok, f"login_digital_mobile_cnt_{i}"].to_numpy() for i in (0, 1)]
    check = f"mean mobile logins of active users, {relaunch:%b %Y} / {previous:%b %Y}"
    factor = drift["mobile_login_factor"]
    rows = [mean_ratio_row(check, "all", mobile[1], mobile[0], factor, paired=True)]
    registered = before(panel, "ebanking_flag", False).astype(bool)
    dormant = ~before(panel, "digital_active_flag", True).astype(bool)
    at_risk = panel["has_prev"].to_numpy() & registered & dormant
    months = sorted(panel["snapshot_month"].unique())
    rates = [
        panel.loc[at_risk & panel["snapshot_month"].isin(window), "digital_active_flag"].mean()
        for window in (months[1 : 1 + TREND_MONTHS], months[-TREND_MONTHS:])
    ]
    check = f"digital activation rate, last {TREND_MONTHS} months / first {TREND_MONTHS} > 1"
    rows.append(side_row(check, "all", at_risk.sum(), 1.0, float(rates[1] / rates[0])))
    return rows
