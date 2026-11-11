"""`run` and the CLI (D-024): the Target Factory stage through `python -m core_modelling run`,
every stage on the two example configs at once (one model input, then EDA and Feature Checks per
config), and the guided notebooks calling only the Public API."""

import json
import re
from pathlib import Path

import pytest
import yaml
from conftest import write_environment_file
from pyspark.sql import SparkSession

from core_modelling.__main__ import main
from core_modelling.config import load_config
from core_modelling.dataset.model_input import METADATA_FILE
from core_modelling.environment import feature_dir, load_environment
from core_modelling.feature_checks.findings import STEP_ORDER
from core_modelling.ledger import COLUMNS_BY_STAGE, read_ledger
from core_modelling.run import run

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "tests/conf/cc_acquisition.yml"
SECOND_CONFIG = ROOT / "tests/conf/td_acquisition.yml"
MODEL_INPUT = "05_model_input/retail_acquisition"
NOTEBOOK = ROOT / "notebooks/01_target_factory.ipynb"
NOTEBOOKS = [
    NOTEBOOK,
    ROOT / "notebooks/02_eda.ipynb",
    ROOT / "notebooks/03_feature_checks.ipynb",
    ROOT / "notebooks/00_eda_fc_helper.ipynb",
]
EDA_CANDIDATES = ["age", "income", "segment", "onboarding_channel", "cc_bal", "spend_cc_cnt"]
# The Public API table of docs/architecture.md: what the shipped notebooks may import.
PUBLIC_API = {
    "core_modelling.config": {"load_config", "UseCaseConfig"},
    "core_modelling.environment": {"get_spark_session", "load_environment", "feature_dir"},
    "core_modelling.config.audit_log": {
        "record_decision",
        "show_decisions",
        "resolve_config",
        "read_resolved_config",
    },  # fmt: skip
    "core_modelling.target_factory": {"run_target_factory", "TargetSummary"},
    "core_modelling.dataset": {"build_frames", "save_model_input", "Frames"},
    "core_modelling.run": {"run"},
    "core_modelling.artifacts": {"StageResult", "read_stage", "list_data_definitions"},
    "core_modelling.ledger": {"read_ledger"},
    "core_modelling.eda": {
        "run_eda",
        "pivot_target",
        "lift_by_group",
        "compare_sides",
        "rate_by_period",
    },  # fmt: skip
    "core_modelling.feature_checks": {"run_feature_checks"},
}


def _environment_file(tmp_path: Path, unit_output: tuple[str, dict]) -> Path:
    """An environment file on the written unit preset with the model input under the test
    folder and the Spark settings of the test session."""
    return write_environment_file(unit_output[0], tmp_path)


