"""Tests of the model results report's explanation views on small constructed tables, no Spark:
each view builds for both tasks, the partial dependence chart draws a numeric and a categorical,
the beeswarm's rows are seeded and capped, the waterfall labels read `feature = value`, the
statistics read the sampled rows only, and a table not computed, or not whole, shows its
reason."""

from collections.abc import Callable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from core_modelling.config import UseCaseConfig
from core_modelling.evaluation import views_explain as views
from core_modelling.evaluation.effects import EFFECTS, effect_table
from core_modelling.evaluation.permutation import permutation_unavailable
from core_modelling.reporting.blocks import not_available
from core_modelling.reporting.explain_charts import ROW_CAP, pdp_ice_chart
from core_modelling.statistics.distributions import range_label

EDGES = np.array([1.0, 2.0, 3.0])  # numeric `a`'s buckets: < 1, [1, 2), [2, 3), ≥ 3
VIEWS = [views.importance_view, views.beeswarm_view, views.effects_view, views.waterfalls_view,
         views.permutation_importance_view, views.pdp_ice_view]  # fmt: skip


def _sample(rows: int, seed: int) -> pd.DataFrame:
    """A sample in Evaluation's `contributions` shape for numeric `a` (every ninth null) and
    categorical `b`, with `base_value`, `score`, the three waterfall rows marked and every row
    `sampled` but the highest, a waterfall row outside the hashed rows."""
    rng = np.random.default_rng(seed)
    a = pd.Series(rng.uniform(0, 4, rows)).mask(np.arange(rows) % 9 == 0)
    b = pd.Series(rng.choice(["x", "y", "z"], rows)).mask(np.arange(rows) % 11 == 0)
    frame = pd.DataFrame({"a": a, "b": b, "a__contribution": rng.normal(0, 1, rows),
                          "b__contribution": rng.normal(0, 0.5, rows),
                          "base_value": -2.0})  # fmt: skip
    frame["score"] = rng.uniform(0, 1, rows)
    frame["waterfall"] = None
    frame.loc[:2, "waterfall"] = ["highest", "cut", "typical"]
    frame["sampled"] = frame["waterfall"].ne("highest")
    return frame


def _group_rows(feature: str, groups: list[str]) -> pd.DataFrame:
    """An EDA group table for `feature`: rows, support, the estimate's interval and the lift
    over a base of 0.1."""
    estimate = np.linspace(0.05, 0.2, len(groups))
    return pd.DataFrame({"feature": feature, "group": groups, "rows": 100, "support": 30.0,
                         "estimate": estimate, "low": estimate * 0.8, "high": estimate * 1.2,
                         "lift": estimate / 0.1, "insufficient": False})  # fmt: skip


def _pdp(feature: str, levels: list[str] | None) -> pd.DataFrame:
    """`partial_dependence` rows of one feature: three grid points (a categorical's `levels`),
    the mean and two ICE rows."""
    rows = []
    for point in range(3):
        value = np.nan if levels else float(point)
        level = levels[point] if levels else None
        rows.append((feature, "pdp", pd.NA, point, value, level, 0.1 * point + 0.2))
        rows += [(feature, "ice", ice, point, value, level, 0.1 * point + ice / 10)
                 for ice in (0, 4)]  # fmt: skip
    columns = ["feature", "curve", "row", "point", "value", "level", "score"]
    return pd.DataFrame(rows, columns=columns).astype({"row": "Int64"})


