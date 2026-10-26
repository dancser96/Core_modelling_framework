"""Mart checks: the feature mart's form — names, the column list, 0/1 flags, the null rule and the
types in memory.

Expectations are restated from the spec ("Feature mart" in docs/components/test_harness.md), never
taken from the generator: columns are classified by the spec's name grammar (rollups
`{base}_{a}_{b}_months_{agg}`, ratios, recency, `_trap_{kind}`), and each nullable column's cases
are recomputed from other mart columns. Months on the book come from `relationship_days` and the
month, as `events.build_panel`'s tenure + 1 (1 in the entry month). A rollup over months 0–b is null
while fewer than b + 1 months are on the book (a ratio needs 6); a utilisation rollup also while no
month of its window had a card, a ratio also when its 3–5 average is 0. A "since last" column is
null until a first non-zero month since joining. Earlier months come from
`events.values_at`; where the history a case needs lies before the mart's first month (the
burn-in), only what the visible months decide is checked. Columns filled at random (missing
income, the low-fill traps, the missing-value leak) have no null rule here: the traps family checks
their fill shares. Rollup values are left to the Spark recompute in the tests. Every row is a rule
(tolerance 0). The family reads every mart column (`MART_COLUMNS = None`) and only the oracle's
keys, which it doesn't use.
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd

from synthetic.checks.events import values_at
from synthetic.checks.table import offenders_row, row
from synthetic.mechanisms.mart import parse_column

MART_COLUMNS = None  # every column: names, nulls and types are checked on all of them
ORACLE_COLUMNS = ["client_id", "snapshot_month"]

SNAPSHOT = Path(__file__).parents[4] / "tests" / "data" / "synthetic_mart_columns.txt"
ROLLUP = re.compile(
    r"^(?P<base>.+)_(?P<first>\d+)_(?P<last>\d+)_months_(?P<agg>avg|sum|max|min|std|nz)$"
)
RATIO = re.compile(r"^(?P<base>.+)_0_2_vs_3_5_months_ratio$")
RATIO_MONTHS = 6  # months 0–5 on the book
TRAP = re.compile(r"_trap_[a-z_]+$")
EXTRA = re.compile(r"^extra_\d{4}_trap_(weak|noise)$")  # off by default; not in the snapshot
UPSTREAM = re.compile(
    r"^(?P<product>.+)_acquire_next_(?P<months>\d+)_months_flag_trap_upstream_target$"
)
# The 3–5 average comes from the identity 3·avg(3–5) = 6·avg(0–5) − 3·avg(0–2). Averages of amounts
# may be rounded to 0.01, which leaves up to 0.015 of rounding in it; a non-zero 3–5 average of
# amounts in AED, or of counts (at least 1/3), lies far above 0.02.
ZERO_AVERAGE = 0.02
STRING_COLUMNS = (
    "segment",
    "subsegment",
    "nationality_group",
    "nationality",
    "employment_status",
    "emirate",
    "onboarding_channel",
    "preferred_language",
    "booking_country",
    "referral_branch_code",
    "complaint_category",
    "cc_offer_code",
)
INTEGER_COLUMNS = (
    "age",
    "relationship_days",
    "residence_days",
    "days_since_last_login_digital",
    "statement_cycle_days",
    "relationship_months",
)
# Filled at random, so no null rule: income (not at random, plus a little at random) and the traps
# whose fill shares the traps family checks.
ANY_NULLS = (
    "income",
    "loyalty_points_bal_trap_low_fill",
    "complaint_category_trap_low_fill",
    "cc_offer_code_trap_missing_leak",
)


def check_mart(mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict) -> pd.DataFrame:
    """Names parse, the column list, 0/1 flags, the null rule and the types in memory.

    `oracle` is unused: every family takes the same arguments.
    """
    spec = truth["spec"]
    rows = [_check_names(mart, spec), _check_column_list(mart), _check_flags(mart)]
    rows += _check_null_rule(mart, spec) + _check_types(mart)
    return pd.DataFrame(rows)


def snapshot_columns() -> list[str]:
    """The committed column snapshot (`tests/data/synthetic_mart_columns.txt`), in order."""
    if not SNAPSHOT.is_file():
        raise FileNotFoundError(f"the mart column snapshot is missing: {SNAPSHOT}")
    return SNAPSHOT.read_text().split()


def _check_names(mart: pd.DataFrame, spec: dict) -> dict:
    """Every column name parses with the spec's grammar (`mart.parse_column`, under test)."""
    failed = []
    for name in mart.columns:
        try:
            parse_column(name, list(spec["products"]))
        except ValueError:  # the API's way of saying the name breaks the grammar
            failed.append(name)
    return offenders_row("every column name parses", failed, mart.shape[1])


def _check_column_list(mart: pd.DataFrame) -> dict:
    """The mart's columns, extra columns aside, are the committed snapshot's, in its order."""
    expected = snapshot_columns()
    actual = [c for c in mart.columns if not EXTRA.match(c)]
    offenders = [f"missing {c}" for c in expected if c not in actual]
    offenders += [f"unexpected {c}" for c in actual if c not in expected]
    if not offenders and actual != expected:
        first = next(a for a, b in zip(actual, expected, strict=True) if a != b)
        offenders = [f"out of order from {first}"]
    return offenders_row("column list equals the snapshot", offenders, len(expected))


