"""Evaluation's metric tables, read from one scorer's score cells.

`metric_tables` turns the cells `cells.score_cells` collected (`all` and `split`, and apart from
them each stratum's) into what the report draws and `evaluation/tables/` stores: every metric
per part, pooled, per period and per stratum level, each with its client-bootstrap interval
(`metrics`; `metric_rows` gives them without the strata, all a baseline needs); the slices
(`slices.slices_table`); the curves, the reliability and the score distribution pooled per
part; the strata's list composition at the decision's slice (`slices.composition`, the `strata`
table); and the note that the
pooled and the per-period ranking differ (`pooling`, D-098). The parts are `test`, `validation` and
`validation_test_clients`, the validation period's test-split clients from the `split` cells: a
train client's earlier periods were fitted on, so validation on unseen clients alone is reported
beside it.

Each part's metrics are one `replicate_values` pass: the metric runs per period (or level) on
every replicate and returns each group's values keyed `(group, name)` (`_scoped_metrics`), so
the mean of the periods gets its interval from the same draws. The pooled row and the mean are
flags of the call, never read from a label, so a stratum level named `pooled` or `mean` is a
level like any other. Every task choice comes from `tasks.TASK_SPECS`: the cell metrics, the
order metrics (the pooling note's), the reliability's group count and the metrics a stratum
level cannot have. Pure pandas and numpy.
"""

from collections.abc import Callable
from functools import partial

import numpy as np
import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.evaluation.slices import SLICE_COLUMNS, composition, slices_table
from core_modelling.statistics.bootstrap import replicate_values
from core_modelling.statistics.metrics import (
    NAN,
    distribution_table,
    reliability_table,
    threshold_table,
)
from core_modelling.statistics.score_cells import MEAN, PARTS, POOLED
from core_modelling.tasks import TASK_SPECS

Metric = Callable[[pd.DataFrame], dict[str, float]]
VALIDATION_TEST_CLIENTS = "validation_test_clients"  # the validation period's test-split clients
SUPPORT = ("rows", "events")  # every row's columns, not metric rows
METRIC_COLUMNS = ["metric", "part", "period", "stratum", "level", "value", "low", "high", "rows",
                  "events", "insufficient"]  # fmt: skip
STRATA_COLUMNS = ["part", "stratum", "level", "rows", "events", "insufficient", "slice",
                  "list_rows", "population_share", "list_share", "capture",
                  "unavailable"]  # fmt: skip


def metric_tables(
    cells: dict[str, pd.DataFrame],
    strata: dict[str, pd.DataFrame],
    cfg: UseCaseConfig,
    base: float,
    population: dict[str, int],
    *,
    loss: str | None,
) -> dict[str, pd.DataFrame]:
    """One scorer's tables from its score cells over every replicate.

    `cells` holds `all` (as `score_cells` returns them with `by=[]`, required) and `split`
    (`by=["split"]`); `strata` each stratum variable's (`by=[variable]`, its levels already
    capped), apart from them, so a variable of any name, `all` too, never stands in for the
    part's cells. `base` is the unsampled train split's rate (regression: its mean),
    `population` each period label's eligible rows over both splits (the frames'
    `meta["eligible_rows"]`), and `loss` the row loss the cells carry (`scorer_loss(cfg,
    objective)` for the model; None for a raw feature).

    Returns `metrics` (`METRIC_COLUMNS`), `slices` (`SLICE_COLUMNS`), `curves`, `reliability` and
    `score_distribution` (the `statistics/metrics.py` tables with `part` first), `strata`
    (`STRATA_COLUMNS`) and `pooling` (`part, metric, pooled, mean, differs`).
    """
    parts = part_cells(cells)
    _check_request(parts, strata, cfg, population)
    metric = _scorer_metric(cfg, base, loss)
    first = {part: frame.loc[frame["replicate"] == 0] for part, frame in parts.items()}
    metrics, compositions = [metric_rows(cells, cfg, base, loss=loss)], []
    for variable, frame in strata.items():
        level_metrics, composed = _strata_tables(frame, variable, metric, cfg, population)
        metrics.append(level_metrics)
        compositions.append(composed)
    table = pd.concat(metrics, ignore_index=True)[METRIC_COLUMNS]
    slices = [slices_table(frame, part, cfg, population) for part, frame in parts.items()]
    return {
        "metrics": table,
        "slices": pd.concat(slices, ignore_index=True)[SLICE_COLUMNS],
        **_pooled_tables(first, cfg),
        "strata": _concat(compositions, STRATA_COLUMNS),
        "pooling": _pooling_notes(table, TASK_SPECS[cfg.task]["order_metrics"]),
    }


