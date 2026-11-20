"""The score cells in Spark: the one aggregate every Evaluation metric reads, summed from the
scores table (evaluation.md → "Score cells", A92–A94).

`score_edges` cuts one scorer's bins once over every scored row, at `bin_quantiles`'
probabilities (a regression target's bins as `tasks.TASK_SPECS` cuts them); `score_cells` then
sums the rows into `statistics/score_cells.py`'s cells, replicate 0 as the rows are and 1 to R
weighted by `client_weights`, a stratum's levels capped first as EDA caps them
(`stratum_labels`). Each row's weights are exploded and summed in one `groupBy`, whose partial
aggregation collapses the exploded rows inside each partition, so the shuffle carries cells,
not rows (the counts table's pattern): pure Spark SQL, nothing Python-side on the executors and
no weight array through Arrow. Only the cells reach the driver.
"""

import math

import numpy as np
import pandas as pd
from pyspark.ml.feature import Bucketizer
from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, FloatType

from core_modelling.config import UseCaseConfig
from core_modelling.dataset.counts import NULL_BIN, OTHER
from core_modelling.eda.population import cap_levels
from core_modelling.periods import period_spec
from core_modelling.statistics.losses import TWEEDIE_METRIC_POWER
from core_modelling.statistics.metrics import NAN
from core_modelling.statistics.score_cells import (
    CELL_EXTREMES,
    CELL_KEYS,
    CELL_SUMS,
    PARTS,
    PROBABILITY_CLIP,
    ROW_LOSSES,
    STRATA_STEP,
    quantile_passes,
)
from core_modelling.tasks import TASK_SPECS, ZERO_BIN_EDGES

WEIGHT_SALT = "client_bootstrap"  # fixed, so two runs on the same rows share the weights (A47)
UNIFORM_BITS = 53  # a double holds a uniform of this many random bits exactly
POISSON_MAX = 17  # the largest weight: P(X > 17) < 2⁻⁵³, below the uniform's resolution
# P(X ≤ k) of a Poisson(1) for k = 0 … POISSON_MAX − 1, the inverse CDF's thresholds
POISSON_CDF = np.cumsum([math.exp(-1) / math.factorial(k) for k in range(POISSON_MAX)])
SKETCH_POINTS = 4000  # quantiles of a regression target its bins are cut from (EDA's rules)
# `approxQuantile`'s rank error, as a share of the rows it reads: a tenth of the narrowest score
# bin of each pass (0.1% of every row in the body; 0.001% of every row, so 0.1% of the tail's,
# in the tail) and below the target sketch's spacing (2.5e-4); its summary keeps of the order
# of 1 / error entries per partition
QUANTILE_ERROR = 1e-4
# A regression objective's deviance when the decision's metric names none (binary: always log)
OBJECTIVE_LOSSES = {"log_loss": "log_loss", "tweedie": "tweedie_deviance",
                    "poisson": "poisson_deviance"}  # fmt: skip


def client_weights(client: Column, replicates: int, salt: str) -> Column:
    """The client's bootstrap weights as `array<int>`: element r − 1 is replicate r's Poisson(1)
    weight, drawn from `xxhash64(client, r, salt)` (`_uniform`) through the inverse CDF
    (`_poisson_weight`). Two `transform`s over `sequence(1, replicates)`, so the plan holds one
    hash and one sum of 17 comparisons whatever the replicate count, and each element's hash is
    computed once. Column expressions only, so a client's rows share each weight and the
    weights repeat on every run and machine that hashes the same client (A47, A94)."""
    if replicates < 1:
        raise ValueError(f"client_weights: replicates must be at least 1, got {replicates}")
    replicate = F.sequence(F.lit(1), F.lit(replicates))
    uniforms = F.transform(replicate, lambda r: _uniform(client, r, salt))
    return F.transform(uniforms, _poisson_weight)


def _uniform(client: Column, replicate: Column, salt: str) -> Column:
    """A uniform in [0, 1): the low `UNIFORM_BITS` bits of `xxhash64(client, replicate, salt)`
    over 2^`UNIFORM_BITS` (the replicate an int, the salt a string, so the hash's input types
    never change)."""
    hashed = F.xxhash64(client, replicate.cast("int"), F.lit(salt))
    low_bits = hashed.bitwiseAND(F.lit((1 << UNIFORM_BITS) - 1))
    return low_bits.cast("double") / float(1 << UNIFORM_BITS)


