"""`run_eda`: the EDA stage for one entity, in the order of docs/components/eda.md "How one run
flows".

It resolves the config (the audit log replayed, D-125), builds the frames (the snapshot
collected, `rows` left in Spark and persisted for the counts passes of `dataset/counts.py`),
checks the strata and the listed key features against the snapshot (requirement 12), computes
the tables with `ranking.py`, `population.py`, `slices.py`, `profile.py` and `deep_dives.py`
and the association on the snapshot, creates a fresh ledger with EDA's columns, turns
everything into views and renders the report (`report.py`) before anything is written, then
writes in the order that makes `eda.json` the commit marker: Feature Checks' stale folder
removed, the ledger saved, `eda/` written with `report.html` in it (D-136). It orchestrates
only; every statistic lives in the modules it calls. EDA informs and never changes data: it
drops no row and no feature and writes no audit-log entry.
"""

import time
from datetime import date

import numpy as np
import pandas as pd
from pyspark.sql import DataFrame, SparkSession

from core_modelling.artifacts import StageResult, remove_stage, settings_meta, write_stage
from core_modelling.config import UseCaseConfig
from core_modelling.config.audit_log import resolve_config, show_decisions
from core_modelling.dataset import Frames, build_frames
from core_modelling.dataset.counts import (
    bin_edges,
    client_constant_shares,
    count_cells,
    count_lagged_cells,
    estimate_cells,
    window_clients,
    window_levels,
)
from core_modelling.eda.deep_dives import (
    BOX_COLUMNS,
    bin_table,
    dive_group_count,
    level_table,
    per_period_concordance,
    quartiles_by_target,
    strata_pivots,
    target_quartiles_by_group,
)
from core_modelling.eda.population import (
    funnel_per_period,
    headline_numbers,
    is_numeric,
    known_rows,
    reference_groups,
    sources_per_period,
    strata_frame,
    strata_tables,
    target_per_period,
)
from core_modelling.eda.profile import value_profile
from core_modelling.eda.ranking import (
    count_levels,
    encoding_prior_rows,
    feature_statistics,
    rank_features,
    select_key_features,
)
from core_modelling.eda.report import build_views, eda_warnings, report_sections
from core_modelling.eda.slices import slice_shares, slice_tables
from core_modelling.environment import EnvironmentConfig, feature_dir
from core_modelling.ledger import COLUMNS_BY_STAGE, add_columns, create_ledger, save_ledger
from core_modelling.periods import period_spec
from core_modelling.reporting.html import render_report
from core_modelling.sources import HELPER_COLUMNS, KEYS
from core_modelling.statistics.association import association_table, pairwise_sample
from core_modelling.tasks import TASK_SPECS

# EDA's digest, which Feature Checks checks; the validation period decides the compared periods
# and the population counts yet is outside the data-definition hash (D-088).
SETTINGS_PATHS = ["features.kinds", "strata", "eda", "time.validation_period"]
HOUSEKEEPING_KEYS = ("entity", "config_hash", "data_definition_hash", "resolved_input_hash",
                     "hash_version", "replayed_to")  # fmt: skip
FRAMEWORK_COLUMNS = [*KEYS, *HELPER_COLUMNS]  # added by the framework; never a stratum
# The stacked deep-dive tables' columns, so an empty one (no key feature of that kind) keeps its
# schema within a task; the group tables add the task's summary columns (`_dive_columns`).
DIVE_COLUMNS = {
    "bins": ["feature", "group"],
    "levels": ["feature", "group"],
    "quartiles": ["feature", "target_class", *BOX_COLUMNS, "skew"],
    "per_period": ["feature", "period", "rows", "support", "concordance", "se", "insufficient",
                   "unavailable"],
    "target_quartiles": ["feature", "group", *BOX_COLUMNS, "skew"],
}  # fmt: skip


