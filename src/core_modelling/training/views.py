"""Training's report blocks: the search, selection, calibration and sign-off views
(docs/components/training.md "The search" item 14, "Selection", "Fold models and calibration",
"The sign-off view").

Each function turns one of Training's stored tables into the blocks notebook 04 displays and
Evaluation's report embeds (Stylers, figures and HTML strings, by view key), the way
`feature_checks/report.py` builds its views; the explanation charts are `reporting/
explain_charts.py`'s and sit beside these. Everything shown is train-only evidence (D-031): the
fold metrics are optimistic, and the test split is the first honest number. The views decide
nothing and write nothing. `training_views` puts them together for one run.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from pandas.io.formats.style import Styler

from core_modelling.config import UseCaseConfig
from core_modelling.config.replay import Entry
from core_modelling.reporting import blocks
from core_modelling.reporting.charts import apply_theme
from core_modelling.reporting.explain_charts import beeswarm, importance_bar
from core_modelling.reporting.formats import COUNT, SHARE, finding_number
from core_modelling.reporting.html import paragraph, style_table
from core_modelling.reporting.theme import THEME
from core_modelling.statistics.losses import metric_value
from core_modelling.training.ledger_run import LIST_COLUMNS, OPPOSITE, OUTCOMES, RULES, SECTIONS
from core_modelling.training.tables import sample_contributions

SEARCH_COLUMNS = ["family", "trials", "seconds", "seconds_per_trial", "seconds_longest",
                  "best_fold_metric", "best_trial", "share_seconds"]  # fmt: skip
RULE_VALUES = (
    "value and threshold per rule: cluster, the train concordance against the representative's; "
    "floor, the train concordance (best order when the train split marks the feature "
    "non_monotone) against 0.5 + z · SE; "
    "prune, the out-of-fold contribution share against the best noise column's"
)
# The sign-off columns each section shows (the table holds them all, null where they do not apply).
SECTION_VIEW = {
    "model": ["feature", "contribution_share", "cumulative_share", "direction_model",
              "direction_eda", "direction_agrees", "monotone", "wrong_sign", "represents",
              "source", "notes", "kept_flags"],
    "held": ["feature", "open_flags", "monotone", "direction_eda", "source", "notes",
             "kept_flags"],
    "excluded": ["feature", "exclude_entry", "exclude_reason", "monotone", "direction_eda",
                 "source", "notes"],
    # every constrained feature outside the model, whatever its section (Monotone constraints 6)
    "declared_not_in_model": ["feature", "section", "monotone", "wrong_sign", "dropped_by",
                              "open_flags", "exclude_entry", "exclude_reason", "direction_eda",
                              "source"],
}  # fmt: skip
SECTION_CAPTIONS = {
    "model": "The final list by out-of-fold contribution on train clients, largest first, with "
    "the running total; the model's direction beside EDA's; wrong_sign: the declared constraint "
    "against EDA's direction or its non_monotone mark",
    "held": "Held: an open flag holds each out of training until a person keeps or excludes it",
    "excluded": "Excluded by a person, with the exclude entry in force and its reason",
    "declared_not_in_model": "Declared, not in the model: every feature with a monotone "
    "constraint that is held, excluded or dropped by selection, its section beside it (a "
    "constraint protects nothing; keep does)",
}


def search_summary(trials: pd.DataFrame, metric: str) -> pd.DataFrame:
    """One row per family in run order (`SEARCH_COLUMNS`): the trials, the seconds in total, per
    trial (median) and of the longest trial, the best fold metric (`metric` read back from the
    lowest fold loss) and the trial that first reached it, and the family's share of the run's
    seconds. `trials` is Training's trials table."""
    total = trials["seconds"].sum()
    rows = []
    for family, part in trials.groupby("family", sort=False):
        part = part.sort_values("trial")
        finite = part["fold_loss"].where(np.isfinite(part["fold_loss"]))
        if finite.isna().all():
            raise ValueError(f"every trial of the family {family!r} has a non-finite fold loss")
        best = part.loc[finite.idxmin()]
        rows.append({
            "family": family, "trials": len(part), "seconds": part["seconds"].sum(),
            "seconds_per_trial": part["seconds"].median(),
            "seconds_longest": part["seconds"].max(),
            "best_fold_metric": metric_value(metric, best["fold_loss"]),
            "best_trial": int(best["trial"]), "share_seconds": part["seconds"].sum() / total,
        })  # fmt: skip
    return pd.DataFrame(rows, columns=SEARCH_COLUMNS)


