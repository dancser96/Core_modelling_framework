"""Population checks: the mix, the client description, day counters, hidden traits and turnover.

Shares within a binomial tolerance, rules that must always hold (violation share 0), statistics
within a few standard errors, all restated from the spec. Turnover is read from the mart itself:
exits are clients whose last row comes before the final month, entries clients whose first row
comes after the first month.
"""

import numpy as np
import pandas as pd

from synthetic.checks.events import expected_latent_means, expected_medians
from synthetic.checks.table import Z_TOL, flags_as_bool, profile_of, row, share_row, violations_row
from synthetic.spec.presets import EMIRATES, EMPLOYMENT, LATENTS, NATIONALITY_GROUPS

WEALTH = LATENTS.index("wealth")
BIRTH_ROUNDING_DAYS = 16  # the birth month rounded: ≤ half a month (15.2 days) + a day
MART_COLUMNS = [
    "client_id",
    "snapshot_month",
    "segment",
    "subsegment",
    "nationality_group",
    "nationality",
    "employment_status",
    "income",
    "salary_transfer_flag",
    "emirate",
    "onboarding_channel",
    "age",
    "residence_days",
    "relationship_days",
]
ORACLE_COLUMNS = ["client_id", "snapshot_month", *[f"z_{name}" for name in LATENTS]]


def check_population(mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict) -> pd.DataFrame:
    """Mix, day counters, dates, residence and income nulls, latent traits, turnover."""
    spec, mart = truth["spec"], flags_as_bool(mart)
    months = mart["snapshot_month"]
    first, last = mart[months == months.min()], mart[months == months.max()]
    rows = (
        _check_mix(spec, first)
        + _check_profile_mix(spec, first)
        + _check_counters(mart)
        + _check_dates(spec, first)
        + _check_residence(spec, mart)
        + _check_income(spec, first)
        + _check_income_wealth(spec, mart, oracle)
        + _check_latents(spec, last, oracle[oracle["snapshot_month"] == months.max()])
        + _check_persistence(spec, mart, oracle)
        + _check_turnover(spec, mart)
    )
    return pd.DataFrame(rows)


def _check_mix(spec: dict, df: pd.DataFrame) -> list[dict]:
    """Subsegment shares, and the most common country's share within each nationality group."""
    n = len(df)
    subs = spec["subsegments"]
    rows = [
        share_row("subsegment share", s, subs[s]["share"], (df["subsegment"] == s).sum(), n)
        for s in subs
    ]
    for group, (names, exponent) in spec["countries"].items():
        weights = np.arange(1, len(names) + 1) ** -float(exponent)
        part = df[df["nationality_group"] == group]
        hits = (part["nationality"] == names[0]).sum()
        top_share = weights[0] / weights.sum()
        rows.append(share_row("top country share in group", group, top_share, hits, len(part)))
    return rows


def _check_profile_mix(spec: dict, df: pd.DataFrame) -> list[dict]:
    """Nationality, employment and emirate mixes, salary transfers and digital onboarding, per
    profile (the spec's profile order is the order of `onboarding_channel.digital_share`)."""
    profile = profile_of(spec, df)
    mixes = [
        ("nationality group share", "nationality_group", NATIONALITY_GROUPS, "nationality"),
        ("employment share", "employment_status", EMPLOYMENT, "employment"),
        ("emirate share", "emirate", EMIRATES, "emirate"),
    ]
    rows, digital_share = [], spec["onboarding_channel"]["digital_share"]
    for i, (name, p) in enumerate(spec["profiles"].items()):
        part = df[profile == name]
        hits = (part["onboarding_channel"] == "digital").sum()
        rows.append(share_row("digital onboarding share", name, digital_share[i], hits, len(part)))
        for check, column, levels, key in mixes:
            for level, share in zip(levels, p[key], strict=True):
                hits = (part[column] == level).sum()
                rows.append(share_row(check, f"{name} / {level}", share, hits, len(part)))
        employed = part[part["employment_status"] == "Employed"]
        hits, n = employed["salary_transfer_flag"].sum(), len(employed)
        rows.append(
            share_row("salary transfer among employed", name, p["salary_transfer"], hits, n)
        )
    return rows