def run_eda(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession
) -> StageResult:
    """EDA for one entity: the tables, the ledger, the views and `eda/` with `report.html`
    written under the data definition's folder; the result carries the collected snapshot and
    the resolved config (D-137)."""
    seconds: dict[str, float] = {}
    start = time.perf_counter()
    resolved = resolve_config(cfg, entity, env)
    frames = build_frames(resolved, entity, env, spark, "eda")
    _check_frame_names(resolved, frames)
    labels, window = _compared_periods(resolved, frames.log)
    seconds["frames"], start = _lap(start)
    rows = frames.rows.persist()
    try:
        counts = _count_tables(rows, frames, resolved, window)
    finally:
        rows.unpersist()
    seconds["passes"], start = _lap(start)
    ranking, correlation, prior_rows, extra = _rank(counts, frames, resolved, labels)
    seconds["statistics"], start = _lap(start)
    meta = _stage_meta(resolved, frames, counts, ranking, labels)
    tables = _population_tables(frames, resolved, counts, labels, ranking)
    tables.update(cells=counts["cells"], client_constant=counts["client_constant"])
    tables.update(ranking=ranking, correlation=correlation)
    window = meta["compared_periods"]["window"]
    tables["slices"], tables["capture_curve"] = slice_tables(counts["cells"], ranking, meta,
                                                             resolved, window)  # fmt: skip
    tables["profile"] = value_profile(frames.snapshot, frames.meta["kinds"], ranking,
                                      counts["cells"], meta["snapshot_period"])  # fmt: skip
    keys = ranking.loc[ranking["key_feature"] != ""].iterrows()
    dives = [_deep_dive(key, counts, frames, resolved, labels, prior_rows) for _, key in keys]
    tables.update(_dive_tables(dives, resolved.task))
    seconds["tables"], start = _lap(start)
    ledger = _ledger(frames.meta, ranking)
    meta["warnings"] = eda_warnings(tables, frames.log, resolved, meta["snapshot_period"])
    headline = headline_numbers(frames.snapshot, tables["target_per_period"], resolved.task)
    meta["headline"] = {name: None if pd.isna(value) else value for name, value in headline.items()}
    meta["timings"] = {"seconds": seconds, "cells_estimate": counts["estimate"], **extra}
    views = build_views(tables, meta, resolved, ledger, show_decisions(cfg, entity, env))
    result = StageResult(tables=tables, ledger=ledger, log=frames.log, meta=meta, paths={},
                         views=views, frame=frames.snapshot, config=resolved)  # fmt: skip
    _write(result, env, entity)
    return result


def _lap(start: float) -> tuple[float, float]:
    """The seconds since `start`, rounded, and the new start."""
    now = time.perf_counter()
    return round(now - start, 2), now


def _check_frame_names(resolved: UseCaseConfig, frames: Frames) -> None:
    """Refuse, once the snapshot exists (requirement 12): a stratum that is no snapshot column or
    is one the framework adds, a modelling tag (constant on the eligible rows), a numeric stratum
    with more than `strata.max_levels` distinct values, and a listed key feature that is no
    supported candidate."""
    snapshot, kinds, strata = frames.snapshot, frames.meta["kinds"], resolved.strata
    columns = [column for column in snapshot.columns if column not in FRAMEWORK_COLUMNS]
    refused = [name for name in strata.variables if name not in columns]
    if refused:
        raise ValueError(
            f"strata.variables names {refused}, which are not snapshot columns or are columns the "
            f"framework adds (a lineage or unsupported column is dropped; a source column named "
            f"like a framework column is read as 'source_<name>', e.g. 'source_{refused[0]}'); "
            f"the snapshot's columns: {columns}"
        )
    tags = [name for name in strata.variables if name in frames.meta["tags"]]
    if tags:
        raise ValueError(
            f"strata.variables names the modelling tags {tags}, which are 1 on every eligible "
            "row: their two sides are compared under the report's reference groups"
        )
    numeric = [name for name in strata.variables if is_numeric(snapshot[name], kinds.get(name))]
    wide = {name: int(snapshot[name].nunique()) for name in numeric}
    wide = {name: count for name, count in wide.items() if count > strata.max_levels}
    if wide:
        raise ValueError(
            f"the numeric strata {wide} have more distinct values than strata.max_levels = "
            f"{strata.max_levels}: bin it upstream or list the levels"
        )
    unknown = sorted(set(resolved.eda.key_features.include) - set(kinds))
    if unknown:
        raise ValueError(
            f"eda.key_features.include names {unknown}, which are not supported candidates "
            "(features.candidates minus the lineage and the unsupported columns)"
        )


