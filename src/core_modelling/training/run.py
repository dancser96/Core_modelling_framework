"""`run_training`: the Training stage for one entity, in the order of
docs/components/training.md "How one run flows".

1. Resolve the config (the audit log replayed, D-125), check the search's spaces and budget,
   and pass the gate (`gate.py`): EDA and Feature Checks of the same data definition, the
   feature set in force, the train frame collected with its folds, the panel's counts and kinds
   against EDA's, the encoder fitted on train (a constraint on an unordered categorical is
   refused there).
2. `create_run` reserves the run number and writes `run.json`, once every refusal that needs
   no fit has passed, so a refused run takes no number.
3. Apply the encoder, once.
4. Select: the cluster rule, the floor, importance pruning (`train_data.py`, `selection.py`).
5. Search each family on its budget (`search.py`); the best family and configuration.
6. Fit the K fold models there: the out-of-fold margins and contributions, checked against the
   loss the search reported for that configuration; the calibration.
7. Fit the final model on every train row; write the bundle, self-check it and sweep the
   reloaded bundle against the declared constraints.
8. Write the per-run ledger and the `stage2/` copies; build the sign-off table and the tables.
9. Write `training/` last, the commit marker (D-136), then the `run` entry (no periods, D-088).

It orchestrates only: every statistic and every fit is in the modules it calls. It reads the
train split and nothing else (`CLAUDE.md` §4.4), FLAML only searches, and the model the bundle
holds is the framework's own fit (D-140 (a)). A folder without `training/` is a crashed run.
"""

import json
import os
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
from pyspark.sql import SparkSession

from core_modelling.artifacts import StageResult, lap, local_path, stage_identity, write_stage
from core_modelling.config import UseCaseConfig
from core_modelling.config.audit_log import load_entries, record_stage_entry, resolve_config
from core_modelling.config.identities import feature_signature, short
from core_modelling.config.replay import Entry, signed_off
from core_modelling.dataset import Frames, build_frames
from core_modelling.environment import EnvironmentConfig, models_dir
from core_modelling.model.bundle import (
    MANIFEST_FILE,
    OUTPUT_COLUMNS,
    THREAD_PARAMS,
    load_bundle,
    write_bundle,
)
from core_modelling.model.calibration import apply_calibration, uncalibrated
from core_modelling.model.families import FAMILIES, check_monotone
from core_modelling.model.family_inputs import check_order
from core_modelling.model.scoring import check_bundle
from core_modelling.runs import create_run
from core_modelling.statistics.losses import mean_fold_loss
from core_modelling.tasks import FEW_CONVERTING_CLIENTS, FEW_POSITIVE_ROWS
from core_modelling.training.calibrate import calibrate
from core_modelling.training.fold_models import FOLD_COLUMN, fit_fold_models
from core_modelling.training.gate import (
    Stage2,
    check_counts,
    check_kinds,
    feature_set,
    read_stage2,
    save_stage2,
)
from core_modelling.training.ledger_run import build_run_ledger, save_run_ledger, signoff_table
from core_modelling.training.search import (
    Search,
    check_judged_model,
    check_spaces,
    search_families,
)
from core_modelling.training.tables import (
    BASE_COLUMN,
    explanation_sample,
    oof_table,
    train_metrics,
)
from core_modelling.training.train_data import TrainData, encode_and_select, fit_train_encoder
from core_modelling.training.views import search_summary, training_views

SELF_CHECK_ROWS = 1000  # the train rows the reloaded bundle must score as the model in memory
RUN_REASON = "Training fitted this run's model and wrote its bundle."
TIME_BUDGET_NOTE = (
    "training.time_budget_s is set: FLAML then picks by measured seconds, so this run is "
    "reproducible to the recipe, not the model"
)


