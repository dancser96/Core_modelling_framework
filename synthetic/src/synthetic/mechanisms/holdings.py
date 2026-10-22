"""Holdings month by month: each client's chances, and what it holds, opens, loses and uses.

Chances. A chance is `σ(intercept + score)` on the log-odds scale (`product_score`): hidden traits,
age, descriptors (e.g. salary transfer), the half-strict income threshold and, given a month, the
calendar terms (`time_terms`). The intercept is set once per product and profile (`calibrate`), on
the starting book, so that the book matches the spec's shares; how long a holding lasts then
follows from the spec's event volume. `share_held_after` gives the exact chance of each state after
a client's months on book, so the starting book is drawn consistent with tenure, income and traits.

State. A dict of arrays aligned with the client table:
- 0/1 products: `<key>_held`, `<key>_ever` (for never / churned / active), `<key>_gained`;
- loans: `<key>_remaining`, the months left on each account slot (0 is an empty slot);
- usage: `<key>_active`; static products: `<key>_held`, drawn once;
- `onboarding_left`: onboarding months a new client still has.

`start_holdings` draws the starting book (card and e-banking at their steady state, other products
from each client's history) and new clients empty. `step_holdings` moves every product from the
state at the end of last month and returns the chance behind every event plus the state-free
scores and lapse chances the oracle prices windows with. It also moves the regression oracle's
simulated paths, with the state as (clients, paths) arrays. A usage chain that requires a product
is at risk only while it is held. `holding_columns` turns the state into mart columns, plus the
hidden state (revolver chain, loan slots) for the oracle.
"""

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.special import expit, logit

from synthetic.mechanisms.clients import client_age, months_on_book
from synthetic.mechanisms.seasons import after_bonus, wake_shift
from synthetic.spec.presets import LATENTS
from synthetic.spec.products import PROFILE_ORDER


def product_score(
    spec: dict,
    key: str,
    clients: pd.DataFrame,
    z: np.ndarray,
    age: np.ndarray,
) -> np.ndarray:
    """A product's log-odds score per client, before the profile intercept and the time terms.

    `z` is (clients, traits), or (clients, paths, traits) for the regression oracle's paths: the
    client terms then broadcast over the paths (`per_client`).
    """
    product, rules = spec["products"][key], spec["holding_rules"]
    loadings = np.array([product.get("traits", {}).get(name, 0.0) for name in LATENTS])
    out = z @ loadings
    age_cfg = product.get("age", {})
    if "slope_per_decade" in age_cfg:
        out = out + per_client(age_cfg["slope_per_decade"] * (age - 40) / 10, z)
    if "peak" in age_cfg:
        out = out - per_client(age_cfg["curvature"] * ((age - age_cfg["peak"]) / 10) ** 2, z)
    for column, effect in product.get("effects", {}).items():
        out = out + per_client(clients[column].map(effect).fillna(0.0).to_numpy(), z)
    if "min_income" in product:
        below = below_threshold(rules, clients, product["min_income"])
        out = out + per_client(np.log(rules["below_threshold_odds"]) * below, z)
    return out


