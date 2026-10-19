"""The oracle's ground truth on demand: the standard targets, their realised values, the true
window probabilities and the oracle's metrics (D-066, D-068; test_harness.md, "Ground truth and
oracle").

A standard target is an event in the mart over the `w` months after an observation month t
(`STANDARD_TARGETS`): a 0/1 product acquired (its flag is 1 in any month of the window, for a
non-holder at t), a loan opened (its count rises in any month), a usage chain activated (its flag
is 1 in any month, for a client dormant at t who holds the product it requires), or next-3-month
card spend (a sum). A target is null where the client isn't eligible at t, leaves before t+w, or
the window runs past the panel.

`window_probability` prices exactly these events with the client's state frozen at t, on its
realised trait path: for each month s of the window, the chance from the profile intercept
(truth's calibration) plus the oracle's `score_<product>` at s, with the churned odds of a status
product, onboarding by tenure, loan slots and maturities as scheduled at t (a maturity in month s
hides an opening), and for a chain the steady active share in t+1 if the required product was
gained at t; a chain whose required product can be given up also needs it kept, month by month.
The probability of any event is built month by month from the chance of none before; it slightly
under-predicts (`_any_event`). `oracle_metrics` gives truth.json, per binary target, the expected
events in 6 observation months (sizing) and, per window, the AUC of the window probability against
the realised target, pooled and per segment.

Rows sit on a clients × months grid (`month_grid`, `ahead`), so a row reads its own client's later
months whatever order the mart rows come in; the oracle's rows are matched to them by key
(`oracle_rows`).
"""

import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import rankdata

from synthetic.spec.products import HOLDING_RULES, PRODUCTS

KEYS = ["client_id", "snapshot_month"]
WINDOWS = (1, 3, 6)
SIZING_MONTHS, SIZING_EVENTS = 6, 200  # ≳ 200 events in 6 observation months, else low confidence
SLOTS = range(1, HOLDING_RULES["max_loan_accounts"] + 1)
# Usage targets by name (test_harness.md) → the chain they read.
CHAIN_TARGETS = {
    "fx_activate": "fx",
    "digital_activate": "digital",
    "cc_activate": "cc_activity",
    "casa_reactivate": "casa_activity",
}


def _chain_target(key: str) -> dict:
    """A usage chain's activation: its flag at 0 (dormant), the required product's at 1."""
    product = PRODUCTS[key]
    flag = product.get("flag", f"{key}_active_flag")
    eligible = {f"{product['requires']}_flag": 1} if "requires" in product else {}
    return dict(kind="activate", product=key, column=flag, eligible={**eligible, flag: 0})


# Name → kind, product, the mart column the event is read from, eligibility at t (column → value).
STANDARD_TARGETS = {
    **{
        f"{key}_acquire": dict(
            kind="acquire", product=key, column=f"{key}_flag", eligible={f"{key}_flag": 0}
        )
        for key, p in PRODUCTS.items()
        if p["kind"] == "holding"
    },
    **{
        f"{key}_open": dict(kind="open", product=key, column=f"{key}_cnt", eligible={})
        for key, p in PRODUCTS.items()
        if p["kind"] == "loans"
    },
    **{name: _chain_target(key) for name, key in CHAIN_TARGETS.items()},
    "spend_cc_next_3_months": dict(
        kind="regression", product="cc", column="spend_cc_vol", eligible={"cc_flag": 1}
    ),
}
BINARY_TARGETS = [name for name, t in STANDARD_TARGETS.items() if t["kind"] != "regression"]


def target_columns(target: str) -> tuple[list[str], list[str]]:
    """The mart and oracle columns a binary target's realised value, window probability and
    metrics read (`output.write_mart` reads only these back, one target at a time)."""
    spec = STANDARD_TARGETS[target]
    key = spec["product"]
    # The segment (metrics), the profile (intercept) and tenure (onboarding) besides the event.
    mart = [*KEYS, "segment", "subsegment", "relationship_days", spec["column"], *spec["eligible"]]
    oracle = [*KEYS, f"score_{key}"]
    if PRODUCTS[key].get("status"):
        mart.append(f"{key}_status")
    if spec["kind"] == "open":
        oracle += [f"{key}_remaining_{s}" for s in SLOTS]
    required = PRODUCTS[key].get("requires")
    if spec["kind"] == "activate" and required and PRODUCTS[required]["kind"] != "static":
        oracle += [f"lapse_{key}", f"p_{required}_acquire"]
    return list(dict.fromkeys(mart)), oracle


def realised_target(mart: pd.DataFrame, target: str, w: int) -> pd.Series:
    """The realised `target` over the `w` months after each row's month, aligned with `mart`:
    0/1 (the sum, for regression), null where not eligible, the client left or the window runs
    past the panel."""
    return _realised(mart, month_grid(mart), target, w)


