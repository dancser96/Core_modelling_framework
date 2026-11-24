"""The four SHAP-style explanation charts, drawn in plotly from the model libraries' own
per-feature contributions (D-141 (f), docs/components/reporting.md "The explanation charts").

Training's sign-off view and Evaluation's report both draw them from stored contributions, so
the notebook and the report cannot differ, and the package imports no `shap`. A contributions
frame holds one row per sampled row and one column per feature, each the feature's contribution
to the margin (no base column); a values frame holds the same rows and columns with the raw
feature values (numbers, level texts, nulls). The charts take shap's colours
(`THEME["contribution"]`: red raises, blue lowers, blue to red for a low to high value, grey for
a missing value) and the house fonts, titles and margins (`charts.apply_theme`). The beeswarm
and the dependence scatter are the named row-level exceptions to "every figure is
pre-aggregated" (requirement 5): each draws at most `ROW_CAP` seeded rows per feature. Beside
them, `pdp_ice_chart` draws Evaluation's partial dependence and ICE table. Traces are SVG only,
as in `charts.py`.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core_modelling.reporting import charts
from core_modelling.reporting.charts import NULL_LABEL, apply_theme
from core_modelling.reporting.formats import plain_number
from core_modelling.reporting.model_charts import part_colour
from core_modelling.reporting.theme import THEME
from core_modelling.statistics.intervals import t_interval
from core_modelling.statistics.score_cells import PARTS

ROW_CAP = 1500  # rows the beeswarm and the dependence scatter draw per feature (requirement 5)
SEED = 0  # the dependence scatter's sample and jitter
SWARM_HEIGHT = 0.42  # half the height of a beeswarm row, in rows
MARKER_SIZE = 5
# A hover number in d3's decimal notation (`r`, never an exponent) to four significant digits with
# thousands separators and no trailing zeros: `plain_number`'s digits up to 9,999, where it keeps
# every integer digit and this rounds (123,456 reads 123,500). Per-point text would grow the page.
HOVER_FORMAT = ",.4~r"
MIN_GROUP_ROWS = 20  # sample rows below which a group's mean contribution is greyed
# The importance bars' parts when `compare` is given, coloured as the model charts colour theirs
PART_NAMES = (PARTS[0], "train, out of fold")
PART_ORDER = [*PARTS, PART_NAMES[1]]
LIFT_COLUMNS = ["group", "lift", "lift_low", "lift_high", "support", "insufficient"]
# `effect_chart`'s mean-contribution columns, by `group_means`' names for them
MEAN_COLUMNS = {"mean_contribution": "estimate", "mean_low": "low", "mean_high": "high",
                "sample_rows": "support", "sample_insufficient": "insufficient"}  # fmt: skip


def _check_contributions(
    contributions: pd.DataFrame | pd.Series, *others: pd.DataFrame | pd.Series | None
) -> None:
    """Fail unless the contributions hold a value and no null, and every other frame or series
    carries their labels (the index, and the columns of a frame), in order."""
    if contributions.empty:
        raise ValueError("explanation charts: the contributions hold no row or no feature")
    if contributions.isna().to_numpy().any():
        raise ValueError("explanation charts: a contribution is null; a model's never is")
    for other in others:
        if other is None:
            continue
        same = other.index.equals(contributions.index)
        if isinstance(other, pd.DataFrame):
            same = same and other.columns.equals(contributions.columns)
        if not same:
            raise ValueError(
                "explanation charts: the values (or colour) must carry the contributions' row "
                "and feature labels, in the same order"
            )


def _ranked(contributions: pd.DataFrame) -> pd.Index:
    """The features by mean absolute contribution, largest first (ties in column order)."""
    return contributions.abs().mean().sort_values(ascending=False, kind="stable").index


def _sample_rows(rows: int, cap: int, seed: int) -> np.ndarray:
    """At most `cap` seeded row positions out of `rows`, in row order; every row when they fit."""
    if rows <= cap:
        return np.arange(rows)
    return np.sort(np.random.default_rng(seed).choice(rows, size=cap, replace=False))


def _is_numeric(values: pd.Series) -> bool:
    """Whether a feature's values are numbers (ordered, so coloured low to high)."""
    return pd.api.types.is_numeric_dtype(values)


def _format_value(value: object) -> str:
    """A feature value as a label shows it: `null` when missing, a number through
    `plain_number` (never scientific notation), a level as its text."""
    if pd.isna(value):
        return NULL_LABEL
    if isinstance(value, int | float | np.number) and not isinstance(value, bool):
        return plain_number(value)
    return str(value)


