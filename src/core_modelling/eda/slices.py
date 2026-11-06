"""The decision view's data: what one key feature achieves at the evaluation slices
(docs/components/eda.md, "At the decision's slices").

A list built from one feature alone on the snapshot period's labelled cells (one row per
client), cut at the slices, shares of those rows (`slice_shares`: `decision.n` first for a
`top_n` decision, then the resolved `evaluation.slices`, V55; `skipped_slices` names the counts
above the rows). The list order is the rule a person could apply, the null bin last (V56): a
numeric by value in the raw sign of its snapshot concordance (`ordered_numeric_bins`); a
categorical per client fold by the level encoding fitted on the other folds
(`ordered_categorical_bins`), since an order fitted on the same clients' other periods flatters
a null code as it did the concordance (D-135). `capture_table` cuts each fold's cumulative
counts at a slice's share, linearly inside the boundary bin (V57), sums them over the folds and
gives the estimate with its interval (the task's `period_estimate`), the lift and the capture,
the share of `sum_y` (the positives, or the amount); `capture_curve` gives the capture on
`SLICE_GRID`; `slice_tables` stacks both over the key features.

The view is in sample and descriptive: the key features and a numeric's direction are read on
these rows, and the interval treats the order as fixed. It never sets a baseline (those are
`decision.baselines`) or a metric (§4.3). A list or a capture that cannot exist is decided
before computing and named in `unavailable` (D-035). Pure pandas and numpy.
"""

import numpy as np
import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.eda.deep_dives import MIN_BIN_SUPPORT
from core_modelling.statistics.cells import pool_periods, support_by_bin
from core_modelling.statistics.concordance import encode_levels
from core_modelling.tasks import TASK_SPECS

SLICE_GRID = np.arange(1, 101) / 100  # the curve's shares of rows, 1% … 100%
RANDOM = "random"  # the curve's diagonal group: a random list captures its share
SLICE_COLUMNS = ["feature", "slice", "share", "rows", "support", "estimate", "low", "high", "lift",
                 "capture", "insufficient", "unavailable"]  # fmt: skip
CURVE_COLUMNS = ["feature", "share", "capture"]
SUMMED = ["n", "sum_y", "sum_y2", "support"]
NO_BASE = "not available: capture and lift need a positive base"
SIGNED = "not available: capture needs a target that is never negative"


def _slice_counts(resolved: UseCaseConfig) -> tuple[dict[str, int], dict[str, int]]:
    """The configured counts by label: the decision's (`decision n = …`, a `top_n` decision
    only) and `evaluation.slices.top_n`'s (`n = …`, a count equal to the decision's left out)."""
    decision_n = resolved.decision.n if resolved.decision.type == "top_n" else None
    decision = {f"decision n = {decision_n:,}": decision_n} if decision_n else {}
    listed = {f"n = {n:,}": n for n in resolved.evaluation.slices.top_n if n != decision_n}
    return decision, listed


def skipped_slices(resolved: UseCaseConfig, rows: int) -> list[str]:
    """The labels of the configured counts above the snapshot's `rows` labelled rows: the
    slices `slice_shares` leaves out, for the caption (the crunch's rule)."""
    decision, listed = _slice_counts(resolved)
    return [label for label, n in {**decision, **listed}.items() if n > rows]


def slice_shares(resolved: UseCaseConfig, rows: int) -> dict[str, float]:
    """The slices as shares of the snapshot's `rows` labelled rows, by label: `decision n = …`
    first for a `top_n` decision, then `evaluation.slices.top_pct` (`top 1%`) and `top_n`
    (`n = …`), the `skipped_slices` left out."""
    if rows <= 0:
        raise ValueError(f"slice_shares: the snapshot needs labelled rows, got {rows}")
    decision, listed = _slice_counts(resolved)
    skipped = skipped_slices(resolved, rows)
    shares = {label: n / rows for label, n in decision.items() if label not in skipped}
    shares.update({f"top {pct * 100:g}%": pct for pct in resolved.evaluation.slices.top_pct})
    shares.update({label: n / rows for label, n in listed.items() if label not in skipped})
    return shares


def _snapshot_bins(cells: pd.DataFrame, snapshot: str) -> pd.DataFrame:
    """The snapshot's bins holding labelled rows: `bin`, `bin_order`, `is_null` and `SUMMED`,
    pooled over the target bins."""
    pooled = pool_periods(cells, [snapshot])
    labelled = pooled.loc[pooled["target_bin"].notna()]
    keys = ["bin", "bin_order", "is_null"]
    per_bin = labelled.groupby(keys, as_index=False)[["n", "sum_y", "sum_y2"]].sum()
    per_bin["support"] = per_bin["bin"].map(support_by_bin(pooled))
    return per_bin.loc[per_bin["n"] > 0]


