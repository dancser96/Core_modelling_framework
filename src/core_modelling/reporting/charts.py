"""The five chart primitives, each one function returning a plotly figure with the chart rules
applied (docs/components/reporting.md), and `side_by_side`, which sets two of them in one figure.

Every figure is drawn from pre-aggregated tables (group tables, quartiles), never from rows. The
rules enforced: a rate axis follows the data (from 0 to 1.25 times the plotted values on each
side of it, never a fixed 0 to 1), a group with too little support is greyed but drawn with its
interval, `null` is its own category and comes last, one colour stands for one thing, and traces
are SVG only (no WebGL: browsers allow a handful of WebGL contexts per page). Every figure
carries `layout.meta` (its reference line, whether anything is greyed): shapes and annotations do
not move into a subplot, so `side_by_side` redraws them from it.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core_modelling.reporting.theme import THEME

NULL_LABEL = "null"
TITLE_SIZE = 14
LIFT_TITLE = "Lift vs base rate (1 = base)"  # the lift axis' title, every lift chart's


def _apply_theme(fig: go.Figure, title: str, x_title: str, y_title: str, height: int) -> go.Figure:
    """The theme and layout every primitive shares: fonts, colours, margins, grid, axis titles."""
    fig.update_layout(
        template="none", title={"text": title, "x": 0.5, "xanchor": "center",
                                "font": {"size": TITLE_SIZE}},
        font={"family": THEME["font"], "color": THEME["text"], "size": 12},
        paper_bgcolor=THEME["background"], plot_bgcolor=THEME["background"],
        colorway=THEME["sequence"], margin={"l": 70, "r": 40, "t": 70, "b": 70}, height=height,
    )  # fmt: skip
    # automargin grows the margins for rotated tick labels and long axis titles: nothing clipped.
    axis = {"gridcolor": THEME["border"], "linecolor": THEME["border"], "zeroline": False,
            "automargin": True}  # fmt: skip
    fig.update_xaxes(title_text=x_title, **axis)
    fig.update_yaxes(title_text=y_title, **axis)
    return fig


def _note_insufficient(fig: go.Figure, y_shift: int = 0) -> None:
    """Say on the chart, top right, that grey means too little support (chart rule 3)."""
    fig.add_annotation(
        text="grey = insufficient support", xref="paper", yref="paper", x=1.0, y=1.06,
        yshift=y_shift, xanchor="right", showarrow=False,
        font={"size": 11, "color": THEME["muted"]},
    )  # fmt: skip


def _add_reference_and_note(fig: go.Figure, reference: float | None, insufficient: bool) -> None:
    """The dashed reference line and the insufficient note, both recorded in `layout.meta`."""
    if reference is not None:
        fig.add_hline(y=reference, line_dash="dash", line_color=THEME["muted"])
    if insufficient:
        _note_insufficient(fig)
    fig.layout.meta = {"reference": reference, "insufficient": insufficient}


def _axis_range(values: np.ndarray, reference: float | None, from_zero: bool) -> list[float] | None:
    """The axis range that follows the data (chart rule 1): from zero, 1.25 × the plotted values
    on each side of it (a regression target can be negative); else the data's span padded; the
    reference stays in view. None when nothing but zero is plotted."""
    plotted = np.asarray(values, dtype=float)
    if reference is not None:
        plotted = np.append(plotted, reference)
    plotted = plotted[np.isfinite(plotted)]
    if plotted.size == 0:
        return None
    low, high = plotted.min(), plotted.max()
    if from_zero:
        span = [min(0.0, 1.25 * low), max(0.0, 1.25 * high)]
        return None if span == [0.0, 0.0] else span
    pad = 0.1 * (high - low) if high > low else 0.05 * abs(high) or 0.05
    return [low - pad, high + pad]


def _plotted(
    df: pd.DataFrame,
    estimate: str,
    low: str | None,
    high: str | None,
    insufficient: np.ndarray,
) -> np.ndarray:
    """Every estimate and the interval ends of the supported rows: a greyed bar keeps its true
    height (chart rule 3), while its wide interval may run past the axis."""
    parts = [df[estimate].to_numpy(dtype=float)]
    for end in (low, high):
        if end is not None:
            parts.append(df[end].to_numpy(dtype=float)[~insufficient])
    return np.concatenate(parts)


def _flags(df: pd.DataFrame, insufficient: str | None) -> np.ndarray:
    """The insufficient flags as a boolean array; all False without the column, a missing flag
    False."""
    if insufficient is None:
        return np.zeros(len(df), dtype=bool)
    return df[insufficient].astype("boolean").fillna(False).to_numpy(dtype=bool)


def _null_last(df: pd.DataFrame, x: str) -> pd.DataFrame:
    """A copy with x as text, a missing category labelled `null`, and the null rows last."""
    out = df.copy()
    out[x] = out[x].astype(object).where(out[x].notna(), NULL_LABEL).astype(str)
    return out.iloc[out[x].eq(NULL_LABEL).to_numpy().argsort(kind="stable")]


def _error_bars(df: pd.DataFrame, estimate: np.ndarray, low: str, high: str, colour: str) -> dict:
    """Asymmetric interval error bars from the `low` and `high` columns around `estimate`."""
    return {"type": "data", "symmetric": False, "color": colour, "thickness": 1.2,
            "array": df[high].to_numpy(dtype=float) - estimate,
            "arrayminus": estimate - df[low].to_numpy(dtype=float)}  # fmt: skip


def _bar_colour(label: str, insufficient: bool, position: int, by_level: bool) -> str:
    """A bar's colour: grey if insufficient, the null colour for `null`, else level or accent."""
    if insufficient:
        return THEME["insufficient"]
    if label == NULL_LABEL:
        return THEME["null"]
    if by_level:
        return THEME["sequence"][position % len(THEME["sequence"])]
    return THEME["accent"]


