"""Draw clients' fixed description: who they are, which never changes month to month.

Each client gets a subsegment (and with it a segment and a profile), a nationality group and
country, an employment status, an emirate, a birth month, a relationship start and a residence
start. Income and the salary-transfer flag are drawn separately (`draw_income`), after the hidden
traits, because income rises with the wealth trait; the true income (hidden) is the income before
some of it is hidden as undeclared. Dates are stored as integer months or days
since 1970, so pandas never reinterprets their units; the month loop turns them into age and day
counters. Draws run in a fixed order: reordering them changes the data for a given seed.
"""

import numpy as np
import pandas as pd
from scipy import stats

from synthetic.presets import EMIRATES, EMPLOYMENT, NATIONALITY_GROUPS
from synthetic.products import PROFILE_ORDER

DAYS_PER_YEAR = 365.25


def draw_subsegments(spec: dict, n: int, rng: np.random.Generator) -> np.ndarray:
    """Draw n subsegments from the spec's shares (the starting book)."""
    names = list(spec["subsegments"])
    # No renormalising: shares that don't sum to 1 are a spec error, and rng.choice raises.
    return rng.choice(names, size=n, p=[spec["subsegments"][s]["share"] for s in names])


def draw_clients(
    spec: dict,
    subsegment: np.ndarray,
    month: np.datetime64,
    rng: np.random.Generator,
    new_to_bank: bool,
) -> pd.DataFrame:
    """Draw clients of the given subsegments as of `month`.

    New-to-bank clients start their relationship within `month`; existing ones started earlier.
    """
    clients = _draw_descriptors(spec, subsegment, rng)
    return pd.concat([clients, _draw_dates(spec, clients, month, rng, new_to_bank)], axis=1)


def draw_income(
    spec: dict, clients: pd.DataFrame, wealth_dev: np.ndarray, rng: np.random.Generator
) -> pd.DataFrame:
    """Declared income (null when not declared), the salary-transfer flag and the true income.

    `wealth_dev` is the wealth trait minus its mean, in within-profile standard deviations, so
    income rises with wealth inside each subsegment. The true income (hidden) is the declared
    income before hiding; it exists for every client.
    """
    cfg = spec["income"]
    median = clients["subsegment"].map(lambda s: spec["subsegments"][s]["median_income"]).to_numpy()
    emp = clients["employment_status"]
    log_income = (
        np.log(median * emp.map(cfg["employment_multiplier"]).to_numpy())
        + cfg["wealth_loading"] * wealth_dev
        + cfg["sigma"] * rng.standard_normal(len(clients))
    )
    p_missing = 1 - (1 - emp.map(cfg["missing"]).to_numpy()) * (
        1 - cfg["missing_private_extra"] * (clients["segment"] == "Private").to_numpy()
    )
    missing = rng.random(len(clients)) < p_missing
    p_salary = clients["profile"].map(lambda p: spec["profiles"][p]["salary_transfer"]).to_numpy()
    salary = (emp == "Employed").to_numpy() & (rng.random(len(clients)) < p_salary)
    true_income = np.round(np.exp(log_income), -1)
    return pd.DataFrame(
        {
            "income": np.where(missing, np.nan, true_income),
            "salary_transfer_flag": salary,
            "true_income": true_income,
        },
        index=clients.index,
    )


def _draw_descriptors(spec: dict, subsegment: np.ndarray, rng: np.random.Generator) -> pd.DataFrame:
    """Segment, profile, nationality, employment and emirate for the given subsegments."""
    subs, profiles = spec["subsegments"], spec["profiles"]
    n = len(subsegment)
    profile = np.array([subs[s]["profile"] for s in subsegment], dtype=object)
    nat_mix = np.array([profiles[p]["nationality"] for p in profile]).reshape(
        n, len(NATIONALITY_GROUPS)
    )
    group = np.asarray(NATIONALITY_GROUPS)[_choose_rows(nat_mix, rng)]
    country = _draw_countries(spec["countries"], group, rng)
    emp_mix = np.array([profiles[p]["employment"] for p in profile]).reshape(n, len(EMPLOYMENT))
    employment = np.asarray(EMPLOYMENT)[_choose_rows(emp_mix, rng)]
    emirate_mix = np.array([profiles[p]["emirate"] for p in profile]).reshape(n, len(EMIRATES))
    emirate = np.asarray(EMIRATES)[_choose_rows(emirate_mix, rng)]
    return pd.DataFrame(
        {
            "segment": [subs[s]["segment"] for s in subsegment],
            "subsegment": subsegment,
            "profile": profile,
            "nationality_group": group,
            "nationality": country,
            "employment_status": employment,
            "emirate": emirate,
        }
    )