def search_progress_chart(trials: pd.DataFrame, metric: str) -> go.Figure:
    """The best fold metric so far against the family's cumulative seconds, one stepped line per
    family in run order: how fast each family's search settles, to spend a main run's budget."""
    fig = go.Figure()
    sequence = THEME["sequence"]
    for position, (family, part) in enumerate(trials.groupby("family", sort=False)):
        part = part.sort_values("trial")
        best = [metric_value(metric, loss) for loss in part["fold_loss"].cummin()]
        fig.add_trace(go.Scatter(
            x=part["seconds"].cumsum(), y=best, mode="lines+markers", name=str(family),
            line={"color": sequence[position % len(sequence)], "shape": "hv"},
        ))  # fmt: skip
    apply_theme(fig, "Search progress per family", "Seconds since the family's search started",
                 f"Best fold {metric} so far", 380)  # fmt: skip
    fig.update_xaxes(rangemode="tozero")
    fig.update_layout(legend_title_text="Family")
    return fig


def _rule_counts(selection: pd.DataFrame) -> Styler | str:
    """The features per rule and outcome, the rules that ran in run order; a line when none ran."""
    if selection.empty:
        return paragraph("No selection rule ran: training.selection switches every rule off.")
    ran = [rule for rule in RULES if rule in set(selection["rule"])]
    counts = pd.crosstab(selection["rule"], selection["outcome"])
    counts = counts.reindex(index=ran, columns=list(OUTCOMES), fill_value=0)
    table = counts.rename_axis(index="rule", columns=None).reset_index()
    caption = (
        "Features per rule and outcome; protected: the rule would drop it, a person's keep holds "
        "it; a rule after the one that dropped a feature does not measure it"
    )
    return style_table(table, dict.fromkeys(OUTCOMES, COUNT), caption=caption)


def selection_view(run_ledger: pd.DataFrame, selection: pd.DataFrame) -> dict:
    """The selection blocks: `summary` (a line: how many features entered and how many are in
    the final list), `counts` (per rule and outcome) and `dropped` (the dropped features with
    their value and threshold, then a line when pruning was undone)."""
    selected, protected = int(run_ledger["selected"].sum()), int(run_ledger["protected"].sum())
    summary = paragraph(
        f"{selected} of the {len(run_ledger)} features that entered selection are in the final "
        f"list; {protected} with a person's keep were measured by every rule and dropped by none."
    )
    dropped = selection.loc[selection["outcome"] == "dropped"]
    if dropped.empty:
        dropped_blocks: list = [paragraph("No feature was dropped by a selection rule.")]
    else:
        table = dropped[["feature", "rule", "value", "threshold", "represented_by"]]
        formats = {"value": finding_number, "threshold": finding_number}
        caption = f"The features dropped, one row each; {RULE_VALUES}"
        dropped_blocks = [style_table(table.reset_index(drop=True), formats, caption=caption)]
    undone = selection.loc[(selection["rule"] == "prune") & (selection["outcome"] == "undone")]
    if not undone.empty:
        dropped_blocks.append(paragraph(
            f"Pruning was undone: without its {len(undone)} candidates "
            f"({', '.join(undone['feature'])}) the out-of-fold loss rose, so nothing was pruned."
        ))  # fmt: skip
    return {"summary": summary, "counts": _rule_counts(selection), "dropped": dropped_blocks}


def _number(value: object, number_format: str) -> str:
    """A number in its format, `n/a` when missing."""
    return "n/a" if value is None or pd.isna(value) else number_format.format(value)


def _binary_line(chosen: pd.Series) -> str:
    """The bundle's method with the true and sampled rates and the offset."""
    return paragraph(
        f"The bundle's calibration: {chosen['method']}. True rate "
        f"{_number(chosen['true_rate'], '{:.2%}')}, sampled rate "
        f"{_number(chosen['sampled_rate'], '{:.2%}')}, offset {_number(chosen['offset'], '{:.4f}')}"
        " (zero without sampling and under client_sample)."
    )


