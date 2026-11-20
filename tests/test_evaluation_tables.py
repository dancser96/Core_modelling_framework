"""Evaluation's scores table and score cells (`evaluation/scores.py`, `evaluation/cells.py`):
the bootstrap weights' inverse CDF, the edges' rules, the strata's levels, the pooled cells,
the scorer's loss and the families' thread counts without Spark; then, in real local Spark (run
by the main thread), `score_parts` and `write_scores` on a bundle from `test_bundle.py`'s
helpers, the client weights, and the cells against `cells_from_rows`, their pandas mirror, on a
small scores table built here.
"""

import json
import os
from collections.abc import Callable
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from conftest import REGRESSION, with_training
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from scipy.stats import poisson
from test_bundle import IDENTITY, raw_frame, trained

from core_modelling.config import UseCaseConfig
from core_modelling.dataset.counts import OTHER
from core_modelling.eda.population import cap_levels
from core_modelling.evaluation.cells import (
    POISSON_CDF,
    POISSON_MAX,
    UNIFORM_BITS,
    WEIGHT_SALT,
    _check_other,
    _distinct_edges,
    _poisson_weight,
    _uniform,
    client_weights,
    score_cells,
    score_edges,
    scorer_loss,
    stratum_labels,
)
from core_modelling.evaluation.scores import score_parts, write_scores
from core_modelling.model import FAMILIES, encode_frame, load_bundle, score_frame, write_bundle
from core_modelling.model.bundle import OUTPUT_COLUMNS
from core_modelling.model.scoring import _task_threads
from core_modelling.periods import period_spec
from core_modelling.statistics.score_cells import (
    STRATA_STEP,
    bin_quantiles,
    cells_from_rows,
    pool_cells,
    quantile_passes,
)

WINDOW = [date(2025, 6, 1), date(2025, 7, 1)]  # two months of the test part
VALIDATION = date(2025, 11, 1)  # the test config's validation period
# Each row loss once and none (a squared-error model): the Spark losses against the mirror's
LOSS_CASES = [("binary", "log_loss"), ("regression", "tweedie_deviance"),
              ("regression", "poisson_deviance"), ("regression", None)]  # fmt: skip
TOP_UNIFORM = 1 - 2.0**-UNIFORM_BITS  # the largest uniform `_uniform` gives
CHANNELS = ["branch", "online", "null", *[f"partner_{n:02d}" for n in range(11)]]  # 14 levels


def with_replicates(cfg: UseCaseConfig, replicates: int) -> UseCaseConfig:
    """`cfg` with `evaluation.intervals.replicates` changed, validated."""
    data = cfg.model_dump()
    data["evaluation"]["intervals"]["replicates"] = replicates
    return UseCaseConfig.model_validate(data)


def scores_table(task: str, clients: int = 600, seed: int = 0) -> pd.DataFrame:
    """A scores table as `score_parts` returns it, without a model: the even clients are the
    test split, each with a row at both `WINDOW` months (`part` `test`), and every client has
    a row at `VALIDATION`. Binary scores are distinct probabilities; regression's are positive
    with a fifth of the rows at exactly 1.0 (a mass point), and a third of its targets are 0.
    The stratum `onboarding_channel` has `CHANNELS`' 14 levels, more than `strata.max_levels`,
    and 5% nulls."""
    rng = np.random.default_rng(seed)
    ids = np.array([f"c{number:04d}" for number in range(clients)])
    test = ids[::2]
    parts = [
        pd.DataFrame({"unit_id": test, "period": month, "part": "test", "split": "test"})
        for month in WINDOW
    ]
    split = np.where(np.arange(clients) % 2 == 0, "test", "train")
    validation = {"unit_id": ids, "period": VALIDATION, "part": "validation", "split": split}
    frame = pd.concat([*parts, pd.DataFrame(validation)], ignore_index=True)
    rows = len(frame)
    if task == "binary":
        margin = rng.normal(-1, 1.5, rows)
        score = 1 / (1 + np.exp(-margin))
        target = (rng.random(rows) < score).astype(np.int64)
    else:
        margin = np.where(rng.random(rows) < 0.2, 0.0, rng.normal(0, 0.8, rows))
        score = np.exp(margin)
        target = np.where(rng.random(rows) < 0.3, 0.0, rng.gamma(2, score / 2))
    shares = 0.7 ** np.arange(len(CHANNELS))
    channel = rng.choice(np.array(CHANNELS, dtype=object), rows, p=shares / shares.sum())
    return frame.assign(
        target=target,
        margin=margin,
        score_raw=score,
        score=score,
        segment=rng.choice(["mass", "affluent", "private"], rows),
        onboarding_channel=np.where(rng.random(rows) < 0.05, None, channel),
    )


