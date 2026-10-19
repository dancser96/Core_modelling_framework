"""Who the clients are: their fixed description, income and hidden traits and attributes.

Each client gets a subsegment (and with it a segment and a profile), a nationality group and
country, an employment status, an emirate, a birth month, a relationship start and a residence
start (`draw_clients`). Income and the salary-transfer flag are drawn after the hidden traits,
because income rises with the wealth trait (`draw_income`); the true income (hidden) is the income
before some of it is hidden as undeclared. Dates are stored as integer months or days since 1970,
so pandas never reinterprets their units; the month loop turns them into age and day counters.

Hidden traits (wealth, activity, digital, credit appetite, cross-border) drive behaviour but never
appear in the mart. Each has a long-run mean, the subsegment's mean plus shifts for nationality
group and employment (`latent_means`), and a profile-specific spread and correlation. Month to
month they follow a stationary AR(1) (`step_latents`), so they persist but drift and their
distribution never changes; the oracle file records them. `draw_hidden_attributes` draws, once per
client, the attributes the amounts need: onboarding channel, remitter flag, bonus month and size,
school-fee payer and annual fee, card repayment share, the "other" share of non-salary inflow.
Draws run in a fixed order within each stream: reordering them changes the data for a given seed.
"""

import numpy as np
import pandas as pd
from scipy import stats

from synthetic.spec.presets import EMIRATES, EMPLOYMENT, LATENTS, NATIONALITY_GROUPS
from synthetic.spec.products import PROFILE_ORDER

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
    median = subsegment_medians(spec, clients)
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


def draw_hidden_attributes(
    spec: dict, clients: pd.DataFrame, age: np.ndarray, rng: np.random.Generator
) -> pd.DataFrame:
    """Hidden attributes of newly drawn clients (`rng`: the attributes stream); `age` is their age
    when drawn.

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
    other_share = (
        clients["employment_status"].map(levels["inflow_other_share"]).to_numpy(dtype=float)
        + levels["inflow_other_private_extra"] * (clients["profile"] == "private").to_numpy()
    )
    repay_share = rng.uniform(*levels["card"]["repay_share_range"], n)
    channel = spec["onboarding_channel"]
    digital = rng.random(n) < profile_values(clients, channel["digital_share"])
    return pd.DataFrame(
        {
            "onboarding_channel": np.where(digital, channel["levels"][1], channel["levels"][0]),
            "remitter_flag": remitter,
            "bonus_month": bonus_month,
            "bonus_factor": bonus_factor,
            "school_payer_flag": payer,
            "school_fee": np.where(payer, fee, 0.0),
            "repay_share": repay_share,
            "other_share": other_share,
        },
        index=clients.index,
    )


def subsegment_medians(spec: dict, clients: pd.DataFrame) -> np.ndarray:
    """Each client's subsegment median income (the spec's `median_income`)."""
    medians = {name: s["median_income"] for name, s in spec["subsegments"].items()}
    return clients["subsegment"].map(medians).to_numpy(dtype=float)


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
    rate = 12 * profiles.map(lambda p: p["entry_rate"]).to_numpy(dtype=float)  # a year
    if (rate <= 0).any():
        raise ValueError("entry_rate must be positive: the book's tenure follows it")
    # The turnover's steady state: clients join at the entry rate and leave at the exit rate, so
    # in a book growing at entry − exit, tenure is exponential at the entry rate. Clients join
    # younger than the book's mean age by that mean tenure; the starting book adds its tenure to
    # the age it joined at. So the book's tenure and age (the spec's `age`: the book's mean) stay
    # put month after month, and so do the shares of products that build up over tenure or age.
    mean_tenure = 1 / rate
    mean = clients["subsegment"].map(lambda s: spec["subsegments"][s]["age"]).to_numpy()
    mean = mean - mean_tenure
    sd = profiles.map(lambda p: p["age_sd"]).to_numpy()
    joined_at = stats.truncnorm.rvs((lo - mean) / sd, (hi - mean) / sd, mean, sd, random_state=rng)
    month_start = month.astype("datetime64[D]").astype(int)
    if new_to_bank:
        days_in_month = (month + 1).astype("datetime64[D]").astype(int) - month_start
        relationship_years = np.zeros(n)
        relationship_start = month_start + rng.integers(0, days_in_month, n)
    else:
        relationship_years = rng.exponential(mean_tenure)
        relationship_start = month_start - _years_to_days(relationship_years)
    age = joined_at + relationship_years
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


def profile_codes(clients: pd.DataFrame) -> np.ndarray:
    """Each client's profile as its position in PROFILE_ORDER (the spec's per-profile lists)."""
    return clients["profile"].map({p: i for i, p in enumerate(PROFILE_ORDER)}).to_numpy()


def profile_values(clients: pd.DataFrame, values: list[float]) -> np.ndarray:
    """Each client's entry of a per-profile list of the spec (order: PROFILE_ORDER)."""
    lookup = dict(zip(PROFILE_ORDER, values, strict=True))
    return clients["profile"].map(lookup).to_numpy(dtype=float)


def latent_means(spec: dict, clients: pd.DataFrame) -> np.ndarray:
    """Each client's long-run mean: subsegment mean plus nationality-group and employment shifts."""
    shape = (len(clients), len(LATENTS))  # explicit, so zero clients still gives a 2-D array
    subs = spec["subsegments"]
    base = np.array([subs[s]["latent_mean"] for s in clients["subsegment"]]).reshape(shape)
    nat_shift = spec["latent_shift_nationality"]
    nat = np.array([nat_shift[g] for g in clients["nationality_group"]]).reshape(shape)
    emp_shift = spec["latent_shift_employment"]
    emp = np.array([emp_shift[e] for e in clients["employment_status"]]).reshape(shape)
    return base + nat + emp


def latent_covariances(spec: dict) -> dict[str, np.ndarray]:
    """Covariance per profile, D R D."""
    out = {}
    for name, p in spec["profiles"].items():
        scale = np.diag(p["latent_scale"])
        out[name] = scale @ np.array(p["latent_corr"]) @ scale
    return out


def draw_latents(
    spec: dict, clients: pd.DataFrame, means: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """Draw from each client's stationary distribution N(mean, Σ_profile)."""
    return means + _correlated_noise(spec, clients, rng)


def step_latents(
    spec: dict, clients: pd.DataFrame, z: np.ndarray, means: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    """One month of AR(1); the stationary distribution stays exactly N(mean, Σ_profile).

    `z` may carry a paths axis, (clients, paths, traits), with `means` as (clients, 1, traits):
    the regression oracle's simulated paths.
    """
    rho = spec["latent_rho"]
    noise = _correlated_noise(spec, clients, rng, z.shape)
    return means + rho * (z - means) + np.sqrt(1 - rho**2) * noise


def _correlated_noise(
    spec: dict, clients: pd.DataFrame, rng: np.random.Generator, shape: tuple | None = None
) -> np.ndarray:
    """Standard normal noise per client (and path), correlated with its profile's covariance.

    `shape` is (clients, traits) by default, or (clients, paths, traits).
    """
    names = list(spec["profiles"])
    # Cholesky fails loud if a profile's correlation matrix is not positive definite.
    chol = np.stack([np.linalg.cholesky(c) for c in latent_covariances(spec).values()])
    codes = clients["profile"].map({name: i for i, name in enumerate(names)}).to_numpy()
    eps = rng.standard_normal((len(clients), len(LATENTS)) if shape is None else shape)
    return np.einsum("nij,n...j->n...i", chol[codes], eps)