def _clip_range(known: np.ndarray) -> tuple[float, float]:
    """A feature's colour range: its 5th to 95th percentile, widened to the 1st to 99th, then
    to the whole span, when it collapses (shap's rule); one unit wide for a single value."""
    for q in (5, 1, 0):
        low, high = np.percentile(known, q), np.percentile(known, 100 - q)
        if low < high:
            return float(low), float(high)
    return float(low), float(low) + 1.0


def _unit_colour(values: pd.Series) -> np.ndarray | None:
    """Each value's place on the low-to-high colour scale, in [0, 1] (NaN when missing); None
    when the values have no order to colour by (a categorical) or none is known."""
    if not _is_numeric(values) or values.isna().all():
        return None
    numbers = values.to_numpy(dtype=float, na_value=np.nan)
    low, high = _clip_range(numbers[~np.isnan(numbers)])
    return np.clip((numbers - low) / (high - low), 0.0, 1.0)


def _add_points(
    fig: go.Figure,
    x: np.ndarray,
    y: np.ndarray,
    by: pd.Series | None,
    hover: str,
    scale_title: str,
    show_scale: bool,
    axes: dict,
) -> bool:
    """Points at (x, y), coloured by `by` (the same rows): a missing value grey, drawn first so
    the coloured points sit on top as in shap; a number on the low-to-high scale; a categorical,
    or no `by`, in the neutral colour. `hover` is the hover's fixed part, `by`'s value is added
    to it. Returns whether the colour bar was drawn."""
    palette = THEME["contribution"]
    # Single precision halves a beeswarm in the report (about 0.5 MB at 1,500 rows x 15 features)
    x, y = np.asarray(x, dtype="float32"), np.asarray(y, dtype="float32")
    missing = np.zeros(len(x), dtype=bool) if by is None else by.isna().to_numpy()
    unit = None if by is None else _unit_colour(by)
    common = {"mode": "markers", "showlegend": False, **axes}
    named = "" if by is None else f"<br>{by.name} = "
    if missing.any():
        fig.add_trace(go.Scatter(
            x=x[missing], y=y[missing], marker={"color": palette["missing"], "size": MARKER_SIZE},
            hovertemplate=f"{hover}{named}{NULL_LABEL}<extra></extra>", **common,
        ))  # fmt: skip
    kept = ~missing
    if not kept.any():
        return False
    marker = {"color": palette["neutral"], "size": MARKER_SIZE}
    if unit is not None:
        marker = {"color": unit[kept].astype("float32"), "colorscale": palette["scale"],
                  "cmin": 0, "cmax": 1, "size": MARKER_SIZE, "showscale": show_scale,
                  "colorbar": {"title": {"text": scale_title, "side": "right"}, "tickvals": [0, 1],
                               "ticktext": ["Low", "High"], "thickness": 12, "len": 0.9,
                               "outlinewidth": 0}}  # fmt: skip
    data, value = (None, "") if by is None else _hover_values(by[kept])
    fig.add_trace(go.Scatter(x=x[kept], y=y[kept], marker=marker, customdata=data,
                             hovertemplate=f"{hover}{named}{value}<extra></extra>",
                             **common))  # fmt: skip
    return unit is not None and show_scale


def _hover_values(by: pd.Series) -> tuple[np.ndarray, str]:
    """`by`'s known values as hover data and their placeholder: numbers as compact floats shown
    in `HOVER_FORMAT`, levels as text."""
    if _is_numeric(by):
        return by.to_numpy(dtype="float32"), f"%{{customdata:{HOVER_FORMAT}}}"
    return by.astype(str).to_numpy(), "%{customdata}"


