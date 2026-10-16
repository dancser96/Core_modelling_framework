"""Step-3 levels: medians, ordering, persistence, tails and segment overlap of the amounts.

Amounts are compared with their level: the spec's median multiple per profile × the hidden base
(true income or wealth base, from the oracle) × the salary-transfer adjustment, × the market index
for wealth (test_harness.md "Levels"). Statistics use one row per client, from the panel's first
May (no seasonal factor, school fee, bonus or app relaunch) or the pair April–May, so their standard
errors are analytical; spec ranges are checked as ranges.

Medians: holders and active users are picked by the same hidden traits that move their amounts
(FX activity and FX volume both load on the cross-border trait), so among them the median of
amount / level sits above the spec's multiple. Each row's trait term (λ·Δz, maths §4, with the
client's trait mean restated from the spec) is therefore removed, and the median of what is left
is restated from the spec's variance components (`scipy.stats.exponnorm`). A term-deposit balance
is drawn at adoption and at each rollover, so its row is the client's first draw in the panel.
Rows whose deposit floor or card limit could move them across the median are left out: a
condition on the client's base and limit, never on the amount. The mix behind the amounts
(remittance, cash, logins, the pooled relationship, the new-client ramp) is `checks_amount_mix`.
"""

from datetime import date

import numpy as np
import pandas as pd
from scipy.stats import exponnorm

from synthetic.check_stats import (
    first_month,
    hill_estimate,
    median_ratio_row,
    pair_rows,
    shift_month,
    side_row,
    sorted_panel,
)
from synthetic.check_table import range_row, row
from synthetic.holding_events import before
from synthetic.presets import LATENTS
from synthetic.products import PROFILE_ORDER
from synthetic.spec_restated import trait_deviation

REFERENCE_MONTH = 5  # May
SPEC_KEYS = {"spend_cc_vol": "spend_cc"}  # mart column → spec measure, where the names differ
MEDIAN_MARGIN = 0.25  # a floor or cap this far (log) from the expected median can't move it
LAG1_BANDS = {"casa_bal": (0.9, 1.0), "spend_cc_vol": (0.6, 0.8), "fx_vol": (0.6, 0.8),
              "inflow_casa_other_vol": (0.6, 0.8)}  # fmt: skip
HILL_TOP_SHARE, HILL_REL_TOL = 0.05, 0.30
MM_ABOVE_UM = (0.20, 0.30)  # share of MM clients above the UM median balance ("Segment overlap")
UP_ABOVE_LP = (0.0, 0.05)  # share of Upper Priority above the Lower Private median: "fewer than 5%"
MART_COLUMNS = [
    "client_id", "snapshot_month", "subsegment", "nationality_group", "employment_status",
    "salary_transfer_flag", "relationship_days",
    *[f"loan_{key}_maturity_months" for key in ("personal", "auto", "home")],
    "casa_active_flag", "cc_active_flag", "td_flag", "wealth_digital_flag", "wealth_trad_flag",
    "fx_active_flag", "casa_bal", "inflow_casa_other_vol", "cc_limit", "cc_utilisation_ratio",
    "spend_cc_vol", "td_bal", "wealth_digital_bal", "wealth_trad_bal", "fx_vol",
]  # fmt: skip
ORACLE_COLUMNS = ["client_id", "snapshot_month", "true_income", "wealth_base", "revolver_flag",
                  *[f"z_{t}" for t in ("wealth", "activity", "crossborder")]]  # fmt: skip


def check_amount_levels(mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict) -> pd.DataFrame:
    """Step 3, levels: medians, ordering, persistence, tails and overlap."""
    spec = truth["spec"]
    panel = sorted_panel(spec, mart, oracle)
    ref = first_month(panel, REFERENCE_MONTH)
    at_ref = panel[panel["snapshot_month"] == ref]
    ramp = len(spec["levels"]["new_client_ramp"])  # settled: past the ramp, with a month to spare
    settled = at_ref[at_ref["casa_active_flag"] & (at_ref["tenure_months"] > ramp)]
    market = truth["market_index"][f"{ref:%Y-%m}"]
    samples = {
        "casa_bal": settled,
        "td_bal": _deposit_draws(panel),
        "wealth_digital_bal": at_ref[at_ref["wealth_digital_flag"]],
        "wealth_trad_bal": at_ref[at_ref["wealth_trad_flag"]],
        "fx_vol": at_ref[at_ref["fx_active_flag"]],
        "spend_cc_vol": at_ref[at_ref["cc_active_flag"] & ~at_ref["revolver_flag"]],
    }
    rows = (
        _check_medians(spec, samples, market)
        + _check_order_and_overlap(spec, settled)
        + _check_lag1(spec, panel, ref)
        + _check_tails(spec, settled, at_ref, market)
    )
    return pd.DataFrame(rows)


