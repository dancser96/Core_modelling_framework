"""`compare_runs`: "did it help?" for two evaluated runs of one data definition, read from their
stored scores and run folders alone (evaluation.md → "`compare_runs`", D-141 (h)).

1. Both runs are found, and refused before anything else is read when they are of two data
   definitions, of another than the config's, or not evaluated; then each run folder is opened
   against its contract (`run_artifacts.open_run_folder`), before any Spark work.
2. Their stored scores are joined on their rows, refused unless both scored the same rows, so
   both are measured on identical rows, and each run's score cells are summed on those rows as
   Evaluation sums them: its own bins (`score_edges`), then the `split` cells (`score_cells`).
   A client's bootstrap weights come from a hash of its id and the fixed `WEIGHT_SALT`, so
   replicate k weights it alike in both runs and each replicate's `b − a` is one draw of the
   difference.
3. On the test part both runs' metrics sit side by side, and each metric with a direction
   (the task's `metric_directions`) gets its difference, the percentile interval of the
   replicates' differences (`bootstrap_intervals`) and the word `better`, `worse` or `no clear
   difference`.
4. Validation is reported, never chosen on (D-083): its numbers sit side by side and no
   difference exists for it; `_with_differences` refuses every part but test.
5. Beside them: the features that entered or left, the largest moves in importance rank, and
   each run's budget and seconds per family with its headline on the shared test rows.

Two runs that give every shared row the same score (a run with itself, a rerun reproducible to
the model) share one set of cells, so their differences are exactly 0: two Spark quantile
sketches of one column can differ by their merge order. Nothing is written.
"""

import math
from functools import partial

import pandas as pd
from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F

from core_modelling.artifacts import local_path, read_stage_meta
from core_modelling.config import UseCaseConfig
from core_modelling.config.audit_log import read_resolved_config
from core_modelling.config.identities import data_definition_hash, short
from core_modelling.config.schema import split_budget
from core_modelling.environment import EnvironmentConfig, models_dir
from core_modelling.evaluation.cells import score_cells, score_edges, scorer_loss
from core_modelling.evaluation.scores import SCORES_FOLDER
from core_modelling.evaluation.tables import (
    SUPPORT,
    VALIDATION_TEST_CLIENTS,
    Metric,
    headline_names,
    metric_key,
    part_cells,
)
from core_modelling.run_artifacts import RunFolder, open_run_folder, train_level
from core_modelling.runs import read_run
from core_modelling.sources import KEYS
from core_modelling.statistics.bootstrap import replicate_values
from core_modelling.statistics.score_cells import PARTS, pool_cells
from core_modelling.tasks import TASK_SPECS

RUNS = ("a", "b")  # the roles of `run_a` and `run_b`; a difference is b − a
REPORTED_PARTS = ("validation", VALIDATION_TEST_CLIENTS)  # side by side, never differenced
REPORTED_ONLY = "reported, never chosen on"  # the `use` of every validation row (D-083)
UNCLEAR = "no clear difference"  # the difference's interval holds zero
NOT_AVAILABLE = "not available"  # the difference's verdict when `reason` says why there is none
NO_DIFFERENCE = "undefined on the shared rows or in a replicate"  # e.g. no row loss in one run
IMPORTANCE_ROWS = 10  # the largest moves in importance rank shown
COMPARED = ("split", "target", "score")  # the scores' columns each run's side keeps
ROWS_COLUMNS = ["part", "rows_a", "rows_b", "shared", "scored_differently"]
SIDE_COLUMNS = ["part", "metric", "value_a", "low_a", "high_a", "value_b", "low_b", "high_b",
                "rows", "events"]  # fmt: skip
DIFFERENCE_COLUMNS = ["part", "metric", "better_when", "difference", "low", "high", "verdict",
                      "reason"]  # fmt: skip
FEATURE_COLUMNS = ["feature", "contribution_share", "contribution_rank"]


