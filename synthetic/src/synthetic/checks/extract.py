"""Extract checks: the feature-store extract (`fs_extract`) holds what the spec says.

`check_extract` reads the extract beside the mart's keys and holding flags and the oracle's hidden
traits. Rules (tolerance 0): the columns and their types, ids as unpadded digit strings, months as
their last day, no nulls, level features holding only the spec's levels, no key repeated or
outside the mart, each client in all of its mart months or none, and the look-ahead column equal
to the count of holding flags in the client's last mart month. Statistics, on one row per covered
client (the panel's middle month): the coverage share (binomial), each feature's rank correlation
with its trait (the spec's moderate range) and each level's share (binomial). Coverage, traits and
levels come from the spec in truth; the rest is restated from docs/components/test_harness.md
("Feature-store extract").
"""

import calendar
import datetime as dt

import numpy as np
import pandas as pd

from synthetic.checks.events import KEYS, LATENT_COLUMNS, observation_month
from synthetic.checks.mart import snapshot_columns
from synthetic.checks.table import offenders_row, range_row, rank_corr, share_row, violations_row

# Restated from the spec section "Feature-store extract".
EXTRACT_KEYS = ["customer_no", "as_of_date"]
LOOKAHEAD = "holding_cnt_trap_lookahead"
FLAGS = [
    "casa_flag",
    "cc_flag",
    "td_flag",
    "wealth_digital_flag",
    "wealth_trad_flag",
    "ebanking_flag",
]
FORM_DTYPES = {"count": "int64", "score": "int64", "logistic": "float64", "levels": "object"}
MART_COLUMNS = [*KEYS, *FLAGS]
ORACLE_COLUMNS = [*KEYS, *LATENT_COLUMNS]


def check_extract(
    mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict, extract: pd.DataFrame
) -> pd.DataFrame:
    """Every rule and statistic of the extract (see the module docstring)."""
    spec = truth["spec"]["extract"]
    keyed = extract.assign(
        client_id=pd.to_numeric(extract["customer_no"]),
        snapshot_month=[d.replace(day=1) for d in extract["as_of_date"]],
    )
    rows = _check_columns(spec, extract) + _check_keys(mart, extract, keyed)
    rows += [_check_lookahead(mart, keyed), *_check_signal(spec, mart, oracle, keyed)]
    return pd.DataFrame(rows)


def _check_columns(spec: dict, extract: pd.DataFrame) -> list[dict]:
    """The columns are the keys, the spec's features and the look-ahead column, none a mart
    column, each with its type; ids unpadded digit strings, months dates on their last day, no
    nulls."""
    dtypes = {name: FORM_DTYPES[f["form"]] for name, f in spec["features"].items()}
    expected = {"customer_no": "object", "as_of_date": "object", **dtypes, LOOKAHEAD: "int64"}
    names = [c for c in expected if c not in extract] + [c for c in extract if c not in expected]
    wrong = [c for c, t in expected.items() if c in extract and str(extract[c].dtype) != t]
    shared = sorted(set(extract.columns) & set(snapshot_columns()))
    ids = extract["customer_no"].map(lambda v: isinstance(v, str) and v.isdigit() and v[0] != "0")
    dates = extract["as_of_date"].map(
        lambda d: type(d) is dt.date and d.day == calendar.monthrange(d.year, d.month)[1]
    )
    levels = [
        violations_row(
            f"extract: {name} holds only the spec's levels", ~extract[name].isin(list(f["levels"]))
        )
        for name, f in spec["features"].items()
        if "levels" in f
    ]
    return [
        *levels,
        offenders_row(
            "extract: columns are the keys, the features and the look-ahead", names, len(expected)
        ),
        offenders_row("extract: column types", wrong, len(expected)),
        offenders_row("extract: no column shares a mart column's name", shared, len(expected)),
        violations_row("extract: customer_no an unpadded digit string", ~ids),
        violations_row("extract: as_of_date a date on the month's last day", ~dates),
        violations_row("extract: no nulls", extract.isna().any(axis=1)),
    ]


def _check_keys(mart: pd.DataFrame, extract: pd.DataFrame, keyed: pd.DataFrame) -> list[dict]:
    """Keys unique and all in the mart; a client is in all of its mart months or in none."""
    both = mart[KEYS].merge(keyed[KEYS], how="outer", indicator=True)
    outside = both["_merge"] == "right_only"
    partial = both[~outside].groupby("client_id")["_merge"].nunique() > 1
    return [
        violations_row("extract: keys unique", extract.duplicated(EXTRACT_KEYS)),
        violations_row(
            "extract: every key a mart client-month", outside[both["_merge"] != "left_only"]
        ),
        violations_row("extract: a client in all of its mart months or none", partial),
    ]


def _check_lookahead(mart: pd.DataFrame, keyed: pd.DataFrame) -> dict:
    """The look-ahead column equals the holding flags held in the client's last mart month."""
    last = mart.sort_values(KEYS).groupby("client_id")[FLAGS].last().sum(axis=1)
    expected = keyed["client_id"].map(last)
    return violations_row(
        "extract: look-ahead = flags held in the client's last month", keyed[LOOKAHEAD] != expected
    )


def _check_signal(
    spec: dict, mart: pd.DataFrame, oracle: pd.DataFrame, keyed: pd.DataFrame
) -> list[dict]:
    """Coverage share over the mart's clients; per feature, the rank correlation with its trait in
    the spec's range and each level's share, on one row per covered client (the middle month)."""
    clients = mart["client_id"].unique()
    covered = np.isin(clients, keyed["client_id"].unique())
    rows = [
        share_row("extract: coverage", "clients", spec["coverage"], covered.sum(), len(clients))
    ]
    month = observation_month(mart).date()
    one = keyed[keyed["snapshot_month"] == month].merge(oracle, on=KEYS, validate="one_to_one")
    for name, feature in spec["features"].items():
        levels = feature.get("levels")
        values = one[name].map({v: i for i, v in enumerate(levels)}) if levels else one[name]
        corr = rank_corr(values, one[f"z_{feature['trait']}"])
        check = f"extract: rank correlation with z_{feature['trait']}"
        rows.append(range_row(check, name, len(one), *spec["rank_corr_range"], corr))
        for level, share in (levels or {}).items():
            hits = int((one[name] == level).sum())
            rows.append(
                share_row("extract: level share", f"{name} = {level}", share, hits, len(one))
            )
    return rows