def per_client(values: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Per-client `values` (clients,) shaped to broadcast against `z`'s path axes: unchanged for
    (clients, traits), a (clients, 1) column for (clients, paths, traits)."""
    return np.reshape(values, (len(values),) + (1,) * (np.ndim(z) - 2))


def time_terms(spec: dict, key: str, clients: pd.DataFrame, month: np.datetime64) -> np.ndarray:
    """Calendar terms on a product's adoption or wake-up log-odds (maths §3).

    Seasonal wake-ups, the uptake trend and the bonus trigger. Lapses, the starting book and the
    calibration leave them out: they move who adopts or wakes up in a month, not how long spells
    last.
    """
    return wake_shift(spec, key, clients, month) + after_bonus(spec, key, clients, month)


def below_threshold(rules: dict, clients: pd.DataFrame, min_income: float) -> np.ndarray:
    """True where a client is below an income threshold; some clients without income are exempt."""
    exempt = rules["income_exempt"]
    no_income = clients["income"].isna().to_numpy()
    is_exempt = (
        clients["profile"].isin(exempt["profiles"]).to_numpy()
        | clients["employment_status"].isin(exempt["employment"]).to_numpy()
    )
    low = (clients["income"] < min_income).to_numpy()
    return low | (no_income & ~is_exempt)


def lapse_chance(spec: dict, key: str, client_score: np.ndarray, score_mean: float) -> np.ndarray:
    """Usage products: the monthly chance an active client goes dormant (lower for keen clients).

    Centred on the starting book's mean score, so a typical client's active spell lasts the
    spec's `mean_active_months`.
    """
    product, rules = spec["products"][key], spec["holding_rules"]
    keenness = rules["lapse_loading"] * (client_score - score_mean)
    return expit(logit(1 / product["mean_active_months"]) - keenness)


def churned_chance(spec: dict, key: str, log_odds: np.ndarray) -> np.ndarray:
    """Adoption chance of a client who held the product before (higher odds for status products)."""
    if not spec["products"][key].get("status"):
        return expit(log_odds)
    return expit(log_odds + np.log(spec["holding_rules"]["churned_odds"]))


def share_held_after(
    chance: np.ndarray, churned: np.ndarray, leave: float, months: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Chance of holding, and of having held but left, after `months` monthly steps from "never".

    The exact solution of the stepped never → held ⇄ churned chain: a never-holder adopts with
    `chance`, a holder leaves with `leave`, a churned client adopts with `churned`.
    """
    stay_never = 1 - chance
    decay = 1 - leave - churned  # how much of the held/churned split carries over each month
    never = stay_never**months
    held = churned * (1 - decay**months) / (1 - decay) + (chance - churned) * (
        never - decay**months
    ) / (stay_never - decay)
    return held, 1 - never - held


def held_at_start(
    spec: dict, key: str, product_calib: dict, log_odds: np.ndarray, months: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Chances of holding, and of having held but left, for the starting book."""
    chance, leave = expit(log_odds), product_calib["leave_chance"]
    if spec["products"][key].get("onboarding"):  # reached its steady state at onboarding
        return chance / (chance + leave), np.zeros(len(chance))
    return share_held_after(chance, churned_chance(spec, key, log_odds), leave, months)


def calibrate(
    spec: dict, clients: pd.DataFrame, z: np.ndarray, age: np.ndarray, months: np.ndarray
) -> dict:
    """Intercepts per product and profile, plus each product's derived values, on the starting book.

    The intercepts make the profile's mean equal the spec's share: of the chance of holding after
    each client's months on book (0/1 products; the steady-state share with an onboarding wave), of
    the chance of at least one open loan, or of the steady-state active share (usage; among the
    clients expected to hold the product it requires). `months` counts the monthly steps each
    client has lived, the join month included.
    """
    out, held = {}, {}
    for key, product in spec["products"].items():
        if product["kind"] == "static":
            continue
        client_score = product_score(spec, key, clients, z, age)
        derived = _derived_values(spec, key, client_score)
        weights = held.get(product.get("requires"), np.ones(len(clients)))
        intercept = {}
        for share, name in zip(product["shares"], PROFILE_ORDER, strict=True):
            rows = (clients["profile"] == name).to_numpy()
            if not rows.any():  # no client in this profile, so no new client ever joins it either
                intercept[name] = np.nan
                continue
            args = (share, spec, key, client_score[rows], months[rows], weights[rows], derived)
            intercept[name] = brentq(_calibration_gap, -30, 15, args=args)  # raises if no root
        out[key] = {"intercept": intercept, **derived}
        if product["kind"] == "holding":
            log_odds = clients["profile"].map(intercept).to_numpy() + client_score
            held[key] = held_at_start(spec, key, out[key], log_odds, months)[0]
    return out


def _derived_values(spec: dict, key: str, client_score: np.ndarray) -> dict:
    """Leaving chance (0/1 products) or the starting book's mean score (usage)."""
    product = spec["products"][key]
    if product["kind"] == "holding":
        return {"leave_chance": _leave_chance(spec, product)}
    if product["kind"] == "usage":
        return {"score_mean": float(np.mean(client_score))}
    return {}


def _leave_chance(spec: dict, product: dict) -> float:
    """Monthly leaving chance of a 0/1 product, from its spec volume.

    The spec's adoptions include those refilling the holdings of clients who left the bank
    (holders × exit rate), except with an onboarding wave, where new clients refill them; the rest
    balances the holders who give the product up.
    """
    weights = _profile_weights(spec)
    shares = np.array(product["shares"])
    exit_rates = np.array([spec["profiles"][name]["exit_rate"] for name in PROFILE_ORDER])
    refill = 0.0 if product.get("onboarding") else weights @ (shares * exit_rates)
    rate = product["events_per_100k"] / 100_000 - refill
    if rate <= 0:
        raise ValueError(f"{product['label']}: events_per_100k too low for the book's turnover")
    return rate / (weights @ shares)


def _calibration_gap(
    intercept: float,
    share: float,
    spec: dict,
    key: str,
    client_score: np.ndarray,
    months: np.ndarray,
    weights: np.ndarray,
    derived: dict,
) -> float:
    """Profile mean at this intercept minus the spec's share; `calibrate` finds its root."""
    product = spec["products"][key]
    log_odds = intercept + client_score
    chance = expit(log_odds)
    if product["kind"] == "usage":
        lapse = lapse_chance(spec, key, client_score, derived["score_mean"])
        value = chance / (chance + lapse)
    elif product["kind"] == "loans":
        value = 1 - (1 - chance) ** np.minimum(months, product["term_months"])
    else:
        value = held_at_start(spec, key, derived, log_odds, months)[0]
    return float(np.average(value, weights=weights)) - share


def _profile_weights(spec: dict) -> np.ndarray:
    """Each profile's share of the book (order: PROFILE_ORDER), from the subsegment shares."""
    subs = spec["subsegments"].values()
    return np.array(
        [sum(s["share"] for s in subs if s["profile"] == name) for name in PROFILE_ORDER]
    )


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
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, np.ndarray]]:
    """One month of adoptions, losses, openings, maturities, wake-ups and lapses.

    Every product moves from `before`, the state at the end of the previous month. Returns the new
    state, the chance of each mart-visible event per client (null where not at risk), and the
    oracle's state-free terms (D-064): `score_<key>`, the log-odds without the intercept and the
    state terms (churned odds, onboarding), calendar terms included, and `lapse_<key>`, a usage
    chain's lapse chance before the required product's leaving chance compounds it. With `z` as
    (clients, paths, traits) and the state as (clients, paths) arrays, it moves simulated paths
    (the regression oracle; 0/1 products and usage chains only, `onboarding_left` stays per client).
    """
    age = client_age(clients, month)
    before = state  # arrays are replaced below, never changed in place, so this stays as it was
    state = dict(state, onboarding_left=np.maximum(state["onboarding_left"] - 1, 0))
    chances, scores = {}, {}
    for key, product in spec["products"].items():
        if product["kind"] == "static":
            continue
        u = rng.random(z.shape[:-1])  # one draw per product and client (and path), fixed order
        client_score = product_score(spec, key, clients, z, age)
        time = per_client(time_terms(spec, key, clients, month), z)
        log_odds = per_client(_intercepts(calib[key], clients), z) + client_score + time
        scores[f"score_{key}"] = client_score + time
        if product["kind"] == "holding":
            onboarding = per_client(before["onboarding_left"] > 0, z)
            chances[f"{key}_acquire"] = _step_holding(
                spec, key, before, state, log_odds, onboarding, u, calib
            )
        elif product["kind"] == "loans":
            chances[f"{key}_open"] = _step_loans(product, key, before, state, log_odds, u)
        else:
            lapse = lapse_chance(spec, key, client_score, calib[key]["score_mean"])
            scores[f"lapse_{key}"] = lapse
            activate, lapse = _step_usage(
                spec, key, before, state, expit(log_odds), lapse, u, calib
            )
            chances[f"{key}_activate"], chances[f"{key}_lapse"] = activate, lapse
    return state, chances, scores