def _check_flags(mart: pd.DataFrame) -> dict:
    """Flags hold only 0 and 1 (nulls aside: the upstream target is null by design)."""
    flags = [c for c in mart.columns if TRAP.sub("", c).endswith("_flag")]
    bad = [c for c in flags if not mart[c].dropna().isin([0, 1]).all()]
    return offenders_row("flags hold only 0/1", bad, len(flags))


def _check_null_rule(mart: pd.DataFrame, spec: dict) -> list[dict]:
    """One row per nullable column (null exactly in its spec cases), then no nulls elsewhere.

    A case is 1 (must be null), 0 (must not be) or NaN (the mart can't tell, left out).
    """
    cases = {**_rollup_cases(mart), **_since_last_cases(mart), **_state_cases(mart, spec)}
    rows = []
    for column, (rule, want) in cases.items():
        known = ~np.isnan(want)
        bad = mart[column].isna().to_numpy()[known] != (want[known] == 1)
        share = float(bad.mean()) if bad.size else np.nan  # nothing to judge fails the row
        rows.append(row(f"null rule: {column}", rule, bad.size, 0, share, 0, rule=True))
    ruled = [*cases, *ANY_NULLS]
    columns = [c for c in mart.columns if c not in ruled]
    with_nulls = [c for c in columns if mart[c].isna().any()]
    rows.append(offenders_row("no nulls outside the null rule", with_nulls, len(columns)))
    return rows


def _months_on_book(mart: pd.DataFrame) -> np.ndarray:
    """Months on the book, the current one included (1 in the entry month): `build_panel`'s
    tenure + 1."""
    month = pd.to_datetime(mart["snapshot_month"])
    month_end = month + pd.to_timedelta(month.dt.days_in_month - 1, unit="D")
    start = month_end - pd.to_timedelta(mart["relationship_days"], unit="D")
    return ((month.dt.year - start.dt.year) * 12 + month.dt.month - start.dt.month + 1).to_numpy()


def _numbers(mart: pd.DataFrame, column: str) -> np.ndarray:
    """A numeric column as floats, NaN for nulls."""
    return mart[column].to_numpy(dtype=float, na_value=np.nan)


def _rollup_cases(mart: pd.DataFrame) -> dict[str, tuple[str, np.ndarray]]:
    """Rollups and ratios: null while the window reaches before relationship start; utilisation's
    also with no card month in the window, ratios also with a zero 3–5 average."""
    on_book, cases = _months_on_book(mart), {}
    for column in mart.columns:
        rollup, ratio = ROLLUP.match(column), RATIO.match(column)
        if rollup:
            months = int(rollup["last"]) + 1
            short = on_book < months
            if rollup["base"] == "cc_utilisation_ratio":
                rule = f"null iff < {months} months on the book or no card month in them"
                cases[column] = (rule, _card_window_case(mart, short, months))
            else:
                cases[column] = (f"null iff < {months} months on the book", short.astype(float))
        elif ratio:
            avg = {k: _numbers(mart, f"{ratio['base']}_0_{k}_months_avg") for k in (2, 5)}
            zero = np.abs(6 * avg[5] - 3 * avg[2]) / 3 <= ZERO_AVERAGE  # NaN (short) is not zero
            want = (on_book < RATIO_MONTHS) | zero
            rule = f"null iff < {RATIO_MONTHS} months on the book or a zero 3–5 average"
            cases[column] = (rule, want.astype(float))
    return cases


def _card_window_case(mart: pd.DataFrame, short: np.ndarray, months: int) -> np.ndarray:
    """Utilisation rollups: null if the window is short or no month in it had a card; unknown
    (NaN) if no visible month had one but part of the window lies before the mart's months."""
    window = values_at(mart, "cc_flag", range(1 - months, 1))
    card = (window == 1).any(axis=1)
    want = (short | ~card).astype(float)
    want[~short & ~card & np.isnan(window).any(axis=1)] = np.nan
    return want


def _since_last_cases(mart: pd.DataFrame) -> dict[str, tuple[str, np.ndarray]]:
    """'Since last' columns: recency on its `_vol` measure, days since last login on the login
    counts."""
    has_prev = ~np.isnan(values_at(mart, "relationship_days", [-1])[:, 0])
    logins = _numbers(mart, "login_digital_mobile_cnt") + _numbers(mart, "login_digital_online_cnt")
    cases = {}
    for column in mart.columns:
        if column.startswith("months_since_last_"):
            active = _numbers(mart, column.removeprefix("months_since_last_") + "_vol") > 0
        elif column == "days_since_last_login_digital":
            active = logins > 0
        else:
            continue
        rule = "null iff no non-zero month since joining"
        cases[column] = (rule, _since_last_case(mart, column, active, has_prev))
    return cases


