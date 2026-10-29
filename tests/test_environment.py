"""Environment adapter: the environment file, Spark session, source reading and paths (D-130)."""

import threading
from pathlib import Path

import pytest
from pydantic import ValidationError
from pyspark.sql import SparkSession

from core_modelling.environment import (
    ENVIRONMENT_VARIABLE,
    EnvironmentConfig,
    Roots,
    Source,
    SparkSettings,
    audit_log_dir,
    data_path,
    get_spark_session,
    load_environment,
    read_source,
)
from synthetic.checks.mart import snapshot_columns
from synthetic.output import read_output

EXAMPLE = Path(__file__).resolve().parents[1] / "conf" / "base" / "environment.example.yml"


def _write_environment(folder: Path, text: str) -> str:
    """`text` written as `folder/environment.yml`; its path."""
    file = folder / "environment.yml"
    file.write_text(text)
    return str(file)


def test_example_file_loads_once_its_placeholders_are_filled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The example loads by path and through the variable: the local defaults and every source."""
    path = _write_environment(
        tmp_path, EXAMPLE.read_text().replace("/ABSOLUTE/PATH", str(tmp_path))
    )
    env = load_environment(path)
    assert env.schema_version == 1 and env.spark == SparkSettings()
    assert env.roots == Roots(data=f"{tmp_path}/data")
    assert sorted(env.sources["entity_a"]) == [
        "cc_acquisition_input",
        "retail_holdings",
        "retail_mart",
    ]
    assert (
        env.sources["entity_a"]["retail_mart"].path == f"{tmp_path}/data/01_raw/synthetic_dev/mart"
    )
    assert (env.collect_budget_gb, env.theme) == (1.5, None)
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, path)
    assert load_environment() == env


def test_load_environment_fails_loud(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither a path nor the variable, a non-mapping file, a missing schema_version, an unknown
    key and a relative parquet path each fail naming the problem."""
    monkeypatch.delenv(ENVIRONMENT_VARIABLE, raising=False)
    with pytest.raises(ValueError, match=ENVIRONMENT_VARIABLE):
        load_environment()
    path = _write_environment(tmp_path, "- a list\n")
    with pytest.raises(ValueError, match="environment.yml must be a YAML mapping, got list"):
        load_environment(path)
    path = _write_environment(tmp_path, f"roots: {{data: {tmp_path}}}\n")
    with pytest.raises(ValueError, match="environment file needs an integer schema_version"):
        load_environment(path)
    head = f"schema_version: 1\nroots: {{data: {tmp_path}}}\n"
    path = _write_environment(tmp_path, head + "training: {max_iter: 5}\n")
    with pytest.raises(ValueError, match="training\n  Extra inputs are not permitted"):
        load_environment(path)
    relative = {"format": "parquet", "path": "data/01_raw/synthetic_dev/mart"}
    path = _write_environment(
        tmp_path, head + f"sources: {{entity_a: {{retail_mart: {relative}}}}}\n"
    )
    with pytest.raises(ValueError, match="must be absolute or a URI"):
        load_environment(path)


def test_source_takes_the_locator_of_its_format() -> None:
    """A table source has no `path`, a parquet source no `table`; the feature store is not a format
    yet (OD-26)."""
    with pytest.raises(ValidationError, match="a table source takes `table`, not `path`"):
        Source(format="table", table="db.t", path="/x")
    with pytest.raises(ValidationError, match="a parquet source needs `path`"):
        Source(format="parquet", table="db.t")
    with pytest.raises(ValidationError, match="Input should be 'parquet' or 'table'"):
        Source(format="feature_store")


def test_spark_extra_refuses_named_and_fixed_keys() -> None:
    """A key with a named field, or one the framework fixes, is refused with the way to set it."""
    with pytest.raises(ValidationError, match="use the named field 'shuffle_partitions'"):
        SparkSettings(extra={"spark.sql.shuffle.partitions": "4"})
    with pytest.raises(ValidationError, match="'spark.ui.enabled' is fixed by the framework"):
        SparkSettings(extra={"spark.ui.enabled": "true"})
    assert SparkSettings(extra={"spark.sql.adaptive.enabled": "false"}).extra


