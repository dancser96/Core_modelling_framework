"""The numbers Feature Checks reads from EDA's cells that EDA does not store (D-135).

A window concordance's SE as EDA computes it (`effective_se`), the lagged concordance
(`lagged_concordance`, N11), PSI between two named periods (`period_psi`) and the label-free
per-period table (`per_period_table`). They come from the same cells through the same
`statistics` functions as EDA's numbers, so they differ from EDA's by data, never by method. A
value that cannot exist is decided before computing and named (D-035). Pure pandas.
"""

import numpy as np
import pandas as pd

from core_modelling.statistics.cells import group_shares, pool_periods, shares, target_shares
from core_modelling.statistics.concordance import cross_fitted_concordance
from core_modelling.statistics.distributions import merge_bins, psi
from core_modelling.statistics.scope import cross_fit_unavailable, feature_se, unavailable_reason
from core_modelling.tasks import TASK_SPECS

PSI_GROUPS = 10  # the groups a numeric's bins are merged into for PSI, the null bin beside them
PERIOD_GROUPS = ("window", "gap", "latest")  # eda.json's compared periods, in time order
PER_PERIOD_COLUMNS = ["feature", "period", "group", "rows", "missing_share", "psi"]
ONE_PERIOD = "not available: a one-period window has no lagged value"  # no lag in EDA's rows


def effective_se(
    value: float,
    events: float,
    non_events: float,
    target_bin_shares: np.ndarray,
    *,
    kind: str,
    task: str,
    clients: dict[str, float],
) -> tuple[float, float]:
    """A window concordance's SE as EDA computes it (`scope.feature_se` on `eda.json`'s
    `clients`) and its support in effective events (the task's `client_support`).

    `events` and `non_events` are the rows the concordance reads; `target_bin_shares` their
    target-bin shares (Kendall's SE reads them).
    """
    events, non_events = TASK_SPECS[task]["client_support"](events, non_events, clients)
    return feature_se(value, events, non_events, target_bin_shares, kind, task), float(events)


def lagged_concordance(
    cells: pd.DataFrame,
    kind: str,
    *,
    task: str,
    window: list[str],
    prior_rows: float,
    exact: bool,
    sign: int,
) -> dict:
    """One feature's concordance on each row's value one period earlier against its current
    target, over `window[1:]`, read in the window's direction so a flip reads below 0.5 (N11);
    computed on whatever support there is (Q540).

    `cells` holds the feature's current and lagged cells. The window's first period is left
    out: its previous period is not in EDA's rows, so it has no lagged cells.
    A numeric's pooled lagged cells go through the task's `cells_concordance` with `sign` (the
    ranking's `raw_sign_window`); a categorical's through `cross_fitted_concordance` with
    `read=window[1:]` and `lagged=True`, its encoding fitted on the whole window's current cells.

    Returns a dict: `value`; `events`, `non_events` and `target_bin_shares` of the non-null
    lagged rows, what `effective_se` reads (NaN and None when `reason`); `missing_share`, the
    lagged rows with no value (no row in the previous period or a null there; NaN for a
    one-period window); `reason`, '' or "not available: …".
    """
    nan = float("nan")
    out = {"value": nan, "missing_share": nan, "reason": ONE_PERIOD, "events": nan,
           "non_events": nan, "target_bin_shares": None}  # fmt: skip
    if len(window) < 2:
        return out
    read = window[1:]
    pooled = pool_periods(cells, read, lagged=True)
    counts = shares(pooled)
    reason = _lagged_reason(cells, pooled, counts, kind, window, sign)
    out.update(missing_share=counts["missing_share"], reason=reason)
    if reason:
        return out
    if kind == "categorical":
        value = cross_fitted_concordance(cells, window, prior_rows, read=read, lagged=True)
    else:
        value = TASK_SPECS[task]["cells_concordance"](pooled, exact, sign)
    return {**out, "value": value, "events": counts["events"], "non_events": counts["non_events"],
            "target_bin_shares": target_shares(pooled)}  # fmt: skip


def _lagged_reason(
    cells: pd.DataFrame, pooled: pd.DataFrame, counts: dict, kind: str, window: list[str], sign: int
) -> str:
    """Why the lagged concordance cannot exist, decided before computing (the scope's guards
    on the lagged rows of `window[1:]`, pooled, a categorical's encoding fitted on the window's
    current cells; a numeric's direction from the window's concordance); '' when it can."""
    reason = unavailable_reason(pooled, counts, lagged=True)
    if not reason and kind == "categorical":
        reason = cross_fit_unavailable(cells, window[1:], window, lagged=True)
    elif not reason and sign == 0:
        reason = "no window concordance to take the direction from"
    return f"not available: {reason}" if reason else ""