def expected_cells(
    table: pd.DataFrame,
    cfg: UseCaseConfig,
    by: list[str],
    edges: np.ndarray,
    target: np.ndarray | None,
    loss: str | None,
) -> pd.DataFrame:
    """`cells_from_rows` on `table` (with its `weight` column) binned in numpy as the
    `Bucketizer` bins: bucket i is [e_i, e_{i+1}) over [−inf, *edges, inf]; a 0/1 target is its
    own bin. The period is its label and a stratum in `by` EDA's level (`cap_levels` over
    every row), as `score_cells` gives them."""
    score_bin = np.searchsorted(edges, table["score"].to_numpy(), side="right")
    values = table["target"].to_numpy()
    target_bin = values if target is None else np.searchsorted(target, values, side="right")
    strata = [name for name in by if name in cfg.strata.variables]
    rows = table.assign(
        score_bin=score_bin,
        target_bin=target_bin,
        period=table["period"].map(period_spec(cfg).label),
        **{name: cap_levels(table[name], cfg.strata.max_levels).astype(str) for name in strata},
    )
    return cells_from_rows(rows, by, loss)


def replicate_weights(spark: SparkSession, table: pd.DataFrame, replicate: int) -> pd.Series:
    """Each row's weight in `replicate` (≥ 1), from `client_weights` keyed by the client."""
    clients = spark.createDataFrame(table[["unit_id"]].drop_duplicates())
    weights = client_weights(F.col("unit_id"), replicate, WEIGHT_SALT)[replicate - 1]
    found = clients.select("unit_id", weights.alias("weight")).toPandas()
    return table["unit_id"].map(found.set_index("unit_id")["weight"])


def thresholds_below(u: np.ndarray) -> np.ndarray:
    """Per uniform, the count of `POISSON_CDF`'s thresholds below it: `_poisson_weight` in
    numpy."""
    return (u[:, None] > POISSON_CDF).sum(axis=1)


def drawn_weights(frame: DataFrame, replicates: int, salt: str) -> np.ndarray:
    """`client_weights` of `frame`'s rows, a row of `replicates` weights per frame row, the
    rows ordered by client (a client's rows next to each other)."""
    weights = client_weights(F.col("unit_id"), replicates, salt).alias("weights")
    found = frame.select("unit_id", weights).toPandas().sort_values("unit_id", kind="stable")
    return np.stack(found["weights"].to_numpy())


def booster_threads(booster: object) -> str | None:
    """An XGBoost booster's own `nthread` setting; None for the other families' models."""
    if not hasattr(booster, "save_config"):
        return None
    return json.loads(booster.save_config())["learner"]["generic_param"]["nthread"]


def random_rows(seed: int) -> pd.DataFrame:
    """Binned rows as `cells_from_rows` receives them: two parts, two periods, two splits,
    a few bins, a 0/1 target, a probability and weights 0 to 3."""
    rng = np.random.default_rng(seed)
    rows = 500
    return pd.DataFrame(
        {
            "part": rng.choice(["test", "validation"], rows),
            "period": rng.choice(["2024-01", "2024-02"], rows),
            "split": rng.choice(["train", "test"], rows),
            "score_bin": rng.integers(0, 6, rows),
            "target_bin": rng.integers(0, 2, rows),
            "score": rng.uniform(0.01, 0.99, rows),
            "weight": rng.integers(0, 4, rows),
        }
    ).assign(target=lambda frame: frame["target_bin"])


# ---- no Spark ---------------------------------------------------------------------------------


def test_the_poisson_thresholds_are_scipys_inverse_cdf() -> None:
    """The count of `POISSON_CDF`'s thresholds below u, `_poisson_weight`'s sum in numpy, is
    scipy's Poisson(1) `ppf` on a fine grid and at the largest uniform, which reaches
    `POISSON_MAX`: the cap cuts off less than one uniform step. At a threshold itself k is
    taken, just above it k + 1; there scipy's own CDF can differ in the last bit (k = 0, 9),
    so the thresholds are scipy's CDF to within two bits."""
    u = np.concatenate([np.linspace(0, 1, 200_001)[1:-1], [TOP_UNIFORM]])
    weights = thresholds_below(u)
    np.testing.assert_array_equal(weights, poisson.ppf(u, 1))
    assert weights.max() == POISSON_MAX and poisson.sf(POISSON_MAX, 1) < 2.0**-UNIFORM_BITS
    ks = np.arange(POISSON_MAX)
    np.testing.assert_allclose(POISSON_CDF, poisson.cdf(ks, 1), rtol=0, atol=2.0**-52)
    np.testing.assert_array_equal(thresholds_below(POISSON_CDF), ks)
    np.testing.assert_array_equal(thresholds_below(np.nextafter(POISSON_CDF, 1)), ks + 1)


