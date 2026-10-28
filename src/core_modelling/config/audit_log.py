"""The decision audit log (D-125): append-only entries beside a frozen config.

The config is the intent, immutable once the target is built. Every later decision, by a person,
a rule or a stage, is one small JSON file, `<seq>.json`, in the log folder of one use case, entity
and data definition (`audit_log_dir`). Entries are never edited: a reversal is a new entry. The
entry model and the replay (entries → resolved config) are in `replay.py`; this module stores
and writes entries and holds the public functions `record_decision`, `resolve_config` and
`show_decisions` (the CLI command `decide` is in `__main__`), plus `read_resolved_config` for a
saved resolved config. Stage 1 writes to the local filesystem only; the HDFS transport comes with
M2.4.
"""

import copy
import getpass
import json
import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml
from pydantic import ValidationError

from core_modelling import __version__
from core_modelling.config import load_config
from core_modelling.config.identities import (
    HASH_VERSION,
    config_hash,
    data_definition_hash,
    resolved_input_hash,
    short,
)
from core_modelling.config.levels import level_filled
from core_modelling.config.replay import (
    LOGGABLE_SETTINGS,
    By,
    Entry,
    check_candidates,
    get_at,
    replay,
    set_at,
    validate_raw,
    write_resolved,
)
from core_modelling.config.schema import UseCaseConfig
from core_modelling.dataset.model_input import saved_candidates
from core_modelling.environment import EnvironmentConfig, audit_log_dir, load_environment

__all__ = [
    "Entry",
    "LOGGABLE_SETTINGS",
    "read_resolved_config",
    "record_decision",
    "resolve_config",
    "show_decisions",
]

LOG_SCHEMA_VERSION = 1
COLUMNS = ["seq", "time", "by", "stage", "op", "what", "reason", "evidence"]

logger = logging.getLogger(__name__)


def _local_folder(log_dir: str) -> Path:
    """The log folder as a local path; a URI never reaches `pathlib` (T2)."""
    if "://" in log_dir:
        raise NotImplementedError(
            f"audit log at {log_dir}: the hdfs:// transport arrives with M2.4; use a local "
            "roots.data until then"
        )
    return Path(log_dir)


def _read_entry(path: Path) -> Entry:
    """One entry file; a newer-schema or malformed entry fails naming the file."""
    data = json.loads(path.read_text())
    version = data.get("log_schema_version") if isinstance(data, dict) else None
    if version not in (None, LOG_SCHEMA_VERSION):
        raise ValueError(
            f"audit log entry {path} has log_schema_version {version}; this version reads "
            f"{LOG_SCHEMA_VERSION}; raise the use case's framework pin"
        )
    try:
        entry = Entry.model_validate(data)
    except (ValidationError, ValueError) as exc:
        raise ValueError(f"audit log entry {path} is not valid: {exc}") from exc
    if path.stem != f"{entry.seq:04d}":
        raise ValueError(f"audit log entry {path} carries seq {entry.seq}; the file name disagrees")
    return entry


def read_entries(log_dir: str) -> list[Entry]:
    """Every entry of a log folder in `seq` order; a gap or a duplicate fails loud, a missing
    folder is an empty log."""
    folder = _local_folder(log_dir)
    if not folder.is_dir():
        return []
    entries = sorted((_read_entry(path) for path in folder.glob("*.json")), key=lambda e: e.seq)
    seqs = [entry.seq for entry in entries]
    if seqs != list(range(1, len(seqs) + 1)):
        raise ValueError(f"audit log {log_dir}: entries must run 1..n without gaps; found {seqs}")
    return entries


def _log_dir(cfg: UseCaseConfig, entity: str, env: EnvironmentConfig) -> str:
    """The log folder of this config, entity and data definition."""
    return audit_log_dir(env, cfg.use_case, entity, short(data_definition_hash(cfg, entity)))


def _load_entries(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, *, warn_if_missing: bool = False
) -> list[Entry]:
    """The log's entries; one written under another data definition fails citing its `seq`. A
    reader warns when the folder is missing, since a wrong root looks like an empty log."""
    log_dir = _log_dir(cfg, entity, env)
    entries = read_entries(log_dir)
    if warn_if_missing and not _local_folder(log_dir).is_dir():
        logger.warning("no audit log at %s: 0 entries replayed", log_dir)
    expected = data_definition_hash(cfg, entity)
    for entry in entries:
        if entry.data_definition_hash != expected:
            raise ValueError(
                f"entry {entry.seq} was written for data definition "
                f"{short(entry.data_definition_hash)}, the config's is {short(expected)}"
            )
    return entries


