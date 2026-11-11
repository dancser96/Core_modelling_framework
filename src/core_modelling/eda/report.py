"""The EDA report: the views from the stage's tables, the four parts and the warnings
(docs/components/eda.md "The views", docs/components/reporting.md "The EDA report").

`build_views` turns the stored tables and the meta into the Stylers, figures and HTML blocks the
report embeds and notebook 02 displays; `report_sections` arranges them as summary → core →
extended → appendix; `eda_warnings` applies eda.md's six warning rules. `group_chart`,
`strata_chart` and `boxes` are public because `explore.py` draws the same views.
Every estimate axis takes the task's `axis_format`; lift and concordance axes stay plain. What
cannot be drawn is decided before drawing (no lift over a base that is not positive, no log axis
over a non-positive whisker, T30); an empty section reads "Not available: <reason>" (D-035).

`StageResult.views`, by key; a dict maps each subsection's name to its list of blocks:
- `choices` (Styler): what was chosen, its value and the alternatives (D-032).
- `how_to_read` (list of HTML): the five reading notes.
- `headline` (HTML): the snapshot's and the window's headline numbers.
- `warnings` (HTML): the numbered warnings.
- `funnel` (Styler): the rows per window period through each eligibility step.
- `sources` (Styler, or "Not available" when the spine is the only source): the share of the
  spine's rows each joined feature source matched, per compared period and over them all.
- `target_per_period` (list): the table (with the pooled `all` row) and the chart per period,
  each with its 95% interval.
- `target_by_stratum` (dict variable → [Styler, Figure]): the target by each stratum's levels.
- `ranking` (Styler): every supported candidate by rank, a bar on the concordance it is ordered
  by (`RANKING_VIEW`).
- `excluded` (Styler): the lineage and unsupported columns, excluded automatically.
- `decision_note` (HTML): the decision against the snapshot, what the slices are and are not,
  the leak cue; the report opens the slices with it, notebook 02 says it in its text.
- `slices` (list): the key features at the decision's slices (Styler) and their capture curve
  (Figure), "Not available" when nothing can be shown.
- `deep_dives` (dict feature → list): per key feature, the listed ones first
  (`list_key_features`), `_deep_dive`'s views.
- `reference_groups` (dict tag → list of Stylers): the rows kept and excluded per window period
  (from the funnel), the snapshot's size, composition per stratum, key features.
- `correlation` (list): the association heatmap of the key features, then the candidates they
  represent (Styler, or a line saying none).
- `profile` (list of two Stylers, each "Not available" without a candidate of its kind): the
  numerics' value ranges, then the categoricals' largest levels, in rank order.
- `concordance_per_period` (Styler): every candidate × window period, in rank order, read in
  the window's direction, greyed where insufficient (`_per_period_view`).
- `kinds`, `ledger`, `decisions`, `collect`, `timings` (Stylers), `resolved_config` (HTML): the
  appendix.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from pandas.io.formats.style import Styler

from core_modelling.config.schema import UseCaseConfig
from core_modelling.dataset.frames import GB, SNAPSHOT_CALLOUT
from core_modelling.eda.deep_dives import MIN_BIN_SUPPORT
from core_modelling.eda.population import headline_formats
from core_modelling.eda.profile import QUANTILES, TOP_LEVELS
from core_modelling.eda.ranking import list_key_features
from core_modelling.eda.slices import RANDOM, skipped_slices
from core_modelling.reporting import blocks, charts
from core_modelling.reporting.formats import COUNT, SHARE, column_formats, format_of, plain_number
from core_modelling.reporting.html import paragraph, style_table
from core_modelling.reporting.theme import THEME
from core_modelling.statistics.association import PAIRWISE_ROWS
from core_modelling.tasks import TASK_SPECS

RANKING_VIEW = ["rank", "feature", "kind", "concordance", "concordance_plain", "direction",
                "concordance_window", "missing_share", "null_concordance", "zero_share",
                "dominant_share", "levels", "key_feature", "represented_by",
                "unavailable"]  # fmt: skip
CHOICE_NAMES = ["automation_level", "task", "decision", "metric", "slices", "period",
                "observation_window", "target_window", "validation_period", "eligibility_analysis",
                "eligibility_modelling", "candidate_count", "candidate_patterns", "kinds_summary",
                "kind_overrides", "snapshot", "bins", "key_features", "strata", "pairwise_cap",
                "replayed_to", "config_hash", "data_definition_hash"]  # fmt: skip
ALL_CLIENTS = (
    "EDA reads every client of the observation window: feature decisions taken from this report "
    "have seen the labels of the clients that later form the test split."
)


def _group_table(groups: pd.DataFrame, task: str, caption: str, interval: bool = False) -> Styler:
    """A group table (deep dive or stratum): rows, support, the estimate coloured by its lift,
    the lift and an amount's median and non-zero share; insufficient groups greyed."""
    label = "group" if "group" in groups else "level"
    shown = [label, "rows", "support", "estimate", *(["low", "high"] if interval else []), "lift",
             "median", "nonzero_share"]  # fmt: skip
    table = groups[[column for column in shown if column in groups]].reset_index(drop=True)
    lift = table[["lift"]].rename(columns={"lift": "estimate"})
    greyed = groups["insufficient"].reset_index(drop=True)
    return style_table(table, column_formats(table, task), lift, greyed, caption=caption)