def _poisson_weight(uniform: Column) -> Column:
    """The Poisson(1) inverse CDF of `uniform`, as scipy's `poisson.ppf`: the count of
    `POISSON_CDF`'s thresholds below u, a sum of `POISSON_MAX` (17) comparisons, which is the
    smallest k with P(X ≤ k) ≥ u, at most `POISSON_MAX`."""
    terms = [(uniform > float(threshold)).cast("int") for threshold in POISSON_CDF]
    return sum(terms[1:], start=terms[0])


def scorer_loss(cfg: UseCaseConfig, objective: str) -> str | None:
    """The row loss (`ROW_LOSSES`) of the model's score and of a baseline that predicts like it:
    the decision's metric when it is one, else the objective's (the log loss for binary, a
    deviance under Tweedie or Poisson), else None. `objective` is the run's, from its
    `run.json`, not the config's: a run named for Evaluation or `compare_runs` may have been
    trained under another. The Tweedie deviance is at the metric's constant power, never the
    objective's (A67)."""
    if cfg.decision.metric in ROW_LOSSES:
        return cfg.decision.metric
    return OBJECTIVE_LOSSES.get(objective)


def score_edges(
    scores: DataFrame, cfg: UseCaseConfig, column: str = "score"
) -> dict[str, np.ndarray | None]:
    """One scorer's bin edges, cut once over every scored row so each `by` shares them (A93):
    `score` the quantiles at `bin_quantiles`, `strata` every `STRATA_STEP`-th of them, so a
    stratum's bin is whole score bins, `target` the task's target bins as EDA cuts them from
    `SKETCH_POINTS` quantiles (`target_bins`: None for a 0/1 target, its own bin). One Spark
    job over `column` and `target` takes the body's quantiles (`quantile_passes`); a task with
    a tail (binary's top 1%) takes the tail's in a second, over the rows at or above the body's
    last edge. A value that fills a bin becomes its own bin (`quantile_edges`' mass point), so
    the edges ascend strictly. When the body's last edge sits on a block of tied scores, the
    whole block joins the tail and its bins widen by the block's share: valid, only coarser."""
    body, tail = quantile_passes(cfg.task)
    sketch = [(i + 0.5) / SKETCH_POINTS for i in range(SKETCH_POINTS)]
    quantiles = scores.approxQuantile([column, "target"], [*body, *sketch], QUANTILE_ERROR)
    score_values, target_values = (np.asarray(values, dtype=float) for values in quantiles)
    score_cuts, target_sketch = score_values[: body.size], target_values[body.size :]
    _check_quantiles({column: score_cuts, "target": target_sketch})
    if tail.size:
        top = scores.where(F.col(column) >= float(score_cuts[-1]))
        top_cuts = np.asarray(top.approxQuantile(column, tail.tolist(), QUANTILE_ERROR), float)
        _check_quantiles({column: top_cuts})
        score_cuts = np.concatenate([score_cuts, top_cuts])
    step = STRATA_STEP[cfg.task]
    return {
        "score": _distinct_edges(score_cuts),
        "strata": _distinct_edges(score_cuts[step - 1 :: step]),
        "target": TASK_SPECS[cfg.task]["target_bins"](target_sketch, False),
    }


def _check_quantiles(quantiles: dict[str, np.ndarray]) -> None:
    """Fail loud on a column `approxQuantile` found no value of, or a NaN among its quantiles
    (Spark orders a NaN above every number)."""
    for name, values in quantiles.items():
        if values.size == 0 or np.isnan(values).any():
            raise ValueError(f"`{name}` has no value to cut into bins, or holds NaN")


def _distinct_edges(quantiles: np.ndarray) -> np.ndarray:
    """Strictly ascending edges from ascending quantiles: each value once, and a value met at
    two or more quantiles (it fills a bin) also its next float up, so `[v, next)` holds exactly
    `v`; the edges of a subset of the quantiles are a subset of these."""
    distinct, counts = np.unique(quantiles + 0.0, return_counts=True)  # -0.0 becomes 0.0
    return np.unique(np.concatenate([distinct, np.nextafter(distinct[counts > 1], np.inf)]))