@dataclass
class Opened:
    """A run that passed the gate: the resolved config, the entries it was replayed from, what
    the gate read, the feature set in force with its log entry (`opening`), the frames, the
    encoder fitted on the train frame, the reserved run number, and the log and the warnings so
    far (both grow as the run goes on)."""

    resolved: UseCaseConfig
    entries: list[Entry]
    stage2: Stage2
    features: list[str]
    opening: dict
    frames: Frames
    encoder: dict
    run: str
    log: list[dict]
    warnings: list[str]


@dataclass
class OutOfFold:
    """The fold models' result on the train rows: the out-of-fold margins and contributions
    (a column per final feature, then `base_value`; the train frame's index), the bundle's
    calibration fitted on those margins, and Training's `calibration` table."""

    margins: np.ndarray
    contributions: pd.DataFrame
    calibration: dict
    table: pd.DataFrame


def run_training(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession
) -> StageResult:
    """Train one run for one entity: the bundle, the per-run ledger, the `stage2/` copies and
    `training/` under the next run number of `<use_case>/06_models/`, then the audit log's `run`
    entry. The result's `ledger` is the per-run ledger and its meta is `training.json`.

    It trains or refuses, at both automation levels: missing or stale EDA or Feature Checks
    artifacts fail loud naming `run` (D-132). A failure after the number is reserved leaves the
    folder without `training/`, listed as an incomplete run.
    """
    seconds: dict[str, float] = {}
    clock = time.perf_counter()
    threads = os.cpu_count() or 1  # a run setting: no model depends on it, no hash holds it
    opened = _open_run(cfg, entity, env, spark)
    seconds["frames"], clock = lap(clock)
    data, entries, notes = encode_and_select(
        opened.frames.train, opened.encoder, opened.stage2.ledger, opened.resolved, threads
    )
    opened.log += entries
    _note(opened, notes)
    seconds["selection"], clock = lap(clock)
    check_order(data.X, data.encoder)
    search = search_families(
        data.X, data.y, data.folds, data.encoder, data.monotone, opened.resolved, threads
    )
    seconds["search"], clock = lap(clock)
    oof = _fit_out_of_fold(opened, data, search)
    seconds["fold_models"], clock = lap(clock)
    booster = _fit_final(data, search, opened.resolved.task)
    seconds["final_fit"], clock = lap(clock)
    manifest = _write_bundle(opened, data, search, booster, oof.calibration, env)
    seconds["bundle"], clock = lap(clock)
    description = FAMILIES[search.family].describe(booster)
    run_ledger = _save_ledgers(opened, data, oof.contributions, description, env)
    result = _build_result(opened, data, search, oof, booster, manifest, run_ledger, env)
    seconds["tables"], clock = lap(clock)
    result.meta["timings"] = {"seconds": seconds}
    result.meta["summary"]["seconds"] = round(sum(seconds.values()), 1)
    _write(result, cfg, entity, env, opened, search.logs)
    return result


def _open_run(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession
) -> Opened:
    """Steps 1 and 2: the config resolved, the search's spaces and budget checked, the gate
    passed, the train frame collected, the panel's counts and kinds checked against EDA's, the
    encoder fitted, and only then the run number reserved: every refusal that needs no model
    comes before it."""
    resolved = resolve_config(cfg, entity, env)
    check_spaces(resolved)
    entries = load_entries(resolved, entity, env)
    stage2 = read_stage2(resolved, entity, env)
    features, opening, warnings = feature_set(stage2, resolved, entries)
    frames = build_frames(resolved, entity, env, spark, "training", features=features)
    check_counts(frames.meta["population"], stage2.eda_meta["population"])
    check_kinds(stage2.ledger, frames.meta["kinds"])
    encoder = fit_train_encoder(frames.train, features, stage2.ledger, resolved)
    if resolved.training.time_budget_s is not None:
        warnings.append(TIME_BUDGET_NOTE)
    warnings += _few_events_notes(frames.train)
    run = create_run(env, resolved, entity, stage2.tokens)
    print(
        f"training {run} of {resolved.use_case} on {entity}: {len(features)} features in force "
        f"({len(opening['held'])} held, which for Training are excluded without a final "
        f"decision; {len(opening['excluded'])} excluded; {len(opening['kept'])} kept; Feature "
        f"Checks' run held {opening['held_by_feature_checks']}); {len(frames.train):,} train rows"
    )
    for warning in warnings:
        print(f"warning: {warning}")
    log = [*frames.log, opening]
    return Opened(resolved, entries, stage2, features, opening, frames, encoder, run, log, warnings)


