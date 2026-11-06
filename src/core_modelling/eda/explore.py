"""The exploration functions a reader calls on a stage result; they read `result` only and change
nothing (docs/components/eda.md "Interface", notebook 02 step 7).

`pivot_target` summarises the target by any snapshot columns; `lift_by_group` draws a column's
lift by group, or one line per group of a second column; `compare_sides` sets a modelling
filter's excluded rows against the modelling population; `rate_by_period` follows a candidate's
groups through the window periods from the stage's cells, so the window stays uncollected. They
read every label statistic on the snapshot's eligible rows with a known target and draw with the
report's chart builders. A numeric is cut as its deep dive cuts it (`dive_group_count` over the
stage's edges). A categorical keeps its most frequent levels, the rest `__other__`, null its own
group, last:
- `LEVEL_CAP` as `lift_by_group`'s feature without `by`, as its deep dive caps it (the group
  chart and the level table);
- `strata.max_levels` as `lift_by_group`'s feature and its `by` together, as the strata chart
  and pivot cap them;
- `strata.max_levels` in `pivot_target`, `compare_sides` and `rate_by_period` (one line per
  level: fifty lines would not read).
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from pandas.io.formats.style import Styler

from core_modelling.artifacts import StageResult
from core_modelling.dataset.counts import LEVEL_CAP, NEW, NULL_BIN, OTHER, bin_edges
from core_modelling.eda.deep_dives import (
    MIN_BIN_SUPPORT,
    box_table,
    dive_group_count,
    merged_groups,
    numeric_groups,
    value_labels,
)
from core_modelling.eda.population import (
    cap_levels,
    is_numeric,
    known_rows,
    reference_sides,
    summarise_groups,
)
from core_modelling.eda.report import boxes, group_chart, strata_chart
from core_modelling.reporting import charts
from core_modelling.reporting.html import style_table
from core_modelling.statistics.cells import pool_periods, zero_target_bins
from core_modelling.statistics.distributions import quantile_edges, range_label
from core_modelling.tasks import TASK_SPECS

PIVOT_BINS = 10  # the quantile bins of a numeric pivot dimension


def pivot_target(
    result: StageResult,
    rows: str | list[str],
    columns: str | None = None,
    where: str | None = None,
) -> Styler:
    """The target's summary by the `rows` dimensions (optionally against `columns`) over the
    stage result's snapshot rows that are eligible with a known target, after a `DataFrame.query`
    filter `where` (a bank-style name in backticks); a numeric dimension cut into ten quantile
    bins, a categorical capped at `strata.max_levels`; estimates coloured by their lift against
    the snapshot's base, cells below `strata.min_events` greyed. A candidate's kind is the
    ledger's; any other column's comes from its dtype (numeric, not boolean, is binned)."""
    cfg = result.config
    row_dims = [rows] if isinstance(rows, str) else list(rows)
    if not row_dims:
        raise ValueError("pivot_target: rows names no column; give one column or a list of them")
    dims = row_dims + ([columns] if columns else [])
    _check_columns(result, dims)
    if len(set(dims)) < len(dims):
        raise ValueError(f"pivot_target: dimensions {dims} must be distinct")
    known = known_rows(result.frame)
    base = known["target"].mean()
    data = known.query(where) if where else known
    if data.empty:
        raise ValueError(
            f"pivot_target: where={where!r} leaves no eligible row with a known target"
        )
    keys = pd.DataFrame(
        {dim: _dimension(data[dim], _kind(result, dim), cfg.strata.max_levels) for dim in dims}
    )
    table = summarise_groups(data["target"], keys, cfg.task, base, cfg.strata.min_events)
    # The keys come back as text: as ordered categoricals they keep their order when unstacked
    # (bins in bin order, levels by rows, null last), not the text's.
    table = table.astype({dim: keys[dim].dtype for dim in dims})
    return _styled_pivot(table, row_dims, columns, cfg.task, base, cfg.strata.min_events)


def _check_columns(result: StageResult, names: list[str]) -> None:
    """Refuse a name that is not a column of the stage result's snapshot, naming its columns."""
    unknown = [name for name in names if name not in result.frame.columns]
    if unknown:
        raise ValueError(
            f"{unknown} are not columns of the stage result's snapshot; its columns: "
            f"{list(result.frame.columns)}"
        )


