"""`run_training`: the Training stage for one entity, in the order of
docs/components/training.md "How one run flows".

1. Resolve the config (the audit log replayed, D-125), check the search's spaces and budget,
   and pass the gate (`gate.py`): EDA and Feature Checks of the same data definition, the
   feature set in force, the train frame collected with its folds, the panel's counts and kinds
   against EDA's, a target the objective can take, the encoder fitted on train (a constraint on
   an unordered categorical is refused there).
2. Apply the encoder, once, and screen: the cluster rule and the floor, the selection rules
   that fit no model (`train_data.py`, `selection.py`).
3. `create_run` reserves the run number and writes `run.json`, once every refusal that needs
   no fit has passed, so a refused run takes no number.
4. Prune by importance, the selection rule that fits models.
5. Search each family on its budget (`search.py`); the best family and configuration.
6. Fit the K fold models there: the out-of-fold margins and contributions; with the further
   dealings' fold models, their mean loss is checked against the loss the search reported for
   that configuration (`fold_models.py`, `search.py`); the calibration.
7. Fit the final model on every train row; write the bundle, self-check it and sweep the
   reloaded bundle against the declared constraints (`run_bundle.py`).
8. Write the per-run ledger and the `stage2/` copies; build the sign-off table and the tables.
9. Write `training/` last, the commit marker (D-136), then the `run` entry (no periods, D-088).

It orchestrates only: every statistic and every fit is in the modules it calls. It reads the
train split and nothing else (`CLAUDE.md` §4.4), FLAML only searches, and the model the bundle
holds is the framework's own fit (D-140 (a)). Every fit and predict runs on the environment's
`threads` (absent: the machine's cores). A folder without `training/` is a crashed run.
"""

import os
import time
from dataclasses import dataclass
from importlib.metadata import version

import numpy as np
import pandas as pd
from pyspark.sql import SparkSession

from core_modelling.artifacts import StageResult, lap, stage_identity, write_stage
from core_modelling.config import UseCaseConfig
from core_modelling.config.audit_log import load_entries, record_stage_entry, resolve_config
from core_modelling.config.identities import feature_signature, short
from core_modelling.config.replay import Entry, signed_off
from core_modelling.dataset import Frames, build_frames
from core_modelling.environment import EnvironmentConfig, models_dir
from core_modelling.model.family_inputs import check_order
from core_modelling.reporting.training_views import search_summary, training_views
from core_modelling.run_artifacts import BASE_COLUMN
from core_modelling.runs import create_run
from core_modelling.tasks import TASK_SPECS
from core_modelling.training.calibrate import calibrate
from core_modelling.training.fold_models import (
    FOLD_COLUMN,
    FinalModel,
    every_dealing_loss,
    fit_final_model,
    fit_fold_models,
)
from core_modelling.training.gate import (
    Stage2,
    check_counts,
    check_kinds,
    check_target_range,
    feature_set,
    read_stage2,
    save_stage2,
)
from core_modelling.training.ledger_run import build_run_ledger, ledger_warnings, save_run_ledger
from core_modelling.training.run_bundle import write_run_bundle
from core_modelling.training.search import (
    Search,
    check_judged_model,
    check_spaces,
    search_families,
)
from core_modelling.training.signoff import signoff_table
from core_modelling.training.tables import explanation_sample, oof_table, train_metrics
from core_modelling.training.train_data import (
    Screened,
    TrainData,
    encode_and_screen,
    finish_selection,
    fit_train_encoder,
)

RUN_REASON = "Training fitted this run's model and wrote its bundle."
# The libraries whose versions `training.json` records: FLAML, every family's, numpy, sklearn
LIBRARIES = ("flaml", "lightgbm", "xgboost", "catboost", "numpy", "scikit-learn")
TIME_BUDGET_NOTE = (
    "training.time_budget_s is set: FLAML then picks by measured seconds, so this run is "
    "reproducible to the recipe, not the model"
)


@dataclass
class Opened:
    """A run that passed the gate: the resolved config, the entries it was replayed from, what
    the gate read, the log entry of the feature set in force (`opening`), the frames, the
    encoder fitted on the train frame, the frame encoded and screened, the reserved run number,
    and the log and the warnings so far (both grow as the run goes on)."""

    resolved: UseCaseConfig
    entries: list[Entry]
    stage2: Stage2
    opening: dict
    frames: Frames
    encoder: dict
    screened: Screened
    run: str
    log: list[dict]
    warnings: list[str]


