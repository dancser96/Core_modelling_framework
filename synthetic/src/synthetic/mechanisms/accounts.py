"""Balances and the flows through the current/savings account; FX volumes.

Balances (test_harness.md "Amounts", maths §4): each is the spec's median multiple of the client's
wealth base × its random part (`variation.log_variation`). The current/savings balance also carries
the salary-transfer adjustment, the new-client ramp and the summer dip; in a dormant month the
observed balance stays frozen while the path behind it moves on. A term deposit is drawn at
adoption and at each 12-month rollover and stays fixed in between; wealth moves every month with
its own noise and the shared market index. Loans are annuities: a principal drawn when an account
opens, equal instalments from the month after, the outstanding balance summed over the accounts.

Flows follow the balance. Inflow is the salary (with the bonus in the bonus month), transfers and
other non-salary inflow; outflow is the spending (85% of the regular inflow × its own variation),
split into remittance, cash, bills and transfers by monthly Dirichlet shares around the client's
tilted mean shares, plus school fees in bills and the card repayment and loan instalments as
transfers. Whatever the balance moved beyond these is booked as a transfer, in or out, so inflow −
outflow equals the change in the observed balance exactly. Every amount is rounded to the cent and
is exactly 0 without the product or in a dormant month; counts are positive exactly when their
amount is.
"""

import numpy as np
import pandas as pd

from synthetic.mechanisms.clients import months_on_book, profile_values, subsegment_medians
from synthetic.mechanisms.seasons import bonus_due, school_fee_due, season_factor
from synthetic.mechanisms.variation import (
    draw_counts,
    draw_shares,
    draw_transaction_counts,
    measure_level,
    split_amount,
    tilted_shares,
)

INFLOW_PARTS = ("salary", "transfers", "other")  # the inflow subcategories, in the mart's order


def casa_balance(
    spec: dict,
    clients: pd.DataFrame,
    profiles: np.ndarray,
    log_part: np.ndarray,
    months_on_book: np.ndarray,
    month: np.datetime64,
    held: np.ndarray,
    active: np.ndarray,
    last: np.ndarray,
) -> np.ndarray:
    """The observed current/savings monthly average balance.

    Active: the path, level × salary-transfer adjustment × ramp (by months on book) × summer
    dip × exp(log part). Dormant: last month's balance. Without the account: 0. `profiles` are
    PROFILE_ORDER codes.
    """
    levels = spec["levels"]
    transfer = clients["salary_transfer_flag"].to_numpy()
    adjust = np.where(transfer, 1.0, levels["no_salary_transfer"]["casa_bal"])
    ramp_factors = levels["new_client_ramp"]
    ramp = np.ones(len(months_on_book))
    for i, factor in enumerate(ramp_factors):  # months on book 1, 2, …
        ramp = np.where(months_on_book == i + 1, factor, ramp)
    season = season_factor(spec, "casa_bal", profiles, month)
    # An explicit dtype: an empty batch of new clients carries object columns.
    wealth_base = clients["wealth_base"].to_numpy(dtype=float)
    level = measure_level(spec, "casa_bal", profiles, wealth_base) * adjust * ramp * season
    path = np.round(level * np.exp(log_part), 2)
    return np.where(held, np.where(active, path, last), 0.0)


