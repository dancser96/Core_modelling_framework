"""Tests of the model charts on small constructed tables with the columns of Evaluation's tables:
each chart builds, has one trace per part plus its reference line, copes with one part only and
any number of rows, and a missing column fails loud. No pixel checks."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from core_modelling.reporting.model_charts import (
    capture_chart,
    metric_lines,
    pr_chart,
    predicted_vs_observed,
    reliability_chart,
    roc_chart,
    score_distribution,
)
from core_modelling.reporting.theme import THEME


def _curves(parts: tuple[str, ...] = ("test", "validation"), bins: int = 40) -> pd.DataFrame:
    """A threshold table per part: cumulative from the top, `bins` rows, a 5% rate."""
    frames = []
    for shift, part in enumerate(parts):
        depth = np.arange(1, bins + 1) / bins
        capture = depth ** (0.5 + 0.1 * shift)
        frames.append(pd.DataFrame({
            "part": part, "score_bin": np.arange(bins, 0, -1), "threshold": depth[::-1],
            "rows": depth * 1000, "target": capture * 50, "depth": depth, "capture": capture,
            "rate": capture * 0.05 / depth, "lift": capture / depth,
            "false_positive_rate": (depth - capture * 0.05) / 0.95,
        }))  # fmt: skip
    return pd.concat(frames, ignore_index=True)


def _reliability(parts: tuple[str, ...] = ("test", "validation"), groups: int = 10) -> pd.DataFrame:
    """A reliability table per part: rare rates, slightly over-predicted."""
    predicted = np.linspace(0.002, 0.05, groups)
    return pd.concat([
        pd.DataFrame({"part": part, "group": np.arange(groups), "rows": 500,
                      "predicted": predicted, "observed": predicted * 0.9})
        for part in parts
    ], ignore_index=True)  # fmt: skip


def _distribution(with_part: bool = True) -> pd.DataFrame:
    """A score-distribution table: two classes over 20 bins, the ratio to chance by percentile."""
    bins = np.arange(20)
    frames = []
    for part in ("test", "validation") if with_part else ("",):
        for label, weight in (("0", np.ones(20)), ("1", bins + 1.0)):
            share = weight / weight.sum()
            frame = pd.DataFrame({"score_bin": bins, "score": (bins + 1) / 21,
                                  "percentile": (bins + 1) / 20, "class": label, "rows": 100,
                                  "share": share, "ratio": share / 0.05})  # fmt: skip
            frames.append(frame.assign(part=part) if with_part else frame)
    return pd.concat(frames, ignore_index=True)


def _metrics(metric: str = "auc") -> pd.DataFrame:
    """A metrics table: three test periods, the validation period, and a pooled row per part,
    one test period insufficient."""
    rows = []
    for part, periods in (("test", ["2025-01-01", "2025-02-01", "2025-03-01"]),
                          ("validation", ["2025-06-01"])):  # fmt: skip
        for i, period in enumerate([*periods, "pooled"]):
            value = 0.70 + 0.01 * i
            rows.append({"metric": metric, "part": part,
                         "period": period if period == "pooled" else pd.Timestamp(period),
                         "stratum": "all", "level": "all", "value": value, "low": value - 0.03,
                         "high": value + 0.03, "rows": 1000, "events": 50,
                         "insufficient": part == "test" and i == 1})  # fmt: skip
    return pd.DataFrame(rows)


def _names(fig: go.Figure) -> list[str]:
    """The names of a figure's traces."""
    return [trace.name for trace in fig.data]


@pytest.mark.parametrize(("chart", "random"), [(roc_chart, "random"), (capture_chart, "random")])
def test_curve_charts_have_a_line_per_part_and_the_diagonal(chart: object, random: str) -> None:
    """ROC and capture: a line per part in the table's bins, then the dashed diagonal; the axes
    stop at 100%."""
    fig = chart(_curves())
    assert _names(fig) == ["test", "validation", random]
    assert len(fig.data[0].x) == 40
    assert list(fig.layout.yaxis.range) == [0, 1]
    assert fig.data[-1].line.dash == "dash"


