"""From entries to the resolved config (D-125): the entry model and what each operation does.

An `Entry` is one decision. `APPLY_BY_OP` maps every allowed operation to one small function on
the config's raw dict; `replay` runs entries 1–n through it in one pass, keeping the state after
each entry, and the result validated by the config schema is the resolved config, a run's one
input. A `set` changes a setting, one of the paths in `LOGGABLE_SETTINGS`. A `revert` takes the
stored state after entry `to_seq` (the entries after it stay as the trail). The feature entries
change the three feature lists, which the replay writes last from the effective entries (the ones
no revert undid): `features.excluded` and `features.kept` from `decisions_in_force`, the one walk
of what exclude, include and keep mean, and `features.held` from the open flags (`open_flags`),
which Training leaves out (D-134). The other operations are the trail. `check_resolved` refuses
a config that was only loaded where the resolved one is needed, and `dump_resolved` is the
resolved config's one YAML form. Storage, writing and the public functions live in
`audit_log.py`.
"""

import copy
from collections.abc import Callable
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import ConfigDict, Field, ValidationError, model_validator

from core_modelling.config.identities import REPLAY_FIELDS, resolved_input_hash, short
from core_modelling.config.levels import refill_level_defaults, unmark_level_filled
from core_modelling.config.schema import StrictModel, UseCaseConfig

Op = Literal[
    "exclude", "include", "keep", "set",
    "revert", "flag", "dropped", "sign_off", "register", "promote", "run",
]  # fmt: skip
FEATURE_OPS = {"exclude", "include", "keep", "flag", "dropped"}
INPUT_FEATURE_OPS = {"exclude", "include", "keep", "flag"}  # the ones replay checks
Finding = Annotated[str, Field(pattern=r"^[a-z_]+\.[a-z_]+$")]  # `<step>.<finding>`

# Setting path → the stage that reruns from it. Never listed: the data definition and `decision`
# (declared before any result, §4.3); `data.split` and `training.seed`, since a test score must not
# pick its own sample or seed. `lifecycle`, `inference` and `monitoring` wait for M2.4 and M4. A
# new schema field is not loggable until it is added here.
LOGGABLE_SETTINGS: dict[str, str] = {
    "automation_level": "eda",  # a level move reruns every stage from EDA (D-132)
    "features.kinds": "eda",  # how a column is read; outside the data-definition hash
    "strata.variables": "eda",
    "strata.max_levels": "eda",
    "strata.min_events": "eda",
    "eda.snapshot": "eda",
    "eda.bins": "eda",
    "eda.key_features.top_n": "eda",
    "eda.key_features.include": "eda",
    "eda.key_features.max_correlation": "eda",
    # Every threshold of the five steps, one leaf each; a step left out of the config is not run,
    # so a `set` under it is refused (`check_settable`).
    "feature_checks.quality.dominant_share_max": "feature_checks",
    "feature_checks.quality.missing_share_max": "feature_checks",
    "feature_checks.quality.max_levels": "feature_checks",
    "feature_checks.quality.nulls_may_be_zeros.missing_min": "feature_checks",
    "feature_checks.quality.nulls_may_be_zeros.zero_share_max": "feature_checks",
    "feature_checks.quality.nulls_informative_min": "feature_checks",
    "feature_checks.leakage.concordance_max": "feature_checks",
    "feature_checks.leakage.null_concordance_max": "feature_checks",
    "feature_checks.leakage.rare_effect_max": "feature_checks",
    "feature_checks.leakage.dominant_share_min": "feature_checks",
    "feature_checks.time_alignment.signal_kept_min": "feature_checks",
    "feature_checks.time_alignment.constant_clients_min": "feature_checks",
    "feature_checks.time_alignment.concordance_min": "feature_checks",
    "feature_checks.stability.psi_note_min": "feature_checks",
    "feature_checks.stability.psi_max": "feature_checks",
    "feature_checks.stability.heterogeneity_p_max": "feature_checks",
    "feature_checks.stability.concordance_range_min": "feature_checks",
    "feature_checks.stability.concordance_range_floor": "feature_checks",
    "feature_checks.stability.new_level_share_max": "feature_checks",
    "feature_checks.redundancy.correlation_max": "feature_checks",
    "feature_checks.redundancy.association_max": "feature_checks",
    "training.estimator_list": "training",
    "training.max_iter": "training",
    "training.time_budget_s": "training",
    "training.search_space": "training",
    "training.selection.univariate_floor": "training",
    "training.selection.importance_floor": "training",
    "training.categoricals.min_level_count": "training",
    "training.calibration.method": "training",
    "training.sampling": "training",
    # EDA reads these two: the compared periods, and its decision-slices view.
    "time.validation_period": "eda",  # refused once Feature Checks compared it (D-088)
    "evaluation.slices.top_pct": "eda",
    "evaluation.slices.top_n": "eda",
    "evaluation.views": "evaluation",
}


class By(StrictModel):
    """Who decided: a person (user id), a rule (its name) or a stage."""

    kind: Literal["person", "rule", "stage"]
    id: str


