"""A reporting stage's artifact folder (D-136, D-137): the one result shape, written and read back.

Every reporting stage returns one `StageResult` and writes it with `write_stage` into its folder
(`<use_case>/04_feature/<ddh>/<stage>/` for EDA and Feature Checks): `tables/<table>.parquet`,
`<stage>.json` (the meta, stamped with `schema_version`, the framework version, the time and the
tables written), `resolved_config.yml`, `log.json` and the stage's text files (its
`report.html`). The folder is written into a temporary sibling and swapped in whole, so a crash
leaves the previous run's folder (or none), never half a stage; a stage renders its report
first, saves the ledger next and writes its folder last, so `<stage>.json` is the commit marker.
A stage's meta opens with `stage_identity` (the hashes, the stage's settings and where its
sources physically are, which no hash covers) and carries the run's `new_run_token`, which the
ledger's sidecar records too, so `read_ledger` pairs the two exactly. The next stage reads it
with `read_upstream`, which refuses it when its data definition, settings (named by path) or
sources (named by source) no longer match. `local_path`, `utc_now`, `write_parquet`,
`write_json` and `read_parquet` are shared with the ledger, the audit log and the model input.
Local paths only in 0.x, so `pathlib` is used and a URI is refused (T2); the HDFS transport
comes for every artifact at once in M2.4 (D-136).
"""

import hashlib
import json
import os
import secrets
import shutil
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from core_modelling import __version__
from core_modelling.config.identities import canonical_json, short
from core_modelling.config.replay import check_resolved, dump_resolved, get_at
from core_modelling.config.schema import UseCaseConfig
from core_modelling.environment import EnvironmentConfig, feature_dir, find_source
from core_modelling.sources import feature_source_names, source_name

STAGE_SCHEMA_VERSION = 3  # 2: the run's `run_token` (11-10); 3: the sources' digest (11-11)
STAMP_KEYS = ("schema_version", "stage", "framework_version", "written_at", "tables")
HOUSEKEEPING_KEYS = ("entity", "config_hash", "data_definition_hash", "resolved_input_hash",
                     "hash_version", "replayed_to")  # fmt: skip
# EDA's settings: the validation period decides the compared periods and the population counts
# yet is outside the data-definition hash (D-088); `decision` and `evaluation.slices` shape its
# decision-slices view.
_EDA_SETTINGS = ["features.kinds", "strata", "eda", "time.validation_period", "decision",
                 "evaluation.slices"]  # fmt: skip
# The settings each stage's digest covers, which the next stage checks; Feature Checks': EDA's
# (the cells its steps read) and its thresholds.
SETTINGS_PATHS_BY_STAGE: dict[str, list[str]] = {
    "eda": _EDA_SETTINGS,
    "feature_checks": [*_EDA_SETTINGS, "feature_checks"],
}


@dataclass
class StageResult:
    """What a reporting stage returns (D-137): its tables, the ledger, the run log, the meta
    written as `<stage>.json`, the paths written, the views the report embeds (Stylers and
    figures), the collected snapshot (`None` when nothing is collected) and the resolved config."""

    tables: dict[str, pd.DataFrame]
    ledger: pd.DataFrame
    log: list[dict]
    meta: dict
    paths: dict[str, str]
    views: dict
    frame: pd.DataFrame | None
    config: UseCaseConfig


def local_path(folder: str) -> Path:
    """A local folder or file as a `Path`; a URI is refused until the HDFS transport (T2,
    D-136)."""
    if "://" in folder:
        raise NotImplementedError(
            f"{folder}: local paths only until the HDFS transport arrives with M2.4 (D-136); "
            "use a local roots.data or source path"
        )
    return Path(folder)


def utc_now() -> str:
    """The UTC time as an ISO string to the second, with its offset."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def lap(start: float) -> tuple[float, float]:
    """The seconds since `start` (a `time.perf_counter()`), rounded, and the new start."""
    now = time.perf_counter()
    return round(now - start, 2), now


def new_run_token() -> str:
    """A short random hex token naming one stage run, written into its `<stage>.json` and the
    ledger's sidecar so the two are paired exactly."""
    return secrets.token_hex(6)


def _to_json(value: object) -> object:
    """A date, timestamp or `np.datetime64` (scalar or array) as its ISO string, a numpy scalar
    or array as Python and pandas' or numpy's missing markers as null; any other type fails
    naming it."""
    if value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, date):
        return value.isoformat()
    # Before the generic numpy branch: `.tolist()` would give nanoseconds since the epoch.
    if isinstance(value, np.datetime64):
        return None if np.isnat(value) else pd.Timestamp(value).isoformat()
    if isinstance(value, np.ndarray) and np.issubdtype(value.dtype, np.datetime64):
        return [_to_json(item) for item in value]
    if isinstance(value, np.generic | np.ndarray):
        return value.tolist()
    raise TypeError(f"{type(value).__name__} is not JSON-serialisable: {value!r}")