def compare_runs(
    cfg: UseCaseConfig,
    entity: str,
    env: EnvironmentConfig,
    spark: SparkSession,
    run_a: str,
    run_b: str,
) -> dict[str, pd.DataFrame]:
    """Did `run_b` help against `run_a`? Two evaluated runs of the config's data definition on
    `entity`, measured on the rows both scored, the intervals at `evaluation.intervals`.

    Returns small tables by name: `rows` (`ROWS_COLUMNS`, per part), `metrics` (`SIDE_COLUMNS`,
    the test part), `differences` (`DIFFERENCE_COLUMNS`, the test part only), `validation`
    (`SIDE_COLUMNS` and `use`, `REPORTED_ONLY`: the validation part and its test-split clients,
    with no difference), `features` and `importance` (`_feature_changes`) and `budgets`
    (`_budgets`). Each run's cells carry the row loss of its own objective (`scorer_loss`).
    Spark runs one aggregate for the rows, then a quantile sketch and one aggregate per run;
    nothing is collected but counts and cells.
    """
    records = _check_runs(cfg, entity, env, run_a, run_b)
    runs = {role: record["run_id"] for role, record in records.items()}
    folders = {role: models_dir(env, cfg, run) for role, run in runs.items()}
    opened = {role: open_run_folder(folder) for role, folder in folders.items()}
    trained = {role: _training_config(read) for role, read in opened.items()}
    losses = {
        role: scorer_loss(cfg, read.run["training_settings"]["training"]["objective"])
        for role, read in opened.items()
    }
    features = {role: _features(folder) for role, folder in folders.items()}
    scores = {role: f"{folder}/evaluation/{SCORES_FOLDER}" for role, folder in folders.items()}
    shared, rows = _shared_scores(spark, scores)
    alike = bool((rows["scored_differently"] == 0).all()) and losses["a"] == losses["b"]
    cells = _run_cells(shared, cfg, losses, same=alike)
    cell_metrics = TASK_SPECS[cfg.task]["cell_metrics"]
    metrics = {
        role: partial(cell_metrics, base=train_level(opened[role]), has_loss=loss is not None)
        for role, loss in losses.items()
    }
    tables = _compare_cells(cells, metrics, cfg, _incomparable(losses, cfg))
    changes, importance = _feature_changes(features["a"], features["b"])
    budgets = _budgets(opened, trained, tables["metrics"], cfg)
    return {
        "rows": rows,
        **tables,
        "features": changes,
        "importance": importance,
        "budgets": budgets,
    }


def _check_runs(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, run_a: str, run_b: str
) -> dict[str, dict]:
    """Each role's `run.json` (`run_id` in its canonical form, `r007`), once only the two are
    read: a run trained on another entity, two runs of two data definitions (naming both
    hashes), runs of another data definition than the config's, and a run without
    `evaluation/` are refused."""
    named = dict(zip(RUNS, (run_a, run_b), strict=True))
    records = {role: read_run(env, cfg, run) for role, run in named.items()}
    runs = {role: record["run_id"] for role, record in records.items()}
    other = [runs[role] for role in RUNS if records[role]["entity"] != entity]
    if other:
        raise ValueError(
            f"compare_runs: the runs {other} were trained on another entity than {entity!r}"
        )
    hashes = {role: records[role]["data_definition_hash"] for role in RUNS}
    if hashes["a"] != hashes["b"]:
        raise ValueError(
            f"compare_runs: run {runs['a']} is of data definition {short(hashes['a'])} and run "
            f"{runs['b']} of {short(hashes['b'])}: runs of two data definitions score other rows "
            "against other targets and are never compared"
        )
    expected = data_definition_hash(cfg, entity)
    if hashes["a"] != expected:
        raise ValueError(
            f"compare_runs: the runs are of data definition {short(hashes['a'])}, the config's "
            f"on {entity!r} is {short(expected)}: pass the config the runs were trained with"
        )
    for run in runs.values():
        if not (local_path(models_dir(env, cfg, run, "evaluation")) / "evaluation.json").is_file():
            raise ValueError(
                f"compare_runs: run {run} has no evaluation/: run Evaluation on it first "
                f"(run_evaluation(..., run={run!r}), or the CLI's run --stages evaluation "
                f"--run {run})"
            )
    return records