def _now() -> str:
    """The UTC time as an ISO string to the second, with its offset."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_resolved_config(path: str | Path) -> UseCaseConfig:
    """A resolved config saved by `resolve_config`, read back as is: no level defaults to apply,
    and its replayed lists and housekeeping are the replay's own."""
    return UseCaseConfig.model_validate(yaml.safe_load(Path(path).read_text()))


def resolve_config(
    cfg: UseCaseConfig,
    entity: str,
    env: EnvironmentConfig,
    upto: int | None = None,
    save_to: str | Path | None = None,
) -> UseCaseConfig:
    """The config with entries 1–`upto` (default: all) replayed and validated, its housekeeping
    filled; with `save_to`, also written as one YAML file."""
    entries = _load_entries(cfg, entity, env, warn_if_missing=True)
    if upto is not None and not 0 <= upto <= len(entries):
        raise ValueError(f"upto={upto} is outside the log, which has {len(entries)} entries")
    entries = entries[:upto]
    raw = replay(cfg, entries)
    resolved = validate_raw(raw, "the replayed config")
    resolved.housekeeping = {
        "framework_version": __version__,
        "resolved_at": _now(),
        "entity": entity,
        "config_hash": config_hash(cfg),
        "data_definition_hash": data_definition_hash(cfg, entity),
        "resolved_input_hash": resolved_input_hash(resolved),
        "replayed_to": entries[-1].seq if entries else 0,
        "hash_version": HASH_VERSION,
        "level_filled": level_filled(raw),
        "environment": env.model_dump(mode="json"),
    }
    if save_to is not None:
        write_resolved(resolved, entries, save_to)
    return resolved


def _one_operation(
    exclude: list[str] | None,
    include: list[str] | None,
    keep_despite_flag: list[str] | None,
    set: dict[str, object] | None,
) -> tuple[str, object]:
    """The one operation given as (op, operand); none or several fail."""
    operands = {
        "exclude": exclude,
        "include": include,
        "keep_despite_flag": keep_despite_flag,
        "set": set,
    }
    given = {op: value for op, value in operands.items() if value is not None}
    if len(given) != 1:
        raise ValueError(
            "a decision is exactly one of exclude / include / keep_despite_flag / set; "
            f"got {sorted(given) or 'none'}"
        )
    return next(iter(given.items()))


def _check_includable(entries: list[Entry], current: dict, features: list[str]) -> None:
    """`include` reverses a person's `exclude` only: the feature is excluded now, and the entry
    that last excluded it is a person's (a rule's exclude is reversed by changing the rule)."""
    for feature in features:
        if feature not in current["features"]["excluded"]:
            raise ValueError(f"{feature!r} is not excluded, so there is nothing to include")
        last = next(
            (e for e in reversed(entries) if e.op == "exclude" and feature in e.features), None
        )
        if last is None:
            raise ValueError(
                f"{feature!r} is excluded by the config file itself, not by an entry; "
                "edit the config"
            )
        if last.by.kind == "rule":
            raise ValueError(
                f"{feature!r} was excluded by rule {last.by.id!r} (entry {last.seq}); a rule's "
                "exclude is reversed by changing the rule in the config, not by include"
            )


def _feature_fields(
    cfg: UseCaseConfig,
    entity: str,
    env: EnvironmentConfig,
    current: dict,
    entries: list[Entry],
    op: str,
    features: object,
) -> dict:
    """A feature op's entry fields, every feature checked against the saved model input's
    candidate list when the config names one, else against the candidate patterns."""
    if not isinstance(features, list) or not features:
        raise ValueError(f"{op} needs a non-empty list of feature names, got {features!r}")
    candidates = saved_candidates(cfg, entity, env)
    if candidates is None:
        check_candidates(cfg, features, f"{op} refused")
        why = (
            "the config names no model input"
            if cfg.data.model_input is None
            else (f"the model input {cfg.data.model_input!r} is not saved yet")
        )
        print(f"checked against the candidate patterns only: {why}")
    else:
        unknown = [feature for feature in features if feature not in candidates]
        if unknown:
            raise ValueError(
                f"{op} refused: {unknown} are not candidates of the model input "
                f"{cfg.data.model_input!r}; its candidates: {candidates}"
            )
    if op == "include":
        _check_includable(entries, current, features)
    return {"features": features, "stage": "feature_checks"}


