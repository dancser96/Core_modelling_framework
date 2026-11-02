"""The feature-store extract (`fs_extract`): a second feature source with its own keys (D-064).

`extract_frame` builds it from a finished clean panel (the mart's keys and holding flags, the
oracle's hidden traits), so it runs after the month loop and never moves the mart, the oracle or
the holdings. Draws, from the `extract` stream in this order: one uniform per client in client
order (covered when below the spec's coverage), then one standard normal per covered row and
feature, the rows sorted by month and client. A feature mixes its trait's normal score (from the
trait's ranks within the month) with that noise at the Pearson correlation whose rank correlation
is the spec's, (6/π)·asin(ρ/2) for normal data, then takes its monotone form (`spec.extract`).
The look-ahead trap column counts the holding flags of the client's last panel month and stamps it
on every month: a "current" value pulled today and written over history.
"""

import numpy as np
import pandas as pd
import pyarrow as pa
from scipy.special import expit
from scipy.stats import norm

from synthetic.mechanisms.traps import trap_name, trap_record

KEYS = ["client_id", "snapshot_month"]
EXTRACT_KEYS = ["customer_no", "as_of_date"]  # named unlike the mart's: the id is a string
LOOKAHEAD = trap_name("holding_cnt", "lookahead")
FORM_TYPES = {"count": pa.int64(), "score": pa.int64(), "logistic": pa.float64()}


def extract_frame(
    spec: dict, mart: pd.DataFrame, oracle: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    """The extract of a clean panel: keys, the spec's features and the look-ahead column, one row
    per covered client per mart month, sorted by month and client.

    `mart` needs the keys and the look-ahead's holding flags, `oracle` the keys and the `z_*`
    traits of the spec's features.
    """
    cfg, flags = spec["extract"], trap_record(spec, "lookahead")["parameters"]["flags"]
    traits = [f"z_{f['trait']}" for f in cfg["features"].values()]
    panel = mart[[*KEYS, *flags]].merge(
        # once per trait: two features proxy the digital trait
        oracle[[*KEYS, *dict.fromkeys(traits)]],
        on=KEYS,
        validate="one_to_one",
    )
    if len(panel) != len(mart):
        raise ValueError("oracle rows must line up with mart rows")
    panel = panel.sort_values(["snapshot_month", "client_id"], ignore_index=True)
    last = panel.groupby("client_id")[flags].last().sum(axis=1)  # rows are in month order
    clients = np.sort(panel["client_id"].unique())
    covered = clients[rng.random(len(clients)) < cfg["coverage"]]
    rows = panel[panel["client_id"].isin(covered)].reset_index(drop=True)
    noise = rng.standard_normal((len(rows), len(cfg["features"])))
    month_end = pd.to_datetime(rows["snapshot_month"]) + pd.offsets.MonthEnd(0)
    frame = pd.DataFrame(
        {"customer_no": rows["client_id"].astype(str), "as_of_date": month_end.dt.date}
    )
    for j, (name, feature) in enumerate(cfg["features"].items()):
        score = _normal_score(rows, f"z_{feature['trait']}")
        rho = 2 * np.sin(np.pi * feature["rank_corr"] / 6)
        frame[name] = _form(feature, rho * score + np.sqrt(1 - rho**2) * noise[:, j])
    frame[LOOKAHEAD] = rows["client_id"].map(last).to_numpy(dtype=np.int64)
    return frame


def extract_schema(spec: dict) -> pa.Schema:
    """The extract's written types: the id a string, the month a date, counts and scores int64,
    logistic features double, levels strings, the look-ahead count int64."""
    features = spec["extract"]["features"]
    fields = [pa.field("customer_no", pa.string()), pa.field("as_of_date", pa.date32())]
    fields += [pa.field(n, FORM_TYPES.get(f["form"], pa.string())) for n, f in features.items()]
    return pa.schema([*fields, pa.field(LOOKAHEAD, pa.int64())])


def _normal_score(rows: pd.DataFrame, trait: str) -> np.ndarray:
    """The trait's normal score within each month: Φ⁻¹(rank / (n + 1)), standard normal."""
    month = rows.groupby("snapshot_month")[trait]
    return norm.ppf((month.rank() / (month.transform("size") + 1)).to_numpy())


def _form(feature: dict, s: np.ndarray) -> np.ndarray:
    """A feature's values from its standard normal `s`, by the spec's monotone form."""
    form = feature["form"]
    if form == "count":
        return np.round(feature["median"] * np.exp(feature["spread"] * s)).astype(np.int64)
    if form == "score":
        values = np.round(feature["centre"] + feature["scale"] * s)
        return np.clip(values, feature["low"], feature["high"]).astype(np.int64)
    if form == "logistic":
        return np.round(expit(feature["centre"] + feature["scale"] * s), 3)
    if form == "levels":
        names, shares = list(feature["levels"]), np.array(list(feature["levels"].values()))
        if not np.isclose(shares.sum(), 1):
            raise ValueError(f"level shares must sum to 1, not {shares.sum()}: {feature}")
        return np.array(names, dtype=object)[np.searchsorted(norm.ppf(shares.cumsum()[:-1]), s)]
    raise ValueError(f"unknown extract feature form {form!r}")
