"""The decision audit log (D-125): append-only entries beside a frozen config.

The config is the intent, immutable once the target is built. Every later decision, by a person,
a rule or a stage, is one small JSON file, `<seq>.json`, in the log folder of one use case and
data definition (`audit_log_dir`, which carries the entity through the hash). Entries are never
edited: a reversal is a new entry. The entry model and the replay (entries → resolved config) are
in `replay.py`; this module stores and writes entries and holds the public functions
`record_decision`, `resolve_config` and `show_decisions` (the CLI command `decide` is in
`__main__`), `read_resolved_config` for a saved resolved config, and `record_stage_entry`, the
writer of a stage's `flag` and `run` entries. The log is on the local filesystem only; the HDFS
transport comes with M2.4.
"""

import copy
import getpass
import json
import logging
import re
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

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
    check_settable,
    effective_entries,
    get_at,
    open_flags,
    replay,
    set_at,
    validate_raw,
    write_resolved,
)
from core_modelling.config.schema import UseCaseConfig
from core_modelling.dataset.model_input import saved_candidates
from core_modelling.environment import EnvironmentConfig, audit_log_dir, load_environment
from core_modelling.periods import period_spec

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
# The labels `periods.PERIODS` writes (2025-06 · 2025-W23 · 2025-06-15), part of the entry
# format: a run's `periods` compare with the validation period's label.
PERIOD_LABEL_FORMS = {
    "month": r"\d{4}-(0[1-9]|1[0-2])",
    "week": r"\d{4}-W(0[1-9]|[1-4]\d|5[0-3])",
    "day": r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])",
}

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
    """One entry file; a corrupt, newer-schema or malformed entry fails naming the file."""
    try:
        data = json.loads(path.read_text())
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError both are
        raise ValueError(f"audit log entry {path} is not valid JSON: {exc}") from exc
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


def _load_entries(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, *, warn_if_missing: bool = False
) -> list[Entry]:
    """The log's entries; one written under another data definition fails citing its `seq`. A
    reader warns when the folder is missing, since a wrong root looks like an empty log."""
    log_dir = audit_log_dir(env, cfg, entity)
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
    _check_not_compared(resolved, entries, "the replayed config is stale")
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
    keep: list[str] | None,
    set: dict[str, object] | None,
    revert_to: int | None,
) -> tuple[str, object]:
    """The one operation given as (op, operand); none or several fail."""
    operands = {
        "exclude": exclude,
        "include": include,
        "keep": keep,
        "set": set,
        "revert": revert_to,
    }
    given = {op: value for op, value in operands.items() if value is not None}
    if len(given) != 1:
        raise ValueError(
            "a decision is exactly one of exclude / include / keep / set / revert_to; got "
            f"{sorted(given) or 'none'}"
        )
    return next(iter(given.items()))


