"""The Training stage end to end on the unit preset (D-139, D-140): the card config and the
regression variant, each trained once per session in `conftest.py` (`lgbm`, four trials) after
EDA and Feature Checks. What a run must leave and keep: every artifact of the run folder, a model
that is the one the search judged, the train split and nothing else, the feature set in force
without a held feature, the `run` entry without periods, one `model_hash` for a repeated run, an
incomplete run after a crash, and the `autonomous` rule of `run` (`CLAUDE.md` §4.4, §4.10, §4.13).
The four families through the search are the slow test on the `dev` preset.
"""

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
import yaml
from conftest import ENTITY, QUICK_SEARCH, write_environment_file
from pyspark.sql import SparkSession

import core_modelling.training.run as training_run
from core_modelling.artifacts import STAGE_SCHEMA_VERSIONS, StageResult, read_stage
from core_modelling.config import UseCaseConfig, load_config
from core_modelling.config.audit_log import read_entries
from core_modelling.dataset import Frames
from core_modelling.environment import (
    EnvironmentConfig,
    audit_log_dir,
    feature_dir,
    load_environment,
    models_dir,
)
from core_modelling.ledger import LEDGER_SCHEMA_VERSION, read_ledger
from core_modelling.model.bundle import load_bundle
from core_modelling.run import run
from core_modelling.runs import list_runs, show_run
from core_modelling.statistics.losses import mean_fold_loss
from core_modelling.training import run_training
from core_modelling.training.gate import (
    STAGE2_FILE,
    STAGE2_TABLES,
    Stage2,
    read_stage2_copy,
    save_stage2,
)
from core_modelling.training.ledger_run import read_run_ledger

ROOT = Path(__file__).resolve().parents[1]
TABLES = {"trials", "selection", "oof", "explanation_sample", "calibration", "signoff"}
META_KEYS = {"run_id", "stage2", "summary", "best", "search", "search_space", "metrics",
             "final_features", "sampling", "folds", "reproducible_to", "warnings",
             "timings"}  # fmt: skip
VIEWS = {"opening", "warnings", "search", "selection", "calibration", "signoff", "explanation"}
A_FEW_CANDIDATES = ["age", "income", "segment", "onboarding_channel", "tenure_months"]


@pytest.fixture(params=["trained_card", "trained_regression"])
def trained(request: pytest.FixtureRequest) -> StageResult:
    """Each config's trained run in turn."""
    return request.getfixturevalue(request.param)


@pytest.fixture(scope="module")
def env(
    trained_env: EnvironmentConfig,
    trained_card: StageResult,
    trained_regression: StageResult,
    tmp_path_factory: pytest.TempPathFactory,
) -> EnvironmentConfig:
    """The trained runs' environment on a copy of their data root, this module's own: a test
    that trains again writes there."""
    root = tmp_path_factory.mktemp("training_data")
    shutil.copytree(trained_env.roots.data, root, dirs_exist_ok=True)
    roots = trained_env.roots.model_copy(update={"data": str(root)})
    return trained_env.model_copy(update={"roots": roots})


def test_the_run_folder_holds_every_artifact(
    trained: StageResult, trained_env: EnvironmentConfig
) -> None:
    """The run folder holds `run.json`, the bundle, the per-run ledger, the `stage2/` copies of
    the final features and `training/` with its json, tables and FLAML's log, and each reads
    back; the listing shows the run as trained."""
    cfg, run_id = trained.config, trained.meta["run_id"]
    folder = Path(models_dir(trained_env, cfg, run_id))
    final = trained.meta["final_features"]
    assert (folder / "run.json").is_file()
    assert load_bundle(str(folder / "bundle")).features == final
    saved = read_run_ledger(str(folder))
    assert list(saved.columns) == list(trained.ledger.columns)
    assert saved["feature"].tolist() == trained.ledger["feature"].tolist()
    for name in STAGE2_TABLES:
        assert set(pd.read_parquet(folder / "stage2" / f"{name}.parquet")["feature"]) <= set(final)
    candidates = pd.read_parquet(folder / "stage2" / "ledger.parquet")["feature"]
    assert set(trained.ledger["feature"]) < set(candidates)
    meta, tables = read_stage(str(folder / "training"), "training")
    assert META_KEYS <= set(meta) and set(tables) == TABLES and set(trained.views) == VIEWS
    for name in ("log.json", "resolved_config.yml", "flaml_lgbm.log"):
        assert (folder / "training" / name).is_file()
    assert meta["summary"]["family"] == meta["best"]["family"] == "lgbm"
    assert meta["summary"]["trials"] == len(tables["trials"]) == QUICK_SEARCH["max_iter"]
    assert meta["reproducible_to"] == "model" and "n_jobs" not in meta["best"]["parameters"]
    listed = list_runs(trained_env, cfg, ENTITY).set_index("run").loc[run_id]
    assert listed["trained"] and listed["family"] == "lgbm" and not listed["signed_off"]
    assert meta["summary"]["model_hash"] in show_run(trained_env, cfg, ENTITY, run_id)


