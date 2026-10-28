"""The panel: the spine, the other sources and the targets joined, eligibility applied, the
candidates resolved (D-129, D-131).

`load_panel` reads every source of an entity through `read_keyed_source` (keys renamed, months
at their last day), left-joins the other feature sources and the targets (`load_targets`, built
over the whole target source, never a window of it) to the governing spine on the keys, and
keeps the months from the observation window's first to the spine's last. `apply_eligibility`
runs the ordered steps on every month alike (§4.9): a `define` adds a boolean column later steps
reuse, a `before: eda` filter drops its rows, a `before: model` filter tags them (a 0/1 column
named after the step) and `eligible` marks the rows every pre-model filter passes. A condition
may reference the sources' columns and earlier define names only: the keys, the target, the
split and another filter's tag never select the population, since eligibility SQL is a leakage
surface outside the screens. `resolve_candidates` turns the config's patterns into the candidate
list, minus the keys, the helper columns, the lineage and the step names
(docs/components/dataset.md).
"""

import re
from fnmatch import fnmatchcase
from functools import reduce

from pyspark.errors import AnalysisException
from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType

from core_modelling.config import UseCaseConfig
from core_modelling.config.identities import HASH_VERSION, data_definition_hash, target_spec_hash
from core_modelling.config.schema import EligibilityStep
from core_modelling.dataset.contract import check_contract
from core_modelling.dataset.split import assign_split
from core_modelling.environment import EnvironmentConfig
from core_modelling.sources import missing_months, read_keyed_source
from core_modelling.target_factory import load_targets, target_lineage

KEYS = ["unit_id", "month"]
# Columns the dataset adds: never candidates, never referenced by an eligibility condition.
HELPER_COLUMNS = ["target", "null_in_window", "split", "eligible"]
PANEL_META_KEYS = ("data_definition_hash", "target_spec_hash", "hash_version", "lineage",
                   "candidates", "tags")  # what `build_panel` puts in the meta  # fmt: skip
# SQL a condition may not contain: a star in a call (expands over every column, the target
# included), a subquery (reads the catalog, not the panel), a window function (looks across rows).
UNSAFE_SQL = {r"[(,]\s*\*": "a star", r"\bselect\b": "a subquery", r"\bover\s*\(": "a window"}


def load_panel(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession
) -> tuple[DataFrame, list[dict]]:
    """The governing spine with the other feature sources and the targets left-joined on the
    keys, from the window's first month to the spine's last; the join log, one entry per source,
    with the rows each matched per month."""
    if entity not in cfg.entities:
        raise ValueError(f"unknown entity {entity!r}: the config has {sorted(cfg.entities)}")
    names = cfg.entities[entity].sources.features
    panel, spine_log = read_keyed_source(cfg, entity, names[0], env, spark)
    _check_spine_months(spine_log, cfg)
    joined = [(spine_log, None, "spine")]  # (log, the column that shows a match, role)
    for name in names[1:]:
        source, log = read_keyed_source(cfg, entity, name, env, spark)
        _check_no_shared_column(panel, source, name)
        marker = f"_from_{name}"
        panel = panel.join(source.withColumn(marker, F.lit(True)), KEYS, "left")
        joined.append((log, marker, "joined"))
    targets, log = load_targets(cfg, entity, env, spark)
    panel = panel.join(targets.withColumn("_from_targets", F.lit(True)), KEYS, "left")
    joined.append((log, "_from_targets", "targets"))
    first, last = cfg.time.train_months.first, spine_log["months"][-1]
    panel = panel.where(F.col("month").between(first, last))
    _check_named_features(panel, cfg)
    entries = _join_log(panel, joined, cfg)
    return panel.drop(*[marker for _, marker, _ in joined if marker]), entries


def _check_spine_months(log: dict, cfg: UseCaseConfig) -> None:
    """The spine has every month from the window's first to the validation month: a gap would
    drop a month of rows quietly, and the validation month must exist to be scored."""
    missing = missing_months(log["months"], cfg.time.train_months.first, cfg.time.validation_month)
    if missing:
        raise ValueError(
            f"spine {log['source']!r} lacks the months {missing}; it must have every month from "
            "time.train_months.first to time.validation_month"
        )


def _check_no_shared_column(panel: DataFrame, source: DataFrame, name: str) -> None:
    """A non-key column in two feature sources fails loud: the join would carry two of it."""
    shared = sorted(set(panel.columns) & set(source.columns) - set(KEYS))
    if shared:
        raise ValueError(
            f"feature source {name!r} shares the columns {shared} with an earlier source; rename "
            "them upstream"
        )


