"""Presets and the population spec of the synthetic retail book.

The spec is plain data: subsegments with their segment, share, income level, age and hidden-trait
means; four profiles (private, priority, affluent, mass) that set the nationality, employment and
emirate mixes, turnover and how spread out and correlated the hidden traits are; the income model;
the products and holding rules (from `products`); amount levels and time effects (from `levels`).
The generator reads only this dict, so another domain or entity is another spec, not new code.
Values are ballpark, close to public UAE figures without copying any bank's book; the tables in
docs/components/test_harness.md explain them.
"""

from synthetic.levels import LEVELS, SEASONS
from synthetic.products import HOLDING_RULES, PRODUCTS

LATENTS = ("wealth", "activity", "digital", "credit", "crossborder")
NATIONALITY_GROUPS = ("ASIA", "ARAB", "WESTERN", "UAE", "GCC", "AFRICA", "OTHER")
EMPLOYMENT = ("Employed", "Self-employed", "Unemployed", "Retired", "Other")
EMIRATES = (
    "Dubai",
    "Abu Dhabi",
    "Sharjah",
    "Ajman",
    "Ras Al Khaimah",
    "Fujairah",
    "Umm Al Quwain",
    "Others",  # outside the UAE or unknown
)


def _sub(
    segment: str, share: float, profile: str, median_income: int, age: int, latent_mean: list[float]
) -> dict:
    """One subsegment row of the spec."""
    return dict(
        segment=segment,
        share=share,
        profile=profile,
        median_income=median_income,
        age=age,
        latent_mean=latent_mean,
    )


# fmt: off
# Wealthiest first: segment, share, profile, median declared monthly income (AED) of an employed
# client, mean age, latent mean (order: LATENTS).
SUBSEGMENTS = {
    "Upper Private":  _sub("Private",  0.0025, "private",  150_000, 54, [ 3.0,  0.6,  0.3, -0.3,  0.6]),
    "Lower Private":  _sub("Private",  0.0075, "private",   90_000, 52, [ 2.5,  0.5,  0.3, -0.2,  0.5]),
    "Upper Priority": _sub("Priority", 0.01,   "priority",  60_000, 46, [ 2.0,  0.5,  0.4,  0.0,  0.4]),
    "Lower Priority": _sub("Priority", 0.03,   "priority",  40_000, 43, [ 1.6,  0.4,  0.4,  0.1,  0.3]),
    "UA":             _sub("PSB",      0.043,  "affluent",  30_000, 41, [ 1.2,  0.3,  0.3,  0.2,  0.2]),
    "A":              _sub("PSB",      0.043,  "affluent",  20_000, 39, [ 0.8,  0.2,  0.2,  0.2,  0.1]),
    "UM":             _sub("PSB",      0.205,  "mass",      12_000, 36, [ 0.3,  0.1,  0.1,  0.2,  0.0]),
    "MM":             _sub("PSB",      0.616,  "mass",       6_000, 34, [-0.2,  0.0,  0.0,  0.1,  0.0]),
    "LM":             _sub("PSB",      0.043,  "mass",       3_000, 31, [-0.8, -0.3, -0.3, -0.1, -0.1]),
}

# Countries per nationality group, most common first, with the Zipf exponent of their frequencies.
COUNTRIES = {
    "ASIA": (["India", "Pakistan", "Bangladesh", "Philippines", "Sri Lanka", "Nepal", "China",
              "Iran", "Indonesia", "Afghanistan", "Malaysia", "South Korea", "Japan", "Vietnam",
              "Thailand", "Kazakhstan", "Uzbekistan"], 1.2),
    "ARAB": (["Egypt", "Jordan", "Syria", "Lebanon", "Palestine", "Iraq", "Yemen", "Sudan",
              "Morocco", "Tunisia", "Algeria", "Libya"], 1.0),
    "WESTERN": (["United Kingdom", "United States", "Canada", "France", "Germany", "Australia",
                 "Italy", "Netherlands", "Ireland", "Spain", "Switzerland", "Sweden",
                 "New Zealand"], 1.0),
    "UAE": (["United Arab Emirates"], 1.0),
    "GCC": (["Saudi Arabia", "Oman", "Bahrain", "Kuwait", "Qatar"], 1.0),
    "AFRICA": (["Nigeria", "Kenya", "Ethiopia", "Uganda", "South Africa", "Ghana", "Somalia",
                "Cameroon", "Tanzania", "Zimbabwe"], 1.0),
    "OTHER": (["Russia", "Ukraine", "Turkey", "Brazil", "Colombia", "Mexico"], 1.0),
}

