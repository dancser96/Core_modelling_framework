"""The EDA report: the views from the stage's tables, the four parts and the warnings
(docs/components/eda.md "The views", docs/components/reporting.md "The EDA report").

`build_views` turns the stored tables and the meta into the Stylers, figures and HTML blocks the
report embeds and notebook 02 displays; `report_sections` arranges them as summary → core →
extended → appendix; `eda_warnings` applies eda.md's six warning rules. `group_chart`,
`strata_chart`, `boxes` and `pivot_table` are public because `explore.py` draws the same views.
What cannot be drawn is decided before drawing (no lift over a base that is not positive, no log
axis over a non-positive whisker, T30); an empty section reads "Not available: <reason>" (D-035).

`StageResult.views`, by key; a dict maps each subsection's name to its list of blocks:
- `choices` (Styler): what was chosen, its value and the alternatives (D-032).
- `how_to_read` (list of HTML): the five reading notes.
- `headline` (HTML): the snapshot's and the window's headline numbers.
- `warnings` (HTML): the numbered warnings.
- `funnel` (Styler): the rows per window period through each eligibility step.
- `target_per_period` (list): the table (with the pooled `all` row) and the chart per period,
  each with its 95% interval.
- `target_by_stratum` (dict variable → [Styler, Figure]): the target by each stratum's levels.
- `ranking` (Styler): every supported candidate by rank, a bar on the concordance it is ordered
  by (`RANKING_VIEW`).
- `excluded` (Styler): the lineage and unsupported columns, excluded automatically.
- `deep_dives` (dict feature → list): per key feature in rank order, `_deep_dive`'s views.
- `reference_groups` (dict tag → list of Stylers): the rows kept and excluded per window period
  (from the funnel), the snapshot's size, composition per stratum, key features.
- `correlation` (list): the association heatmap of the key features and those they represent.
- `kinds`, `ledger`, `decisions`, `collect`, `timings` (Stylers), `resolved_config` (HTML): the
  appendix.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import yaml
from pandas.io.formats.style import Styler

from core_modelling.config.identities import short
from core_modelling.config.schema import UseCaseConfig
from core_modelling.dataset.frames import GB, SNAPSHOT_CALLOUT
from core_modelling.eda.deep_dives import MIN_BIN_SUPPORT
from core_modelling.reporting import blocks, charts
from core_modelling.reporting.html import paragraph, preformatted, style_table
from core_modelling.statistics.association import PAIRWISE_ROWS
from core_modelling.tasks import TASK_SPECS

COUNT, SHARE, VALUE = "{:,.0f}", "{:.1%}", "{:,.4g}"
CONCORDANCES = ["concordance", "concordance_plain", "concordance_se", "concordance_best_order",
                "concordance_window", "null_concordance", "null_concordance_window",
                "se"]  # fmt: skip
SHARES = ["missing_share", "missing_share_window", "zero_share", "zero_share_window",
          "dominant_share", "dominant_share_window", "nonzero_share", "nonzero_low",
          "nonzero_high", "eligible_share"]  # fmt: skip
ESTIMATES = ["estimate", "low", "high", "median", "nonzero_mean", "nonzero_median", "q1", "q3",
             "lower_whisker", "upper_whisker"]  # fmt: skip
PREFIXES = {"rows_": COUNT, "share_": SHARE, "median_": VALUE, "p10_": VALUE, "p90_": VALUE}
RANKING_VIEW = ["rank", "feature", "kind", "concordance", "concordance_plain", "direction",
                "concordance_window", "missing_share", "null_concordance", "zero_share",
                "dominant_share", "levels", "key_feature", "represented_by",
                "unavailable"]  # fmt: skip
CHOICE_NAMES = ["automation_level", "task", "decision", "metric", "period", "observation_window",
                "target_window", "validation_period", "eligibility_analysis",
                "eligibility_modelling", "candidate_count", "candidate_patterns", "kinds_summary",
                "kind_overrides", "snapshot", "bins", "key_features", "strata", "pairwise_cap",
                "replayed_to", "config_hash", "data_definition_hash"]  # fmt: skip
ALL_CLIENTS = (
    "EDA reads every client of the observation window: feature decisions taken from this report "
    "have seen the labels of the clients that later form the test split."
)


def _formats(df: pd.DataFrame, task: str) -> dict[str, str]:
    """Each known column's format: counts with separators, the estimate as the task prints it,
    shares as percentages, concordances to three decimals, lift and differences to two."""
    estimate = TASK_SPECS[task]["estimate_format"]
    rules = {
        **dict.fromkeys(["rows", "support", "positive_rows", "levels", "rank", "n"], COUNT),
        **dict.fromkeys(ESTIMATES, estimate),
        **dict.fromkeys(SHARES, SHARE),
        **dict.fromkeys(CONCORDANCES, "{:.3f}"),
        **dict.fromkeys(["lift", "smd", "skew"], "{:.2f}"),
    }
    prefixed = {c: f for c in df.columns for p, f in PREFIXES.items() if str(c).startswith(p)}
    return {c: rules.get(c, prefixed.get(c)) for c in df.columns if c in rules or c in prefixed}


def _group_table(groups: pd.DataFrame, task: str, caption: str, interval: bool = False) -> Styler:
    """A group table (deep dive or stratum): rows, support, the estimate coloured by its lift,
    the lift and an amount's median and non-zero share; insufficient groups greyed."""
    label = "group" if "group" in groups else "level"
    shown = [label, "rows", "support", "estimate", *(["low", "high"] if interval else []), "lift",
             "median", "nonzero_share"]  # fmt: skip
    table = groups[[column for column in shown if column in groups]].reset_index(drop=True)
    lift = table[["lift"]].rename(columns={"lift": "estimate"})
    greyed = groups["insufficient"].reset_index(drop=True)
    return style_table(table, _formats(table, task), lift, greyed, caption=caption)