def _compared_periods(
    resolved: UseCaseConfig, log: list[dict]
) -> tuple[dict[str, object], list[date]]:
    """The compared periods' labels by group (the frames' `compared_periods` entry), and the
    window periods the panel holds as dates, which the passes take."""
    entry = next((item for item in log if item["step"] == "compared_periods"), None)
    if entry is None:
        raise ValueError(
            'the frames\' log has no `compared_periods` entry, which build_frames(..., "eda") '
            "writes: build the frames for the eda stage"
        )
    spec, window = period_spec(resolved), resolved.time.observation_window
    indices = range(spec.index(window.first), spec.index(window.last) + 1)
    dates = [spec.from_index(i) for i in indices]
    labels = {group: entry[group] for group in ("window", "gap", "latest")}
    return labels, [period for period in dates if spec.label(period) in labels["window"]]


def _count_tables(
    rows: DataFrame, frames: Frames, resolved: UseCaseConfig, window: list[date]
) -> dict:
    """The Spark side over the persisted `rows` (eda.md steps 4–6): the cell estimate, the edges,
    the window levels, the target bins, the cells of both passes, the client-constant table and
    the window's clients."""
    kinds, snapshot, bins = frames.meta["kinds"], frames.snapshot, resolved.eda.bins
    estimate = estimate_cells(rows, kinds, bins, window)
    edges = bin_edges(snapshot, kinds, bins)
    categoricals = [name for name, kind in kinds.items() if kind == "categorical"]
    levels, over_ceiling = window_levels(rows, categoricals, window)
    known = known_rows(snapshot)["target"].to_numpy(dtype=float)
    target_edges = TASK_SPECS[resolved.task]["target_bins"](known, exact=bins is None)
    args = (rows, edges, levels, over_ceiling, target_edges, window, period_spec(resolved))
    cells = pd.concat([count_cells(*args), count_lagged_cells(*args)], ignore_index=True)
    return {"estimate": estimate, "edges": edges, "levels": levels, "over_ceiling": over_ceiling,
            "target_edges": target_edges, "cells": cells,
            "client_constant": client_constant_shares(rows, [*edges, *levels], window),
            "clients": window_clients(rows, window)}  # fmt: skip


def _rank(
    counts: dict, frames: Frames, resolved: UseCaseConfig, labels: dict
) -> tuple[pd.DataFrame, pd.DataFrame, float, dict]:
    """The ranking with the key features, the association table, the level encoding's prior rows
    and the timing extras: the association's seconds and the numerics' distinct null masks over
    the rows it reads (what the exact Spearman's cost grows with, T28)."""
    kinds, snapshot, task = frames.meta["kinds"], frames.snapshot, resolved.task
    cells, window, exact = counts["cells"], labels["window"], resolved.eda.bins is None
    prior_rows = encoding_prior_rows(cells, task, resolved.strata.min_events, window)
    levels = count_levels(snapshot, kinds)
    snapshot_period = frames.meta["snapshot_period"]
    stats = feature_statistics(
        cells, kinds, task, snapshot_period, window, counts["clients"], prior_rows, levels, exact
    )
    # The association's own seeded cap, drawn here once, so the null masks are counted on the
    # rows it reads (its cap is then a no-op) and not on the whole snapshot.
    eligible = pairwise_sample(snapshot.loc[snapshot["eligible"] == 1, list(kinds)])
    start = time.perf_counter()
    correlation = association_table(eligible, kinds)
    seconds, _ = _lap(start)
    numerics = [name for name, kind in kinds.items() if kind == "numeric"]
    masks = np.unique(eligible[numerics].isna().to_numpy(), axis=1).shape[1] if numerics else 0
    ranking = select_key_features(rank_features(stats), correlation, resolved.eda.key_features)
    extra = {"association_seconds": seconds, "numeric_null_masks": int(masks)}
    return ranking, correlation, prior_rows, extra


