"""Evaluation's metric tables, read from one scorer's score cells (A92, A96, A98, A102).

`metric_tables` turns the cells `scores.score_cells` collected, one frame per `by` (`all`,
`split`, each stratum), into what the report draws and `evaluation/tables/` stores: every metric
per part, pooled, per period and per stratum level, each with its client-bootstrap interval
(`metrics`); the slices cut inside each period and then added up, their capture, rate and lift
with intervals too, since no formula covers them (`slices`); the curves, the
reliability and the score distribution pooled per part; the strata's list composition at the
decision's slice (`strata`); and the note that the pooled and the per-period ranking differ
(`pooling`, D-098). The parts are `test`, `validation` and `validation_test_clients`, the
validation period's test-split clients from the `split` cells: a train client's earlier periods
were fitted on, so validation on unseen clients alone is reported beside it.

Each part's metrics are one `bootstrap_intervals` pass, and its slices another: the metric runs
per period (or level) on every replicate and returns each scope's values flat
(`_scoped_metrics`, `_slice_values`), so the mean of the periods and the pooled slice get their
intervals from the same draws. Every task choice comes from `tasks.TASK_SPECS`: the cell
metrics, the order metrics (the pooling note's), the reliability's group count and the metrics
a stratum level cannot have. Pure pandas and numpy.
"""

from collections.abc import Callable
from functools import partial

import numpy as np
import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.config.schema import Slices
from core_modelling.statistics.bootstrap import bootstrap_intervals, replicate_values
from core_modelling.statistics.metrics import (
    NAN,
    distribution_table,
    reliability_table,
    slice_metrics,
    slice_rates,
    threshold_table,
)
from core_modelling.statistics.score_cells import MEAN, PARTS, POOLED
from core_modelling.tasks import TASK_SPECS

Metric = Callable[[pd.DataFrame], dict[str, float]]
VALIDATION_TEST_CLIENTS = "validation_test_clients"  # the validation period's test-split clients
CAPTURE_DEPTHS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5)  # the capture view's fixed depths
SLICE_RATES = ("capture", "rate", "lift")  # each slice's rates, each with its interval
SUPPORT = ("rows", "events")  # every row's columns, not metric rows
METRIC_COLUMNS = ["metric", "part", "period", "stratum", "level", "value", "low", "high", "rows",
                  "events", "insufficient"]  # fmt: skip
SLICE_COLUMNS = ["part", "period", "slice", "configured", "rows", "target", "part_rows",
                 "part_target", "capture", "capture_low", "capture_high", "rate", "rate_low",
                 "rate_high", "lift", "lift_low", "lift_high", "unavailable"]  # fmt: skip
STRATA_COLUMNS = ["part", "stratum", "level", "rows", "events", "insufficient", "slice",
                  "list_rows", "population_share", "list_share", "capture",
                  "unavailable"]  # fmt: skip
NO_SLICE = "not available: no slice is configured"


def metric_tables(
    cells: dict[str, pd.DataFrame],
    cfg: UseCaseConfig,
    base: float,
    population: dict[str, int],
    *,
    loss: bool,
) -> dict[str, pd.DataFrame]:
    """One scorer's tables from its score cells over every replicate, keyed by `by`: `all` (as
    `score_cells` returns them with `by=[]`, required), `split` (`by=["split"]`) and each stratum
    variable (`by=[variable]`, its levels already capped). `base` is the unsampled train split's
    rate (regression: its mean), `population` each period label's eligible rows over both splits
    (the frames' `meta["eligible_rows"]`), and `loss` whether the cells carry the scorer's loss sums
    (`scorer_loss(cfg, objective)` is not None for the model; False for a raw feature).

    Returns `metrics` (`METRIC_COLUMNS`), `slices` (`SLICE_COLUMNS`), `curves`, `reliability` and
    `score_distribution` (the `statistics/metrics.py` tables with `part` first), `strata`
    (`STRATA_COLUMNS`) and `pooling` (`part, metric, pooled, mean, differs`).
    """
    _check_request(cells, cfg, population)
    metric = _scorer_metric(cfg, base, loss)
    parts = part_cells(cells)
    first = {part: frame.loc[frame["replicate"] == 0] for part, frame in parts.items()}
    metrics = [_period_metrics(frame, part, metric, cfg) for part, frame in parts.items()]
    slices = [_slices_table(frame, part, cfg, population) for part, frame in parts.items()]
    compositions = []
    for variable in [name for name in cells if name in cfg.strata.variables]:
        level_metrics, composition = _strata_tables(cells[variable], variable, metric, cfg,
                                                    population)  # fmt: skip
        metrics.append(level_metrics)
        compositions.append(composition)
    table = pd.concat(metrics, ignore_index=True)[METRIC_COLUMNS]
    return {
        "metrics": table,
        "slices": pd.concat(slices, ignore_index=True)[SLICE_COLUMNS],
        **_pooled_tables(first, cfg),
        "strata": _concat(compositions, STRATA_COLUMNS),
        "pooling": _pooling_notes(table, TASK_SPECS[cfg.task]["order_metrics"]),
    }