@dataclass
class OutOfFold:
    """The fold models' result on the train rows: the out-of-fold margins and contributions
    (a column per final feature, then `base_value`; the train frame's index), the bundle's
    calibration fitted on those margins, Training's `calibration` table and the judged-model
    check's record (`check_judged_model`)."""

    margins: np.ndarray
    contributions: pd.DataFrame
    calibration: dict
    table: pd.DataFrame
    judged: dict


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
    # A run setting: no model depends on it, no hash holds it
    threads = env.threads or os.cpu_count() or 1
    opened = _open_run(cfg, entity, env, spark)
    seconds["frames"], clock = lap(clock)
    data, entry, notes = finish_selection(
        opened.frames.train, opened.encoder, opened.screened, opened.resolved, threads
    )
    opened.log.append(entry)
    _note(opened, notes)
    check_order(data.X, data.encoder)  # once: every fit below takes this frame
    seconds["selection"], clock = lap(clock)
    search = search_families(
        data.X, data.y, data.folds, data.encoder, data.monotone, opened.resolved, threads
    )
    seconds["search"], clock = lap(clock)
    oof = _fit_out_of_fold(opened, data, search, threads)
    seconds["fold_models"], clock = lap(clock)
    final = fit_final_model(
        data.X, data.y, search.family, search.parameters, opened.resolved.task, threads
    )
    seconds["final_fit"], clock = lap(clock)
    manifest = write_run_bundle(
        models_dir(env, opened.resolved, opened.run, "bundle"), opened.resolved, opened.run, data,
        search, final, oof.calibration, opened.frames.train, threads,
    )  # fmt: skip
    seconds["bundle"], clock = lap(clock)
    run_ledger = _save_run_ledger(opened, data, oof.contributions, final.description, env)
    stage2_folder = models_dir(env, opened.resolved, opened.run, "stage2")
    save_stage2(stage2_folder, opened.stage2, list(data.X.columns))
    seconds["ledger_and_stage2"], clock = lap(clock)
    result = _build_result(opened, data, search, oof, final, manifest, run_ledger, env, threads)
    seconds["tables"], clock = lap(clock)
    result.meta["timings"] = {"seconds": seconds}
    # Up to the write: `training/` cannot hold the time it takes to write itself
    result.meta["summary"]["seconds"] = round(sum(seconds.values()), 1)
    _write(result, cfg, entity, env, opened, search.logs)
    return result


def _open_run(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession
) -> Opened:
    """Steps 1 to 3: the config resolved, the search's spaces and budget checked, the gate
    passed, the train frame collected, the panel's counts and kinds checked against EDA's, the
    encoder fitted, the frame encoded and screened (the cluster rule and the floor, which fit no
    model and refuse when they leave no feature), and only then the run number reserved: every
    refusal that needs no model comes before it."""
    resolved = resolve_config(cfg, entity, env)
    check_spaces(resolved)
    entries = load_entries(resolved, entity, env)
    stage2 = read_stage2(resolved, entity, env)
    features, opening, warnings = feature_set(stage2, resolved, entries)
    frames = build_frames(resolved, entity, env, spark, "training", features=features)
    check_counts(frames.meta["population"], stage2.eda_meta["population"])
    check_kinds(stage2.ledger, frames.meta["kinds"])
    encoder = fit_train_encoder(frames.train, features, stage2.ledger, resolved)
    check_target_range(frames.train, resolved.training.objective)
    screened, encoded, notes = encode_and_screen(frames.train, encoder, stage2.ledger, resolved)
    warnings += notes
    if resolved.training.time_budget_s is not None:
        warnings.append(TIME_BUDGET_NOTE)
    warnings += _few_events_notes(frames.train, resolved.task)
    run = create_run(env, resolved, entity, stage2.tokens)
    print(
        f"training {run} of {resolved.use_case} on {entity}: {len(features)} features in force "
        f"({len(opening['held'])} held, which for Training are excluded without a final "
        f"decision; {len(opening['excluded'])} excluded; {len(opening['kept'])} kept; Feature "
        f"Checks' run held {opening['held_by_feature_checks']}); {len(frames.train):,} train rows"
    )
    for warning in warnings:
        print(f"warning: {warning}")
    log = [*frames.log, opening, encoded]
    return Opened(resolved, entries, stage2, opening, frames, encoder, screened, run, log, warnings)


def _few_events_notes(train: pd.DataFrame, task: str) -> list[str]:
    """The task's warning that the fold metric is noisy, counted on the train split's clients
    and rows with a non-zero target (`few_events_warning` in `tasks.py`)."""
    events = train["target"] != 0
    clients, rows = int(train.loc[events, "unit_id"].nunique()), int(events.sum())
    note = TASK_SPECS[task]["few_events_warning"](clients, rows, where="in the train split")
    return [] if note is None else [note]


