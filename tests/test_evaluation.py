"""The Evaluation stage end to end on the unit preset: the card config's and the regression
variant's trained runs, each evaluated once per session in `conftest.py` (20 replicates). What a
run must leave and keep: every table, the json's identity and summary, the report and the
model card, one scored
row per client, period and part, the `run` entry with the validation period it scored, a run of
another data definition refused before anything is read, nothing staged left by a failure after
scoring, the latest run by default, and an older run evaluated again with nothing but
`evaluation/` rewritten (`CLAUDE.md` §4.10).
"""

import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest
from conftest import ENTITY
from pyspark.sql import SparkSession

from core_modelling.artifacts import StageResult, read_stage
from core_modelling.config import UseCaseConfig
from core_modelling.config.audit_log import read_entries
from core_modelling.config.identities import short
from core_modelling.environment import EnvironmentConfig, audit_log_dir, models_dir
from core_modelling.evaluation import run_evaluation
from core_modelling.evaluation.effects import EFFECTS
from core_modelling.evaluation.explain import explanation_cut
from core_modelling.evaluation.views import TRAINING_SIGNOFF, TRAINING_TRIALS
from core_modelling.evaluation.views_explain import TRAIN_SAMPLE
from core_modelling.model.bundle import load_bundle
from core_modelling.periods import period_spec
from core_modelling.runs import list_runs, read_run, show_run
from core_modelling.statistics.score_cells import PARTS, POOLED
from core_modelling.training import run_training

TABLES = {"metrics", "slices", "curves", "reliability", "score_distribution", "strata", "pooling",
          "baselines", "contributions", "features", "permutation_importance",
          "partial_dependence", "cells", "drift_features", "drift_edges", "drift_scores",
          TRAINING_SIGNOFF, TRAINING_TRIALS, TRAIN_SAMPLE, EFFECTS}  # fmt: skip
FILES = ("evaluation.json", "log.json", "resolved_config.yml", "report.html", "model_card.json",
         "model_card.html")  # fmt: skip


@pytest.fixture(params=["evaluated_card", "evaluated_regression"])
def evaluated(request: pytest.FixtureRequest) -> StageResult:
    """Each config's evaluated run in turn."""
    return request.getfixturevalue(request.param)


def _validation_label(cfg: UseCaseConfig) -> str:
    """The label of the config's validation period."""
    return period_spec(cfg).label(cfg.time.validation_period)


def _digests(folder: Path) -> dict[str, str]:
    """The sha256 of every file of a run folder outside `evaluation/`, by relative path."""
    return {
        str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file() and path.relative_to(folder).parts[0] != "evaluation"
    }


def test_evaluation_writes_every_table_and_its_identity(
    evaluated: StageResult, trained_env: EnvironmentConfig
) -> None:
    """`evaluation/` holds its json, log, resolved config, report, model card and scores table,
    and every table, none empty, the effects table of effect features only; the json names
    the run, the bundle's model hash, the validation period scored and when Training ran, and
    its summary the headline metrics per part, which `list_runs` and `show_run` show."""
    cfg, run_id = evaluated.config, evaluated.meta["run_id"]
    folder = Path(models_dir(trained_env, cfg, run_id, "evaluation"))
    meta, tables = read_stage(str(folder), "evaluation")
    assert set(tables) == TABLES and all(len(tables[name]) for name in TABLES)
    effects = set(meta["choices"]["effect_features"])
    assert set(tables[EFFECTS]["feature"]) <= effects
    assert all((folder / name).is_file() for name in FILES) and (folder / "scores").is_dir()
    assert json.loads((folder / "model_card.json").read_text())["details"]["run_id"] == run_id
    assert meta["trained_at"] and meta["training_seconds"]
    assert meta["unavailable"] == {} and "row_loss" in meta
    assert meta["training_config_hash"] == read_run(trained_env, cfg, run_id)["config_hash"]
    assert all({"code", "text"} <= set(warning) for warning in meta["warnings"])
    bundle = load_bundle(models_dir(trained_env, cfg, run_id, "bundle"))
    assert meta["model_hash"] == bundle.model_hash
    assert meta["validation_period"] == _validation_label(cfg)
    assert meta["data_definition_hash"] == cfg.housekeeping["data_definition_hash"]
    headline = meta["choices"]["headline"]
    assert headline[0] == cfg.decision.metric
    names = {f"{part}_{name}" for part in PARTS for name in headline}
    assert names <= set(meta["summary"]) and meta["summary"][f"test_{headline[-1]}"] is not None
    assert list_runs(trained_env, cfg, ENTITY).set_index("run").loc[run_id, "evaluated"]
    assert "evaluated: True" in show_run(trained_env, cfg, ENTITY, run_id)


