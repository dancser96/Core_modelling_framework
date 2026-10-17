"""The regression oracle: the true distribution of each card holder's card spend over the next
three months (D-060; test_harness.md, "Ground truth and oracle").

For every client holding a card at the end of a panel month t, `simulate_card_spend` runs forward
paths of months t+1..t+3 from the client's true state at t, with the generator's own functions on
(clients, paths) arrays, per-client inputs as (clients, 1) columns: one AR(1) step of the hidden
traits (`latents.step_latents`); the card and the chains that require it (`holdings.step_holdings`
on those products alone: leaving, re-adoption with onboarding by tenure, card activity and the
revolver state, each at risk only with the card at the end of the previous month); the AR(1) noise
of the current/savings balance (its random part D, which every flow carries) and of card spend
(`variation`); a new limit for a re-adopted card (`cards.draw_limits`); the wanted spend with its
travel months, shares and seasons (`cards.wanted_spend`); and the card step (`cards.step_card`).
Paths are conditioned on the client staying with the bank (no exits). The oracle columns are the
mean and the 10%, 50% and 90% quantiles (`np.quantile`, linear) of the 3-month total, null without
a card. Clients run in chunks to bound memory; every draw comes from the `regression` stream, sized
by the card holders and the paths, so no other column of the dataset moves with it.
"""

import numpy as np

from synthetic.cards import draw_limits, step_card, wanted_spend
from synthetic.holdings import step_holdings
from synthetic.latents import step_latents
from synthetic.population import profile_codes
from synthetic.presets import LATENTS
from synthetic.variation import log_variation, measure_offsets, measures_of_kind, step_noise

TARGET = "spend_cc_next_3_months"  # the standard regression target (test_harness.md)
CARD = "cc"
HORIZON = 3  # months after t
QUANTILES = {"q10": 0.1, "q50": 0.5, "q90": 0.9}
COLUMNS = [f"{TARGET}_{name}" for name in ("mean", *QUANTILES)]
CHUNK = 5_000  # clients per chunk: 5,000 × 200 paths keeps each array near 8 MB
MEASURES = ("casa_bal", "spend_cc")  # D and the card spend's own variation


def simulate_card_spend(
    spec: dict, sim: dict, month: np.datetime64, rng: np.random.Generator, n_paths: int = 200
) -> dict[str, np.ndarray]:
    """Mean and quantiles of each card holder's simulated card spend over the 3 months after
    `month`, from the state at its end (`sim`), aligned with `sim["clients"]`; null without a
    card."""
    holders = np.flatnonzero(sim["holdings"][f"{CARD}_held"])
    out = {column: np.full(len(sim["clients"]), np.nan) for column in COLUMNS}
    offsets = measure_offsets(spec)  # a root search per measure and profile: once per month
    for start in range(0, len(holders), CHUNK):
        rows = holders[start : start + CHUNK]
        totals = _simulate_chunk(spec, sim, rows, month, offsets, rng, n_paths)
        out[COLUMNS[0]][rows] = totals.mean(axis=1)
        quantiles = np.quantile(totals, list(QUANTILES.values()), axis=1)
        for column, values in zip(COLUMNS[1:], quantiles, strict=True):
            out[column][rows] = values
    return out


def _simulate_chunk(
    spec: dict,
    sim: dict,
    rows: np.ndarray,
    month: np.datetime64,
    offsets: dict[str, np.ndarray],
    rng: np.random.Generator,
    n_paths: int,
) -> np.ndarray:
    """The 3-month card spend of each path, (clients at `rows`, paths); `offsets` are the
    measures' median offsets (`variation.measure_offsets`)."""
    clients = sim["clients"].iloc[rows].reset_index(drop=True)
    shape = (len(rows), n_paths)
    means = sim["means"][rows][:, None, :]
    z = np.broadcast_to(sim["z"][rows][:, None, :], (*shape, len(LATENTS)))
    card_spec = _card_spec(spec)
    holdings = _start_paths(sim["holdings"], _path_keys(card_spec), rows, shape)
    holdings["onboarding_left"] = sim["holdings"]["onboarding_left"][rows]  # per client
    amounts = _start_amounts(spec, sim["amounts"], rows, shape)
    per_client = {
        "profiles": profile_codes(clients)[:, None],
        "income": clients["true_income"].to_numpy(dtype=float)[:, None],
        "repay_share": clients["repay_share"].to_numpy(dtype=float)[:, None],
    }
    total = np.zeros(shape)
    for ahead in range(1, HORIZON + 1):
        later = month + ahead
        z = step_latents(spec, clients, z, means, rng)
        holdings = step_holdings(card_spec, holdings, clients, z, later, sim["calibration"], rng)[0]
        amounts, spend = _step_spend(
            spec, amounts, holdings, per_client, z - means, offsets, later, rng
        )
        total = total + spend
    return total