def build_views(
    tables: dict[str, pd.DataFrame],
    meta: dict,
    resolved: UseCaseConfig,
    ledger: pd.DataFrame,
    decisions: pd.DataFrame,
) -> dict:
    """Every view by its `StageResult.views` key (the module docstring's list)."""
    ranking = tables["ranking"]
    keys = ranking.loc[ranking["key_feature"] != ""].set_index("feature")
    return {
        **_summary_views(meta, resolved),
        **_target_views(tables, resolved),
        **_ranking_views(ranking, meta, resolved.task),
        "deep_dives": {
            name: _deep_dive(row, tables, meta["snapshot_base"], resolved)
            for name, row in keys.iterrows()
        },
        "reference_groups": _reference_views(
            tables["reference_groups"], tables["funnel"], resolved.task
        ),
        "correlation": _correlation_view(tables["correlation"], ranking),
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
        "snapshot": f"{resolved.eda.snapshot}: {meta['snapshot_period']}",
        "pairwise_cap": f"{PAIRWISE_ROWS:,}",
        "replayed_to": meta["replayed_to"],
        "config_hash": short(meta["config_hash"]),
        "data_definition_hash": short(meta["data_definition_hash"]),
    }
    choices = [
        {**blocks.CHOICES[name], **({"value": values[name]} if name in values else {})}
        for name in CHOICE_NAMES
    ]
    numbers = {name.replace("_", " "): value for name, value in meta["headline"].items()}
    spec = TASK_SPECS[resolved.task]
    notes = (resolved.eda.bins, spec["estimate_noun"], spec["support_name"], MIN_BIN_SUPPORT)
    return {
        "choices": blocks.choices_block(resolved, choices),
        "how_to_read": blocks.how_to_read(*notes),
        "headline": blocks.headline(numbers),
        "warnings": blocks.warnings_block(meta["warnings"]),
    }


