"""The decision audit log: the worked example of `docs/components/config.md` replayed, a revert,
the flags and the held set, every refusal of `record_decision`, the stage writer, the storage
rules and the `decide` command."""

import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import get_args

import pytest
import yaml
from pydantic import BaseModel, ValidationError

from core_modelling.__main__ import main
from core_modelling.config import UseCaseConfig, load_config
from core_modelling.config.audit_log import (
    LOG_SCHEMA_VERSION,
    LOGGABLE_SETTINGS,
    Entry,
    _write_entry,
    read_entries,
    read_resolved_config,
    record_decision,
    record_stage_entry,
    resolve_config,
    show_decisions,
)
from core_modelling.config.identities import (
    HASH_VERSION,
    data_definition_hash,
    resolved_input_hash,
    short,
)
from core_modelling.config.replay import (
    APPLY_BY_OP,
    Op,
    effective_entries,
    open_flags,
    replay,
    validate_raw,
)
from core_modelling.config.schema import FeatureChecks
from core_modelling.environment import EnvironmentConfig, Roots, audit_log_dir

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "conf/base/cc_acquisition.yml"
ENTITY = "entity_a"
LEAKS = ["cc_preapproval_score_trap_leak", "cc_campaign_response_score_trap_leak"]
QUALITY = ["legacy_risk_grade_trap_all_null", "paper_statement_flag_trap_near_constant"]
# Feature Checks' run of the worked example: the six window periods, the gap, the latest period.
COMPARED = [f"2025-{month:02d}" for month in range(3, 11)] + ["2026-02"]
LEAK, UNSTABLE_FINDING = "leakage.too_strong", "stability.concordance_unstable"
UNSTABLE = [
    "login_digital_mobile_cnt",
    "login_digital_mobile_cnt_0_2_months_avg",
    "login_digital_mobile_cnt_0_5_months_avg",
    "login_digital_mobile_cnt_0_5_months_max",
    "login_digital_mobile_cnt_0_5_months_std",
]
NEVER_LOGGABLE = (
    "data.",
    "time.observation_window",
    "time.target_window",
    "entities",
    "features.candidates",
    "decision",
    "training.seed",
    "lifecycle",
    "inference",
    "monitoring",
)


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """The example config copied next to the test's data root."""
    return Path(shutil.copy(EXAMPLE, tmp_path / "cc_acquisition.yml"))


@pytest.fixture
def env_path(tmp_path: Path) -> Path:
    """An environment file whose data root is the test folder."""
    path = tmp_path / "environment.yml"
    # The example config names a model input; mapped but never saved here, so feature decisions
    # are checked against the candidate patterns.
    model_input = {"format": "parquet", "path": str(tmp_path / "model_input")}
    sources = {"entity_a": {"retail_acquisition_input": model_input}}
    content = {"schema_version": 1, "roots": {"data": str(tmp_path)}, "sources": sources}
    path.write_text(yaml.safe_dump(content))
    return path


@pytest.fixture
def env(tmp_path: Path) -> EnvironmentConfig:
    """The same environment as `env_path`, as a model."""
    return EnvironmentConfig(schema_version=1, roots=Roots(data=str(tmp_path)))


@pytest.fixture
def cfg(config_path: Path) -> UseCaseConfig:
    """The copied example config, loaded."""
    return load_config(config_path)


def _write_json(cfg: UseCaseConfig, env: EnvironmentConfig, seq: int, **fields: object) -> Path:
    """Write one entry file by hand (rules and Training's run markers have no writer yet)."""
    log_dir = Path(audit_log_dir(env, cfg, ENTITY))
    log_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "seq": seq,
        "time": f"2026-10-27T10:{seq:02d}:00",
        "reason": "rule outcome",
        "evidence": [],
        "data_definition_hash": data_definition_hash(cfg, ENTITY),
        "hash_version": HASH_VERSION,
        "log_schema_version": LOG_SCHEMA_VERSION,
        **fields,
    }
    path = log_dir / f"{seq:04d}.json"
    path.write_text(json.dumps(entry))
    return path


def _rule(name: str) -> dict:
    """A rule as the writer."""
    return {"kind": "rule", "id": name}


def _entry(cfg: UseCaseConfig, **fields: object) -> Entry:
    """A person's entry 1 built in code, with the given operands."""
    return Entry(
        seq=1,
        time="2026-10-27T11:00:00+00:00",
        by={"kind": "person", "id": "someone"},
        stage="feature_checks",
        reason="r",
        data_definition_hash=data_definition_hash(cfg, ENTITY),
        hash_version=HASH_VERSION,
        log_schema_version=LOG_SCHEMA_VERSION,
        **fields,
    )


def _variant(config_path: Path, candidates: dict) -> Path:
    """A copy of the config with other candidate patterns (another data definition)."""
    raw = yaml.safe_load(config_path.read_text())
    raw["features"]["candidates"] = candidates
    path = config_path.with_name("variant.yml")
    path.write_text(yaml.safe_dump(raw))
    return path


def _flag(cfg: UseCaseConfig, env: EnvironmentConfig, finding: str, features: list[str]) -> Entry:
    """Feature Checks' `flag` entry for one finding, through the stage writer."""
    write = dict(stage="feature_checks", reason=f"{finding} raised")
    return record_stage_entry(
        cfg, ENTITY, env, op="flag", finding=finding, features=features, **write
    )


def _held(cfg: UseCaseConfig, env: EnvironmentConfig) -> list[str]:
    """The held features of the resolved config."""
    return resolve_config(cfg, ENTITY, env).features.held


