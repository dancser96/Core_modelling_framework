"""The decision view's data: what one key feature achieves at the evaluation slices
(docs/components/eda.md, "At the decision's slices").

A list built from one feature alone on the snapshot period's labelled cells (one row per
client), cut at the slices, shares of those rows (`slice_shares`: `decision.n` first for a
`top_n` decision, then the resolved `evaluation.slices`, V55; `skipped_slices` names the counts
above the rows). The list order is the rule a person could apply, the null bin last (V56): a
numeric by value in the raw sign of its snapshot concordance (`ordered_numeric_bins`); a
categorical per client fold by the level encoding fitted on the other folds, the concordance's
own (`ordered_categorical_bins`), since an order fitted on the same clients' other periods
flatters a null code as it did the concordance (D-135). The cut at the slices is
`statistics/capture.py`'s (`capture_table`, and `capture_curve` on `SLICE_GRID`); `slice_tables`
stacks both over the key features, a slice greyed below `MIN_BIN_SUPPORT` support.

The view is in sample and descriptive: the key features and a numeric's direction are read on
these rows, and the interval treats the order as fixed. It never sets a baseline (those are
`decision.baselines`) or a metric (§4.3). A list or a capture that cannot exist is decided
before computing and named in `unavailable` (D-035). Pure pandas and numpy.
"""

import numpy as np
import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.eda.deep_dives import MIN_BIN_SUPPORT
from core_modelling.eda.ranking import list_key_features
from core_modelling.statistics.capture import SUMMED, capture_curve, capture_table
from core_modelling.statistics.cells import pool_periods, population_cells, support_by_bin
from core_modelling.statistics.concordance import fold_encodings
from core_modelling.tasks import TASK_SPECS

SLICE_GRID = np.arange(1, 101) / 100  # the curve's shares of rows, 1% … 100%
RANDOM = "random"  # the curve's diagonal group: a random list captures its share
SLICE_COLUMNS = ["feature", "slice", "share", "rows", "support", "estimate", "low", "high", "lift",
                 "capture", "insufficient", "unavailable"]  # fmt: skip
CURVE_COLUMNS = ["feature", "share", "capture"]
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
    """One feature's snapshot-period bins that hold labelled rows, one row per bin (the cells'
    folds pooled): `bin, bin_order, is_null`, then `SUMMED`: `n, sum_y, sum_y2` summed over the
    labelled target bins and `support` from `support_by_bin`."""
    pooled = pool_periods(cells, [snapshot])
    labelled = pooled.loc[pooled["target_bin"].notna()]
    keys = ["bin", "bin_order", "is_null"]
    per_bin = labelled.groupby(keys, as_index=False)[["n", "sum_y", "sum_y2"]].sum()
    per_bin["support"] = per_bin["bin"].map(support_by_bin(pooled))
    return per_bin.loc[per_bin["n"] > 0]


def _in_list_order(bins: pd.DataFrame) -> pd.DataFrame:
    """The bins in list order, `fold, bin` and `SUMMED`: per fold, the non-null bins by `key`
    ascending (ties by `bin_order`), then the null bin."""
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
    cells: pd.DataFrame, snapshot: str, window: list[str], prior_rows: float
) -> pd.DataFrame:
    """A categorical's snapshot bins in list order per client fold: its levels by the encoding
    fitted on the other folds' cells over `window` with the run's `prior_rows`
    (`fold_encodings`, so the list follows the order the concordance read), highest first, a
    level unseen there at their base; the null bin last. No client's label informs its own
    fold's order but through the prior's weight, one number for the run (D-135)."""
    if snapshot not in window:
        raise ValueError(f"ordered_categorical_bins: the snapshot {snapshot} is not in `window`")
    in_window = cells.loc[cells["period"].isin(window)]
    encodings = fold_encodings(in_window, window, prior_rows)
    parts = []
    for fold in sorted(in_window.loc[in_window["period"] == snapshot, "fold"].unique()):
        encoding, base = encodings[fold]
        bins = _snapshot_bins(in_window.loc[in_window["fold"] == fold], snapshot)
        parts.append(bins.assign(fold=fold, key=-bins["bin"].map(encoding).fillna(base)))
    return _in_list_order(pd.concat(parts, ignore_index=True))


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
    prior_rows: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two stacked tables over the key features, in `list_key_features`' order; both keep their
    columns when empty:
    - `slices` (`SLICE_COLUMNS`): one row per key feature and slice of `meta["slices"]`,
      `insufficient` below `MIN_BIN_SUPPORT`; a feature without a snapshot concordance
      (`raw_sign` 0) gets one row with the ranking's `unavailable`;
    - `capture_curve` (`CURVE_COLUMNS`): one row per key feature and `SLICE_GRID` share, plus the
      `RANDOM` diagonal; empty when capture is not available.

    `meta` gives `snapshot_period`, `snapshot_base` and `slices` (`slice_shares`); `window` and
    `prior_rows` are the ranking's.
    """
    keys = list_key_features(ranking)
    if keys.empty:
        return _stack([], SLICE_COLUMNS), _stack([], CURVE_COLUMNS)
    snapshot, base, task = meta["snapshot_period"], meta["snapshot_base"], resolved.task
    current = cells.loc[~cells["lagged"] & cells["feature"].isin(keys["feature"])]
    labelled = pool_periods(population_cells(cells), [snapshot]).dropna(subset=["target_bin"])
    shares, reason = meta["slices"], _capture_unavailable(labelled, base, task)
    slices, curves = [], []
    for _, key in keys.iterrows():
        name, own = key["feature"], current.loc[current["feature"] == key["feature"]]
        if key["raw_sign"] == 0:  # no snapshot concordance: no direction, no list
            slices.append(pd.DataFrame({"feature": [name], "insufficient": [False],
                                        "unavailable": [key["unavailable"]]}))  # fmt: skip
            continue
        if key["kind"] == "categorical":
            ordered = ordered_categorical_bins(own, snapshot, window, prior_rows)
        else:
            ordered = ordered_numeric_bins(own, int(key["raw_sign"]), snapshot)
        table = capture_table(ordered, shares, base, task, reason)
        slices.append(table.assign(feature=name, insufficient=table["support"] < MIN_BIN_SUPPORT))
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