def _few_events_notes(train: pd.DataFrame) -> list[str]:
    """The warning that the fold metric is noisy: fewer than `FEW_CONVERTING_CLIENTS` train
    clients, or `FEW_POSITIVE_ROWS` train rows, with a non-zero target. It never advises fewer
    folds, which bias the estimate down and buy no precision."""
    positive = train["target"] != 0
    clients, rows = int(train.loc[positive, "unit_id"].nunique()), int(positive.sum())
    if clients >= FEW_CONVERTING_CLIENTS and rows >= FEW_POSITIVE_ROWS:
        return []
    return [
        f"{clients} train clients and {rows} train rows have a non-zero target, fewer than "
        f"{FEW_CONVERTING_CLIENTS} clients or {FEW_POSITIVE_ROWS} rows: the fold metric is noisy "
        "at this size; set training.fold_repeats: 3, keep the trial budget small and read "
        "differences between runs against their intervals"
    ]


def _note(opened: Opened, notes: list[str]) -> None:
    """Add warnings to the run's and print each: a warning never changes what the run does."""
    for note in notes:
        print(f"warning: {note}")
    opened.warnings += notes


def _fit_out_of_fold(opened: Opened, data: TrainData, search: Search) -> OutOfFold:
    """Step 6: the K fold models of the first dealing at the best configuration, their loss
    checked against the one the search reported for it (at one dealing the two are the same
    fits; with more, the search's is over every dealing and cannot be compared), then the
    calibration on their out-of-fold margins (inside train, §4.7)."""
    resolved, train = opened.resolved, opened.frames.train
    training = resolved.training
    check_order(data.X, data.encoder)
    margins, parts = fit_fold_models(
        data.X, data.y, data.folds, search.family, search.parameters, resolved.task
    )
    if training.fold_repeats == 1:
        score_raw, _ = apply_calibration(margins, uncalibrated(training.objective), resolved.task)
        fold = data.folds[FOLD_COLUMN].to_numpy()
        own_loss = mean_fold_loss(resolved.decision.metric, data.y, score_raw, fold)
        _note(opened, check_judged_model(search, own_loss, training.time_budget_s is not None))
    calibration, table, notes = calibrate(
        margins, data.y, train["unit_id"].to_numpy(), resolved, opened.frames.meta["sampling"]
    )
    _note(opened, notes)
    contributions = pd.DataFrame(parts, index=data.X.index, columns=[*data.X.columns, BASE_COLUMN])
    return OutOfFold(margins, contributions, calibration, table)


def _fit_final(data: TrainData, search: Search, task: str) -> object:
    """Step 7's fit: the family's own `fit` on every train row as trained, at the best
    configuration. A booster whose feature names are not the final list fails loud (D-094 (a))."""
    check_order(data.X, data.encoder)
    booster = FAMILIES[search.family].fit(data.X, data.y, search.parameters, task)
    names = list(FAMILIES[search.family].describe(booster)["features"])
    if names != list(data.X.columns):
        raise ValueError(
            f"the fitted {search.family} model names its features {names}, the final list is "
            f"{list(data.X.columns)}: the model would score another frame than the bundle records"
        )
    return booster