def _in_list_order(bins: pd.DataFrame) -> pd.DataFrame:
    """`fold`, `bin` and `SUMMED` of the bins, each fold by `key` ascending, the null bin last."""
    ordered = bins.sort_values(["fold", "is_null", "key", "bin_order"])
    return ordered[["fold", "bin", *SUMMED]].reset_index(drop=True)


def ordered_numeric_bins(cells: pd.DataFrame, sign: int, snapshot: str) -> pd.DataFrame:
    """A numeric's snapshot bins in list order as one fold (`fold` 0): by value, highest first
    for `sign` +1 and lowest for −1, the null bin last."""
    if sign not in (1, -1):
        raise ValueError(f"ordered_numeric_bins: sign must be +1 or -1, got {sign}")
    bins = _snapshot_bins(cells, snapshot)
    return _in_list_order(bins.assign(fold=0, key=-sign * bins["bin_order"]))


def ordered_categorical_bins(
    cells: pd.DataFrame, snapshot: str, window: list[str], min_events: int, task: str
) -> pd.DataFrame:
    """A categorical's snapshot bins in list order per client fold: its levels by
    `encode_levels` fitted on the other folds' cells over `window`, its prior the task's
    `shrinkage_rows(min_events, …)` at those folds' base (`encoding_prior_rows`' rule), highest
    first, a level unseen there at their base (as in `cross_fitted_concordance`); the null bin
    last. No client's label informs its own fold's order (D-135)."""
    in_window = cells.loc[cells["period"].isin(window)]
    if snapshot not in window or "fold" not in cells or in_window["fold"].isna().any():
        raise ValueError(
            "ordered_categorical_bins: needs the snapshot inside `window` and a client fold on "
            "every window cell (a categorical's counts-table cells)"
        )
    parts = []
    for fold in sorted(in_window.loc[in_window["period"] == snapshot, "fold"].unique()):
        held_out = in_window["fold"] == fold
        fit = pool_periods(in_window.loc[~held_out], window)
        labelled = fit.loc[fit["target_bin"].notna()]
        prior_rows = TASK_SPECS[task]["shrinkage_rows"](
            min_events, labelled["sum_y"].sum() / labelled["n"].sum()
        )
        values = labelled.loc[~labelled["is_null"]]
        base = values["sum_y"].sum() / values["n"].sum()
        bins = _snapshot_bins(in_window.loc[held_out], snapshot)
        score = bins["bin"].map(encode_levels(fit, prior_rows)).fillna(base)
        parts.append(bins.assign(fold=fold, key=-score))
    return _in_list_order(pd.concat(parts, ignore_index=True))


def _cumulative(fold: pd.DataFrame) -> pd.DataFrame:
    """One fold's running sums of `SUMMED` in list order, from a leading row of zeros."""
    sums = fold[SUMMED].astype(float).cumsum()
    return pd.concat([pd.DataFrame(0.0, index=[0], columns=SUMMED), sums], ignore_index=True)


def _counts_at(ordered: pd.DataFrame, share: np.ndarray) -> dict[str, np.ndarray]:
    """`SUMMED` but `n` at `share` of each fold's rows, linear inside the boundary bin, summed
    over the folds: each fold's list has its own order, so each is cut on its own."""
    at = {name: np.zeros(share.size) for name in SUMMED[1:]}
    for _, fold in ordered.groupby("fold"):
        cum = _cumulative(fold)
        for name in at:
            at[name] += np.interp(share * cum["n"].iloc[-1], cum["n"], cum[name])
    return at


def _captured(sum_y: np.ndarray, ordered: pd.DataFrame) -> np.ndarray:
    """`sum_y` as a share of the bins' total; refused on a total that is not positive (decide
    it up front: `_capture_unavailable`)."""
    total = ordered["sum_y"].sum()
    if not total > 0:
        raise ValueError(f"capture: the total target {total} is not positive")
    return sum_y / total


