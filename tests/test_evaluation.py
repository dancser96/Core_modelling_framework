"""The Evaluation stage end to end on the unit preset: the card config's and the regression
variant's trained runs, each evaluated once per session in `conftest.py` (20 replicates). What a
run must leave and keep: every table, the json's identity and summary, the report and the
model card, one scored row per client, period and part (the test part's null-target rows kept
for the drift reference, never in a cell), the `run` entry with the validation period it
scored, a run of another data definition refused before anything is read, nothing staged left
by a failure after scoring, the latest run by default, and an older run evaluated again with
nothing but `evaluation/` rewritten (`CLAUDE.md` §4.10). Without Spark: train's in-sample
concordance read on test's cells from a hand-made `oof.parquet`, and two steps' tables of one
name refused.
"""

import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from conftest import ENTITY
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from core_modelling.artifacts import StageResult, read_stage, read_stage_meta
from core_modelling.config import UseCaseConfig
from core_modelling.config.audit_log import read_entries
from core_modelling.config.identities import short
from core_modelling.environment import EnvironmentConfig, audit_log_dir, models_dir
from core_modelling.evaluation import run_evaluation
from core_modelling.evaluation.cells import score_cells, score_edges, scorer_loss
from core_modelling.evaluation.drift_reference import (
    DRIFT_REFERENCE_FILE,
    DRIFT_REFERENCE_SCHEMA_VERSION,
    FEATURE_COLUMNS,
    SCORE_COLUMNS,
)
from core_modelling.evaluation.effects import EFFECT_COLUMNS, EFFECTS
from core_modelling.evaluation.explain import PDP_COLUMNS, explanation_cut
from core_modelling.evaluation.permutation import PERMUTATION_COLUMNS
from core_modelling.evaluation.run import _in_sample_concordance, _merge_tables
from core_modelling.evaluation.slices import SLICE_COLUMNS
from core_modelling.evaluation.tables import METRIC_COLUMNS, STRATA_COLUMNS, VALIDATION_TEST_CLIENTS
from core_modelling.model.bundle import load_bundle
from core_modelling.periods import period_labels, period_spec
from core_modelling.run_artifacts import TRAIN_SAMPLE, TRAINING_SIGNOFF, TRAINING_TRIALS, RunFolder
from core_modelling.runs import list_runs, read_run, show_run
from core_modelling.statistics.metrics import binned_concordance
from core_modelling.statistics.score_cells import MEAN, PARTS, POOLED
from core_modelling.training import run_training

TABLES = {"metrics", "slices", "curves", "reliability", "score_distribution", "strata", "pooling",
          "baselines", "contributions", "features", "permutation_importance",
          "partial_dependence", "cells", "drift_features", "drift_edges", "drift_scores",
          TRAINING_SIGNOFF, TRAINING_TRIALS, TRAIN_SAMPLE, EFFECTS}  # fmt: skip
COLUMNS = {"metrics": METRIC_COLUMNS, "slices": SLICE_COLUMNS, "strata": STRATA_COLUMNS,
           "partial_dependence": PDP_COLUMNS, "permutation_importance": PERMUTATION_COLUMNS,
           EFFECTS: EFFECT_COLUMNS, "drift_features": FEATURE_COLUMNS,
           "drift_scores": SCORE_COLUMNS,
           "drift_edges": ["feature", "position", "edge"]}  # fmt: skip