def _write_bundle(
    opened: Opened,
    data: TrainData,
    search: Search,
    booster: object,
    calibration: dict,
    env: EnvironmentConfig,
) -> dict:
    """Step 7's writes: the bundle (`write_bundle` checks all of it first), the self-check (the
    bundle reloaded scores `SELF_CHECK_ROWS` train rows exactly as the model in memory) and the
    grid check of the reloaded booster against the declared constraints. Returns the manifest."""
    resolved, train, family = opened.resolved, opened.frames.train, search.family
    final, housekeeping = list(data.X.columns), resolved.housekeeping
    sampling = resolved.training.sampling
    recipe = {
        "task": resolved.task,
        "family": family,
        "parameters": {k: v for k, v in search.parameters.items() if k not in THREAD_PARAMS},
        "features": final,
        "encoder": data.encoder,
        "monotone": data.monotone,
        "calibration": {"method": calibration["method"], "folds": resolved.training.folds},
        "sampling": None if sampling is None else sampling.model_dump(mode="json"),
        "split": resolved.data.split.model_dump(mode="json"),
        "data_definition_hash": housekeeping["data_definition_hash"],
    }
    content = {"task": resolved.task, "features": final, "encoder": data.encoder,
               "calibration": calibration, "recipe": recipe}  # fmt: skip
    identity = {"run_id": opened.run, "data_definition_hash": housekeeping["data_definition_hash"],
                "config_hash": housekeeping["config_hash"],
                "resolved_input_hash": housekeeping["resolved_input_hash"]}  # fmt: skip
    folder = models_dir(env, resolved, opened.run, "bundle")
    write_bundle(folder, family, booster, content, identity)
    head = train.iloc[:SELF_CHECK_ROWS]
    margin = FAMILIES[family].predict(booster, data.X.iloc[:SELF_CHECK_ROWS])
    score_raw, score = apply_calibration(margin, calibration, resolved.task)
    expected = pd.DataFrame(
        {"margin": margin, "score_raw": score_raw, "score": score}, index=head.index
    )
    check_bundle(folder, head[final], expected[OUTPUT_COLUMNS])
    check_monotone(family, load_bundle(folder).booster, data.X, data.monotone)
    return json.loads((local_path(folder) / MANIFEST_FILE).read_text())


def _save_ledgers(
    opened: Opened,
    data: TrainData,
    contributions: pd.DataFrame,
    description: dict,
    env: EnvironmentConfig,
) -> pd.DataFrame:
    """Step 8's writes: the per-run ledger, built from the selection table, the final model's
    `description` and the out-of-fold `contributions` (a column per final feature, then
    `base_value`) and saved beside the bundle, then the run's `stage2/` copies. A constraint
    against EDA's direction, or on a feature EDA marked `non_monotone`, joins the warnings: it
    holds and never refuses."""
    resolved, stage2, final = opened.resolved, opened.stage2, list(data.X.columns)
    run_ledger = build_run_ledger(
        data.selection, data.statistics, description, contributions[final], data.X,
        data.entered_encoder, data.shares, resolved.training.monotone, stage2.ledger,
        list(resolved.features.kept),
    )  # fmt: skip
    wrong = run_ledger.loc[run_ledger["monotone_agrees"].eq(False).fillna(False), "feature"]
    if len(wrong):
        _note(opened, [
            f"the constraints on {wrong.tolist()} go against EDA's direction or its "
            "non_monotone mark; they hold: a person may know more than the window shows"
        ])  # fmt: skip
    sidecar = {"run_id": opened.run, "stage2": stage2.tokens,
               "data_definition_hash": resolved.housekeeping["data_definition_hash"]}  # fmt: skip
    save_run_ledger(run_ledger, models_dir(env, resolved, opened.run), sidecar)
    save_stage2(models_dir(env, resolved, opened.run, "stage2"), stage2, final)
    return run_ledger


