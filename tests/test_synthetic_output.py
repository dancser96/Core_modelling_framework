"""Synthetic data on disk: what is written reads back as generated, and stale data fails loud."""

import json
from pathlib import Path

import pandas as pd
import pytest

from synthetic.generate import generate_mart
from synthetic.output import load_truth, read_output, write_mart


def test_written_dataset_reads_back_as_generated(
    unit_output: tuple[str, dict], unit: tuple[pd.DataFrame, pd.DataFrame, dict]
) -> None:
    """Mart, oracle and truth read back from disk equal the in-memory ones; flags are int32."""
    out_dir, truth = unit_output
    mart, oracle, memory_truth = unit
    written = read_output(out_dir, "mart")
    pd.testing.assert_frame_equal(written, mart)
    pd.testing.assert_frame_equal(read_output(out_dir, "oracle"), oracle)
    assert truth == memory_truth == load_truth(out_dir)
    flags = [c for c in written.columns if c.endswith("_flag")]
    assert flags and (written[flags].dtypes == "int32").all()


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


def test_switches_not_built_yet_fail_loud() -> None:
    """Dirty data and extra columns come with build step 5; asking for them now raises."""
    with pytest.raises(NotImplementedError):
        generate_mart("unit", dirty=True)
    with pytest.raises(NotImplementedError):
        generate_mart("unit", n_extra_columns=10)