def score_cells(
    scores: DataFrame,
    cfg: UseCaseConfig,
    by: list[str],
    edges: dict[str, np.ndarray | None],
    *,
    loss: str | None,
    column: str = "score",
) -> pd.DataFrame:
    """The score cells of one scorer (`column`: `score`, or a baseline's column), collected.

    Receives the scores table (one row per client, period and part) and `score_edges`' edges;
    `by` names columns of it: `[]`, `["split"]` or a stratum. The caller asks for `["split"]`
    only and derives the `all` cells with `pool_cells(cells, "split")`, one Spark pass fewer.
    A `by` holding one of `strata.variables` makes stratum cells: the `strata` edges, the
    levels capped as EDA caps them before the aggregate (`stratum_labels`), and a regression
    target cut at EDA's zero bin only (`ZERO_BIN_EDGES`): the zero bin and one bin of the
    positive targets (a third bin holds negative ones, if any), so a level's `events` count
    right, while 20 target bins would outgrow the driver at bank size and the strata table reads
    no concordance per level; a 0/1 target keeps its two. `loss` is the scorer's row
    loss (`scorer_loss(cfg, objective)`, or None for a scorer that predicts nothing, the single
    feature): `loss_sum` and `link_sum` are null without it.

    Returns one row per non-empty cell and replicate, 0 to `evaluation.intervals.replicates`:
    `part, period` (its label), `by`'s columns, `score_bin, target_bin, replicate`, `CELL_SUMS`
    and `CELL_EXTREMES`, sorted by replicate, then the keys. A part without rows, a null or
    NaN score, or a row outside its loss's domain fails loud, naming it.
    """
    _check_request(scores, by, column, loss)
    strata = [name for name in by if name in cfg.strata.variables]
    bin_edges, target_edges = edges["score"], edges["target"]
    if strata:
        bin_edges = edges["strata"]
        target_edges = None if target_edges is None else ZERO_BIN_EDGES
    capped, other_rows = _capped_strata(scores, strata, cfg.strata.max_levels)
    binned = _binned(capped, column, bin_edges, target_edges)
    keys = [*CELL_KEYS[:2], *by, *CELL_KEYS[2:]]  # `by`'s columns follow `period`
    replicates = cfg.evaluation.intervals.replicates
    weights = F.concat(  # replicate 0 first, every row at weight 1
        F.array(F.lit(1)), client_weights(F.col("unit_id"), replicates, WEIGHT_SALT)
    )
    terms = _row_terms(F.col(column), loss)
    # two selects: the row terms are computed once per row, before the explode
    named = [value.alias(name) for name, value in terms.items()]
    per_row = binned.select(*keys, *named, weights.alias("weights"))
    drawn = per_row.select(
        *keys, *terms, F.posexplode("weights").alias("replicate", "weight")
    ).where(F.col("weight") > 0)
    weight = F.col("weight")
    aggregated = drawn.groupBy(*keys, "replicate").agg(
        F.sum(weight).alias("rows"),
        *[F.sum(weight * F.col(name)).alias(name) for name in terms if name in CELL_SUMS],
        F.min("scorer").alias("score_min"),
        F.max("scorer").alias("score_max"),
    )
    cells = aggregated.toPandas()
    _check_cells(cells, column, loss, bin_edges.size)
    _check_other(cells, other_rows)
    cells["period"] = cells["period"].map(period_spec(cfg).label)
    ordered = cells[[*keys, "replicate", *CELL_SUMS, *CELL_EXTREMES]]
    return ordered.sort_values(["replicate", *keys]).reset_index(drop=True)


def _check_request(scores: DataFrame, by: list[str], column: str, loss: str | None) -> None:
    """Fail loud before Spark runs on a scorer column or a `by` column the scores lack, a `by`
    column that is a cell key, or a loss `ROW_LOSSES` does not hold."""
    absent = [name for name in [column, *by] if name not in scores.columns]
    if absent:
        raise ValueError(f"score_cells: the scores lack the columns {absent}")
    reserved = [name for name in by if name in {*CELL_KEYS, "replicate", "unit_id"}]
    if reserved:
        raise ValueError(f"score_cells: by names the cell keys {reserved}")
    if loss is not None and loss not in ROW_LOSSES:
        raise ValueError(f"score_cells: unknown loss {loss!r}; known: {sorted(ROW_LOSSES)}")


def stratum_labels(values: pd.Series, rows: pd.Series, max_levels: int) -> pd.Series:
    """Each distinct value's level label as EDA's `cap_levels` gives its rows, from row counts.

    Receives one entry per distinct value of a stratum (`values`, null and NaN included) and its
    row count (`rows`) on one index; returns the label (str) on that index: the `max_levels`
    labels with the most rows, ties by label, as `cap_levels` names them (a real level named
    like a reserved bin quoted), the rest `__other__`, null and NaN `null`. Only the ranking is
    redone here, since `cap_levels` reads rows, not counts; a test pins the two together.
    """
    text = cap_levels(values, len(values)).astype(str)  # each value its own label, none pooled
    real = values.notna()
    totals = rows[real].groupby(text[real]).sum()
    kept = totals.sort_index().sort_values(ascending=False, kind="stable").index[:max_levels]
    return text.where(~real | text.isin(kept), OTHER)