def importance_bar(
    contributions: pd.DataFrame, compare: pd.DataFrame | None = None, top: int = 15
) -> go.Figure:
    """Each feature's share of the mean absolute contribution (its mean |contribution| over every
    row, divided by the sum across the frame's features), the `top` largest first and the rest's
    share in one bar; `compare` (train out of fold beside test, the same features) as a second
    bar per feature, its shares from its own frame so the two compare, in the main frame's
    order. Receives one row per sampled row and one column per feature."""
    _check_contributions(contributions)
    parts = [(contributions, "the contributions hold")]
    if compare is not None:
        _check_contributions(compare)
        if set(compare.columns) != set(contributions.columns):
            raise ValueError("importance_bar: compare must hold the same features")
        parts.append((compare, "compare holds"))
    ranked = _ranked(contributions)
    shown, others = list(ranked[:top]), list(ranked[top:])
    labels = shown + ([f"Sum of {len(others)} other features"] if others else [])
    fig, highest = go.Figure(), 0.0
    for (frame, which), name in zip(parts, PART_NAMES[: len(parts)], strict=True):
        mean = frame.abs().mean()
        if mean.sum() == 0:  # the shares would be 0 / 0
            raise ValueError(f"importance_bar: {which} only zero contributions")
        share = mean / mean.sum()
        part = f" ({name})" if compare is not None else ""  # a lone sample is not named
        heights = [*share[shown]] + ([share[others].sum()] if others else [])
        highest = max(highest, *heights)
        fig.add_trace(go.Bar(
            x=heights, y=labels, orientation="h", name=name if part else None,
            marker_color=part_colour(name, PART_ORDER),
            text=[f"{h:.1%}" for h in heights], textposition="outside", cliponaxis=False,
            hovertemplate=f"%{{y}}: %{{x:.1%}}{part}<extra></extra>",
        ))  # fmt: skip
    height = 26 * len(labels) * len(parts) + 140
    x_title = "Share of the mean |contribution| to the margin"
    apply_theme(fig, "Global feature importance", x_title, "Feature", height)
    fig.update_layout(showlegend=compare is not None, barmode="group")
    fig.update_xaxes(showgrid=False, range=[0, 1.15 * highest], ticks="outside", tickformat=".0%")
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return fig


def _swarm_offsets(x: np.ndarray, rng: np.random.Generator, bins: int = 100) -> np.ndarray:
    """Vertical offsets in (-1, 1) for one beeswarm row: points sharing one of `bins` x bins
    stack alternately above and below the row's centre, in random order within the bin."""
    place = np.round(bins * (x - x.min()) / (x.max() - x.min() + 1e-8)).astype(int)
    order = np.lexsort((rng.random(len(x)), place))  # by bin, random within the bin
    starts = np.r_[0, np.flatnonzero(np.diff(place[order])) + 1]
    layer = np.arange(len(x)) - np.repeat(starts, np.diff(np.r_[starts, len(x)]))
    offsets = np.empty(len(x))
    offsets[order] = np.ceil(layer / 2) * ((layer % 2) * 2 - 1)
    return offsets / (np.abs(offsets).max() + 1)


def beeswarm(
    contributions: pd.DataFrame,
    values: pd.DataFrame,
    top: int = 15,
    clients: int = ROW_CAP,
    seed: int = 0,
) -> go.Figure:
    """One row per feature (the `top` by mean absolute contribution over every row), one point
    per sampled row at its contribution, coloured by the feature's value; at most `clients`
    seeded rows, the same rows for every feature. Receives the contributions and the raw values,
    one row per sampled row and one column per feature."""
    _check_contributions(contributions, values)
    if not 1 <= clients <= ROW_CAP:
        raise ValueError(
            f"beeswarm: clients must be between 1 and {ROW_CAP:,} per feature (requirement 5); "
            f"got {clients}"
        )
    features = list(_ranked(contributions)[:top])
    rows = _sample_rows(len(contributions), clients, seed)
    rng, fig, scale = np.random.default_rng(seed), go.Figure(), False
    for r, feature in enumerate(features):
        x = contributions[feature].to_numpy(dtype=float)[rows]
        y = (len(features) - 1 - r) + SWARM_HEIGHT * _swarm_offsets(x, rng)
        scale |= _add_points(fig, x, y, values[feature].iloc[rows], "contribution %{x:.3f}",
                             "Feature value", not scale, {})  # fmt: skip
    fig.add_vline(x=0, line_color=THEME["muted"], line_width=1)
    height = 34 * len(features) + 150
    title = "Feature contributions, one point per sampled row"
    apply_theme(
        fig, title, "Contribution to the margin (higher raises the score)", "Feature", height
    )
    fig.update_xaxes(showgrid=False, ticks="outside")
    fig.update_yaxes(tickvals=list(range(len(features)))[::-1], ticktext=features,
                     range=[-0.7, len(features) - 0.3], griddash="dot")  # fmt: skip
    return fig


