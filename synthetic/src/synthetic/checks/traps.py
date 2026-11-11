"""Trap checks: every trap in the trap summary meets its expected behaviour.

`check_traps` builds one table: the traps on the two trap products (credit card: the leaks, one
U-shaped, the missing-value leak, the upstream target, the application status, Simpson's reversal;
personal loan: the rare level; both: a process leak and a shifted column), the deposit rate's
missing-value leak, the card spend leak and the traps on any product (null controls, the
high-cardinality code, constants, the redundant column, low-fill columns, quality columns, login
drift). Targets come from `events.realised_target`, the checks' own; the oracle enters through its
window probabilities (the ceiling a leak must beat, on its own window) and its monthly opening
chances (the rare level). AUC and correlation rows, which carry a standard error, use one row per
client (the panel's middle month); rules comparing two columns, event shares and Simpson's signs
use every row. The monthly control columns are checked in `controls`, the off-by-default switches
in `switches`.
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
    range_row,
    rank_corr,
    row,
    share_row,
    side_row,
    trap_parameters,
    violations_row,
)
from synthetic.truth.oracle import window_probability

NUMERIC_NULL_CONTROLS = [
    "insurance_premium_vol_trap_null_control",
    "branch_visit_cnt_trap_null_control",
    "marketing_consent_flag_trap_null_control",
]
CATEGORICAL_NULL_CONTROLS = [  # the branch code is independent of everything too, so it is one
    "preferred_language_trap_null_control",
    "referral_branch_code_trap_high_cardinality",
]
NEAR_CONSTANT = "paper_statement_flag_trap_near_constant"
ALL_NULL = "legacy_risk_grade_trap_all_null"
LEAK = "cc_preapproval_score_trap_leak"
CAMPAIGN = "cc_campaign_response_score_trap_leak"
MISSING_LEAK = "cc_offer_code_trap_missing_leak"
UPSTREAM = "cc_acquire_next_3_months_flag_trap_upstream_target"
REVIEW_SCORE = "cc_review_score_trap_leak"  # the U-shaped leak
TD_RATE = "td_offer_rate_trap_missing_leak"
CC_APPLICATION = "application_cc_cnt_trap_process_leak"
CC_STATUS = "application_cc_status_trap_process_leak"  # the status of a CC_APPLICATION
SPEND_REVIEW = "cc_spend_review_trap_spend_leak"
# Process leaks: trap column → (the target of its product, the flag whose holders never apply);
# shifted columns, each with the target of its product.
PROCESS_LEAKS = {
    "application_loan_personal_cnt_trap_process_leak": ("loan_personal_open", None),
    CC_APPLICATION: ("cc_acquire", "cc_flag"),
}
SHIFTED_COLUMNS = {  # trap column → (the real column it holds one month on, the target)
    "loan_personal_bal_trap_shifted": ("loan_personal_bal", "loan_personal_open"),
    "cc_limit_trap_shifted": ("cc_limit", "cc_acquire"),
}
REDUNDANT = "relationship_months_trap_redundant"
LOW_FILL_CLIENTS = "loyalty_points_bal_trap_low_fill"  # filled for a share of clients, all months
LOW_FILL_ROWS = "complaint_category_trap_low_fill"  # filled in a share of rows, at random
LOGINS = "login_digital_mobile_cnt"
LOGINS_AVG = "login_digital_mobile_cnt_0_2_months_avg"

# The traps' parameters (AUCs, windows, shares, levels, values) come from the spec rows
# (`trap_parameters`); what is set here is the checks' own: thresholds and the target's window.
LEAK_COLUMNS = [LEAK, CAMPAIGN, REVIEW_SCORE, MISSING_LEAK, UPSTREAM]  # share one window w
RARE_LEVEL_COLUMN, RARE_RATE_RATIO = "nationality", 2.0  # +1.5 log-odds is about × 4.5 at low rates
NULL_CONTROL_WINDOW = 3
CONSTANT_COLUMNS = ["booking_country_trap_constant", "statement_cycle_days_trap_constant"]
REDUNDANT_CORR_MIN, REDUNDANT_AUC_TOL = 0.99, 0.01
DRIFT_FIRST_MONTH = 4  # panel month where the drift reference starts (months 4–15)
DRIFT_PSI_MIN, STABLE_PSI_MAX = 0.25, 0.1
HASH_KEY = "trap-null-halves"  # 16 characters, as pandas' hash needs: splits clients in halves
# Acquirers sit `offset` (the spec's 1) further from the centre on their own side: the value orders
# them at 0.5, the distance at P(|ε₁| + 1 > |ε₂|) for standard normals.
REVIEW_DISTANCE_AUC = 0.885
# Hanley's SE at 0.5 assumes one distribution for both groups; the U shape's is about 1.5× it.
REVIEW_VALUE_AUC_RANGE = (0.45, 0.55)
SPEND_ZERO_SHARE_MIN = 0.90

TRAP_COLUMNS = [*NUMERIC_NULL_CONTROLS, *CATEGORICAL_NULL_CONTROLS, NEAR_CONSTANT, ALL_NULL]
TRAP_COLUMNS += [*CONSTANT_COLUMNS, REDUNDANT, LOW_FILL_CLIENTS, LOW_FILL_ROWS, MISSING_LEAK]
TRAP_COLUMNS += [LEAK, CAMPAIGN, UPSTREAM, *PROCESS_LEAKS, *SHIFTED_COLUMNS]
TRAP_COLUMNS += [REVIEW_SCORE, TD_RATE, CC_STATUS, SPEND_REVIEW]
TARGET_COLUMNS = [c for name in BINARY_TARGETS for c in STANDARD_TARGETS[name]["eligible"]]
TARGET_COLUMNS += [STANDARD_TARGETS[name]["column"] for name in BINARY_TARGETS]
# Tenure (`relationship_days`) and the profile feed the oracle's chances; the card spend feeds
# the spend leak.
OWN_COLUMNS = [
    "subsegment",
    "onboarding_channel",
    "nationality",
    "relationship_days",
    "loan_personal_maturity_months",
    "spend_cc_vol",
]
OWN_COLUMNS += [LOGINS, LOGINS_AVG, *[real for real, _ in SHIFTED_COLUMNS.values()]]
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
    window = _leak_window(truth)
    card = realised_target(panel, "cc_acquire", window)
    card_chance = _window_probability(mart, oracle, truth, "cc_acquire", window)
    next_chance = {  # the oracle's chance of each trap product's event next month (w = 1)
        target: _window_probability(mart, oracle, truth, target, 1)
        for target in ("cc_acquire", "loan_personal_open")
    }
    rows = (
        _check_leak(truth, panel, card, card_chance, at_obs, window)
        + _check_u_leak(truth, panel, card, card_chance, at_obs, window)
        + _check_missing_leak(truth, panel, card, card_chance, at_obs, window)
        + _check_deposit_rate(truth, panel)
        + _check_upstream(truth, panel, card, month, window)
        + _check_process_leak(truth, panel, next_chance)
        + _check_status(truth, panel)
        + _check_spend_leak(truth, panel, at_obs)
        + _check_shifted(panel, next_chance)
        + _check_rare_level(truth, panel)
        + _check_simpson(truth["spec"], panel, card_chance)
        + _check_null_controls(panel, at_obs)
        + _check_constants(truth, panel)
        + _check_redundant(truth, panel, card, at_obs, window)
        + _check_low_fill(truth, panel, at_obs)
        + _check_quality(truth, panel, at_obs)
        + _check_drift(truth["spec"], panel, month)
    )
    return pd.DataFrame(rows)


def _leak_window(truth: dict) -> int:
    """The one window `w` the card leaks, the offer code and the upstream target share (card
    acquisition within `w` months); raises if their spec rows differ."""
    windows = {trap_parameters(truth, column)["w"] for column in LEAK_COLUMNS}
    if len(windows) != 1:
        raise ValueError(f"the card leaks' spec rows have different windows: {sorted(windows)}")
    return windows.pop()


def _window_probability(
    mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict, target: str, w: int
) -> pd.Series:
    """The oracle's window probability for `target`, checked to line up with the mart's rows."""
    chance = window_probability(mart, oracle, truth, target, w)
    if not chance.index.equals(mart.index):
        raise ValueError(f"window_probability({target}, {w}) is not aligned with the mart")
    return chance.astype("float64")


def _check_leak(
    truth: dict,
    panel: pd.DataFrame,
    target: pd.Series,
    chance: pd.Series,
    at_obs: np.ndarray,
    window: int,
) -> list[dict]:
    """The calibrated leaks: each at its AUC for card acquisition in its window, above the
    oracle's on that window (the moderate one only just), and with noise independent of the
    other's.

    The oracle's AUC is NaN, and its rows fail, if it has no chance where the target is set.
    """
    use = at_obs & target.notna().to_numpy()
    y = target[use].to_numpy() == 1
    stratum, oracle_auc = f"w={window}, one month", auc(chance[use], y)
    rows = []
    for column in (LEAK, CAMPAIGN):
        expected = trap_parameters(truth, column)["auc"]
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


def _check_u_leak(
    truth: dict,
    panel: pd.DataFrame,
    target: pd.Series,
    chance: pd.Series,
    at_obs: np.ndarray,
    window: int,
) -> list[dict]:
    """The U-shaped leak: for card acquisition in its window its value orders clients at AUC 0.5
    (within 0.45–0.55) and its distance from the centre at 0.885, above the oracle's AUC on that
    window (one month)."""
    use = at_obs & target.notna().to_numpy()
    y = target[use].to_numpy() == 1
    value = panel.loc[use, REVIEW_SCORE].to_numpy(dtype=float)
    centre = trap_parameters(truth, REVIEW_SCORE)["centre"]
    distance_auc = auc(np.abs(value - centre), y)
    stratum, n = f"w={window}, one month", use.sum()
    check = f"U leak {REVIEW_SCORE}: AUC for cc_acquire"
    return [
        range_row(f"{check} in value order", stratum, n, *REVIEW_VALUE_AUC_RANGE, auc(value, y)),
        row(
            f"{check} by the distance from {centre}",
            stratum,
            n,
            REVIEW_DISTANCE_AUC,
            distance_auc,
            Z_TOL * hanley_se(REVIEW_DISTANCE_AUC, y.sum(), (~y).sum()),
        ),
        side_row(
            f"U leak {REVIEW_SCORE}: AUC by the distance above the oracle's",
            stratum,
            n,
            auc(chance[use], y),
            distance_auc,
        ),
    ]


def _check_missing_leak(
    truth: dict,
    panel: pd.DataFrame,
    target: pd.Series,
    chance: pd.Series,
    at_obs: np.ndarray,
    window: int,
) -> list[dict]:
    """The missing-value leak: filled at the spec's share for the non-holders who take the card
    within its window and at the other's for the other non-holders, never for holders, with one of
    the offer codes; "is filled" beats the oracle for card acquisition on that window.

    Shares pool every row with a known target: the fill is drawn row by row.
    """
    p = trap_parameters(truth, MISSING_LEAK)
    offer_codes = [f"{p['prefix']}{i:02d}" for i in range(1, p["codes"] + 1)]
    code = panel[MISSING_LEAK]
    filled = code.notna().to_numpy()
    holder = panel["cc_flag"].to_numpy() == 1
    known = target.notna().to_numpy()
    acquirer = target.to_numpy() == 1
    groups = {  # group → (its rows, the spec's fill share)
        "acquirers": (known & acquirer, p["fill_acquirers"]),
        "other non-holders": (known & ~acquirer, p["fill_others"]),
    }
    rows = [
        share_row(
            f"missing leak: {MISSING_LEAK} filled among {group} (w={window})",
            "all",
            share,
            (filled & rows_in).sum(),
            rows_in.sum(),
        )
        for group, (rows_in, share) in groups.items()
    ]
    use = at_obs & known
    y = acquirer[use]
    rows += [
        violations_row(f"missing leak: {MISSING_LEAK} null for every holder", code[holder].notna()),
        violations_row(
            f"missing leak: {MISSING_LEAK} one of the offer codes", ~code[filled].isin(offer_codes)
        ),
        side_row(
            f"missing leak: AUC of '{MISSING_LEAK} is filled' for cc_acquire above the oracle's",
            f"w={window}, one month",
            use.sum(),
            auc(chance[use], y),
            auc(filled[use].astype(float), y),
        ),
    ]
    return rows


def _check_deposit_rate(truth: dict, panel: pd.DataFrame) -> list[dict]:
    """The deposit rate's missing-value leak: a rate within the spec's range, null only for
    non-holders who take a deposit within its window inside the panel (so never for holders), and
    for the spec's share of them.

    The share pools every such row: the blank is drawn row by row.
    """
    p = trap_parameters(truth, TD_RATE)
    rate = panel[TD_RATE].to_numpy(dtype=float)
    null = np.isnan(rate)
    holder = panel["td_flag"].to_numpy() == 1
    ahead = values_at(panel, "td_flag", range(1, p["w"] + 1))
    takes = ~holder & (ahead == 1).any(axis=1)
    low, high = p["rate_range"]
    check = f"deposit rate {TD_RATE}"
    taker = f"non-holders taking a deposit within {p['w']} months"
    return [
        violations_row(f"{check}: null only for {taker}", pd.Series(null & ~takes)),
        share_row(
            f"{check}: null among {taker}",
            "all",
            p["blank_share"],
            null[takes].sum(),
            takes.sum(),
        ),
        violations_row(
            f"{check}: values within [{low}, {high}]",
            pd.Series((rate[~null] < low) | (rate[~null] > high)),
        ),
    ]


def _check_upstream(
    truth: dict, panel: pd.DataFrame, target: pd.Series, month: pd.Series, w: int
) -> list[dict]:
    """The upstream target: the realised target where both are set, the spec's value for leavers,
    null exactly for holders and the last w months.

    A leaver who took the card before leaving is left out: the spec makes such a row both 1 ("taken
    in any of the next w months") and the leavers' value.
    """
    leavers = trap_parameters(truth, UPSTREAM)["leavers_without_card"]
    upstream = panel[UPSTREAM].astype("float64")
    holder = panel["cc_flag"].to_numpy() == 1
    last = (month >= np.sort(month.unique())[-w]).to_numpy()
    left = ~holder & ~last & target.isna().to_numpy()  # eligible, window inside: a month is missing
    took_card = (values_at(panel, "cc_flag", range(1, w + 1)) == 1).any(axis=1)
    both = upstream.notna() & target.notna()
    return [
        violations_row(
            f"upstream: equals the realised cc_acquire (w={w})", (upstream != target)[both]
        ),
        violations_row(
            f"upstream: {leavers} for leavers without a card",
            (upstream != leavers)[left & ~took_card],
        ),
        violations_row(
            f"upstream: null exactly for holders and the last {w} months",
            upstream.isna() != (holder | last),
        ),
    ]


def _check_process_leak(
    truth: dict, panel: pd.DataFrame, next_chance: dict[str, pd.Series]
) -> list[dict]:
    """The process leaks: the spec's share of openings (acquisitions) follow an application, the
    spec's share of applications are declined, and the application count beats the oracle for the
    event next month.

    Rows with a known w = 1 target: eligible at t with a next month, so the panel's last month and,
    for the card, holders are left out; a rule says nobody there applies.
    """
    last = (panel["snapshot_month"] == panel["snapshot_month"].max()).to_numpy()
    rows = []
    for column, (target_name, flag) in PROCESS_LEAKS.items():
        p = trap_parameters(truth, column)
        target = realised_target(panel, target_name, 1)
        applied = panel[column].to_numpy() > 0
        known = target.notna().to_numpy()
        opened = target.to_numpy() == 1
        y = opened[known]
        held = (panel[flag].to_numpy() == 1) if flag else np.zeros(len(panel), dtype=bool)
        rows += [
            violations_row(
                f"process leak {column}: none from holders or in the last month",
                pd.Series(applied & (held | last)),
            ),
            share_row(
                f"process leak {column}: {target_name} at t+1 with an application at t",
                "all",
                p["precede_chance"],
                applied[opened].sum(),
                opened.sum(),
            ),
            share_row(
                f"process leak {column}: applications at t declined (no {target_name} at t+1)",
                "all",
                p["declined_share"],
                (applied & known & ~opened).sum(),
                (applied & known).sum(),
            ),
            side_row(
                f"process leak {column}: AUC for {target_name} (w=1) above the oracle's",
                "all",
                known.sum(),
                auc(next_chance[target_name][known], y),
                auc(panel.loc[known, column], y),
            ),
        ]
    return rows


def _check_status(truth: dict, panel: pd.DataFrame) -> list[dict]:
    """The card application's status: approved where the client applied and holds the card next
    month, declined where it applied and does not (or has left), none without an application."""
    applied = panel[CC_APPLICATION].to_numpy() > 0
    card_next = values_at(panel, "cc_flag", [1])[:, 0] == 1
    none, approved, declined = trap_parameters(truth, CC_STATUS)["levels"]
    expected = np.where(applied, np.where(card_next, approved, declined), none)
    check = f"status {CC_STATUS}: {approved} ⇔ applied and the card next month, {declined} ⇔"
    check += f" applied and not, else {none}"
    return [violations_row(check, panel[CC_STATUS] != expected)]


def _check_spend_leak(truth: dict, panel: pd.DataFrame, at_obs: np.ndarray) -> list[dict]:
    """The spend leak: 1 exactly for card holders whose card spend over the next w months (a
    month without a row counts 0) exceeds the spec's threshold, else 0; 0 for more than 90% of the
    holders (one month)."""
    p = trap_parameters(truth, SPEND_REVIEW)
    holder = panel["cc_flag"].to_numpy() == 1
    ahead = values_at(panel, p["of"], range(1, p["w"] + 1))
    expected = holder & (np.nansum(ahead, axis=1) > p["threshold"])
    leak = panel[SPEND_REVIEW].to_numpy()
    held = at_obs & holder
    check = f"spend leak {SPEND_REVIEW}"
    spending = f"a holder spending over {p['threshold']:,} in the next {p['w']} months"
    return [
        violations_row(f"{check}: 1 ⇔ {spending}", pd.Series(leak != expected)),
        side_row(
            f"{check}: share of 0 among holders",
            "one month",
            held.sum(),
            SPEND_ZERO_SHARE_MIN,
            float((leak[held] == 0).mean()),
        ),
    ]


def _check_shifted(panel: pd.DataFrame, next_chance: dict[str, pd.Series]) -> list[dict]:
    """The shifted columns: each holds its real column's next month (null without a next month),
    and beats the oracle for its product's event next month."""
    rows = []
    for column, (real, target_name) in SHIFTED_COLUMNS.items():
        shifted = panel[column].to_numpy(dtype=float, na_value=np.nan)
        following = values_at(panel, real, [1])[:, 0]
        has_next = ~np.isnan(following)
        bad = np.where(has_next, shifted != following, ~np.isnan(shifted))
        target = realised_target(panel, target_name, 1)
        known = target.notna().to_numpy()
        y = target[known].to_numpy() == 1
        rows += [
            violations_row(f"shifted: {column} = next month's {real}", pd.Series(bad)),
            side_row(
                f"shifted {column}: AUC for {target_name} (w=1) above the oracle's",
                "all",
                known.sum(),
                auc(next_chance[target_name][known], y),
                auc(shifted[known], y),
            ),
        ]
    return rows


def _check_rare_level(truth: dict, panel: pd.DataFrame) -> list[dict]:
    """The rare level: its monthly opening rate over the rest of the same profiles is above 2,
    and matches the same ratio of the oracle's chances.

    Openings are month-on-month count rises; months where an account matures are left out, since
    the maturity can hide the opening. "The rest of the same profiles" is indirect standardisation:
    each Ghana row is set against the other clients' rate in its profile. The tolerance counts the
    rare level's openings' Poisson-binomial spread only; the rest is about 300 times larger.
    """
    level = trap_parameters(truth, RARE_LEVEL_COLUMN)["level"]
    before = values_at(panel, "loan_personal_cnt", [-1])[:, 0]
    matured = values_at(panel, "loan_personal_maturity_months", [-1])[:, 0] == 1
    chance = panel["p_loan_personal_open"].astype("float64").to_numpy()
    at_risk = ~np.isnan(before) & ~np.isnan(chance) & ~matured
    df = pd.DataFrame(
        dict(
            profile=profile_of(truth["spec"], panel),
            rare=panel[RARE_LEVEL_COLUMN] == level,
            opened=panel["loan_personal_cnt"].to_numpy() > before,
            chance=chance,
        )
    )[at_risk]
    rare = df[df["rare"]]
    rest = df[~df["rare"]].groupby("profile")[["opened", "chance"]].mean().loc[rare["profile"]]
    realised = rare["opened"].sum() / rest["opened"].sum()
    expected = rare["chance"].sum() / rest["chance"].sum()
    spread = np.sqrt((rare["chance"] * (1 - rare["chance"])).sum()) / rest["opened"].sum()
    check = f"rare level: opening rate {level} / the rest of the same profiles"
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
    """Null controls (the high-cardinality code among them): AUC 0.5 for every binary standard
    target (w=3), one month.

    A categorical control is scored by its level's event rate, estimated on the other half of the
    clients (split by a seeded hash of `client_id`), so the rates never see the rows they score.
    """
    hashed = pd.util.hash_pandas_object(panel["client_id"], index=False, hash_key=HASH_KEY)
    first_half = (hashed % 2 == 0).to_numpy()
    rows = []
    for target in BINARY_TARGETS:
        y = realised_target(panel, target, NULL_CONTROL_WINDOW)
        use = at_obs & y.notna().to_numpy()
        rows += [_null_row(target, c, panel.loc[use, c], y[use]) for c in NUMERIC_NULL_CONTROLS]
        fit, score = use & first_half, use & ~first_half
        for column in CATEGORICAL_NULL_CONTROLS:
            level = panel[column]
            rates = y[fit].groupby(level[fit]).mean()
            # A level the fitting half never saw gets its overall rate, as a fitted encoder would.
            scores = level[score].map(rates).fillna(y[fit].mean())
            rows.append(_null_row(target, column, scores, y[score]))
    return rows


def _null_row(target: str, column: str, scores: pd.Series, y: pd.Series) -> dict:
    """A null control's AUC against 0.5, within Z_TOL Hanley–McNeil standard errors at 0.5."""
    hit = y.to_numpy() == 1
    tolerance = Z_TOL * hanley_se(0.5, hit.sum(), (~hit).sum())
    check = f"null control: AUC for {target} (w={NULL_CONTROL_WINDOW}, one month)"
    return row(check, column, len(hit), 0.5, auc(scores, hit), tolerance)


def _check_constants(truth: dict, panel: pd.DataFrame) -> list[dict]:
    """Constants: each holds its spec's value in every row (a null is a violation too)."""
    values = {c: trap_parameters(truth, c)["value"] for c in CONSTANT_COLUMNS}
    return [
        violations_row(f"constant: {column} = {value!r} in every row", panel[column] != value)
        for column, value in values.items()
    ]


def _check_redundant(
    truth: dict, panel: pd.DataFrame, target: pd.Series, at_obs: np.ndarray, window: int
) -> list[dict]:
    """The redundant column: floor(relationship_days / days per month) in every row, rank
    correlation with the days above 0.99, and the same AUC for card acquisition within 0.01.

    The AUC is direction-agnostic (max(a, 1 − a)): tenure lowers the acquisition chance.
    """
    p = trap_parameters(truth, REDUNDANT)
    of, days_per_month = p["of"], p["days_per_month"]
    days = panel[of].to_numpy(dtype=float)
    months = panel[REDUNDANT].to_numpy(dtype=float, na_value=np.nan)
    use = at_obs & target.notna().to_numpy()
    y = target[use].to_numpy() == 1
    days_auc, months_auc = (_either_way_auc(x[use], y) for x in (days, months))
    return [
        violations_row(
            f"redundant: {REDUNDANT} = floor({of} / {days_per_month}) in every row",
            pd.Series(months != np.floor(days / days_per_month)),
        ),
        side_row(
            f"redundant: rank correlation of {REDUNDANT} with {of}",
            "one month",
            at_obs.sum(),
            REDUNDANT_CORR_MIN,
            rank_corr(panel.loc[at_obs, REDUNDANT], panel.loc[at_obs, of]),
        ),
        row(
            f"redundant: AUC of {REDUNDANT} for cc_acquire equals {of}'s",
            f"w={window}, one month",
            use.sum(),
            days_auc,
            months_auc,
            REDUNDANT_AUC_TOL,
        ),
    ]


def _either_way_auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """The AUC in the column's stronger direction, max(a, 1 − a)."""
    a = auc(scores, labels)
    return max(a, 1 - a)


def _check_low_fill(truth: dict, panel: pd.DataFrame, at_obs: np.ndarray) -> list[dict]:
    """Low-fill columns: the points balance is filled for the spec's share of clients, in all of a
    client's months or none; the complaint category is filled in the spec's share of rows, with
    one of its levels."""
    client_share = trap_parameters(truth, LOW_FILL_CLIENTS)["fill_share"]
    row_share = trap_parameters(truth, LOW_FILL_ROWS)["fill_share"]
    levels = trap_parameters(truth, LOW_FILL_ROWS)["levels"]
    points = panel[LOW_FILL_CLIENTS].notna()
    per_client = points.groupby(panel["client_id"]).agg(["any", "all"])
    complaint = panel[LOW_FILL_ROWS]
    filled = complaint.notna()
    return [
        share_row(
            f"low fill: {LOW_FILL_CLIENTS} clients with a value",
            "one month",
            client_share,
            points[at_obs].sum(),
            at_obs.sum(),
        ),
        violations_row(
            f"low fill: {LOW_FILL_CLIENTS} filled in all of a client's months or none",
            per_client["any"] & ~per_client["all"],
        ),
        share_row(
            f"low fill: {LOW_FILL_ROWS} rows filled",
            "all",
            row_share,
            filled.sum(),
            len(filled),
        ),
        violations_row(
            f"low fill: {LOW_FILL_ROWS} one of its {len(levels)} levels",
            ~complaint[filled].isin(levels),
        ),
    ]


def _check_quality(truth: dict, panel: pd.DataFrame, at_obs: np.ndarray) -> list[dict]:
    """Quality traps: the near-constant flag is 0 for the spec's share of clients (one month); the
    all-null column is null in every row."""
    share_zero = trap_parameters(truth, NEAR_CONSTANT)["share_zero"]
    flag = panel.loc[at_obs, NEAR_CONSTANT]
    zeros = (flag == 0).sum()
    return [
        share_row("quality: near-constant flag is 0", "one month", share_zero, zeros, len(flag)),
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
