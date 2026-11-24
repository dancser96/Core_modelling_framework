"""The run folder's contract: what Training wrote into a run folder, as every later stage reads
it (training.md → "What Training writes").

Evaluation, `compare_runs` and, from M2.4, register, Inference and Monitoring open a run folder
through `open_run_folder`, so reading one needs neither FLAML nor Training's code. It reads
`run.json`, the bundle, `training.json`, the per-run ledger and the `stage2/` copy once and
checks the contract before any Spark work; every refusal names the file, what it lacks and what
to do. The names both the writing and the reading side use are defined here once.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from core_modelling.artifacts import local_path, read_json, read_parquet, read_stage_meta
from core_modelling.model.bundle import MANIFEST_FILE, Bundle, build_bundle, read_bundle_files
from core_modelling.runs import read_run_record
from core_modelling.sources import KEYS

STAGE2_TABLES = ("cells", "edges", "bins", "levels")  # EDA's tables a run keeps its own copy of
STAGE2_FILE = "_stage2.json"  # the copy's version, and which versions and runs it is a copy of
STAGE2_COPY_SCHEMA_VERSION = 1  # the `stage2/` copy's own format: its tables and their columns
_GROUP_COLUMNS = ("feature", "group", "rows", "support", "estimate", "low", "high", "lift",
                  "insufficient")  # fmt: skip
# The copy's columns per table as of `STAGE2_COPY_SCHEMA_VERSION`, frozen: Training writes
# exactly these, so a later EDA or ledger column changes no copy; a change here bumps the version
STAGE2_COLUMNS = {
    "ledger": ("feature", "kind", "source", "lineage", "unsupported", "levels", "concordance",
               "concordance_se", "direction", "concordance_best_order", "non_monotone",
               "concordance_window", "missing_share", "missing_share_window", "null_concordance",
               "null_concordance_window", "zero_share", "zero_share_window", "dominant_share",
               "dominant_share_window", "rank", "key_feature", "represented_by", "flags", "notes",
               "lagged_concordance", "signal_kept", "constant_share", "concordance_range",
               "heterogeneity_p", "psi_window", "psi_latest", "new_level_share", "cluster",
               "explained_by_others", "partners"),
    "cells": ("feature", "period", "lagged", "fold", "bin", "bin_order", "is_null", "target_bin",
              "n", "sum_y", "sum_y2"),
    "edges": ("feature", "position", "edge"),
    "bins": _GROUP_COLUMNS,
    "levels": _GROUP_COLUMNS,
}  # fmt: skip
LEDGER_RUN_SCHEMA_VERSION = 2  # 2: `floor_cleared_by`
LEDGER_RUN_FILE = "ledger_run.parquet"
SIDECAR_FILE = "_ledger_run.json"  # starts with `_`, never `_metadata` (T21)
RULES = ("cluster", "floor", "prune")  # the selection rules, in the order they run
OUTCOMES = ("passed", "dropped", "protected", "undone")
SECTIONS = ("model", "held", "excluded", "declared_not_in_model")  # the sign-off table's
OPPOSITE = {"increasing": "-", "decreasing": "+"}  # EDA's direction that contradicts a constraint
LIST_COLUMNS = ("represents", "notes", "kept_flags", "open_flags")  # the sign-off's list columns
EXPLANATION_ROWS = 5000  # the explanation sample: this many seeded train rows, or every row
CONTRIBUTION_SUFFIX = "__contribution"  # a feature's contribution column in the sample
# The contributions' base value: a row's contributions and it sum to its margin
BASE_COLUMN = "base_value"
TRAINING_SIGNOFF = "training_signoff"  # Training's `signoff` table, among Evaluation's tables
TRAINING_TRIALS = "training_trials"  # Training's `trials` table, among Evaluation's tables
TRAIN_SAMPLE = "training_explanation_sample"  # Training's `explanation_sample`, as stored
# Training's tables Evaluation carries so that `evaluation/` renders alone, by stored name
CARRIED_TABLES = {TRAINING_SIGNOFF: "signoff", TRAINING_TRIALS: "trials",
                  TRAIN_SAMPLE: "explanation_sample"}  # fmt: skip

# The contract: what a later stage reads of what Training wrote. A key path is a tuple of keys,
# since a settings key may hold a dot (`features.order`).
TRAIN_METRIC_KEYS = ("metric", "out_of_fold", "out_of_fold_concordance", "in_sample_concordance")
RUN_PATHS = (
    ("training_settings", "training", "objective"),
    ("training_settings", "features.order"),
)
TRAINING_PATHS = (
    ("run_id",), ("written_at",), ("warnings",), ("search",), ("final_features",), ("folds",),
    ("reproducible_to",), ("best", "family"), ("settings", "training", "path"),
    ("settings", "training", "time_budget_s"), ("sampling", "method"), ("timings", "seconds"),
    *[("metrics", key) for key in TRAIN_METRIC_KEYS],
)  # fmt: skip
SAMPLED_PATH = ("sampling", "true_rate")  # read when `sampling.method` is not None
SEARCH_KEYS = ("family", "trials", "seconds")  # of each family's record in `search`
SIGNOFF_COLUMNS = [
    "section", "feature", "contribution_share", "cumulative_share", "direction_model",
    "direction_eda", "direction_agrees", "monotone", "wrong_sign", "represents", "source",
    "notes", "kept_flags", "open_flags", "exclude_entry", "exclude_reason", "dropped_by",
]  # fmt: skip
# Training's `calibration` table: one row per method the task fits, one schema for both tasks,
# null where a column does not apply; `parameters` is JSON text, so the table writes to parquet.
CALIBRATION_COLUMNS = {
    "method": "object",
    "chosen": "bool",
    "parameters": "object",
    "oof_loss": "float64",  # the task's calibration loss (binary: the log loss), else null
    "true_rate": "float64",
    "sampled_rate": "float64",
    "offset": "float64",
    "factor": "float64",
    "factor_low": "float64",
    "factor_high": "float64",
    "half_total_rows": "Int64",
}
TRAINING_TABLE_COLUMNS = {
    "signoff": tuple(SIGNOFF_COLUMNS),
    "calibration": tuple(CALIBRATION_COLUMNS),
    "selection": ("feature", "rule", "outcome"),
    "trials": ("family", "trial", "fold_loss", "seconds"),
    # and, per final feature, its raw value and `<feature>__contribution`
    "explanation_sample": (*KEYS, BASE_COLUMN),
    "oof": ("target", "score_in_sample"),
}  # fmt: skip


@dataclass
class RunFolder:
    """A run folder as `open_run_folder` read and checked it, each piece once: the folder, its
    `run.json`, the bundle (its model hash recomputed over its files), its manifest,
    `training.json`, the per-run ledger and the `stage2/` copy (`read_stage2_copy`)."""

    folder: str
    run: dict
    bundle: Bundle
    manifest: dict
    training: dict
    run_ledger: pd.DataFrame
    stage2: dict[str, pd.DataFrame]


def open_run_folder(run_folder: str) -> RunFolder:
    """Read a run folder once and check it against the contract before any Spark work:
    `run.json` (`read_run_record`, then `RUN_PATHS`), the bundle (its model hash recomputed),
    `training.json` (its version, `TRAINING_PATHS`, `SEARCH_KEYS`), Training's
    `resolved_config.yml` and tables (`TRAINING_TABLE_COLUMNS`, from the parquet footers), the
    per-run ledger and the `stage2/` copy (their versions), and pieces of different runs
    (`_check_run_pieces`)."""
    root = local_path(run_folder)
    run = _read_run_json(root)
    files = read_bundle_files(str(root / "bundle"))
    bundle = build_bundle(files, str(root / "bundle"))
    manifest = json.loads(files[MANIFEST_FILE])
    training = read_stage_meta(str(root / "training"), "training")
    _check_training(training, root / "training" / "training.json")
    _check_resolved_config(root / "training" / "resolved_config.yml")
    _check_training_tables(root / "training" / "tables", training["final_features"])
    _check_run_pieces(run, manifest, training, bundle)
    return RunFolder(run_folder, run, bundle, manifest, training, read_run_ledger(run_folder),
                     read_stage2_copy(run_folder))  # fmt: skip


def _missing_paths(data: dict, paths: Iterable[tuple[str, ...]]) -> list[str]:
    """The key paths of `paths` that `data` lacks, each written with `/` between its keys."""
    missing = []
    for path in paths:
        value = data
        for key in path:
            if not isinstance(value, dict) or key not in value:
                missing.append("/".join(path))
                break
            value = value[key]
    return missing


def _refuse_missing(missing: list[str], where: Path, what: str) -> None:
    """Fail naming the file and the keys or columns it lacks, and what to do; nothing when none."""
    if missing:
        raise ValueError(
            f"{where} lacks the {what} {missing}: the run was written by another framework "
            "version or did not finish; read it with the framework version that trained it (the "
            "use case's pin), or train a new run"
        )


def _read_run_json(root: Path) -> dict:
    """A run folder's `run.json` as `read_run_record` reads it, also refused without a key path
    of `RUN_PATHS`."""
    run = read_run_record(root)
    _refuse_missing(_missing_paths(run, RUN_PATHS), root / "run.json", "keys")
    return run


def _check_resolved_config(path: Path) -> None:
    """Refuse a run without Training's `resolved_config.yml`, which `compare_runs` reads."""
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is missing: the run was written by another framework version or did not "
            "finish; train a new run"
        )