def _target_views(tables: dict[str, pd.DataFrame], resolved: UseCaseConfig) -> dict:
    """The funnel, the target per window period (table and chart) and by stratum."""
    task, spec, min_events = resolved.task, TASK_SPECS[resolved.task], resolved.strata.min_events
    funnel, per_period = tables["funnel"], tables["target_per_period"]
    chart = charts.grouped_lines(
        per_period.loc[per_period["period"] != "all"], "period", "estimate", low="low",
        high="high", support="support", title="Target per period", x_title="Period",
        y_title=f"Target {spec['estimate_noun']}", support_title=spec["support_name"],
    )  # fmt: skip
    caption = (
        f"The target per window period and pooled, with its 95% interval (the pooled row's on "
        f"effective clients), greyed below strata.min_events = {min_events} "
        f"{spec['support_name']}"
    )
    shown = per_period.drop(columns="insufficient")  # the grey rows say it
    table = style_table(shown, _formats(shown, task), greyed=per_period["insufficient"],
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
        y_title=f"Target {spec['estimate_noun']}", by_level=True,
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
        "ranking": style_table(view, _formats(view, task), bar="concordance", caption=caption,
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
        pivot_table(part, name, v, task, min_events, orders[v]) for v, part in parts.items()
    ]


def _concordance_row(name: str, tables: dict[str, pd.DataFrame], task: str) -> list:
    """The per-period concordance, beside a numeric's boxes by target class when it has them;
    "Not available" with the periods' reasons when no period has one (D-035)."""
    quartiles = _rows_of(tables["quartiles"], name)
    periods = _rows_of(tables["per_period"], name)
    if periods["concordance"].isna().all():
        reasons = periods.loc[periods["unavailable"] != "", "unavailable"]
        why = "; ".join(dict.fromkeys(reasons.str.removeprefix("not available: ")))
        chart = paragraph(f"Not available: {name}'s concordance per period ({why}).")
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
    noun = TASK_SPECS[task]["estimate_noun"]
    if TASK_SPECS[task]["lift_available"](base):
        data = groups.assign(lift_low=groups["low"] / base, lift_high=groups["high"] / base)
        return charts.lift_chart(data, "group", title=f"Lift by {name}", x_title=name)
    title = f"Target {noun} by {name}<br><sup>no lift: the base is not positive</sup>"
    return charts.bar_with_intervals(groups, "group", title=title, x_title=name,
                                     y_title=f"Target {noun}")  # fmt: skip


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
    lift, noun = TASK_SPECS[task]["lift_available"](base), TASK_SPECS[task]["estimate_noun"]
    return charts.grouped_lines(
        part, "feature_group", "lift" if lift else "estimate", group="level",
        reference=1.0 if lift else None, title=f"{name} by {variable}", x_title=name,
        y_title=charts.LIFT_TITLE if lift else f"Target {noun}", legend_title=variable,
        group_order=level_order,
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


def pivot_table(
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
            f"pivot_table: {name} × {variable} has levels {sorted(present - set(level_order))} "
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
    formats = dict.fromkeys(shown.columns, spec["estimate_format"])
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
        views[tag] = [style_table(sizes, _formats(sizes, task), caption=caption)]
        for section, caption in captions.items():
            rows = _section_rows(part, section)
            if not rows.empty:
                styled = style_table(rows, _formats(rows, task), caption=f"{tag}: {caption}")
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


def _correlation_view(correlation: pd.DataFrame, ranking: pd.DataFrame) -> list:
    """The association heatmap of the key features and the candidates they represent, the method
    on hover; a name without a compared pair among them is left out and counted."""
    keys = ranking.loc[ranking["key_feature"] != "", "feature"].tolist()
    names = keys + ranking.loc[ranking["represented_by"] != "", "feature"].tolist()
    inside = correlation["a"].isin(names) & correlation["b"].isin(names)
    pairs = correlation.loc[inside & correlation["statistic"].notna()]
    compared = [name for name in names if name in set(pairs["a"]) | set(pairs["b"])]
    if len(compared) < 2:
        return [paragraph("Not available: fewer than two of the key features and the candidates "
                          "they represent have a compared pair.")]  # fmt: skip
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
        f"on a seeded cap of {PAIRWISE_ROWS:,} snapshot rows; the key features and the candidates "
        f"they represent: {len(compared)} shown, {len(names) - len(compared)} without a compared "
        "pair left out; blank: not compared"
    )
    return [charts.heatmap(matrix, hover, title=f"Association<br><sup>{note}</sup>")]


def _appendix_views(
    meta: dict, resolved: UseCaseConfig, ledger: pd.DataFrame, decisions: pd.DataFrame
) -> dict:
    """The kinds with the overrides, the ledger, the resolved config, the decisions, the collect
    log and the timings (the association's seconds within the statistics')."""
    overrides = resolved.features.kinds
    kinds = ledger[["feature", "kind", "lineage", "unsupported"]].assign(
        override=ledger["feature"].map(lambda name: overrides.get(name, ""))
    )
    collect = pd.DataFrame(meta["collect"]).drop(columns="step")
    counts = dict.fromkeys(collect.columns.drop("frame"), COUNT)
    config = yaml.safe_dump(resolved.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
    times = meta["timings"]
    seconds = {**times["seconds"], "association (within statistics)": times["association_seconds"]}
    timings = pd.DataFrame({"phase": list(seconds), "seconds": list(seconds.values())})
    timed = (f"Seconds per phase; {times['cells_estimate']:,} cells estimated, "
             f"{times['numeric_null_masks']:,} distinct numeric null masks")  # fmt: skip
    return {
        "kinds": style_table(kinds, caption="Kinds from the schema; override: features.kinds"),
        "ledger": style_table(ledger, _formats(ledger, resolved.task), caption="The ledger"),
        "resolved_config": preformatted(config),
        "decisions": style_table(decisions, caption="The audit log's entries, replayed in order"),
        "collect": style_table(collect, counts, caption="Collected frames (bytes)"),
        "timings": style_table(timings, {"seconds": "{:.1f}"}, caption=timed),
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
    return list(views.items()) or [paragraph(f"Not available: {reason}.")]


def report_sections(views: dict) -> list[tuple[str, list]]:
    """The four parts in eda.md's order, each section's blocks from `views`."""
    return [
        ("Summary", [("Choices", [views["choices"]]), ("How to read", views["how_to_read"]),
                     ("Headline", [views["headline"]]), ("Warnings", [views["warnings"]])]),
        ("Core", [
            ("Funnel per window period", [views["funnel"]]),
            ("Target per period", views["target_per_period"]),
            ("Target by stratum", _nested(views["target_by_stratum"], "no strata.variables")),
            ("Univariate ranking",
             [views["ranking"], ("Excluded automatically", [views["excluded"]])]),
            ("Key features", _nested(views["deep_dives"], "no key feature")),
        ]),
        ("Extended", [
            ("Reference groups", _nested(views["reference_groups"], "no modelling filter")),
            ("Correlation overview", views["correlation"]),
        ]),
        ("Appendix", [
            ("Kinds", [views["kinds"]]), ("Feature ledger", [views["ledger"]]),
            ("Resolved config", [views["resolved_config"]]),
            ("Decisions", [views["decisions"]]), ("Collect log", [views["collect"]]),
            ("Timings", [views["timings"]]),
        ]),
    ]  # fmt: skip