def _interval_bars(
    df: pd.DataFrame,
    x: str,
    value: str,
    low: str,
    high: str,
    support: str | None,
    insufficient: str | None,
    title: str,
    x_title: str,
    y_title: str,
    by_level: bool,
    reference: float | None,
) -> go.Figure:
    """Bars with interval error bars: the body of `bar_with_intervals` and `lift_chart`."""
    data = _null_last(df, x)
    flags = _flags(data, insufficient)
    colours = [
        _bar_colour(label, flag, i, by_level)
        for i, (label, flag) in enumerate(zip(data[x], flags, strict=True))
    ]
    estimate = data[value].to_numpy(dtype=float)
    bar = go.Bar(
        x=data[x], y=estimate, marker_color=colours,
        error_y=_error_bars(data, estimate, low, high, THEME["text"]),
        customdata=data[[low, high]].to_numpy(dtype=float),
        hovertemplate="%{x}<br>%{y:.4g} [%{customdata[0]:.4g}, %{customdata[1]:.4g}]"
                      "<extra></extra>",
    )  # fmt: skip
    if support is not None:
        bar.text = data[support].map(lambda n: "" if pd.isna(n) else f"{n:,.0f}")
        bar.textposition = "auto"  # inside the bar when it fits, so a tall bar's text is not cut
        bar.insidetextanchor = "start"  # at the base, clear of the error bar around the top
    fig = go.Figure(bar)
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=list(data[x]))
    _apply_theme(fig, title, x_title, y_title, 380)
    fig.update_layout(showlegend=False)
    if data[x].str.len().max() > 12:  # long labels tilt
        fig.update_xaxes(tickangle=-30)
    plotted = _plotted(data, value, low, high, flags)
    fig.update_yaxes(range=_axis_range(plotted, reference, True))
    _add_reference_and_note(fig, reference, bool(flags.any()))
    return fig


def bar_with_intervals(
    df: pd.DataFrame,
    x: str,
    estimate: str = "estimate",
    low: str = "low",
    high: str = "high",
    support: str | None = "support",
    insufficient: str | None = "insufficient",
    title: str = "",
    x_title: str = "",
    y_title: str = "",
    by_level: bool = False,
) -> go.Figure:
    """The estimate by category as bars with interval error bars, the support as bar text;
    `by_level` gives every category its own colour (a stratum's levels)."""
    return _interval_bars(
        df, x, value=estimate, low=low, high=high, support=support, insufficient=insufficient,
        title=title, x_title=x_title, y_title=y_title, by_level=by_level, reference=None,
    )  # fmt: skip


