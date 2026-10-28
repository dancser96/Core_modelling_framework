"""The client split and train-only sampling (§4.11, §4.12; D-030, D-049, D-117).

`assign_split` puts a client's every row in `test` or `train` by a seeded hash of its id, so the
assignment is stable across months, reruns and machines; it applies from Training on, after
Feature Checks (D-030). `sample_train` thins the train split only, and only when the config
declares it: `negative_downsampling` keeps every positive row and a hashed fraction of the
negatives (rare binary targets), `client_sample` keeps a hashed share of the clients (common
targets, regression), one fraction for the whole window (D-117). The record carries the true
(unsampled train) and the sampled rate for the prior-shift offset (D-049). The sampling hash is
salted apart from the split's, so equal seeds never make the sample a slice of the split (T20).
"""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from core_modelling.config import UseCaseConfig

SPLIT_BUCKETS = 1_000
SAMPLE_BUCKETS = 1_000_000


def _bucket(columns: list[Column], salt: str, seed: int, buckets: int) -> Column:
    """`pmod(xxhash64(salt, columns…, seed), buckets)`: a stable bucket in 0 … buckets − 1."""
    return F.pmod(F.xxhash64(F.lit(salt), *columns, F.lit(seed)), F.lit(buckets))


def assign_split(panel: DataFrame, cfg: UseCaseConfig) -> DataFrame:
    """`split` = `test` for the clients hashed below `data.split.test_share`, else `train`, every
    month of a client alike."""
    split = cfg.data.split
    bucket = _bucket([F.col("unit_id")], "split", split.seed, SPLIT_BUCKETS)
    in_test = bucket < split.test_share * SPLIT_BUCKETS
    return panel.withColumn("split", F.when(in_test, "test").otherwise("train"))


def sample_train(train: DataFrame, cfg: UseCaseConfig) -> tuple[DataFrame, dict]:
    """The train split thinned as `training.sampling` declares, with the record: the method and
    its parameter, the rows and the target's mean (binary: the positive rate) before and after;
    the identity, recorded, without sampling."""
    sampling = cfg.training.sampling
    if sampling is None:
        return train, {"step": "sampling", "method": None}
    unit = F.col("unit_id")
    if sampling.method == "negative_downsampling":
        bucket = _bucket([unit, F.col("month")], "sample", sampling.seed, SAMPLE_BUCKETS)
        keep = (F.col("target") == 1) | (bucket < sampling.keep_fraction * SAMPLE_BUCKETS)
        parameter = {"keep_fraction": sampling.keep_fraction}
    else:
        bucket = _bucket([unit], "sample", sampling.seed, SAMPLE_BUCKETS)
        keep = bucket < sampling.share * SAMPLE_BUCKETS
        parameter = {"share": sampling.share}
    sampled = train.where(keep)
    rows_before, true_rate = _rows_and_rate(train)
    rows_after, sampled_rate = _rows_and_rate(sampled)
    if not rows_after:
        raise ValueError(
            f"the train split is empty after {sampling.method} {parameter} ({rows_before:,} "
            "rows before); raise the parameter"
        )
    record = {
        "step": "sampling",
        "method": sampling.method,
        **parameter,
        "seed": sampling.seed,
        "rows_before": rows_before,
        "rows_after": rows_after,
        "true_rate": true_rate,
        "sampled_rate": sampled_rate,
    }
    print(f"sampling {sampling.method} {parameter}: {rows_before:,} → {rows_after:,} train rows; "
          f"target mean {true_rate:.4f} → {sampled_rate:.4f}")  # fmt: skip
    return sampled, record


def _rows_and_rate(frame: DataFrame) -> tuple[int, float]:
    """The frame's rows and its target's mean, from one aggregate."""
    row = frame.agg(F.count(F.lit(1)), F.avg(F.col("target").cast("double"))).collect()[0]
    return row[0], row[1]