def test_curve_charts_cope_with_one_part_and_another_number_of_bins() -> None:
    """A single part and 200 bins draw the same way; the part keeps its colour."""
    both = roc_chart(_curves())
    one = roc_chart(_curves(parts=("validation",), bins=200))
    assert _names(one) == ["validation", "random"]
    assert len(one.data[0].x) == 200
    assert one.data[0].line.color == THEME["sequence"][1] != both.data[0].line.color


def test_pr_chart_marks_each_parts_base_rate() -> None:
    """A dashed line per part at the rate of its deepest row, however the rows are ordered."""
    curves = _curves().sample(frac=1.0, random_state=0)
    fig = pr_chart(curves)
    assert _names(fig) == ["test", "validation", "base rate, test", "base rate, validation"]
    assert list(fig.data[2].y) == pytest.approx([0.05, 0.05])


def test_reliability_chart_zooms_to_the_rare_rates() -> None:
    """One line per part and the diagonal; both axes run from zero to 1.25 times the highest
    value, not to 100%, and the diagonal ends there."""
    fig = reliability_chart(_reliability())
    assert _names(fig) == ["test", "validation", "perfect"]
    assert list(fig.layout.xaxis.range) == pytest.approx([0, 1.25 * 0.05])
    assert list(fig.layout.yaxis.range) == list(fig.layout.xaxis.range)
    assert fig.data[-1].x[-1] == pytest.approx(0.0625)


def test_predicted_vs_observed_draws_20_groups_with_the_diagonal() -> None:
    """The regression chart: a line per part over 20 groups and the diagonal."""
    amounts = _reliability(groups=20).assign(predicted=lambda d: d["predicted"] * 1e4)
    fig = predicted_vs_observed(amounts.assign(observed=amounts["predicted"] * 0.9))
    assert _names(fig) == ["test", "validation", "perfect"]
    assert len(fig.data[0].x) == 20


def test_score_distribution_draws_each_class_per_part() -> None:
    """A panel per part with a line per class and the dashed chance line at 1, one legend entry
    each, a class' colour the same in every panel; without a `part` column one panel."""
    fig = score_distribution(_distribution())
    assert len(fig.data) == 6
    assert [t.showlegend for t in fig.data] == [True, True, True, False, False, False]
    assert fig.data[0].line.color == fig.data[3].line.color
    assert list(fig.data[2].y) == [1, 1]
    single = score_distribution(_distribution(with_part=False))
    assert _names(single) == ["class 0", "class 1", "chance (ratio 1)"]


def test_metric_lines_greys_insufficient_and_leaves_out_the_pooled_row() -> None:
    """A line per part over the periods only; the validation period is a point of its part; the
    insufficient point is grey, not dropped."""
    fig = metric_lines(_metrics())
    assert _names(fig) == ["test", "validation"]
    assert len(fig.data[0].x) == 3
    assert len(fig.data[1].x) == 1
    assert fig.data[0].marker.color[1] == THEME["insufficient"]
    assert fig.data[0].marker.color[0] == THEME["sequence"][0]
    assert "pooled" not in {str(x) for trace in fig.data for x in trace.x}


def test_metric_lines_refuse_two_metrics() -> None:
    """The table holds one metric: two fail loud."""
    both = pd.concat([_metrics("auc"), _metrics("brier_skill")], ignore_index=True)
    with pytest.raises(ValueError, match="one metric at a time"):
        metric_lines(both)


@pytest.mark.parametrize(
    ("chart", "table", "column"),
    [
        (roc_chart, _curves(), "false_positive_rate"),
        (roc_chart, _curves(), "part"),
        (pr_chart, _curves(), "rate"),
        (pr_chart, _curves(), "depth"),
        (capture_chart, _curves(), "capture"),
        (reliability_chart, _reliability(), "observed"),
        (predicted_vs_observed, _reliability(), "predicted"),
        (score_distribution, _distribution(), "percentile"),
        (score_distribution, _distribution(), "ratio"),
        (metric_lines, _metrics(), "insufficient"),
    ],
)  # fmt: skip
def test_a_missing_column_fails_loud(chart: object, table: pd.DataFrame, column: str) -> None:
    """Every chart names the chart and the column it lacks."""
    with pytest.raises(ValueError, match=f"{chart.__name__}: .*{column}"):
        chart(table.drop(columns=column))
