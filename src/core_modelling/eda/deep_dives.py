"""The key features' deep dives and the strata pivots (docs/components/eda.md).

A deep dive reads the snapshot's eligible rows with a known target. `dive_group_count` is the
one rule for how it groups a feature: one row per level (a categorical, or a numeric with at
most `strata.max_levels` values), or a numeric's buckets (the counts table's `Bucketizer`
buckets, `bin_orders`) merged into about `strata.max_levels` groups (`numeric_groups`, a mass
point its own group, chart rule 4). `group_table` summarises each group with the per-task
summary columns, `quartiles_by_target` and `target_quartiles_by_group` give boxes
(`box_table`), and `concordance_per_period` gives every ranked candidate's concordance per window
period in the window's direction (stored, and read by Feature Checks' stability step). A group
below `MIN_BIN_SUPPORT` events (a strata cell below `strata.min_events`) is greyed, never hidden.
`strata_pivots` crosses every key feature's groups with each other stratum variable's levels.
`dive_group_count`, `numeric_groups`, `merged_groups`, `value_labels` and `box_table` are public
because `explore.py` cuts and draws the same groups.
"""

import numpy as np
import pandas as pd
from scipy import stats

from core_modelling.config.schema import Strata
from core_modelling.dataset.counts import LEVEL_CAP, NULL_BIN
from core_modelling.eda.population import cap_levels, known_rows, strata_frame, summarise_groups
from core_modelling.statistics.cells import group_of_bins
from core_modelling.statistics.distributions import bin_labels, merge_bins
from core_modelling.statistics.scope import scope_statistics
from core_modelling.tasks import TASK_SPECS

MIN_BIN_SUPPORT = 20  # events (units with a non-zero target) below which a group is greyed
BOX_COLUMNS = ["rows", "q1", "median", "q3", "lower_whisker", "upper_whisker"]


def dive_group_count(kind: str, levels: int, max_levels: int) -> int | None:
    """How a feature's deep dive groups it: None (one group per level) for a categorical or a
    numeric with at most `max_levels` (`strata.max_levels`) distinct non-null eligible values
    (`levels`), else `max_levels`, the number of merged groups to aim for."""
    return None if kind == "categorical" or levels <= max_levels else max_levels


def bin_orders(values: pd.Series, edges: np.ndarray | None) -> np.ndarray:
    """Each value's bucket on the interior `edges` as the counts table's `Bucketizer` gives it,
    `np.digitize`'s index (`[e_i, e_{i+1})`, -0.0 as 0.0); -1 for a null or NaN; 0 without
    edges."""
    numbers = values.to_numpy(dtype=float, na_value=np.nan) + 0.0
    orders = np.zeros(numbers.size, dtype=int) if edges is None else np.digitize(numbers, edges)
    return np.where(np.isnan(numbers), -1, orders)


def _merged(per_bin: pd.DataFrame, groups: int | None, edges: np.ndarray | None) -> pd.DataFrame:
    """The groups over `per_bin` (one row per bin: `bin_order, bin, n`), one row per group in bin
    order with `bin_order_first` and `label` (its outer range on `edges`): `merge_bins` into about
    `groups`, or every bin its own group when `groups` is None or no larger (also `merge_bins`'
    rule, kept here for a feature without a non-null value)."""
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


def _assign_groups(values: pd.Series, edges: np.ndarray | None, merged: pd.DataFrame) -> pd.Series:
    """Each value's group label (`value_labels` of the groups'; an ordered categorical in bin
    order, `null` last when a value is null) by its bucket's place among the groups' first
    buckets; `merged` is cut from the same values, so every bucket has its group."""
    orders = bin_orders(values, edges)
    filled = orders >= 0
    place = np.full(orders.size, -1)  # -1 picks null
    place[filled] = group_of_bins(merged["bin_order_first"].to_numpy(), orders[filled])
    groups = value_labels(merged["label"].tolist())
    names = np.array([*groups, NULL_BIN], dtype=object)
    labels = names[place]
    order = [*groups, *([] if filled.all() else [NULL_BIN])]
    return pd.Series(pd.Categorical(labels, categories=order, ordered=True), index=values.index)


def numeric_groups(values: pd.Series, edges: np.ndarray | None, groups: int | None) -> pd.Series:
    """Each value's group label, an ordered categorical on `values`' index: its buckets on
    `edges`, counted over `values` itself and merged into about `groups` (None: one group per
    bucket); null its own group, last, when there is one."""
    orders = bin_orders(values, edges)
    counts = pd.Series(orders[orders >= 0]).value_counts().sort_index()
    labels = bin_labels(np.array([]) if edges is None else edges)
    per_bin = pd.DataFrame(
        {"bin_order": counts.index, "bin": [labels[o] for o in counts.index], "n": counts.values}
    )
    merged = _merged(per_bin, groups, edges)
    return _assign_groups(values, edges, merged)


def merged_groups(
    pooled: pd.DataFrame, edges: np.ndarray | None, groups: int | None
) -> pd.DataFrame:
    """A numeric's groups from one period's pooled cells (`pool_periods`), one row per group: its
    non-null bins, `n` summed over the target bins, merged into about `groups` (None: one per
    bin; columns as `_merged` gives them, `bin_order_first` and `label` among them)."""
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