def _check_training(training: dict, path: Path) -> None:
    """Refuse a `training.json` without a key path of `TRAINING_PATHS`, without `SAMPLED_PATH`
    when Training sampled, or with a `search` record without `SEARCH_KEYS`."""
    missing = _missing_paths(training, TRAINING_PATHS)
    if not missing and training["sampling"]["method"] is not None:
        missing = _missing_paths(training, [SAMPLED_PATH])
    if not missing:
        missing = [f"search/{key}" for key in SEARCH_KEYS
                   if any(key not in record for record in training["search"])]  # fmt: skip
    _refuse_missing(missing, path, "keys")


def _check_columns(path: Path, columns: Iterable[str]) -> None:
    """Refuse a missing table, or one whose parquet footer lacks one of `columns`; no row is
    read."""
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is missing: the run was written by another framework version or did not "
            "finish; train a new run"
        )
    names = set(pq.read_schema(path).names)
    _refuse_missing([column for column in columns if column not in names], path, "columns")


def _check_training_tables(folder: Path, features: list[str]) -> None:
    """Every table of `TRAINING_TABLE_COLUMNS` in Training's `tables/` with its columns; the
    explanation sample also with each final feature's value and contribution."""
    for name, columns in TRAINING_TABLE_COLUMNS.items():
        if name == "explanation_sample":
            columns = (*columns, *features, *[f"{f}{CONTRIBUTION_SUFFIX}" for f in features])
        _check_columns(folder / f"{name}.parquet", columns)