def _capped_strata(
    scores: DataFrame, strata: list[str], max_levels: int
) -> tuple[DataFrame, dict[str, int]]:
    """`scores` with each of `strata` as its level label (str, `stratum_labels`), from one
    count per stratum, so a many-level stratum adds at most `max_levels` + 2 levels (`__other__`
    and `null`) to the cells, as in EDA's strata tables; and per stratum the rows its counts
    put in `__other__`, which `_check_other` holds the cells to."""
    other_rows = {}
    for name in strata:
        counts = scores.groupBy(name).count().toPandas()
        labels = stratum_labels(counts[name], counts["count"], max_levels)
        other_rows[name] = int(counts.loc[(labels == OTHER).to_numpy(), "count"].sum())
        column = F.col(name)
        missing = column.isNull()
        if isinstance(scores.schema[name].dataType, DoubleType | FloatType):
            missing |= F.isnan(column)  # pandas reads a NaN as null, so EDA does too (N2)
        label = F.when(missing, NULL_BIN)
        for value, text in zip(counts[name], labels, strict=True):
            if pd.notna(value) and text != OTHER:
                plain = value.item() if isinstance(value, np.generic) else value
                label = label.when(column == F.lit(plain), text)
        scores = scores.withColumn(name, label.otherwise(OTHER))
    return scores, other_rows


def _check_other(cells: pd.DataFrame, other_rows: dict[str, int]) -> None:
    """Fail loud when a stratum's `__other__` cells at replicate 0 hold other rows than its
    counts' levels that were not kept: a value that matched no kept level's comparison in Spark
    (`_capped_strata`) would fall into `__other__` unseen."""
    first = cells[cells["replicate"] == 0]
    for name, expected in other_rows.items():
        found = int(first.loc[first[name] == OTHER, "rows"].sum())
        if found != expected:
            raise ValueError(
                f"score_cells: the stratum `{name}` puts {found:,} rows in {OTHER}, but its "
                f"levels that were not kept hold {expected:,}: a kept level's value matched "
                "none of its rows in Spark"
            )


def _binned(
    scores: DataFrame, column: str, edges: np.ndarray, target_edges: np.ndarray | None
) -> DataFrame:
    """The scores with `score_bin` (int, ascending in `column`) and `target_bin` (int: a 0/1
    target itself when `target_edges` is None, else its bucket on them), from one `Bucketizer`
    with `handleInvalid="keep"`: bucket i is [e_i, e_{i+1}) over [−inf, *edges, inf], a NaN
    lands in bucket len(edges) + 1 and a null stays null. Values are normalised with `+ 0.0`
    first (Java orders −0.0 below 0.0, `counts._bucketize`)."""
    splits: dict[str, tuple[str, np.ndarray]] = {"score_bin": (column, edges)}
    if target_edges is not None:
        splits["target_bin"] = ("target", target_edges)
    values = [(F.col(source) + 0.0).alias(f"{name}_value") for name, (source, _) in splits.items()]
    bucketizer = Bucketizer(
        splitsArray=[[-np.inf, *map(float, cut), np.inf] for _, cut in splits.values()],
        inputCols=[f"{name}_value" for name in splits],
        outputCols=list(splits),
        handleInvalid="keep",
    )
    binned = bucketizer.transform(scores.select("*", *values)).drop(*[f"{n}_value" for n in splits])
    target_bin = F.col("target") if target_edges is None else F.col("target_bin")
    return binned.withColumn("score_bin", F.col("score_bin").cast("int")).withColumn(
        "target_bin", target_bin.cast("int")
    )


def _row_terms(score: Column, loss: str | None) -> dict[str, Column]:
    """Each row's value of every sum but `rows`, named as its sum, and the scorer as `scorer`
    (for the extremes): `score_cells.cells_from_rows`' terms in Spark."""
    target, score = F.col("target").cast("double"), score.cast("double")
    error, null = target - score, F.lit(None).cast("double")
    return {
        "target_sum": target,
        "score_sum": score,
        "sq_error_sum": error * error,
        "abs_error_sum": F.abs(error),
        "loss_sum": ROW_LOSS_COLUMNS[loss](target, score) if loss else null,
        "target_sq_sum": target * target,
        "link_sum": _logit(score) if loss == "log_loss" else null,
        "scorer": score,
    }


