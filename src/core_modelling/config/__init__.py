"""The config spine: load a use-case YAML into a validated `UseCaseConfig`.

Load = read YAML → `migrate` → refuse what only a replay writes → `apply_level_defaults` →
validate. The audit log's replay (`replay.py`) runs later, in `resolve_config` (`audit_log.py`),
on the loaded config.
"""

from pathlib import Path

import yaml

from core_modelling.config.levels import apply_level_defaults
from core_modelling.config.migrations import CURRENT_SCHEMA_VERSION, MIGRATIONS, migrate
from core_modelling.config.schema import UseCaseConfig

__all__ = ["UseCaseConfig", "load_config"]


def _refuse_replay_fields(raw: dict, path: str | Path) -> None:
    """A config file carries intent only: the replayed lists and housekeeping come from the audit
    log's replay (D-125), never from the file."""
    features = raw.get("features") if isinstance(raw.get("features"), dict) else {}
    for name, entry in (("excluded", "an exclude"), ("kept_despite_flags", "a keep_despite_flag")):
        if features.get(name):
            raise ValueError(
                f"config {path}: features.{name} is written by the audit log's replay; record "
                f"{entry} entry instead (D-125)"
            )
    if raw.get("housekeeping") is not None:
        raise ValueError(
            f"config {path}: housekeeping is written by resolve_config, not by a config file; "
            "a resolved config is read back with read_resolved_config (D-125)"
        )


def load_config(path: str | Path) -> UseCaseConfig:
    """Read, migrate, level-resolve and validate one use-case config file."""
    raw = yaml.safe_load(Path(path).read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"config {path} must be a YAML mapping, got {type(raw).__name__}")
    raw = migrate(raw, MIGRATIONS, CURRENT_SCHEMA_VERSION, "config")
    _refuse_replay_fields(raw, path)
    return UseCaseConfig.model_validate(apply_level_defaults(raw))
