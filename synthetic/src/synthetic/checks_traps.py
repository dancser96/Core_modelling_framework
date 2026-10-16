"""Step-5 checks: every planted trap meets its expected behaviour in the spec's trap summary.

`check_traps` builds one table: the traps on the two trap products here (credit card: calibrated
leak, upstream target, Simpson's reversal; personal loan: process leak, rare level), the traps on
any product from `checks_trap_columns` (null controls, quality, login drift). Targets come from
`target_windows`, the checks' own realised targets, never from the generator. The oracle enters
through its window probabilities (the ceiling a leak must beat) and its monthly opening chances
(the rare level). The leak's AUC row, which carries a standard error, uses one row per client (the
panel's middle month). Rules comparing two scores, the event shares and Simpson's signs use every
row: each event's draw is independent, and a rule has no standard error to inflate.
"""

import numpy as np
import pandas as pd

from synthetic.check_stats import auc, hanley_se, rank_corr, side_row
from synthetic.check_table import Z_TOL, profile_of, row, share_row, violations_row
from synthetic.checks_trap_columns import COLUMN_TRAP_MART_COLUMNS, column_trap_rows
from synthetic.target_windows import (
    BINARY_TARGETS,
    KEYS,
    STANDARD_TARGETS,
    observation_month,
    realised_target,
    to_panel,
    values_at,
)

LEAK = "cc_preapproval_score_trap_leak"
UPSTREAM = "cc_acquire_next_3_months_flag_trap_upstream_target"
APPLICATION = "application_loan_personal_cnt_trap_process_leak"
LOGINS_AVG = "login_digital_mobile_cnt_0_2_months_avg"

# Restated from the trap summary (docs/components/test_harness.md) and plan §4.2.
LEAK_AUC = 0.97  # μ = √2 · Φ⁻¹(0.97) puts the AUC at Φ(μ / √2) = 0.97
LEAK_WINDOW = 3  # the leak and the upstream target look 3 months ahead
APPLIED_BEFORE_OPENING = 0.8
DECLINED_SHARE = 0.3
RARE_LEVEL, RARE_RATE_RATIO = "Ghana", 2.0  # +1.5 log-odds is about × 4.5 at these low rates

TARGET_COLUMNS = [c for name in BINARY_TARGETS for c in STANDARD_TARGETS[name]["eligible"]]
TARGET_COLUMNS += [STANDARD_TARGETS[name]["column"] for name in BINARY_TARGETS]
# Tenure (`relationship_days`) and the profile feed the oracle's chances.
OWN_COLUMNS = [
    "subsegment",
    "onboarding_channel",
    "nationality",
    "relationship_days",
    "loan_personal_maturity_months",
]
OWN_COLUMNS += [LOGINS_AVG, LEAK, UPSTREAM, APPLICATION]
MART_COLUMNS = list(
    dict.fromkeys([*KEYS, *OWN_COLUMNS, *TARGET_COLUMNS, *COLUMN_TRAP_MART_COLUMNS])
)
# The opening chance (rare level) and what `oracle.window_probability` reads for cc_acquire and
# loan_personal_open (plan, Stage E: `score_<product>` and the loan slots).
ORACLE_COLUMNS = [*KEYS, "p_loan_personal_open", "score_cc", "score_loan_personal"]
ORACLE_COLUMNS += [f"loan_personal_remaining_{slot}" for slot in range(1, 5)]


def check_traps(mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict) -> pd.DataFrame:
    """Step 5: every trap of the trap summary except the off-by-default switches."""
    panel = to_panel(mart, oracle)
    mart, oracle = panel[mart.columns], panel[oracle.columns]  # sorted, sharing the panel's index
    month = pd.to_datetime(panel["snapshot_month"])
    at_obs = (month == observation_month(panel)).to_numpy()
    card = realised_target(panel, "cc_acquire", LEAK_WINDOW)
    card_chance = _window_probability(mart, oracle, truth, "cc_acquire", LEAK_WINDOW)
    loan_chance = _window_probability(mart, oracle, truth, "loan_personal_open", 1)
    rows = (
        _check_leak(panel, card, card_chance, at_obs)
        + _check_upstream(panel, card, month)
        + _check_process_leak(panel, loan_chance)
        + _check_rare_level(truth["spec"], panel)
        + _check_simpson(truth["spec"], panel, card_chance)
        + column_trap_rows(panel, truth["spec"])
    )
    return pd.DataFrame(rows)


def _window_probability(
    mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict, target: str, w: int
) -> pd.Series:
    """The oracle's window probability for `target`, checked to line up with the mart's rows."""
    # Imported here: the oracle (build stage E) may not exist while the trap checks are written.
    from synthetic.oracle import window_probability

    chance = window_probability(mart, oracle, truth, target, w)
    if not chance.index.equals(mart.index):
        raise ValueError(f"window_probability({target}, {w}) is not aligned with the mart")
    return chance.astype("float64")


def _check_leak(
    panel: pd.DataFrame, target: pd.Series, chance: pd.Series, at_obs: np.ndarray
) -> list[dict]:
    """The calibrated leak: AUC 0.97 for card acquisition in 3 months, and above the oracle's.

    The oracle's AUC is NaN, and the second row fails, if it has no chance where the target is set.
    """
    use = at_obs & target.notna().to_numpy()
    y = target[use].to_numpy() == 1
    stratum = f"w={LEAK_WINDOW}, one month"
    realised = auc(panel.loc[use, LEAK], y)
    tolerance = Z_TOL * hanley_se(LEAK_AUC, y.sum(), (~y).sum())
    return [
        row("leak: AUC for cc_acquire", stratum, use.sum(), LEAK_AUC, realised, tolerance),
        side_row("leak: AUC above the oracle's", stratum, use.sum(), auc(chance[use], y), realised),
    ]


