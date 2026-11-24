"""The score cells: the one aggregate of a scorer's scores that every Evaluation metric reads.

A scorer's cells hold one row per part, period, the columns of `by`, score bin and target bin,
with the sums the metrics need, each row weighted by its client's weight (1 at replicate 0, a
Poisson draw in a bootstrap replicate). The Spark aggregate (`evaluation/cells.py`) builds them
over the scored rows with a known target, with a `replicate` column; `pool_cells` sums a `by`
column's levels away (the `all` cells from the `split` ones). Score bins are quantile bins of
the scorer's column, cut once per scorer over those rows at `bin_quantiles` (the task's
`score_grid` in `tasks.TASK_SPECS`, with its `strata_step` and `tail_start`, which the callers
pass in: this module imports no task), narrowing towards the top rows, where the average
precision and the top slices are read; `narrowest_bin` is the finest bin's share, of which a
slice spans a few at least (`evaluation/slices.py::MIN_SLICE_BINS`). A regression target's bins
are EDA's (`tasks.TARGET_BINS`, zero its own bin).

The sums are taken per row, so the log loss, the Brier score, the errors and the deviance are
exact, and only the rank metrics, the slices, the curves and the calibration slope carry the
binning's tolerance. `loss_sum` is the sum of one of `evaluation/cells.py`'s `ROW_LOSSES`,
named by the caller, and `link_sum` the clipped score's logit, filled for the log loss only (a
probability): both are null for a scorer without such a loss. Pure pandas and numpy.
"""

import numpy as np
import pandas as pd

PARTS = ("test", "validation")  # the values of `part`, as `build_frames(…, "evaluation")` gives
POOLED = "pooled"  # the period of a row over all of its part's periods (the tables, the charts)
MEAN = "mean"  # the period of the row holding the plain mean of the periods' values
# The cell's keys; the columns of `by` follow `period`, and the Spark frame adds `replicate`.
CELL_KEYS = ["part", "period", "score_bin", "target_bin"]
# Weighted sums: `sq_error_sum` is the Brier sum of a binary target.
CELL_SUMS = ["rows", "target_sum", "score_sum", "sq_error_sum", "abs_error_sum", "loss_sum",
             "target_sq_sum", "link_sum"]  # fmt: skip
CELL_EXTREMES = ["score_min", "score_max"]  # the cell's unweighted extremes (the drift edges)
PROBABILITY_CLIP = 1e-15  # the log loss and the logit read the score clipped to [c, 1 − c]


def bin_quantiles(grid: list[tuple[float, int]]) -> np.ndarray:
    """The interior cumulative probabilities, ascending, at which a scorer's column is cut:
    the task's score `grid` (`(upper, bins)` segments from the lowest score), each segment split
    into its equal bins.

    Binned on binary's, on 1 to 2 million simulated rows at base rates from 0.05% to 5%, the
    average precision lay within 0.0015 of the rows' (at most 4% of it low, a weak score at
    0.05%), the calibration slope within 0.0003 and the intercept within 0.0015 of the row fit;
    the former 200 bins (none below 0.1%) read it up to 5% low at 1% and up to 61% low below.
    Every `strata_step`-th edge is the strata's grid, binary's 95 bins: a stratum's
    average precision 0.0007 low at a 2.9% rate, where 50 bins read it 0.010 (4%) low.

    On regression's, on a million simulated amounts at three tail weights and four periods,
    each slice's capture lay within 4.5% of the rows' own top k from the top 0.05% on, within
    1.6% from the top 0.3% on, and up to 41% off at the finest bin, where the list of 40 rows'
    own bootstrap error is as large; the former 50 bins read the top 0.1% 27% to 48% low and
    the top 0.3% 9% to 13% low.
    """
    cuts, lower = [], 0.0
    for upper, bins in grid:
        cuts.append(np.linspace(lower, upper, bins + 1)[1:])
        lower = upper
    return np.concatenate(cuts)[:-1]


def narrowest_bin(grid: list[tuple[float, int]], step: int = 1) -> float:
    """The share of the rows in the narrowest score bin of `grid`, every `step`-th edge of it
    (the task's `strata_step` for the strata's)."""
    if step < 1:
        raise ValueError(f"narrowest_bin: the step must be at least 1, got {step}")
    edges = bin_quantiles(grid)[step - 1 :: step]
    # rounded off `linspace`'s float noise, so a slice declared at exactly that share is read
    return round(float(np.diff([0.0, *edges, 1.0]).min()), 12)


def quantile_passes(
    grid: list[tuple[float, int]], tail_start: float | None
) -> tuple[np.ndarray, np.ndarray]:
    """`bin_quantiles(grid)` as Spark takes them: the body's over every row, ending at
    `tail_start`, and the tail's over the rows at or above that edge, as shares of those rows
    (empty without a tail: `tail_start` None)."""
    cuts = bin_quantiles(grid)
    if tail_start is None:
        return cuts, np.array([])
    if tail_start not in cuts:
        raise ValueError(f"quantile_passes: the tail start {tail_start} is no edge of the grid")
    in_tail = cuts > tail_start
    return cuts[~in_tail], (cuts[in_tail] - tail_start) / (1 - tail_start)


def pool_cells(cells: pd.DataFrame, over: str) -> pd.DataFrame:
    """The cells with the levels of `over` pooled: the `split` cells summed over `split` are the
    `all` cells, so Spark sums them once per scorer.

    Receives cells (`CELL_KEYS` with `by`'s columns, `replicate` when there, `CELL_SUMS`,
    `CELL_EXTREMES`); returns one row per remaining key, the columns in the same order without
    `over`, sorted by the keys: the sums added (a null sum stays null), the extremes their min
    and max. An `over` that is no `by` column of the cells fails loud.
    """
    measures = [*CELL_SUMS, *CELL_EXTREMES]
    if over not in cells.columns or over in [*CELL_KEYS, "replicate", *measures]:
        raise ValueError(f"pool_cells: {over!r} is no `by` column of the cells")
    keys = [column for column in cells.columns if column not in [*measures, over]]
    grouped = cells.groupby(keys, dropna=False, sort=True)
    sums = grouped[CELL_SUMS].sum(min_count=1)
    extremes = grouped.agg(score_min=("score_min", "min"), score_max=("score_max", "max"))
    return sums.join(extremes).reset_index()