def test_run_through_the_cli_prints_the_summary_and_saves_the_model_input(
    spark: SparkSession,  # so `run`'s get_spark_session reuses the test session (same settings)
    tmp_path: Path,
    unit_output: tuple[str, dict],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`run <config> --env … --entity entity_a --stages target_factory` prints the target summary
    and the join printout and writes the model input with its metadata."""
    env_file = _environment_file(tmp_path, unit_output)
    command = ["run", str(CONFIG), "--env", str(env_file), "--entity", "entity_a"]
    main([*command, "--stages", "target_factory"])
    out = capsys.readouterr().out
    assert "run target_factory for entity_a" in out and "positive_events" in out
    assert "model input saved:" in out and "entity_a: ran target_factory" in out
    metadata = json.loads((tmp_path / "data" / MODEL_INPUT / METADATA_FILE).read_text())
    assert metadata["use_cases"] == ["cc_acquisition"] and metadata["entity"] == "entity_a"


def test_run_two_configs_runs_every_stage(
    spark: SparkSession, tmp_path: Path, unit_output: tuple[str, dict]
) -> None:
    """`run([a, b])` runs every built stage (a few candidates to keep it short): Target Factory
    returns both summaries and saves one model input whose sidecar lists both use cases and whose
    table carries both target columns; EDA and then Feature Checks run per config on it and
    return the folders they wrote by use case, `eda/` with its json and report, every Feature
    Checks step run, and the ledger beside them pairs the two runs."""
    env_file = _environment_file(tmp_path, unit_output)
    paths = []
    for config in (CONFIG, SECOND_CONFIG):
        raw = yaml.safe_load(config.read_text())
        raw["features"]["candidates"]["include"] = EDA_CANDIDATES
        paths.append(tmp_path / config.name)
        paths[-1].write_text(yaml.safe_dump(raw))
    out = run(paths, env_path=str(env_file))["entity_a"]
    stage = out["target_factory"]
    assert sorted(stage["summary"]) == ["cc_acquisition", "td_acquisition"]
    metadata = json.loads(Path(stage["model_input"], METADATA_FILE).read_text())
    assert metadata["use_cases"] == ["cc_acquisition", "td_acquisition"]
    columns = spark.read.parquet(stage["model_input"]).columns
    assert {"target_cc_acquisition", "target_td_acquisition"} <= set(columns)
    assert "target" not in columns and "eligible" not in columns
    assert sorted(out["eda"]) == sorted(out["feature_checks"]) == sorted(stage["summary"])
    env = load_environment(str(env_file))
    for cfg in map(load_config, paths):
        eda, checks = out["eda"][cfg.use_case], out["feature_checks"][cfg.use_case]
        assert eda["folder"] == feature_dir(env, cfg, "entity_a", "eda")
        assert f"/{cfg.use_case}/04_feature/" in eda["folder"]
        assert Path(eda["eda.json"]).is_file() and Path(eda["report.html"]).is_file()
        assert checks["folder"] == feature_dir(env, cfg, "entity_a", "feature_checks")
        meta = json.loads(Path(checks["folder"], "feature_checks.json").read_text())
        assert meta["steps_run"] == STEP_ORDER
        eda_token = json.loads(Path(eda["eda.json"]).read_text())["run_token"]
        tokens = {"eda": eda_token, "feature_checks": meta["run_token"]}
        folder = feature_dir(env, cfg, "entity_a")
        ledger = read_ledger(folder, meta["data_definition_hash"], tokens)
        assert set(COLUMNS_BY_STAGE["feature_checks"]) <= set(ledger.columns)


def test_run_refuses_an_unknown_stage_or_entity_or_no_config(
    tmp_path: Path, unit_output: tuple[str, dict]
) -> None:
    """A stage not built, an entity the config doesn't list, an empty config list, or configs
    listing different entities when no entity is given, each fail before anything runs."""
    env_file = _environment_file(tmp_path, unit_output)
    with pytest.raises(ValueError, match=r"unknown stages \['training'\]; the built"):
        run(CONFIG, env_path=str(env_file), stages=["training"])
    with pytest.raises(ValueError, match="unknown entity 'entity_b': the config 'cc_acquisition'"):
        run(CONFIG, env_path=str(env_file), entity="entity_b")
    with pytest.raises(ValueError, match="run needs at least one config"):
        run([], env_path=str(env_file))
    second = yaml.safe_load(CONFIG.read_text())
    second["use_case"] = "td_acquisition"
    second["entities"]["entity_b"] = second["entities"]["entity_a"]
    second_path = tmp_path / "td_acquisition.yml"
    second_path.write_text(yaml.safe_dump(second))
    different = (
        "'cc_acquisition' and 'td_acquisition' list different entities "
        r"\(\['entity_a'\] vs \['entity_a', 'entity_b'\]\)"
    )
    with pytest.raises(ValueError, match=different):
        run([CONFIG, second_path], env_path=str(env_file))


@pytest.mark.parametrize("notebook", NOTEBOOKS, ids=lambda path: path.stem)
def test_notebook_calls_only_the_public_api(notebook: Path) -> None:
    """Each shipped notebook imports from the Public API table only and defines nothing (D-024,
    D-039)."""
    cells = json.loads(notebook.read_text())["cells"]
    code = "\n".join("".join(cell["source"]) for cell in cells if cell["cell_type"] == "code")
    imports = re.findall(r"^from (core_modelling\S*) import (.+)$", code, flags=re.MULTILINE)
    assert imports, "the notebook imports nothing from core_modelling"
    for module, names in imports:
        assert module in PUBLIC_API, f"{module} has no public function"
        unknown = {name.strip() for name in names.split(",")} - PUBLIC_API[module]
        assert not unknown, f"{module}: {unknown} are not public"
    assert not re.search(r"^\s*(def|class) ", code, flags=re.MULTILINE)


def test_example_configs_share_one_model_input() -> None:
    """The two example configs load and share what one model input needs: the entity's feature
    sources, the keys, the period and the model input's name; the notebook names both."""
    first, second = load_config(CONFIG), load_config(SECOND_CONFIG)
    assert (first.use_case, second.use_case) == ("cc_acquisition", "td_acquisition")
    for cfg in (first, second):
        assert cfg.data.model_input == "retail_acquisition_input"
    features = [cfg.entities["entity_a"].sources.features for cfg in (first, second)]
    assert features[0] == features[1]
    assert first.data.keys == second.data.keys and first.time.period == second.time.period
    notebook = NOTEBOOK.read_text()
    assert "conf/base/cc_acquisition.yml" in notebook  # the notebooks name the shipped examples
    assert "conf/base/td_acquisition.yml" in notebook