def test_distinct_edges_ascend_strictly_and_a_subset_of_quantiles_coarsens() -> None:
    """A value met at two quantiles fills a bin and gets the singleton `[v, next)`; −0.0 reads
    as 0.0; the edges of every fourth quantile are a subset of the edges of all of them."""
    found = _distinct_edges(np.array([-0.0, 0.0, 1.0, 2.0, 2.0, 2.0, 3.0]))
    expected = [0.0, np.nextafter(0.0, 1), 1.0, 2.0, np.nextafter(2.0, 3), 3.0]
    np.testing.assert_array_equal(found, expected)
    assert not np.signbit(found[0])
    quantiles = np.sort(np.random.default_rng(0).integers(0, 60, 199).astype(float))
    fine, coarse = _distinct_edges(quantiles), _distinct_edges(quantiles[3::4])
    assert (np.diff(fine) > 0).all() and set(coarse) <= set(fine)


def test_stratum_labels_are_the_levels_cap_levels_gives_the_rows() -> None:
    """From one row count per distinct value, each value gets the level EDA's `cap_levels`
    gives its rows: the most frequent kept (ties by label), the rest `__other__`, null and NaN
    `null`, a real level named like a reserved bin or blank quoted, a number or boolean as its
    text."""
    for values in (
        pd.Series(["b", "a", "null", "c", None, "d", "__other__", " "], dtype=object),
        pd.Series([3.0, 1.0, np.nan, 2.0, 7.0]),
        pd.Series([True, False, None], dtype=object),
    ):
        rows = pd.Series(np.resize([5, 5, 9, 1, 3, 2], len(values)), index=values.index)
        expanded = values.repeat(rows)  # the rows themselves, on their value's index
        capped = cap_levels(expanded.reset_index(drop=True), 3).astype(str)
        expected = capped.groupby(expanded.index.to_numpy()).first()
        pd.testing.assert_series_equal(stratum_labels(values, rows, 3), expected)


def test_the_two_quantile_passes_are_the_grid_and_the_strata_whole_score_bins() -> None:
    """Spark's two passes give back each task's grid: binary's body ends at the tail's start and
    its tail's shares of the top 1% land on the grid's 189 top cuts; regression takes one pass.
    Every `STRATA_STEP`-th edge leaves the strata whole score bins: binary 95, regression 50."""
    for task, strata_bins in (("binary", 95), ("regression", 50)):
        cuts = bin_quantiles(task)
        body, tail = quantile_passes(task)
        start = body[-1] if tail.size else 1.0
        np.testing.assert_allclose(np.concatenate([body, start + tail * (1 - start)]), cuts)
        assert (cuts.size + 1) % STRATA_STEP[task] == 0
        assert (cuts.size + 1) // STRATA_STEP[task] == strata_bins
    assert quantile_passes("binary")[0][-1] == 0.99 and quantile_passes("binary")[1].size == 189
    assert quantile_passes("regression")[1].size == 0


def test_a_kept_level_that_matched_no_row_in_spark_is_refused() -> None:
    """The `__other__` rows at replicate 0 must be the rows of the levels that were not kept;
    other replicates' weights do not count."""
    cells = pd.DataFrame({"replicate": [0, 0, 0, 1], "channel": ["a", OTHER, OTHER, OTHER],
                          "rows": [5.0, 3.0, 4.0, 9.0]})  # fmt: skip
    _check_other(cells, {"channel": 7})
    with pytest.raises(ValueError, match="puts 7 rows in __other__, but its levels"):
        _check_other(cells, {"channel": 2})