def _check_upstream(panel: pd.DataFrame, target: pd.Series, month: pd.Series) -> list[dict]:
    """The upstream target: the realised target where both are set, 0 for leavers, null exactly
    for holders and the last 3 months.

    A leaver who took the card before leaving is left out: the spec makes such a row both 1 ("taken
    in any of the next 3 months") and 0 ("leavers count as 0").
    """
    upstream = panel[UPSTREAM].astype("float64")
    holder = panel["cc_flag"].to_numpy() == 1
    last = (month >= np.sort(month.unique())[-LEAK_WINDOW]).to_numpy()
    left = ~holder & ~last & target.isna().to_numpy()  # eligible, window inside: a month is missing
    took_card = (values_at(panel, "cc_flag", range(1, LEAK_WINDOW + 1)) == 1).any(axis=1)
    both = upstream.notna() & target.notna()
    return [
        violations_row(
            "upstream: equals the realised cc_acquire (w=3)", (upstream != target)[both]
        ),
        violations_row(
            "upstream: 0 for leavers without a card", (upstream != 0)[left & ~took_card]
        ),
        violations_row(
            "upstream: null exactly for holders and the last 3 months",
            upstream.isna() != (holder | last),
        ),
    ]


def _check_process_leak(panel: pd.DataFrame, chance: pd.Series) -> list[dict]:
    """The process leak: 80% of openings follow an application, 30% of applications are declined,
    and the application count beats the oracle for openings next month."""
    target = realised_target(panel, "loan_personal_open", 1)
    applied = panel[APPLICATION].to_numpy() > 0
    known = target.notna().to_numpy()
    opened = target.to_numpy() == 1
    y = opened[known]
    return [
        share_row(
            "process leak: openings at t+1 with an application at t",
            "all",
            APPLIED_BEFORE_OPENING,
            applied[opened].sum(),
            opened.sum(),
        ),
        share_row(
            "process leak: applications at t declined (no opening at t+1)",
            "all",
            DECLINED_SHARE,
            (applied & known & ~opened).sum(),
            (applied & known).sum(),
        ),
        side_row(
            "process leak: AUC for loan_personal_open (w=1) above the oracle's",
            "all",
            known.sum(),
            auc(chance[known], y),
            auc(panel.loc[known, APPLICATION], y),
        ),
    ]


def _check_rare_level(spec: dict, panel: pd.DataFrame) -> list[dict]:
    """The rare level: Ghana's monthly opening rate over the rest of the same profiles is above 2,
    and matches the same ratio of the oracle's chances.

    Openings are month-on-month count rises; months where an account matures are left out, since
    the maturity can hide the opening. "The rest of the same profiles" is indirect standardisation:
    each Ghana row is set against the other clients' rate in its profile. The tolerance counts the
    Ghana openings' Poisson-binomial spread only; the rest is about 300 times larger.
    """
    before = values_at(panel, "loan_personal_cnt", [-1])[:, 0]
    matured = values_at(panel, "loan_personal_maturity_months", [-1])[:, 0] == 1
    chance = panel["p_loan_personal_open"].astype("float64").to_numpy()
    at_risk = ~np.isnan(before) & ~np.isnan(chance) & ~matured
    df = pd.DataFrame(
        dict(
            profile=profile_of(spec, panel),
            rare=panel["nationality"] == RARE_LEVEL,
            opened=panel["loan_personal_cnt"].to_numpy() > before,
            chance=chance,
        )
    )[at_risk]
    rare = df[df["rare"]]
    rest = df[~df["rare"]].groupby("profile")[["opened", "chance"]].mean().loc[rare["profile"]]
    realised = rare["opened"].sum() / rest["opened"].sum()
    expected = rare["chance"].sum() / rest["chance"].sum()
    spread = np.sqrt((rare["chance"] * (1 - rare["chance"])).sum()) / rest["opened"].sum()
    check = f"rare level: opening rate {RARE_LEVEL} / the rest of the same profiles"
    return [
        side_row(check, "realised above 2", len(rare), RARE_RATE_RATIO, realised),
        row(check, "realised vs the oracle's", len(rare), expected, realised, Z_TOL * spread),
    ]


def _check_simpson(spec: dict, panel: pd.DataFrame, chance: pd.Series) -> list[dict]:
    """Simpson's reversal: mobile logins rise with the oracle's card chance within each
    onboarding channel and fall with it pooled (eligible rows, every month)."""
    use = (panel["cc_flag"].to_numpy() == 0) & chance.notna() & panel[LOGINS_AVG].notna()
    logins, card = panel.loc[use, LOGINS_AVG], chance[use]
    group = panel.loc[use, "onboarding_channel"]
    check = "Simpson: rank correlation of 3-month mobile logins with the cc_acquire chance (w=3)"
    rows = [
        side_row(check, g, (group == g).sum(), 0.0, rank_corr(logins[group == g], card[group == g]))
        for g in spec["onboarding_channel"]["levels"]
    ]
    rows.append(side_row(check, "pooled", use.sum(), 0.0, rank_corr(logins, card), above=False))
    return rows
