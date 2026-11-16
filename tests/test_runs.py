"""The runs of a use case without Spark: the run number, the exclusive run folder and `run.json`,
`find_run`'s rule, `list_runs`' states, the sign-off and the CLI's `runs`, `show-run` and
`decide --sign-off`. Run folders are built by hand in a `tmp_path`-rooted environment."""

import json
import shutil
from pathlib import Path

import pytest
import yaml
from conftest import build_entry

from core_modelling import runs
from core_modelling.__main__ import main
from core_modelling.artifacts import write_json
from core_modelling.config import UseCaseConfig, load_config
from core_modelling.config.audit_log import record_stage_entry, resolve_config
from core_modelling.config.identities import HASH_VERSION, feature_signature
from core_modelling.environment import EnvironmentConfig, models_dir
from core_modelling.runs import (
    _canonical_run,
    create_run,
    find_run,
    list_runs,
    next_run_id,
    read_run,
    show_run,
    sign_off,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "tests/conf/cc_acquisition.yml"
ENTITY = "entity_a"
FEATURES = ["age", "income"]
STAGE2 = {"eda": "a1b2c3", "feature_checks": "d4e5f6"}
SOURCES = ["retail_mart", "retail_fs_extract", "retail_holdings", "retail_acquisition_input"]


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """The example config copied next to the test's data root."""
    return Path(shutil.copy(EXAMPLE, tmp_path / "cc_acquisition.yml"))


@pytest.fixture
def env_path(tmp_path: Path) -> Path:
    """An environment file whose data root is the test folder, mapping the config's sources
    (never read: `run.json` records only where they are)."""
    sources = {name: {"format": "parquet", "path": str(tmp_path / name)} for name in SOURCES}
    content = {"schema_version": 1, "roots": {"data": str(tmp_path)},
               "sources": {ENTITY: sources}}  # fmt: skip
    path = tmp_path / "environment.yml"
    path.write_text(yaml.safe_dump(content))
    return path


@pytest.fixture
def env(env_path: Path) -> EnvironmentConfig:
    """The same environment as `env_path`, as a model."""
    return EnvironmentConfig.model_validate(yaml.safe_load(env_path.read_text()))


@pytest.fixture
def cfg(config_path: Path) -> UseCaseConfig:
    """The copied example config, loaded."""
    return load_config(config_path)


@pytest.fixture
def resolved(cfg: UseCaseConfig, env: EnvironmentConfig) -> UseCaseConfig:
    """The example config resolved on the entity (an empty log)."""
    return resolve_config(cfg, ENTITY, env)


def _new_run(env: EnvironmentConfig, resolved: UseCaseConfig) -> str:
    """A new run reserved through `create_run`."""
    return create_run(env, resolved, ENTITY, STAGE2)


def _train(
    env: EnvironmentConfig,
    cfg: UseCaseConfig,
    run: str,
    features: list[str] = FEATURES,
    manifest: dict | None = None,
) -> Path:
    """Mark a run trained by hand: `training/training.json` with a summary, and the bundle's
    `bundle.json` with the final list and its manifest, by default with the list's signature
    and the current hash version."""
    folder = Path(models_dir(env, cfg, run))
    (folder / "training").mkdir(parents=True)
    (folder / "bundle").mkdir()
    summary = {"family": "lgbm", "features": len(features)}
    (folder / "training" / "training.json").write_text(json.dumps({"summary": summary}))
    signed = {"feature_signature": feature_signature(features), "hash_version": HASH_VERSION}
    manifest = signed if manifest is None else manifest
    (folder / "bundle" / "manifest.json").write_text(json.dumps(manifest))
    (folder / "bundle" / "bundle.json").write_text(json.dumps({"features": features}))
    return folder


def _hand_run(env: EnvironmentConfig, cfg: UseCaseConfig, run: str, **changes: object) -> None:
    """A run folder whose `run.json` is r001's with `changes`."""
    record = {**read_run(env, cfg, "r001"), "run_id": run, **changes}
    folder = Path(models_dir(env, cfg, run))
    folder.mkdir()
    (folder / "run.json").write_text(json.dumps(record))


def test_run_numbers_are_normalised() -> None:
    """`r7`, `7`, `R007` and `r007` are one run; `r1000` stays; anything else is refused."""
    assert {_canonical_run(text) for text in ("r7", "7", "R007", "r007", " r7 ")} == {"r007"}
    assert _canonical_run("r1000") == "r1000"
    for text in ("x7", "", "r", "r0", "r7a"):
        with pytest.raises(ValueError, match="is not a run number"):
            _canonical_run(text)


def test_next_number_counts_the_folders_and_the_log(tmp_path: Path) -> None:
    """`r001` on nothing; else one above the highest folder, in any case, or run the entries
    name."""
    assert next_run_id(str(tmp_path / "missing"), []) == "r001"
    (tmp_path / "r002").mkdir()
    (tmp_path / "notes").mkdir()
    named = build_entry(1, "run", stage="training", run_id="r005")
    assert next_run_id(str(tmp_path), []) == "r003"
    assert next_run_id(str(tmp_path), [named]) == "r006"
    (tmp_path / "R009").mkdir()
    assert next_run_id(str(tmp_path), [named]) == "r010"


def test_a_number_taken_between_the_count_and_the_create_moves_on(
    env: EnvironmentConfig, resolved: UseCaseConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another writer creates the counted folder first: the run takes the next number and
    writes nothing into the other's folder; a number that stays taken fails after a few tries."""
    count = runs.next_run_id

    def clash(folder: str, entries: list) -> str:
        """The real count, whose folder another writer then takes, once."""
        run = count(folder, entries)
        monkeypatch.setattr(runs, "next_run_id", count)
        Path(folder, run).mkdir()
        return run

    monkeypatch.setattr(runs, "next_run_id", clash)
    assert _new_run(env, resolved) == "r002"
    assert not any(Path(models_dir(env, resolved, "r001")).iterdir())
    monkeypatch.setattr(runs, "next_run_id", lambda folder, entries: "r001")
    with pytest.raises(RuntimeError, match="5 run numbers in a row were taken"):
        _new_run(env, resolved)


def test_a_deleted_folders_number_is_not_given_again(
    env: EnvironmentConfig, cfg: UseCaseConfig, resolved: UseCaseConfig
) -> None:
    """Training's `run` entry names r001, so after its folder is deleted the next run is r002."""
    assert _new_run(env, resolved) == "r001"
    record_stage_entry(cfg, ENTITY, env, stage="training", op="run", run_id="r001", reason="t")
    shutil.rmtree(models_dir(env, resolved, "r001"))
    assert _new_run(env, resolved) == "r002"


def test_run_json_is_written_once_from_the_resolved_config(
    env: EnvironmentConfig, resolved: UseCaseConfig
) -> None:
    """`run.json` holds the spec's keys, filled from the resolved config, and cannot be written
    twice; a `stage2` without exactly EDA's and Feature Checks' tokens is refused before a
    number is taken."""
    run = _new_run(env, resolved)
    record = read_run(env, resolved, "1")
    assert list(record) == list(runs.RUN_KEYS) and record["run_id"] == run == "r001"
    assert record["stage2"] == STAGE2 and record["entity"] == ENTITY
    assert record["resolved_input_hash"] == resolved.housekeeping["resolved_input_hash"]
    with pytest.raises(FileExistsError):
        write_json(record, Path(models_dir(env, resolved, run, "run.json")), exclusive=True)
    with pytest.raises(ValueError, match=r"stage2 holds \['eda'\]"):
        create_run(env, resolved, ENTITY, {"eda": "a1"})
    with pytest.raises(FileNotFoundError, match="no run r009"):
        read_run(env, resolved, "r9")
    assert sorted(p.name for p in Path(models_dir(env, resolved)).iterdir()) == ["r001"]


def test_incomplete_crashed_and_truncated_runs(
    env: EnvironmentConfig, cfg: UseCaseConfig, resolved: UseCaseConfig
) -> None:
    """No runs give the fixed columns; a run without `training/` lists with its states false; a
    folder without `run.json` is described as a crash; a truncated json fails naming its file."""
    assert list(list_runs(env, cfg, ENTITY).columns) == runs.FIXED_COLUMNS + runs.STATE_COLUMNS
    _new_run(env, resolved)
    (row,) = list_runs(env, cfg, ENTITY).to_dict("records")
    assert row["run"] == "r001" and not (row["trained"] or row["evaluated"] or row["signed_off"])
    assert "not trained (incomplete)" in show_run(env, cfg, ENTITY, "r1")
    Path(models_dir(env, cfg, "r002")).mkdir()
    assert list_runs(env, cfg, ENTITY)["run"].tolist() == ["r002", "r001"]
    with pytest.raises(FileNotFoundError, match="the run crashed before it was written"):
        show_run(env, cfg, ENTITY, "r2")
    with pytest.raises(ValueError, match="r002: no run.json: the run crashed"):
        find_run(env, resolved, ENTITY)
    Path(models_dir(env, cfg, "r002", "run.json")).write_text('{"run_id": "r0')
    with pytest.raises(ValueError, match=r"r002/run.json is not valid JSON"):
        list_runs(env, cfg, ENTITY)
    shutil.rmtree(models_dir(env, cfg, "r002"))
    _train(env, cfg, "r001")
    Path(models_dir(env, cfg, "r001", "training", "training.json")).write_text('{"summ')
    with pytest.raises(ValueError, match=r"training/training.json is not valid JSON"):
        list_runs(env, cfg, ENTITY)


def test_find_run_takes_the_latest_matching_trained_run(
    env: EnvironmentConfig, cfg: UseCaseConfig, resolved: UseCaseConfig
) -> None:
    """r001 matches; r002 has other training settings, r003 is not trained, r004 is of another
    data definition: the latest match is r001, and a named run must be of the data definition
    and trained."""
    with pytest.raises(ValueError, match="latest runs: none. Run Training first"):
        find_run(env, resolved, ENTITY)
    _train(env, cfg, _new_run(env, resolved))
    _hand_run(env, cfg, "r002", training_settings_digest="other")
    _train(env, cfg, "r002")
    _hand_run(env, cfg, "r003")
    _hand_run(env, cfg, "r004", data_definition_hash="e" * 64)
    _train(env, cfg, "r004")
    assert find_run(env, resolved, ENTITY) == "r001"
    assert find_run(env, resolved, ENTITY, run="2") == "r002"
    with pytest.raises(ValueError, match="r004 was trained for data definition eeeeeeeeeeee"):
        find_run(env, resolved, ENTITY, run="r4")
    with pytest.raises(ValueError, match="r003 is incomplete"):
        find_run(env, resolved, ENTITY, run="r3")
    shutil.rmtree(models_dir(env, cfg, "r001"))
    with pytest.raises(ValueError, match="r004: data definition eeeeeeeeeeee") as refusal:
        find_run(env, resolved, ENTITY)
    assert "r003: not trained" in str(refusal.value)
    assert "other training settings" in str(refusal.value)


def test_a_named_run_of_another_split_or_other_sources_is_refused(
    env: EnvironmentConfig, cfg: UseCaseConfig, resolved: UseCaseConfig
) -> None:
    """r002 was trained under another client split and r003 from sources now mapped elsewhere:
    named, each is refused; by default the latest match, r001, is taken, and once it is gone
    the refusal names r003's moved sources."""
    _train(env, cfg, _new_run(env, resolved))
    settings = read_run(env, cfg, "r001")["training_settings"]
    other = {**settings["data.split"], "seed": settings["data.split"]["seed"] + 1}
    _hand_run(
        env,
        cfg,
        "r002",
        training_settings={**settings, "data.split": other},
        training_settings_digest="digest of the other split",
    )
    _train(env, cfg, "r002")
    _hand_run(env, cfg, "r003", sources_digest="moved")
    _train(env, cfg, "r003")
    with pytest.raises(ValueError, match="r002 was trained with the client split"):
        find_run(env, resolved, ENTITY, run="r2")
    with pytest.raises(ValueError, match="r003 was trained from sources the environment now"):
        find_run(env, resolved, ENTITY, run="r3")
    assert find_run(env, resolved, ENTITY) == "r001"
    shutil.rmtree(models_dir(env, cfg, "r001"))
    with pytest.raises(ValueError, match="r003: trained from sources the environment now maps"):
        find_run(env, resolved, ENTITY)


def test_a_sign_off_covers_the_runs_of_its_feature_list(
    env: EnvironmentConfig, cfg: UseCaseConfig, resolved: UseCaseConfig
) -> None:
    """`sign_off` writes the run, the list and its signature; `list_runs` then shows that run and
    a later one with the same list signed off, not one with another list."""
    for features in (FEATURES, FEATURES, ["age"]):
        _train(env, cfg, _new_run(env, resolved), features)
    _new_run(env, resolved)
    with pytest.raises(ValueError, match="r004 is incomplete"):
        sign_off(cfg, ENTITY, env, "r4", "defensible")
    entry = sign_off(cfg, ENTITY, env, "r1", "each defensible")
    assert (entry.op, entry.by.kind, entry.stage) == ("sign_off", "person", "sign_off")
    assert (entry.run_id, entry.features) == ("r001", FEATURES)
    assert entry.signature == feature_signature(FEATURES)
    table = list_runs(env, cfg, ENTITY)
    signed = dict(zip(table["run"], table["signed_off"], strict=True))
    assert signed == {"r004": False, "r003": False, "r002": True, "r001": True}
    assert table.columns[4:6].tolist() == ["family", "features"]
    assert "signed off: yes, entry 1" in show_run(env, cfg, ENTITY, "r2")


def test_a_sign_off_refuses_a_manifest_that_does_not_name_its_list(
    env: EnvironmentConfig, cfg: UseCaseConfig, resolved: UseCaseConfig
) -> None:
    """A manifest whose signature is not the list's is refused; one without a signature too,
    by `sign_off` and by `list_runs`, never shown as not signed off; one of another hash
    version is refused naming the version, not as a changed bundle."""
    _train(
        env,
        cfg,
        _new_run(env, resolved),
        ["zzz"],
        {"feature_signature": "sig1", "hash_version": HASH_VERSION},
    )
    with pytest.raises(ValueError, match="is not the signature of bundle.json's features"):
        sign_off(cfg, ENTITY, env, "r1", "looks fine")
    _train(env, cfg, _new_run(env, resolved), FEATURES, {})
    with pytest.raises(ValueError, match="lacks bundle.json's features or the manifest's"):
        sign_off(cfg, ENTITY, env, "r2", "looks fine")
    with pytest.raises(ValueError, match="lacks bundle.json's features or the manifest's"):
        list_runs(env, cfg, ENTITY)
    later = {"feature_signature": feature_signature(FEATURES), "hash_version": HASH_VERSION + 1}
    _train(env, cfg, _new_run(env, resolved), FEATURES, later)
    with pytest.raises(ValueError, match=f"computed under hash_version {HASH_VERSION + 1}"):
        sign_off(cfg, ENTITY, env, "r3", "looks fine")


def test_summary_keys_both_stages_hold_are_prefixed(
    env: EnvironmentConfig, cfg: UseCaseConfig, resolved: UseCaseConfig
) -> None:
    """A key in both summaries gets its stage's prefix; the others keep their names."""
    folder = _train(env, cfg, _new_run(env, resolved))
    (folder / "evaluation").mkdir()
    summary = {"features": 2, "roc_auc": 0.81}
    (folder / "evaluation" / "evaluation.json").write_text(json.dumps({"summary": summary}))
    (row,) = list_runs(env, cfg, ENTITY).to_dict("records")
    assert row["training_features"] == row["evaluation_features"] == 2
    assert row["family"] == "lgbm" and row["roc_auc"] == 0.81 and row["evaluated"]


def test_cli_lists_shows_and_signs_off(
    config_path: Path,
    env_path: Path,
    env: EnvironmentConfig,
    cfg: UseCaseConfig,
    resolved: UseCaseConfig,
    capsys: pytest.CaptureFixture,
) -> None:
    """`runs`, `show-run` and `decide --sign-off` print what the functions return, the sign-off
    its list first; a sign-off without `--run`, or with a decision's operand, is refused."""
    common = [str(config_path), "--entity", ENTITY, "--env", str(env_path)]
    main(["runs", *common])
    assert capsys.readouterr().out.startswith("no runs at ")
    _train(env, cfg, _new_run(env, resolved))
    main(["runs", *common])
    assert "r001" in capsys.readouterr().out
    main(["decide", *common, "--sign-off", "--run", "r1", "--reason", "each defensible"])
    *_, shown, written = capsys.readouterr().out.splitlines()
    assert shown.startswith("signed off r001: 2 features, signature ")
    assert shown.endswith(": age, income")
    assert written.startswith("entry 1: sign_off of r001 by ")
    main(["show-run", *common, "--run", "1"])
    assert "signed off: yes, entry 1" in capsys.readouterr().out
    for extra in ([], ["--run", "r1", "--revert-to", "0"], ["--run", "r1", "--evidence", "x"]):
        with pytest.raises(SystemExit):
            main(["decide", *common, "--sign-off", "--reason", "r", *extra])
    with pytest.raises(SystemExit):
        main(["decide", *common, "--run", "r1", "--reason", "r", "--keep", "age"])
