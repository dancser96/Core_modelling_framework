"""Trap checks: every trap in the trap summary meets its expected behaviour.

`check_traps` builds one table: the traps on the two trap products (credit card: the leaks, the
upstream target, Simpson's reversal; personal loan: the process leak, the shifted column, the rare
level) and the traps on any product (null controls, quality columns, login drift). Targets come
from `events.realised_target`, the checks' own; the oracle enters through its window probabilities
(the ceiling a leak must beat, on its own window) and its monthly opening chances (the rare level).
AUC and correlation rows, which carry a standard error, use one row per client (the panel's
middle month); rules
comparing two scores, event shares and Simpson's signs use every row. The off-by-default switches
are checked in `switches`.
"""

import numpy as np
import pandas as pd

from synthetic.checks.events import (
    BINARY_TARGETS,
    KEYS,
    STANDARD_TARGETS,
    observation_month,
    realised_target,
    to_panel,
    values_at,
)
from synthetic.checks.table import (
    Z_TOL,
    auc,
    fisher_row,
    hanley_se,
    profile_of,
    psi,
    rank_corr,
    row,
    share_row,
    side_row,
    violations_row,
)
from synthetic.truth.oracle import window_probability

NUMERIC_NULL_CONTROLS = [
    "insurance_premium_vol_trap_null_control",
    "branch_visit_cnt_trap_null_control",
]
CATEGORICAL_NULL_CONTROL = "preferred_language_trap_null_control"
NEAR_CONSTANT = "paper_statement_flag_trap_near_constant"
ALL_NULL = "legacy_risk_grade_trap_all_null"
LEAK = "cc_preapproval_score_trap_leak"
CAMPAIGN = "cc_campaign_response_score_trap_leak"
UPSTREAM = "cc_acquire_next_3_months_flag_trap_upstream_target"
APPLICATION = "application_loan_personal_cnt_trap_process_leak"
SHIFTED, SHIFTED_OF = "loan_personal_bal_trap_shifted", "loan_personal_bal"
LOGINS = "login_digital_mobile_cnt"
LOGINS_AVG = "login_digital_mobile_cnt_0_2_months_avg"

# Restated from the trap summary (docs/components/test_harness.md).
LEAK_AUCS = {LEAK: 0.97, CAMPAIGN: 0.875}  # μ = √2 · Φ⁻¹(auc) puts the AUC at Φ(μ / √2) = auc
LEAK_WINDOW = 3  # the leaks and the upstream target look 3 months ahead
APPLIED_BEFORE_OPENING = 0.8
DECLINED_SHARE = 0.3
RARE_LEVEL, RARE_RATE_RATIO = "Ghana", 2.0  # +1.5 log-odds is about × 4.5 at these low rates
NULL_CONTROL_WINDOW = 3
NEAR_CONSTANT_ZEROS = 0.999
DRIFT_FIRST_MONTH = 4  # panel month where the drift reference starts (months 4–15)
DRIFT_PSI_MIN, STABLE_PSI_MAX = 0.25, 0.1
HASH_KEY = "trap-null-halves"  # 16 characters, as pandas' hash needs: splits clients in halves

TRAP_COLUMNS = [*NUMERIC_NULL_CONTROLS, CATEGORICAL_NULL_CONTROL, NEAR_CONSTANT, ALL_NULL]
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
OWN_COLUMNS += [LOGINS, LOGINS_AVG, LEAK, CAMPAIGN, UPSTREAM, APPLICATION, SHIFTED, SHIFTED_OF]
MART_COLUMNS = list(dict.fromkeys([*KEYS, *OWN_COLUMNS, *TARGET_COLUMNS, *TRAP_COLUMNS]))
# The opening chance (rare level) and what `oracle.window_probability` reads for cc_acquire and
# loan_personal_open (`score_<product>` and the loan slots).
ORACLE_COLUMNS = [*KEYS, "p_loan_personal_open", "score_cc", "score_loan_personal"]
ORACLE_COLUMNS += [f"loan_personal_remaining_{slot}" for slot in range(1, 5)]


def check_traps(mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict) -> pd.DataFrame:
    """Every trap of the trap summary except the off-by-default switches."""
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
        + _check_shifted(panel, loan_chance)
        + _check_rare_level(truth["spec"], panel)
        + _check_simpson(truth["spec"], panel, card_chance)
        + _check_null_controls(panel, at_obs)
        + _check_quality(panel, at_obs)
        + _check_drift(truth["spec"], panel, month)
    )
    return pd.DataFrame(rows)


def _window_probability(
    mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict, target: str, w: int
) -> pd.Series:
    """The oracle's window probability for `target`, checked to line up with the mart's rows."""
    chance = window_probability(mart, oracle, truth, target, w)
    if not chance.index.equals(mart.index):
        raise ValueError(f"window_probability({target}, {w}) is not aligned with the mart")
    return chance.astype("float64")


def _check_leak(
    panel: pd.DataFrame, target: pd.Series, chance: pd.Series, at_obs: np.ndarray
) -> list[dict]:
    """The calibrated leaks: each at its AUC for card acquisition in 3 months, above the oracle's
    on that window (the moderate one only just), and with noise independent of the other's.

    The oracle's AUC is NaN, and its rows fail, if it has no chance where the target is set.
    """
    use = at_obs & target.notna().to_numpy()
    y = target[use].to_numpy() == 1
    stratum, oracle_auc = f"w={LEAK_WINDOW}, one month", auc(chance[use], y)
    rows = []
    for column, expected in LEAK_AUCS.items():
        realised = auc(panel.loc[use, column], y)
        tolerance = Z_TOL * hanley_se(expected, y.sum(), (~y).sum())
        check = f"leak {column}: AUC for cc_acquire"
        rows.append(row(check, stratum, use.sum(), expected, realised, tolerance))
        check = f"leak {column}: AUC above the oracle's"
        rows.append(side_row(check, stratum, use.sum(), oracle_auc, realised))
    # Independent noise: shared noise would let the two leaks' difference separate acquirers.
    calm = use & (target.to_numpy() == 0)
    corr = float(np.corrcoef(panel.loc[calm, LEAK], panel.loc[calm, CAMPAIGN])[0, 1])
    check = "leaks: correlation among non-acquirers (independent noise)"
    rows.append(fisher_row(check, stratum, calm.sum(), 0.0, corr))
    return rows


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


