"""Step-3 mix: what the amounts are made of, beyond their levels.

The rows read the shares and relationships behind the amounts (test_harness.md "Subcategories",
"FX and logins", "Segment overlap", "Levels"): the remitter share of non-nationals per profile,
remittance weighing more on mass outflow than on private, cash falling with the digital trait, the
pooled balance–spend rank correlation above the within-subsegment one, logins per active month
rising from private to mass, and the new-client ramp of the current/savings balance. Like
`checks_amount_levels` they use one row per client, from the panel's first May (no seasonal factor,
school fee, bonus or app relaunch), so standard errors are analytical; spec ranges are checked as
ranges and orderings as one-sided rules.
"""

import numpy as np
import pandas as pd

from synthetic.check_stats import (
    first_month,
    fisher_tolerance,
    mean_row,
    rank_corr,
    side_row,
    sorted_panel,
)
from synthetic.check_table import range_row, share_row
from synthetic.checks_amount_levels import REFERENCE_MONTH
from synthetic.presets import LATENTS
from synthetic.products import PROFILE_ORDER

LOGIN_RATIO_REL_TOL = 0.15
MART_COLUMNS = [
    "client_id", "snapshot_month", "subsegment", "nationality_group", "relationship_days",
    *[f"loan_{key}_maturity_months" for key in ("personal", "auto", "home")],
    "casa_active_flag", "cc_flag", "cc_active_flag", "digital_active_flag", "casa_bal",
    "outflow_casa_vol", "outflow_casa_remittance_vol", "outflow_casa_cash_vol",
    "outflow_casa_bills_vol", "spend_cc_vol", "login_digital_mobile_cnt",
    "login_digital_online_cnt",
]  # fmt: skip
ORACLE_COLUMNS = ["client_id", "snapshot_month", "remitter_flag", "z_digital"]


def check_amount_mix(mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict) -> pd.DataFrame:
    """Step 3, mix: pooled vs within subsegments, remittance and cash, the ramp, logins."""
    spec = truth["spec"]
    panel = sorted_panel(spec, mart, oracle)
    at_ref = panel[panel["snapshot_month"] == first_month(panel, REFERENCE_MONTH)]
    rows = (
        _check_pooled(at_ref)
        + _check_remittance(spec, at_ref)
        + _check_ramp(spec, panel)
        + _check_logins(spec, at_ref)
    )
    return pd.DataFrame(rows)


def _check_pooled(at_ref: pd.DataFrame) -> list[dict]:
    """Balance vs card spend among active card holders: the pooled rank correlation is above the
    median within-subsegment one, since subsegments differ in both (segment overlap)."""
    cards = at_ref[at_ref["cc_flag"] & at_ref["cc_active_flag"]]
    pooled = rank_corr(cards["casa_bal"], cards["spend_cc_vol"])
    within = [rank_corr(g["casa_bal"], g["spend_cc_vol"]) for _, g in cards.groupby("subsegment")]
    check = "rank corr casa_bal vs spend_cc_vol: pooled − median within subsegment > 0"
    return [side_row(check, "active card holders", len(cards), 0.0, pooled - np.median(within))]


