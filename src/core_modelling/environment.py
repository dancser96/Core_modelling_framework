"""Environment adapter: the one seam between framework logic and where it runs (laptop vs bank).

Framework code never checks where it runs; it asks this module, and `conf/local/` decides. For now
it only creates the local Spark session the tests use; settings from `conf/local/`, file transport
(local paths and `hdfs://` alike), path building and source resolution arrive in M2
(docs/components/environment.md).
"""

from pyspark.sql import SparkSession

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