def _clipped(score: Column) -> Column:
    """The score clipped to [`PROBABILITY_CLIP`, 1 − `PROBABILITY_CLIP`]."""
    return F.least(F.greatest(score, F.lit(PROBABILITY_CLIP)), F.lit(1 - PROBABILITY_CLIP))


def _logit(score: Column) -> Column:
    """`ln(p / (1 − p))` of the clipped score, scipy's `logit`; NaN outside [0, 1]."""
    p = _clipped(score)
    return F.when(score.between(0, 1), F.log(p / (1 - p))).otherwise(NAN)


def _log_loss(target: Column, score: Column) -> Column:
    """`−(y·ln p + (1 − y)·ln(1 − p))` on the clipped score; NaN unless the target is 0 or 1 and
    the score in [0, 1]."""
    p = _clipped(score)
    loss = -(target * F.log(p) + (1 - target) * F.log1p(-p))
    return F.when(target.isin(0, 1) & score.between(0, 1), loss).otherwise(NAN)


def _tweedie_deviance(target: Column, score: Column) -> Column:
    """The unit Tweedie deviance at `TWEEDIE_METRIC_POWER` p, `2·(y^(2−p) / ((1−p)(2−p)) −
    y·μ^(1−p) / (1−p) + μ^(2−p) / (2−p))`; NaN unless y ≥ 0 and μ > 0."""
    p = TWEEDIE_METRIC_POWER
    deviance = 2 * (
        F.pow(target, 2 - p) / ((1 - p) * (2 - p))
        - target * F.pow(score, 1 - p) / (1 - p)
        + F.pow(score, 2 - p) / (2 - p)
    )
    return F.when((target >= 0) & (score > 0), deviance).otherwise(NAN)


def _poisson_deviance(target: Column, score: Column) -> Column:
    """The unit Poisson deviance `2·(y·ln(y / μ) − y + μ)`, the log term 0 at y = 0; NaN unless
    y ≥ 0 and μ > 0 (Spark's `log` of a non-positive number is null, never an error)."""
    log_term = F.when(target == 0, F.lit(0.0)).otherwise(target * F.log(target / score))
    deviance = 2 * (log_term - target + score)
    return F.when((target >= 0) & (score > 0), deviance).otherwise(NAN)


# `ROW_LOSSES` as Spark columns. Not shared with it: those take numpy arrays (scipy's `xlogy`,
# `np.clip`) and refuse a row outside the domain at once, which a lazy column cannot; a test
# compares the two per loss (`test_evaluation_tables.py`)
ROW_LOSS_COLUMNS = {
    "log_loss": _log_loss,
    "tweedie_deviance": _tweedie_deviance,
    "poisson_deviance": _poisson_deviance,
}


def _check_cells(cells: pd.DataFrame, column: str, loss: str | None, edge_count: int) -> None:
    """On replicate 0, where every row counts once: fail loud on a part of `PARTS` without a
    cell (the rows are never collected, so nothing earlier notices a test split or a
    validation period without an eligible row with a known target), on rows whose score is
    null or NaN (no bin, or the NaN bucket), and on rows outside the loss's domain."""
    first = cells[cells["replicate"] == 0]
    missing = [part for part in PARTS if part not in set(first["part"])]
    if missing:
        raise ValueError(
            f"the {' and '.join(missing)} part has no scored row: no eligible row with a known "
            "target in the test split's window periods or at the validation period"
        )
    unbinned = first["score_bin"].isna() | (first["score_bin"] > edge_count)
    if unbinned.any():
        raise ValueError(
            f"`{column}` is null or NaN on {int(first.loc[unbinned, 'rows'].sum()):,} scored "
            "rows; a scorer gives every row a number"
        )
    if loss is None:
        return
    sums = ["loss_sum", "link_sum"] if loss == "log_loss" else ["loss_sum"]
    undefined = ~np.isfinite(first[sums].to_numpy(dtype=float)).all(axis=1)
    if undefined.any():
        rows = int(first.loc[undefined, "rows"].sum())
        raise ValueError(
            f"the {loss} of `{column}` is undefined on some of {rows:,} scored rows: the log "
            "loss needs a 0/1 target and a score in [0, 1], a deviance a target >= 0 and a "
            "score > 0"
        )
