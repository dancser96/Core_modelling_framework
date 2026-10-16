"""The feature mart's derived columns (rollups, recency, ratios) and the types it is written with.

The month loop (`generate.advance_simulation`) keeps a history per client: for every rolled-up
measure the last six months' values (newest last; NaN before the client joined, and utilisation is
NaN in months without a card), and for every recency measure the month index of the last non-zero
value (NaN = none yet). The history starts empty for every client, the starting book included, and
the burn-in months fill it, so the panel's first month has full windows. It is per-client state,
reindexed every month like the rest (`generate._keep_and_append`). `history_columns` turns it into
the mart's derived columns (test_harness.md, "Columns" and "Null rule, history and types"):
- a rollup over months 0..b is null while the client has fewer than b + 1 months on the book
  (`population.months_on_book`, 1 in the join month); averages leave out months without a value
  (utilisation averages the months with a card) and are null if none has one; `std` is the sample
  standard deviation (ddof 1, as Spark's `stddev`); `nz` counts the non-zero months;
- recency counts months back to the last non-zero month (0 = non-zero now), null if there is none
  since the later of relationship start and the start of the simulation;
- a ratio is the average of months 0–2 over that of months 3–5, null with fewer than 6 months on
  the book or a zero 3–5 average.
Derived values are not rounded. `arrow_schema` gives every column its written type from the kind
its name carries (`names.parse_column`).
"""

import numpy as np
import pandas as pd
import pyarrow as pa

from synthetic.names import parse_column, ratio_name, recency_name, rollup_name

WINDOW_MONTHS = 6  # the longest window: months 0–5
AVERAGED = (  # 3- and 6-month averages
    "casa_bal", "cc_bal", "inflow_casa_vol", "inflow_casa_salary_vol", "inflow_casa_other_vol",
    "outflow_casa_vol", "outflow_casa_remittance_vol", "outflow_casa_cash_vol",
    "outflow_casa_bills_vol", "outflow_casa_cnt", "spend_cc_vol", "spend_cc_cnt",
    "spend_cc_travel_vol", "spend_cc_online_vol", "cc_utilisation_ratio", "fx_vol",
    "login_digital_mobile_cnt", "login_digital_online_cnt",
)  # fmt: skip
AVERAGED_6 = ("td_bal", "wealth_digital_bal", "wealth_trad_bal", "loan_personal_bal")
OTHER_6 = {  # other 6-month aggregates
    "casa_bal": ("min", "max", "std"),
    "inflow_casa_vol": ("max", "std", "nz"),
    "spend_cc_vol": ("max", "std", "nz"),
    "spend_cc_travel_vol": ("nz",),
    "fx_vol": ("max", "std", "nz"),
    "login_digital_mobile_cnt": ("max", "std", "nz"),
}
# (base, months, agg) in the mart's column order.
ROLLUPS = [
    *[(base, months, "avg") for base in AVERAGED for months in (3, WINDOW_MONTHS)],
    *[(base, WINDOW_MONTHS, "avg") for base in AVERAGED_6],
    *[(base, WINDOW_MONTHS, agg) for base, aggs in OTHER_6.items() for agg in aggs],
]
RECENCY = ["inflow_casa_vol", "outflow_casa_remittance_vol", "outflow_casa_cash_vol",
           "spend_cc_vol", "fx_vol"]  # fmt: skip
RATIOS = ["casa_bal", "inflow_casa_vol", "spend_cc_vol", "login_digital_mobile_cnt"]
HISTORY_BASES = list(dict.fromkeys([base for base, _, _ in ROLLUPS] + RATIOS))
DERIVED_COLUMNS = [
    *[rollup_name(base, 0, months - 1, agg) for base, months, agg in ROLLUPS],
    *map(recency_name, RECENCY),
    *map(ratio_name, RATIOS),
]
EXTREMES = ("max", "min", "sum")  # aggregations that keep their base's type
# Written type of each kind a column name carries (test_harness.md, types).
KIND_TYPES = {
    "key": pa.int64(),
    "date": pa.date32(),
    "category": pa.string(),
    "status": pa.string(),
    "amount": pa.float64(),
    "bal": pa.float64(),
    "vol": pa.float64(),
    "utilisation_ratio": pa.float64(),
    "limit": pa.decimal128(18, 2),
    "flag": pa.int32(),
    "active_flag": pa.int32(),
    "cnt": pa.int64(),
    "maturity_months": pa.int64(),
    "years": pa.int64(),
    "days": pa.int64(),
}