# Each operand → the operations that take it; any other operation given it is refused.
OPS_BY_OPERAND: dict[str, set[str]] = {
    "features": FEATURE_OPS,
    "path": {"set"},
    "from_value": {"set"},
    "to_value": {"set"},
    "to_seq": {"revert"},
    "finding": {"flag"},
    "findings": {"keep"},
    "periods": {"run"},
    "run_id": {"run"},
    "replayed_to": {"run"},
    "resolved_input_hash": {"run"},
}


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
    finding: Finding | None = None  # flag: the finding whose feature set it records
    findings: list[Finding] | None = None  # keep: the flags it settles, possibly none
    periods: list[str] | None = None  # Feature Checks' run: the period labels it compared
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
        """Each operand belongs to its operations (`OPS_BY_OPERAND`), counted when given, even as
        null. A feature op names its features, empty only in a `flag` (which closes its finding);
        a `flag` names its finding, a `keep` the findings it settles; a `set` names its path and
        the new value, which may be null (e.g. sampling off); a `revert` names an earlier state
        (`to_seq` below its own `seq`)."""
        for field, ops in OPS_BY_OPERAND.items():
            if field in self.model_fields_set and self.op not in ops:
                stored = field.removesuffix("_value")  # `from` / `to` as stored
                raise ValueError(f"entry {self.seq}: op {self.op!r} takes no `{stored}`")
        if self.op == "revert" and (self.to_seq is None or self.to_seq >= self.seq):
            raise ValueError(
                f"entry {self.seq}: op 'revert' needs `to_seq` below {self.seq} (an earlier "
                "entry, or 0 for the config as written)"
            )
        if self.op == "flag" and (self.finding is None or self.features is None):
            raise ValueError(
                f"entry {self.seq}: op 'flag' needs `finding` and `features` (empty only to "
                "close the finding)"
            )
        if self.op == "keep" and self.findings is None:
            raise ValueError(
                f"entry {self.seq}: op 'keep' needs `findings`, the flags it settles (may be [])"
            )
        if self.op in FEATURE_OPS - {"flag"} and not self.features:
            raise ValueError(f"entry {self.seq}: op {self.op!r} needs a non-empty `features`")
        if self.op == "set" and (self.path is None or "to_value" not in self.model_fields_set):
            raise ValueError(f"entry {self.seq}: op 'set' needs `path` and `to` (`to` may be null)")
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


def check_settable(raw: dict, path: str, context: str) -> None:
    """Refuse a dotted path under a section the config leaves null: a `feature_checks` step left
    out of a present mapping is not run, so it has no threshold to set (D-137)."""
    *parents, _ = path.split(".")
    node = raw
    for depth, key in enumerate(parents, start=1):
        node = node[key]
        if node is None:
            section = ".".join(parents[:depth])
            raise ValueError(
                f"{context}: {section} is not in this config, so {path} cannot be set; add "
                f"{section} to the config first (a feature_checks step left out is not run)"
            )


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
    """An entry that changes no setting: a trail entry, recorded only, or a feature entry, which
    acts through the feature lists `replay` writes last from the effective entries."""
    return raw