def _tables(rows: int = 60, seed: int = 0) -> tuple[dict[str, pd.DataFrame], dict]:
    """Constructed tables and meta for the six views: the sample, Training's sample, the
    feature table, permutation importance, partial dependence and the effects table of `a` and
    `b` from constructed EDA groups."""
    numeric = [range_label(EDGES, 0, 1), range_label(EDGES, 2, 3), "null"]
    permutation = pd.DataFrame({
        "cluster": pd.array([1, pd.NA], dtype="Int64"), "members": [["a"], ["b"]],
        "loss_change": [0.02, 0.01], "loss_change_sd": [0.004, 0.012],
        "importance_rank": [1, 2], "contribution_share": [0.6, 0.4],
        "contribution_rank": [1, 2], "rank_gap": [0, 0], "disagrees": False,
        "rank_correlation": 1.0,
    })  # fmt: skip
    sample = _sample(rows, seed)
    effects = effect_table(
        sample, _group_rows("a", numeric), _group_rows("b", ["x", "__other__", "null"]),
        pd.DataFrame({"feature": "a", "position": [0, 1, 2], "edge": EDGES}),
        pd.Series({"a": "numeric", "b": "categorical"}), ["a", "b"],
    )  # fmt: skip
    tables = {
        "contributions": sample,
        views.TRAIN_SAMPLE: _sample(rows, seed + 1).drop(columns=["score", "waterfall", "sampled"]),
        "features": pd.DataFrame({"feature": ["a", "b"], "contribution_share": [0.6, 0.4]}),
        "permutation_importance": permutation,
        "partial_dependence": pd.concat([_pdp("a", None), _pdp("b", ["x", "y", "z"])]),
        EFFECTS: effects,
    }
    meta = {"choices": {"effect_features": ["a", "b"],
                        "explanation_cut": {"slice": "top 1%", "score": 0.9},
                        "permutation_rows": 400, "objective": "poisson"},
            "unavailable": {}, "row_loss": None}  # fmt: skip
    return tables, meta


def _figures(blocks: list) -> list[go.Figure]:
    """Every figure among the blocks, subsections included."""
    found = []
    for block in blocks:
        if isinstance(block, tuple):
            found += _figures(block[1])
        elif isinstance(block, go.Figure):
            found.append(block)
    return found


@pytest.mark.parametrize("view", VIEWS, ids=lambda view: view.__name__)
def test_each_view_builds_for_both_tasks(
    view: Callable[..., list], cc_config: UseCaseConfig, regression_cfg: UseCaseConfig
) -> None:
    """Every view returns blocks for a binary and a regression config, each figure with data."""
    tables, meta = _tables()
    for resolved in (cc_config, regression_cfg):
        blocks = view(tables, meta, resolved)
        assert blocks
        assert all(figure.data for figure in _figures(blocks))


def test_the_scale_note_reads_the_runs_objective_not_the_configs(
    regression_cfg: UseCaseConfig,
) -> None:
    """A run trained under Poisson reads the Poisson log scale, and one trained under squared
    error the prediction's own, whatever objective the evaluating config names."""
    _, meta = _tables()
    assert "log scale of the poisson objective" in views._scale_note(meta, regression_cfg)
    meta["choices"]["objective"] = "squared_error"
    assert "the prediction&#x27;s own scale" in views._scale_note(meta, regression_cfg)


def test_pdp_ice_chart_draws_numeric_and_categorical() -> None:
    """A numeric draws one partial dependence line over one ICE trace of both rows' lines, each
    ended by a gap; a categorical draws points on a category axis in grid order."""
    numeric = pdp_ice_chart(_pdp("a", None))
    ice, pdp = numeric.data
    assert pdp.mode == "lines+markers" and list(pdp.x) == [0.0, 1.0, 2.0]
    assert ice.mode == "lines" and np.isnan(np.asarray(ice.y, dtype=float)).sum() == 2
    levels = pdp_ice_chart(_pdp("b", ["x", "y", "z"]))
    assert [trace.mode for trace in levels.data] == ["markers", "markers"]
    assert levels.layout.xaxis.type == "category"
    assert list(levels.layout.xaxis.categoryarray) == ["x", "y", "z"]
    with pytest.raises(ValueError, match="one feature"):
        pdp_ice_chart(pd.concat([_pdp("a", None), _pdp("b", ["x", "y", "z"])]))