def _shared_scores(spark: SparkSession, paths: dict[str, str]) -> tuple[DataFrame, pd.DataFrame]:
    """The rows both runs scored, lazy, and the `rows` table.

    Receives each role's scores folder (one row per client, period and part); the rows with a
    null target, which the scores keep for the drift reference only, are left out. Returns their
    inner join on the keys and `part`, pruned to the keys, `part`, `split`, `target`, `score_a`
    and `score_b`; and, from one aggregate over their outer join, per part of `PARTS`:
    `rows_a`, `rows_b`, `shared` and `scored_differently` (the shared rows the two runs score
    apart; 0 throughout for one model's scores). `_check_shared` refuses what cannot be
    compared.
    """
    on = [*KEYS, "part"]
    a, b = (
        spark.read.parquet(paths[role])
        .where(F.col("target").isNotNull())
        .select(*on, *[F.col(name).alias(f"{name}_{role}") for name in COMPARED])
        for role in RUNS
    )
    marked = a.withColumn("in_a", F.lit(1)).join(b.withColumn("in_b", F.lit(1)), on=on, how="full")
    both = F.col("in_a").isNotNull() & F.col("in_b").isNotNull()
    counts = marked.groupBy("part").agg(
        F.count("in_a").alias("rows_a"),
        F.count("in_b").alias("rows_b"),
        F.sum(both.cast("int")).alias("shared"),
        *[_differing(name, both).alias(f"{name}_differs") for name in COMPARED],
    )
    rows = _check_shared(counts.toPandas())
    renamed = [F.col(f"{name}_a").alias(name) for name in ("split", "target")]
    shared = a.join(b, on=on, how="inner").select(*on, *renamed, "score_a", "score_b")
    return shared, rows


def _differing(name: str, both: Column) -> Column:
    """The count of the shared rows (`both`) whose `<name>_a` and `<name>_b` differ."""
    return F.sum((both & ~F.col(f"{name}_a").eqNullSafe(F.col(f"{name}_b"))).cast("int"))


def _check_shared(counts: pd.DataFrame) -> pd.DataFrame:
    """The `rows` table (`ROWS_COLUMNS`, one row per part of `PARTS`) from the outer join's
    counts per part (`rows_a, rows_b, shared` and `<column>_differs` per `COMPARED`). Fails
    loud on a shared row whose target or client split differs between the runs (the rows would
    not be the same rows: other data, or another client split, so a test client of one is a
    train client of the other), on a part without a shared row, and on a row only one run
    scored (a source period changed after a run, which reproducibility assumes never happens)."""
    table = counts.set_index("part").reindex(list(PARTS), fill_value=0)
    target, split = int(table["target_differs"].sum()), int(table["split_differs"].sum())
    if target or split:
        raise ValueError(
            f"compare_runs: of the rows both runs scored, {target:,} have another target and "
            f"{split:,} another client split in the two runs: they were evaluated on other data "
            "or trained with another data.split, so they score other rows"
        )
    empty = table.index[table["shared"] == 0].tolist()
    if empty:
        raise ValueError(
            f"compare_runs: the runs share no scored row in the parts {empty} (each run's rows: "
            f"{table.loc[empty, ['rows_a', 'rows_b']].to_dict('index')}): evaluate both at one "
            "validation period, and train both with one data.split"
        )
    partial = table.index[
        (table["shared"] != table["rows_a"]) | (table["shared"] != table["rows_b"])
    ]
    if len(partial):
        raise ValueError(
            f"compare_runs: one run scored rows the other did not in the parts {partial.tolist()} "
            f"({table.loc[partial, ['rows_a', 'rows_b', 'shared']].to_dict('index')}): two runs "
            "of one data definition and split score the same rows, so a source period changed "
            "after a run; evaluate both again on the current data"
        )
    table = table.rename(columns={"score_differs": "scored_differently"}).reset_index()
    return table[ROWS_COLUMNS]


