"""Shared fixtures: one real local Spark session (never a stub, T15), the synthetic datasets, the
config variants several modules read, EDA's frames and EDA's runs on the unit preset, and an
audit-log entry builder.

The unit preset is generated in memory once and written to disk once. The dev preset is written
once per session by a separate process, for the trap acceptance test (`test_traps.py`), with an
environment file on it. The canonical dataset is written once per session by a separate process
(`python -m synthetic`), for the slow tests (`pytest -m slow`). Each slow test checks one family
of it in a separate process too: a family's working set at the canonical size reaches several GB
(the panel is sorted, joined and turned into bools, copies of the columns read), so the test run
itself stays small and every family's memory goes back to the system when it ends.

EDA's frames and the two EDA runs (the card config and the regression variant) are built once per
session and shared: `test_eda.py` reads the runs and Feature Checks' tests run on a copy of their
data root. A shared value is read-only; a test that changes one, or a file under it, works on its
own copy.
"""

import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pandas as pd
import pytest
import yaml
from pyspark.sql import DataFrame, SparkSession

from core_modelling.artifacts import StageResult
from core_modelling.config import UseCaseConfig, load_config
from core_modelling.config.audit_log import LOG_SCHEMA_VERSION
from core_modelling.config.identities import HASH_VERSION
from core_modelling.config.replay import Entry
from core_modelling.dataset import Frames, build_frames
from core_modelling.eda import run_eda
from core_modelling.environment import (
    EnvironmentConfig,
    Roots,
    Source,
    feature_dir,
    get_spark_session,
)
from synthetic.generate import generate_mart
from synthetic.output import load_truth, write_mart

ENTITY = "entity_a"
# The regression variant's sections: card spend summed forward for holders, on the mart alone.
REGRESSION = {
    "task": "regression",
    "entities": {ENTITY: {"sources": {"features": ["retail_mart"], "targets": None}}},
    "data": {
        "model_input": None,
        "target": {"rule": "forward_sum", "column": "spend_cc_vol"},
        "eligibility": {
            "modelling": [
                {"name": "holders", "filter": "cc_flag = 1", "reason": "spend needs a card"}
            ]
        },
    },
}


@pytest.fixture(scope="session")
def spark(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SparkSession]:
    """A local Spark session shared by the whole test run, built through the adapter with its local
    defaults and stopped at the end."""
    env = EnvironmentConfig(
        schema_version=1, roots=Roots(data=str(tmp_path_factory.mktemp("data")))
    )
    session = get_spark_session(env)
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
def unit_env(
    unit_output: tuple[str, dict], tmp_path_factory: pytest.TempPathFactory
) -> EnvironmentConfig:
    """An environment whose `entity_a` sources are the written unit mart, holdings and
    feature-store extract, with the local Spark defaults and a temporary data root."""
    tables = {
        "retail_mart": "mart",
        "retail_holdings": "holdings",
        "retail_fs_extract": "fs_extract",
    }
    sources = {
        name: Source(format="parquet", path=f"{unit_output[0]}/{table}")
        for name, table in tables.items()
    }
    return EnvironmentConfig(
        schema_version=1,
        roots=Roots(data=str(tmp_path_factory.mktemp("data"))),
        sources={"entity_a": sources},
    )


@pytest.fixture(scope="session")
def cc_config() -> UseCaseConfig:
    """The walking skeleton's config, `tests/conf/cc_acquisition.yml` (a frozen copy of the
    shipped example, so a try-out in `conf/base/` changes no test), loaded; tests derive variants
    from its dump, re-validated, and never change it."""
    return load_config(Path(__file__).resolve().parents[1] / "tests/conf/cc_acquisition.yml")


@pytest.fixture(scope="session")
def variant(cc_config: UseCaseConfig) -> Callable[..., UseCaseConfig]:
    """A function giving `cc_config` with sections changed and re-validated: each keyword is a
    section (`time`, `data`, …) whose dict merges into it, nested dicts merging too, and any
    other value replaces it (`task="regression"`)."""

    def make(**sections: object) -> UseCaseConfig:
        """The changed config, validated."""
        data = cc_config.model_dump()
        for name, change in sections.items():
            data[name] = _merged(data[name], change) if isinstance(change, dict) else change
        return UseCaseConfig.model_validate(data)

    return make


def _merged(base: dict, change: dict) -> dict:
    """`base` with `change` merged in, dict values merged one level deeper."""
    out = dict(base)
    for key, value in change.items():
        nested = isinstance(value, dict) and isinstance(out.get(key), dict)
        out[key] = _merged(out[key], value) if nested else value
    return out


@pytest.fixture(scope="session")
def in_memory(variant: Callable[..., UseCaseConfig]) -> UseCaseConfig:
    """The skeleton's config without a model input: its frames are built in memory."""
    return variant(data={"model_input": None})


@pytest.fixture(scope="session")
def regression_cfg(variant: Callable[..., UseCaseConfig]) -> UseCaseConfig:
    """`REGRESSION` on a narrow candidate list that keeps the spend leak."""
    include = ["age", "income", "segment", "onboarding_channel", "employment_status",
               "cc_active_flag", "cc_bal*", "cc_limit", "spend_cc_*",
               "*_trap_spend_leak"]  # fmt: skip
    return variant(**REGRESSION, features={"candidates": {"include": include, "exclude": []}})


@pytest.fixture(scope="session")
def eda_frames(
    spark: SparkSession, unit_env: EnvironmentConfig, in_memory: UseCaseConfig
) -> Frames:
    """EDA's frames of `in_memory` on the unit preset, built once for every module."""
    return build_frames(in_memory, ENTITY, unit_env, spark, "eda")