# Hidden-trait correlations (order: LATENTS), kept within [0, 0.2]. The wealthy profiles decouple
# wealth from credit appetite.
_R_PSB = [
    [1.0,  0.2,  0.1,  0.1,  0.05],
    [0.2,  1.0,  0.2,  0.15, 0.1 ],
    [0.1,  0.2,  1.0,  0.1,  0.05],
    [0.1,  0.15, 0.1,  1.0,  0.0 ],
    [0.05, 0.1,  0.05, 0.0,  1.0 ],
]
_R_WEALTHY = [
    [1.0,  0.15, 0.05, 0.0,  0.1 ],
    [0.15, 1.0,  0.2,  0.1,  0.15],
    [0.05, 0.2,  1.0,  0.05, 0.05],
    [0.0,  0.1,  0.05, 1.0,  0.0 ],
    [0.1,  0.15, 0.05, 0.0,  1.0 ],
]

# Mixes per profile (orders: NATIONALITY_GROUPS, EMPLOYMENT, EMIRATES).
#                    ASIA  ARAB  WEST   UAE   GCC    AFR   OTHER
_NATIONALITY = {
    "private":      [0.15, 0.08, 0.20,  0.40, 0.12,  0.03, 0.02],
    "priority":     [0.30, 0.12, 0.28,  0.18, 0.06,  0.03, 0.03],
    "affluent":     [0.50, 0.14, 0.12,  0.14, 0.03,  0.04, 0.03],
    "mass":         [0.74, 0.12, 0.015, 0.04, 0.005, 0.07, 0.01],
}
#                    Empl  Self  Unemp  Retir Other
_EMPLOYMENT = {
    "private":      [0.25, 0.30, 0.10,  0.20, 0.15],
    "priority":     [0.55, 0.22, 0.08,  0.07, 0.08],
    "affluent":     [0.76, 0.13, 0.04,  0.03, 0.04],
    "mass":         [0.91, 0.05, 0.015, 0.01, 0.015],
}
#                    Dubai AbuDh Sharj Ajman RAK   Fuj   UAQ   Others
_EMIRATE = {
    "private":      [0.50, 0.15, 0.04, 0.02, 0.02, 0.01, 0.01, 0.25],
    "priority":     [0.60, 0.17, 0.08, 0.03, 0.03, 0.01, 0.01, 0.07],
    "affluent":     [0.50, 0.15, 0.13, 0.05, 0.03, 0.02, 0.01, 0.11],
    "mass":         [0.50, 0.15, 0.13, 0.05, 0.03, 0.02, 0.01, 0.11],
}
# fmt: on


def _profile(
    name: str,
    *,
    salary_transfer: float,
    non_resident: float,
    entry_rate: float,
    exit_rate: float,
    age_sd: float,
    relationship_beta: tuple[float, float],
    latent_scale: list[float],
    latent_corr: list[list[float]],
) -> dict:
    """One profile of the spec; its mixes come from the tables above."""
    return dict(
        nationality=_NATIONALITY[name],
        employment=_EMPLOYMENT[name],
        emirate=_EMIRATE[name],
        salary_transfer=salary_transfer,  # share of Employed clients whose salary comes in
        non_resident=non_resident,  # share of non-nationals with no residence in the country
        entry_rate=entry_rate,  # new clients a month, as a share of the profile's clients
        exit_rate=exit_rate,
        age_sd=age_sd,
        relationship_beta=relationship_beta,  # share of adult life spent as a client (Beta)
        latent_scale=latent_scale,  # order: LATENTS
        latent_corr=latent_corr,
    )