def metric_rows(
    cells: dict[str, pd.DataFrame], cfg: UseCaseConfig, base: float, *, loss: str | None
) -> pd.DataFrame:
    """One scorer's metric rows without strata (`METRIC_COLUMNS`), as `metric_tables` gives
    them: per part of `part_cells(cells)`, pooled, per period and their mean, each with its
    interval. All `compare_baselines` reads of a ranking baseline."""
    metric = _scorer_metric(cfg, base, loss)
    rows = [_period_metrics(frame, part, metric, cfg) for part, frame in part_cells(cells).items()]
    return pd.concat(rows, ignore_index=True)[METRIC_COLUMNS]


def _check_request(
    parts: dict[str, pd.DataFrame],
    strata: dict[str, pd.DataFrame],
    cfg: UseCaseConfig,
    population: dict[str, int],
) -> None:
    """Fail loud on strata cells of a variable that is no `strata.variables`, and on a period
    of the parts' cells without its eligible population."""
    unknown = sorted(set(strata) - set(cfg.strata.variables))
    if unknown:
        raise ValueError(f"metric_tables: {unknown} are not among the strata.variables")
    periods = {period for frame in parts.values() for period in frame["period"].unique()}
    missing = sorted(periods - set(population))
    if missing:
        raise ValueError(f"metric_tables: no eligible population for the periods {missing}")


def _scorer_metric(cfg: UseCaseConfig, base: float, loss: str | None) -> Metric:
    """The task's cell metrics (`TASK_SPECS[task]["cell_metrics"]`) at `base`, with the loss
    sums when `loss` names a row loss, and the scorer's and the target's means
    (`_with_means`)."""
    cell_metrics = partial(TASK_SPECS[cfg.task]["cell_metrics"], base=base,
                           has_loss=loss is not None)  # fmt: skip
    return partial(_with_means, metric=cell_metrics)


def _with_means(cells: pd.DataFrame, metric: Metric) -> dict[str, float]:
    """`metric` on the cells with `mean_score` (the scorer's mean, its mean prediction) and
    `mean_target` (the observed rate or mean), which `compare_baselines` sets beside a rate."""
    rows = cells["rows"].to_numpy(dtype=float).sum()
    return {
        **metric(cells),
        "mean_score": cells["score_sum"].to_numpy(dtype=float).sum() / rows,
        "mean_target": cells["target_sum"].to_numpy(dtype=float).sum() / rows,
    }