def test_beeswarm_is_seeded_and_capped(cc_config: UseCaseConfig) -> None:
    """Above the cap the beeswarm draws `ROW_CAP` rows per feature, the same rows on two calls."""
    tables, meta = _tables(rows=2000)
    first, second = (_figures(views.beeswarm_view(tables, meta, cc_config))[0] for _ in range(2))
    assert sum(len(trace.x) for trace in first.data) == ROW_CAP * 2
    for one, two in zip(first.data, second.data, strict=True):
        np.testing.assert_array_equal(one.x, two.x)


def test_waterfall_labels_read_feature_equals_value(cc_config: UseCaseConfig) -> None:
    """Each of the three waterfalls labels its bars `feature = value`, a missing value `null`."""
    tables, meta = _tables()
    figures = _figures(views.waterfalls_view(tables, meta, cc_config))
    assert len(figures) == 3
    sample = tables["contributions"]
    for figure, (_, row) in zip(figures, sample.iloc[:3].iterrows(), strict=True):
        expected = "null" if pd.isna(row["a"]) else f"{row['a']:.4g}"
        assert f"a = {expected}" in list(figure.layout.yaxis.ticktext)


def test_permutation_importance_shows_its_reason_when_not_available(
    cc_config: UseCaseConfig,
) -> None:
    """With `meta["unavailable"]` naming the table, the view is the reason alone; otherwise the
    table shows the loss change's standard deviation beside it."""
    tables, meta = _tables()
    text, table = views.permutation_importance_view(tables, meta, cc_config)
    html = table.to_html()
    assert "loss_change_sd" in html and "permutation sample of 400 seeded test rows" in html
    assert "not the draw of the rows" in text
    meta["unavailable"] = {"permutation_importance": "the sample holds one cluster"}
    blocks = views.permutation_importance_view(tables, meta, cc_config)
    assert blocks == [not_available("the sample holds one cluster")]


def test_the_reason_a_target_of_one_value_gives_reads_not_available_once(
    cc_config: UseCaseConfig,
) -> None:
    """Evaluation stores the bare reason and the view adds "Not available: " once."""
    tables, meta = _tables()
    reason = permutation_unavailable(pd.DataFrame({"target": [0, 0, 0]}), cc_config, "binary")
    meta["unavailable"] = {"permutation_importance": reason}
    (block,) = views.permutation_importance_view(tables, meta, cc_config)
    assert reason.startswith("0 positive rows in the permutation sample")
    assert block == f"<p>Not available: {reason}.</p>"


def test_the_partial_dependence_shows_the_features_it_left_out(cc_config: UseCaseConfig) -> None:
    """An effect feature null on every sample row is absent from the table: the view says so in
    one line and draws the others."""
    tables, meta = _tables()
    pdp = tables["partial_dependence"]
    tables["partial_dependence"] = pdp.loc[pdp["feature"] != "a"]
    meta["unavailable"] = {"partial_dependence": "null on every sample row: a"}
    blocks = views.pdp_ice_view(tables, meta, cc_config)
    assert not_available("null on every sample row: a") in blocks
    assert len(_figures(blocks)) == 1


def test_the_statistics_read_the_sampled_rows_only(cc_config: UseCaseConfig) -> None:
    """The importance and the beeswarm count the 59 sampled rows, never the highest-score row
    picked by hand; the waterfalls still draw it."""
    tables, meta = _tables()
    importance = views.importance_view(tables, meta, cc_config)
    assert any("Test: the 59 rows" in block for block in importance if isinstance(block, str))
    beeswarm = views.beeswarm_view(tables, meta, cc_config)
    assert any("of the explanation sample&#x27;s 59 test rows" in block for block in beeswarm
               if isinstance(block, str))  # fmt: skip
    assert len(_figures(views.waterfalls_view(tables, meta, cc_config))) == 3