def _check_counters(mart: pd.DataFrame) -> list[dict]:
    """Day counters grow by exactly the days in the month; age steps by 0 or 1."""
    m = mart.sort_values(["client_id", "snapshot_month"])
    # Clients never come back after exit, so a client's rows are consecutive months.
    same = m["client_id"].eq(m["client_id"].shift())
    days = pd.to_datetime(m["snapshot_month"]).dt.days_in_month
    residence_step = m["residence_days"].astype("float64").diff()
    age_step = m["age"].diff()[same]
    new = m[~same & (m["snapshot_month"] > m["snapshot_month"].min())]
    return [
        violations_row(
            "relationship_days grows by days in month",
            (m["relationship_days"].diff() != days)[same],
        ),
        violations_row(
            "residence_days grows by days in month",
            ((residence_step != days) & m["residence_days"].notna())[same],
        ),
        violations_row("age steps by 0 or 1", ~age_step.isin([0, 1])),
        share_row("age steps up once a year", "all", 1 / 12, (age_step == 1).sum(), len(age_step)),
        violations_row(
            "new clients start at 0–30 relationship days", ~new["relationship_days"].between(0, 30)
        ),
    ]


def _check_dates(spec: dict, df: pd.DataFrame) -> list[dict]:
    """Relationship ≤ residence ≤ age for residents; every relationship starts after 18."""
    resident = df[df["residence_days"].notna()]
    # Whole years understate the age by up to a year; the birth month is rounded to the month.
    adult_days = (df["age"] - spec["age_range"][0] + 1) * 366 + BIRTH_ROUNDING_DAYS
    return [
        violations_row(
            "relationship ≤ residence", resident["relationship_days"] > resident["residence_days"]
        ),
        violations_row("residence ≤ age", resident["residence_days"] > (resident["age"] + 1) * 366),
        violations_row("relationship starts after 18", df["relationship_days"] > adult_days),
    ]


def _check_residence(spec: dict, mart: pd.DataFrame) -> list[dict]:
    """Residence is null exactly for nationals and non-residents; the arrival gap is varied.

    The gap (residence − relationship days) is fixed per client, so each client's first row counts
    once. It is a mix of exponentials, so P(gap < 1 year) has a closed form; the age cap is at least
    18 years and never touches gaps under a year.
    """
    df = mart[mart["snapshot_month"] == mart["snapshot_month"].min()]
    national = df["nationality_group"] == spec["national_group"]
    nationals_null = df.loc[national, "residence_days"].isna().mean()
    rows = [row("residence null for nationals", "nationals", national.sum(), 1, nationals_null, 0)]
    profile = profile_of(spec, df)
    for name, p in spec["profiles"].items():
        part = df[(profile == name) & ~national]
        hits = part["residence_days"].isna().sum()
        rows.append(
            share_row("residence null for non-residents", name, p["non_resident"], hits, len(part))
        )
    first_rows = mart.drop_duplicates("client_id")  # the mart is in month order
    residents = first_rows[first_rows["residence_days"].notna()]
    gap = residents["residence_days"].astype("float64") - residents["relationship_days"]
    cfg = spec["residence_gap"]
    share = cfg["recent_share"]
    expected = share * (1 - np.exp(-1 / cfg["recent_mean_years"])) + (1 - share) * (
        1 - np.exp(-1 / cfg["settled_mean_years"])
    )
    hits = (gap < 365.25).sum()
    rows.append(share_row("residence gap under a year", "residents", expected, hits, len(gap)))
    return rows


def _check_income(spec: dict, df: pd.DataFrame) -> list[dict]:
    """Income missingness per employment status and segment; employed medians per subsegment."""
    cfg = spec["income"]
    rows = []
    for emp in EMPLOYMENT:
        for private in (False, True):
            part = df[(df["employment_status"] == emp) & ((df["segment"] == "Private") == private)]
            expected = 1 - (1 - cfg["missing"][emp]) * (1 - cfg["missing_private_extra"] * private)
            stratum = f"{emp} / {'Private' if private else 'not Private'}"
            hits = part["income"].isna().sum()
            rows.append(share_row("income missing", stratum, expected, hits, len(part)))
    # Employed log income is normal around log(subsegment median); a median's se is 1.2533 sd/√n.
    sd = np.hypot(cfg["wealth_loading"], cfg["sigma"])
    employed = df[(df["employment_status"] == "Employed") & df["income"].notna()]
    for sub, part in employed.groupby("subsegment"):
        expected = np.log(expected_medians(spec)[sub])
        tolerance = Z_TOL * 1.2533 * sd / np.sqrt(len(part))
        realised = np.log(part["income"].median())
        rows.append(
            row("log median income, employed", sub, len(part), expected, realised, tolerance)
        )
    return rows