def _check_run_pieces(run: dict, manifest: dict, training: dict, bundle: Bundle) -> None:
    """Refuse a run folder of pieces of different runs: one run id across `run.json`, the
    manifest and `training.json`, and Training's final features the bundle's."""
    ids = {run["run_id"], manifest["run_id"], training["run_id"]}
    if len(ids) != 1:
        raise ValueError(f"the run folder's files name the runs {sorted(ids)}: one folder, one run")
    if training["final_features"] != bundle.features:
        raise ValueError("training.json's final_features are not the bundle's: train again")


def read_training_tables(read: RunFolder, names: Iterable[str]) -> dict[str, pd.DataFrame]:
    """Training's tables of `names`, by name, from a run folder `open_run_folder` checked."""
    folder = local_path(read.folder) / "training" / "tables"
    return {name: read_parquet(folder / f"{name}.parquet") for name in names}


def read_stage2_copy(run_folder: str) -> dict[str, pd.DataFrame]:
    """The run's own copy of Stage 2 (`<run_folder>/stage2/`, `save_stage2`'s) by table name:
    `ledger` and `STAGE2_TABLES`. `STAGE2_FILE` is read first: a copy of another
    `stage2_copy_schema_version`, or of none (written before the copy had its own version), is
    refused, and so is a table without its `STAGE2_COLUMNS`. The EDA and ledger versions the
    copy records are provenance, never checked. The only reader of `stage2/`."""
    folder = local_path(run_folder) / "stage2"
    stamp_file = folder / STAGE2_FILE
    if not stamp_file.is_file():
        raise FileNotFoundError(
            f"{folder} holds no {STAGE2_FILE}: the run's copy of Stage 2 is missing or "
            "unfinished; train the run again"
        )
    version = read_json(stamp_file, "train the run again").get("stage2_copy_schema_version")
    if version != STAGE2_COPY_SCHEMA_VERSION:
        raise ValueError(
            f"{stamp_file} has stage2_copy_schema_version {version}, this framework reads "
            f"{STAGE2_COPY_SCHEMA_VERSION}: read the run with the framework version that trained "
            "it, or train the run again"
        )
    for name, columns in STAGE2_COLUMNS.items():
        _check_columns(folder / f"{name}.parquet", columns)
    return {name: read_parquet(folder / f"{name}.parquet") for name in STAGE2_COLUMNS}


