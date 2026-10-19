"""The feature mart's columns: the name grammar, the derived columns and the written types.

Names (test_harness.md, "Names"): plain names for the keys and the client description; product
states `{product}_{kind}` (`cc_flag`, `casa_bal`); activity `{measure}_{product}[_{subcat}]_{kind}`
(`spend_cc_travel_vol`); rollups `{base}_{a}_{b}_months_{agg}` over months a..b back (0 = now);
recency `months_since_last_{base}` (and `days_since_last_login_digital`); ratios
`{base}_0_2_vs_3_5_months_ratio`; trap columns `{name}_trap_{kind}` (`traps.trap_name`).
`parse_column` reads any name back into its parts, so the checks confirm every column follows the
grammar and `arrow_schema` types a column from the kind its name carries.

Derived columns. The month loop keeps a history per client: for every rolled-up measure the last
six months' values (newest last; NaN before the client joined; utilisation NaN without a card) and
for every recency measure the month of the last non-zero value. It starts empty and the burn-in
fills it, so the panel's first month has full windows. `history_columns` turns it into:
- rollups over months 0..b, null while the client has fewer than b + 1 months on the book;
  averages leave out months without a value; `std` is the sample standard deviation (ddof 1, as
  Spark's `stddev`); `nz` counts the non-zero months;
- recency: months back to the last non-zero month (0 = now), null if none since the later of
  relationship start and the start of the simulation;
- ratios: the average of months 0–2 over that of months 3–5, null with fewer than 6 months on the
  book or a zero 3–5 average.
Derived values are not rounded. Written types: flags int32, counts int64, amounts float64,
`cc_limit` decimal(18, 2), categories strings; trap columns as `traps.TRAP_TYPES`.
"""

import re

import numpy as np
import pandas as pd
import pyarrow as pa

from synthetic.mechanisms.traps import TRAP_KINDS, TRAP_TYPES, trap_name

MEASURES = ("inflow", "outflow", "spend", "repayment", "interest", "instalment", "login",
            "application")  # fmt: skip
# Product-state kinds; `active_flag` before `flag`, so `cc_active_flag` reads as card activity.
KINDS = ("active_flag", "flag", "status", "cnt", "maturity_months", "bal", "limit",
         "utilisation_ratio", "vol")  # fmt: skip
ACTIVITY_KINDS = ("vol", "cnt")
SUBCATS = ("salary", "transfers", "other", "remittance", "cash", "bills", "travel", "retail",
           "online", "dining", "mobile")  # fmt: skip
AGGS = ("avg", "sum", "max", "min", "std", "nz")
# Plain names and their kind (what they hold), for the keys, the description and the product count.
PLAIN = {
    "client_id": "key",
    "snapshot_month": "date",
    "segment": "category",
    "subsegment": "category",
    "nationality_group": "category",
    "nationality": "category",
    "employment_status": "category",
    "income": "amount",
    "salary_transfer_flag": "flag",
    "emirate": "category",
    "onboarding_channel": "category",
    "age": "years",
    "residence_days": "days",
    "relationship_days": "days",
    "product_cnt": "cnt",
}
RECENCY_PREFIXES = {"months_since_last_": "vol", "days_since_last_": "cnt"}  # → the base's kind
RATIO_SUFFIX = "_0_2_vs_3_5_months_ratio"
ROLLUP = re.compile(rf"(?P<base>.+)_(?P<first>\d+)_(?P<last>\d+)_months_(?P<agg>{'|'.join(AGGS)})")
TRAP = re.compile(rf"(?P<name>[a-z][a-z0-9_]*?)_trap_(?P<kind>{'|'.join(TRAP_KINDS)})")
ACTIVITY = re.compile(
    rf"(?P<measure>{'|'.join(MEASURES)})_(?P<rest>.+)_(?P<kind>{'|'.join(ACTIVITY_KINDS)})"
)


