"""Step-3 rules for amounts: exact zeros, identities, and the card, loan and deposit mechanics.

Every row is a rule that holds in every client-month (tolerance 0), so the fast suite runs it on
the small preset: zeros for non-holders and dormant users, a card given up this month repaying its
whole last balance and nothing else, subcategories that add up to their totals, the
current/savings booking identity, card interest, repayment and limits, loan balances, the term
deposit's 12-month terms, salary and bonuses, remittance, logins and the days since the last
login, amounts in whole cents. Each rule is restated from the spec (test_harness.md "Amounts",
maths §5) and read from the mart, with the oracle's hidden attributes where the spec defines a rule
through them (true income, bonus month, remitter and revolver flags). "Last month" is the client's
previous row, or nothing held for a new client's first row; rules about last month skip the first
panel month, whose previous month is not in the panel.
"""

import numpy as np
import pandas as pd

from synthetic.check_stats import month_number, sorted_panel
from synthetic.check_table import violations_row
from synthetic.holding_events import before

LOANS = ("loan_personal", "loan_auto", "loan_home")
INFLOW_PARTS = [f"inflow_casa_{s}_vol" for s in ("salary", "transfers", "other")]
OUTFLOW_PARTS = [f"outflow_casa_{s}_vol" for s in ("remittance", "cash", "bills", "transfers")]
SPEND_PARTS = [f"spend_cc_{s}_vol" for s in ("travel", "retail", "online", "dining")]
TOTALS = {"inflow_casa_vol": INFLOW_PARTS, "outflow_casa_vol": OUTFLOW_PARTS,
          "spend_cc_vol": SPEND_PARTS}  # fmt: skip
CASA_FLOWS = [
    "inflow_casa_vol", *INFLOW_PARTS, "inflow_casa_cnt",
    "outflow_casa_vol", *OUTFLOW_PARTS, "outflow_casa_cnt", "outflow_casa_remittance_cnt",
]  # fmt: skip
CARD_FLOWS = ["spend_cc_vol", "spend_cc_cnt", *SPEND_PARTS, "repayment_cc_vol", "interest_cc_vol"]
LOGINS = ["login_digital_mobile_cnt", "login_digital_online_cnt"]
DAYS = "days_since_last_login_digital"
COUNTS = ["inflow_casa_cnt", "outflow_casa_cnt", "outflow_casa_remittance_cnt", "spend_cc_cnt",
          "fx_cnt", *LOGINS]  # fmt: skip
AMOUNTS = [
    "casa_bal", "inflow_casa_vol", *INFLOW_PARTS, "outflow_casa_vol", *OUTFLOW_PARTS,
    "cc_limit", "cc_bal", "spend_cc_vol", *SPEND_PARTS, "repayment_cc_vol", "interest_cc_vol",
    *[f"{key}_bal" for key in LOANS], *[f"instalment_{key}_vol" for key in LOANS],
    "td_bal", "wealth_digital_bal", "wealth_trad_bal", "fx_vol",
]  # fmt: skip
# Amount (count) pairs: a count is positive exactly when its amount is.
COUNTED = [("outflow_casa_remittance_vol", "outflow_casa_remittance_cnt"),
           ("spend_cc_vol", "spend_cc_cnt"), ("fx_vol", "fx_cnt"),
           ("outflow_casa_vol", "outflow_casa_cnt")]  # fmt: skip
SUM_TOL = 0.005  # totals are sums of parts rounded to 0.01; float sums stay well within this
BOOKING_TOL = 0.02  # inflow − outflow against the balance change, after rounding both sides
CENT_TOL = 0.01  # one cent: a salary equal to the true income, a repayment to the last balance
MART_COLUMNS = [
    "client_id", "snapshot_month", "subsegment", "nationality_group", "salary_transfer_flag",
    "relationship_days", "casa_active_flag", "cc_flag", "cc_active_flag", "td_flag",
    "wealth_digital_flag", "wealth_trad_flag", "ebanking_flag", "digital_active_flag",
    "fx_active_flag", *[f"{key}_{kind}" for key in LOANS for kind in ("cnt", "maturity_months")],
    *AMOUNTS, "cc_utilisation_ratio", *COUNTS, DAYS,
]  # fmt: skip
ORACLE_COLUMNS = ["client_id", "snapshot_month", "true_income", "bonus_month", "remitter_flag",
                  "revolver_flag"]  # fmt: skip