def test_the_run_keeps_its_stage2_versions_and_the_report_blocks(
    trained: StageResult, trained_env: EnvironmentConfig
) -> None:
    """`stage2/_stage2.json` records the versions of the copies and the two runs' tokens, and
    `read_stage2_copy` reads every copy back; the metrics carry their optimism note; the views
    hold the search's best and the calibration's train-side metrics."""
    folder = Path(models_dir(trained_env, trained.config, trained.meta["run_id"]))
    versions = json.loads((folder / "stage2" / STAGE2_FILE).read_text())
    assert versions == {
        "eda_schema_version": STAGE_SCHEMA_VERSIONS["eda"],
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
        "runs": trained.meta["stage2"],
    }
    assert set(read_stage2_copy(str(folder))) == {"ledger", *STAGE2_TABLES}
    note = trained.meta["metrics"]["note"]
    assert isinstance(note, str) and note
    assert "best" in trained.views["search"]
    assert "metrics" in trained.views["calibration"]


def test_the_stage2_copy_reads_back_and_refuses_a_version_it_cannot_read(
    tmp_path: Path,
) -> None:
    """No Spark: a copy `save_stage2` wrote reads back table by table (the final features'
    rows, every candidate's ledger row); a missing `_stage2.json` and an EDA or ledger version
    other than this framework's are refused, the message naming both versions."""
    tables = {name: pd.DataFrame({"feature": ["age", "income"], "n": [1, 2]})
              for name in STAGE2_TABLES}  # fmt: skip
    ledger = pd.DataFrame({"feature": ["age", "income", "segment"]})
    stage2 = Stage2({"schema_version": STAGE_SCHEMA_VERSIONS["eda"]}, tables, {}, ledger,
                    {"eda": "aa", "feature_checks": "bb"})  # fmt: skip
    run_folder = tmp_path / "r001"
    run_folder.mkdir()
    save_stage2(str(run_folder / "stage2"), stage2, final=["income"])
    copy = read_stage2_copy(str(run_folder))
    pd.testing.assert_frame_equal(copy["ledger"], ledger)
    assert all(copy[name]["feature"].tolist() == ["income"] for name in STAGE2_TABLES)
    versions_file = run_folder / "stage2" / STAGE2_FILE
    versions = json.loads(versions_file.read_text())
    for key, older in (("eda_schema_version", 4), ("ledger_schema_version", 2)):
        versions_file.write_text(json.dumps({**versions, key: older}))
        current = versions[key]
        with pytest.raises(ValueError, match=rf"has {key} {older}, this framework reads {current}"):
            read_stage2_copy(str(run_folder))
    versions_file.unlink()
    with pytest.raises(FileNotFoundError, match=rf"holds no {STAGE2_FILE}"):
        read_stage2_copy(str(run_folder))


def test_the_kept_model_is_the_one_the_search_judged(trained: StageResult) -> None:
    """FLAML only searches: the fold models the framework fitted at the best configuration give,
    on the uncalibrated score and the same folds, the loss FLAML reported for its best trial."""
    oof, trials = trained.tables["oof"], trained.tables["trials"]
    metric = trained.config.decision.metric
    own = mean_fold_loss(metric, oof["target"], oof["score_raw"], oof["cv_fold"])
    assert own == pytest.approx(trials["fold_loss"].min(), abs=1e-9)
    assert json.loads(trials.loc[trials["fold_loss"].idxmin(), "configuration"]).items() <= (
        trained.meta["best"]["parameters"].items()
    )