def _check_named_features(panel: DataFrame, cfg: UseCaseConfig) -> None:
    """A name in the audit log's replayed lists that is not a column fails loud (a typo in an
    entry would otherwise exclude nothing)."""
    for field in ("excluded", "kept_despite_flags"):
        unknown = [n for n in getattr(cfg.features, field) if n not in panel.columns]
        if unknown:
            raise ValueError(f"features.{field} names columns the sources don't have: {unknown}")


def _join_log(panel: DataFrame, joined: list[tuple], cfg: UseCaseConfig) -> list[dict]:
    """One entry per source from one rollup of the panel: the spine's rows per month, and per
    joined source the rows it matched per month and their share; a window month with no known
    target fails loud (the target source matched nothing there: keys or months disagree)."""
    markers = [marker for _, marker, _ in joined if marker]
    counts = [F.count(marker).alias(marker) for marker in markers]
    rows = panel.groupBy("month").agg(
        F.count(F.lit(1)).alias("rows"), F.count("target").alias("known"), *counts
    )
    by_month = {row.month: row for row in rows.orderBy("month").collect()}
    spine_rows = sum(row.rows for row in by_month.values())
    window = cfg.time.train_months
    in_window = [m for m in by_month if window.first <= m <= window.last]
    unlabelled = [f"{m:%Y-%m}" for m in in_window if not by_month[m].known]
    if unlabelled:
        raise ValueError(
            f"no known target in the window's months {unlabelled}: the target source matched no "
            "spine row there (do the keys and the months agree?)"
        )
    entries = []
    for log, marker, role in joined:
        entry = {"step": "join", "source": log["source"], "role": role}
        entry["month_tag"] = log["month_tag"]
        if marker is None:
            entry["rows"] = {f"{m:%Y-%m}": r.rows for m, r in by_month.items()}
            print(f"spine {log['source']} ({log['month_tag']} months): {spine_rows:,} rows from "
                  f"{min(by_month):%Y-%m} to {max(by_month):%Y-%m}")  # fmt: skip
        else:
            matched = {f"{m:%Y-%m}": r[marker] for m, r in by_month.items()}
            entry.update(matched_share=sum(matched.values()) / spine_rows, matched=matched)
            print(f"join {log['source']} ({role}, {log['month_tag']} months): "
                  f"{entry['matched_share']:.1%} of the spine's rows matched")  # fmt: skip
        entries.append(entry)
    return entries


def apply_eligibility(
    panel: DataFrame, steps: list[EligibilityStep]
) -> tuple[DataFrame, list[dict]]:
    """The ordered steps applied to every month alike: a define adds its column for later steps
    (dropped at the end), a `before: eda` filter drops its rows, a `before: model` filter tags
    them 0/1 under its name; `eligible` is 1 where every tag is. The log has one entry per
    filter (`step: eligibility`, the step's `name`) with its rows per month and the rows whose
    condition was null (counted as not passing)."""
    allowed = [c for c in panel.columns if c not in KEYS and c not in HELPER_COLUMNS]
    defines, tags, log = [], [], []
    for step in steps:
        if step.name in panel.columns or step.name in (*KEYS, *HELPER_COLUMNS):
            raise ValueError(
                f"eligibility step {step.name!r} is named like a column of the panel or one the "
                f"dataset adds ({', '.join(HELPER_COLUMNS)})"
            )
        condition = _condition(panel, step, allowed)
        if step.define is not None:
            panel = panel.withColumn(step.name, condition)
            defines.append(step.name)
            allowed.append(step.name)
            continue
        passes = F.coalesce(condition, F.lit(False))  # a null condition counts as false
        rows, passing, nulls = _rows_per_month(panel, condition)
        entry = {"step": "eligibility", "name": step.name, "before": step.before}
        entry.update(reason=step.reason, rows=rows, null_condition=nulls)
        total, kept, unknown = sum(rows.values()), sum(passing.values()), sum(nulls.values())
        if step.before == "eda":
            panel = panel.where(passes)
            log.append({**entry, "rows_out": passing})
            print(f"eligibility {step.name} (before eda): {total:,} → {kept:,} rows "
                  f"({unknown:,} with a null condition, dropped); {step.reason}")  # fmt: skip
        else:
            panel = panel.withColumn(step.name, passes.cast("int"))
            tags.append(step.name)
            log.append({**entry, "tagged_1": passing})
            print(f"eligibility {step.name} (before model): {kept:,} of {total:,} rows tagged 1 "
                  f"({unknown:,} with a null condition, tagged 0), the rest stay for EDA; "
                  f"{step.reason}")  # fmt: skip
    eligible = reduce(lambda a, b: a & b, [F.col(tag) == 1 for tag in tags], F.lit(True))
    return panel.withColumn("eligible", eligible.cast("int")).drop(*defines), log


