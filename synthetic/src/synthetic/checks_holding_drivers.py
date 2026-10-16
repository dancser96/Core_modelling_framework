"""Step-2 checks of what drives adoption: the income threshold and churned status.

Each check compares two groups' event rates as a log ratio. Other drivers (traits, age, profile,
salary transfer) differ between the groups, so each group's events are divided by the sum of its
chances without the effect under test, restated from the product spec (test_harness.md maths §3).
"""

import numpy as np
import pandas as pd
from scipy.special import expit

from synthetic.check_table import Z_TOL, row
from synthetic.holding_events import before, product_keys, sum_row

NEAR_THRESHOLD = 0.2  # income within ±20% of a product's minimum


def check_drivers(
    spec: dict, calib: dict, panel: pd.DataFrame, events: dict[str, dict]
) -> list[dict]:
    """The income-threshold jump (and exemptions) and the churned odds, against the spec."""
    return _check_threshold(spec, calib, panel, events) + _check_churned(spec, calib, panel, events)


def _log_odds(spec: dict, calib: dict, key: str, panel: pd.DataFrame) -> np.ndarray:
    """A product's chance on the log-odds scale, restated from the spec (test_harness.md §3),
    without the income threshold and churned effects."""
    product = spec["products"][key]
    out = panel["profile"].map(calib[key]["intercept"]).to_numpy(dtype=float)
    for trait, loading in product.get("traits", {}).items():
        out = out + loading * panel[f"z_{trait}"].to_numpy()
    age, age_cfg = panel["age"].to_numpy(), product.get("age", {})
    if "slope_per_decade" in age_cfg:
        out = out + age_cfg["slope_per_decade"] * (age - 40) / 10
    if "peak" in age_cfg:
        out = out - age_cfg["curvature"] * ((age - age_cfg["peak"]) / 10) ** 2
    for column, effect in product.get("effects", {}).items():
        out = out + panel[column].map(effect).fillna(0.0).to_numpy()
    return out


def _ratio_row(
    check: str, stratum: str, s: np.ndarray, hit: np.ndarray, top: tuple, bottom: tuple
) -> dict:
    """Log ratio of two groups' event rates, each over its chance without the spec's effect.

    `top` and `bottom` are (rows, the spec's effect on the log-odds scale). Dividing each group's
    events by Σσ(s) over its own rows removes the other drivers (traits, age, profile, salary
    transfer), which differ between the groups; the tolerance is the Poisson standard error of the
    two event counts.
    """
    realised, expected, hits = [], [], []
    for rows, effect in (top, bottom):
        base = expit(s[rows]).sum()
        hits.append(max(hit[rows].sum(), 1))  # no events: realised is -inf and the row fails
        realised.append(np.log(hit[rows].sum() / base))
        expected.append(np.log(expit(s[rows] + effect).sum() / base))
    tolerance = Z_TOL * np.sqrt(1 / hits[0] + 1 / hits[1])
    n = int(top[0].sum() + bottom[0].sum())
    return row(check, stratum, n, expected[0] - expected[1], realised[0] - realised[1], tolerance)


def _check_threshold(
    spec: dict, calib: dict, panel: pd.DataFrame, events: dict[str, dict]
) -> list[dict]:
    """Below the income threshold adoption odds fall by the spec's factor; among clients without
    income, the exempt ones behave as if above it. Card: non-holders after onboarding."""
    rules, income = spec["holding_rules"], panel["income"].to_numpy()
    exempt = panel["profile"].isin(rules["income_exempt"]["profiles"]) | panel[
        "employment_status"
    ].isin(rules["income_exempt"]["employment"])
    onboarded = (panel["tenure_months"] >= rules["onboarding_months"]).to_numpy()
    jump, rows = np.log(rules["below_threshold_odds"]), []
    for key, event in (("cc", "cc acquire"), ("loan_personal", "loan_personal open")):
        e, low = events[event], spec["products"][key]["min_income"]
        judged = e["at_risk"] & ~np.isnan(e["realised"]) & onboarded
        s, check = _log_odds(spec, calib, key, panel), f"{key}: log odds ratio above vs below"
        above = judged & (income >= low) & (income <= low * (1 + NEAR_THRESHOLD))
        below = judged & (income < low) & (income >= low / (1 + NEAR_THRESHOLD))
        free, bound = judged & np.isnan(income) & exempt, judged & np.isnan(income) & ~exempt
        rows += [
            _ratio_row(check, "income within 20%", s, e["realised"], (above, 0), (below, jump)),
            _ratio_row(
                check, "no income: exempt vs not", s, e["realised"], (free, 0), (bound, jump)
            ),
        ]
    return rows


def _check_churned(
    spec: dict, calib: dict, panel: pd.DataFrame, events: dict[str, dict]
) -> list[dict]:
    """Status products: the oracle holds for never and churned clients separately, and churned
    clients re-adopt at the spec's higher odds (direction and size, other drivers removed)."""
    odds, rows = np.log(spec["holding_rules"]["churned_odds"]), []
    for key in [k for k in product_keys(spec, "holding") if spec["products"][k].get("status")]:
        e, status = events[f"{key} acquire"], before(panel, f"{key}_status", "never")
        judged = e["at_risk"] & ~np.isnan(e["realised"])
        never, churned = judged & (status == "never"), judged & (status == "churned")
        for name, part in (("never", never), ("churned", churned)):
            check = f"{key} acquire: events vs Σ chance"
            rows.append(sum_row(check, f"was {name}", e["chance"][part], e["realised"][part]))
        s, check = _log_odds(spec, calib, key, panel), f"{key}: log odds ratio churned vs never"
        rows.append(_ratio_row(check, "all", s, e["realised"], (churned, odds), (never, 0)))
    return rows
