"""What Evaluation compares the model with (evaluation.md → Baselines; D-009, D-141 (e)).

`decision.baselines` names the forms. Two rank nothing and are one rate each: the
`population_base_rate` (the unsampled train split's rate, the `base` the skill scores are
measured against) and a `historic_predicted_rate` number. The others are scored like the
model, from one score column each, `baseline_<form>` (`baseline_columns`), which `add_baselines`
adds to the evaluation rows before scoring, so the scores table stores them: the
`single_feature`, a `previous_model` column and a `historic_predicted_rate` column. A null in
any of them scores lowest, `NULL_SCORE`, so it ranks like the single feature's null.

The single feature is chosen from the run's per-run ledger alone (`choose_single_feature`): the
highest train concordance among the numerics and the ordered categoricals, used in train's
direction, so nothing is computed on train and no test row is read (§4.4). `carried_columns`
names what the evaluation frames must carry for the baselines. `baseline_loss` decides up
front, from the form and a column's facts (`describe_baseline_columns`, one Spark aggregate),
which row loss a baseline's cells carry and which compared metrics it cannot fill, and why;
the caller and `compare_baselines` both read it. `compare_baselines` sets the model beside each
baseline at the decision's metric and the order metrics, on test and on validation; a cell a
baseline cannot fill reads "not available: reason", decided before any number (D-035), and a
value the part's rows leave undefined reads `UNDEFINED`, so a blank cell never stands for one.
Nothing passes or fails: the person who approves a promotion judges (D-032).

`choice`, as `carried_columns`, `baseline_columns` and `add_baselines` read it, holds `features`
(the bundle's, `load_bundle(…).features`) and `single_feature` (`choose_single_feature` on the
run's `read_run_ledger`, the `ledger` of `read_stage2_copy` and `run.json`'s
`training_settings["features.order"]`; None when no feature qualifies).
"""

import numpy as np
import pandas as pd
from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import NumericType

from core_modelling.config import UseCaseConfig
from core_modelling.config.schema import DEVIANCE_METRICS
from core_modelling.evaluation.cells import scorer_loss
from core_modelling.evaluation.scores import BASELINE_PREFIX
from core_modelling.evaluation.tables import pooled_metrics
from core_modelling.model.encoder import CLIP, ENCODER_SCHEMA_VERSION, encode_frame
from core_modelling.statistics.metrics import NAN
from core_modelling.statistics.score_cells import PARTS
from core_modelling.tasks import TASK_SPECS

NULL_SCORE = -2 * CLIP  # a null's baseline score: below every value, clipped to ±CLIP
COLUMN_FORMS = ("previous_model", "historic_predicted_rate")  # forms whose argument may be a column
FACTS = ("null_share", "min", "max")  # what `describe_baseline_columns` gives per column
MEAN_PREDICTION = "mean_prediction"  # the comparison's level row: a mean score, or a rate
COMPARISON_COLUMNS = ["scorer", "part", "metric", "value", "low", "high", "unavailable"]
RATE_ONLY = "not available: one rate for every row ranks nothing; it is compared on its rate"
RAW_FEATURE = "not available: a raw feature's values are no prediction"
NOT_CHOSEN = "not available: no numeric or ordered categorical feature has a train concordance"
UNDEFINED = "not available: undefined on this part's rows"  # a NaN no reason was declared for


