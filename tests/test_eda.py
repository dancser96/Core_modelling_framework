"""The EDA stage end to end on the unit preset (D-135, D-136): the card config (every candidate)
and a regression variant (a narrow candidate list), each run once in a module fixture. What a
run must leave: every file and table of the stage, `eda.json` with the D-088 population counts
and the settings digest Feature Checks checks, the ledger with every EDA column, a report with
plotly.js once and every section, no stale Feature Checks folder, and no label outside the
window nor any validation-period cell in the counts table (§4.1, §4.4). The views follow the
report's layout, and the exploration functions cut the deep dives' groups and refuse what they
cannot draw.
"""

import json
import re
from collections.abc import Callable
from dataclasses import replace
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest
from pandas.io.formats.style import Styler
from plotly.offline import get_plotlyjs
from pyspark.sql import SparkSession

from core_modelling.artifacts import StageResult, check_upstream, read_stage, settings_digest
from core_modelling.config import UseCaseConfig
from core_modelling.dataset import Frames
from core_modelling.dataset.counts import bin_edges
from core_modelling.eda import compare_sides, lift_by_group, pivot_target, rate_by_period, run_eda
from core_modelling.eda.deep_dives import (
    DEEP_DIVE_GROUPS,
    dive_group_count,
    level_table,
    strata_pivots,
    target_quartiles_by_group,
)
from core_modelling.eda.report import RANKING_VIEW
from core_modelling.eda.run import (
    _check_frame_names,
    _compared_periods,
    _dive_columns,
    _dive_tables,
    _write,
)
from core_modelling.environment import EnvironmentConfig, feature_dir
from core_modelling.ledger import COLUMNS_BY_STAGE, read_ledger
from core_modelling.periods import period_spec
from core_modelling.tasks import TASK_SPECS

ENTITY = "entity_a"
SETTINGS = ["features.kinds", "strata", "eda", "time.validation_period"]
TABLES = {"cells", "client_constant", "population", "funnel", "sources", "target_per_period",
          "ranking", "correlation", "slices", "capture_curve", "profile", "bins", "levels",
          "quartiles", "per_period", "strata", "reference_groups",
          "concordance_per_period"}  # fmt: skip
# The report's sections and subsections in order (a deep dive's and a tag's names between).
HEADINGS = ["Summary", "Choices", "How to read", "Headline", "Warnings", "Core",
            "Funnel per window period", "Sources per period", "Target per period",
            "Target by stratum", "Univariate ranking", "Excluded automatically",
            "At the decision's slices", "Key features", "Extended", "Reference groups",
            "Correlation overview", "Value profile", "Concordance per period", "Appendix", "Kinds",
            "Feature ledger", "Resolved config", "Decisions", "Collect log",
            "Timings"]  # fmt: skip
REGRESSION_CANDIDATES = ["age", "income", "segment", "onboarding_channel", "employment_status",
                         "cc_active_flag", "cc_bal*", "cc_limit", "spend_cc_*"]  # fmt: skip


def _run_with_stale_checks(
    cfg: UseCaseConfig, env: EnvironmentConfig, spark: SparkSession
) -> StageResult:
    """EDA after planting a Feature Checks folder, as an earlier run would have left it."""
    stale = Path(feature_dir(env, cfg, ENTITY, "feature_checks"))
    stale.mkdir(parents=True, exist_ok=True)
    (stale / "feature_checks.json").write_text("{}")
    return run_eda(cfg, ENTITY, env, spark)


@pytest.fixture(scope="module")
def card(
    spark: SparkSession, unit_env: EnvironmentConfig, variant: Callable[..., UseCaseConfig]
) -> StageResult:
    """The card config's EDA, built in memory (no model input)."""
    return _run_with_stale_checks(variant(data={"model_input": None}), unit_env, spark)


@pytest.fixture(scope="module")
def regression(
    spark: SparkSession, unit_env: EnvironmentConfig, variant: Callable[..., UseCaseConfig]
) -> StageResult:
    """Card spend summed forward for holders, on a narrow candidate list."""
    cfg = variant(
        task="regression",
        entities={ENTITY: {"sources": {"features": ["retail_mart"], "targets": None}}},
        data={
            "model_input": None,
            "target": {"rule": "forward_sum", "column": "spend_cc_vol"},
            "eligibility": {
                "modelling": [
                    {"name": "holders", "filter": "cc_flag = 1", "reason": "spend needs a card"}
                ]
            },
        },
        features={"candidates": {"include": REGRESSION_CANDIDATES, "exclude": []}},
    )
    return _run_with_stale_checks(cfg, unit_env, spark)