def period_psi(cells: pd.DataFrame, kind: str, expected: str, actual: str) -> float:
    """PSI from the `expected` period to the `actual` one over one feature's current cells.

    A numeric: the expected period's non-null bins merged into about `PSI_GROUPS` groups, the
    same `bin_order` ranges applied to the actual period (a bin empty in the expected period
    joins the group whose range starts at or below it, the first group when below every range),
    plus the null bin. A categorical: its bins as they are (kept levels, `__other__`, `__new__`,
    null), aligned on their union. Shares are over all the period's rows, null included, never
    renormalised; `psi` floors them.
    """
    current = cells.loc[~cells["lagged"]]
    first, second = (pool_periods(current, [period]) for period in (expected, actual))
    return _psi_against(_psi_reference(first, kind), second, kind)


def _psi_reference(
    cells: pd.DataFrame, kind: str
) -> tuple[pd.Series | np.ndarray, pd.DataFrame | None]:
    """The expected side of `period_psi` on one period's cells: a categorical's bin shares, or a
    numeric's group shares with the groups (`_value_groups`) the actual period is cut by."""
    if kind == "categorical":
        return _bin_shares(cells), None
    groups = _value_groups(cells)
    return group_shares(cells, groups), groups


def _psi_against(
    reference: tuple[pd.Series | np.ndarray, pd.DataFrame | None], cells: pd.DataFrame, kind: str
) -> float:
    """`period_psi` from a `_psi_reference` to another period's cells."""
    expected, groups = reference
    if kind == "categorical":
        a, b = expected.align(_bin_shares(cells), fill_value=0)
        return psi(a.to_numpy(), b.to_numpy())
    return psi(expected, group_shares(cells, groups))


def _bin_shares(pooled: pd.DataFrame) -> pd.Series:
    """Each bin's share of the pooled rows, the null bin included."""
    by_bin = pooled.groupby("bin")["n"].sum()
    if by_bin.sum() == 0:
        raise ValueError("period_psi: a period's cells hold no rows")
    return by_bin / by_bin.sum()


def _value_groups(pooled: pd.DataFrame) -> pd.DataFrame:
    """The PSI groups cut on one period's non-null bins (`merge_bins`, a mass point its own
    group); one group for every value when the period holds none, so the other period's values
    still have a group to fall in."""
    values = pooled.loc[~pooled["is_null"]]
    if values.empty:
        return pd.DataFrame({"bin_order_first": [0]})
    per_bin = values.groupby("bin_order", as_index=False)["n"].sum()
    return merge_bins(per_bin, PSI_GROUPS, None)  # no edges: the group labels go unread


def per_period_table(
    cells: pd.DataFrame,
    kinds: dict[str, str],
    *,
    periods: dict[str, list[str]],
    snapshot_period: str,
) -> pd.DataFrame:
    """One row per feature of `kinds` and compared period (`periods`: group → labels), from the
    counts table's current cells, label-free; never the validation period, which the cells do
    not hold.

    Columns `PER_PERIOD_COLUMNS`: `group` (window, gap or latest), `rows` (all of the period's
    rows), `missing_share` and `psi` against `snapshot_period` (`period_psi`). Refused when a
    feature has no cells in a compared period. The window's concordance per period is EDA's
    `concordance_per_period`.
    """
    compared = [(group, period) for group in PERIOD_GROUPS for period in periods[group]]
    chosen = cells["feature"].isin(list(kinds)) & cells["period"].isin([p for _, p in compared])
    current = cells.loc[~cells["lagged"] & chosen]
    # one split, not a `pool_periods` per feature and period: the PSI helpers sum by bin anyway
    by_cell = dict(tuple(current.groupby(["feature", "period"])))
    absent = [(name, p) for name in kinds for _, p in compared if (name, p) not in by_cell]
    if absent:
        raise ValueError(f"per_period_table: no current cells for (feature, period) {absent[:5]}")
    rows = []
    for name, kind in kinds.items():
        # the snapshot's PSI groups are the same against every period: cut once per feature
        reference = _psi_reference(by_cell[name, snapshot_period], kind)
        rows += [
            {"feature": name, "period": period, "group": group,
             "psi": _psi_against(reference, by_cell[name, period], kind)}
            for group, period in compared
        ]  # fmt: skip
    table = pd.DataFrame(rows, columns=["feature", "period", "group", "psi"])
    return table.join(_period_rows(current), on=["feature", "period"])[PER_PERIOD_COLUMNS]


def _period_rows(current: pd.DataFrame) -> pd.DataFrame:
    """One row per (`feature`, `period`) index of the current cells: `rows` (all of the
    period's rows) and `missing_share` (null rows / rows)."""
    filled = current["n"].where(~current["is_null"], 0)
    counts = current.assign(filled=filled).groupby(["feature", "period"])[["n", "filled"]].sum()
    return pd.DataFrame({"rows": counts["n"], "missing_share": 1 - counts["filled"] / counts["n"]})