def check_amount_rules(mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict) -> pd.DataFrame:
    """Step 3, rules: zeros, identities, card, loan, deposit, salary, remittance and login rules."""
    spec = truth["spec"]
    panel = sorted_panel(spec, mart, oracle)
    rows = (
        _check_card(spec, panel)
        + _check_card_given_up(panel)
        + _check_loans(panel)
        + _check_deposit_and_wealth(spec, panel)
        + _check_casa(panel)
        + _check_salary(spec, panel)
        + _check_remittance_and_counts(spec, panel)
        + _check_digital(panel)
        + _check_units(panel)
    )
    return pd.DataFrame(rows)


def _check_card(spec: dict, panel: pd.DataFrame) -> list[dict]:
    """Zeros without a card, limits on the tiers, utilisation, interest, repayment, dormant spend.

    Rows with no card now nor last month must show nothing: a card given up this month still
    repays its last balance.
    """
    card = spec["levels"]["card"]
    held, active = panel["cc_flag"].to_numpy(), panel["cc_active_flag"].to_numpy()
    held_before = before(panel, "cc_flag", False).astype(bool)
    last_bal = before(panel, "cc_bal", 0.0).astype(float)
    known, has_prev = panel["known"].to_numpy(), panel["has_prev"].to_numpy()
    none = known & ~held & ~held_before
    util = panel["cc_utilisation_ratio"].to_numpy(dtype="float64", na_value=np.nan)
    interest, repayment = panel["interest_cc_vol"], panel["repayment_cc_vol"]
    revolver = panel["revolver_flag"].to_numpy()
    rows = [
        violations_row(f"no card now nor last month: {column} = 0", panel.loc[none, column] != 0)
        for column in ["cc_limit", "cc_bal", *CARD_FLOWS]
    ]
    rate, minimum = card["monthly_interest"], card["minimum_repayment"]
    off_tier = ~panel["cc_limit"][held].isin(card["limit_tiers"])
    too_much = (interest > rate * last_bal + 0.01)[known]
    too_little = (repayment < minimum * last_bal - 0.01)[has_prev & held & held_before]
    rows += [
        violations_row("no card now nor last month: cc_active_flag 0", active[none]),
        violations_row("cc_utilisation_ratio null exactly without a card", np.isnan(util) == held),
        violations_row("cc_limit a product tier when held", off_tier),
        violations_row("0 ≤ cc_utilisation_ratio ≤ 1", ~((util >= 0) & (util <= 1))[held]),
        violations_row(f"interest_cc_vol ≤ {rate} × last cc_bal + 0.01", too_much),
        violations_row("interest_cc_vol > 0 only for revolvers", (interest > 0) & ~revolver),
        violations_row(f"repayment ≥ {minimum} × last cc_bal − 0.01, held both months", too_little),
    ]
    rows += [
        violations_row(f"card dormant: {column} = 0", panel.loc[~active, column] != 0)
        for column in ("spend_cc_vol", "spend_cc_cnt")
    ]
    return rows


def _check_card_given_up(panel: pd.DataFrame) -> list[dict]:
    """A card given up this month (held at the end of last month, not now): no limit, balance,
    spend or interest, and a repayment of its whole last balance."""
    gave_up = before(panel, "cc_flag", False).astype(bool) & ~panel["cc_flag"].to_numpy()
    last_bal = before(panel, "cc_bal", 0.0).astype(float)
    zeros = ["cc_limit", "cc_bal", *[c for c in CARD_FLOWS if c != "repayment_cc_vol"]]
    rows = [
        violations_row(f"card given up this month: {column} = 0", panel.loc[gave_up, column] != 0)
        for column in zeros
    ]
    unpaid = np.abs(panel["repayment_cc_vol"].to_numpy() - last_bal) > CENT_TOL
    check = f"card given up this month: repayment_cc_vol = last cc_bal ±{CENT_TOL}"
    rows.append(violations_row(check, unpaid[gave_up]))
    return rows