def start_history(n: int) -> dict[str, np.ndarray]:
    """The history of `n` new clients: no month in any window, no non-zero month yet."""
    windows = {base: np.full((n, WINDOW_MONTHS), np.nan) for base in HISTORY_BASES}
    return windows | {recency_name(column): np.full(n, np.nan) for column in RECENCY}


def advance_history(
    history: dict[str, np.ndarray], values: dict[str, object], month_index: int
) -> dict[str, np.ndarray]:
    """The history after this month: each window moves on by one month, and a non-zero value
    makes this month (`month_index`) the last non-zero one.

    `values` are the month's mart amounts (`amounts.step_amounts`), aligned with the history.
    """
    windows = {
        base: np.column_stack([history[base][:, 1:], np.asarray(values[base], dtype=float)])
        for base in HISTORY_BASES
    }
    last = {
        recency_name(c): np.where(np.asarray(values[c]) != 0, month_index, history[recency_name(c)])
        for c in RECENCY
    }
    return windows | last


def history_columns(
    history: dict[str, np.ndarray], months_on_book: np.ndarray, month_index: int
) -> dict[str, object]:
    """The month's rollups, recency and ratios, in the mart's column order (`DERIVED_COLUMNS`)."""
    rollups = {
        rollup_name(base, 0, months - 1, agg): _rollup(
            history[base][:, -months:], agg, months_on_book < months, base.endswith("_cnt")
        )
        for base, months, agg in ROLLUPS
    }
    recency = {
        recency_name(c): pd.array(month_index - history[recency_name(c)], dtype="Int64")
        for c in RECENCY
    }
    ratios = {ratio_name(base): _ratio(history[base], months_on_book) for base in RATIOS}
    return rollups | recency | ratios


def arrow_schema(columns: list[str], products: list[str]) -> pa.Schema:
    """The written type of each mart column, from the kind its name carries.

    Flags int32; counts and nullable counters int64; amounts, averages, deviations and ratios
    float64; `cc_limit` decimal(18, 2); categoricals and statuses strings. `products` are the
    spec's product keys (`names.parse_column`).
    """
    return pa.schema([(name, _written_type(parse_column(name, products))) for name in columns])


def _rollup(window: np.ndarray, agg: str, short: np.ndarray, of_count: bool) -> object:
    """One rollup over each client's window; null where the window reaches before joining.

    Counts of non-zero months, and extremes of counts, are nullable integers; the rest floats.
    """
    values = np.where(short, np.nan, _aggregate(window, agg))
    if agg == "nz" or (of_count and agg in EXTREMES):
        return pd.array(values, dtype="Int64")
    return values


def _aggregate(window: np.ndarray, agg: str) -> np.ndarray:
    """One aggregation of each row of `window` (clients × months).

    The average leaves out months without a value (NaN) and is NaN if none has one; the other
    aggregations are taken where every month has a value (no other measure has NaN months).
    """
    known = ~np.isnan(window)
    if agg == "avg":
        count = known.sum(axis=1)
        total = np.where(known, window, 0.0).sum(axis=1)
        return np.divide(total, count, out=np.full(len(window), np.nan), where=count > 0)
    if agg == "nz":
        return (known & (window != 0)).sum(axis=1).astype(float)
    if agg == "std":
        return window.std(axis=1, ddof=1)
    return {"max": np.max, "min": np.min, "sum": np.sum}[agg](window, axis=1)


def _ratio(window: np.ndarray, months_on_book: np.ndarray) -> np.ndarray:
    """The average of months 0–2 over that of months 3–5 (oldest first in `window`); null with
    fewer than 6 months on the book or a zero 3–5 average."""
    recent, earlier = window[:, 3:].mean(axis=1), window[:, :3].mean(axis=1)
    defined = (months_on_book >= WINDOW_MONTHS) & (earlier != 0)
    return np.divide(recent, earlier, out=np.full(len(window), np.nan), where=defined)


def _written_type(parts: dict) -> pa.DataType:
    """The written type of a parsed column name (`names.parse_column`)."""
    group = parts["group"]
    if group in ("plain", "state", "activity"):
        return KIND_TYPES[parts["kind"]]
    if group == "recency" or (group == "rollup" and parts["agg"] == "nz"):
        return pa.int64()
    if group == "ratio" or (group == "rollup" and parts["agg"] not in EXTREMES):
        return pa.float64()
    if group == "rollup":
        return _written_type(parts["of"])
    raise ValueError(f"no written type for a {group} column: {parts}")