def _build_result(
    opened: Opened,
    data: TrainData,
    search: Search,
    oof: OutOfFold,
    booster: object,
    manifest: dict,
    run_ledger: pd.DataFrame,
    env: EnvironmentConfig,
) -> StageResult:
    """Step 8: the stage result built for step 9, writing nothing: the tables,
    `training.json`'s content and the views. `run_ledger` is the per-run ledger as saved."""
    resolved, train = opened.resolved, opened.frames.train
    final, family = list(data.X.columns), FAMILIES[search.family]
    seed = resolved.training.seed
    tables = {
        "trials": search.trials,
        "selection": data.selection,
        "oof": oof_table(train, oof.margins, oof.calibration, resolved.task),
        "explanation_sample": explanation_sample(train, oof.contributions, seed),
        "calibration": oof.table,
        "signoff": signoff_table(run_ledger, opened.stage2.ledger, opened.entries, resolved),
    }
    metrics = train_metrics(
        resolved.decision.metric, resolved.task, data.y, data.folds[FOLD_COLUMN].to_numpy(),
        oof.margins, oof.calibration, family.predict(booster, data.X),
    )  # fmt: skip
    meta = _stage_meta(opened, data, search, metrics, manifest, env)
    signed = signed_off(opened.entries, feature_signature(final))
    views = training_views(
        opened.run, opened.opening, opened.warnings, tables, run_ledger, resolved, signed,
        meta["best"], metrics,
    )  # fmt: skip
    return StageResult(tables=tables, ledger=run_ledger, log=opened.log, meta=meta, paths={},
                       views=views, frame=None, config=resolved)  # fmt: skip


def _stage_meta(
    opened: Opened,
    data: TrainData,
    search: Search,
    metrics: dict,
    manifest: dict,
    env: EnvironmentConfig,
) -> dict:
    """`training.json` without the timings: the identity (`stage_identity`), the run and the
    Stage 2 runs it was trained against, the flat `summary` `list_runs` and `show_run` display,
    the best family and its parameters, the per-family search table, the space each family
    searched, the train-side metrics, the final features, the sampling record, the fold counts
    and the warnings."""
    resolved, final = opened.resolved, list(data.X.columns)
    searched = search_summary(search.trials, metrics["metric"])
    summary = {
        "family": search.family,
        "features": len(final),
        "feature_signature": short(manifest["feature_signature"]),
        "trials": len(search.trials),
        f"oof_{metrics['metric']}": round(metrics["out_of_fold"], 6),
        "recipe_hash": short(manifest["recipe_hash"]),
        "model_hash": short(manifest["model_hash"]),
    }
    best = {k: v for k, v in search.parameters.items() if k not in THREAD_PARAMS}
    return {
        **stage_identity(resolved, "training", env),
        "run_id": opened.run,
        "stage2": opened.stage2.tokens,
        "summary": summary,
        "best": {"family": search.family, "parameters": best},
        "search": searched.to_dict("records"),
        "search_space": search.spaces,
        "metrics": metrics,
        "final_features": final,
        "sampling": opened.frames.meta["sampling"],
        "folds": opened.frames.meta["folds"].to_dict("records"),
        "reproducible_to": "model" if resolved.training.time_budget_s is None else "recipe",
        "warnings": opened.warnings,
    }


def _write(
    result: StageResult,
    cfg: UseCaseConfig,
    entity: str,
    env: EnvironmentConfig,
    opened: Opened,
    logs: dict[str, str],
) -> None:
    """Step 9: `training/` written whole with FLAML's log of each family in it
    (`training.json` is the commit marker of a trained run), then the audit log's `run` entry
    with the run number and no periods, so a Training run never blocks moving the validation
    period (D-088)."""
    resolved, run = opened.resolved, opened.run
    folder = models_dir(env, resolved, run, "training")
    result.paths = write_stage(result, folder, "training", texts=logs)
    housekeeping = resolved.housekeeping
    record_stage_entry(
        cfg, entity, env, stage="training", op="run", reason=RUN_REASON, run_id=run,
        replayed_to=housekeeping["replayed_to"],
        resolved_input_hash=housekeeping["resolved_input_hash"],
    )  # fmt: skip
    print(f"training {run} written: {folder}")