def _waterfall_steps(
    contributions: pd.Series, values: pd.Series, shown: int
) -> tuple[np.ndarray, list[str]]:
    """The waterfall's steps from the bottom up, with their labels: the rest summed as `n other
    features` first (when any), then the `shown` largest contributions by size, smallest first,
    each labelled `feature = value`."""
    order = contributions.abs().sort_values(ascending=False, kind="stable").index
    largest, rest = list(order[:shown])[::-1], list(order[shown:])
    steps = [float(contributions[feature]) for feature in largest]
    labels = [f"{feature} = {_format_value(values[feature])}" for feature in largest]
    if rest:
        steps = [float(contributions[rest].sum()), *steps]
        labels = [f"{len(rest)} other features", *labels]
    return np.array(steps), labels


def _signed(step: float) -> str:
    """A step with its sign, in `plain_number`'s digits: a small step keeps its size, never
    `+0.00`."""
    return f"+{plain_number(step)}" if step > 0 else plain_number(step)


def waterfall(
    contributions: pd.Series, base: float, values: pd.Series, shown: int = 9
) -> go.Figure:
    """One row's walk from the base value to its margin: the `shown` largest contributions and
    the rest as one bar, each starting where the one below ends. Receives one row: a
    contribution and a raw value per feature, both indexed by feature."""
    _check_contributions(contributions, values)
    steps, labels = _waterfall_steps(contributions, values, shown)
    start = base + np.r_[0.0, np.cumsum(steps)[:-1]]
    end, y = start + steps, np.arange(len(steps))
    palette = THEME["contribution"]
    colours = [palette["raises"] if s > 0 else palette["lowers"] for s in steps]
    fig = go.Figure(go.Bar(x=steps, base=start, y=y, orientation="h", width=0.6,
                           marker_color=colours, customdata=labels,
                           hovertemplate="%{customdata}: %{x:+.3f}<extra></extra>"))  # fmt: skip
    # The arrow tips and the value labels in one marker trace: plotly offsets the text by the
    # marker's size.
    fig.add_trace(go.Scatter(
        x=end, y=y, mode="markers+text", hoverinfo="skip", marker_color=colours, marker_size=9,
        marker_symbol=["triangle-right" if s > 0 else "triangle-left" for s in steps],
        text=[_signed(s) for s in steps], textfont={"color": colours},
        textposition=["middle right" if s > 0 else "middle left" for s in steps],
    ))  # fmt: skip
    for i in range(len(steps) - 1):  # dotted connectors between the bars' ends
        fig.add_shape(type="line", x0=end[i], x1=end[i], y0=i + 0.3, y1=i + 0.7,
                      line={"color": palette["missing"], "dash": "dot"})  # fmt: skip
    margin = float(end[-1])
    for value, text, at, anchor in ((base, f"E[f(X)] = {base:.2f}", 0.0, "top"),
                                    (margin, f"f(x) = {margin:.2f}", 1.0, "bottom")):  # fmt: skip
        fig.add_vline(x=value, line_color=palette["missing"], line_dash="dot", line_width=1)
        fig.add_annotation(x=value, y=at, xref="x", yref="paper", text=text, showarrow=False,
                           yanchor=anchor, yshift=-48 if at == 0 else 0,
                           font={"color": THEME["muted"]})  # fmt: skip
    low, high = min(start.min(), end.min(), base), max(start.max(), end.max(), base)
    pad = 0.12 * (high - low) or 0.1
    title = f"One row: margin {margin:.2f} from the base value {base:.2f}"
    apply_theme(fig, title, "Margin", "Feature = value", 34 * len(steps) + 170)
    fig.update_xaxes(range=[low - pad, high + pad], showgrid=False, ticks="outside",
                     title_standoff=55)  # fmt: skip
    fig.update_yaxes(tickvals=list(y), ticktext=labels, showgrid=False)
    return fig


def _value_positions(values: pd.Series) -> tuple[np.ndarray, list[str] | None]:
    """Each value's place on the dependence scatter's x axis, NaN when missing: a number as
    itself, a level at its position among the levels by rows (most first, ties by text); and
    the levels in that order, None for numbers."""
    if _is_numeric(values):
        return values.to_numpy(dtype=float, na_value=np.nan), None
    text = values.astype(str).where(values.notna())
    counts = text.value_counts().sort_index().sort_values(ascending=False, kind="stable")
    codes = pd.Categorical(text, categories=list(counts.index)).codes.astype(float)
    return np.where(codes < 0, np.nan, codes), list(counts.index)