def _condition(panel: DataFrame, step: EligibilityStep, allowed: list[str]) -> Column:
    """The step's SQL as a boolean Column, resolved against the allowed columns only, so a
    reference to the keys, the target, the split or another filter's tag fails naming the step."""
    sql = step.define if step.define is not None else step.filter
    for pattern, what in UNSAFE_SQL.items():
        if re.search(pattern, sql, flags=re.IGNORECASE):
            raise ValueError(
                f"eligibility step {step.name!r}: {sql!r} holds {what}; a condition is a plain "
                "expression over the row's own columns"
            )
    try:
        probe = panel.select(*allowed).select(F.expr(sql).alias(step.name)).schema
    except AnalysisException as exc:
        raise ValueError(
            f"eligibility step {step.name!r}: {sql!r} may reference the sources' columns and "
            "earlier define names only, never the keys, the target, the split, `eligible` or "
            f"another filter's tag; Spark says: {exc}"
        ) from exc
    column_type = probe[step.name].dataType
    if not isinstance(column_type, BooleanType):
        raise TypeError(
            f"eligibility step {step.name!r}: {sql!r} is {column_type.simpleString()}, not a "
            "boolean condition"
        )
    return F.expr(sql)


def _rows_per_month(panel: DataFrame, condition: Column) -> tuple[dict, dict, dict]:
    """The panel's rows per month, the rows passing the condition and the rows whose condition
    is null, from one aggregate."""
    counts = panel.groupBy("month").agg(
        F.count(F.lit(1)).alias("rows"),
        F.count(F.when(condition, True)).alias("passing"),
        F.count(F.when(condition.isNull(), True)).alias("nulls"),
    )
    collected = counts.orderBy("month").collect()
    per_month = lambda field: {f"{row.month:%Y-%m}": row[field] for row in collected}  # noqa: E731
    return per_month("rows"), per_month("passing"), per_month("nulls")


def pre_model_tags(cfg: UseCaseConfig) -> list[str]:
    """The tag columns the panel carries: one per `before: model` filter, named after the step."""
    return [step.name for step in cfg.data.eligibility if step.before == "model"]


def resolve_candidates(columns: list[str], cfg: UseCaseConfig, lineage: list[str]) -> list[str]:
    """The columns matching an include pattern and no exclude pattern, minus the keys, the
    helper columns, the lineage (T12) and the eligibility steps' names (tags and defines)."""
    patterns = cfg.features.candidates
    reserved = {*KEYS, *HELPER_COLUMNS, *lineage, *(step.name for step in cfg.data.eligibility)}
    candidates = [
        column
        for column in columns
        if column not in reserved
        and any(fnmatchcase(column, pattern) for pattern in patterns.include)
        and not any(fnmatchcase(column, pattern) for pattern in patterns.exclude)
    ]
    if not candidates:
        raise ValueError(
            f"no candidate column: features.candidates {patterns.model_dump()} matches none of "
            f"{sorted(set(columns) - reserved)}; never candidates: the keys, {HELPER_COLUMNS}, "
            f"the lineage {lineage} and the eligibility steps' names"
        )
    return candidates


def build_panel(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession
) -> tuple[DataFrame, list[dict], dict]:
    """The panel built in memory: sources joined, eligibility applied, the contract checked
    (`null_in_window` serves it and goes), the split assigned, the targets outside the window
    and the validation month nulled; the keys, the candidates, the tags, `eligible`, `target`
    and `split`, with the log and the meta (`PANEL_META_KEYS`)."""
    panel, log = load_panel(cfg, entity, env, spark)
    panel, eligibility_log = apply_eligibility(panel, cfg.data.eligibility)
    lineage = target_lineage(cfg)
    candidates = resolve_candidates(panel.columns, cfg, lineage)
    tags = pre_model_tags(cfg)
    contract_log = check_contract(panel, cfg)
    panel = assign_split(panel, cfg)
    # Labels stay in the window and at the validation month only: the later months, which
    # Feature Checks reads label-free, carry none (§4.4), as Target Factory's summary shows none.
    window = cfg.time.train_months
    labelled = F.col("month").between(window.first, window.last) | (
        F.col("month") == cfg.time.validation_month
    )
    panel = panel.withColumn("target", F.when(labelled, F.col("target")))
    columns = [*KEYS, *candidates, *tags, "eligible", "target", "split"]
    meta = {
        "data_definition_hash": data_definition_hash(cfg, entity),
        "target_spec_hash": target_spec_hash(cfg, entity),
        "hash_version": HASH_VERSION,
        "lineage": lineage,
        "candidates": candidates,
        "tags": tags,
    }
    return panel.select(columns), [*log, *eligibility_log, *contract_log], meta
