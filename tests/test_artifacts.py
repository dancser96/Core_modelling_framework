"""The stage artifact folder: written whole or not at all, read back as written, and refused when
its data definition or settings no longer fit the resolved config (D-136, D-137)."""

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core_modelling import __version__
from core_modelling.artifacts import (
    StageResult,
    check_upstream,
    read_stage,
    remove_stage,
    settings_meta,
    write_stage,
)
from core_modelling.config.audit_log import read_resolved_config
from core_modelling.config.identities import data_definition_hash
from core_modelling.config.schema import UseCaseConfig
from core_modelling.eda.run import SETTINGS_PATHS as EDA_PATHS


def _result(config: UseCaseConfig, run: int = 1) -> StageResult:
    """A small stage result: two tables (one with list and nullable-int columns), a meta with
    dates, numpy datetimes and numpy values, one log line."""
    ranking = pd.DataFrame(
        {
            "feature": ["a", "b", "c"],
            "flags": [["leakage.too_strong", "quality.high_missing"], [], None],
            "rank": pd.array([1, None, 3], dtype="Int64"),
            "concordance": [0.71, np.nan, 0.55],
        }
    )
    cells = pd.DataFrame({"feature": ["a", "a"], "period": [date(2025, 1, 31)] * 2, "n": [3, 4]})
    meta = {
        "run": run,
        "snapshot": date(2025, 1, 31),
        "latest": np.datetime64("2025-01-31T00:00:00", "ns"),  # as `series.values.max()` gives
        "periods": np.array(["2024-12-31", "NaT"], dtype="datetime64[ns]"),
        "rows": np.int64(7),
        "ok": np.bool_(True),
    }
    return StageResult(
        tables={"ranking": ranking, "cells": cells},
        ledger=pd.DataFrame(),
        log=[{"step": "counts", "rows": np.int64(7)}],
        meta=meta,
        paths={},
        views={},
        frame=None,
        config=config,
    )


def _fail_second_parquet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the second `to_parquet` call of the test raise, as a full disk would."""
    original, calls = pd.DataFrame.to_parquet, []

    def to_parquet(frame: pd.DataFrame, *args: object, **kwargs: object) -> object:
        """The real write, except the second call fails."""
        calls.append(1)
        if len(calls) == 2:
            raise OSError("planted: disk full")
        return original(frame, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_parquet", to_parquet)


def test_a_stage_reads_back_as_written(cc_config: UseCaseConfig, tmp_path: Path) -> None:
    """Tables (list and nullable-int columns included), the stamped meta, the log and the
    resolved config survive the round trip; numpy datetimes are written as ISO strings."""
    result = _result(cc_config)
    paths = write_stage(result, str(tmp_path / "eda"), "eda")
    meta, tables = read_stage(str(tmp_path / "eda"), "eda")

    assert set(paths) == {
        "folder", "tables/ranking.parquet", "tables/cells.parquet", "eda.json", "log.json",
        "resolved_config.yml",
    }  # fmt: skip
    assert all(Path(path).exists() for path in paths.values())
    pd.testing.assert_frame_equal(tables["ranking"], result.tables["ranking"])
    pd.testing.assert_frame_equal(tables["cells"], result.tables["cells"])
    assert tables["ranking"]["flags"][0] == ["leakage.too_strong", "quality.high_missing"]
    assert meta["schema_version"] == 1 and meta["stage"] == "eda"
    assert meta["tables"] == ["ranking", "cells"]
    assert meta["framework_version"] == __version__ and meta["written_at"]
    assert (meta["snapshot"], meta["rows"], meta["ok"]) == ("2025-01-31", 7, True)
    assert meta["latest"] == "2025-01-31T00:00:00"
    assert meta["periods"] == ["2024-12-31T00:00:00", None]
    assert read_resolved_config(paths["resolved_config.yml"]) == cc_config
    assert Path(paths["log.json"]).read_text().count('"rows": 7') == 1


def test_a_nan_in_the_meta_fails_loud(cc_config: UseCaseConfig, tmp_path: Path) -> None:
    """A NaN would be written as a bare `NaN`, which strict JSON readers reject; nothing is left."""
    result = _result(cc_config)
    result.meta["concordance"] = np.float64("nan")
    with pytest.raises(ValueError, match="write None for a missing value"):
        write_stage(result, str(tmp_path / "eda"), "eda")
    assert list(tmp_path.iterdir()) == []


def test_a_failed_first_write_leaves_no_folder(
    cc_config: UseCaseConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write failing on its second table leaves neither the stage folder nor a temporary one."""
    _fail_second_parquet(monkeypatch)
    with pytest.raises(OSError, match="planted"):
        write_stage(_result(cc_config), str(tmp_path / "eda"), "eda")
    assert list(tmp_path.iterdir()) == []


