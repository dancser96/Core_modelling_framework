"""The credit card's amounts: limit, wanted spend, and the month's step from balance to balance.

A limit is set when the card is taken: the largest product tier at or below the profile's multiple
× true income (at least the lowest tier), one tier up or down for a few new cards by the credit
trait. The wanted spend is a flow (`variation.log_variation`) split into travel, retail, online and
dining by monthly Dirichlet shares around the client's tilted mean shares; travel happens only in
travel months, and the summer and December factors multiply the travel and the other parts (so the
total rises with them). `step_card` then caps the spend at the room left under the limit and moves
the month-end balance (test_harness.md "Credit card", maths §5): a transactor repays last month's
balance in full; a revolver repays its share of it, carries the rest and pays interest on what it
carried; a card given up repays its whole balance and ends at 0. `wanted_spend` and `step_card`
work on arrays of any matching shape and take no pandas objects, so the regression oracle can run
them on (clients, paths) arrays.
"""

import numpy as np
import pandas as pd

from synthetic.population import profile_values
from synthetic.presets import LATENTS
from synthetic.seasons import season_factor, travel_chance
from synthetic.variation import draw_counts, draw_shares, split_amount, tilted_shares

TRAVEL = "travel"  # the card subcategory that happens only in travel months


def draw_limits(
    spec: dict, clients: pd.DataFrame, credit_dev: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """A limit tier for every client, for those taking a card now (one draw per client)."""
    card = spec["levels"]["card"]
    tiers = np.asarray(card["limit_tiers"], dtype=float)
    target = profile_values(clients, card["limit_multiples"]) * clients["true_income"].to_numpy(
        dtype=float
    )
    tier = np.maximum(np.searchsorted(tiers, target, side="right") - 1, 0)
    moved = rng.random(len(clients)) < card["adjusted_share"]
    tier = np.where(moved, tier + np.where(credit_dev > 0, 1, -1), tier)
    return tiers[np.clip(tier, 0, len(tiers) - 1)]


def wanted_spend(
    spec: dict,
    profiles: np.ndarray,
    income: np.ndarray,
    log_part: np.ndarray,
    dz: np.ndarray,
    month: np.datetime64,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Wanted card spend before the limit: its total and its parts (last axis, spec order).

    `profiles` (PROFILE_ORDER codes), `income` and `log_part` broadcast together; `dz` has the
    traits on its last axis. Draws: whether the month is a travel month, then the shares.
    """
    levels = spec["levels"]
    names = levels["subcategories"]["spend_cc"]["names"]
    level = np.asarray(levels["measures"]["spend_cc"]["multiples"])[profiles] * income
    chance = travel_chance(spec, profiles, dz[..., LATENTS.index("crossborder")], month)
    travelling = rng.random(np.shape(chance)) < chance
    # Outside travel months the travel share goes to the others (a Gamma with shape 0 is 0).
    keep = np.stack([travelling if n == TRAVEL else np.ones_like(travelling) for n in names], -1)
    mean = tilted_shares(spec, "spend_cc", profiles, dz) * keep
    concentration = levels["subcategories"]["concentration"]
    shares = draw_shares(rng, mean / mean.sum(axis=-1, keepdims=True), concentration)
    factors = [season_factor(spec, "travel_spend" if n == TRAVEL else "card_other_spend",
                             profiles, month) for n in names]  # fmt: skip
    season = np.stack(factors, axis=-1)
    parts = np.round((level * np.exp(log_part))[..., None] * shares * season, 2)
    return np.round(parts.sum(axis=-1), 2), parts


def step_card(
    last_balance: np.ndarray,
    limit: np.ndarray,
    revolver: np.ndarray,
    held: np.ndarray,
    held_before: np.ndarray,
    active: np.ndarray,
    wanted: np.ndarray,
    repay_share: np.ndarray,
    rate: float,
) -> dict[str, np.ndarray]:
    """One month of the card: carried, interest, spend, repayment, balance, utilisation.

    `limit` is this month's (0 without a card); `revolver`, `held` and `active` are the states at
    the end of this month, `held_before` at the end of last month. Utilisation is NaN without a
    card.
    """
    keeps = held & held_before & revolver
    carried = np.where(keeps, np.round((1 - repay_share) * last_balance, 2), 0.0)
    repayment = np.where(held_before, np.round(last_balance - carried, 2), 0.0)
    interest = np.round(rate * carried, 2)
    room = np.maximum(np.round(limit - carried - interest, 2), 0.0)
    safe_limit = np.where(held, limit, 1.0)  # no division by a missing card's 0
    # A revolver spends less as its card fills up, so few sit exactly at the limit.
    filled = np.where(keeps, np.minimum(last_balance / safe_limit, 1.0), 0.0)
    spend = np.where(held & active, np.minimum(np.round(wanted * (1 - filled), 2), room), 0.0)
    balance = np.where(held, np.round(carried + interest + spend, 2), 0.0)
    return {
        "spend": spend,
        "repayment": repayment,
        "interest": interest,
        "balance": balance,
        "utilisation": np.where(held, balance / safe_limit, np.nan),
    }


def capped_parts(parts: np.ndarray, wanted: np.ndarray, spend: np.ndarray) -> np.ndarray:
    """The wanted parts scaled down to the spend actually made, in cents adding up to it."""
    shares = parts / np.where(wanted > 0, wanted, 1.0)[..., None]
    return np.where((spend < wanted)[..., None], split_amount(spend, shares), parts)


def start_card(
    spec: dict,
    clients: pd.DataFrame,
    dz: np.ndarray,
    holdings: dict[str, np.ndarray],
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """Card state of newly drawn clients: a limit for the starting book's cards, no balance."""
    limits = draw_limits(spec, clients, dz[:, LATENTS.index("credit")], rng)
    return {"cc_limit": np.where(holdings["cc_held"], limits, 0.0), "cc_bal": np.zeros(len(limits))}


def card_amounts(
    spec: dict,
    state: dict[str, np.ndarray],
    clients: pd.DataFrame,
    profiles: np.ndarray,
    holdings: dict[str, np.ndarray],
    log_part: np.ndarray,
    dz: np.ndarray,
    month: np.datetime64,
    count_tilt: np.ndarray,
    rng: np.random.Generator,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """One month of the card: (state entries, mart columns in the mart's order).

    A new card gets a new limit; a card held at the end of last month is the one with a limit.
    Draws: limit tiers, the wanted spend (travel month, shares), then the spend count.
    """
    card, held = spec["levels"]["card"], holdings["cc_held"]
    held_before = state["cc_limit"] > 0
    new_limits = draw_limits(spec, clients, dz[:, LATENTS.index("credit")], rng)
    limit = np.where(held, np.where(holdings["cc_gained"], new_limits, state["cc_limit"]), 0.0)
    income = clients["true_income"].to_numpy(dtype=float)
    wanted, parts = wanted_spend(spec, profiles, income, log_part, dz, month, rng)
    step = step_card(
        state["cc_bal"], limit, holdings["cc_revolver_active"], held, held_before,
        holdings["cc_activity_active"], wanted, clients["repay_share"].to_numpy(dtype=float),
        card["monthly_interest"],
    )  # fmt: skip
    parts = capped_parts(parts, wanted, step["spend"])
    counts = spec["levels"]["counts"]
    spend_count = draw_counts(rng, counts["spend_cc"] * count_tilt, counts["gamma_shape"])
    names = spec["levels"]["subcategories"]["spend_cc"]["names"]
    columns = {
        "cc_limit": limit,
        "cc_bal": step["balance"],
        "cc_utilisation_ratio": step["utilisation"],
        "spend_cc_vol": np.round(parts.sum(axis=1), 2),
        "spend_cc_cnt": np.where(step["spend"] > 0, 1 + spend_count, 0),
        **{f"spend_cc_{name}_vol": parts[:, j] for j, name in enumerate(names)},
        "repayment_cc_vol": step["repayment"],
        "interest_cc_vol": step["interest"],
    }
    return {"cc_limit": limit, "cc_bal": step["balance"]}, columns
