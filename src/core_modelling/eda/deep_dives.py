"""The key features' deep dives and the strata pivots (docs/components/eda.md).

A deep dive reads the snapshot: `bin_table` merges a numeric's snapshot cells into about ten
groups (`merged_groups`, a mass point its own group, chart rule 4) and summarises the eligible
rows with a known target mapped to those groups through the feature's edges, the way the counts
table's `Bucketizer` buckets them (`bin_orders`); `level_table` gives one row per level instead
(a categorical, or a numeric with few values); `quartiles_by_target` the feature's box per target
class and `target_quartiles_by_group` an amount target's box per group of the feature
(`box_table`); `per_period_concordance` the window periods' concordance read in the window's
direction. Every group table carries the per-task summary columns (`population.summarise_groups`)
and greys a group below `MIN_BIN_SUPPORT` events (strata cells below `strata.min_events`), never
hides it. `dive_group_count` is the one rule for how a feature's deep dive groups it (by level,
or about ten merged groups). `strata_pivots` crosses every key feature's groups with each other
stratum variable's levels. A numeric whose every group is one value (by level) reads its values,
`0`, `1`, not `= 0` (`value_labels`); merged ranges and a mass point among them keep `[a, b)` and
`= v`. `dive_group_count`, `numeric_groups`, `merged_groups`, `value_labels` and `box_table` are
public because the exploration functions (`explore.py`) cut and draw the same groups.
"""

import numpy as np
import pandas as pd
from scipy import stats

from core_modelling.config.schema import Strata
from core_modelling.dataset.counts import LEVEL_CAP, NULL_BIN
from core_modelling.eda.population import cap_levels, known_rows, strata_frame, summarise_groups
from core_modelling.eda.ranking import scope_statistics
from core_modelling.statistics.cells import pool_periods, target_shares
from core_modelling.statistics.concordance import CROSS_FIT_SE_INFLATION
from core_modelling.statistics.distributions import bin_labels, merge_bins
from core_modelling.tasks import TASK_SPECS

MIN_BIN_SUPPORT = 20  # events (units with a non-zero target) below which a group is greyed
DEEP_DIVE_GROUPS = 10  # the groups a numeric's bins are merged into (chart rule 4)
BOX_COLUMNS = ["rows", "q1", "median", "q3", "lower_whisker", "upper_whisker"]


def dive_group_count(kind: str, levels: int, max_levels: int) -> int | None:
    """How a feature's deep dive groups it: None, one group per level, for a categorical or a
    numeric with at most `max_levels` (`strata.max_levels`) distinct non-null eligible values
    (`levels`); else about `DEEP_DIVE_GROUPS` merged groups."""
    return None if kind == "categorical" or levels <= max_levels else DEEP_DIVE_GROUPS


def bin_orders(values: pd.Series, edges: np.ndarray | None) -> np.ndarray:
    """Each value's bucket on the interior `edges`, as the counts table's `Bucketizer` gives it
    (bucket i is `[e_i, e_{i+1})` over `[-inf, *edges, inf]`, `np.digitize`'s index; -0.0 as 0.0,
    ±inf in the outer buckets); -1 for a null or a NaN. No edges: every value in bucket 0."""
    numbers = values.to_numpy(dtype=float, na_value=np.nan) + 0.0
    orders = np.zeros(numbers.size, dtype=int) if edges is None else np.digitize(numbers, edges)
    return np.where(np.isnan(numbers), -1, orders)


def _merged(per_bin: pd.DataFrame, groups: int | None, edges: np.ndarray | None) -> pd.DataFrame:
    """The groups over `per_bin` (`bin_order`, `bin`, `n`): `merge_bins` into about `groups`, or
    every bin its own group when `groups` is None or no larger (also `merge_bins`' rule, kept here
    for a feature without a non-null value); `bin_order_first` and `label` in bin order, a
    group's label its outer range on `edges`."""
    if groups is None or len(per_bin) <= groups:
        return per_bin.sort_values("bin_order").rename(
            columns={"bin_order": "bin_order_first", "bin": "label"}
        )
    return merge_bins(per_bin[["bin_order", "n"]], groups, edges)


