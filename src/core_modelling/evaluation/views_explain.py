"""The model results report's six explanation views: importance, beeswarm, effects, waterfalls,
permutation importance and partial dependence (docs/components/reporting.md "The model results
report", views 8 to 11, 15 and 16).

Each view is a `View` of `evaluation/report.py`: it reads only Evaluation's stored tables, its
meta and the resolved config, and draws `reporting/explain_charts.py`'s charts, so the page
renders again from `evaluation/` without Spark. Beside Evaluation's own explanation tables
(`evaluation/explain.py`), the importance view reads Training's explanation sample, stored with
them (`TRAIN_SAMPLE`, train out of fold), and the effects view the effects table
(`evaluation/effects.py`: the mean contribution per EDA group beside EDA's lift). Every view
but the waterfalls reads the explanation sample's sampled rows only (`sampled_rows`), never the
hand-picked waterfall rows. The views only draw; nothing is chosen on these numbers (`CLAUDE.md`
§4.4).
"""

import pandas as pd
from pandas.io.formats.style import Styler

from core_modelling.config import UseCaseConfig
from core_modelling.config.schema import LOG_LINK_OBJECTIVES
from core_modelling.evaluation.effects import EFFECTS, MAX_EFFECTS, TOP_EFFECTS
from core_modelling.evaluation.explain import WATERFALL_COLUMN, sampled_rows
from core_modelling.evaluation.permutation import DISAGREEMENTS, PERMUTATIONS
from core_modelling.reporting.blocks import not_available
from core_modelling.reporting.explain_charts import (
    MIN_GROUP_ROWS,
    ROW_CAP,
    beeswarm,
    dependence,
    effect_chart,
    importance_bar,
    pdp_ice_chart,
    waterfall,
)
from core_modelling.reporting.formats import COUNT, SHARE, column_formats, plain_number
from core_modelling.reporting.html import paragraph, style_table
from core_modelling.run_artifacts import BASE_COLUMN, TRAIN_SAMPLE, sample_contributions
from core_modelling.tasks import TASK_SPECS

BEESWARM_TOP = 15
WATERFALL_TITLES = {
    "highest": "The highest score of test",
    "cut": "A row at the decision's cut",
    "typical": "A typical row: the sample's median score",
}


def _final_features(tables: dict[str, pd.DataFrame]) -> list[str]:
    """The model's final features, largest test contribution share first (the feature table)."""
    return tables["features"]["feature"].tolist()


def _scale_note(meta: dict, resolved: UseCaseConfig) -> str:
    """One line on the margin's scale the contributions are on, under the run's own objective
    (`meta["choices"]["objective"]`, from its `run.json`): a named run may have been trained
    under another than the evaluating config's."""
    spec, objective = TASK_SPECS[resolved.task], meta["choices"]["objective"]
    if spec["log_link_scale"] and objective in LOG_LINK_OBJECTIVES:
        scale = spec["log_link_scale"].format(objective=objective)
    else:
        scale = spec["margin_scale"]
    return paragraph(
        f"Contributions are the model library's own, on the margin's scale ({scale}), before "
        "calibration: a row's contributions and the base value sum to its margin."
    )


