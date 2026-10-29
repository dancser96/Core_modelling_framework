"""From entries to the resolved config (D-125): the entry model and what each operation does.

An `Entry` is one decision. `APPLY_BY_OP` maps every allowed operation to one small function on
the config's raw dict; `replay` runs entries 1–n through it, and the result validated by the
config schema is the resolved config, a run's one input. Only `exclude`, `include`,
`keep_despite_flag` and `set` change the input; `set` may touch the paths in `LOGGABLE_SETTINGS`
only. A `revert` restarts the replay from an earlier state (the entries after it stay as the
trail). The other operations are the trail. Storage, writing and the public functions live in
`audit_log.py`.
"""

from collections.abc import Callable
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Literal

import yaml
from pydantic import ConfigDict, Field, ValidationError, model_validator

from core_modelling.config.identities import short
from core_modelling.config.levels import refill_level_defaults, unmark_level_filled
from core_modelling.config.schema import StrictModel, UseCaseConfig

Op = Literal[
    "exclude", "include", "keep_despite_flag", "set",
    "revert", "flag", "dropped", "sign_off", "register", "promote", "run",
]  # fmt: skip
FEATURE_OPS = {"exclude", "include", "keep_despite_flag", "flag", "dropped"}
INPUT_FEATURE_OPS = {"exclude", "include", "keep_despite_flag"}  # the ones replay checks

# Setting path → the stage that reruns from it. Never listed: the data definition and `decision`
# (declared before any result, §4.3); `data.split` and `training.seed`, since a test score must not
# pick its own sample or seed. `lifecycle`, `inference` and `monitoring` wait for M2.4 and M4. A
# new schema field is not loggable until it is added here.
LOGGABLE_SETTINGS: dict[str, str] = {
    "automation_level": "eda",  # a level move reruns every stage from EDA (D-132)
    "strata.variables": "eda",
    "strata.max_levels": "eda",
    "strata.min_events": "eda",
    "eda.key_features.top_n": "eda",
    "eda.key_features.include": "eda",
    "eda.chart_sample_share": "eda",
    "feature_checks.steps": "feature_checks",
    "training.estimator_list": "training",
    "training.max_iter": "training",
    "training.time_budget_s": "training",
    "training.search_space": "training",
    "training.selection.univariate_floor": "training",
    "training.selection.importance_floor": "training",
    "training.categoricals.min_level_count": "training",
    "training.calibration.method": "training",
    "training.sampling": "training",
    "time.validation_period": "evaluation",  # refused once Feature Checks compared it: M2.2 (D-088)
    "evaluation.slices.top_pct": "evaluation",
    "evaluation.slices.top_n": "evaluation",
    "evaluation.views": "evaluation",
}


class By(StrictModel):
    """Who decided: a person (user id), a rule (its name) or a stage."""

    kind: Literal["person", "rule", "stage"]
    id: str


SET_ONLY_FIELDS = ("path", "from_value", "to_value")


