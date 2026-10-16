"""Product spec of the synthetic retail book: what clients hold and how often that changes.

Plain data, read by `hazards` and `holdings`. Each product is set with as few numbers as possible:
- `shares`: who holds it at the start, per profile (private, priority, affluent, mass);
- 0/1 products: `events_per_100k`, how many adoptions a month a book of 100k clients sees,
  including those that refill holdings of clients who left the bank (for products with an
  onboarding wave: after onboarding). How long a holding lasts follows from these two;
- loans: `term_months`, the fixed term; new loans a month follow from the share and the term;
- drivers of each client's monthly chance (`traits`, `age`, `effects`, `min_income`), on the
  log-odds scale, so clients differ within a profile and their chances move as their traits drift.

Kinds: `holding` is a 0/1 product (it can be lost and re-adopted); `loans` are account counts that
close only at maturity; `usage` is an active/dormant chain; `static` never changes after joining.
Products with `onboarding` (credit card, e-banking) are taken up by many new clients within their
first `onboarding_months`; the others build up over each client's tenure. A usage chain may
`requires` another product (at risk only while the client holds it), and has two optional fields:
`flag`, its column name (default `<key>_active_flag`), and `in_mart` (default True; False keeps a
hidden state such as the revolver out of the mart and in the oracle). Chains never count as
products. `HOLDING_RULES["bonus_trigger"]` raises some products' adoption odds in the months after
a client's bonus (the bonus itself is in `levels.SEASONS`). Values are ballpark (public UAE
figures, D-064).
"""

PROFILE_ORDER = ("private", "priority", "affluent", "mass")  # order of every `shares` list

HOLDING_RULES = {
    "onboarding_months": 3,  # for products with `onboarding`
    "below_threshold_odds": 0.2,  # below a product's minimum income, the odds of adopting are × 0.2
    # Without a declared income, these clients count as above every income threshold.
    "income_exempt": {"profiles": ["private", "priority"], "employment": ["Retired", "Other"]},
    "churned_odds": 2.0,  # clients who held the product before re-adopt at twice the odds
    "max_loan_accounts": 4,
    "lapse_loading": 0.5,  # usage: the drivers that wake a client also keep it active (× this)
    # A bonus multiplies these products' adoption odds in the `months_after` months that follow it.
    "bonus_trigger": {
        "products": ["td", "wealth_digital", "wealth_trad"],
        "odds": 2.0,
        "months_after": 2,
    },
}

PRODUCTS = {
    "casa": dict(kind="static", label="current/savings account", share=0.99),
    "cc": dict(
        kind="holding",
        label="credit card",
        onboarding=True,
        shares=[0.85, 0.80, 0.65, 0.30],
        events_per_100k=500,
        min_income=5_000,
        traits={"credit": 0.6, "activity": 0.3, "digital": 0.3},  # digital: the Simpson's trap
        effects={"salary_transfer_flag": {True: 0.7}},
    ),
    "td": dict(
        kind="holding",
        label="term deposit",
        shares=[0.40, 0.30, 0.15, 0.04],
        events_per_100k=260,
        traits={"wealth": 0.5, "digital": -0.3},
        age={"slope_per_decade": 0.2},
        status=True,
    ),
    "wealth_digital": dict(
        kind="holding",
        label="digital wealth",
        shares=[0.10, 0.20, 0.12, 0.02],
        events_per_100k=400,
        traits={"digital": 0.6, "wealth": 0.4},
        age={"slope_per_decade": -0.2},
        status=True,
    ),
    "wealth_trad": dict(
        kind="holding",
        label="traditional wealth",
        shares=[0.60, 0.35, 0.10, 0.01],
        events_per_100k=30,
        traits={"wealth": 0.7, "digital": -0.3},
        age={"slope_per_decade": 0.3},
        effects={"employment_status": {"Retired": 1.0}},
        status=True,
    ),
    "ebanking": dict(
        kind="holding",
        label="e-banking registration",
        onboarding=True,
        in_product_count=False,  # a channel, not a banking product
        shares=[0.80, 0.90, 0.90, 0.75],
        events_per_100k=120,
        traits={"digital": 0.6},
        age={"slope_per_decade": -0.2},
    ),
    "loan_personal": dict(
        kind="loans",
        label="personal loan",
        shares=[0.05, 0.10, 0.20, 0.20],
        term_months=48,  # the UAE maximum
        min_income=5_000,
        traits={"credit": 0.6, "wealth": -0.3},
        age={"peak": 35, "curvature": 0.6},  # inverted U, peaking in the mid-30s (trap F18)
        # Ghana: a rare high-rate level (trap).
        effects={"salary_transfer_flag": {True: 1.0}, "nationality": {"Ghana": 1.5}},
    ),
    "loan_auto": dict(
        kind="loans",
        label="auto loan",
        shares=[0.03, 0.08, 0.12, 0.06],
        term_months=60,  # the UAE maximum
        min_income=5_000,
        traits={"credit": 0.4, "wealth": 0.2},
        age={"peak": 35, "curvature": 0.4},
    ),
    "loan_home": dict(
        kind="loans",
        label="home loan",
        shares=[0.15, 0.20, 0.10, 0.02],
        term_months=300,  # 25 years, the UAE maximum for expatriates
        min_income=15_000,
        traits={"wealth": 0.5},
        age={"peak": 42, "curvature": 0.5},
        effects={"nationality_group": {"UAE": 0.5, "GCC": 0.5, "WESTERN": 0.5}},
    ),
    # Usage: `shares` is the share active; FX for every client, the others among the clients
    # holding the product they require.
    "fx": dict(
        kind="usage",
        label="FX activity",
        shares=[0.60, 0.45, 0.30, 0.12],
        mean_active_months=24,
        traits={"crossborder": 0.8},
    ),
    "digital": dict(
        kind="usage",
        label="digital activity",
        shares=[0.80, 0.80, 0.80, 0.80],
        mean_active_months=36,
        requires="ebanking",
        traits={"digital": 0.8},
        age={"slope_per_decade": -0.2},
    ),
    "cc_activity": dict(
        kind="usage",
        label="card activity",
        shares=[0.85, 0.85, 0.80, 0.75],
        mean_active_months=24,
        requires="cc",
        traits={"activity": 0.6},
        flag="cc_active_flag",
    ),
    "casa_activity": dict(
        kind="usage",
        label="current/savings activity",
        shares=[0.91, 0.93, 0.94, 0.96],
        mean_active_months=180,
        requires="casa",
        traits={"activity": 0.5},
        effects={"salary_transfer_flag": {True: 2.4}},  # salary-transfer clients rarely go dormant
        flag="casa_active_flag",
    ),
    "cc_revolver": dict(
        kind="usage",
        label="revolver (carries a card balance)",
        shares=[0.10, 0.20, 0.30, 0.45],
        mean_active_months=24,
        requires="cc",
        traits={"credit": 0.5, "wealth": -0.3},
        flag="revolver_flag",
        in_mart=False,  # hidden: interest above 0 reveals it
    ),
}
