"""The ground truth of a generated dataset, as it goes into `truth.json`.

`build_truth` collects what the generator knows and the mart doesn't show: seed, preset, size, the
generator and library versions (the seed-to-data mapping depends on them), the spec, the
calibrated intercepts and leaving chances, turnover per month and profile, the market index
behind wealth balances per simulated month, the column schema (`column_schema`: written type,
kind and generating mechanism of every mart column), the trap list (`trap_spec.TRAPS`), the drift
(the digital uptake trend and the app relaunch: columns, month, size), the null rule and, with
dirty data on, the record of its defects (`dirty.apply_dirty`). `with_oracle` adds the oracle's
metrics per standard target and window (`oracle.oracle_metrics`) and the relevance rankings
(`relevance.relevance_rankings`); `complete_truth` does both from a panel in memory, while
`output.write_mart` reads back what they need. Values are made JSON-safe (numpy numbers as Python
numbers, tuples as lists, dict keys as strings, NaN as null) and round-tripped through JSON, so the
truth in memory is exactly what `output.load_truth` reads back. Keys become `str(key)`: the spec's
`{True: 0.7}` reads back as `{"True": 0.7}`, so readers look levels up by their string form.
"""

import json

import numpy as np
import pandas as pd
import pyarrow as pa
import scipy

from synthetic import __version__
from synthetic.mart import arrow_schema
from synthetic.names import parse_column
from synthetic.oracle import oracle_metrics
from synthetic.relevance import relevance_rankings
from synthetic.traps import RISK_GRADE, UPSTREAM

# Mechanism (module) behind each kind of current-month value, by product or by measure.
PRODUCT_MECHANISMS = {"casa": "balances", "cc": "cards", "fx": "flows", "digital": "logins"}
MEASURE_MECHANISMS = {"inflow": "flows", "outflow": "flows", "spend": "cards", "repayment": "cards",
                      "interest": "cards", "instalment": "balances", "login": "logins"}  # fmt: skip
HOLDING_KINDS = ("flag", "active_flag", "status", "cnt", "maturity_months")
STOCK_KINDS = ("bal", "limit", "utilisation_ratio")


def complete_truth(sim: dict, mart: pd.DataFrame, oracle: pd.DataFrame) -> dict:
    """The full truth of a finished simulation whose clean panel is in memory."""
    truth = build_truth(sim, list(mart.columns))
    metrics = oracle_metrics(mart, oracle, truth)
    return with_oracle(truth, metrics, relevance_rankings(mart, oracle, truth))


def build_truth(sim: dict, columns: list[str]) -> dict:
    """The truth of a simulation (see the module docstring) without the oracle part, JSON-safe;
    `columns` are the mart's."""
    spec = sim["spec"]
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
        "spec": spec,
        "calibration": sim["calibration"],
        "turnover": sim["turnover"],
        "market_index": sim["market_index"],  # "YYYY-MM" → the shared wealth index
        "columns": column_schema(columns, list(spec["products"])),
        "traps": spec["traps"],
        "drift": _drift(spec, columns),
        "null_rule": _null_rule(columns, list(spec["products"])),
        **({"dirty": sim["dirty"]} if "dirty" in sim else {}),
    }
    # The round trip also copies the spec, so editing the truth never changes the preset.
    return _round_trip(truth)


def with_oracle(truth: dict, metrics: dict, relevance: dict) -> dict:
    """The truth with its oracle part: `oracle.targets` (`oracle.oracle_metrics`) and
    `oracle.relevance` (`relevance.relevance_rankings`), JSON-safe."""
    return _round_trip({**truth, "oracle": {"targets": metrics, "relevance": relevance}})


def column_schema(columns: list[str], products: list[str]) -> list[dict]:
    """One entry per mart column: name, written type (`mart.arrow_schema`), kind (id, time,
    static, holding, stock, flow, count, rollup, categorical, trap or noise) and the mechanism
    (module) that generates it."""
    types = arrow_schema(columns, products)
    out = []
    for name in columns:
        kind, mechanism = _kind_and_mechanism(parse_column(name, products))
        out.append({"name": name, "type": str(types.field(name).type), "kind": kind,
                    "mechanism": mechanism})  # fmt: skip
    return out


def _kind_and_mechanism(parts: dict) -> tuple[str, str]:
    """A parsed column name's (`names.parse_column`) schema kind and generating mechanism."""
    group = parts["group"]
    if group == "plain":
        plain = {"key": "id", "date": "time", "category": "categorical", "cnt": "holding"}
        kind = plain.get(parts["kind"], "static")
        return kind, {"id": "generate", "time": "generate", "holding": "holdings"}.get(
            kind, "population"
        )
    if group in ("rollup", "recency", "ratio"):
        return "rollup", "mart"
    if group == "trap":
        return ("noise" if parts["kind"] == "noise" else "trap"), "traps"
    if group == "state" and parts["kind"] in HOLDING_KINDS:
        return "holding", "holdings"
    if group == "state":
        kind = "stock" if parts["kind"] in STOCK_KINDS else "flow"
        mechanism = PRODUCT_MECHANISMS.get(parts["product"], "balances")
        return kind, "flows" if parts["product"] == "casa" and kind == "flow" else mechanism
    kind = "flow" if parts["kind"] == "vol" else "count"
    return kind, MEASURE_MECHANISMS.get(parts["measure"], "traps")


def _drift(spec: dict, columns: list[str]) -> dict:
    """The planted drift (test_harness.md, "Time effects"): the digital uptake trend and the app
    relaunch, with the columns that show each, the month and the size."""
    drift = spec["seasons"]["drift"]
    trend = spec["products"][drift["trend_product"]]
    mobile = "login_digital_mobile_cnt"
    return {
        "uptake_trend": {
            "columns": [trend.get("flag", f"{drift['trend_product']}_active_flag")],
            "from_month": spec["first_month"],
            "wake_odds_per_year": drift["wake_odds_per_year"],
        },
        "app_relaunch": {
            "columns": [c for c in columns if c.startswith(mobile)],
            "month": drift["app_relaunch_month"],
            "mobile_login_factor": drift["mobile_login_factor"],
        },
    }


def _null_rule(columns: list[str], products: list[str]) -> list[dict]:
    """Where the mart has nulls (test_harness.md, "Null rule, history and types"): the columns and
    when each is null; every other column is never null."""
    groups = {c: parse_column(c, products)["group"] for c in columns}
    of_group = {g: [c for c in columns if groups[c] == g] for g in ("rollup", "recency", "ratio")}
    maturity = [c for c in columns if c.endswith("_maturity_months")]
    months_since = [c for c in of_group["recency"] if c.startswith("months_since_last_")]
    rules = [
        (["income"], "income not declared"),
        (["residence_days"], "nationals and non-residents"),
        (["cc_utilisation_ratio"], "no card"),
        (maturity, "no account"),
        (["days_since_last_login_digital"], "never logged in"),
        (months_since, "no non-zero month since the later of relationship start and the "
                              "start of the simulation"),
        (of_group["ratio"], "fewer than 6 months on the book, or a zero average over months 3–5"),
        (of_group["rollup"], "the window reaches before relationship start (fewer months on the "
                             "book than the window); utilisation also with no card month in it"),
        ([UPSTREAM], "card holders, and the last 3 panel months"),
        ([RISK_GRADE], "always"),
    ]  # fmt: skip
    return [{"columns": cols, "null_when": when} for cols, when in rules if cols]


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