def holding_columns(
    spec: dict, state: dict[str, np.ndarray]
) -> tuple[dict[str, object], dict[str, np.ndarray]]:
    """Columns of the current state: for the mart, and the hidden state for the oracle.

    Mart, in the spec's column order (`_mart_order`): flags, statuses (strings), usage flags,
    account counts and months to maturity, then the product count. Usage chains never count as
    products; one with `in_mart` False goes to the oracle instead, as do each loan slot's months
    to maturity (`<loan>_remaining_<slot>`).
    """
    columns, hidden, product_cnt = {}, {}, 0
    for key in _mart_order(spec["products"]):
        product = spec["products"][key]
        if product["kind"] in ("static", "holding"):
            held = state[f"{key}_held"]
            columns[f"{key}_flag"] = held
            if product.get("status"):
                status = np.select([held, state[f"{key}_ever"]], ["active", "churned"], "never")
                columns[f"{key}_status"] = status.astype(object)
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
            # Each slot's months to maturity, for the oracle's window probabilities (0 = empty).
            hidden |= {
                f"{key}_remaining_{i + 1}": remaining[:, i] for i in range(remaining.shape[1])
            }
        else:
            target = columns if product.get("in_mart", True) else hidden
            target[product.get("flag", f"{key}_active_flag")] = state[f"{key}_active"]
    columns["product_cnt"] = np.asarray(product_cnt, dtype=int)
    return columns, hidden


def _mart_order(products: dict) -> list[str]:
    """Product keys in the mart's column order (test_harness.md, "Columns"): each 0/1 product
    followed by the usage chains that require it, then the chains that require none, then loans."""
    chains = {k: p.get("requires") for k, p in products.items() if p["kind"] == "usage"}
    order = []
    for key, product in products.items():
        if product["kind"] in ("static", "holding"):
            order += [key, *[chain for chain, required in chains.items() if required == key]]
    order += [chain for chain, required in chains.items() if required is None]
    order += [key for key, product in products.items() if product["kind"] == "loans"]
    if sorted(order) != sorted(products):
        raise ValueError(f"products without a place in the mart: {set(products) ^ set(order)}")
    return order


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