def group_table(
    snapshot: pd.DataFrame,
    feature: str,
    kind: str,
    edges: np.ndarray | None,
    task: str,
    base: float,
    group_count: int | None,
) -> pd.DataFrame:
    """A key feature's deep dive, one row per group in group order, null last (`_known_groups`: by
    level when `group_count` is None, else about `group_count` merged from the eligible rows'
    buckets, as the snapshot period's cells count them). Columns: `feature, group`, then the
    task's summary columns on the known rows against `base`, `insufficient` below
    `MIN_BIN_SUPPORT`. A group without a known target keeps its row with 0 rows and support,
    insufficient."""
    groups = _known_groups(snapshot, feature, kind, edges, group_count)
    target = snapshot.loc[groups.index, "target"]
    table = summarise_groups(target, groups.rename("group").to_frame(), task, base, MIN_BIN_SUPPORT)
    table = table.set_index("group").reindex(groups.cat.categories)
    table[["rows", "support"]] = table[["rows", "support"]].fillna(0)
    table["insufficient"] = table["insufficient"].astype("boolean").fillna(True).astype(bool)
    table = table.rename_axis("group").reset_index()
    return table.assign(feature=feature)[["feature", *table.columns]]


def _box(values: pd.Series) -> dict:
    """One box: rows, the quartiles and Tukey's whiskers (the furthest value within 1.5 IQR)."""
    q1, median, q3 = np.quantile(values, [0.25, 0.5, 0.75])
    reach = 1.5 * (q3 - q1)
    return {"rows": len(values), "q1": q1, "median": median, "q3": q3,
            "lower_whisker": values[values >= q1 - reach].min(),
            "upper_whisker": values[values <= q3 + reach].max()}  # fmt: skip


def box_table(values: pd.Series, groups: pd.Series | np.ndarray, column: str) -> pd.DataFrame:
    """One box per group of `values` in the groups' order (`column`, then `BOX_COLUMNS`; an empty
    group has no row), and `skew`, the skewness of all `values` (NaN below three), from which the
    caller picks a log axis once it has checked the whiskers are positive (T30)."""
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
    """An amount target's box per group of one feature (eda.md view 6) on the known rows, grouped
    as `group_table` groups it. Columns: `feature, group`, `BOX_COLUMNS` and `skew`
    (`box_table`)."""
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
    """One feature's concordance per window period, one row each, read in `sign`, the window's
    raw sign (`raw_sign_window`), so a flip reads below 0.5 and noise stays near 0.5; a
    categorical's is cross-fitted (`read=[period]`) in its encoding's direction. `sign` 0 means
    the window has no concordance, so no period has one (its rows are a subset). The SE is the
    scope's on the period's own rows (`feature_se` at max(value, 1 − value), so the sign leaves
    it unchanged). Columns: `feature, period, rows` (labelled non-null rows), `support,
    concordance, se, insufficient` (support below `min_events`), `unavailable`."""
    if sign not in (1, -1, 0):
        raise ValueError(f"per_period_concordance: sign must be +1, -1 or 0, got {sign}")
    current = cells.loc[(cells["feature"] == feature) & ~cells["lagged"]]
    args = (task, window_periods, prior_rows, exact, None)
    records = []
    for period in window_periods:
        scope = scope_statistics(current, kind, [period], *args)
        events, non_events = scope["events"], scope["non_events"]
        value = np.nan if scope["reason"] else _read_in(scope, kind, sign)
        reason = f"not available: {scope['reason']}" if scope["reason"] else ""
        records.append({"feature": feature, "period": period, "rows": events + non_events,
                        "support": events, "concordance": value, "se": scope["se"],
                        "insufficient": events < min_events, "unavailable": reason})  # fmt: skip
    return pd.DataFrame.from_records(records)


def concordance_per_period(
    cells: pd.DataFrame,
    ranking: pd.DataFrame,
    task: str,
    window_periods: list[str],
    prior_rows: float,
    min_events: int,
    exact: bool,
) -> pd.DataFrame:
    """`per_period_concordance` of every feature of `ranking` in its order, each read in its
    `raw_sign_window`, stacked (`per_period_concordance`'s columns)."""
    current = cells.loc[~cells["lagged"]]
    by_feature = dict(tuple(current.groupby("feature")))  # one pass, not one filter per feature
    settings = {"task": task, "window_periods": window_periods, "prior_rows": prior_rows,
                "min_events": min_events, "exact": exact}  # fmt: skip
    parts = [
        per_period_concordance(by_feature[row.feature], row.feature, row.kind,
                               sign=int(row.raw_sign_window), **settings)
        for row in ranking.itertuples()
    ]  # fmt: skip
    return pd.concat(parts, ignore_index=True)


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
    """One long table in `strata_tables`' shape: for each of `features` (every key feature) ×
    each stratum variable but itself (a diagonal), one row per observed feature group and stratum
    level on the snapshot's eligible rows with a known target. A numeric is grouped as its deep
    dive groups it (`dive_group_count` over `edges`), a categorical capped at
    `strata.max_levels`; the summary columns against the snapshot's base, `insufficient` below
    `strata.min_events`."""
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
