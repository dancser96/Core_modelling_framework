"""The client folds of the train split (§4.4, §4.11; D-106).

Hand-made train frames of many clients over three periods check that every client sits in one
fold of each dealing, that a binary task's converting clients are dealt evenly, that two
dealings differ while a rerun repeats, that the folds are drawn apart from the client split,
that a binary use case with fewer converting clients than folds fails loud, and that a
regression gets the plain hash folds without positive counts. The counts check runs without
Spark on hand-made tables.
"""

from datetime import date

import pandas as pd
import pytest
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from core_modelling.config import UseCaseConfig
from core_modelling.dataset.folds import (
    FOLD_COUNT_COLUMNS,
    assign_folds,
    check_folds,
    fold_columns,
    fold_counts,
)
from core_modelling.dataset.split import assign_split

PERIODS = [date(2025, 3, 31), date(2025, 4, 30), date(2025, 5, 31)]


def _train(spark: SparkSession, clients: int, converting: int) -> DataFrame:
    """`clients` train clients over three periods, the first `converting` of them with a
    positive row in the second period: `unit_id, period, x, target, split`."""
    rows = [
        (f"c{c:04d}", period, float(c), int(c < converting and i == 1), "train")
        for c in range(clients)
        for i, period in enumerate(PERIODS)
    ]
    return spark.createDataFrame(
        rows, "unit_id string, period date, x double, target int, split string"
    )


def _with_training(cfg: UseCaseConfig, **fields: object) -> UseCaseConfig:
    """`cfg` with the `training` fields changed (not re-validated)."""
    return cfg.model_copy(update={"training": cfg.training.model_copy(update=fields)})


@pytest.fixture(scope="module")
def twice(cc_config: UseCaseConfig) -> UseCaseConfig:
    """The card config with five folds dealt twice."""
    return _with_training(cc_config, folds=5, fold_repeats=2)


def test_converting_clients_are_dealt_evenly_and_a_client_sits_in_one_fold(
    spark: SparkSession, twice: UseCaseConfig
) -> None:
    """Two dealings over 300 clients, 23 converting: the fold columns follow the train columns;
    in each dealing every row of a client has one fold in 0 … 4 and the folds' converting
    clients differ by at most one; the counts agree with the rows and pass the check."""
    train = _train(spark, 300, 23)
    folded = assign_folds(train, twice)
    assert folded.columns == [*train.columns, "cv_fold", "cv_fold_2"]
    rows = folded.toPandas()
    converting = rows.loc[rows["target"] == 1, "unit_id"].unique()
    for name in ("cv_fold", "cv_fold_2"):
        assert (rows.groupby("unit_id")[name].nunique() == 1).all()
        assert set(rows[name]) == set(range(5))
        dealt = rows[rows["unit_id"].isin(converting)].groupby(name)["unit_id"].nunique()
        assert len(dealt) == 5 and dealt.max() - dealt.min() <= 1
    counts = fold_counts(folded, twice)
    assert counts.columns.tolist() == FOLD_COUNT_COLUMNS and len(counts) == 10
    for _, dealing in counts.groupby("dealing"):
        assert dealing["rows"].sum() == 900 and dealing["clients"].sum() == 300
        assert dealing["converting_clients"].sum() == 23 and dealing["positive_rows"].sum() == 23
    check_folds(counts)


def test_two_dealings_differ_a_rerun_repeats_and_the_seed_moves_them(
    spark: SparkSession, twice: UseCaseConfig
) -> None:
    """The two dealings give some client different folds; the same config gives the same folds
    again; another `training.seed` gives other folds."""
    train = _train(spark, 300, 23)
    first = assign_folds(train, twice).toPandas().sort_values(["unit_id", "period"])
    again = assign_folds(train, twice).toPandas().sort_values(["unit_id", "period"])
    pd.testing.assert_frame_equal(first, again)
    assert (first["cv_fold"] != first["cv_fold_2"]).any()
    reseeded = _with_training(twice, seed=7)
    other = assign_folds(train, reseeded).toPandas().sort_values(["unit_id", "period"])
    assert (first["cv_fold"].to_numpy() != other["cv_fold"].to_numpy()).any()


