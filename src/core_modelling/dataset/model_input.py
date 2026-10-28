"""The model input: the panel saved once and read by every later stage (D-131).

`save_model_input` writes the panel of `panel.build_panel` (the keys, the candidates, the
pre-model tags, `eligible`, `target`, `split`) to the path the environment file maps for
`data.model_input`, partitioned by month, with `_model_input.json` in the same folder holding
the hashes, the lineage, the candidates, the tags, `data.split` and the logs. The folder is
rewritten whole on every save, so a rerun never leaves months of an earlier definition behind
and a failed sidecar write leaves a table without one, refused on read. The sidecar's name
starts with `_` so Spark's listing skips it, and never with `_metadata`, which Spark reads as a
parquet summary (T21). Reading checks the sidecar first: another schema or hash version, another
data definition or another split is refused naming `save_model_input`, the rebuild being the
migration until release 1.0. Saving is the moment the config freezes (D-125). The path is local
until the M2.4 transport.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from core_modelling import __version__
from core_modelling.config import UseCaseConfig
from core_modelling.config.identities import HASH_VERSION, data_definition_hash
from core_modelling.dataset.panel import PANEL_META_KEYS, build_panel
from core_modelling.environment import EnvironmentConfig

MODEL_INPUT_SCHEMA_VERSION = 1  # bumped when the sidecar's keys or the `Split` fields change
METADATA_FILE = "_model_input.json"  # never `_metadata…`: Spark reads that as a parquet summary


def _model_input_path(cfg: UseCaseConfig, entity: str, env: EnvironmentConfig) -> str:
    """Where the environment file maps `data.model_input` for `entity`: a parquet path, local
    until the M2.4 transport (T2)."""
    name = cfg.data.model_input
    if name is None:
        raise ValueError("the config sets no data.model_input: name the model input to save there")
    sources = env.sources.get(entity, {})
    if name not in sources:
        raise ValueError(
            f"the environment file maps no source {name!r} for entity {entity!r}; add the model "
            f"input's path under sources.{entity}"
        )
    source = sources[name]
    if source.format != "parquet":
        raise ValueError(f"model input {name!r} must be a parquet source, not {source.format!r}")
    if "://" in source.path:
        raise NotImplementedError(
            f"model input at {source.path}: the hdfs:// transport arrives with M2.4; use a local "
            "path until then"
        )
    return source.path


def save_model_input(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession
) -> str:
    """The panel written as the model input at the path the environment file maps for
    `data.model_input`, partitioned by month, with `_model_input.json`; the path written. The
    config freezes here (D-125)."""
    path = _model_input_path(cfg, entity, env)
    table, log, meta = build_panel(cfg, entity, env, spark)
    table.write.mode("overwrite").partitionBy("month").parquet(path)  # the folder, whole
    metadata = {
        "schema_version": MODEL_INPUT_SCHEMA_VERSION,
        "framework_version": __version__,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "use_case": cfg.use_case,
        "entity": entity,
        "model_input": cfg.data.model_input,
        **meta,
        "split": cfg.data.split.model_dump(mode="json"),
        "columns": table.columns,
        "log": log,
    }
    Path(path, METADATA_FILE).write_text(json.dumps(metadata, indent=2))
    print(f"model input saved: {path}")
    return path


def read_model_input_metadata(cfg: UseCaseConfig, entity: str, env: EnvironmentConfig) -> dict:
    """The saved model input's metadata, checked: a missing table, another schema or hash
    version, another data definition or another split fail naming `save_model_input`."""
    path = _model_input_path(cfg, entity, env)
    file = Path(path, METADATA_FILE)
    if not file.is_file():
        raise ValueError(
            f"no model input at {path}: save it with save_model_input (the Target Factory "
            "notebook, or `run --stages target_factory`)"
        )
    metadata = json.loads(file.read_text())
    if metadata.get("schema_version") != MODEL_INPUT_SCHEMA_VERSION:
        raise ValueError(
            f"model input at {path} has schema_version {metadata.get('schema_version')}; this "
            f"version reads {MODEL_INPUT_SCHEMA_VERSION}; rebuild it with save_model_input"
        )
    if metadata["hash_version"] != HASH_VERSION:
        raise ValueError(
            f"model input at {path} was hashed with hash_version {metadata['hash_version']}, "
            f"this version uses {HASH_VERSION}; rebuild it with save_model_input"
        )
    if metadata["data_definition_hash"] != data_definition_hash(cfg, entity):
        raise ValueError(
            f"model input at {path} was built from another data definition; rebuild it with "
            "save_model_input"
        )
    split = cfg.data.split.model_dump(mode="json")
    if metadata["split"] != split:
        raise ValueError(
            f"model input at {path} was split with other settings ({metadata['split']}) than "
            f"data.split ({split}); rebuild it with save_model_input"
        )
    return metadata


def saved_candidates(cfg: UseCaseConfig, entity: str, env: EnvironmentConfig) -> list[str] | None:
    """The saved model input's candidate list for the audit log's feature decisions, or None
    when the config names no model input or none is saved yet; a model input the environment
    doesn't map, or one saved from another data definition or split, fails loud."""
    if cfg.data.model_input is None:
        return None
    if not Path(_model_input_path(cfg, entity, env), METADATA_FILE).is_file():
        return None
    return read_model_input_metadata(cfg, entity, env)["candidates"]


def read_model_input(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession
) -> tuple[DataFrame, list[dict], dict]:
    """The saved model input as the panel (its columns in the saved order), with the logs and the
    meta it was saved with."""
    metadata = read_model_input_metadata(cfg, entity, env)
    saved = spark.read.parquet(_model_input_path(cfg, entity, env))
    # The partition column comes back as a date only while Spark's partition type inference is
    # on (its default); cast, so a session without it gives the same frames.
    panel = saved.withColumn("month", F.col("month").cast("date")).select(metadata["columns"])
    meta = {key: metadata[key] for key in PANEL_META_KEYS}
    print(f"model input read: {metadata['model_input']} built {metadata['built_at']} by "
          f"core_modelling {metadata['framework_version']}")  # fmt: skip
    return panel, list(metadata["log"]), meta
