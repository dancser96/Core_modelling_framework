"""Oracle checks: the window probabilities, the regression quantiles and `truth.json`.

The window probability (`oracle.window_probability`, the API under test) is set against the checks'
own realised targets (`events.realised_target`, written from the spec's standard-targets table
without the generator's code): it is null exactly where the target is; events match the sum of the
probabilities overall and, for w = 3, per probability decile and per status at the observation
month (the churned clients' doubled odds), within the Poisson-binomial standard error. Rows whose
windows don't overlap are uncorrelated even for one client (an outcome is known before the next
window starts, and the probability is its chance given all that is known then), so each window
length w uses every w-th panel month (w = 3: months 3, 6, …, 21). The AUC computed here must equal
truth's to 1e-9 (two realised-target implementations agree), and so must the sizing.
Regression: on observation months 2, 3, 9, 14, 15, 21 (2 and 14 are Novembers, so a December
falls inside the window), realised next-3-month card spend against the oracle's quantiles and
mean. Last, `truth.json` carries what the checks and the notebook read (layout below).
"""

import numpy as np
import pandas as pd

from synthetic.checks.events import BINARY_TARGETS, STANDARD_TARGETS, realised_target
from synthetic.checks.mart import snapshot_columns
from synthetic.checks.table import (
    Z_TOL,
    auc,
    mean_ratio_row,
    offenders_row,
    row,
    share_row,
    side_row,
    sum_row,
    violations_row,
)
from synthetic.spec.products import HOLDING_RULES, PRODUCTS
from synthetic.truth.oracle import window_probability

KEYS = ["client_id", "snapshot_month"]
LOANS = [key for key, p in PRODUCTS.items() if p["kind"] == "loans"]
SLOTS = range(1, HOLDING_RULES["max_loan_accounts"] + 1)  # loan slots in the oracle
REGRESSION_TARGET = next(t for t, s in STANDARD_TARGETS.items() if s["event"] == "sum")
REGRESSION_WINDOW = 3
QUANTILES = ("mean", "q10", "q50", "q90")
MART_COLUMNS = [
    *KEYS,
    "segment",
    # What window_probability reads beyond the targets' columns: profile, tenure, status at t.
    "subsegment",
    "relationship_days",
    *[f"{key}_status" for key, p in PRODUCTS.items() if p.get("status")],
    *sorted({c for t in STANDARD_TARGETS.values() for c in (t["column"], *t["eligible"])}),
]
ORACLE_COLUMNS = [
    *KEYS,
    *[f"score_{key}" for key, p in PRODUCTS.items() if p["kind"] != "static"],
    # The chains' steady share after a fresh adoption of the product they require.
    *["lapse_digital", "lapse_cc_activity", "p_ebanking_acquire", "p_cc_acquire"],
    *[f"{key}_remaining_{i}" for key in LOANS for i in SLOTS],
    *[f"{REGRESSION_TARGET}_{q}" for q in QUANTILES],
]

WINDOWS = (1, 3, 6)
DECILE_WINDOW = 3  # deciles, segments and statuses for this window; the others overall only
DECILES = 10
TRUTH_MATCH = 1e-9  # what the checks recompute equals truth's, AUCs and sizing
SIZING_MONTHS, SIZING_EVENTS = 6, 200  # expected events in 6 observation months; < 200: low
REGRESSION_MONTHS = (2, 3, 9, 14, 15, 21)  # panel months (1 = the first); 2 and 14: Novembers
N_PATHS = 200  # the regression oracle's simulated paths (spec)

# Truth layout read here (keys are strings, as truth.json stores them); the generator must match:
#   truth[key] for key in REQUIRED_TRUTH_KEYS;
#   truth["columns"]: [{name, type, kind}], one per mart column, kind in SCHEMA_KINDS;
#   truth["spec"]["traps"]: [{column, product, target, kind, trap_column, parameters, expected}];
#   truth["oracle"][target]: {expected_events_6m, low_confidence, w1, w3, w6} per binary target;
#     truth["oracle"][target][f"w{w}"]: {auc, auc_by_segment: {segment: auc},
#     positive_rows_per_month}; `auc` is the Mann–Whitney AUC (ties count one half) of
#     window_probability against the realised target over every mart row where both are
#     non-null, all months together; `auc_by_segment` the same within each `segment` (null
#     where a class is empty).
REQUIRED_TRUTH_KEYS = (
    *("generator_version", "versions", "seed", "preset", "n_clients", "n_months", "first_month"),
    *("spec", "calibration", "market_index", "columns", "oracle"),
)
TARGET_KEYS = ("expected_events_6m", "low_confidence")  # a missing window raises on reading
METRIC_KEYS = ("auc", "auc_by_segment", "positive_rows_per_month")
SCHEMA_FIELDS = ("name", "type", "kind")
SCHEMA_KINDS = (
    *("id", "time", "static", "holding", "stock", "flow", "count", "rollup", "categorical"),
    *("trap", "noise"),
)