def _note(opened: Opened, notes: list[str]) -> None:
    """Add warnings to the run's and print each: a warning never changes what the run does."""
    for note in notes:
        print(f"warning: {note}")
    opened.warnings += notes


def _fit_out_of_fold(opened: Opened, data: TrainData, search: Search, threads: int) -> OutOfFold:
    """Step 6: the K fold models of the first dealing at the best configuration; their mean loss
    over every dealing (the further dealings' fold models fitted for it) checked against the
    one the search reported for it; then the calibration on the first dealing's out-of-fold
    margins (inside train, §4.7)."""
    resolved, train, training = opened.resolved, opened.frames.train, opened.resolved.training
    family, parameters = search.family, search.parameters
    margins, parts = fit_fold_models(
        data.X, data.y, data.folds, family, parameters, resolved.task, threads
    )
    own_loss = every_dealing_loss(
        data.X, data.y, data.folds, margins, family, parameters, resolved, threads
    )
    judged, notes = check_judged_model(
        search, own_loss, training.time_budget_s is not None, training.fold_repeats
    )
    _note(opened, notes)
    calibration, table, notes = calibrate(
        margins, data.y, train["unit_id"].to_numpy(), resolved, opened.frames.meta["sampling"]
    )
    _note(opened, notes)
    contributions = pd.DataFrame(parts, index=data.X.index, columns=[*data.X.columns, BASE_COLUMN])
    return OutOfFold(margins, contributions, calibration, table, judged)


def _save_run_ledger(
    opened: Opened,
    data: TrainData,
    contributions: pd.DataFrame,
    description: dict,
    env: EnvironmentConfig,
) -> pd.DataFrame:
    """Step 8's first write: the per-run ledger, built from the selection table, the final
    model's `description` and the out-of-fold `contributions` (a column per final feature, then
    `base_value`) and saved beside the bundle. Its warnings (`ledger_warnings`) join the run's:
    they never refuse."""
    resolved, final = opened.resolved, list(data.X.columns)
    run_ledger = build_run_ledger(
        data.selection, data.statistics, description, contributions[final], data.X,
        data.entered_encoder, data.shares, resolved.training.monotone, opened.stage2.ledger,
        list(resolved.features.kept),
    )  # fmt: skip
    _note(opened, ledger_warnings(run_ledger))
    sidecar = {"run_id": opened.run, "stage2": opened.stage2.tokens,
               "data_definition_hash": resolved.housekeeping["data_definition_hash"]}  # fmt: skip
    save_run_ledger(run_ledger, models_dir(env, resolved, opened.run), sidecar)
    return run_ledger


def _build_result(
    opened: Opened,
    data: TrainData,
    search: Search,
    oof: OutOfFold,
    final: FinalModel,
    manifest: dict,
    run_ledger: pd.DataFrame,
    env: EnvironmentConfig,
    threads: int,
) -> StageResult:
    """Step 8: the stage result built for step 9, writing nothing: the tables,
    `training.json`'s content and the views. `run_ledger` is the per-run ledger as saved."""
    resolved, train = opened.resolved, opened.frames.train
    seed = resolved.training.seed
    tables = {
        "trials": search.trials,
        "selection": data.selection,
        "oof": oof_table(train, oof.margins, oof.calibration, resolved.task, final.margins),
        "explanation_sample": explanation_sample(train, oof.contributions, seed),
        "calibration": oof.table,
        "signoff": signoff_table(run_ledger, opened.stage2.ledger, opened.entries, resolved),
    }
    metrics = train_metrics(
        resolved.decision.metric, resolved.task, data.y, data.folds[FOLD_COLUMN].to_numpy(),
        oof.margins, oof.calibration, final.margins,
    )  # fmt: skip
    meta = _stage_meta(opened, data, search, metrics, manifest, env)
    meta |= {"judged_model": oof.judged, "threads": threads, "library_versions": _versions()}
    signed = signed_off(opened.entries, feature_signature(list(data.X.columns)))
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
    return {
        **stage_identity(resolved, "training", env),
        "run_id": opened.run,
        "stage2": opened.stage2.tokens,
        "summary": summary,
        "best": {"family": search.family, "parameters": search.recorded_parameters},
        "search": searched.to_dict("records"),
        "search_space": search.spaces,
        "metrics": metrics,
        "final_features": final,
        "sampling": opened.frames.meta["sampling"],
        "folds": opened.frames.meta["folds"].to_dict("records"),
        "reproducible_to": "model" if resolved.training.time_budget_s is None else "recipe",
        "warnings": opened.warnings,
    }


def _versions() -> dict[str, str]:
    """The installed version of each of `LIBRARIES`: what a model and its numbers depend on
    beyond the framework's own code version."""
    return {library: version(library) for library in LIBRARIES}


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
