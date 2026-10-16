"""Amount spec of the synthetic retail book: how large amounts are, how they move, and when.

Plain data, read by the amount mechanisms (`variation`, `balances`, `flows`, `cards`, `logins`,
`amounts`) and the time effects (`seasons`). Every amount is a median multiple of a hidden base per
profile: flows scale with the client's true income, balances with its wealth base. Around that
median, a persistent client effect, monthly AR(1) noise, one hidden trait's deviation and (for
balances) a persistent power-law multiplier make clients differ and amounts persist. `SEASONS`
holds the time effects, which differ by profile. Lists of four values follow `PROFILE_ORDER`
(private, priority, affluent, mass). The tables in docs/components/test_harness.md ("Amounts")
explain the values.
"""

# fmt: off
LEVELS = {
    # Median multiple of the base per profile, for a holder in an active, non-seasonal month.
    # `kind`: stock (a balance) or flow; `trait` / `loading`: the hidden trait whose deviation from
    # the client's mean moves the amount; `effect_sd`: the persistent client effect; `tail`: the
    # power-law tail index of the persistent multiplier (stocks only).
    "measures": {
        "casa_bal":           dict(kind="stock", base="wealth", multiples=[40, 4, 1.5, 0.5], tail=2.0, trait="wealth", loading=0.3, effect_sd=0.7),
        "td_bal":             dict(kind="stock", base="wealth", multiples=[20, 10, 6, 3],    tail=1.8, trait="wealth", loading=0.3, effect_sd=0.5),
        "wealth_trad_bal":    dict(kind="stock", base="wealth", multiples=[60, 15, 8, 4],    tail=1.5, trait="wealth", loading=0.3, effect_sd=0.5),
        "wealth_digital_bal": dict(kind="stock", base="wealth", multiples=[10, 4, 2, 1],     tail=1.5, trait="wealth", loading=0.3, effect_sd=0.5),
        "inflow_casa":        dict(kind="flow",  base="income", multiples=[1.5, 1.3, 1.15, 1.05], trait="activity",    loading=0.2),
        "outflow_casa":       dict(kind="flow",  base="income", spend_share=0.85,                 trait="activity",    loading=0.2),
        "spend_cc":           dict(kind="flow",  base="income", multiples=[0.4, 0.3, 0.3, 0.35],  trait="activity",    loading=0.3),
        "fx_vol":             dict(kind="flow",  base="income", multiples=[1.0, 0.6, 0.4, 0.3],   trait="crossborder", loading=0.25),
    },
    "stock_noise": {"rho": 0.8, "sd": 0.25},  # monthly AR(1) noise of log balances
    "flow_noise": {"rho": 0.3, "sd": 0.35, "effect_sd": 0.4},
    "balance_elasticity": 0.3,  # flows × (current/savings random part)^0.3: coherent, thinner tails
    # Clients without salary transfer bank their salary elsewhere.
    "no_salary_transfer": {"flows": 0.4, "casa_bal": 0.6},
    "new_client_ramp": [0.5, 0.75],  # current/savings balance × in months on book 1 and 2
    "deposit": {"minimum": 10_000, "term_months": 12},
    "market": {"mean": 0.005, "sd": 0.03},  # monthly log return of the shared wealth index
    # Counts: 1 + Poisson(mean × G), G ~ Gamma(shape, 1 / shape), in active months.
    "counts": {
        "gamma_shape": 2.0,
        "activity_loading": 0.3,  # means × exp(0.3 × activity deviation)
        "outflow_casa": 12, "spend_cc": 10, "inflow_casa": 2, "remittance": 0.5, "fx": 1.0,
    },
    # Share of non-salary inflow that is "other" rather than transfers, by employment.
    "inflow_other_share": {"Employed": 0.2, "Self-employed": 0.6, "Unemployed": 0.3, "Retired": 0.5,
                           "Other": 0.7},
    "inflow_other_private_extra": 0.1,  # added to the "other" share in Private
    "subcategories": {
        "concentration": 50,  # Dirichlet concentration of monthly shares around the client's mean
        "outflow_casa": {
            "names": ["remittance", "cash", "bills", "transfers"],
            "shares": {"private": [5, 3, 12, 80], "priority": [12, 8, 20, 60],
                       "affluent": [20, 15, 25, 40], "mass": [30, 30, 25, 15]},
        },
        "spend_cc": {
            "names": ["travel", "retail", "online", "dining"],
            "shares": {"private": [45, 25, 15, 15], "priority": [30, 32, 20, 18],
                       "affluent": [18, 40, 24, 18], "mass": [6, 50, 24, 20]},
        },
        "remittance": {
            "remitter_share": [0.30, 0.40, 0.50, 0.60],  # of non-nationals
            "never": ["UAE", "GCC"],
            "nationality_factor": {"ASIA": 1.2, "AFRICA": 1.2, "ARAB": 1.0, "WESTERN": 0.5, "OTHER": 0.8},
            "income_elasticity": -0.3,  # × (income / subsegment median)^−0.3
        },
        # Share tilts: × exp(loading × trait deviation), then renormalised.
        "tilts": {"cash": {"digital": -0.4, "wealth": -0.2}, "travel": {"crossborder": 0.4},
                  "online": {"digital": 0.4}},
        "travel_months": {"chance": [0.5, 0.4, 0.3, 0.1], "crossborder": 0.5, "cap": 0.95},
    },
    "card": {
        "limit_multiples": [3, 2.5, 2, 1.5],
        "limit_tiers": [5_000, 10_000, 20_000, 35_000, 50_000, 75_000, 100_000, 150_000, 250_000, 500_000],
        "adjusted_share": 0.10,  # new cards one tier up (credit above the client's mean) or down
        "monthly_interest": 0.03,
        "minimum_repayment": 0.05,
        "repay_share_range": [0.05, 0.30],
    },
    "loans": {
        "principal_sd": 0.3,
        "loan_personal": {"principal_multiple": 8, "annual_rate": 0.07},
        "loan_auto": {"principal_multiple": 5, "annual_rate": 0.04},
        "loan_home": {"principal_multiple": 60, "annual_rate": 0.05},
    },
    "logins": {
        "per_month": [7, 10, 13, 16],  # logins a month of an active user
        "digital_loading": 0.4,
        "channel_factor": {"branch": 1.0, "digital": 2.0},  # digitally onboarded clients log in more
        "mobile_share": {"intercept": 1.5, "digital": 0.5, "age_per_decade": -0.3, "age_centre": 40},
        "gamma_shape": 2.0,
        "dormant_start_days": [30, 720],  # starting book: registered, dormant, logged in before
    },
}

