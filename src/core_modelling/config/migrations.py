"""Schema migrations (CLAUDE.md §2): old files keep loading, with a deprecation warning.

A migration is keyed by the `schema_version` it starts from, turns a raw dict of that version into
the next one and sets `schema_version` itself. `migrate` applies them in order up to the current
version; the config's table and version live here, the environment file's in `environment.py`.
No migration exists yet: 0.x promises nothing (D-007 (c)).
"""

import warnings
from collections.abc import Callable

CURRENT_SCHEMA_VERSION = 1

MIGRATIONS: dict[int, Callable[[dict], dict]] = {}


def migrate(
    raw: dict, migrations: dict[int, Callable[[dict], dict]], current: int, what: str
) -> dict:
    """The raw dict of `what` (a config or an environment file) brought to schema version
    `current`, one migration step at a time."""
    version = raw.get("schema_version")
    if not isinstance(version, int):
        raise ValueError(
            f"{what} needs an integer schema_version, got {version!r}; "
            f"add `schema_version: {current}`"
        )
    if version > current:
        raise ValueError(
            f"{what} schema_version {version} is newer than this framework's {current}; "
            "raise the use case's framework pin"
        )
    for step in range(version, current):
        if step not in migrations:
            raise ValueError(f"no migration from {what} schema_version {step}; rewrite the file")
        warnings.warn(
            f"{what} schema_version {step} is deprecated; migrated to {step + 1} at load. "
            f"Rewrite the file at schema_version {current}",
            DeprecationWarning,
            stacklevel=2,
        )
        raw = migrations[step](raw)
    return raw