def _regression_line(chosen: pd.Series) -> str:
    """The bundle's method with the level factor, its interval and the rows holding half of the
    target's total."""
    return paragraph(
        f"The bundle's calibration: {chosen['method']}. Level factor "
        f"{_number(chosen['factor'], '{:.3f}')} (interval {_number(chosen['factor_low'], '{:.3f}')}"
        f" to {_number(chosen['factor_high'], '{:.3f}')}); "
        f"{_number(chosen['half_total_rows'], COUNT)} rows hold half of the target's total."
    )


# Per task: the calibration table's columns (any other is null for the task), its caption and
# the summary line.
CALIBRATION_BY_TASK = {
    "binary": {
        "columns": ["method", "chosen", "oof_log_loss", "parameters"],
        "caption": "Every method considered on the out-of-fold margins inside train, the "
        "bundle's marked chosen; the log loss is taken before the offset, at the sampled rate. "
        "Each method's log loss is in sample, not cross-fitted: the method is fitted and judged "
        "on the same rows, so one with more parameters never looks worse, and a gap in the "
        "fourth decimal or beyond is no reason to switch",
        "line": _binary_line,
    },
    "regression": {
        "columns": ["method", "chosen", "factor", "factor_low", "factor_high", "half_total_rows",
                    "parameters"],
        "caption": "The level factor: the total observed over the total predicted out of fold, "
        "its interval from a client bootstrap",
        "line": _regression_line,
    },
}  # fmt: skip
CALIBRATION_FORMATS = {"oof_log_loss": "{:.4f}", "factor": "{:.3f}", "factor_low": "{:.3f}",
                       "factor_high": "{:.3f}", "half_total_rows": COUNT}  # fmt: skip


def calibration_view(calibration: pd.DataFrame, task: str) -> dict:
    """The calibration blocks: `methods` (binary: `none`, `platt` and `beta` with their
    out-of-fold log loss; regression: the level factor with its interval; the bundle's method
    marked `chosen`) and `summary` (one line on the bundle's method)."""
    if task not in CALIBRATION_BY_TASK:
        raise ValueError(
            f"no calibration view for task {task!r}; tasks: {list(CALIBRATION_BY_TASK)}"
        )
    spec = CALIBRATION_BY_TASK[task]
    chosen = calibration.loc[calibration["chosen"].astype(bool)]
    if len(chosen) != 1:
        raise ValueError(f"the calibration table marks {len(chosen)} methods chosen, not one")
    table = calibration[spec["columns"]].reset_index(drop=True)
    formats = {column: f for column, f in CALIBRATION_FORMATS.items() if column in table}
    return {
        "methods": style_table(table, formats, caption=spec["caption"]),
        "summary": spec["line"](chosen.iloc[0]),
    }


def _joined(value: list) -> str:
    """A list cell as comma-separated text."""
    return ", ".join(str(item) for item in value)


def _section_block(signoff: pd.DataFrame, section: str) -> Styler | str:
    """One section's rows with the columns it uses (`SECTION_VIEW`); a line when it is empty.
    "Declared, not in the model" takes every constrained row outside the model."""
    if section == "declared_not_in_model":
        mask = (signoff["section"] != "model") & signoff["monotone"].notna()
    else:
        mask = signoff["section"] == section
    rows = signoff.loc[mask, SECTION_VIEW[section]]
    if rows.empty:
        return paragraph(f"{section.replace('_', ' ').capitalize()}: none.")
    table = rows.reset_index(drop=True)
    for column in LIST_COLUMNS:
        if column in table:
            table[column] = table[column].map(_joined)
    formats = {"contribution_share": SHARE, "cumulative_share": SHARE, "exclude_entry": "#{}"}
    shown = {column: f for column, f in formats.items() if column in table}
    return style_table(table, shown, caption=SECTION_CAPTIONS[section])


def _wrong_signs(signoff: pd.DataFrame) -> list[str]:
    """The wrong-sign warnings of the model's features: the constraint against EDA's opposite
    direction, or against its non_monotone mark."""
    warned = signoff.loc[(signoff["section"] == "model") & signoff["wrong_sign"].fillna(False)]
    items = []
    for row in warned.itertuples():
        opposite = row.direction_eda == OPPOSITE[row.monotone]
        reason = (
            f"EDA's direction is {row.direction_eda}" if opposite else "EDA marked it non_monotone"
        )
        items.append(
            f"{row.feature}: declared {row.monotone}, but {reason}; the constraint holds, a "
            "person may know more than the window shows."
        )
    return items