def value_labels(labels: list[str]) -> list[str]:
    """A numeric's group labels by value (`0`, `1`) when every group is one value (`= v`), else
    as given: a mass point among ranges keeps `= v`."""
    if labels and all(label.startswith("= ") for label in labels):
        return [label.removeprefix("= ") for label in labels]
    return labels


def _assign_groups(
    values: pd.Series, edges: np.ndarray | None, merged: pd.DataFrame, with_null: bool
) -> pd.Series:
    """Each value's group label (`value_labels` of the groups'; an ordered categorical in bin
    order, `null` last when `with_null`) by its bucket's place among the groups' first
    buckets."""
    orders = bin_orders(values, edges)
    place = np.searchsorted(merged["bin_order_first"].to_numpy(), orders, side="right") - 1
    filled = orders >= 0
    if (filled & (place < 0)).any() or (not with_null and not filled.all()):
        raise ValueError(f"{values.name}: a row falls outside the groups cut from its own bins")
    groups = value_labels(merged["label"].tolist())
    names = np.array([*groups, NULL_BIN], dtype=object)  # -1 picks null
    labels = names[np.where(filled, place, -1)]
    order = [*groups, *([NULL_BIN] if with_null else [])]
    return pd.Series(pd.Categorical(labels, categories=order, ordered=True), index=values.index)


def numeric_groups(values: pd.Series, edges: np.ndarray | None, groups: int | None) -> pd.Series:
    """A numeric's group labels over its own rows' buckets (`bin_order`, `bin` its label and `n`
    per bucket): merged into about `groups` (None: one group per bucket), null its own group last
    when there is one."""
    orders = bin_orders(values, edges)
    counts = pd.Series(orders[orders >= 0]).value_counts().sort_index()
    labels = bin_labels(np.array([]) if edges is None else edges)
    per_bin = pd.DataFrame(
        {"bin_order": counts.index, "bin": [labels[o] for o in counts.index], "n": counts.values}
    )
    merged = _merged(per_bin, groups, edges)
    return _assign_groups(values, edges, merged, bool(values.isna().any()))


def merged_groups(
    pooled: pd.DataFrame, edges: np.ndarray | None, groups: int | None
) -> pd.DataFrame:
    """A numeric's groups from one period's pooled cells (`pool_periods`): its non-null bins
    merged into about `groups` (None: one per bin; `_merged`: `bin_order_first`, `label`, …)."""
    values = pooled.loc[~pooled["is_null"]]
    per_bin = values.groupby(["bin_order", "bin"], as_index=False)["n"].sum()
    return _merged(per_bin, groups, edges)


def _known_groups(
    snapshot: pd.DataFrame, feature: str, kind: str, edges: np.ndarray | None, count: int | None
) -> pd.Series:
    """A feature's deep-dive group on each eligible row with a known target, cut over every
    eligible row: a categorical's `LEVEL_CAP` most frequent levels, then `__other__`; a numeric's
    buckets of `edges` merged into about `count` groups (None: one per bucket); null last."""
    values = snapshot.loc[snapshot["eligible"] == 1, feature]
    if kind == "categorical":
        groups = cap_levels(values, LEVEL_CAP)
    else:
        groups = numeric_groups(values, edges, count)
    return groups.loc[known_rows(snapshot).index]


def _group_table(
    target: pd.Series, groups: pd.Series, feature: str, task: str, base: float
) -> pd.DataFrame:
    """One row per category of `groups` in order (`feature, group`, the summary columns),
    `insufficient` below `MIN_BIN_SUPPORT`; a group without a known target keeps its row with no
    rows and no support, insufficient."""
    table = summarise_groups(target, groups.rename("group").to_frame(), task, base, MIN_BIN_SUPPORT)
    table = table.set_index("group").reindex(groups.cat.categories)
    table[["rows", "support"]] = table[["rows", "support"]].fillna(0)
    table["insufficient"] = table["insufficient"].astype("boolean").fillna(True).astype(bool)
    table = table.rename_axis("group").reset_index()
    return table.assign(feature=feature)[["feature", *table.columns]]