def _check_income_wealth(spec: dict, mart: pd.DataFrame, oracle: pd.DataFrame) -> list[dict]:
    """Income rises with the wealth trait at the spec's slope.

    Uses new clients' first month, where the wealth trait is still its entry draw: the log-income
    residual on the standardised wealth deviation has slope `wealth_loading`.
    """
    first_rows = mart.drop_duplicates("client_id")  # the mart is in month order
    new = first_rows[
        (first_rows["snapshot_month"] > mart["snapshot_month"].min()) & first_rows["income"].notna()
    ].merge(oracle[["client_id", "snapshot_month", "z_wealth"]], on=["client_id", "snapshot_month"])
    cfg = spec["income"]
    median = new["subsegment"].map(expected_medians(spec))
    residual = np.log(
        new["income"] / (median * new["employment_status"].map(cfg["employment_multiplier"]))
    )
    scale = profile_of(spec, new).map(lambda p: spec["profiles"][p]["latent_scale"][WEALTH])
    x = (new["z_wealth"] - expected_latent_means(spec, new)[:, WEALTH]) / scale
    slope = np.cov(x, residual)[0, 1] / x.var()
    tolerance = Z_TOL * cfg["sigma"] / np.sqrt(len(x) * x.var())
    return [
        row(
            "income slope on wealth trait",
            "new clients",
            len(x),
            cfg["wealth_loading"],
            slope,
            tolerance,
        )
    ]


def _check_latents(spec: dict, df: pd.DataFrame, oracle: pd.DataFrame) -> list[dict]:
    """Latents are stationary: mean and covariance of (z − client mean) match the spec."""
    z = df[["client_id"]].merge(oracle, on="client_id")[[f"z_{n}" for n in LATENTS]].to_numpy()
    dev = z - expected_latent_means(spec, df)
    profile = profile_of(spec, df).to_numpy()
    rows = []
    for name, p in spec["profiles"].items():
        sigma = np.outer(p["latent_scale"], p["latent_scale"]) * np.array(p["latent_corr"])
        part = dev[profile == name]
        n = len(part)
        mean_z = np.abs(part.mean(axis=0)) / np.sqrt(np.diag(sigma) / n)
        cov_se = np.sqrt((np.outer(np.diag(sigma), np.diag(sigma)) + sigma**2) / n)
        cov_z = np.abs(np.cov(part, rowvar=False) - sigma) / cov_se
        rows.append(row("latent mean (max z-score)", name, n, 0, mean_z.max(), Z_TOL))
        rows.append(row("latent covariance (max z-score)", name, n, 0, cov_z.max(), Z_TOL))
    return rows


def _check_persistence(spec: dict, mart: pd.DataFrame, oracle: pd.DataFrame) -> list[dict]:
    """Hidden traits persist: the lag-1 correlation of (z − client mean) is ρ for every trait.

    Uses clients present in the last two months; a correlation's standard error is (1 − ρ²)/√n.
    """
    months = sorted(mart["snapshot_month"].unique())
    keys = ["client_id", "subsegment", "nationality_group", "employment_status"]
    both = (
        mart.loc[mart["snapshot_month"] == months[-1], keys]
        .merge(oracle[oracle["snapshot_month"] == months[-2]], on="client_id")
        .merge(
            oracle[oracle["snapshot_month"] == months[-1]], on="client_id", suffixes=("_0", "_1")
        )
    )
    means = expected_latent_means(spec, both)
    before = both[[f"z_{n}_0" for n in LATENTS]].to_numpy() - means
    after = both[[f"z_{n}_1" for n in LATENTS]].to_numpy() - means
    rho = spec["latent_rho"]
    profile = profile_of(spec, both).to_numpy()
    rows = []
    for name in spec["profiles"]:
        a, b = before[profile == name], after[profile == name]
        corr = np.array([np.corrcoef(a[:, d], b[:, d])[0, 1] for d in range(len(LATENTS))])
        z = np.abs(corr - rho) / ((1 - rho**2) / np.sqrt(len(a)))
        rows.append(row("latent lag-1 correlation (max z-score)", name, len(a), 0, z.max(), Z_TOL))
    return rows


def _check_turnover(spec: dict, mart: pd.DataFrame) -> list[dict]:
    """Monthly exit and entry rates per profile, read from the mart itself (panel months 2 on).

    Exposure is the book in months 1–23: exits are clients whose last row comes before the final
    month, entries clients whose first row comes after the first month.
    """
    months = mart["snapshot_month"]
    first_rows = mart.drop_duplicates("client_id")  # the mart is in month order
    last_rows = mart.drop_duplicates("client_id", keep="last")
    exposure = profile_of(spec, mart[months < months.max()]).value_counts()
    left = profile_of(spec, last_rows[last_rows["snapshot_month"] < months.max()]).value_counts()
    joined = profile_of(
        spec, first_rows[first_rows["snapshot_month"] > months.min()]
    ).value_counts()
    rows = []
    for name, p in spec["profiles"].items():
        n = int(exposure.get(name, 0))
        rows.append(share_row("monthly exit rate", name, p["exit_rate"], left.get(name, 0), n))
        rows.append(share_row("monthly entry rate", name, p["entry_rate"], joined.get(name, 0), n))
    return rows
