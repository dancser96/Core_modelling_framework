"""The model results report: Evaluation's compatibility table and the page its views render to
(evaluation.md → "The compatibility table"; the page shell is `reporting/`'s).

`VIEWS` holds one row per view, keyed by its name (the names `evaluation.skip_views` takes) in
the report's order: its title, its section and the function that builds its blocks from the
stage's tables, its meta (`evaluation.json`) and the resolved config, or, per task, the reason
the task cannot produce it, decided up front and never by catching an error (D-035). A new view
is one row.
`report_views` builds the views a config does not skip (`evaluation.skip_views`, checked by
`check_skip_views`; the summary always renders) and `render_views` renders built views as one
page (summary, core, extended, appendix). A view reads the stored
tables and the meta only, so a page can be rendered again from `evaluation/` without Spark; the
appendix adds the stage's log (`log.json`) and the audit log's entries. The views are
`views_summary.py`'s, `views.py`'s and `views_explain.py`'s.
"""

import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.evaluation.views import (
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
# One row per view, in the report's order: its `title`, its `section` (summary, core or extended)
# and its `view`: the function for every task, or per task its function or why it is not
# available.
VIEWS: dict[str, dict] = {
    "summary": {"title": "Summary", "section": "summary", "view": summary_view},
    "metrics": {"title": "Metrics per period", "section": "core", "view": metrics_view},
    "curves": {"title": "ROC and precision-recall", "section": "core",
               "view": {"binary": curves_view, "regression": NO_CLASSES}},
    "capture": {"title": "Capture", "section": "core", "view": capture_view},
    "reliability": {"title": "Reliability", "section": "core", "view": reliability_view},
    "score_distribution": {"title": "Score distribution", "section": "core",
                           "view": {"binary": distribution_view, "regression": NO_CLASSES}},
    "strata": {"title": "Strata", "section": "core", "view": strata_view},
    "importance": {"title": "Importance", "section": "core", "view": importance_view},
    "beeswarm": {"title": "Beeswarm", "section": "core", "view": beeswarm_view},
    "effects": {"title": "Effects", "section": "core", "view": effects_view},
    "waterfalls": {"title": "Waterfalls", "section": "core", "view": waterfalls_view},
    "sign_off": {"title": "Sign-off (train only)", "section": "core", "view": sign_off_view},
    "search": {"title": "Search", "section": "core", "view": search_view},
    "thresholds": {"title": "Thresholds", "section": "extended",
                   "view": {"binary": thresholds_view, "regression": NO_CLASSES}},
    "permutation_importance": {"title": "Permutation importance per cluster",
                               "section": "extended", "view": permutation_importance_view},
    "pdp_ice": {"title": "Partial dependence and ICE", "section": "extended",
                "view": pdp_ice_view},
    "validation_test_clients": {"title": "Validation on test clients only",
                                "section": "extended", "view": validation_clients_view},
}  # fmt: skip


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
    """Each view's blocks by name, in `VIEWS` order: a view named in `evaluation.skip_views` is
    left out, one the task cannot produce is its reason as one line. The skipped names are
    checked once, when Evaluation opens the run (`check_skip_views`)."""
    views = {}
    for name, row in VIEWS.items():
        if name in resolved.evaluation.skip_views:
            continue
        entry = row["view"]
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


def _titled(views: dict[str, list], section: str) -> list[tuple[str, list]]:
    """The built views of `section` (core or extended), each as a subsection under its title,
    in `VIEWS` order."""
    return [(VIEWS[name]["title"], blocks) for name, blocks in views.items()
            if VIEWS[name]["section"] == section]  # fmt: skip


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
    sections = [(VIEWS[ALWAYS]["title"], views[ALWAYS]), ("Core", _titled(views, "core")),
                ("Extended", _titled(views, "extended")),
                ("Appendix", _appendix(meta, resolved, log, decisions))]  # fmt: skip
    title = f"Evaluation: {resolved.use_case} run {meta['run_id']} ({meta['entity']})"
    return render_report(title, [(heading, blocks) for heading, blocks in sections if blocks])