def write_json(data: dict | list, path: Path, exclusive: bool = False) -> None:
    """`data` as indented JSON, dates as ISO strings and numpy values as Python; a NaN or inf
    fails loud, since strict JSON readers reject it. `exclusive` never overwrites: an existing
    file raises `FileExistsError` (the audit log's entries)."""
    try:
        text = json.dumps(data, indent=2, default=_to_json, allow_nan=False)
    except ValueError as err:
        raise ValueError(
            f"{path}: {err}; write None for a missing value, never NaN or inf"
        ) from err
    with open(path, "x" if exclusive else "w") as file:
        file.write(text)


def write_parquet(frame: pd.DataFrame, path: Path) -> None:
    """One table as parquet; timestamps as microseconds, which Spark 3.4 reads (T18), and a
    nanosecond part fails loud instead of being truncated."""
    frame.to_parquet(path, coerce_timestamps="us")


def read_parquet(path: Path) -> pd.DataFrame:
    """One table as written: list columns come back as Python lists, not numpy arrays, so a
    value compares, prints and serialises as it did before the round trip."""
    table = pq.read_table(path)
    frame = table.to_pandas()
    for field in table.schema:
        if pa.types.is_list(field.type):
            frame[field.name] = table.column(field.name).to_pylist()
    return frame


def _write_files(result: StageResult, temporary: Path, name: str) -> list[str]:
    """Every file of the stage into the temporary folder; returns the paths written, relative."""
    (temporary / "tables").mkdir()
    written = []
    for table, frame in result.tables.items():
        written.append(f"tables/{table}.parquet")
        write_parquet(frame, temporary / written[-1])
    stamp = {
        "schema_version": STAGE_SCHEMA_VERSION,
        "stage": name,
        "framework_version": __version__,
        "written_at": utc_now(),
        "tables": list(result.tables),
    }
    write_json({**stamp, **result.meta}, temporary / f"{name}.json")
    write_json(result.log, temporary / "log.json")
    # The same body as `write_resolved`, without its header: the entries are not in the result.
    (temporary / "resolved_config.yml").write_text(dump_resolved(result.config))
    return [*written, f"{name}.json", "log.json", "resolved_config.yml"]


def _write_texts(texts: dict[str, str], temporary: Path) -> list[str]:
    """The stage's text files (its report) into the temporary folder after its own files; a
    name that is not a plain file name, or one the stage writes itself, fails."""
    for file, text in texts.items():
        path = temporary / file
        if path.parent != temporary or path.exists():
            raise ValueError(
                f"write_stage: the text file {file!r} must be a plain file name the stage does "
                "not write itself"
            )
        path.write_text(text, encoding="utf-8")
    return list(texts)


def _swap_in(temporary: Path, target: Path) -> None:
    """Move the written folder onto `target`; an older `target` is moved aside first, moved back
    when the swap fails and removed only after it succeeds, so no failure leaves half of it."""
    aside = target.with_name(f"{target.name}.old-{os.getpid()}")
    if target.exists():
        target.rename(aside)
    try:
        temporary.rename(target)
    except BaseException:
        if aside.exists():
            aside.rename(target)
        shutil.rmtree(temporary)
        raise
    if aside.exists():
        shutil.rmtree(aside)


def write_stage(
    result: StageResult, folder: str, name: str, texts: dict[str, str] | None = None
) -> dict[str, str]:
    """Write a stage's artifacts into `folder` whole, replacing an older run's folder, through a
    temporary sibling that is removed when any write fails; `texts` adds text files by name (the
    rendered `report.html`). Returns each file's full path by its path relative to the folder,
    plus `folder`. A meta that sets a stamp key, or leftovers of an unfinished earlier write,
    fail loud. The stage saves the ledger before calling it, so `<name>.json` is the commit
    marker (`save_ledger` says why)."""
    reserved = sorted(set(STAMP_KEYS) & set(result.meta))
    if reserved:
        raise ValueError(f"stage {name}: the meta may not set {reserved}; write_stage stamps them")
    target = local_path(folder)
    stale = sorted(
        str(path)
        for kind in ("tmp", "old")
        for path in target.parent.glob(f"{target.name}.{kind}-*")
    )
    if stale:
        raise ValueError(
            f"stage {name}: {stale} are left from an earlier write that did not finish; look at "
            "them and remove them before rerunning"
        )
    temporary = target.with_name(f"{target.name}.tmp-{os.getpid()}")
    temporary.mkdir(parents=True)
    try:
        written = _write_files(result, temporary, name) + _write_texts(texts or {}, temporary)
    except BaseException:
        shutil.rmtree(temporary)
        raise
    _swap_in(temporary, target)
    return {"folder": str(target), **{path: str(target / path) for path in written}}