@pytest.fixture(params=["card", "regression"])
def result(request: pytest.FixtureRequest) -> StageResult:
    """Each config's result in turn."""
    return request.getfixturevalue(request.param)


def test_the_folder_holds_every_file_and_table(result: StageResult) -> None:
    """`eda/` holds the json, the log, the resolved config, the report and every table, and
    reads back whole; an amount target adds its boxes per group."""
    folder = Path(result.paths["folder"])
    for name in ("eda.json", "log.json", "resolved_config.yml", "report.html"):
        assert (folder / name).is_file(), name
    meta, tables = read_stage(str(folder), "eda")
    extra = {"target_quartiles"} if result.config.task == "regression" else set()
    assert set(tables) == TABLES | extra and meta["stage"] == "eda"
    assert not (folder.parent / "feature_checks").exists()  # the stale judgement is gone


def test_eda_json_carries_the_population_counts_and_the_digest(result: StageResult) -> None:
    """The D-088 counts per compared period, the digest Feature Checks recomputes (its upstream
    check passes on the same resolved config) and the key features with why."""
    meta = json.loads(Path(result.paths["eda.json"]).read_text())
    periods = meta["compared_periods"]
    assert [row["period"] for row in meta["population"]] == [
        *periods["window"],
        *periods["gap"],
        *periods["latest"],
    ]
    window = [row for row in meta["population"] if row["period"] in periods["window"]]
    assert all(row["known_target"] is not None and row["eligible_rows"] > 0 for row in window)
    assert meta["settings_digest"] == settings_digest(result.config, SETTINGS)
    check_upstream(meta, result.config, SETTINGS)
    assert set(meta["key_features"].values()) <= {"top_n", "listed"}
    assert len(meta["key_features"]) == result.config.eda.key_features.top_n
    assert list(meta["slices"]) == list(dict.fromkeys(result.tables["slices"]["slice"].dropna()))
    assert all(0 < share <= 1 for share in meta["slices"].values())


def test_the_ledger_holds_every_eda_column(result: StageResult) -> None:
    """One row per candidate and lineage column, the identity and EDA columns only, saved
    beside `eda/` for this data definition."""
    folder = str(Path(result.paths["folder"]).parent)
    ledger = read_ledger(folder, result.meta["data_definition_hash"])
    assert ledger.columns.tolist() == [*COLUMNS_BY_STAGE["identity"], *COLUMNS_BY_STAGE["eda"]]
    assert set(ledger.loc[ledger["lineage"], "feature"]) == set(result.meta["lineage"])
    read = ledger.loc[~(ledger["lineage"] | ledger["unsupported"])]
    assert read["rank"].notna().all() and set(read["feature"]) == set(result.meta["kinds"])


def test_the_report_has_plotly_once_and_every_section(result: StageResult) -> None:
    """The report parses, embeds plotly.js once and carries every heading in order and no strata
    pivots section; the views it shows are the result's (one subsection per key feature)."""
    text = Path(result.paths["report.html"]).read_text(encoding="utf-8")
    HTMLParser().feed(text)
    assert text.count(get_plotlyjs()[:300]) == 1
    headings = [unescape(h) for h in re.findall(r'<h[2-6] id="[^"]+">([^<]+)</h', text)]
    assert [h for h in headings if h in HEADINGS] == HEADINGS and "Strata pivots" not in headings
    assert set(result.views["deep_dives"]) == set(result.meta["key_features"]) <= set(headings)
    assert isinstance(result.views["timings"], Styler)
    print(f"{result.config.task} report: {Path(result.paths['report.html']).stat().st_size:,} B")


def test_no_label_outside_the_window_and_no_validation_cell(result: StageResult) -> None:
    """The gap and latest periods' cells carry no label (`sum_y` and `target_bin` null), no
    cell is of the validation period, and the lagged cells are the window's only."""
    cells, periods = result.tables["cells"], result.meta["compared_periods"]
    outside = cells.loc[~cells["period"].isin(periods["window"])]
    assert not outside.empty  # the unit preset has gap and latest periods
    assert outside["sum_y"].isna().all() and outside["target_bin"].isna().all()
    validation = period_spec(result.config).label(result.config.time.validation_period)
    assert validation not in set(cells["period"])
    assert set(cells.loc[cells["lagged"], "period"]) <= set(periods["window"])