RETAIL = {
    "first_month": "2024-10",
    "burn_in_months": 12,
    "age_range": (18, 85),
    # New-to-bank clients are younger than the book; without this the book ages over the panel.
    "new_to_bank_age_shift": -5,
    "latent_rho": 0.95,
    # Scales the distances between subsegment trait means around their book-weighted centre: at
    # 0.5 subsegments overlap more and pooled relationships move towards within-subsegment ones.
    "separation": 1.0,
    "national_group": "UAE",  # no residence length for nationals
    # Years between arrival in the country and relationship start: most open an account soon after
    # arriving, the rest had lived here for years (switchers). The same mix applies to existing and
    # new-to-bank clients, since existing clients were new to the bank once.
    "residence_gap": {"recent_share": 0.6, "recent_mean_years": 0.3, "settled_mean_years": 4.0},
    "subsegments": SUBSEGMENTS,
    "countries": COUNTRIES,
    # Turnover falls with wealth; entry minus exit is the same everywhere, so the mix stays flat.
    "profiles": {
        "private": _profile(
            "private",
            salary_transfer=0.30,
            non_resident=0.15,
            entry_rate=0.004,
            exit_rate=0.002,
            age_sd=10,
            relationship_beta=(2.0, 2.0),
            latent_scale=[0.4, 0.6, 0.7, 0.6, 0.8],
            latent_corr=_R_WEALTHY,
        ),
        "priority": _profile(
            "priority",
            salary_transfer=0.50,
            non_resident=0.03,
            entry_rate=0.006,
            exit_rate=0.004,
            age_sd=9,
            relationship_beta=(1.5, 2.5),
            latent_scale=[0.4, 0.7, 0.8, 0.7, 0.8],
            latent_corr=_R_WEALTHY,
        ),
        "affluent": _profile(
            "affluent",
            salary_transfer=0.65,
            non_resident=0.0,
            entry_rate=0.008,
            exit_rate=0.006,
            age_sd=9,
            relationship_beta=(1.2, 3.0),
            latent_scale=[0.5, 0.8, 0.9, 0.8, 0.8],
            latent_corr=_R_PSB,
        ),
        "mass": _profile(
            "mass",
            salary_transfer=0.70,
            non_resident=0.0,
            entry_rate=0.012,
            exit_rate=0.010,
            age_sd=8,
            relationship_beta=(1.2, 3.0),
            latent_scale=[0.5, 0.8, 0.9, 0.8, 0.8],
            latent_corr=_R_PSB,
        ),
    },
    # Shifts added to the subsegment's latent mean (order: LATENTS).
    "latent_shift_nationality": {
        "ASIA": [0, 0, 0, 0, 0.8],
        "ARAB": [0, 0, 0, 0.1, 0.3],
        "WESTERN": [0, 0, 0.3, 0, 0.5],
        "UAE": [0, 0, 0.2, 0.3, -0.8],
        "GCC": [0, 0, 0.2, 0.2, 0.0],
        "AFRICA": [0, 0, 0, 0, 0.6],
        "OTHER": [0, 0, 0, 0, 0.3],
    },
    "latent_shift_employment": {
        "Employed": [0, 0, 0, 0, 0],
        "Self-employed": [0, 0.3, 0, 0.1, 0],
        "Unemployed": [0, -0.5, 0, -0.5, 0],
        "Retired": [0.3, -0.3, -0.3, -0.4, 0],
        "Other": [0.3, 0, 0, -0.2, 0],
    },
    "income": {
        "employment_multiplier": {
            "Employed": 1.0,
            "Self-employed": 1.3,
            "Unemployed": 0.15,
            "Retired": 0.5,
            "Other": 1.0,
        },
        "wealth_loading": 0.3,  # log-income change per within-subsegment sd of the wealth trait
        "sigma": 0.35,
        "missing": {
            "Employed": 0.02,
            "Self-employed": 0.10,
            "Unemployed": 0.80,
            "Retired": 0.60,
            "Other": 0.85,
        },
        "missing_private_extra": 0.30,  # wealthy clients often never declare an income
    },
    "products": PRODUCTS,
    "holding_rules": HOLDING_RULES,
    "levels": LEVELS,
    "seasons": SEASONS,
}

PRESETS = {
    "unit": {"spec": RETAIL, "n_clients": 5_000, "n_months": 24},
    "canonical": {"spec": RETAIL, "n_clients": 100_000, "n_months": 24},
}