def test_the_split_cells_pooled_over_split_are_the_unsplit_cells() -> None:
    """`pool_cells` over `split` gives the cells `cells_from_rows` builds without it, with and
    without a loss (whose null sums stay null); a cell key is no `by` column to pool."""
    rows = random_rows(seed=4)
    for loss in ("log_loss", None):
        pooled = pool_cells(cells_from_rows(rows, ["split"], loss), "split")
        pd.testing.assert_frame_equal(pooled, cells_from_rows(rows, [], loss), rtol=1e-12)
    with pytest.raises(ValueError, match="'part' is no `by` column"):
        pool_cells(cells_from_rows(rows, ["split"], None), "part")


def test_the_scorer_loss_follows_the_metric_then_the_objective(
    in_memory: UseCaseConfig, variant: Callable[..., UseCaseConfig]
) -> None:
    """Binary's loss is the log loss; regression's is the decision's deviance when it names
    one, else the run's objective's (not the config's), else none (squared error)."""
    regression = variant(**REGRESSION)
    assert scorer_loss(in_memory, in_memory.training.objective) == "log_loss"
    assert scorer_loss(regression, regression.training.objective) is None
    assert scorer_loss(regression, "poisson") == "poisson_deviance"
    tweedie = with_training(regression, objective="tweedie")
    assert scorer_loss(tweedie, "tweedie") == "tweedie_deviance"
    data = tweedie.model_dump()
    data["decision"]["metric"] = "poisson_deviance"
    assert scorer_loss(UseCaseConfig.model_validate(data), "tweedie") == "poisson_deviance"


@pytest.mark.parametrize("family", list(FAMILIES))
@pytest.mark.parametrize("task", ["binary", "regression"])
def test_the_families_predict_the_same_margins_at_any_thread_count(family: str, task: str) -> None:
    """Scoring inside Spark caps each library's threads at the task's CPUs: the margins are
    the same bits at the library's default and at 1, 2 and 4 threads, and an XGBoost booster's
    own thread setting is back as it was after each call."""
    booster, content = trained(family, task)
    encoded, _ = encode_frame(raw_frame(300, seed=1), content["encoder"])
    predict = FAMILIES[family].predict
    default = predict(booster, encoded)
    setting = booster_threads(booster)
    for threads in (1, 2, 4):
        np.testing.assert_array_equal(predict(booster, encoded, threads), default)
        assert booster_threads(booster) == setting


def test_the_thread_count_is_read_inside_a_spark_task_only() -> None:
    """Outside a Spark task there is no task's CPU count to read: it fails loud."""
    with pytest.raises(RuntimeError, match="outside a Spark task"):
        _task_threads()


# ---- Spark ------------------------------------------------------------------------------------


def test_score_parts_scores_every_row_and_refuses_other_features(
    spark: SparkSession, tmp_path: Path, in_memory: UseCaseConfig
) -> None:
    """One scored row per client, period and part, with the table's columns in order and the
    scores `score_frame` gives; rows with a feature fewer or a column more than the bundle's (a
    baseline column not named is one), a baseline named like a feature, or a bundle of another
    task, are refused before Spark runs. `write_scores` stages the table beside the stage's
    folder and refuses to run while an earlier staging folder is left."""
    folder, other = str(tmp_path / "binary"), str(tmp_path / "regression")
    write_bundle(folder, "lgbm", *trained("lgbm", "binary"), IDENTITY)
    write_bundle(other, "lgbm", *trained("lgbm", "regression"), IDENTITY)
    frame = raw_frame(400, seed=3)
    tested = frame.iloc[:200].assign(period=WINDOW[0], part="test", split="test")
    validation = frame.assign(period=VALIDATION, part="validation")
    validation["split"] = np.where(validation.index < 200, "test", "train")
    table = pd.concat([tested, validation], ignore_index=True)
    table = table.assign(target=np.arange(len(table)) % 2, segment="mass", baseline_rate=0.1)
    table["onboarding_channel"] = "online"
    rows = spark.createDataFrame(table).repartition(3)
    baselines = ["baseline_rate"]
    scores = score_parts(folder, rows, in_memory, baselines)
    strata = ["segment", "onboarding_channel"]
    assert scores.columns == ["unit_id", "period", "part", "split", "target", *OUTPUT_COLUMNS,
                              *strata, "baseline_rate"]  # fmt: skip
    keys = ["unit_id", "part"]
    found = scores.toPandas().sort_values(keys, ignore_index=True)
    expected = table.sort_values(keys, ignore_index=True)
    scored = score_frame(load_bundle(folder), expected)
    pd.testing.assert_frame_equal(found[OUTPUT_COLUMNS], scored, check_exact=True)
    assert found[keys].equals(expected[keys])
    with pytest.raises(ValueError, match=r"the rows lack \['age'\] and hold \[\]"):
        score_parts(folder, rows.drop("age"), in_memory, baselines)
    with pytest.raises(ValueError, match=r"the rows lack \[\] and hold \['cc_flag'\]"):
        score_parts(folder, rows.withColumn("cc_flag", F.lit(1)), in_memory, baselines)
    unnamed = rows.withColumn("baseline_score", F.lit(0.5))
    with pytest.raises(ValueError, match=r"the rows lack \[\] and hold \['baseline_score'\]"):
        score_parts(folder, unnamed, in_memory, baselines)
    with pytest.raises(ValueError, match=r"the baselines \['age'\] are named like a feature"):
        score_parts(folder, rows, in_memory, ["age"])
    with pytest.raises(ValueError, match="is a regression model; the config's task is binary"):
        score_parts(other, rows, in_memory, baselines)
    staged = write_scores(scores, str(tmp_path / "evaluation"))
    assert Path(staged).name == f"evaluation.scores-{os.getpid()}"
    back = spark.read.parquet(staged).toPandas().sort_values(keys, ignore_index=True)
    pd.testing.assert_frame_equal(back[found.columns], found, check_exact=True)
    with pytest.raises(ValueError, match="left from an earlier Evaluation that did not finish"):
        write_scores(scores, str(tmp_path / "evaluation"))


