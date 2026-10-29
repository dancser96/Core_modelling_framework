"""The identities (D-088): the hashes that decide what reruns.

Each hash is sha256 over the canonical JSON of a dict that names its parts, taken from the
validated model's JSON dump (dates become ISO strings), so one config hashes the same on a laptop
and inside the bank, and no two kinds of hash can coincide by content. The config hash keys the
use-case definition, the data-definition hash the EDA and Feature Checks artifacts, the target-spec
hash the saved model input (D-131), and the resolved-input hash the run (D-125). Writers store
`HASH_VERSION` beside every hash; `short` gives the prefix used in paths and `run_id`.
"""

import hashlib
import json

from core_modelling.config.schema import UseCaseConfig

HASH_VERSION = 1
REPLAY_FIELDS = {"excluded", "kept_despite_flags"}  # `features` lists the audit log's replay writes


def canonical_json(data: dict) -> str:
    """Sorted keys and no whitespace: the one serialisation every hash is taken over."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def short(digest: str) -> str:
    """The 12-character prefix of a digest, for paths and `run_id`."""
    return digest[:12]


def _sha256(text: str) -> str:
    """The full hex digest of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sources(cfg: UseCaseConfig, entity: str) -> dict:
    """An entity's sources as plain data; an entity the config doesn't list fails naming them."""
    if entity not in cfg.entities:
        raise ValueError(f"entity {entity!r} is not in the config; listed: {sorted(cfg.entities)}")
    return cfg.entities[entity].sources.model_dump(mode="json")


def config_hash(cfg: UseCaseConfig) -> str:
    """Every section after level resolution, without housekeeping and the replayed lists."""
    data = cfg.model_dump(mode="json", exclude={"housekeeping": True, "features": REPLAY_FIELDS})
    return _sha256(canonical_json({"config": data}))


def data_definition_hash(cfg: UseCaseConfig, entity: str) -> str:
    """Entity, task, sources, keys, eligibility, target, period, observation window, `w` and
    candidates."""
    parts = {
        "entity": entity,
        "task": cfg.task,
        "sources": _sources(cfg, entity),
        "data": cfg.data.model_dump(mode="json", include={"keys", "eligibility", "target"}),
        "time": cfg.time.model_dump(
            mode="json", include={"period", "observation_window", "target_window"}
        ),
        "features": cfg.features.model_dump(mode="json", include={"candidates"}),
    }
    return _sha256(canonical_json(parts))


def target_spec_hash(cfg: UseCaseConfig, entity: str) -> str:
    """Task, target spec, keys, `w` and the entity's target source: what one label column
    depends on (the same upstream column read as binary and as regression is two labels)."""
    parts = {
        "task": cfg.task,
        "target": cfg.data.target.model_dump(mode="json"),
        "keys": cfg.data.keys.model_dump(mode="json"),
        "target_window": cfg.time.target_window,
        "target_source": _sources(cfg, entity)["targets"],
    }
    return _sha256(canonical_json(parts))


def resolved_input_hash(resolved: UseCaseConfig) -> str:
    """The run's one input (config plus replayed entries, D-125), without housekeeping."""
    data = resolved.model_dump(mode="json", exclude={"housekeeping"})
    return _sha256(canonical_json({"resolved_input": data}))
