"""Step-2 checks: holdings, statuses, loan accounts, usage states and the chances behind them.

Expected values are restated from the product spec and read from the mart, never taken from the
generator's functions. Events come from `holding_events`: month-on-month moves in the mart, set
against the oracle's chances. Rows of the first panel month have no known previous state and count
only in share checks. Shares stay flat over the panel except for the product with the uptake trend
(digital activity, a drift trap), which must rise. What drives adoption is in
`checks_holding_drivers`.
"""

import numpy as np
import pandas as pd

from synthetic.check_table import Z_TOL, range_row, row, share_row, violations_row
from synthetic.holding_events import (
    PANEL_MART_COLUMNS,
    PANEL_ORACLE_COLUMNS,
    before,
    build_panel,
    leave_events,
    oracle_events,
    product_keys,
    sum_row,
    usage_flag,
)
from synthetic.products import PROFILE_ORDER

MART_COLUMNS = PANEL_MART_COLUMNS
ORACLE_COLUMNS = PANEL_ORACLE_COLUMNS

STATUSES = ("never", "churned", "active")
# Allowed status moves in a month: rows are the old status, columns the new (order: STATUSES).
STATUS_MOVES = np.array([[True, False, True], [False, True, True], [False, True, True]])
# Shares hit the spec in expectation on the starting book, 13 months before the panel; since then
# clients aged and the book's tenure grew, so shares moved a little: a 10% relative floor.
SHARE_REL_TOL = 0.10
# The spec's volume is the steady-state flow. The book's tenure mix is still settling, so slow
# products keep building up; the check nets that growth out, and 25% covers what remains.
VOLUME_REL_TOL = 0.25
MIN_OPENINGS, SIZING_MONTHS = 200, 6  # sizing rule for loan targets
# A count-rise target misses openings in a month an account matures: fine while that is rare.
MAX_HIDDEN_OPENINGS = 0.02
# Current/savings dormant share at month 1 by salary transfer: the spec's "≈ 1% with, ≈ 10%
# without" as ranges (salary-transfer flag → range).
CASA_DORMANT_RANGES = {True: (0.005, 0.025), False: (0.07, 0.13)}


def check_holdings(mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict) -> pd.DataFrame:
    """Step 2: rules, oracle against events, shares, volumes, thresholds, churn and onboarding."""
    spec, calib = truth["spec"], truth["calibration"]
    panel = build_panel(spec, mart, oracle)
    months = panel["snapshot_month"]
    first, last = panel[months == months.min()], panel[months == months.max()]
    events = oracle_events(spec, panel)
    rows = (
        _check_statuses(spec, panel)
        + _check_loan_rules(spec, panel)
        + _check_other_rules(spec, panel)
        + _check_at_risk(events)
        + _check_realised(events, bins=10)
        + _check_realised(leave_events(spec, calib, panel), bins=1)
        + _check_shares(spec, first)
        + _check_casa_dormant(first)
        + _check_flat(spec, first, last)
        + _check_trend(spec, first, last)
        + _check_volumes(spec, panel, events)
        + _check_openings(panel, events)
        + _check_onboarding(spec, panel)
    )
    return pd.DataFrame(rows)


def _check_statuses(spec: dict, panel: pd.DataFrame) -> list[dict]:
    """Statuses are valid, active exactly when held, and move only along the allowed paths."""
    known, rows = panel["known"].to_numpy(), []
    for key in [k for k in product_keys(spec, "holding") if spec["products"][k].get("status")]:
        status = panel[f"{key}_status"]
        now = pd.Categorical(status, categories=STATUSES).codes
        then = pd.Categorical(before(panel, f"{key}_status", "never"), categories=STATUSES).codes
        bad = (now < 0) | ((status == "active").to_numpy() != panel[f"{key}_flag"].to_numpy())
        rows.append(violations_row(f"{key}: status valid, active exactly when held", bad))
        moved = known & (now >= 0) & (then >= 0)
        bad = ~STATUS_MOVES[then[moved], now[moved]]
        rows.append(violations_row(f"{key}: status moves never→active→churned→active", bad))
    return rows


def _check_loan_rules(spec: dict, panel: pd.DataFrame) -> list[dict]:
    """Counts within the cap; maturity counts down by 1 and accounts close only at maturity."""
    cap, known, rows = spec["holding_rules"]["max_loan_accounts"], panel["known"].to_numpy(), []
    for key in product_keys(spec, "loans"):
        term = spec["products"][key]["term_months"]
        cnt, mat = panel[f"{key}_cnt"].to_numpy(), panel[f"{key}_maturity_months"].to_numpy()
        cnt0 = before(panel, f"{key}_cnt", 0)
        mat0 = before(panel, f"{key}_maturity_months", np.nan)
        rules = {
            f"0 ≤ count ≤ {cap}": (cnt < 0) | (cnt > cap),
            f"maturity set exactly when count > 0, within 1..{term}": (np.isnan(mat) != (cnt == 0))
            | (mat < 1)
            | (mat > term),
        }
        moves = {
            "count falls only at maturity": (cnt < cnt0) & (mat0 != 1),
            "at most one opening a month": cnt > cnt0 + 1,
            "maturity falls by 1 a month": (mat0 > 1) & (mat != mat0 - 1),
            "a first account shows the full term": (cnt0 == 0) & (cnt == 1) & (mat != term),
        }
        rows += [violations_row(f"{key}: {rule}", bad) for rule, bad in rules.items()]
        rows += [violations_row(f"{key}: {rule}", bad[known]) for rule, bad in moves.items()]
    return rows


