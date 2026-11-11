"""Reporting primitives: the writer, the chart rules, the table styling and the blocks."""

import re
import warnings
from html.parser import HTMLParser

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest
from plotly.offline import get_plotlyjs

from core_modelling.config.schema import UseCaseConfig
from core_modelling.eda.report import _how_to_read
from core_modelling.reporting import charts
from core_modelling.reporting.blocks import (
    appendix,
    choices_block,
    headline,
    not_available,
    warnings_block,
)
from core_modelling.reporting.formats import SHARE, format_of, plain_number
from core_modelling.reporting.html import paragraph, render_report, style_table, table_html
from core_modelling.reporting.theme import THEME
from core_modelling.tasks import TASK_SPECS


def _groups(n: int = 20, insufficient: tuple[int, ...] = ()) -> pd.DataFrame:
    """A group table in the shared shape: estimate, interval, support, insufficient."""
    estimate = np.linspace(0.01, 0.05, n)
    return pd.DataFrame(
        {
            "group": [f"g{i}" for i in range(n)],
            "estimate": estimate,
            "low": estimate * 0.8,
            "high": estimate * 1.3,
            "support": np.arange(n) * 10 + 5,
            "insufficient": [i in insufficient for i in range(n)],
        }
    )


class _Ids(HTMLParser):
    """Collects every id and every in-page link of a document."""

    def __init__(self) -> None:
        """Start with no ids or links."""
        super().__init__()
        self.ids: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record an element's id and an anchor's in-page target."""
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])
        if tag == "a" and values.get("href", "").startswith("#"):
            self.links.append(values["href"][1:])


def test_report_embeds_plotly_once_with_unique_ids() -> None:
    """Sixty figures and tables share one plotly.js; ids and uuids never repeat; it parses."""
    figures = [charts.bar_with_intervals(_groups(), "group") for _ in range(60)]
    tables = [style_table(_groups(3)) for _ in range(5)]
    sections = [
        ("Summary", [paragraph("a < b")]),
        ("Core", [*figures[:30], ("Sub", [*figures[30:], *tables])]),
    ]
    text = render_report("Report", sections)
    assert text.count(get_plotlyjs()[:300]) == 1
    div_ids = re.findall(r'<div id="(fig\d+)"', text)
    assert len(div_ids) == 60 and len(set(div_ids)) == 60
    uuids = re.findall(r'<table id="(T_t\d+)"', text)
    assert len(uuids) == 5 and len(set(uuids)) == 5
    ids = _Ids()
    ids.feed(text)
    assert ids.links == ["s1", "s2", "s2-1"]
    assert set(ids.links) <= set(ids.ids)
    print(f"report with sixty 20-bar figures: {len(text.encode()) / 1e6:.2f} MB")


def test_render_report_refuses_unknown_blocks_and_shapes() -> None:
    """An unknown block type (a views dict passed unconverted among them) fails naming it, as do
    blocks that are not a list and a subsection that is not a 2-tuple."""
    with pytest.raises(TypeError, match="int"):
        render_report("R", [("S", [42])])
    with pytest.raises(TypeError, match="got dict"):
        render_report("R", [("S", [{"k": "v"}])])
    with pytest.raises(TypeError, match=r"section 1 'S': the blocks must be a list; got str"):
        render_report("R", [("S", "text")])
    with pytest.raises(TypeError, match=r"a subsection of 'S'.*got a 3-tuple"):
        render_report("R", [("S", [("Sub", [], "extra")])])


def test_rate_axis_follows_supported_values() -> None:
    """The axis is (0, 1.25 × the largest supported estimate or interval top); a greyed bar's
    wide interval does not widen it."""
    df = _groups(5)
    top = df["high"].max()
    fig = charts.bar_with_intervals(df, "group")
    assert fig.layout.yaxis.range == pytest.approx((0, 1.25 * top))
    df.loc[0, ["insufficient", "high"]] = [True, 0.9]
    fig = charts.bar_with_intervals(df, "group")
    assert fig.layout.yaxis.range == pytest.approx((0, 1.25 * df.loc[1:, "high"].max()))
    assert fig.data[0].marker.color[0] == THEME["insufficient"]
    assert fig.data[0].error_y.array[0] > 0  # the interval is still drawn
    df.loc[0, "estimate"] = 0.5  # a greyed bar keeps its true height: its estimate counts
    assert charts.bar_with_intervals(df, "group").layout.yaxis.range[1] == pytest.approx(0.625)


def test_axis_from_zero_keeps_negative_values_in_view() -> None:
    """A negative mean (a regression target) and its supported interval stay in view: the axis
    runs from 1.25 × the lowest plotted value to 1.25 × the highest, through zero."""
    df = _groups(3).assign(estimate=[-2.0, 1.0, 3.0], low=[-3.0, 0.5, 2.0], high=[-1.0, 1.5, 4.0])
    fig = charts.bar_with_intervals(df, "group")
    assert fig.layout.yaxis.range == pytest.approx((1.25 * -3.0, 1.25 * 4.0))
    negative = df.assign(estimate=[-2.0, -1.0, -0.5], low=-3.0, high=-0.1)
    assert charts.bar_with_intervals(negative, "group").layout.yaxis.range == pytest.approx(
        (1.25 * -3.0, 0.0)
    )


def test_null_category_is_its_own_last_bar() -> None:
    """A missing category becomes the bar `null`, placed last, in lift charts too."""
    df = _groups(4)
    df.loc[1, "group"] = None
    for fig in (
        charts.bar_with_intervals(df, "group"),
        charts.lift_chart(
            df.assign(lift_low=df["low"], lift_high=df["high"], lift=df["estimate"]), "group"
        ),
    ):
        assert list(fig.data[0].x)[-1] == "null"
        assert fig.data[0].marker.color[-1] == THEME["null"]
    lift = charts.lift_chart(df.assign(lift=2.0, lift_low=1.5, lift_high=2.5), "group")
    assert lift.layout.yaxis.range == pytest.approx((0, 1.25 * 2.5))
    assert any(shape.y0 == 1.0 for shape in lift.layout.shapes)


def test_box_refuses_log_with_zero_quartile() -> None:
    """A log axis with a zero quartile fails naming the column; a linear axis draws on a category
    axis (labels like "0" stay categories); only boxes by target class take the classes'
    colours; null is its own box, last."""
    df = pd.DataFrame(
        {"group": ["0", "1"], "q1": [0.0, 1.0], "median": [1.0, 2.0], "q3": [2.0, 3.0],
         "lower": [0.5, 0.5], "upper": [4.0, 5.0]}
    )  # fmt: skip
    with pytest.raises(ValueError, match="'q1'"):
        charts.box_from_quartiles(df, "group", log=True)
    fig = charts.box_from_quartiles(df, "group", by_target_class=True)
    assert [trace.marker.color for trace in fig.data] == list(THEME["target_class"].values())
    assert fig.layout.xaxis.type == "category" and fig.layout.xaxis.categoryarray == ("0", "1")
    plain = charts.box_from_quartiles(df, "group")
    assert [trace.marker.color for trace in plain.data] == THEME["sequence"][:2]
    positive = df.assign(q1=[0.5, 1.0], lower=[0.1, 0.5])
    assert charts.box_from_quartiles(positive, "group", log=True).layout.yaxis.type == "log"
    with_null = df.assign(group=[None, "a"])
    null_last = charts.box_from_quartiles(with_null, "group")
    assert [trace.x[0] for trace in null_last.data] == ["a", "null"]
    assert null_last.data[1].marker.color == THEME["null"]


def test_primitives_shared_rules() -> None:
    """Every primitive draws SVG traces only under a centred title; an insufficient period gets a
    grey marker; the support axis keeps its title; a null line is drawn last; the reference
    stays in view; a heatmap refuses a matrix that is not square."""
    df = _groups(4, insufficient=(2,)).assign(period=["a", "b", "c", "d"])
    matrix = pd.DataFrame(np.eye(3), index=list("xyz"), columns=list("xyz"))
    quartiles = pd.DataFrame(
        {"group": ["0"], "q1": [1.0], "median": [2.0], "q3": [3.0], "lower": [0.5], "upper": [4.0]}
    )
    lines = charts.grouped_lines(
        df, "period", "estimate", low="low", high="high", support="support", reference=0.5
    )
    figures = [
        charts.bar_with_intervals(df, "group"),
        lines,
        charts.box_from_quartiles(quartiles, "group"),
        charts.heatmap(matrix, hover=matrix.astype(str)),
    ]
    traces = {trace.type for fig in figures for trace in fig.data}
    assert traces <= {"bar", "scatter", "box", "heatmap"}
    assert all(fig.layout.title.x == 0.5 for fig in figures)
    assert lines.data[0].marker.color[2] == THEME["insufficient"]
    assert lines.layout.yaxis2.title.text == "Support"  # the support axis keeps its own title
    grouped = charts.grouped_lines(df.assign(level=["x", None, "x", None]), "period",
                                   "estimate", group="level")  # fmt: skip
    assert [trace.name for trace in grouped.data] == ["x", "null"]  # a null line is drawn last
    assert lines.layout.yaxis.range[1] == pytest.approx(1.25 * 0.5)  # the reference stays in view
    heat = figures[3].layout  # every label shown, the paper just wider than the square
    assert heat.xaxis.tickvals == heat.yaxis.tickvals == ("x", "y", "z")
    # the paper holds the square (kept square by scaleanchor) and is at least 560 px for the title
    assert heat.width - heat.margin.l - heat.margin.r >= heat.height - heat.margin.t - heat.margin.b
    assert heat.width >= 560
    with pytest.raises(ValueError, match="square"):
        charts.heatmap(matrix.iloc[:2])


def test_grouped_lines_over_a_features_groups() -> None:
    """Lines over a feature's groups keep the data's group order (not plotly's sort), padded half
    a slot at both ends, one line per level under the legend's title."""
    groups = ["< 50", "[50, 100)", "≥ 100", "null"]
    df = pd.DataFrame(
        {"feature_group": np.repeat(groups, 2), "level": ["b", "a"] * 4,
         "lift": np.linspace(0.5, 2.0, 8), "insufficient": False}
    )  # fmt: skip
    fig = charts.grouped_lines(df, "feature_group", "lift", group="level", reference=1.0,
                               x_title="income", legend_title="segment")  # fmt: skip
    assert list(fig.layout.xaxis.categoryarray) == groups
    assert fig.layout.xaxis.range == (-0.5, 3.5)
    assert [trace.name for trace in fig.data] == ["b", "a"]
    assert fig.layout.legend.title.text == "segment" and fig.layout.xaxis.title.text == "income"


def test_grouped_lines_take_their_order_and_colours_from_group_order() -> None:
    """`group_order` orders the lines and gives each the colour of its position (an absent group
    keeps its slot); a null group takes the null colour; a group the order lacks fails."""
    df = pd.DataFrame(
        {"feature_group": ["g1", "g2"] * 3, "level": ["b", "b", "a", "a", None, None],
         "lift": np.linspace(0.5, 2.0, 6), "insufficient": False}
    )  # fmt: skip
    fig = charts.grouped_lines(df, "feature_group", "lift", group="level",
                               group_order=["a", "x", "b", "null"])  # fmt: skip
    assert [trace.name for trace in fig.data] == ["a", "b", "null"]
    sequence = THEME["sequence"]
    colours = [trace.line.color for trace in fig.data]
    assert colours == [sequence[0], sequence[2], THEME["null"]]
    with pytest.raises(ValueError, match=r"group_order lacks the groups \['b'\]"):
        charts.grouped_lines(df, "feature_group", "lift", group="level",
                             group_order=["a", "null"])  # fmt: skip


def test_y_format_shows_on_the_axis_and_the_hover() -> None:
    """A binary rate reads as a percentage on the axis and in the hover, of bars and lines; with
    None the axis keeps plotly's default and the bars' hover four significant digits."""
    rate = TASK_SPECS["binary"]["axis_format"]
    df = _groups(3).assign(period=["a", "b", "c"])
    bars = charts.bar_with_intervals(df, "group", y_format=rate)
    assert bars.layout.yaxis.tickformat == rate
    assert f"%{{y:{rate}}} [%{{customdata[0]:{rate}}}" in bars.data[0].hovertemplate
    lines = charts.grouped_lines(df, "period", "estimate", y_format=rate)
    assert lines.layout.yaxis.tickformat == lines.layout.yaxis.hoverformat == rate
    plain = charts.bar_with_intervals(df, "group")
    assert plain.layout.yaxis.tickformat is None and "%{y:.4g}" in plain.data[0].hovertemplate
    assert charts.grouped_lines(df, "period", "estimate").layout.yaxis.hoverformat is None


def test_line_range_caps_the_grey_points_at_twice_the_supported() -> None:
    """A line chart's top is min(every point, twice the highest supported point): a grey point
    within the cap sets it (its interval does not), one above runs off; with every point grey,
    every point and interval sets it."""
    df = _groups(4, insufficient=(3,)).assign(period=["a", "b", "c", "d"])
    top = df.loc[:2, "estimate"].max()
    df.loc[3, ["estimate", "high"]] = [1.5 * top, 9 * top]
    fig = charts.grouped_lines(df, "period", "estimate", low="low", high="high")
    assert fig.layout.yaxis.range == pytest.approx((0, 1.25 * 1.5 * top))
    df.loc[3, "estimate"] = 5 * top
    capped = charts.grouped_lines(df, "period", "estimate", low="low", high="high")
    assert capped.layout.yaxis.range == pytest.approx((0, 1.25 * 2 * top))  # the grey point is off
    grey = charts.grouped_lines(df.assign(insufficient=True), "period", "estimate", low="low",
                                high="high")  # fmt: skip
    assert grey.layout.yaxis.range == pytest.approx((0, 1.25 * 9 * top))


def test_grouped_lines_on_a_numeric_x() -> None:
    """`x_numeric` draws the shares as numbers on a linear [0, 1] axis shown as percentages, a
    `random` line on the diagonal; support bars over a numeric x are refused."""
    share = np.linspace(0.01, 1.0, 100)
    df = pd.DataFrame(
        {"feature": np.repeat(["income", "random"], 100), "share": np.tile(share, 2),
         "capture": np.concatenate([np.sqrt(share), share])}
    )  # fmt: skip
    fig = charts.grouped_lines(df, "share", "capture", group="feature", insufficient=None,
                               x_numeric=True)  # fmt: skip
    axis = fig.layout.xaxis
    assert axis.type == "linear" and axis.range == (0, 1) and axis.tickformat == ".0%"
    (random,) = [trace for trace in fig.data if trace.name == "random"]
    assert random.x.dtype.kind == "f" and np.allclose(random.x, random.y)
    with pytest.raises(ValueError, match="x_numeric"):
        charts.grouped_lines(df.assign(support=1), "share", "capture", support="support",
                             insufficient=None, x_numeric=True)  # fmt: skip


def test_side_by_side_keeps_both_panels() -> None:
    """A lift chart beside a line with support bars: every trace, the support bars on the right
    panel's secondary axis, both panels' titles, axes and reference lines, one grey note."""
    df = _groups(4, insufficient=(1,)).assign(period=["p1", "p2", "p3", "p4"])
    lift = charts.lift_chart(df.assign(lift=df["estimate"] / 0.03, lift_low=df["low"] / 0.03,
                                       lift_high=df["high"] / 0.03),
                             "group", title="income", x_title="income")  # fmt: skip
    lines = charts.grouped_lines(df, "period", "estimate", support="support", reference=0.5,
                                 from_zero=False, title="Concordance per period",
                                 x_title="Period", y_title="Concordance")  # fmt: skip
    fig = charts.side_by_side(lift, lines)
    assert len(fig.data) == len(lift.data) + len(lines.data)
    assert [t.type for t in fig.select_traces(row=1, col=2, secondary_y=True)] == ["bar"]
    texts = [annotation.text for annotation in fig.layout.annotations]
    assert {"income", "Concordance per period"} <= set(texts)
    assert texts.count("grey = insufficient support") == 1
    dashed = {(s.xref, s.yref, s.y0) for s in fig.layout.shapes if s.line.dash == "dash"}
    assert dashed == {("x domain", "y", 1.0), ("x2 domain", "y2", 0.5)}  # primary axes
    (left_x,) = fig.select_xaxes(row=1, col=1)
    assert left_x.title.text == "income" and left_x.categoryarray == lift.layout.xaxis.categoryarray
    (left_y,) = fig.select_yaxes(row=1, col=1)
    assert left_y.title.text == "Lift vs base rate (1 = base)"
    (right_x,) = fig.select_xaxes(row=1, col=2)
    assert right_x.title.text == "Period" and right_x.range == lines.layout.xaxis.range
    (right_y,) = fig.select_yaxes(row=1, col=2, secondary_y=False)
    assert right_y.title.text == "Concordance" and right_y.range == lines.layout.yaxis.range
    (support_y,) = fig.select_yaxes(row=1, col=2, secondary_y=True)
    assert support_y.title.text == "Support"
    assert fig.layout.meta == {"reference": [1.0, 0.5], "insufficient": True}
    with pytest.raises(ValueError, match="single-panel"):
        charts.side_by_side(fig, lift)
    by_level = charts.grouped_lines(df.assign(level=["x", "y", "x", "y"]), "period", "estimate",
                                    group="level", legend_title="segment")  # fmt: skip
    assert charts.side_by_side(lift, by_level).layout.legend.title.text == "segment"
    with pytest.raises(ValueError, match="the left figure shows a legend"):
        charts.side_by_side(by_level, lift)


def test_side_by_side_refuses_a_heatmap_and_a_figure_without_meta() -> None:
    """A heatmap (its square cells need their own axes) and a figure not made by a primitive
    (no `layout.meta`) are refused."""
    bars = charts.bar_with_intervals(_groups(3), "group")
    matrix = pd.DataFrame(np.eye(2), index=list("xy"), columns=list("xy"))
    with pytest.raises(ValueError, match="single-panel"):
        charts.side_by_side(bars, charts.heatmap(matrix))
    with pytest.raises(ValueError, match="single-panel"):
        charts.side_by_side(go.Figure(go.Bar(x=["a"], y=[1])), bars)


def test_style_table_greys_rows_and_cells_and_colours_lift() -> None:
    """Greyed rows and cells carry the insufficient colour; lift cells are coloured by lift; the
    caption carries its own style, so a notebook shows it as the report does."""
    df = pd.DataFrame({"estimate": [0.1, 0.2, np.nan], "support": [5, 500, 70]})
    styler = style_table(df, {"estimate": "{:.1%}"}, greyed=pd.Series([True, False, False]))
    uuid = styler.uuid
    rows = table_html(styler, "a")
    assert styler.uuid == uuid  # a notebook's Styler keeps its own CSS ids
    assert rows.count(THEME["insufficient"]) >= 1 and "#T_a_row0_col0, #T_a_row0_col1" in rows
    assert "10.0%" in rows
    cells = pd.DataFrame({"estimate": [False, True, False]})
    lift = pd.DataFrame({"estimate": [2.0, 0.5, np.nan]})
    html = table_html(style_table(df, greyed=cells, lift=lift, bar="support", caption="c<"), "b")
    assert "rgba(217, 130, 43" in html  # lift 2 is the full "high" colour
    assert "#T_b_row1_col0 {\n  color:" in html and "#T_b_row0_col0 {" in html
    assert "linear-gradient" in html and "<caption>c&lt;</caption>" in html
    assert "#T_b caption {\n  caption-side: top;\n  text-align: left;" in html


def test_style_table_escapes_axis_names_and_reads_a_missing_flag_as_false() -> None:
    """The index's and the columns' names are escaped like the labels (the lift and grey still
    land on their cells); a missing greyed flag is not greyed, without a pandas warning."""
    df = pd.DataFrame({"a": [0.1, 0.2]}, index=pd.Index(["x", "y"], name="<b>"))
    df.columns.name = "c&d"
    greyed = pd.Series([None, True], index=df.index, dtype=object)
    lift = pd.DataFrame({"a": [2.0, np.nan]}, index=df.index)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        html = table_html(style_table(df, greyed=greyed, lift=lift), "e")
    assert "&lt;b&gt;" in html and "c&amp;d" in html and "<b>" not in html
    assert "#T_e_row0_col0 {\n  background-color: rgba(217, 130, 43" in html  # not greyed
    assert f"#T_e_row1_col0 {{\n  color: {THEME['insufficient']}" in html


def test_choices_block_reads_config_and_caller_values(cc_config: UseCaseConfig) -> None:
    """A path row reads the resolved config; a path-less row takes the caller's value; a
    path-less row without one and a value for a row not shown fail."""
    names = ["task", "kind_overrides", "candidate_count"]
    table = choices_block(cc_config, names, {"candidate_count": 139}).data
    assert list(table.columns) == ["Choice", "Value", "Alternatives"]
    assert list(table["Value"]) == ["binary", "none", "139"]
    with pytest.raises(ValueError, match="Candidate features"):
        choices_block(cc_config, ["candidate_count"], {})
    with pytest.raises(ValueError, match=r"not in names: \['bins'\]"):
        choices_block(cc_config, ["task"], {"bins": 10})
    window = choices_block(cc_config, ["observation_window"], {}).data["Value"][0]
    assert window == "first: 2025-03-31, last: 2025-08-31"


def test_appendix_and_format_of(cc_config: UseCaseConfig) -> None:
    """The appendix shows the timings at one decimal under the caller's caption; `format_of`
    gives a column its format by name or prefix, None for an unknown name."""
    decisions = pd.DataFrame({"seq": [1], "op": ["run"]})
    views = appendix(cc_config, decisions, {"frames": 1.26}, "Seconds per phase")
    assert list(views) == ["resolved_config", "decisions", "timings"]
    timings = table_html(views["timings"], "t")
    assert ">1.3<" in timings and "Seconds per phase" in timings
    assert views["resolved_config"].startswith("<pre>")
    assert format_of("estimate", "binary") == TASK_SPECS["binary"]["estimate_format"]
    assert format_of("share_kept", "regression") == SHARE
    assert format_of("p10_amount", "binary") is plain_number
    assert format_of("feature", "binary") is None


def test_text_blocks() -> None:
    """Headline, warnings, "not available" and how-to-read escape their text and follow the
    spec's wording; the headline reads each number in the format it is given (no scientific
    notation below 1e-4), refuses a number without one and carries its own layout for a
    notebook without the report's CSS."""
    rate = TASK_SPECS["binary"]["estimate_format"]
    values = {"clients <": 1234, "snapshot_rate": 0.00005, "eligible_share": 0.6449}
    numbers = headline(
        values, {"clients <": "{:,.0f}", "snapshot_rate": rate, "eligible_share": SHARE}
    )
    assert "1,234" in numbers and "&lt;" in numbers
    assert ">0.01%<" in numbers and ">64.5%<" in numbers and ">snapshot rate<" in numbers
    missing = headline({"none": None, "nan": float("nan")}, {"none": SHARE, "nan": plain_number})
    assert missing.count(">n/a<") == 2
    with pytest.raises(ValueError, match=r"no format for \['rows'\]"):
        headline({"rows": 3}, {})
    assert 'style="display: inline-block; margin: 4px 16px 4px 0"' in numbers
    assert warnings_block([]) == "<p>No warnings.</p>"
    assert warnings_block(["a & b", "c"]).count("<li>") == 2
    assert not_available("x's view") == "<p>Not available: x&#x27;s view.</p>"
    binned = _how_to_read(100, "rate", "positive events", 20)
    exact = _how_to_read(None, "mean", "units with a non-zero target", 20)
    assert len(binned) == len(exact) == 5
    assert "100 quantile bins" in binned[0] and "quantile" not in exact[0]
    assert "base rate" in binned[1] and "base mean" in exact[1]
    assert "min_events units with a non-zero target (20 in" in exact[3]
    assert exact[4].startswith("<p>null is")


def test_style_table_bar_starts_at_bar_min() -> None:
    """With `bar_min=0.5` a concordance of 0.6 fills 40% of the way to the largest (0.75), and a
    value at or below 0.5 draws no bar; the default starts at 0."""
    df = pd.DataFrame({"concordance": [0.45, 0.5, 0.6, 0.75]})
    html = table_html(style_table(df, bar="concordance", bar_min=0.5), "m")
    assert "#T_m_row0_col0, #T_m_row1_col0 {\n  width: 10em;\n}" in html
    assert "#T_m_row2_col0 {\n  width: 10em;\n  background: linear-gradient(90deg, " in html
    assert f"{THEME['bar']} 40.0%" in html
    assert f"{THEME['bar']} 80.0%" in table_html(style_table(df, bar="concordance"), "z")
