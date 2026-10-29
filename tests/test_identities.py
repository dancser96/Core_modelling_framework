"""The identities (D-088): each hash moves with exactly the parts it covers and nothing else."""

import re
from datetime import date
from pathlib import Path

import pytest

from core_modelling.config import UseCaseConfig, load_config
from core_modelling.config.identities import (
    HASH_VERSION,
    config_hash,
    data_definition_hash,
    resolved_input_hash,
    short,
    target_spec_hash,
)
from core_modelling.config.replay import set_at

EXAMPLE = Path(__file__).resolve().parents[1] / "conf/base/cc_acquisition.yml"
ENTITY = "entity_a"
# The example's digests under HASH_VERSION 1 (re-pinned 2026-10-28 when the unit of analysis
# became `time.period`, the `time` fields and `data.keys.period` were renamed and `task` joined
# both hashes); test_golden_hashes_of_the_example says what a change means.
GOLDEN = {
    "data_definition": "87db23cd29669a7e625562449f7aab0121b2e9847943fff60249b89be0f1a6b5",
    "target_spec": "ed51852ef4acb007730d569c91cbdc6780f65c21d47f8c098357275ee3594e68",
}


@pytest.fixture
def cfg() -> UseCaseConfig:
    """The example config, loaded through the public path."""
    return load_config(EXAMPLE)


def _variant(cfg: UseCaseConfig, path: str, value: object) -> UseCaseConfig:
    """The config re-validated with the field at a dotted path replaced."""
    return UseCaseConfig.model_validate(set_at(cfg.model_dump(), path, value))


def _all_hashes(cfg: UseCaseConfig) -> dict[str, str]:
    """The four identities of one config on the example entity."""
    return {
        "config": config_hash(cfg),
        "data_definition": data_definition_hash(cfg, ENTITY),
        "target_spec": target_spec_hash(cfg, ENTITY),
        "resolved_input": resolved_input_hash(cfg),
    }


def _changed(before: UseCaseConfig, after: UseCaseConfig) -> set[str]:
    """The names of the identities that differ between two configs."""
    first, second = _all_hashes(before), _all_hashes(after)
    return {name for name in first if first[name] != second[name]}


def test_same_config_hashes_the_same_twice(cfg: UseCaseConfig) -> None:
    """Two loads of one file give the same four full sha256 digests, all distinct."""
    hashes = _all_hashes(cfg)
    assert hashes == _all_hashes(load_config(EXAMPLE))
    assert all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest in hashes.values())
    assert len(set(hashes.values())) == 4


def test_golden_hashes_of_the_example(cfg: UseCaseConfig) -> None:
    """The example's data-definition and target-spec digests are pinned. A failure here means the
    canonical form of a hashed section changed (a renamed or added field, another dump). Until
    the December pre-release nothing is kept inside the bank, so re-pin the digests; from then on,
    bump `HASH_VERSION` and decide how artifacts written under the old one are read (D-088)."""
    assert HASH_VERSION == 1
    assert data_definition_hash(cfg, ENTITY) == GOLDEN["data_definition"]
    assert target_spec_hash(cfg, ENTITY) == GOLDEN["target_spec"]


def test_validation_period_moves_only_the_config_and_resolved_input(cfg: UseCaseConfig) -> None:
    """EDA and Feature Checks never depend on the validation period (D-088)."""
    moved = _variant(cfg, "time.validation_period", date(2025, 12, 1))
    assert _changed(cfg, moved) == {"config", "resolved_input"}


def test_period_moves_the_data_definition_not_the_target_spec(cfg: UseCaseConfig) -> None:
    """Another unit of analysis is another data definition; the label column's identity stays
    with the target spec, keys and `w`."""
    weekly = _variant(cfg, "time", {**cfg.model_dump()["time"], "period": "week"})
    assert _changed(cfg, weekly) == {"config", "data_definition", "resolved_input"}


def test_task_moves_the_data_definition_and_the_target_spec(cfg: UseCaseConfig) -> None:
    """The same upstream target column read as binary and as regression is another data
    definition and another label column."""
    regression = _variant(cfg, "task", "regression")
    assert _changed(cfg, regression) >= {"data_definition", "target_spec"}


def test_candidate_pattern_moves_the_data_definition_not_the_target_spec(
    cfg: UseCaseConfig,
) -> None:
    """A candidate change reruns EDA but leaves the label column's identity alone."""
    narrowed = _variant(cfg, "features.candidates.exclude", ["login_*"])
    assert _changed(cfg, narrowed) == {"config", "data_definition", "resolved_input"}


def test_entity_name_is_in_the_data_definition_hash(cfg: UseCaseConfig) -> None:
    """Two entities with identical sources need their own EDA artifacts (D-034)."""
    entities = cfg.model_dump()["entities"]
    both = _variant(cfg, "entities", {**entities, "entity_b": entities[ENTITY]})
    assert data_definition_hash(both, "entity_a") != data_definition_hash(both, "entity_b")
    assert target_spec_hash(both, "entity_a") == target_spec_hash(both, "entity_b")


def test_training_budget_moves_only_the_config_and_resolved_input(cfg: UseCaseConfig) -> None:
    """A stage section never reruns EDA or rebuilds the model input."""
    assert _changed(cfg, _variant(cfg, "training.max_iter", 7)) == {"config", "resolved_input"}


def test_replayed_exclusions_move_the_resolved_input_not_the_config(cfg: UseCaseConfig) -> None:
    """A decision in the audit log leaves the config hash unchanged (D-088)."""
    resolved = _variant(cfg, "features.excluded", ["nationality"])
    assert _changed(cfg, resolved) == {"resolved_input"}
    kept = _variant(cfg, "features.kept_despite_flags", ["age"])
    assert _changed(cfg, kept) == {"resolved_input"}


def test_housekeeping_changes_nothing(cfg: UseCaseConfig) -> None:
    """The housekeeping block records a run; it is outside every hash."""
    stamped = _variant(cfg, "housekeeping", {"framework_version": "0.1.0"})
    assert _changed(cfg, stamped) == set()


def test_unknown_entity_fails_naming_the_listed_ones(cfg: UseCaseConfig) -> None:
    """Both entity-keyed hashes refuse an entity the config doesn't list."""
    with pytest.raises(ValueError, match=r"'entity_z'.*\['entity_a'\]"):
        data_definition_hash(cfg, "entity_z")
    with pytest.raises(ValueError, match=r"'entity_z'.*\['entity_a'\]"):
        target_spec_hash(cfg, "entity_z")


def test_short_gives_twelve_characters(cfg: UseCaseConfig) -> None:
    """The prefix used in paths and `run_id` is the digest's first 12 characters."""
    digest = config_hash(cfg)
    assert short(digest) == digest[:12] and len(short(digest)) == 12