def build_views(
    tables: dict[str, pd.DataFrame],
    meta: dict,
    resolved: UseCaseConfig,
    ledger: pd.DataFrame,
    decisions: pd.DataFrame,
) -> dict:
    """Every view by its `StageResult.views` key (the module docstring's list)."""
    ranking = tables["ranking"]
    keys = list_key_features(ranking).set_index("feature")
    return {
        **_summary_views(meta, resolved),
        **_target_views(tables, resolved),
        "sources": _sources_view(tables["sources"]),
        **_ranking_views(ranking, meta, resolved.task),
        **_slices_views(tables, meta, resolved),
        "deep_dives": {
            name: _deep_dive(row, tables, meta["snapshot_base"], resolved)
            for name, row in keys.iterrows()
        },
        "reference_groups": _reference_views(
            tables["reference_groups"], tables["funnel"], resolved.task
        ),
        "correlation": _correlation_view(
            tables["correlation"], ranking, resolved.eda.key_features.max_correlation, resolved.task
        ),
        "profile": _profile_views(tables["profile"]),
        "concordance_per_period": _per_period_view(
            tables["concordance_per_period"], meta["compared_periods"]["window"], resolved
        ),
        **_appendix_views(meta, resolved, ledger, decisions),
    }


def _summary_views(meta: dict, resolved: UseCaseConfig) -> dict:
    """The choices block, the how-to-read notes, the headline and the numbered warnings."""
    kinds = list(meta["kinds"].values())
    unsupported, lineage = len(meta["unsupported"]), len(meta["lineage"])
    values = {
        "metric": resolved.decision.metric or "derived from decision.type",
        "candidate_count": f"{len(meta['candidates'])} ({unsupported} unsupported); {lineage} "
        "lineage columns excluded",
        "kinds_summary": f"{kinds.count('numeric')} numeric, {kinds.count('categorical')} "
        f"categorical, {unsupported} unsupported",
        "slices": list(meta["slices"]),
        "snapshot": f"{resolved.eda.snapshot}: {meta['snapshot_period']}",
        "pairwise_cap": f"{PAIRWISE_ROWS:,}",
        **blocks.identity_values(meta),
    }
    spec = TASK_SPECS[resolved.task]
    notes = (resolved.eda.bins, spec["estimate_noun"], spec["support_name"], MIN_BIN_SUPPORT)
    return {
        "choices": blocks.choices_block(resolved, CHOICE_NAMES, values),
        "how_to_read": _how_to_read(*notes),
        "headline": blocks.headline(meta["headline"], headline_formats(resolved.task)),
        "warnings": blocks.warnings_block(meta["warnings"]),
    }


def _how_to_read(
    bins: int | None, estimate_noun: str, support_name: str, group_support: int
) -> list[str]:
    """The five how-to-read notes of a report that shows concordance, lift and intervals
    (reporting.md req. 8).

    `bins` is `eda.bins`; with None every statistic is exact and the binning sentence is left
    out. `estimate_noun` and `support_name` are the task's words for its estimate (`rate`,
    `mean`) and its support; `group_support` is the support a key feature's group needs.
    """
    concordance = (
        "Concordance says how well a feature orders clients by the target: 0.5 is no better "
        "than chance, 1 a perfect ordering, whichever way round (the direction column says "
        "which). For a yes/no target it is the AUC of that feature alone."
    )
    if bins is not None:
        concordance += (
            f" Numerics are read on {bins} quantile bins; pairs inside one bin count half."
        )
    notes = [
        concordance,
        f"Lift is a group's {estimate_noun} divided by the snapshot's base {estimate_noun}: 1 is "
        "the base, 2 twice the base.",
        "Intervals are 95%: Wilson for a rate, Student t for a mean. On charts they are the "
        "error bars.",
        f"Grey means too little support, still shown: fewer than strata.min_events "
        f"{support_name} ({group_support} in a key feature's groups). Read the interval, not "
        "the point.",
        "null is the clients without a value: their own bar or level, always last.",
    ]
    return [paragraph(note) for note in notes]