def test_a_failed_rewrite_keeps_the_previous_stage(
    cc_config: UseCaseConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rerun failing mid-write leaves the previous run's folder whole and nothing beside it."""
    folder = str(tmp_path / "eda")
    write_stage(_result(cc_config, run=1), folder, "eda")
    _fail_second_parquet(monkeypatch)
    with pytest.raises(OSError, match="planted"):
        write_stage(_result(cc_config, run=2), folder, "eda")
    meta, tables = read_stage(folder, "eda")
    assert meta["run"] == 1 and set(tables) == {"ranking", "cells"}
    assert [path.name for path in tmp_path.iterdir()] == ["eda"]


def test_a_failed_swap_restores_the_previous_stage(
    cc_config: UseCaseConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When moving the new folder in fails after the old one was moved aside, the old one is
    moved back and the new one removed."""
    folder = str(tmp_path / "eda")
    write_stage(_result(cc_config, run=1), folder, "eda")
    original = Path.rename

    def rename(self: Path, target: Path) -> Path:
        """The real rename, except moving the written folder in fails."""
        if ".tmp-" in self.name:
            raise OSError("planted: rename failed")
        return original(self, target)

    monkeypatch.setattr(Path, "rename", rename)
    with pytest.raises(OSError, match="planted"):
        write_stage(_result(cc_config, run=2), folder, "eda")
    assert read_stage(folder, "eda")[0]["run"] == 1
    assert [path.name for path in tmp_path.iterdir()] == ["eda"]


def test_a_left_over_temporary_folder_is_refused(cc_config: UseCaseConfig, tmp_path: Path) -> None:
    """A `.tmp-*` or `.old-*` sibling from a crashed write is named, never reused or removed."""
    (tmp_path / "eda.old-123").mkdir()
    with pytest.raises(ValueError, match=r"eda\.old-123.*did not finish"):
        write_stage(_result(cc_config), str(tmp_path / "eda"), "eda")
    assert [path.name for path in tmp_path.iterdir()] == ["eda.old-123"]


def test_a_rerun_rewrites_the_folder_whole(cc_config: UseCaseConfig, tmp_path: Path) -> None:
    """A rerun's folder holds only its own files: a table the earlier run wrote is gone."""
    folder = str(tmp_path / "eda")
    write_stage(_result(cc_config, run=1), folder, "eda")
    rerun = _result(cc_config, run=2)
    del rerun.tables["cells"]
    write_stage(rerun, folder, "eda")
    meta, tables = read_stage(folder, "eda")
    assert meta["run"] == 2 and set(tables) == {"ranking"}
    assert [path.name for path in tmp_path.iterdir()] == ["eda"]


def test_a_text_file_is_committed_with_the_stage(cc_config: UseCaseConfig, tmp_path: Path) -> None:
    """A text file handed to `write_stage` (the report) is in the folder after the commit and in
    the returned paths; a name the stage writes itself or a subfolder fails, leaving nothing."""
    folder = str(tmp_path / "eda")
    paths = write_stage(_result(cc_config), folder, "eda", texts={"report.html": "<p>é</p>"})
    assert Path(paths["report.html"]).read_text(encoding="utf-8") == "<p>é</p>"
    for clash in ("log.json", "sub/report.html"):
        with pytest.raises(ValueError, match="plain file name"):
            write_stage(_result(cc_config), str(tmp_path / "other"), "eda", texts={clash: "x"})
    assert [path.name for path in tmp_path.iterdir()] == ["eda"]


def test_the_meta_may_not_set_the_stamp(cc_config: UseCaseConfig, tmp_path: Path) -> None:
    """`schema_version` and the other stamped keys come from `write_stage` only."""
    result = _result(cc_config)
    result.meta["schema_version"] = 2
    with pytest.raises(ValueError, match="schema_version"):
        write_stage(result, str(tmp_path / "eda"), "eda")
    assert list(tmp_path.iterdir()) == []


def test_read_stage_refuses_a_missing_stage_and_another_version(
    cc_config: UseCaseConfig, tmp_path: Path
) -> None:
    """A stage not run yet names the stage to run; a newer `schema_version` is refused."""
    folder = str(tmp_path / "eda")
    with pytest.raises(FileNotFoundError, match="run the eda stage first"):
        read_stage(folder, "eda")
    write_stage(_result(cc_config), folder, "eda")
    path = tmp_path / "eda" / "eda.json"
    path.write_text(path.read_text().replace('"schema_version": 1', '"schema_version": 2'))
    with pytest.raises(ValueError, match="schema_version 2"):
        read_stage(folder, "eda")


def test_read_stage_refuses_a_missing_or_extra_table(
    cc_config: UseCaseConfig, tmp_path: Path
) -> None:
    """A table the run wrote that is gone, or one it did not write, is named with the stage to
    rerun."""
    folder = str(tmp_path / "eda")
    paths = write_stage(_result(cc_config), folder, "eda")
    Path(paths["tables/cells.parquet"]).unlink()
    with pytest.raises(ValueError, match=r"lacks the eda tables \['cells'\].*rerun the eda"):
        read_stage(folder, "eda")
    pd.DataFrame({"x": [1]}).to_parquet(tmp_path / "eda" / "tables" / "cells.parquet")
    pd.DataFrame({"x": [1]}).to_parquet(tmp_path / "eda" / "tables" / "stray.parquet")
    with pytest.raises(ValueError, match=r"holds \['stray'\]"):
        read_stage(folder, "eda")


def test_a_uri_is_refused_until_the_hdfs_transport(cc_config: UseCaseConfig) -> None:
    """Local paths only in 0.x (T2, D-136)."""
    with pytest.raises(NotImplementedError, match="M2.4"):
        write_stage(_result(cc_config), "hdfs://namenode/root/eda", "eda")


def _resolved(variant: Callable[..., UseCaseConfig], **sections: object) -> UseCaseConfig:
    """A config variant carrying the housekeeping `resolve_config` would give it."""
    resolved = variant(**sections)
    resolved.housekeeping = {"data_definition_hash": data_definition_hash(resolved, "entity_a")}
    return resolved


def _eda_meta(resolved: UseCaseConfig) -> dict:
    """The meta EDA would store for the resolved config, as read back from its json."""
    meta = {
        "stage": "eda",
        "data_definition_hash": resolved.housekeeping["data_definition_hash"],
        **settings_meta(resolved, EDA_PATHS),
    }
    return json.loads(json.dumps(meta))


def test_check_upstream_names_the_changed_path(variant: Callable[..., UseCaseConfig]) -> None:
    """Unchanged settings pass; a changed kind, strata setting or validation period (it decides
    the compared periods, outside the data-definition hash) is refused naming its path."""
    meta = _eda_meta(_resolved(variant))
    check_upstream(meta, _resolved(variant), EDA_PATHS)
    moved = _resolved(variant, time={"validation_period": None})
    with pytest.raises(ValueError, match=r"time\.validation_period"):
        check_upstream(meta, moved, EDA_PATHS)
    kinds = _resolved(variant, features={"kinds": {"income": "categorical"}})
    with pytest.raises(ValueError, match=r"features\.kinds = \{\}.*'income': 'categorical'"):
        check_upstream(meta, kinds, EDA_PATHS)
    strata = _resolved(variant, strata={"max_levels": 5})
    with pytest.raises(ValueError, match="eda ran with strata = .*rerun eda"):
        check_upstream(meta, strata, EDA_PATHS)


def test_check_upstream_refuses_another_data_definition(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """Artifacts written for another data definition are refused, and so is a config that is not
    resolved (no hash to compare)."""
    resolved = _resolved(variant)
    meta = {**_eda_meta(resolved), "data_definition_hash": "0" * 64}
    with pytest.raises(ValueError, match="data definition 000000000000"):
        check_upstream(meta, resolved, EDA_PATHS)
    with pytest.raises(ValueError, match="needs the resolved config"):
        check_upstream(meta, variant(), EDA_PATHS)


def test_check_upstream_refuses_an_incomplete_meta_and_an_unknown_path(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """A meta without the keys it compares is refused naming them; a dotted path the config does
    not have is named in full."""
    resolved = _resolved(variant)
    meta = _eda_meta(resolved)
    del meta["stage"], meta["settings_digest"]
    with pytest.raises(ValueError, match=r"lacks \['stage', 'settings_digest'\]"):
        check_upstream(meta, resolved, EDA_PATHS)
    with pytest.raises(KeyError, match=r"no setting at eda\.binz"):
        check_upstream(_eda_meta(resolved), resolved, ["eda.binz"])


def test_remove_stage_removes_the_folder(cc_config: UseCaseConfig, tmp_path: Path) -> None:
    """A stage folder goes; a missing one is fine."""
    folder = str(tmp_path / "feature_checks")
    write_stage(_result(cc_config), folder, "feature_checks")
    remove_stage(folder)
    remove_stage(folder)
    assert list(tmp_path.iterdir()) == []
