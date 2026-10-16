"""The mart's column-name grammar (test_harness.md, "Names"): building derived names, parsing any.

Every mart column comes from one grammar: plain names for the keys and the client description;
product states `{product}_{kind}` (`cc_flag`, `casa_bal`); activity
`{measure}_{product}[_{subcat}]_{kind}` (`spend_cc_travel_vol`); rollups
`{base}_{a}_{b}_months_{agg}` over months a..b back (0 = the current month); recency
`months_since_last_{base}` (and `days_since_last_login_digital`); ratios
`{base}_0_2_vs_3_5_months_ratio`; planted traps `{name}_trap_{kind}`. `mart` builds the derived
names with the functions here; `parse_column` reads any name back into its parts, so the mart
checks can confirm every column follows the grammar and `mart.arrow_schema` can type a column from
its kind. Product keys come from the spec (`list(spec["products"])`, usage chains included).
"""

import re

MEASURES = ("inflow", "outflow", "spend", "repayment", "interest", "instalment", "login",
            "application")  # fmt: skip
# Product-state kinds; `active_flag` before `flag`, so `cc_active_flag` reads as card activity.
KINDS = ("active_flag", "flag", "status", "cnt", "maturity_months", "bal", "limit",
         "utilisation_ratio", "vol")  # fmt: skip
ACTIVITY_KINDS = ("vol", "cnt")
SUBCATS = ("salary", "transfers", "other", "remittance", "cash", "bills", "travel", "retail",
           "online", "dining", "mobile")  # fmt: skip
AGGS = ("avg", "sum", "max", "min", "std", "nz")
TRAP_KINDS = ("leak", "upstream_target", "process_leak", "null_control", "near_constant",
              "all_null", "weak", "noise")  # fmt: skip
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


def trap_name(name: str, kind: str) -> str:
    """`{name}_trap_{kind}`: a planted trap column (D-069), e.g. `extra_0001_trap_weak`."""
    if kind not in TRAP_KINDS:
        raise ValueError(f"unknown trap kind {kind!r}; one of {TRAP_KINDS}")
    return f"{name}_trap_{kind}"


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