class Entry(StrictModel):
    """One decision as stored; `from_value` / `to_value` are written as `from` / `to`."""

    # `to: null` (a setting switched off) must differ from `to` absent, so the entry tracks the
    # fields it was given (`model_fields_set`) and the writer dumps only those (`exclude_unset`).
    model_config = ConfigDict(validate_by_name=True)

    seq: int = Field(ge=1)
    time: str
    by: By
    stage: str
    op: Op
    features: list[str] | None = None
    path: str | None = None
    from_value: object | None = Field(default=None, alias="from")
    to_value: object | None = Field(default=None, alias="to")
    to_seq: int | None = Field(default=None, ge=0)  # revert: 0 is the config as written
    reason: str
    evidence: list[str] = []
    data_definition_hash: str
    hash_version: int
    log_schema_version: int
    run_id: str | None = None
    replayed_to: int | None = None
    resolved_input_hash: str | None = None

    @model_validator(mode="after")
    def _check_operands(self) -> "Entry":
        """A feature op names its features and nothing of a `set`; a `set` names its path and the
        new value, which may be null (e.g. switching sampling off), and no features; a `revert`
        names an earlier state (`to_seq` below its own `seq`) and nothing else."""
        given = self.model_fields_set
        if self.op == "revert":
            if self.to_seq is None or self.to_seq >= self.seq:
                raise ValueError(
                    f"entry {self.seq}: op 'revert' needs `to_seq` below {self.seq} (an earlier "
                    "entry, or 0 for the config as written)"
                )
            if self.features is not None or given & set(SET_ONLY_FIELDS):
                raise ValueError(
                    f"entry {self.seq}: op 'revert' takes no features / path / from / to"
                )
        elif self.to_seq is not None:
            raise ValueError(f"entry {self.seq}: op {self.op!r} takes no `to_seq`")
        if self.op in FEATURE_OPS:
            if not self.features:
                raise ValueError(f"entry {self.seq}: op {self.op!r} needs a non-empty `features`")
            if given & set(SET_ONLY_FIELDS):
                raise ValueError(f"entry {self.seq}: op {self.op!r} takes no path / from / to")
        if self.op == "set":
            if self.path is None or "to_value" not in given:
                raise ValueError(
                    f"entry {self.seq}: op 'set' needs `path` and `to` (`to` may be null)"
                )
            if self.features is not None:
                raise ValueError(f"entry {self.seq}: op 'set' takes no `features`")
        return self


def get_at(raw: dict, path: str) -> object:
    """The value at a dotted path of the raw config."""
    node = raw
    for key in path.split("."):
        node = node[key]
    return node


def set_at(raw: dict, path: str, value: object) -> dict:
    """The raw config with `value` written at a dotted path (in place)."""
    *parents, leaf = path.split(".")
    node = raw
    for key in parents:
        node = node[key]
    node[leaf] = value
    return raw


def _add_once(names: list[str], features: list[str]) -> None:
    """Append each feature that is not in the list yet (in place)."""
    for feature in features:
        if feature not in names:
            names.append(feature)


def _apply_exclude(raw: dict, entry: Entry) -> dict:
    """Add the entry's features to `features.excluded`."""
    _add_once(raw["features"]["excluded"], entry.features)
    return raw


def _apply_include(raw: dict, entry: Entry) -> dict:
    """Remove the entry's features from `features.excluded`."""
    excluded = raw["features"]["excluded"]
    raw["features"]["excluded"] = [name for name in excluded if name not in entry.features]
    return raw


def _apply_keep(raw: dict, entry: Entry) -> dict:
    """Add the entry's features to `features.kept_despite_flags`."""
    _add_once(raw["features"]["kept_despite_flags"], entry.features)
    return raw


def _apply_set(raw: dict, entry: Entry) -> dict:
    """Write the entry's `to` value at its path; a level move refills the level-filled paths, any
    other `set` makes its path explicit, so a later level move keeps it (D-132)."""
    set_at(raw, entry.path, entry.to_value)
    if entry.path == "automation_level":
        refill_level_defaults(raw, entry.to_value)
    else:
        unmark_level_filled(raw, entry.path)
    return raw


def _leave_unchanged(raw: dict, entry: Entry) -> dict:
    """A trail entry: recorded, but it changes nothing at replay."""
    return raw


APPLY_BY_OP: dict[str, Callable[[dict, Entry], dict]] = {
    "exclude": _apply_exclude,
    "include": _apply_include,
    "keep_despite_flag": _apply_keep,
    "set": _apply_set,
    "flag": _leave_unchanged,
    "dropped": _leave_unchanged,
    "sign_off": _leave_unchanged,
    "register": _leave_unchanged,
    "promote": _leave_unchanged,
    "run": _leave_unchanged,
}