def _check_request(
    cells: dict[str, pd.DataFrame], cfg: UseCaseConfig, population: dict[str, int]
) -> None:
    """Fail loud without `all` cells, on a key that is no `by` Evaluation aggregates, and on a
    period of the cells without its eligible population."""
    unknown = sorted(set(cells) - {"all", "split", *cfg.strata.variables})
    if "all" not in cells or unknown:
        raise ValueError(
            f"metric_tables: the cells are keyed by `all`, `split` and the strata variables, `all` "
            f"required; got {sorted(cells)}"
        )
    missing = sorted(set(cells["all"]["period"]) - set(population))
    if missing:
        raise ValueError(f"metric_tables: no eligible population for the periods {missing}")


def _scorer_metric(cfg: UseCaseConfig, base: float, loss: bool) -> Metric:
    """The task's cell metrics (`TASK_SPECS[task]["cell_metrics"]`) at `base` and `loss`, with
    the scorer's and the target's means (`_with_means`)."""
    cell_metrics = partial(TASK_SPECS[cfg.task]["cell_metrics"], base=base, loss=loss)
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
    """Each part's cells over every replicate: `test` and `validation` from `all` and, with
    `split` cells, `VALIDATION_TEST_CLIENTS` (the validation part's `split == "test"` rows, the
    `split` column dropped). A part without cells fails loud. `compare_runs` reads a run's
    parts through it too."""
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


def _key(scope: str, name: str) -> str:
    """The flat key of a scope's metric; a metric name holds no `|`, so the key is unique."""
    return f"{scope}|{name}"


def _scoped_metrics(
    cells: pd.DataFrame, metric: Metric, column: str, scopes: list[str], names: list[str]
) -> dict[str, float]:
    """One replicate's `metric` per scope, flat for `bootstrap_intervals` (keys `_key`):
    `POOLED` on every cell, `MEAN` the plain mean of the other scopes' values (NaN when one is
    NaN), any other scope on the cells whose `column` holds it, NaN throughout when it has none
    there (none of its clients drawn)."""
    groups = [scope for scope in scopes if scope not in (POOLED, MEAN)]
    labels = cells[column].to_numpy()
    values = {}
    for group in groups:
        chosen = labels == group
        values[group] = metric(cells.loc[chosen]) if chosen.any() else dict.fromkeys(names, NAN)
    if POOLED in scopes:
        values[POOLED] = metric(cells)
    if MEAN in scopes:
        values[MEAN] = {name: float(np.mean([values[g][name] for g in groups])) for name in names}
    return {_key(scope, name): values[scope][name] for scope in scopes for name in names}


def _scope_rows(
    frame: pd.DataFrame,
    metric: Metric,
    column: str,
    scopes: list[str],
    cfg: UseCaseConfig,
    left_out: tuple[str, ...] = (),
) -> pd.DataFrame:
    """One part's long rows per scope and metric (`_scoped_metrics`) but `left_out`: `scope,
    metric, value` (on replicate 0), `low, high` (over replicates 1 … R), `rows, events` (the
    scope's support on replicate 0; the mean's, its periods' sums) and `insufficient` (fewer
    events than `strata.min_events`; the mean's, any of its periods)."""
    names = list(metric(frame.loc[frame["replicate"] == 0]))
    scoped = partial(_scoped_metrics, metric=metric, column=column, scopes=scopes, names=names)
    intervals = cfg.evaluation.intervals
    values, bounds = replicate_values(frame, scoped, intervals.level, intervals.replicates)
    groups = [scope for scope in scopes if scope != MEAN]
    rows = {scope: values[_key(scope, "rows")] for scope in groups}
    events = {scope: values[_key(scope, "events")] for scope in groups}
    short = {scope: events[scope] < cfg.strata.min_events for scope in groups}
    if MEAN in scopes:
        periods = [scope for scope in groups if scope != POOLED]
        rows[MEAN], events[MEAN] = (sum(d[p] for p in periods) for d in (rows, events))
        short[MEAN] = any(short[p] for p in periods)
    records = [
        {"scope": scope, "metric": name, "value": values[_key(scope, name)],
         "low": bounds[_key(scope, name)][0], "high": bounds[_key(scope, name)][1],
         "rows": rows[scope], "events": events[scope], "insufficient": short[scope]}
        for scope in scopes for name in names if name not in (*SUPPORT, *left_out)
    ]  # fmt: skip
    return pd.DataFrame(records)


