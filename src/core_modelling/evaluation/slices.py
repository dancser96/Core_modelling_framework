"""The slices: the top of a scorer's score read as lists, cut inside each period and added up.

`slices_table` gives one part's slices: the configured ones (`decision.n` first for a `top_n`
decision) and the capture view's fixed depths, each cut inside each period
(`statistics/metrics.py`'s `slice_metrics`) and added up over the periods, its capture, rate
and lift with client-bootstrap intervals, since no formula covers them. `composition` splits the
decision's list (`decision_slice`) over a stratum's levels. Both cut through `cut_slices`, so a
`top_n` above its period's eligible population, or a slice narrower than `MIN_SLICE_BINS` of the
finest score bins of the cells it reads (`narrowest_slice`), is not available, decided from the
declared slice and the population before any number (D-035). `metric_tables` (`tables.py`)
calls both. Pandas and numpy; the score grid is the task's spec.
"""

from functools import partial

import numpy as np
import pandas as pd

from core_modelling.config import UseCaseConfig
from core_modelling.config.schema import Slices
from core_modelling.statistics.bootstrap import bootstrap_intervals
from core_modelling.statistics.metrics import NAN, cut_slices, slice_metrics, slice_rates
from core_modelling.statistics.score_cells import POOLED, narrowest_bin
from core_modelling.tasks import TASK_SPECS

# The narrowest slice read from cells spans this many of its grid's finest bins: from 12 on, the
# measured regression capture error is under half the sampling error (evaluation.md, the table)
MIN_SLICE_BINS = 12
CAPTURE_DEPTHS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5)  # the capture view's fixed depths
SLICE_RATES = ("capture", "rate", "lift")  # each slice's rates, each with its interval
SLICE_COLUMNS = ["part", "period", "slice", "configured", "rows", "target", "part_rows",
                 "part_target", "capture", "capture_low", "capture_high", "rate", "rate_low",
                 "rate_high", "lift", "lift_low", "lift_high", "unavailable",
                 "no_interval"]  # fmt: skip
NO_SLICE = "not available: no slice is configured"
# Why a rate of an available slice has no interval (the bootstrap's undefined replicate)
NO_INTERVAL = ("undefined in some bootstrap replicate, one that drew no client of a period or "
               "none with a positive target in it")  # fmt: skip


def narrowest_slice(grid: list[tuple[float, int]], step: int = 1) -> float:
    """The narrowest share of the rows a slice is read at from cells: `MIN_SLICE_BINS` times the
    finest bin of `grid` at every `step`-th edge (`narrowest_bin`), rounded off float noise so a
    slice declared at exactly that share is read."""
    return round(MIN_SLICE_BINS * narrowest_bin(grid, step), 12)


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
    cells: pd.DataFrame,
    lists: tuple[Slices, Slices],
    population: dict[str, int],
    narrowest: float,
) -> pd.DataFrame:
    """One replicate's slices of one part: each slice of `lists` (configured, then the capture
    depths) cut inside each period (`slice_metrics`, `narrowest` the share `narrowest_slice`
    gives), then per period and added up over the
    periods (`POOLED`) by `slice_rates`. One row per period and slice: `period, slice`, the
    counts, `capture, rate, lift`, `unavailable` and `configured` (the slice is of the first
    list)."""
    counts = pd.concat(
        [slice_metrics(group, slices, population[period], narrowest)
         .assign(period=period, configured=flag)
         for period, group in cells.groupby("period")
         for slices, flag in zip(lists, (True, False), strict=True)],
        ignore_index=True,
    )  # fmt: skip
    each = slice_rates(counts, by=("period", "slice"))
    table = pd.concat([each, slice_rates(counts).assign(period=POOLED)], ignore_index=True)
    flags = dict(zip(counts["slice"], counts["configured"], strict=True))
    return table.assign(configured=table["slice"].map(flags))


def _slice_keys(table: pd.DataFrame) -> list[tuple[str, str, str]]:
    """The keys of a slices table's rates, `(period, slice, rate)`, rate by rate."""
    pairs = list(zip(table["period"], table["slice"], strict=True))
    return [(period, label, rate) for rate in SLICE_RATES for period, label in pairs]


def _slice_values(
    cells: pd.DataFrame,
    lists: tuple[Slices, Slices],
    population: dict[str, int],
    narrowest: float,
    periods: list[str],
    keys: list[tuple[str, str, str]],
) -> dict[tuple[str, str, str], float]:
    """One replicate's capture, rate and lift per period and slice (`_slice_rows`) under `keys`
    (`_slice_keys` of replicate 0), for `bootstrap_intervals`. A period of `periods` without
    cells here (none of its clients drawn) leaves its own rates NaN and the pooled ones too,
    whose sum would be short; the other periods keep theirs."""
    table = _slice_rows(cells, lists, population, narrowest)
    found = np.concatenate([table[rate].to_numpy(dtype=float) for rate in SLICE_RATES])
    complete = set(cells["period"]) == set(periods)
    values = dict.fromkeys(keys, NAN)
    values.update({key: value for key, value in zip(_slice_keys(table), found, strict=True)
                   if complete or key[0] != POOLED})  # fmt: skip
    return values