def read_stage(folder: str, name: str) -> tuple[dict, dict[str, pd.DataFrame]]:
    """A stage's json and every table it wrote, by table name; a stage not run yet, written under
    another `schema_version`, or whose tables on disk differ from those it wrote, fails saying
    what to do."""
    path = local_path(folder) / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"no {name} artifacts at {folder}: run the {name} stage first")
    meta = json.loads(path.read_text())
    version = meta.get("schema_version")
    if version != STAGE_SCHEMA_VERSION:
        raise ValueError(
            f"{path} has schema_version {version} (written by framework "
            f"{meta.get('framework_version')}); this version reads {STAGE_SCHEMA_VERSION}: rerun "
            f"the {name} stage, or raise the use case's framework pin when it is newer"
        )
    tables = local_path(folder) / "tables"
    found = {table.stem for table in tables.glob("*.parquet")}
    recorded = meta.get("tables", [])
    missing, extra = sorted(set(recorded) - found), sorted(found - set(recorded))
    if missing or extra:
        raise ValueError(
            f"{tables} lacks the {name} tables {missing} and holds {extra}, which the {name} "
            f"run did not write: rerun the {name} stage"
        )
    return meta, {table: read_parquet(tables / f"{table}.parquet") for table in recorded}


def _settings(resolved: UseCaseConfig, paths: list[str]) -> dict[str, object]:
    """The resolved config's values at the dotted paths, as JSON-ready data."""
    raw = resolved.model_dump(mode="json")
    settings = {}
    for path in paths:
        try:
            settings[path] = get_at(raw, path)
        except (KeyError, TypeError) as err:
            raise KeyError(f"the resolved config has no setting at {path}") from err
    return settings


def settings_digest(resolved: UseCaseConfig, paths: list[str]) -> str:
    """A short sha256 of the canonical JSON of the values at the dotted `paths` (a stage's are in
    `SETTINGS_PATHS_BY_STAGE`)."""
    return _digest(_settings(resolved, paths))


def settings_meta(resolved: UseCaseConfig, paths: list[str]) -> dict:
    """The meta keys `check_upstream` reads: the digest of the values at `paths`, and the values,
    so a refusal can name the path that changed."""
    return {
        "settings_digest": settings_digest(resolved, paths),
        "settings": _settings(resolved, paths),
    }


def _sources(env: EnvironmentConfig, resolved: UseCaseConfig) -> dict[str, dict]:
    """Every logical source the config names for its entity (the feature sources, the target
    source, the model input) with its environment entry (format, path or table): where the data
    physically is, which the data-definition hash, on logical names, does not cover (Q577). The
    feature and target sources count also when a stage reads the model input only: the model
    input is built from them, so a moved one means it should be rebuilt."""
    entity = resolved.housekeeping["entity"]
    targets = resolved.entities[entity].sources.targets
    names = [*feature_source_names(resolved, entity), source_name(targets) if targets else None,
             resolved.data.model_input]  # fmt: skip
    return {
        name: find_source(env, entity, name).model_dump(mode="json")
        for name in dict.fromkeys(names)
        if name is not None
    }


def stage_identity(resolved: UseCaseConfig, stage: str, env: EnvironmentConfig) -> dict:
    """The head of a stage's meta: the resolved config's `HOUSEKEEPING_KEYS`, the digest and
    values of the stage's settings (`SETTINGS_PATHS_BY_STAGE`), the ones the run used, and the
    digest and entries of its sources in `env` (`sources_digest`, `sources`)."""
    check_resolved(resolved, f"stage_identity for {stage}")
    sources = _sources(env, resolved)
    return {
        **{key: resolved.housekeeping[key] for key in HOUSEKEEPING_KEYS},
        **settings_meta(resolved, SETTINGS_PATHS_BY_STAGE[stage]),
        "sources_digest": _digest(sources),
        "sources": sources,
    }


def _digest(values: dict) -> str:
    """A short sha256 of the canonical JSON of `values`."""
    return short(hashlib.sha256(canonical_json(values).encode("utf-8")).hexdigest())


