"""The model input: the sources joined with one target column per use case, saved once and
prepared on read by every use case's own config (D-131; the Stage 1 addendum, section B).

`save_model_input` writes the panel of `panel.load_panel` (the keys, every feature column, one
`target_<use_case>` column per config) to the path the environment file maps for
`data.model_input`, partitioned by `period`, with `_model_input.json` in the same folder holding
the definition the table was built from, per use case its target's spec hash, lineage, windows,
null share and the target source's last period, the columns and the join log. Everything
config-driven after the join (eligibility, the candidates, the contract, the split) is derived
on read from the reader's config by `panel.prepare_panel`, so a changed eligibility, window,
split or candidate list never forces a rebuild, and one table serves several use cases. The
folder is rewritten whole on every save, so a rerun never leaves periods of an earlier
definition behind, and a failed sidecar write leaves a table without one, refused on read. The
sidecar's name starts with `_` so Spark's listing skips it, and never with `_metadata`, which
Spark reads as a parquet summary (T21). Reading checks the sidecar first: another schema or
hash version, another join definition, a use case the table lacks, another target spec, a
target source ending before the validation period's labels are known, or periods it doesn't
cover are refused naming `save_model_input`, the rebuild being the migration until release
1.0. Saving is the moment the configs freeze (D-125). The path is local until the M2.4
transport.
"""

import json
from datetime import date, datetime, timezone
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from core_modelling import __version__
from core_modelling.config import UseCaseConfig
from core_modelling.config.identities import HASH_VERSION, target_spec_hash
from core_modelling.dataset.eligibility import resolve_candidates
from core_modelling.dataset.panel import load_panel, prepare_panel, read_side_columns
from core_modelling.environment import EnvironmentConfig
from core_modelling.periods import period_spec

# Bumped when the sidecar's keys, the log entries' keys or a column's meaning change: an older
# table is refused by name, not by chance. 3: the table is the sources joined plus one
# `target_<use_case>` column per use case; eligibility, candidates, contract and split are
# derived on read, `period` is the unit, the sidecar holds the join definition and `targets`
# (10-28). 2: eligibility entries carry `kind`, labels in every month with a complete window,
# the draw in [0, 1) (10-28).
MODEL_INPUT_SCHEMA_VERSION = 3
METADATA_FILE = "_model_input.json"  # never `_metadata…`: Spark reads that as a parquet summary
JOIN_FIELDS = ("sources", "keys", "period")  # the sidecar's definition a reader must share


def _model_input_path(cfg: UseCaseConfig, entity: str, env: EnvironmentConfig) -> str:
    """Where the environment file maps `data.model_input` for `entity`: a parquet path, local
    until the M2.4 transport (T2)."""
    name = cfg.data.model_input
    if name is None:
        raise ValueError(
            f"the config {cfg.use_case!r} sets no data.model_input: name the model input to "
            "save there"
        )
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
    cfgs: UseCaseConfig | list[UseCaseConfig],
    entity: str,
    env: EnvironmentConfig,
    spark: SparkSession,
) -> str:
    """The panel of the configs (one, or a list sharing one data definition) written as the
    model input at the path the environment file maps for `data.model_input`, partitioned by
    period, with `_model_input.json`; the path written. The configs freeze here (D-125)."""
    cfgs = [cfgs] if isinstance(cfgs, UseCaseConfig) else list(cfgs)
    if not cfgs:
        raise ValueError("save_model_input needs at least one config")
    path = _model_input_path(cfgs[0], entity, env)
    table, log, meta = load_panel(cfgs, entity, env, spark)
    for cfg in cfgs:  # a column clash on the read side fails here, not at every later read
        read_side_columns(table.columns, meta["targets"], cfg.use_case, meta["sources"]["features"])
    table.write.mode("overwrite").partitionBy("period").parquet(path)  # the folder, whole
    metadata = {
        "schema_version": MODEL_INPUT_SCHEMA_VERSION,
        "framework_version": __version__,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entity": entity,
        "model_input": cfgs[0].data.model_input,
        "use_cases": [cfg.use_case for cfg in cfgs],
        **meta,
        "columns": table.columns,
        "log": log,
    }
    Path(path, METADATA_FILE).write_text(json.dumps(metadata, indent=2))
    print(f"model input saved: {path} ({', '.join(metadata['use_cases'])})")
    return path


def read_model_input_metadata(cfg: UseCaseConfig, entity: str, env: EnvironmentConfig) -> dict:
    """The saved model input's metadata, checked in order: a missing table, another schema or
    hash version, another join definition (the feature sources, the keys, the period), a use
    case the table lacks, another target spec for it, or periods not covering the window's
    first to the validation period fail naming `save_model_input`. A changed eligibility,
    window, split or candidate list is derived on read and never refused."""
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
    _check_join_definition(metadata, cfg, entity, path)
    _check_target(metadata, cfg, entity, path)
    _check_periods(metadata, cfg, path)
    return metadata


