"""Holdings and states month by month: what each client holds, opens, loses and uses.

The state is a dict of arrays aligned with the client table:
- 0/1 products: `<key>_held`, `<key>_ever` (ever held here, for never / churned / active) and
  `<key>_gained` (adopted in the latest month);
- loans: `<key>_remaining`, the months left on each account (0 is an empty slot);
- usage: `<key>_active`; static products: `<key>_held`, drawn once;
- `onboarding_left`: onboarding months a new client still has.

The starting book is drawn so that holdings agree with income, traits and tenure from the first
month: credit card and e-banking at the client's steady-state share, other 0/1 products and loans
from the client's history since relationship start (`hazards.held_at_start`, Binomial openings for
loans), usage at its steady state. New clients start without products (usage at its steady state)
and live the same history. Every month `step_holdings` moves all products from the state at the end
of the previous month, with the month's time terms in the scores, and returns the chance behind
every event, for the oracle. Usage chains that require a product are at risk only while it is held
(card activity and the revolver state need a card, current/savings activity the static account).
`holding_columns` turns the state into mart columns, plus the hidden chains for the oracle.
"""

import numpy as np
import pandas as pd
from scipy.special import expit

from synthetic.hazards import (
    churned_chance,
    held_at_start,
    lapse_chance,
    product_score,
    time_terms,
)
from synthetic.population import client_age, months_on_book

STATUS_LEVELS = ["never", "churned", "active"]


def start_holdings(
    spec: dict,
    clients: pd.DataFrame,
    z: np.ndarray,
    month: np.datetime64,
    calib: dict,
    rng: np.random.Generator,
    new_to_bank: bool,
) -> dict[str, np.ndarray]:
    """Holdings of newly drawn clients: the starting book as above, new-to-bank clients empty."""
    n, rules = len(clients), spec["holding_rules"]
    age, months = client_age(clients, month), months_on_book(clients, month)
    state = {"onboarding_left": np.full(n, rules["onboarding_months"] if new_to_bank else 0)}
    for key, product in spec["products"].items():
        u = rng.random(n)  # one draw per product and client, in a fixed order
        if product["kind"] == "static":
            state[f"{key}_held"] = u < product["share"]
            continue
        # Starting states are steady states: no calendar terms (they'd count as permanent history).
        client_score = product_score(spec, key, clients, z, age)
        log_odds = _intercepts(calib[key], clients) + client_score
        if product["kind"] == "holding":
            held, churned = held_at_start(spec, key, calib[key], log_odds, months)
            state[f"{key}_held"] = (u < held) & (not new_to_bank)
            state[f"{key}_ever"] = (u < held + churned) & (not new_to_bank)
            state[f"{key}_gained"] = np.zeros(n, dtype=bool)
        elif product["kind"] == "loans":
            window = np.minimum(months, product["term_months"]) * (not new_to_bank)
            state[f"{key}_remaining"] = _starting_loans(
                rules, product, expit(log_odds), window, rng
            )
        else:
            chance = expit(log_odds)
            lapse = lapse_chance(spec, key, client_score, calib[key]["score_mean"])
            active = u < chance / (chance + lapse)
            if "requires" in product:
                active &= state[f"{product['requires']}_held"]
            state[f"{key}_active"] = active
    return state