def check_oracle(mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict) -> pd.DataFrame:
    """Window probabilities against realised targets, truth's AUCs and sizing, the regression
    oracle and the truth schema. (The leak columns beat the oracle: the trap family's rows.)"""
    if not mart[KEYS].reset_index(drop=True).equals(oracle[KEYS].reset_index(drop=True)):
        raise ValueError("oracle rows must line up with mart rows")
    months = sorted(mart["snapshot_month"].unique())
    rows = []
    for target in BINARY_TARGETS:
        for w in WINDOWS:
            rows += _check_target(mart, oracle, truth, target, w, months)
    rows += _check_regression(mart, oracle, months)
    rows += _check_truth_schema(truth)
    return pd.DataFrame(rows)


def _target_metrics(truth: dict, target: str, w: int) -> dict:
    """Truth's oracle metrics for one target and window (layout above)."""
    return truth["oracle"][target][f"w{w}"]


def _check_target(
    mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict, target: str, w: int, months: list
) -> list[dict]:
    """One target and window: nulls agree, AUCs equal truth's, events match the probabilities, and
    (w = 1) truth's sizing is 6 × the mean monthly sum of the probabilities."""
    realised = realised_target(mart, target, w).to_numpy(dtype=float, na_value=np.nan)
    chance = window_probability(mart, oracle, truth, target, w)
    chance = chance.to_numpy(dtype=float, na_value=np.nan)
    name = f"{target} w{w}"
    mismatch = np.isnan(realised) != np.isnan(chance)
    rows = [violations_row(f"{name}: probability null iff target null", pd.Series(mismatch))]
    judged = ~np.isnan(realised) & ~np.isnan(chance)
    rows += _auc_rows(name, mart, _target_metrics(truth, target, w), w, realised, chance, judged)
    sample = judged & mart["snapshot_month"].isin(months[w - 1 :: w]).to_numpy()
    rows += _calibration_rows(name, mart, target, w, realised[sample], chance[sample], sample)
    if w == 1:  # one month ahead a positive row is one event: the sizing counts events
        rows += _sizing_rows(target, truth["oracle"][target], mart, chance, judged)
    return rows


def _auc_or_nan(scores: np.ndarray, labels: np.ndarray) -> float:
    """The AUC, or NaN when one class is empty."""
    positives = int(np.sum(labels == 1))
    return np.nan if positives in (0, len(labels)) else auc(scores, labels)


def _auc_rows(
    name: str,
    mart: pd.DataFrame,
    metrics: dict,
    w: int,
    realised: np.ndarray,
    chance: np.ndarray,
    judged: np.ndarray,
) -> list[dict]:
    """The AUC computed here equals truth's to 1e-9: pooled, and per segment for w = 3.

    Both undefined (one class empty) counts as agreement.
    """
    strata = {"all": (judged, metrics["auc"])}
    if w == DECILE_WINDOW:
        segment = mart["segment"].to_numpy()
        for seg in np.unique(segment[judged]):
            strata[seg] = (judged & (segment == seg), metrics["auc_by_segment"][seg])
    rows = []
    for stratum, (part, expected) in strata.items():
        expected = np.nan if expected is None else float(expected)
        mine = _auc_or_nan(chance[part], realised[part])
        out = row(
            f"{name}: AUC equals truth's",
            stratum,
            part.sum(),
            expected,
            mine,
            TRUTH_MATCH,
            rule=True,
        )
        rows.append({**out, "passed": out["passed"] or bool(np.isnan(expected) and np.isnan(mine))})
    return rows


