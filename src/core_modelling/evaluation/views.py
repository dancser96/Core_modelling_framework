"""The model results report's own core and extended views: the metrics, the curves and the
calibration, the strata, Training's sign-off and search, the thresholds and validation on test
clients only (docs/components/reporting.md "The model results report"); the summary is
`views_summary.py`'s.

Each view is `(tables, meta, resolved) -> list` of blocks, read from Evaluation's stored tables,
its meta (`evaluation.json`) and the resolved config only; views 12 and 13 read Training's
`signoff` and `trials`, which `run_evaluation` stores among Evaluation's tables as
`TRAINING_SIGNOFF` and `TRAINING_TRIALS`. A value prints with its client-bootstrap interval in
one cell (`interval_text`), a reason where a cell is not available, and a row below
`strata.min_events` greyed, never hidden. The explanation views are `views_explain.py`'s; the
compatibility table and the page are `report.py`'s.
"""

from collections.abc import Callable
from functools import partial

import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.evaluation.explain import curve_at_depths
from core_modelling.evaluation.tables import (
    CAPTURE_DEPTHS,
    VALIDATION_TEST_CLIENTS,
    metric_key,
    pooled_metrics,
)
from core_modelling.reporting.formats import COUNT, SHARE, plain_number
from core_modelling.reporting.html import paragraph, style_table
from core_modelling.reporting.model_charts import (
    capture_chart,
    metric_lines,
    pr_chart,
    predicted_vs_observed,
    reliability_chart,
    roc_chart,
    score_distribution,
)
from core_modelling.statistics.score_cells import MEAN, PARTS, POOLED
from core_modelling.tasks import TASK_SPECS
from core_modelling.training.ledger_run import SECTIONS
from core_modelling.training.views import search_progress_chart, search_table, signoff_view

View = Callable[[dict[str, pd.DataFrame], dict, UseCaseConfig], list]
Format = str | Callable[[float], str]
TRAINING_SIGNOFF = "training_signoff"  # Training's `signoff` table, among Evaluation's tables
TRAINING_TRIALS = "training_trials"  # Training's `trials` table, among Evaluation's tables
HIDDEN_METRICS = ("mean_score", "mean_target")  # the baselines' inputs, not metrics to read
REFERENCES = {"roc_auc": 0.5, "concordance": 0.5}  # read around chance: the data's span
SUPPORT_FORMATS = {"rows": COUNT, "events": COUNT}
# Per task: the calibration chart, the metrics beside it, the events below which a note warns
# that the groups are noisy, the error metrics per stratum level, what the `events` column counts
# (the greying's support), the clause on how train's and test's ordering metric are computed, the
# strata note's sentence on its coarser score bins (binary only: `STRATA_STEP`) and the summary's
# statement only the task needs (None: none).
VIEWS_BY_TASK = {
    "binary": {
        "calibration_chart": partial(reliability_chart,
                                     axis_format=TASK_SPECS["binary"]["axis_format"]),
        "calibration_metrics": ["observed_to_expected", "calibration_slope",
                                "calibration_intercept"],
        "note_below_events": 200,
        "strata_metrics": ["roc_auc", "observed_to_expected"],
        "events": "positive rows",
        "gap_clause": None,
        "strata_clause": " A level's metrics are computed on coarser score bins than the pooled "
                         "ones (every fourth edge), so a level's ordering metrics read slightly "
                         "below what the pooled grid would give.",
        "statement": "Average precision moves with the base rate: it is not comparable across "
                     "use cases.",
    },
    "regression": {
        "calibration_chart": predicted_vs_observed,
        "calibration_metrics": ["predicted_to_observed"],
        "note_below_events": None,
        "strata_metrics": ["rmse", "mae", "predicted_to_observed"],
        "events": "rows with a non-zero target",
        "gap_clause": "train's is computed on rows, test's on score cells, which reads up to "
                      "about 0.01 higher, so a test value above train's is no finding",
        "strata_clause": "",  # a regression's levels keep the pooled grid
        "statement": None,
    },
}  # fmt: skip