def test_target_boxes_share_the_deep_dives_groups(regression: StageResult) -> None:
    """An amount target's boxes per group: a binned key feature's cover its bin table's groups
    with the same rows, each box ordered; by level, a categorical's boxes are the known rows'
    target per level."""
    bins = regression.tables["bins"]
    feature = bins["feature"].iloc[0]
    groups = bins.loc[(bins["feature"] == feature) & (bins["rows"] > 0), ["group", "rows"]]
    boxes = regression.tables["target_quartiles"]
    boxes = boxes.loc[boxes["feature"] == feature].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        boxes[["group", "rows"]], groups.reset_index(drop=True), check_dtype=False
    )
    ordered = boxes["lower_whisker"] <= boxes["q1"]
    ordered &= (boxes["q1"] <= boxes["median"]) & (boxes["median"] <= boxes["q3"])
    assert (ordered & (boxes["q3"] <= boxes["upper_whisker"])).all()
    snapshot = regression.frame
    known = snapshot.loc[(snapshot["eligible"] == 1) & snapshot["target"].notna()]
    by_level = target_quartiles_by_group(snapshot, "segment", "categorical", None, None)
    expected = known.groupby(known["segment"].fillna("null"))["target"].median()
    assert dict(zip(by_level["group"], by_level["median"], strict=True)) == pytest.approx(
        expected.to_dict()
    )


def test_a_stratum_named_like_a_framework_column_is_refused(
    spark: SparkSession, unit_env: EnvironmentConfig, variant: Callable[..., UseCaseConfig]
) -> None:
    """A stratum `target` is refused once the snapshot is collected, with the `source_<name>`
    hint."""
    cfg = variant(data={"model_input": None}, strata={"variables": ["segment", "target"]})
    with pytest.raises(ValueError, match="'source_target'"):
        run_eda(cfg, ENTITY, unit_env, spark)


def test_a_changed_validation_period_makes_eda_stale(card: StageResult) -> None:
    """The validation period decides the compared periods and the population counts yet is
    outside the data-definition hash (D-088): Feature Checks' upstream check refuses EDA's meta
    once it changes, naming it."""
    meta = json.loads(Path(card.paths["eda.json"]).read_text())
    time = card.config.time.model_copy(update={"validation_period": None})
    moved = card.config.model_copy(update={"time": time})
    with pytest.raises(ValueError, match=r"eda ran with time\.validation_period"):
        check_upstream(meta, moved, SETTINGS)


def test_a_numeric_stratum_outside_the_candidates_is_checked(regression: StageResult) -> None:
    """A stratum without a kind (here `income` with its kind taken away) is judged numeric by its
    dtype and refused above strata.max_levels values; a modelling tag as a stratum is refused
    (constant on the eligible rows); a log without the `compared_periods` entry fails naming
    it."""
    kinds = {name: kind for name, kind in regression.meta["kinds"].items() if name != "income"}
    meta = {"kinds": kinds, "tags": ["holders"]}
    frames = Frames(regression.frame, None, None, None, None, [], meta)
    strata = regression.config.strata.model_copy(update={"variables": ["income"]})
    cfg = regression.config.model_copy(update={"strata": strata})
    with pytest.raises(ValueError, match=r"the numeric strata \{'income'"):
        _check_frame_names(cfg, frames)
    strata = regression.config.strata.model_copy(update={"variables": ["segment", "holders"]})
    cfg = regression.config.model_copy(update={"strata": strata})
    with pytest.raises(ValueError, match=r"the modelling tags \['holders'\]"):
        _check_frame_names(cfg, frames)
    with pytest.raises(ValueError, match="no `compared_periods` entry"):
        _compared_periods(regression.config, [])


def test_dive_tables_keep_their_columns(result: StageResult) -> None:
    """The stacked deep-dive tables hold exactly the task's columns (the group tables its
    summary columns, an amount target its boxes per group too), and without a key feature they
    are empty with those columns. The per-period dive is the key features' rows of
    `concordance_per_period`, which holds every ranked candidate in every window period."""
    columns = _dive_columns(result.config.task)
    for name, names in columns.items():
        assert result.tables[name].columns.tolist() == names, name
    every, periods = result.tables["concordance_per_period"], result.meta["compared_periods"]
    assert every.columns.tolist() == columns["per_period"]
    assert len(every) == len(result.tables["ranking"]) * len(periods["window"])
    keys = every.loc[every["feature"].isin(list(result.meta["key_features"]))]
    keys = keys.reset_index(drop=True)
    pd.testing.assert_frame_equal(keys, result.tables["per_period"], check_like=True)
    empty = _dive_tables([], result.config.task)
    assert set(empty) == set(columns)
    assert all(table.empty and table.columns.tolist() == columns[name]
               for name, table in empty.items())  # fmt: skip