def _kind(result: StageResult, name: str) -> str | None:
    """A candidate's kind from the ledger; None for any other column."""
    return result.ledger.set_index("feature")["kind"].get(name)


def _dimension(values: pd.Series, kind: str | None, max_levels: int) -> pd.Series:
    """A pivot dimension's labels: a numeric cut into `PIVOT_BINS` quantile bins (each value its
    own bin when it has that few), a categorical capped at `max_levels`, null a level."""
    if not is_numeric(values, kind):
        return cap_levels(values, max_levels)
    edges = quantile_edges(values.dropna().to_numpy(dtype=float), PIVOT_BINS)
    return numeric_groups(values, edges, None)


def _styled_pivot(
    table: pd.DataFrame,
    row_dims: list[str],
    column: str | None,
    task: str,
    base: float,
    min_events: int,
) -> Styler:
    """The pivot styled: a long table (rows, support, estimate, lift) without `column`, else the
    estimate with one column per level; lift colours, insufficient greyed."""
    spec = TASK_SPECS[task]
    estimate = spec["estimate_format"]
    indexed = table.set_index(row_dims if column is None else [*row_dims, column])
    if column is None:
        shown = indexed[["rows", "support", "estimate", "lift"]]
        lift = indexed[["lift"]].rename(columns={"lift": "estimate"})
        greyed = indexed["insufficient"]
        formats = {"rows": "{:,.0f}", "support": "{:,.0f}", "estimate": estimate, "lift": "{:.2f}"}
    else:
        shown, lift = (indexed[name].unstack(column) for name in ("estimate", "lift"))
        greyed = indexed["insufficient"].unstack(column).astype("boolean").fillna(True).astype(bool)
        formats = dict.fromkeys(shown.columns, estimate)
    caption = (
        f"The target's estimate by {', '.join(row_dims + ([column] if column else []))}: coloured "
        f"by lift against the snapshot's base {estimate.format(base)}, greyed below "
        f"strata.min_events = {min_events} {spec['support_name']}"
    )
    return style_table(shown, formats=formats, lift=lift, greyed=greyed, caption=caption)


def _groups_of(result: StageResult, name: str, categorical_cap: int) -> pd.Series:
    """A snapshot column's group labels on the eligible rows: a numeric (a candidate by its kind,
    any other column by its dtype) as its deep dive cuts it (`_numeric_cut`), a categorical's
    `categorical_cap` most frequent levels; null last."""
    values = result.frame.loc[result.frame["eligible"] == 1, name]
    if not is_numeric(values, _kind(result, name)):
        return cap_levels(values, categorical_cap)
    return numeric_groups(values, *_numeric_cut(result, name))


def _numeric_cut(result: StageResult, name: str) -> tuple[np.ndarray | None, int | None]:
    """A numeric's edges as the stage cut them (`bin_edges` on the same eligible rows gives the
    same edges) and its deep-dive group count (`dive_group_count` on its distinct eligible
    values, as the ranking's `levels` counts them)."""
    frame, cfg = result.frame, result.config
    levels = frame.loc[frame["eligible"] == 1, name].nunique()
    edges = bin_edges(frame, {name: "numeric"}, cfg.eda.bins)[name]
    return edges, dive_group_count("numeric", levels, cfg.strata.max_levels)