def signoff_view(signoff: pd.DataFrame, signed: Entry | None) -> dict:
    """The sign-off blocks: `status` (a line: whether this feature list is signed off, and by
    which entry), `sections` (section → its table, or a line when empty, in `SECTIONS` order)
    and `warnings` (the wrong-sign warnings as a numbered list)."""
    if signed is None:
        status = paragraph(
            "This feature list is not signed off: a person signs off the final list before the "
            "model is registered (notebook 05)."
        )
    else:
        status = paragraph(
            f"This feature list is signed off by entry #{signed.seq} on run {signed.run_id} "
            f"({signed.time}): {signed.reason}"
        )
    return {
        "status": status,
        "sections": {section: _section_block(signoff, section) for section in SECTIONS},
        "warnings": blocks.warnings_block(_wrong_signs(signoff)),
    }


def _best_table(best: dict) -> Styler:
    """The chosen family and the parameters every later fit uses (`training.json`'s `best`,
    without the thread count), one row each."""
    rows = [("family", best["family"]), *best["parameters"].items()]
    table = pd.DataFrame(rows, columns=["parameter", "value"]).astype({"value": str})
    return style_table(table, caption="The chosen family and its parameters")


def _metrics_table(metrics: dict) -> Styler:
    """The run's train-side numbers (`training.json`'s `metrics`), one row each."""
    rows = [
        (f"{metrics['metric']}, out of fold", metrics["out_of_fold"]),
        ("concordance, out of fold", metrics["out_of_fold_concordance"]),
        ("concordance, in sample", metrics["in_sample_concordance"]),
    ]
    caption = f"{metrics['note']} The concordance is the AUC for a binary target."
    table = pd.DataFrame(rows, columns=["number", "value"])
    return style_table(table, {"value": "{:.4f}"}, caption=caption)


def training_views(
    run: str,
    opening: dict,
    warnings: list[str],
    tables: dict[str, pd.DataFrame],
    run_ledger: pd.DataFrame,
    resolved: UseCaseConfig,
    signed: Entry | None,
    best: dict,
    metrics: dict,
) -> dict:
    """One run's views by key, what notebook 04 shows and Evaluation's report embeds: `opening`
    (the feature set in force, from the gate's log entry `opening`), `warnings`, `search` (its
    `summary` per family, its `progress` chart and the `best` family's parameters), `selection`,
    `calibration` (with the train-side `metrics`), `signoff` and `explanation` (the `importance`
    bars and the `beeswarm` on the explanation sample). `tables` are Training's, `signed` the
    `sign_off` entry covering the final list, if any, `best` and `metrics` `training.json`'s."""
    metric = resolved.decision.metric
    final = run_ledger.loc[run_ledger["selected"], "feature"].tolist()
    sample = tables["explanation_sample"]
    contributions = sample_contributions(sample, final)
    caption = (
        f"The search per family; best_fold_metric is the fold {metric}, the mean over every "
        "dealing's folds, and best_trial its trial"
    )
    return {
        "opening": paragraph(
            f"Run {run}: {opening['features']} features in force; held "
            f"{', '.join(opening['held']) or 'none'}; excluded "
            f"{', '.join(opening['excluded']) or 'none'}; kept "
            f"{', '.join(opening['kept']) or 'none'}. Feature Checks' run held "
            f"{opening['held_by_feature_checks']}. For Training a held feature is an excluded "
            f"feature without a final decision. The fold metric is {metric}."
        ),
        "warnings": blocks.warnings_block(warnings),
        "search": {
            "summary": style_table(search_summary(tables["trials"], metric), caption=caption),
            "progress": search_progress_chart(tables["trials"], metric),
            "best": _best_table(best),
        },
        "selection": selection_view(run_ledger, tables["selection"]),
        "calibration": {
            **calibration_view(tables["calibration"], resolved.task),
            "metrics": _metrics_table(metrics),
        },
        "signoff": signoff_view(tables["signoff"], signed),
        "explanation": {
            "importance": importance_bar(contributions),
            "beeswarm": beeswarm(contributions, sample[final]),
        },
    }
