"""The model charts of the model results report: ROC, precision-recall, capture, reliability,
score distribution, a metric by period and predicted against observed.

Each function takes one of Evaluation's tables (`pd.DataFrame`, columns in docs/components/
evaluation.md) and returns a plotly figure with the chart rules applied
(docs/components/reporting.md). None reads rows: the curve tables hold one row per score bin (up
to 200) and a `part` column, so the functions assume neither a number of rows nor that both parts
are present. A part keeps its colour across every chart (chart rule 6), present or not. The line
charts reuse `charts.grouped_lines`; the rest use `charts.apply_theme`.
"""

from collections.abc import Sequence

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core_modelling.reporting.charts import TITLE_SIZE, apply_theme, axis_range, grouped_lines
from core_modelling.reporting.theme import THEME
from core_modelling.statistics.score_cells import MEAN, PARTS, POOLED


def _require(df: pd.DataFrame, chart: str, *columns: str) -> None:
    """Fail loud, naming the chart and the missing columns."""
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{chart}: the table lacks the columns {missing}; has {list(df.columns)}")


def _part_order(df: pd.DataFrame) -> list[str]:
    """`PARTS`, then any other part of the table sorted: a fixed order, so a part keeps its
    colour in every chart."""
    extra = sorted(set(df["part"].astype(str)) - set(PARTS))
    return [*PARTS, *extra]


def part_colour(name: str, parts: Sequence[str] = PARTS) -> str:
    """A part's colour by its place in `parts`, the one rule for every chart that tells parts
    apart (chart rule 6): test the first sequence colour, validation the second."""
    sequence = THEME["sequence"]
    return sequence[list(parts).index(name) % len(sequence)]


def _part_lines(df: pd.DataFrame) -> list[tuple[str, pd.DataFrame, str]]:
    """Each part present: its name, its rows and its colour (`part_colour` by place in
    `_part_order`)."""
    rows = dict(list(df.assign(part=df["part"].astype(str)).groupby("part", sort=False)))
    order = _part_order(df)
    return [(name, rows[name], part_colour(name, order)) for name in order if name in rows]


def _reference_line(x: list[float], y: list[float], name: str) -> go.Scatter:
    """A dashed, muted reference line (chart rule 9) that the legend names."""
    return go.Scatter(x=x, y=y, mode="lines", name=name, hoverinfo="skip",
                      line={"color": THEME["muted"], "dash": "dash"})  # fmt: skip


def _curve_chart(
    curves: pd.DataFrame, chart: str, x: str, y: str, title: str, x_title: str, y_title: str,
    y_format: str | None,
) -> go.Figure:  # fmt: skip
    """One line per part of `y` against the share `x` (a linear 0 to 100% axis, no markers); the
    caller adds the reference and fixes the y range."""
    _require(curves, chart, "part", x, y)
    fig = grouped_lines(
        curves, x=x, y=y, group="part", insufficient=None, title=title, x_title=x_title,
        y_title=y_title, legend_title="Part", group_order=_part_order(curves), y_format=y_format,
        x_numeric=True,
    )  # fmt: skip
    fig.update_xaxes(hoverformat=".1%")  # the depths read to a tenth of a percent
    return fig


def roc_chart(curves: pd.DataFrame) -> go.Figure:
    """ROC: `capture` (the true positive rate) against `false_positive_rate`, one line per
    `part`, the diagonal of a random list dashed. Both axes are fixed to 0 to 100%, which is the
    chart's frame (a curve is judged against the diagonal), unlike a rate axis (chart rule 1)."""
    fig = _curve_chart(
        curves,
        "roc_chart",
        "false_positive_rate",
        "capture",
        "ROC curve",
        "False positive rate",
        "Capture of events (true positive rate)",
        ".0%",
    )
    fig.update_yaxes(range=[0, 1])
    return fig.add_trace(_reference_line([0, 1], [0, 1], "random"))


