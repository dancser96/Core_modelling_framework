"""`compare_runs` (evaluation/compare.py): no difference exists for validation, a run against
itself differs by exactly zero, the direction of each metric reads `better` or `worse`, and
runs that cannot be compared are refused. The tables' functions run on cells built from
constructed rows with `cells_from_rows`, with no Spark; the Spark tests compare the evaluated
card run with itself and with a second run trained with another seed."""

import shutil
from collections.abc import Callable
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from cells_oracle import cells_from_rows
from conftest import ENTITY, with_evaluation, with_training
from pyspark.sql import SparkSession
from scipy.special import expit

from core_modelling.artifacts import StageResult, local_path
from core_modelling.config import UseCaseConfig
from core_modelling.config.identities import short
from core_modelling.environment import EnvironmentConfig, models_dir
from core_modelling.evaluation.compare import (
    NOT_AVAILABLE,
    REPORTED_ONLY,
    REPORTED_PARTS,
    ROWS_COLUMNS,
    UNCLEAR,
    _check_shared,
    _compare_cells,
    _feature_changes,
    _incomparable,
    _stacked,
    _verdict,
    _with_differences,
    compare_runs,
)
from core_modelling.evaluation.run import run_evaluation
from core_modelling.evaluation.scores import SCORES_FOLDER
from core_modelling.evaluation.tables import part_cells
from core_modelling.statistics.score_cells import pool_cells
from core_modelling.tasks import TASK_SPECS
from core_modelling.training import run_training

REPLICATES = 20
PERIODS = ["2024-01", "2024-02"]
VALIDATION = "2024-06"
BASES = {"binary": 0.2, "regression": 30.0}
LOSSES = {"binary": "log_loss", "regression": None}  # each task's row loss in the cells


def _rows(task: str, clients: int = 2_000) -> pd.DataFrame:
    """Test-split clients in two periods and every client at the validation period: `client,
    part, period, split, target` and two scores, `signal` (the target's own probability or
    mean) and `noise` (unrelated to it); a regression target is zero on about half the rows."""
    rng = np.random.default_rng(7)
    client = np.arange(clients)
    split = np.where(client % 3 == 0, "train", "test")
    frames = []
    for period in [*PERIODS, VALIDATION]:
        signal = expit(rng.normal(-1.5, 1.0, clients))
        if task == "binary":
            target = (rng.random(clients) < signal).astype(float)
        else:
            signal = 100 * signal
            target = rng.exponential(2 * signal) * (rng.random(clients) < 0.5)
        part = "validation" if period == VALIDATION else "test"
        frames.append(pd.DataFrame({
            "client": client, "part": part, "period": period, "split": split, "target": target,
            "signal": signal, "noise": expit(rng.normal(-1.5, 1.0, clients)),
        }).loc[(split == "test") | (part == "validation")])  # fmt: skip
    return pd.concat(frames, ignore_index=True)


def _parts(
    rows: pd.DataFrame, score: str, task: str, loss: str | None = None
) -> dict[str, pd.DataFrame]:
    """One scorer's cells per part (`part_cells`) over replicate 0 and `REPLICATES` Poisson
    client weights, drawn with one seed for every scorer, so replicate k weights a client alike
    in both runs as `client_weights` does; the score cut at its own 20 quantile bins, the
    target its own bin (binary) or its quartile (regression); the row loss the task's
    (`LOSSES`) unless `loss` names one."""
    edges = np.quantile(rows[score], np.linspace(0, 1, 21)[1:-1])
    target = rows["target"].to_numpy()
    if task == "regression":
        target = np.searchsorted(np.quantile(target, [0.25, 0.5, 0.75]), target, side="right")
    binned = rows.assign(score=rows[score], target_bin=target.astype(int),
                         score_bin=np.searchsorted(edges, rows[score], side="right"))  # fmt: skip
    rng = np.random.default_rng(11)
    clients = rows["client"].max() + 1
    weights = [np.ones(clients, int), *[rng.poisson(1.0, clients) for _ in range(REPLICATES)]]
    split = pd.concat(
        [cells_from_rows(binned.assign(weight=w[binned["client"]]), ["split"],
                         loss or LOSSES[task])
         .assign(replicate=r) for r, w in enumerate(weights)],
        ignore_index=True,
    )  # fmt: skip
    return part_cells({"all": pool_cells(split, "split"), "split": split})


def _metrics(task: str) -> dict[str, Callable[[pd.DataFrame], dict[str, float]]]:
    """Each role's metric: the task's `cell_metrics` at its base, with the loss sums when the
    task's cells carry them."""
    metric = partial(
        TASK_SPECS[task]["cell_metrics"], base=BASES[task], has_loss=LOSSES[task] is not None
    )
    return {"a": metric, "b": metric}


