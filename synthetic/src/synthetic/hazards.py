"""Each client's monthly chance of adopting, opening, waking up or lapsing, per product.

A chance is `σ(intercept + score)` on the log-odds scale. The score holds everything that makes
clients differ: hidden traits, age, descriptors (e.g. salary transfer) and the half-strict income
threshold. The intercept is set once per product and profile (`calibrate`), on the starting book,
so that the book matches the spec's shares; how long a holding lasts then follows from the spec's
event volume. Products without an onboarding wave build up over each client's months on book from
"never held" at relationship start; `share_held_after` gives the exact chance of each state for the
stepped monthly process, and the starting book is drawn from it, so holdings agree with tenure,
income and traits from the first month. The same functions give the generator its chances and the
oracle its truth.
"""

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.special import expit, logit

from synthetic.presets import LATENTS
from synthetic.products import PROFILE_ORDER


def product_score(
    spec: dict, key: str, clients: pd.DataFrame, z: np.ndarray, age: np.ndarray
) -> np.ndarray:
    """A product's log-odds score per client, before the profile intercept."""
    product, rules = spec["products"][key], spec["holding_rules"]
    loadings = np.array([product.get("traits", {}).get(name, 0.0) for name in LATENTS])
    out = z @ loadings
    age_cfg = product.get("age", {})
    if "slope_per_decade" in age_cfg:
        out = out + age_cfg["slope_per_decade"] * (age - 40) / 10
    if "peak" in age_cfg:
        out = out - age_cfg["curvature"] * ((age - age_cfg["peak"]) / 10) ** 2
    for column, effect in product.get("effects", {}).items():
        out = out + clients[column].map(effect).fillna(0.0).to_numpy()
    if "min_income" in product:
        below = below_threshold(rules, clients, product["min_income"])
        out = out + np.log(rules["below_threshold_odds"]) * below
    return out


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
