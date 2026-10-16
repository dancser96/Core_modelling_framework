"""Generate the synthetic mart month by month, together with its hidden truth.

`generate_mart` draws the starting book (holdings drawn from each client's history), runs burn-in
months, then the panel months. Each month: clients leave and new clients join (rates per profile,
higher for the lower segments), the hidden traits take one AR(1) step, holdings and usage states
move with each client's chances, and the month's rows are emitted twice: mart rows (what upstream
would publish) and oracle rows (hidden truth: traits and the chance behind every event, never
features).
Each mechanism draws from its own random stream, so a later build step never changes the columns
of an earlier one.
"""

import copy

import numpy as np
import pandas as pd

from synthetic import __version__
from synthetic.hazards import calibrate
from synthetic.holdings import holding_columns, start_holdings, step_holdings
from synthetic.latents import draw_latents, latent_means, step_latents
from synthetic.population import (
    client_age,
    draw_clients,
    draw_income,
    draw_subsegments,
    months_on_book,
)
from synthetic.presets import LATENTS, PRESETS

# New mechanisms are appended here: SeedSequence.spawn keeps the earlier streams identical.
STREAMS = ("population", "latents", "holdings")
WEALTH = LATENTS.index("wealth")
DESCRIPTION_COLUMNS = [
    "segment",
    "subsegment",
    "nationality_group",
    "nationality",
    "employment_status",
    "income",
    "salary_transfer_flag",
    "emirate",
]


def generate_mart(
    preset: str = "unit", n_clients: int | None = None, seed: int = 0
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return (mart, oracle, truth) in memory. The oracle holds the hidden per-row truth."""
    spec = PRESETS[preset]["spec"]
    n_clients = PRESETS[preset]["n_clients"] if n_clients is None else n_clients
    n_months = PRESETS[preset]["n_months"]
    rngs = dict(zip(STREAMS, np.random.default_rng(seed).spawn(len(STREAMS)), strict=True))
    first = np.datetime64(spec["first_month"], "M")
    month = first - spec["burn_in_months"] - 1
    subsegment = draw_subsegments(spec, n_clients, rngs["population"])
    state = _new_clients(spec, subsegment, month, rngs, new_to_bank=False, first_id=1)
    age, months = client_age(state["clients"], month), months_on_book(state["clients"], month)
    calib = calibrate(spec, state["clients"], state["z"], age, months)
    state["holdings"] = start_holdings(
        spec, state["clients"], state["z"], month, calib, rngs["holdings"], new_to_bank=False
    )
    marts, oracles, turnover = [], [], []
    for _ in range(spec["burn_in_months"] + n_months):
        month = month + 1
        state, moves, chances = _advance_month(spec, state, month, rngs, calib)
        if month >= first:
            mart, oracle = _month_rows(spec, state, month, chances)
            marts.append(mart)
            oracles.append(oracle)
            turnover.extend(moves)
    truth = {
        "generator_version": __version__,
        "seed": seed,
        "preset": preset,
        "n_clients": n_clients,
        "n_months": n_months,
        "first_month": spec["first_month"],
        "spec": copy.deepcopy(spec),  # a copy, so editing truth never changes the preset
        "calibration": calib,
        "turnover": turnover,
    }
    return pd.concat(marts, ignore_index=True), pd.concat(oracles, ignore_index=True), truth


def _new_clients(
    spec: dict,
    subsegment: np.ndarray,
    month: np.datetime64,
    rngs: dict[str, np.random.Generator],
    new_to_bank: bool,
    first_id: int,
) -> dict:
    """Clients of the given subsegments with their hidden traits, income and ids."""
    clients = draw_clients(spec, subsegment, month, rngs["population"], new_to_bank)
    means = latent_means(spec, clients)
    z = draw_latents(spec, clients, means, rngs["latents"])
    wealth_sd = clients["profile"].map(lambda p: spec["profiles"][p]["latent_scale"][WEALTH])
    wealth_dev = (z[:, WEALTH] - means[:, WEALTH]) / wealth_sd.to_numpy()
    income = draw_income(spec, clients, wealth_dev, rngs["population"])
    clients = pd.concat([clients, income], axis=1)
    n = len(clients)
    clients.insert(0, "client_id", np.arange(first_id, first_id + n))
    return {"clients": clients, "means": means, "z": z, "next_id": first_id + n}


def _advance_month(
    spec: dict,
    state: dict,
    month: np.datetime64,
    rngs: dict[str, np.random.Generator],
    calib: dict,
) -> tuple[dict, list[dict], dict[str, np.ndarray]]:
    """Exits, new-to-bank entries, one AR(1) step for those who stayed, then holdings move.

    Turnover rates are per profile and apply to the clients on the books at the start of the
    month. Returns the new state, one turnover record per profile and the month's event chances.
    """
    clients, rng = state["clients"], rngs["population"]
    profile_spec = clients["profile"].map(spec["profiles"])
    stay = rng.random(len(clients)) >= profile_spec.map(lambda p: p["exit_rate"]).to_numpy()
    names = list(spec["subsegments"])
    counts = clients["subsegment"].value_counts().reindex(names, fill_value=0).to_numpy()
    entry_rate = [spec["profiles"][spec["subsegments"][s]["profile"]]["entry_rate"] for s in names]
    n_new = rng.binomial(counts, entry_rate)
    new = _new_clients(
        spec, np.repeat(names, n_new), month, rngs, new_to_bank=True, first_id=state["next_id"]
    )
    kept = clients[stay]
    z = step_latents(spec, kept, state["z"][stay], state["means"][stay], rngs["latents"])
    advanced = {
        # An empty batch is left out: concatenating it can change column dtypes.
        "clients": pd.concat([kept, new["clients"]] if n_new.sum() else [kept], ignore_index=True),
        "means": np.vstack([state["means"][stay], new["means"]]),
        "z": np.vstack([z, new["z"]]),
        "next_id": new["next_id"],
    }
    new_holdings = start_holdings(
        spec, new["clients"], new["z"], month, calib, rngs["holdings"], new_to_bank=True
    )
    holdings = {k: np.concatenate([v[stay], new_holdings[k]]) for k, v in state["holdings"].items()}
    advanced["holdings"], chances = step_holdings(
        spec, holdings, advanced["clients"], advanced["z"], month, calib, rngs["holdings"]
    )
    return advanced, _turnover_records(spec, clients, stay, new["clients"], month), chances


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


def _month_rows(
    spec: dict, state: dict, month: np.datetime64, chances: dict[str, np.ndarray]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The mart rows and oracle rows of one month; day counters are as of the month's last day."""
    clients = state["clients"]
    month_end = (month + 1).astype("datetime64[D]").astype(int) - 1
    keys = {
        "client_id": clients["client_id"].to_numpy(),
        "snapshot_month": [month.astype("datetime64[D]").item()] * len(clients),
    }
    mart = pd.DataFrame(
        {
            **keys,
            **{col: clients[col].to_numpy() for col in DESCRIPTION_COLUMNS},
            "age": client_age(clients, month),
            "residence_days": (month_end - clients["residence_start"]).astype("Int64").array,
            "relationship_days": month_end - clients["relationship_start"].to_numpy(),
            **holding_columns(spec, state["holdings"]),
        }
    )
    oracle = pd.DataFrame(
        {
            **keys,
            **{f"z_{n}": state["z"][:, i] for i, n in enumerate(LATENTS)},
            **{f"p_{event}": chance for event, chance in chances.items()},
        }
    )
    return mart, oracle