def choose_single_feature(
    run_ledger: pd.DataFrame, stage2_ledger: pd.DataFrame, order: dict[str, list[str]]
) -> dict | None:
    """The single-feature baseline, from the ledgers alone: the per-run ledger's feature with
    the highest `train_concordance` (the direction taken out) among the numerics and the
    ordered categoricals, the ledger's first on a tie; None when none has a train concordance.

    The kind is the Stage 2 ledger's (`numeric`, `categorical`); a categorical is ordered when
    `order` (the run's `features.order`) names it. An unordered categorical has no order to
    score by and is never chosen. Returns `feature`, `kind` (`numeric` or `ordered`), `sign`
    (train's raw direction, ±1), `levels` (the declared order, lowest first; None for a numeric)
    and `train_concordance`.
    """
    kinds = stage2_ledger.set_index("feature")["kind"]
    missing = sorted(set(run_ledger["feature"]) - set(kinds.index))
    if missing:
        raise ValueError(f"choose_single_feature: the Stage 2 ledger has no row for {missing}")
    kind = run_ledger["feature"].map(kinds)
    ordered = (kind == "categorical") & run_ledger["feature"].isin(list(order))
    scorable = (kind == "numeric") | ordered
    known = run_ledger["train_concordance"].notna() & (run_ledger["train_sign"] != 0)
    usable = run_ledger.loc[scorable & known]
    if usable.empty:
        return None
    best = usable.iloc[int(np.argmax(usable["train_concordance"].to_numpy(dtype=float)))]
    name = best["feature"]
    return {
        "feature": name,
        "kind": "ordered" if kinds[name] == "categorical" else "numeric",
        "sign": int(best["train_sign"]),
        "levels": order.get(name),
        "train_concordance": float(best["train_concordance"]),
    }


def single_feature_warnings(
    cfg: UseCaseConfig, single: dict | None, run_ledger: pd.DataFrame
) -> list[dict]:
    """Evaluation's warnings on the single-feature baseline (`single`, `choose_single_feature`'s):
    configured but not chosen, or chosen with nulls on train, since it was chosen on the train
    rows where it is known while its nulls score lowest on every row. The share is the per-run
    ledger's `null_share` (the encoder's, on the train frame). Each is a `code`, its values and
    the `text`."""
    configured = "single_feature" in cfg.decision.baselines
    if configured and single is None:
        return [{"code": "single_feature_baseline_not_chosen",
                 "text": f"the single-feature baseline is {NOT_CHOSEN}"}]  # fmt: skip
    if single is None:
        return []
    name = single["feature"]
    share = float(run_ledger.set_index("feature").loc[name, "null_share"])
    if not share > 0:
        return []
    text = (f"the single-feature baseline {name} was chosen on the train rows where it is "
            f"known; it is null on {share:.1%} of train rows and nulls score lowest, so the "
            "baseline may be weaker than it looks")  # fmt: skip
    return [{"code": "single_feature_baseline_has_nulls", "feature": name,
             "train_null_share": share, "text": text}]  # fmt: skip


def _forms(cfg: UseCaseConfig) -> dict[str, str | float | None]:
    """`decision.baselines` by form (each named once, checked at load), with its argument: a
    column or a number; None for `population_base_rate` and `single_feature`."""
    forms: dict[str, str | float | None] = {}
    for entry in cfg.decision.baselines:
        dumped = {entry: None} if isinstance(entry, str) else entry.model_dump()
        forms.update(dumped)
    return forms


def _column_forms(cfg: UseCaseConfig) -> dict[str, str]:
    """The column baselines, form → column: a `previous_model`, a `historic_predicted_rate`
    given as a column."""
    forms = _forms(cfg).items()
    return {form: arg for form, arg in forms if form in COLUMN_FORMS and isinstance(arg, str)}


def _source_columns(cfg: UseCaseConfig, choice: dict) -> dict[str, str]:
    """Each ranking baseline's form → the column its score reads: the chosen single feature
    (none when no feature qualified), then the column baselines."""
    columns = {}
    if "single_feature" in _forms(cfg) and choice["single_feature"] is not None:
        columns["single_feature"] = choice["single_feature"]["feature"]
    return {**columns, **_column_forms(cfg)}


def baseline_columns(cfg: UseCaseConfig, choice: dict) -> dict[str, str]:
    """The score columns `add_baselines` adds, form → `baseline_<form>`: what `score_parts`
    keeps and each baseline's `score_cells(…, column=…)`."""
    return {form: f"{BASELINE_PREFIX}{form}" for form in _source_columns(cfg, choice)}


