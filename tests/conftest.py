"""Shared fixtures: one real local Spark session (never a stub, T15) and the canonical mart."""

from collections.abc import Iterator

import pandas as pd
import pytest
from pyspark.sql import SparkSession

from core_modelling.environment import _get_spark_session
from synthetic.generate import generate_mart


@pytest.fixture(scope="session")
def spark() -> Iterator[SparkSession]:
    """A local Spark session shared by the whole test run, stopped at the end."""
    session = _get_spark_session()
    yield session
    session.stop()


@pytest.fixture(scope="session")
def canonical() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """The canonical 100k mart with seed 0, generated once for every check test (read-only).

    The 5k preset has too few Private clients for many check rows to show anything.
    """
    return generate_mart("canonical", seed=0)
