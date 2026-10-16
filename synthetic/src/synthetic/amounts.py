"""Amounts of the synthetic book: what clients keep, earn, spend and repay, month by month.

Every amount is a median multiple of a hidden base per profile (`levels.LEVELS`): flows scale with
the true income, balances with the wealth base. This module draws the hidden client attributes the
amounts need, once, when a client is drawn and before its holdings start, from the amounts
stream: the remitter flag, the bonus month and size, the school-fee payer flag and annual fee, the
card repayment share, and the "other" share of non-salary inflow (no draw). They never reach the
mart; the oracle records them. Build stage B adds `start_amounts` and `step_amounts`, which run the
amount mechanisms month by month (worknotes/handovers/synthetic_build.md).
"""

import numpy as np
import pandas as pd

from synthetic.population import profile_values


def draw_hidden_attributes(
    spec: dict, clients: pd.DataFrame, age: np.ndarray, rng: np.random.Generator
) -> pd.DataFrame:
    """Hidden attributes of newly drawn clients; `age` is their age when drawn.

    Every draw is one value per client, made for everyone and used where it applies, so the stream
    stays aligned whatever the clients' outcomes.
    """
    n, levels, seasons = len(clients), spec["levels"], spec["seasons"]
    remittance = levels["subcategories"]["remittance"]
    can_remit = ~clients["nationality_group"].isin(remittance["never"]).to_numpy()
    remitter = can_remit & (rng.random(n) < profile_values(clients, remittance["remitter_share"]))
    bonus = seasons["bonus"]  # only salary-transfer clients: the bonus comes with the salary
    has_bonus = clients["salary_transfer_flag"].to_numpy() & (rng.random(n) < bonus["share"])
    bonus_month = np.where(has_bonus, rng.choice(bonus["months"], n), 0)
    bonus_factor = np.where(has_bonus, rng.uniform(*bonus["factor_range"], n), 0.0)
    school = seasons["school_fees"]
    youngest, oldest = school["payer_ages"]
    payer = (
        (age >= youngest)
        & (age <= oldest)
        & (rng.random(n) < profile_values(clients, school["payer_share"]))
    )
    # Lognormal with median 1 around the profile's annual fee.
    fee = profile_values(clients, school["annual_fee"]) * np.exp(
        school["fee_sd"] * rng.standard_normal(n)
    )
    other = levels["inflow_other_share"]
    other_share = (
        clients["employment_status"].map(other).to_numpy(dtype=float)
        + other["private_extra"] * (clients["profile"] == "private").to_numpy()
    )
    return pd.DataFrame(
        {
            "remitter_flag": remitter,
            "bonus_month": bonus_month,
            "bonus_factor": bonus_factor,
            "school_payer_flag": payer,
            "school_fee": np.where(payer, fee, 0.0),
            "repay_share": rng.uniform(*levels["card"]["repay_share_range"], n),
            "other_share": other_share,
        },
        index=clients.index,
    )
