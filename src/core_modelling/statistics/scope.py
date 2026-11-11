"""A feature's concordance read from its cells over a scope, the rules every stage shares (D-135).

A scope is one feature's current cells over some periods: the snapshot period, the window
pooled, one window period. `scope_statistics` reads a scope's shares, null concordance and
concordance (a categorical's cross-fitted) with its SE and direction, after deciding up front
whether the concordance can exist (D-035). Its parts are the rules EDA's ranking and Feature
Checks both read, written once: `feature_se`, the SE of a feature's concordance;
`concordance_direction`, the sign it is read in; the availability guards
(`unavailable_reason`, `cross_fit_unavailable`), which Feature Checks also reads on the lagged
rows; and `null_concordance`. `encoding_prior_rows` gives the level encoding's prior on the
window. Pure pandas and numpy.
"""

import numpy as np
import pandas as pd

from core_modelling.statistics.cells import (
    null_table,
    pool_periods,
    population_cells,
    shares,
    target_shares,
)
from core_modelling.statistics.concordance import (
    CROSS_FIT_SE_INFLATION,
    concordance_from_table,
    cross_fitted_concordance,
)
from core_modelling.tasks import TASK_SPECS

NULL_SHARE_RANGE = (0.005, 0.995)  # the missing shares for which EDA reads the null concordance


def encoding_prior_rows(
    cells: pd.DataFrame, task: str, min_events: int, window_periods: list[str]
) -> float:
    """The level encoding's prior weight in rows: `strata.min_events` pseudo-events at the
    window's base rate (regression: `min_events` rows), through
    `TASK_SPECS[task]["shrinkage_rows"]`; a level's rate is `(events + prior · base) / (rows +
    prior)`. The base is the window's mean target from the population's labelled cells
    (`population_cells`)."""
    labelled = pool_periods(population_cells(cells), window_periods).dropna(subset=["target_bin"])
    base = labelled["sum_y"].sum() / labelled["n"].sum()
    return TASK_SPECS[task]["shrinkage_rows"](min_events, base)


def scope_statistics(
    cells: pd.DataFrame,
    kind: str,
    read: list[str],
    task: str,
    window_periods: list[str],
    prior_rows: float,
    exact: bool,
    clients: dict[str, float] | None,
) -> dict:
    """One feature's current cells over the `read` periods: the shares, the null concordance,
    the concordance (direction taken out; a categorical's cross-fitted, in its encoding's
    direction) with `signed` (read with sign +1), its SE and sign (`concordance_direction`),
    the events and non-events, the pooled cells and `reason`, why no concordance exists ('' when
    it does). `clients` given: a window, its SE on effective clients; else one period, its SE on
    its own rows (one per client)."""
    spec = TASK_SPECS[task]
    pooled = pool_periods(cells, read)
    counts = shares(pooled)
    out = {key: counts[key] for key in ("missing_share", "zero_share", "dominant_share")}
    low, high = NULL_SHARE_RANGE
    null = null_concordance(pooled) if low <= counts["missing_share"] <= high else np.nan
    out.update(pooled=pooled, null_concordance=null)
    out.update(events=counts["events"], non_events=counts["non_events"])
    out.update(concordance=np.nan, signed=np.nan, se=np.nan, sign=0)
    out["reason"] = unavailable_reason(pooled, counts)
    if not out["reason"] and kind == "categorical":
        out["reason"] = cross_fit_unavailable(cells, read, window_periods)
    if out["reason"]:
        return out
    if kind == "categorical":  # read in the encoding's direction already
        signed = cross_fitted_concordance(cells, window_periods, prior_rows, read=read)
        value = signed
    else:
        signed = spec["cells_concordance"](pooled, exact, 1)
        value = max(signed, 1 - signed)
    se = feature_se(
        value, counts["events"], counts["non_events"], target_shares(pooled), kind, task, clients
    )
    sign = concordance_direction(value, signed, se)
    return {**out, "concordance": value, "signed": signed, "se": se, "sign": sign}