def _check_join_definition(metadata: dict, cfg: UseCaseConfig, entity: str, path: str) -> None:
    """The table was joined from the config's feature sources, keys and period."""
    mine = {
        "sources": {"features": cfg.entities[entity].sources.features},
        "keys": cfg.data.keys.model_dump(),
        "period": cfg.time.period,
    }
    for field in JOIN_FIELDS:
        if metadata[field] != mine[field]:
            raise ValueError(
                f"model input at {path} was built with {field} {metadata[field]}, the config "
                f"{cfg.use_case!r} has {mine[field]}; rebuild it with save_model_input"
            )


def _check_target(metadata: dict, cfg: UseCaseConfig, entity: str, path: str) -> None:
    """The table carries the use case's target, built from the config's target spec, and its
    target source reached far enough for the config's validation period to be labelled."""
    targets = metadata["targets"]
    if cfg.use_case not in targets:
        raise ValueError(
            f"model input at {path} has no target for use case {cfg.use_case!r}; its use cases: "
            f"{metadata['use_cases']}; save it with save_model_input for every config together"
        )
    if targets[cfg.use_case]["target_spec_hash"] != target_spec_hash(cfg, entity):
        built_by = metadata["framework_version"]
        by = "" if built_by == __version__ else f" (by {built_by}, this is {__version__})"
        raise ValueError(
            f"model input at {path}: the target of {cfg.use_case!r} was built from another "
            f"target spec{by}; rebuild it with save_model_input"
        )
    _check_labels_reach(targets[cfg.use_case], cfg, path)


def _check_labels_reach(target: dict, cfg: UseCaseConfig, path: str) -> None:
    """The target source the table was built from ends at or after the validation period + w,
    so the validation period's labels are known (a later `time.validation_period` than the one
    the table was saved with needs a rebuild)."""
    spec, w, v = period_spec(cfg), cfg.time.target_window, cfg.time.validation_period
    target_last = date.fromisoformat(target["target_last"])
    if spec.index(v) + w > spec.index(target_last):
        known_until = spec.from_index(spec.index(target_last) - w)
        needed = spec.from_index(spec.index(v) + w)
        raise ValueError(
            f"model input at {path}: the target source of {cfg.use_case!r} ends at "
            f"{spec.label(target_last)}, so labels are known up to {spec.label(known_until)}; "
            f"time.validation_period {spec.label(v)} needs it to reach {spec.label(needed)}; "
            "rebuild it with save_model_input"
        )


def _check_periods(metadata: dict, cfg: UseCaseConfig, path: str) -> None:
    """The saved periods cover the window's first to the validation period. The labels sort
    chronologically (`YYYY-MM`, `YYYY-Www`, `YYYY-MM-DD`), so they compare as strings."""
    spec, saved = period_spec(cfg), metadata["periods"]
    first = spec.label(cfg.time.observation_window.first)
    validation = spec.label(cfg.time.validation_period)
    if saved["first"] > first or saved["last"] < validation:
        raise ValueError(
            f"model input at {path} covers the periods {saved['first']} … {saved['last']}, not "
            f"{first} (time.observation_window.first) … {validation} (time.validation_period); "
            "rebuild it with save_model_input"
        )


def saved_candidates(cfg: UseCaseConfig, entity: str, env: EnvironmentConfig) -> list[str] | None:
    """The candidate list the saved model input gives the config, for the audit log's feature
    decisions, resolved from the sidecar's columns dropped and renamed as `prepare_panel` does
    (`read_side_columns`; no Spark); None when the config names no model input or none is saved
    yet; a model input the environment doesn't map, or one the config can't read, fails loud."""
    if cfg.data.model_input is None:
        return None
    if not Path(_model_input_path(cfg, entity, env), METADATA_FILE).is_file():
        return None
    metadata = read_model_input_metadata(cfg, entity, env)
    features = metadata["sources"]["features"]
    dropped, renames = read_side_columns(
        metadata["columns"], metadata["targets"], cfg.use_case, features
    )
    columns = [renames.get(c, c) for c in metadata["columns"] if c not in dropped]
    lineage = [renames.get(c, c) for c in metadata["targets"][cfg.use_case]["lineage"]]
    return resolve_candidates(columns, cfg, lineage)


def read_model_input(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession
) -> tuple[DataFrame, list[dict], dict]:
    """The saved model input prepared for the config (`prepare_panel`), with the join log it
    was saved with followed by the preparation's log, and the preparation's meta."""
    metadata = read_model_input_metadata(cfg, entity, env)
    saved = spark.read.parquet(_model_input_path(cfg, entity, env))
    # The partition column comes back as a date only while Spark's partition type inference is
    # on (its default); cast, so a session without it gives the same frames.
    panel = saved.withColumn("period", F.col("period").cast("date")).select(metadata["columns"])
    print(f"model input read: {metadata['model_input']} for {metadata['use_cases']}, built "
          f"{metadata['built_at']} by core_modelling {metadata['framework_version']}")  # fmt: skip
    panel, log, meta = prepare_panel(panel, cfg, entity, metadata["targets"])
    return panel, [*metadata["log"], *log], meta