def _check_loans(panel: pd.DataFrame) -> list[dict]:
    """Outstanding balance exactly with an account, instalments only with an account now or last
    month, and outstanding falling every month while the count holds (no maturity last month,
    which could hide an opening behind a closure)."""
    known, has_prev, rows = panel["known"].to_numpy(), panel["has_prev"].to_numpy(), []
    for key in LOANS:
        cnt, bal = panel[f"{key}_cnt"].to_numpy(), panel[f"{key}_bal"].to_numpy()
        cnt_before, bal_before = before(panel, f"{key}_cnt", 0), before(panel, f"{key}_bal", 0.0)
        matured = before(panel, f"{key}_maturity_months", np.nan) == 1
        steady = has_prev & (cnt == cnt_before) & (cnt > 0) & ~matured
        none = known & (cnt == 0) & (cnt_before == 0)
        paid = panel[f"instalment_{key}_vol"].to_numpy()[none] != 0
        rows += [
            violations_row(f"{key}_bal 0 exactly when {key}_cnt is 0", (bal == 0) != (cnt == 0)),
            violations_row(f"instalment_{key}_vol 0 with no account now nor last month", paid),
            violations_row(f"{key}_bal falls while the count holds", (bal >= bal_before)[steady]),
        ]
    return rows


def _check_deposit_and_wealth(spec: dict, panel: pd.DataFrame) -> list[dict]:
    """Term deposit: 0 exactly when not held, the minimum when held, fixed within each term;
    wealth: 0 exactly when not held (and never negative, by `_check_units`)."""
    deposit = spec["levels"]["deposit"]
    held, bal = panel["td_flag"].to_numpy(), panel["td_bal"].to_numpy()
    term, minimum = deposit["term_months"], deposit["minimum"]
    rows = [
        violations_row("td_bal 0 exactly when not held", (bal == 0) != ~held),
        violations_row(f"td_bal ≥ {minimum} when held", (bal < minimum)[held]),
        violations_row(f"td_bal changes ≤ once in {term} held months", _early_redraws(panel, term)),
    ]
    for key in ("wealth_digital", "wealth_trad"):
        held, bal = panel[f"{key}_flag"].to_numpy(), panel[f"{key}_bal"].to_numpy()
        rows.append(violations_row(f"{key}_bal 0 exactly when not held", (bal == 0) != ~held))
    return rows


def _early_redraws(panel: pd.DataFrame, term: int) -> np.ndarray:
    """For every change of td_bal within a holding, whether it comes less than `term` months after
    the holding's last draw (its start or its previous change).

    A holding already running at the first panel month started at an unknown time, so its first
    change in the panel is not judged.
    """
    held = panel["td_flag"].to_numpy()
    held_before = before(panel, "td_flag", False).astype(bool)
    changed = held & held_before & (panel["td_bal"].to_numpy() != before(panel, "td_bal", 0.0))
    started = held & ~held_before
    month = month_number(panel["snapshot_month"]).astype(float)
    draws = np.where(changed | started, month, np.nan)
    draws[started & ~panel["known"].to_numpy()] = -np.inf
    last_draw = pd.Series(draws).shift(1).ffill().to_numpy()
    return (month - last_draw < term)[changed]


def _check_casa(panel: pd.DataFrame) -> list[dict]:
    """Dormant months: no flows and a frozen balance; totals equal their parts; the booking
    identity in active months (a new client's first row starts from 0)."""
    active = panel["casa_active_flag"].to_numpy()
    bal, last_bal = panel["casa_bal"].to_numpy(), before(panel, "casa_bal", 0.0).astype(float)
    rows = [
        violations_row(f"current/savings dormant: {column} = 0", panel.loc[~active, column] != 0)
        for column in CASA_FLOWS
    ]
    frozen = (bal != last_bal)[~active & panel["has_prev"].to_numpy()]
    rows.append(violations_row("current/savings dormant: casa_bal = last month's", frozen))
    for total, parts in TOTALS.items():
        gap = (panel[total] - panel[parts].sum(axis=1)).abs()
        rows.append(violations_row(f"{total} = sum of its subcategories ±{SUM_TOL}", gap > SUM_TOL))
    net = (panel["inflow_casa_vol"] - panel["outflow_casa_vol"]).to_numpy()
    booked = np.abs(net - (bal - last_bal)) > BOOKING_TOL
    check = f"inflow − outflow = change in casa_bal ±{BOOKING_TOL}, active months"
    rows.append(violations_row(check, booked[panel["known"].to_numpy() & active]))
    return rows