def lift_chart(
    df: pd.DataFrame,
    x: str,
    lift: str = "lift",
    low: str = "lift_low",
    high: str = "lift_high",
    support: str | None = "support",
    insufficient: str | None = "insufficient",
    title: str = "",
    x_title: str = "",
    y_title: str = LIFT_TITLE,
) -> go.Figure:
    """Lift by group as bars with interval error bars and a reference line at 1; `low` and
    `high` are in lift units (the caller divides the estimate's interval by the base)."""
    return _interval_bars(
        df, x, value=lift, low=low, high=high, support=support, insufficient=insufficient,
        title=title, x_title=x_title, y_title=y_title, by_level=False, reference=1.0,
    )  # fmt: skip


def box_from_quartiles(
    df: pd.DataFrame,
    group: str,
    q1: str = "q1",
    median: str = "median",
    q3: str = "q3",
    lower: str = "lower",
    upper: str = "upper",
    title: str = "",
    x_title: str = "",
    y_title: str = "",
    log: bool = False,
    by_target_class: bool = False,
) -> go.Figure:
    """One box per group from precomputed quartiles and whiskers, no raw points, over a category
    axis in the table's order (null last); with `by_target_class` the groups are target classes
    and take their colours (chart rule 6). `log=True` refuses a non-positive value, which plotly
    would clamp silently (T30)."""
    if log:
        refused = [column for column in (lower, q1, median, q3, upper) if (df[column] <= 0).any()]
        if refused:
            raise ValueError(
                f"log axis needs positive values; column {refused[0]!r} holds a zero or negative "
                "value (T30): use a linear axis or show the zero share separately"
            )
    sequence, fig = THEME["sequence"], go.Figure()
    data = _null_last(df, group)
    for i, (_, row) in enumerate(data.iterrows()):
        label = row[group]
        colour = sequence[i % len(sequence)]
        if label == NULL_LABEL:
            colour = THEME["null"]
        elif by_target_class:
            colour = THEME["target_class"].get(label, colour)
        fig.add_trace(go.Box(
            x=[label], q1=[row[q1]], median=[row[median]], q3=[row[q3]],
            lowerfence=[row[lower]], upperfence=[row[upper]], name=label, marker_color=colour,
            fillcolor=colour, line_color=colour, boxpoints=False,
        ))  # fmt: skip
    # A category axis, or plotly.js reads labels like "0" and "1" as numbers (and drops "null").
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=list(data[group]))
    _apply_theme(fig, title, x_title, y_title, 380)
    fig.update_layout(showlegend=False)
    fig.update_yaxes(type="log" if log else "linear")
    _add_reference_and_note(fig, None, False)
    return fig


def _axis_labels(values: pd.Series) -> pd.Series:
    """Category labels as text: a datetime as its date, so the axis marks every period (chart
    rule 9), anything else as it prints."""
    if pd.api.types.is_datetime64_any_dtype(values):
        return values.dt.strftime("%Y-%m-%d")
    return values.astype(str)


def _add_line(
    fig: go.Figure,
    part: pd.DataFrame,
    x: str,
    y: str,
    low: str | None,
    high: str | None,
    insufficient: str | None,
    name: str,
    colour: str,
    show_legend: bool,
) -> None:
    """One line with its interval bars; insufficient points get grey markers."""
    estimate = part[y].to_numpy(dtype=float)
    intervals = low is not None and high is not None
    markers = [THEME["insufficient"] if flag else colour for flag in _flags(part, insufficient)]
    fig.add_trace(go.Scatter(
        x=_axis_labels(part[x]), y=estimate, mode="lines+markers", name=name,
        showlegend=show_legend, line={"color": colour}, marker={"color": markers, "size": 8},
        error_y=_error_bars(part, estimate, low, high, colour) if intervals else None,
    ), secondary_y=False)  # fmt: skip


def _add_support(fig: go.Figure, df: pd.DataFrame, x: str, support: str, title: str) -> None:
    """The support as grey bars on the second y axis, kept to the lower part of the height."""
    fig.add_trace(go.Bar(
        x=_axis_labels(df[x]), y=df[support], name=title, marker_color=THEME["border"],
        opacity=0.6, showlegend=False,
    ), secondary_y=True)  # fmt: skip
    top = float(df[support].max())  # the bars fill at most a quarter of the height
    fig.update_yaxes(range=[0, top / 0.25] if top > 0 else None, title_text=title,
                     showgrid=False, secondary_y=True)  # fmt: skip


