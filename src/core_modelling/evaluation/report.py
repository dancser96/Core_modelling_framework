"""The model results report: Evaluation's compatibility table and the page its views render to
(evaluation.md → "The compatibility table"; the page shell is `reporting/`'s).

`VIEWS` maps each view's name, in the report's order, to the function that builds its blocks
from the stage's tables, its meta (`evaluation.json`) and the resolved config, or, per task, to
the reason the task cannot produce it, decided up front and never by catching an error (D-035).
`report_views` builds the views a config does not skip (`evaluation.skip_views`, checked by
`check_skip_views`; the summary always renders), `render_views` renders built views as one page
(summary, core, extended, appendix) and `build_report` does both. A view reads the stored
tables and the meta only, so a page can be rendered again from `evaluation/` without Spark; the
appendix adds the stage's log (`log.json`) and the audit log's entries. The views are
`views_summary.py`'s, `views.py`'s and `views_explain.py`'s.
"""

import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.evaluation.views import (
    View,
    capture_view,
    curves_view,
    distribution_view,
    metrics_view,
    reliability_view,
    search_view,
    sign_off_view,
    strata_view,
    thresholds_view,
    validation_clients_view,
)
from core_modelling.evaluation.views_explain import (
    beeswarm_view,
    effects_view,
    importance_view,
    pdp_ice_view,
    permutation_importance_view,
    waterfalls_view,
)
from core_modelling.evaluation.views_summary import summary_view
from core_modelling.reporting.blocks import appendix, not_available
from core_modelling.reporting.formats import COUNT
from core_modelling.reporting.html import render_report, style_table

ALWAYS = "summary"  # the view `evaluation.skip_views` cannot leave out
NO_CLASSES = "the target is an amount, without classes"
# A view's entry: its function for every task, or per task its function or why it is not
# available.
VIEWS: dict[str, View | dict[str, View | str]] = {
    "summary": summary_view,
    "metrics": metrics_view,
    "curves": {"binary": curves_view, "regression": NO_CLASSES},
    "capture": capture_view,
    "reliability": reliability_view,
    "score_distribution": {"binary": distribution_view, "regression": NO_CLASSES},
    "strata": strata_view,
    "importance": importance_view,
    "beeswarm": beeswarm_view,
    "effects": effects_view,
    "waterfalls": waterfalls_view,
    "sign_off": sign_off_view,
    "search": search_view,
    "thresholds": {"binary": thresholds_view, "regression": NO_CLASSES},
    "permutation_importance": permutation_importance_view,
    "pdp_ice": pdp_ice_view,
    "validation_test_clients": validation_clients_view,
}
EXTENDED = ("thresholds", "permutation_importance", "pdp_ice", "validation_test_clients")
TITLES = {
    "summary": "Summary",
    "metrics": "Metrics per period",
    "curves": "ROC and precision-recall",
    "capture": "Capture",
    "reliability": "Reliability",
    "score_distribution": "Score distribution",
    "strata": "Strata",
    "importance": "Importance",
    "beeswarm": "Beeswarm",
    "effects": "Effects",
    "waterfalls": "Waterfalls",
    "sign_off": "Sign-off (train only)",
    "search": "Search",
    "thresholds": "Thresholds",
    "permutation_importance": "Permutation importance per cluster",
    "pdp_ice": "Partial dependence and ICE",
    "validation_test_clients": "Validation on test clients only",
}


def check_skip_views(cfg: UseCaseConfig) -> None:
    """Refuse an `evaluation.skip_views` name that is no view, and the summary, which always
    renders; the message lists the names that can be skipped."""
    valid = [name for name in VIEWS if name != ALWAYS]
    wrong = [name for name in cfg.evaluation.skip_views if name not in valid]
    if wrong:
        raise ValueError(
            f"evaluation.skip_views names {wrong}, which cannot be skipped (the summary always "
            f"renders); the views are {valid}"
        )


def report_views(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> dict:
    """Each view's blocks by name, in `VIEWS` order, after `check_skip_views`: a view named in
    `evaluation.skip_views` is left out, one the task cannot produce is its reason as one
    line."""
    check_skip_views(resolved)
    views = {}
    for name, entry in VIEWS.items():
        if name in resolved.evaluation.skip_views:
            continue
        view = entry[resolved.task] if isinstance(entry, dict) else entry
        views[name] = (
            [not_available(view)] if isinstance(view, str) else view(tables, meta, resolved)
        )
    return views


def _appendix(
    meta: dict, resolved: UseCaseConfig, log: list[dict], decisions: pd.DataFrame
) -> list[tuple]:
    """The appendix's subsections: the resolved config, the audit log's entries (`decisions`,
    `show_decisions`' table), the frames collected (the log's `collect` steps) and the seconds
    per phase (`meta["timings"]`)."""
    shared = appendix(resolved, decisions, meta["timings"]["seconds"], "Seconds per phase")
    collected = pd.DataFrame([step for step in log if step["step"] == "collect"])
    collect = style_table(collected.drop(columns="step"), {"rows": COUNT, "columns": COUNT},
                          caption="Collected frames (bytes)")  # fmt: skip
    return [
        ("Resolved config", [shared["resolved_config"]]),
        ("Audit log", [shared["decisions"]]),
        ("Collected frames", [collect]),
        ("Timings", [shared["timings"]]),
    ]


def render_views(
    views: dict[str, list],
    meta: dict,
    resolved: UseCaseConfig,
    log: list[dict],
    decisions: pd.DataFrame,
) -> str:
    """Views already built (`report_views`) as one self-contained HTML page: the summary, the
    core and the extended views, each a subsection under its title, then the appendix from the
    stage's `log` and the audit log's entries (`decisions`)."""
    core = [(TITLES[name], blocks) for name, blocks in views.items()
            if name != ALWAYS and name not in EXTENDED]  # fmt: skip
    extended = [(TITLES[name], blocks) for name, blocks in views.items() if name in EXTENDED]
    sections = [(TITLES[ALWAYS], views[ALWAYS]), ("Core", core), ("Extended", extended),
                ("Appendix", _appendix(meta, resolved, log, decisions))]  # fmt: skip
    title = f"Evaluation: {resolved.use_case} run {meta['run_id']} ({meta['entity']})"
    return render_report(title, [(heading, blocks) for heading, blocks in sections if blocks])


def build_report(
    tables: dict[str, pd.DataFrame],
    meta: dict,
    resolved: UseCaseConfig,
    log: list[dict],
    decisions: pd.DataFrame,
) -> str:
    """The model results report as one self-contained HTML page (`report_views`, then
    `render_views`)."""
    return render_views(report_views(tables, meta, resolved), meta, resolved, log, decisions)