def _target_views(tables: dict[str, pd.DataFrame], resolved: UseCaseConfig) -> dict:
    """The funnel, the target per window period (table and chart) and by stratum."""
    task, spec, min_events = resolved.task, TASK_SPECS[resolved.task], resolved.strata.min_events
    funnel, per_period = tables["funnel"], tables["target_per_period"]
    chart = charts.grouped_lines(
        per_period.loc[per_period["period"] != "all"], "period", "estimate", low="low",
        high="high", support="support", title="Target per period", x_title="Period",
        y_title=f"Target {spec['estimate_noun']}", support_title=spec["support_name"],
        y_format=spec["axis_format"],
    )  # fmt: skip
    caption = (
        f"The target per window period and pooled, with its 95% interval (the pooled row's on "
        f"effective clients), greyed below strata.min_events = {min_events} "
        f"{spec['support_name']}"
    )
    shown = per_period.drop(columns="insufficient")  # the grey rows say it
    table = style_table(shown, column_formats(shown, task), greyed=per_period["insufficient"],
                        caption=caption)  # fmt: skip
    plain = tables["strata"].loc[tables["strata"]["feature"].isna()]
    steps = ("Rows per window period through each eligibility step (tagged: the rows a modelling "
             "filter keeps for the model)")  # fmt: skip
    return {
        "funnel": style_table(funnel, dict.fromkeys(funnel.columns[1:], COUNT), caption=steps),
        "target_per_period": [table, chart],
        "target_by_stratum": {
            variable: _stratum_views(part, variable, task, min_events)
            for variable, part in plain.groupby("variable", sort=False)
        },
    }


def _stratum_views(part: pd.DataFrame, variable: str, task: str, min_events: int) -> list:
    """One stratum variable's table (with the interval) and chart, a colour per level."""
    spec = TASK_SPECS[task]
    caption = (
        f"The target by {variable} on the snapshot's eligible rows, coloured by lift, greyed "
        f"below strata.min_events = {min_events} {spec['support_name']}"
    )
    chart = charts.bar_with_intervals(
        part, "level", title=f"Target by {variable}", x_title=variable,
        y_title=f"Target {spec['estimate_noun']}", by_level=True, y_format=spec["axis_format"],
    )  # fmt: skip
    return [_group_table(part, task, caption, interval=True), chart]


def _ranking_views(ranking: pd.DataFrame, meta: dict, task: str) -> dict:
    """The ranking's lean view, a bar on the concordance it is ordered by, and the columns
    excluded automatically."""
    excluded = [(name, "lineage: the target is built from it") for name in meta["lineage"]]
    excluded += [(name, f"unsupported type: {kind}") for name, kind in meta["unsupported"].items()]
    caption = (
        "Every supported candidate by rank, ordered by concordance: the best order's for a "
        "non-monotone feature, whose plain value shows in concordance_plain; every column is in "
        "tables/ranking"
    )
    view = ranking.assign(
        concordance=ranking["ranking_value"],
        concordance_plain=ranking["concordance"].where(ranking["non_monotone"].astype(bool)),
    )[RANKING_VIEW]
    return {
        "ranking": style_table(view, column_formats(view, task), bar="concordance", caption=caption,
                               bar_min=0.5),
        "excluded": style_table(pd.DataFrame(excluded, columns=["feature", "why"]),
                                caption="Excluded automatically, never ranked"),
    }  # fmt: skip


def _rows_of(table: pd.DataFrame, name: str) -> pd.DataFrame:
    """A stacked table's rows of one feature."""
    return table.loc[table["feature"] == name].reset_index(drop=True)


def _deep_dive(
    row: pd.Series, tables: dict[str, pd.DataFrame], base: float, resolved: UseCaseConfig
) -> list:
    """One key feature's views from the stored tables: the group table (by level, or any for an
    amount target), the group chart beside the first stratum's chart (two legends cannot share a
    figure), each further stratum's chart, the concordance row, an amount target's boxes per
    group, then one pivot table per stratum variable but the feature itself. A stratum's levels
    keep the order (and the colours) of "Target by stratum"."""
    name, task, spec = row.name, resolved.task, TASK_SPECS[resolved.task]
    by_level = name in set(tables["levels"]["feature"])
    groups = _rows_of(tables["levels" if by_level else "bins"], name)
    parts = dict(tuple(_rows_of(tables["strata"], name).groupby("variable", sort=False)))
    plain = tables["strata"].loc[tables["strata"]["feature"].isna()]
    orders = {v: list(part["level"]) for v, part in plain.groupby("variable", sort=False)}
    views = []
    if by_level or spec["target_distribution"]:
        value = row["ranking_value"]
        concordance = row["unavailable"] if pd.isna(value) else f"concordance {value:.3f}"
        caption = (
            f"{name} ({row['kind']}, {row['key_feature']}; {concordance}): the target per "
            f"group against the snapshot's base "
            f"{spec['estimate_format'].format(base)}, greyed below MIN_BIN_SUPPORT = "
            f"{MIN_BIN_SUPPORT} {spec['support_name']}"
        )
        views.append(_group_table(groups, task, caption))
    group = group_chart(groups, name, base, task)
    by_stratum = [strata_chart(part, name, v, base, task, orders[v]) for v, part in parts.items()]
    views += [charts.side_by_side(group, by_stratum[0]) if by_stratum else group, *by_stratum[1:]]
    views += _concordance_row(name, tables, task)
    if spec["target_distribution"]:
        target = _rows_of(tables["target_quartiles"], name)
        views.append(boxes(target, "group", f"Target by {name}", name, "Target"))
    min_events = resolved.strata.min_events
    return views + [
        _stratum_pivot(part, name, v, task, min_events, orders[v]) for v, part in parts.items()
    ]


