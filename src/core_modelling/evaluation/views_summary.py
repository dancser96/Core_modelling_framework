"""The model results report's summary, view 1 (docs/components/reporting.md "The model results
report", evaluation.md "What the report states").

`summary_view` states what was evaluated and chosen (D-032), the headline numbers with their
intervals, the model beside each baseline (no pass or fail), the how-to-read notes, what the
numbers cannot say on their own and the warnings. Like every view it reads Evaluation's stored
tables, its meta and the resolved config only.
"""

from html import escape

import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.config.identities import short
from core_modelling.config.schema import Baseline
from core_modelling.evaluation.tables import headline_names, metric_key, pooled_metrics
from core_modelling.evaluation.views import (
    VIEWS_BY_TASK,
    interval_text,
    interval_texts,
    labelled_metrics,
)
from core_modelling.reporting.blocks import choices_block, headline, identity_values, warnings_block
from core_modelling.reporting.formats import plain_number
from core_modelling.reporting.html import paragraph, style_table
from core_modelling.statistics.score_cells import PARTS
from core_modelling.tasks import TASK_SPECS

CHOICE_ROWS = ["automation_level", "task", "decision", "metric", "validation_period", "slices",
               "strata", "min_events", "replayed_to", "config_hash",
               "data_definition_hash"]  # fmt: skip


def _baseline_text(baseline: Baseline) -> str:
    """A baseline's form as the config writes it: its name, or `form: argument`."""
    if isinstance(baseline, str):
        return baseline
    return ", ".join(f"{form}: {argument}" for form, argument in baseline.model_dump().items())


def _settings_text(meta: dict, resolved: UseCaseConfig) -> str:
    """The choices the choices table has no row for: the baselines (the single feature when it
    is configured), the intervals and the explanation sample's cut."""
    baselines = resolved.decision.baselines
    text = f"Baselines: {', '.join(_baseline_text(b) for b in baselines)}."
    if "single_feature" in baselines:
        single = meta["choices"]["single_feature"]
        chosen = "not chosen" if single is None else f"{single['feature']} in train's direction"
        text += f" Single feature: {chosen}; a null takes the lowest score."
    intervals, cut = resolved.evaluation.intervals, meta["choices"]["explanation_cut"]
    return (
        f"{text} Intervals: {intervals.level:.0%} client bootstrap over {intervals.replicates} "
        f"replicates. The explanation sample's cut row is at the {cut['slice']} of test, score "
        f"{plain_number(cut['score'])}."
    )


def _opening(meta: dict, resolved: UseCaseConfig) -> str:
    """The report's first sentence: the run, its model and what it was scored on."""
    noun = TASK_SPECS[resolved.task]["estimate_noun"]
    return (
        f"Run {meta['run_id']} of {resolved.use_case} on {meta['entity']}, model "
        f"{short(meta['model_hash'])}: scored on the test clients over the observation window "
        f"and on the validation period {meta['validation_period']}. The skill scores are "
        f"measured against the unsampled train split's {noun}, {plain_number(meta['base'])}."
    )


def _how_to_read(resolved: UseCaseConfig) -> list[str]:
    """The five reading notes of a report that shows a concordance (reporting.md requirement
    8): concordance, lift, intervals, grey, null."""
    noun, intervals = TASK_SPECS[resolved.task]["estimate_noun"], resolved.evaluation.intervals
    notes = [
        "Concordance says how well the score orders clients by the target: 0.5 is no better "
        "than chance, 1 a perfect ordering. For a yes/no target it is the AUC.",
        f"Lift is a slice's {noun} divided by its part's {noun}: 1 is the part's level, 2 twice "
        "it.",
        f"Intervals are {intervals.level:.0%}, from a client bootstrap over "
        f"{intervals.replicates} replicates: a client's rows move together. They are written "
        "after each value, value (low to high), and drawn as error bars. A value reads "
        "undefined where the data leave the metric without one, and (no interval) follows it "
        "where the metric was undefined in at least one bootstrap replicate.",
        f"Grey means too little support, still shown: fewer than strata.min_events = "
        f"{resolved.strata.min_events} {VIEWS_BY_TASK[resolved.task]['events']} (the events "
        "column) in a period or a level. An outcome counts once in every period whose target "
        "window holds it, so a pooled row can count it up to the window's length in periods. "
        "Read the interval, not the point.",
        "null is a missing feature value: grey in the explanation charts, its own group last.",
    ]
    return [paragraph(note) for note in notes]


