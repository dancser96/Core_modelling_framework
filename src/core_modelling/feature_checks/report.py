"""The Feature Checks report: the views from the stage's tables and meta in four parts
(docs/components/feature_checks.md "The report", docs/components/reporting.md "The Feature
Checks report").

`build_views` turns the stored tables, EDA's concordance per window period, the meta, the
resolved config after the run's entries, the ledger with its derived decisions, the held
features and the audit log into the Stylers,
figures and HTML blocks the report embeds and notebook 03 displays; `report_sections` arranges
them as summary → core → extended → appendix. A flag holds a feature out of training until a
person keeps or excludes it, a note never affects training (D-134): the report states both and
never suggests a verb for a flag, and for near-duplicates it names the trade-off and leaves the
choice to a person. A step left out of the `feature_checks` mapping reads "Not run"; what cannot
be shown is decided before drawing and reads "Not available: <reason>" (D-035). Concordance axes
stay plain, around 0.5.

`StageResult.views`, by key; a dict maps each subsection's name to its list of blocks:
- `choices` (Styler): what was chosen, its value and the alternatives (D-032): the level, the
  periods, the support rule, each step's thresholds, the skipped steps, the compared periods.
- `how_to_read` (list of HTML): the five reading notes.
- `headline` (HTML): EDA's headline numbers.
- `warnings` (HTML): the numbered warnings, always the all-client one (D-030).
- `raised` (Styler): per finding of the steps that ran, its kind and count, a flag's features.
- `held` (list): the held features with the statistic behind each open flag (Styler, the
  hold-out sentence its caption) or a line saying none.
- `steps` (dict step → list): per step in run order, its raised findings' texts (Styler), its
  findings table with the ledger's statistics beside it (or a line: not run, no finding), then
  what it could not test; redundancy shows one row per cluster before its feature table.
- `proposed_decisions` (list): per open flag finding its threshold and features with their
  values (Styler), then the two calls per finding to copy (a code block whose header comment
  says where CONFIG and ENVIRONMENT come from); a line when no flag is open.
- `ledger` (Styler): every candidate with its derived decision and Feature Checks' columns.
- `per_period` (list): a line saying the concordance per window period is in EDA's report,
  then the PSI against the snapshot per compared period, every candidate (Styler).
- `stability_chart` (Figure, or "Not available"): the concordance per window period of the
  features `concordance_unstable` raised, from EDA's `concordance_per_period`, greyed below
  `strata.min_events` (still tested).
- `resolved_config` (HTML), `decisions`, `entries_written`, `timings` (Stylers): the appendix.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import yaml
from pandas.io.formats.style import Styler

from core_modelling.config.identities import short
from core_modelling.config.schema import UseCaseConfig
from core_modelling.feature_checks.findings import FINDINGS, STEP_ORDER
from core_modelling.reporting import blocks, charts
from core_modelling.reporting.formats import COUNT, column_formats, plain_number
from core_modelling.reporting.html import paragraph, preformatted, style_table
from core_modelling.tasks import TASK_SPECS

CHOICE_NAMES = ["automation_level", "task", "period", "observation_window", "validation_period",
                "min_events", *STEP_ORDER, "skipped_steps", "compared_periods", "replayed_to",
                "config_hash", "data_definition_hash"]  # fmt: skip
# The ledger's statistics a reader needs beside each step's findings (one `keep` settles them).
STEP_STATISTICS = {
    "quality": ["missing_share_window", "dominant_share_window", "zero_share_window", "levels"],
    "leakage": ["concordance_window", "null_concordance_window", "missing_share_window"],
    "time_alignment": ["concordance_window", "lagged_concordance", "signal_kept",
                       "constant_share"],
    "stability": ["concordance_window", "psi_window", "psi_latest"],
}  # fmt: skip
REDUNDANCY_VIEW = ["finding", "cluster", "feature", "kind", "value", "threshold",
                   "concordance_window", "association_with_best", "explained_by_others",
                   "detail"]  # fmt: skip
CLUSTER_SUMMARY = ["cluster", "feature", "concordance", "size", "features", "association_min",
                   "explained_by_others_max"]  # fmt: skip
NEAR_DUPLICATES = (
    "A note holds nothing: every member stays a candidate. Where members measure the same thing "
    "(a total beside its parts, one measure over two windows), consider excluding those that add "
    "nothing and keeping the one easiest to explain and to keep filled, often the first; "
    "otherwise Training's selection picks among them, and a boosted model splits their "
    "importance, so read a cluster's importances together at the sign-off."
)
LEDGER_VIEW = ["feature", "kind", "verdict", "flags", "notes", "kept", "excluded",
               "concordance_window", "missing_share_window", "lagged_concordance", "signal_kept",
               "constant_share", "concordance_range", "heterogeneity_p", "psi_window",
               "psi_latest", "new_level_share", "cluster",
               "explained_by_others"]  # fmt: skip
HELD = (
    "For Training, a held feature acts as an excluded feature without a final decision: the "
    "model is built without it until a person keeps or excludes it."
)
ALL_CLIENTS = (
    "Feature Checks reads every eligible client of the observation window: people's feature "
    "decisions here have seen the labels of the clients that later form the test split."
)
WRITTEN = (
    "The entries this run wrote: changed flag sets, then the run entry. A run whose report failed "
    "to render leaves its entries written and the previous folder in place; the next run then "
    "lists only its run entry, and the flags the failed run wrote show in the audit log above"
)
NOT_RUN = "Not run: the step is left out of the feature_checks mapping."
NOTES_LISTED = "see Findings per step"  # notes run to dozens of features: kept off the summary


def _listed(values: object) -> str:
    """A list cell as text, its items comma-separated (a list read back from parquet is a numpy
    array); '' for None only, anything else fails."""
    if values is None:
        return ""
    if not isinstance(values, list | np.ndarray):
        raise TypeError(f"a list cell holds a {type(values).__name__}, not a list")
    return ", ".join(str(value) for value in values)


def build_views(
    tables: dict[str, pd.DataFrame],
    concordance_per_period: pd.DataFrame,
    meta: dict,
    resolved: UseCaseConfig,
    ledger: pd.DataFrame,
    held: pd.DataFrame,
    decisions: pd.DataFrame,
) -> dict:
    """Every view by its `StageResult.views` key (the module docstring's list).
    `concordance_per_period` is EDA's table of that name, `ledger` carries the derived decisions
    (`render_decisions`), `held` is `held_summary`'s table and `decisions` the audit log as
    `show_decisions` gives it."""
    task, findings = resolved.task, tables["findings"]
    return {
        **_summary_views(meta, resolved, held),
        "steps": {step: _step_views(step, tables, ledger, meta, task) for step in STEP_ORDER},
        "proposed_decisions": _review_views(tables["proposed_decisions"]),
        "ledger": _ledger_view(ledger, task),
        "per_period": _per_period_views(tables["per_period"], meta, resolved),
        "stability_chart": _stability_chart(concordance_per_period, findings),
        **_appendix_views(meta, resolved, decisions),
    }


def _choices(meta: dict, resolved: UseCaseConfig) -> Styler:
    """The choices block: a step's value is its thresholds' mapping, "not run" when skipped."""
    periods = meta["compared_periods"]
    compared = "; ".join(f"{group}: {', '.join(labels) or 'none'}"
                         for group, labels in periods.items())  # fmt: skip
    values = {
        **{step: "not run" for step in meta["steps_skipped"]},
        "skipped_steps": meta["steps_skipped"],
        "compared_periods": compared,
        "replayed_to": meta["replayed_to"],
        "config_hash": short(meta["config_hash"]),
        "data_definition_hash": short(meta["data_definition_hash"]),
    }
    choices = [
        {**blocks.CHOICES[name], **({"value": values[name]} if name in values else {})}
        for name in CHOICE_NAMES
    ]
    return blocks.choices_block(resolved, choices)


def _how_to_read(resolved: UseCaseConfig) -> list[str]:
    """The five reading notes: concordance, a flag, a note, grey, `null`."""
    support = TASK_SPECS[resolved.task]["support_name"]
    notes = [
        "Concordance says how well a feature orders clients by the target: 0.5 is no better "
        "than chance, 1 a perfect ordering. Per period and lagged it is read in the window's "
        "direction, so a flipped feature reads below 0.5.",
        f"A flag holds the feature out of training at both automation levels until a person "
        f"records keep or exclude. {HELD}",
        "A note never affects training: it says look at this.",
        f"Grey means too little support, still shown and still tested: a window period with "
        f"fewer than strata.min_events = {resolved.strata.min_events} {support} is greyed, and a "
        "finding's detail says when a result is not significant at its support.",
        "null is the clients without a value: its own bin in every statistic (PSI, new levels), "
        "always last.",
    ]
    return [paragraph(note) for note in notes]


def _warnings(meta: dict) -> list[str]:
    """The warnings: the skipped steps, whose earlier flags stay as the audit log has them, and
    always the all-client warning (D-030)."""
    skipped = meta["steps_skipped"]
    items = []
    if skipped:
        items.append(
            f"The steps {', '.join(skipped)} were not run: they wrote no flag entry, so their "
            "earlier flags stay open or closed as the audit log has them."
        )
    return [*items, ALL_CLIENTS]


def _summary_views(meta: dict, resolved: UseCaseConfig, held: pd.DataFrame) -> dict:
    """The choices, the reading notes, EDA's headline, the warnings, the findings raised per
    finding and the held features."""
    named = {name: _listed(spec["features"]) if spec["kind"] == "flag" else NOTES_LISTED
             for name, spec in meta["findings"].items() if spec["features"]}  # fmt: skip
    raised = pd.DataFrame(
        [{"finding": name, "kind": spec["kind"], "count": spec["count"],
          "features": named.get(name, "")} for name, spec in meta["findings"].items()],
        columns=["finding", "kind", "count", "features"],
    )  # fmt: skip
    caption = (
        "The findings of the steps that ran, in run order: how many features raised each, the "
        "flagged ones named (the noted ones are listed under Findings per step)"
    )
    numbers = {name.replace("_", " "): value for name, value in meta["eda_headline"].items()}
    return {
        "choices": _choices(meta, resolved),
        "how_to_read": _how_to_read(resolved),
        "headline": blocks.headline(numbers),
        "warnings": blocks.warnings_block(_warnings(meta)),
        "raised": style_table(raised, {"count": COUNT}, caption=caption),
        "held": _held_views(held, resolved.task),
    }


def _values_text(values: dict) -> str:
    """A held feature's `flag_values` as dict-like text, `{'concordance_window': 0.9532}`."""
    shown = (f"'{measure}': " + ("'not raised'" if value is None else plain_number(value))
             for measure, value in values.items())  # fmt: skip
    return "{" + ", ".join(shown) + "}"


def _held_views(held: pd.DataFrame, task: str) -> list:
    """The held features with their open flags and the statistic behind each, the hold-out
    sentence their caption, or a line saying none is held."""
    if held.empty:
        return [paragraph("No feature is held: no flag is open.")]
    table = held.assign(findings=held["findings"].map(_listed),
                        flag_values=held["flag_values"].map(_values_text))  # fmt: skip
    caption = (
        f"Held features: {len(held)}, each with its open flags and window statistics; "
        f"flag_values: per open flag, the statistic that raised it; not raised: open from an "
        f"earlier run. {HELD}"
    )
    return [style_table(table, column_formats(table, task), caption=caption)]


def _step_views(
    step: str, tables: dict[str, pd.DataFrame], ledger: pd.DataFrame, meta: dict, task: str
) -> list:
    """The raised findings' texts (`finding`, `text`), then one step's findings table with the
    ledger's statistics beside each row and the detail last (redundancy: its clusters first),
    then what it could not test; "Not run" when skipped."""
    if step in meta["steps_skipped"]:
        return [paragraph(NOT_RUN)]
    findings = tables["findings"]
    rows = findings.loc[findings["step"] == step].reset_index(drop=True)
    views: list = []
    if rows.empty:
        views.append(paragraph(f"No finding: no feature reached a {step} threshold."))
    else:
        raised = [name for name in FINDINGS if name in set(rows["finding"])]
        texts = pd.DataFrame({"finding": raised, "text": [FINDINGS[n]["text"] for n in raised]})
        views.append(style_table(texts, caption="The findings this step raised"))
    if step == "redundancy":
        views += _redundancy_views(rows, tables["clusters"], ledger, task)
    elif not rows.empty:
        statistics = ledger.set_index("feature")[STEP_STATISTICS[step]]
        table = rows[["feature", "finding", "kind", "value", "threshold"]]
        table = table.join(statistics, on="feature").assign(detail=rows["detail"])
        caption = "Each row's value against its threshold, the ledger's statistics beside it"
        views.append(_findings_styler(table, task, caption))
    unavailable = tables["unavailable"]
    untested = unavailable.loc[unavailable["finding"].str.startswith(f"{step}.")]
    if not untested.empty:
        views.append(_untested_view(untested))
    return views


def _findings_styler(table: pd.DataFrame, task: str, caption: str) -> Styler:
    """A findings table styled, its detail column kept wide."""
    styler = style_table(table, column_formats(table, task), caption=caption)
    # a wide table squeezes the last column: the detail would wrap a word per line
    return styler.set_properties(subset=["detail"], **{"min-width": "24em"})


def _cluster_summary(clusters: pd.DataFrame) -> pd.DataFrame:
    """One row per cluster (`CLUSTER_SUMMARY`): its first member (the highest concordance) and
    that member's concordance, the size, every member in the cluster's order, the lowest
    association of another member with the first and the highest `explained_by_others` (NaN
    when none)."""
    rows = []
    for number, members in clusters.groupby("cluster", sort=True):
        first = members.iloc[0]
        rows.append({
            "cluster": number, "feature": first["feature"], "concordance": first["concordance"],
            "size": len(members), "features": ", ".join(members["feature"]),
            "association_min": members["association_with_best"].iloc[1:].min(),
            "explained_by_others_max": members["explained_by_others"].max(),
        })  # fmt: skip
    return pd.DataFrame(rows, columns=CLUSTER_SUMMARY)


def _redundancy_views(
    rows: pd.DataFrame, clusters: pd.DataFrame, ledger: pd.DataFrame, task: str
) -> list:
    """The clusters one row each (or a line when there is none), then the redundancy findings
    by finding, cluster and value (descending), the cluster's columns joined beside each."""
    views: list = []
    if clusters.empty:
        views.append(paragraph("No cluster: no pair reached a redundancy threshold."))
    else:
        summary = _cluster_summary(clusters)
        caption = (
            "One row per cluster of near-duplicates: feature is its member with the highest "
            "concordance (on the snapshot) and concordance that member's, size the number of "
            "members, features every member strongest first, association_min the weakest "
            "|association| of another member with the first, explained_by_others_max the "
            "highest R² on ranks of a numeric member from the other numeric members (blank: "
            f"none computable). {NEAR_DUPLICATES}"
        )
        views.append(style_table(summary, column_formats(summary, task), caption=caption))
    if rows.empty:
        return views
    joined = clusters.set_index("feature")[["cluster", "association_with_best",
                                            "explained_by_others"]]  # fmt: skip
    table = rows.join(joined, on="feature").join(
        ledger.set_index("feature")["concordance_window"], on="feature"
    )
    table = table.assign(position=table["finding"].map(list(FINDINGS).index))
    table = table.sort_values(["position", "cluster", "value"], ascending=[True, True, False],
                              kind="stable", ignore_index=True)  # fmt: skip
    caption = (
        "Each feature's strongest |association| with a partner against its threshold, by "
        "finding, cluster and value; association_with_best is |association| with its cluster's "
        "first member, the partners in the detail"
    )
    return [*views, _findings_styler(table[REDUNDANCY_VIEW], task, caption)]


def _untested_view(untested: pd.DataFrame) -> Styler:
    """A step's findings it could not test, grouped by finding and reason."""
    grouped = untested.groupby(["finding", "reason"], sort=False)["feature"].agg(list)
    table = grouped.reset_index().rename(columns={"feature": "features"})
    table.insert(2, "count", table["features"].map(len))
    table["features"] = table["features"].map(_listed)
    caption = "Not available, decided before computing: no finding either way"
    return style_table(table, {"count": COUNT}, caption=caption)


def _review_views(proposed: pd.DataFrame) -> list:
    """The proposed decisions: one row per open flag finding with its threshold and each feature
    beside this run's value, then the two calls per finding to copy, verb left to the person; a
    line when no flag is open."""
    if proposed.empty:
        return [paragraph("No flag is open: nothing to decide.")]
    features = [
        "\n".join(f"{name}: {'not raised' if value is None else plain_number(value)}"
                  for name, value in zip(row.features, row.values, strict=True))
        for row in proposed.itertuples()
    ]  # fmt: skip
    table = proposed[["finding", "threshold"]].assign(features=features)
    caption = (
        "One row per open flag, each feature with this run's value ('not raised': open from an "
        "earlier run); a keep settles only the finding it names"
    )
    styler = style_table(table, {"threshold": plain_number}, caption=caption)
    calls = "\n\n".join(
        f"# {row.finding}\n{row.keep_call}\n{row.exclude_call}" for row in proposed.itertuples()
    )
    header = (
        "# The calls to copy: each takes any subset of the finding's features. Put each feature in "
        "the call\n# you choose (keep some, exclude others, leave the rest held), delete what you "
        "do not use and write\n# the reason; CONFIG and ENVIRONMENT are notebook 03's setup "
        "cell's."
    )
    return [styler.set_properties(subset=["features"], **{"white-space": "pre-line"}),
            preformatted(f"{header}\n\n{calls}")]  # fmt: skip


def _ledger_view(ledger: pd.DataFrame, task: str) -> Styler:
    """Every candidate in the ledger's order with its derived decision (from the audit log, never
    stored) and Feature Checks' columns; list cells comma-separated."""
    table = ledger[[column for column in LEDGER_VIEW if column in ledger]].copy()
    for column in ("flags", "notes", "kept"):
        table[column] = table[column].map(_listed)
    caption = (
        "The ledger with the derived decisions: held (an open flag holds it out of training), "
        "kept and excluded (the entries in force), auto_excluded (lineage or unsupported), pass; "
        "every column is in ledger.parquet"
    )
    return style_table(table, column_formats(table, task), caption=caption)


def _per_period_views(per_period: pd.DataFrame, meta: dict, resolved: UseCaseConfig) -> list:
    """A line pointing to EDA's report for the concordance per window period, then every
    candidate's PSI against the snapshot per compared period as a feature × period table."""
    periods = [label for labels in meta["compared_periods"].values() for label in labels]
    psi = per_period.pivot(index="feature", columns="period", values="psi").reindex(
        columns=periods, index=pd.unique(per_period["feature"])
    )
    stability = resolved.feature_checks.stability
    fires = (
        "the stability step did not run, so no psi note fires"
        if stability is None
        else f"a psi_window or psi_latest note fires at feature_checks.stability.psi_note_min = "
        f"{plain_number(stability.psi_note_min)}, its _large flag at psi_max = "
        f"{plain_number(stability.psi_max)}"
    )
    psi_caption = (
        f"PSI of each compared period against the snapshot {meta['snapshot_period']}, label-free; "
        f"{fires}; never the validation period"
    )
    return [
        paragraph("Every candidate's concordance per window period is in EDA's report."),
        style_table(psi, dict.fromkeys(psi.columns, "{:.3f}"), caption=psi_caption),
    ]


def _stability_chart(
    concordance_per_period: pd.DataFrame, findings: pd.DataFrame
) -> go.Figure | str:
    """The concordance per window period (EDA's `concordance_per_period`) of the features
    `concordance_unstable` raised, one line each (a PSI finding says nothing about the
    concordance; EDA's report shows every candidate); "Not available" without one (D-035)."""
    unstable = findings["finding"] == "stability.concordance_unstable"
    names = list(dict.fromkeys(findings.loc[unstable, "feature"]))
    if not names:
        return paragraph("Not available: no concordance_unstable finding.")
    rows = concordance_per_period.loc[concordance_per_period["feature"].isin(names)]
    return charts.grouped_lines(
        rows, "period", "concordance", group="feature", reference=0.5, from_zero=False,
        title="Concordance per period: the features concordance_unstable raised", x_title="Period",
        y_title="Concordance (window's direction)", legend_title="Feature", group_order=names,
    )  # fmt: skip


def _appendix_views(meta: dict, resolved: UseCaseConfig, decisions: pd.DataFrame) -> dict:
    """The resolved config, the audit log, the entries this run wrote and the timings."""
    config = yaml.safe_dump(resolved.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
    written = pd.DataFrame(meta["entries_written"], columns=["seq", "op", "finding"])
    seconds = meta["timings"]["seconds"]
    timings = pd.DataFrame({"phase": list(seconds), "seconds": list(seconds.values())})
    return {
        "resolved_config": preformatted(config),
        "decisions": style_table(decisions, caption="The audit log's entries, replayed in order"),
        "entries_written": style_table(written, caption=WRITTEN),
        "timings": style_table(timings, {"seconds": "{:.2f}"}, caption="Seconds per phase"),
    }


def _step_sections(views: dict) -> list[tuple[str, list]]:
    """Each step's blocks as a subsection headed by its name in words, "Time alignment"."""
    return [(step.replace("_", " ").capitalize(), step_blocks)
            for step, step_blocks in views["steps"].items()]  # fmt: skip


def report_sections(views: dict) -> list[tuple[str, list]]:
    """The four parts in feature_checks.md's order, each section's blocks from `views`."""
    return [
        ("Summary", [("Choices", [views["choices"]]), ("How to read", views["how_to_read"]),
                     ("EDA headline", [views["headline"]]), ("Warnings", [views["warnings"]]),
                     ("Flags and notes", [views["raised"]]), ("Held features", views["held"])]),
        ("Core", [
            ("Findings per step", _step_sections(views)),
            ("Proposed decisions", views["proposed_decisions"]),
            ("Ledger with decisions", [views["ledger"]]),
        ]),
        ("Extended", [
            ("Per period", [*views["per_period"], views["stability_chart"]]),
        ]),
        ("Appendix", [
            ("Resolved config", [views["resolved_config"]]),
            ("Decisions", [views["decisions"]]), ("Entries written", [views["entries_written"]]),
            ("Timings", [views["timings"]]),
        ]),
    ]  # fmt: skip