def _concordance_row(name: str, tables: dict[str, pd.DataFrame], task: str) -> list:
    """The per-period concordance, beside a numeric's boxes by target class when it has them;
    "Not available" with the periods' reasons when no period has one (D-035)."""
    quartiles = _rows_of(tables["quartiles"], name)
    periods = _rows_of(tables["per_period"], name)
    if periods["concordance"].isna().all():
        reasons = periods.loc[periods["unavailable"] != "", "unavailable"]
        why = "; ".join(dict.fromkeys(reasons.str.removeprefix("not available: ")))
        chart = blocks.not_available(f"{name}'s concordance per period ({why})")
    else:
        chart = charts.grouped_lines(
            periods, "period", "concordance", support="support", reference=0.5, from_zero=False,
            title=f"{name}: concordance per period", x_title="Period",
            y_title="Concordance (window's direction)",
            support_title=TASK_SPECS[task]["support_name"],
        )  # fmt: skip
    if quartiles.empty:
        return [chart]
    by_class = boxes(quartiles, "target_class", f"{name} by target class", "Target class", name,
                     by_target_class=True)  # fmt: skip
    if isinstance(chart, str):
        return [by_class, chart]
    return [charts.side_by_side(by_class, chart)]


def group_chart(groups: pd.DataFrame, name: str, base: float, task: str) -> go.Figure:
    """Lift by group of a group table with its interval in lift units, or the estimate when no
    lift exists over `base` (decided before drawing, D-035)."""
    spec = TASK_SPECS[task]
    if spec["lift_available"](base):
        data = groups.assign(lift_low=groups["low"] / base, lift_high=groups["high"] / base)
        return charts.lift_chart(data, "group", title=f"Lift by {name}", x_title=name)
    noun = spec["estimate_noun"]
    title = f"Target {noun} by {name}<br><sup>no lift: the base is not positive</sup>"
    return charts.bar_with_intervals(groups, "group", title=title, x_title=name,
                                     y_title=f"Target {noun}",
                                     y_format=spec["axis_format"])  # fmt: skip


def strata_chart(
    part: pd.DataFrame,
    name: str,
    variable: str,
    base: float,
    task: str,
    level_order: list | None = None,
) -> go.Figure:
    """One line per level of `variable` over a feature's groups (`part`: strata rows), in
    `level_order` (its colours; default the table's order): the lift, or the estimate when no
    lift exists over `base` (D-035); insufficient points greyed."""
    spec = TASK_SPECS[task]
    lift = spec["lift_available"](base)
    return charts.grouped_lines(
        part, "feature_group", "lift" if lift else "estimate", group="level",
        reference=1.0 if lift else None, title=f"{name} by {variable}", x_title=name,
        y_title=charts.LIFT_TITLE if lift else f"Target {spec['estimate_noun']}",
        legend_title=variable, group_order=level_order,
        y_format=None if lift else spec["axis_format"],
    )  # fmt: skip


def boxes(
    quartiles: pd.DataFrame,
    group: str,
    title: str,
    x_title: str,
    y_title: str,
    by_target_class: bool = False,
) -> go.Figure:
    """Box plots from quartiles, on a log axis only when skewed above 2 with every whisker
    positive (decided before drawing: a zero would be clamped silently, T30); with
    `by_target_class` the groups take the target classes' colours. An empty table fails naming
    the chart."""
    if quartiles.empty:
        raise ValueError(f"boxes: no quartiles to draw for {title!r}")
    log = bool(quartiles["skew"].iloc[0] > 2 and (quartiles["lower_whisker"] > 0).all())
    return charts.box_from_quartiles(
        quartiles, group, lower="lower_whisker", upper="upper_whisker", title=title,
        x_title=x_title, y_title=y_title + (" (log axis)" if log else ""), log=log,
        by_target_class=by_target_class,
    )  # fmt: skip