def window_probability(
    mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict, target: str, w: int
) -> pd.Series:
    """The true chance of the binary `target`'s event within `w` months of each row's month (the
    module docstring), aligned with `mart`; null exactly where the realised target is."""
    _check_spec(truth)
    grid = month_grid(mart)
    return _window_probability(mart, oracle, oracle_rows(oracle, grid), grid, truth, target, w)


def oracle_metrics(mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict) -> dict:
    """Per binary target: `expected_events_6m` (6 × the mean monthly Σ of the w = 1 probability:
    one month ahead a positive row is one event), `low_confidence` (fewer than 200 of them), and
    per window (`w1`, `w3`, `w6`) the oracle's AUC pooled and per segment and the realised
    positive rows per observation month (a w-month window sees one event in up to w rows).

    AUC: Mann–Whitney (ties count one half) of the window probability against the realised target
    over every row where both are set, all months pooled; null where a class is empty.
    """
    return {target: target_metrics(mart, oracle, truth, target) for target in BINARY_TARGETS}


def target_metrics(mart: pd.DataFrame, oracle: pd.DataFrame, truth: dict, target: str) -> dict:
    """One binary target's metrics (`oracle_metrics`)."""
    _check_spec(truth)
    grid = month_grid(mart)
    rows_of = oracle_rows(oracle, grid)
    segment, month = mart["segment"].to_numpy(), grid["month"]
    out = {}
    for w in WINDOWS:
        realised = _realised(mart, grid, target, w).to_numpy()
        chance = _window_probability(mart, oracle, rows_of, grid, truth, target, w).to_numpy()
        both = ~np.isnan(realised) & ~np.isnan(chance)
        out[f"w{w}"] = _metrics(realised, chance, both, segment, month)
        if w == 1:  # sizing counts events (two loan openings in one month count once)
            months = np.unique(month[both])
            expected = np.bincount(month[both], weights=chance[both])[months]
            events = SIZING_MONTHS * expected.mean() if len(months) else 0.0
    sizing = {"expected_events_6m": float(events), "low_confidence": bool(events < SIZING_EVENTS)}
    return sizing | out


