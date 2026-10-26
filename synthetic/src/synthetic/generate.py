"""Generate the synthetic mart month by month, together with its hidden truth.

The month loop is three functions every driver shares: `start_simulation` draws the starting book
(holdings drawn from each client's history) and calibrates the products on it;
`advance_simulation` runs one month and returns the panel months that are final;
`finish_simulation` returns what is still buffered at the end. `generate_mart` collects the months
in memory; `output.write_mart` writes each to disk as it comes.

Each month: clients leave and new clients join (rates per profile), the hidden traits take one
AR(1) step, holdings and usage states move with each client's chances, the amounts follow from
the holdings at the month's end, and the month's rows come out twice (`month_rows`): mart rows
(what upstream would publish, trap and extra columns included) and oracle rows (hidden truth:
traits, hidden attributes, the chance behind every event and the state-free scores behind the
window probabilities, never features). Panel months also get the regression oracle. The
look-ahead trap columns make a panel month wait in a buffer (`buffer_month`) until the months its
windows read have run; burn-in months run but come out nowhere. Dirty data is planted in the
finished panel. Each mechanism draws from its own random stream (`STREAMS`), so a new stream never
changes another stream's columns; within a stream, a new draw moves every later one.
"""

import numpy as np
import pandas as pd

from synthetic.mechanisms.amounts import start_amounts, step_amounts, step_market
from synthetic.mechanisms.clients import (
    client_age,
    draw_clients,
    draw_hidden_attributes,
    draw_income,
    draw_latents,
    draw_subsegments,
    latent_means,
    months_on_book,
    relationship_days,
    step_latents,
    subsegment_medians,
)
from synthetic.mechanisms.holdings import calibrate, holding_columns, start_holdings, step_holdings
from synthetic.mechanisms.mart import advance_history, history_columns, start_history
from synthetic.mechanisms.traps import (
    dirty_panel,
    extra_columns,
    finalize_lookahead,
    lookahead_months,
    noise_columns,
    start_noise_state,
    start_trap_state,
    trap_columns,
)
from synthetic.spec.presets import LATENTS, PRESETS
from synthetic.truth.regression import simulate_card_spend
from synthetic.truth.truth_file import complete_truth

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
    "noise",  # the noise, high-cardinality and low-fill trap columns (0.5.0)
    "card_leaks",  # the card twins' and the offer code's look-ahead draws (0.5.0)
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
    "onboarding_channel",
]
# Oracle columns from the client table: hidden attributes, drawn once per client.
HIDDEN_CLIENT_COLUMNS = [
    "true_income",
    "wealth_base",
    "remitter_flag",
    "school_payer_flag",
    "bonus_month",
]


