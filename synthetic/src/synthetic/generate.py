"""Generate the synthetic mart month by month, together with its hidden truth.

The month loop is three functions every driver shares: `start_simulation` draws the starting book
(holdings drawn from each client's history) and calibrates the products on it;
`advance_simulation` runs one month and returns the panel months that are final;
`finish_simulation` returns what is still buffered at the end. `generate_mart` collects the months
in memory, `output.write_mart` writes each to disk as it comes. Each month: clients leave and new
clients join (rates per profile, higher for the lower segments), the hidden traits take one AR(1)
step, holdings and usage states move with each client's chances (time terms included), and the
month's rows come out twice: mart rows (what upstream would publish) and oracle rows (hidden truth:
traits, hidden attributes and the chance behind every event, never features). Burn-in months run
but come out nowhere. Each mechanism draws from its own random stream (`STREAMS`), so a later
build step never changes the columns of an earlier one.
"""

import numpy as np
import pandas as pd

from synthetic.amounts import draw_hidden_attributes
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
)
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
HIDDEN_CLIENT_COLUMNS = ["true_income", "wealth_base"]  # oracle columns from the client table


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
    """The simulation before its first month: the starting book, calibrated, with its holdings.

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
    return {
        **book,
        "holdings": holdings,
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
    step of the traits for those who stayed, then holdings move. With no look-ahead columns yet, a
    panel month is final as soon as it has run; burn-in months return none.
    """
    spec, rngs, calib, month = sim["spec"], sim["rngs"], sim["calibration"], sim["month"] + 1
    clients = sim["clients"]
    stay, new = _turn_over(spec, clients, month, rngs, sim["next_id"])
    kept = clients[stay]
    z = step_latents(spec, kept, sim["z"][stay], sim["means"][stay], rngs["latents"])
    new_holdings = start_holdings(
        spec, new["clients"], new["z"], month, calib, rngs["holdings"], new_to_bank=True
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
    holdings = _keep_and_append(sim["holdings"], stay, new_holdings)
    advanced["holdings"], chances = step_holdings(
        spec, holdings, advanced["clients"], advanced["z"], month, calib, rngs["holdings"]
    )
    if month < sim["first_month"]:
        return advanced, []
    records = _turnover_records(spec, clients, stay, new["clients"], month)
    advanced["turnover"] = sim["turnover"] + records
    return advanced, [_month_rows(advanced, chances)]


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
    median = clients["subsegment"].map(lambda s: spec["subsegments"][s]["median_income"])
    wealth_base = median.to_numpy() * np.exp(spec["income"]["wealth_loading"] * wealth_dev)
    clients = clients.assign(wealth_base=wealth_base)
    age = client_age(clients, month)
    clients = pd.concat(
        [clients, draw_hidden_attributes(spec, clients, age, rngs["amounts"])], axis=1
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


def _month_rows(sim: dict, chances: dict[str, np.ndarray]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The mart rows and oracle rows of the month; day counters are as of the month's last day."""
    clients, month = sim["clients"], sim["month"]
    month_end = (month + 1).astype("datetime64[D]").astype(int) - 1
    keys = {
        "client_id": clients["client_id"].to_numpy(),
        "snapshot_month": [month.astype("datetime64[D]").item()] * len(clients),
    }
    mart_holdings, hidden_holdings = holding_columns(sim["spec"], sim["holdings"])
    mart = pd.DataFrame(
        {
            **keys,
            **{col: clients[col].to_numpy() for col in DESCRIPTION_COLUMNS},
            "age": client_age(clients, month),
            "residence_days": (month_end - clients["residence_start"]).astype("Int64").array,
            "relationship_days": month_end - clients["relationship_start"].to_numpy(),
            **mart_holdings,
        }
    )
    oracle = pd.DataFrame(
        {
            **keys,
            **{f"z_{n}": sim["z"][:, i] for i, n in enumerate(LATENTS)},
            **{f"p_{event}": chance for event, chance in chances.items()},
            **{col: clients[col].to_numpy() for col in HIDDEN_CLIENT_COLUMNS},
            **hidden_holdings,
        }
    )
    return _with_int_flags(mart), _with_int_flags(oracle)


def _with_int_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Booleans as 0/1 int32, the mart's flag type (test_harness.md, types)."""
    flags = [column for column, dtype in df.dtypes.items() if dtype == np.dtype(bool)]
    return df.astype(dict.fromkeys(flags, "int32"))