def _scatter(contributions: pd.Series, values: pd.Series, colour: pd.Series | None) -> go.Figure:
    """`dependence`'s scatter: the contribution against the value for at most
    `ROW_CAP` seeded rows, a level jittered around its position, a missing value in a `null`
    strip on the left (drawn only when a sampled value is missing); coloured by `colour` when
    given."""
    name, rng = str(values.name), np.random.default_rng(SEED)
    rows = _sample_rows(len(contributions), ROW_CAP, SEED)
    positions, levels = _value_positions(values)
    x, y = positions[rows], contributions.to_numpy(dtype=float)[rows]
    missing = np.isnan(x)
    if levels is not None:
        x = x + rng.uniform(-0.3, 0.3, x.size)
    strip = rng.uniform(-0.35, 0.35, x.size)
    known = f"{name} = %{{x:{HOVER_FORMAT}}}<br>" if levels is None else ""  # a level: its tick
    hovers = {"x": f"{known}contribution %{{y:.3f}}",
              "x2": f"{name} = {NULL_LABEL}<br>contribution %{{y:.3f}}"}  # fmt: skip
    scale_title = "" if colour is None else str(colour.name)
    fig, scale = go.Figure(), False
    for axis, mask in (("x", ~missing), ("x2", missing)):
        part = None if colour is None else colour.iloc[rows[mask]]
        where = x[mask] if axis == "x" else strip[mask]
        scale |= _add_points(fig, where, y[mask], part, hovers[axis], scale_title, not scale,
                             {"xaxis": axis})  # fmt: skip
    axis = {"showgrid": False, "ticks": "outside"}
    if levels is not None:
        axis |= {"tickvals": list(range(len(levels))), "ticktext": levels,
                 "range": [-0.5, len(levels) - 0.5]}  # fmt: skip
    left = 0.1 if missing.any() else 0.0  # the main panel leaves room for the strip
    fig.update_layout(
        xaxis={"domain": [left, 1], **axis},
        yaxis={"anchor": "free", "position": 0, "showgrid": False, "ticks": "outside",
               "range": charts.axis_range(y, 0.0, from_zero=False)},
    )  # fmt: skip
    if missing.any():
        fig.update_layout(xaxis2={"domain": [0, 0.07], "anchor": "y", "tickvals": [0],
                                  "ticktext": [NULL_LABEL], "range": [-0.5, 0.5],
                                  "showgrid": False})  # fmt: skip
    fig.add_shape(type="line", xref="paper", x0=left, x1=1, yref="y", y0=0, y1=0,
                  line={"color": THEME["muted"], "dash": "dot", "width": 1})  # fmt: skip
    title = f"Dependence: {name}" + ("" if colour is None else f", coloured by {colour.name}")
    apply_theme(fig, title, "", "", 460)
    fig.update_layout(xaxis_title_text=name, yaxis_title_text="Contribution to the margin")
    return fig


def group_means(contributions: pd.Series, groups: pd.Series, order: list[str]) -> pd.DataFrame:
    """The mean contribution per group with its 95% t interval, one row per group of `order`
    (a group without a sampled row keeps its row, empty): `group, estimate, low, high, support`
    (the sampled rows) and `insufficient` below `MIN_GROUP_ROWS`. Receives one row per sampled
    row, `groups` holding each row's group label."""
    by = contributions.groupby(groups.to_numpy())
    table = pd.DataFrame({"estimate": by.mean(), "sd": by.std(), "support": by.size()})
    table = table.reindex(order).rename_axis("group").reset_index()
    table["support"] = table["support"].fillna(0)
    table[["low", "high"]] = np.nan
    known = table["support"] >= 2
    if known.any():
        low, high = t_interval(table.loc[known, "estimate"], table.loc[known, "sd"],
                               table.loc[known, "support"])  # fmt: skip
        table.loc[known, "low"], table.loc[known, "high"] = low, high
    table["insufficient"] = table["support"] < MIN_GROUP_ROWS
    return table