def read_run_ledger(run_folder: str) -> pd.DataFrame:
    """The saved per-run ledger; a missing one and another `ledger_run_schema_version` are refused
    before the parquet is read."""
    target = local_path(run_folder)
    if not (target / SIDECAR_FILE).is_file():
        raise FileNotFoundError(
            f"no per-run ledger at {run_folder}: the run crashed before writing it, or this is no "
            "run folder"
        )
    sidecar = read_json(target / SIDECAR_FILE, "train the run again")
    version = sidecar.get("ledger_run_schema_version")
    if version != LEDGER_RUN_SCHEMA_VERSION:
        raise ValueError(
            f"the per-run ledger at {run_folder} has ledger_run_schema_version {version} (written "
            f"by framework {sidecar.get('framework_version')}); this version reads "
            f"{LEDGER_RUN_SCHEMA_VERSION}: read the run with the framework version that wrote it "
            "(the use case's pin), or train a new run"
        )
    return read_parquet(target / LEDGER_RUN_FILE)


def train_level(read: RunFolder) -> float:
    """The unsampled train split's rate (regression: its mean), the `base` the skill scores and
    the `population_base_rate` read (D-098), from a run folder `open_run_folder` checked:
    `training.json`'s `sampling.true_rate` when Training sampled, else the target mean of
    `oof.parquet`, which then holds every train row and is read for that one column."""
    sampling = read.training["sampling"]
    if sampling["method"] is not None:
        return float(sampling["true_rate"])
    path = local_path(read.folder) / "training" / "tables" / "oof.parquet"
    return float(pd.read_parquet(path, columns=["target"])["target"].mean())


def sample_contributions(sample: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """The explanation sample's contributions under the features' own names, one column per
    feature: the shape the explanation charts take beside `sample[features]`, the raw values."""
    columns = [f"{name}{CONTRIBUTION_SUFFIX}" for name in features]
    return sample[columns].set_axis(features, axis=1)


def read_in_sample(read: RunFolder) -> pd.DataFrame:
    """Training's train rows with their `target` and in-sample score (`score_in_sample`: the
    final model's on the rows it was fitted on, on the score's scale), from `oof.parquet`, read
    for those two columns, from a run folder `open_run_folder` checked."""
    path = local_path(read.folder) / "training" / "tables" / "oof.parquet"
    return pd.read_parquet(path, columns=["target", "score_in_sample"])