def test_client_weights_are_the_clients_repeat_and_are_poisson_one(spark: SparkSession) -> None:
    """A client's rows share every weight, a second run draws the same, another salt others;
    over 4,000 clients and 50 replicates the weights' mean and variance are 1 and a weight is 0
    with probability e⁻¹. The weights of replicate r do not depend on the replicate count."""
    clients = spark.range(4000).select(F.col("id").cast("string").alias("unit_id"))
    rows = clients.unionByName(clients)  # each client at two periods
    first = drawn_weights(rows, 50, WEIGHT_SALT)
    np.testing.assert_array_equal(first[0::2], first[1::2])
    np.testing.assert_array_equal(drawn_weights(rows, 50, WEIGHT_SALT), first)
    values = first[0::2]
    assert abs(values.mean() - 1) < 0.03 and abs(values.var() - 1) < 0.05
    assert abs((values == 0).mean() - np.exp(-1)) < 0.01
    assert (drawn_weights(clients, 50, "another_salt") != values).mean() > 0.5
    np.testing.assert_array_equal(drawn_weights(clients, 5, WEIGHT_SALT), values[:, :5])
    with pytest.raises(ValueError, match="replicates must be at least 1"):
        client_weights(F.col("unit_id"), 0, WEIGHT_SALT)


def test_the_poisson_weight_inverts_the_cdf_on_literal_uniforms(spark: SparkSession) -> None:
    """In Spark, `_poisson_weight` gives the same k as the thresholds in numpy at 0, at every
    threshold and just above it, and at the largest uniform; `_uniform` lies in [0, 1) and
    averages a half."""
    edges = np.concatenate([POISSON_CDF, np.nextafter(POISSON_CDF, 1)])
    u = np.concatenate([[0.0, 0.5], edges[edges < 1], [TOP_UNIFORM]])
    literal = spark.createDataFrame(pd.DataFrame({"u": u}))
    found = literal.select(_poisson_weight(F.col("u")).alias("k")).toPandas()["k"]
    np.testing.assert_array_equal(found, thresholds_below(u))
    uniform = spark.range(20000).select(_uniform(F.col("id"), F.lit(1), WEIGHT_SALT).alias("u"))
    drawn = uniform.toPandas()["u"]
    assert drawn.between(0, 1, inclusive="left").all() and abs(drawn.mean() - 0.5) < 0.01


