"""Environment adapter: the one seam between framework logic and where it runs (laptop vs bank).

Framework code never checks where it runs; it asks this module, and the environment file decides
(`conf/local/environment.yml`, gitignored; the example is `conf/base/environment.example.yml`,
D-130). The file has its own schema, so a modelling setting can't hide in it: the Spark settings,
the storage roots, the physical source behind every logical name per entity, the collect budget
and the report theme. From it come the Spark session, source reading and path construction. The
`hdfs dfs` transport and the registered / production roots arrive with M2.4
(docs/components/environment.md).

The adapter keeps its own `extra="forbid"` base instead of importing `config.schema.StrictModel`:
it must not depend on the config schema, so an environment fact can never be validated as a
modelling setting or the reverse. The one shared piece is the version-migration mechanics in
`config.migrations`.
"""

import os
import re
from collections.abc import Callable
from typing import Annotated, Literal, Self

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    ValidationError,
    field_validator,
    model_validator,
)
from pyspark.sql import DataFrame, SparkSession

from core_modelling.config.migrations import migrate

ENVIRONMENT_VARIABLE = "CORE_MODELLING_ENVIRONMENT"
ENVIRONMENT_SCHEMA_VERSION = 1
ENVIRONMENT_MIGRATIONS: dict[int, Callable[[dict], dict]] = {}
_URI = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
# Spark keys the file sets through a named field, and the ones the framework fixes.
NAMED_SPARK_KEYS = {
    "spark.master": "master",
    "spark.driver.memory": "driver_memory",
    "spark.sql.shuffle.partitions": "shuffle_partitions",
    "spark.sql.session.timeZone": "time_zone",
}
FIXED_SPARK_KEYS = {
    "spark.app.name",
    "spark.sql.execution.arrow.pyspark.enabled",
    "spark.sql.execution.arrow.pyspark.fallback.enabled",
    "spark.ui.enabled",
}


def _check_absolute(path: str) -> str:
    """`path` unchanged when absolute or a URI; a relative one would resolve against the working
    directory (T5)."""
    if not (path.startswith("/") or _URI.match(path)):
        raise ValueError(f"{path!r} must be absolute or a URI (scheme://...), not relative")
    return path


AbsolutePath = Annotated[str, AfterValidator(_check_absolute)]


class SparkSettings(BaseModel):
    """The Spark session's settings; `extra` holds any other `spark.*` key verbatim."""

    model_config = ConfigDict(extra="forbid")
    master: str = "local[*]"
    driver_memory: str = "2g"
    shuffle_partitions: int = 8
    time_zone: str = "UTC"
    extra: dict[str, str] = {}

    @field_validator("extra")
    @classmethod
    def _check_extra_keys(cls, value: dict[str, str]) -> dict[str, str]:
        """A key with a named field, or one the framework fixes, can't be set through `extra`."""
        for key in value:
            if key in NAMED_SPARK_KEYS:
                raise ValueError(
                    f"spark.extra {key!r}: use the named field {NAMED_SPARK_KEYS[key]!r}"
                )
            if key in FIXED_SPARK_KEYS:
                raise ValueError(f"spark.extra {key!r} is fixed by the framework")
        return value


class Roots(BaseModel):
    """Storage roots: `data` carries the layers of data/README.md; the tiers come with M2.4."""

    model_config = ConfigDict(extra="forbid")
    data: AbsolutePath
    registered: AbsolutePath | None = None
    production: AbsolutePath | None = None


class Source(BaseModel):
    """One physical source: parquet at `path` or a Hive `table` (the feature store: OD-26)."""

    model_config = ConfigDict(extra="forbid")
    format: Literal["parquet", "table"]
    path: AbsolutePath | None = None
    table: str | None = None

    @model_validator(mode="after")
    def _check_locator(self) -> Self:
        """A parquet source takes `path`, a table source takes `table`, never the other."""
        needed, other = ("path", "table") if self.format == "parquet" else ("table", "path")
        if getattr(self, needed) is None:
            raise ValueError(f"a {self.format} source needs `{needed}`")
        if getattr(self, other) is not None:
            raise ValueError(f"a {self.format} source takes `{needed}`, not `{other}`")
        return self


class EnvironmentConfig(BaseModel):
    """The environment file (D-130): where the framework runs, never what the model is."""

    model_config = ConfigDict(extra="forbid")
    schema_version: int
    spark: SparkSettings = SparkSettings()
    roots: Roots
    sources: dict[str, dict[str, Source]] = {}  # entity → logical name → physical source
    collect_budget_gb: float = 1.5
    theme: str | None = None