def _since_last_case(
    mart: pd.DataFrame, column: str, active: np.ndarray, has_prev: np.ndarray
) -> np.ndarray:
    """Null iff nothing happened now and last month was null (or the client joined this month).

    In the mart's first month the history lies in the burn-in: only an active row is known.
    """
    null_before = np.isnan(values_at(mart, column, [-1])[:, 0])
    want = (~active & (null_before | ~has_prev)).astype(float)
    first_month = (mart["snapshot_month"] == mart["snapshot_month"].min()).to_numpy()
    want[first_month & ~active] = np.nan
    return want


def _state_cases(mart: pd.DataFrame, spec: dict) -> dict[str, tuple[str, np.ndarray]]:
    """Nulls set by a state: utilisation without a card, months to maturity without an account,
    residence, the upstream target for holders and in the panel's last months, each shifted column
    without a next month, the all-null trap."""
    no_card = (_numbers(mart, "cc_flag") == 0).astype(float)
    cases = {"cc_utilisation_ratio": ("null iff no card", no_card)}
    for column in mart.columns:
        upstream = UPSTREAM.match(column)
        if column.endswith("_maturity_months"):
            count = _numbers(mart, column.removesuffix("_maturity_months") + "_cnt")
            cases[column] = ("null iff no account", (count == 0).astype(float))
        elif upstream:
            last = np.sort(mart["snapshot_month"].unique())[-int(upstream["months"]) :]
            late = mart["snapshot_month"].isin(last).to_numpy()
            held = _numbers(mart, f"{upstream['product']}_flag") == 1
            rule = "null iff a holder or in the panel's last months"
            cases[column] = (rule, (held | late).astype(float))
        elif column.endswith("_trap_all_null"):
            cases[column] = ("always null", np.ones(len(mart)))
        elif column.endswith("_trap_shifted"):  # next month's value: none if the client has none
            no_next = np.isnan(values_at(mart, "relationship_days", [1])[:, 0])
            cases[column] = ("null iff no next month", no_next.astype(float))
    rule = "null for nationals; for others only in profiles with non-residents"
    cases["residence_days"] = (rule, _residence_case(mart, spec))
    return cases


def _residence_case(mart: pd.DataFrame, spec: dict) -> np.ndarray:
    """Null for nationals; never for other clients of profiles without non-residents; unknown for
    the rest (the mart doesn't say who is a non-resident)."""
    national = (mart["nationality_group"] == spec["national_group"]).to_numpy()
    with_non_residents = {
        name: spec["profiles"][sub["profile"]]["non_resident"] > 0
        for name, sub in spec["subsegments"].items()
    }
    maybe = mart["subsegment"].map(lambda s: with_non_residents[s]).to_numpy(dtype=bool)
    return np.where(national, 1.0, np.where(maybe, np.nan, 0.0))


def _check_types(mart: pd.DataFrame) -> list[dict]:
    """Types in memory: flags and counts integers, amounts floats, categoricals strings, the month
    dates; the spec fixes no type for the other columns."""
    tests = {
        "integer": pd.api.types.is_integer_dtype,
        "float": pd.api.types.is_float_dtype,
        "string": _holds_strings,
        "date": _holds_dates,
    }
    kinds = {c: _type_of(c) for c in mart.columns}
    rows = []
    for kind, test in tests.items():
        columns = [c for c, k in kinds.items() if k == kind]
        bad = [c for c in columns if not test(mart[c])]
        rows.append(offenders_row(f"{kind} columns have a {kind} type", bad, len(columns)))
    return rows


def _type_of(name: str) -> str | None:
    """The in-memory type a column's name implies; None where the spec sets none (keys, `nz`
    counts, extremes of counts, scores, extra columns)."""
    base = TRAP.sub("", name)
    rollup = ROLLUP.match(base)
    if rollup:
        of_amount = rollup["base"].endswith(("_vol", "_bal", "_ratio"))
        extreme = rollup["agg"] in ("min", "max", "sum")
        return "float" if rollup["agg"] in ("avg", "std") or (of_amount and extreme) else None
    if base == "snapshot_month":
        return "date"
    if base in STRING_COLUMNS or base.endswith("_status"):
        return "string"
    if (
        base in INTEGER_COLUMNS
        or base.endswith(("_flag", "_cnt", "_maturity_months"))
        or base.startswith("months_since_last_")
    ):
        return "integer"
    if base == "income" or base.endswith(("_vol", "_bal", "_limit", "_ratio")):
        return "float"
    return None


def _holds_strings(series: pd.Series) -> bool:
    """Strings, as plain values or as the categories of a categorical."""
    is_categorical = isinstance(series.dtype, pd.CategoricalDtype)
    values = series.cat.categories if is_categorical else series
    return pd.api.types.infer_dtype(values, skipna=True) == "string"


def _holds_dates(series: pd.Series) -> bool:
    """Dates: `datetime.date` values or a datetime type."""
    is_datetime = pd.api.types.is_datetime64_any_dtype(series)
    return is_datetime or pd.api.types.infer_dtype(series, skipna=True) == "date"
