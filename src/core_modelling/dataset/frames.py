"""Frames: what a stage works on, from the prepared panel (D-030, D-133, D-135).

`build_frames` takes the prepared panel (`panel.build_panel` in memory, or the saved model
input prepared for the config by `model_input.read_model_input` when the config names one:
sources joined, the own target as `target`, eligibility, the candidates, the contract checked,
the split assigned) and builds what the stage asks for. For EDA, the **snapshot**: the
`eda.snapshot` period collected whole (every row after the analysis filters, the modelling tags,
`eligible`, `target` and `split`, the supported candidates only), and **`rows`**: the Spark frame
of the eligible rows of the compared periods (`counts.compared_periods`), the label kept in the
window only, never collected: a lazy plan, which the EDA stage persists for its counts passes.
The kinds come from the Spark schema (`detect_kinds`, with the `features.kinds` overrides) and
the unsupported columns are dropped before anything is collected; the D-088 population counts
join the meta, since only the frames hold the panel. For Training and Evaluation: train, test
and validation (the eligible rows with a known target, train sampled when declared), which need
a validation period. Every stage's meta names each candidate's and lineage column's source
(`sources`, from the join entries' `columns`). Before a frame leaves Spark, `collect_frame`
prints its rows, columns and estimated size, and above the collect budget the callout worded
for the frame; it never stops.
"""

from dataclasses import dataclass

import pandas as pd
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType, NumericType, StringType, StructType

from core_modelling.config import UseCaseConfig
from core_modelling.config.schema import snapshot_period
from core_modelling.dataset.counts import compared_periods, population_counts
from core_modelling.dataset.model_input import read_model_input
from core_modelling.dataset.panel import build_panel
from core_modelling.dataset.split import sample_train
from core_modelling.environment import EnvironmentConfig
from core_modelling.periods import Period, label_by_period, period_spec
from core_modelling.sources import KEYS, missing_periods

SAMPLE_ROWS = 10_000  # measured for bytes per row before a collect
GB = 1024**3
STAGE_FRAMES = {"eda": "snapshot", "training": "modelling", "evaluation": "modelling"}
SPARK_SETTINGS = "spark.driver.maxResultSize caps the collect, spark.driver.memory holds the frame"
TRAINING_CALLOUT = (
    "declare training.sampling (negative_downsampling for a rare binary target, client_sample "
    "for a common target or regression) or raise collect_budget_gb in the environment file with "
    f"the Spark settings ({SPARK_SETTINGS})"
)
SNAPSHOT_CALLOUT = (
    "raise collect_budget_gb in the environment file with the Spark settings "
    f"({SPARK_SETTINGS}), or pick a smaller eda.snapshot population through eligibility, which "
    "changes the data-definition hash and reruns EDA; the analysis population is never sampled"
)
CALLOUTS = {
    "snapshot": SNAPSHOT_CALLOUT,
    "train": TRAINING_CALLOUT,
    "test": TRAINING_CALLOUT,
    "validation": TRAINING_CALLOUT,
}


@dataclass
class Frames:
    """What a stage works on: the pandas frames and the Spark `rows` (None when the stage didn't
    ask for them), the log (join, eligibility, contract, compared-periods, null-target, sampling
    and collect entries, in order) and the meta (hashes, candidates, tags, lineage, the columns'
    sources, kinds, the unsupported columns, the snapshot period, the population counts, the
    sampling record, the collect measurements)."""

    snapshot: pd.DataFrame | None
    rows: DataFrame | None
    train: pd.DataFrame | None
    test: pd.DataFrame | None
    validation: pd.DataFrame | None
    log: list[dict]
    meta: dict


def build_frames(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession, stage: str
) -> Frames:
    """The frames `stage` works on (`eda`: the snapshot collected and `rows` left in Spark;
    `training`, `evaluation`: train, test, validation), from the model input when the config
    names one, else built in memory with the same logs."""
    if stage not in STAGE_FRAMES:
        raise ValueError(f"unknown stage {stage!r}; the frames serve {sorted(STAGE_FRAMES)}")
    kind = STAGE_FRAMES[stage]
    if kind == "modelling" and cfg.time.validation_period is None:
        raise ValueError(
            "time.validation_period is null: an EDA-only config; Training and Evaluation need it"
        )
    if cfg.data.model_input is None:
        panel, log, meta = build_panel(cfg, entity, env, spark)
    else:
        panel, log, meta = read_model_input(cfg, entity, env, spark)
    meta["column_sources"] = _column_sources(log, meta["candidates"], meta["lineage"])
    frames: dict = {}
    if kind == "snapshot":
        frames["snapshot"], frames["rows"] = _eda_frames(panel, cfg, env, log, meta)
    else:
        frames.update(_modelling_frames(panel, cfg, env, log, meta))
    meta["collect"] = [entry for entry in log if entry["step"] == "collect"]
    return Frames(
        snapshot=frames.get("snapshot"),
        rows=frames.get("rows"),
        train=frames.get("train"),
        test=frames.get("test"),
        validation=frames.get("validation"),
        log=log,
        meta=meta,
    )


