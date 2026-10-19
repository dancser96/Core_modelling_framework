"""Amounts of the synthetic book: what clients keep, earn, spend and repay, month by month.

Every amount is a median multiple of a hidden base per profile (`spec.amounts.LEVELS`): flows
scale with the true income, balances with the wealth base. `start_amounts` draws each new client's
persistent parts (client effects, AR(1) noise at its stationary start, power-law multipliers) and,
for the starting book, the amounts it already holds (balances, deposit terms, loan principals,
card limits, days since the last login). `step_amounts` runs one month after the holdings have
moved, in this order: noise steps; balances (current/savings, term deposit, wealth with the market
index, loans); the card; the current/savings flows, which book the card repayment and loan
instalments; FX; logins. It returns the new state, the month's mart columns (in the mart's order)
and the hidden oracle columns. The market index (`step_market`) is shared by every client, so it
lives outside the per-client state. Streams: amounts, cards and logins.
"""

import numpy as np
import pandas as pd

from synthetic.mechanisms.accounts import (
    account_flows,
    fx_amounts,
    loan_keys,
    start_balances,
    step_balances,
)
from synthetic.mechanisms.cards import card_amounts, start_card
from synthetic.mechanisms.clients import client_age, profile_codes
from synthetic.mechanisms.logins import login_amounts, start_days_since_login
from synthetic.mechanisms.variation import (
    draw_effects,
    draw_multipliers,
    log_variation,
    measure_offsets,
    measures_of_kind,
    start_noise,
    step_noise,
)
from synthetic.spec.presets import LATENTS


def start_amounts(
    spec: dict,
    clients: pd.DataFrame,
    z: np.ndarray,
    means: np.ndarray,
    holdings: dict[str, np.ndarray],
    month: np.datetime64,
    rngs: dict[str, np.random.Generator],
    new_to_bank: bool,
) -> dict[str, np.ndarray]:
    """Amounts state of newly drawn clients as of `month`, aligned with `clients`.

    The starting book holds its products already: a current/savings balance on its path, deposits
    at a uniform point of their term, loans amortised from their opening, card limits, days since
    the last login. New-to-bank clients hold nothing yet; their first month starts from 0.
    """
    n, levels, rng = len(clients), spec["levels"], rngs["amounts"]
    measures, flow = levels["measures"], levels["flow_noise"]
    stocks = measures_of_kind(spec, "stock")
    n_flows = len(measures_of_kind(spec, "flow"))
    state = {
        "stock_effect": draw_effects(rng, n, np.array([measures[k]["effect_sd"] for k in stocks])),
        "flow_effect": draw_effects(rng, n, np.full(n_flows, flow["effect_sd"])),
        "stock_noise": start_noise(rng, n, np.full(len(stocks), levels["stock_noise"]["sd"])),
        "flow_noise": start_noise(rng, n, np.full(n_flows, flow["sd"])),
        "stock_pareto": draw_multipliers(rng, n, np.array([measures[k]["tail"] for k in stocks])),
    }
    profiles, dz = profile_codes(clients), z - means
    log_parts = log_variation(spec, measure_offsets(spec), state, dz, profiles)
    state |= start_balances(spec, clients, profiles, log_parts, holdings, month, new_to_bank, rng)
    state |= start_card(spec, clients, profiles, dz, holdings, rngs["cards"])
    registered, active = holdings["ebanking_held"], holdings["digital_active"]
    state["login_days"] = start_days_since_login(spec, registered, active, month, rngs["logins"])
    return state


def step_market(spec: dict, index: float, rng: np.random.Generator) -> float:
    """The shared market index after one month's log return (one draw from the amounts stream)."""
    market = spec["levels"]["market"]
    return float(index * np.exp(market["mean"] + market["sd"] * rng.standard_normal()))


def step_amounts(
    spec: dict,
    state: dict[str, np.ndarray],
    clients: pd.DataFrame,
    z: np.ndarray,
    means: np.ndarray,
    holdings: dict[str, np.ndarray],
    month: np.datetime64,
    market: float,
    rngs: dict[str, np.random.Generator],
) -> tuple[dict, dict[str, object], dict[str, np.ndarray]]:
    """One month of amounts from the holdings at its end: (new state, mart columns, oracle columns).

    The current/savings random part comes from the balance's path even in dormant months, so the
    flows keep their link to it. Own-product payments leave the account as outflow transfers.
    """
    levels, rng = spec["levels"], rngs["amounts"]
    state = _step_noises(spec, state, rng)
    profiles, dz = profile_codes(clients), z - means
    log_parts = log_variation(spec, measure_offsets(spec), state, dz, profiles)
    count_tilt = np.exp(levels["counts"]["activity_loading"] * dz[:, LATENTS.index("activity")])
    balance_state, balances = step_balances(
        spec, state, clients, profiles, holdings, log_parts, month, market, rng
    )
    card_state, card = card_amounts(
        spec, state, clients, profiles, holdings, log_parts["spend_cc"], dz, month, count_tilt,
        rngs["cards"],
    )  # fmt: skip
    instalments = [balances[f"instalment_{key}_vol"] for key in loan_keys(spec)]
    payments = card["repayment_cc_vol"] + sum(instalments)
    casa_bal = balances.pop("casa_bal")
    flows = account_flows(
        spec, clients, profiles, log_parts, dz, month, holdings["casa_activity_active"],
        casa_bal - state["casa_bal"], payments, count_tilt, rng,
    )  # fmt: skip
    fx = fx_amounts(
        spec, clients, profiles, log_parts["fx_vol"], month, holdings["fx_active"], count_tilt, rng
    )
    age = client_age(clients, month)
    login_days, logins = login_amounts(
        spec, state["login_days"], profiles, clients, holdings, dz, age, month, rngs["logins"]
    )
    state = state | balance_state | card_state | {"casa_bal": casa_bal, "login_days": login_days}
    mart, oracle = _month_columns(
        spec, state["stock_pareto"], casa_bal, flows, card, balances, fx, logins
    )
    return state, mart, oracle


def _step_noises(
    spec: dict, state: dict[str, np.ndarray], rng: np.random.Generator
) -> dict[str, np.ndarray]:
    """The state after one month of the stocks' and the flows' AR(1) noise."""
    stock, flow = spec["levels"]["stock_noise"], spec["levels"]["flow_noise"]
    return dict(
        state,
        stock_noise=step_noise(state["stock_noise"], stock["rho"], stock["sd"], rng),
        flow_noise=step_noise(state["flow_noise"], flow["rho"], flow["sd"], rng),
    )


def _month_columns(
    spec: dict,
    pareto: np.ndarray,
    casa_bal: np.ndarray,
    flows: dict[str, np.ndarray],
    card: dict[str, np.ndarray],
    balances: dict[str, np.ndarray],
    fx: tuple[np.ndarray, np.ndarray],
    logins: dict[str, object],
) -> tuple[dict[str, object], dict[str, np.ndarray]]:
    """The month's mart columns in the mart's order, and the oracle's power-law multipliers."""
    fx_vol, fx_cnt = fx
    mart = {"casa_bal": casa_bal, **flows, **card, **balances, "fx_vol": fx_vol,
            "fx_cnt": fx_cnt, **logins}  # fmt: skip
    stocks = measures_of_kind(spec, "stock")
    oracle = {f"pareto_{name.removesuffix('_bal')}": pareto[:, j] for j, name in enumerate(stocks)}
    return mart, oracle