def test_reference_groups_open_with_the_rows_per_period(result: StageResult) -> None:
    """Each modelling tag's views open with the rows it keeps and excludes per window period,
    which add up to the rows after the analysis filters; no deep-dive caption prints `nan`."""
    funnel = result.tables["funnel"]
    judged = funnel[[column for column in funnel.columns if column.startswith("after_")][-1]]
    assert result.views["reference_groups"]
    for tag, views in result.views["reference_groups"].items():
        sizes = views[0].data
        assert sizes.columns.tolist() == ["period", "rows_kept", "rows_excluded", "share_excluded"]
        assert sizes["rows_kept"].tolist() == funnel[f"tagged_{tag}"].tolist()
        assert (sizes["rows_kept"] + sizes["rows_excluded"]).tolist() == judged.tolist()
        features = next(view.data for view in views if "standardised" in view.caption)
        assert {"feature", "smd"} <= set(features.columns) and "variable" not in features
    captions = [view.caption for dive in result.views["deep_dives"].values() for view in dive
                if isinstance(view, Styler)]  # fmt: skip
    assert not any(re.search(r"\bnan\b", caption) for caption in captions)


def _panels(block: object) -> int:
    """A view block's panel count: its x axes for a figure, 0 for anything else."""
    return len(list(block.select_xaxes())) if isinstance(block, go.Figure) else 0


def test_the_views_follow_the_report_layout(result: StageResult) -> None:
    """A deep dive opens with its group table when by level (or for an amount target), else with
    its chart; the group chart sits beside the first stratum's chart; one pivot table per stratum
    variable but the feature itself (a key feature that is a stratum has no diagonal). The
    ranking view shows `RANKING_VIEW`, `concordance` the ranking value and `concordance_plain`
    exactly on the non-monotone rows."""
    variables = result.config.strata.variables
    by_level = set(result.tables["levels"]["feature"])
    distribution = TASK_SPECS[result.config.task]["target_distribution"]
    for name, blocks in result.views["deep_dives"].items():
        others = [variable for variable in variables if variable != name]
        table_first = name in by_level or distribution
        assert isinstance(blocks[0], Styler if table_first else go.Figure), name
        assert _panels(blocks[int(table_first)]) == (2 if others else 1), name
        pivots = [b for b in blocks if isinstance(b, Styler) and b.caption.startswith(f"{name} ×")]
        assert len(pivots) == len(others), name
    view, ranking = result.views["ranking"].data, result.tables["ranking"]
    assert view.columns.tolist() == RANKING_VIEW
    assert view["concordance"].equals(ranking["ranking_value"])
    assert view["concordance_plain"].notna().tolist() == ranking["non_monotone"].tolist()


def test_estimate_axes_take_the_task_format_and_lift_axes_stay_plain(result: StageResult) -> None:
    """Every estimate axis reads as the task prints it (a rate in percent, an amount plotly's
    way): the target per period and by stratum, `rate_by_period`; a lift axis stays plain."""
    axis_format = TASK_SPECS[result.config.task]["axis_format"]
    by_stratum = next(iter(result.views["target_by_stratum"].values()))[1]
    feature = result.tables["bins"]["feature"].iloc[0]
    estimate_axes = [result.views["target_per_period"][1].layout.yaxis, by_stratum.layout.yaxis,
                     rate_by_period(result, feature).layout.yaxis]  # fmt: skip
    assert [axis.tickformat for axis in estimate_axes] == [axis_format] * 3
    assert lift_by_group(result, feature).layout.yaxis.tickformat is None


