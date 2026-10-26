"""Automation-level defaults (D-023, D-132): what a config leaves null, the level fills.

`LEVEL_DEFAULTS` maps a dotted path in the config to one value per level. `apply_level_defaults`
runs on the raw dict before validation and fills a path only when it is absent or null, so an
explicit value always wins, and it records the filled paths in `housekeeping.level_filled`, so a
later level move (a `set` on `automation_level` in the audit log) refills exactly those paths from
the new level and leaves the explicit values alone. A `set` entry on a filled path, or on a
section holding one, makes it explicit too: it leaves the list, so a level move after it keeps the
person's value.
"""

import copy

LEVELS = ("autonomous", "assisted")

LEVEL_DEFAULTS: dict[str, dict[str, object]] = {
    "eda.key_features.top_n": {"autonomous": 10, "assisted": 20},
    "training.max_iter": {"autonomous": 50, "assisted": 200},
    "evaluation.slices.top_pct": {"autonomous": [0.01, 0.1], "assisted": [0.01, 0.05, 0.1]},
}


def _check_level(level: object) -> str:
    """The level unchanged when it is a known one."""
    if level not in LEVELS:
        raise ValueError(f"automation_level must be one of {LEVELS}, got {level!r}")
    return level


def apply_level_defaults(raw: dict) -> dict:
    """A copy of the raw config with every null or absent level-default path filled and the filled
    paths recorded in `housekeeping.level_filled`."""
    level = _check_level(raw.get("automation_level"))
    resolved = copy.deepcopy(raw)
    filled = [
        path
        for path, by_level in LEVEL_DEFAULTS.items()
        if _fill(resolved, path.split("."), copy.deepcopy(by_level[level]))
    ]
    resolved["housekeeping"] = {"level_filled": filled}
    return resolved


def level_filled(raw: dict) -> list[str]:
    """The paths `apply_level_defaults` filled; a dict that skipped it fails loud."""
    housekeeping = raw.get("housekeeping") or {}
    if "level_filled" not in housekeeping:
        raise ValueError(
            "the config carries no housekeeping.level_filled; load it with load_config"
        )
    return housekeeping["level_filled"]


def refill_level_defaults(raw: dict, level: str) -> dict:
    """The raw config with exactly the level-filled paths set from `level`'s defaults (in place);
    explicit values stay."""
    _check_level(level)
    for path in level_filled(raw):
        *parents, leaf = path.split(".")
        node = raw
        for key in parents:
            node = node[key]
        node[leaf] = copy.deepcopy(LEVEL_DEFAULTS[path][level])
    return raw


def unmark_level_filled(raw: dict, path: str) -> dict:
    """The raw config with `path` and the level-filled paths under it taken off
    `housekeeping.level_filled` (in place): a `set` entry made them explicit."""
    raw["housekeeping"]["level_filled"] = [
        filled
        for filled in level_filled(raw)
        if filled != path and not filled.startswith(f"{path}.")
    ]
    return raw


def _fill(node: dict, keys: list[str], value: object) -> bool:
    """Set `value` at the nested path when it is absent or null, creating missing sections;
    whether it was set."""
    for key in keys[:-1]:
        if node.get(key) is None:
            node[key] = {}
        node = node[key]
        if not isinstance(node, dict):
            return False  # not a section; the schema reports it
    if node.get(keys[-1]) is not None:
        return False
    node[keys[-1]] = value
    return True
