"""Realised targets over forward windows, computed by the checks' own code (D-066).

The oracle prices events exactly as the spec defines them in the mart, and the oracle module has
its own realised targets; these are a second implementation, written from the spec's standard
targets table alone, so `checks_oracle` can compare the two and the trap checks never share a
target with the generator. A column is laid out as a clients × months grid (NaN where the client
has no row), and each mart row reads its own client's months t, t+1, …, t+w from it: one window
offset at a time, never a loop over clients. Events, for an observation at month t:
- `any_flag`: the column is 1 in any month of (t, t+w] (acquisition, activation);
- `count_rise`: the column rises month on month in any month of (t, t+w] (loan openings);
- `sum`: the column summed over t+1..t+w (the regression target).
A target is NaN where the client isn't eligible at t, where it has no row in some month of the
window (it left), and where the window runs past the mart's last month. Two helpers serve the trap
checks: `to_panel` (mart and oracle side by side) and `observation_month` (the month a statistic
that needs one row per client reads).
"""

import numpy as np
import pandas as pd

KEYS = ["client_id", "snapshot_month"]

# The spec's standard targets: the event, the column it is read from, and eligibility at t as
# column → required value (docs/components/test_harness.md, "Ground truth and oracle").
STANDARD_TARGETS = {
    **{
        f"{key}_acquire": dict(event="any_flag", column=f"{key}_flag", eligible={f"{key}_flag": 0})
        for key in ("cc", "td", "wealth_digital", "wealth_trad", "ebanking")
    },
    **{
        f"{key}_open": dict(event="count_rise", column=f"{key}_cnt", eligible={})
        for key in ("loan_personal", "loan_auto", "loan_home")
    },
    "fx_activate": dict(event="any_flag", column="fx_active_flag", eligible={"fx_active_flag": 0}),
    "digital_activate": dict(
        event="any_flag",
        column="digital_active_flag",
        eligible={"ebanking_flag": 1, "digital_active_flag": 0},
    ),
    "cc_activate": dict(
        event="any_flag", column="cc_active_flag", eligible={"cc_flag": 1, "cc_active_flag": 0}
    ),
    "casa_reactivate": dict(
        event="any_flag",
        column="casa_active_flag",
        eligible={"casa_flag": 1, "casa_active_flag": 0},
    ),
    "spend_cc_next_3_months": dict(event="sum", column="spend_cc_vol", eligible={"cc_flag": 1}),
}
BINARY_TARGETS = [name for name, t in STANDARD_TARGETS.items() if t["event"] != "sum"]


def realised_target(mart: pd.DataFrame, target: str, w: int) -> pd.Series:
    """The realised `target` over the `w` months after each row's month, aligned with `mart`.

    0/1 (or the window sum) where defined, NaN where not eligible, left or past the last month.
    """
    spec = STANDARD_TARGETS[target]  # an unknown target raises KeyError
    values = values_at(mart, spec["column"], range(w + 1))
    future = values[:, 1:]
    if spec["event"] == "any_flag":
        hit = (future == 1).any(axis=1)
    elif spec["event"] == "count_rise":
        hit = (np.diff(values, axis=1) > 0).any(axis=1)
    else:
        hit = future.sum(axis=1)
    eligible = np.ones(len(mart), dtype=bool)
    for column, value in spec["eligible"].items():
        eligible &= mart[column].astype("float64").to_numpy() == value
    defined = eligible & ~np.isnan(future).any(axis=1)
    return pd.Series(np.where(defined, hit, np.nan), index=mart.index, name=target)


def values_at(mart: pd.DataFrame, column: str, offsets: range | list[int]) -> np.ndarray:
    """Rows × offsets: each row's client's `column` that many months after the row's month.

    Offsets may be negative (earlier months). NaN where the client has no row in that month or the
    month lies outside the mart's months. Mart rows may come in any order.
    """
    client, month, n_months = _positions(mart)
    grid = np.full((client.max() + 1, n_months), np.nan)
    grid[client, month] = mart[column].astype("float64").to_numpy()
    at = month[:, None] + np.asarray(offsets)[None, :]
    inside = (at >= 0) & (at < n_months)
    values = np.full(at.shape, np.nan)
    values[inside] = grid[np.broadcast_to(client[:, None], at.shape)[inside], at[inside]]
    return values


def _positions(mart: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, int]:
    """Each row's client position, month position (0 = the mart's first month), and the number of
    months from the first to the last; raises on duplicate client-months."""
    client = pd.factorize(mart["client_id"])[0]
    stamps = pd.to_datetime(mart["snapshot_month"])
    number = (stamps.dt.year * 12 + stamps.dt.month).to_numpy()
    month = number - number.min()
    n_months = int(month.max()) + 1
    if np.bincount(client * n_months + month).max() > 1:
        raise ValueError("the mart has duplicate client-months")
    return client, month, n_months


def to_panel(mart: pd.DataFrame, oracle: pd.DataFrame) -> pd.DataFrame:
    """Mart and oracle columns side by side, sorted by client and month, indexed 0..n−1.

    Raises unless both tables hold the same client-months.
    """
    mart, oracle = (df.sort_values(KEYS, ignore_index=True) for df in (mart, oracle))
    if not mart[KEYS].equals(oracle[KEYS]):
        raise ValueError("oracle rows must line up with mart rows")
    return pd.concat([mart, oracle.drop(columns=KEYS)], axis=1)


def observation_month(mart: pd.DataFrame) -> pd.Timestamp:
    """The mart's middle month, for one row per client (of 24: month 12, so 6-month windows fit)."""
    months = np.sort(pd.to_datetime(mart["snapshot_month"]).unique())
    return pd.Timestamp(months[(len(months) - 1) // 2])
