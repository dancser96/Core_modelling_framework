"""The ranking table: every candidate's statistics from the cells, its rank and the key features.

`feature_statistics` reads each feature's current cells twice: the snapshot period's (the
`concordance`, its SE, `direction`, the best order and `non_monotone`, and the snapshot shares)
and the window periods' pooled (the `*_window` twins, the best order's among them, which Feature
Checks' leak screen reads: a U-shaped leak shows only in best order), with the definitions of
`docs/components/eda.md` "The statistics", each through `statistics.scope.scope_statistics`. A
snapshot's SE takes its support in its own rows (one per client); a window's in effective
clients (`client_support`). A categorical's value is cross-fitted by client fold and its SE
inflated by `CROSS_FIT_SE_INFLATION`; it has no best order. A statistic that cannot exist (no
events, one target value, too few folds) is decided before computing and named in
`unavailable` (D-035).
`rank_features` orders by the ranking value (V2) and `select_key_features` walks that order with
the correlation skip. The ledger's `levels` come from the snapshot (`count_levels`), not the
cells, since the counts table caps a categorical's levels.
"""

import numpy as np
import pandas as pd

from core_modelling.config.schema import KeyFeatures
from core_modelling.statistics.concordance import (
    best_order_concordance,
    is_non_monotone,
    ranking_value,
)
from core_modelling.statistics.scope import scope_statistics

DIRECTIONS = {1: "+", -1: "-", 0: None}
STATISTIC_COLUMNS = [
    "feature", "kind", "levels", "concordance", "concordance_se", "direction",
    "concordance_best_order", "non_monotone", "concordance_window",
    "concordance_best_order_window", "direction_window",
    "raw_sign", "raw_sign_window",
    "missing_share", "missing_share_window", "null_concordance", "null_concordance_window",
    "zero_share", "zero_share_window", "dominant_share", "dominant_share_window", "unavailable",
]  # fmt: skip


def count_levels(snapshot: pd.DataFrame, kinds: dict[str, str]) -> dict[str, int]:
    """Per feature, the distinct non-null values on the snapshot's eligible rows, before any
    level cap (the ledger's `levels`); a float NaN is null (N2)."""
    eligible = snapshot.loc[snapshot["eligible"] == 1]
    return {name: int(eligible[name].nunique(dropna=True)) for name in kinds}


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
    `rank`, `key_feature` and `represented_by`, plus `kind`, `concordance_best_order_window`
    (the best order on the window's pooled cells), `direction_window`, `raw_sign`
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


def _record(
    name: str, kind: str, levels: int, snapshot: dict, window: dict, prior_rows: float
) -> dict:
    """One feature's row of the statistics table from its snapshot and window scopes."""
    best = _best_order(snapshot, kind, prior_rows)
    plain, se = snapshot["concordance"], snapshot["se"]
    non_monotone = not np.isnan(best) and is_non_monotone(plain, best, se)
    scopes = {"snapshot": snapshot, "window": window}
    reasons = [f"{s['reason']} in the {scope}" for scope, s in scopes.items() if s["reason"]]
    shares = ["missing_share", "null_concordance", "zero_share", "dominant_share"]
    return {
        "feature": name, "kind": kind, "levels": levels, "concordance": snapshot["concordance"],
        "concordance_se": snapshot["se"], "direction": DIRECTIONS[snapshot["sign"]],
        "concordance_best_order": best, "non_monotone": non_monotone,
        "concordance_window": window["concordance"],
        "concordance_best_order_window": _best_order(window, kind, prior_rows),
        "direction_window": DIRECTIONS[window["sign"]],
        "raw_sign": _raw_sign(snapshot), "raw_sign_window": _raw_sign(window),
        **{column: snapshot[column] for column in shares},
        **{f"{column}_window": window[column] for column in shares},
        "unavailable": f"not available: {'; '.join(reasons)}" if reasons else "",
    }  # fmt: skip


def _best_order(scope: dict, kind: str, prior_rows: float) -> float:
    """A scope's best-order concordance for an available numeric; NaN otherwise (a categorical's
    equals its plain value by definition)."""
    if kind != "numeric" or scope["reason"]:
        return np.nan
    return best_order_concordance(scope["pooled"], prior_rows)


def _raw_sign(scope: dict) -> int:
    """A scope's raw sign of D: +1 at or above 0.5 (an exact 0 reads +), −1 below, 0 without a
    concordance."""
    return 0 if scope["reason"] else (1 if scope["signed"] >= 0.5 else -1)


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