def _set_fields(cfg: UseCaseConfig, current: dict, setting: object) -> dict:
    """A `set`'s entry fields: one listed path whose new value passes the schema."""
    if not isinstance(setting, dict) or len(setting) != 1:
        raise ValueError(f"a set changes exactly one setting, as {{path: value}}; got {setting!r}")
    ((path, value),) = setting.items()
    if path not in LOGGABLE_SETTINGS:
        raise ValueError(
            f"{path!r} is not a loggable setting; listed: {sorted(LOGGABLE_SETTINGS)}. "
            "Anything else needs a new config (D-125)"
        )
    validate_raw(set_at(copy.deepcopy(current), path, value), f"set {path} = {value!r}")
    return {
        "path": path,
        "from_value": get_at(current, path),
        "to_value": value,
        "stage": LOGGABLE_SETTINGS[path],
    }


def _write_entry(entry: Entry, log_dir: str) -> Entry:
    """Create `<seq>.json`, never overwriting: a number another writer took meanwhile fails, and
    the decision is re-run against the log as it is then."""
    folder = _local_folder(log_dir)
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(entry.model_dump(mode="json", by_alias=True, exclude_unset=True), indent=2)
    try:
        with open(folder / f"{entry.seq:04d}.json", "x") as file:
            file.write(text)
    except FileExistsError:
        raise RuntimeError(
            f"audit log {log_dir}: entry {entry.seq} was written by another writer meanwhile; "
            "re-run the decision"
        ) from None
    return entry


def record_decision(
    config_path: str | Path,
    entity: str,
    *,
    exclude: list[str] | None = None,
    include: list[str] | None = None,
    keep_despite_flag: list[str] | None = None,
    set: dict[str, object] | None = None,
    reason: str,
    evidence: Sequence[str] = (),
    stage: str | None = None,
    env_path: str | None = None,
) -> Entry:
    """Append one person decision, exactly one of the four operations with a reason, to the audit
    log of `config_path` on `entity`; the writer is the current user id."""
    op, operand = _one_operation(exclude, include, keep_despite_flag, set)
    if not reason or not reason.strip():
        raise ValueError("a decision needs a non-empty reason")
    cfg, env = load_config(config_path), load_environment(env_path)
    entries = _load_entries(cfg, entity, env)
    current = replay(cfg, entries)
    if op == "set":
        fields = _set_fields(cfg, current, operand)
    else:
        fields = _feature_fields(cfg, entity, env, current, entries, op, operand)
    default_stage = fields.pop("stage")
    entry = Entry(
        seq=len(entries) + 1,
        time=_now(),
        by=By(kind="person", id=getpass.getuser()),
        stage=stage or default_stage,
        op=op,
        reason=reason,
        evidence=list(evidence),
        data_definition_hash=data_definition_hash(cfg, entity),
        hash_version=HASH_VERSION,
        log_schema_version=LOG_SCHEMA_VERSION,
        **fields,
    )
    return _write_entry(entry, _log_dir(cfg, entity, env))


def _what(entry: Entry) -> str:
    """The features, `path: from → to`, or the run id."""
    if entry.features:
        return ", ".join(entry.features)
    if entry.path:
        return f"{entry.path}: {entry.from_value} → {entry.to_value}"
    return entry.run_id or ""


def show_decisions(cfg: UseCaseConfig, entity: str, env: EnvironmentConfig) -> pd.DataFrame:
    """The log as a table, one row per entry: who, stage, op, what, reason and evidence."""
    rows = [
        {
            "seq": entry.seq,
            "time": entry.time,
            "by": f"{entry.by.kind} {entry.by.id}",
            "stage": entry.stage,
            "op": entry.op,
            "what": _what(entry),
            "reason": entry.reason,
            "evidence": "; ".join(entry.evidence),
        }
        for entry in _load_entries(cfg, entity, env, warn_if_missing=True)
    ]
    return pd.DataFrame(rows, columns=COLUMNS)