def test_folds_are_drawn_apart_from_the_client_split(
    spark: SparkSession, cc_config: UseCaseConfig
) -> None:
    """With the split's seed equal to the folds' (both 42), every fold of 2,000 clients holds
    near the split's test share: the folds' own salt keeps the draws apart, where the same salt
    would put every test client in the lowest folds."""
    cfg = _with_training(cc_config, folds=5, fold_repeats=1, seed=cc_config.data.split.seed)
    clients = assign_split(_train(spark, 2_000, 0), cfg)
    rows = assign_folds(clients, cfg).toPandas()
    share = (rows["split"] == "test").groupby(rows["cv_fold"]).mean()
    expected = cc_config.data.split.test_share
    assert len(share) == 5 and share.between(expected - 0.1, expected + 0.1).all()


def test_fewer_converting_clients_than_folds_fail_loud(
    spark: SparkSession, twice: UseCaseConfig
) -> None:
    """Three converting clients for five folds: the counts name the folds without a positive
    row and the check fails, naming them and the converting clients."""
    folded = assign_folds(_train(spark, 300, 3), twice)
    counts = fold_counts(folded, twice)
    assert (counts.groupby("dealing")["positive_rows"].apply(lambda s: (s == 0).sum()) == 2).all()
    message = r"have no positive row: the train split's 3 converting clients cannot give each of"
    with pytest.raises(ValueError, match=message):
        check_folds(counts)


def test_regression_gets_plain_hash_folds_and_no_positive_counts(
    spark: SparkSession, regression_cfg: UseCaseConfig
) -> None:
    """A regression target: two dealings of plain hash folds, one fold per client, every fold
    filled; the counts' positive columns null; the check passes."""
    cfg = _with_training(regression_cfg, folds=5, fold_repeats=2)
    train = _train(spark, 300, 0).withColumn("target", (1.5 * F.col("x")).cast("double"))
    folded = assign_folds(train, cfg)
    rows = folded.toPandas()
    for name in fold_columns(2):
        assert (rows.groupby("unit_id")[name].nunique() == 1).all()
        assert set(rows[name]) == set(range(5))
    counts = fold_counts(folded, cfg)
    assert counts["converting_clients"].isna().all() and counts["positive_rows"].isna().all()
    assert (counts.groupby("dealing")["clients"].sum() == 300).all()
    check_folds(counts)


def _counts(positives: list[int | None], rows: list[int] | None = None) -> pd.DataFrame:
    """A one-dealing counts table with the positive rows (and converting clients) given per
    fold; `rows` per fold, ten each by default; None positives make it a regression's."""
    rows = rows or [10] * len(positives)
    return pd.DataFrame(
        {
            "dealing": 1,
            "fold": range(len(positives)),
            "rows": rows,
            "clients": [r // 2 for r in rows],
            "converting_clients": positives,
            "positive_rows": positives,
        }
    )[FOLD_COUNT_COLUMNS]


def test_fold_columns_name_the_dealings() -> None:
    """`cv_fold` for the first dealing, `cv_fold_<r>` for the others."""
    assert fold_columns(1) == ["cv_fold"]
    assert fold_columns(3) == ["cv_fold", "cv_fold_2", "cv_fold_3"]


def test_check_folds_passes_folds_with_positives_and_a_regression() -> None:
    """Every fold with a positive row passes; a regression's null positive counts pass."""
    check_folds(_counts([2, 1, 1, 2, 1]))
    check_folds(_counts([None] * 5))


def test_check_folds_names_each_fold_without_a_positive_or_a_row() -> None:
    """A binary fold without a positive row fails naming every such (dealing, fold) and the
    converting clients, with no advice to change the folds; a fold without a row fails for a
    regression too, naming the clients and the folds."""
    with pytest.raises(ValueError, match=r"\(dealing, fold\) \[\(1, 3\), \(1, 4\)\] have no") as e:
        check_folds(_counts([1, 1, 1, 0, 0]))
    assert "3 converting clients cannot give each of the 5 folds one" in str(e.value)
    assert "fewer" not in str(e.value)
    message = r"\[\(1, 2\)\] hold no train row: the train split has 12 clients for 3 folds"
    with pytest.raises(ValueError, match=message):
        check_folds(_counts([None] * 3, rows=[12, 12, 0]))
