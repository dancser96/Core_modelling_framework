"""The client split and train-only sampling (§4.11, §4.12; D-117).

A hand-made frame of many clients over three periods checks that the split is by client, stable
across periods and reruns and near the asked share; that `negative_downsampling` keeps every
positive row and the asked fraction of the negatives; that `client_sample` keeps whole clients
and the asked share of them even when its seed equals the split's (T20); and that no sampling is
the identity, recorded.
"""

from collections.abc import Callable
from datetime import date

import pytest
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from core_modelling.config import UseCaseConfig
from core_modelling.dataset.split import _hash_uniform, assign_split, sample_train

PERIODS = [date(2025, 3, 31), date(2025, 4, 30), date(2025, 5, 31)]
UNITS = 2_000


@pytest.fixture(scope="module")
def frame(spark: SparkSession) -> DataFrame:
    """2,000 units over three periods, every 20th row positive."""
    rows = [(u, p, int((u + i) % 20 == 0)) for u in range(UNITS) for i, p in enumerate(PERIODS)]
    return spark.createDataFrame(rows, "unit_id int, period date, target int")


def test_split_is_by_client_stable_and_near_the_share(
    frame: DataFrame, variant: Callable[..., UseCaseConfig], cc_config: UseCaseConfig
) -> None:
    """No client in both splits, the same assignment every period and every run, about
    `test_share` of the clients in test; another seed gives another assignment."""
    split = (
        assign_split(frame, cc_config)
        .groupBy("unit_id")
        .agg(F.countDistinct("split").alias("splits"), F.first("split").alias("split"))
    )
    per_unit = split.collect()
    assert all(row.splits == 1 for row in per_unit)
    test_share = sum(row.split == "test" for row in per_unit) / UNITS
    assert test_share == pytest.approx(cc_config.data.split.test_share, abs=0.03)
    again = {r.unit_id: r.split for r in assign_split(frame, cc_config).collect()}
    assert {r.unit_id: r.split for r in per_unit} == again
    other = variant(data={"split": {"seed": 7}})
    reseeded = {r.unit_id: r.split for r in assign_split(frame, other).collect()}
    assert reseeded != again


def test_negative_downsampling_keeps_positives_and_a_fraction_of_negatives(
    frame: DataFrame, variant: Callable[..., UseCaseConfig]
) -> None:
    """Every positive row stays (the draw is on `unit_id, period`), about `keep_fraction` of the
    negatives stay, and the record carries the rows and the rate before and after."""
    cfg = variant(training={"sampling": {"method": "negative_downsampling", "keep_fraction": 0.2}})
    train = assign_split(frame, cfg).where("split = 'train'")
    sampled, record = sample_train(train, cfg)
    positives = train.where("target = 1").count()
    negatives = train.count() - positives
    assert sampled.where("target = 1").count() == positives
    kept = (sampled.count() - positives) / negatives
    assert kept == pytest.approx(0.2, abs=0.03)
    assert record["method"] == "negative_downsampling" and record["keep_fraction"] == 0.2
    assert record["rows_before"] == train.count() and record["rows_after"] == sampled.count()
    assert record["true_rate"] == pytest.approx(0.05, abs=0.01)
    assert record["sampled_rate"] == pytest.approx(positives / sampled.count())


def test_client_sample_keeps_whole_clients_whatever_the_split_seed(
    frame: DataFrame, variant: Callable[..., UseCaseConfig]
) -> None:
    """About `share` of the train clients stay with all their periods, with the sampling seed
    equal to the split seed: the two hashes are salted apart (T20)."""
    cfg = variant(training={"sampling": {"method": "client_sample", "share": 0.5, "seed": 42}})
    assert cfg.data.split.seed == 42
    train = assign_split(frame, cfg).where("split = 'train'")
    sampled, record = sample_train(train, cfg)
    periods = sampled.groupBy("unit_id").count().collect()
    assert all(row["count"] == len(PERIODS) for row in periods)
    train_units = train.select("unit_id").distinct().count()
    assert len(periods) / train_units == pytest.approx(0.5, abs=0.04)
    assert record["share"] == 0.5 and record["rows_after"] == len(periods) * len(PERIODS)


def test_no_sampling_is_the_identity(frame: DataFrame, cc_config: UseCaseConfig) -> None:
    """Without `training.sampling` the train split comes back as is, recorded as none."""
    assert cc_config.training.sampling is None
    sampled, record = sample_train(frame, cc_config)
    assert sampled is frame and record == {"step": "sampling", "method": None}


def test_hash_draw_is_pinned_and_matches_the_bucket_test(spark: SparkSession) -> None:
    """One key's draw is pinned (Spark 3.4.3), so a Spark upgrade that changes `xxhash64` or the
    division fails loud; and `draw < share` agrees with the integer bucket test at the boundary
    for every row (the share with up to six decimals is exact)."""
    one = spark.createDataFrame([("12345",)], "unit_id string")
    draw = _hash_uniform([F.col("unit_id")], "split", 42)
    assert one.select(draw).collect()[0][0] == 0.322993
    ids = spark.range(200_000).select(F.col("id").cast("string").alias("unit_id"))
    bucket = F.pmod(F.xxhash64(F.lit("split"), F.col("unit_id"), F.lit(42)), F.lit(1_000_000))
    for share in (0.3, 0.1, 0.05, 0.333333):
        disagree = ids.where((draw < share) != (bucket < round(share * 1_000_000))).count()
        assert disagree == 0, share