def _check_remittance(spec: dict, at_ref: pd.DataFrame) -> list[dict]:
    """Remitter shares per profile; remittance weighs more on mass outflow than on private; the
    cash share falls with the digital trait (cash / (cash + bills): free of remittance and of
    booked or own-product transfers, which depend on other things)."""
    cfg = spec["levels"]["subcategories"]["remittance"]
    foreign = at_ref[~at_ref["nationality_group"].isin(cfg["never"])]
    rows = []
    for profile, share in zip(PROFILE_ORDER, cfg["remitter_share"], strict=True):
        flags = foreign.loc[foreign["profile"] == profile, "remitter_flag"]
        check = "remitter share of non-nationals"
        rows.append(share_row(check, profile, share, flags.sum(), len(flags)))
    spending = at_ref[at_ref["casa_active_flag"] & (at_ref["outflow_casa_vol"] > 0)]
    share = spending["outflow_casa_remittance_vol"] / spending["outflow_casa_vol"]
    by_profile = share.groupby(spending["profile"]).mean()
    gap = float(by_profile["mass"] - by_profile["private"])
    check = "mean remittance share of outflow: mass − private > 0"
    rows.append(side_row(check, "mass vs private", len(spending), 0.0, gap))
    mass = spending[spending["profile"] == "mass"]
    cash_and_bills = mass["outflow_casa_cash_vol"] + mass["outflow_casa_bills_vol"]
    mass, cash_and_bills = mass[cash_and_bills > 0], cash_and_bills[cash_and_bills > 0]
    corr = rank_corr(mass["outflow_casa_cash_vol"] / cash_and_bills, mass["z_digital"])
    bound = -fisher_tolerance(len(mass), rank=True)
    check = "rank corr of cash / (cash + bills) with z_digital < −4.5 SE"
    rows.append(side_row(check, "mass", len(mass), bound, corr, above=False))
    return rows


def _casa_season(spec: dict, months: pd.Series, profiles: pd.Series) -> np.ndarray:
    """The spec's seasonal factor of the current/savings balance per row (the summer dip)."""
    seasons = spec["seasons"]
    factor = np.array(seasons["summer"]["casa_bal"])[profiles.map(PROFILE_ORDER.index).to_numpy()]
    summer = pd.to_datetime(months).dt.month.isin(seasons["summer_months"]).to_numpy()
    return np.where(summer, factor, 1.0)


def _check_ramp(spec: dict, panel: pd.DataFrame) -> list[dict]:
    """New clients' balance in their first month against their third, active both, season taken
    out: the mean log ratio is log of the ramp's first factor (the noise change averages 0)."""
    columns = ["client_id", "snapshot_month", "profile", "casa_bal"]
    active = panel[panel["casa_active_flag"]]
    first, third = (active.loc[active["tenure_months"] == t, columns] for t in (0, 2))
    pairs = first.merge(third, on=["client_id", "profile"], suffixes=("_1", "_3"))
    first_bal, third_bal = (
        pairs[f"casa_bal{s}"] / _casa_season(spec, pairs[f"snapshot_month{s}"], pairs["profile"])
        for s in ("_1", "_3")
    )
    log_ratio = np.log(first_bal / third_bal)
    expected = np.log(spec["levels"]["new_client_ramp"][0])
    check = "mean log casa_bal month 1 / month 3 on book"
    return [mean_row(check, "new clients", log_ratio.to_numpy(), expected)]


def _check_logins(spec: dict, at_ref: pd.DataFrame) -> list[dict]:
    """Logins per active month rise from private to mass; mass / private is the ratio of the
    spec's means × E[exp(0.4 Δz_digital)] of each profile (lognormal: exp(0.4² σ² / 2))."""
    cfg = spec["levels"]["logins"]
    users = at_ref[at_ref["digital_active_flag"]]
    logins = users["login_digital_mobile_cnt"] + users["login_digital_online_cnt"]
    means = logins.groupby(users["profile"]).mean()[list(PROFILE_ORDER)].to_numpy()
    sd = {p: spec["profiles"][p]["latent_scale"][LATENTS.index("digital")] for p in PROFILE_ORDER}
    trait = np.exp(cfg["digital_loading"] ** 2 / 2 * (sd["mass"] ** 2 - sd["private"] ** 2))
    expected = cfg["per_month"][-1] / cfg["per_month"][0] * trait
    low, high = (1 - LOGIN_RATIO_REL_TOL) * expected, (1 + LOGIN_RATIO_REL_TOL) * expected
    step, ratio = float(np.log(means[1:] / means[:-1]).min()), float(means[-1] / means[0])
    check = "logins per active month: smallest log step private → mass > 0"
    return [
        side_row(check, "all", len(users), 0.0, step),
        range_row("logins per active month, mass / private", "mass", len(users), low, high, ratio),
    ]
