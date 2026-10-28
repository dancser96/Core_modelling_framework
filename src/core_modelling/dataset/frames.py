"""Frames: what a stage works on, collected from Spark with the printout (D-030, D-133).

`build_frames` takes the panel (`panel.build_panel`: sources joined, eligibility, the
candidates, the contract checked, the split assigned; or the saved model input of
`model_input.read_model_input` when the config names one) and collects what the stage asks for:
the window frame (every row after the pre-EDA filters, the pre-model tags and `eligible` as
columns, every client, labels included) for EDA and Feature Checks, or train, test and
validation (the eligible rows with a known target, train sampled when declared) for Training and
Evaluation. Before a frame leaves Spark, `collect_frame` prints its rows, columns, the estimated
size and the collect budget, and the callout above the budget; it never stops.
"""

from dataclasses import dataclass

import pandas as pd
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from core_modelling.config import UseCaseConfig
from core_modelling.dataset.model_input import read_model_input
from core_modelling.dataset.panel import build_panel
from core_modelling.dataset.split import sample_train
from core_modelling.environment import EnvironmentConfig

SAMPLE_ROWS = 10_000  # measured for bytes per row before a collect
GB = 1024**3
STAGE_FRAMES = {
    "eda": "window",
    "feature_checks": "window",
    "training": "modelling",
    "evaluation": "modelling",
}


@dataclass
class Frames:
    """What a stage works on: pandas frames (None when the stage didn't ask for them), the log
    (join, eligibility, contract, null-target, sampling and collect entries, in order) and the
    meta (hashes, candidates, tags, lineage, the sampling record, the collect measurements)."""

    window: pd.DataFrame | None
    train: pd.DataFrame | None
    test: pd.DataFrame | None
    validation: pd.DataFrame | None
    log: list[dict]
    meta: dict


def build_frames(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession, stage: str
) -> Frames:
    """The frames `stage` works on (`eda`, `feature_checks`: the window; `training`,
    `evaluation`: train, test, validation), from the model input when the config names one,
    else built in memory with the same logs."""
    if stage not in STAGE_FRAMES:
        raise ValueError(f"unknown stage {stage!r}; the frames serve {sorted(STAGE_FRAMES)}")
    if cfg.data.model_input is None:
        panel, log, meta = build_panel(cfg, entity, env, spark)
    else:
        panel, log, meta = read_model_input(cfg, entity, env, spark)
    frames: dict[str, pd.DataFrame] = {}
    if STAGE_FRAMES[stage] == "window":
        frames["window"], entry = collect_frame(_window(panel, cfg), "window", env)
        log.append(entry)
    else:
        modelling, null_log = _modelling_rows(panel, cfg)
        log.append(null_log)
        train, record = sample_train(_window(modelling, cfg).where("split = 'train'"), cfg)
        log.append(record)
        meta["sampling"] = record
        parts = {
            "train": train,
            "test": _window(modelling, cfg).where("split = 'test'"),
            "validation": modelling.where(F.col("month") == cfg.time.validation_month),
        }
        for name, part in parts.items():
            frames[name], entry = collect_frame(part, name, env)
            log.append(entry)
    meta["collect"] = [entry for entry in log if entry["step"] == "collect"]
    return Frames(
        window=frames.get("window"),
        train=frames.get("train"),
        test=frames.get("test"),
        validation=frames.get("validation"),
        log=log,
        meta=meta,
    )


def _window(panel: DataFrame, cfg: UseCaseConfig) -> DataFrame:
    """The panel's rows in the observation window."""
    window = cfg.time.train_months
    return panel.where(F.col("month").between(window.first, window.last))


def _modelling_rows(panel: DataFrame, cfg: UseCaseConfig) -> tuple[DataFrame, dict]:
    """The eligible rows with a known target, in the window and at the validation month; the
    share of eligible rows dropped for a null target, per month, logged and printed."""
    eligible = panel.where(F.col("eligible") == 1)
    window = cfg.time.train_months
    months = F.col("month").between(window.first, window.last) | (
        F.col("month") == cfg.time.validation_month
    )
    counts = (
        eligible.where(months)
        .groupBy("month")
        .agg((1 - F.count("target") / F.count(F.lit(1))).alias("null_share"))
        .orderBy("month")
        .collect()
    )
    shares = {f"{row.month:%Y-%m}": row.null_share for row in counts}
    print("null targets dropped from the modelling frames, per month: "
          + ", ".join(f"{m} {s:.1%}" for m, s in shares.items()))  # fmt: skip
    return eligible.where(F.col("target").isNotNull()), {"step": "null_target", "share": shares}


def estimate_collect(frame: DataFrame, name: str) -> dict:
    """The frame's exact rows, its bytes per row measured on a sample in pandas and the estimate
    at the conversion peak (twice the frame, D-133); an empty frame fails loud."""
    rows = frame.count()
    if rows == 0:
        raise ValueError(f"the frame {name!r} is empty: no row to collect")
    sample = frame.limit(SAMPLE_ROWS).toPandas()
    bytes_per_row = sample.memory_usage(deep=True).sum() / len(sample)
    estimate = int(2 * rows * bytes_per_row)
    return {"rows": rows, "columns": len(frame.columns), "estimate_bytes": estimate}


def collect_frame(frame: DataFrame, name: str, env: EnvironmentConfig) -> tuple[pd.DataFrame, dict]:
    """The frame collected to pandas after the printout: rows, columns, the estimate and the
    budget; above the budget a callout, and the collect proceeds. The measured size joins the
    entry."""
    estimate = estimate_collect(frame, name)
    budget = int(env.collect_budget_gb * GB)
    print(f"collect {name}: {estimate['rows']:,} rows × {estimate['columns']} columns, "
          f"≈ {estimate['estimate_bytes'] / GB:.2f} GB at the conversion peak "
          f"(budget {env.collect_budget_gb} GB)")  # fmt: skip
    if estimate["estimate_bytes"] > budget:
        print(
            "  above the budget: declare training.sampling (negative_downsampling for a rare "
            "binary target, client_sample for a common target or regression) or raise "
            "collect_budget_gb in the environment file with the Spark settings "
            "(spark.driver.maxResultSize caps the collect, spark.driver.memory holds the frame); "
            "collecting anyway"
        )
    collected = frame.toPandas()
    measured = int(collected.memory_usage(deep=True).sum())
    print(f"  collected {name}: {measured / GB:.2f} GB in pandas")
    entry = {"step": "collect", "frame": name, **estimate, "measured_bytes": measured,
             "budget_bytes": budget}  # fmt: skip
    return collected, entry