@pytest.fixture(scope="module")
def intervals(in_memory: UseCaseConfig, regression_cfg: UseCaseConfig) -> dict[str, UseCaseConfig]:
    """Each task's config with `REPLICATES` replicates, by task: `_compare_cells` reads its task
    and its intervals only."""
    tasks = (in_memory, regression_cfg)
    return {cfg.task: with_evaluation(cfg, intervals={"replicates": REPLICATES}) for cfg in tasks}


def test_a_difference_is_refused_on_every_part_but_test(
    intervals: dict[str, UseCaseConfig],
) -> None:
    """The difference function refuses validation's cells, its test clients' and a mix with
    test; the tables hold differences on test only and none for validation (D-083)."""
    rows = _rows("binary")
    cells = {"a": _parts(rows, "noise", "binary"), "b": _parts(rows, "signal", "binary")}
    metrics, directions = _metrics("binary"), TASK_SPECS["binary"]["metric_directions"]
    mixed = pd.concat([_stacked(cells, "test"), _stacked(cells, "validation")])
    for stacked in [_stacked(cells, part) for part in REPORTED_PARTS] + [mixed]:
        with pytest.raises(ValueError, match="test part only"):
            _with_differences(stacked, metrics, directions)
    tables = _compare_cells(cells, metrics, intervals["binary"], {})
    assert set(tables["differences"]["part"]) == {"test"}
    assert set(tables["validation"]["part"]) == set(REPORTED_PARTS)
    assert (tables["validation"]["use"] == REPORTED_ONLY).all()
    assert not {"difference", "verdict"} & set(tables["validation"].columns)


@pytest.mark.parametrize("task", ["binary", "regression"])
def test_every_cell_metric_has_a_direction_or_none(task: str) -> None:
    """Each of the task's cell metrics is in exactly one of `metric_directions` (±1) and
    `undirected_metrics`, so a new metric cannot reach the comparison without one."""
    spec = TASK_SPECS[task]
    test = _parts(_rows(task), "signal", task)["test"]
    names = set(_metrics(task)["a"](test.loc[test["replicate"] == 0]))
    directed, undirected = set(spec["metric_directions"]), set(spec["undirected_metrics"])
    assert directed | undirected == names and not directed & undirected
    assert set(spec["metric_directions"].values()) <= {1, -1}


@pytest.mark.parametrize("task", ["binary", "regression"])
def test_one_set_of_cells_differs_by_exactly_zero(
    task: str, intervals: dict[str, UseCaseConfig]
) -> None:
    """Two runs on one set of cells (a run against itself) give every difference 0 with a
    zero-width interval and no clear difference, both runs' numbers equal, for either task;
    only a metric the scorer cannot have (the deviance without a row loss) is not available."""
    parts = _parts(_rows(task), "signal", task)
    tables = _compare_cells({"a": parts, "b": parts}, _metrics(task), intervals[task], {})
    differences = tables["differences"].set_index("metric")
    undefined = ["deviance"] if task == "regression" else []
    assert (differences.loc[undefined, "verdict"] == NOT_AVAILABLE).all()
    defined = differences.drop(index=undefined)
    assert len(defined) >= 4
    assert (defined[["difference", "low", "high"]] == 0).all().all()
    assert (defined["verdict"] == UNCLEAR).all()
    for name in ("metrics", "validation"):
        side = tables[name]
        assert side["value_a"].equals(side["value_b"]) and side["low_a"].equals(side["low_b"])


def test_a_better_scorer_reads_better_and_the_swap_worse(
    intervals: dict[str, UseCaseConfig],
) -> None:
    """The target's own probability against an unrelated score: AUC rises and the log loss
    falls, both `better` in their direction; with the runs swapped, both `worse`."""
    rows = _rows("binary")
    noise, signal = _parts(rows, "noise", "binary"), _parts(rows, "signal", "binary")
    for a, b, word in ((noise, signal, "better"), (signal, noise, "worse")):
        tables = _compare_cells({"a": a, "b": b}, _metrics("binary"), intervals["binary"], {})
        table = tables["differences"]
        verdicts = table.set_index("metric")["verdict"]
        assert verdicts["roc_auc"] == word and verdicts["log_loss"] == word
        assert table.set_index("metric").loc["log_loss", "better_when"] == "lower"