def test_the_scores_hold_one_row_per_client_period_and_part(
    spark: SparkSession, evaluated: StageResult, trained_env: EnvironmentConfig
) -> None:
    """The scores table holds one row per client, period and part, each with a model score, as
    many as the stored split cells count at replicate 0, and the single feature's column when
    one was chosen."""
    cfg, run_id = evaluated.config, evaluated.meta["run_id"]
    scores = spark.read.parquet(models_dir(trained_env, cfg, run_id, "evaluation", "scores"))
    rows = scores.count()
    assert scores.select("unit_id", "period", "part").distinct().count() == rows
    assert scores.where(scores["score"].isNotNull()).count() == rows
    cells = evaluated.tables["cells"]
    counted = cells.loc[(cells["by"] == "split") & (cells["replicate"] == 0), "rows"].sum()
    assert counted == rows
    chosen = evaluated.meta["choices"]["single_feature"] is not None
    assert ("baseline_single_feature" in scores.columns) == chosen


def test_the_run_entry_names_the_run_and_the_validation_period(
    evaluated: StageResult, trained_env: EnvironmentConfig
) -> None:
    """The audit log gains one `run` entry of stage `evaluation` with the run and the label of
    the validation period it scored."""
    cfg = evaluated.config
    entries = read_entries(audit_log_dir(trained_env, cfg, ENTITY))
    runs = [entry for entry in entries if entry.stage == "evaluation"]
    expected = [("run", evaluated.meta["run_id"], _validation_label(cfg))]
    assert [(entry.op, entry.run_id, entry.validation_period) for entry in runs] == expected


def test_a_run_of_another_data_definition_is_refused(
    spark: SparkSession,
    trained_env: EnvironmentConfig,
    card_quick: UseCaseConfig,
    trained_card: StageResult,
    trained_regression: StageResult,
) -> None:
    """The card config naming the regression variant's run is refused, naming both data
    definitions, and nothing is written."""
    log = audit_log_dir(trained_env, card_quick, ENTITY)
    before = read_entries(log)
    run_id = trained_regression.meta["run_id"]
    with pytest.raises(ValueError, match="was trained for data definition") as refused:
        run_evaluation(card_quick, ENTITY, trained_env, spark, run_id)
    for meta in (trained_card.meta, trained_regression.meta):
        assert short(meta["data_definition_hash"]) in str(refused.value)
    assert read_entries(log) == before