def test_training_sees_the_feature_set_in_force_and_no_held_feature(
    trained_card: StageResult, trained_env: EnvironmentConfig
) -> None:
    """A flag holds a feature out of training until a person decides (§4.6): the features that
    entered selection are the ledger's candidates without the held ones, and the opening names
    them; the final features are among those that entered."""
    cfg = trained_card.config
    opening = next(entry for entry in trained_card.log if entry.get("step") == "feature_set")
    definition = cfg.housekeeping["data_definition_hash"]
    stage2 = read_ledger(
        feature_dir(trained_env, cfg, ENTITY), definition, trained_card.meta["stage2"]
    )
    held = set(opening["held"])
    entered = set(trained_card.ledger["feature"])
    assert opening["step"] == "feature_set" and held and len(entered) == opening["features"]
    assert not held & entered and entered < set(stage2["feature"])
    assert set(trained_card.meta["final_features"]) <= entered


def test_the_run_entry_names_the_run_and_no_periods(
    trained: StageResult, trained_env: EnvironmentConfig
) -> None:
    """A Training run never blocks moving the validation period (D-088): its `run` entry holds
    the run number and no periods."""
    entries = read_entries(audit_log_dir(trained_env, trained.config, ENTITY))
    runs = [entry for entry in entries if entry.stage == "training"]
    assert [(entry.op, entry.run_id) for entry in runs] == [("run", trained.meta["run_id"])]
    assert runs[0].periods is None


