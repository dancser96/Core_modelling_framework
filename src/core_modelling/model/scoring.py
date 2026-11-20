"""Scoring: the one path from raw feature values to `margin`, `score_raw` and `score`.

`score_frame` encodes a pandas frame with the bundle's encoder, predicts the margin through the
family and applies the calibration; Training's self-check (`check_bundle`), Evaluation and
Inference all score through it, and `score_spark` runs the same function inside Spark with
`mapInPandas`. The driver ships the bundle's bytes in the function's closure, never a path
(A28), so an executor needs no access to the folder; each partition refuses a model library
version other than the driver's, builds the bundle once from those bytes, verifying
`model_hash` again, and writes nothing to disk. Arrow stays on and nothing is collected. A
partition predicts on its task's CPUs (`spark.task.cpus`): LightGBM and XGBoost default to
every core of the host, which the executor's other tasks share (measured; CatBoost's default
too, though its scoring measured near one core), and the scores are the same at any count.
"""

from collections.abc import Iterator
from importlib.metadata import version

import numpy as np
import pandas as pd
from pyspark import TaskContext
from pyspark.sql import DataFrame
from pyspark.sql.types import DoubleType, StructField, StructType

from core_modelling.config.identities import short
from core_modelling.model.bundle import (
    OUTPUT_COLUMNS,
    Bundle,
    build_bundle,
    load_bundle,
    read_bundle_files,
)
from core_modelling.model.calibration import apply_calibration
from core_modelling.model.encoder import encode_frame
from core_modelling.model.families import FAMILIES


def score_frame(bundle: Bundle, frame: pd.DataFrame, threads: int | None = None) -> pd.DataFrame:
    """The scores of a frame of raw feature values (any rows holding the bundle's features; a
    missing one fails in `encode_frame`): `OUTPUT_COLUMNS` as float64 on the frame's index. A
    non-finite value fails loud (the `log` link overflows to inf near a margin of 710).
    `threads` caps the model library's threads (None: its default, every core); the scores are
    the same at any count."""
    encoded, _ = encode_frame(frame, bundle.encoder)
    margin = FAMILIES[bundle.family].predict(bundle.booster, encoded, threads)
    score_raw, score = apply_calibration(margin, bundle.calibration, bundle.task)
    columns = {"margin": margin, "score_raw": score_raw, "score": score}
    for name, values in columns.items():
        count = int((~np.isfinite(values)).sum())
        if count:
            raise ValueError(
                f"the bundle {short(bundle.model_hash)} gives {count} of {len(values)} rows a "
                f"non-finite {name}; a score is always a finite number"
            )
    return pd.DataFrame(columns, index=frame.index, columns=OUTPUT_COLUMNS)


def check_bundle(folder: str, sample: pd.DataFrame, expected: pd.DataFrame) -> None:
    """The self-check at save: the bundle reloaded from `folder` must score `sample` (raw
    feature values, about 1,000 train rows) exactly as `expected` (the model in memory's
    `OUTPUT_COLUMNS` on the sample's index). An empty sample, a difference or a non-finite
    expectation fails loud, naming the first such column and the largest difference."""
    if sample.empty:
        raise ValueError(f"{folder}: the self-check got no rows to score; it compares nothing")
    scores = score_frame(load_bundle(folder), sample)
    missing = [column for column in OUTPUT_COLUMNS if column not in expected.columns]
    if missing:
        raise ValueError(f"{folder}: the expected scores lack the columns {missing}")
    if not expected.index.equals(scores.index):
        raise ValueError(
            f"{folder}: the expected scores are not on the sample's index; score the same rows "
            "in the same order"
        )
    for column in OUTPUT_COLUMNS:
        found, wanted = scores[column].to_numpy(), expected[column].to_numpy(dtype=np.float64)
        if not np.isfinite(wanted).all():  # `score_frame` refused any in `found`
            raise ValueError(
                f"{folder}: the expected scores hold a non-finite {column}; a score is always "
                "a finite number"
            )
        if not np.array_equal(found, wanted):
            raise ValueError(
                f"{folder}: the reloaded bundle's {column} differs from the model in memory by "
                f"up to {np.abs(found - wanted).max():.3g}; the bundle does not score as the "
                "trained model did, so it must not be used"
            )


def score_spark(folder: str, rows: DataFrame, keep: list[str]) -> DataFrame:
    """`rows` scored inside Spark, one output row per input row: the `keep` columns with their
    types and `OUTPUT_COLUMNS` as doubles. The driver reads the bundle's files, verifies those
    very bytes by building the bundle once, and ships them with its own versions of the model
    library; each partition refuses other versions, then builds the bundle once."""
    files = read_bundle_files(folder)
    bundle = build_bundle(files, folder)
    _check_spark_columns(folder, rows, keep, bundle.features)
    driver = {library: version(library) for library in bundle.content["library_version"]}
    scores = [StructField(name, DoubleType()) for name in OUTPUT_COLUMNS]
    schema = StructType([rows.schema[name] for name in keep] + scores)

    def score_batches(batches: Iterator[pd.DataFrame]) -> Iterator[pd.DataFrame]:
        """One partition's batches, each as its `keep` columns and scores; the bundle is built
        from the shipped bytes once for the partition (`folder` is only named in messages), and
        the library predicts on the task's own cores."""
        _check_library_versions(driver)
        bundle = build_bundle(files, folder)
        threads = _task_threads()
        for batch in batches:
            yield pd.concat([batch[keep], score_frame(bundle, batch, threads)], axis=1)

    columns = dict.fromkeys([*keep, *bundle.features])
    return rows.select(*columns).mapInPandas(score_batches, schema)


def _task_threads() -> int:
    """The CPUs Spark gives the running task (`spark.task.cpus`, 1 by default): each library
    would otherwise predict on every core of the host while the executor runs a task per core."""
    context = TaskContext.get()
    if context is None:
        raise RuntimeError("score_spark: the partition runs outside a Spark task")
    return context.cpus()


def _check_library_versions(driver: dict[str, str]) -> None:
    """Fail loud when this process's model library differs from the driver's (`driver`: name
    to version): a partition must score with the driver's library, and on an executor a
    warning would go to a log nobody reads."""
    for library, expected in driver.items():
        installed = version(library)
        if installed != expected:
            raise RuntimeError(
                f"score_spark: this executor has {library} {installed}, the driver "
                f"{expected}; install one version on the driver and every executor"
            )


def _check_spark_columns(
    folder: str, rows: DataFrame, keep: list[str], features: list[str]
) -> None:
    """Fail loud before Spark runs when `keep` names a column `rows` lacks, a score column or
    one column twice, or when `rows` lacks a feature of the bundle at `folder`."""
    reserved = [name for name in keep if name in OUTPUT_COLUMNS]
    if reserved:  # first: a score name is refused whether or not the rows hold such a column
        raise ValueError(f"score_spark: keep names {reserved}; the score columns are added")
    absent = [name for name in keep if name not in rows.columns]
    if absent:
        raise ValueError(f"score_spark: keep names {absent}, which the rows lack")
    repeated = sorted({name for name in keep if keep.count(name) > 1})
    if repeated:
        raise ValueError(f"score_spark: keep names {repeated} more than once")
    missing = [name for name in features if name not in rows.columns]
    if missing:
        raise ValueError(
            f"score_spark: the rows lack the features {missing} of the bundle at {folder}"
        )