def carried_columns(cfg: UseCaseConfig, choice: dict) -> list[str]:
    """What `build_frames(…, "evaluation", carry=…)` must carry for the baselines: each ranking
    baseline's source column that the bundle's features lack, each once."""
    columns = dict.fromkeys(_source_columns(cfg, choice).values())
    return [name for name in columns if name not in choice["features"]]


def _known(column: Column) -> Column:
    """The column as a double, a NaN as null."""
    number = column.cast("double")
    return F.nanvl(number, F.lit(None).cast("double"))


def describe_baseline_columns(rows: DataFrame, cfg: UseCaseConfig) -> dict[str, dict[str, float]]:
    """Each column baseline's facts by form (`FACTS`), from one Spark aggregate over the
    evaluation rows before `add_baselines` replaces the columns: `null_share` (the rows null or
    NaN in it) and the `min` and `max` of its known values (NaN when it has none). A column the
    rows lack or that is not numeric fails loud before Spark runs; without a column baseline,
    nothing runs."""
    columns = _column_forms(cfg)
    if not columns:
        return {}
    wrong = [n for n in columns.values() if n not in rows.columns
             or not isinstance(rows.schema[n].dataType, NumericType)]  # fmt: skip
    if wrong:
        raise ValueError(
            f"the baseline columns {wrong} are not numeric columns of the evaluation rows; carry "
            "them (`carried_columns`) and give them as numbers"
        )
    aggregates = []
    for name in columns.values():
        value = _known(F.col(name))
        aggregates += [F.avg(value.isNull().cast("double")), F.min(value), F.max(value)]
    found = rows.agg(*aggregates).first()
    if found[0] is None:
        raise ValueError("describe_baseline_columns: the evaluation rows are empty")
    numbers = [NAN if value is None else float(value) for value in found]
    return {
        form: dict(zip(FACTS, numbers[i * len(FACTS) : (i + 1) * len(FACTS)], strict=True))
        for i, form in enumerate(columns)
    }


def add_baselines(rows: DataFrame, cfg: UseCaseConfig, choice: dict) -> DataFrame:
    """The evaluation rows with one score column per ranking baseline (`baseline_columns`): the
    single feature as `_single_feature_score` gives it, a column baseline's values as
    doubles, a null or NaN at `NULL_SCORE`. Rows already holding a column of those names (a
    feature, stratum or carried column) are refused. The carried columns are dropped once read,
    unless a stratum: `score_parts` refuses any column that is no key, stratum, baseline or
    feature of the bundle."""
    added = baseline_columns(cfg, choice)
    clashing = sorted(set(added.values()) & set(rows.columns))
    if clashing:
        raise ValueError(
            f"the evaluation rows hold {clashing}, the names of the baseline score columns; "
            "rename that feature, stratum or column upstream"
        )
    scores = {
        added[form]: (
            _single_feature_score(choice["single_feature"])
            if form == "single_feature"
            else F.coalesce(_known(F.col(column)), F.lit(NULL_SCORE))
        )
        for form, column in _source_columns(cfg, choice).items()
    }
    dropped = [name for name in carried_columns(cfg, choice) if name not in cfg.strata.variables]
    return rows.select("*", *[score.alias(name) for name, score in scores.items()]).drop(*dropped)


def _ordered_position(column: Column, levels: list[str]) -> Column:
    """An ordered categorical's position in `levels` as the encoder codes it (`encode_frame`:
    the value's level text, so a level held as the double 3.0 is `3`), NaN for a null or an
    undeclared level; a pandas UDF, since the level text is Python's (`level_text`)."""
    entry = {"name": "value", "kind": "ordered", "levels": list(levels)}
    encoder = {"schema_version": ENCODER_SCHEMA_VERSION, "unordered": "codes", "features": [entry]}

    def position(values: pd.Series) -> pd.Series:
        """One batch's positions."""
        return encode_frame(values.to_frame("value"), encoder)[0]["value"]

    return F.pandas_udf(position, "double")(column)


