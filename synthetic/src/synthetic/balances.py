"""Balances of the synthetic book: current/savings, term deposit, wealth and loans.

Each balance is the spec's median multiple of the client's wealth base × its random part
(`variation.log_variation`), test_harness.md "Amounts" and maths §4. The current/savings balance
also carries the salary-transfer adjustment, the new-client ramp and the summer dip; in a dormant
month the observed balance stays frozen at its last value while the path behind it moves on. A
term deposit is drawn at adoption and at each 12-month rollover (at least the minimum) and stays
fixed in between; wealth moves every month with its own noise and the shared market index. Loans
are annuities: a principal drawn when an account opens, equal instalments from the month after,
and the outstanding balance after the instalments paid so far, summed over the client's accounts.
Every amount is rounded to the cent and is exactly 0 without the product.
"""

import numpy as np
import pandas as pd

from synthetic.population import months_on_book, profile_values
from synthetic.seasons import season_factor


def stock_level(spec: dict, measure: str, clients: pd.DataFrame) -> np.ndarray:
    """A balance's median per client before its random part: multiple × wealth base."""
    multiples = spec["levels"]["measures"][measure]["multiples"]
    # An explicit dtype: an empty batch of new clients carries object columns.
    return profile_values(clients, multiples) * clients["wealth_base"].to_numpy(dtype=float)


def casa_balance(
    spec: dict,
    clients: pd.DataFrame,
    profiles: np.ndarray,
    log_part: np.ndarray,
    months: np.ndarray,
    month: np.datetime64,
    held: np.ndarray,
    active: np.ndarray,
    last: np.ndarray,
) -> np.ndarray:
    """The observed current/savings monthly average balance.

    Active: the path, level × salary-transfer adjustment × ramp (by `months` on book) × summer
    dip × exp(log part). Dormant: last month's balance. Without the account: 0. `profiles` are
    PROFILE_ORDER codes.
    """
    levels = spec["levels"]
    transfer = clients["salary_transfer_flag"].to_numpy()
    adjust = np.where(transfer, 1.0, levels["no_salary_transfer"]["casa_bal"])
    ramp_factors = levels["new_client_ramp"]
    ramp = np.ones(len(months))
    for i, factor in enumerate(ramp_factors):  # months on book 1, 2, …
        ramp = np.where(months == i + 1, factor, ramp)
    season = season_factor(spec, "casa_bal", profiles, month)
    level = stock_level(spec, "casa_bal", clients) * adjust * ramp * season
    path = np.round(level * np.exp(log_part), 2)
    return np.where(held, np.where(active, path, last), 0.0)


def deposit_balance(
    spec: dict,
    clients: pd.DataFrame,
    log_part: np.ndarray,
    held: np.ndarray,
    gained: np.ndarray,
    last: np.ndarray,
    last_months: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Term-deposit balance and months since it was drawn.

    Drawn (at least the minimum) at adoption and when a term ends, fixed in between; 0 without a
    deposit. `last_months` counts the held months since the last draw (0 in the draw month).
    """
    deposit = spec["levels"]["deposit"]
    months = np.where(held, last_months + 1, 0)
    draw = held & (gained | (months >= deposit["term_months"]))
    value = np.maximum(
        np.round(stock_level(spec, "td_bal", clients) * np.exp(log_part), 2), deposit["minimum"]
    )
    balance = np.where(draw, value, np.where(held, last, 0.0))
    return balance, np.where(draw, 0, months)


def wealth_balance(
    spec: dict,
    measure: str,
    clients: pd.DataFrame,
    log_part: np.ndarray,
    held: np.ndarray,
    market: float,
) -> np.ndarray:
    """Assets under management: level × market index × exp(log part) when held, else 0."""
    value = np.round(stock_level(spec, measure, clients) * market * np.exp(log_part), 2)
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
    months = months_on_book(clients, month)
    state["casa_bal"] = casa_balance(
        spec, clients, profiles, log_parts["casa_bal"], months, month, held, held, none
    )
    td = holdings["td_held"]
    state["td_bal"] = deposit_balance(spec, clients, log_parts["td_bal"], td, td, none, none)[0]
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
    months = months_on_book(clients, month)
    casa = casa_balance(
        spec, clients, profiles, log_parts["casa_bal"], months, month, holdings["casa_held"],
        holdings["casa_activity_active"], state["casa_bal"],
    )  # fmt: skip
    new, columns = _step_loans(spec, state, clients, holdings, rng)
    new["td_bal"], new["td_months"] = deposit_balance(
        spec, clients, log_parts["td_bal"], holdings["td_held"], holdings["td_gained"],
        state["td_bal"], state["td_months"],
    )  # fmt: skip
    columns["td_bal"] = new["td_bal"]
    for key in ("wealth_digital", "wealth_trad"):
        held = holdings[f"{key}_held"]
        columns[f"{key}_bal"] = wealth_balance(
            spec, f"{key}_bal", clients, log_parts[f"{key}_bal"], held, market
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