APPLY_BY_OP: dict[str, Callable[[dict, Entry], dict]] = {
    "exclude": _leave_unchanged,
    "include": _leave_unchanged,
    "keep": _leave_unchanged,
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
    """The config's raw dict after the entries, in one pass; a stale entry fails citing its `seq`.
    `states[n]` is the state after the first n entries (entry n, since the entries run 1..n): a
    `revert` takes `states[to_seq]` and the later entries continue from it. The feature lists are
    written last: the excluded and kept features in force, and the open flags' in `held`. A
    config that sets one of those lists is refused: its values would be overwritten without a
    word (the replay starts from the config as loaded; `resolve_config` refuses a resolved one)."""
    filled = sorted(name for name in REPLAY_FIELDS if getattr(cfg.features, name))
    if filled:
        raise ValueError(
            f"the config sets features.{', features.'.join(filled)}, which the audit log's "
            "replay writes: record exclude and keep entries instead (D-125, D-134)"
        )
    states = [cfg.model_dump(mode="json")]
    for entry in entries:
        if entry.op == "revert":
            states.append(states[entry.to_seq])
            continue
        stale = f"entry {entry.seq} is stale"
        if entry.op in INPUT_FEATURE_OPS:
            check_candidates(cfg, entry.features, stale)
        if entry.op == "set":
            # A hand-edited or old entry must not change the data definition, `decision` or the
            # seed, nor set a threshold of a step the config no longer runs.
            if entry.path not in LOGGABLE_SETTINGS:
                raise ValueError(f"{stale}: {entry.path} is not a loggable setting")
            check_settable(states[-1], entry.path, stale)
        raw = APPLY_BY_OP[entry.op](copy.deepcopy(states[-1]), entry)  # stored states stay as is
        if entry.op == "set":
            validate_raw(raw, f"{stale}: set {entry.path} = {entry.to_value!r}")
        states.append(raw)
    raw = states[-1]
    kept, excluded = decisions_in_force(entries)
    raw["features"]["excluded"] = sorted(excluded)
    raw["features"]["kept"] = sorted(kept)
    raw["features"]["held"] = held_features(entries)
    return raw


def open_flags(entries: list[Entry]) -> dict[str, list[str]]:
    """Per feature, the findings holding it out of training (D-134), over the effective entries:
    each finding's latest `flag` entry names the feature and no `keep` naming the feature and
    that finding settles it. A `keep` settles every (feature, finding) pair it names, which the
    writer stores only when open on every named feature. It stays valid when the same finding
    returns with new values; a different finding opens again. An excluded feature is excluded,
    not held."""
    latest: dict[str, list[str]] = {}  # finding → the features of its latest flag entry
    settled: set[tuple[str, str]] = set()  # (feature, finding)
    for entry in effective_entries(entries):
        if entry.op == "flag":
            latest[entry.finding] = entry.features
        elif entry.op == "keep":
            settled |= {(name, finding) for name in entry.features for finding in entry.findings}
    _, excluded = decisions_in_force(entries)
    flags: dict[str, list[str]] = {}
    for finding, features in latest.items():
        for name in features:
            if name not in excluded and (name, finding) not in settled:
                flags.setdefault(name, []).append(finding)
    return {name: sorted(flags[name]) for name in sorted(flags)}


def held_features(entries: list[Entry]) -> list[str]:
    """The features with an open flag, sorted: for Training, excluded features without a final
    decision (D-134)."""
    return list(open_flags(entries))


def effective_entries(entries: list[Entry]) -> list[Entry]:
    """The entries that shape the current state once every revert is applied, in one pass:
    `after[n]` are the effective entries after the first n, and a revert takes `after[to_seq]`
    the way `replay` takes the state; reverts themselves are never effective."""
    after: list[list[Entry]] = [[]]
    for entry in entries:
        after.append(after[entry.to_seq] if entry.op == "revert" else [*after[-1], entry])
    return after[-1]


def decisions_in_force(entries: list[Entry]) -> tuple[dict[str, list[int]], dict[str, int]]:
    """Per feature, over the effective entries: the `seq`s of its `keep` entries, and the `seq`
    of its latest `exclude` that no later `include` reversed."""
    kept: dict[str, list[int]] = {}
    excluded: dict[str, int] = {}
    for entry in effective_entries(entries):
        for feature in entry.features or []:
            if entry.op == "keep":
                kept.setdefault(feature, []).append(entry.seq)
            elif entry.op == "exclude":
                excluded[feature] = entry.seq
            elif entry.op == "include":
                excluded.pop(feature, None)
    return kept, excluded


def _origins(entries: list[Entry]) -> dict[str, int]:
    """Each changed value's key → the entry that set it (the latest wins, an include removes, a
    revert restarts from the earlier state); a held feature → the latest flag entry holding it.
    It walks the effective entries itself rather than reading `decisions_in_force`: the keys'
    order, the resolved file's header order, is the order the values were first set."""
    origins: dict[str, int] = {}
    effective = effective_entries(entries)
    for entry in effective:
        if entry.op == "set":
            origins[entry.path] = entry.seq
        elif entry.op == "exclude":
            origins.update({f"features.excluded.{name}": entry.seq for name in entry.features})
        elif entry.op == "include":
            for name in entry.features:
                origins.pop(f"features.excluded.{name}", None)
        elif entry.op == "keep":
            origins.update({f"features.kept.{name}": entry.seq for name in entry.features})
    latest_flag = {entry.finding: entry.seq for entry in effective if entry.op == "flag"}
    for name, findings in open_flags(entries).items():
        origins[f"features.held.{name}"] = max(latest_flag[finding] for finding in findings)
    return origins


def check_resolved(cfg: UseCaseConfig, what: str) -> None:
    """Refuse a config that was only loaded where `what` needs the resolved one (a loaded config's
    replayed lists are empty, so it would pass a held or excluded feature as usable), and a
    resolved one whose content no longer matches its hash (a list emptied by hand in a saved
    file, a value changed in code)."""
    stored = (cfg.housekeeping or {}).get("resolved_input_hash")
    if stored is None:
        raise ValueError(
            f"{what} needs the resolved config, not a loaded one (its housekeeping has no "
            "resolved_input_hash and its held and excluded lists are empty): pass "
            "resolve_config(...)'s result"
        )
    if stored != resolved_input_hash(cfg):
        raise ValueError(
            f"{what}: the config's content no longer matches its resolved_input_hash (changed "
            "after it was resolved, or migrated from an older schema): resolve it again with "
            "resolve_config(...)"
        )


def dump_resolved(resolved: UseCaseConfig) -> str:
    """The resolved config as YAML, the one serialisation every writer of it uses."""
    return yaml.safe_dump(resolved.model_dump(mode="json"), sort_keys=False, allow_unicode=True)


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
    Path(save_to).write_text("\n".join(header) + "\n" + dump_resolved(resolved))