def _stratum_pivot(
    part: pd.DataFrame,
    name: str,
    variable: str,
    task: str,
    min_events: int,
    level_order: list,
) -> Styler:
    """One feature × stratum variable (`part`: its strata rows): the estimate by group (in the
    table's order) × level (in `level_order`, "Target by stratum"'s), coloured by lift, greyed
    below `min_events` or without rows; a level missing from `level_order` fails."""
    spec = TASK_SPECS[task]
    present = set(part["level"])
    if not present <= set(level_order):
        raise ValueError(
            f"_stratum_pivot: {name} × {variable} has levels {sorted(present - set(level_order))} "
            "that level_order lacks"
        )
    columns = [level for level in level_order if level in present]
    order = {"index": pd.unique(part["feature_group"]), "columns": columns}
    shown, lift, greyed = (
        part.pivot(index="feature_group", columns="level", values=column)
        .reindex(**order).rename_axis(index=name, columns=variable)
        for column in ("estimate", "lift", "insufficient")
    )  # fmt: skip
    greyed = greyed.astype("boolean").fillna(True).astype(bool)  # a combination without rows
    caption = (
        f"{name} × {variable}: the target per group and level, coloured by lift, greyed below "
        f"strata.min_events = {min_events} {spec['support_name']}"
    )
    formats = dict.fromkeys(shown.columns, format_of("estimate", task))
    return style_table(shown, formats, lift, greyed, caption=caption)


def _tag_sizes(funnel: pd.DataFrame, tag: str) -> pd.DataFrame:
    """Per window period (and `all`), the rows a modelling tag keeps and excludes of those it
    judges: the last `after_` column (modelling filters run after every analysis filter)."""
    after = [column for column in funnel.columns if column.startswith("after_")]
    judged, kept = funnel[after[-1] if after else "spine"], funnel[f"tagged_{tag}"]
    excluded = judged - kept
    return pd.DataFrame({"period": funnel["period"], "rows_kept": kept, "rows_excluded": excluded,
                         "share_excluded": excluded / judged})  # fmt: skip


def _reference_views(table: pd.DataFrame, funnel: pd.DataFrame, task: str) -> dict[str, list]:
    """Per modelling tag, its rows kept and excluded per window period, then its non-empty
    sections: size, composition per stratum, key features."""
    captions = {
        "size": "on the snapshot, the rows the filter excludes (tag 0) against the modelling "
        "population",
        "composition": "each stratum level's share of each side",
        "feature": "the key features on each side and the standardised difference (|SMD| ≥ "
        "0.25 differs: a description, not a test)",
    }
    views: dict[str, list] = {}
    for tag, part in table.groupby("tag", sort=False):
        sizes = _tag_sizes(funnel, tag)
        caption = f"{tag}: the rows per window period the filter keeps and excludes (tag 0)"
        views[tag] = [style_table(sizes, column_formats(sizes, task), caption=caption)]
        for section, caption in captions.items():
            rows = _section_rows(part, section)
            if not rows.empty:
                styled = style_table(rows, column_formats(rows, task), caption=f"{tag}: {caption}")
                views[tag].append(styled)
    return views


def _section_rows(part: pd.DataFrame, section: str) -> pd.DataFrame:
    """One tag's rows of a reference section without the columns the section does not fill; the
    feature section keeps `smd` when no feature has one (`unavailable` says why) and names its
    name column `feature`."""
    rows = part.loc[part["section"] == section].drop(columns=["tag", "section"])
    filled = rows.notna().any()
    if section == "feature":
        filled["smd"] = True
        rows = rows.rename(columns={"variable": "feature"})
    return rows.loc[:, filled.to_numpy()].reset_index(drop=True)


def _correlation_view(
    correlation: pd.DataFrame, ranking: pd.DataFrame, max_correlation: float, task: str
) -> list:
    """The association heatmap of the key features, the method on hover (one without a compared
    pair among them left out and counted; "Not available" when fewer than two have one, D-035),
    then the candidates they represent (`_represented_view`)."""
    keys = list_key_features(ranking)["feature"].tolist()
    inside = correlation["a"].isin(keys) & correlation["b"].isin(keys)
    pairs = correlation.loc[inside & correlation["statistic"].notna()]
    compared = [name for name in keys if name in set(pairs["a"]) | set(pairs["b"])]
    represented = _represented_view(correlation, ranking, max_correlation, task)
    if len(compared) < 2:
        why = "fewer than two key features have a compared pair"
        return [blocks.not_available(why), represented]
    both = pd.concat([pairs, pairs.rename(columns={"a": "b", "b": "a"})], ignore_index=True)
    matrix, hover = (
        both.pivot(index="a", columns="b", values=column)
        .reindex(index=compared, columns=compared).rename_axis(index=None, columns=None)
        for column in ("statistic", "method")
    )  # fmt: skip
    diagonal = pd.DataFrame(np.eye(len(compared), dtype=bool), index=compared, columns=compared)
    matrix = matrix.mask(diagonal, 1.0)
    hover = hover.mask(matrix.isna(), "not compared").mask(diagonal, "itself")
    note = (
        f"on a seeded cap of {PAIRWISE_ROWS:,} snapshot rows: {len(compared)} shown, "
        f"{len(keys) - len(compared)} without a compared pair left out; blank: not compared"
    )
    title = f"Association of the key features<br><sup>{note}</sup>"
    return [charts.heatmap(matrix, hover, title=title), represented]