def deposit_balance(
    spec: dict,
    clients: pd.DataFrame,
    profiles: np.ndarray,
    log_part: np.ndarray,
    held: np.ndarray,
    gained: np.ndarray,
    last: np.ndarray,
    months_since_draw: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Term-deposit balance and months since it was drawn.

    Drawn (at least the minimum) at adoption and when a term ends, fixed in between; 0 without a
    deposit. `months_since_draw` is last month's count of held months since the last draw (0 in
    the draw month).
    """
    deposit = spec["levels"]["deposit"]
    since_draw = np.where(held, months_since_draw + 1, 0)
    draw = held & (gained | (since_draw >= deposit["term_months"]))
    level = measure_level(spec, "td_bal", profiles, clients["wealth_base"].to_numpy(dtype=float))
    value = np.maximum(np.round(level * np.exp(log_part), 2), deposit["minimum"])
    balance = np.where(draw, value, np.where(held, last, 0.0))
    return balance, np.where(draw, 0, since_draw)


def wealth_balance(
    spec: dict,
    measure: str,
    clients: pd.DataFrame,
    profiles: np.ndarray,
    log_part: np.ndarray,
    held: np.ndarray,
    market: float,
) -> np.ndarray:
    """Assets under management: level × market index × exp(log part) when held, else 0."""
    level = measure_level(spec, measure, profiles, clients["wealth_base"].to_numpy(dtype=float))
    value = np.round(level * market * np.exp(log_part), 2)
    return np.where(held, value, 0.0)


def draw_principals(spec: dict, key: str, clients: pd.DataFrame, draws: np.ndarray) -> np.ndarray:
    """Loan principals: multiple × true income × exp(sd × draw), the shape of `draws`."""
    loans = spec["levels"]["loans"]
    income = clients["true_income"].to_numpy(dtype=float).reshape(-1, *[1] * (draws.ndim - 1))
    return loans[key]["principal_multiple"] * income * np.exp(loans["principal_sd"] * draws)


def loan_amounts(
    spec: dict,
    key: str,
    remaining: np.ndarray,
    principal: np.ndarray,
    last_principal: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Outstanding balance and instalment of one loan type, summed over the client's accounts.

    Per account slot (n, slots): `remaining` months to maturity now (0 = empty), `principal` of
    the account open now and `last_principal` of the one open at the end of last month (0 =
    none). Instalments are paid by accounts open at the end of last month, one maturing this
    month included; the outstanding balance is the annuity's after j = term − remaining
    instalments (maths §5).
    """
    term = spec["products"][key]["term_months"]
    rate = spec["levels"]["loans"][key]["annual_rate"] / 12
    instalment = (annuity(last_principal, rate, term) * (last_principal > 0)).sum(axis=1)
    growth = (1 + rate) ** (term - remaining)
    owed = principal * growth - annuity(principal, rate, term) * (growth - 1) / rate
    outstanding = np.where(remaining > 0, owed, 0.0).sum(axis=1)
    return np.round(outstanding, 2), np.round(instalment, 2)


def annuity(principal: np.ndarray, rate: float, term: int) -> np.ndarray:
    """Equal monthly instalment that repays `principal` over `term` months at monthly `rate`."""
    return principal * rate / (1 - (1 + rate) ** -term)


