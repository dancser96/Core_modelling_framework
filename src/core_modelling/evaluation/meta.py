"""`evaluation.json`'s content and the stage result, assembled from what `run_evaluation` found,
scored and computed (evaluation.md → "What Evaluation writes").

`Opened` is the run as `run.py` found and read it; `build_result` turns it, the frames, the
tables and the choices made into the `StageResult` whose meta is `evaluation.json`, with the
run's warnings (`_warnings`, the only place they are written) and the report's views built
once. Nothing here reads data or runs Spark.
"""

from dataclasses import dataclass

import pandas as pd

from core_modelling.artifacts import StageResult, stage_identity
from core_modelling.config import UseCaseConfig
from core_modelling.config.replay import Entry
from core_modelling.dataset import Frames
from core_modelling.environment import EnvironmentConfig
from core_modelling.evaluation.baselines import single_feature_warnings
from core_modelling.evaluation.cells import scorer_loss
from core_modelling.evaluation.drift_reference import DRIFT_REFERENCE_SCHEMA_VERSION
from core_modelling.evaluation.report import report_views
from core_modelling.evaluation.tables import headline_names, metric_key, pooled_metrics
from core_modelling.periods import period_spec
from core_modelling.run_artifacts import RunFolder
from core_modelling.statistics.score_cells import PARTS


@dataclass
class Opened:
    """A run found and read: the resolved config, the audit log's entries, the run number and
    folder, the newer runs `find_run` passed over (`"r007: reason, reason"`, empty for the
    newest or a named run), the run folder as `check_card_inputs` read it (`read`), Training's
    tables the report draws (`CARRIED_TABLES`), the run's `training.objective` (from
    `run.json`: a named run may have been trained under another config than the evaluating
    one), the unsampled train level (`base`) and what the baselines read (`choice`: the
    bundle's `features` and the chosen `single_feature`)."""

    resolved: UseCaseConfig
    entries: list[Entry]
    run: str
    passed_over: list[str]
    folder: str
    read: RunFolder
    trained: dict[str, pd.DataFrame]
    objective: str
    base: float
    choice: dict


def build_result(
    opened: Opened,
    frames: Frames,
    tables: dict[str, pd.DataFrame],
    decided: dict,
    in_sample: float | None,
    env: EnvironmentConfig,
    seconds: dict[str, float],
) -> StageResult:
    """The stage result, writing nothing: `evaluation.json`'s content, its keys as evaluation.md
    → "What Evaluation writes" lists them, and the report's views, built once here. `decided`
    holds the explanation's `choices` and `unavailable`; `in_sample` is train's in-sample
    concordance on test's cells (None for a 0/1 target); `seconds` the stage's laps, which the
    caller goes on filling."""
    resolved, training = opened.resolved, opened.read.training
    label = period_spec(resolved).label(resolved.time.validation_period)
    meta = {
        **stage_identity(resolved, "evaluation", env),
        "run_id": opened.run,
        "training_config_hash": opened.read.run["config_hash"],
        "model_hash": opened.read.bundle.model_hash,
        "row_loss": scorer_loss(resolved, opened.objective),
        "validation_period": label,
        "summary": _summary(tables["metrics"], resolved, label),
        "base": opened.base,
        "eligible_rows": frames.meta["eligible_rows"],
        "choices": {
            "headline": headline_names(resolved),
            "objective": opened.objective,
            "single_feature": opened.choice["single_feature"],
            **decided["choices"],
        },
        "unavailable": decided["unavailable"],
        "in_sample_concordance_cells": in_sample,
        "training": training["metrics"],
        "training_warnings": training["warnings"],
        "trained_at": training["written_at"],
        "training_seconds": training["timings"]["seconds"],
        "earlier_validations": _earlier_validations(opened.entries),
        "drift_reference_schema_version": DRIFT_REFERENCE_SCHEMA_VERSION,
        "warnings": _warnings(opened, tables["features"], decided["choices"]["explanation_cut"]),
        "timings": {"seconds": seconds},
    }
    views = report_views(tables, meta, resolved)
    return StageResult(tables=tables, ledger=opened.read.run_ledger, log=frames.log, meta=meta,
                       paths={}, views=views, frame=None, config=resolved)  # fmt: skip


def _summary(metrics: pd.DataFrame, cfg: UseCaseConfig, label: str) -> dict:
    """`evaluation.json`'s flat `summary`, which `list_runs` and `show_run` display: the scored
    validation period and each headline metric pooled per part (`<part>_<metric>`), rounded; a
    metric undefined on a part is None."""
    values = pooled_metrics(metrics).set_index(["part", "metric"])["value"]
    summary: dict[str, object] = {"validation_period": label}
    for part in PARTS:
        for name in headline_names(cfg):
            value = values.loc[(part, metric_key(cfg, name))]
            summary[f"{part}_{name}"] = None if pd.isna(value) else round(float(value), 6)
    return summary


def _earlier_validations(entries: list[Entry]) -> list[dict]:
    """The validation periods earlier Evaluation runs scored, from the audit log's `run` entries
    of stage `evaluation`: `seq, time, run_id, validation_period` each."""
    return [
        {"seq": e.seq, "time": e.time, "run_id": e.run_id, "validation_period": e.validation_period}
        for e in entries
        if e.stage == "evaluation" and e.op == "run"
    ]


def _warnings(opened: Opened, features: pd.DataFrame, cut: dict) -> list[dict]:
    """The run's warnings, the only place they are written: newer runs `find_run` passed over,
    the single-feature baseline's (`single_feature_warnings`), final features with nulls at
    scoring and none in train, and an explanation cut that fell back from the decision's slice
    (`explanation_cut`). Each is a `code`, its values and the `text` printed here, which the
    report shows; the card copies the code and the values. A warning never changes what the
    run does."""
    notes = []
    if opened.passed_over:
        text = (f"{opened.run} is not the newest run of this data definition: newer runs were "
                f"passed over ({'; '.join(opened.passed_over)})")  # fmt: skip
        notes.append({"code": "newer_runs_passed_over", "runs": opened.passed_over, "text": text})
    notes += single_feature_warnings(opened.resolved, opened.choice["single_feature"],
                                     opened.read.run_ledger)  # fmt: skip
    unseen = features.loc[features["null_not_in_train"], "feature"].tolist()
    if unseen:
        text = (f"{unseen} hold nulls at scoring and none in train: the model never learnt "
                "where their nulls go; read their contributions with care")  # fmt: skip
        notes.append({"code": "nulls_not_in_train", "features": unseen, "text": text})
    if not cut["available"]:
        text = f"{cut['reason']} on test: the explanation's cut is the {cut['slice']}"
        notes.append({"code": "explanation_cut_not_at_decision_slice", "slice": cut["slice"],
                      "reason": cut["reason"], "text": text})  # fmt: skip
    for note in notes:
        print(f"warning: {note['text']}")
    return notes
