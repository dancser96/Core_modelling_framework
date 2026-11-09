"""The numbers Feature Checks reads from EDA's cells that EDA does not store (D-135).

EDA's ledger and tables hold the snapshot's and the window's statistics, the window's concordance
per period among them (`concordance_per_period`); the numbers here come from the same cells through
the same functions, so they differ from EDA's by data, never by method. `effective_se` is a window
concordance's SE as EDA computes it: its support in effective clients (a client labelled in several
periods counts about once) and the task's SE. `lagged_concordance` is a feature's window
concordance on each row's value one period earlier against its current target, read in the window's
direction, so a flip reads below 0.5 (N11), over the window after its first period: the first
period's previous one is not in EDA's rows, so its lagged values are null by construction. It is
computed on whatever support there is (Q540) and returns the counts its SE is computed from.
`period_psi` compares two named periods: a numeric on ten groups merged from the first period's
bins plus the null bin, a categorical on its bins as they are. `per_period_table` gives every
candidate in every compared period against the snapshot, label-free: rows, missing share and PSI. A
value that cannot exist is decided before computing and named (D-035). Pure pandas; no Spark.
"""

import numpy as np
import pandas as pd

from core_modelling.statistics.cells import group_shares, pool_periods, shares, target_shares
from core_modelling.statistics.concordance import CROSS_FIT_SE_INFLATION, cross_fitted_concordance
from core_modelling.statistics.distributions import merge_bins, psi
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
    """A window concordance's SE as EDA computes it (`ranking.scope_statistics`) and its support
    in effective events.

    `events` and `non_events` are the rows the concordance reads, scaled to effective clients by
    the task's `client_support` on `eda.json`'s `clients`; the task's `concordance_se` at
    `max(value, 1 − value)` (Hanley–McNeil is not symmetric in A, so a value below 0.5 would
    look surer), a categorical's times `CROSS_FIT_SE_INFLATION`. `target_bin_shares` are the
    read rows' target-bin shares (Kendall's SE reads them).
    """
    spec = TASK_SPECS[task]
    events, non_events = spec["client_support"](events, non_events, clients)
    se = spec["concordance_se"](max(value, 1 - value), events, non_events, target_bin_shares)
    return se * (CROSS_FIT_SE_INFLATION if kind == "categorical" else 1), float(events)


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
    """One feature's concordance on its lagged cells over `window[1:]`, read in the window's
    direction, with the counts its SE is computed from.

    The window's first period is left out: its previous period is not in EDA's rows, so its
    lagged cells are null by construction and would only inflate the share with no lagged value.
    A numeric's pooled lagged cells through the task's `cells_concordance` with `sign` (the
    ranking's `raw_sign_window`); a categorical's `cross_fitted_concordance(read=window[1:],
    lagged=True)`, its encoding fitted on the whole window's current cells, in that encoding's
    direction. `cells` holds the feature's current and lagged cells. Returns `value`, `events`,
    `non_events` and `target_bin_shares` of the non-null lagged rows (what `effective_se` reads
    at whichever value a judgement needs; NaN and None when `reason`), `missing_share` (the
    lagged rows with no value: no row in the previous period or a null there, N11; NaN for a
    one-period window) and `reason`: '' or "not available: …" when no value exists.
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
    """Why the lagged concordance cannot exist, decided before computing (the ranking's guards
    on the lagged rows of `window[1:]`, pooled); '' when it can."""
    if counts["events"] == 0:
        return "not available: no events among the non-null lagged rows"
    values = pooled.loc[~pooled["is_null"] & pooled["target_bin"].notna() & (pooled["n"] > 0)]
    if values["target_bin"].nunique() < 2:
        return "not available: a single target value among the non-null lagged rows"
    if kind == "categorical":
        return _lagged_cross_fit_reason(cells, window)
    if sign == 0:
        return "not available: no window concordance to take the direction from"
    return ""


def _lagged_cross_fit_reason(cells: pd.DataFrame, window: list[str]) -> str:
    """Why a categorical's lagged cross-fit cannot exist: the encoding needs labelled current
    values of the window in two client folds, and Somers' D a fold whose lagged rows of
    `window[1:]` hold two target values."""
    labelled = cells.loc[~cells["is_null"] & cells["target_bin"].notna() & (cells["n"] > 0)]
    current = labelled.loc[~labelled["lagged"] & labelled["period"].isin(window)]
    if current["fold"].nunique() < 2:
        return "not available: labelled values in fewer than two client folds"
    lagged = labelled.loc[labelled["lagged"] & labelled["period"].isin(window[1:])]
    if not (lagged.groupby("fold")["target_bin"].nunique() >= 2).any():
        return "not available: no client fold with two target values among the non-null lagged rows"
    return ""


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
    return _pooled_psi(first, second, kind)


def _pooled_psi(first: pd.DataFrame, second: pd.DataFrame, kind: str) -> float:
    """`period_psi` on two periods' pooled cells."""
    if kind == "categorical":
        a, b = _bin_shares(first).align(_bin_shares(second), fill_value=0)
        return psi(a.to_numpy(), b.to_numpy())
    groups = _value_groups(first)
    return psi(group_shares(first, groups), group_shares(second, groups))


def _bin_shares(pooled: pd.DataFrame) -> pd.Series:
    """Each bin's share of the pooled rows, the null bin included."""
    by_bin = pooled.groupby("bin")["n"].sum()
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
    """Every feature of `kinds` in every compared period (`PER_PERIOD_COLUMNS`, never the
    validation period, which the cells do not hold), label-free: `group` (window, gap or
    latest), `rows` (all of the period's rows), `missing_share` and `psi` against the snapshot
    period (`period_psi`). The window's concordance per period is EDA's `concordance_per_period`.
    """
    current = cells.loc[~cells["lagged"]]
    by_feature = dict(tuple(current.groupby("feature")))
    compared = [(group, period) for group in PERIOD_GROUPS for period in periods[group]]
    rows = []
    for name, kind in kinds.items():
        pooled = {period: pool_periods(by_feature[name], [period]) for _, period in compared}
        rows += [
            _label_free_row(name, kind, group, period, pooled[period], pooled[snapshot_period])
            for group, period in compared
        ]
    return pd.DataFrame(rows, columns=PER_PERIOD_COLUMNS)


def _label_free_row(
    name: str, kind: str, group: str, period: str, pooled: pd.DataFrame, snapshot: pd.DataFrame
) -> dict:
    """One feature's label-free numbers in one period: its rows, missing share and PSI from the
    snapshot period."""
    counts = shares(pooled)
    return {"feature": name, "period": period, "group": group, "rows": counts["rows"],
            "missing_share": counts["missing_share"],
            "psi": _pooled_psi(snapshot, pooled, kind)}  # fmt: skip