def _check_other_rules(spec: dict, panel: pd.DataFrame) -> list[dict]:
    """Usage needs its required product; product count matches its definition; static is static."""
    rows, counted = [], 0
    for key, product in spec["products"].items():
        if product["kind"] == "usage" and "requires" in product:
            flag, needs = usage_flag(spec, key), f"{product['requires']}_flag"
            active = panel[flag].to_numpy()
            woke = active & ~before(panel, flag, True).astype(bool)
            no_need = ~before(panel, needs, False).astype(bool)
            rows += [
                violations_row(f"{flag} = 1 only with {needs} = 1", active & ~panel[needs]),
                violations_row(f"{flag} wakes only with {needs} = 1 last month", woke & no_need),
            ]
        elif product["kind"] in ("static", "holding") and product.get("in_product_count", True):
            counted = counted + panel[f"{key}_flag"].astype(int)
        elif product["kind"] == "loans":
            counted = counted + (panel[f"{key}_cnt"] > 0).astype(int)
    rows.append(
        violations_row("product_cnt matches its definition", panel["product_cnt"] != counted)
    )
    for key in product_keys(spec, "static"):
        changed = panel[f"{key}_flag"].to_numpy() != before(panel, f"{key}_flag", False)
        rows.append(violations_row(f"{key}_flag never changes", changed[panel["has_prev"]]))
    return rows


def _check_at_risk(events: dict[str, dict]) -> list[dict]:
    """The oracle has a chance exactly for the rows the mart shows at risk."""
    return [
        violations_row(
            f"{name}: oracle chance set exactly when at risk",
            (~np.isnan(e["chance"]) != e["at_risk"])[e["scope"]],
        )
        for name, e in events.items()
    ]


def _check_realised(events: dict[str, dict], bins: int) -> list[dict]:
    """Events read from the mart against the sum of the chances, overall and per chance decile."""
    rows = []
    for name, e in events.items():
        judged = e["at_risk"] & ~np.isnan(e["realised"])
        chance, hit, check = (
            e["chance"][judged],
            e["realised"][judged],
            f"{name}: events vs Σ chance",
        )
        rows.append(sum_row(check, "all", chance, hit))
        decile = pd.qcut(chance, bins, labels=False, duplicates="drop") if bins > 1 else None
        for b in range(bins if bins > 1 else 0):
            part = decile == b
            rows.append(sum_row(check, f"chance decile {b + 1}", chance[part], hit[part]))
    return rows


def _held(spec: dict, df: pd.DataFrame) -> dict[str, tuple[pd.Series, pd.Series]]:
    """What each product's spec share counts: (held, rows it is a share of)."""
    out, everyone = {}, pd.Series(True, index=df.index)
    for key, product in spec["products"].items():
        if product["kind"] == "holding":
            out[key] = (df[f"{key}_flag"], everyone)
        elif product["kind"] == "loans":
            out[key] = (df[f"{key}_cnt"] > 0, everyone)
        elif product["kind"] == "usage":
            needs = product.get("requires")
            out[key] = (df[usage_flag(spec, key)], df[f"{needs}_flag"] if needs else everyone)
    return out


def _check_shares(spec: dict, first: pd.DataFrame) -> list[dict]:
    """Shares held in the first panel month against the spec, per product and profile."""
    rows = [
        share_row("held share at month 1", key, p["share"], first[f"{key}_flag"].sum(), len(first))
        for key, p in spec["products"].items()
        if p["kind"] == "static"
    ]
    for key, (held, base) in _held(spec, first).items():
        for name, expected in zip(PROFILE_ORDER, spec["products"][key]["shares"], strict=True):
            part = held[base & (first["profile"] == name)]
            rows.append(_spec_share_row("held share at month 1", f"{key} / {name}", expected, part))
    return rows


def _spec_share_row(check: str, stratum: str, expected: float, held: pd.Series) -> dict:
    """A share against the spec within max(binomial tolerance, SHARE_REL_TOL relative)."""
    se = np.sqrt(expected * (1 - expected) / len(held))
    tolerance = max(Z_TOL * se, SHARE_REL_TOL * expected)
    return row(check, stratum, len(held), expected, held.mean(), tolerance)


def _check_casa_dormant(first: pd.DataFrame) -> list[dict]:
    """Current/savings dormant share at month 1, with and without salary transfer, in its range."""
    rows, holders = [], first[first["casa_flag"]]
    for salary, (low, high) in CASA_DORMANT_RANGES.items():
        part = holders.loc[holders["salary_transfer_flag"] == salary, "casa_active_flag"]
        stratum, dormant = "salary transfer" if salary else "no salary transfer", 1 - part.mean()
        check = "casa dormant share at month 1"
        rows.append(range_row(check, stratum, len(part), low, high, dormant))
    return rows