def test_the_explanation_cut_falls_back_only_without_a_usable_slice(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """The cut is the decision's slice; the top 10% stands in when no slice is configured or its
    row is unavailable, saying why, and a configured slice without a row fails loud."""
    above = "not available: above the population of 1,000"
    slices = pd.DataFrame({"part": "test", "period": POOLED,
                           "slice": ["top 1%", "top 10%", "top 10,000"],
                           "rows": [10.0, 100.0, None], "part_rows": 1000.0,
                           "unavailable": ["", "", above]})  # fmt: skip
    curves = pd.DataFrame({"part": "test", "depth": [0.01, 0.1, 1.0], "threshold": [0.9, 0.5, 0.0]})
    cut = explanation_cut(slices, curves, variant())
    assert (cut["slice"], cut["available"], cut["score"]) == ("top 1%", True, 0.9)
    cut = explanation_cut(slices, curves, variant(evaluation={"slices": {"top_pct": []}}))
    assert (cut["slice"], cut["available"], cut["score"]) == ("top 10%", False, 0.5)
    assert above in cut["reason"]
    unset = variant(evaluation={"slices": {"top_pct": [], "top_n": []}})
    assert explanation_cut(slices, curves, unset)["reason"] == "no slice is configured"
    with pytest.raises(ValueError, match="no row for the decision's slice 'top 5%'"):
        explanation_cut(slices, curves, variant(evaluation={"slices": {"top_pct": [0.05]}}))


@pytest.fixture(scope="module")
def env(
    trained_env: EnvironmentConfig,
    evaluated_card: StageResult,
    evaluated_regression: StageResult,
    tmp_path_factory: pytest.TempPathFactory,
) -> EnvironmentConfig:
    """The evaluated runs' environment on a copy of their data root, this module's own: a test
    that trains or evaluates again writes there."""
    root = tmp_path_factory.mktemp("evaluation_data")
    shutil.copytree(trained_env.roots.data, root, dirs_exist_ok=True)
    roots = trained_env.roots.model_copy(update={"data": str(root)})
    return trained_env.model_copy(update={"roots": roots})


@pytest.fixture(scope="module")
def second_card(spark: SparkSession, env: EnvironmentConfig, card_quick: UseCaseConfig) -> str:
    """A second card run trained in this module's copy, after the evaluated ones: the latest
    run of the card's data definition. Returns its run number."""
    return run_training(card_quick, ENTITY, env, spark).meta["run_id"]


def test_a_failure_after_scoring_leaves_no_staged_scores(
    spark: SparkSession,
    env: EnvironmentConfig,
    card_quick: UseCaseConfig,
    evaluated_card: StageResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evaluation failing after the scores table is staged (here at the card) raises its own
    error, leaves no sibling of `evaluation/` (no `.scores-*`, no `.tmp-*`), keeps the earlier
    `evaluation/` as it was and records no entry."""
    run_id = evaluated_card.meta["run_id"]
    folder = Path(models_dir(env, card_quick, run_id))
    before = (folder / "evaluation" / "evaluation.json").read_bytes()
    entries = read_entries(audit_log_dir(env, card_quick, ENTITY))

    def fail(*args: object) -> dict:
        """Stand in for the card, failing once the scores are staged (asserted, so the test
        cannot pass vacuously if the card ever ran before the scores were written)."""
        assert list(folder.glob("evaluation.scores-*"))
        raise RuntimeError("the card failed")

    monkeypatch.setattr("core_modelling.evaluation.run.build_card", fail)
    with pytest.raises(RuntimeError, match="the card failed"):
        run_evaluation(card_quick, ENTITY, env, spark, run_id)
    assert not list(folder.glob("evaluation.*"))
    assert (folder / "evaluation" / "evaluation.json").read_bytes() == before
    assert read_entries(audit_log_dir(env, card_quick, ENTITY)) == entries


def test_the_latest_run_is_evaluated_by_default(
    spark: SparkSession, env: EnvironmentConfig, card_quick: UseCaseConfig, second_card: str
) -> None:
    """Without a run named, Evaluation evaluates the latest trained run of the data definition."""
    assert run_evaluation(card_quick, ENTITY, env, spark).meta["run_id"] == second_card


def test_an_older_run_is_evaluated_again_and_only_evaluation_changes(
    spark: SparkSession,
    env: EnvironmentConfig,
    card_quick: UseCaseConfig,
    evaluated_card: StageResult,
    second_card: str,
) -> None:
    """The older card run, named while a later one exists, is evaluated again: `evaluation/` is
    rewritten whole (a file planted in it is gone), every other file of the run folder stays
    byte-identical, the audit log gains one entry, and the json lists the validation periods the
    earlier Evaluation runs scored."""
    older = evaluated_card.meta["run_id"]
    folder = Path(models_dir(env, card_quick, older))
    before = _digests(folder)
    planted = folder / "evaluation" / "planted.txt"
    planted.write_text("from an earlier run")
    entries = read_entries(audit_log_dir(env, card_quick, ENTITY))
    result = run_evaluation(card_quick, ENTITY, env, spark, older)
    assert result.meta["run_id"] == older and older != second_card
    assert _digests(folder) == before and not planted.exists()
    assert (folder / "evaluation" / "evaluation.json").is_file()
    after = read_entries(audit_log_dir(env, card_quick, ENTITY))
    assert after[: len(entries)] == entries and len(after) == len(entries) + 1
    assert (after[-1].stage, after[-1].run_id) == ("evaluation", older)
    earlier = [entry for entry in entries if entry.stage == "evaluation" and entry.op == "run"]
    assert earlier
    assert [item["seq"] for item in result.meta["earlier_validations"]] == [
        entry.seq for entry in earlier
    ]