def pr_chart(curves: pd.DataFrame) -> go.Figure:
    """Precision-recall: `rate` (precision) against `capture` (recall), one line per `part`, and
    each part's base rate as a dashed line: its `rate` at the deepest cumulative row, which holds
    all of the part's rows. The y axis follows the data from zero (chart rule 1): a rare rate
    would vanish on a fixed 0 to 100% axis (T16)."""
    _require(curves, "pr_chart", "depth")
    fig = _curve_chart(
        curves,
        "pr_chart",
        "capture",
        "rate",
        "Precision-recall curve",
        "Capture of events (recall)",
        "Precision (rate among the list)",
        ".1%",
    )
    for name, rows, _ in _part_lines(curves):
        base = rows.loc[rows["depth"].idxmax(), "rate"]
        fig.add_trace(_reference_line([0, 1], [base, base], f"base rate, {name}"))
    return fig


def capture_chart(curves: pd.DataFrame) -> go.Figure:
    """Capture of the target (events, or the amount for a regression) against `depth`, the share
    of rows taken from the highest score, one line per `part`; the diagonal is a random list.
    Both axes stop at 100% (chart rule 9)."""
    fig = _curve_chart(curves, "capture_chart", "depth", "capture", "Capture curve",
                       "Depth (share of rows, highest scores first)",
                       "Capture (share of the target)", ".0%")  # fmt: skip
    fig.update_yaxes(range=[0, 1])
    return fig.add_trace(_reference_line([0, 1], [0, 1], "random"))


def _calibration_chart(
    table: pd.DataFrame, chart: str, title: str, x_title: str, y_title: str, axis_format: str | None
) -> go.Figure:  # fmt: skip
    """`observed` against `predicted` per group, one line with markers per part and the diagonal.
    Both axes share one range, from zero to 1.25 times the highest plotted value of either
    column (chart rule 1), so the diagonal is clipped to the data and a rare rate stays readable
    (T16)."""
    _require(table, chart, "part", "group", "rows", "predicted", "observed")
    span = axis_range(table[["predicted", "observed"]].to_numpy(dtype=float), None, True)
    low, high = span or [0.0, 1.0]
    fmt = axis_format or ".4g"
    fig = go.Figure()
    for name, rows, colour in _part_lines(table):
        fig.add_trace(go.Scatter(
            x=rows["predicted"], y=rows["observed"], mode="lines+markers", name=name,
            line={"color": colour}, marker={"color": colour, "size": 8},
            customdata=rows[["rows"]].to_numpy(dtype=float),
            hovertemplate=f"{name}<br>predicted %{{x:{fmt}}}<br>observed %{{y:{fmt}}}<br>"
                          "%{customdata[0]:,.0f} rows<extra></extra>",
        ))  # fmt: skip
    fig.add_trace(_reference_line([low, high], [low, high], "perfect"))
    apply_theme(fig, title, x_title, y_title, 380)
    fig.update_layout(legend_title_text="Part")
    fig.update_xaxes(range=span, tickformat=axis_format)
    fig.update_yaxes(range=span, tickformat=axis_format)
    fig.layout.meta = {"reference": None, "insufficient": False}
    return fig


def reliability_chart(reliability: pd.DataFrame, axis_format: str | None = ".1%") -> go.Figure:
    """Reliability: the observed rate against the mean score of each `group` (the task's
    `reliability_groups` quantile groups of the score), one line per `part`, the diagonal
    dashed. `axis_format` is the task's (binary: percent)."""
    return _calibration_chart(reliability, "reliability_chart", "Reliability",
                              "Predicted (mean score of the group)",
                              "Observed rate of the group", axis_format)  # fmt: skip


def predicted_vs_observed(reliability: pd.DataFrame, *, groups: int) -> go.Figure:
    """Regression: the mean observed against the mean predicted amount in each of the `groups`
    groups of the prediction (the task's `reliability_groups`), one line per `part`, the
    diagonal dashed."""
    return _calibration_chart(reliability, "predicted_vs_observed", "Predicted against observed",
                              f"Mean predicted ({groups} groups of the prediction)",
                              "Mean observed", None)  # fmt: skip


def _class_colour(label: str, position: int) -> str:
    """A target class' colour (chart rule 6); a class the theme does not name takes the
    categorical sequence by position."""
    sequence = THEME["sequence"]
    return THEME["target_class"].get(label, sequence[position % len(sequence)])


