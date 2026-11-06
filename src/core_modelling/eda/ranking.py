"""The ranking table: every candidate's statistics from the cells, its rank and the key features.

`feature_statistics` reads each feature's current cells twice: the snapshot period's (the
`concordance`, its SE, `direction`, the best order and `non_monotone`, and the snapshot shares)
and the window periods' pooled (the `*_window` twins), with the definitions of
`docs/components/eda.md` "The statistics" and the functions of `statistics/`. A snapshot's SE
takes its support in its own rows (one per client); a window's in effective clients
(`client_support`). A categorical's value is cross-fitted by client fold and its SE inflated by
`CROSS_FIT_SE_INFLATION`; it has no best order. A statistic that cannot exist (no events, one
target value, too few folds) is decided before computing and named in `unavailable` (D-035).
`rank_features` orders by the ranking value (V2) and `select_key_features` walks that order with
the correlation skip. The ledger's `levels` come from the snapshot (`count_levels`), not the
cells, since the counts table caps a categorical's levels.
"""

import numpy as np
import pandas as pd

from core_modelling.config.schema import KeyFeatures
from core_modelling.statistics.cells import null_table, pool_periods, shares, target_shares
from core_modelling.statistics.concordance import (
    CROSS_FIT_SE_INFLATION,
    best_order_concordance,
    concordance_from_table,
    cross_fitted_concordance,
    is_non_monotone,
    ranking_value,
)
from core_modelling.tasks import TASK_SPECS

NULL_SHARE_RANGE = (0.005, 0.995)  # the missing shares for which the null concordance is read
DIRECTIONS = {1: "+", -1: "-", 0: None}
STATISTIC_COLUMNS = [
    "feature", "kind", "levels", "concordance", "concordance_se", "direction",
    "concordance_best_order", "non_monotone", "concordance_window", "direction_window",
    "raw_sign", "raw_sign_window",
    "missing_share", "missing_share_window", "null_concordance", "null_concordance_window",
    "zero_share", "zero_share_window", "dominant_share", "dominant_share_window", "unavailable",
]  # fmt: skip


def count_levels(snapshot: pd.DataFrame, kinds: dict[str, str]) -> dict[str, int]:
    """Per feature, the distinct non-null values on the snapshot's eligible rows, before any
    level cap (the ledger's `levels`); a float NaN is null (N2)."""
    eligible = snapshot.loc[snapshot["eligible"] == 1]
    return {name: int(eligible[name].nunique(dropna=True)) for name in kinds}


def encoding_prior_rows(
    cells: pd.DataFrame, task: str, min_events: int, window_periods: list[str]
) -> float:
    """The level encoding's prior weight in rows: `strata.min_events` pseudo-events at the
    window's base rate (regression: `min_events` rows), through
    `TASK_SPECS[task]["shrinkage_rows"]`; a level's rate is `(events + prior · base) / (rows +
    prior)`. The base is the window's mean target from one feature's labelled cells (every
    feature's cells cover every eligible row)."""
    current = cells.loc[~cells["lagged"]]
    if current.empty:
        raise ValueError("encoding_prior_rows: the cells hold no current rows")
    one = current.loc[current["feature"] == current["feature"].iloc[0]]
    labelled = pool_periods(one, window_periods).dropna(subset=["target_bin"])
    base = labelled["sum_y"].sum() / labelled["n"].sum()
    return TASK_SPECS[task]["shrinkage_rows"](min_events, base)