def rollup_name(base: str, first: int, last: int, agg: str) -> str:
    """`{base}_{first}_{last}_months_{agg}`: `agg` over months `first`..`last` back (0 = now)."""
    if agg not in AGGS:
        raise ValueError(f"unknown aggregation {agg!r}; one of {AGGS}")
    return f"{base}_{first}_{last}_months_{agg}"


def recency_name(base: str) -> str:
    """The recency column of a `_vol` column: `spend_cc_vol` → `months_since_last_spend_cc`."""
    if not base.endswith("_vol"):
        raise ValueError(f"recency is kept for `_vol` columns, not {base!r}")
    return "months_since_last_" + base.removesuffix("_vol")


def ratio_name(base: str) -> str:
    """`{base}_0_2_vs_3_5_months_ratio`: the average of months 0–2 over that of months 3–5."""
    return base + RATIO_SUFFIX


def parse_column(name: str, products: list[str]) -> dict:
    """The parts of a column name: `group` (plain, state, activity, rollup, recency, ratio, trap)
    and the group's fields; rollups, recency and ratios carry their base's parts under `of`.

    Raises ValueError if the name doesn't follow the grammar.
    """
    if name in PLAIN:
        return {"group": "plain", "name": name, "kind": PLAIN[name]}
    trap = TRAP.fullmatch(name)
    if trap:
        return {"group": "trap", **trap.groupdict()}
    if name.endswith(RATIO_SUFFIX):
        base = name.removesuffix(RATIO_SUFFIX)
        return {"group": "ratio", "base": base, "of": _parse_value(base, products)}
    rollup = ROLLUP.fullmatch(name)
    if rollup:
        first, last = int(rollup["first"]), int(rollup["last"])
        of = _parse_value(rollup["base"], products)
        return {"group": "rollup", **rollup.groupdict(), "first": first, "last": last, "of": of}
    for prefix, kind in RECENCY_PREFIXES.items():
        if name.startswith(prefix):
            of = _parse_value(f"{name.removeprefix(prefix)}_{kind}", products)
            return {"group": "recency", "unit": prefix.split("_")[0], "of": of}
    return _parse_value(name, products)


def _parse_value(name: str, products: list[str]) -> dict:
    """A current-month value: a product state or an activity; raises ValueError otherwise."""
    for kind in KINDS:
        if name.endswith(f"_{kind}") and name.removesuffix(f"_{kind}") in products:
            return {"group": "state", "product": name.removesuffix(f"_{kind}"), "kind": kind}
    activity = ACTIVITY.fullmatch(name)
    if activity:
        product, subcat = activity["rest"], None
        if product not in products:
            product, _, subcat = product.rpartition("_")
        if product in products and (subcat is None or subcat in SUBCATS):
            parts = {"measure": activity["measure"], "product": product, "subcat": subcat}
            return {"group": "activity", **parts, "kind": activity["kind"]}
    raise ValueError(f"{name!r} doesn't follow the mart's name grammar (test_harness.md, Names)")


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
EXTRA_KINDS = ("weak", "noise")  # extra columns: floats


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
    float64; `cc_limit` decimal(18, 2); categoricals and statuses strings; trap columns as
    `TRAP_TYPES`, extra columns float64. `products` are the spec's product keys
    (`parse_column`).
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
    """The written type of a parsed column name (`parse_column`)."""
    group = parts["group"]
    if group in ("plain", "state", "activity"):
        return KIND_TYPES[parts["kind"]]
    if group == "recency" or (group == "rollup" and parts["agg"] == "nz"):
        return pa.int64()
    if group == "ratio" or (group == "rollup" and parts["agg"] not in EXTREMES):
        return pa.float64()
    if group == "rollup":
        return _written_type(parts["of"])
    if group == "trap" and parts["kind"] in EXTRA_KINDS:
        return pa.float64()
    if group == "trap":
        return TRAP_TYPES[trap_name(parts["name"], parts["kind"])]  # an unknown trap: KeyError
    raise ValueError(f"no written type for a {group} column: {parts}")