def _run_cells(
    shared: DataFrame, cfg: UseCaseConfig, losses: dict[str, str | None], same: bool
) -> dict[str, dict]:
    """Each role's cells per part (`tables.part_cells`) on the shared rows, as Evaluation sums
    them: the run's own bins (`score_edges` of `score_<role>`), then its `split` cells with its
    own row loss (`losses`). With `same` (every shared row scored alike, one loss), `b` takes
    `a`'s cells and Spark runs for `a` alone."""
    cells: dict[str, dict] = {}
    for role in RUNS:
        if role == "b" and same:
            cells[role] = cells["a"]
            continue
        column = f"score_{role}"
        edges = score_edges(shared, cfg, column)
        split = score_cells(shared, cfg, ["split"], edges, loss=losses[role], column=column)
        cells[role] = part_cells({"all": pool_cells(split, "split"), "split": split})
    return cells


def _incomparable(losses: dict[str, str | None], cfg: UseCaseConfig) -> dict[str, str]:
    """The metrics whose difference is not available, by name, with the reason, decided up
    front from each run's row loss (`scorer_loss` of its own objective): under two losses (one
    Tweedie, one Poisson, say) the metric of the loss sum is another loss in each run, so both
    values are shown side by side and never differenced (D-035)."""
    if losses["a"] == losses["b"]:
        return {}
    keys = TASK_SPECS[cfg.task]["metric_keys"]
    named = {role: losses[role] or "no row loss" for role in RUNS}
    reason = (
        f"run a's row loss is {named['a']} and run b's {named['b']}, each its own objective's: "
        "two losses are never differenced"
    )
    return {keys.get(loss, loss): reason for loss in losses.values() if loss is not None}


def _compare_cells(
    cells: dict[str, dict],
    metrics: dict[str, Metric],
    cfg: UseCaseConfig,
    incomparable: dict[str, str],
) -> dict[str, pd.DataFrame]:
    """`metrics`, `differences` and `validation` from both roles' cells per part
    (`tables.part_cells`) and each role's metric (the task's `cell_metrics` at the run's base):
    one bootstrap pass per part (`replicate_values`). Only the test part's pass computes
    differences (`_with_differences`), for the directed metrics but the `incomparable`
    (`_incomparable`); the reported parts' pass has none to compute (`_both_runs`)."""
    directions = TASK_SPECS[cfg.task]["metric_directions"]
    level, replicates = cfg.evaluation.intervals.level, cfg.evaluation.intervals.replicates
    compared = {name: sign for name, sign in directions.items() if name not in incomparable}
    with_differences = partial(_with_differences, metrics=metrics, directions=compared)
    values, bounds = replicate_values(_stacked(cells, "test"), with_differences, level, replicates)
    reported = []
    for part in REPORTED_PARTS:
        part_values, part_bounds = replicate_values(
            _stacked(cells, part), partial(_both_runs, metrics=metrics), level, replicates
        )
        reported.append(_side_by_side(part_values, part_bounds, part))
    return {
        "metrics": _side_by_side(values, bounds, "test"),
        "differences": _difference_table(values, bounds, directions, incomparable),
        "validation": pd.concat(reported, ignore_index=True).assign(use=REPORTED_ONLY),
    }


def _stacked(cells: dict[str, dict], part: str) -> pd.DataFrame:
    """Both roles' cells of one part over every replicate, stacked, with `run` (the role)."""
    return pd.concat([cells[role][part].assign(run=role) for role in RUNS], ignore_index=True)


def _both_runs(cells: pd.DataFrame, metrics: dict[str, Metric]) -> dict[tuple[str, str], float]:
    """One replicate's metrics of both runs on one part, keyed `(role, name)`: each role's
    metric on the cells whose `run` is that role."""
    run = cells["run"].to_numpy()
    return {
        (role, name): value
        for role in RUNS
        for name, value in metrics[role](cells.loc[run == role]).items()
    }