def score_distribution(distribution: pd.DataFrame) -> go.Figure:
    """The score's distribution per `class` as a ratio to chance: `ratio` (the class' share in
    the bin over the bin's share of all rows) against the score's `percentile`, from the lowest
    score to the highest, so a rare class sits on the same scale as a common one. A class the
    score separates rises above the dashed line at 1 (chance) at one end and falls below it at
    the other; a class on the line is not separated. The bin's mean `score` is in the hover.
    One panel per `part` when the table has one."""
    _require(distribution, "score_distribution", "score", "percentile", "class", "ratio")
    data = distribution.assign(**{"class": distribution["class"].astype(str)})
    has_part = "part" in data.columns
    panels = _part_lines(data) if has_part else [("", data, "")]
    classes = list(dict.fromkeys(data["class"]))
    titles = [name for name, _, _ in panels] if has_part else None
    fig = make_subplots(rows=1, cols=len(panels), shared_yaxes=True, subplot_titles=titles)
    fig.update_annotations(font_size=TITLE_SIZE)
    shown: set[str] = {"chance"}
    for col, (_, rows, _) in enumerate(panels, start=1):
        for label, group in rows.groupby("class", sort=False):
            fig.add_trace(go.Scatter(
                x=group["percentile"], y=group["ratio"], mode="lines", name=f"class {label}",
                legendgroup=label, showlegend=label not in shown,
                line={"color": _class_colour(label, classes.index(label))},
                customdata=group[["score"]].to_numpy(dtype=float),
                hovertemplate="percentile %{x:.1%}<br>ratio %{y:.3g}<br>"
                              "score %{customdata[0]:.4g}<extra></extra>",
            ), row=1, col=col)  # fmt: skip
            shown.add(label)
        chance = _reference_line([0, 1], [1, 1], "chance (ratio 1)")
        chance.showlegend = col == 1
        fig.add_trace(chance, row=1, col=col)
    apply_theme(fig, "Score distribution by class", "Percentile of the score", "", 380)
    fig.update_yaxes(title_text="Ratio to chance", row=1, col=1)  # the panels share one y axis
    fig.update_xaxes(range=[0, 1], tickformat=".0%")
    ratios = data["ratio"].to_numpy(dtype=float)
    fig.update_yaxes(range=axis_range(ratios, 1.0, True))
    return fig


def metric_lines(
    metrics: pd.DataFrame, from_zero: bool = False, y_format: str | None = None,
    reference: float | None = None,
) -> go.Figure:  # fmt: skip
    """One metric by `period` with its interval (`low`, `high`), one line per `part`; the
    validation period is a period of its own part. A row with `insufficient` true is greyed
    (chart rule 3), never hidden. The `pooled` and `mean` rows are no point on the time axis and
    are left out (the metrics table shows them). The table holds one metric; `from_zero`,
    `y_format` and `reference` are the metric's (a concordance around 0.5: the data's span, a
    reference of 0.5)."""
    _require(metrics, "metric_lines", "metric", "part", "period", "value", "low", "high",
             "insufficient")  # fmt: skip
    names = metrics["metric"].unique()
    if len(names) != 1:
        raise ValueError(f"metric_lines: draw one metric at a time; the table holds {list(names)}")
    timed = metrics[~metrics["period"].astype(str).isin([POOLED, MEAN])]
    if timed.empty:
        raise ValueError("metric_lines: the table holds no period besides the pooled and mean rows")
    # the pooled row made the column mixed; infer_objects gives the periods their date type back
    timed = timed.assign(period=timed["period"].infer_objects())
    timed = timed.sort_values("period", kind="stable")
    return grouped_lines(
        timed, x="period", y="value", group="part", low="low", high="high",
        insufficient="insufficient", reference=reference, from_zero=from_zero,
        title=f"{names[0]} by period", x_title="Observation period", y_title=str(names[0]),
        legend_title="Part", group_order=_part_order(timed), y_format=y_format,
    )  # fmt: skip
