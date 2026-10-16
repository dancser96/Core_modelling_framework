"""Generate the synthetic mart month by month, together with its hidden truth.

The month loop is three functions every driver shares: `start_simulation` draws the starting book
(holdings drawn from each client's history) and calibrates the products on it;
`advance_simulation` runs one month and returns the panel months that are final;
`finish_simulation` returns what is still buffered at the end. `generate_mart` collects the months
in memory, `output.write_mart` writes each to disk as it comes. Each month: clients leave and new
clients join (rates per profile, higher for the lower segments), the hidden traits take one AR(1)
step, holdings and usage states move with each client's chances (time terms included), the amounts
follow from the holdings at the month's end (with the shared market index), and the month's rows
come out twice (`month_rows`): mart rows (what upstream would publish) and oracle rows (hidden
truth: traits, hidden attributes and the chance behind every event, never features). Burn-in
months run but come out nowhere. Each mechanism draws from its own random stream (`STREAMS`), so a
later build step never changes the columns of an earlier one.
"""

import numpy as np
import pandas as pd

from synthetic.amounts import draw_hidden_attributes, start_amounts, step_amounts, step_market
from synthetic.hazards import calibrate
from synthetic.holdings import start_holdings, step_holdings
from synthetic.latents import draw_latents, latent_means, step_latents
from synthetic.mart import advance_history, start_history
from synthetic.month_rows import month_rows
from synthetic.population import (
    client_age,
    draw_clients,
    draw_income,
    draw_subsegments,
    months_on_book,
    subsegment_medians,
)
from synthetic.presets import LATENTS, PRESETS
from synthetic.truth import build_truth

# New mechanisms are appended here: SeedSequence.spawn keeps the earlier streams identical.
STREAMS = (
    "population",
    "latents",
    "holdings",
    "amounts",
    "cards",
    "logins",
    "traps",
    "leaks",
    "extras",
    "regression",
    "attributes",  # hidden client attributes, so amounts' draws never move holdings
)
WEALTH = LATENTS.index("wealth")


