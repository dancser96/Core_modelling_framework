"""The run folder's contract (Spark, through the session's `evaluated_card`): `open_run_folder`
accepts the run folder Training and Evaluation wrote, and refuses a copy with one thing damaged,
naming the damage.

Until 1.0 no run folder is stored in the repo: 0.x promises no older format, so this version only
has to read what it writes. From 1.0 a frozen folder per format version joins these tests
(`docs/roadmap.md`, backlog).
"""

import json
import shutil
from collections.abc import Callable
from functools import partial
from pathlib import Path

import pandas as pd
import pytest

from core_modelling.artifacts import StageResult
from core_modelling.run_artifacts import open_run_folder, read_run_ledger, read_stage2_copy


def _run_folder(evaluated: StageResult) -> Path:
    """The evaluated run's folder (`06_models/rNNN/`)."""
    return Path(evaluated.paths["folder"]).parent


def test_the_written_run_meets_the_run_contract(evaluated_card: StageResult) -> None:
    """`open_run_folder` accepts the written folder: one run across its pieces, the per-run
    ledger and the `stage2/` copy read back."""
    folder = _run_folder(evaluated_card)
    read = open_run_folder(str(folder))
    assert read.run["run_id"] == read.training["run_id"] == folder.name
    assert read.training["final_features"] == read.bundle.features
    assert len(read_run_ledger(str(folder)))
    assert set(read_stage2_copy(str(folder))["ledger"]["feature"]) >= set(read.bundle.features)


MISSING = object()  # `_change_json`'s value for a key to delete


def _change_json(file: str, path: tuple[str, ...], value: object, folder: Path) -> None:
    """Set the key at `path` of the run folder's json `file` to `value`, or delete it when
    `value` is `MISSING`."""
    target = folder / file
    data = json.loads(target.read_text())
    holder = data
    for key in path[:-1]:
        holder = holder[key]
    if value is MISSING:
        del holder[path[-1]]
    else:
        holder[path[-1]] = value
    target.write_text(json.dumps(data))


def _remove(file: str, folder: Path) -> None:
    """Delete `file` from the run folder."""
    (folder / file).unlink()


def _write_text(file: str, text: str, folder: Path) -> None:
    """Overwrite the run folder's `file` with `text` (a truncated or non-object json)."""
    (folder / file).write_text(text)


def _drop_last_final_feature(folder: Path) -> None:
    """Drop the last of `training.json`'s final features: still columns of every table, no
    longer the bundle's."""
    target = folder / "training" / "training.json"
    data = json.loads(target.read_text())
    data["final_features"] = data["final_features"][:-1]
    target.write_text(json.dumps(data))


def _drop_column(file: str, column: str, folder: Path) -> None:
    """Rewrite the run folder's parquet `file` without `column`."""
    table = pd.read_parquet(folder / file)
    table.drop(columns=column).to_parquet(folder / file)


DAMAGES = {
    "no run.json": (
        partial(_remove, "run.json"),
        FileNotFoundError,
        "the run crashed before it was written",
    ),
    "run.json of another version": (
        partial(_change_json, "run.json", ("run_schema_version",), 99),
        ValueError,
        "run_schema_version 99; this version reads",
    ),
    "a truncated run.json": (
        partial(_write_text, "run.json", '{"run_id": "r0'),
        ValueError,
        "run.json is not valid JSON",
    ),
    "a run.json holding a list": (
        partial(_write_text, "run.json", "[]"),
        ValueError,
        "run.json holds a list",
    ),
    "a truncated training.json": (
        partial(_write_text, "training/training.json", '{"sche'),
        ValueError,
        r"training.json is not valid JSON .*train the run again",
    ),
    "no training resolved config": (
        partial(_remove, "training/resolved_config.yml"),
        FileNotFoundError,
        "resolved_config.yml is missing",
    ),
    "run.json without a key": (
        partial(_change_json, "run.json", ("config_hash",), MISSING),
        ValueError,
        r"lacks the keys \['config_hash'\]",
    ),
    "run.json without a nested key": (
        partial(_change_json, "run.json", ("training_settings", "training"), MISSING),
        ValueError,
        "training_settings/training/objective",
    ),
    "training.json without a key": (
        partial(_change_json, "training/training.json", ("best", "family"), MISSING),
        ValueError,
        r"lacks the keys \['best/family'\]",
    ),
    "a search record without its trials": (
        partial(_change_json, "training/training.json", ("search",), [{"family": "lgbm"}]),
        ValueError,
        "search/trials",
    ),
    "final features other than the bundle's": (
        _drop_last_final_feature,
        ValueError,
        "final_features are not the bundle's",
    ),
    "a missing training table": (
        partial(_remove, "training/tables/selection.parquet"),
        FileNotFoundError,
        "selection.parquet is missing",
    ),
    "a training table without a column": (
        partial(_drop_column, "training/tables/selection.parquet", "rule"),
        ValueError,
        r"lacks the columns \['rule'\]",
    ),
    "no per-run ledger": (
        partial(_remove, "_ledger_run.json"),
        FileNotFoundError,
        "no per-run ledger",
    ),
    "a per-run ledger of another version": (
        partial(_change_json, "_ledger_run.json", ("ledger_run_schema_version",), 1),
        ValueError,
        "ledger_run_schema_version 1",
    ),
    "a truncated per-run ledger sidecar": (
        partial(_write_text, "_ledger_run.json", '{"ledger'),
        ValueError,
        r"_ledger_run.json is not valid JSON .*train the run again",
    ),
    "a stage2 stamp holding a list": (
        partial(_write_text, "stage2/_stage2.json", "[1]"),
        ValueError,
        r"_stage2.json holds a list, not a JSON object: train the run again",
    ),
    "a stage2 copy of another version": (
        partial(_change_json, "stage2/_stage2.json", ("stage2_copy_schema_version",), 0),
        ValueError,
        "stage2_copy_schema_version 0",
    ),
}


@pytest.mark.parametrize("name", DAMAGES)
def test_a_damaged_run_folder_is_refused_naming_what_is_wrong(
    name: str, evaluated_card: StageResult, tmp_path: Path
) -> None:
    """On a copy of the written run folder with one thing damaged (a file deleted, a version
    changed, a key or a column dropped), `open_run_folder` refuses and the message names the
    damage; the undamaged copy opens."""
    folder = _run_folder(evaluated_card)
    copy = tmp_path / folder.name
    shutil.copytree(folder, copy)
    assert open_run_folder(str(copy)).run["run_id"] == folder.name
    damage: Callable[[Path], None]
    damage, error, message = DAMAGES[name]
    damage(copy)
    with pytest.raises(error, match=message):
        open_run_folder(str(copy))
