"""The model results report's views and page: the table-shaping helpers on small constructed
tables, the skip-views check on a config, and the rendered page of the card run and of the
regression variant (Spark, through the session's `evaluated_card` and `evaluated_regression`).
"""

from html import escape

import pandas as pd
import pytest
from conftest import with_evaluation
from pandas.io.formats.style import Styler

from core_modelling.artifacts import StageResult
from core_modelling.config import UseCaseConfig
from core_modelling.config.audit_log import COLUMNS
from core_modelling.evaluation.report import (
    ALWAYS,
    NO_CLASSES,
    VIEWS,
    check_skip_views,
    render_views,
    report_views,
)
from core_modelling.evaluation.tables import headline_names, metric_key, pooled_metrics
from core_modelling.evaluation.views import (
    _period_rows,
    interval_text,
    labelled_metrics,
    threshold_rows,
    validation_clients_view,
    wide_metrics,
)
from core_modelling.evaluation.views_summary import _warnings_blocks, baseline_table
from core_modelling.reporting.blocks import warnings_block
from core_modelling.reporting.html import paragraph
from core_modelling.reporting.theme import THEME
from core_modelling.statistics.score_cells import PARTS

NO_DECISIONS = pd.DataFrame(columns=COLUMNS)  # the audit log's table, empty: the page's checks


def _metric_rows(rows: list[tuple]) -> pd.DataFrame:
    """Long metric rows from `(part, period, metric, value, low, high, events, insufficient)`,
    100 rows each, no stratum."""
    columns = ["part", "period", "metric", "value", "low", "high", "events", "insufficient"]
    return pd.DataFrame(rows, columns=columns).assign(rows=100.0, stratum=None, level=None)


def test_interval_text_never_reads_a_missing_number_as_precise() -> None:
    """A value with its interval; `(no interval)` after a value whose interval is NaN (a
    replicate left the metric undefined); `undefined` without a value."""
    assert interval_text(0.5, 0.25, 0.75) == "0.5 (0.25 to 0.75)"
    assert interval_text(0.031, 0.02, 0.04, "{:.1%}") == "3.1% (2.0% to 4.0%)"
    assert interval_text(0.5, float("nan"), float("nan")) == "0.5 (no interval)"
    assert interval_text(float("nan"), 0.1, 0.9) == "undefined"


def test_the_deviance_is_named_by_the_loss_the_cells_carry() -> None:
    """`deviance` reads as `meta["row_loss"]`'s name; without a row loss it is dropped."""
    rows = _metric_rows([("test", "pooled", metric, 0.5, 0.4, 0.6, 80.0, False)
                         for metric in ("rmse", "deviance")])  # fmt: skip
    named = labelled_metrics(rows, "tweedie_deviance")
    assert named["metric"].tolist() == ["rmse", "tweedie_deviance"]
    assert labelled_metrics(rows, None)["metric"].tolist() == ["rmse"]


def test_wide_metrics_keeps_the_rows_order_and_the_flags() -> None:
    """One row per part and period in the rows' order, a column per metric in theirs, the
    baselines' helper metrics left out, `insufficient` returned beside the table."""
    rows = _metric_rows([
        ("test", "2025-02", "roc_auc", 0.7, 0.6, 0.8, 10.0, True),
        ("test", "2025-02", "mean_score", 0.1, 0.1, 0.1, 10.0, True),
        ("test", "2025-02", "log_loss", 0.2, 0.1, 0.3, 10.0, True),
        ("test", "2025-01", "roc_auc", 0.9, 0.8, 1.0, 80.0, False),
        ("test", "2025-01", "log_loss", 0.4, 0.3, 0.5, 80.0, False),
    ])  # fmt: skip
    table, flags = wide_metrics(rows, ["part", "period"])
    assert list(table.columns) == ["part", "period", "rows", "events", "roc_auc", "log_loss"]
    assert table["period"].tolist() == ["2025-02", "2025-01"]
    assert table.loc[1, "roc_auc"] == "0.9 (0.8 to 1)"
    assert flags.tolist() == [True, False]


