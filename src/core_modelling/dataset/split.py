"""The client split and train-only sampling (§4.11, §4.12; D-030, D-049, D-117).

Both draw with a hash instead of a random number. `_hash_uniform` turns a row's key columns, a
salt and the seed into a number in [0, 1) that is the same on every machine, rerun and
partition, so a client's every period lands on the same side of the split and a sample can be
rebuilt exactly. `assign_split` puts a client in `test` when its number is below
`data.split.test_share`; it applies from Training on, after Feature Checks (D-030).
`sample_train` thins the train split only, and only when the config declares it:
`negative_downsampling` keeps every positive row and the negatives whose number is below
`keep_fraction` (rare binary targets), `client_sample` keeps the clients whose number is below
`share`, with all their periods (common targets, regression); one fraction for the whole window
(D-117). The record carries the true (unsampled train) and the sampled rate for the prior-shift
offset (D-049). The salt keeps the sampling draw independent of the split's: with the same
function of the same key, every train client would sit above `test_share` and a sample would be
a slice of the split, not the share asked (T20).
"""

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from core_modelling.config import UseCaseConfig

RESOLUTION = 1_000_000  # the hash is folded into this many equal buckets, then scaled to [0, 1)


def _hash_uniform(columns: list[Column], salt: str, seed: int) -> Column:
    """A number in [0, 1), a fixed function of the columns, the salt and the seed, spread evenly:
    `xxhash64` of them all, folded into `RESOLUTION` buckets and scaled."""
    bucket = F.pmod(F.xxhash64(F.lit(salt), *columns, F.lit(seed)), F.lit(RESOLUTION))
    return bucket / RESOLUTION


def assign_split(panel: DataFrame, cfg: UseCaseConfig) -> DataFrame:
    """`split` = `test` for the clients whose draw is below `data.split.test_share`, else
    `train`, every period of a client alike."""
    split = cfg.data.split
    draw = _hash_uniform([F.col("unit_id")], "split", split.seed)
    return panel.withColumn("split", F.when(draw < split.test_share, "test").otherwise("train"))


def sample_train(train: DataFrame, cfg: UseCaseConfig) -> tuple[DataFrame, dict]:
    """The train split thinned as `training.sampling` declares, with the record: the method and
    its parameter, the rows and the target's mean (binary: the positive rate) before and after;
    the identity, recorded, without sampling."""
    sampling = cfg.training.sampling
    if sampling is None:
        return train, {"step": "sampling", "method": None}
    unit = F.col("unit_id")
    if sampling.method == "negative_downsampling":
        draw = _hash_uniform([unit, F.col("period")], "sample", sampling.seed)  # per row
        keep = (F.col("target") == 1) | (draw < sampling.keep_fraction)
        parameter = {"keep_fraction": sampling.keep_fraction}
    else:
        draw = _hash_uniform([unit], "sample", sampling.seed)  # per client
        keep = draw < sampling.share
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