def feature_statistics(
    cells: pd.DataFrame,
    kinds: dict[str, str],
    task: str,
    snapshot_period: str,
    window_periods: list[str],
    clients: dict[str, float],
    prior_rows: float,
    levels: dict[str, int],
    exact: bool,
) -> pd.DataFrame:
    """One row per feature of `kinds` (`STATISTIC_COLUMNS`): the ledger's EDA columns except
    `rank`, `key_feature` and `represented_by`, plus `kind`, `direction_window`, `raw_sign`
    (the snapshot's D's sign, + on an exact 0, 0 without a snapshot concordance: the direction a
    one-feature list takes, `slices.py`), `raw_sign_window` (the sign a per-period concordance
    is read in: the window's D's, so it equals `direction_window` where that exists) and
    `unavailable` ('' or the "not available: …" reason).

    `clients` is `counts.window_clients`' dict, `prior_rows` from `encoding_prior_rows`,
    `levels` from `count_levels`, `exact` true when `eda.bins` is null.
    """
    current = cells.loc[~cells["lagged"]]
    by_feature = dict(tuple(current.groupby("feature")))
    missing = sorted(set(kinds) - set(by_feature))
    if missing:
        raise ValueError(f"feature_statistics: the cells hold no current rows for {missing}")
    args = (task, window_periods, prior_rows, exact)
    records = []
    for name, kind in kinds.items():
        snapshot = scope_statistics(by_feature[name], kind, [snapshot_period], *args, clients=None)
        window = scope_statistics(by_feature[name], kind, window_periods, *args, clients=clients)
        records.append(_record(name, kind, levels[name], snapshot, window, prior_rows))
    return pd.DataFrame(records, columns=STATISTIC_COLUMNS)


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
    direction) with `signed` (read with sign +1), its SE and sign (+1, −1, or 0 below 0.5 + 2 SE),
    the events and non-events, the pooled cells and `reason`, why no concordance exists ('' when
    it does). `clients` given: a window, its SE on effective clients; else one period, its SE on
    its own rows (one per client)."""
    spec = TASK_SPECS[task]
    pooled = pool_periods(cells, read)
    counts = shares(pooled)
    out = {key: counts[key] for key in ("missing_share", "zero_share", "dominant_share")}
    out.update(pooled=pooled, null_concordance=_null_concordance(pooled, counts["missing_share"]))
    out.update(events=counts["events"], non_events=counts["non_events"])
    out.update(concordance=np.nan, signed=np.nan, se=np.nan, sign=0)
    out["reason"] = _unavailable(pooled, counts)
    if not out["reason"] and kind == "categorical":
        out["reason"] = _cross_fit_unavailable(cells, read, window_periods)
    if out["reason"]:
        return out
    if kind == "categorical":  # read in the encoding's direction already
        signed = cross_fitted_concordance(cells, window_periods, prior_rows, read=read)
        value = signed
    else:
        signed = spec["cells_concordance"](pooled, exact, 1)
        value = max(signed, 1 - signed)
    events, non_events = counts["events"], counts["non_events"]
    if clients is not None:
        events, non_events = spec["client_support"](events, non_events, clients)
    # Hanley–McNeil is not symmetric in A: a cross-fitted value below 0.5 would look surer
    se = spec["concordance_se"](max(value, 1 - value), events, non_events, target_shares(pooled))
    se *= CROSS_FIT_SE_INFLATION if kind == "categorical" else 1
    sign = 0 if value < 0.5 + 2 * se else (1 if signed >= 0.5 else -1)
    return {**out, "concordance": value, "signed": signed, "se": se, "sign": sign}


def _record(
    name: str, kind: str, levels: int, snapshot: dict, window: dict, prior_rows: float
) -> dict:
    """One feature's row of the statistics table from its snapshot and window scopes; the best
    order for an available numeric only (a categorical's equals its plain value by definition)."""
    best, non_monotone = np.nan, False
    if kind == "numeric" and not snapshot["reason"]:
        best = best_order_concordance(snapshot["pooled"], prior_rows)
        non_monotone = is_non_monotone(snapshot["concordance"], best, snapshot["se"])
    scopes = {"snapshot": snapshot, "window": window}
    reasons = [f"{s['reason']} in the {scope}" for scope, s in scopes.items() if s["reason"]]
    shares = ["missing_share", "null_concordance", "zero_share", "dominant_share"]
    return {
        "feature": name, "kind": kind, "levels": levels, "concordance": snapshot["concordance"],
        "concordance_se": snapshot["se"], "direction": DIRECTIONS[snapshot["sign"]],
        "concordance_best_order": best, "non_monotone": non_monotone,
        "concordance_window": window["concordance"], "direction_window": DIRECTIONS[window["sign"]],
        "raw_sign": _raw_sign(snapshot), "raw_sign_window": _raw_sign(window),
        **{column: snapshot[column] for column in shares},
        **{f"{column}_window": window[column] for column in shares},
        "unavailable": f"not available: {'; '.join(reasons)}" if reasons else "",
    }  # fmt: skip


def _raw_sign(scope: dict) -> int:
    """A scope's raw sign of D: +1 at or above 0.5 (an exact 0 reads +), −1 below, 0 without a
    concordance."""
    return 0 if scope["reason"] else (1 if scope["signed"] >= 0.5 else -1)


def _labelled_target_bins(pooled: pd.DataFrame, non_null: bool) -> int:
    """The target bins holding labelled rows (the non-null rows only with `non_null`)."""
    labelled = pooled.loc[pooled["target_bin"].notna() & (pooled["n"] > 0)]
    if non_null:
        labelled = labelled.loc[~labelled["is_null"]]
    return labelled["target_bin"].nunique()


def _unavailable(pooled: pd.DataFrame, counts: dict) -> str:
    """Why the concordance of the pooled cells cannot exist, decided up front; '' when it can."""
    if counts["events"] == 0:
        return "no events among the non-null rows"
    if _labelled_target_bins(pooled, non_null=True) < 2:
        return "a single target value among the non-null rows"
    return ""


def _cross_fit_unavailable(cells: pd.DataFrame, read: list[str], window_periods: list[str]) -> str:
    """Why a categorical's cross-fitted concordance cannot exist: the encoding needs labelled
    values in two client folds, and Somers' D a fold whose `read` rows hold two target values."""
    values = cells.loc[~cells["is_null"] & cells["target_bin"].notna() & (cells["n"] > 0)]
    if values.loc[values["period"].isin(window_periods), "fold"].nunique() < 2:
        return "labelled values in fewer than two client folds"
    per_fold = values.loc[values["period"].isin(read)].groupby("fold")["target_bin"].nunique()
    if not (per_fold >= 2).any():
        return "no client fold with two target values among the non-null rows"
    return ""


def _null_concordance(pooled: pd.DataFrame, missing_share: float) -> float:
    """The null indicator's concordance (direction taken out), read for a missing share inside
    `NULL_SHARE_RANGE` with labelled rows in two target bins; NaN otherwise."""
    low, high = NULL_SHARE_RANGE
    if not low <= missing_share <= high or _labelled_target_bins(pooled, non_null=False) < 2:
        return np.nan
    return concordance_from_table(null_table(pooled))


def rank_features(stats: pd.DataFrame) -> pd.DataFrame:
    """The statistics with `ranking_value` (a numeric's best order when non-monotone, else the
    plain concordance; NaN when not available) and `rank` 1… by it descending, ties by name,
    the features without a value last."""
    values = [
        ranking_value(row.concordance, row.concordance_best_order, row.concordance_se)
        if row.kind == "numeric" and pd.notna(row.concordance)
        else row.concordance
        for row in stats.itertuples()
    ]
    ranked = stats.assign(ranking_value=values).sort_values(
        ["ranking_value", "feature"], ascending=[False, True], na_position="last"
    )
    return ranked.assign(rank=np.arange(1, len(ranked) + 1)).reset_index(drop=True)


def select_key_features(
    ranking: pd.DataFrame, association: pd.DataFrame, rule: KeyFeatures
) -> pd.DataFrame:
    """The ranking with `key_feature` (`top_n`, `listed` or '') and `represented_by` (the key
    feature a candidate was skipped for, or '').

    The `include` features are chosen first and never skipped; then the ranking is walked by rank
    over the features with a value: a candidate whose |statistic| with a chosen key feature
    exceeds `rule.max_correlation` is skipped (a "not compared" pair, NaN, never skips), until
    `rule.top_n` are chosen on top of the listed ones. `association` is
    `association_table`'s long table and must hold every pair the walk compares.
    """
    unknown = sorted(set(rule.include) - set(ranking["feature"]))
    if unknown:
        raise ValueError(f"eda.key_features.include names {unknown}, which are not ranked")
    strength = {}
    for a, b, statistic in association[["a", "b", "statistic"]].itertuples(index=False):
        strength[a, b] = strength[b, a] = abs(statistic)
    chosen = dict.fromkeys(rule.include, "listed")
    represented: dict[str, str] = {}
    ordered = ranking.sort_values("rank").reset_index(drop=True)
    walked = 0
    for name in ordered.loc[ordered["ranking_value"].notna(), "feature"]:
        if walked == rule.top_n:
            break
        if name in chosen:
            continue
        partner = _represented_by(name, list(chosen), strength, rule.max_correlation)
        if partner:
            represented[name] = partner
            continue
        chosen[name] = "top_n"
        walked += 1
    return ordered.assign(
        key_feature=ordered["feature"].map(chosen).fillna(""),
        represented_by=ordered["feature"].map(represented).fillna(""),
    )


def _represented_by(
    name: str, chosen: list[str], strength: dict[tuple[str, str], float], threshold: float
) -> str:
    """The chosen key feature most associated with `name` above `threshold`, or ''."""
    absent = [key for key in chosen if (name, key) not in strength]
    if absent:
        raise ValueError(
            f"select_key_features: the association table has no pair {name} × {absent}"
        )
    above = {key: strength[name, key] for key in chosen if strength[name, key] > threshold}
    return max(above, key=above.get) if above else ""