def test_baseline_table_shows_a_reason_where_a_baseline_cannot_fill_a_cell() -> None:
    """One row per scorer in the table's order, a column per part and metric; an unavailable
    cell reads its reason, never a number."""
    reason = "not available: one rate for every row ranks nothing"
    baselines = pd.DataFrame({
        "scorer": ["model", "model", "population_base_rate", "population_base_rate"],
        "part": ["test", "validation", "test", "validation"],
        "metric": ["roc_auc"] * 4,
        "value": [0.8, 0.7, float("nan"), float("nan")],
        "low": [0.7, 0.6, float("nan"), float("nan")],
        "high": [0.9, 0.8, float("nan"), float("nan")],
        "unavailable": ["", "", reason, reason],
    })  # fmt: skip
    table = baseline_table(baselines)
    assert table["scorer"].tolist() == ["model", "population_base_rate"]
    assert list(table.columns) == ["scorer", "test roc_auc", "validation roc_auc"]
    assert table.loc[0, "test roc_auc"] == "0.8 (0.7 to 0.9)"
    assert table.loc[1, "validation roc_auc"] == reason


def test_threshold_rows_take_the_first_bin_reaching_each_depth_once() -> None:
    """Per part, the first row whose cumulative depth reaches each depth; a bin reached by two
    depths is shown once."""
    curves = pd.DataFrame({"part": ["test"] * 4, "depth": [0.05, 0.2, 0.6, 1.0],
                           "threshold": [0.9, 0.5, 0.2, 0.0]})  # fmt: skip
    picked = threshold_rows(curves, (0.01, 0.05, 0.1, 0.5))
    assert picked["depth"].tolist() == [0.05, 0.2, 0.6]


@pytest.mark.parametrize("name", ["no_such_view", ALWAYS])
def test_check_skip_views_refuses_an_unknown_name_and_the_summary(
    cc_config: UseCaseConfig, name: str
) -> None:
    """A name that is no view, and the summary, are refused with the names that can be
    skipped."""
    with pytest.raises(ValueError, match="the views are") as refused:
        check_skip_views(with_evaluation(cc_config, skip_views=[name]))
    assert "metrics" in str(refused.value)
    check_skip_views(with_evaluation(cc_config, skip_views=["metrics", "pdp_ice"]))


def test_period_rows_put_test_periods_then_validation_then_pooled_then_the_mean() -> None:
    """Each part's periods in time order, validation's one period after test's, test pooled,
    the periods' mean last; validation's pooled row, a repeat of its period, left out."""
    rows = _metric_rows([
        (part, period, "roc_auc", 0.7, 0.6, 0.8, 80.0, False)
        for part, period in [("validation", "pooled"), ("test", "mean"), ("validation", "2025-11"),
                             ("test", "pooled"), ("test", "2025-02"), ("test", "2025-01")]
    ])  # fmt: skip
    ordered = _period_rows(rows)
    assert list(zip(ordered["part"], ordered["period"], strict=True)) == [
        ("test", "2025-01"), ("test", "2025-02"), ("validation", "2025-11"), ("test", "pooled"),
        ("test", "mean"),
    ]  # fmt: skip


def test_a_row_below_the_support_rule_is_greyed_in_the_rendered_view(
    cc_config: UseCaseConfig,
) -> None:
    """Validation's test-split clients below `strata.min_events` render greyed, still shown."""
    rows = _metric_rows([
        ("validation", "pooled", "roc_auc", 0.7, 0.6, 0.8, 80.0, False),
        ("validation_test_clients", "pooled", "roc_auc", 0.9, 0.5, 1.0, 9.0, True),
    ])  # fmt: skip
    (table,) = validation_clients_view({"metrics": rows}, {"row_loss": None}, cc_config)
    html = table.to_html()
    assert html.count(f"color: {THEME['insufficient']}") == 1
    assert "0.9 (0.5 to 1)" in html


def test_the_warnings_section_lists_evaluations_then_trainings() -> None:
    """Evaluation's own warnings come first, then a "From Training" list from
    `meta["training_warnings"]`."""
    meta = {"warnings": [{"code": "a", "text": "own sentence"}],
            "training_warnings": ["held feature released"]}  # fmt: skip
    own, (heading, trained) = _warnings_blocks(meta)
    assert own == warnings_block(["own sentence"])
    assert heading == "From Training" and trained == [warnings_block(["held feature released"])]