def interval_text(
    value: float, low: float, high: float, number_format: Format = plain_number
) -> str:
    """A value with its interval as one cell, `0.7793 (0.7313 to 0.8293)`; `0.7793 (no
    interval)` when the interval is NaN (the metric was undefined in at least one bootstrap
    replicate); `undefined` without a value."""
    if pd.isna(value):
        return "undefined"

    def shown(x: float) -> str:
        """One number in `number_format`."""
        return number_format(x) if callable(number_format) else number_format.format(x)

    if pd.isna(low) or pd.isna(high):
        return f"{shown(value)} (no interval)"
    return f"{shown(value)} ({shown(low)} to {shown(high)})"


def interval_texts(
    df: pd.DataFrame, column: str, number_format: Format = plain_number
) -> list[str]:
    """`interval_text` per row of `column` and its `<column>_low`, `<column>_high` (`value`'s are
    `low` and `high`)."""
    low, high = ("low", "high") if column == "value" else (f"{column}_low", f"{column}_high")
    return [interval_text(v, lo, hi, number_format)
            for v, lo, hi in zip(df[column], df[low], df[high], strict=True)]  # fmt: skip


def labelled_metrics(rows: pd.DataFrame, row_loss: str | None) -> pd.DataFrame:
    """`rows` with the metric `deviance` named by the loss the cells carry (`meta["row_loss"]`,
    e.g. `tweedie_deviance`); without a row loss the run has no deviance, so its rows are
    dropped."""
    if row_loss is None:
        return rows.loc[rows["metric"] != "deviance"]
    return rows.assign(metric=rows["metric"].replace({"deviance": row_loss}))


def wide_metrics(rows: pd.DataFrame, index: list[str]) -> tuple[pd.DataFrame, pd.Series]:
    """Long metric rows (`tables.METRIC_COLUMNS`) as one row per `index` value, in the rows'
    order: `index`, `rows`, `events`, then one column per metric in the rows' order, holding
    its value and interval as text (`HIDDEN_METRICS` left out). Returns the table and each
    row's `insufficient` flag."""
    shown = rows.loc[~rows["metric"].isin(HIDDEN_METRICS)]
    names = list(dict.fromkeys(shown["metric"]))
    texts = shown.assign(text=interval_texts(shown, "value"))
    values = texts.pivot(index=index, columns="metric", values="text")
    support = shown.drop_duplicates(index)[[*index, "rows", "events", "insufficient"]]
    table = support.merge(values[names].reset_index(), on=index, how="left")
    return table.drop(columns="insufficient"), table["insufficient"].astype(bool)


def _shown_parts(table: pd.DataFrame) -> pd.DataFrame:
    """The rows of `PARTS` (test and validation); validation on test clients only has its own
    view."""
    return table.loc[table["part"].isin(PARTS)].reset_index(drop=True)


def _plain_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    """The metric rows without a stratum."""
    return metrics.loc[metrics["stratum"].isna()]


def _period_rows(plain: pd.DataFrame) -> pd.DataFrame:
    """The plain metric rows of `PARTS` in the metrics view's order: each part's periods in time
    order (validation's one period after test's), then test pooled, then the periods' mean last.
    Validation's pooled row repeats its one period and is left out."""
    rows = _shown_parts(plain)
    rows = rows.loc[~((rows["part"] != PARTS[0]) & (rows["period"] == POOLED))]
    keys = pd.DataFrame({
        "scope": rows["period"].map({POOLED: 1, MEAN: 2}).fillna(0),
        "part": rows["part"].map({part: i for i, part in enumerate(PARTS)}),
        "period": rows["period"],
    })  # fmt: skip
    order = keys.sort_values(["scope", "part", "period"], kind="stable").index
    return rows.loc[order].reset_index(drop=True)