@pytest.fixture
def worked_example(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """Entries 1–12 of the worked example: Feature Checks through the stage writer, a rule and
    Training's run markers by hand, people through the API."""
    decide = dict(env_path=str(env_path))
    _flag(cfg, env, "quality.all_null", QUALITY[:1])
    _flag(cfg, env, "quality.near_constant", QUALITY[1:])
    _flag(cfg, env, LEAK, LEAKS)
    _flag(cfg, env, UNSTABLE_FINDING, UNSTABLE)
    record_stage_entry(cfg, ENTITY, env, stage="feature_checks", op="run", periods=COMPARED,
                       reason="Feature Checks run")  # fmt: skip
    record_decision(config_path, ENTITY, exclude=LEAKS, evidence=["#3"],
                    reason="Set after the offer, not known at scoring time", **decide)  # fmt: skip
    record_decision(config_path, ENTITY, keep=UNSTABLE, findings=[UNSTABLE_FINDING],
                    evidence=["#4"], reason="Digital adoption trend; monitoring watches it",
                    **decide)  # fmt: skip
    _write_json(cfg, env, 8, by={"kind": "stage", "id": "training"}, stage="training", op="run",
                run_id="r1", replayed_to=7, reason="run")  # fmt: skip
    _write_json(cfg, env, 9, by=_rule("selection.importance"), stage="training", op="dropped",
                features=["age", "tenure_months"])  # fmt: skip
    record_decision(config_path, ENTITY, set={"training.max_iter": 300},
                    reason="AUC still rising at the last trials", **decide)  # fmt: skip
    _write_json(cfg, env, 11, by={"kind": "stage", "id": "training"}, stage="training", op="run",
                run_id="r2", replayed_to=10, reason="run")  # fmt: skip
    record_decision(config_path, ENTITY, exclude=["nationality"], stage="sign_off",
                    reason="Not used for product targeting", **decide)  # fmt: skip


@pytest.fixture
def revert_example(config_path: Path, env_path: Path) -> None:
    """Path A (entries 1–3), a revert to the state after entry 1 (entry 4), path B (entry 5)."""
    decide = dict(env_path=str(env_path))
    record_decision(config_path, ENTITY, exclude=LEAKS, reason="leak", **decide)
    record_decision(config_path, ENTITY, keep=UNSTABLE, reason="trend", **decide)
    record_decision(config_path, ENTITY, set={"training.max_iter": 300}, reason="A", **decide)
    record_decision(config_path, ENTITY, revert_to=1, reason="path A overfits", **decide)
    record_decision(config_path, ENTITY, set={"training.max_iter": 250}, reason="B", **decide)


def _sizes(cfg: UseCaseConfig, env: EnvironmentConfig, upto: int) -> tuple[int, int, int, int]:
    """Excluded, kept and held counts and `max_iter` after entry `upto`."""
    resolved = resolve_config(cfg, ENTITY, env, upto=upto)
    features = resolved.features
    return (
        len(features.excluded),
        len(features.kept),
        len(features.held),
        resolved.training.max_iter,
    )


def test_replay_states_follow_the_worked_example(
    worked_example: None, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """The excluded, kept and held lists and `max_iter` after each entry match the replay table
    (200 is the assisted level's default); the lists are sorted."""
    states = {upto: _sizes(cfg, env, upto) for upto in (0, 5, 6, 7, 10, 12)}
    assert states == {
        0: (0, 0, 0, 200),
        5: (0, 0, 9, 200),
        6: (2, 0, 7, 200),
        7: (2, 5, 2, 200),
        10: (2, 5, 2, 300),
        12: (3, 5, 2, 300),
    }
    final = resolve_config(cfg, ENTITY, env)
    assert final.features.excluded == sorted([*LEAKS, "nationality"])
    assert final.features.kept == sorted(UNSTABLE) and final.features.held == sorted(QUALITY)
    assert final.housekeeping["replayed_to"] == 12


def test_revert_restarts_the_replay_from_the_earlier_state(
    revert_example: None, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """The resolved config is the config plus entries 1 and 5; `upto=3` still reproduces path A, and
    entry 5 was written against the reverted state (its `from` is the level default, not 300)."""
    entries = read_entries(audit_log_dir(env, cfg, ENTITY))
    final = resolve_config(cfg, ENTITY, env)
    one_and_five = validate_raw(replay(cfg, [entries[0], entries[4]]), "entries 1 and 5")
    assert resolved_input_hash(final) == resolved_input_hash(one_and_five)
    assert final.features.kept == [] and final.training.max_iter == 250
    assert final.housekeeping["replayed_to"] == 5
    path_a = resolve_config(cfg, ENTITY, env, upto=3)
    assert path_a.features.kept == UNSTABLE and path_a.training.max_iter == 300
    assert (entries[3].op, entries[3].to_seq, entries[3].stage) == ("revert", 1, "feature_checks")
    assert entries[4].from_value == 200


def test_revert_to_zero_gives_the_config_as_written(
    revert_example: None,
    config_path: Path,
    env_path: Path,
    cfg: UseCaseConfig,
    env: EnvironmentConfig,
) -> None:
    """Entry 6 reverts to 0: the resolved input is the config's own, the log keeps all six."""
    record_decision(config_path, ENTITY, revert_to=0, reason="start over", env_path=str(env_path))
    resolved = resolve_config(cfg, ENTITY, env)
    assert resolved_input_hash(resolved) == resolved_input_hash(
        resolve_config(cfg, ENTITY, env, upto=0)
    )
    assert resolved.housekeeping["replayed_to"] == 6
    assert show_decisions(cfg, ENTITY, env)["what"].tolist()[3:] == [
        "to #1",
        "training.max_iter: 200 → 250",
        "to #0",
    ]


def test_revert_shows_in_the_resolved_file_and_the_table(
    revert_example: None, cfg: UseCaseConfig, env: EnvironmentConfig, tmp_path: Path
) -> None:
    """The YAML header names the revert; the origins are those of the surviving entries only; the
    table row says where it went back to."""
    saved = tmp_path / "resolved.yml"
    resolve_config(cfg, ENTITY, env, save_to=saved)
    lines = saved.read_text().splitlines()
    assert lines[0].startswith("# resolved: cc_acquisition + entries 1–5")
    assert lines[1] == "# entry 4 reverted to the state after #1"
    assert "# training.max_iter: #5" in lines and not [line for line in lines if ": #2" in line]
    table = show_decisions(cfg, ENTITY, env)
    assert (table.loc[3, "op"], table.loc[3, "what"], table.loc[3, "reason"]) == (
        "revert",
        "to #1",
        "path A overfits",
    )


def test_revert_refusals(
    revert_example: None, config_path: Path, env_path: Path, cfg: UseCaseConfig
) -> None:
    """A revert goes to an earlier state only (never the current one or beyond), carries no other
    operand, and a stored entry must point below its own `seq`."""
    decide = dict(env_path=str(env_path))
    for to_seq in (5, 7, -1):
        with pytest.raises(
            ValueError, match=f"revert_to={to_seq} is not an earlier state: the log has 5"
        ):
            record_decision(config_path, ENTITY, revert_to=to_seq, reason="r", **decide)
    with pytest.raises(ValueError, match="exactly one of"):
        record_decision(config_path, ENTITY, revert_to=0, exclude=["age"], reason="r", **decide)
    with pytest.raises(ValidationError, match="entry 1: op 'revert' needs `to_seq` below 1"):
        _entry(cfg, op="revert", to_seq=1)
    with pytest.raises(ValidationError, match="op 'revert' needs `to_seq` below 1"):
        _entry(cfg, op="revert")
    with pytest.raises(ValidationError, match="op 'revert' takes no `features`"):
        _entry(cfg, op="revert", to_seq=0, features=["age"])
    with pytest.raises(ValidationError, match="op 'set' takes no `to_seq`"):
        _entry(cfg, op="set", path="training.max_iter", to=300, to_seq=0)


def test_resolved_input_hash_moves_only_with_input_entries(
    worked_example: None, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """Flag, exclude, keep and set entries change the run's input (a flag through
    `features.held`); runs and drops do not."""
    hashes = [resolved_input_hash(resolve_config(cfg, ENTITY, env, upto=n)) for n in range(13)]
    changed = {n for n in range(1, 13) if hashes[n] != hashes[n - 1]}
    assert changed == {1, 2, 3, 4, 6, 7, 10, 12}


def test_set_entry_records_from_to_and_stage(
    worked_example: None, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """Entry 10 carries the resolved value before, the new value and the setting's stage."""
    entry = read_entries(audit_log_dir(env, cfg, ENTITY))[9]
    assert (entry.path, entry.from_value, entry.to_value) == ("training.max_iter", 200, 300)
    assert entry.stage == "training" and entry.by.kind == "person" and entry.by.id
    assert entry.hash_version == HASH_VERSION and entry.time.endswith("+00:00")
    assert json.loads(Path(audit_log_dir(env, cfg, ENTITY), "0010.json").read_text())["to"] == 300


def test_mixed_case_use_case_writes_under_its_lower_case_folder(
    config_path: Path, env_path: Path, env: EnvironmentConfig
) -> None:
    """`CC_Acquisition` logs under `cc_acquisition`, so names differing only in case share one
    folder on a case-sensitive file system as on a case-insensitive one."""
    raw = yaml.safe_load(config_path.read_text())
    raw["use_case"] = "CC_Acquisition"
    config_path.write_text(yaml.safe_dump(raw))
    record_decision(config_path, ENTITY, exclude=LEAKS, reason="leak", env_path=str(env_path))
    definition = short(data_definition_hash(load_config(config_path), ENTITY))
    folder = Path(env.roots.data, "cc_acquisition", "04_feature", definition, "decisions")
    assert [path.name for path in folder.glob("*.json")] == ["0001.json"]
    # The folder's own spelling, which a case-insensitive file system would not check above.
    assert [path.name for path in folder.parents[3].iterdir() if path.is_dir()] == [
        "cc_acquisition"
    ]


def test_set_to_null_switches_a_setting_off(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """A `set` may write null (sampling off, no time budget): stored as `to: null`, replayed."""
    sampling = {"method": "client_sample", "share": 0.2}
    record_decision(
        config_path,
        ENTITY,
        set={"training.sampling": sampling},
        reason="budget",
        env_path=str(env_path),
    )
    entry = record_decision(
        config_path,
        ENTITY,
        set={"training.sampling": None},
        reason="the dev data fits",
        env_path=str(env_path),
    )
    assert entry.to_value is None and entry.from_value == sampling  # as set, not normalised
    stored = json.loads(Path(audit_log_dir(env, cfg, ENTITY), "0002.json").read_text())
    assert "to" in stored and stored["to"] is None
    assert resolve_config(cfg, ENTITY, env, upto=1).training.sampling is not None
    assert resolve_config(cfg, ENTITY, env).training.sampling is None


def test_level_move_refills_the_level_defaults_only(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """A `set` on `automation_level` brings the new level's defaults for the paths the level
    filled; an explicit value in the file stays (D-132)."""
    record_decision(
        config_path,
        ENTITY,
        set={"automation_level": "autonomous"},
        reason="fast",
        env_path=str(env_path),
    )
    resolved = resolve_config(cfg, ENTITY, env)
    assert resolved.training.max_iter == 50
    assert resolved.evaluation.slices.top_pct == [0.01, 0.10]  # explicit in the file
    assert resolved.housekeeping["level_filled"] == cfg.housekeeping["level_filled"]


@pytest.mark.parametrize(
    ("setting", "budgets", "still_filled"),
    [
        ({"training.max_iter": 300}, (300, 10), []),
        ({"eda.key_features.top_n": 15}, (50, 15), ["training.max_iter"]),
    ],
)
def test_level_move_keeps_a_persons_set(
    config_path: Path,
    env_path: Path,
    cfg: UseCaseConfig,
    env: EnvironmentConfig,
    setting: dict,
    budgets: tuple[int, int],
    still_filled: list[str],
) -> None:
    """A level-filled path a person `set` is explicit from then on: a later level move keeps it and
    refills only the paths still filled; a `set` on a plain default (`top_n`) leaves the list
    alone (D-132)."""
    for decision in (setting, {"automation_level": "autonomous"}):
        record_decision(config_path, ENTITY, set=decision, reason="r", env_path=str(env_path))
    resolved = resolve_config(cfg, ENTITY, env)
    assert (resolved.training.max_iter, resolved.eda.key_features.top_n) == budgets
    assert resolved.housekeeping["level_filled"] == still_filled


def test_resolved_housekeeping_records_the_environment(
    cfg: UseCaseConfig, env: EnvironmentConfig, caplog: pytest.LogCaptureFixture
) -> None:
    """Housekeeping carries the environment used and the level-filled paths; a missing log folder
    replays nothing and says so."""
    with caplog.at_level(logging.WARNING, logger="core_modelling.config.audit_log"):
        resolved = resolve_config(cfg, ENTITY, env)
        table = show_decisions(cfg, ENTITY, env)
    assert resolved.housekeeping["environment"] == env.model_dump(mode="json")
    assert resolved.housekeeping["level_filled"] == cfg.housekeeping["level_filled"]
    assert table.empty
    assert [r.getMessage() for r in caplog.records] == [
        f"no audit log at {audit_log_dir(env, cfg, ENTITY)}: 0 entries replayed"
    ] * 2


def test_show_decisions_has_one_row_per_entry(
    worked_example: None, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """Twelve rows with the `what` column filled for every kind of entry: a flag led by its
    finding, a keep followed by the findings it settles, a run by its id or its periods."""
    table = show_decisions(cfg, ENTITY, env)
    assert list(table.columns) == ["seq", "time", "by", "stage", "op", "what", "reason", "evidence"]
    assert table["seq"].tolist() == list(range(1, 13))
    assert (table["what"] != "").all()
    assert table.loc[2, "what"] == f"{LEAK}: {', '.join(LEAKS)}"
    assert table.loc[2, "by"] == "stage feature_checks"
    assert table.loc[4, "what"] == "periods 2025-03 … 2026-02"
    assert table.loc[6, "what"] == f"{', '.join(UNSTABLE)} (settles {UNSTABLE_FINDING})"
    assert table.loc[9, "what"] == "training.max_iter: 200 → 300"
    assert table.loc[7, "what"] == "r1" and table.loc[5, "evidence"] == "#3"


def test_saved_resolved_config_names_its_entries_and_loads_back(
    worked_example: None, cfg: UseCaseConfig, env: EnvironmentConfig, tmp_path: Path
) -> None:
    """The YAML view carries the entry numbers as comments, a held feature its flag entry, and is
    a valid config again."""
    saved = tmp_path / "resolved.yml"
    resolved = resolve_config(cfg, ENTITY, env, save_to=saved)
    text = saved.read_text()
    assert text.startswith("# resolved: cc_acquisition + entries 1–12")
    assert "# training.max_iter: #10" in text and "# features.excluded.nationality: #12" in text
    assert f"# features.held.{QUALITY[1]}: #2" in text and f"features.held.{LEAKS[0]}" not in text
    assert resolved_input_hash(read_resolved_config(saved)) == resolved_input_hash(resolved)
    with pytest.raises(ValueError, match="features.excluded is written by the audit log"):
        load_config(saved)


def test_stale_entry_fails_naming_its_seq(config_path: Path, env: EnvironmentConfig) -> None:
    """An entry on a feature outside the candidates stops the replay at that entry."""
    cfg = load_config(_variant(config_path, {"include": ["*"], "exclude": ["not_a_*"]}))
    _write_json(cfg, env, 1, by=_rule("target_lineage"), stage="target_factory", op="exclude",
                features=["cc_flag"])  # fmt: skip
    _write_json(cfg, env, 2, by={"kind": "person", "id": "someone"}, stage="feature_checks",
                op="exclude", features=["not_a_column"])  # fmt: skip
    with pytest.raises(ValueError, match=r"entry 2 is stale.*'not_a_column'"):
        resolve_config(cfg, ENTITY, env)


@pytest.mark.parametrize("path, value", [("training.seed", 7), ("data.target.column", "age")])
def test_set_entry_outside_the_loggable_settings_is_stale(
    cfg: UseCaseConfig, env: EnvironmentConfig, path: str, value: object
) -> None:
    """A hand-written `set` on a path that is not loggable stops the replay, never applied."""
    _write_json(cfg, env, 1, by={"kind": "person", "id": "someone"}, stage="training", op="set",
                path=path, to=value)  # fmt: skip
    with pytest.raises(ValueError, match=f"entry 1 is stale: {path} is not a loggable setting"):
        resolve_config(cfg, ENTITY, env)


def test_refusals_of_record_decision(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """Each write-time rule refuses with a message naming what to fix."""
    decide = dict(env_path=str(env_path))
    _write_json(cfg, env, 1, by=_rule("target_lineage"), stage="target_factory", op="exclude",
                features=["cc_flag"])  # fmt: skip
    with pytest.raises(ValueError, match="non-empty reason"):
        record_decision(config_path, ENTITY, exclude=["age"], reason=" ", **decide)
    with pytest.raises(ValueError, match="exactly one of"):
        record_decision(config_path, ENTITY, exclude=["age"], include=["age"], reason="r", **decide)
    with pytest.raises(ValueError, match="`findings` goes with `keep` only"):
        record_decision(config_path, ENTITY, exclude=["age"], findings=[LEAK], reason="r", **decide)
    with pytest.raises(ValueError, match="'decision.n' is not a loggable setting"):
        record_decision(config_path, ENTITY, set={"decision.n": 10}, reason="r", **decide)
    with pytest.raises(ValueError, match="set training.max_iter = 0 is rejected"):
        record_decision(config_path, ENTITY, set={"training.max_iter": 0}, reason="r", **decide)
    with pytest.raises(
        ValueError, match="'cc_flag' was excluded by rule 'target_lineage' \\(entry 1\\)"
    ):
        record_decision(config_path, ENTITY, include=["cc_flag"], reason="r", **decide)
    with pytest.raises(ValueError, match="'age' is not excluded"):
        record_decision(config_path, ENTITY, include=["age"], reason="r", **decide)
    assert len(read_entries(audit_log_dir(env, cfg, ENTITY))) == 1  # nothing was written


def test_a_persons_no_op_exclude_never_hides_a_rules(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """Entry 1 is a rule's exclude, entry 2 a person's exclude of the same feature (a no-op):
    `include` is refused naming the rule, both as the log stands and after a revert to 1."""
    decide = dict(env_path=str(env_path))
    _write_json(cfg, env, 1, by=_rule("target_lineage"), stage="target_factory", op="exclude",
                features=["cc_flag"])  # fmt: skip
    record_decision(config_path, ENTITY, exclude=["cc_flag"], reason="again", **decide)
    refused = "'cc_flag' was excluded by rule 'target_lineage' \\(entry 1\\)"
    with pytest.raises(ValueError, match=refused):
        record_decision(config_path, ENTITY, include=["cc_flag"], reason="r", **decide)
    record_decision(config_path, ENTITY, revert_to=1, reason="undo the no-op", **decide)
    with pytest.raises(ValueError, match=refused):
        record_decision(config_path, ENTITY, include=["cc_flag"], reason="r", **decide)
    assert len(read_entries(audit_log_dir(env, cfg, ENTITY))) == 3


def test_include_after_a_revert_undid_the_exclude_is_refused(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """Entry 1 is a person's exclude, entry 2 reverts to 0: the feature is not excluded any more,
    so there is nothing to include."""
    decide = dict(env_path=str(env_path))
    record_decision(config_path, ENTITY, exclude=LEAKS, reason="leak", **decide)
    record_decision(config_path, ENTITY, revert_to=0, reason="start over", **decide)
    with pytest.raises(ValueError, match=f"{LEAKS[0]!r} is not excluded"):
        record_decision(config_path, ENTITY, include=LEAKS[:1], reason="r", **decide)
    assert len(read_entries(audit_log_dir(env, cfg, ENTITY))) == 2


def test_effective_entries_drop_what_a_revert_undid(
    revert_example: None, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """Of entries 1–5, the revert (4) undoes 2 and 3 and is not itself effective: 1 and 5 remain;
    before the revert, entries 1–3 all count."""
    entries = read_entries(audit_log_dir(env, cfg, ENTITY))
    assert [e.seq for e in effective_entries(entries)] == [1, 5]
    assert [e.seq for e in effective_entries(entries[:3])] == [1, 2, 3]


def test_feature_outside_the_candidate_patterns_is_refused(
    config_path: Path, env_path: Path
) -> None:
    """A name matching no include pattern, or an exclude pattern, is not a candidate."""
    variant = _variant(config_path, {"include": ["cc_*", "login_*"], "exclude": ["cc_flag"]})
    with pytest.raises(ValueError, match=r"'nationality' matches no candidate include pattern"):
        record_decision(
            variant, ENTITY, exclude=["nationality"], reason="r", env_path=str(env_path)
        )
    with pytest.raises(ValueError, match=r"'cc_flag' matches candidate exclude pattern"):
        record_decision(variant, ENTITY, keep=["cc_flag"], reason="r", env_path=str(env_path))


def test_write_clash_fails_and_leaves_the_log_alone(
    cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """When `0001.json` appears between the read and the write, the write fails naming the seq."""
    log_dir = audit_log_dir(env, cfg, ENTITY)
    _write_json(cfg, env, 1, by=_rule("target_lineage"), stage="target_factory", op="exclude",
                features=["cc_flag"])  # fmt: skip
    with pytest.raises(RuntimeError, match="entry 1 was written by another writer meanwhile"):
        _write_entry(_entry(cfg, op="exclude", features=["age"]), log_dir)
    assert [e.features for e in read_entries(log_dir)] == [["cc_flag"]]


def test_entry_operands_belong_to_their_op(cfg: UseCaseConfig) -> None:
    """Features go with the feature ops, path / from / to with a `set`, a run's id, replay point
    and input hash with a `run` only; a trail op takes none of them."""
    with pytest.raises(ValidationError, match="op 'set' takes no `features`"):
        _entry(cfg, op="set", path="training.max_iter", to=300, features=["age"])
    with pytest.raises(ValidationError, match="op 'exclude' takes no `to`"):
        _entry(cfg, op="exclude", features=["age"], to=None)
    with pytest.raises(ValidationError, match="op 'run' takes no `features`"):
        _entry(cfg, op="run", features=["age"], periods=["2025-03"])
    with pytest.raises(ValidationError, match="op 'sign_off' takes no `path`"):
        _entry(cfg, op="sign_off", path="training.max_iter")
    with pytest.raises(ValidationError, match="op 'exclude' takes no `run_id`"):
        _entry(cfg, op="exclude", features=["age"], run_id="r1")
    with pytest.raises(ValidationError, match="op 'flag' takes no `replayed_to`"):
        _entry(cfg, op="flag", features=[], finding=LEAK, replayed_to=3)
    with pytest.raises(ValidationError, match="op 'set' needs `path` and `to`"):
        _entry(cfg, op="set", path="training.max_iter")
    assert _entry(cfg, op="set", path="training.sampling", to=None).to_value is None


def test_every_op_has_its_apply_function() -> None:
    """`APPLY_BY_OP` is the closed list of operations, exactly the `Op` literal less `revert`, which
    restarts the replay instead of applying to one state."""
    assert set(APPLY_BY_OP) == set(get_args(Op)) - {"revert"}


def test_hdfs_log_root_is_refused_before_pathlib(cfg: UseCaseConfig) -> None:
    """An hdfs:// data root stops at the transport boundary (T2) until M2.4."""
    hdfs = EnvironmentConfig(schema_version=1, roots=Roots(data="hdfs://name/x"))
    with pytest.raises(NotImplementedError, match="hdfs://name/x.*transport arrives with M2.4"):
        resolve_config(cfg, ENTITY, hdfs)


def test_gaps_newer_schema_and_unknown_ops_fail_loud(
    cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """The log is a closed list of operations numbered 1..n, read by one schema version."""
    log_dir = audit_log_dir(env, cfg, ENTITY)
    _write_json(cfg, env, 1, by=_rule("r"), stage="s", op="exclude", features=["cc_flag"])
    _write_json(cfg, env, 3, by=_rule("r"), stage="s", op="exclude", features=["age"])
    with pytest.raises(ValueError, match=r"without gaps; found \[1, 3\]"):
        read_entries(log_dir)
    path = _write_json(cfg, env, 2, by=_rule("r"), stage="s", op="rename", features=["age"])
    with pytest.raises(ValueError, match=f"{path.name} is not valid"):
        read_entries(log_dir)
    _write_json(cfg, env, 2, by=_rule("r"), stage="s", op="rename", log_schema_version=2)
    with pytest.raises(ValueError, match="log_schema_version 2; this version reads 1; raise"):
        read_entries(log_dir)
    path.write_text('{"seq": 2, "op": ')
    with pytest.raises(ValueError, match=f"{path.name} is not valid JSON"):
        read_entries(log_dir)


def _model_in(annotation: object) -> type[BaseModel] | None:
    """The Pydantic model an annotation names, `X | None` unwrapped; None for a plain value."""
    for candidate in (annotation, *get_args(annotation)):
        if isinstance(candidate, type) and issubclass(candidate, BaseModel):
            return candidate
    return None


def _field_at(path: str) -> bool:
    """Whether a dotted path names a field of `UseCaseConfig`, walking the nested models."""
    model: type[BaseModel] | None = UseCaseConfig
    *parents, leaf = path.split(".")
    for key in parents:
        model = _model_in(model.model_fields[key].annotation)
        if model is None:
            return False
    return leaf in model.model_fields


def _leaves(model: type[BaseModel], prefix: str) -> list[str]:
    """Every non-model field under `model` as a dotted path, nested models walked."""
    paths = []
    for name, field in model.model_fields.items():
        nested = _model_in(field.annotation)
        paths += _leaves(nested, f"{prefix}.{name}") if nested else [f"{prefix}.{name}"]
    return paths


def test_loggable_settings_exist_and_never_touch_the_data_definition_or_decision() -> None:
    """Every listed path is a schema field; none is the data definition, declared before results,
    the training seed, or a setting that acts after registration."""
    assert all(_field_at(path) for path in LOGGABLE_SETTINGS), LOGGABLE_SETTINGS
    assert not [p for p in LOGGABLE_SETTINGS if p.startswith(NEVER_LOGGABLE)]
    assert set(LOGGABLE_SETTINGS.values()) <= {"eda", "feature_checks", "training", "evaluation"}


def test_every_feature_checks_threshold_is_loggable() -> None:
    """Each of the 20 threshold leaves of the five steps, nested ones included, is listed at stage
    `feature_checks`, so a new parameter can't be added without deciding it (D-125)."""
    leaves = _leaves(FeatureChecks, "feature_checks")
    assert len(leaves) == 20
    assert {path: LOGGABLE_SETTINGS.get(path) for path in leaves} == dict.fromkeys(
        leaves, "feature_checks"
    )


def test_decide_command_writes_an_entry(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """`python -m core_modelling decide` records a `set` with its value read as YAML."""
    command = [
        sys.executable,
        "-m",
        "core_modelling",
        "decide",
        str(config_path),
        "--entity",
        ENTITY,
        "--reason",
        "AUC still rising",
        "--set",
        "training.max_iter=300",
        "--evidence",
        "model results report",
        "--env",
        str(env_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    log_dir = audit_log_dir(env, cfg, ENTITY)
    assert result.stdout.splitlines() == [
        f"starting a new audit log at {log_dir}",
        "entry 1: set by " + read_entries(log_dir)[0].by.id,
    ]
    assert resolve_config(cfg, ENTITY, env).training.max_iter == 300


def test_decide_command_reverts(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """`decide --revert-to 0` after a `set` records the revert; the config is as written again."""
    record_decision(
        config_path, ENTITY, set={"training.max_iter": 300}, reason="A", env_path=str(env_path)
    )
    command = [
        sys.executable,
        "-m",
        "core_modelling",
        "decide",
        str(config_path),
        "--entity",
        ENTITY,
    ]
    command += ["--reason", "start over", "--revert-to", "0", "--env", str(env_path)]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    entries = read_entries(audit_log_dir(env, cfg, ENTITY))
    assert result.stdout.strip() == f"entry 2: revert by {entries[1].by.id}"
    assert entries[1].to_seq == 0 and entries[1].stage == "training"
    assert resolve_config(cfg, ENTITY, env).training.max_iter == 200


def test_keep_findings_default_to_the_flags_open_on_its_features(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """A `keep` without `findings` stores every flag open on its feature (sorted), `[]` when none
    is open; named findings are stored as named, and one not open on a named feature is refused
    (a misspelt finding would settle nothing)."""
    decide = dict(env_path=str(env_path))
    _flag(cfg, env, LEAK, ["age", "income"])
    _flag(cfg, env, "quality.near_constant", ["age"])
    kept = record_decision(config_path, ENTITY, keep=["age"], reason="r", **decide)
    assert kept.findings == ["leakage.too_strong", "quality.near_constant"]
    stored = json.loads(Path(audit_log_dir(env, cfg, ENTITY), "0003.json").read_text())
    assert stored["findings"] == kept.findings
    with pytest.raises(ValueError, match=r"\['income: leakage.too_strng'\] are not open"):
        record_decision(config_path, ENTITY, keep=["income"], findings=["leakage.too_strng"],
                        reason="r", **decide)  # fmt: skip
    named = record_decision(config_path, ENTITY, keep=["income"], findings=[LEAK], reason="r",
                            **decide)  # fmt: skip
    assert named.findings == [LEAK] and _held(cfg, env) == []
    unflagged = record_decision(config_path, ENTITY, keep=["tenure_months"], reason="r", **decide)
    assert unflagged.findings == []
    assert resolve_config(cfg, ENTITY, env).features.kept == ["age", "income", "tenure_months"]


def test_a_flag_entry_holds_its_features_and_an_empty_one_releases_them(
    cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """A flag's features enter `features.held` and move the resolved-input hash; the finding's
    next entry with no features closes it, and the input is the config's again."""
    unflagged = resolved_input_hash(resolve_config(cfg, ENTITY, env))
    _flag(cfg, env, LEAK, ["income", "age"])
    assert _held(cfg, env) == ["age", "income"]
    assert resolved_input_hash(resolve_config(cfg, ENTITY, env)) != unflagged
    _flag(cfg, env, LEAK, [])
    assert _held(cfg, env) == []
    assert resolved_input_hash(resolve_config(cfg, ENTITY, env)) == unflagged
    assert (
        show_decisions(cfg, ENTITY, env)["what"].tolist()[1] == f"{LEAK}: none (closes the finding)"
    )


def test_keep_settles_only_its_findings(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """The same finding with new values leaves a kept feature settled; a different finding opens
    it again; a revert that undoes the keep holds it again."""
    decide = dict(env_path=str(env_path))
    _flag(cfg, env, LEAK, ["age"])
    record_decision(config_path, ENTITY, keep=["age"], reason="known at scoring", **decide)
    _flag(cfg, env, LEAK, ["age", "income"])
    entries = read_entries(audit_log_dir(env, cfg, ENTITY))
    assert open_flags(entries) == {"income": [LEAK]}
    _flag(cfg, env, "time_alignment.client_constant", ["age"])
    entries = read_entries(audit_log_dir(env, cfg, ENTITY))
    assert open_flags(entries) == {"age": ["time_alignment.client_constant"], "income": [LEAK]}
    record_decision(config_path, ENTITY, revert_to=1, reason="undo the keep", **decide)
    assert _held(cfg, env) == ["age"]


def test_an_excluded_feature_is_excluded_not_held(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """An `exclude` in force takes a flagged feature out of the held set; an `include` brings the
    still-open flag back."""
    decide = dict(env_path=str(env_path))
    _flag(cfg, env, LEAK, ["age", "income"])
    record_decision(config_path, ENTITY, exclude=["age"], reason="set after the offer", **decide)
    resolved = resolve_config(cfg, ENTITY, env)
    assert (resolved.features.excluded, resolved.features.held) == (["age"], ["income"])
    record_decision(config_path, ENTITY, include=["age"], reason="known after all", **decide)
    assert _held(cfg, env) == ["age", "income"]


def test_config_file_carrying_held_is_refused(config_path: Path) -> None:
    """`features.held` is written by the replay only (D-134)."""
    raw = yaml.safe_load(config_path.read_text())
    raw["features"]["held"] = ["age"]
    config_path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="features.held is written by the audit log's replay"):
        load_config(config_path)


def test_validation_period_a_run_compared_is_refused(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """A `set` moving the validation period to one a Feature Checks run compared is refused naming
    the run entry, also after a revert undid the run; a period no run compared is accepted."""
    decide = dict(env_path=str(env_path))
    record_stage_entry(cfg, ENTITY, env, stage="feature_checks", op="run", periods=COMPARED,
                       reason="Feature Checks run")  # fmt: skip
    record_decision(config_path, ENTITY, revert_to=0, reason="start over", **decide)
    refused = "2026-02 was compared by the run of entry 1"
    with pytest.raises(ValueError, match=refused):
        record_decision(config_path, ENTITY, set={"time.validation_period": "2026-02-28"},
                        reason="later", **decide)  # fmt: skip
    entry = record_decision(config_path, ENTITY, set={"time.validation_period": "2025-12-01"},
                            reason="one more month", **decide)  # fmt: skip
    assert entry.stage == "evaluation"
    assert str(resolve_config(cfg, ENTITY, env).time.validation_period) == "2025-12-31"


def test_validation_period_set_to_null_is_refused(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """An EDA-only config is written in the file: a `set` of the validation period to null is
    refused, and nothing is written to the log."""
    refused = "write null in the config file instead: a frozen training config does not become"
    with pytest.raises(ValueError, match=refused):
        record_decision(config_path, ENTITY, set={"time.validation_period": None},
                        reason="EDA only", env_path=str(env_path))  # fmt: skip
    assert read_entries(audit_log_dir(env, cfg, ENTITY)) == []


def test_stage_writer_records_the_stage_and_refuses_missing_operands(
    cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """`by` is the stage itself; a flag needs its finding, a run its periods, and a stage writes
    no other op."""
    entry = _flag(cfg, env, LEAK, ["age"])
    assert (entry.by.kind, entry.by.id, entry.stage) == (
        "stage",
        "feature_checks",
        "feature_checks",
    )
    write = dict(stage="feature_checks", reason="r")
    with pytest.raises(ValidationError, match="op 'flag' needs `finding` and `features`"):
        record_stage_entry(cfg, ENTITY, env, op="flag", features=["age"], **write)
    with pytest.raises(ValueError, match="a `run` entry needs `periods`"):
        record_stage_entry(cfg, ENTITY, env, op="run", **write)
    with pytest.raises(ValueError, match="a stage writes `flag` or `run` entries, not 'exclude'"):
        record_stage_entry(cfg, ENTITY, env, op="exclude", features=["age"], **write)
    assert len(read_entries(audit_log_dir(env, cfg, ENTITY))) == 1


def test_new_operands_belong_to_their_op(cfg: UseCaseConfig) -> None:
    """`finding` only on a flag, `findings` only on a keep (needed there), `periods` only on a
    run; a finding is written `<step>.<finding>`."""
    with pytest.raises(ValidationError, match="op 'exclude' takes no `finding`"):
        _entry(cfg, op="exclude", features=["age"], finding=LEAK)
    with pytest.raises(ValidationError, match="op 'exclude' takes no `findings`"):
        _entry(cfg, op="exclude", features=["age"], findings=[LEAK])
    with pytest.raises(ValidationError, match="op 'set' takes no `periods`"):
        _entry(cfg, op="set", path="training.max_iter", to=300, periods=["2025-03"])
    with pytest.raises(ValidationError, match="op 'keep' needs `findings`"):
        _entry(cfg, op="keep", features=["age"])
    with pytest.raises(ValidationError, match="String should match pattern"):
        _entry(cfg, op="flag", features=[], finding="too strong")
    with pytest.raises(ValidationError, match="op 'exclude' needs a non-empty `features`"):
        _entry(cfg, op="exclude", features=[])


def test_set_under_a_step_the_config_does_not_run_is_refused(
    config_path: Path, env_path: Path
) -> None:
    """A present `feature_checks` mapping without `leakage` runs no leakage step, so its
    threshold can't be set (D-137); a listed step's can."""
    raw = yaml.safe_load(config_path.read_text())
    raw["feature_checks"] = {"quality": {}}
    config_path.write_text(yaml.safe_dump(raw))
    decide = dict(env_path=str(env_path), reason="r")
    with pytest.raises(ValueError, match="feature_checks.leakage is not in this config"):
        record_decision(config_path, ENTITY, set={"feature_checks.leakage.concordance_max": 0.9},
                        **decide)  # fmt: skip
    path = "feature_checks.quality.nulls_may_be_zeros.missing_min"
    assert record_decision(config_path, ENTITY, set={path: 0.3}, **decide).from_value == 0.2


def test_decide_keep_with_findings_round_trip(
    config_path: Path,
    env_path: Path,
    cfg: UseCaseConfig,
    env: EnvironmentConfig,
    capsys: pytest.CaptureFixture,
) -> None:
    """`decide --keep … --findings …` settles the named finding only; `--findings` without
    `--keep` is refused by `record_decision`."""
    _flag(cfg, env, LEAK, LEAKS)
    _flag(cfg, env, "quality.near_constant", LEAKS[:1])
    command = ["decide", str(config_path), "--entity", ENTITY, "--env", str(env_path)]
    main([*command, "--reason", "known at scoring", "--keep", *LEAKS, "--findings", LEAK])
    entry = read_entries(audit_log_dir(env, cfg, ENTITY))[-1]
    assert capsys.readouterr().out.strip().endswith(f"entry 3: keep by {entry.by.id}")
    assert entry.findings == [LEAK] and _held(cfg, env) == LEAKS[:1]
    with pytest.raises(ValueError, match="`findings` goes with `keep` only"):
        main([*command, "--reason", "r", "--findings", LEAK])


def test_keep_settles_only_pairs_open_on_every_feature(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """Two features with different open flags: one default keep of both is refused, split keeps
    are accepted, and a finding raised later on the second feature holds it. A named finding not
    open on every feature, and `findings=[]` while flags are open, are refused."""
    decide = dict(env_path=str(env_path), reason="r")
    _flag(cfg, env, LEAK, ["age"])
    _flag(cfg, env, UNSTABLE_FINDING, ["income"])
    with pytest.raises(ValueError, match="the features' open flags differ.*split the keep"):
        record_decision(config_path, ENTITY, keep=["age", "income"], **decide)
    with pytest.raises(ValueError, match=r"\['income: leakage.too_strong'\] are not open"):
        record_decision(config_path, ENTITY, keep=["age", "income"], findings=[LEAK], **decide)
    with pytest.raises(ValueError, match=r"findings=\[\] settles nothing.*\{'age': \["):
        record_decision(config_path, ENTITY, keep=["age"], findings=[], **decide)
    assert record_decision(config_path, ENTITY, keep=["age"], **decide).findings == [LEAK]
    split = record_decision(config_path, ENTITY, keep=["income"], **decide)
    assert split.findings == [UNSTABLE_FINDING] and _held(cfg, env) == []
    unflagged = record_decision(config_path, ENTITY, keep=["tenure_months"], findings=[], **decide)
    assert unflagged.findings == []
    _flag(cfg, env, LEAK, ["age", "income"])
    assert _held(cfg, env) == ["income"]


def test_revert_is_checked_like_a_set(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """A revert bringing back a validation period a run compared is refused at write; the same
    revert written by hand stops `resolve_config` as stale, naming the run entry, while the
    state before it still resolves."""
    decide = dict(env_path=str(env_path))
    record_decision(config_path, ENTITY, set={"time.validation_period": "2025-12-31"},
                    reason="one more month", **decide)  # fmt: skip
    record_stage_entry(cfg, ENTITY, env, stage="feature_checks", op="run",
                       periods=[*COMPARED, "2025-11"], reason="Feature Checks run")  # fmt: skip
    compared = "the validation period 2025-11 was compared by the run of entry 2"
    with pytest.raises(ValueError, match=f"revert_to=0 refused: {compared}"):
        record_decision(config_path, ENTITY, revert_to=0, reason="start over", **decide)
    _write_json(cfg, env, 3, by={"kind": "person", "id": "someone"}, stage="training",
                op="revert", to_seq=0, reason="by hand")  # fmt: skip
    with pytest.raises(ValueError, match=f"the replayed config is stale: {compared}"):
        resolve_config(cfg, ENTITY, env)
    assert str(resolve_config(cfg, ENTITY, env, upto=2).time.validation_period) == "2025-12-31"


def test_revert_may_not_null_the_validation_period(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """In an EDA-only config a revert is accepted while the validation period stays null; once a
    `set` gave it one, a revert to a null state is refused."""
    raw = yaml.safe_load(config_path.read_text())
    raw["time"]["validation_period"] = None
    config_path.write_text(yaml.safe_dump(raw))
    decide = dict(env_path=str(env_path))
    record_decision(config_path, ENTITY, exclude=["age"], reason="r", **decide)
    record_decision(config_path, ENTITY, revert_to=0, reason="undo", **decide)
    record_decision(config_path, ENTITY, set={"time.validation_period": "2025-11-30"},
                    reason="ready to train", **decide)  # fmt: skip
    with pytest.raises(ValueError, match="revert_to=2 refused: it moves time.validation_period"):
        record_decision(config_path, ENTITY, revert_to=2, reason="r", **decide)
    assert len(read_entries(audit_log_dir(env, cfg, ENTITY))) == 3


def test_run_periods_are_labels_of_the_configs_period(
    cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """A run's `periods` is a non-empty list of labels as the framework writes them: a day on a
    monthly config is refused naming the label and an example."""
    write = dict(stage="feature_checks", op="run", reason="r")
    refused = r"periods \['2026-01-31'\] are not month labels.*e.g. '2025-08'"
    with pytest.raises(ValueError, match=refused):
        record_stage_entry(cfg, ENTITY, env, periods=["2025-03", "2026-01-31"], **write)
    with pytest.raises(ValueError, match="a `run` entry needs `periods`, a non-empty list"):
        record_stage_entry(cfg, ENTITY, env, periods=[], **write)
    assert read_entries(audit_log_dir(env, cfg, ENTITY)) == []


def test_a_writer_starting_a_new_log_says_where(
    config_path: Path,
    env_path: Path,
    cfg: UseCaseConfig,
    env: EnvironmentConfig,
    capsys: pytest.CaptureFixture,
) -> None:
    """Entry 1 prints the log's folder, so a wrong root or a log left at an old path shows
    itself; a later entry does not."""
    _flag(cfg, env, LEAK, ["age"])
    folder = audit_log_dir(env, cfg, ENTITY)
    assert capsys.readouterr().out == f"starting a new audit log at {folder}\n"
    record_decision(config_path, ENTITY, keep=["age"], reason="r", env_path=str(env_path))
    assert "starting a new audit log" not in capsys.readouterr().out


def test_stale_set_under_a_step_the_config_does_not_run(
    config_path: Path, env: EnvironmentConfig
) -> None:
    """A hand-written `set` under a `feature_checks` step the config leaves out stops the replay
    naming the entry (`check_settable`)."""
    raw = yaml.safe_load(config_path.read_text())
    raw["feature_checks"] = {"quality": {}}
    config_path.write_text(yaml.safe_dump(raw))
    cfg = load_config(config_path)
    _write_json(cfg, env, 1, by={"kind": "person", "id": "someone"}, stage="feature_checks",
                op="set", path="feature_checks.leakage.concordance_max", to=0.9)  # fmt: skip
    stale = "entry 1 is stale: feature_checks.leakage is not in this config"
    with pytest.raises(ValueError, match=stale):
        resolve_config(cfg, ENTITY, env)