def _deposit_draws(panel: pd.DataFrame) -> pd.DataFrame:
    """Each client's first month in the panel whose term-deposit balance was drawn: adoption, or a
    change at rollover (a holding running at the first panel month has no known draw there)."""
    held = panel["td_flag"].to_numpy()
    held_before = before(panel, "td_flag", False).astype(bool)
    redrawn = panel["td_bal"].to_numpy() != before(panel, "td_bal", 0.0)
    draws = panel[held & panel["known"].to_numpy() & (~held_before | redrawn)]
    return draws.drop_duplicates("client_id")


def _level(spec: dict, df: pd.DataFrame, measure: str) -> np.ndarray:
    """The spec's level of a measure per row: multiple × base × salary-transfer adjustment.

    Non-salary inflow is (multiple − 1) × income with salary transfer, 0.4 × multiple × income
    without; its "other" part is a share set by employment ("Current/savings account"). The market
    index, for wealth, is the caller's.
    """
    levels = spec["levels"]
    profile = df["profile"].map(PROFILE_ORDER.index).to_numpy()
    transfer = df["salary_transfer_flag"].to_numpy()
    no_transfer = levels["no_salary_transfer"]
    if measure == "inflow_casa_other_vol":
        multiple = np.array(levels["measures"]["inflow_casa"]["multiples"])[profile]
        non_salary = np.where(transfer, multiple - 1, no_transfer["flows"] * multiple)
        private = (df["profile"] == "private").to_numpy()
        share = df["employment_status"].map(levels["inflow_other_share"]).to_numpy()
        share = share + levels["inflow_other_private_extra"] * private
        return non_salary * share * df["true_income"].to_numpy()
    cfg = levels["measures"][SPEC_KEYS.get(measure, measure)]
    base = df["wealth_base" if cfg["base"] == "wealth" else "true_income"].to_numpy()
    adjust = np.where(transfer, 1.0, no_transfer["casa_bal"]) if measure == "casa_bal" else 1.0
    return np.array(cfg["multiples"])[profile] * base * adjust


def _trait_term(spec: dict, df: pd.DataFrame, measure: str) -> np.ndarray:
    """The trait term in log(amount / level): λ·Δz of the measure's trait, plus φ·λ·Δz of the
    current/savings balance's trait for flows (maths §4)."""
    levels = spec["levels"]
    cfg, casa = levels["measures"][SPEC_KEYS.get(measure, measure)], levels["measures"]["casa_bal"]
    term = cfg["loading"] * trait_deviation(spec, df, cfg["trait"])
    if cfg["kind"] == "flow":
        phi = levels["balance_elasticity"]
        term = term + phi * casa["loading"] * trait_deviation(spec, df, casa["trait"])
    return term


def _log_median(sd: float, rate: float) -> float:
    """Log median of N(0, sd²) + Exponential(rate): an exponentially modified normal."""
    return float(exponnorm.median(1 / (sd * rate), scale=sd))


def _expected_log_median(spec: dict, measure: str, profile: str) -> float:
    """Median of log(amount / level) less the trait term, restated from maths §4.

    The random part is N(0, s²) + Exponential(rate) − c, where c, the log median of the whole part,
    counts the trait term's variance in s²; without the trait term the median is
    offset(s without it) − offset(s). Flows add the balance's part: φ² s²_casa to the normal part,
    rate a_casa / φ.
    """
    levels, scale = spec["levels"], spec["profiles"][profile]["latent_scale"]
    cfg, casa = levels["measures"][SPEC_KEYS.get(measure, measure)], levels["measures"]["casa_bal"]
    traits = (cfg["loading"] * scale[LATENTS.index(cfg["trait"])]) ** 2
    stock_noise = levels["stock_noise"]["sd"] ** 2
    if cfg["kind"] == "stock":
        rest, rate = cfg["effect_sd"] ** 2 + stock_noise, cfg["tail"]
    else:
        phi, flow = levels["balance_elasticity"], levels["flow_noise"]
        rest = flow["effect_sd"] ** 2 + flow["sd"] ** 2
        rest += phi**2 * (casa["effect_sd"] ** 2 + stock_noise)
        traits += (phi * casa["loading"] * scale[LATENTS.index(casa["trait"])]) ** 2
        rate = casa["tail"] / phi
    return _log_median(np.sqrt(rest), rate) - _log_median(np.sqrt(rest + traits), rate)


