"""Who is in: the eligibility steps applied to the panel, and the candidate columns (D-129, §4.9).

`apply_eligibility` runs the two ordered lists on every period alike, the `analysis` steps then
the `modelling` steps: a `define` adds a boolean column later steps reuse, an analysis filter
drops its rows, a modelling filter tags them (a 0/1 column named after the step) and `eligible`
marks the rows every modelling filter passes. A condition may reference the sources' columns
and earlier define names only: the keys, the target, the split and another filter's tag never
select the population, since eligibility SQL is a leakage surface outside the screens.
`resolve_candidates` turns the config's patterns into the candidate list, minus the keys, the
helper columns, the lineage and the step names (docs/components/dataset.md).
"""

import re
from fnmatch import fnmatchcase
from functools import reduce

from pyspark.errors import AnalysisException
from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType

from core_modelling.config import UseCaseConfig
from core_modelling.config.schema import Eligibility, EligibilityStep
from core_modelling.periods import Period, label_by_period
from core_modelling.sources import HELPER_COLUMNS, KEYS

# SQL a condition may not contain: a star in a call (expands over every column, the target
# included), a subquery (reads the catalog, not the panel), a window function (looks across
# rows), a non-deterministic function (the population would differ between the model input's
# build and a later run, §4.9).
NON_DETERMINISTIC = (
    r"rand|randn|uuid|current_date|current_timestamp|now|localtimestamp|"
    r"monotonically_increasing_id|spark_partition_id|input_file_name"
)
UNSAFE_SQL = {
    r"[(,]\s*\*": "a star",
    r"\bselect\b": "a subquery",
    r"\bover\s*\(": "a window",
    rf"\b({NON_DETERMINISTIC})\s*\(": "a non-deterministic function",
}


def apply_eligibility(
    panel: DataFrame, eligibility: Eligibility, spec: Period
) -> tuple[DataFrame, list[dict]]:
    """The analysis steps then the modelling steps, applied to every period alike: a define
    adds its column for later steps (dropped at the end), an analysis filter drops its rows, a
    modelling filter tags them 0/1 under its name; `eligible` is 1 where every tag is. The log
    has one entry per filter (`step: eligibility`, the step's `name` and `kind`) with its rows
    per period (keyed by the spec's label) and the rows whose condition was null (counted as not
    passing)."""
    allowed = [c for c in panel.columns if c not in KEYS and c not in HELPER_COLUMNS]
    defines, tags, log = [], [], []
    steps = [(step, "analysis") for step in eligibility.analysis]
    steps += [(step, "modelling") for step in eligibility.modelling]
    for step, kind in steps:
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
        rows, passing, nulls = _rows_per_period(panel, condition, spec)
        entry = {"step": "eligibility", "name": step.name, "kind": kind}
        entry.update(reason=step.reason, rows=rows, null_condition=nulls)
        total, kept, unknown = sum(rows.values()), sum(passing.values()), sum(nulls.values())
        if kind == "analysis":
            panel = panel.where(passes)
            log.append({**entry, "rows_out": passing})
            print(f"eligibility {step.name} (analysis): {total:,} → {kept:,} rows "
                  f"({unknown:,} with a null condition, dropped); {step.reason}")  # fmt: skip
        else:
            panel = panel.withColumn(step.name, passes.cast("int"))
            tags.append(step.name)
            log.append({**entry, "tagged_1": passing})
            print(f"eligibility {step.name} (modelling): {kept:,} of {total:,} rows tagged 1 "
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
            "another filter's tag (a source column named like one of these is read as "
            f"`source_<name>`); Spark says: {exc}"
        ) from exc
    column_type = probe[step.name].dataType
    if not isinstance(column_type, BooleanType):
        raise TypeError(
            f"eligibility step {step.name!r}: {sql!r} is {column_type.simpleString()}, not a "
            "boolean condition"
        )
    return F.expr(sql)


def _rows_per_period(panel: DataFrame, condition: Column, spec: Period) -> tuple[dict, dict, dict]:
    """The panel's rows per period (keyed by the spec's label), the rows passing the condition
    and the rows whose condition is null, from one aggregate."""
    counts = panel.groupBy("period").agg(
        F.count(F.lit(1)).alias("rows"),
        F.count(F.when(condition, True)).alias("passing"),
        F.count(F.when(condition.isNull(), True)).alias("nulls"),
    )
    collected = counts.orderBy("period").collect()
    return tuple(label_by_period(collected, field, spec) for field in ("rows", "passing", "nulls"))


def modelling_tags(cfg: UseCaseConfig) -> list[str]:
    """The tag columns the panel carries: one per modelling filter, named after the step."""
    return [step.name for step in cfg.data.eligibility.modelling if step.filter is not None]


def step_names(cfg: UseCaseConfig) -> list[str]:
    """Every eligibility step's name, both lists (tags and defines)."""
    eligibility = cfg.data.eligibility
    return [step.name for step in (*eligibility.analysis, *eligibility.modelling)]


def resolve_candidates(columns: list[str], cfg: UseCaseConfig, lineage: list[str]) -> list[str]:
    """The columns matching an include pattern and no exclude pattern, minus the keys, the
    helper columns, the lineage (T12) and the eligibility steps' names (tags and defines)."""
    patterns = cfg.features.candidates
    reserved = {*KEYS, *HELPER_COLUMNS, *lineage, *step_names(cfg)}
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
