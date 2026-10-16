"""Holding events read from the mart, side by side with the oracle's chances (step-2 checks).

Mart and oracle go side by side, sorted by client and month, so each row sees the client's state at
the end of last month: its previous row, or "empty" for a new client's first row. A first row is no
transition, so entry-month events are left out of the event tables. Events are read from the mart
and set against the oracle's chances, so the oracle is checked against the data, not the other way
round.
"""

import numpy as np
import pandas as pd

from synthetic.check_table import Z_TOL, profile_of, row


def build_panel(spec: dict, mart: pd.DataFrame, oracle: pd.DataFrame) -> pd.DataFrame:
    """Mart and oracle side by side, sorted by client and month, with tenure in whole months."""
    keys = ["client_id", "snapshot_month"]
    if not mart[keys].equals(oracle[keys]):
        raise ValueError("oracle rows must line up with mart rows")
    panel = pd.concat([mart, oracle.drop(columns=keys)], axis=1)
    panel = panel.sort_values(keys, kind="stable", ignore_index=True)
    for key in product_keys(spec, "loans"):  # NaN instead of NA, for plain numpy comparisons
        panel[f"{key}_maturity_months"] = panel[f"{key}_maturity_months"].astype("float64")
    panel["profile"] = profile_of(spec, panel)
    panel["has_prev"] = panel["client_id"].eq(panel["client_id"].shift())
    panel["known"] = panel["has_prev"] | (panel["snapshot_month"] > panel["snapshot_month"].min())
    month = pd.to_datetime(panel["snapshot_month"])
    month_end = month + pd.to_timedelta(month.dt.days_in_month - 1, unit="D")
    start = month_end - pd.to_timedelta(panel["relationship_days"], unit="D")
    panel["tenure_months"] = (month.dt.year - start.dt.year) * 12 + month.dt.month - start.dt.month
    return panel


def product_keys(spec: dict, kind: str) -> list[str]:
    """The spec's products of one kind."""
    return [key for key, p in spec["products"].items() if p["kind"] == kind]


def before(panel: pd.DataFrame, column: str, empty: object) -> np.ndarray:
    """Each row's `column` at the end of last month: its previous row, or `empty` if none."""
    return np.where(panel["has_prev"], np.roll(panel[column].to_numpy(), 1), empty)


def _event(scope: np.ndarray, at_risk: np.ndarray, realised: np.ndarray, chance: object) -> dict:
    """One event: rows with a previous month, rows at risk, the event read from the mart (NaN where
    it can't be read) and the chance applied."""
    return dict(
        scope=scope, at_risk=scope & at_risk, realised=realised.astype(float), chance=chance
    )


def oracle_events(spec: dict, panel: pd.DataFrame) -> dict[str, dict]:
    """Every event the oracle carries a chance for, read from the mart as month-on-month moves.

    A client's first row is no transition, so it is left out (its entry-month events too).
    """
    has_prev, events = panel["has_prev"].to_numpy(), {}
    cap = spec["holding_rules"]["max_loan_accounts"]
    for key, product in spec["products"].items():
        if product["kind"] == "holding":
            held_before = before(panel, f"{key}_flag", False).astype(bool)
            chance = panel[f"p_{key}_acquire"].to_numpy()
            events[f"{key} acquire"] = _event(has_prev, ~held_before, panel[f"{key}_flag"], chance)
        elif product["kind"] == "loans":
            cnt, cnt0 = panel[f"{key}_cnt"].to_numpy(), before(panel, f"{key}_cnt", 0)
            matured = before(panel, f"{key}_maturity_months", np.nan) == 1
            # Openings are count rises. When an account matures the count can't rise, and an
            # opening hides behind the closure: those rows are quantified in `_check_volumes`.
            opened = np.where(matured, np.nan, cnt > cnt0)
            chance = panel[f"p_{key}_open"].to_numpy()
            events[f"{key} open"] = _event(has_prev, (cnt0 < cap) | matured, opened, chance)
        elif product["kind"] == "usage":
            active_before = before(panel, f"{key}_active_flag", False).astype(bool)
            active = panel[f"{key}_active_flag"].to_numpy()
            needs = product.get("requires")  # held at the end of last month
            eligible = before(panel, f"{needs}_flag", False).astype(bool) if needs else True
            chance = panel[f"p_{key}_activate"].to_numpy()
            events[f"{key} activate"] = _event(has_prev, ~active_before & eligible, active, chance)
            chance = panel[f"p_{key}_lapse"].to_numpy()
            events[f"{key} lapse"] = _event(has_prev, active_before, ~active, chance)
    return events


def leave_events(spec: dict, calib: dict, panel: pd.DataFrame) -> dict[str, dict]:
    """Losses of 0/1 products, at the constant leaving chance recorded in the truth."""
    has_prev, events = panel["has_prev"].to_numpy(), {}
    for key in product_keys(spec, "holding"):
        held_before = before(panel, f"{key}_flag", False).astype(bool)
        chance = np.full(len(panel), calib[key]["leave_chance"])
        events[f"{key} leave"] = _event(has_prev, held_before, ~panel[f"{key}_flag"], chance)
    return events


def sum_row(check: str, stratum: str, chance: np.ndarray, hit: np.ndarray) -> dict:
    """Event count against Σp, with the Poisson-binomial standard error."""
    tolerance = Z_TOL * np.sqrt(np.sum(chance * (1 - chance)))
    return row(check, stratum, len(chance), float(chance.sum()), float(hit.sum()), tolerance)