def effect_chart(table: pd.DataFrame) -> go.Figure:
    """One feature's mean contribution per group with its interval (a group under
    `MIN_GROUP_ROWS` sample rows greyed) beside EDA's lift by the same groups, two panels.
    Receives one row per group in group order: `feature`, `MEAN_COLUMNS` and `LIFT_COLUMNS`,
    the lift's interval in lift units (Evaluation's effects table, one feature's rows)."""
    lacking = [c for c in ["feature", *MEAN_COLUMNS, *LIFT_COLUMNS] if c not in table.columns]
    if lacking:
        raise ValueError(f"effect_chart: the table lacks the columns {lacking}")
    names = table["feature"].unique()
    if len(names) != 1:
        raise ValueError(f"effect_chart: one feature's rows expected, got {list(names)}")
    name = str(names[0])
    means = table[["group", *MEAN_COLUMNS]].rename(columns=MEAN_COLUMNS)
    left = charts.bar_with_intervals(
        means, "group", title=f"Mean contribution by {name}", x_title=name,
        y_title="Mean contribution to the margin",
    )  # fmt: skip
    right = charts.lift_chart(table, "group", title=f"EDA: lift by {name}", x_title=name)
    return charts.side_by_side(left, right)


def dependence(
    contributions: pd.Series, values: pd.Series, colour: pd.Series | None = None
) -> go.Figure:
    """A feature's contribution against its raw value: a scatter of at most `ROW_CAP` seeded
    rows, coloured by a second feature's values `colour` when given. Receives one row per
    sampled row, the series on the same index."""
    _check_contributions(contributions, values, colour)
    return _scatter(contributions, values, colour)


def _pdp_and_ice(table: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """One feature's partial dependence rows in grid order and its ICE scores as an array of
    one row per ICE row and one column per grid point; fails unless the table holds one
    feature with a `pdp` row at every point the ICE rows cover."""
    names = table["feature"].unique()
    if len(names) != 1:
        raise ValueError(f"pdp_ice_chart: one feature's rows expected, got {list(names)}")
    pdp = table.loc[table["curve"] == "pdp"].sort_values("point").reset_index(drop=True)
    ice = table.loc[table["curve"] == "ice"].pivot(index="row", columns="point", values="score")
    if pdp.empty or not set(ice.columns) <= set(pdp["point"]):
        raise ValueError(f"pdp_ice_chart: {names[0]} has no partial dependence row per point")
    return pdp, ice.reindex(columns=pdp["point"]).to_numpy(dtype=float)


def pdp_ice_chart(table: pd.DataFrame, y_format: str | None = None) -> go.Figure:
    """Partial dependence over the ICE lines of one feature: the mean score over the sample at
    each grid point as one line, each ICE row's scores as a thin muted line beneath it; a
    categorical (its `level` set) as points per level in grid order. `y_format` is the score's
    d3 format (the task's `axis_format`). Receives `partial_dependence`'s long rows of one
    feature: `feature, curve, row, point, value, level, score`."""
    pdp, ice = _pdp_and_ice(table)
    name, categorical = str(pdp["feature"].iloc[0]), bool(pdp["level"].notna().any())
    grid = pdp["level"].astype(str) if categorical else pdp["value"].astype(float)
    if categorical:
        x, y = np.tile(grid.to_numpy(dtype=object), len(ice)), ice.ravel()
    else:  # one trace for every ICE row, each row's line ended by a gap (NaN)
        x = np.tile(np.r_[grid.to_numpy(), np.nan], len(ice))
        y = np.c_[ice, np.full(len(ice), np.nan)].ravel()
    hover = f"%{{y:{y_format or '.4g'}}}<extra></extra>"
    fig = go.Figure(go.Scatter(
        x=x, y=y.astype("float32"), mode="markers" if categorical else "lines",
        name=f"ICE: {len(ice)} sampled rows", opacity=0.35,
        line={"color": THEME["muted"], "width": 1}, marker={"color": THEME["muted"], "size": 4},
        hovertemplate=f"ICE {hover}",
    ))  # fmt: skip
    fig.add_trace(go.Scatter(
        x=grid, y=pdp["score"], mode="markers" if categorical else "lines+markers",
        name="Partial dependence (mean)", line={"color": THEME["accent"], "width": 3},
        marker={"color": THEME["accent"], "size": 10 if categorical else 6},
        hovertemplate=f"mean {hover}",
    ))  # fmt: skip
    scores = np.r_[ice.ravel(), pdp["score"].to_numpy(dtype=float)]
    apply_theme(fig, f"Partial dependence and ICE: {name}", name, "Score", 420)
    fig.update_yaxes(range=charts.axis_range(scores, None, from_zero=False), tickformat=y_format,
                     showgrid=False, ticks="outside")  # fmt: skip
    axis = {"type": "category", "categoryorder": "array", "categoryarray": list(grid)}
    fig.update_xaxes(showgrid=False, ticks="outside", **(axis if categorical else {}))
    return fig
