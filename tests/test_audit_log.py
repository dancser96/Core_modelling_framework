"""The decision audit log: the worked example of `docs/components/config.md` replayed, every
refusal of `record_decision`, the storage rules and the `decide` command."""

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

from core_modelling.config import UseCaseConfig, load_config
from core_modelling.config.audit_log import (
    LOG_SCHEMA_VERSION,
    LOGGABLE_SETTINGS,
    Entry,
    _log_dir,
    _write_entry,
    read_entries,
    read_resolved_config,
    record_decision,
    resolve_config,
    show_decisions,
)
from core_modelling.config.identities import HASH_VERSION, data_definition_hash, resolved_input_hash
from core_modelling.config.replay import APPLY_BY_OP, Op
from core_modelling.environment import EnvironmentConfig, Roots

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "conf/base/cc_acquisition.yml"
ENTITY = "entity_a"
LEAKS = ["cc_preapproval_score_trap_leak", "cc_campaign_response_score_trap_leak"]
QUALITY = ["legacy_risk_grade_trap_all_null", "paper_statement_flag_trap_near_constant"]
UNSTABLE = [
    "login_digital_mobile_cnt",
    "login_digital_mobile_cnt_0_2_months_avg",
    "login_digital_mobile_cnt_0_5_months_avg",
    "login_digital_mobile_cnt_0_5_months_max",
    "login_digital_mobile_cnt_0_5_months_std",
]
NEVER_LOGGABLE = (
    "data.",
    "time.train_months",
    "time.target_window_months",
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
    sources = {"entity_a": {"cc_acquisition_input": model_input}}
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
    """Write one rule or stage entry file by hand (rules have no writer yet)."""
    log_dir = Path(_log_dir(cfg, ENTITY, env))
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


@pytest.fixture
def worked_example(
    config_path: Path, env_path: Path, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """Entries 1–12 of the worked example: rules and stages by hand, people through the API."""
    decide = dict(env_path=str(env_path))
    _write_json(cfg, env, 1, by=_rule("target_lineage"), stage="target_factory", op="exclude",
                features=["cc_flag"])  # fmt: skip
    _write_json(cfg, env, 2, by=_rule("quality.all_null"), stage="feature_checks", op="exclude",
                features=QUALITY[:1])  # fmt: skip
    _write_json(cfg, env, 3, by=_rule("quality.near_constant"), stage="feature_checks",
                op="exclude", features=QUALITY[1:])  # fmt: skip
    _write_json(cfg, env, 4, by=_rule("leakage.too_strong"), stage="feature_checks", op="flag",
                features=LEAKS)  # fmt: skip
    _write_json(cfg, env, 5, by=_rule("stability.psi"), stage="feature_checks", op="flag",
                features=UNSTABLE)  # fmt: skip
    record_decision(config_path, ENTITY, exclude=LEAKS, evidence=["#4"],
                    reason="Set after the offer, not known at scoring time", **decide)  # fmt: skip
    record_decision(config_path, ENTITY, keep_despite_flag=UNSTABLE, evidence=["#5"],
                    reason="Digital adoption trend; monitoring watches it", **decide)  # fmt: skip
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


def test_replay_states_follow_the_worked_example(
    worked_example: None, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """The excluded and kept lists and `max_iter` after each entry match the replay table."""
    after_3 = resolve_config(cfg, ENTITY, env, upto=3).features
    assert after_3.excluded == ["cc_flag", *QUALITY] and after_3.kept_despite_flags == []
    assert resolve_config(cfg, ENTITY, env, upto=5).features == after_3  # flags change nothing
    assert resolve_config(cfg, ENTITY, env, upto=6).features.excluded == [
        "cc_flag",
        *QUALITY,
        *LEAKS,
    ]
    after_7 = resolve_config(cfg, ENTITY, env, upto=7)
    assert len(after_7.features.excluded) == 5 and after_7.features.kept_despite_flags == UNSTABLE
    assert after_7.training.max_iter == 200  # the assisted level's default
    assert resolve_config(cfg, ENTITY, env, upto=10).training.max_iter == 300
    final = resolve_config(cfg, ENTITY, env)
    assert final.features.excluded[-1] == "nationality" and len(final.features.excluded) == 6
    assert final.housekeeping["replayed_to"] == 12


def test_resolved_input_hash_moves_only_with_input_entries(
    worked_example: None, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """Exclude, keep and set entries change the run's input; flags, runs and drops do not."""
    hashes = [resolved_input_hash(resolve_config(cfg, ENTITY, env, upto=n)) for n in range(13)]
    changed = {n for n in range(1, 13) if hashes[n] != hashes[n - 1]}
    assert changed == {1, 2, 3, 6, 7, 10, 12}


def test_set_entry_records_from_to_and_stage(
    worked_example: None, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """Entry 10 carries the resolved value before, the new value and the setting's stage."""
    entry = read_entries(_log_dir(cfg, ENTITY, env))[9]
    assert (entry.path, entry.from_value, entry.to_value) == ("training.max_iter", 200, 300)
    assert entry.stage == "training" and entry.by.kind == "person" and entry.by.id
    assert entry.hash_version == HASH_VERSION and entry.time.endswith("+00:00")
    assert json.loads(Path(_log_dir(cfg, ENTITY, env), "0010.json").read_text())["to"] == 300


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
    stored = json.loads(Path(_log_dir(cfg, ENTITY, env), "0002.json").read_text())
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
    assert (resolved.training.max_iter, resolved.eda.key_features.top_n) == (50, 10)
    assert resolved.evaluation.slices.top_pct == [0.01, 0.10]  # explicit in the file
    assert resolved.housekeeping["level_filled"] == cfg.housekeeping["level_filled"]


@pytest.mark.parametrize(
    ("setting", "budgets", "still_filled"),
    [
        ({"training.max_iter": 300}, (300, 10), ["eda.key_features.top_n"]),
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
    refills only the paths still filled (D-132)."""
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
        f"no audit log at {_log_dir(cfg, ENTITY, env)}: 0 entries replayed"
    ] * 2


def test_show_decisions_has_one_row_per_entry(
    worked_example: None, cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """Twelve rows with the `what` column filled for every kind of entry."""
    table = show_decisions(cfg, ENTITY, env)
    assert list(table.columns) == ["seq", "time", "by", "stage", "op", "what", "reason", "evidence"]
    assert table["seq"].tolist() == list(range(1, 13))
    assert (table["what"] != "").all()
    assert table.loc[9, "what"] == "training.max_iter: 200 → 300"
    assert table.loc[7, "what"] == "r1" and table.loc[5, "evidence"] == "#4"


def test_saved_resolved_config_names_its_entries_and_loads_back(
    worked_example: None, cfg: UseCaseConfig, env: EnvironmentConfig, tmp_path: Path
) -> None:
    """The YAML view carries the entry numbers as comments and is a valid config again."""
    saved = tmp_path / "resolved.yml"
    resolved = resolve_config(cfg, ENTITY, env, save_to=saved)
    text = saved.read_text()
    assert text.startswith("# resolved: cc_acquisition + entries 1–12")
    assert "# training.max_iter: #10" in text and "# features.excluded.nationality: #12" in text
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
    assert len(read_entries(_log_dir(cfg, ENTITY, env))) == 1  # nothing was written


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
        record_decision(
            variant, ENTITY, keep_despite_flag=["cc_flag"], reason="r", env_path=str(env_path)
        )


def test_write_clash_fails_and_leaves_the_log_alone(
    cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """When `0001.json` appears between the read and the write, the write fails naming the seq."""
    log_dir = _log_dir(cfg, ENTITY, env)
    _write_json(cfg, env, 1, by=_rule("target_lineage"), stage="target_factory", op="exclude",
                features=["cc_flag"])  # fmt: skip
    with pytest.raises(RuntimeError, match="entry 1 was written by another writer meanwhile"):
        _write_entry(_entry(cfg, op="exclude", features=["age"]), log_dir)
    assert [e.features for e in read_entries(log_dir)] == [["cc_flag"]]


def test_entry_operands_belong_to_their_op(cfg: UseCaseConfig) -> None:
    """A `set` carries no features; a feature op carries no path / from / to."""
    with pytest.raises(ValidationError, match="op 'set' takes no `features`"):
        _entry(cfg, op="set", path="training.max_iter", to=300, features=["age"])
    with pytest.raises(ValidationError, match="op 'exclude' takes no path / from / to"):
        _entry(cfg, op="exclude", features=["age"], to=None)
    with pytest.raises(ValidationError, match="op 'set' needs `path` and `to`"):
        _entry(cfg, op="set", path="training.max_iter")
    assert _entry(cfg, op="set", path="training.sampling", to=None).to_value is None


def test_every_op_has_its_apply_function() -> None:
    """`APPLY_BY_OP` is the closed list of operations, exactly the `Op` literal."""
    assert set(APPLY_BY_OP) == set(get_args(Op))


def test_hdfs_log_root_is_refused_before_pathlib(cfg: UseCaseConfig) -> None:
    """An hdfs:// data root stops at the transport boundary (T2) until M2.4."""
    hdfs = EnvironmentConfig(schema_version=1, roots=Roots(data="hdfs://name/x"))
    with pytest.raises(NotImplementedError, match="hdfs://name/x.*transport arrives with M2.4"):
        resolve_config(cfg, ENTITY, hdfs)


def test_gaps_newer_schema_and_unknown_ops_fail_loud(
    cfg: UseCaseConfig, env: EnvironmentConfig
) -> None:
    """The log is a closed list of operations numbered 1..n, read by one schema version."""
    log_dir = _log_dir(cfg, ENTITY, env)
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


def _field_at(path: str) -> bool:
    """Whether a dotted path names a field of `UseCaseConfig`, walking the nested models."""
    model: type[BaseModel] = UseCaseConfig
    *parents, leaf = path.split(".")
    for key in parents:
        annotation = model.model_fields[key].annotation
        if not (isinstance(annotation, type) and issubclass(annotation, BaseModel)):
            return False
        model = annotation
    return leaf in model.model_fields


def test_loggable_settings_exist_and_never_touch_the_data_definition_or_decision() -> None:
    """Every listed path is a schema field; none is the data definition, declared before results,
    the training seed, or a setting that acts after registration."""
    assert all(_field_at(path) for path in LOGGABLE_SETTINGS), LOGGABLE_SETTINGS
    assert not [p for p in LOGGABLE_SETTINGS if p.startswith(NEVER_LOGGABLE)]
    assert set(LOGGABLE_SETTINGS.values()) <= {"eda", "feature_checks", "training", "evaluation"}


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
    assert (
        result.stdout.strip()
        == "entry 1: set by " + read_entries(_log_dir(cfg, ENTITY, env))[0].by.id
    )
    assert resolve_config(cfg, ENTITY, env).training.max_iter == 300