def test_the_correlation_overview_shows_the_key_features_and_whom_they_represent(
    card: StageResult,
) -> None:
    """The heatmap's names are the key features with a compared pair among them, in rank order;
    the table beneath lists the candidates the key-feature rule skipped, each above
    max_correlation with the key feature that represents it."""
    heatmap, represented = card.views["correlation"]
    keys, correlation = list(card.meta["key_features"]), card.tables["correlation"]
    pairs = correlation.loc[correlation["a"].isin(keys) & correlation["b"].isin(keys)]
    named = set(pairs.dropna(subset=["statistic"])[["a", "b"]].stack())
    assert list(heatmap.data[0].x) == [name for name in keys if name in named]
    table = represented.data
    assert table["candidate"].tolist() == list(card.meta["represented_by"])
    rule = card.config.eda.key_features.max_correlation
    assert (table["association"].abs() > rule).all()


def test_the_exploration_functions_cut_the_deep_dives_groups(card: StageResult) -> None:
    """On a binned key feature, `lift_by_group` draws the deep dive's groups and, by a stratum,
    one line per level; `rate_by_period` one line per deep-dive group over the window periods,
    at the snapshot period the deep dive's estimate; `compare_sides` two boxes for a numeric and
    two lines for a categorical."""
    bins = card.tables["bins"]
    feature = bins["feature"].iloc[0]
    groups = bins.loc[bins["feature"] == feature, ["group", "rows"]]
    shown = groups.loc[groups["rows"] > 0, "group"].tolist()
    assert list(lift_by_group(card, feature).data[0].x) == shown
    strata = card.tables["strata"]
    levels = strata.loc[strata["feature"].isna() & (strata["variable"] == "segment"), "level"]
    by_segment = lift_by_group(card, feature, by="segment")
    assert sorted(trace.name for trace in by_segment.data) == sorted(levels)
    lines = rate_by_period(card, feature)
    names = [trace.name for trace in lines.data if trace.name != "null"]
    assert len(lines.data) == len(groups)  # labelled by the buckets each receives (ML1)
    assert names[0].startswith(("<", "≤")) and names[-1].startswith((">", "≥"))
    window = card.meta["compared_periods"]["window"]
    assert all(list(trace.x) == window for trace in lines.data)
    at_snapshot = window.index(card.meta["snapshot_period"])
    estimates = bins.loc[bins["feature"] == feature, "estimate"].tolist()
    shown = [trace.y[at_snapshot] for trace in lines.data]
    assert shown == pytest.approx(estimates, nan_ok=True)
    for name in ("age", "segment"):  # a numeric: two boxes; a categorical: two lines
        sides = compare_sides(card, name, "non_holders").data
        assert [trace.name for trace in sides] == ["excluded", "eligible"], name


def test_a_numeric_is_cut_by_level_up_to_strata_max_levels(card: StageResult) -> None:
    """One rule (`dive_group_count`) decides a numeric's deep-dive groups: with `strata.max_levels`
    raised to a binned key feature's distinct values, `lift_by_group`, `rate_by_period` and the
    strata pivots cut it by level, one group per bucket as `level_table` gives it; a few-valued
    numeric reads its values (`1`, not `= 1`), as a feature and as a `by`."""
    feature = card.tables["bins"]["feature"].iloc[0]
    levels = int(card.tables["ranking"].set_index("feature").loc[feature, "levels"])
    assert dive_group_count("numeric", levels, levels - 1) == DEEP_DIVE_GROUPS
    assert dive_group_count("numeric", levels, levels) is None
    assert dive_group_count("categorical", levels, 2) is None
    strata = card.config.strata.model_copy(update={"max_levels": levels})
    wide = replace(card, config=card.config.model_copy(update={"strata": strata}))
    edges = bin_edges(card.frame, {feature: "numeric"}, card.config.eda.bins)[feature]
    base = card.meta["snapshot_base"]
    table = level_table(card.frame, feature, "numeric", edges, card.config.task, base)
    shown = table.loc[table["rows"] > 0, "group"].tolist()
    assert list(lift_by_group(wide, feature).data[0].x) == shown
    assert len(rate_by_period(wide, feature).data) == len(table)
    pivots = strata_pivots(card.frame, [feature], {feature: edges}, strata, card.config.task)
    assert set(pivots["feature_group"]) <= set(table["group"])
    few = replace(card, frame=card.frame.assign(few=[i % 3 for i in range(len(card.frame))]))
    assert {trace.name for trace in lift_by_group(few, "segment", by="few").data} == {"0", "1", "2"}
    assert list(lift_by_group(few, "few").data[0].x) == ["0", "1", "2"]  # by value, not "= 0"
    levels = card.tables["levels"]
    by_level = levels.loc[levels["feature"].map(card.meta["kinds"]) == "numeric"]
    name = by_level["feature"].iloc[0]  # a by-level numeric key feature of the card
    lines = [trace.name for trace in rate_by_period(card, name).data]
    assert not any(line.startswith("= ") for line in lines)  # its value, or the range received
    assert set(lines) & set(by_level.loc[by_level["feature"] == name, "group"])