def _check_medians(spec: dict, samples: dict[str, pd.DataFrame], market: float) -> list[dict]:
    """Median of log(amount / level) less the trait term, per measure and profile.

    Left out: rows whose deposit floor (or, for a transactor, card limit) lies within MEDIAN_MARGIN
    of the expected median on the log scale, where flooring (capping) could move a value across it.
    """
    rows, floor = [], np.log(spec["levels"]["deposit"]["minimum"])
    for measure, df in samples.items():
        level = _level(spec, df, measure) * (market if measure.startswith("wealth") else 1.0)
        trait = _trait_term(spec, df, measure)
        adjusted = np.log(df[measure].to_numpy(dtype=float) / level) - trait
        cap = np.log(df["cc_limit"].to_numpy(dtype=float)) if measure == "spend_cc_vol" else np.inf
        for profile in PROFILE_ORDER:
            expected = _expected_log_median(spec, measure, profile)
            centre = np.log(level) + trait + expected
            floor_clear = floor < centre - MEDIAN_MARGIN if measure == "td_bal" else True
            keep = (df["profile"] == profile).to_numpy() & (cap > centre + MEDIAN_MARGIN)
            keep &= floor_clear
            check = f"log median {measure} / level, trait term removed"
            rows.append(median_ratio_row(check, profile, adjusted[keep], expected))
    return rows


def _check_order_and_overlap(spec: dict, settled: pd.DataFrame) -> list[dict]:
    """Balance medians fall with each subsegment; MM overlaps UM; Private stands apart."""
    medians = settled.groupby("subsegment")["casa_bal"].median()[list(spec["subsegments"])]
    gaps = np.log(medians.to_numpy()[:-1] / medians.to_numpy()[1:])
    mm = settled.loc[settled["subsegment"] == "MM", "casa_bal"]
    upper = settled.loc[settled["subsegment"] == "Upper Priority", "casa_bal"]
    mm_above = float((mm > medians["UM"]).mean())
    up_above = float((upper > medians["Lower Private"]).mean())
    check = "casa_bal medians by subsegment: smallest log step down > 0"
    return [
        side_row(check, "all", len(settled), 0.0, float(gaps.min())),
        range_row("share above the UM median casa_bal", "MM", len(mm), *MM_ABOVE_UM, mm_above),
        range_row("share above the Lower Private median", "Upper Priority", len(upper),
                  *UP_ABOVE_LP, up_above),
    ]  # fmt: skip


def _check_lag1(spec: dict, panel: pd.DataFrame, ref: date) -> list[dict]:
    """Lag-1 correlation of log(amount / level) from April to May, one pair per client.

    Balances: active both months and past the ramp. Flows: positive both months; card spend only
    for transactors below the limit both months, where spend is the wanted spend.
    """
    prev, ramp = shift_month(ref, -1), len(spec["levels"]["new_client_ramp"])
    two = panel[panel["snapshot_month"].isin([prev, ref])].copy()
    two["casa_ok"] = two["casa_active_flag"] & (two["tenure_months"] > ramp)
    two["card_ok"] = ~two["revolver_flag"] & (two["cc_utilisation_ratio"] < 1)
    for measure in LAG1_BANDS:
        amount = two[measure].to_numpy(dtype=float)
        level = _level(spec, two, measure)
        two[f"log_{measure}"] = np.log(np.where(amount > 0, amount, np.nan) / level)
    pairs = pair_rows(two, prev, ref, [*[f"log_{m}" for m in LAG1_BANDS], "casa_ok", "card_ok"])
    rows = []
    for measure, (low, high) in LAG1_BANDS.items():
        x, y = pairs[f"log_{measure}_0"].to_numpy(), pairs[f"log_{measure}_1"].to_numpy()
        ok = ~np.isnan(x) & ~np.isnan(y)
        if measure in ("casa_bal", "spend_cc_vol"):
            flag = "casa_ok" if measure == "casa_bal" else "card_ok"
            ok &= (pairs[f"{flag}_0"] & pairs[f"{flag}_1"]).to_numpy()
        corr = float(np.corrcoef(x[ok], y[ok])[0, 1])
        check = f"lag-1 correlation of log {measure} / level"
        rows.append(range_row(check, f"{prev:%b}–{ref:%b}", ok.sum(), low, high, corr))
    return rows


def _check_tails(spec: dict, settled: pd.DataFrame, at_ref: pd.DataFrame, market: float) -> list:
    """Hill estimate of the tail index on the top 5% of amount / level, all profiles pooled
    (amount / level takes out the profile's scale; mass alone holds too few wealth clients)."""
    samples = {
        "casa_bal": settled,
        "td_bal": at_ref[at_ref["td_flag"]],
        "wealth_trad_bal": at_ref[at_ref["wealth_trad_flag"]],
    }
    rows = []
    for measure, df in samples.items():
        level = _level(spec, df, measure) * (market if measure.startswith("wealth") else 1.0)
        estimate, k = hill_estimate(df[measure].to_numpy(dtype=float) / level, HILL_TOP_SHARE)
        tail = spec["levels"]["measures"][measure]["tail"]
        check = f"Hill tail index of {measure} / level, top {HILL_TOP_SHARE:.0%} (k)"
        rows.append(row(check, "all profiles", k, tail, estimate, HILL_REL_TOL * tail))
    return rows