def _card_spec(spec: dict) -> dict:
    """The spec with only the card and the usage chains that require it as products."""
    products = {
        key: product
        for key, product in spec["products"].items()
        if key == CARD or product.get("requires") == CARD
    }
    return {**spec, "products": products}


def _path_keys(card_spec: dict) -> list[str]:
    """The holdings state the card's products move (`holdings` module docstring)."""
    chains = [key for key, p in card_spec["products"].items() if p["kind"] == "usage"]
    return [f"{CARD}_held", f"{CARD}_ever", f"{CARD}_gained", *[f"{c}_active" for c in chains]]


def _start_paths(
    state: dict[str, np.ndarray], keys: list[str], rows: np.ndarray, shape: tuple[int, int]
) -> dict[str, np.ndarray]:
    """Per-client state at t, the same on every path (read-only views: steps build new arrays)."""
    return {key: np.broadcast_to(state[key][rows][:, None], shape) for key in keys}


def _start_amounts(
    spec: dict, state: dict[str, np.ndarray], rows: np.ndarray, shape: tuple[int, int]
) -> dict[str, np.ndarray]:
    """The amounts state the card spend needs at t: the current/savings and card-spend columns of
    the effects, noise and multiplier (`MEASURES`), the card's limit and balance."""
    stock = [measures_of_kind(spec, "stock").index(MEASURES[0])]
    flow = [measures_of_kind(spec, "flow").index(MEASURES[1])]
    out = {
        "stock_effect": state["stock_effect"][rows][:, None, stock],
        "stock_pareto": state["stock_pareto"][rows][:, None, stock],
        "flow_effect": state["flow_effect"][rows][:, None, flow],
        "stock_noise": np.broadcast_to(state["stock_noise"][rows][:, None, stock], (*shape, 1)),
        "flow_noise": np.broadcast_to(state["flow_noise"][rows][:, None, flow], (*shape, 1)),
    }
    return out | _start_paths(state, ["cc_limit", "cc_bal"], rows, shape)


def _step_spend(
    spec: dict,
    amounts: dict[str, np.ndarray],
    holdings: dict[str, np.ndarray],
    per_client: dict[str, np.ndarray],
    dz: np.ndarray,
    offsets: dict[str, np.ndarray],
    month: np.datetime64,
    rng: np.random.Generator,
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """One month of the paths' amounts, in the generator's order (`amounts.step_amounts`,
    `cards.card_amounts`): noise steps, the log variation, the limit, the wanted spend, the card
    step. Returns the new amounts state and the month's card spend."""
    levels = spec["levels"]
    stock, flow = levels["stock_noise"], levels["flow_noise"]
    amounts = dict(
        amounts,
        stock_noise=step_noise(amounts["stock_noise"], stock["rho"], stock["sd"], rng),
        flow_noise=step_noise(amounts["flow_noise"], flow["rho"], flow["sd"], rng),
    )
    spend_spec = {
        **spec,
        "levels": {**levels, "measures": {m: levels["measures"][m] for m in MEASURES}},
    }
    profiles, income = per_client["profiles"], per_client["income"]
    log_part = log_variation(spend_spec, offsets, amounts, dz, profiles)[MEASURES[1]]
    held, held_before = holdings[f"{CARD}_held"], amounts["cc_limit"] > 0
    new_limits = draw_limits(spec, profiles, income, dz[..., LATENTS.index("credit")], rng)
    limit = np.where(
        held, np.where(holdings[f"{CARD}_gained"], new_limits, amounts["cc_limit"]), 0.0
    )
    wanted, _ = wanted_spend(spec, profiles, income, log_part, dz, month, rng)
    step = step_card(
        amounts["cc_bal"], limit, holdings["cc_revolver_active"], held, held_before,
        holdings["cc_activity_active"], wanted, per_client["repay_share"],
        levels["card"]["monthly_interest"],
    )  # fmt: skip
    return amounts | {"cc_limit": limit, "cc_bal": step["balance"]}, step["spend"]