WARNING_CODES = {
    "newer_runs_passed_over",
    "nulls_not_in_train",
    "explanation_cut_not_at_decision_slice",
    "single_feature_baseline_not_chosen",
    "single_feature_baseline_has_nulls",
}
FILES = ("evaluation.json", "log.json", "resolved_config.yml", "report.html", "model_card.json",
         "model_card.html", DRIFT_REFERENCE_FILE)  # fmt: skip


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
    """`evaluation/` holds its json, log, resolved config, report, model card, drift reference
    sidecar (the run and model it is of) and scores table, and every table, none empty, the
    effects table of effect features only; the json names
    the run, the bundle's model hash, the validation period scored, when Training ran and
    Training's warnings as written, and its summary the headline metrics per part, which
    `list_runs` and `show_run` show."""
    cfg, run_id = evaluated.config, evaluated.meta["run_id"]
    folder = Path(models_dir(trained_env, cfg, run_id, "evaluation"))
    meta, tables = read_stage(str(folder), "evaluation")
    assert set(tables) == TABLES and all(len(tables[name]) for name in TABLES)
    for name, columns in COLUMNS.items():
        assert list(tables[name].columns) == columns, name
    effects = set(meta["choices"]["effect_features"])
    assert set(tables[EFFECTS]["feature"]) <= effects
    assert all((folder / name).is_file() for name in FILES) and (folder / "scores").is_dir()
    assert json.loads((folder / "model_card.json").read_text())["details"]["run_id"] == run_id
    sidecar = json.loads((folder / DRIFT_REFERENCE_FILE).read_text())
    assert sidecar["drift_reference_schema_version"] == DRIFT_REFERENCE_SCHEMA_VERSION
    assert (sidecar["run_id"], sidecar["model_hash"]) == (run_id, meta["model_hash"])
    assert meta["trained_at"] and meta["training_seconds"]
    assert meta["unavailable"] == {} and "row_loss" in meta
    assert meta["training_config_hash"] == read_run(trained_env, cfg, run_id)["config_hash"]
    assert all({"code", "text"} <= set(warning) for warning in meta["warnings"])
    assert {warning["code"] for warning in meta["warnings"]} <= WARNING_CODES
    training = read_stage_meta(models_dir(trained_env, cfg, run_id, "training"), "training")
    assert meta["training_warnings"] == training["warnings"]  # as Training wrote them
    bundle = load_bundle(models_dir(trained_env, cfg, run_id, "bundle"))
    assert meta["model_hash"] == bundle.model_hash
    assert meta["validation_period"] == _validation_label(cfg)
    assert meta["data_definition_hash"] == cfg.housekeeping["data_definition_hash"]
    headline = meta["choices"]["headline"]
    assert headline[0] == cfg.decision.metric
    names = {f"{part}_{name}" for part in PARTS for name in headline}
    assert names <= set(meta["summary"]) and meta["summary"][f"test_{headline[-1]}"] is not None
    assert list_runs(cfg, ENTITY, trained_env).set_index("run").loc[run_id, "evaluated"]
    assert "evaluated: True" in show_run(cfg, ENTITY, trained_env, run_id)


def test_the_metric_rows_hold_the_parts_and_periods_scored_and_their_counts(
    evaluated: StageResult,
) -> None:
    """The model's metric rows are those of the test part over the observation window's periods
    then pooled and their mean, of the validation part and of its test-split clients over the
    validation period then pooled, and of each strata variable; each part's pooled `rows` is
    the sum of its stored split cells' rows, and the strata table names the same variables."""
    cfg, tables = evaluated.config, evaluated.tables
    metrics = tables["metrics"]
    plain = metrics.loc[metrics["stratum"].isna()]
    window = cfg.time.observation_window
    labels = set(period_labels(window.first, window.last, period_spec(cfg)))
    assert set(plain["part"]) == {*PARTS, VALIDATION_TEST_CLIENTS}
    test = set(plain.loc[plain["part"] == "test", "period"])
    assert {POOLED, MEAN} <= test and test - {POOLED, MEAN} <= labels
    for part in ("validation", VALIDATION_TEST_CLIENTS):
        assert set(plain.loc[plain["part"] == part, "period"]) == {_validation_label(cfg), POOLED}
    variables = set(cfg.strata.variables)
    assert set(metrics["stratum"].dropna()) == variables == set(tables["strata"]["stratum"])
    cells = tables["cells"]
    split = cells.loc[cells["by"] == "split"]
    validation = split["part"] == "validation"
    stored = {"test": split.loc[split["part"] == "test", "rows"].sum(),
              "validation": split.loc[validation, "rows"].sum(),
              VALIDATION_TEST_CLIENTS: split.loc[validation & (split["level"] == "test"),
                                                 "rows"].sum()}  # fmt: skip
    pooled = plain.loc[plain["period"] == POOLED].drop_duplicates("part").set_index("part")["rows"]
    assert pooled.to_dict() == pytest.approx(stored)


def test_the_warnings_are_those_the_run_found(evaluated: StageResult) -> None:
    """Each warning's code is a known one and appears once; the explanation-cut warning is there
    exactly when the cut fell back from the decision's slice, and the nulls warning exactly
    when the feature table marks a feature null at scoring and never in train, naming them."""
    meta, features = evaluated.meta, evaluated.tables["features"]
    warnings = {warning["code"]: warning for warning in meta["warnings"]}
    assert len(warnings) == len(meta["warnings"]) and set(warnings) <= WARNING_CODES
    fell_back = not meta["choices"]["explanation_cut"]["available"]
    assert ("explanation_cut_not_at_decision_slice" in warnings) == fell_back
    unseen = features.loc[features["null_not_in_train"], "feature"].tolist()
    assert ("nulls_not_in_train" in warnings) == bool(unseen)
    if unseen:
        assert warnings["nulls_not_in_train"]["features"] == unseen


