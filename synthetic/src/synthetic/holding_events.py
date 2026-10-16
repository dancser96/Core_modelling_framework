"""Holding events read from the mart, side by side with the oracle's chances (step-2 checks).

Mart and oracle go side by side, sorted by client and month, so each row sees the client's state at
the end of last month: its previous row, or "empty" for a new client's first row. A first row is no
transition, so entry-month events are left out of the event tables. Events are read from the mart
(and, for hidden chains such as the revolver state, the oracle's flag) and set against the oracle's
chances, so the oracle is checked against the data, not the other way round. The panel's columns
are declared here, for the families that read it (`checks_holdings`, `checks_holding_drivers`).
"""

import numpy as np
import pandas as pd

from synthetic.check_table import Z_TOL, flags_as_bool, profile_of, row

LATENT_COLUMNS = ["z_wealth", "z_activity", "z_digital", "z_credit", "z_crossborder"]
PANEL_MART_COLUMNS = [
    "client_id",
    "snapshot_month",
    "subsegment",
    "nationality_group",
    "nationality",
    "employment_status",
    "income",
    "salary_transfer_flag",
    "onboarding_channel",
    "age",
    "relationship_days",
    "casa_flag",
    "cc_flag",
    "td_flag",
    "td_status",
    "wealth_digital_flag",
    "wealth_digital_status",
    "wealth_trad_flag",
    "wealth_trad_status",
    "ebanking_flag",
    "loan_personal_cnt",
    "loan_personal_maturity_months",
    "loan_auto_cnt",
    "loan_auto_maturity_months",
    "loan_home_cnt",
    "loan_home_maturity_months",
    "fx_active_flag",
    "digital_active_flag",
    "cc_active_flag",
    "casa_active_flag",
    "product_cnt",
]
PANEL_ORACLE_COLUMNS = [
    "client_id",
    "snapshot_month",
    *LATENT_COLUMNS,
    *[f"p_{key}_acquire" for key in ("cc", "td", "wealth_digital", "wealth_trad", "ebanking")],
    *[f"p_{key}_open" for key in ("loan_personal", "loan_auto", "loan_home")],
    *[
        f"p_{key}_{move}"
        for key in ("fx", "digital", "cc_activity", "casa_activity", "cc_revolver")
        for move in ("activate", "lapse")
    ],
    "revolver_flag",
]


def build_panel(spec: dict, mart: pd.DataFrame, oracle: pd.DataFrame) -> pd.DataFrame:
    """Mart and oracle side by side, sorted by client and month, with tenure in whole months.

    Flags become bools here, so the checks can use them as masks.
    """
    keys = ["client_id", "snapshot_month"]
    if not mart[keys].equals(oracle[keys]):
        raise ValueError("oracle rows must line up with mart rows")
    panel = flags_as_bool(pd.concat([mart, oracle.drop(columns=keys)], axis=1))
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


def usage_flag(spec: dict, key: str) -> str:
    """The column of a usage chain: the spec's `flag`, by default `<key>_active_flag`."""
    return spec["products"][key].get("flag", f"{key}_active_flag")


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
            flag = usage_flag(spec, key)
            active_before = before(panel, flag, False).astype(bool)
            active = panel[flag].to_numpy()
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
