"""The ground truth of a generated dataset, as it goes into `truth.json`.

`build_truth` collects what the generator knows and the mart doesn't show: seed, preset, size, the
generator and library versions (the seed-to-data mapping depends on them), the spec (its `traps`
list is the trap summary), the calibrated intercepts and leaving chances, the market index behind
wealth balances per simulated month, the column schema (`column_schema`: written type and kind of
every mart column) and, with dirty data on, the record of its defects (`traps.apply_dirty`).
`with_oracle` adds the oracle's metrics per standard target (`oracle.oracle_metrics`);
`complete_truth` does both from a panel in memory, while `output.write_mart` reads back what the
metrics need. Whatever anyone can recompute from the mart and the oracle file stays out.

Values are made JSON-safe (numpy numbers as Python numbers, tuples as lists, dict keys as strings,
NaN as null) and round-tripped through JSON, so the truth in memory is exactly what
`output.load_truth` reads back. Keys become `str(key)`: the spec's `{True: 0.7}` reads back as
`{"True": 0.7}`, so readers look levels up by their string form.
"""

import json

import numpy as np
import pandas as pd
import pyarrow as pa
import scipy

from synthetic import __version__
from synthetic.mechanisms.mart import arrow_schema, parse_column
from synthetic.truth.oracle import oracle_metrics

PLAIN_KINDS = {"key": "id", "date": "time", "category": "categorical", "cnt": "holding"}
HOLDING_KINDS = ("flag", "active_flag", "status", "maturity_months")
STOCK_KINDS = ("bal", "limit", "utilisation_ratio")


def complete_truth(sim: dict, mart: pd.DataFrame, oracle: pd.DataFrame) -> dict:
    """The full truth of a finished simulation whose clean panel is in memory."""
    truth = build_truth(sim, list(mart.columns))
    return with_oracle(truth, oracle_metrics(mart, oracle, truth))


def build_truth(sim: dict, columns: list[str]) -> dict:
    """The truth of a simulation (see the module docstring) without the oracle part, JSON-safe;
    `columns` are the mart's."""
    truth = {
        "generator_version": __version__,
        "versions": {
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "pandas": pd.__version__,
            "pyarrow": pa.__version__,
        },
        "seed": sim["seed"],
        "preset": sim["preset"],
        "n_clients": sim["n_clients"],
        "n_months": sim["n_months"],
        "first_month": str(sim["first_month"]),
        "spec": sim["spec"],
        "calibration": sim["calibration"],
        "market_index": sim["market_index"],  # "YYYY-MM" → the shared wealth index
        "columns": column_schema(columns, sim["spec"]["products"]),
        **({"dirty": sim["dirty"]} if "dirty" in sim else {}),
    }
    # The round trip also copies the spec, so editing the truth never changes the preset.
    return _round_trip(truth)


def with_oracle(truth: dict, metrics: dict) -> dict:
    """The truth with its oracle part, `oracle` (`oracle.oracle_metrics`), JSON-safe."""
    return _round_trip({**truth, "oracle": metrics})


def column_schema(columns: list[str], products: dict) -> list[dict]:
    """One entry per mart column: name, written type (`mart.arrow_schema`) and kind (id, time,
    static, categorical, holding, stock, flow, count, rollup, trap or noise)."""
    types = arrow_schema(columns, list(products))
    return [
        {"name": name, "type": str(types.field(name).type), "kind": _kind(name, products)}
        for name in columns
    ]


def _kind(name: str, products: dict) -> str:
    """A mart column's schema kind, from the parts of its name (`mart.parse_column`)."""
    parts = parse_column(name, list(products))
    group, kind = parts["group"], parts.get("kind")
    if group == "plain":
        return PLAIN_KINDS.get(kind, "static")
    if group == "recency" and parts["unit"] == "days":
        return "count"  # days since the last login move with the logins; not derived
    if group in ("rollup", "recency", "ratio"):
        return "rollup"
    if group == "trap":
        return "noise" if kind == "noise" else "trap"
    if group == "state" and kind == "cnt":  # an account count, or a usage product's transactions
        return "holding" if products[parts["product"]]["kind"] == "loans" else "count"
    if group == "state" and kind in HOLDING_KINDS:
        return "holding"
    if group == "state":
        return "stock" if kind in STOCK_KINDS else "flow"
    return "flow" if kind == "vol" else "count"


def _round_trip(truth: dict) -> dict:
    """`truth` made JSON-safe and read back through JSON."""
    return json.loads(json.dumps(_json_safe(truth), allow_nan=False))


def _json_safe(value: object) -> object:
    """`value` with numpy numbers as Python numbers, tuples as lists, keys as strings, NaN as None.

    Anything else JSON can't hold is left as it is, so `json.dumps` fails loud on it.
    """
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | np.ndarray):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and np.isnan(value):
        return None  # e.g. an AUC with one class empty; ±inf still fails loud
    return value