@pytest.mark.parametrize(("task", "loss"), LOSS_CASES)
def test_score_cells_equal_their_pandas_mirror_at_replicates_0_and_1(
    spark: SparkSession,
    in_memory: UseCaseConfig,
    regression_cfg: UseCaseConfig,
    task: str,
    loss: str | None,
) -> None:
    """The cells summed in Spark equal `cells_from_rows` on the same rows binned in numpy, at
    replicate 0 (every row once) and 1 (the clients' weights, some 0), unstratified, by split
    and by a stratum (the strata's edges, its 14 levels capped as EDA caps them before the
    aggregate, a regression target in EDA's zero bin or above it, so a level's events count
    right), once per row loss and without one, so the
    Spark losses and the pandas mirror's cannot drift apart; the split cells pooled over split
    are the unsplit ones. The body's edges cut the rows at `quantile_passes`' body, the tail's
    are the top rows' scores, and the strata's are a subset of them, with regression's mass
    point its own bin."""
    cfg = with_replicates(in_memory if task == "binary" else regression_cfg, 20)
    table = scores_table(task)
    scores = spark.createDataFrame(table).repartition(4)
    edges = score_edges(scores, cfg)
    assert set(edges["strata"]) <= set(edges["score"]) and (np.diff(edges["score"]) > 0).all()
    body, _ = quantile_passes(task)
    if task == "binary":  # distinct scores: each body edge cuts its share of the rows
        found = edges["score"][: body.size]
        below = (table["score"].to_numpy()[:, None] < found).mean(axis=0)
        assert np.abs(below - body).max() <= 3 / len(table)  # a rank or two off, at most
        # the tail pass cuts the top 1% (12 rows here) finer than a row: each its own bin
        top = table.loc[table["score"] >= found[-1], "score"].to_numpy()
        assert set(edges["score"][body.size :]) <= {*top, *np.nextafter(top, 2)}
    else:
        assert {1.0, np.nextafter(1.0, 2)} <= set(edges["score"])
    weights = replicate_weights(spark, table, 1)
    assert (weights == 0).any()
    found_by = {}
    for by, cut in (([], "score"), (["split"], "score"), (["onboarding_channel"], "strata")):
        cells = found_by[tuple(by)] = score_cells(scores, cfg, by, edges, loss=loss)
        assert set(cells["replicate"]) == set(range(21))
        target = edges["target"]
        if by == ["onboarding_channel"]:  # max_levels kept, `__other__`, null, a quoted level
            levels = set(cells["onboarding_channel"])
            assert len(levels) == cfg.strata.max_levels + 2 and "'null'" in levels
            if target is not None:  # a regression target: EDA's zero bin and the rest above it
                target = np.array([0.0, np.nextafter(0.0, 1)])
                assert set(cells["target_bin"]) == {1, 2}
                once = cells[cells["replicate"] == 0]
                events = once.loc[once["target_sum"] != 0, "rows"].sum()  # regression_metrics'
                assert events == (table["target"] != 0).sum()
        for replicate, weight in ((0, 1), (1, weights)):
            found = cells[cells["replicate"] == replicate].drop(columns="replicate")
            weighted = table.assign(weight=weight)
            expected = expected_cells(weighted, cfg, by, edges[cut], target, loss)
            pd.testing.assert_frame_equal(
                found.reset_index(drop=True), expected, check_dtype=False, rtol=1e-9
            )
    order = ["replicate", "part", "period", "score_bin", "target_bin"]
    pooled = pool_cells(found_by[("split",)], "split").sort_values(order, ignore_index=True)
    unsplit = found_by[()].sort_values(order, ignore_index=True)
    pd.testing.assert_frame_equal(pooled, unsplit, check_dtype=False, rtol=1e-9)


def test_score_cells_refuse_a_part_without_rows_and_a_bad_request(
    spark: SparkSession, in_memory: UseCaseConfig
) -> None:
    """Scores without a validation row fail loud, as do a binary score outside [0, 1] under
    the log loss, a `by` column the scores lack or that is a cell key, and an unknown loss."""
    cfg = with_replicates(in_memory, 20)
    table = scores_table("binary", clients=200)
    scores = spark.createDataFrame(table)
    edges = score_edges(scores, cfg)
    tested = scores.where(F.col("part") == "test")
    with pytest.raises(ValueError, match="the validation part has no scored row"):
        score_cells(tested, cfg, [], edges, loss="log_loss")
    above = scores.withColumn("score", F.when(F.col("unit_id") == "c0001", 1.5).otherwise(
        F.col("score")))  # fmt: skip
    with pytest.raises(ValueError, match="the log_loss of `score` is undefined"):
        score_cells(above, cfg, [], edges, loss="log_loss")
    with pytest.raises(ValueError, match=r"the scores lack the columns \['nope'\]"):
        score_cells(scores, cfg, ["nope"], edges, loss="log_loss")
    with pytest.raises(ValueError, match=r"by names the cell keys \['period'\]"):
        score_cells(scores, cfg, ["period"], edges, loss="log_loss")
    with pytest.raises(ValueError, match="unknown loss 'rmse'"):
        score_cells(scores, cfg, [], edges, loss="rmse")