def _draw_dates(
    spec: dict,
    clients: pd.DataFrame,
    month: np.datetime64,
    rng: np.random.Generator,
    new_to_bank: bool,
) -> pd.DataFrame:
    """Birth month, relationship start and residence start (null: no residence length)."""
    n = len(clients)
    profiles = clients["profile"].map(spec["profiles"])
    lo, hi = spec["age_range"]
    mean = clients["subsegment"].map(lambda s: spec["subsegments"][s]["age"]).to_numpy()
    mean = mean + spec["new_to_bank_age_shift"] * new_to_bank
    sd = profiles.map(lambda p: p["age_sd"]).to_numpy()
    age = stats.truncnorm.rvs((lo - mean) / sd, (hi - mean) / sd, mean, sd, random_state=rng)
    month_start = month.astype("datetime64[D]").astype(int)
    if new_to_bank:
        days_in_month = (month + 1).astype("datetime64[D]").astype(int) - month_start
        relationship_years = np.zeros(n)
        relationship_start = month_start + rng.integers(0, days_in_month, n)
    else:
        beta = np.array(profiles.map(lambda p: p["relationship_beta"]).tolist()).reshape(n, 2)
        relationship_years = (age - lo) * rng.beta(beta[:, 0], beta[:, 1])
        relationship_start = month_start - _years_to_days(relationship_years)
    # Arrival in the country comes before the relationship and never before birth.
    gap_years = np.minimum(
        _draw_residence_gap(spec["residence_gap"], n, rng), age - relationship_years
    )
    residence_start = relationship_start - _years_to_days(gap_years)
    non_resident = rng.random(n) < profiles.map(lambda p: p["non_resident"]).to_numpy()
    no_residence = (
        non_resident | (clients["nationality_group"] == spec["national_group"]).to_numpy()
    )
    return pd.DataFrame(
        {
            "birth_month": month.astype(int) - np.round(age * 12).astype(int),
            "relationship_start": relationship_start,
            "residence_start": np.where(no_residence, np.nan, residence_start),
        },
        index=clients.index,
    )


def _draw_residence_gap(cfg: dict, n: int, rng: np.random.Generator) -> np.ndarray:
    """Years from arrival to relationship start: a mix of recent arrivals and settled residents."""
    recent = rng.random(n) < cfg["recent_share"]
    recent_gap = rng.exponential(cfg["recent_mean_years"], n)
    settled_gap = rng.exponential(cfg["settled_mean_years"], n)
    return np.where(recent, recent_gap, settled_gap)


def _draw_countries(countries: dict, group: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Zipf-distributed country within each nationality group."""
    u = rng.random(len(group))
    out = np.empty(len(group), dtype=object)
    for name in np.unique(group):  # a group missing from `countries` raises KeyError
        names, exponent = countries[name]
        weights = np.arange(1, len(names) + 1) ** -float(exponent)
        rows = group == name
        idx = np.searchsorted(np.cumsum(weights / weights.sum()), u[rows], side="right")
        out[rows] = np.asarray(names)[np.minimum(idx, len(names) - 1)]
    return out


def _choose_rows(probs: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """One categorical draw per row of a (rows × levels) probability matrix; returns indices."""
    u = rng.random(len(probs))
    return np.minimum((u[:, None] > probs.cumsum(axis=1)).sum(axis=1), probs.shape[1] - 1)


def _years_to_days(years: np.ndarray) -> np.ndarray:
    """Whole days in a number of years."""
    return np.round(years * DAYS_PER_YEAR).astype(int)


def client_age(clients: pd.DataFrame, month: np.datetime64) -> np.ndarray:
    """Age in whole years in `month`."""
    return (month.astype(int) - clients["birth_month"].to_numpy()) // 12


def months_on_book(clients: pd.DataFrame, month: np.datetime64) -> np.ndarray:
    """Monthly steps a client has lived by the end of `month`, the join month included."""
    days = clients["relationship_start"].to_numpy().astype("datetime64[D]")
    return month.astype(int) - days.astype("datetime64[M]").astype(int) + 1


def profile_values(clients: pd.DataFrame, values: list[float]) -> np.ndarray:
    """Each client's entry of a per-profile list of the spec (order: PROFILE_ORDER)."""
    lookup = dict(zip(PROFILE_ORDER, values, strict=True))
    return clients["profile"].map(lookup).to_numpy(dtype=float)
