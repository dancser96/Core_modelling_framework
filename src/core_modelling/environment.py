"""Environment adapter: the one seam between framework logic and where it runs (laptop vs bank).

Framework code never checks where it runs; it asks this module, and `conf/local/` decides. For now
it creates the local Spark session the tests use and reads a logical source through a mapping file
(`conf/local/sources.yml`, example in `conf/base/`); settings from `conf/local/`, file transport
(local paths and `hdfs://` alike), path building and the full source resolution arrive in M2
(docs/components/environment.md).
"""

import yaml
from pyspark.sql import DataFrame, SparkSession

# Local-mode defaults, sized for an 8 GB laptop. conf/local/ will override them (M2).
_LOCAL_SPARK_SETTINGS = {
    "spark.master": "local[*]",
    "spark.app.name": "core_modelling",
    "spark.driver.memory": "2g",
    "spark.sql.shuffle.partitions": "8",
    "spark.sql.session.timeZone": "UTC",  # independent of the laptop; conf/local sets the bank's
    "spark.sql.execution.arrow.pyspark.enabled": "true",
    # Without this, a failing Arrow conversion silently falls back to the slow path.
    "spark.sql.execution.arrow.pyspark.fallback.enabled": "false",
    "spark.ui.enabled": "false",  # no port clashes between parallel test runs
}


def _get_spark_session() -> SparkSession:
    """Create or get the local Spark session."""
    return SparkSession.builder.config(map=_LOCAL_SPARK_SETTINGS).getOrCreate()


def _load_sources(path: str) -> dict:
    """The source mapping file at `path`: logical name → {format, path or table}.

    A missing file raises; so does a source without a `format`.
    """
    with open(path) as file:  # a local file: conf/local/ is never on HDFS
        sources = yaml.safe_load(file)
    if not isinstance(sources, dict):
        raise ValueError(f"{path} must map logical source names to sources")
    missing = [
        name
        for name, source in sources.items()
        if not isinstance(source, dict) or "format" not in source
    ]
    if missing:
        raise ValueError(f"{path}: sources without a format: {missing}")
    return sources


def _read_source(spark: SparkSession, source: dict) -> DataFrame:
    """One source of the mapping as a Spark DataFrame: parquet by `path`, or a table by `table`."""
    if source["format"] == "parquet":
        return spark.read.parquet(source["path"])
    if source["format"] == "table":
        return spark.table(source["table"])
    raise ValueError(f"unknown source format {source['format']!r}: expected parquet or table")