def _lines(df: pd.DataFrame, group: str, order: list | None) -> list[tuple[str, pd.DataFrame, str]]:
    """Each group's name, rows and colour in `order` (default the data's, a missing group the
    line `null`, last): a colour by position in the order, so a group absent here keeps the
    others' colours, and `null` its own colour (chart rules 6 and 7); a group missing from
    `order` fails."""
    parts = dict(list(_null_last(df, group).groupby(group, sort=False)))
    names = list(parts) if order is None else [str(name) for name in order]
    missing = [name for name in parts if name not in names]
    if missing:
        raise ValueError(f"grouped_lines: group_order lacks the groups {missing}")
    sequence = THEME["sequence"]
    return [
        (name, parts[name], THEME["null"] if name == NULL_LABEL else sequence[i % len(sequence)])
        for i, name in enumerate(names)
        if name in parts
    ]


def grouped_lines(
    df: pd.DataFrame,
    x: str,
    y: str,
    group: str | None = None,
    low: str | None = None,
    high: str | None = None,
    support: str | None = None,
    insufficient: str | None = "insufficient",
    reference: float | None = None,
    from_zero: bool = True,
    title: str = "",
    x_title: str = "",
    y_title: str = "",
    support_title: str = "Support",
    legend_title: str | None = None,
    group_order: list | None = None,
) -> go.Figure:
    """One line per group (or one line) over an ordered category axis (periods, or a feature's
    groups) in the data's order, with optional interval bars, a reference line and support bars
    on a second axis (one line only); the y axis from zero when `from_zero`, else the data's
    span (a concordance around 0.5). A NaN in `y` (a label-free period) shows no point.
    `group_order` orders the lines, hence their colours (default the data's order); a `null`
    group takes the null colour."""
    if support is not None and group is not None:
        raise ValueError("support bars are drawn for a single line: do not combine with group")
    fig = make_subplots(specs=[[{"secondary_y": support is not None}]])
    _apply_theme(fig, title, x_title, y_title, 380)  # first: it titles every y axis
    lines = _lines(df, group, group_order) if group else [("", df, THEME["accent"])]
    for name, part, colour in lines:
        _add_line(fig, part, x, y, low, high, insufficient, name, colour, group is not None)
    if support is not None:
        _add_support(fig, df, x, support, support_title)
    # The data's order, not plotly's order of first appearance across the lines; half a slot
    # of padding at both ends, as bars have.
    categories = list(_axis_labels(df[x]).unique())
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=categories,
                     range=[-0.5, len(categories) - 0.5])  # fmt: skip
    flags = _flags(df, insufficient)
    plotted = _plotted(df, y, low, high, flags)
    fig.update_yaxes(range=_axis_range(plotted, reference, from_zero), secondary_y=False)
    if legend_title is not None:
        fig.update_layout(legend_title_text=legend_title)
    _add_reference_and_note(fig, reference, bool(flags.any()))
    return fig


def heatmap(
    matrix: pd.DataFrame,
    hover: pd.DataFrame | None = None,
    title: str = "",
    x_title: str = "",
    z_title: str = "association",
) -> go.Figure:
    """A square association matrix as a heatmap, 0 to 1 (-1 to 1 when a value is negative);
    `hover` adds a text per cell, e.g. the method."""
    if matrix.shape[0] != matrix.shape[1] or not matrix.index.equals(matrix.columns):
        raise ValueError("a heatmap needs a square matrix with the same labels on both axes")
    if hover is not None and not (hover.index.equals(matrix.index)
                                  and hover.columns.equals(matrix.columns)):  # fmt: skip
        raise ValueError("hover must be shaped and labelled like the matrix")
    signed = bool((matrix.to_numpy(dtype=float) < 0).any())
    template = "%{y} × %{x}<br>%{z:.3f}" + ("<br>%{text}" if hover is not None else "")
    fig = go.Figure(go.Heatmap(
        z=matrix.to_numpy(dtype=float), x=[str(c) for c in matrix.columns],
        y=[str(i) for i in matrix.index], zmin=-1.0 if signed else 0.0, zmax=1.0,
        colorscale=THEME["heat_scale_signed" if signed else "heat_scale"],
        text=None if hover is None else hover.to_numpy(),
        hovertemplate=template + "<extra></extra>", colorbar={"title": {"text": z_title}},
    ))  # fmt: skip
    size = min(900, max(420, 28 * len(matrix) + 160))
    _apply_theme(fig, title, x_title, "", size)
    fig.update_xaxes(showgrid=False, constrain="domain", tickangle=-45)
    fig.update_yaxes(showgrid=False, autorange="reversed", scaleanchor="x", constrain="domain")
    _add_reference_and_note(fig, None, False)
    return fig