def _calibration_rows(
    name: str,
    mart: pd.DataFrame,
    target: str,
    w: int,
    realised: np.ndarray,
    chance: np.ndarray,
    sample: np.ndarray,
) -> list[dict]:
    """Events against Σ probability on the sample of non-overlapping windows: overall; for w = 3
    also per probability decile and, for a status product, per status at the observation month."""
    check = f"{name}: events vs Σ window probability"
    if not sample.any():  # a target nobody is eligible for: fail, don't pass vacuously
        return [row(check, "no rows to judge", 0, np.nan, np.nan, np.nan)]
    rows = [sum_row(check, "all", chance, realised)]
    if w != DECILE_WINDOW:
        return rows
    decile = pd.qcut(chance, DECILES, labels=False, duplicates="drop")
    for b in range(int(decile.max()) + 1):
        part = decile == b
        rows.append(sum_row(check, f"probability decile {b + 1}", chance[part], realised[part]))
    status = f"{target.removesuffix('_acquire')}_status"
    if target.endswith("_acquire") and status in mart.columns:
        at_t = mart[status].to_numpy()[sample]
        for value in ("never", "churned"):
            part = at_t == value
            rows.append(sum_row(check, f"{status} {value}", chance[part], realised[part]))
    return rows


def _sizing_rows(
    target: str, sizing: dict, mart: pd.DataFrame, chance: np.ndarray, judged: np.ndarray
) -> list[dict]:
    """Truth's expected events in 6 observation months equal 6 × the mean monthly sum of the
    one-month window probability (to 1e-9 relative), and its low-confidence flag their test."""
    month = mart["snapshot_month"].to_numpy()[judged]
    expected = SIZING_MONTHS * pd.Series(chance[judged]).groupby(month).sum().mean()
    flag = bool(expected < SIZING_EVENTS)
    stated = sizing["expected_events_6m"]
    return [
        row(f"{target}: expected events in 6 months equal truth's", "w=1", judged.sum(),
            stated, expected, TRUTH_MATCH * stated, rule=True),
        row(f"{target}: low-confidence flag equals truth's", "w=1", judged.sum(),
            float(sizing["low_confidence"]), float(flag), 0, rule=True),
    ]  # fmt: skip


def _expected_coverage(q: float) -> float:
    """E[F(q̂)] for `np.quantile` (linear) of N_PATHS draws: (q·(N − 1) + 1) / (N + 1), since
    E[F(X_(k))] = k / (N + 1); 0.1040 for q10, 0.5 for q50, 0.8960 for q90."""
    return (q * (N_PATHS - 1) + 1) / (N_PATHS + 1)


def _check_regression(mart: pd.DataFrame, oracle: pd.DataFrame, months: list) -> list[dict]:
    """Realised next-3-month card spend against the oracle's quantiles and mean, per observation
    month (2, 3, 9, 14, 15, 21), and the ratio of means per predicted-mean decile, months
    pooled."""
    realised = realised_target(mart, REGRESSION_TARGET, REGRESSION_WINDOW)
    realised = realised.to_numpy(dtype=float, na_value=np.nan)
    pred = {
        q: oracle[f"{REGRESSION_TARGET}_{q}"].to_numpy(dtype=float, na_value=np.nan)
        for q in QUANTILES
    }
    fits = [months[k - 1] for k in REGRESSION_MONTHS if k + REGRESSION_WINDOW <= len(months)]
    judged = ~np.isnan(realised) & ~np.isnan(pred["mean"])
    rows = []
    for month in fits:
        part = judged & (mart["snapshot_month"] == month).to_numpy()
        stratum = f"observation {month:%Y-%m}"
        rows += _coverage_rows(stratum, realised[part], {q: v[part] for q, v in pred.items()})
    pooled = judged & mart["snapshot_month"].isin(fits).to_numpy()
    decile = pd.qcut(pred["mean"][pooled], DECILES, labels=False, duplicates="drop")
    check = f"{REGRESSION_TARGET}: realised / predicted mean"
    for b in range(int(decile.max()) + 1):
        part = decile == b
        num, den = realised[pooled][part], pred["mean"][pooled][part]
        rows.append(mean_ratio_row(check, f"predicted-mean decile {b + 1}", num, den, 1.0, True))
    return rows


