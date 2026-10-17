"""Mart rows on a clients × months grid, so a row can read its own client's later months.

The oracle's realised targets and window probabilities (`oracle`) need, for each mart row at month
t, the same client's values at t+1, …, t+w, whatever order the rows come in. `month_grid` places
every row in the grid (client position, month position from the mart's first month); `ahead`
reads a row-aligned column some months later (NaN where the client has no row then: it left, or
the month lies past the mart's last); `oracle_rows` matches the oracle's rows to the mart's by key.
Month numbers are months since 1970-01, each distinct month converted once (millions of rows share
a few dozen months).
"""

import numpy as np
import pandas as pd


def month_grid(mart: pd.DataFrame) -> dict:
    """Each mart row's client and month position (0 = the mart's first month), and the row
    holding each cell of the grid (−1 = none); raises on duplicate client-months."""
    client, ids = pd.factorize(mart["client_id"])
    number = month_numbers(mart["snapshot_month"])
    month = number - number.min()
    row_at = np.full((len(ids), int(month.max()) + 1), -1)
    row_at[client, month] = np.arange(len(mart))
    if (row_at >= 0).sum() != len(mart):
        raise ValueError("the mart has duplicate client-months")
    return {"client": client, "month": month, "ids": ids, "first": number.min(), "row_at": row_at}


def oracle_rows(oracle: pd.DataFrame, grid: dict) -> np.ndarray:
    """The oracle row of each mart row; raises unless both tables hold the same client-months."""
    client = pd.Index(grid["ids"]).get_indexer(oracle["client_id"])
    month = month_numbers(oracle["snapshot_month"]) - grid["first"]
    row_at = grid["row_at"]
    inside = (client >= 0) & (month >= 0) & (month < row_at.shape[1])
    mart_row = np.full(len(oracle), -1)
    mart_row[inside] = row_at[client[inside], month[inside]]
    n = len(grid["client"])
    if len(oracle) != n or (mart_row < 0).any() or np.unique(mart_row).size != n:
        raise ValueError("the oracle must hold exactly the mart's client-months")
    out = np.empty(n, dtype=int)
    out[mart_row] = np.arange(n)
    return out


def ahead(grid: dict, values: np.ndarray, offsets: range | list[int]) -> np.ndarray:
    """Rows × offsets: each row's client's `values` (aligned with the mart) that many months
    later (offsets ≥ 0); NaN where the client has no row then or the month is past the mart's."""
    row_at, values = grid["row_at"], np.asarray(values, dtype=float)
    out = np.full((len(grid["client"]), len(offsets)), np.nan)
    for j, offset in enumerate(offsets):  # one offset at a time keeps the temporaries small
        at = grid["month"] + offset
        inside = np.flatnonzero(at < row_at.shape[1])
        source = row_at[grid["client"][inside], at[inside]]
        found = source >= 0
        out[inside[found], j] = values[source[found]]
    return out


def stays(grid: dict, w: int) -> np.ndarray:
    """Rows whose client has a row in each of the `w` months after (inside the mart)."""
    present = ahead(grid, np.zeros(len(grid["client"])), range(1, w + 1))
    return ~np.isnan(present).any(axis=1)


def months_on_book(mart: pd.DataFrame) -> np.ndarray:
    """Monthly steps lived by the end of each row's month, the join month included, from
    `relationship_days` (counted to the month's last day, as `month_rows` writes it)."""
    month = month_numbers(mart["snapshot_month"])
    month_end = (month + 1).astype("datetime64[M]").astype("datetime64[D]").astype(int) - 1
    days = mart["relationship_days"].to_numpy(dtype="int64")
    start = (month_end - days).astype("datetime64[D]")
    return month - start.astype("datetime64[M]").astype(int) + 1


def month_numbers(stamps: pd.Series) -> np.ndarray:
    """Months since 1970-01 of date values (each distinct month converted once)."""
    codes, months = pd.factorize(stamps)
    numbers = np.array([np.datetime64(month, "M").astype(int) for month in months])
    return numbers[codes]


def as_float(values: object) -> np.ndarray:
    """Values as a float array, missing values as NaN (nullable integers included)."""
    return pd.Series(values).to_numpy(dtype=float, na_value=np.nan)