def test_read_source_reads_the_written_mart(
    spark: SparkSession, unit_env: EnvironmentConfig, unit_output: tuple[str, dict]
) -> None:
    """The unit mart read through the environment: every month of the synthetic data, every
    row, the snapshot's columns (Spark puts the partition column last) and the written types."""
    sdf = read_source(spark, unit_env, "entity_a", "retail_mart")
    assert sdf.select("snapshot_month").distinct().count() == 24
    assert sdf.count() == len(read_output(unit_output[0], "mart", ["client_id"]))
    snapshot = snapshot_columns()
    assert sdf.columns == [c for c in snapshot if c != "snapshot_month"] + ["snapshot_month"]
    types = dict(sdf.dtypes)
    assert {t for c, t in types.items() if c.endswith("_flag")} == {"int"}
    assert (types["cc_limit"], types["snapshot_month"]) == ("decimal(18,2)", "date")


def test_read_source_fails_loud(spark: SparkSession, unit_env: EnvironmentConfig) -> None:
    """An unknown entity or name fails naming the known ones."""
    with pytest.raises(ValueError, match="unknown entity 'entity_b'.*\\['entity_a'\\]"):
        read_source(spark, unit_env, "entity_b", "retail_mart")
    with pytest.raises(ValueError, match="unknown source 'retail_unknown'.*retail_holdings"):
        read_source(spark, unit_env, "entity_a", "retail_unknown")


def test_second_session_request_checks_the_settings(
    spark: SparkSession, unit_env: EnvironmentConfig
) -> None:
    """The same settings return the running session; other settings fail naming the key and both
    values, never reusing the session quietly (D-100 (c))."""
    assert get_spark_session(unit_env) is spark
    other = unit_env.model_copy(update={"spark": SparkSettings(shuffle_partitions=16)})
    with pytest.raises(
        RuntimeError, match="spark.sql.shuffle.partitions: running '8', requested '16'"
    ):
        get_spark_session(other)


def _in_thread(env: EnvironmentConfig) -> SparkSession | Exception:
    """`get_spark_session(env)` run in another thread: its session or the exception it raised."""
    outcome: list[SparkSession | Exception] = []

    def run() -> None:
        """Collect the result or the error."""
        try:
            outcome.append(get_spark_session(env))
        except Exception as exc:  # noqa: BLE001 - the test asserts on it
            outcome.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    return outcome[0]


def test_running_session_is_seen_from_another_thread(
    spark: SparkSession, unit_env: EnvironmentConfig
) -> None:
    """The check is process-wide: a thread (a notebook's background cell, a parallel test) finds the
    running session and its settings, since getActiveSession() alone is thread-local."""
    assert _in_thread(unit_env) is spark
    other = unit_env.model_copy(update={"spark": SparkSettings(shuffle_partitions=16)})
    outcome = _in_thread(other)
    assert isinstance(outcome, RuntimeError) and "requested '16'" in str(outcome)


def test_data_path_joins_strings(unit_env: EnvironmentConfig) -> None:
    """Paths are string joins, so an hdfs:// root survives (pathlib would make it hdfs:/, T2)."""
    hdfs = unit_env.model_copy(update={"roots": Roots(data="hdfs://namenode/data/")})
    assert (
        data_path(hdfs, "04_feature", "cc_acquisition")
        == "hdfs://namenode/data/04_feature/cc_acquisition"
    )
    assert audit_log_dir(hdfs, "cc_acquisition", "entity_a", "0123abcd") == (
        "hdfs://namenode/data/04_feature/cc_acquisition/entity_a/0123abcd/decisions"
    )
    assert data_path(unit_env, "01_raw") == unit_env.roots.data + "/01_raw"
