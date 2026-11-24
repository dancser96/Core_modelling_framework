"""The client folds of the train split, and their counts (§4.4, §4.11; D-106).

Training cross-validates on folds the dataset deals, so no fold mixes a client's rows and the
search, the selection and the calibration all read the same folds. `assign_folds` deals the
train clients to K folds (`training.folds`) in `cv_fold`, and `training.fold_repeats` adds the
further dealings `cv_fold_2`, …. Every draw is the client split's salted hash (`split.py`) of
the client id under the salt `fold_<dealing>` and `training.seed`: a salt of its own, so the
folds are independent of the train/test cut (salt `split`) and of the sampling (`sample`), two
dealings differ, and a rerun repeats. For a binary task the converting clients (a positive
target row in the train split) are put in the order of that draw and dealt to the folds in turn,
so the folds' counts of them differ by at most one; every other client, and every client of a
regression, takes the plain hash fold, the draw cut into K. Dealing in turn needs one global
order, which is cheap for the few converting clients and would be a single-partition sort for
millions of others. Train labels arrange train folds only: the frame passed in holds train
rows alone. `fold_counts` counts each dealing's folds and `check_folds` fails loud on a fold
without a train row, for a binary task without a positive row, and for either task on a fold
whose targets take one value: no metric can judge a trial there.
"""

import pandas as pd
from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

from core_modelling.config import UseCaseConfig
from core_modelling.dataset.split import hash_uniform
from core_modelling.tasks import TASK_SPECS

FOLD_COUNT_COLUMNS = ["dealing", "fold", "rows", "clients", "converting_clients", "positive_rows",
                      "target_min", "target_max"]  # fmt: skip


def fold_columns(repeats: int) -> list[str]:
    """The dealings' fold columns: `cv_fold`, then `cv_fold_2` … `cv_fold_<repeats>`."""
    return ["cv_fold", *[f"cv_fold_{dealing}" for dealing in range(2, repeats + 1)]]


def _fold_draw(dealing: int, seed: int) -> Column:
    """The client's draw in [0, 1) for one dealing, under the salt `fold_<dealing>`."""
    return hash_uniform([F.col("unit_id")], f"fold_{dealing}", seed)


def assign_folds(train: DataFrame, cfg: UseCaseConfig) -> DataFrame:
    """The train split's rows (one per client and period, with `unit_id` and `target`), lazily,
    with one int column per dealing (`fold_columns`), 0 … K−1, the same on every row of a
    client: a binary task's converting clients dealt in turn, every other client's plain hash
    fold."""
    folds, seed = cfg.training.folds, cfg.training.seed
    columns = fold_columns(cfg.training.fold_repeats)
    plain = {
        name: F.floor(_fold_draw(dealing, seed) * folds).cast("int")
        for dealing, name in enumerate(columns, start=1)
    }
    if not TASK_SPECS[cfg.task]["balanced_folds"]:
        return train.withColumns(plain)
    dealt = train.join(_dealt_folds(train, columns, folds, seed), "unit_id", "left")
    return dealt.withColumns({name: F.coalesce(F.col(name), plain[name]) for name in columns})


def _dealt_folds(train: DataFrame, columns: list[str], folds: int, seed: int) -> DataFrame:
    """One row per converting client of `train` (a client with a positive target row):
    `unit_id` and each dealing's fold, the clients in the order of that dealing's draw (the id
    breaks a tie) dealt to the folds in turn."""
    converting = train.where(F.col("target") == 1).select("unit_id").distinct()
    for dealing, name in enumerate(columns, start=1):
        # one partition on purpose (the converting clients are few); the constant key says so,
        # where a window without one would warn at every action
        order = Window.partitionBy(F.lit(0)).orderBy(_fold_draw(dealing, seed), "unit_id")
        position = F.row_number().over(order) - 1
        converting = converting.withColumn(name, F.pmod(position, F.lit(folds)).cast("int"))
    return converting


def fold_counts(train: DataFrame, cfg: UseCaseConfig) -> pd.DataFrame:
    """One row per dealing (1 … R) and fold (0 … K−1), every fold listed, an empty one with zero
    counts: `FOLD_COUNT_COLUMNS`, the rows, the clients, the converting clients and the positive
    rows (null for a regression), and the fold's smallest and largest target, from one aggregate
    of the train rows with their fold columns."""
    folds, repeats = cfg.training.folds, cfg.training.fold_repeats
    pairs = [
        F.struct(F.lit(dealing).alias("dealing"), F.col(name).alias("fold"))
        for dealing, name in enumerate(fold_columns(repeats), start=1)
    ]
    positive = F.col("target") == 1
    counts = [
        F.count(F.lit(1)).alias("rows"),
        F.countDistinct("unit_id").alias("clients"),
        F.min("target").cast("double").alias("target_min"),
        F.max("target").cast("double").alias("target_max"),
    ]
    balanced = TASK_SPECS[cfg.task]["balanced_folds"]
    if balanced:
        counts += [
            F.countDistinct(F.when(positive, F.col("unit_id"))).alias("converting_clients"),
            F.count(F.when(positive, True)).alias("positive_rows"),
        ]
    exploded = train.select("unit_id", "target", F.explode(F.array(*pairs)).alias("pair"))
    counted = exploded.select("unit_id", "target", "pair.*").groupBy("dealing", "fold").agg(*counts)
    counted = counted.toPandas().astype({"dealing": "int64", "fold": "int64"})
    grid = pd.MultiIndex.from_product(
        [range(1, repeats + 1), range(folds)], names=["dealing", "fold"]
    )
    table = counted.set_index(["dealing", "fold"]).reindex(grid, fill_value=0).reset_index()
    if not balanced:
        table["converting_clients"] = table["positive_rows"] = None
    return table[FOLD_COUNT_COLUMNS]


def check_folds(counts: pd.DataFrame) -> None:
    """Fail loud, naming each (dealing, fold), on a fold without a train row, for a binary task
    (the positive counts not null) on a fold without a positive row, and on a fold whose targets
    take one value (`target_min` equals `target_max`): such a fold cannot judge a trial, and a
    regression's concordance or r2 is not defined on it."""
    first = counts[counts["dealing"] == 1]  # a client sits in one fold of each dealing
    empty = counts[counts["rows"] == 0]
    if len(empty):
        raise ValueError(
            f"the folds (dealing, fold) {_pairs(empty)} hold no train row: the train split has "
            f"{int(first['clients'].sum())} clients for {len(first)} folds"
        )
    without = counts[counts["positive_rows"] == 0]  # a regression's null counts never equal 0
    if len(without):
        raise ValueError(
            f"the folds (dealing, fold) {_pairs(without)} have no positive row: the train "
            f"split's {int(first['converting_clients'].sum())} converting clients cannot give "
            f"each of the {len(first)} folds one, and a fold without a positive event cannot "
            "judge a trial"
        )
    constant = counts[counts["target_min"] == counts["target_max"]]
    if len(constant):
        values = sorted(set(constant["target_min"].astype(float)))
        raise ValueError(
            f"the folds (dealing, fold) {_pairs(constant)} hold one target value ({values}): "
            "no metric can tell a better trial from a worse one there; the target takes too "
            "few values on the train split for the folds"
        )


def _pairs(counts: pd.DataFrame) -> list[tuple[int, int]]:
    """The (dealing, fold) pairs of the rows of a counts table."""
    return list(zip(counts["dealing"].astype(int), counts["fold"].astype(int), strict=True))