def _coverage_rows(stratum: str, realised: np.ndarray, pred: dict[str, np.ndarray]) -> list[dict]:
    """One observation month: P(realised < q10) and P(realised ≤ q90) one-sided (safe with the zero
    spend atom), P(realised < q10) where q10 > 0 two-sided (no atom below a positive q10),
    P(realised ≤ q50) where q50 > 0 (a zero median is the atom, not a median of the continuous
    part), and the ratio of means."""
    n, name = len(realised), REGRESSION_TARGET
    low, high = _expected_coverage(0.1), _expected_coverage(0.9)
    low_bound = low + Z_TOL * np.sqrt(low * (1 - low) / n)
    high_bound = high - Z_TOL * np.sqrt(high * (1 - high) / n)
    below_low = float(np.mean(realised < pred["q10"]))
    within_high = float(np.mean(realised <= pred["q90"]))
    positive = pred["q50"] > 0
    hits = int(np.sum(realised[positive] <= pred["q50"][positive]))
    low_positive = pred["q10"] > 0
    below = int(np.sum(realised[low_positive] < pred["q10"][low_positive]))
    ratio = f"{name}: realised / predicted mean"
    return [
        side_row(f"{name}: P(realised < q10)", stratum, n, low_bound, below_low, above=False),
        share_row(f"{name}: P(realised < q10), q10 > 0", stratum, low, below, low_positive.sum()),
        share_row(f"{name}: P(realised ≤ q50), q50 > 0", stratum, 0.5, hits, positive.sum()),
        side_row(f"{name}: P(realised ≤ q90)", stratum, n, high_bound, within_high),
        mean_ratio_row(ratio, stratum, realised, pred["mean"], 1.0, paired=True),
    ]


def _check_truth_schema(truth: dict) -> list[dict]:
    """truth.json holds the required keys, metrics for every binary target and window, a complete
    schema entry for every mart column, a record for every trap column, and AUCs in [0.5, 1]
    (pooled: a rule; per segment: at the canonical size)."""
    columns = snapshot_columns()
    trap_columns = [c for c in columns if "_trap_" in c]
    schema = {entry["name"]: entry for entry in truth["columns"]}
    traps = {record["column"] for record in truth["spec"]["traps"]}
    metrics = {f"{t} w{w}": _target_metrics(truth, t, w) for t in BINARY_TARGETS for w in WINDOWS}
    aucs = {pair: m["auc"] for pair, m in metrics.items()}
    by_segment = {
        f"{pair} {segment}": value
        for pair, m in metrics.items()
        for segment, value in m["auc_by_segment"].items()
    }
    incomplete = [
        name
        for name, entry in schema.items()
        if any(f not in entry for f in SCHEMA_FIELDS) or entry["kind"] not in SCHEMA_KINDS
    ]
    no_key = [k for k in REQUIRED_TRUTH_KEYS if k not in truth]
    no_metric = [f"{p}: {k}" for p, m in metrics.items() for k in METRIC_KEYS if k not in m]
    no_metric += [
        f"{t}: {k}" for t in BINARY_TARGETS for k in TARGET_KEYS if k not in truth["oracle"][t]
    ]
    no_schema = [c for c in columns if c not in schema]
    no_trap = [c for c in trap_columns if c not in traps]
    off_range = [k for k, v in aucs.items() if v is not None and not 0.5 <= v <= 1]
    off_segment = [k for k, v in by_segment.items() if v is not None and not 0.5 <= v <= 1]
    n_metrics = len(metrics) * len(METRIC_KEYS) + len(BINARY_TARGETS) * len(TARGET_KEYS)
    return [
        offenders_row("truth: required keys", no_key, len(REQUIRED_TRUTH_KEYS)),
        offenders_row("truth: every metric per target and window", no_metric, n_metrics),
        offenders_row("truth: a schema entry per mart column", no_schema, len(columns)),
        offenders_row("truth: schema entries complete, kinds the spec's", incomplete, len(schema)),
        offenders_row("truth: a trap record per trap column", no_trap, len(trap_columns)),
        offenders_row("truth: pooled oracle AUCs in [0.5, 1]", off_range, len(aucs)),
        # Not a rule: in a small segment (Private in the 5k preset) an AUC can dip below 0.5.
        offenders_row(
            "truth: oracle AUCs per segment in [0.5, 1]", off_segment, len(by_segment), rule=False
        ),
    ]
