"""Dirty-data switches: defects planted in a finished panel, off by default (trap summary, "Dirty
switches").

Real marts arrive with defects the framework's contract checks and operational monitoring must
catch: duplicate client-months, a month whose digital login columns are null (an outage), declared
income × 12 from one month on (a unit change: annual instead of monthly), and a few current/savings
balances × 1,000 (typos). `apply_dirty` plants all four in a whole panel at once and returns the
record that goes to `truth["dirty"]`, so the checks know exactly what to find; `dirty_panel` does
it for the month loop's (mart, oracle) months, which `generate.generate_mart` and
`output.write_mart` call with `dirty=True` (meant for small presets: the panel is held in memory).
The draws come from the `traps` stream after every month has run, so switching the defects on
changes no clean value. The oracle stays clean.
"""

import numpy as np
import pandas as pd

from synthetic.traps import trap_record

KEYS = ["client_id", "snapshot_month"]


def dirty_panel(
    sim: dict, frames: list[tuple[pd.DataFrame, pd.DataFrame]]
) -> tuple[dict, list[tuple[pd.DataFrame, pd.DataFrame]]]:
    """The panel months with the defects planted in their mart rows, and the simulation with the
    record (`sim["dirty"]`, for truth); each mart month keeps its duplicates."""
    mart = pd.concat([m for m, _ in frames], ignore_index=True)
    mart, record = apply_dirty(sim["spec"], mart, sim["rngs"]["traps"])
    months = mart["snapshot_month"].to_numpy()
    dirty = [
        (mart[months == m["snapshot_month"].iloc[0]].reset_index(drop=True), o) for m, o in frames
    ]
    return dict(sim, dirty=record), dirty


def apply_dirty(
    spec: dict, mart: pd.DataFrame, rng: np.random.Generator
) -> tuple[pd.DataFrame, dict]:
    """The mart with every defect planted, and its record for `truth["dirty"]`.

    Record: `duplicate_rows` (extra rows repeating a client-month), `outage_month` and
    `unit_change_month` ("YYYY-MM-DD"), `outage_columns`, `unit_change_factor`, `typo_factor` and
    `typos` (a list of `{client_id, snapshot_month}`). Duplicates are copied last, so they repeat
    the defective rows, and sit right after their originals. Draws: the typo rows, then the
    duplicated rows.
    """
    p = trap_record(spec, "dirty")["parameters"]
    outage, change = (_month_of(mart, p[key]) for key in ("outage_month", "unit_change_month"))
    month = mart["snapshot_month"].to_numpy()
    in_outage = month == outage
    mart = mart.assign(
        income=np.where(month >= change, mart["income"] * p["unit_change_factor"], mart["income"]),
        **{c: _nulled(mart[c], in_outage) for c in p["outage_columns"]},
    )
    typos = rng.choice(_typo_candidates(mart), size=p["typos"], replace=False)
    balance = mart["casa_bal"].to_numpy().copy()
    balance[typos] *= p["typo_factor"]
    mart = mart.assign(casa_bal=balance)
    copies = rng.choice(len(mart), size=round(p["duplicate_share"] * len(mart)), replace=False)
    rows = np.sort(np.concatenate([np.arange(len(mart)), copies]), kind="stable")
    record = {
        "duplicate_rows": len(copies),
        "outage_month": outage.isoformat(),
        "outage_columns": p["outage_columns"],
        "unit_change_month": change.isoformat(),
        "unit_change_factor": p["unit_change_factor"],
        "typo_factor": p["typo_factor"],
        "typos": [
            {"client_id": int(c), "snapshot_month": m.isoformat()}
            for c, m in mart.iloc[np.sort(typos)][KEYS].itertuples(index=False)
        ],
    }
    return mart.iloc[rows].reset_index(drop=True), record


def _month_of(mart: pd.DataFrame, month: str) -> object:
    """The panel's `snapshot_month` value of a "YYYY-MM" month; raises if the panel lacks it."""
    found = [m for m in mart["snapshot_month"].unique() if m.isoformat()[:7] == month]
    if len(found) != 1:
        raise ValueError(f"dirty-data month {month} is not in the panel")
    return found[0]


def _nulled(column: pd.Series, where: np.ndarray) -> pd.Series:
    """`column` with nulls where `where` holds; integer counts become nullable integers."""
    if pd.api.types.is_integer_dtype(column):
        column = column.astype("Int64")
    return column.mask(where)


def _typo_candidates(mart: pd.DataFrame) -> np.ndarray:
    """Rows a typo stands out in: a positive balance at least the client's median, of a client
    with two or more months (so × 1,000 lies far above its other months)."""
    by_client = mart.groupby("client_id")["casa_bal"]
    median, months = by_client.transform("median"), by_client.transform("size")
    usable = (mart["casa_bal"] > 0) & (mart["casa_bal"] >= median) & (months >= 2)
    return np.flatnonzero(usable.to_numpy())
