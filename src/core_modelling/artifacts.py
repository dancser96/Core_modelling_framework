"""A reporting stage's artifact folder (D-136, D-137): the one result shape, written and read back.

Every reporting stage returns one `StageResult` and writes it with `write_stage` into its folder,
`<use_case>/04_feature/<ddh>/<stage>/` for EDA and Feature Checks: `tables/<table>.parquet`,
`<stage>.json` (the stage's meta, stamped with `schema_version`, the framework version, when and
the tables written), `resolved_config.yml`, `log.json` and the text files the stage hands it (its
`report.html`, rendered before anything is written). The folder is written whole into a
temporary sibling and swapped in only once every file is written, so a crash leaves the previous
run's folder (or none), never half a stage. A stage renders its report first, saves the ledger
next and writes its folder last, so `<stage>.json` is the commit marker.
The next stage reads it with `read_stage` and refuses it with `check_upstream` when its data
definition or the settings it was computed from (`settings_meta`, a digest plus the values, so the
refusal names the changed path) no longer match the resolved config. `write_parquet`, `write_json`
and `read_parquet` are shared with the ledger (`ledger.py`). Local paths only in 0.x, so `pathlib`
is used and a URI is refused (T2); the HDFS transport comes for every artifact at once in M2.4
(D-136).
"""

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from core_modelling import __version__
from core_modelling.config.identities import canonical_json, short
from core_modelling.config.replay import get_at
from core_modelling.config.schema import UseCaseConfig

STAGE_SCHEMA_VERSION = 1
STAMP_KEYS = ("schema_version", "stage", "framework_version", "written_at", "tables")


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
    """A local folder as a `Path`; a URI is refused until the HDFS transport (T2, D-136)."""
    if "://" in folder:
        raise NotImplementedError(
            f"{folder}: artifacts are written to local paths only until the HDFS transport "
            "arrives with M2.4 (D-136); use a local roots.data"
        )
    return Path(folder)


def utc_now() -> str:
    """The UTC time as an ISO string to the second, with its offset."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def write_json(data: dict | list, path: Path) -> None:
    """`data` as indented JSON, dates as ISO strings and numpy values as Python; a NaN or inf
    fails loud, since strict JSON readers reject it."""
    try:
        text = json.dumps(data, indent=2, default=_to_json, allow_nan=False)
    except ValueError as err:
        raise ValueError(
            f"{path}: {err}; write None for a missing value, never NaN or inf"
        ) from err
    path.write_text(text)


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
    config = yaml.safe_dump(
        result.config.model_dump(mode="json"), sort_keys=False, allow_unicode=True
    )
    (temporary / "resolved_config.yml").write_text(config)
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
    rendered `report.html`), committed with the rest. Returns the paths written by their path
    relative to the folder, plus `folder` itself. The stage saves the ledger before calling it,
    so `<name>.json` is the commit marker: a crash in between leaves a new ledger beside the old
    json, which `check_upstream` then refuses, never an old ledger beside a new json."""
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
    """A short sha256 of the canonical JSON of the values at the dotted `paths` (EDA's:
    `features.kinds`, `strata`, `eda`, `time.validation_period`)."""
    text = canonical_json(_settings(resolved, paths))
    return short(hashlib.sha256(text.encode("utf-8")).hexdigest())


def settings_meta(resolved: UseCaseConfig, paths: list[str]) -> dict:
    """The meta keys `check_upstream` reads: the digest of the values at `paths`, and the values,
    so a refusal can name the path that changed."""
    return {
        "settings_digest": settings_digest(resolved, paths),
        "settings": _settings(resolved, paths),
    }


def check_upstream(meta: dict, resolved: UseCaseConfig, paths: list[str]) -> None:
    """Refuse an upstream stage's artifacts that no longer fit the resolved config: written for
    another data definition, or computed with other values at `paths` (naming the first one)."""
    missing = [k for k in ("stage", "data_definition_hash", "settings_digest") if k not in meta]
    if missing:
        raise ValueError(
            f"the upstream stage's meta lacks {missing}: write_stage stamps `stage`, and the "
            "stage's meta carries its data_definition_hash and settings_meta(...); rerun it"
        )
    stage = meta["stage"]
    expected = (resolved.housekeeping or {}).get("data_definition_hash")
    if expected is None:
        raise ValueError(
            "check_upstream needs the resolved config, whose housekeeping carries the "
            "data-definition hash (resolve_config fills it)"
        )
    stored = meta["data_definition_hash"]
    if stored != expected:
        raise ValueError(
            f"the {stage} artifacts were written for data definition {short(str(stored))}, the "
            f"config's is {short(expected)}: rerun {stage}"
        )
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


def remove_stage(folder: str) -> None:
    """Remove a stage folder (an EDA run removes a stale `feature_checks/`); a missing one is
    fine."""
    target = local_path(folder)
    if target.exists():
        shutil.rmtree(target)