def _statements(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> str:
    """What the numbers cannot say on their own, as a list (evaluation.md "What the report
    states"): the optimism of Training's out-of-fold metric, the train-to-test gap, the labels
    Stage 2's decisions saw, validation's role, the periods earlier runs scored, the pooling
    note and the task's own statement (`VIEWS_BY_TASK`)."""
    training, clause = meta["training"], VIEWS_BY_TASK[resolved.task]["gap_clause"]
    order = TASK_SPECS[resolved.task]["order_metrics"][0]
    pooled = pooled_metrics(tables["metrics"]).set_index(["part", "metric"])["value"]
    earlier = sorted({entry["validation_period"] for entry in meta["earlier_validations"]})
    differs = tables["pooling"].loc[tables["pooling"]["differs"].astype(bool)]
    items = [
        f"Training's out-of-fold {training['metric']}, {plain_number(training['out_of_fold'])}, "
        "is optimistic: the features and the configuration were chosen on the same folds; test "
        "is the first honest number for those choices.",
        f"Train {order}, on the rows the model was fitted on, "
        f"{plain_number(training['in_sample_concordance'])}; test "
        f"{plain_number(pooled[('test', order)])}: the gap is how far the model fits its own rows"
        + (f"; {clause}." if clause else "."),
        "People's feature decisions in EDA and Feature Checks saw every eligible client, test "
        "labels included; the validation period, whose labels they never saw, is the one honest "
        "number.",
        "Validation is reported, never chosen on: when test chose among variants, the gap from "
        "test to validation mixes overfitting with selection.",
        f"Earlier Evaluation runs scored the validation periods {', '.join(earlier)}."
        if earlier else "No earlier Evaluation run scored a validation period.",
    ]  # fmt: skip
    if len(differs):
        items.append(
            f"The pooled and the per-period {', '.join(sorted(set(differs['metric'])))} differ "
            f"on {', '.join(sorted(set(differs['part'])))}: the base rate moved inside the "
            "window; read the values per period."
        )
    statement = VIEWS_BY_TASK[resolved.task]["statement"]
    items += [statement] if statement else []
    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"


def _headline_numbers(metrics: pd.DataFrame, meta: dict, resolved: UseCaseConfig) -> dict:
    """The run, its training date and each headline metric pooled per part with its interval,
    as text (`interval_text`)."""
    pooled = pooled_metrics(metrics).set_index(["part", "metric"])
    numbers: dict[str, object] = {"run": meta["run_id"], "trained": meta["trained_at"][:10]}
    for part in PARTS:
        for name in headline_names(resolved):
            row = pooled.loc[(part, metric_key(resolved, name))]
            numbers[f"{part}_{name}"] = interval_text(row["value"], row["low"], row["high"])
    return numbers


def baseline_table(baselines: pd.DataFrame) -> pd.DataFrame:
    """The baselines comparison (one row per scorer, part and metric) as one row per scorer and
    one column per part and metric, in the table's order: the value with its interval, or the
    reason a scorer cannot fill the cell."""
    reasons = baselines["unavailable"].fillna("")
    cells = [r or t for r, t in zip(reasons, interval_texts(baselines, "value"), strict=True)]
    long = baselines.assign(cell=cells, column=baselines["part"] + " " + baselines["metric"])
    wide = long.pivot(index="scorer", columns="column", values="cell")
    wide = wide.reindex(index=list(dict.fromkeys(long["scorer"])),
                        columns=list(dict.fromkeys(long["column"])))  # fmt: skip
    return wide.rename_axis(index=None, columns=None).reset_index(names="scorer")


def summary_view(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> list:
    """View 1: what was evaluated and chosen (D-032), the headline numbers with their intervals,
    the model beside each baseline, the reading notes, what the numbers cannot say and the
    warnings (each warning's `text`)."""
    numbers = _headline_numbers(tables["metrics"], meta, resolved)
    comparison = style_table(
        baseline_table(labelled_metrics(tables["baselines"], meta["row_loss"])),
        caption="The model beside each baseline, each value with its interval; no pass or fail",
    )
    return [
        paragraph(_opening(meta, resolved)),
        headline(numbers, dict.fromkeys(numbers, "{}")),
        ("Choices", [choices_block(resolved, CHOICE_ROWS, identity_values(meta)),
                     paragraph(_settings_text(meta, resolved))]),
        ("Baselines", [comparison]),
        ("How to read", _how_to_read(resolved)),
        ("What these numbers cannot say", [_statements(tables, meta, resolved)]),
        ("Warnings", [warnings_block([warning["text"] for warning in meta["warnings"]])]),
    ]  # fmt: skip