def test_the_scores_hold_one_row_per_client_period_and_part(
    spark: SparkSession, evaluated: StageResult, trained_env: EnvironmentConfig
) -> None:
    """The scores table holds one row per client, period and part, each with a model score; a
    null target on test rows only; the stored split cells count its rows with a known target at
    replicate 0 and the drift reference's pooled score rows every test row; and the single
    feature's column when one was chosen."""
    cfg, run_id = evaluated.config, evaluated.meta["run_id"]
    scores = spark.read.parquet(models_dir(trained_env, cfg, run_id, "evaluation", "scores"))
    rows = scores.count()
    assert scores.select("unit_id", "period", "part").distinct().count() == rows
    assert scores.where(scores["score"].isNotNull()).count() == rows
    unlabelled = scores.where(F.col("target").isNull())
    assert unlabelled.where(F.col("part") != "test").count() == 0
    cells = evaluated.tables["cells"]
    counted = cells.loc[(cells["by"] == "split") & (cells["replicate"] == 0), "rows"].sum()
    assert counted == rows - unlabelled.count()
    drift = evaluated.tables["drift_scores"]
    tested = scores.where(F.col("part") == "test").count()
    assert drift.loc[drift["period"] == POOLED, "rows"].sum() == tested
    chosen = evaluated.meta["choices"]["single_feature"] is not None
    assert ("baseline_single_feature" in scores.columns) == chosen


def test_spark_the_metric_cells_are_those_of_the_known_targets_alone(
    spark: SparkSession, evaluated: StageResult, trained_env: EnvironmentConfig
) -> None:
    """The stored split cells, which every metric, slice, calibration, baseline and replicate
    reads, are the cells of the stored scores with a known target, recomputed here: identical
    whether the null-target rows were in the table or not."""
    cfg, run_id = evaluated.config, evaluated.meta["run_id"]
    scores = spark.read.parquet(models_dir(trained_env, cfg, run_id, "evaluation", "scores"))
    known = scores.where(F.col("target").isNotNull())
    edges = score_edges(known, cfg)
    loss = scorer_loss(cfg, evaluated.meta["choices"]["objective"])
    cells = score_cells(known, cfg, ["split"], edges, loss=loss)
    recomputed = cells.loc[cells["replicate"] == 0].rename(columns={"split": "level"})
    stored = evaluated.tables["cells"]
    stored = stored.loc[stored["by"] == "split", recomputed.columns]
    pd.testing.assert_frame_equal(stored.reset_index(drop=True),
                                  recomputed.reset_index(drop=True))  # fmt: skip


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
    without_fallback = slices.loc[slices["slice"] != "top 10%"]
    with pytest.raises(ValueError, match="the test slices hold no row for 'top 10%'"):
        explanation_cut(without_fallback, curves, unset)


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


def test_trains_in_sample_concordance_is_read_on_tests_cells(tmp_path: Path) -> None:
    """From a hand-made `oof.parquet`: on test's score edges and target bins, train's in-sample
    score gives `binned_concordance`'s value; a 0/1 target's cells hold the target itself, so
    None (`open_run_folder` refuses an `oof.parquet` without `score_in_sample` before)."""
    tables = tmp_path / "training" / "tables"
    tables.mkdir(parents=True)
    score = np.array([0.1, 0.5, 0.6, 0.9, 1.3, 0.2, 0.3])
    target = np.array([0.0, 2.0, 1.0, 3.0, 5.0, 0.0, 4.0])
    oof = pd.DataFrame({"unit_id": [f"c{i}" for i in range(7)], "target": target,
                        "score": score / 2, "score_in_sample": score})  # fmt: skip
    oof.to_parquet(tables / "oof.parquet")
    edges = {"score": np.array([0.3, 0.8]), "target": np.array([0.5, 2.5])}
    read = RunFolder(folder=str(tmp_path), run={}, bundle=None, manifest={}, training={},
                     run_ledger=pd.DataFrame(), stage2={})  # fmt: skip
    assert _in_sample_concordance(read, edges) == pytest.approx(15 / 16)
    assert _in_sample_concordance(read, edges) == binned_concordance(
        score, target, edges["score"], edges["target"]
    )
    assert _in_sample_concordance(read, {**edges, "target": None}) is None


def test_two_steps_tables_of_one_name_are_refused() -> None:
    """Merging the steps' tables refuses a name two of them hold, naming it, so no table
    silently replaces another; distinct names merge in order."""
    one, two = pd.DataFrame({"a": [1]}), pd.DataFrame({"b": [2]})
    merged = _merge_tables({"metrics": one}, {"features": two}, {"signoff": one})
    assert list(merged) == ["metrics", "features", "signoff"]
    with pytest.raises(ValueError, match=r"tables \['features'\] are each written by two steps"):
        _merge_tables({"metrics": one, "features": one}, {"features": two})