def capture_table(
    ordered: pd.DataFrame, shares: dict[str, float], base: float, task: str, reason: str
) -> pd.DataFrame:
    """One row per slice (`SLICE_COLUMNS` but `feature`): the counts at its share (`_counts_at`);
    the task's estimate with its interval; `lift` over `base` when `lift_available(base)`;
    `capture`, NaN with `reason` in `unavailable` when the run has one (`_capture_unavailable`);
    `insufficient` below `MIN_BIN_SUPPORT` support."""
    spec = TASK_SPECS[task]
    share = np.array(list(shares.values()), dtype=float)
    rows, at = share * ordered["n"].sum(), _counts_at(ordered, share)
    support = np.minimum(at["support"], rows)  # interpolation can round an ulp above the rows
    estimate = spec["period_estimate"](rows, support, at["sum_y"], at["sum_y2"])
    nan = np.full(share.size, np.nan)
    return pd.DataFrame({
        "slice": list(shares), "share": share, "rows": rows, "support": support,
        **{name: estimate[name] for name in ("estimate", "low", "high")},
        "lift": estimate["estimate"] / base if spec["lift_available"](base) else nan,
        "capture": nan if reason else _captured(at["sum_y"], ordered),
        "insufficient": support < MIN_BIN_SUPPORT, "unavailable": reason,
    })  # fmt: skip


def capture_curve(ordered: pd.DataFrame, grid: np.ndarray) -> pd.DataFrame:
    """The capture at each share of `grid` (`share`, `capture`), cut as in `capture_table`;
    only for a run without a `_capture_unavailable` reason."""
    captured = _captured(_counts_at(ordered, grid)["sum_y"], ordered)
    return pd.DataFrame({"share": grid, "capture": captured})


def _capture_unavailable(labelled: pd.DataFrame, base: float, task: str) -> str:
    """Why no capture exists, decided once from the snapshot's labelled cells: no positive base
    (`NO_BASE`), or a target bin summing below 0 (`SIGNED`: an amount that can be negative has
    no share to capture, lift stays); '' when it can."""
    if not TASK_SPECS[task]["lift_available"](base):
        return NO_BASE
    if (labelled.groupby("target_bin")["sum_y"].sum() < 0).any():
        return SIGNED
    return ""


def slice_tables(
    cells: pd.DataFrame,
    ranking: pd.DataFrame,
    meta: dict,
    resolved: UseCaseConfig,
    window: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The key features' `slices` (`SLICE_COLUMNS`; a feature without a snapshot concordance,
    `raw_sign` 0, one row with the ranking's `unavailable`) and `capture_curve` (`CURVE_COLUMNS`,
    plus the `RANDOM` diagonal) in rank order, from the counts table's cells, the ranking with
    its key features, `meta`'s `snapshot_period`, `snapshot_base` and `slices` (the shares,
    `slice_shares`), and the window periods' labels (the ranking's); both keep their columns
    when empty."""
    keys = ranking.loc[ranking["key_feature"] != ""].sort_values("rank")
    if keys.empty:
        return _stack([], SLICE_COLUMNS), _stack([], CURVE_COLUMNS)
    snapshot, base, task = meta["snapshot_period"], meta["snapshot_base"], resolved.task
    current = cells.loc[~cells["lagged"] & cells["feature"].isin(keys["feature"])]
    one = current.loc[current["feature"] == keys["feature"].iloc[0]]  # each covers every row
    labelled = pool_periods(one, [snapshot]).dropna(subset=["target_bin"])
    shares, reason = meta["slices"], _capture_unavailable(labelled, base, task)
    slices, curves = [], []
    for _, key in keys.iterrows():
        name, own = key["feature"], current.loc[current["feature"] == key["feature"]]
        if key["raw_sign"] == 0:  # no snapshot concordance: no direction, no list
            slices.append(pd.DataFrame({"feature": [name], "insufficient": [False],
                                        "unavailable": [key["unavailable"]]}))  # fmt: skip
            continue
        if key["kind"] == "categorical":
            min_events = resolved.strata.min_events
            ordered = ordered_categorical_bins(own, snapshot, window, min_events, task)
        else:
            ordered = ordered_numeric_bins(own, int(key["raw_sign"]), snapshot)
        slices.append(capture_table(ordered, shares, base, task, reason).assign(feature=name))
        if not reason:
            curves.append(capture_curve(ordered, SLICE_GRID).assign(feature=name))
    if curves:
        curves.append(pd.DataFrame({"feature": RANDOM, "share": SLICE_GRID, "capture": SLICE_GRID}))
    return _stack(slices, SLICE_COLUMNS), _stack(curves, CURVE_COLUMNS)


def _stack(parts: list[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
    """The parts stacked with `columns` in order, or an empty frame with them."""
    if not parts:
        return pd.DataFrame(columns=columns)
    return pd.concat(parts, ignore_index=True)[columns]