@pytest.fixture(scope="session")
def eda_env(
    unit_env: EnvironmentConfig, tmp_path_factory: pytest.TempPathFactory
) -> EnvironmentConfig:
    """The unit environment on a data root that only the shared EDA runs write."""
    roots = unit_env.roots.model_copy(update={"data": str(tmp_path_factory.mktemp("eda_data"))})
    return unit_env.model_copy(update={"roots": roots})


def _run_with_stale_checks(
    cfg: UseCaseConfig, env: EnvironmentConfig, spark: SparkSession
) -> StageResult:
    """EDA after planting a Feature Checks folder, as an earlier run would have left it."""
    stale = Path(feature_dir(env, cfg, ENTITY, "feature_checks"))
    stale.mkdir(parents=True, exist_ok=True)
    (stale / "feature_checks.json").write_text("{}")
    return run_eda(cfg, ENTITY, env, spark)


@pytest.fixture(scope="session")
def eda_card(
    spark: SparkSession, eda_env: EnvironmentConfig, in_memory: UseCaseConfig
) -> StageResult:
    """The card config's EDA (every candidate, built in memory), run once on `eda_env`."""
    return _run_with_stale_checks(in_memory, eda_env, spark)


@pytest.fixture(scope="session")
def eda_regression(
    spark: SparkSession, eda_env: EnvironmentConfig, regression_cfg: UseCaseConfig
) -> StageResult:
    """The regression variant's EDA, run once on `eda_env`."""
    return _run_with_stale_checks(regression_cfg, eda_env, spark)


def build_entry(seq: int, op: str, **fields: object) -> Entry:
    """Audit-log entry `seq` built in code at the current hash and log versions: a person's, on
    Feature Checks' stage, unless `fields` say otherwise."""
    defaults = {"time": "2026-11-06T10:00:00+00:00", "by": {"kind": "person", "id": "someone"},
                "stage": "feature_checks", "reason": "r",
                "data_definition_hash": "d" * 64}  # fmt: skip
    versions = {"hash_version": HASH_VERSION, "log_schema_version": LOG_SCHEMA_VERSION}
    return Entry(seq=seq, op=op, **versions, **{**defaults, **fields})


@pytest.fixture
def write_sources(spark: SparkSession, tmp_path: Path) -> Callable[..., EnvironmentConfig]:
    """A function writing keyed panels (`unit_id`, `period`, …) to parquet under the config's key
    names (`client_id`, `snapshot_month`) as `entity_a`'s sources of a new environment on the
    test's folder; other keywords are environment settings (`collect_budget_gb=…`)."""

    def write(panels: dict[str, DataFrame], **settings: object) -> EnvironmentConfig:
        """The environment whose sources are the panels written."""
        sources = {}
        for name, panel in panels.items():
            path = str(tmp_path / name)
            raw = panel.withColumnRenamed("unit_id", "client_id")
            raw.withColumnRenamed("period", "snapshot_month").write.parquet(path)
            sources[name] = Source(format="parquet", path=path)
        return EnvironmentConfig(
            schema_version=1,
            roots=Roots(data=str(tmp_path)),
            sources={"entity_a": sources},
            **settings,
        )

    return write


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
def dev_output(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, dict]:
    """The dev preset (seed 0) written by a separate process, which keeps the generator's memory
    (about 1.2 GB) out of the test run: (out_dir, truth)."""
    out_dir = str(tmp_path_factory.mktemp("dev_output"))
    command = [sys.executable, "-m", "synthetic", "--preset", "dev", "--seed", "0"]
    subprocess.run([*command, "--out", out_dir], check=True)
    return out_dir, load_truth(out_dir)


def write_environment_file(out_dir: str, root: Path) -> Path:
    """Write `root/environment.yml`: `entity_a`'s sources are the mart, holdings and
    feature-store extract written to `out_dir` and the model input under the data root
    `root/data`, with the local Spark defaults (so `run` reuses the `spark` session)."""
    data = str(root / "data")
    tables = {"retail_mart": "mart", "retail_holdings": "holdings",
              "retail_fs_extract": "fs_extract"}  # fmt: skip
    sources = {name: {"format": "parquet", "path": f"{out_dir}/{table}"}
               for name, table in tables.items()}  # fmt: skip
    model_input = f"{data}/05_model_input/retail_acquisition"
    sources["retail_acquisition_input"] = {"format": "parquet", "path": model_input}
    path = root / "environment.yml"
    content = {"schema_version": 1, "roots": {"data": data}, "sources": {"entity_a": sources}}
    path.write_text(yaml.safe_dump(content))
    return path


@pytest.fixture(scope="session")
def dev_env_file(dev_output: tuple[str, dict], tmp_path_factory: pytest.TempPathFactory) -> str:
    """An environment file on the written dev preset under a temporary data root."""
    return str(write_environment_file(dev_output[0], tmp_path_factory.mktemp("dev_env")))


@pytest.fixture(scope="session")
def canonical_checks(
    canonical_output: tuple[str, dict, dict], tmp_path_factory: pytest.TempPathFactory
) -> Callable[..., pd.DataFrame]:
    """A function giving one family's check table on the canonical dataset, run in a separate
    process the way `checks.suite.write_checks` runs it (the mart family on its client sample)."""
    folder = tmp_path_factory.mktemp("canonical_checks")

    def check_family(family: str) -> pd.DataFrame:
        """The family's check table, from a separate process."""
        path = Path(folder, f"{family}.parquet")
        command = [sys.executable, "-m", "synthetic.checks.suite", canonical_output[0], family]
        subprocess.run([*command, str(path)], check=True)
        return pd.read_parquet(path)

    return check_family
