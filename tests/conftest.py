"""Shared fixtures: one real local Spark session (never a stub, T15) and the synthetic datasets.

The unit preset is generated in memory once and written to disk once. The canonical dataset is
written once per session by a separate process (`python -m synthetic`), for the slow tests
(`pytest -m slow`). Each slow test checks one family of it in a separate process too: a family's
working set at the canonical size reaches several GB (the panel is sorted, joined and turned into
bools, copies of the columns read), so the test run itself stays small and every family's memory
goes back to the system when it ends.
"""

import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

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
    command = [sys.executable, "-m", "synthetic", "--preset", "canonical", "--seed", "0"]
    start = time.perf_counter()
    process = subprocess.Popen([*command, "--out", out_dir])
    # wait4 gives this child's own peak, whatever other processes the test run started.
    _, status, usage = os.wait4(process.pid, 0)
    seconds = time.perf_counter() - start
    process.returncode = os.waitstatus_to_exitcode(status)  # reaped here, not by Popen
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, process.args)
    # ru_maxrss is in bytes on macOS and in KiB on Linux.
    peak_bytes = usage.ru_maxrss if sys.platform == "darwin" else usage.ru_maxrss * 1024
    return out_dir, load_truth(out_dir), {"seconds": seconds, "peak_bytes": peak_bytes}


@pytest.fixture(scope="session")
def canonical_checks(
    canonical_output: tuple[str, dict, dict], tmp_path_factory: pytest.TempPathFactory
) -> Callable[..., pd.DataFrame]:
    """A function giving one family's check table on the canonical dataset, run in a separate
    process the way `check_suite.write_checks` runs it (the mart family on its client sample)."""
    folder = tmp_path_factory.mktemp("canonical_checks")

    def check_family(family: str) -> pd.DataFrame:
        """The family's check table, from a separate process."""
        path = Path(folder, f"{family}.parquet")
        command = [sys.executable, "-m", "synthetic.check_suite", canonical_output[0], family]
        subprocess.run([*command, str(path)], check=True)
        return pd.read_parquet(path)

    return check_family