def _with_differences(
    cells: pd.DataFrame, metrics: dict[str, Metric], directions: dict[str, int]
) -> dict[tuple[str, str], float]:
    """`_both_runs` and, for each metric of `directions` (the task's `metric_directions`), its
    difference b − a under `("difference", name)`. The test part only: validation is
    reported, never chosen on (D-083), so cells of any other part are refused here, whatever
    passes them."""
    parts = sorted(set(cells["part"]))
    if parts != ["test"]:
        raise ValueError(
            f"a difference between two runs is computed on the test part only, never on "
            f"{parts}: validation is reported, never chosen on (D-083)"
        )
    values = _both_runs(cells, metrics)
    differences = {
        ("difference", name): values[("b", name)] - values[("a", name)] for name in directions
    }
    return {**values, **differences}


def _side_by_side(
    values: dict[tuple[str, str], float],
    bounds: dict[tuple[str, str], tuple[float, float]],
    part: str,
) -> pd.DataFrame:
    """One part's metrics of both runs side by side (`SIDE_COLUMNS`), in the task's metric
    order: each run's value and its own interval, and the shared rows' support (`rows`,
    `events`), which is both runs'."""
    names = [name for role, name in values if role == "a" and name not in SUPPORT]
    records = []
    for name in names:
        record = {"part": part, "metric": name}
        for role in RUNS:
            low, high = bounds[(role, name)]
            record |= {f"value_{role}": values[(role, name)], f"low_{role}": low,
                       f"high_{role}": high}  # fmt: skip
        records.append({**record, "rows": values[("a", "rows")], "events": values[("a", "events")]})
    return pd.DataFrame(records, columns=SIDE_COLUMNS)


def _difference_table(
    values: dict[tuple[str, str], float],
    bounds: dict[tuple[str, str], tuple[float, float]],
    directions: dict[str, int],
    incomparable: dict[str, str],
) -> pd.DataFrame:
    """The test part's differences (`DIFFERENCE_COLUMNS`), one row per metric of `directions`:
    b − a on replicate 0, the percentile interval of the replicates' differences and the
    verdict; an `incomparable` metric's row is `NOT_AVAILABLE` with no number and its reason,
    an undefined one's `NO_DIFFERENCE`."""
    records = []
    for name, sign in directions.items():
        record = {"part": "test", "metric": name, "better_when": "higher" if sign > 0 else "lower"}
        if name in incomparable:
            gap = dict.fromkeys(["difference", "low", "high"], math.nan)
            records.append(
                {**record, **gap, "verdict": NOT_AVAILABLE, "reason": incomparable[name]}
            )
            continue
        key = ("difference", name)
        low, high = bounds[key]
        verdict = _verdict(low, high, sign)
        reason = NO_DIFFERENCE if verdict == NOT_AVAILABLE else None
        records.append({**record, "difference": values[key], "low": low, "high": high,
                        "verdict": verdict, "reason": reason})  # fmt: skip
    return pd.DataFrame(records, columns=DIFFERENCE_COLUMNS)


def _verdict(low: float, high: float, direction: int) -> str:
    """`better` or `worse` when the interval of b − a lies on one side of zero, read in the
    metric's `direction` (+1 higher is better, −1 lower is); `UNCLEAR` when it holds zero;
    `NOT_AVAILABLE` when it is undefined. There is no floor: the losses are exact, but each run's
    rank metrics are read on its own score bins, so a `better` or `worse` on the AUC, the
    average precision or the concordance can lie inside the binning's tolerance
    (`score_cells.bin_quantiles`)."""
    if not (math.isfinite(low) and math.isfinite(high)):
        return NOT_AVAILABLE
    if low <= 0 <= high:
        return UNCLEAR
    return "better" if (low > 0) == (direction > 0) else "worse"