def _column_sources(log: list[dict], candidates: list[str], lineage: list[str]) -> dict[str, str]:
    """Each candidate and lineage column → its source, from the join entries' `columns` under
    their read names (the read side's `rename` entry). The feature sources' entries come first,
    so a column is a target source's only when no feature source has it; the column-clash check
    makes it unique among the feature sources. A candidate in no entry fails loud; a lineage
    column in none (an upstream target's) has no source."""
    renamed = {old: new for e in log if e["step"] == "rename" for old, new in e["renamed"].items()}
    sources: dict[str, str] = {}
    for entry in (e for e in log if e["step"] == "join"):
        for column in entry["columns"]:
            sources.setdefault(renamed.get(column, column), entry["source"])
    missing = [name for name in candidates if name not in sources]
    if missing:
        raise ValueError(f"the candidates {missing} are in no source's join entry (`columns`)")
    return {name: sources[name] for name in [*candidates, *lineage] if name in sources}


def _eda_frames(
    panel: DataFrame, cfg: UseCaseConfig, env: EnvironmentConfig, log: list[dict], meta: dict
) -> tuple[pd.DataFrame, DataFrame]:
    """The snapshot collected and `rows` left in Spark (a lazy plan, which the EDA stage
    persists for its passes), the unsupported candidates dropped from both; the kinds, the
    unsupported columns, the snapshot period and the population counts join the meta, the
    compared periods and the collect the log. A snapshot period without a row fails loud before
    the collect."""
    spec = period_spec(cfg)
    supported = _supported_candidates(panel, cfg, meta)
    panel = panel.drop(*meta["unsupported"])
    available = sorted(row.period for row in panel.select("period").distinct().collect())
    snapshot_date = snapshot_period(cfg)
    meta["snapshot_period"] = spec.label(snapshot_date)
    if snapshot_date not in available:  # behind the contract's eligible_rows check today
        raise ValueError(
            f"eda.snapshot is {meta['snapshot_period']}, but the panel holds no row of that "
            "period after the analysis filters (data.eligibility.analysis)"
        )
    periods = compared_periods(cfg, available)
    log.append(_compared_entry(periods, cfg, available, spec))
    snapshot, entry = collect_frame(panel.where(F.col("period") == snapshot_date), "snapshot", env)
    log.append(entry)
    compared = [period for group in periods.values() for period in group]
    label = F.when(
        F.col("period").isin(periods["window"]), F.col("target")
    )  # the window only (§4.4)
    rows = panel.where((F.col("eligible") == 1) & F.col("period").isin(compared)).select(
        *KEYS, *supported, label.alias("target")
    )
    meta["population"] = population_counts(panel, cfg, periods)
    return snapshot, rows


def _supported_candidates(panel: DataFrame, cfg: UseCaseConfig, meta: dict) -> list[str]:
    """The candidates of a supported kind, in order; the kinds (supported ones) and the
    unsupported columns (column → type) join the meta, printed. None supported fails loud."""
    kinds = detect_kinds(panel.schema, meta["candidates"], cfg.features.kinds)
    unsupported = {
        name: panel.schema[name].dataType.simpleString()
        for name, kind in kinds.items()
        if kind == "unsupported"
    }
    supported = [name for name in meta["candidates"] if name not in unsupported]
    if not supported:
        raise ValueError(
            f"every candidate has an unsupported type ({unsupported}): EDA needs a numeric or "
            "categorical one; widen features.candidates or derive one upstream (features.kinds "
            "re-kinds numeric, string and boolean columns only)"
        )
    meta.update(kinds={name: kinds[name] for name in supported}, unsupported=unsupported)
    summary = ", ".join(
        f"{sum(k == kind for k in kinds.values())} {kind}" for kind in ("numeric", "categorical")
    )
    print(f"kinds: {summary}" + (f"; unsupported, dropped: {unsupported}" if unsupported else ""))
    return supported


def _compared_entry(periods: dict, cfg: UseCaseConfig, available: list, spec: Period) -> dict:
    """The `compared_periods` log entry, printed: the labels per group (`window`, `gap`,
    `latest`) and, when the panel lacks a window period, `missing_window` (T19: a gap is named,
    never skipped)."""
    labels = {group: [spec.label(period) for period in dates] for group, dates in periods.items()}
    entry = {"step": "compared_periods", **labels}
    window = cfg.time.observation_window
    missing = missing_periods(available, window.first, window.last, spec)
    if missing:
        entry["missing_window"] = missing
    shown = "; ".join(f"{group} {', '.join(names) or 'none'}" for group, names in labels.items())
    lacks = f"; window periods the panel lacks: {missing}" if missing else ""
    print(f"compared periods: {shown}{lacks}")
    return entry