def test_two_row_losses_give_the_loss_metric_no_difference(
    intervals: dict[str, UseCaseConfig],
) -> None:
    """A Tweedie run against a Poisson one: the deviance is decided up front as not available,
    with both losses named; both runs' deviances still sit side by side; one loss, nothing."""
    cfg = intervals["regression"]
    losses = {"a": "tweedie_deviance", "b": "poisson_deviance"}
    incomparable = _incomparable(losses, cfg)
    assert list(incomparable) == ["deviance"] and all(
        n in incomparable["deviance"] for n in losses.values()
    )
    assert _incomparable({"a": "poisson_deviance", "b": "poisson_deviance"}, cfg) == {}
    rows = _rows("regression")
    cells = {role: _parts(rows, "signal", "regression", loss) for role, loss in losses.items()}
    metric = partial(TASK_SPECS["regression"]["cell_metrics"], base=BASES["regression"])
    tables = _compare_cells(cells, {"a": metric, "b": metric}, cfg, incomparable)
    deviance = tables["differences"].set_index("metric").loc["deviance"]
    assert deviance["verdict"] == NOT_AVAILABLE and deviance["reason"] == incomparable["deviance"]
    assert np.isnan(deviance[["difference", "low", "high"]].astype(float)).all()
    side = tables["metrics"].set_index("metric").loc["deviance"]
    assert np.isfinite(side[["value_a", "value_b"]].astype(float)).all()
    assert side["value_a"] != side["value_b"]


def test_the_verdict_reads_each_direction() -> None:
    """An interval above zero is better where higher is better and worse where lower is; one
    holding zero is no clear difference; an undefined one is not available."""
    assert _verdict(0.01, 0.02, 1) == "better" and _verdict(0.01, 0.02, -1) == "worse"
    assert _verdict(-0.02, -0.01, -1) == "better" and _verdict(-0.02, -0.01, 1) == "worse"
    assert _verdict(-0.01, 0.01, 1) == UNCLEAR and _verdict(0.0, 0.0, -1) == UNCLEAR
    assert _verdict(float("nan"), float("nan"), 1) == NOT_AVAILABLE


def test_the_features_that_moved_entered_or_left() -> None:
    """x5 entered and x4 left; of the features in both, the rank moves, the largest first and
    ties by b's rank, an unmoved feature not listed."""
    a = pd.DataFrame({"feature": ["x1", "x2", "x3", "x4", "x6"],
                      "contribution_share": [0.4, 0.3, 0.15, 0.1, 0.05],
                      "contribution_rank": [1, 2, 3, 4, 5]})  # fmt: skip
    b = pd.DataFrame({"feature": ["x2", "x1", "x5", "x3", "x6"],
                      "contribution_share": [0.4, 0.3, 0.15, 0.1, 0.05],
                      "contribution_rank": [1, 2, 3, 4, 5]})  # fmt: skip
    features, importance = _feature_changes(a, b)
    assert list(zip(features["feature"], features["change"], strict=True)) == [
        ("x5", "entered"), ("x4", "left")
    ]  # fmt: skip
    assert importance["feature"].tolist() == ["x2", "x1", "x3"]
    assert importance["rank_change"].tolist() == [-1, 1, 1]


def _counts(**changed: dict[str, int]) -> pd.DataFrame:
    """The outer join's counts per part, both runs scoring the same 100 and 50 rows alike;
    `changed` overrides a part's columns."""
    base = {"rows_a": 100, "rows_b": 100, "shared": 100, "split_differs": 0, "target_differs": 0,
            "score_differs": 0}  # fmt: skip
    parts = {"test": base, "validation": {**base, "rows_a": 50, "rows_b": 50, "shared": 50}}
    return pd.DataFrame([{"part": p, **v, **changed.get(p, {})} for p, v in parts.items()])


def test_rows_with_another_target_or_no_shared_part_are_refused() -> None:
    """The rows table states each run's rows and the shared ones; a shared row with another
    target or split, or a part both runs never scored together, is refused."""
    rows = _check_shared(_counts(test={"score_differs": 7}))
    assert list(rows.columns) == ROWS_COLUMNS
    assert rows.set_index("part").loc["test", ["rows_b", "scored_differently"]].tolist() == [100, 7]
    with pytest.raises(ValueError, match="another target"):
        _check_shared(_counts(test={"target_differs": 3}))
    with pytest.raises(ValueError, match="another client split"):
        _check_shared(_counts(validation={"split_differs": 2}))
    with pytest.raises(ValueError, match="share no scored row"):
        _check_shared(_counts().iloc[:1])


def test_rows_only_one_run_scored_are_refused() -> None:
    """Two runs of one data definition and split score the same rows: a row only one of them
    scored (a source period changed after a run) is refused, naming each run's rows."""
    with pytest.raises(ValueError, match=r"'rows_a': 100, 'rows_b': 120, 'shared': 100"):
        _check_shared(_counts(test={"rows_b": 120}))
    with pytest.raises(ValueError, match="source period changed"):
        _check_shared(_counts(validation={"rows_a": 60}))