def lift_by_group(result: StageResult, feature: str, by: str | None = None) -> go.Figure:
    """A snapshot column's lift by group against the snapshot's base (the estimate when no lift
    exists) on the eligible rows with a known target, greyed below `MIN_BIN_SUPPORT`; with `by`
    (another column: a column against its own levels is a diagonal), one line per group of `by`
    over the feature's groups (a categorical feature capped at `strata.max_levels`, as the
    strata pivots cap it), greyed below `strata.min_events`: a `by` of at most
    `strata.max_levels` values one line per value labelled as the strata tables label it."""
    _check_columns(result, [feature] + ([by] if by else []))
    if by == feature:
        raise ValueError(f"lift_by_group: by={by!r} is the feature itself; pick another column")
    cfg = result.config
    known = known_rows(result.frame)
    base = known["target"].mean()
    max_levels = cfg.strata.max_levels
    groups = _groups_of(result, feature, LEVEL_CAP if by is None else max_levels)
    groups = groups.loc[known.index]
    if by is None:
        keys = groups.to_frame("group")
        table = summarise_groups(known["target"], keys, cfg.task, base, MIN_BIN_SUPPORT)
        return group_chart(table, feature, base, cfg.task)
    by_values = result.frame.loc[result.frame["eligible"] == 1, by]
    # A numeric `by` with few values is labelled as a stratum (`1`, not `= 1`), else by its
    # deep-dive groups.
    if by_values.nunique() <= max_levels:
        levels = cap_levels(by_values, max_levels).loc[known.index]
    else:
        levels = _groups_of(result, by, max_levels).loc[known.index]
    keys = pd.DataFrame({"feature_group": groups, "level": levels})
    table = summarise_groups(known["target"], keys, cfg.task, base, cfg.strata.min_events)
    order = list(levels.cat.remove_unused_categories().cat.categories)
    return strata_chart(table, feature, by, base, cfg.task, order)


def compare_sides(result: StageResult, feature: str, tag: str) -> go.Figure:
    """A snapshot column on the two sides of a modelling filter, on every snapshot row as the
    reference groups take them (`reference_sides`): the rows the tag excludes (`tag == 0`)
    against the modelling population (`eligible == 1`), refused when a side has no row. A
    numeric: one box per side of its finite values (a log axis by the deep dives' rule); a
    categorical: each level's share of the side's rows, one line per side (`strata.max_levels`
    levels, null last)."""
    tags = list(result.tables["reference_groups"]["tag"].unique())
    if tag not in tags:
        known = f"the tags: {tags}" if tags else "the config has no modelling filter"
        raise ValueError(f"compare_sides: {tag!r} is not a modelling tag; {known}")
    _check_columns(result, [feature])
    frame = result.frame
    sides = reference_sides(frame, tag)
    empty = [side for side, mask in sides.items() if not mask.any()]
    if empty:
        side = " and ".join(empty)
        raise ValueError(f"compare_sides: the {side} side of {tag} has no snapshot row")
    title = f"{feature} by side of {tag}"
    if is_numeric(frame[feature], _kind(result, feature)):
        return boxes(_side_quartiles(frame[feature], sides), "side", title, "side", feature)
    levels = cap_levels(frame[feature], result.config.strata.max_levels)
    rows = pd.DataFrame(
        {side: levels[mask].value_counts(sort=False) for side, mask in sides.items()}
    )
    shares = (rows / rows.sum()).rename_axis("level").reset_index()
    return charts.grouped_lines(
        shares.melt("level", var_name="side"), "level", "value", group="side", insufficient=None,
        title=title, x_title=feature, y_title="Share of rows", legend_title=tag,
    )  # fmt: skip


def _side_quartiles(values: pd.Series, sides: dict[str, pd.Series]) -> pd.DataFrame:
    """One box per side of a numeric's finite values (`box_table`); refused when a side has none,
    naming it."""
    finite = np.isfinite(values.to_numpy(dtype=float, na_value=np.nan))
    parts = pd.concat({side: values[mask & finite] for side, mask in sides.items()})
    side = pd.Categorical(parts.index.get_level_values(0), categories=list(sides))
    quartiles = box_table(parts.astype(float), side, "side")
    missing = [side for side in sides if side not in set(quartiles["side"])]
    if missing:
        raise ValueError(
            f"compare_sides: {values.name} has no finite value on the {' and '.join(missing)} side"
        )
    return quartiles