def bin_table(
    cells: pd.DataFrame,
    snapshot: pd.DataFrame,
    feature: str,
    edges: np.ndarray | None,
    snapshot_period: str,
    task: str,
    base: float,
    group_count: int,
) -> pd.DataFrame:
    """A numeric's deep dive: about `group_count` groups (`dive_group_count`'s; labelled by their
    outer range, null last) merged from the snapshot period's pooled cells, each summarised on
    the known rows mapped to it through `edges` against `base`. Columns: `feature, group`, then
    the task's summary columns."""
    current = cells.loc[(cells["feature"] == feature) & ~cells["lagged"]]
    pooled = pool_periods(current, [snapshot_period])
    with_null = bool(pooled.loc[pooled["is_null"], "n"].sum() > 0)
    known = known_rows(snapshot)
    merged = merged_groups(pooled, edges, group_count)
    groups = _assign_groups(known[feature], edges, merged, with_null)
    return _group_table(known["target"], groups, feature, task, base)


def level_table(
    snapshot: pd.DataFrame,
    feature: str,
    kind: str,
    edges: np.ndarray | None,
    task: str,
    base: float,
) -> pd.DataFrame:
    """A categorical's or a few-valued numeric's deep dive: one row per level (`_known_groups`
    with no merging), each summarised on the known rows against `base`; columns as
    `bin_table`'s."""
    groups = _known_groups(snapshot, feature, kind, edges, None)
    return _group_table(snapshot.loc[groups.index, "target"], groups, feature, task, base)


def _box(values: pd.Series) -> dict:
    """One box: rows, the quartiles and Tukey's whiskers (the furthest value within 1.5 IQR)."""
    q1, median, q3 = np.quantile(values, [0.25, 0.5, 0.75])
    reach = 1.5 * (q3 - q1)
    return {"rows": len(values), "q1": q1, "median": median, "q3": q3,
            "lower_whisker": values[values >= q1 - reach].min(),
            "upper_whisker": values[values <= q3 + reach].max()}  # fmt: skip


def box_table(values: pd.Series, groups: pd.Series | np.ndarray, column: str) -> pd.DataFrame:
    """One box per group of `values` in the groups' order (`column`, then `BOX_COLUMNS`; a group
    without a value has no row) and `skew`, the values' over every group (NaN below three
    values), so the caller can choose a log axis (and must check the whiskers are positive first,
    T30)."""
    parts = values.groupby(groups, observed=True, sort=True)
    records = [{column: name, **_box(part)} for name, part in parts]
    table = pd.DataFrame.from_records(records, columns=[column, *BOX_COLUMNS])
    numbers = values.to_numpy(dtype=float)
    return table.assign(skew=float(stats.skew(numbers)) if numbers.size >= 3 else np.nan)


def quartiles_by_target(snapshot: pd.DataFrame, feature: str, task: str) -> pd.DataFrame:
    """A numeric's box per target class (`TASK_SPECS[task]["target_class"]`) on the known rows'
    finite values (±infinity takes no part): `feature, target_class`, `BOX_COLUMNS` and `skew`
    (`box_table`)."""
    known = known_rows(snapshot)
    values = known[feature].to_numpy(dtype=float, na_value=np.nan)
    finite = np.isfinite(values)
    classes = TASK_SPECS[task]["target_class"](known["target"]).to_numpy()[finite]
    table = box_table(pd.Series(values[finite]), classes, "target_class")
    return table.assign(feature=feature)[["feature", *table.columns]]


def target_quartiles_by_group(
    snapshot: pd.DataFrame,
    feature: str,
    kind: str,
    edges: np.ndarray | None,
    group_count: int | None,
) -> pd.DataFrame:
    """An amount target's box per group of one feature (eda.md view 6) on the known rows, its
    groups `dive_group_count`'s: `level_table`'s for None, else `bin_table`'s, merged into
    about `group_count` over the eligible rows' buckets (which the snapshot period's cells
    count). Columns: `feature, group`, `BOX_COLUMNS` and `skew` (`box_table`)."""
    groups = _known_groups(snapshot, feature, kind, edges, group_count)
    table = box_table(snapshot.loc[groups.index, "target"].astype(float), groups, "group")
    return table.assign(feature=feature)[["feature", *table.columns]]


