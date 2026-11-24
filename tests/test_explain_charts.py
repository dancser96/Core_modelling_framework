"""Tests of the explanation charts on constructed contributions: each figure builds for numeric
and categorical features, the row-level charts keep their cap and seed, a missing value is
grey, the waterfall adds up, and the package never imports `shap`."""

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core_modelling.reporting import explain_charts
from core_modelling.reporting.explain_charts import (
    HOVER_FORMAT,
    ROW_CAP,
    beeswarm,
    dependence,
    importance_bar,
    waterfall,
)
from core_modelling.reporting.model_charts import part_colour
from core_modelling.reporting.theme import THEME

GREY = THEME["contribution"]["missing"]
NEUTRAL = THEME["contribution"]["neutral"]


def _frames(rows: int = 3000) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Contributions and raw values for three features: `age` (numeric, its value the row's
    number, every tenth missing), `region` (categorical, every seventh missing) and `small`
    (numeric, near-zero contributions)."""
    rng = np.random.default_rng(1)
    row = np.arange(rows, dtype=float)
    age = np.where(row % 10 == 0, np.nan, row)
    region = pd.Series(np.array(["north", "south", "east"])[np.arange(rows) % 3], dtype=object)
    region[np.arange(rows) % 7 == 0] = None
    values = pd.DataFrame({"age": age, "region": region, "small": rng.normal(size=rows)})
    contributions = pd.DataFrame({
        "age": rng.normal(0, 1.0, rows), "region": rng.normal(0, 0.5, rows),
        "small": rng.normal(0, 0.01, rows),
    })  # fmt: skip
    return contributions, values


def _points(fig: object, axis: str = "x") -> list[float]:
    """Every marker point's coordinate on `axis` across the figure's scatter traces."""
    return [v for t in fig.data if t.type == "scatter" for v in getattr(t, axis)]


def _feature_of(hover: str, features: list[str]) -> str:
    """The feature a beeswarm trace draws, read from its hover (`<br>feature = value`)."""
    return next(feature for feature in features if f"<br>{feature} = " in hover)


def test_importance_bar_ranks_shares_and_compares() -> None:
    """Each feature's share of the mean absolute contribution, largest first, the rest's share in
    one bar, the shares adding to one; `compare`'s shares come from its own frame, a second bar
    per feature in the same order, with a legend; the axis reads as a percent."""
    contributions, _ = _frames(200)
    fig = importance_bar(contributions, top=2)
    assert list(fig.data[0].y) == ["age", "region", "Sum of 1 other features"]
    mean = contributions.abs().mean()
    assert fig.data[0].x[0] == pytest.approx(mean["age"] / mean.sum())
    assert fig.data[0].x[2] == pytest.approx(mean["small"] / mean.sum())
    assert sum(fig.data[0].x) == pytest.approx(1.0)
    assert fig.layout.xaxis.tickformat == ".0%"
    assert fig.data[0].name is None and "(" not in fig.data[0].hovertemplate  # no part named
    compare = contributions.assign(age=3 * contributions["age"])
    compared = importance_bar(contributions, compare=compare)
    assert len(compared.data) == 2 and compared.layout.showlegend
    other = compare.abs().mean()
    assert compared.data[1].x[0] == pytest.approx(other["age"] / other.sum())
    assert compared.data[0].name == "test" and "(test)" in compared.data[0].hovertemplate
    with pytest.raises(ValueError, match="same features"):
        importance_bar(contributions, compare=contributions[["age"]])
    with pytest.raises(ValueError, match="the contributions hold only zero"):
        importance_bar(contributions * 0)
    with pytest.raises(ValueError, match="compare holds only zero"):
        importance_bar(contributions, compare=contributions * 0)


def test_beeswarm_caps_and_seeds_the_rows() -> None:
    """At most 1,500 seeded rows per feature, the same rows for every feature (`age`'s value is
    the row's number, so its hover data names the rows), the same points for the same seed."""
    contributions, values = _frames()
    values = values.assign(small=np.arange(len(values), dtype=float))
    fig = beeswarm(contributions, values)
    counts = dict.fromkeys(contributions.columns, 0)
    rows = {"age": set(), "small": set()}
    for trace in fig.data:
        feature = _feature_of(trace.hovertemplate, list(contributions.columns))
        counts[feature] += len(trace.x)
        if feature in rows and trace.customdata is not None:  # the grey points carry no data
            rows[feature] |= set(trace.customdata.tolist())
    assert counts == dict.fromkeys(contributions.columns, ROW_CAP)
    assert rows["age"] < rows["small"]  # the same rows; age's missing ones are grey
    assert _points(fig) == _points(beeswarm(contributions, values))
    assert _points(fig) != _points(beeswarm(contributions, values, seed=1))
    for clients in (ROW_CAP + 1, 0, -1):
        with pytest.raises(ValueError, match="between 1 and 1,500"):
            beeswarm(contributions, values, clients=clients)


def test_beeswarm_colours_missing_grey_and_levels_neutral() -> None:
    """A missing value is grey (drawn under the coloured points); a categorical's known values
    take the neutral colour; a numeric's are on the value scale, with one colour bar."""
    contributions, values = _frames(700)
    fig = beeswarm(contributions, values)
    by_feature: dict[str, list] = {}
    for trace in fig.data:
        by_feature.setdefault(_feature_of(trace.hovertemplate, list(values.columns)), []).append(
            trace
        )
    grey, coloured = by_feature["age"]
    assert grey.marker.color == GREY and len(grey.x) == values["age"].isna().sum()
    assert coloured.marker.colorscale is not None
    assert by_feature["region"][0].marker.color == GREY
    assert by_feature["region"][1].marker.color == NEUTRAL
    assert sum(bool(t.marker.showscale) for t in fig.data) == 1


def test_waterfall_adds_up_from_base_to_margin() -> None:
    """Each bar starts where the one below ends, the first at the base, the last ending at the
    base plus every contribution; labels read `feature = value`, a missing value `null`."""
    contributions = pd.Series({"a": 0.8, "b": -0.5, "c": 0.1, "d": -0.05, "e": 0.02})
    values = pd.Series({"a": 3.0, "b": "south", "c": np.nan, "d": 12345.678, "e": 1.0})
    fig = waterfall(contributions, base=-2.0, values=values, shown=3)
    bars = fig.data[0]
    # plotly keeps `base` as an object array
    starts, steps = np.array(bars.base, dtype=float), np.array(bars.x)
    assert starts[0] == pytest.approx(-2.0)
    assert np.allclose(starts[1:], starts[:-1] + steps[:-1])
    assert starts[-1] + steps[-1] == pytest.approx(-2.0 + contributions.sum())
    assert list(fig.layout.yaxis.ticktext) == [
        "2 other features", "c = null", "b = south", "a = 3",
    ]  # fmt: skip
    assert bars.marker.color[-1] == THEME["contribution"]["raises"]
    assert steps[0] == pytest.approx(contributions[["d", "e"]].sum())  # the rest, summed
    assert steps[-1] == pytest.approx(contributions["a"])  # a named bar is its contribution


def test_dependence_scatter_numeric_and_categorical() -> None:
    """At most 1,500 seeded points; a missing value sits in the strip on its own axis; a
    categorical's ticks are its levels by rows; `colour` draws one colour bar."""
    contributions, values = _frames()
    numeric = dependence(contributions["age"], values["age"], colour=values["small"])
    assert len(_points(numeric)) == ROW_CAP
    strip = [t for t in numeric.data if t.xaxis == "x2"]
    assert strip and all(t.hovertemplate.startswith("age = null") for t in strip)
    assert sum(bool(t.marker.showscale) for t in numeric.data) == 1
    assert numeric.layout.xaxis.domain == (0.1, 1)
    complete = dependence(contributions["small"], values["small"])
    assert all(t.xaxis == "x" for t in complete.data)  # nothing missing: no strip
    assert complete.layout.xaxis.domain == (0, 1)
    levels = dependence(contributions["region"], values["region"])
    assert list(levels.layout.xaxis.ticktext) == ["east", "north", "south"]
    assert all(t.marker.color == NEUTRAL for t in levels.data)
    assert _points(levels) == _points(dependence(contributions["region"], values["region"]))


def test_contributions_are_checked() -> None:
    """A null contribution, or values on other rows, fail loud."""
    contributions, values = _frames(50)
    holed = contributions.copy()
    holed.iloc[0, 0] = np.nan
    with pytest.raises(ValueError, match="null"):
        importance_bar(holed)
    with pytest.raises(ValueError, match="same order"):
        beeswarm(contributions, values.iloc[::-1])


def test_package_never_imports_shap() -> None:
    """The charts are drawn from the libraries' own contributions: no module of the package
    imports `shap` (D-141 (f))."""
    package = Path(explain_charts.__file__).resolve().parents[1]
    offenders = []
    for path in sorted(package.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(name.split(".")[0] == "shap" for name in names):
                offenders.append(str(path))
    assert not offenders, f"modules importing shap: {offenders}"


def test_the_importance_bar_takes_the_part_colours_not_the_explanation_colours() -> None:
    """Test is the first sequence colour as in every model chart, train out of fold the next;
    the red that means "raises the score" is not an importance's. A lone bar takes test's."""
    contributions, _ = _frames(50)
    colours = [t.marker.color for t in importance_bar(contributions, compare=contributions).data]
    assert colours == [
        part_colour("test"),
        part_colour("train, out of fold", explain_charts.PART_ORDER),
    ]
    assert colours[0] == THEME["sequence"][0]
    assert importance_bar(contributions).data[0].marker.color == THEME["sequence"][0]


def test_the_waterfall_reads_amounts_and_small_steps_in_plain_digits() -> None:
    """A label shows 250,000 and 0.00001234, never `2.5e+05`; a step of 0.004 reads `+0.004`,
    not `+0.00`; the margin's axes are titled."""
    contributions = pd.Series({"income": 0.5, "ratio": 0.004, "other": -0.3})
    values = pd.Series({"income": 250000.0, "ratio": 1.234e-05, "other": 7})
    fig = waterfall(contributions, base=0.0, values=values, shown=3)
    assert list(fig.layout.yaxis.ticktext) == [
        "ratio = 0.00001234",
        "other = 7",
        "income = 250,000",
    ]
    assert list(fig.data[1].text) == ["+0.004", "-0.3", "+0.5"]
    assert fig.layout.yaxis.title.text == "Feature = value"


def test_hovers_format_numbers_in_the_template_and_carry_no_text_per_point() -> None:
    """The beeswarm's and the dependence scatter's hovers keep numeric data and format it in the
    template with d3's decimal notation (no exponent); the row charts title their y axes."""
    contributions, values = _frames(60)
    values = values.assign(age=np.arange(60) * 5000.0)
    swarm = beeswarm(contributions, values)
    age = [t for t in swarm.data if "<br>age = " in t.hovertemplate][-1]
    assert f"%{{customdata:{HOVER_FORMAT}}}" in age.hovertemplate
    assert age.customdata.dtype == np.float32 and age.text is None
    assert all(trace.text is None for trace in swarm.data)
    scatter = dependence(contributions["age"], values["age"])
    assert f"age = %{{x:{HOVER_FORMAT}}}" in scatter.data[-1].hovertemplate
    assert all(trace.text is None for trace in scatter.data)
    assert swarm.layout.yaxis.title.text == "Feature"
    assert importance_bar(contributions).layout.yaxis.title.text == "Feature"