def _feature_changes(
    features_a: pd.DataFrame, features_b: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The features that entered or left, and the largest moves in importance rank.

    Receives the two runs' `features` tables (`explain.feature_table`: one row per final
    feature, its test contribution share and rank, 1 the largest). Returns `features`: one row
    per feature of one run only, `feature`, `change` (`entered`: in b only; `left`: in a only),
    then each run's `contribution_share` and `contribution_rank` (null where absent), the
    entered first, each by its rank. And `importance`: the features of both runs whose rank
    moved, at most `IMPORTANCE_ROWS`, the largest move first (ties by b's rank): `feature`,
    both ranks, `rank_change` (b − a; below 0 it rose) and both shares.
    """
    merged = features_a[FEATURE_COLUMNS].merge(
        features_b[FEATURE_COLUMNS], on="feature", how="outer", suffixes=("_a", "_b"),
        indicator=True,
    )  # fmt: skip
    ranks = ["contribution_rank_a", "contribution_rank_b"]
    merged[ranks] = merged[ranks].astype("Int64")
    found = merged.pop("_merge").astype(str)
    change = found.map({"right_only": "entered", "left_only": "left", "both": ""})
    changed = merged.assign(change=change).loc[change != ""]
    features = changed.sort_values(["change", "contribution_rank_b", "contribution_rank_a"])
    kept = merged.loc[found == "both"]
    kept = kept.assign(rank_change=kept[ranks[1]] - kept[ranks[0]])
    moved = kept.loc[kept["rank_change"] != 0].sort_values(ranks[1])
    order = moved["rank_change"].abs().sort_values(ascending=False, kind="stable").index
    importance = moved.loc[order].head(IMPORTANCE_ROWS)
    feature_columns = ["feature", "change", "contribution_share_a", "contribution_rank_a",
                       "contribution_share_b", "contribution_rank_b"]  # fmt: skip
    importance_columns = ["feature", *ranks, "rank_change", "contribution_share_a",
                          "contribution_share_b"]  # fmt: skip
    return (
        features[feature_columns].reset_index(drop=True),
        importance[importance_columns].reset_index(drop=True),
    )


def _features(folder: str) -> pd.DataFrame:
    """A run's `features` table (`explain.feature_table`) read alone, once its
    `evaluation.json` passed the version check and records the table."""
    meta = read_stage_meta(str(local_path(folder) / "evaluation"), "evaluation")
    if "features" not in meta["tables"]:
        raise ValueError(f"{folder}/evaluation holds no features table: rerun Evaluation on it")
    path = local_path(folder) / "evaluation" / "tables" / "features.parquet"
    return pd.read_parquet(path, columns=FEATURE_COLUMNS)


def _training_config(read: RunFolder) -> UseCaseConfig:
    """The config a run was trained with (`training/resolved_config.yml`), read before any Spark
    work so a missing or unreadable one fails first."""
    return read_resolved_config(local_path(read.folder) / "training" / "resolved_config.yml")


def _budgets(
    opened: dict[str, RunFolder],
    trained: dict[str, UseCaseConfig],
    metrics: pd.DataFrame,
    cfg: UseCaseConfig,
) -> pd.DataFrame:
    """Each run's search per family beside its headline on the shared test rows, from each run
    folder as `open_run_folder` read it and the config it was trained with (`trained`).

    One row per run and family, in the run's order: `run`, `family`, `chosen` (the family the
    run kept), `budget_trials` (`split_budget` of the run's resolved config), `budget_seconds`
    (`training.time_budget_s`, each family's; null without one), `trials` and `seconds` (what
    the search spent, `training.json`'s `search`), then `test_<metric>` per headline metric
    (`headline_names`, as the cells name them): the run's value in `metrics`, the test part's
    side-by-side table.
    """
    values = metrics.set_index("metric")
    headline = [metric_key(cfg, name) for name in headline_names(cfg)]
    frames = []
    for role, read in opened.items():
        training, resolved = read.training, trained[role]
        search = pd.DataFrame(training["search"])
        frames.append(pd.DataFrame({
            "run": read.run["run_id"], "family": search["family"],
            "chosen": search["family"] == training["best"]["family"],
            "budget_trials": search["family"].map(split_budget(resolved)),
            "budget_seconds": resolved.training.time_budget_s,
            "trials": search["trials"], "seconds": search["seconds"],
            **{f"test_{name}": values.loc[name, f"value_{role}"] for name in headline},
        }))  # fmt: skip
    return pd.concat(frames, ignore_index=True)