def load_environment(path: str | None = None) -> EnvironmentConfig:
    """The environment file at `path`, else at `$CORE_MODELLING_ENVIRONMENT`; neither fails loud."""
    path = path or os.environ.get(ENVIRONMENT_VARIABLE)
    if not path:
        raise ValueError(
            "no environment file: pass its path or set the "
            f"{ENVIRONMENT_VARIABLE} variable (conf/local/environment.yml, D-130)"
        )
    with open(path) as file:  # a local file: conf/local/ is never on HDFS
        data = yaml.safe_load(file)
    if not isinstance(data, dict):
        raise ValueError(
            f"environment file {path} must be a YAML mapping, got {type(data).__name__}"
        )
    data = migrate(data, ENVIRONMENT_MIGRATIONS, ENVIRONMENT_SCHEMA_VERSION, "environment file")
    try:
        return EnvironmentConfig.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"environment file {path}: {exc}") from exc


def _spark_settings(spark: SparkSettings) -> dict[str, str]:
    """The session's settings by Spark key: the file's, the framework's fixed ones, then `extra`."""
    return {
        "spark.master": spark.master,
        "spark.app.name": "core_modelling",
        "spark.driver.memory": spark.driver_memory,
        "spark.sql.shuffle.partitions": str(spark.shuffle_partitions),
        "spark.sql.session.timeZone": spark.time_zone,
        "spark.sql.execution.arrow.pyspark.enabled": "true",
        # Without this, a failing Arrow conversion silently falls back to the slow path.
        "spark.sql.execution.arrow.pyspark.fallback.enabled": "false",
        "spark.ui.enabled": "false",  # no port clashes between parallel runs
        **spark.extra,
    }


def _running_value(session: SparkSession, key: str) -> str | None:
    """The running session's value of `key`: a `spark.sql.*` key from the runtime conf, any other
    from the JVM's SparkConf (the runtime conf echoes a later getOrCreate's static values)."""
    if key.startswith("spark.sql."):
        return session.conf.get(key, None)
    return session.sparkContext.getConf().get(key)


def get_spark_session(env: EnvironmentConfig) -> SparkSession:
    """The Spark session with `env.spark`'s settings: created when none is active, else the active
    one once every setting matches; a difference fails loud, never reuses quietly (D-100 (c))."""
    settings = _spark_settings(env.spark)
    # getActiveSession() is thread-local; the one process-wide handle in PySpark 3.4 is this
    # private attribute, set at creation and cleared by stop().
    session = SparkSession._instantiatedSession
    if session is None:
        return SparkSession.builder.config(map=settings).getOrCreate()
    differences = [
        f"{key}: running {_running_value(session, key)!r}, requested {value!r}"
        for key, value in settings.items()
        if _running_value(session, key) != value
    ]
    if differences:
        raise RuntimeError(
            "a Spark session is already running with other settings; stop it (spark.stop()) or "
            "restart the kernel before changing them:\n  " + "\n  ".join(differences)
        )
    return session


def _find_source(env: EnvironmentConfig, entity: str, name: str) -> Source:
    """`env.sources[entity][name]`; an unknown entity or name fails naming the known ones."""
    if entity not in env.sources:
        raise ValueError(
            f"unknown entity {entity!r}: the environment file has {sorted(env.sources)}"
        )
    if name not in env.sources[entity]:
        known = sorted(env.sources[entity])
        raise ValueError(f"unknown source {name!r} for entity {entity!r}: the file has {known}")
    return env.sources[entity][name]


def read_source(spark: SparkSession, env: EnvironmentConfig, entity: str, name: str) -> DataFrame:
    """The logical source `name` of `entity` as a Spark DataFrame, as the environment maps it."""
    source = _find_source(env, entity, name)
    if source.format == "parquet":
        return spark.read.parquet(source.path)
    return spark.table(source.table)


def data_path(env: EnvironmentConfig, layer: str, *parts: str) -> str:
    """`roots.data/<layer>/<parts…>`, joined as strings so an `hdfs://` root survives (T2)."""
    return "/".join([env.roots.data.rstrip("/"), layer, *parts])


def audit_log_dir(
    env: EnvironmentConfig, use_case: str, entity: str, data_definition_hash: str
) -> str:
    """Where the decision audit log of one use case, entity and data definition lives."""
    return data_path(env, "04_feature", use_case, entity, data_definition_hash, "decisions")