def start_balances(
    spec: dict,
    clients: pd.DataFrame,
    profiles: np.ndarray,
    log_parts: dict[str, np.ndarray],
    holdings: dict[str, np.ndarray],
    month: np.datetime64,
    new_to_bank: bool,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """Balance state of newly drawn clients: the starting book's current/savings balance on its
    path, deposits at a uniform point of their term, loan principals of the open accounts; zeros
    for new-to-bank clients. Draws: the deposit phase, then one principal per loan slot."""
    n, none = len(clients), np.zeros(len(clients))
    phase = rng.integers(0, spec["levels"]["deposit"]["term_months"], n)
    slots = spec["holding_rules"]["max_loan_accounts"]
    state = {}
    for key in loan_keys(spec):
        principal = draw_principals(spec, key, clients, rng.standard_normal((n, slots)))
        state[f"{key}_principal"] = np.where(holdings[f"{key}_remaining"] > 0, principal, 0.0)
    held = holdings["casa_held"] & (not new_to_bank)
    tenure = months_on_book(clients, month)
    state["casa_bal"] = casa_balance(
        spec, clients, profiles, log_parts["casa_bal"], tenure, month, held, held, none
    )
    td = holdings["td_held"]
    state["td_bal"] = deposit_balance(
        spec, clients, profiles, log_parts["td_bal"], td, td, none, none
    )[0]
    state["td_months"] = np.where(td, phase, 0)
    return state


def step_balances(
    spec: dict,
    state: dict[str, np.ndarray],
    clients: pd.DataFrame,
    profiles: np.ndarray,
    holdings: dict[str, np.ndarray],
    log_parts: dict[str, np.ndarray],
    month: np.datetime64,
    market: float,
    rng: np.random.Generator,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """One month of balances: (state entries, mart columns, `casa_bal` first).

    `state["casa_bal"]` stays last month's: the flows book the change. Draws: one principal per
    loan type and client, for an account opening now.
    """
    tenure = months_on_book(clients, month)
    casa = casa_balance(
        spec, clients, profiles, log_parts["casa_bal"], tenure, month, holdings["casa_held"],
        holdings["casa_activity_active"], state["casa_bal"],
    )  # fmt: skip
    new, columns = _step_loans(spec, state, clients, holdings, rng)
    new["td_bal"], new["td_months"] = deposit_balance(
        spec, clients, profiles, log_parts["td_bal"], holdings["td_held"], holdings["td_gained"],
        state["td_bal"], state["td_months"],
    )  # fmt: skip
    columns["td_bal"] = new["td_bal"]
    for key in ("wealth_digital", "wealth_trad"):
        held = holdings[f"{key}_held"]
        columns[f"{key}_bal"] = wealth_balance(
            spec, f"{key}_bal", clients, profiles, log_parts[f"{key}_bal"], held, market
        )
    return new, {"casa_bal": casa, **columns}


def loan_keys(spec: dict) -> list[str]:
    """The spec's loan products, in its order."""
    return [key for key, p in spec["products"].items() if p["kind"] == "loans"]


def _step_loans(
    spec: dict,
    state: dict[str, np.ndarray],
    clients: pd.DataFrame,
    holdings: dict[str, np.ndarray],
    rng: np.random.Generator,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Principals of the open accounts (an account opened now gets a new one), and the mart's
    outstanding balances, then instalments, per loan type."""
    keys = loan_keys(spec)
    draws = rng.standard_normal((len(clients), len(keys)))
    principals, balances, instalments = {}, {}, {}
    for i, key in enumerate(keys):
        remaining, last = holdings[f"{key}_remaining"], state[f"{key}_principal"]
        opened = remaining == spec["products"][key]["term_months"]  # opened this month
        new = draw_principals(spec, key, clients, draws[:, i])[:, None]
        principal = np.where(remaining > 0, np.where(opened, new, last), 0.0)
        principals[f"{key}_principal"] = principal
        balance, instalment = loan_amounts(spec, key, remaining, principal, last)
        balances[f"{key}_bal"], instalments[f"instalment_{key}_vol"] = balance, instalment
    return principals, {**balances, **instalments}


def account_flows(
    spec: dict,
    clients: pd.DataFrame,
    profiles: np.ndarray,
    log_parts: dict[str, np.ndarray],
    dz: np.ndarray,
    month: np.datetime64,
    active: np.ndarray,
    change: np.ndarray,
    payments: np.ndarray,
    count_tilt: np.ndarray,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """Inflow and outflow of the month, by subcategory, with counts (mart columns).

    `change` is the observed balance's change since last month, `payments` the card repayment and
    loan instalments, `count_tilt` the activity tilt on count means. Draws: outflow shares, then
    inflow, outflow and remittance counts.
    """
    levels = spec["levels"]
    inflow = _inflow(spec, clients, log_parts["inflow_casa"], month)
    regular = inflow.pop("salary_without_bonus") + inflow.pop("non_salary")
    spending = levels["measures"]["outflow_casa"]["spend_share"] * regular
    spending = spending * np.exp(log_parts["outflow_casa"])
    mean_shares = _outflow_shares(spec, clients, profiles, dz)
    shares = draw_shares(rng, mean_shares, levels["subcategories"]["concentration"])
    parts = split_amount(spending, shares)
    outflow = {name: parts[:, j] for j, name in enumerate(_outflow_names(spec))}
    outflow["bills"] = np.round(outflow["bills"] + school_fee_due(spec, clients, month), 2)
    outflow["transfers"] = np.round(outflow["transfers"] + payments, 2)
    # Whatever the balance moved beyond the flows is booked as a transfer, in or out.
    gap = np.round(change - (sum(inflow.values()) - sum(outflow.values())), 2)
    inflow["transfers"] = np.round(inflow["transfers"] + np.maximum(gap, 0), 2)
    outflow["transfers"] = np.round(outflow["transfers"] + np.maximum(-gap, 0), 2)
    inflow = {name: np.where(active, x, 0.0) for name, x in inflow.items()}
    outflow = {name: np.where(active, x, 0.0) for name, x in outflow.items()}
    return _columns(spec, inflow, outflow, gap > 0, count_tilt, rng)


def fx_amounts(
    spec: dict,
    clients: pd.DataFrame,
    profiles: np.ndarray,
    log_part: np.ndarray,
    month: np.datetime64,
    active: np.ndarray,
    count_tilt: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """FX volume and count: multiple × true income × summer factor × variation, when active."""
    counts = spec["levels"]["counts"]
    level = measure_level(spec, "fx_vol", profiles, clients["true_income"].to_numpy(dtype=float))
    season = season_factor(spec, "fx_vol", profiles, month)
    volume = np.where(active, np.round(level * season * np.exp(log_part), 2), 0.0)
    count = draw_transaction_counts(rng, volume, counts["fx"] * count_tilt, counts["gamma_shape"])
    return volume, count


def _inflow(
    spec: dict, clients: pd.DataFrame, log_part: np.ndarray, month: np.datetime64
) -> dict[str, np.ndarray]:
    """Inflow parts (salary with any bonus, transfers, other), plus the salary without the bonus
    and the non-salary inflow before rounding, which set the spending.

    Non-salary inflow is (multiple − 1) × true income with salary transfer, the no-salary-transfer
    factor × multiple × true income without, × its variation; the "other" share is set by
    employment (plus extra in Private).
    """
    levels = spec["levels"]
    income = clients["true_income"].to_numpy(dtype=float)
    transfer = clients["salary_transfer_flag"].to_numpy()
    multiple = profile_values(clients, levels["measures"]["inflow_casa"]["multiples"])
    factor = np.where(transfer, multiple - 1, levels["no_salary_transfer"]["flows"] * multiple)
    non_salary = factor * income * np.exp(log_part)
    other_share = clients["other_share"].to_numpy(dtype=float)
    parts = split_amount(non_salary, np.stack([1 - other_share, other_share], axis=-1))
    salary = np.round(np.where(transfer, income, 0.0) + bonus_due(spec, clients, month), 2)
    return {
        "salary": salary,
        "transfers": parts[:, 0],
        "other": parts[:, 1],
        "salary_without_bonus": np.where(transfer, income, 0.0),
        "non_salary": non_salary,
    }


def _outflow_shares(
    spec: dict, clients: pd.DataFrame, profiles: np.ndarray, dz: np.ndarray
) -> np.ndarray:
    """Each client's mean spending shares: tilted by traits, remittance only for remitters and
    scaled by nationality group and (income / subsegment median)^elasticity; renormalised.

    A remitter whose nationality group has no factor raises (UAE and GCC nationals never remit,
    so only they have none).
    """
    remit = spec["levels"]["subcategories"]["remittance"]
    shares = tilted_shares(spec, "outflow_casa", profiles, dz)
    relative = clients["true_income"].to_numpy(dtype=float) / subsegment_medians(spec, clients)
    remitter = clients["remitter_flag"].to_numpy(dtype=bool)
    groups = clients["nationality_group"]
    group_factor = groups.map(remit["nationality_factor"]).to_numpy(dtype=float)
    missing = remitter & np.isnan(group_factor)
    if missing.any():
        raise KeyError(f"no remittance factor for remitters of {sorted(set(groups[missing]))}")
    factor = np.where(remitter, group_factor * relative ** remit["income_elasticity"], 0.0)
    column = _outflow_names(spec).index("remittance")
    shares[:, column] = shares[:, column] * factor
    return shares / shares.sum(axis=1, keepdims=True)


def _columns(
    spec: dict,
    inflow: dict[str, np.ndarray],
    outflow: dict[str, np.ndarray],
    booked_in: np.ndarray,
    count_tilt: np.ndarray,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """The mart's flow columns: totals as sums of their parts, and the counts.

    Inflow count: the salary (1) + Poisson + 1 for a booked transfer in, at least 1 with any
    inflow. Outflow count: 1 + Poisson for the outflow other than remittance, plus the
    remittances.
    """
    counts, shape = spec["levels"]["counts"], spec["levels"]["counts"]["gamma_shape"]
    in_count = draw_counts(rng, counts["inflow_casa"] * count_tilt, shape)
    other_out = sum(x for name, x in outflow.items() if name != "remittance")
    out_count = draw_transaction_counts(rng, other_out, counts["outflow_casa"] * count_tilt, shape)
    remittance = outflow["remittance"]
    remitted = draw_transaction_counts(rng, remittance, counts["remittance"] * count_tilt, shape)
    in_total, out_total = np.round(sum(inflow.values()), 2), np.round(sum(outflow.values()), 2)
    in_count = np.maximum((inflow["salary"] > 0) + in_count + booked_in, 1)
    return {
        "inflow_casa_vol": in_total,
        **{f"inflow_casa_{name}_vol": inflow[name] for name in INFLOW_PARTS},
        "inflow_casa_cnt": np.where(in_total > 0, in_count, 0),
        "outflow_casa_vol": out_total,
        **{f"outflow_casa_{name}_vol": x for name, x in outflow.items()},
        "outflow_casa_cnt": out_count + remitted,
        "outflow_casa_remittance_cnt": remitted,
    }


def _outflow_names(spec: dict) -> list[str]:
    """The spending subcategories, in the spec's order."""
    return spec["levels"]["subcategories"]["outflow_casa"]["names"]