def test_a_second_run_repeats_the_model_and_reads_train_only(
    spark: SparkSession,
    env: EnvironmentConfig,
    card_quick: UseCaseConfig,
    trained_card: StageResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rerun under the same config, data and seed gives the same model and recipe hashes
    under the next run number (§4.10), and the one set of frames Training asks for is the train
    split alone: no test or validation row reaches it (§4.4)."""
    asked: list[tuple[str, Frames]] = []
    build_frames = training_run.build_frames

    def recording(*arguments: object, **keywords: object) -> Frames:
        """`build_frames`, recording the stage asked for and the frames returned."""
        frames = build_frames(*arguments, **keywords)
        asked.append((arguments[4], frames))
        return frames

    monkeypatch.setattr(training_run, "build_frames", recording)
    again = run_training(card_quick, ENTITY, env, spark)
    first, second = trained_card.meta["summary"], again.meta["summary"]
    assert again.meta["run_id"] != trained_card.meta["run_id"]
    for key in ("model_hash", "recipe_hash", "feature_signature", "oof_log_loss"):
        assert second[key] == first[key]
    assert again.tables["trials"]["configuration"].equals(
        trained_card.tables["trials"]["configuration"]
    )
    ((stage, frames),) = asked
    assert stage == "training" and frames.snapshot is None and frames.rows is None
    assert set(frames.train["split"]) == {"train"}
    assert len(frames.train) == len(again.tables["oof"])


def test_a_crash_after_the_number_is_reserved_leaves_an_incomplete_run(
    spark: SparkSession,
    env: EnvironmentConfig,
    card_quick: UseCaseConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run that fails after `create_run` keeps its folder and number, is listed as not
    trained and writes no `run` entry: `training/` is the commit marker (D-136)."""
    before = read_entries(audit_log_dir(env, card_quick, ENTITY))

    def failing(*arguments: object) -> None:
        """A step that crashes."""
        raise RuntimeError("the machine went away")

    monkeypatch.setattr(training_run, "encode_and_select", failing)
    with pytest.raises(RuntimeError, match="the machine went away"):
        run_training(card_quick, ENTITY, env, spark)
    newest = list_runs(env, card_quick, ENTITY).iloc[0]
    folder = Path(models_dir(env, card_quick, newest["run"]))
    assert not newest["trained"] and (folder / "run.json").is_file()
    assert not (folder / "training").exists()
    assert read_entries(audit_log_dir(env, card_quick, ENTITY)) == before


def _config_file(folder: Path, level: str) -> Path:
    """The card config as a file at an automation level, built in memory from a few candidates
    with `QUICK_SEARCH` and no selection rule (five features need none)."""
    raw = yaml.safe_load((ROOT / "tests/conf/cc_acquisition.yml").read_text())
    raw["automation_level"] = level
    raw["data"]["model_input"] = None
    raw["features"]["candidates"]["include"] = A_FEW_CANDIDATES
    unselected = {"cluster": False, "floor_z": None, "prune": False}
    raw["training"].update({**QUICK_SEARCH, "selection": unselected})
    path = folder / f"{level}.yml"
    path.write_text(yaml.safe_dump(raw))
    return path


def test_run_adds_the_missing_stages_at_autonomous_and_training_alone_refuses(
    spark: SparkSession, tmp_path: Path, unit_output: tuple[str, dict]
) -> None:
    """No model without data knowledge (§4.13, D-132): on a root where neither stage has run,
    `run_training` refuses at both levels naming `run`, `run --stages training` refuses at
    `assisted`, and at `autonomous` it runs EDA, then Feature Checks, then Training."""
    env_file = str(write_environment_file(unit_output[0], tmp_path))
    env = load_environment(env_file)
    for level in ("assisted", "autonomous"):
        with pytest.raises(FileNotFoundError, match="needs the artifacts of eda and feature_ch"):
            run_training(load_config(_config_file(tmp_path, level)), ENTITY, env, spark)
    with pytest.raises(FileNotFoundError, match="run --stages eda feature_checks training"):
        run(_config_file(tmp_path, "assisted"), env_path=env_file, stages=["training"])
    out = run(_config_file(tmp_path, "autonomous"), env_path=env_file, stages=["training"])
    paths = out[ENTITY]["training"]["cc_acquisition"]
    meta = json.loads(Path(paths["training.json"]).read_text())
    assert meta["run_id"] == "r001" and sorted(meta["stage2"]) == ["eda", "feature_checks"]
    assert 0 < len(meta["final_features"]) <= len(A_FEW_CANDIDATES)


@pytest.fixture(scope="module")
def family_env_file(dev_output: tuple[str, dict], tmp_path_factory: pytest.TempPathFactory) -> str:
    """An environment file on the dev preset with a data root of its own. The family runs read
    the sources directly; under `dev_env_file` they would meet `dev_stage2`'s EDA, which read the
    model input, and Training refuses artifacts read from other data."""
    return str(write_environment_file(dev_output[0], tmp_path_factory.mktemp("family_env")))


@pytest.mark.slow
@pytest.mark.parametrize("family", ["lgbm", "xgboost", "xgb_limitdepth", "catboost"])
def test_every_family_trains_end_to_end_on_dev(
    family: str, spark: SparkSession, family_env_file: str, tmp_path: Path
) -> None:
    """Each family alone through the whole stage on the `dev` preset, on every candidate in
    force (no selection rule, so the declared categoricals and the constrained numeric stay):
    its search, the framework's own fits, and inside the run the bundle's round trip and the
    constraint's sweep on the reloaded model. The kept model is the one its search judged
    (XGBoost's margins are float32, hence the tolerance). The first case runs EDA and Feature
    Checks (`autonomous`); the others find them."""
    raw = yaml.safe_load((ROOT / "tests/conf/cc_acquisition.yml").read_text())
    raw["automation_level"] = "autonomous"
    raw["data"]["model_input"] = None
    raw["training"].update(
        estimator_list=[family], max_iter=3, monotone={"age": "increasing"},
        selection={"cluster": False, "floor_z": None, "prune": False},
    )  # fmt: skip
    path = tmp_path / "config.yml"
    path.write_text(yaml.safe_dump(raw))
    out = run(path, env_path=family_env_file, stages=["training"], entity=ENTITY)
    meta, tables = read_stage(out[ENTITY]["training"]["cc_acquisition"]["folder"], "training")
    oof, trials = tables["oof"], tables["trials"]
    assert meta["best"]["family"] == family and len(trials) == 3
    assert {"age", "segment"} <= set(meta["final_features"])
    own = mean_fold_loss("log_loss", oof["target"], oof["score_raw"], oof["cv_fold"])
    assert own == pytest.approx(trials["fold_loss"].min(), abs=1e-8)
