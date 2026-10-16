"""Shared fixtures: one real local Spark session (never a stub, T15) and the synthetic datasets.

The unit preset is generated in memory once and written to disk once; the canonical dataset is
written once per session by a separate process, for the slow tests (`pytest -m slow`), which read
only the columns each check family declares.
"""

import resource
import subprocess
import sys
import time
from collections.abc import Iterator

import pandas as pd
import pytest
from pyspark.sql import SparkSession

from core_modelling.environment import _get_spark_session
from synthetic.generate import generate_mart
from synthetic.output import load_truth, write_mart


@pytest.fixture(scope="session")
def spark() -> Iterator[SparkSession]:
    """A local Spark session shared by the whole test run, stopped at the end."""
    session = _get_spark_session()
    yield session
    session.stop()


@pytest.fixture(scope="session")
def unit() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """The unit preset with seed 0 in memory: (mart, oracle, truth), read-only."""
    return generate_mart("unit", seed=0)


@pytest.fixture(scope="session")
def unit_output(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, dict]:
    """The unit preset with seed 0 written to a temporary folder: (out_dir, truth)."""
    out_dir = str(tmp_path_factory.mktemp("unit_output"))
    return out_dir, write_mart(out_dir, preset="unit", seed=0)


@pytest.fixture(scope="session")
def canonical_output(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, dict, dict]:
    """The canonical dataset (seed 0) written by a separate process: (out_dir, truth, timing).

    The separate process keeps the generator's memory out of the test run and lets its wall time
    and peak memory (`timing`: seconds, peak_bytes) be measured on their own.
    """
    out_dir = str(tmp_path_factory.mktemp("canonical_output"))
    code = (
        "from synthetic.output import write_mart; "
        f"write_mart({out_dir!r}, preset='canonical', seed=0)"
    )
    start = time.perf_counter()
    subprocess.run([sys.executable, "-c", code], check=True)
    seconds = time.perf_counter() - start
    # The largest finished child process of the test run: the generator, by far. ru_maxrss is in
    # bytes on macOS and in KiB on Linux.
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    peak_bytes = peak if sys.platform == "darwin" else peak * 1024
    return out_dir, load_truth(out_dir), {"seconds": seconds, "peak_bytes": peak_bytes}