@pytest.fixture(scope="module")
def second_run(
    spark: SparkSession,
    trained_env: EnvironmentConfig,
    card_quick: UseCaseConfig,
    evaluated_card: StageResult,
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[EnvironmentConfig, str, str]:
    """A copy of the evaluated runs' data root with a second card run, trained with another
    seed and evaluated: (the copy's environment, the evaluated card run, the second run)."""
    root = tmp_path_factory.mktemp("compared_data")
    shutil.copytree(trained_env.roots.data, root, dirs_exist_ok=True)
    env = trained_env.model_copy(
        update={"roots": trained_env.roots.model_copy(update={"data": str(root)})}
    )
    cfg = with_training(card_quick, seed=7)
    second = run_training(cfg, ENTITY, env, spark).meta["run_id"]
    run_evaluation(cfg, ENTITY, env, spark, run=second)
    return env, evaluated_card.meta["run_id"], second


def test_a_run_against_itself_differs_by_zero_on_all_its_rows(
    spark: SparkSession,
    trained_env: EnvironmentConfig,
    card_quick: UseCaseConfig,
    evaluated_card: StageResult,
) -> None:
    """The evaluated card run against itself: every row with a known target shared and scored
    alike (the scores table's null-target rows are no part of a comparison), every difference 0
    with a zero-width interval, no feature moved."""
    run = evaluated_card.meta["run_id"]
    result = compare_runs(card_quick, ENTITY, trained_env, spark, run, run)
    scores = models_dir(trained_env, card_quick, run, "evaluation", SCORES_FOLDER)
    known = spark.read.parquet(scores).where("target IS NOT NULL")
    counted = known.groupBy("part").count().toPandas()
    rows = result["rows"].set_index("part").join(counted.set_index("part"))
    assert (rows["shared"] == rows["count"]).all() and (rows["rows_a"] == rows["count"]).all()
    assert (rows["rows_b"] == rows["count"]).all() and (rows["scored_differently"] == 0).all()
    differences = result["differences"]
    assert (differences[["difference", "low", "high"]] == 0).all().all()
    assert (differences["verdict"] == UNCLEAR).all()
    assert result["features"].empty and result["importance"].empty


def test_two_runs_differ_on_test_only_and_report_validation_side_by_side(
    spark: SparkSession, card_quick: UseCaseConfig, second_run: tuple[EnvironmentConfig, str, str]
) -> None:
    """Two runs of one data definition: the differences are the test part's alone, validation
    sits side by side with no difference under "reported, never chosen on", and the budgets
    name both runs, one chosen family each."""
    env, first, second = second_run
    result = compare_runs(card_quick, ENTITY, env, spark, first, second)
    # another seed scores every part otherwise, so a broken count or difference would show
    assert (result["rows"]["scored_differently"] > 0).all()
    assert (result["differences"]["difference"] != 0).any()
    assert list(result) == ["rows", "metrics", "differences", "validation", "features",
                            "importance", "budgets"]  # fmt: skip
    assert set(result["differences"]["part"]) == {"test"}
    assert set(result["metrics"]["part"]) == {"test"}
    validation = result["validation"]
    assert set(validation["part"]) == set(REPORTED_PARTS)
    assert (validation["use"] == REPORTED_ONLY).all()
    assert not {"difference", "verdict"} & set(validation.columns)
    budgets = result["budgets"]
    assert set(budgets["run"]) == {first, second}
    assert budgets.groupby("run")["chosen"].sum().tolist() == [1, 1]


def test_runs_of_two_data_definitions_are_refused(
    spark: SparkSession,
    trained_env: EnvironmentConfig,
    card_quick: UseCaseConfig,
    trained_card: StageResult,
    trained_regression: StageResult,
) -> None:
    """The card run against the regression variant's run is refused, naming both hashes."""
    card, regression = trained_card.meta, trained_regression.meta
    with pytest.raises(ValueError, match="two data definitions") as refused:
        compare_runs(card_quick, ENTITY, trained_env, spark, card["run_id"],
                     regression["run_id"])  # fmt: skip
    for meta in (card, regression):
        assert short(meta["data_definition_hash"]) in str(refused.value)


def test_a_run_without_evaluation_is_refused(
    spark: SparkSession,
    trained_env: EnvironmentConfig,
    card_quick: UseCaseConfig,
    evaluated_card: StageResult,
    tmp_path: Path,
) -> None:
    """On a copy of the data root whose card run lost its `evaluation/`, the comparison asks
    for Evaluation first."""
    shutil.copytree(trained_env.roots.data, tmp_path, dirs_exist_ok=True)
    env = trained_env.model_copy(
        update={"roots": trained_env.roots.model_copy(update={"data": str(tmp_path)})}
    )
    run = evaluated_card.meta["run_id"]
    shutil.rmtree(local_path(models_dir(env, card_quick, run, "evaluation")))
    with pytest.raises(ValueError, match="run Evaluation on it first"):
        compare_runs(card_quick, ENTITY, env, spark, run, run)