def step_holdings(
    spec: dict,
    state: dict[str, np.ndarray],
    clients: pd.DataFrame,
    z: np.ndarray,
    month: np.datetime64,
    calib: dict,
    rng: np.random.Generator,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """One month of adoptions, losses, openings, maturities, wake-ups and lapses.

    Every product moves from `before`, the state at the end of the previous month. Returns the new
    state and the chance of each mart-visible event per client (null where not at risk), which the
    oracle records.
    """
    n, age = len(clients), client_age(clients, month)
    before = state  # arrays are replaced below, never changed in place, so this stays as it was
    state = dict(state, onboarding_left=np.maximum(state["onboarding_left"] - 1, 0))
    chances = {}
    for key, product in spec["products"].items():
        if product["kind"] == "static":
            continue
        u = rng.random(n)  # one draw per product and client, in a fixed order
        client_score = product_score(spec, key, clients, z, age)
        log_odds = (
            _intercepts(calib[key], clients) + client_score + time_terms(spec, key, clients, month)
        )
        if product["kind"] == "holding":
            onboarding = before["onboarding_left"] > 0
            chances[f"{key}_acquire"] = _step_holding(
                spec, key, before, state, log_odds, onboarding, u, calib
            )
        elif product["kind"] == "loans":
            chances[f"{key}_open"] = _step_loans(product, key, before, state, log_odds, u)
        else:
            lapse = lapse_chance(spec, key, client_score, calib[key]["score_mean"])
            activate, lapse = _step_usage(
                spec, key, before, state, expit(log_odds), lapse, u, calib
            )
            chances[f"{key}_activate"], chances[f"{key}_lapse"] = activate, lapse
    return state, chances


def holding_columns(
    spec: dict, state: dict[str, np.ndarray]
) -> tuple[dict[str, object], dict[str, np.ndarray]]:
    """Columns of the current state: for the mart, and the hidden chains' flags for the oracle.

    Mart: flags, statuses, account counts, months to maturity, usage flags, product count. Usage
    chains never count as products; one with `in_mart` False goes to the oracle instead.
    """
    columns, hidden, product_cnt = {}, {}, 0
    for key, product in spec["products"].items():
        if product["kind"] in ("static", "holding"):
            held = state[f"{key}_held"]
            columns[f"{key}_flag"] = held
            if product.get("status"):
                status = np.select([held, state[f"{key}_ever"]], ["active", "churned"], "never")
                columns[f"{key}_status"] = pd.Categorical(status, categories=STATUS_LEVELS)
            if product.get("in_product_count", True):
                product_cnt = product_cnt + held
        elif product["kind"] == "loans":
            remaining = state[f"{key}_remaining"]
            count = (remaining > 0).sum(axis=1)
            nearest = np.where(remaining > 0, remaining, np.inf).min(axis=1)
            columns[f"{key}_cnt"] = count
            # Months until the nearest account matures; null without an account.
            columns[f"{key}_maturity_months"] = (
                pd.Series(nearest).where(count > 0).astype("Int64").array
            )
            product_cnt = product_cnt + (count > 0)
        else:
            target = columns if product.get("in_mart", True) else hidden
            target[product.get("flag", f"{key}_active_flag")] = state[f"{key}_active"]
    columns["product_cnt"] = np.asarray(product_cnt, dtype=int)
    return columns, hidden


def _intercepts(product_calib: dict, clients: pd.DataFrame) -> np.ndarray:
    """Each client's profile intercept for one product."""
    return clients["profile"].map(product_calib["intercept"]).to_numpy(dtype=float)


def _starting_loans(
    rules: dict, product: dict, chance: np.ndarray, window: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """Accounts of the starting book: the openings of the last `window` months.

    At most one account opens a month, so there are Binomial(window, chance) of them (capped at
    the slots), each opened at a uniform time in the window: its months left run from
    term − window + 1 to term.
    """
    term, slots = product["term_months"], rules["max_loan_accounts"]
    count = np.minimum(rng.binomial(window, chance), slots)
    opened_ago = np.floor(rng.random((len(chance), slots)) * window[:, None]).astype(int)
    remaining = term - opened_ago
    remaining[np.arange(slots) >= count[:, None]] = 0
    return remaining


def _step_holding(
    spec: dict,
    key: str,
    before: dict[str, np.ndarray],
    state: dict[str, np.ndarray],
    log_odds: np.ndarray,
    onboarding: np.ndarray,
    u: np.ndarray,
    calib: dict,
) -> np.ndarray:
    """Adopt or lose a 0/1 product (updates `state`); returns each non-holder's adoption chance."""
    rules, leave = spec["holding_rules"], calib[key]["leave_chance"]
    held, ever = before[f"{key}_held"], before[f"{key}_ever"]
    chance = np.where(ever & ~held, churned_chance(spec, key, log_odds), expit(log_odds))
    if spec["products"][key].get("onboarding"):
        # A constant monthly chance that reaches the steady-state share by the onboarding's end.
        steady = chance / (chance + leave)
        onboarding_chance = 1 - (1 - steady) ** (1 / rules["onboarding_months"])
        chance = np.where(onboarding, onboarding_chance, chance)
    gained = ~held & (u < chance)
    lost = held & (u < leave)
    state[f"{key}_held"] = (held & ~lost) | gained
    state[f"{key}_ever"] = ever | gained
    state[f"{key}_gained"] = gained
    return np.where(held, np.nan, chance)


def _step_loans(
    product: dict,
    key: str,
    before: dict[str, np.ndarray],
    state: dict[str, np.ndarray],
    log_odds: np.ndarray,
    u: np.ndarray,
) -> np.ndarray:
    """Close matured accounts, then open at most one (updates `state`); returns opening chances."""
    remaining = np.maximum(before[f"{key}_remaining"] - 1, 0)  # accounts reaching 0 have matured
    chance = expit(log_odds)
    can_open = (remaining == 0).any(axis=1)
    opened = np.flatnonzero(can_open & (u < chance))
    remaining[opened, np.argmax(remaining[opened] == 0, axis=1)] = product["term_months"]
    state[f"{key}_remaining"] = remaining
    return np.where(can_open, chance, np.nan)


def _step_usage(
    spec: dict,
    key: str,
    before: dict[str, np.ndarray],
    state: dict[str, np.ndarray],
    wake: np.ndarray,
    lapse: np.ndarray,
    u: np.ndarray,
    calib: dict,
) -> tuple[np.ndarray, np.ndarray]:
    """Dormant clients may wake up, active ones may lapse (updates `state`).

    A chain that requires a product (digital needs e-banking) is at risk only if the client held
    it at the end of last month, and goes dormant if the client loses it this month; in the month
    after adopting it, the wake chance is the client's steady-state active share. A static product
    (the current/savings account) is never lost or gained. The returned chances price exactly the
    transitions the mart shows, these included.
    """
    active, required = before[f"{key}_active"], spec["products"][key].get("requires")
    if required:
        held_before, held_now = before[f"{required}_held"], state[f"{required}_held"]
        keep = 1.0
        if spec["products"][required]["kind"] != "static":
            keep = 1 - calib[required]["leave_chance"]
            wake = np.where(before[f"{required}_gained"], wake / (wake + lapse), wake)
    else:
        held_before = held_now = np.ones_like(active)
        keep = 1.0
    at_risk = ~active & held_before
    woke = at_risk & (u < wake)
    lapsed = active & (u < lapse)
    state[f"{key}_active"] = ((active & ~lapsed) | woke) & held_now
    return np.where(at_risk, wake * keep, np.nan), np.where(active, 1 - (1 - lapse) * keep, np.nan)
