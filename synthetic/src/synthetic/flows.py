"""Flows through the current/savings account, and FX volumes (test_harness.md "Amounts").

The balance comes first (`balances.casa_balance`); the flows follow. Inflow is the salary
(salary-transfer clients: the true income, plus the bonus in the bonus month), transfers and other
non-salary inflow; outflow is the spending (85% of the regular inflow × its own variation), split
into remittance, cash, bills and transfers by monthly Dirichlet shares around the client's tilted
mean shares, plus school fees in bills and the card repayment and loan instalments as transfers.
Whatever the balance moved beyond these is booked as a transfer, in or out, so inflow − outflow
equals the change in the observed balance exactly. Parts are rounded to the cent and totals are
their sums. In a dormant month, or without the account, everything is exactly 0. Counts are
overdispersed and positive exactly when their amount is.
"""

import numpy as np
import pandas as pd

from synthetic.population import profile_values, subsegment_medians
from synthetic.seasons import bonus_due, school_fee_due, season_factor
from synthetic.variation import draw_counts, draw_shares, split_amount, tilted_shares

INFLOW_PARTS = ("salary", "transfers", "other")  # the inflow subcategories, in the mart's order


def account_flows(
    spec: dict,
    clients: pd.DataFrame,
    profiles: np.ndarray,
    log_parts: dict[str, np.ndarray],
    dz: np.ndarray,
    month: np.datetime64,
    active: np.ndarray,
    change: np.ndarray,
    payments: np.ndarray,
    count_tilt: np.ndarray,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """Inflow and outflow of the month, by subcategory, with counts (mart columns).

    `change` is the observed balance's change since last month, `payments` the card repayment and
    loan instalments, `count_tilt` the activity tilt on count means. Draws: outflow shares, then
    inflow, outflow and remittance counts.
    """
    levels = spec["levels"]
    inflow = _inflow(spec, clients, log_parts["inflow_casa"], month)
    regular = inflow.pop("salary_without_bonus") + inflow.pop("non_salary")
    spending = levels["measures"]["outflow_casa"]["spend_share"] * regular
    spending = spending * np.exp(log_parts["outflow_casa"])
    mean_shares = _outflow_shares(spec, clients, profiles, dz)
    shares = draw_shares(rng, mean_shares, levels["subcategories"]["concentration"])
    parts = split_amount(spending, shares)
    outflow = {name: parts[:, j] for j, name in enumerate(_outflow_names(spec))}
    outflow["bills"] = np.round(outflow["bills"] + school_fee_due(spec, clients, month), 2)
    outflow["transfers"] = np.round(outflow["transfers"] + payments, 2)
    # Whatever the balance moved beyond the flows is booked as a transfer, in or out.
    gap = np.round(change - (sum(inflow.values()) - sum(outflow.values())), 2)
    inflow["transfers"] = np.round(inflow["transfers"] + np.maximum(gap, 0), 2)
    outflow["transfers"] = np.round(outflow["transfers"] + np.maximum(-gap, 0), 2)
    inflow = {name: np.where(active, x, 0.0) for name, x in inflow.items()}
    outflow = {name: np.where(active, x, 0.0) for name, x in outflow.items()}
    return _columns(spec, inflow, outflow, gap > 0, count_tilt, rng)


def fx_amounts(
    spec: dict,
    clients: pd.DataFrame,
    profiles: np.ndarray,
    log_part: np.ndarray,
    month: np.datetime64,
    active: np.ndarray,
    count_tilt: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """FX volume and count: multiple × true income × summer factor × variation, when active."""
    levels = spec["levels"]
    level = profile_values(clients, levels["measures"]["fx_vol"]["multiples"])
    level = level * clients["true_income"].to_numpy(dtype=float)
    season = season_factor(spec, "fx_vol", profiles, month)
    volume = np.where(active, np.round(level * season * np.exp(log_part), 2), 0.0)
    count = draw_counts(rng, levels["counts"]["fx"] * count_tilt, levels["counts"]["gamma_shape"])
    return volume, np.where(volume > 0, 1 + count, 0)


def _inflow(
    spec: dict, clients: pd.DataFrame, log_part: np.ndarray, month: np.datetime64
) -> dict[str, np.ndarray]:
    """Inflow parts (salary with any bonus, transfers, other), plus the salary without the bonus
    and the non-salary inflow before rounding, which set the spending.

    Non-salary inflow is (multiple − 1) × true income with salary transfer, the no-salary-transfer
    factor × multiple × true income without, × its variation; the "other" share is set by
    employment (plus extra in Private).
    """
    levels = spec["levels"]
    income = clients["true_income"].to_numpy(dtype=float)
    transfer = clients["salary_transfer_flag"].to_numpy()
    multiple = profile_values(clients, levels["measures"]["inflow_casa"]["multiples"])
    factor = np.where(transfer, multiple - 1, levels["no_salary_transfer"]["flows"] * multiple)
    non_salary = factor * income * np.exp(log_part)
    other_share = clients["other_share"].to_numpy(dtype=float)
    parts = split_amount(non_salary, np.stack([1 - other_share, other_share], axis=-1))
    salary = np.round(np.where(transfer, income, 0.0) + bonus_due(spec, clients, month), 2)
    return {
        "salary": salary,
        "transfers": parts[:, 0],
        "other": parts[:, 1],
        "salary_without_bonus": np.where(transfer, income, 0.0),
        "non_salary": non_salary,
    }


def _outflow_shares(
    spec: dict, clients: pd.DataFrame, profiles: np.ndarray, dz: np.ndarray
) -> np.ndarray:
    """Each client's mean spending shares: tilted by traits, remittance only for remitters and
    scaled by nationality group and (income / subsegment median)^elasticity; renormalised."""
    remit = spec["levels"]["subcategories"]["remittance"]
    shares = tilted_shares(spec, "outflow_casa", profiles, dz)
    relative = clients["true_income"].to_numpy(dtype=float) / subsegment_medians(spec, clients)
    factor = (
        clients["remitter_flag"].to_numpy()
        # UAE and GCC nationals never remit, so they have no factor.
        * clients["nationality_group"].map(remit["nationality_factor"]).fillna(0.0).to_numpy()
        * relative ** remit["income_elasticity"]
    )
    column = _outflow_names(spec).index("remittance")
    shares[:, column] = shares[:, column] * factor
    return shares / shares.sum(axis=1, keepdims=True)


def _columns(
    spec: dict,
    inflow: dict[str, np.ndarray],
    outflow: dict[str, np.ndarray],
    booked_in: np.ndarray,
    count_tilt: np.ndarray,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """The mart's flow columns: totals as sums of their parts, and the counts.

    Inflow count: the salary (1) + Poisson + 1 for a booked transfer in, at least 1 with any
    inflow. Outflow count: 1 + Poisson for the outflow other than remittance, plus the
    remittances.
    """
    counts, shape = spec["levels"]["counts"], spec["levels"]["counts"]["gamma_shape"]
    in_count = draw_counts(rng, counts["inflow_casa"] * count_tilt, shape)
    out_count = draw_counts(rng, counts["outflow_casa"] * count_tilt, shape)
    remitted = draw_counts(rng, counts["remittance"] * count_tilt, shape)
    in_total, out_total = np.round(sum(inflow.values()), 2), np.round(sum(outflow.values()), 2)
    in_count = np.maximum((inflow["salary"] > 0) + in_count + booked_in, 1)
    remitted = np.where(outflow["remittance"] > 0, 1 + remitted, 0)
    other_out = sum(x for name, x in outflow.items() if name != "remittance") > 0
    return {
        "inflow_casa_vol": in_total,
        **{f"inflow_casa_{name}_vol": inflow[name] for name in INFLOW_PARTS},
        "inflow_casa_cnt": np.where(in_total > 0, in_count, 0),
        "outflow_casa_vol": out_total,
        **{f"outflow_casa_{name}_vol": x for name, x in outflow.items()},
        "outflow_casa_cnt": np.where(other_out, 1 + out_count, 0) + remitted,
        "outflow_casa_remittance_cnt": remitted,
    }


def _outflow_names(spec: dict) -> list[str]:
    """The spending subcategories, in the spec's order."""
    return spec["levels"]["subcategories"]["outflow_casa"]["names"]