def _interval_notes(table: pd.DataFrame) -> list[str]:
    """Per row of a slices table, why a rate with a value has no interval (`NO_INTERVAL`, the
    rates named), '' when every rate with a value has one."""
    lacking = pd.DataFrame({
        rate: table[rate].notna() & (table[f"{rate}_low"].isna() | table[f"{rate}_high"].isna())
        for rate in SLICE_RATES
    })  # fmt: skip
    notes = []
    for row in lacking.itertuples(index=False):
        rates = [rate for rate, missing in zip(SLICE_RATES, row, strict=True) if missing]
        notes.append(f"no interval for the {' and '.join(rates)}: {NO_INTERVAL}" if rates else "")
    return notes


def slices_table(
    frame: pd.DataFrame, part: str, cfg: UseCaseConfig, population: dict[str, int]
) -> pd.DataFrame:
    """One part's slices (`SLICE_COLUMNS`) from its cells over every replicate, on the full
    score grid (a slice narrower than `narrowest_slice` of the task's `score_grid` is not
    available): replicate 0's (`_slice_rows`) with each rate's client-bootstrap interval,
    `<rate>_low` and `<rate>_high` (NaN for a slice not available), and `no_interval`
    (`_interval_notes`); `configured` is False for a capture depth no slice asked for."""
    lists, narrowest = _slice_lists(cfg), narrowest_slice(TASK_SPECS[cfg.task]["score_grid"])
    replicate = frame["replicate"].to_numpy()
    first = frame.loc[replicate == 0]
    table = _slice_rows(first, lists, population, narrowest)
    keys = _slice_keys(table)
    values = partial(_slice_values, lists=lists, population=population, narrowest=narrowest,
                     periods=sorted(first["period"].unique()), keys=keys)  # fmt: skip
    intervals = cfg.evaluation.intervals
    bounds = bootstrap_intervals(
        frame.loc[replicate > 0], values, intervals.level, intervals.replicates
    )
    ends = np.array([bounds[key] for key in keys]).reshape(len(SLICE_RATES), len(table), 2)
    for i, rate in enumerate(SLICE_RATES):
        table[f"{rate}_low"], table[f"{rate}_high"] = ends[i, :, 0], ends[i, :, 1]
    return table.assign(part=part, no_interval=_interval_notes(table))[SLICE_COLUMNS]


def _list_by_level(
    cells: pd.DataFrame, variable: str, cut: Slices, population: int, narrowest: float
) -> tuple[pd.DataFrame, pd.Series]:
    """One period's list at `cut` (`cut_slices`) over the levels of `variable`: per level
    `list_rows` and `list_target` inside it (NaN when the list is not available), and the
    cut's row (`slice`, `rows`, `unavailable`)."""
    counts, inside = cut_slices(cells, cut, population, narrowest)
    lists = pd.DataFrame({
        variable: cells[variable].to_numpy(),
        "list_rows": cells["rows"].to_numpy(dtype=float) * inside[0],
        "list_target": cells["target_sum"].to_numpy(dtype=float) * inside[0],
    })  # fmt: skip
    return lists.groupby(variable)[["list_rows", "list_target"]].sum(min_count=1), counts.iloc[0]


def composition(
    first: pd.DataFrame, variable: str, cfg: UseCaseConfig, population: dict[str, int]
) -> pd.DataFrame:
    """One part's list composition from a stratum's replicate-0 cells, indexed by level.

    The decision's list (`decision_slice`) is cut inside each period on the strata's grid
    (`narrowest_slice` at the task's `strata_step`, so a share narrower than `MIN_SLICE_BINS` of
    its finest bins is not available), split over the levels and the periods added up. Columns
    `slice, rows, list_rows, population_share` (the level's share of the part's rows),
    `list_share` (its share of the list), `capture` (its target inside the list over its
    target; NaN when not positive) and `unavailable`: a list not available in one period, or
    without a slice, is not available, its numbers NaN.
    """
    cut = decision_slice(cfg)
    levels = first.groupby(variable)[["rows", "target_sum"]].sum()
    listed = pd.DataFrame(NAN, index=levels.index, columns=["list_rows", "list_target"])
    label, reason = None, NO_SLICE
    if cut is not None:
        spec = TASK_SPECS[cfg.task]
        narrowest = narrowest_slice(spec["score_grid"], spec["strata_step"])
        lists = [_list_by_level(cells, variable, cut, population[period], narrowest)
                 for period, cells in first.groupby("period")]  # fmt: skip
        label = lists[0][1]["slice"]
        reason = max(row["unavailable"] for _, row in lists)  # '' sorts below a reason
        if not reason:
            listed = pd.concat([by_level for by_level, _ in lists]).groupby(level=0).sum()
    target = levels["target_sum"].where(levels["target_sum"] > 0)
    return pd.DataFrame({
        "slice": label, "rows": levels["rows"], "list_rows": listed["list_rows"],
        "population_share": levels["rows"] / levels["rows"].sum(),
        "list_share": listed["list_rows"] / listed["list_rows"].sum(min_count=1),
        "capture": listed["list_target"] / target, "unavailable": reason,
    })  # fmt: skip