def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """The Mann–Whitney AUC of `scores` for 0/1 `labels`, ties counting one half; NaN when a
    class is empty."""
    positive = np.asarray(labels) == 1
    n_pos, n_neg = int(positive.sum()), int((~positive).sum())
    if n_pos == 0 or n_neg == 0:
        return np.nan
    ranks = rankdata(np.asarray(scores, dtype=float))
    return float((ranks[positive].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def _metrics(
    realised: np.ndarray,
    chance: np.ndarray,
    both: np.ndarray,
    segment: np.ndarray,
    month: np.ndarray,
) -> dict:
    """One target and window's AUCs and realised positive rows per month (`oracle_metrics`)."""
    months = np.unique(month[both])
    positives = np.bincount(month[both], weights=realised[both])[months]
    return {
        "auc": auc(chance[both], realised[both]),
        "auc_by_segment": {
            str(s): auc(chance[both & (segment == s)], realised[both & (segment == s)])
            for s in np.unique(segment[both])
        },
        "positive_rows_per_month": float(positives.mean()) if len(months) else 0.0,
    }


def _realised(mart: pd.DataFrame, grid: dict, target: str, w: int) -> pd.Series:
    """`realised_target` on a laid-out mart (`month_grid`)."""
    spec = STANDARD_TARGETS[target]  # an unknown target raises KeyError
    values = ahead(grid, as_float(mart[spec["column"]]), range(w + 1))
    future = values[:, 1:]
    if spec["kind"] == "open":
        hit = (np.diff(values, axis=1) > 0).any(axis=1)
    elif spec["kind"] == "regression":
        hit = future.sum(axis=1)
    else:
        hit = (future == 1).any(axis=1)
    defined = _eligible(mart, spec) & stays(grid, w)
    return pd.Series(np.where(defined, hit, np.nan), index=mart.index, name=target)


def _window_probability(
    mart: pd.DataFrame,
    oracle: pd.DataFrame,
    rows_of: np.ndarray,
    grid: dict,
    truth: dict,
    target: str,
    w: int,
) -> pd.Series:
    """`window_probability` on a laid-out panel (`month_grid`; `rows_of`, the oracle row of each
    mart row)."""
    spec = STANDARD_TARGETS[target]
    if spec["kind"] == "regression":
        raise ValueError(f"{target} is a regression target: its oracle is the regression columns")
    key = spec["product"]
    rows = np.flatnonzero(_eligible(mart, spec) & stays(grid, w))
    profiles = {name: s["profile"] for name, s in truth["spec"]["subsegments"].items()}
    intercepts = mart["subsegment"].map(profiles).map(truth["calibration"][key]["intercept"])
    intercepts = as_float(intercepts)[rows]
    if np.isnan(intercepts).any():
        raise ValueError(f"{target}: rows whose subsegment or profile has no calibrated intercept")
    scores = ahead(grid, _column(oracle, rows_of, f"score_{key}"), range(1, w + 1))[rows]
    log_odds = intercepts[:, None] + scores
    if spec["kind"] == "acquire":
        chance, keep = _acquire_chances(mart, truth, key, rows, log_odds), 1.0
    elif spec["kind"] == "open":
        slots = [_column(oracle, rows_of, f"{key}_remaining_{s}")[rows] for s in SLOTS]
        chance, keep = _open_chances(np.column_stack(slots), log_odds), 1.0
    else:
        chance, keep = _activate_chances(oracle, rows_of, grid, truth, key, rows, log_odds)
    out = np.full(len(mart), np.nan)
    out[rows] = _any_event(chance, keep)
    return pd.Series(out, index=mart.index, name=target)


def _acquire_chances(
    mart: pd.DataFrame, truth: dict, key: str, rows: np.ndarray, log_odds: np.ndarray
) -> np.ndarray:
    """Monthly adoption chances of non-holders at t (rows × months): churned odds as at t, the
    onboarding chance while the client's months on book are within the onboarding months."""
    product, rules = truth["spec"]["products"][key], truth["spec"]["holding_rules"]
    if product.get("status"):
        churned = mart[f"{key}_status"].to_numpy()[rows] == "churned"
        log_odds = log_odds + np.log(rules["churned_odds"]) * churned[:, None]
    chance = expit(log_odds)
    if not product.get("onboarding"):
        return chance
    months = rules["onboarding_months"]
    tenure = months_on_book(mart)[rows, None] + np.arange(1, log_odds.shape[1] + 1)
    steady = chance / (chance + truth["calibration"][key]["leave_chance"])
    return np.where(tenure <= months, 1 - (1 - steady) ** (1 / months), chance)


def _open_chances(remaining: np.ndarray, log_odds: np.ndarray) -> np.ndarray:
    """Monthly visible-opening chances (rows × months) from each slot's months left at t (0 =
    empty): a slot must be free in month s, and no account may mature in s (it hides the
    opening)."""
    months = np.arange(1, log_odds.shape[1] + 1)
    free = (remaining[:, :, None] <= months).any(axis=1)
    maturing = (remaining[:, :, None] == months).any(axis=1)
    return expit(log_odds) * (free & ~maturing)


def _activate_chances(
    oracle: pd.DataFrame,
    rows_of: np.ndarray,
    grid: dict,
    truth: dict,
    key: str,
    rows: np.ndarray,
    log_odds: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Monthly wake-up chances of clients dormant at t (rows × months), and the chance each month
    keeps the required product (1 where it can't be lost).

    A client who gained the required product at t (not held at t − 1: it had an adoption chance at
    t) wakes in t+1 with its steady active share, wake / (wake + lapse in t+1), as the generator
    does in the month after adoption.
    """
    products = truth["spec"]["products"]
    chance, required = expit(log_odds), products[key].get("requires")
    if not required or products[required]["kind"] == "static":
        return chance, 1.0
    gained = ~np.isnan(_column(oracle, rows_of, f"p_{required}_acquire")[rows])
    lapse = ahead(grid, _column(oracle, rows_of, f"lapse_{key}"), [1])[rows, 0]
    first = np.where(gained, chance[:, 0] / (chance[:, 0] + lapse), chance[:, 0])
    keep = 1 - truth["calibration"][required]["leave_chance"]
    return np.column_stack([first, chance[:, 1:]]), keep


def _any_event(chance: np.ndarray, keep: float) -> np.ndarray:
    """The chance of an event in some month of the window: an event in month s needs none
    before, the month's chance, and the required product kept (`keep`, 1 where nothing can be
    lost). With `keep` 1 this is 1 − Π(1 − chance).

    An approximation: losing and re-adopting the required product inside the window is ignored
    (the loss ends the window), as are hidden openings refilling a full set of 4 loan slots. Both
    make the oracle slightly under-predict, little for w ≤ 6.
    """
    no_event, hit = np.ones(len(chance)), np.zeros(len(chance))
    for s in range(chance.shape[1]):
        hit = hit + no_event * chance[:, s] * keep
        no_event = no_event * (1 - chance[:, s]) * keep
    return hit


def _check_spec(truth: dict) -> None:
    """Raise unless truth's products (keys, kinds, required products) and loan slots are this
    module's `PRODUCTS` and `HOLDING_RULES`."""
    # The targets, their eligibility and SLOTS come from the code's spec, the chances from
    # truth's: a dataset from another spec would be priced with the wrong targets.
    spec = truth["spec"]
    shapes = [
        {key: (p["kind"], p.get("requires")) for key, p in products.items()}
        for products in (spec["products"], PRODUCTS)
    ]
    slots = spec["holding_rules"]["max_loan_accounts"], HOLDING_RULES["max_loan_accounts"]
    if shapes[0] != shapes[1] or slots[0] != slots[1]:
        raise ValueError("truth's products or loan slots differ from the oracle's targets' spec")


def _eligible(mart: pd.DataFrame, spec: dict) -> np.ndarray:
    """Rows eligible for a target at their month: each eligibility column at its value."""
    eligible = np.ones(len(mart), dtype=bool)
    for column, value in spec["eligible"].items():
        eligible &= as_float(mart[column]) == value
    return eligible


def _column(oracle: pd.DataFrame, rows_of: np.ndarray, name: str) -> np.ndarray:
    """An oracle column as floats in the mart's row order (`oracle_rows`)."""
    return as_float(oracle[name])[rows_of]


def month_grid(mart: pd.DataFrame) -> dict:
    """Each mart row's client and month position (0 = the mart's first month), and the row
    holding each cell of the grid (−1 = none); raises on duplicate client-months."""
    client, ids = pd.factorize(mart["client_id"])
    number = month_numbers(mart["snapshot_month"])
    month = number - number.min()
    row_at = np.full((len(ids), int(month.max()) + 1), -1)
    row_at[client, month] = np.arange(len(mart))
    if (row_at >= 0).sum() != len(mart):
        raise ValueError("the mart has duplicate client-months")
    return {"client": client, "month": month, "ids": ids, "first": number.min(), "row_at": row_at}


def oracle_rows(oracle: pd.DataFrame, grid: dict) -> np.ndarray:
    """The oracle row of each mart row; raises unless both tables hold the same client-months."""
    client = pd.Index(grid["ids"]).get_indexer(oracle["client_id"])
    month = month_numbers(oracle["snapshot_month"]) - grid["first"]
    row_at = grid["row_at"]
    inside = (client >= 0) & (month >= 0) & (month < row_at.shape[1])
    mart_row = np.full(len(oracle), -1)
    mart_row[inside] = row_at[client[inside], month[inside]]
    n = len(grid["client"])
    if len(oracle) != n or (mart_row < 0).any() or np.unique(mart_row).size != n:
        raise ValueError("the oracle must hold exactly the mart's client-months")
    out = np.empty(n, dtype=int)
    out[mart_row] = np.arange(n)
    return out


def ahead(grid: dict, values: np.ndarray, offsets: range | list[int]) -> np.ndarray:
    """Rows × offsets: each row's client's `values` (aligned with the mart) that many months
    later (offsets ≥ 0); NaN where the client has no row then or the month is past the mart's."""
    row_at, values = grid["row_at"], np.asarray(values, dtype=float)
    out = np.full((len(grid["client"]), len(offsets)), np.nan)
    for j, offset in enumerate(offsets):  # one offset at a time keeps the temporaries small
        at = grid["month"] + offset
        inside = np.flatnonzero(at < row_at.shape[1])
        source = row_at[grid["client"][inside], at[inside]]
        found = source >= 0
        out[inside[found], j] = values[source[found]]
    return out


def stays(grid: dict, w: int) -> np.ndarray:
    """Rows whose client has a row in each of the `w` months after (inside the mart)."""
    present = ahead(grid, np.zeros(len(grid["client"])), range(1, w + 1))
    return ~np.isnan(present).any(axis=1)


def months_on_book(mart: pd.DataFrame) -> np.ndarray:
    """Monthly steps lived by the end of each row's month, the join month included, from
    `relationship_days` (counted to the month's last day, as `generate.month_rows` writes it)."""
    month = month_numbers(mart["snapshot_month"])
    month_end = (month + 1).astype("datetime64[M]").astype("datetime64[D]").astype(int) - 1
    days = mart["relationship_days"].to_numpy(dtype="int64")
    start = (month_end - days).astype("datetime64[D]")
    return month - start.astype("datetime64[M]").astype(int) + 1


def month_numbers(stamps: pd.Series) -> np.ndarray:
    """Months since 1970-01 of date values (each distinct month converted once)."""
    codes, months = pd.factorize(stamps)
    numbers = np.array([np.datetime64(month, "M").astype(int) for month in months])
    return numbers[codes]


def as_float(values: object) -> np.ndarray:
    """Values as a float array, missing values as NaN (nullable integers included)."""
    return pd.Series(values).to_numpy(dtype=float, na_value=np.nan)