def generate_mart(
    preset: str = "unit",
    n_clients: int | None = None,
    seed: int = 0,
    n_months: int | None = None,
    dirty: bool = False,
    n_extra_columns: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return (mart, oracle, truth) in memory (small presets). The oracle holds the hidden truth.

    `dirty` plants the dirty-data defects (`traps.dirty_panel`); `n_extra_columns` adds extra
    columns. The truth's oracle metrics come from the clean panel.
    """
    sim = start_simulation(preset, n_clients, seed, n_months, n_extra_columns)
    frames = []
    while sim["month"] < sim["last_month"]:
        sim, final = advance_simulation(sim)
        frames += final
    frames += finish_simulation(sim)
    mart = pd.concat([m for m, _ in frames], ignore_index=True)
    oracle = pd.concat([o for _, o in frames], ignore_index=True)
    if not dirty:
        return mart, oracle, complete_truth(sim, mart, oracle)
    sim, planted = dirty_panel(sim, frames)
    truth = complete_truth(sim, mart, oracle)
    return pd.concat([m for m, _ in planted], ignore_index=True), oracle, truth


def start_simulation(
    preset: str, n_clients: int | None, seed: int, n_months: int | None, n_extra_columns: int
) -> dict:
    """The simulation before its first month: the starting book, calibrated, with its holdings
    and amounts.

    The starting book is drawn one month before the burn-in starts; `n_clients` and `n_months`
    default to the preset's.
    """
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
        "n_extra_columns": n_extra_columns,
        "buffer": [],  # panel months waiting for their look-ahead columns
    }


def advance_simulation(sim: dict) -> tuple[dict, list[tuple[pd.DataFrame, pd.DataFrame]]]:
    """Run one month; return the new simulation and the (mart, oracle) months now final.

    Exits and entries apply to the clients on the books at the start of the month; then one AR(1)
    step of the traits for those who stayed, then holdings move, then the market index and the
    amounts, then each client's history (for the mart's rollups, recency and ratios) takes the
    month's amounts. Per-client state (holdings, amounts, history, trap state) keeps the stayers
    and appends the new clients. Panel months get the regression oracle and wait in the
    look-ahead buffer (`buffer_month`); burn-in months return none.
    """
    spec, rngs, calib, month = sim["spec"], sim["rngs"], sim["calibration"], sim["month"] + 1
    stay, new = _turn_over(spec, sim["clients"], month, rngs, sim["next_id"])
    kept = sim["clients"][stay]
    z = step_latents(spec, kept, sim["z"][stay], sim["means"][stay], rngs["latents"])
    advanced = _join_month(sim, month, stay, new, z)
    clients, z, means = advanced["clients"], advanced["z"], advanced["means"]
    holdings, chances, scores = step_holdings(
        spec, advanced["holdings"], clients, z, month, calib, rngs["holdings"]
    )
    market = step_market(spec, list(sim["market_index"].values())[-1], rngs["amounts"])
    amounts, mart_amounts, oracle_amounts = step_amounts(
        spec, advanced["amounts"], clients, z, means, holdings, month, market, rngs
    )
    advanced |= {
        "holdings": holdings,
        "amounts": amounts,
        "history": advance_history(advanced["history"], mart_amounts, month.astype(int)),
        "market_index": {**sim["market_index"], str(month): market},
    }
    if month < sim["first_month"]:
        return advanced, []
    regression = simulate_card_spend(spec, advanced, month, rngs["regression"])
    return buffer_month(advanced, chances, mart_amounts, scores | oracle_amounts | regression)


def _join_month(
    sim: dict, month: np.datetime64, stay: np.ndarray, new: dict, z: np.ndarray
) -> dict:
    """The simulation at the start of `month`: the new clients' holdings and amounts started, and
    every per-client state (clients, traits, holdings, amounts, history, trap state) of the
    stayers followed by the new clients'; `z` is the stayers' traits after their AR(1) step."""
    spec, rngs, calib, n_new = sim["spec"], sim["rngs"], sim["calibration"], len(new["clients"])
    new_holdings = start_holdings(
        spec, new["clients"], new["z"], month, calib, rngs["holdings"], new_to_bank=True
    )
    new_amounts = start_amounts(
        spec, new["clients"], new["z"], new["means"], new_holdings, month, rngs, new_to_bank=True
    )
    # An empty batch is left out: concatenating it can change column dtypes.
    kept = sim["clients"][stay]
    batch = [kept, new["clients"]] if n_new else [kept]
    return dict(
        sim,
        month=month,
        clients=pd.concat(batch, ignore_index=True),
        means=np.vstack([sim["means"][stay], new["means"]]),
        z=np.vstack([z, new["z"]]),
        next_id=new["next_id"],
        holdings=_keep_and_append(sim["holdings"], stay, new_holdings, n_new),
        amounts=_keep_and_append(sim["amounts"], stay, new_amounts, n_new),
        history=_keep_and_append(sim["history"], stay, start_history(n_new), n_new),
        trap_state=_keep_and_append(sim["trap_state"], stay, new["trap_state"], n_new),
    )


def finish_simulation(sim: dict) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """The months still buffered when the panel ends, oldest first, their look-ahead columns
    from the months that follow inside the panel (truncated windows)."""
    spec, buffer, rngs = sim["spec"], sim["buffer"], sim["rngs"]
    leaks, card = rngs["leaks"], rngs["card_leaks"]
    return [
        (finalize_lookahead(spec, buffer[start:], leaks, card), buffer[start][1])
        for start in range(len(buffer))
    ]


def _new_clients(
    spec: dict,
    subsegment: np.ndarray,
    month: np.datetime64,
    rngs: dict[str, np.random.Generator],
    new_to_bank: bool,
    first_id: int,
) -> dict:
    """Clients of the given subsegments with their hidden traits, income, hidden attributes, ids
    and persistent trap values (`traps.start_trap_state`, `traps.start_noise_state`).

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
    trap_state = start_trap_state(spec, n, rngs["traps"])
    trap_state |= start_noise_state(spec, n, rngs["noise"])
    return {"clients": clients, "means": means, "z": z, "next_id": first_id + n,
            "trap_state": trap_state}  # fmt: skip


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