def part_cells(cells: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Each part's cells over every replicate: `test` and `validation` from `all` (required)
    and, with `split` cells, `VALIDATION_TEST_CLIENTS` (the validation part's `split == "test"`
    rows, the `split` column dropped). Another key, or a part without cells, fails loud.
    `compare_runs` reads a run's parts through it too."""
    if "all" not in cells or set(cells) - {"all", "split"}:
        raise ValueError(f"the cells are keyed by `all` (required) and `split`: {sorted(cells)}")
    every = cells["all"]
    parts = {part: every.loc[every["part"] == part] for part in PARTS}
    if "split" in cells:
        split = cells["split"]
        chosen = (split["part"] == "validation") & (split["split"] == "test")
        named = split.loc[chosen].drop(columns="split").assign(part=VALIDATION_TEST_CLIENTS)
        parts[VALIDATION_TEST_CLIENTS] = named
    empty = [part for part, frame in parts.items() if frame.empty]
    if empty:
        raise ValueError(f"metric_tables: the parts {empty} hold no score cells")
    return parts


def _scoped_metrics(
    cells: pd.DataFrame,
    metric: Metric,
    column: str,
    groups: list[str],
    names: list[str],
    *,
    pooled: bool,
    mean: bool,
) -> dict[tuple[str, str], float]:
    """One replicate's `metric` keyed `(group, name)` for `bootstrap_intervals`: each of
    `groups` on the cells whose `column` holds it (NaN throughout when it has none there, none
    of its clients drawn); with `pooled`, `POOLED` on every cell; with `mean`, `MEAN` the plain
    mean of the groups' values (NaN when one is NaN)."""
    labels = cells[column].to_numpy()
    by_group = {}
    for group in groups:
        chosen = labels == group
        by_group[group] = metric(cells.loc[chosen]) if chosen.any() else dict.fromkeys(names, NAN)
    values = {}
    if pooled:
        values |= {(POOLED, name): value for name, value in metric(cells).items()}
    values |= {(group, name): by_group[group][name] for group in groups for name in names}
    if mean:
        values |= {(MEAN, name): float(np.mean([by_group[g][name] for g in groups]))
                   for name in names}  # fmt: skip
    return values


def _scope_rows(
    frame: pd.DataFrame,
    metric: Metric,
    column: str,
    groups: list[str],
    cfg: UseCaseConfig,
    *,
    pooled: bool,
    mean: bool,
    left_out: tuple[str, ...] = (),
) -> pd.DataFrame:
    """One part's long rows per scope and metric (`_scoped_metrics`) but `left_out`, the scopes
    `POOLED` (with `pooled`), then `groups`, then `MEAN` (with `mean`): `scope, metric, value`
    (on replicate 0), `low, high` (over replicates 1 … R), `rows, events` (the scope's support
    on replicate 0; the mean's, its groups' sums) and `insufficient` (fewer events than
    `strata.min_events`; the mean's, any of its groups)."""
    if (pooled and POOLED in groups) or (mean and MEAN in groups):
        raise ValueError(f"metric_tables: a group is named {POOLED!r} or {MEAN!r}: {groups}")
    names = list(metric(frame.loc[frame["replicate"] == 0]))
    scoped = partial(_scoped_metrics, metric=metric, column=column, groups=groups, names=names,
                     pooled=pooled, mean=mean)  # fmt: skip
    intervals = cfg.evaluation.intervals
    values, bounds = replicate_values(frame, scoped, intervals.level, intervals.replicates)
    supported = [*([POOLED] if pooled else []), *groups]
    rows = {scope: values[(scope, "rows")] for scope in supported}
    events = {scope: values[(scope, "events")] for scope in supported}
    short = {scope: events[scope] < cfg.strata.min_events for scope in supported}
    if mean:
        rows[MEAN], events[MEAN] = (sum(d[g] for g in groups) for d in (rows, events))
        short[MEAN] = any(short[g] for g in groups)
    records = [
        {"scope": scope, "metric": name, "value": values[(scope, name)],
         "low": bounds[(scope, name)][0], "high": bounds[(scope, name)][1],
         "rows": rows[scope], "events": events[scope], "insufficient": short[scope]}
        for scope in [*supported, *([MEAN] if mean else [])]
        for name in names if name not in (*SUPPORT, *left_out)
    ]  # fmt: skip
    return pd.DataFrame(records)


def _period_metrics(
    frame: pd.DataFrame, part: str, metric: Metric, cfg: UseCaseConfig
) -> pd.DataFrame:
    """One part's metric rows: `POOLED`, each period in order and, over two or more periods,
    `MEAN`; no stratum."""
    periods = sorted(frame["period"].unique())
    rows = _scope_rows(frame, metric, "period", periods, cfg, pooled=True, mean=len(periods) > 1)
    return rows.rename(columns={"scope": "period"}).assign(part=part, stratum=None, level=None)


def _strata_tables(
    frame: pd.DataFrame,
    variable: str,
    metric: Metric,
    cfg: UseCaseConfig,
    population: dict[str, int],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One stratum variable's metric rows (pooled per part and level, levels by rows on
    replicate 0, largest first; without the task's `strata_absent_metrics`) and its list
    composition (`slices.composition`) with each level's support and `insufficient` beside it,
    for `test` and `validation`. Each level is a group of its own: neither pooled nor a mean."""
    if frame[variable].isna().any():
        raise ValueError(f"metric_tables: the stratum {variable!r} has a null level, not a label")
    absent = TASK_SPECS[cfg.task]["strata_absent_metrics"]
    metrics, compositions = [], []
    for part in PARTS:
        cells = frame.loc[frame["part"] == part]
        first = cells.loc[cells["replicate"] == 0]
        by_rows = first.groupby(variable)["rows"].sum().sort_values(ascending=False, kind="stable")
        rows = _scope_rows(cells, metric, variable, list(by_rows.index), cfg, pooled=False,
                           mean=False, left_out=absent)  # fmt: skip
        rows = rows.rename(columns={"scope": "level"}).assign(part=part, period=POOLED,
                                                              stratum=variable)  # fmt: skip
        support = rows.drop_duplicates("level").set_index("level")[["events", "insufficient"]]
        composed = composition(first, variable, cfg, population)
        compositions.append(composed.join(support).reset_index(names="level")
                            .assign(part=part, stratum=variable))  # fmt: skip
        metrics.append(rows)
    return pd.concat(metrics, ignore_index=True), pd.concat(compositions, ignore_index=True)


def pooled_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    """The metric rows without a stratum, pooled over each part's periods (`stratum` null and
    `period == POOLED`), in the `metrics` table's columns."""
    return metrics.loc[metrics["stratum"].isna() & (metrics["period"] == POOLED)]


def headline_names(cfg: UseCaseConfig) -> list[str]:
    """The headline metrics: the decision's metric and the task's first order metric (AUC, or
    the concordance in regression), each once."""
    return list(dict.fromkeys([cfg.decision.metric, TASK_SPECS[cfg.task]["order_metrics"][0]]))


def metric_key(cfg: UseCaseConfig, name: str) -> str:
    """A metric's name in the `metrics` table: the task's `metric_keys` where they differ (the
    regression deviances are `deviance`), else the name itself."""
    return TASK_SPECS[cfg.task]["metric_keys"].get(name, name)


def _pooled_tables(first: dict[str, pd.DataFrame], cfg: UseCaseConfig) -> dict[str, pd.DataFrame]:
    """`curves` (`threshold_table`), `reliability` and `score_distribution` of each part's
    replicate-0 cells pooled over its periods, stacked with `part` first."""
    spec = TASK_SPECS[cfg.task]
    makers = {
        "curves": partial(threshold_table, roc=spec["roc_curve"]),
        "reliability": partial(reliability_table, groups=spec["reliability_groups"]),
        "score_distribution": partial(distribution_table, target_class=spec["target_class"]),
    }
    return {
        name: pd.concat({part: make(cells) for part, cells in first.items()}, names=["part"])
        .reset_index(level="part")
        .reset_index(drop=True)
        for name, make in makers.items()
    }


def _pooling_notes(metrics: pd.DataFrame, order: tuple[str, ...]) -> pd.DataFrame:
    """Per part with a `MEAN` row and per order metric (`order`): the pooled value beside the
    mean of the periods' values, `differs` when their intervals do not overlap: the base rate
    moved inside the window and the per-period values are the ones to read (D-098 item 3);
    False when an interval is undefined."""
    plain = metrics.loc[metrics["stratum"].isna() & metrics["metric"].isin(order)]
    pooled, mean = (
        plain.loc[plain["period"] == period].set_index(["part", "metric"])[["value", "low", "high"]]
        for period in (POOLED, MEAN)
    )
    both = pooled.join(mean, lsuffix="_pooled", rsuffix="_mean", how="inner")
    differs = (both["high_pooled"] < both["low_mean"]) | (both["high_mean"] < both["low_pooled"])
    out = pd.DataFrame({"pooled": both["value_pooled"], "mean": both["value_mean"],
                        "differs": differs})  # fmt: skip
    return out.reset_index()


def _concat(frames: list[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
    """The frames stacked in `columns`; an empty frame with them when there are none."""
    if not frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True)[columns]