def generate_mart(
    preset: str = "unit",
    n_clients: int | None = None,
    seed: int = 0,
    n_months: int | None = None,
    dirty: bool = False,
    n_extra_columns: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return (mart, oracle, truth) in memory (small presets). The oracle holds the hidden truth."""
    if dirty:
        raise NotImplementedError("dirty-data switches are not built yet (test_harness step 5)")
    sim = start_simulation(preset, n_clients, seed, n_months, n_extra_columns)
    frames = []
    while sim["month"] < sim["last_month"]:
        sim, final = advance_simulation(sim)
        frames += final
    frames += finish_simulation(sim)
    mart = pd.concat([m for m, _ in frames], ignore_index=True)
    oracle = pd.concat([o for _, o in frames], ignore_index=True)
    return mart, oracle, build_truth(sim)


def start_simulation(
    preset: str, n_clients: int | None, seed: int, n_months: int | None, n_extra_columns: int
) -> dict:
    """The simulation before its first month: the starting book, calibrated, with its holdings
    and amounts.

    The starting book is drawn one month before the burn-in starts; `n_clients` and `n_months`
    default to the preset's.
    """
    if n_extra_columns:
        raise NotImplementedError("extra columns are not built yet (test_harness step 5)")
    spec = PRESETS[preset]["spec"]
    n_clients = PRESETS[preset]["n_clients"] if n_clients is None else n_clients
    n_months = PRESETS[preset]["n_months"] if n_months is None else n_months
    rngs = dict(zip(STREAMS, np.random.default_rng(seed).spawn(len(STREAMS)), strict=True))
    first = np.datetime64(spec["first_month"], "M")
    month = first - spec["burn_in_months"] - 1
    subsegment = draw_subsegments(spec, n_clients, rngs["population"])
    book = _new_clients(spec, subsegment, month, rngs, new_to_bank=False, first_id=1)
    clients, z = book["clients"], book["z"]
    calib = calibrate(spec, clients, z, client_age(clients, month), months_on_book(clients, month))
    holdings = start_holdings(spec, clients, z, month, calib, rngs["holdings"], new_to_bank=False)
    amounts = start_amounts(
        spec, clients, z, book["means"], holdings, month, rngs, new_to_bank=False
    )
    return {
        **book,
        "holdings": holdings,
        "amounts": amounts,
        "history": start_history(n_clients),  # the burn-in fills it
        "market_index": {str(month): 1.0},  # 1 when the book is drawn, then one return a month
        "spec": spec,
        "preset": preset,
        "seed": seed,
        "n_clients": n_clients,
        "n_months": n_months,
        "first_month": first,
        "last_month": first + n_months - 1,
        "month": month,
        "rngs": rngs,
        "calibration": calib,
        "turnover": [],
    }


def advance_simulation(sim: dict) -> tuple[dict, list[tuple[pd.DataFrame, pd.DataFrame]]]:
    """Run one month; return the new simulation and the (mart, oracle) months now final.

    Exits and entries apply to the clients on the books at the start of the month; then one AR(1)
    step of the traits for those who stayed, then holdings move, then the market index and the
    amounts, then each client's history (for the mart's rollups, recency and ratios) takes the
    month's amounts. Per-client state (holdings, amounts, history) keeps the stayers and appends
    the new clients.
    With no look-ahead columns yet, a panel month is final as soon as it has run; burn-in months
    return none.
    """
    spec, rngs, calib, month = sim["spec"], sim["rngs"], sim["calibration"], sim["month"] + 1
    clients = sim["clients"]
    stay, new = _turn_over(spec, clients, month, rngs, sim["next_id"])
    kept = clients[stay]
    z = step_latents(spec, kept, sim["z"][stay], sim["means"][stay], rngs["latents"])
    new_holdings = start_holdings(
        spec, new["clients"], new["z"], month, calib, rngs["holdings"], new_to_bank=True
    )
    new_amounts = start_amounts(
        spec, new["clients"], new["z"], new["means"], new_holdings, month, rngs, new_to_bank=True
    )
    # An empty batch is left out: concatenating it can change column dtypes.
    batch = [kept, new["clients"]] if len(new["clients"]) else [kept]
    advanced = dict(
        sim,
        month=month,
        clients=pd.concat(batch, ignore_index=True),
        means=np.vstack([sim["means"][stay], new["means"]]),
        z=np.vstack([z, new["z"]]),
        next_id=new["next_id"],
    )
    clients, z, means = advanced["clients"], advanced["z"], advanced["means"]
    holdings = _keep_and_append(sim["holdings"], stay, new_holdings)
    holdings, chances = step_holdings(spec, holdings, clients, z, month, calib, rngs["holdings"])
    market = step_market(spec, list(sim["market_index"].values())[-1], rngs["amounts"])
    amounts = _keep_and_append(sim["amounts"], stay, new_amounts)
    amounts, mart_amounts, oracle_amounts = step_amounts(
        spec, amounts, clients, z, means, holdings, month, market, rngs
    )
    history = _keep_and_append(sim["history"], stay, start_history(len(new["clients"])))
    advanced |= {
        "holdings": holdings,
        "amounts": amounts,
        "history": advance_history(history, mart_amounts, month.astype(int)),
        "market_index": {**sim["market_index"], str(month): market},
    }
    if month < sim["first_month"]:
        return advanced, []
    records = _turnover_records(spec, sim["clients"], stay, new["clients"], month)
    advanced["turnover"] = sim["turnover"] + records
    return advanced, [month_rows(advanced, chances, mart_amounts, oracle_amounts)]


def finish_simulation(sim: dict) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """The months still buffered when the panel ends: none while no column looks ahead."""
    return []


def _new_clients(
    spec: dict,
    subsegment: np.ndarray,
    month: np.datetime64,
    rngs: dict[str, np.random.Generator],
    new_to_bank: bool,
    first_id: int,
) -> dict:
    """Clients of the given subsegments with their hidden traits, income, hidden attributes, ids.

    The wealth base (hidden) is the subsegment's median income × exp(wealth loading × the wealth
    trait's deviation): no employment multiplier, so a retired Private client has small flows but
    large balances.
    """
    clients = draw_clients(spec, subsegment, month, rngs["population"], new_to_bank)
    means = latent_means(spec, clients)
    z = draw_latents(spec, clients, means, rngs["latents"])
    wealth_sd = clients["profile"].map(lambda p: spec["profiles"][p]["latent_scale"][WEALTH])
    wealth_dev = (z[:, WEALTH] - means[:, WEALTH]) / wealth_sd.to_numpy()
    income = draw_income(spec, clients, wealth_dev, rngs["population"])
    clients = pd.concat([clients, income], axis=1)
    median = subsegment_medians(spec, clients)
    wealth_base = median * np.exp(spec["income"]["wealth_loading"] * wealth_dev)
    clients = clients.assign(wealth_base=wealth_base)
    age = client_age(clients, month)
    clients = pd.concat(
        [clients, draw_hidden_attributes(spec, clients, age, rngs["attributes"])], axis=1
    )
    n = len(clients)
    clients.insert(0, "client_id", np.arange(first_id, first_id + n))
    return {"clients": clients, "means": means, "z": z, "next_id": first_id + n}


def _turn_over(
    spec: dict,
    clients: pd.DataFrame,
    month: np.datetime64,
    rngs: dict[str, np.random.Generator],
    next_id: int,
) -> tuple[np.ndarray, dict]:
    """Who stays this month, and the new clients who join (turnover rates per profile)."""
    rng = rngs["population"]
    profile_spec = clients["profile"].map(spec["profiles"])
    stay = rng.random(len(clients)) >= profile_spec.map(lambda p: p["exit_rate"]).to_numpy()
    names = list(spec["subsegments"])
    counts = clients["subsegment"].value_counts().reindex(names, fill_value=0).to_numpy()
    entry_rate = [spec["profiles"][spec["subsegments"][s]["profile"]]["entry_rate"] for s in names]
    n_new = rng.binomial(counts, entry_rate)
    subsegment = np.repeat(names, n_new)
    return stay, _new_clients(spec, subsegment, month, rngs, new_to_bank=True, first_id=next_id)


def _keep_and_append(state: dict, stay: np.ndarray, new: dict) -> dict:
    """Per-client state arrays of the clients who stayed, followed by the new clients' arrays."""
    if state.keys() != new.keys():
        raise ValueError(f"state keys differ: {sorted(state.keys() ^ new.keys())}")
    if {len(v) for v in state.values()} - {len(stay)} or len({len(v) for v in new.values()}) > 1:
        raise ValueError("state arrays must line up with the clients")
    return {key: np.concatenate([values[stay], new[key]]) for key, values in state.items()}


def _turnover_records(
    spec: dict,
    clients: pd.DataFrame,
    stay: np.ndarray,
    new_clients: pd.DataFrame,
    month: np.datetime64,
) -> list[dict]:
    """One record per profile: clients on the books at the start, entries and exits."""
    before = clients["profile"].value_counts()
    left = clients.loc[~stay, "profile"].value_counts()
    entered = new_clients["profile"].value_counts()
    return [
        {
            "month": str(month),
            "profile": name,
            "clients_before": int(before.get(name, 0)),
            "entries": int(entered.get(name, 0)),
            "exits": int(left.get(name, 0)),
        }
        for name in spec["profiles"]
    ]