SEASONS = {
    "summer_months": [7, 8],
    "summer": {
        "travel_spend": [1.6, 1.5, 1.4, 1.15],
        "fx_vol": [1.4, 1.3, 1.25, 1.1],
        "casa_bal": [0.90, 0.92, 0.94, 0.98],
        "travel_chance": 2.0,
    },
    "december": {"months": [12], "card_other_spend": [1.15, 1.12, 1.12, 1.08]},
    # Added to the wake-up log-odds of a chain in the given months of year (moves into them).
    "wake_shifts": {"fx": {"months": [7, 8], "shift": [0.5, 0.4, 0.3, 0.1]}},
    "school_fees": {
        "payer_share": [0.5, 0.5, 0.45, 0.15],
        "payer_ages": [28, 55],  # age when the client is drawn
        "annual_fee": [120_000, 80_000, 50_000, 12_000],
        "fee_sd": 0.3,
        "terms": {9: 0.4, 1: 0.3, 4: 0.3},  # month of year → share of the annual fee
    },
    "bonus": {"share": 0.5, "months": [1, 2, 3, 4], "factor_range": [1.0, 2.0]},
    "drift": {
        "trend_product": "digital",
        "wake_odds_per_year": 1.2,  # from the first panel month
        "app_relaunch_month": "2026-01",
        "mobile_login_factor": 1.8,  # PSI of mobile logins ≈ 0.37 after it (1.3 gave 0.07, 1.6 0.23)
    },
}
# fmt: on
