"""What an ordered list achieves at shares of its rows: counts, the estimate, lift and capture.

An ordered list is one frame of bins in list order with `fold`, `n`, `sum_y`, `sum_y2` and
`support` (`SUMMED`), each fold cut on its own since each fold's list has its own order (a
categorical ordered per client fold, D-135). `capture_table` cuts each fold's cumulative counts
at a slice's share, linearly inside the boundary bin (V57), sums them over the folds and gives
the task's estimate with its interval (`period_estimate`), the lift over a base and the capture,
the share of `sum_y` (the positives, or the amount); `capture_curve` gives the capture on a
grid of shares. EDA's decision view cuts one feature's list (`eda/slices.py`); Evaluation cuts
a model's at the same `evaluation.slices`. Whether a capture can exist is the caller's to
decide up front and hand in as a reason (D-035). Pure pandas and numpy.
"""

import numpy as np
import pandas as pd

from core_modelling.tasks import TASK_SPECS

SUMMED = ["n", "sum_y", "sum_y2", "support"]


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
    """`sum_y` as a share of the bins' total; refused on a total that is not positive (the
    caller decides it up front)."""
    total = ordered["sum_y"].sum()
    if not total > 0:
        raise ValueError(f"capture: the total target {total} is not positive")
    return sum_y / total


def capture_table(
    ordered: pd.DataFrame, shares: dict[str, float], base: float, task: str, reason: str
) -> pd.DataFrame:
    """One row per slice (`slice`, `share`, `rows`, `support`, `estimate`, `low`, `high`, `lift`,
    `capture`, `unavailable`): the counts at its share (`_counts_at`); the task's estimate with
    its interval; `lift` over `base` when `lift_available(base)`; `capture`, NaN with `reason` in
    `unavailable` when the caller has one."""
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
        "capture": nan if reason else _captured(at["sum_y"], ordered), "unavailable": reason,
    })  # fmt: skip


def capture_curve(ordered: pd.DataFrame, grid: np.ndarray) -> pd.DataFrame:
    """The capture at each share of `grid` (`share`, `capture`), cut as in `capture_table`;
    only for a list whose capture exists."""
    captured = _captured(_counts_at(ordered, grid)["sum_y"], ordered)
    return pd.DataFrame({"share": grid, "capture": captured})