def _shows_legend(source: go.Figure) -> bool:
    """Whether a primitive's figure shows a legend: only named lines are put in one."""
    return source.layout.showlegend is not False and any(t.showlegend for t in source.data)


def _axis_settings(axis: go.layout.XAxis | go.layout.YAxis) -> dict:
    """An axis' settings (titles, type, category order, range…) without the keys that place it
    in its figure: a panel of `side_by_side` keeps its own."""
    placement = ("anchor", "domain", "overlaying", "side", "position")
    return {k: v for k, v in axis.to_plotly_json().items() if k not in placement}


def _add_panel(fig: go.Figure, source: go.Figure, col: int, secondary: bool, legend: bool) -> None:
    """One source's traces, axis settings and reference line in panel `col` of `fig`."""
    for trace in source.data:
        fig.add_trace(trace, row=1, col=col, secondary_y=trace.yaxis == "y2")
        if not legend:
            fig.data[-1].showlegend = False  # a box or bar source hides its legend in its layout
    # Through row, col and secondary_y only: the axes' names shift with the panels' specs.
    fig.update_xaxes(_axis_settings(source.layout.xaxis), row=1, col=col)
    fig.update_yaxes(_axis_settings(source.layout.yaxis), row=1, col=col, secondary_y=False)
    if secondary:
        fig.update_yaxes(_axis_settings(source.layout.yaxis2), row=1, col=col, secondary_y=True)
    reference = source.layout.meta["reference"]
    if reference is not None:
        fig.add_hline(y=reference, line_dash="dash", line_color=THEME["muted"], row=1, col=col)


def side_by_side(left: go.Figure, right: go.Figure, height: int = 380) -> go.Figure:
    """Two primitives' single-panel figures as one figure with two panels, each keeping its
    title, axes and reference line, and the right one its legend (a legend on the left is
    refused: it would sit right of the right panel); one insufficient note for both. The
    result's `meta["reference"]` lists both panels'."""
    sources = (left, right)
    for source in sources:
        foreign = not isinstance(source.layout.meta, dict)
        # a heatmap's square cells anchor its y axis to its own x axis, which a panel loses
        heat = any(trace.type == "heatmap" for trace in source.data)
        if len(list(source.select_xaxes())) > 1 or foreign or heat:
            raise ValueError(
                "side_by_side takes two single-panel figures from the chart primitives (one x "
                "axis, the primitive's layout.meta, no heatmap); got a subplot, a heatmap or a "
                "foreign figure"
            )
    secondary = [any(trace.yaxis == "y2" for trace in source.data) for source in sources]
    fig = make_subplots(
        rows=1, cols=2, specs=[[{"secondary_y": secondary[0]}, {"secondary_y": secondary[1]}]],
        subplot_titles=[source.layout.title.text or "" for source in sources],
        horizontal_spacing=0.1,
    )  # fmt: skip
    fig.update_annotations(font_size=TITLE_SIZE)  # the panel titles, sized as a figure's title
    _apply_theme(fig, "", "", "", height)  # first: it titles every axis
    if _shows_legend(left):
        # One figure has one legend, right of the right panel: two would also mix their levels.
        raise ValueError(
            "side_by_side: the left figure shows a legend, which sits right of the right panel; "
            "put the figure with the legend on the right (two legends cannot share a figure)"
        )
    legend = _shows_legend(right)
    for col, source in enumerate(sources, start=1):
        _add_panel(fig, source, col, secondary[col - 1], legend and col == 2)
    fig.update_layout(showlegend=legend)
    if legend:
        fig.update_layout(legend_title_text=right.layout.legend.title.text)
    metas = [source.layout.meta for source in sources]
    insufficient = any(meta["insufficient"] for meta in metas)
    if insufficient:
        _note_insufficient(fig, 24)  # px: above the panel titles
    fig.layout.meta = {"reference": [m["reference"] for m in metas], "insufficient": insufficient}
    return fig