def check_candidates(cfg: UseCaseConfig, features: list[str], context: str) -> None:
    """Refuse a feature that matches no candidate include pattern or matches an exclude pattern
    (the patterns only: the resolved candidate list arrives with the model input)."""
    patterns = cfg.features.candidates
    for feature in features:
        if not any(fnmatchcase(feature, pattern) for pattern in patterns.include):
            raise ValueError(
                f"{context}: {feature!r} matches no candidate include pattern {patterns.include}"
            )
        hit = [pattern for pattern in patterns.exclude if fnmatchcase(feature, pattern)]
        if hit:
            raise ValueError(f"{context}: {feature!r} matches candidate exclude pattern {hit[0]!r}")


def validate_raw(raw: dict, context: str) -> UseCaseConfig:
    """The raw config validated by the schema; a rejection names what was being applied."""
    try:
        return UseCaseConfig.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"{context} is rejected by the config schema:\n{exc}") from exc


def replay(cfg: UseCaseConfig, entries: list[Entry]) -> dict:
    """The entries applied in order to the config's raw dict; a stale one fails citing its `seq`.
    A `revert` restarts from the config with entries 1 … `to_seq` applied (the slice, since the
    entries run 1..n) and the later entries continue from there."""
    raw = cfg.model_dump(mode="json")
    for entry in entries:
        if entry.op == "revert":
            raw = replay(cfg, entries[: entry.to_seq])
            continue
        if entry.op in INPUT_FEATURE_OPS:
            check_candidates(cfg, entry.features, f"entry {entry.seq} is stale")
        # A hand-edited or old entry must not change the data definition, `decision` or the seed.
        if entry.op == "set" and entry.path not in LOGGABLE_SETTINGS:
            raise ValueError(f"entry {entry.seq} is stale: {entry.path} is not a loggable setting")
        raw = APPLY_BY_OP[entry.op](raw, entry)
        if entry.op == "set":
            validate_raw(raw, f"entry {entry.seq} is stale: set {entry.path} = {entry.to_value!r}")
    return raw


def effective_entries(entries: list[Entry]) -> list[Entry]:
    """The entries that shape the current state once every revert is applied: a revert drops the
    entries after its `to_seq` up to itself (restarting the way `replay` does), and reverts
    themselves are never effective."""
    effective: list[Entry] = []
    for entry in entries:
        if entry.op == "revert":
            effective = effective_entries(entries[: entry.to_seq])
        else:
            effective.append(entry)
    return effective


def _origins(entries: list[Entry]) -> dict[str, int]:
    """Each changed value's key → the entry that set it (the latest wins, an include removes, a
    revert restarts from the earlier state)."""
    origins: dict[str, int] = {}
    for entry in effective_entries(entries):
        if entry.op == "set":
            origins[entry.path] = entry.seq
        elif entry.op == "exclude":
            origins.update({f"features.excluded.{name}": entry.seq for name in entry.features})
        elif entry.op == "include":
            for name in entry.features:
                origins.pop(f"features.excluded.{name}", None)
        elif entry.op == "keep_despite_flag":
            origins.update(
                {f"features.kept_despite_flags.{name}": entry.seq for name in entry.features}
            )
    return origins


def write_resolved(resolved: UseCaseConfig, entries: list[Entry], save_to: str | Path) -> None:
    """The resolved config as YAML under a comment header: the entries replayed, each revert and,
    per changed value, the entry that set it. `resolved.housekeeping` is filled already."""
    housekeeping = resolved.housekeeping
    header = [
        f"# resolved: {resolved.use_case} + entries 1–{housekeeping['replayed_to']} "
        f"(input hash {short(housekeeping['resolved_input_hash'])})"
    ]
    header += [
        f"# entry {e.seq} reverted to the state after #{e.to_seq}"
        for e in entries
        if e.op == "revert"
    ]
    header += [f"# {key}: #{seq}" for key, seq in _origins(entries).items()]
    body = yaml.safe_dump(resolved.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
    Path(save_to).write_text("\n".join(header) + "\n" + body)