def test_the_exploration_functions_refuse_what_they_cannot_draw(card: StageResult) -> None:
    """An unknown column, a column by itself, a snapshot column without cells in
    `rate_by_period`, an unknown tag and a tag with an empty side each fail naming why."""
    with pytest.raises(ValueError, match="not columns of the stage result's snapshot"):
        lift_by_group(card, "no_such_column")
    with pytest.raises(ValueError, match="is the feature itself"):
        lift_by_group(card, "segment", by="segment")
    with pytest.raises(ValueError, match="is not a candidate with cells; the candidates"):
        rate_by_period(card, "eligible")
    with pytest.raises(ValueError, match="is not a modelling tag; the tags"):
        compare_sides(card, "age", "no_such_tag")
    every_row_kept = replace(card, frame=card.frame.assign(non_holders=1))
    with pytest.raises(ValueError, match="the excluded side of non_holders has no"):
        compare_sides(every_row_kept, "segment", "non_holders")


def test_the_exploration_functions_draw_a_regression_and_a_categorical(
    card: StageResult, regression: StageResult
) -> None:
    """On the regression preset the four functions draw a mean, by a binned key feature's groups;
    a categorical candidate draws by its levels, capped as its deep dive caps it alone and at
    `strata.max_levels` when crossed with a stratum (as the strata pivots cap it)."""
    bins = regression.tables["bins"]
    feature = bins["feature"].iloc[0]
    groups = bins.loc[bins["feature"] == feature]
    shown = groups.loc[groups["rows"] > 0, "group"].tolist()
    assert list(lift_by_group(regression, feature).data[0].x) == shown
    assert {t.name for t in lift_by_group(regression, feature, by="segment").data} <= set(
        regression.frame["segment"].fillna("null")
    )
    lines = rate_by_period(regression, feature)
    assert len(lines.data) == len(groups) and lines.layout.yaxis.title.text == "Target mean"
    assert not pivot_target(regression, feature, "segment").data.empty
    assert [t.name for t in compare_sides(regression, "age", "holders").data] == [
        "excluded",
        "eligible",
    ]
    levels = regression.frame.loc[regression.frame["eligible"] == 1, "employment_status"]
    labels = {*levels.dropna().astype(str), "null", "__other__"}
    assert set(lift_by_group(regression, "employment_status").data[0].x) <= labels
    assert {t.name for t in rate_by_period(regression, "employment_status").data} <= labels
    strata = card.config.strata.model_copy(update={"max_levels": 1})
    narrow = replace(card, config=card.config.model_copy(update={"strata": strata}))
    alone = lift_by_group(narrow, "employment_status").data[0].x
    crossed = lift_by_group(narrow, "employment_status", by="segment").layout.xaxis.categoryarray
    assert len(alone) > 2 and set(crossed) <= {alone[0], "__other__", "null"}


def test_a_render_failure_leaves_the_previous_stage(
    card: StageResult, unit_env: EnvironmentConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The report is rendered before anything is written: a render error leaves `eda/`, its
    report, its tables, the ledger and a Feature Checks folder as the last runs wrote them."""
    folder = Path(card.paths["folder"])
    planted = folder.parent / "feature_checks" / "x"
    planted.parent.mkdir(exist_ok=True)
    planted.write_text("planted")
    files = [*folder.iterdir(), *folder.glob("tables/*.parquet"), folder.parent / "ledger.parquet",
             folder.parent / "_ledger.json"]  # fmt: skip
    before = {path: path.read_bytes() for path in files if path.is_file()}
    assert any(path.parent.name == "tables" for path in before)

    def fail(title: str, sections: list) -> str:
        """A render that fails as a Styler does when it is rendered."""
        raise ValueError("planted: render")

    monkeypatch.setattr("core_modelling.eda.run.render_report", fail)
    with pytest.raises(ValueError, match="planted"):
        _write(card, unit_env, ENTITY)
    assert {path: path.read_bytes() for path in before} == before
    assert planted.read_text() == "planted"
    planted.unlink()
    planted.parent.rmdir()
