"""Training's bundle step (training.md → "The final fit and the bundle"): write the run's bundle
and check it as reloaded.

`write_run_bundle` builds what `write_bundle` takes from the run's pieces (the final features,
the encoder, the calibration, the recipe and the hashes the run was trained under), writes it,
then loads the bundle once and checks it: it scores `SELF_CHECK_ROWS` train rows exactly as the
model in memory did, and its booster keeps the declared monotone constraints.
"""

import json

import pandas as pd

from core_modelling.artifacts import local_path
from core_modelling.config import UseCaseConfig
from core_modelling.model.bundle import MANIFEST_FILE, OUTPUT_COLUMNS, load_bundle, write_bundle
from core_modelling.model.calibration import apply_calibration
from core_modelling.model.families import check_monotone
from core_modelling.model.scoring import check_bundle
from core_modelling.training.fold_models import FinalModel
from core_modelling.training.search import Search
from core_modelling.training.train_data import TrainData

SELF_CHECK_ROWS = 1000  # the train rows the reloaded bundle must score as the model in memory


def write_run_bundle(
    folder: str,
    resolved: UseCaseConfig,
    run: str,
    data: TrainData,
    search: Search,
    final: FinalModel,
    calibration: dict,
    train: pd.DataFrame,
    threads: int,
) -> dict:
    """Write the run's bundle into `folder` (`write_bundle` checks all of it first), then check
    it as reloaded (`_check_reloaded`); returns the manifest. `train` is the collected train
    frame on `data`'s rows, `final` the model fitted on every train row."""
    content, identity = _bundle_content(resolved, run, data, search, calibration)
    write_bundle(folder, search.family, final.booster, content, identity)
    _check_reloaded(folder, train, data, search.family, final, calibration, resolved.task, threads)
    return json.loads((local_path(folder) / MANIFEST_FILE).read_text())


def _bundle_content(
    resolved: UseCaseConfig, run: str, data: TrainData, search: Search, calibration: dict
) -> tuple[dict, dict]:
    """`(content, identity)` of `write_bundle`: the task, the final features, the encoder, the
    calibration and the recipe; the run and the hashes it was trained under."""
    housekeeping, sampling = resolved.housekeeping, resolved.training.sampling
    final = list(data.X.columns)
    recipe = {
        "task": resolved.task,
        "family": search.family,
        "parameters": search.recorded_parameters,
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
    identity = {"run_id": run, "data_definition_hash": housekeeping["data_definition_hash"],
                "config_hash": housekeeping["config_hash"],
                "resolved_input_hash": housekeeping["resolved_input_hash"]}  # fmt: skip
    return content, identity


def _check_reloaded(
    folder: str,
    train: pd.DataFrame,
    data: TrainData,
    family: str,
    final: FinalModel,
    calibration: dict,
    task: str,
    threads: int,
) -> None:
    """The bundle in `folder`, loaded once: the self-check (it scores `SELF_CHECK_ROWS` train
    rows exactly as the model in memory did, from the final model's in-sample margins) and the
    grid check of its booster against the declared constraints."""
    bundle = load_bundle(folder)
    head = train.iloc[:SELF_CHECK_ROWS]
    margin = final.margins[:SELF_CHECK_ROWS]
    score_raw, score = apply_calibration(margin, calibration, task)
    expected = pd.DataFrame(
        {"margin": margin, "score_raw": score_raw, "score": score}, index=head.index
    )
    check_bundle(bundle, head[list(data.X.columns)], expected[OUTPUT_COLUMNS], threads)
    check_monotone(family, bundle.booster, data.X, data.monotone, threads=threads)