def metrics_view(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> list:
    """View 2: every metric per part and period with its interval, the validation period beside
    the window's, test pooled, the periods' mean last; the headline metric by period. A period
    below `strata.min_events` is greyed."""
    plain = _plain_metrics(tables["metrics"])
    rows = labelled_metrics(_period_rows(plain), meta["row_loss"])
    table, short_rows = wide_metrics(rows, ["part", "period"])
    caption = (
        f"Every metric per period, value (interval); greyed: fewer than "
        f"{resolved.strata.min_events} {VIEWS_BY_TASK[resolved.task]['events']} "
        "(strata.min_events)"
    )
    key = metric_key(resolved, resolved.decision.metric)
    timed = _shown_parts(plain).loc[lambda df: (df["metric"] == key) & (df["period"] != MEAN)]
    lines = metric_lines(timed, from_zero=key not in REFERENCES, reference=REFERENCES.get(key))
    return [style_table(table, SUPPORT_FORMATS, greyed=short_rows, caption=caption), lines]


def curves_view(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> list:
    """View 3: ROC and precision-recall, one line per part on all of the part's rows."""
    curves = _shown_parts(tables["curves"])
    return [roc_chart(curves), pr_chart(curves)]


def slice_table(slices: pd.DataFrame, task: str) -> pd.DataFrame:
    """One part's or several parts' slices (`tables.SLICE_COLUMNS`) for the capture view:
    `part, slice, declared` (a configured slice, else a fixed depth), the rows and the target
    captured, capture, the rate (regression: the mean) and lift, each with its interval as text,
    and why a slice is not available (its value cells left empty)."""
    spec = TASK_SPECS[task]
    table = pd.DataFrame({
        "part": slices["part"], "slice": slices["slice"], "declared": slices["configured"],
        "rows": slices["rows"], spec["capture_noun"]: slices["target"],
        "capture": interval_texts(slices, "capture", SHARE),
        spec["estimate_noun"]: interval_texts(slices, "rate", spec["estimate_format"]),
        "lift": interval_texts(slices, "lift", "{:.2f}"), "unavailable": slices["unavailable"],
    }).reset_index(drop=True)  # fmt: skip
    absent = table["unavailable"].ne("").to_numpy()
    table.loc[absent, ["capture", spec["estimate_noun"], "lift"]] = ""
    return table


def capture_view(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> list:
    """View 4: the capture curve per part and the slices, the declared ones then the fixed
    depths, each cut inside each period and added up over the part's periods."""
    slices = tables["slices"]
    pooled = _shown_parts(slices.loc[slices["period"] == POOLED])
    table = slice_table(pooled, resolved.task)
    noun = TASK_SPECS[resolved.task]["capture_noun"]
    caption = (
        "The declared slices, then the depths 1 to 50%, each cut inside each period and added "
        "up over the part's periods; value (interval)"
    )
    formats = {"rows": COUNT, noun: COUNT}
    return [capture_chart(_shown_parts(tables["curves"])),
            style_table(table, formats, caption=caption)]  # fmt: skip


def reliability_view(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> list:
    """View 5: the score against the observed level in groups of the score (regression: the
    prediction), with the calibration metrics per part beside it; binary notes a part under 200
    events, whose groups are noisy."""
    spec = VIEWS_BY_TASK[resolved.task]
    pooled = pooled_metrics(tables["metrics"])
    pooled = _shown_parts(pooled.loc[pooled["metric"].isin(spec["calibration_metrics"])])
    table, _ = wide_metrics(pooled, ["part"])
    blocks = [spec["calibration_chart"](_shown_parts(tables["reliability"])),
              style_table(table, SUPPORT_FORMATS, caption="Calibration, pooled per part, "
                                                          "value (interval)")]  # fmt: skip
    floor = spec["note_below_events"]
    few = table.loc[table["events"] < floor, "part"].tolist() if floor else []
    if few:
        note = (
            f"Fewer than {floor} {spec['events']} on {', '.join(few)}: the groups are noisy; "
            "read the intervals, not the points."
        )
        blocks.append(paragraph(note))
    return blocks


def distribution_view(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> list:
    """View 6: the score's distribution per class, each to its own scale, one panel per part."""
    return [score_distribution(_shown_parts(tables["score_distribution"]))]


def strata_table(levels: pd.DataFrame, composition: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """One stratum variable's table: per part and level (levels by rows, largest first) the
    support and the task's metrics (`wide_metrics` of `levels`, its metric rows), then the
    decision's slice, the level's share of the population and of the list, the capture inside
    it and why the list is not available (`composition`, its `strata` rows). Returns the table
    and each row's `insufficient` flag."""
    table, short_rows = wide_metrics(levels, ["part", "level"])
    columns = ["part", "level", "slice", "population_share", "list_share", "capture", "unavailable"]
    return table.merge(composition[columns], on=["part", "level"], how="left"), short_rows


def strata_view(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> list:
    """View 7: per stratum variable and level the support, the task's metrics and the list's
    composition at the decision's slice; a level below `strata.min_events` greyed."""
    variables = resolved.strata.variables
    if not variables:
        return [paragraph("No strata variables are configured (strata.variables).")]
    metrics, composition = tables["metrics"], tables["strata"]
    chosen = metrics["metric"].isin(VIEWS_BY_TASK[resolved.task]["strata_metrics"])
    formats = {**SUPPORT_FORMATS, "population_share": SHARE, "list_share": SHARE, "capture": SHARE}
    events, clause = (VIEWS_BY_TASK[resolved.task][key] for key in ("events", "strata_clause"))
    blocks: list = [paragraph(
        "No tests across levels: many levels read together will show some differences by chance. "
        f"Greyed: fewer than {resolved.strata.min_events} {events} (strata.min_events).{clause}"
    )]  # fmt: skip
    for variable in variables:
        levels = metrics.loc[chosen & (metrics["stratum"] == variable)]
        table, short_rows = strata_table(
            levels, composition.loc[composition["stratum"] == variable]
        )
        caption = (
            f"{variable}: per part and level, value (interval); the list at the decision's slice"
        )
        blocks.append((variable, [style_table(table, formats, greyed=short_rows, caption=caption)]))
    return blocks


def sign_off_view(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> list:
    """View 12: Training's sign-off view, train-only: the final list by out-of-fold contribution,
    the held and the excluded features with their reasons, the wrong-sign warnings."""
    view = signoff_view(tables[TRAINING_SIGNOFF], None)
    note = paragraph("Train-only evidence: the contributions are out of fold on train clients. "
                     "A person signs off this list before the model is registered.")  # fmt: skip
    sections = [view["sections"][section] for section in SECTIONS]
    return [note, *sections, ("Wrong-sign warnings", [view["warnings"]])]


def search_view(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> list:
    """View 13: the search per family, the best fold metric so far against cumulative seconds,
    and Training's seconds per step."""
    metric, trials = resolved.decision.metric, tables[TRAINING_TRIALS]
    seconds = meta["training_seconds"]
    steps = pd.DataFrame({"step": list(seconds), "seconds": list(seconds.values())})
    return [
        search_table(trials, metric),
        search_progress_chart(trials, metric),
        style_table(steps, {"seconds": "{:.1f}"}, caption="Training's seconds per step"),
    ]


def threshold_rows(curves: pd.DataFrame, depths: tuple[float, ...]) -> pd.DataFrame:
    """Per part (in the table's order), the curve's row at each depth: the first score bin from
    the top whose cumulative share of rows reaches it, each bin once. Same columns as `curves`
    (`statistics.metrics.threshold_table` with `part`)."""
    parts = curves.groupby("part", sort=False)
    return pd.concat([curve_at_depths(curve, depths) for _, curve in parts], ignore_index=True)


def thresholds_view(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> list:
    """View 14: the list's numbers at the score thresholds that reach the capture depths: what a
    threshold decision would take."""
    rows = threshold_rows(_shown_parts(tables["curves"]), CAPTURE_DEPTHS)
    spec = TASK_SPECS[resolved.task]
    columns = ["part", "threshold", "depth", "rows", "target", "capture", "rate", "lift",
               "false_positive_rate"]  # fmt: skip
    formats = {"threshold": plain_number, "depth": SHARE, "rows": COUNT, "target": COUNT,
               "capture": SHARE, "rate": spec["estimate_format"], "lift": "{:.2f}",
               "false_positive_rate": SHARE}  # fmt: skip
    depths = ", ".join(f"{depth:.0%}" for depth in CAPTURE_DEPTHS)
    caption = (
        f"The rows at or above each score threshold, taken where the list first reaches {depths} "
        f"of the part; target: the {spec['capture_noun']} captured"
    )
    return [style_table(rows[columns], formats, caption=caption)]


def validation_clients_view(
    tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig
) -> list:
    """View 17: the validation period's metrics on its test-split clients only, beside all of
    its clients: unseen clients and an unseen period."""
    pooled = pooled_metrics(tables["metrics"])
    rows = pooled.loc[pooled["part"].isin(["validation", VALIDATION_TEST_CLIENTS])]
    table, short_rows = wide_metrics(labelled_metrics(rows, meta["row_loss"]), ["part"])
    caption = (
        "The validation period, all of its clients and its test-split clients only, value "
        "(interval); a train client's earlier periods were fitted on"
    )
    return [style_table(table, SUPPORT_FORMATS, greyed=short_rows, caption=caption)]