def per_period_concordance(
    cells: pd.DataFrame,
    feature: str,
    kind: str,
    task: str,
    window_periods: list[str],
    prior_rows: float,
    min_events: int,
    sign: int,
    exact: bool,
) -> pd.DataFrame:
    """Each window period's concordance of one feature, read in the raw sign of the window's D
    (the ranking's `raw_sign_window`: +1 or −1, so a flip reads below 0.5 and a noise feature
    still sits around 0.5; 0 when the window has no concordance, and then no period has one,
    its rows being a subset of the window's), a categorical's cross-fitted `read=[period]` in
    its encoding's direction; its SE on the period's own rows (a categorical's times
    `CROSS_FIT_SE_INFLATION`); `insufficient` below `min_events` support. Columns: `feature,
    period, rows` (labelled non-null rows), `support, concordance, se, insufficient,
    unavailable`."""
    if sign not in (1, -1, 0):
        raise ValueError(f"per_period_concordance: sign must be +1, -1 or 0, got {sign}")
    spec = TASK_SPECS[task]
    current = cells.loc[(cells["feature"] == feature) & ~cells["lagged"]]
    args = (task, window_periods, prior_rows, exact, None)
    records = []
    for period in window_periods:
        scope = scope_statistics(current, kind, [period], *args)
        events, non_events = scope["events"], scope["non_events"]
        value, se = np.nan, np.nan
        if not scope["reason"]:
            value = _read_in(scope, kind, sign)
            # Hanley–McNeil is not symmetric in A: a flipped period would look surer
            shares = target_shares(scope["pooled"])
            se = spec["concordance_se"](max(value, 1 - value), events, non_events, shares)
            se *= CROSS_FIT_SE_INFLATION if kind == "categorical" else 1
        reason = f"not available: {scope['reason']}" if scope["reason"] else ""
        records.append({"feature": feature, "period": period, "rows": events + non_events,
                        "support": events, "concordance": value, "se": se,
                        "insufficient": events < min_events, "unavailable": reason})  # fmt: skip
    return pd.DataFrame.from_records(records)


def _read_in(scope: dict, kind: str, sign: int) -> float:
    """A period's concordance in the window's direction: a categorical's as cross-fitted (its
    `sign` unread), a numeric's `signed` value flipped for sign −1; refused for sign 0, a window
    without a concordance."""
    if kind == "categorical":
        return scope["signed"]
    if sign == 0:
        raise ValueError("per_period_concordance: a period has a concordance the window lacks")
    return scope["signed"] if sign == 1 else 1 - scope["signed"]


def strata_pivots(
    snapshot: pd.DataFrame,
    features: list[str],
    edges: dict[str, np.ndarray | None],
    strata: Strata,
    task: str,
) -> pd.DataFrame:
    """Each of `features` (every key feature) × each stratum variable but itself (a diagonal) on
    the snapshot's eligible rows with a known target: one row per observed feature group (a
    numeric's buckets of `edges` grouped by `dive_group_count`, as its deep dive; a categorical
    capped at `strata.max_levels`) and stratum level, the summary columns against the snapshot's
    base, `insufficient` below `strata.min_events`; the long shape of `strata_tables`."""
    eligible = snapshot.loc[snapshot["eligible"] == 1]
    known = known_rows(snapshot)
    base = known["target"].mean()
    parts = []
    for feature in features:
        if feature in edges:
            count = dive_group_count("numeric", eligible[feature].nunique(), strata.max_levels)
            groups = numeric_groups(eligible[feature], edges[feature], count)
        else:
            groups = cap_levels(eligible[feature], strata.max_levels)
        for variable in [name for name in strata.variables if name != feature]:
            levels = cap_levels(eligible[variable], strata.max_levels)
            keys = pd.DataFrame({"feature_group": groups, "level": levels}).loc[known.index]
            table = summarise_groups(known["target"], keys, task, base, strata.min_events)
            parts.append(table.assign(variable=variable, feature=feature))
    return strata_frame(parts, task)