def _check_shifted(panel: pd.DataFrame, chance: pd.Series) -> list[dict]:
    """The shifted column holds its real column's next month (null without a next month), and
    beats the oracle for personal-loan openings next month."""
    shifted = panel[SHIFTED].to_numpy(dtype=float, na_value=np.nan)
    following = values_at(panel, SHIFTED_OF, [1])[:, 0]
    has_next = ~np.isnan(following)
    bad = np.where(has_next, shifted != following, ~np.isnan(shifted))
    target = realised_target(panel, "loan_personal_open", 1)
    known = target.notna().to_numpy()
    y = target[known].to_numpy() == 1
    return [
        violations_row(f"shifted: {SHIFTED} = next month's {SHIFTED_OF}", pd.Series(bad)),
        side_row(
            "shifted: AUC for loan_personal_open (w=1) above the oracle's",
            "all",
            known.sum(),
            auc(chance[known], y),
            auc(shifted[known], y),
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


def _check_null_controls(panel: pd.DataFrame, at_obs: np.ndarray) -> list[dict]:
    """Null controls: AUC 0.5 for every binary standard target (w=3), one month.

    The categorical control is scored by its level's event rate, estimated on the other half of the
    clients (split by a seeded hash of `client_id`), so the rates never see the rows they score.
    """
    hashed = pd.util.hash_pandas_object(panel["client_id"], index=False, hash_key=HASH_KEY)
    first_half = (hashed % 2 == 0).to_numpy()
    level, rows = panel[CATEGORICAL_NULL_CONTROL], []
    for target in BINARY_TARGETS:
        y = realised_target(panel, target, NULL_CONTROL_WINDOW)
        use = at_obs & y.notna().to_numpy()
        rows += [_null_row(target, c, panel.loc[use, c], y[use]) for c in NUMERIC_NULL_CONTROLS]
        fit, score = use & first_half, use & ~first_half
        rates = y[fit].groupby(level[fit]).mean()
        # A level the fitting half never saw gets its overall rate, as a fitted encoder would.
        scores = level[score].map(rates).fillna(y[fit].mean())
        rows.append(_null_row(target, CATEGORICAL_NULL_CONTROL, scores, y[score]))
    return rows


def _null_row(target: str, column: str, scores: pd.Series, y: pd.Series) -> dict:
    """A null control's AUC against 0.5, within Z_TOL Hanley–McNeil standard errors at 0.5."""
    hit = y.to_numpy() == 1
    tolerance = Z_TOL * hanley_se(0.5, hit.sum(), (~hit).sum())
    check = f"null control: AUC for {target} (w={NULL_CONTROL_WINDOW}, one month)"
    return row(check, column, len(hit), 0.5, auc(scores, hit), tolerance)


def _check_quality(panel: pd.DataFrame, at_obs: np.ndarray) -> list[dict]:
    """Quality traps: the near-constant flag is 0 for 99.9% of clients (one month); the all-null
    column is null in every row."""
    flag = panel.loc[at_obs, NEAR_CONSTANT]
    zeros = (flag == 0).sum()
    return [
        share_row(
            "quality: near-constant flag is 0", "one month", NEAR_CONSTANT_ZEROS, zeros, len(flag)
        ),
        violations_row("quality: all-null column holds no value", panel[ALL_NULL].notna()),
    ]


def _check_drift(spec: dict, panel: pd.DataFrame, month: pd.Series) -> list[dict]:
    """Login drift: the PSI of active users' mobile logins after the app relaunch against months
    4 to just before it is above 0.25; within those months (second half vs first) below 0.1.

    PSI bins are the earlier sample's deciles (`table.psi`). Panel months count from 1.
    """
    months = pd.DatetimeIndex(np.sort(month.unique()))
    relaunch = months.get_loc(pd.Timestamp(spec["seasons"]["drift"]["app_relaunch_month"])) + 1
    active = panel["digital_active_flag"].to_numpy() == 1
    logins = pd.Series(
        panel.loc[active, LOGINS].astype("float64").to_numpy(),
        index=months.searchsorted(month[active]) + 1,  # panel month, so slices pick month spans
    ).sort_index()
    mid, last = (DRIFT_FIRST_MONTH + relaunch) // 2, len(months)
    reference = logins.loc[DRIFT_FIRST_MONTH : relaunch - 1].to_numpy()
    after = psi(reference, logins.loc[relaunch + 1 : last].to_numpy())
    early, late = logins.loc[DRIFT_FIRST_MONTH : mid - 1], logins.loc[mid : relaunch - 1]
    stable = psi(early.to_numpy(), late.to_numpy())
    check = "drift: PSI of mobile logins, active users"
    after_span = f"months {relaunch + 1}–{last} vs {DRIFT_FIRST_MONTH}–{relaunch - 1}"
    stable_span = f"months {mid}–{relaunch - 1} vs {DRIFT_FIRST_MONTH}–{mid - 1}"
    return [
        side_row(check, after_span, len(reference), DRIFT_PSI_MIN, after),
        side_row(check, stable_span, len(early), STABLE_PSI_MAX, stable, above=False),
    ]