def _single_feature_score(choice: dict) -> Column:
    """The single feature as a score in train's direction: `sign ·` a numeric's value clipped
    to ±`CLIP` as the encoder clips it, or an ordered categorical's position in its declared
    order (`_ordered_position`). A null, a NaN and an undeclared level take `NULL_SCORE`, below
    every value."""
    column = F.col(choice["feature"])
    if choice["kind"] == "ordered":
        value = _known(_ordered_position(column, choice["levels"]))
    else:
        # `greatest` and `least` skip a null, so the clip alone would score a null at ±CLIP
        known = _known(column)
        value = F.when(known.isNotNull(), F.least(F.greatest(known, F.lit(-CLIP)), F.lit(CLIP)))
    return F.coalesce(F.lit(float(choice["sign"])) * value, F.lit(NULL_SCORE))


def _labels(cfg: UseCaseConfig) -> list[str]:
    """The compared metrics: the decision's, the task's other order metrics and
    `mean_prediction`."""
    order = TASK_SPECS[cfg.task]["order_metrics"]
    return [cfg.decision.metric, *[n for n in order if n != cfg.decision.metric], MEAN_PREDICTION]


def baseline_loss(
    form: str, cfg: UseCaseConfig, facts: dict[str, float] | None, objective: str
) -> tuple[str | None, dict[str, str]]:
    """The row loss the cells of baseline `form` carry, for `score_cells(…, loss=…)` and
    `metric_rows(…, loss=…)`, and each compared metric (`_labels`) it cannot fill with its
    reason, decided up front from the form and, for a column baseline, its `facts`
    (`describe_baseline_columns`); `objective` is the run's (`scorer_loss`).

    A rate fills only `mean_prediction`; the single feature only the order metrics (no loss); a
    column with nulls ranks (a null lowest) but fills no other metric (no loss); a column
    outside the task's `prediction_range` is no prediction (no loss, only the order metrics);
    a deviance needs a positive prediction (no loss, the deviance not filled); else the
    model's loss (`scorer_loss`) and every metric.
    """
    labels = _labels(cfg)
    level = [label for label in labels if label not in TASK_SPECS[cfg.task]["order_metrics"]]
    column = _column_forms(cfg).get(form)
    if form == "single_feature":
        return None, dict.fromkeys(level, RAW_FEATURE)
    if column is None:
        return None, {label: RATE_ONLY for label in labels if label != MEAN_PREDICTION}
    if facts is None:
        raise ValueError(f"baseline_loss: the column baseline {form!r} needs its facts")
    loss, share = scorer_loss(cfg, objective), facts["null_share"]
    low, high = facts["min"], facts["max"]
    bounds = TASK_SPECS[cfg.task]["prediction_range"]
    if share > 0:
        return None, dict.fromkeys(level, f"not available: `{column}` has nulls ({share:.1%})")
    if bounds is not None and not bounds[0] <= low <= high <= bounds[1]:
        reason = (f"not available: `{column}` runs from {low:g} to {high:g}, outside "
                  f"[{bounds[0]:g}, {bounds[1]:g}]: no prediction of this task")  # fmt: skip
        return None, dict.fromkeys(level, reason)
    if loss in DEVIANCE_METRICS and not low > 0:  # a deviance needs a prediction > 0
        reason = f"not available: a deviance needs a positive prediction; `{column}` is {low:g}"
        return None, {label: reason for label in labels if label == loss}
    return loss, {}