def _population_tables(
    frames: Frames, resolved: UseCaseConfig, counts: dict, labels: dict, ranking: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    """The population views' tables: the D-088 counts, the funnel, the sources' matched shares
    over the compared periods, the target per period, the strata (by stratum, then every key
    feature's pivots) and the reference groups."""
    snapshot, task, strata = frames.snapshot, resolved.task, resolved.strata
    keys = ranking.loc[ranking["key_feature"] != "", "feature"].tolist()
    population = frames.meta["population"]
    by_stratum = strata_tables(snapshot, strata, task)
    pivots = strata_pivots(snapshot, keys, counts["edges"], strata, task)
    return {
        "population": population,
        "funnel": funnel_per_period(frames.log, labels["window"]),
        "sources": sources_per_period(
            frames.log, [*labels["window"], *labels["gap"], *labels["latest"]]
        ),
        "target_per_period": target_per_period(
            population, counts["cells"], task, strata.min_events, counts["clients"]
        ),
        "strata": strata_frame([by_stratum, pivots], task),
        "reference_groups": reference_groups(
            snapshot, frames.meta["tags"], keys, frames.meta["kinds"], strata
        ),
    }


def _deep_dive(
    ranked: pd.Series,
    counts: dict,
    frames: Frames,
    resolved: UseCaseConfig,
    labels: dict,
    prior: float,
) -> dict[str, pd.DataFrame]:
    """One key feature's parts of the stacked tables from its `ranked` row of the ranking:
    `levels` when `dive_group_count` says by level, else `bins`; `per_period` in the window's
    direction; a numeric's `quartiles` by target class; and, when the task's target has a
    distribution, its `target_quartiles` per group."""
    snapshot, task, cells = frames.snapshot, resolved.task, counts["cells"]
    base = known_rows(snapshot)["target"].mean()
    name, kind = ranked["feature"], ranked["kind"]
    edges = counts["edges"].get(name)
    group_count = dive_group_count(kind, ranked["levels"], resolved.strata.max_levels)
    if group_count is None:
        dive = {"levels": level_table(snapshot, name, kind, edges, task, base)}
    else:
        period = frames.meta["snapshot_period"]
        dive = {"bins": bin_table(cells, snapshot, name, edges, period, task, base, group_count)}
    sign = int(ranked["raw_sign_window"])
    args = (labels["window"], prior, resolved.strata.min_events, sign, resolved.eda.bins is None)
    dive["per_period"] = per_period_concordance(cells, name, kind, task, *args)
    if kind == "numeric":
        dive["quartiles"] = quartiles_by_target(snapshot, name, task)
    if TASK_SPECS[task]["target_distribution"]:
        dive["target_quartiles"] = target_quartiles_by_group(
            snapshot, name, kind, edges, group_count
        )
    return dive


def _dive_columns(task: str) -> dict[str, list[str]]:
    """Each stacked deep-dive table's columns for `task`: `DIVE_COLUMNS`, the group tables with
    the task's summary columns, `target_quartiles` only for a task whose target has a
    distribution."""
    spec = TASK_SPECS[task]
    columns = {
        name: [*base, *spec["summary_columns"]] if name in ("bins", "levels") else base
        for name, base in DIVE_COLUMNS.items()
    }
    if not spec["target_distribution"]:
        del columns["target_quartiles"]
    return columns


def _dive_tables(dives: list[dict[str, pd.DataFrame]], task: str) -> dict[str, pd.DataFrame]:
    """The deep dives stacked in rank order; a table without a part keeps its columns
    (`_dive_columns`)."""
    columns = _dive_columns(task)
    stacked = {name: [dive[name] for dive in dives if name in dive] for name in columns}
    return {
        name: pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns[name])
        for name, parts in stacked.items()
    }