def check_upstream(meta: dict, resolved: UseCaseConfig, env: EnvironmentConfig) -> None:
    """Refuse an upstream stage's artifacts that no longer fit the resolved config and `env`:
    written for another data definition, read from sources `env` now maps elsewhere (naming the
    first one that moved), or computed with other values at the stage's settings paths
    (`SETTINGS_PATHS_BY_STAGE`, naming the first one that changed)."""
    check_resolved(resolved, "check_upstream")
    required = ("stage", "data_definition_hash", "settings_digest", "sources_digest", "run_token")
    missing = [k for k in required if k not in meta]
    if missing:
        stage = meta.get("stage", "the upstream stage")
        raise ValueError(
            f"{stage}'s meta lacks {missing}: write_stage stamps `stage`, and the stage's meta "
            "carries stage_identity(...) and its run_token (an older framework's artifacts lack "
            f"some); rerun {stage}"
        )
    stage = meta["stage"]
    paths = SETTINGS_PATHS_BY_STAGE[stage]
    expected = resolved.housekeeping["data_definition_hash"]
    stored = meta["data_definition_hash"]
    if stored != expected:
        raise ValueError(
            f"the {stage} artifacts were written for data definition {short(str(stored))}, the "
            f"config's is {short(expected)}: rerun {stage}"
        )
    _check_sources(meta, _sources(env, resolved))
    if meta["settings_digest"] == settings_digest(resolved, paths):
        return
    current, recorded = _settings(resolved, paths), meta.get("settings", {})
    changed = next((p for p in paths if p not in recorded or recorded[p] != current[p]), None)
    if changed is None:
        raise ValueError(
            f"the {stage} settings digest differs from the resolved config's over {paths}, "
            f"though no recorded value does: rerun {stage}"
        )
    raise ValueError(
        f"{stage} ran with {changed} = {recorded.get(changed, '(not recorded)')!r}; the resolved "
        f"config has {current[changed]!r}: rerun {stage}"
    )


def _check_sources(meta: dict, current: dict[str, dict]) -> None:
    """Refuse a stage whose sources' entries differ from `current` (the environment's now)."""
    if meta["sources_digest"] == _digest(current):
        return
    stage, recorded = meta["stage"], meta.get("sources", {})
    moved = next((n for n in sorted({*current, *recorded}) if recorded.get(n) != current.get(n)),
                 None)  # fmt: skip
    where = (
        f"{moved} was {recorded.get(moved, '(not read)')}, the environment file has "
        f"{current.get(moved, '(not read)')}"
        if moved
        else "no recorded entry differs, but the digest does"
    )
    raise ValueError(
        f"the {stage} artifacts were read from other data ({where}): rerun {stage}, after "
        "target_factory when the config reads a model input built from the moved source"
    )


def read_upstream(
    env: EnvironmentConfig, resolved: UseCaseConfig, entity: str, stage: str
) -> tuple[dict, dict[str, pd.DataFrame]]:
    """An upstream stage's json and tables from its folder of the data definition, refused by
    `read_stage` when missing and by `check_upstream` when stale or read from other sources."""
    meta, tables = read_stage(feature_dir(env, resolved, entity, stage), stage)
    check_upstream(meta, resolved, env)
    return meta, tables


def list_data_definitions(env: EnvironmentConfig, cfg: UseCaseConfig, entity: str) -> pd.DataFrame:
    """The use case's data-definition folders (`<use_case>/04_feature/<ddh>/`), one row each:
    `data_definition` (the folder's name), `in_use` (the one `cfg` and `entity` define, listed
    first, also before its first run), `entity` (EDA's record; `entity` for the one in use),
    `eda_run` and `feature_checks_run` (when each
    stage last wrote its folder, '' when it has not; read whatever the stage json's format
    version) and `path`; the others by their last EDA run, newest first."""
    in_use = local_path(feature_dir(env, cfg, entity))
    parent = in_use.parent
    folders = {p for p in parent.iterdir() if p.is_dir()} if parent.is_dir() else set()
    rows = []
    for folder in sorted(folders | {in_use}):
        eda, checks = _stage_json(folder, "eda"), _stage_json(folder, "feature_checks")
        rows.append({"data_definition": folder.name, "in_use": folder == in_use,
                     "entity": eda.get("entity", entity if folder == in_use else ""),
                     "eda_run": eda.get("written_at", ""),
                     "feature_checks_run": checks.get("written_at", ""),
                     "path": str(folder)})  # fmt: skip
    table = pd.DataFrame(rows)
    return table.sort_values(["in_use", "eda_run"], ascending=False).reset_index(drop=True)


def _stage_json(folder: Path, stage: str) -> dict:
    """A data definition's `<stage>/<stage>.json` as stored, or {} when the stage has not run."""
    path = folder / stage / f"{stage}.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def remove_stage(folder: str) -> None:
    """Remove a stage folder (an EDA run removes a stale `feature_checks/`); a missing one is
    fine."""
    target = local_path(folder)
    if target.exists():
        shutil.rmtree(target)