def _represented_view(
    correlation: pd.DataFrame, ranking: pd.DataFrame, max_correlation: float, task: str
) -> Styler | str:
    """The candidates the key-feature rule skipped, in rank order, each with the key feature that
    represents it and their association; a line saying none when it skipped nothing."""
    skipped = ranking.loc[ranking["represented_by"] != "", ["feature", "represented_by"]]
    rule = f"eda.key_features.max_correlation = {max_correlation:g}"
    if skipped.empty:
        return paragraph(f"The key features represent no candidate: none is associated with one "
                         f"above {rule}.")  # fmt: skip
    both = pd.concat([correlation, correlation.rename(columns={"a": "b", "b": "a"})])
    table = skipped.merge(both, how="left", left_on=["feature", "represented_by"],
                          right_on=["a", "b"], validate="one_to_one")  # fmt: skip
    table = table.rename(columns={"feature": "candidate", "statistic": "association"})
    caption = (
        f"The candidates the key features represent: each skipped for an association above "
        f"{rule} with the key feature named, on the same capped rows"
    )
    shown = table[["candidate", "represented_by", "association", "method"]]
    return style_table(shown, column_formats(shown, task), caption=caption)


def _slices_views(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> dict:
    """The decision paragraph (`decision_note`), and the key features at the slices with their
    capture curve (`slices`), "Not available" without a key feature (D-035)."""
    snapshot = tables["population"].set_index("period").loc[meta["snapshot_period"]]
    rows, support = int(snapshot["known_target"]), int(snapshot["positive_events"])
    note = _decision_paragraph(resolved, rows, support, meta["snapshot_base"])
    slices = tables["slices"]
    if slices.empty:
        return {"decision_note": note, "slices": [blocks.not_available("no key feature")]}
    curve = _capture_chart(tables["capture_curve"], slices, resolved.task)
    return {"decision_note": note, "slices": [_slices_table(slices, resolved, rows), curve]}


def _decision_paragraph(resolved: UseCaseConfig, rows: int, support: int, base: float) -> str:
    """The decision against the snapshot's `rows` labelled rows (a `top_n` list's share, the
    task's perfect list and a random one), what the slices are and are not, and the leak cue."""
    spec, decision = TASK_SPECS[resolved.task], resolved.decision
    noun, base_text = spec["estimate_noun"], spec["estimate_format"].format(base)
    if decision.type != "top_n":
        opening = f"Decision {decision.type}: no fixed list size; the evaluation slices stand in."
    elif decision.n > rows:
        opening = (f"Decision top_n: n = {decision.n:,} is above the snapshot's {rows:,} "
                   "labelled rows, so no slice stands for it.")  # fmt: skip
    else:
        share, perfect = decision.n / rows, spec["perfect_list"](decision.n, support)
        opening = (
            f"Decision top_n: n = {decision.n:,}, {share:.1%} of the snapshot's {rows:,} labelled "
            f"rows: {f'{perfect}; ' if perfect else ''}a random list captures {share:.1%} of "
            f"the {spec['capture_noun']} at the base {noun} {base_text}."
        )
    context = (
        "Below, what one key feature alone reaches on the snapshot, in sample (the key features "
        "and a numeric's direction are read on these rows; the interval treats the order as "
        "fixed): context for the decision, not a baseline; a model is judged against "
        "decision.baselines."
    )
    leak = (
        "A key feature whose slices capture far more than the others' is a leak candidate for "
        "Feature Checks' screens; a null that stands for the outcome shows in the ranking's null "
        "concordance instead, since the null bin is last in every list."
    )
    return paragraph(f"{opening} {context} {leak}")


def _slices_table(slices: pd.DataFrame, resolved: UseCaseConfig, rows: int) -> Styler:
    """The key features (the listed ones first) × the slices: capture, estimate (coloured by
    lift), lift and support, greyed below `MIN_BIN_SUPPORT`, `unavailable` shown when a row has
    a reason."""
    spec, task = TASK_SPECS[resolved.task], resolved.task
    shown = ["feature", "slice", "capture", "estimate", "lift", "support"]
    shown += ["unavailable"] if (slices["unavailable"] != "").any() else []
    table = slices[shown]
    lift = slices[["lift"]].rename(columns={"lift": "estimate"})
    source = "evaluation.slices" + (" and decision.n" if resolved.decision.type == "top_n" else "")
    skipped = skipped_slices(resolved, rows)
    caption = (
        f"Each key feature alone as a list at the slices of {source}, shares of the snapshot's "
        f"{rows:,} labelled rows: a numeric by value in its snapshot direction (one end only), a "
        f"categorical by its levels' {spec['estimate_noun']} cross-fitted by client fold, the "
        f"null bin last; capture is the slice's share of the {spec['capture_noun']}; coloured by "
        f"lift, greyed below MIN_BIN_SUPPORT = {MIN_BIN_SUPPORT} {spec['support_name']}"
        + (f"; skipped, above the labelled rows: {', '.join(skipped)}" if skipped else "")
    )
    return style_table(table, column_formats(table, task), lift, slices["insufficient"],
                       caption=caption)  # fmt: skip


def _capture_chart(curve: pd.DataFrame, slices: pd.DataFrame, task: str) -> go.Figure | str:
    """The capture by share of rows, one line per key feature (the listed ones first) and the
    `RANDOM` diagonal dashed and muted (a reference, not a feature); "Not available" with the
    slices' reasons when no key feature has a curve (D-035)."""
    if curve.empty:
        reasons = slices.loc[slices["unavailable"] != "", "unavailable"]
        why = "; ".join(dict.fromkeys(reasons.str.removeprefix("not available: ")))
        return blocks.not_available(f"the capture curve ({why})")
    fig = charts.grouped_lines(
        curve, "share", "capture", group="feature", insufficient=None, x_numeric=True,
        title="Capture by share of rows<br><sup>each key feature alone, best first; random: a "
        "random list</sup>", x_title="Share of rows (best first)",
        y_title=f"Share of {TASK_SPECS[task]['capture_noun']} captured",
        legend_title="Key feature", y_format=".0%",
    )  # fmt: skip
    fig.update_layout(yaxis_range=[0, 1.02])  # capture stops at 100%: no from-zero headroom
    return fig.update_traces(line={"dash": "dash", "color": THEME["muted"]},
                             selector={"name": RANDOM})  # fmt: skip


def _profile_views(profile: pd.DataFrame) -> list:
    """The value profile as two tables, numerics then categoricals, in rank order on the
    snapshot's eligible rows; "Not available" for a kind without a candidate (D-035)."""
    rows = f"{int(profile['rows'].iloc[0]):,} eligible snapshot rows" if len(profile) else ""
    numeric = {
        "columns": ["feature", "rank", "missing_share", *QUANTILES, "inf_share"],
        "caption": f"Numerics on the {rows}: the range over the finite non-null values and the "
        "share of ±infinity; a sentinel (−1, 999, 9 999 999) shows as a mass point at min or max",
    }
    categorical = {
        "columns": ["feature", "rank", "missing_share", "top_levels"],
        "caption": f"Categoricals on the {rows}: the {TOP_LEVELS} largest levels with their "
        "shares of the rows",
    }
    formats = {"rank": COUNT, "missing_share": SHARE, "inf_share": SHARE,
               **dict.fromkeys(QUANTILES, plain_number)}  # fmt: skip
    views = []
    for kind, view in {"numeric": numeric, "categorical": categorical}.items():
        part = profile.loc[profile["kind"] == kind, view["columns"]].reset_index(drop=True)
        if part.empty:
            views.append(blocks.not_available(f"no {kind} candidate"))
        else:
            views.append(style_table(part, formats, caption=view["caption"]))
    return views


def _per_period_view(
    per_period: pd.DataFrame, window: list[str], resolved: UseCaseConfig
) -> Styler:
    """Every candidate's concordance per window period (`concordance_per_period`) as a feature ×
    period table in rank order, greyed below `strata.min_events`, blank where not available."""
    order = {"index": pd.unique(per_period["feature"]), "columns": window}
    shown, greyed = (
        per_period.pivot(index="feature", columns="period", values=column).reindex(**order)
        for column in ("concordance", "insufficient")
    )
    support = TASK_SPECS[resolved.task]["support_name"]
    caption = (
        f"Every candidate's concordance per window period, in rank order, read in the window's "
        f"direction (a flip reads below 0.5); greyed below strata.min_events = "
        f"{resolved.strata.min_events} {support}; blank where not available "
        "(tables/concordance_per_period's unavailable says why)"
    )
    formats = dict.fromkeys(shown.columns, format_of("concordance", resolved.task))
    # a period the reindex adds (none in the table) is blank, not greyed
    greyed = greyed.astype("boolean").fillna(False).astype(bool)
    return style_table(shown, formats, greyed=greyed, caption=caption)


def _sources_view(sources: pd.DataFrame) -> Styler | str:
    """The sources' matched shares per compared period; "Not available" when the table holds no
    joined source (decided from its columns, D-035)."""
    if sources.columns.tolist() == ["period", "rows"]:
        return blocks.not_available("the spine is the only source")
    caption = (
        "The spine's rows per compared period (window, gap, latest) and over them all, and the "
        "share of them each joined feature source matched: a share well below 1 means that "
        "source's columns are null for the rest; a drop in the latest periods, a source that "
        "arrives late"
    )
    formats = {"rows": COUNT, **dict.fromkeys(sources.columns[2:], SHARE)}
    return style_table(sources, formats, caption=caption)


def _appendix_views(
    meta: dict, resolved: UseCaseConfig, ledger: pd.DataFrame, decisions: pd.DataFrame
) -> dict:
    """The kinds with the overrides, the ledger, the resolved config, the decisions, the collect
    log and the timings (the association's seconds within the statistics')."""
    overrides = resolved.features.kinds
    kinds = ledger[["feature", "kind", "source", "lineage", "unsupported"]].assign(
        override=ledger["feature"].map(lambda name: overrides.get(name, ""))
    )
    collect = pd.DataFrame(meta["collect"]).drop(columns="step")
    counts = dict.fromkeys(collect.columns.drop("frame"), COUNT)
    times = meta["timings"]
    seconds = {**times["seconds"], "association (within statistics)": times["association_seconds"]}
    kinds_caption = "Kinds from the schema (override: features.kinds) and each column's source"
    estimate = times["cells_estimate"]  # null unless eda.bins is null (exact statistics)
    estimated = "" if estimate is None else f" ({estimate:,} estimated before the passes)"
    timed = (f"Seconds per phase; {times['cells']:,} cells counted{estimated}, "
             f"{times['numeric_null_masks']:,} distinct numeric null masks")  # fmt: skip
    return {
        "kinds": style_table(kinds, caption=kinds_caption),
        "ledger": style_table(ledger, column_formats(ledger, resolved.task), caption="The ledger"),
        "collect": style_table(collect, counts, caption="Collected frames (bytes)"),
        **blocks.appendix(resolved, decisions, seconds, timed),
    }


def eda_warnings(
    tables: dict[str, pd.DataFrame], log: list[dict], resolved: UseCaseConfig, snapshot: str
) -> list[str]:
    """The warnings, one per rule that applies, in eda.md's order: few snapshot events, a thin
    window period, a thin stratum level, the contract's null callout, the snapshot collect above
    its budget, and always the all-client warning (D-030)."""
    spec, min_events = TASK_SPECS[resolved.task], resolved.strata.min_events
    support = spec["support_name"]
    events = tables["population"].set_index("period").loc[snapshot, "positive_events"]
    items = [spec["events_warning"](int(events))]
    per_period = tables["target_per_period"]
    thin = per_period.loc[per_period["insufficient"] & (per_period["period"] != "all"), "period"]
    if not thin.empty:
        items.append(
            f"The window periods {', '.join(thin)} hold fewer than strata.min_events = "
            f"{min_events} {support}: their per-period statistics are insufficient."
        )
    strata = tables["strata"]
    rare = strata.loc[strata["feature"].isna() & strata["insufficient"]]
    if not rare.empty:
        levels = ", ".join(rare["variable"] + " = " + rare["level"].astype(str))
        items.append(f"Stratum levels below strata.min_events = {min_events} {support}: {levels}.")
    items += [entry["callout"] for entry in log if entry.get("check") == "null_in_window"]
    for entry in log:
        if entry["step"] == "collect" and entry["estimate_bytes"] > entry["budget_bytes"]:
            items.append(
                f"The snapshot collect, about {entry['estimate_bytes'] / GB:.2f} GB at "
                f"the conversion peak, is above the collect budget of "
                f"{entry['budget_bytes'] / GB:.2f} GB: {SNAPSHOT_CALLOUT}."
            )
    # The events rule and a contract entry without a callout give None: that rule does not apply.
    return [item for item in items if item] + [ALL_CLIENTS]


def _nested(views: dict[str, list], reason: str) -> list:
    """Each entry as its own subsection, or one "Not available" line when there is none."""
    return list(views.items()) or [blocks.not_available(reason)]


def report_sections(views: dict) -> list[tuple[str, list]]:
    """The four parts in eda.md's order, each section's blocks from `views`."""
    return [
        ("Summary", [("Choices", [views["choices"]]), ("How to read", views["how_to_read"]),
                     ("Headline", [views["headline"]]), ("Warnings", [views["warnings"]])]),
        ("Core", [
            ("Funnel per window period", [views["funnel"]]),
            ("Sources per period", [views["sources"]]),
            ("Target per period", views["target_per_period"]),
            ("Target by stratum", _nested(views["target_by_stratum"], "no strata.variables")),
            ("Univariate ranking",
             [views["ranking"], ("Excluded automatically", [views["excluded"]])]),
            ("At the decision's slices", [views["decision_note"], *views["slices"]]),
            ("Key features", _nested(views["deep_dives"], "no key feature")),
        ]),
        ("Extended", [
            ("Reference groups", _nested(views["reference_groups"], "no modelling filter")),
            ("Correlation overview", views["correlation"]),
            ("Value profile", views["profile"]),
            ("Concordance per period", [views["concordance_per_period"]]),
        ]),
        ("Appendix", [
            ("Kinds", [views["kinds"]]), ("Feature ledger", [views["ledger"]]),
            ("Resolved config", [views["resolved_config"]]),
            ("Decisions", [views["decisions"]]), ("Collect log", [views["collect"]]),
            ("Timings", [views["timings"]]),
        ]),
    ]  # fmt: skip