def _keep_and_append(state: dict, stay: np.ndarray, new: dict, n_new: int) -> dict:
    """Per-client state arrays of the clients who stayed, followed by the `n_new` new clients'
    arrays."""
    if state.keys() != new.keys():
        raise ValueError(f"state keys differ: {sorted(state.keys() ^ new.keys())}")
    if {len(v) for v in state.values()} - {len(stay)} or {len(v) for v in new.values()} - {n_new}:
        raise ValueError("state arrays must line up with the clients")
    return {key: np.concatenate([values[stay], new[key]]) for key, values in state.items()}


def buffer_month(
    sim: dict,
    chances: dict[str, np.ndarray],
    mart_amounts: dict[str, object],
    oracle_values: dict[str, np.ndarray],
) -> tuple[dict, list[tuple[pd.DataFrame, pd.DataFrame]]]:
    """Put the panel month's rows (trap and extra columns included) in the look-ahead buffer;
    once it holds more than `traps.lookahead_months`, the oldest month is final.

    Returns the simulation with its new buffer and the months now final (none or one).
    """
    spec, rngs, state = sim["spec"], sim["rngs"], sim["trap_state"]
    traps = trap_columns(spec, state, rngs["traps"])
    days = relationship_days(sim["clients"], sim["month"])
    traps |= noise_columns(spec, state, days, rngs["noise"])
    traps |= extra_columns(spec, sim["n_extra_columns"], sim["z"], rngs["extras"])
    buffer = [*sim["buffer"], month_rows(sim, chances, mart_amounts, oracle_values, traps)]
    if len(buffer) <= lookahead_months(spec):
        return sim | {"buffer": buffer}, []
    final = (finalize_lookahead(spec, buffer, rngs["leaks"], rngs["card_leaks"]), buffer[0][1])
    return sim | {"buffer": buffer[1:]}, [final]


def month_rows(
    sim: dict,
    chances: dict[str, np.ndarray],
    mart_amounts: dict[str, object],
    oracle_values: dict[str, np.ndarray],
    traps: dict[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The mart rows and oracle rows of the month; day counters are as of the month's last day.

    `mart_amounts` are the month's mart amounts (`amounts.step_amounts`), `oracle_values` its
    other oracle columns (scores and lapse chances from `holdings.step_holdings`, the amounts'
    hidden columns, the regression oracle), `traps` its trap and extra columns
    (`traps.trap_columns`, `traps.noise_columns`, `traps.extra_columns`).
    """
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
            "relationship_days": relationship_days(clients, month),
            **mart_holdings,
            **mart_amounts,
            **history_columns(sim["history"], months_on_book(clients, month), month.astype(int)),
            **traps,
        }
    )
    oracle = pd.DataFrame(
        {
            **keys,
            **{f"z_{n}": sim["z"][:, i] for i, n in enumerate(LATENTS)},
            **{f"p_{event}": chance for event, chance in chances.items()},
            **{col: clients[col].to_numpy() for col in HIDDEN_CLIENT_COLUMNS},
            **hidden_holdings,
            **oracle_values,
        }
    )
    return with_int_flags(mart), with_int_flags(oracle)


def with_int_flags(df: pd.DataFrame) -> pd.DataFrame:
    """`*_flag` columns as 0/1 int32, the mart's flag type (test_harness.md, types).

    Selected by name, as the checks read them; a boolean column with another name, or a flag that
    isn't boolean, is a naming error and fails loud.
    """
    flags = [c for c in df.columns if c.endswith("_flag")]
    bools = [c for c, dtype in df.dtypes.items() if dtype == np.dtype(bool)]
    if set(flags) != set(bools):
        raise ValueError(
            f"flags must be boolean and booleans named *_flag: {set(flags) ^ set(bools)}"
        )
    return df.astype(dict.fromkeys(flags, "int32"))