def _modelling_frames(
    panel: DataFrame, cfg: UseCaseConfig, env: EnvironmentConfig, log: list[dict], meta: dict
) -> dict[str, pd.DataFrame]:
    """Train (sampled when declared), test and validation collected; the null-target, sampling
    and collect entries join the log, the sampling record the meta."""
    modelling, null_log = _modelling_rows(panel, cfg)
    log.append(null_log)
    train, record = sample_train(_window(modelling, cfg).where("split = 'train'"), cfg)
    log.append(record)
    meta["sampling"] = record
    parts = {
        "train": train,
        "test": _window(modelling, cfg).where("split = 'test'"),
        "validation": modelling.where(F.col("period") == cfg.time.validation_period),
    }
    frames = {}
    for name, part in parts.items():
        frames[name], entry = collect_frame(part, name, env)
        log.append(entry)
    return frames


def _window(panel: DataFrame, cfg: UseCaseConfig) -> DataFrame:
    """The panel's rows in the observation window."""
    window = cfg.time.observation_window
    return panel.where(F.col("period").between(window.first, window.last))


def _modelling_rows(panel: DataFrame, cfg: UseCaseConfig) -> tuple[DataFrame, dict]:
    """The eligible rows with a known target, in the window and at the validation period only
    (the panel carries labels beyond them, which no fit may see, §4.4); the share of eligible
    rows dropped for a null target, per period, logged and printed."""
    eligible = panel.where(F.col("eligible") == 1)
    window, spec = cfg.time.observation_window, period_spec(cfg)
    periods = F.col("period").between(window.first, window.last) | (
        F.col("period") == cfg.time.validation_period
    )
    eligible = eligible.where(periods)
    counts = (
        eligible.groupBy("period")
        .agg((1 - F.count("target") / F.count(F.lit(1))).alias("null_share"))
        .orderBy("period")
        .collect()
    )
    shares = label_by_period(counts, "null_share", spec)
    print("null targets dropped from the modelling frames, per period: "
          + ", ".join(f"{p} {s:.1%}" for p, s in shares.items()))  # fmt: skip
    return eligible.where(F.col("target").isNotNull()), {"step": "null_target", "share": shares}


def detect_kinds(
    schema: StructType, candidates: list[str], overrides: dict[str, str]
) -> dict[str, str]:
    """Each candidate's kind from the Spark schema, never from a pandas dtype (N13): `numeric`
    for a numeric type (decimals included), `categorical` for a string or a boolean,
    `unsupported` for the rest (date, timestamp, array, map, struct, binary); then the
    `features.kinds` overrides, which may name candidates only and may not turn a non-numeric
    column numeric (nothing is cast)."""
    unknown = sorted(set(overrides) - set(candidates))
    if unknown:
        raise ValueError(
            f"features.kinds names {unknown}, which are not candidates (features.candidates "
            "resolved over the sources' columns, minus the lineage and the framework's columns)"
        )
    kinds = {}
    for name in candidates:
        column_type = schema[name].dataType
        if isinstance(column_type, NumericType):
            kinds[name] = "numeric"
        elif isinstance(column_type, StringType | BooleanType):
            kinds[name] = "categorical"
        else:
            kinds[name] = "unsupported"
    for name, kind in overrides.items():
        column_type = schema[name].dataType.simpleString()
        if kinds[name] == "unsupported":
            raise ValueError(
                f"features.kinds sets {name!r} to {kind!r}, but its type {column_type} is "
                "unsupported; derive a numeric or string column upstream"
            )
        if kind == "numeric" and kinds[name] != "numeric":
            raise ValueError(
                f"features.kinds sets {name!r} to numeric, but it is a {column_type} column and "
                "nothing is cast; convert it upstream"
            )
        kinds[name] = kind
    return kinds


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
    """The frame collected to pandas after the printout: rows, columns and the estimate; above
    the budget the callout worded for the frame (`CALLOUTS`) with the budget, and the collect
    proceeds. Sorted by the keys with a fresh index; the measured size joins the entry."""
    estimate = estimate_collect(frame, name)
    budget = int(env.collect_budget_gb * GB)
    print(f"collect {name}: {estimate['rows']:,} rows × {estimate['columns']} columns, "
          f"≈ {estimate['estimate_bytes'] / GB:.2f} GB at the conversion peak")  # fmt: skip
    if estimate["estimate_bytes"] > budget:  # the budget is the environment's: named only here
        print(f"  above the budget ({env.collect_budget_gb} GB): {CALLOUTS[name]}; "
              "collecting anyway")  # fmt: skip
    # toPandas() after joins and shuffles has no set row order, and a positional seeded sample
    # (the association's cap) must pick the same rows on a rerun of the same data (T34, §4.10);
    # sorted in Spark, so pandas holds no second copy at the peak
    collected = frame.orderBy("unit_id", "period").toPandas()
    measured = int(collected.memory_usage(deep=True).sum())
    print(f"  collected {name}: {measured / GB:.2f} GB in pandas")
    entry = {"step": "collect", "frame": name, **estimate, "measured_bytes": measured,
             "budget_bytes": budget}  # fmt: skip
    return collected, entry