def feature_se(
    value: float,
    events: float,
    non_events: float,
    target_bin_shares: np.ndarray | None,
    kind: str,
    task: str,
    clients: dict[str, float] | None = None,
) -> float:
    """The SE of a feature's concordance `value` (D-082): the task's `concordance_se` on the
    events and non-events it reads, a window's (`clients` given: `counts.window_clients`) in
    effective clients through the task's `client_support`, a categorical's times
    `CROSS_FIT_SE_INFLATION`. `target_bin_shares` are the read rows' target-bin shares, which
    Kendall's SE reads; Hanley–McNeil reads none, so a binary caller without them passes None."""
    spec = TASK_SPECS[task]
    if clients is not None:
        events, non_events = spec["client_support"](events, non_events, clients)
    # Hanley–McNeil is not symmetric in A: a value below 0.5 (a flipped period, a cross-fitted
    # categorical) would look surer than its mirror image
    se = spec["concordance_se"](max(value, 1 - value), events, non_events, target_bin_shares)
    return se * (CROSS_FIT_SE_INFLATION if kind == "categorical" else 1)


def concordance_direction(value: float, signed: float, se: float) -> int:
    """+1 or −1, the sign the concordance is read in (`signed`, the value read with sign +1, at
    or above 0.5 reads +1, an exact D of 0 included); 0 when `value` is below 0.5 + 2 · `se`."""
    return 0 if value < 0.5 + 2 * se else (1 if signed >= 0.5 else -1)


def unavailable_reason(pooled: pd.DataFrame, counts: dict, lagged: bool = False) -> str:
    """Why the concordance of one feature's pooled cells cannot exist (`counts` their
    `cells.shares`), decided up front; '' when it can. With `lagged` the cells are the lagged
    ones and the reason says so."""
    rows = "non-null lagged rows" if lagged else "non-null rows"
    if counts["events"] == 0:
        return f"no events among the {rows}"
    if _labelled_target_bins(pooled, non_null=True) < 2:
        return f"a single target value among the {rows}"
    return ""


def cross_fit_unavailable(
    cells: pd.DataFrame, read: list[str], window_periods: list[str], lagged: bool = False
) -> str:
    """Why a categorical's cross-fitted concordance cannot exist: the encoding, fitted on the
    current cells of `window_periods`, needs labelled values in two client folds, and Somers' D a
    fold whose rows of `read` (the lagged ones with `lagged`) hold two target values; '' when
    it can."""
    values = cells.loc[~cells["is_null"] & cells["target_bin"].notna() & (cells["n"] > 0)]
    fitted = values.loc[~values["lagged"] & values["period"].isin(window_periods), "fold"]
    if fitted.nunique() < 2:
        return "labelled values in fewer than two client folds"
    in_read = values.loc[(values["lagged"] == lagged) & values["period"].isin(read)]
    if not (in_read.groupby("fold")["target_bin"].nunique() >= 2).any():
        rows = "non-null lagged rows" if lagged else "non-null rows"
        return f"no client fold with two target values among the {rows}"
    return ""


def null_concordance(pooled: pd.DataFrame) -> float:
    """The null indicator's concordance on one feature's pooled cells (direction taken out); NaN
    when their labelled rows hold fewer than two target bins."""
    if _labelled_target_bins(pooled, non_null=False) < 2:
        return np.nan
    return concordance_from_table(null_table(pooled))


def _labelled_target_bins(pooled: pd.DataFrame, non_null: bool) -> int:
    """The target bins holding labelled rows (the non-null rows only with `non_null`)."""
    labelled = pooled.loc[pooled["target_bin"].notna() & (pooled["n"] > 0)]
    if non_null:
        labelled = labelled.loc[~labelled["is_null"]]
    return labelled["target_bin"].nunique()