def _check_flat(spec: dict, first: pd.DataFrame, last: pd.DataFrame) -> list[dict]:
    """Shares stay flat: the last panel month against the first, per product and profile.

    The product with the uptake trend is left out: `_check_trend` checks that it rises.
    """
    rows, before, after = [], _held(spec, first), _held(spec, last)
    trending = spec["seasons"]["drift"]["trend_product"]
    for key, name in [(key, name) for key in before for name in PROFILE_ORDER if key != trending]:
        a = before[key][0][before[key][1] & (first["profile"] == name)]
        b = after[key][0][after[key][1] & (last["profile"] == name)]
        tolerance = Z_TOL * np.sqrt(a.var(ddof=0) / len(a) + b.var(ddof=0) / len(b))
        stratum = f"{key} / {name}"
        rows.append(
            row("share last vs first month", stratum, len(b), a.mean(), b.mean(), tolerance)
        )
    return rows


def _check_trend(spec: dict, first: pd.DataFrame, last: pd.DataFrame) -> list[dict]:
    """The trending product's share rises from the first panel month to the last, by more than
    Z_TOL standard errors of the difference (pooled over profiles)."""
    key = spec["seasons"]["drift"]["trend_product"]
    (held_a, base_a), (held_b, base_b) = _held(spec, first)[key], _held(spec, last)[key]
    a, b = held_a[base_a], held_b[base_b]
    rise = b.mean() - a.mean()
    floor = Z_TOL * np.sqrt(a.var(ddof=0) / len(a) + b.var(ddof=0) / len(b))
    return [range_row("share rises, last vs first month", key, len(b), floor, 1.0, rise)]


def _check_volumes(spec: dict, panel: pd.DataFrame, events: dict[str, dict]) -> list[dict]:
    """Adoptions a month per 100k clients, against the spec's steady-state flow.

    Products that build up over tenure still grow while the book's tenure mix settles (and with the
    book itself), so their holders' growth is netted out. Onboarding products count adoptions after
    onboarding only; the onboarding wave feeds their growth, so nothing is netted.
    """
    onboarded = (panel["tenure_months"] >= spec["holding_rules"]["onboarding_months"]).to_numpy()
    months = panel["snapshot_month"]
    n_months, book = months.nunique(), len(panel) / months.nunique()
    rows = []
    for key in product_keys(spec, "holding"):
        product, e = spec["products"][key], events[f"{key} acquire"]
        clients = e["scope"] & (onboarded | (not product.get("onboarding")))
        rate = (e["at_risk"] & clients & (e["realised"] == 1)).sum() / clients.sum() * 1e5
        held = panel[f"{key}_flag"]
        growth = held[months == months.max()].sum() - held[months == months.min()].sum()
        if not product.get("onboarding"):
            rate -= growth / (n_months - 1) / book * 1e5
        expected = product["events_per_100k"]
        check = "adoptions per 100k a month (steady state)"
        rows.append(row(check, key, clients.sum(), expected, rate, VOLUME_REL_TOL * expected))
    return rows


def _check_openings(panel: pd.DataFrame, events: dict[str, dict]) -> list[dict]:
    """Loans have no spec volume. Sizing rule at the canonical size: ≥ 200 openings (count rises)
    in every 6-month window (realised: the fewest; n: all openings). And the share of openings a
    maturity in the same month hides from a count-rise target, by Σ chance: small by design (short
    of 2%)."""
    rows = []
    for name in [name for name in events if name.endswith(" open")]:
        e = events[name]
        rises = pd.Series(e["at_risk"] & (e["realised"] == 1))[e["scope"]]
        per_month = rises.groupby(panel["snapshot_month"][e["scope"]]).sum()
        fewest = int(per_month.rolling(SIZING_MONTHS).sum().min())
        check = f"fewest openings in a {SIZING_MONTHS}-month window"
        rows.append(range_row(check, name, rises.sum(), MIN_OPENINGS, rises.sum(), fewest))
        hidden = e["at_risk"] & np.isnan(e["realised"])
        share = e["chance"][hidden].sum() / e["chance"][e["at_risk"]].sum()
        check = "share of openings hidden by a maturity"
        rows.append(row(check, name, hidden.sum(), 0.0, share, MAX_HIDDEN_OPENINGS))
    return rows


def _check_onboarding(spec: dict, panel: pd.DataFrame) -> list[dict]:
    """Clients who joined within the panel hold onboarding products at the profile's share in
    their last onboarding month."""
    months = sorted(panel["snapshot_month"].unique())
    last = spec["holding_rules"]["onboarding_months"] - 1
    ended = panel[(panel["tenure_months"] == last) & (panel["snapshot_month"] >= months[last])]
    rows = []
    for key in [k for k, p in spec["products"].items() if p.get("onboarding")]:
        for name, expected in zip(PROFILE_ORDER, spec["products"][key]["shares"], strict=True):
            held = ended.loc[ended["profile"] == name, f"{key}_flag"]
            rows.append(
                _spec_share_row("held share after onboarding", f"{key} / {name}", expected, held)
            )
    return rows