def compare_baselines(
    metrics: dict[str, pd.DataFrame | None],
    cfg: UseCaseConfig,
    base: float,
    facts: dict[str, dict[str, float]],
    objective: str,
) -> pd.DataFrame:
    """The model beside each baseline of `decision.baselines`, on test and on validation, from
    each scorer's pooled metric rows; no pass or fail.

    `metrics` holds each scorer's metric rows (`metric_rows`, as `metric_tables` gives the
    model's): `model`, and each ranking baseline by its form (`single_feature`,
    `previous_model`, `historic_predicted_rate` with a column); `single_feature` is None when
    `choose_single_feature` found none. `base` is the
    unsampled train split's rate, the `population_base_rate`'s; `facts` the column baselines'
    (`describe_baseline_columns`); `objective` the run's. Returns one row per scorer, part and
    metric (`COMPARISON_COLUMNS`): the scorers `model`, the forms in config order and `observed`
    (the part's observed rate or mean, beside the mean predictions); the metrics `_labels`. A
    cell a form cannot fill is NaN with its reason (`baseline_loss`, or `NOT_CHOSEN`); a value
    that is not finite with no reason declared reads `UNDEFINED`: a cell is available only with
    no reason and a finite value.
    """
    forms = _forms(cfg)
    _check_scorers(metrics, forms)
    labels = _labels(cfg)
    keys = {**TASK_SPECS[cfg.task]["metric_keys"], MEAN_PREDICTION: "mean_score"}
    model = _pooled(metrics["model"])
    rows = _comparison_rows("model", model, labels, {}, None, keys)
    for form, argument in forms.items():
        table = metrics.get(form)
        _, reasons = baseline_loss(form, cfg, facts.get(form), objective)
        if form == "single_feature" and table is None:
            reasons = dict.fromkeys(labels, NOT_CHOSEN)
        rate = base if form == "population_base_rate" else argument
        rate = None if isinstance(rate, str) else rate  # a column ranks, it is no rate
        pooled = None if table is None else _pooled(table)
        rows += _comparison_rows(form, pooled, labels, reasons, rate, keys)
    for part in PARTS:
        value, low, high = model.loc[(part, "mean_target")]
        rows.append(dict(zip(COMPARISON_COLUMNS, ["observed", part, MEAN_PREDICTION, value, low,
                                                  high, ""], strict=True)))  # fmt: skip
    table = pd.DataFrame(rows, columns=COMPARISON_COLUMNS)
    undefined = table["unavailable"].eq("") & ~np.isfinite(table["value"].to_numpy(dtype=float))
    return table.assign(unavailable=table["unavailable"].mask(undefined, UNDEFINED))


def _check_scorers(metrics: dict[str, pd.DataFrame | None], forms: dict) -> None:
    """Fail loud unless `metrics` holds the model's table and exactly the ranking forms' (a
    column form's never None): a rate form has no table, and a missing one is never read as
    "not chosen"."""
    ranking = {"single_feature"} & set(forms)
    ranking |= {form for form in COLUMN_FORMS if isinstance(forms.get(form), str)}
    expected = {"model", *ranking}
    unset = [form for form in COLUMN_FORMS if form in metrics and metrics[form] is None]
    if set(metrics) != expected or metrics.get("model") is None or unset:
        raise ValueError(
            f"compare_baselines: metrics holds {sorted(metrics)}; it needs a table for `model` "
            f"and each ranking baseline {sorted(ranking)} (single_feature None when none was "
            "chosen)"
        )


def _pooled(table: pd.DataFrame) -> pd.DataFrame:
    """A scorer's pooled rows of test and validation without strata, by part and metric:
    `value, low, high`."""
    pooled = pooled_metrics(table)
    pooled = pooled.loc[pooled["part"].isin(PARTS)]
    return pooled.set_index(["part", "metric"])[["value", "low", "high"]]


def _comparison_rows(
    scorer: str,
    table: pd.DataFrame | None,
    labels: list[str],
    reasons: dict[str, str],
    rate: float | None,
    keys: dict[str, str],
) -> list[dict]:
    """One scorer's rows per part and metric label: NaN with the label's reason when `reasons`
    gives one, else `rate` (a rate form's, no interval) or the value and interval of `table`
    under the label's key in the cell metrics (`keys`, else the label itself)."""
    rows = []
    for part in PARTS:
        for label in labels:
            why = reasons.get(label, "")
            value, low, high = NAN, NAN, NAN
            if not why and rate is not None:
                value = float(rate)
            elif not why:
                value, low, high = table.loc[(part, keys.get(label, label))]
            rows.append(dict(zip(COMPARISON_COLUMNS, [scorer, part, label, value, low, high, why],
                                 strict=True)))  # fmt: skip
    return rows