def _check_salary(spec: dict, panel: pd.DataFrame) -> list[dict]:
    """Salary only with salary transfer: the true income every active month, plus a bonus of
    1–2 × income in the client's bonus month (test_harness.md "Time effects")."""
    salary, income = panel["inflow_casa_salary_vol"], panel["true_income"]
    transfer = panel["salary_transfer_flag"].to_numpy()
    paid = transfer & panel["casa_active_flag"].to_numpy()
    month_of_year = pd.to_datetime(panel["snapshot_month"]).dt.month
    bonus = (panel["bonus_month"] == month_of_year).to_numpy()
    low, high = (1 + f for f in spec["seasons"]["bonus"]["factor_range"])
    outside = (salary - income).abs() > CENT_TOL
    inside = (salary < low * income - CENT_TOL) | (salary > high * income + CENT_TOL)
    return [
        violations_row("salary 0 without salary transfer", salary[~transfer] != 0),
        violations_row("salary = true_income outside the bonus month", outside[paid & ~bonus]),
        violations_row(
            f"salary / true_income in [{low}, {high}] in bonus month", inside[paid & bonus]
        ),
    ]


def _check_remittance_and_counts(spec: dict, panel: pd.DataFrame) -> list[dict]:
    """Remittance only from remitters, never from the spec's excluded nationalities; counts
    positive exactly when their amounts are."""
    never = spec["levels"]["subcategories"]["remittance"]["never"]
    remittance = panel["outflow_casa_remittance_vol"]
    excluded, remitter = panel["nationality_group"].isin(never), panel["remitter_flag"]
    rows = [
        violations_row(f"remittance 0 for {'/'.join(never)} nationals", remittance[excluded] != 0),
        violations_row("remittance 0 when remitter_flag 0", remittance[~remitter] != 0),
    ]
    for amount, count in COUNTED:
        wrong = (panel[count] > 0) != (panel[amount] > 0)
        rows.append(violations_row(f"{count} > 0 exactly when {amount} > 0", wrong))
    return rows


def _check_digital(panel: pd.DataFrame) -> list[dict]:
    """FX volume and logins exactly in active months; days since the last login.

    Days since the last login: below the days in the month when active; growing by the days in the
    month when dormant after a login; null exactly while the client never logged in (in the first
    panel month, whose history is unknown: null only without a login).
    """
    active = panel["digital_active_flag"].to_numpy()
    logins = panel[LOGINS].sum(axis=1).to_numpy()
    days = panel[DAYS].to_numpy(dtype="float64", na_value=np.nan)
    last_days = np.where(panel["has_prev"], np.roll(days, 1), np.nan)
    month_days = pd.to_datetime(panel["snapshot_month"]).dt.days_in_month.to_numpy()
    known = panel["known"].to_numpy()
    never = np.isnan(last_days) & ~active
    null_wrong = np.where(known, np.isnan(days) != never, np.isnan(days) & active)
    fx_wrong = (panel["fx_vol"] > 0) != panel["fx_active_flag"]
    registered = panel["ebanking_flag"].to_numpy()
    outside = ~((days >= 0) & (days < month_days))[active]
    not_grown = (days != last_days + month_days)[~active & ~np.isnan(last_days)]
    return [
        violations_row("fx_vol > 0 exactly when fx_active_flag 1", fx_wrong),
        violations_row("logins > 0 exactly when digital_active_flag 1", (logins > 0) != active),
        violations_row("logins 0 when ebanking_flag 0", (logins != 0)[~registered]),
        violations_row(f"{DAYS} in [0, days in month) when active", outside),
        violations_row(f"{DAYS} grows by the days in the month when dormant", not_grown),
        violations_row(f"{DAYS} null exactly while never logged in", null_wrong),
    ]


def _check_units(panel: pd.DataFrame) -> list[dict]:
    """Amounts are never negative and in whole cents; counts are whole and never negative.

    Whole cents within float error: a total is the float sum of parts rounded to the cent.
    """
    rows = []
    for column in AMOUNTS:
        x = panel[column].to_numpy(dtype="float64")
        cents = np.abs(x - np.round(x, 2)) <= 1e-9 + 1e-13 * np.abs(x)
        rows.append(violations_row(f"{column} ≥ 0 in whole cents", ~((x >= 0) & cents)))
    for column in [*COUNTS, DAYS]:
        x = panel[column].to_numpy(dtype="float64", na_value=np.nan)
        x = x[~np.isnan(x)] if column == DAYS else x  # nulls: `_check_digital`
        whole = (x >= 0) & (x == np.floor(x))
        rows.append(violations_row(f"{column} a whole number ≥ 0", ~whole))
    return rows