def _period_metrics(
    frame: pd.DataFrame, part: str, metric: Metric, cfg: UseCaseConfig
) -> pd.DataFrame:
    """One part's metric rows: `POOLED`, each period in order and, over two or more periods,
    `MEAN`; no stratum."""
    periods = sorted(frame["period"].unique())
    scopes = [POOLED, *periods, *([MEAN] if len(periods) > 1 else [])]
    rows = _scope_rows(frame, metric, "period", scopes, cfg)
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
    composition (`_composition`) with each level's support and `insufficient` beside it, for
    `test` and `validation`."""
    if frame[variable].isna().any():
        raise ValueError(f"metric_tables: the stratum {variable!r} has a null level, not a label")
    absent = TASK_SPECS[cfg.task]["strata_absent_metrics"]
    metrics, compositions = [], []
    for part in PARTS:
        cells = frame.loc[frame["part"] == part]
        first = cells.loc[cells["replicate"] == 0]
        by_rows = first.groupby(variable)["rows"].sum().sort_values(ascending=False, kind="stable")
        rows = _scope_rows(cells, metric, variable, list(by_rows.index), cfg, absent)
        rows = rows.rename(columns={"scope": "level"}).assign(part=part, period=POOLED,
                                                              stratum=variable)  # fmt: skip
        support = rows.drop_duplicates("level").set_index("level")[["events", "insufficient"]]
        composition = _composition(first, variable, decision_slice(cfg), population)
        compositions.append(composition.join(support).reset_index(names="level")
                            .assign(part=part, stratum=variable))  # fmt: skip
        metrics.append(rows)
    return pd.concat(metrics, ignore_index=True), pd.concat(compositions, ignore_index=True)


def decision_slice(cfg: UseCaseConfig) -> Slices | None:
    """The list the strata's composition and the explanation cut are read at: `decision.n` for
    a `top_n` decision, else the first configured slice (a `top_pct` before a `top_n`); None
    when none is configured."""
    if cfg.decision.type == "top_n":
        return Slices(top_pct=[], top_n=[cfg.decision.n])
    slices = cfg.evaluation.slices
    if slices.top_pct:
        return Slices(top_pct=slices.top_pct[:1])
    if slices.top_n:
        return Slices(top_pct=[], top_n=slices.top_n[:1])
    return None


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


def _list_by_level(cells: pd.DataFrame, variable: str, depth: float) -> pd.DataFrame:
    """One period's list of its top `depth` rows over the levels of `variable`, indexed by
    level: `rows` and `target_sum` (the level's), `list_rows` and `list_target` (inside the
    list), the cut bin split in proportion to its rows (A96). A NaN `depth` gives NaN lists."""
    per_bin = cells.groupby("score_bin")["rows"].sum().sort_index(ascending=False)
    above = per_bin.cumsum() - per_bin
    inside = cells["score_bin"].map(((depth - above) / per_bin).clip(0, 1)).to_numpy()
    lists = cells.assign(list_rows=cells["rows"] * inside, list_target=cells["target_sum"] * inside)
    sums = ["rows", "target_sum", "list_rows", "list_target"]
    return lists.groupby(variable)[sums].sum(min_count=1)


def _composition(
    first: pd.DataFrame, variable: str, cut: Slices | None, population: dict[str, int]
) -> pd.DataFrame:
    """One part's list composition on replicate 0, indexed by level: the decision's list cut
    inside each period (`slice_metrics`' depth) and split over the levels, the periods added up.
    Columns `slice, rows, list_rows, population_share` (the level's share of the part's rows),
    `list_share` (its share of the list), `capture` (its target inside the list over its
    target; NaN when not positive) and `unavailable`: a list not available in one period (a
    `top_n` above its population) or without a slice is not available, its numbers NaN."""
    lists, label, reason = [], None, "" if cut is not None else NO_SLICE
    for period, cells in first.groupby("period"):
        depth = NAN
        if cut is not None:
            counts = slice_metrics(cells, cut, population[period]).iloc[0]
            label, depth, reason = counts["slice"], counts["rows"], reason or counts["unavailable"]
        lists.append(_list_by_level(cells, variable, depth))
    added = pd.concat(lists).groupby(level=0).sum(min_count=1)
    if reason:
        added[["list_rows", "list_target"]] = NAN
    target = added["target_sum"].where(added["target_sum"] > 0)
    return pd.DataFrame({
        "slice": label, "rows": added["rows"], "list_rows": added["list_rows"],
        "population_share": added["rows"] / added["rows"].sum(),
        "list_share": added["list_rows"] / added["list_rows"].sum(min_count=1),
        "capture": added["list_target"] / target, "unavailable": reason,
    })  # fmt: skip


def _slice_lists(cfg: UseCaseConfig) -> tuple[Slices, Slices]:
    """The configured slices (`decision.n` first for a `top_n` decision, then
    `evaluation.slices`) and the `CAPTURE_DEPTHS` not among them."""
    configured = cfg.evaluation.slices
    top_n = list(configured.top_n)
    if cfg.decision.type == "top_n" and cfg.decision.n not in top_n:
        top_n = [cfg.decision.n, *top_n]
    depths = [depth for depth in CAPTURE_DEPTHS if depth not in configured.top_pct]
    return Slices(top_pct=configured.top_pct, top_n=top_n), Slices(top_pct=depths)


def _slice_rows(
    cells: pd.DataFrame, lists: tuple[Slices, Slices], population: dict[str, int]
) -> pd.DataFrame:
    """One replicate's slices of one part: each slice of `lists` (configured, then the capture
    depths) cut inside each period (`slice_metrics`), then per period and added up over the
    periods (`POOLED`) by `slice_rates`. One row per period and slice: `period, slice`, the
    counts, `capture, rate, lift`, `unavailable` and `configured` (the slice is of the first
    list)."""
    counts = pd.concat(
        [slice_metrics(group, slices, population[period]).assign(period=period, configured=flag)
         for period, group in cells.groupby("period")
         for slices, flag in zip(lists, (True, False), strict=True)],
        ignore_index=True,
    )  # fmt: skip
    # `slice_rates` adds up by label, so a label carrying its period keeps each period apart:
    # one call for every period instead of one per period, on each of the R replicates
    each = slice_rates(counts.assign(slice=counts["period"] + "|" + counts["slice"]))
    each[["period", "slice"]] = each["slice"].str.split("|", n=1, expand=True)
    table = pd.concat([each, slice_rates(counts).assign(period=POOLED)], ignore_index=True)
    flags = dict(zip(counts["slice"], counts["configured"], strict=True))
    return table.assign(configured=table["slice"].map(flags))


def _slice_keys(table: pd.DataFrame) -> list[str]:
    """The flat keys of a slices table's rates, `period|slice|rate`, rate by rate."""
    pairs = list(zip(table["period"], table["slice"], strict=True))
    return [_key(f"{period}|{label}", rate) for rate in SLICE_RATES for period, label in pairs]