def importance_view(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> list:
    """View 8: each final feature's share of the mean absolute contribution, test beside train
    out of fold."""
    features = _final_features(tables)
    test = sample_contributions(sampled_rows(tables["contributions"]), features)
    train = sample_contributions(tables[TRAIN_SAMPLE], features)
    text = (
        f"Test: the {len(test):,} rows of Evaluation's explanation sample. Train, out of fold: "
        f"Training's explanation sample, {len(train):,} train rows, each explained by the fold "
        "model that did not see it. A feature far apart in the two is worth a look."
    )
    return [_scale_note(meta, resolved), paragraph(text), importance_bar(test, compare=train)]


def beeswarm_view(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> list:
    """View 9: the `BEESWARM_TOP` features' contributions, `ROW_CAP` seeded test rows at most."""
    sample, features = sampled_rows(tables["contributions"]), _final_features(tables)
    contributions = sample_contributions(sample, features)
    shown = min(ROW_CAP, len(sample))
    text = (
        f"{shown:,} of the explanation sample's {len(sample):,} test rows, seeded by "
        f"training.seed ({resolved.training.seed}), the same rows for every feature; a missing "
        "value is grey."
    )
    fig = beeswarm(contributions, sample[features], BEESWARM_TOP, shown, resolved.training.seed)
    return [_scale_note(meta, resolved), paragraph(text), fig]


def _left_out(rows: pd.DataFrame) -> str | None:
    """The line counting a feature's sample rows no EDA group covers, None when there is none."""
    null, level = int(rows["left_out_null"].iloc[0]), int(rows["left_out_level"].iloc[0])
    if not null and not level:
        return None
    return paragraph(
        f"Sample rows left out of the groups: {null:,} null where EDA's snapshot had no null "
        f"group, {level:,} with a level EDA's groups lack."
    )


def _level_table(rows: pd.DataFrame, task: str) -> Styler:
    """A categorical's levels in EDA's order: EDA's rows, estimate and lift beside the sample's
    rows and mean contribution, a level greyed when EDA's support is too little."""
    table = rows[["group", "eda_rows", "estimate", "lift", "sample_rows", "mean_contribution"]]
    formats = {**column_formats(table, task), "eda_rows": COUNT, "sample_rows": COUNT,
               "mean_contribution": "{:+.3f}"}  # fmt: skip
    caption = (
        f"{rows['feature'].iloc[0]} by level: EDA's rows, estimate and lift on its snapshot, the "
        "test sample's rows and mean contribution"
    )
    return style_table(table, formats, greyed=rows["insufficient"], caption=caption)


def _effect_blocks(tables: dict[str, pd.DataFrame], name: str, task: str) -> list:
    """One effect feature's blocks: its rows of the effects table drawn as the mean
    contribution per EDA group beside EDA's lift (a level table under a categorical), or, when
    its row says why EDA gives no lift (`unavailable`), the scatter with that reason. A feature
    without a row fails loud."""
    effects = tables[EFFECTS]
    rows = effects.loc[effects["feature"] == name].sort_values("group_order")
    if rows.empty:
        raise ValueError(f"the effects table has no row for the effect feature {name}")
    reason = rows["unavailable"].iloc[0]
    if reason:
        sample = sampled_rows(tables["contributions"])
        text = (
            f"No EDA lift beside {name} ({reason}): its contribution against its value, "
            f"{min(ROW_CAP, len(sample)):,} seeded sample rows at most."
        )
        contributions = sample_contributions(sample, [name])[name]
        return [paragraph(text), dependence(contributions, sample[name])]
    blocks: list = [effect_chart(rows.reset_index(drop=True))]
    left_out = _left_out(rows)
    if left_out is not None:
        blocks.append(left_out)
    if rows["kind"].iloc[0] == "categorical":
        blocks.append(_level_table(rows.reset_index(drop=True), task))
    return blocks


def effects_view(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> list:
    """View 10: per effect feature, the model's mean contribution per EDA group beside EDA's
    lift, or the contribution against the value where EDA has no groups."""
    names = meta["choices"]["effect_features"]
    if not names:
        return [paragraph("No effect feature: the model uses none.")]
    text = (
        f"The effect features: the model's {TOP_EFFECTS} largest by Training's out-of-fold "
        f"contribution share and EDA's key features it uses, {MAX_EFFECTS} at most. Left, the "
        "mean contribution of "
        f"the test sample's rows in each of EDA's groups, with its 95% interval, greyed under "
        f"{MIN_GROUP_ROWS} sample rows; right, EDA's lift by the same groups on its snapshot. "
        "The two should rise and fall together."
    )
    blocks: list = [_scale_note(meta, resolved), paragraph(text)]
    return blocks + [(name, _effect_blocks(tables, name, resolved.task)) for name in names]


def waterfalls_view(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> list:
    """View 11: the walk from the base value to the margin for the three marked rows: the
    highest score, the row at the decision's cut and a typical row."""
    sample, features = tables["contributions"], _final_features(tables)
    cut = meta["choices"]["explanation_cut"]
    blocks: list = [_scale_note(meta, resolved)]
    for which, title in WATERFALL_TITLES.items():
        marked = sample.loc[sample[WATERFALL_COLUMN] == which]
        if len(marked) != 1:
            raise ValueError(f"the explanation sample marks {len(marked)} {which!r} rows, not one")
        row = marked.iloc[0]
        contributions = sample_contributions(marked, features).iloc[0].astype(float)
        values = row[features]
        text = f"Score {plain_number(row['score'])}."
        if which == "cut":
            text += f" The cut: the {cut['slice']} of test, score {plain_number(cut['score'])}."
        chart = waterfall(contributions, float(row[BASE_COLUMN]), values)
        blocks.append((title, [paragraph(text), chart]))
    return blocks


def permutation_importance_view(
    tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig
) -> list:
    """View 15: per redundancy cluster, the loss change when its members are permuted together
    (the mean over the permutations, with their standard deviation), with the rank check against
    the contribution shares; the reason instead when `meta["unavailable"]` names the table."""
    reason = meta["unavailable"].get("permutation_importance")
    if reason is not None:
        return [not_available(reason)]
    table = tables["permutation_importance"].copy()
    table["members"] = table["members"].map(", ".join)
    correlation = table["rank_correlation"].iloc[0] if len(table) else None
    said = "undefined" if correlation is None or pd.isna(correlation) else f"{correlation:.2f}"
    columns = ["cluster", "members", "loss_change", "loss_change_sd", "importance_rank",
               "contribution_share", "contribution_rank", "rank_gap", "disagrees"]  # fmt: skip
    rows = meta["choices"]["permutation_rows"]
    caption = (
        f"Per redundancy cluster (Feature Checks'; a feature without one stands alone, cluster "
        f"empty): the change in the {resolved.decision.metric} loss when its members are "
        f"permuted together on the permutation sample of {rows:,} seeded test rows, the mean over "
        f"{PERMUTATIONS} permutations and their standard deviation, largest first, beside the "
        "cluster's contribution share on the explanation sample; disagrees marks the "
        f"{DISAGREEMENTS} largest rank gaps"
    )
    formats = {"loss_change": plain_number, "loss_change_sd": plain_number,
               "contribution_share": SHARE}  # fmt: skip
    text = (
        f"Spearman's rank correlation of the two orders: {said}. The standard deviation covers "
        f"the {PERMUTATIONS} permutations of the same rows only, not the draw of the rows: a "
        "loss change within it is noise, while one beyond it can still move on another sample."
    )
    return [paragraph(text), style_table(table[columns], formats, caption=caption)]


def pdp_ice_view(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> list:
    """View 16: partial dependence over the ICE lines for view 10's features, each one its table
    holds; the reason for the ones it leaves out when `meta["unavailable"]` names the table."""
    names, table = meta["choices"]["effect_features"], tables["partial_dependence"]
    if not names:
        return [paragraph("No effect feature: the model uses none.")]
    text = (
        "Each feature set in turn to every point of its grid on every sample row, the rest "
        "kept: the mean score (partial dependence) over a line per sampled row (ICE). Lines "
        "that cross say the feature acts through others."
    )
    blocks: list = [paragraph(text)]
    reason = meta["unavailable"].get("partial_dependence")
    if reason is not None:
        blocks.append(not_available(reason))
    y_format = TASK_SPECS[resolved.task]["axis_format"]
    drawn = [name for name in names if name in set(table["feature"])]
    return blocks + [pdp_ice_chart(table.loc[table["feature"] == name], y_format) for name in drawn]
