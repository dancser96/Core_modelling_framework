"""Synthetic data on disk: what is written reads back as generated, stale data fails loud, the
command line writes a dataset, and the canonical dataset fits its time and memory budget."""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from synthetic.output import load_truth, read_output, write_mart


def test_written_dataset_reads_back_as_generated(
    unit_output: tuple[str, dict], unit: tuple[pd.DataFrame, pd.DataFrame, dict]
) -> None:
    """Mart, oracle and truth read back from disk equal the in-memory ones (the decimal
    `cc_limit` back as float); flags are int32."""
    out_dir, truth = unit_output
    mart, oracle, memory_truth = unit
    written = read_output(out_dir, "mart")
    pd.testing.assert_frame_equal(written, mart)
    pd.testing.assert_frame_equal(read_output(out_dir, "oracle"), oracle)
    assert truth == memory_truth == load_truth(out_dir)
    flags = [c for c in written.columns if c.endswith("_flag")]
    assert flags and (written[flags].dtypes == "int32").all()


def test_client_sample_reads_every_month_of_a_fixed_sample(
    unit_output: tuple[str, dict], unit: tuple[pd.DataFrame, pd.DataFrame, dict]
) -> None:
    """`client_sample` 5 reads exactly the rows of the clients whose id is a multiple of 5."""
    columns = ["client_id", "snapshot_month", "cc_limit"]
    sample = read_output(unit_output[0], "mart", columns, client_sample=5)
    mart = unit[0]
    expected = mart.loc[mart["client_id"] % 5 == 0, columns].reset_index(drop=True)
    pd.testing.assert_frame_equal(sample, expected)


def test_write_refuses_a_folder_holding_a_dataset(unit_output: tuple[str, dict]) -> None:
    """Writing over a dataset would mix months of two runs, so it raises before generating."""
    with pytest.raises(FileExistsError):
        write_mart(unit_output[0], preset="unit")


def test_load_truth_refuses_another_generator_version(
    unit_output: tuple[str, dict], tmp_path: Path
) -> None:
    """A dataset written by another generator version is stale and must not be read."""
    stale = dict(unit_output[1], generator_version="0.0.0")
    (tmp_path / "truth.json").write_text(json.dumps(stale))
    with pytest.raises(ValueError, match="generate it again"):
        load_truth(str(tmp_path))


@pytest.mark.parametrize("library", ["numpy", "scipy"])
def test_load_truth_refuses_another_library_minor_version(
    unit_output: tuple[str, dict], tmp_path: Path, library: str
) -> None:
    """The seed-to-data mapping depends on numpy and scipy: data written under another major.minor
    version is stale; another patch version is not."""
    truth = unit_output[1]
    major, minor, *_ = truth["versions"][library].split(".")
    path = tmp_path / "truth.json"
    other_minor = {**truth["versions"], library: f"{major}.{int(minor) + 1}.0"}
    path.write_text(json.dumps(dict(truth, versions=other_minor)))
    with pytest.raises(ValueError, match="generate it again"):
        load_truth(str(tmp_path))
    other_patch = {**truth["versions"], library: f"{major}.{minor}.999"}
    path.write_text(json.dumps(dict(truth, versions=other_patch)))
    assert load_truth(str(tmp_path))["versions"] == other_patch


def test_dirty_refuses_a_panel_larger_than_unit(tmp_path: Path) -> None:
    """Dirty data holds the whole panel in memory, so a larger size raises before generating."""
    with pytest.raises(ValueError, match="whole panel in memory"):
        write_mart(str(tmp_path), preset="unit", n_months=25, dirty=True)


def test_command_line_writes_a_dataset(tmp_path: Path) -> None:
    """`python -m synthetic` writes a dataset of the size asked for and prints its rows."""
    out_dir = str(tmp_path / "unit_3_months")
    args = ["--preset", "unit", "--n-months", "3", "--seed", "0", "--out", out_dir]
    run = subprocess.run(
        [sys.executable, "-m", "synthetic", *args], check=True, capture_output=True, text=True
    )
    keys = read_output(out_dir, "mart", ["client_id", "snapshot_month"])
    assert keys["snapshot_month"].nunique() == load_truth(out_dir)["n_months"] == 3
    assert f"{len(keys):,} rows" in run.stdout


@pytest.mark.slow
def test_canonical_fits_its_budget(canonical_output: tuple[str, dict, dict]) -> None:
    """The canonical dataset is written in at most 10 minutes with at most 3 GB of peak memory
    (test_harness.md, "Presets and budgets")."""
    timing = canonical_output[2]
    assert timing["seconds"] <= 600, timing
    assert timing["peak_bytes"] <= 3 * 1024**3, timing