def test_a_new_view_is_one_row_of_the_views(
    cc_config: UseCaseConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row (title, section, view) added to `VIEWS` renders under its title in its section,
    with no second structure to edit."""
    row = {"title": "A new view", "section": "extended", "view": lambda *_: []}
    monkeypatch.setitem(VIEWS, "new_view", row)
    meta = {"run_id": "r001", "entity": "entity_a", "timings": {"seconds": {"scoring": 1.0}}}
    views = {ALWAYS: [paragraph("the summary")], "new_view": [paragraph("shown")]}
    log = [{"step": "collect", "frame": "explanation_sample", "rows": 10, "columns": 3}]
    page = render_views(views, meta, cc_config, log, NO_DECISIONS)
    assert page.index(">Extended</h") < page.index(">A new view</h") < page.index(">Appendix</h")


def test_the_page_ends_with_the_appendix(cc_config: UseCaseConfig) -> None:
    """The rendered page holds the appendix: the resolved config, the audit log, the frames
    collected and the timings."""
    meta = {"run_id": "r001", "entity": "entity_a", "timings": {"seconds": {"scoring": 1.0}}}
    collect = {"step": "collect", "frame": "explanation_sample", "rows": 10, "columns": 3}
    log = [{"step": "join", "source": "spine"}, collect]
    views = {ALWAYS: [paragraph("the summary")]}
    page = render_views(views, meta, cc_config, log, NO_DECISIONS)
    for heading in ("Appendix", "Resolved config", "Audit log", "Collected frames", "Timings"):
        assert f">{heading}</h" in page
    assert page.index(">Appendix</h") > page.index(">Summary</h")
    assert "explanation_sample" in page


def _titles() -> list[str]:
    """Every view's title, in the report's order."""
    return [row["title"] for row in VIEWS.values()]


def _headings(page: str) -> list[str]:
    """The views' titles found in the page as headings."""
    return [title for title in _titles() if f">{title}</h" in page.replace("&#x27;", "'")]


def _headline_texts(result: StageResult) -> list[str]:
    """The pooled value and interval of each headline metric on each part, as the summary prints
    them, from the stored metrics table."""
    cfg = result.config
    pooled = pooled_metrics(result.tables["metrics"]).set_index(["part", "metric"])
    rows = [pooled.loc[(part, metric_key(cfg, name))] for part in PARTS
            for name in headline_names(cfg)]  # fmt: skip
    return [interval_text(row["value"], row["low"], row["high"]) for row in rows]


def _assert_numbers_on_the_page(result: StageResult, page: str) -> None:
    """The headline numbers, every warning's sentence (Evaluation's and Training's) and the
    metrics view's pooled test row of the decision's metric are on the page."""
    assert all(text in page for text in _headline_texts(result))
    for warning in result.meta["warnings"]:
        assert escape(warning["text"]) in page
    for sentence in result.meta["training_warnings"]:
        assert escape(sentence) in page
    cfg = result.config
    pooled = pooled_metrics(result.tables["metrics"]).set_index(["part", "metric"])
    first = pooled.loc[("test", metric_key(cfg, cfg.decision.metric))]
    table = VIEWS["metrics"]["view"](result.tables, result.meta, cfg)[0]
    assert isinstance(table, Styler)
    assert interval_text(first["value"], first["low"], first["high"]) in table.to_html()


def test_the_card_report_holds_every_view(evaluated_card: StageResult) -> None:
    """Every view's heading is on the binary page, none declared impossible for the task, its
    headline numbers and warnings are printed, and plotly.js is embedded once, never loaded
    from a CDN."""
    result = evaluated_card
    page = render_views(result.views, result.meta, result.config, result.log, NO_DECISIONS)
    assert _headings(page) == _titles()
    _assert_numbers_on_the_page(result, page)
    assert ">Appendix</h" in page
    assert f"Not available: {NO_CLASSES}." not in page
    assert page.count('<script type="text/javascript">/**') == 1
    assert '<script src="http' not in page


def test_the_regression_report_says_what_an_amount_cannot_show(
    evaluated_regression: StageResult,
) -> None:
    """The regression page holds every heading and its headline numbers, and the views declared
    impossible for an amount read "not available" with their reason."""
    result = evaluated_regression
    page = render_views(result.views, result.meta, result.config, result.log, NO_DECISIONS)
    assert _headings(page) == _titles()
    _assert_numbers_on_the_page(result, page)
    views = [entry["view"] for entry in VIEWS.values()]
    impossible = [view["regression"] for view in views if isinstance(view, dict)]
    assert impossible == [NO_CLASSES] * 3
    assert page.count(f"Not available: {NO_CLASSES}.") == 3


def test_a_skipped_view_is_left_out_and_the_summary_stays(evaluated_card: StageResult) -> None:
    """A view named in `evaluation.skip_views` leaves the page; the summary always renders."""
    cfg = with_evaluation(evaluated_card.config, skip_views=["curves", "thresholds"])
    result = evaluated_card
    views = report_views(result.tables, result.meta, cfg)
    page = render_views(views, result.meta, cfg, result.log, NO_DECISIONS)
    shown = _headings(page)
    titles = {name: row["title"] for name, row in VIEWS.items()}
    assert titles["curves"] not in shown and titles["thresholds"] not in shown
    assert titles["summary"] in shown and titles["metrics"] in shown