def rate_by_period(result: StageResult, feature: str) -> go.Figure:
    """A candidate's target per window period by its groups (`_cell_groups`: a numeric's the deep
    dive's, a categorical's capped at `strata.max_levels`, not the deep dive's `LEVEL_CAP`, so the
    lines stay readable), from the stage's cells (the window stays uncollected): per period and
    group the rows with a known target, the events (a non-zero target) and the estimate, greyed
    below `MIN_BIN_SUPPORT` events."""
    cells = result.tables["cells"]
    candidates = sorted(cells["feature"].unique())
    if feature not in candidates:
        raise ValueError(
            f"rate_by_period: {feature!r} is not a candidate with cells; the candidates: "
            f"{candidates}"
        )
    window = result.meta["compared_periods"]["window"]
    current = cells.loc[(cells["feature"] == feature) & ~cells["lagged"]]
    labelled = current.loc[current["period"].isin(window) & current["target_bin"].notna()]
    groups, order = _cell_groups(result, feature, current, labelled)
    zero = labelled["target_bin"].isin(zero_target_bins(labelled))
    data = labelled.assign(group=groups, events=labelled["n"].where(~zero, 0))
    sums = data.groupby(["group", "period"])[["n", "events", "sum_y"]].sum()
    present = set(groups)
    grid = pd.MultiIndex.from_product(
        [[g for g in order if g in present], window], names=["group", "period"]
    )
    table = sums.reindex(grid, fill_value=0).reset_index()
    table = table.assign(
        estimate=table["sum_y"] / table["n"], insufficient=table["events"] < MIN_BIN_SUPPORT
    )
    spec = TASK_SPECS[result.config.task]
    return charts.grouped_lines(
        table, "period", "estimate", group="group", title=f"{feature}: target per window period",
        x_title="Period", y_title=f"Target {spec['estimate_noun']}", legend_title=feature,
        y_format=spec["axis_format"],
    )  # fmt: skip


def _cell_groups(
    result: StageResult, feature: str, current: pd.DataFrame, labelled: pd.DataFrame
) -> tuple[np.ndarray, list[str]]:
    """Each `labelled` cell's group and the groups' order, null last. A numeric's are the deep
    dive's (`_numeric_cut`), cut from the snapshot period's cells over the stage's edges; a cell
    joins the group its bucket falls in by `searchsorted` on the groups' first buckets, so another
    period's value in a bucket empty at the snapshot period joins the group below, and one below
    the first group joins the first. Each group is labelled by the buckets it receives
    (`_received_labels`), which can be wider than its deep-dive label. A categorical's are the
    snapshot period's `strata.max_levels` most frequent levels (ties by label), the rest
    `__other__` (`__new__` among them)."""
    snapshot = pool_periods(current, [result.meta["snapshot_period"]])
    null = labelled["is_null"].to_numpy()
    if _kind(result, feature) == "numeric":
        edges, count = _numeric_cut(result, feature)
        merged = merged_groups(snapshot, edges, count)
        if merged.empty and not null.all():
            raise ValueError(
                f"rate_by_period: {feature} has no value in the snapshot period to cut groups from"
            )
        orders = labelled["bin_order"].to_numpy()
        place = np.searchsorted(merged["bin_order_first"].to_numpy(), orders, side="right") - 1
        place = np.where(null, -1, np.maximum(place, 0))  # -1: null
        received = _received_labels(merged, place, orders, edges)
        names = np.array([*received, NULL_BIN], dtype=object)
        return names[place], list(names)
    counts = snapshot.loc[~snapshot["is_null"]].groupby("bin")["n"].sum()
    counts = counts.drop([OTHER, NEW], errors="ignore").sort_index()
    max_levels = result.config.strata.max_levels
    kept = list(counts.sort_values(ascending=False, kind="stable").index[:max_levels])
    labels = np.where(labelled["bin"].isin(kept), labelled["bin"], OTHER)
    return np.where(null, NULL_BIN, labels), [*kept, OTHER, NULL_BIN]


def _received_labels(
    merged: pd.DataFrame, place: np.ndarray, orders: np.ndarray, edges: np.ndarray | None
) -> list[str]:
    """Each group's label by the occupied buckets it receives across the window (`place`: each
    cell's group, `orders`: its bucket), their range from the lowest to the highest
    (`range_label`), so a value no snapshot row took is never counted under a narrower label; a
    group receiving exactly its deep-dive buckets, or none (drawn by no line), reads as in its
    deep dive (`value_labels`: `1` for a by-level numeric's value)."""
    edges = np.array([]) if edges is None else edges
    raw = merged["label"].tolist()
    shown = dict(zip(raw, value_labels(raw), strict=True))
    labels = []
    for group, own in enumerate(raw):
        buckets = orders[place == group]
        labels.append(range_label(edges, buckets.min(), buckets.max()) if buckets.size else own)
    return [shown.get(label, label) for label in labels]