def _ledger(meta: dict, ranking: pd.DataFrame) -> pd.DataFrame:
    """A fresh ledger, every candidate then the lineage columns, with EDA's columns; a fresh one
    holds no Feature Checks column (an EDA rerun removes them)."""
    lineage = meta["lineage"]
    names = [*meta["candidates"], *[name for name in lineage if name not in meta["candidates"]]]
    ledger = create_ledger(
        names, meta["kinds"], lineage, list(meta["unsupported"]), meta["column_sources"]
    )
    return add_columns(ledger, ranking[["feature", *COLUMNS_BY_STAGE["eda"]]], "eda")


def _records(table: pd.DataFrame) -> list[dict]:
    """A table as JSON-ready records, a missing value as None (T31)."""
    return table.astype(object).where(table.notna(), None).to_dict("records")


def _stage_meta(
    resolved: UseCaseConfig, frames: Frames, counts: dict, ranking: pd.DataFrame, labels: dict
) -> dict:
    """`eda.json` without the warnings, the headline and the timings: the hashes, the settings
    digest and values, the periods, the D-088 population counts, the window levels, the clients,
    the key features and why, the kinds, the snapshot's base and the slices (label → share of the
    snapshot's labelled rows)."""
    meta, keys = frames.meta, ranking.loc[ranking["key_feature"] != ""]
    skipped = ranking.loc[ranking["represented_by"] != ""]
    known = known_rows(frames.snapshot)
    return {
        **{key: resolved.housekeeping[key] for key in HOUSEKEEPING_KEYS},
        **settings_meta(resolved, SETTINGS_PATHS),
        "snapshot_period": meta["snapshot_period"],
        "compared_periods": labels,
        "population": _records(meta["population"]),
        "window_levels": counts["levels"],
        "over_ceiling": counts["over_ceiling"],
        "clients": counts["clients"],
        "key_features": dict(zip(keys["feature"], keys["key_feature"], strict=True)),
        "represented_by": dict(zip(skipped["feature"], skipped["represented_by"], strict=True)),
        "candidates": meta["candidates"],
        "kinds": meta["kinds"],
        "kind_overrides": resolved.features.kinds,
        "unsupported": meta["unsupported"],
        "lineage": meta["lineage"],
        "collect": meta["collect"],
        "snapshot_base": float(known["target"].mean()),
        "slices": slice_shares(resolved, len(known)),
    }


def _write(result: StageResult, env: EnvironmentConfig, entity: str) -> None:
    """Render the report, then write in the commit order: Feature Checks' folder removed (its
    judgement is stale), the ledger saved, `eda/` written with `report.html` in it (`eda.json`
    is the commit marker). A render error (a Styler fails only when rendered) leaves the
    previous run's files as they were."""
    resolved, meta = result.config, result.meta
    page = render_report(f"EDA: {resolved.use_case} ({entity})", report_sections(result.views))
    remove_stage(feature_dir(env, resolved, entity, "feature_checks"))
    sidecar = {"stage": "eda", "data_definition_hash": meta["data_definition_hash"],
               "settings_digest": meta["settings_digest"]}  # fmt: skip
    save_ledger(result.ledger, feature_dir(env, resolved, entity), sidecar)
    folder = feature_dir(env, resolved, entity, "eda")
    result.paths = write_stage(result, folder, "eda", texts={"report.html": page})