def _slice_values(
    cells: pd.DataFrame,
    lists: tuple[Slices, Slices],
    population: dict[str, int],
    periods: list[str],
    keys: list[str],
) -> dict[str, float]:
    """One replicate's capture, rate and lift per period and slice (`_slice_rows`), flat for
    `bootstrap_intervals` under `keys` (`_slice_keys` of replicate 0); NaN throughout when one
    of `periods` has no cells (none of its clients drawn), which would leave the sum short."""
    if set(cells["period"].unique()) != set(periods):
        return dict.fromkeys(keys, NAN)
    table = _slice_rows(cells, lists, population)
    values = np.concatenate([table[rate].to_numpy(dtype=float) for rate in SLICE_RATES])
    return dict(zip(_slice_keys(table), values, strict=True))


def _slices_table(
    frame: pd.DataFrame, part: str, cfg: UseCaseConfig, population: dict[str, int]
) -> pd.DataFrame:
    """One part's slices (`SLICE_COLUMNS`) from its cells over every replicate: replicate 0's
    (`_slice_rows`) with each rate's client-bootstrap interval, `<rate>_low` and `<rate>_high`
    (NaN for a slice not available); `configured` is False for a capture depth no slice asked
    for."""
    configured, depths = _slice_lists(cfg)
    replicate = frame["replicate"].to_numpy()
    first = frame.loc[replicate == 0]
    table = _slice_rows(first, (configured, depths), population)
    keys = _slice_keys(table)
    values = partial(_slice_values, lists=(configured, depths), population=population,
                     periods=sorted(first["period"].unique()), keys=keys)  # fmt: skip
    intervals = cfg.evaluation.intervals
    bounds = bootstrap_intervals(
        frame.loc[replicate > 0], values, intervals.level, intervals.replicates
    )
    ends = np.array([bounds[key] for key in keys]).reshape(len(SLICE_RATES), len(table), 2)
    for i, rate in enumerate(SLICE_RATES):
        table[f"{rate}_low"], table[f"{rate}_high"] = ends[i, :, 0], ends[i, :, 1]
    return table.assign(part=part)


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