def _check_includable(entries: list[Entry], current: dict, features: list[str]) -> None:
    """`include` reverses a person's `exclude` only: the feature is excluded now, and no effective
    entry (one no revert undid) is a rule's exclude of it, since a rule's exclude is reversed by
    changing the rule. Any rule's exclude counts, not only the last: a person's later re-exclude
    is a no-op that must not hide it."""
    effective = effective_entries(entries)
    for feature in features:
        if feature not in current["features"]["excluded"]:
            raise ValueError(f"{feature!r} is not excluded, so there is nothing to include")
        excludes = [e for e in effective if e.op == "exclude" and feature in e.features]
        if not excludes:
            raise ValueError(
                f"{feature!r} is excluded by the config file itself, not by an entry; "
                "edit the config"
            )
        by_rule = next((e for e in excludes if e.by.kind == "rule"), None)
        if by_rule is not None:
            raise ValueError(
                f"{feature!r} was excluded by rule {by_rule.by.id!r} (entry {by_rule.seq}); a "
                "rule's exclude is reversed by changing the rule in the config, not by include"
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


def _keep_findings(
    entries: list[Entry], features: list[str], findings: list[str] | None
) -> list[str]:
    """The findings a `keep` settles, each open on every named feature, so each stored (feature,
    finding) pair was open when written (D-134): the named ones, else the features' open flags,
    which must then be the same on each. `[]` only when none is open: the keep then protects from
    automated pruning alone; a `[]` named while flags are open settles nothing and is refused."""
    flags = open_flags(entries)
    open_on = {name: flags.get(name, []) for name in features}
    split = f"open flags per feature: {open_on}; split the keep, one per finding set"
    if findings is None:
        if len({tuple(found) for found in open_on.values()}) > 1:
            raise ValueError(f"keep refused: the features' open flags differ; {split}")
        return open_on[features[0]]
    if not findings and any(open_on.values()):
        flagged = {name: found for name, found in open_on.items() if found}
        raise ValueError(
            f"keep refused: findings=[] settles nothing, but flags are open on {flagged}; name "
            "the findings it settles"
        )
    not_open = [f"{name}: {f}" for name in features for f in findings if f not in open_on[name]]
    if not_open:
        raise ValueError(f"keep refused: {not_open} are not open; {split}")
    return sorted(set(findings))


def _check_not_compared(resolved: UseCaseConfig, entries: list[Entry], context: str) -> None:
    """Refuse a validation period that any `run` entry compared, reverted or not: its drift was
    looked at, so it is no longer an untouched period (D-088, `CLAUDE.md` §4.4)."""
    period = resolved.time.validation_period
    if period is None:
        return
    label = period_spec(resolved).label(period)
    runs = [entry.seq for entry in entries if entry.op == "run" and label in (entry.periods or [])]
    if runs:
        raise ValueError(
            f"{context}: the validation period {label} was compared by the run of entry "
            f"{runs[0]}, so its drift was looked at (D-088); choose a period no run compared"
        )


def _set_fields(current: dict, entries: list[Entry], setting: object) -> dict:
    """A `set`'s entry fields: one listed path, under a section the config has, whose new value
    passes the schema; a null validation period, or one a Feature Checks run compared, is
    refused."""
    if not isinstance(setting, dict) or len(setting) != 1:
        raise ValueError(f"a set changes exactly one setting, as {{path: value}}; got {setting!r}")
    ((path, value),) = setting.items()
    if path not in LOGGABLE_SETTINGS:
        raise ValueError(
            f"{path!r} is not a loggable setting; listed: {sorted(LOGGABLE_SETTINGS)}. "
            "Anything else needs a new config (D-125)"
        )
    if path == "time.validation_period" and value is None:
        raise ValueError(
            "set time.validation_period = None refused: write null in the config file instead: a "
            "frozen training config does not become EDA-only through the log"
        )
    check_settable(current, path, f"set {path} refused")
    changed = validate_raw(set_at(copy.deepcopy(current), path, value), f"set {path} = {value!r}")
    if path == "time.validation_period":
        _check_not_compared(changed, entries, f"set {path} refused")
    return {
        "path": path,
        "from_value": get_at(current, path),
        "to_value": value,
        "stage": LOGGABLE_SETTINGS[path],
    }


def _revert_fields(cfg: UseCaseConfig, current: dict, entries: list[Entry], to_seq: object) -> dict:
    """A revert's entry fields: an earlier state, 0 being the config as written, checked like a
    `set` (D-088): it may not move the validation period to null or to one a run compared. Its
    default stage is the first undone entry's, where the trail restarts. The current state
    (`len(entries)`) is refused here as a no-op revert: the stored entry's own rule (`to_seq`
    below `seq`) is wider, since the new entry's `seq` is `len(entries) + 1`."""
    if not isinstance(to_seq, int) or not 0 <= to_seq < len(entries):
        raise ValueError(
            f"revert_to={to_seq!r} is not an earlier state: the log has {len(entries)} entries, so "
            f"it can go back to 0 (the config as written) … {len(entries) - 1}"
        )
    refused = f"revert_to={to_seq} refused"
    target = validate_raw(replay(cfg, entries[:to_seq]), f"the state after entry {to_seq}")
    if target.time.validation_period is None and current["time"]["validation_period"] is not None:
        raise ValueError(
            f"{refused}: it moves time.validation_period to null; a frozen training config does "
            "not become EDA-only through the log (write null in the config file instead)"
        )
    _check_not_compared(target, entries, refused)
    return {"to_seq": to_seq, "stage": entries[to_seq].stage}


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
    if entry.seq == 1:  # a wrong root, or a log left at an old path, shows itself here
        print(f"starting a new audit log at {log_dir}")
    return entry


def record_decision(
    config_path: str | Path,
    entity: str,
    *,
    exclude: list[str] | None = None,
    include: list[str] | None = None,
    keep: list[str] | None = None,
    findings: list[str] | None = None,
    set: dict[str, object] | None = None,
    revert_to: int | None = None,
    reason: str,
    evidence: Sequence[str] = (),
    stage: str | None = None,
    env_path: str | None = None,
) -> Entry:
    """Append one person decision, exactly one of the five operations with a reason, to the audit
    log of `config_path` on `entity`; the writer is the current user id. `findings` goes with
    `keep` only: the flags it settles, each open on every kept feature; by default the features'
    open flags, which must be the same on each. `revert_to` goes back to the state after entry n
    (0: the config as written); the undone entries stay as the trail."""
    if findings is not None and keep is None:
        raise ValueError("`findings` goes with `keep` only: it names the flags a keep settles")
    op, operand = _one_operation(exclude, include, keep, set, revert_to)
    if not reason or not reason.strip():
        raise ValueError("a decision needs a non-empty reason")
    cfg, env = load_config(config_path), load_environment(env_path)
    entries = _load_entries(cfg, entity, env)
    current = replay(cfg, entries)
    if op == "set":
        fields = _set_fields(current, entries, operand)
    elif op == "revert":
        fields = _revert_fields(cfg, current, entries, operand)
    else:
        fields = _feature_fields(cfg, entity, env, current, entries, op, operand)
    if op == "keep":
        fields["findings"] = _keep_findings(entries, operand, findings)
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
    return _write_entry(entry, audit_log_dir(env, cfg, entity))


def _check_period_labels(cfg: UseCaseConfig, periods: list[str] | None) -> None:
    """A run's `periods`: a non-empty list of labels in the form the config's period is written
    (`PERIOD_LABEL_FORMS`), so each compares with the validation period's label."""
    if not periods:
        raise ValueError(
            "a `run` entry needs `periods`, a non-empty list of the period labels the run compared"
        )
    form = PERIOD_LABEL_FORMS[cfg.time.period]
    bad = [label for label in periods if not re.fullmatch(form, label)]
    if bad:
        example = period_spec(cfg).label(cfg.time.observation_window.last)
        raise ValueError(
            f"run refused: periods {bad} are not {cfg.time.period} labels as the framework writes "
            f"them, e.g. {example!r}"
        )


def record_stage_entry(
    cfg: UseCaseConfig,
    entity: str,
    env: EnvironmentConfig,
    *,
    stage: str,
    op: Literal["flag", "run"],
    reason: str,
    features: list[str] | None = None,
    finding: str | None = None,
    periods: list[str] | None = None,
    evidence: Sequence[str] = (),
    run_id: str | None = None,
    replayed_to: int | None = None,
    resolved_input_hash: str | None = None,
) -> Entry:
    """Append one stage entry, by `{kind: stage, id: stage}`: a `flag` (its `finding` and the
    features, empty to close it) or a `run` marker (the labels of the periods it compared, as
    `periods.PERIODS` writes them). Whether a flag entry is due, its finding's feature set having
    changed, is the stage's call."""
    if op not in ("flag", "run"):
        raise ValueError(f"a stage writes `flag` or `run` entries, not {op!r}")
    if op == "run":
        _check_period_labels(cfg, periods)
    if not reason.strip():
        raise ValueError("a stage entry needs a non-empty reason")
    if features:
        check_candidates(cfg, features, f"{op} {finding} refused")
    entries = _load_entries(cfg, entity, env)
    operands = {
        "features": features,
        "finding": finding,
        "periods": periods,
        "run_id": run_id,
        "replayed_to": replayed_to,
        "resolved_input_hash": resolved_input_hash,
    }
    entry = Entry(
        seq=len(entries) + 1,
        time=_now(),
        by=By(kind="stage", id=stage),
        stage=stage,
        op=op,
        reason=reason,
        evidence=list(evidence),
        data_definition_hash=data_definition_hash(cfg, entity),
        hash_version=HASH_VERSION,
        log_schema_version=LOG_SCHEMA_VERSION,
        **{name: value for name, value in operands.items() if value is not None},
    )
    return _write_entry(entry, audit_log_dir(env, cfg, entity))


def _what(entry: Entry) -> str:
    """The features (a flag led by its finding, a keep followed by the findings it settles),
    `path: from → to`, `to #n` for a revert, or a run's id and the periods it compared."""
    if entry.op == "revert":
        return f"to #{entry.to_seq}"
    if entry.op == "flag":
        return f"{entry.finding}: {', '.join(entry.features) or 'none (closes the finding)'}"
    if entry.features:
        settles = f" (settles {', '.join(entry.findings)})" if entry.findings else ""
        return ", ".join(entry.features) + settles
    if entry.path:
        return f"{entry.path}: {entry.from_value} → {entry.to_value}"
    periods = ""
    if entry.periods:
        first, last = min(entry.periods), max(entry.periods)
        periods = f"periods {first}" if first == last else f"periods {first} … {last}"
    return " ".join(part for part in (entry.run_id, periods) if part)


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
