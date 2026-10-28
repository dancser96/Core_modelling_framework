"""`run` and the CLI (D-024): the Target Factory stage through `python -m core_modelling run`,
and the guided notebook calling only the Public API."""

import json
import re
from pathlib import Path

import pytest
import yaml
from pyspark.sql import SparkSession

from core_modelling.__main__ import main
from core_modelling.dataset.model_input import METADATA_FILE
from core_modelling.run import run

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "conf/base/cc_acquisition.yml"
NOTEBOOK = ROOT / "notebooks/01_target_factory.ipynb"
# The Public API table of docs/architecture.md: what the shipped notebooks may import.
PUBLIC_API = {
    "core_modelling.config": {"load_config", "UseCaseConfig"},
    "core_modelling.environment": {"get_spark_session", "load_environment"},
    "core_modelling.config.audit_log": {
        "record_decision",
        "show_decisions",
        "resolve_config",
        "read_resolved_config",
    },  # fmt: skip
    "core_modelling.target_factory": {"run_target_factory"},
    "core_modelling.dataset": {"build_frames", "save_model_input"},
    "core_modelling.run": {"run"},
}


def _environment_file(tmp_path: Path, unit_output: tuple[str, dict]) -> Path:
    """An environment file on the written unit preset with the model input under the test
    folder and the Spark settings of the test session."""
    data = str(tmp_path / "data")
    sources = {
        "retail_mart": {"format": "parquet", "path": unit_output[0] + "/mart"},
        "retail_holdings": {"format": "parquet", "path": unit_output[0] + "/holdings"},
        "cc_acquisition_input": {"format": "parquet", "path": data + "/05_model_input/cc"},
    }
    path = tmp_path / "environment.yml"
    content = {"schema_version": 1, "roots": {"data": data}, "sources": {"entity_a": sources}}
    path.write_text(yaml.safe_dump(content))
    return path


def test_run_through_the_cli_prints_the_summary_and_saves_the_model_input(
    spark: SparkSession,  # so `run`'s get_spark_session reuses the test session (same settings)
    tmp_path: Path,
    unit_output: tuple[str, dict],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`run <config> --env … --entity entity_a` prints the target summary and the join printout
    and writes the model input with its metadata."""
    env_file = _environment_file(tmp_path, unit_output)
    main(["run", str(CONFIG), "--env", str(env_file), "--entity", "entity_a"])
    out = capsys.readouterr().out
    assert "run target_factory for entity_a" in out and "positive_events" in out
    assert "model input saved:" in out and "entity_a: ran target_factory" in out
    metadata = json.loads((tmp_path / "data/05_model_input/cc" / METADATA_FILE).read_text())
    assert metadata["use_case"] == "cc_acquisition" and metadata["entity"] == "entity_a"


def test_run_refuses_an_unknown_stage_or_entity(
    tmp_path: Path, unit_output: tuple[str, dict]
) -> None:
    """A stage not built or an entity the config doesn't list fails before anything runs."""
    env_file = _environment_file(tmp_path, unit_output)
    with pytest.raises(ValueError, match=r"unknown stages \['eda'\]; the built stages"):
        run(CONFIG, env_path=str(env_file), stages=["eda"])
    with pytest.raises(ValueError, match="unknown entity 'entity_b'"):
        run(CONFIG, env_path=str(env_file), entity="entity_b")


def test_notebook_calls_only_the_public_api() -> None:
    """The shipped notebook imports from the Public API table only and defines nothing (D-024,
    D-039)."""
    cells = json.loads(NOTEBOOK.read_text())["cells"]
    code = "\n".join("".join(cell["source"]) for cell in cells if cell["cell_type"] == "code")
    imports = re.findall(r"^from (core_modelling\S*) import (.+)$", code, flags=re.MULTILINE)
    assert imports, "the notebook imports nothing from core_modelling"
    for module, names in imports:
        assert module in PUBLIC_API, f"{module} has no public function"
        unknown = {name.strip() for name in names.split(",")} - PUBLIC_API[module]
        assert not unknown, f"{module}: {unknown} are not public"
    assert not re.search(r"^\s*(def|class) ", code, flags=re.MULTILINE)
