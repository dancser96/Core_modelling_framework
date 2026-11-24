"""`run_evaluation`: the Evaluation stage for one trained run, in the order of
docs/components/evaluation.md "How one run flows".

1. Resolve the config, check `evaluation.skip_views` and find the run (`find_run`: the latest
   of this data definition, or the one named; another data definition is refused before
   anything is read; newer runs passed over become a warning). Refuse, before any Spark work,
   what would fail only at the end: a leftover of an unfinished write beside `evaluation/` and
   a run folder that breaks the run folder's contract. The run folder is read once
   (`check_card_inputs`, through `run_artifacts.open_run_folder`: the bundle with its hash
   checked, `run.json` with the run's objective, `training.json`, the per-run ledger, the run's
   own `stage2/` copy, each against the contract), then the Training tables the report draws.
2. Build the evaluation rows with the bundle's features and the baselines' columns, add the
   baselines' score columns, score inside Spark and write the scores table beside `evaluation/`;
   every later step reads it back, so nothing is scored twice. The test part's rows with a null
   target are scored and kept for the drift reference only.
3. On the rows with a known target: the model's score cells (per split and pooled, and apart
   from them per stratum), its metric tables with intervals, each ranking baseline's metric
   rows on its own cells, and the baselines comparison.
4. The drift reference from every scored test row and the `stage2/` copy, written with its
   sidecar (`_drift_reference.json`: its version, the run and the model hash).
5. The explanation tables on seeded test samples: contributions, the feature table,
   permutation importance per redundancy cluster, partial dependence and ICE, and the effects
   beside EDA's lift; beside them Training's tables the report draws, so `evaluation/` renders
   alone.
6. Write `evaluation/` whole (its json, assembled by `meta.py`, tables, the report from
   `views.py` and `views_explain.py`, the model card from `evaluation/card.py`, and the scores
   table), then the audit log's `run` entry with the validation period it scored.

It orchestrates only: every statistic is in the modules it calls. Nothing here is fitted or
chosen on test or validation (`CLAUDE.md` §4.4): the single feature comes from the per-run
ledger, the skill scores' base from train. A rerun replaces `evaluation/` and never touches
`training/`, `bundle/` or the per-run ledger.
"""

import json
import shutil
import time
from dataclasses import dataclass
from functools import partial

import pandas as pd
from pyspark.sql import DataFrame, SparkSession

from core_modelling.artifacts import StageResult, check_siblings, lap, local_path, write_stage
from core_modelling.config import UseCaseConfig
from core_modelling.config.audit_log import (
    load_entries,
    record_stage_entry,
    resolve_config,
    show_decisions,
)
from core_modelling.config.identities import short
from core_modelling.dataset import Frames, build_frames
from core_modelling.environment import EnvironmentConfig, models_dir
from core_modelling.evaluation.baselines import (
    add_baselines,
    baseline_columns,
    baseline_loss,
    carried_columns,
    choose_single_feature,
    compare_baselines,
    describe_baseline_columns,
)
from core_modelling.evaluation.card import build_card, check_card_inputs
from core_modelling.evaluation.cells import (
    reference_score_counts,
    score_cells,
    score_edges,
    scorer_loss,
)
from core_modelling.evaluation.drift_reference import (
    DRIFT_REFERENCE_FILE,
    build_drift_reference,
    drift_reference_sidecar,
)
from core_modelling.evaluation.effects import EFFECTS, effect_features, effect_table, key_features
from core_modelling.evaluation.explain import (
    ALL_NULL,
    all_null_features,
    collect_explanation_sample,
    compute_contributions,
    contribution_shares,
    encoding_shares,
    explanation_cut,
    feature_table,
    partial_dependence,
    sampled_rows,
)
from core_modelling.evaluation.meta import Opened, build_result
from core_modelling.evaluation.permutation import (
    PERMUTATION_COLUMNS,
    permutation_importance,
    permutation_unavailable,
)
from core_modelling.evaluation.report import check_skip_views, render_views
from core_modelling.evaluation.scores import SCORES_FOLDER, score_parts, write_scores
from core_modelling.evaluation.tables import metric_rows, metric_tables
from core_modelling.reporting.card import render_card
from core_modelling.run_artifacts import (
    CARRIED_TABLES,
    RunFolder,
    read_in_sample,
    read_training_tables,
    train_level,
)
from core_modelling.runs import find_run
from core_modelling.statistics.losses import metric_loss
from core_modelling.statistics.metrics import binned_concordance
from core_modelling.statistics.score_cells import pool_cells

RUN_REASON = "Evaluation scored this run on its test clients and the validation period."
# The drift reference's tables are stored beside the feature table, whose name `features`
# they would otherwise share
DRIFT_PREFIX = "drift_"
KNOWN_TARGET = "target IS NOT NULL"  # the rows every metric, slice and baseline reads; a string,
# since a module-level Column needs a live SparkContext


@dataclass
class Request:
    """What `run_evaluation` was called with, as the audit log and the frames read it: the
    config as given, the entity and the environment."""

    cfg: UseCaseConfig
    entity: str
    env: EnvironmentConfig


def run_evaluation(
    cfg: UseCaseConfig,
    entity: str,
    env: EnvironmentConfig,
    spark: SparkSession,
    run: str | None = None,
) -> StageResult:
    """Evaluate one trained run for one entity: `run` names it (`r007`), else the latest trained
    run of the config's data definition. Writes `<use_case>/06_models/<run>/evaluation/` whole,
    then the audit log's `run` entry; returns the result, whose meta is `evaluation.json` and
    whose ledger is the run's per-run ledger, unchanged.

    The scores table is written by Spark beside `evaluation/` before the tables are computed and
    moved in with them; a failure before `write_stage` commits removes it and leaves the run as
    it was. When the audit log's entry fails after the commit, `evaluation/` stays written whole
    without its `run` entry; Evaluation run again replaces it and records the entry. The meta's
    `timings.seconds` holds each phase's seconds up to the card; the write's are printed.
    """
    request, seconds, clock = Request(cfg, entity, env), {}, time.perf_counter()
    opened = _open_run(request, run)
    seconds["open"], clock = lap(clock)
    frames, staged, facts = _score_rows(opened, request, spark)
    seconds["scoring"], clock = lap(clock)
    try:
        scores = spark.read.parquet(staged)
        tables, in_sample = _scorer_tables(opened, scores, facts, frames.meta["eligible_rows"])
        seconds["tables"], clock = lap(clock)
        cut = explanation_cut(tables["slices"], tables["curves"], opened.resolved)
        explained, entry, decided = _explanation_tables(
            opened, frames.rows.where(KNOWN_TARGET), scores.where(KNOWN_TARGET), env, cut
        )
        seconds["explanation"], clock = lap(clock)
        frames.log.append(entry)
        tables = _merge_tables(tables, explained, opened.trained)
        result = build_result(opened, frames, tables, decided, in_sample, env, seconds)
        seconds["views"], clock = lap(clock)
        card = build_card(opened.folder, result.tables, result.meta, opened.resolved, opened.read)
        seconds["card"], clock = lap(clock)
        result.meta["summary"]["seconds"] = round(sum(seconds.values()), 1)
        _write(result, request, opened, staged, card)
        print(f"  written in {lap(clock)[0]:.1f} seconds")
    except BaseException as error:
        _discard(staged, error)
        raise
    return result


def _open_run(request: Request, run: str | None) -> Opened:
    """Step 1: the config resolved and its skipped views checked, the run found (a run of
    another data definition refused first, naming both hashes; the newer runs passed over kept
    for a warning), a leftover beside `evaluation/` refused, the run folder read and checked
    once against its contract (`check_card_inputs`), Training's tables the report draws read,
    the single feature chosen from the ledgers and the train level taken (`train_level`)."""
    resolved = resolve_config(request.cfg, request.entity, request.env)
    check_skip_views(resolved)
    run_id, passed_over = find_run(request.env, resolved, request.entity, run)
    folder = models_dir(request.env, resolved, run_id)
    evaluation = local_path(models_dir(request.env, resolved, run_id, "evaluation"))
    check_siblings(evaluation, "evaluation", {}, (SCORES_FOLDER,))
    read = check_card_inputs(folder, resolved)
    tables = read_training_tables(read, CARRIED_TABLES.values())
    trained = {stored: tables[name] for stored, name in CARRIED_TABLES.items()}
    settings = read.run["training_settings"]
    single = choose_single_feature(read.run_ledger, read.stage2["ledger"],
                                   settings["features.order"])  # fmt: skip
    choice = {"features": read.bundle.features, "single_feature": single}
    print(
        f"evaluating {run_id} of {resolved.use_case} on {request.entity}: "
        f"{len(read.bundle.features)} features, model {short(read.bundle.model_hash)}"
    )
    entries = load_entries(resolved, request.entity, request.env)
    return Opened(resolved, entries, run_id, passed_over, folder, read, trained,
                  settings["training"]["objective"], train_level(read), choice)  # fmt: skip


def _score_rows(
    opened: Opened, request: Request, spark: SparkSession
) -> tuple[Frames, str, dict[str, dict[str, float]]]:
    """Step 2: the evaluation frames with the bundle's features and the baselines' columns, the
    column baselines' facts on the rows with a known target (before `add_baselines` replaces
    the columns), every row scored in Spark, the test part's null-target rows too, and written
    beside `evaluation/` (`write_scores`). Returns the frames, the staged scores' path and the
    facts."""
    resolved, choice, env = opened.resolved, opened.choice, request.env
    frames = build_frames(resolved, request.entity, env, spark, "evaluation",
                          features=opened.read.bundle.features,
                          carry=carried_columns(resolved, choice))  # fmt: skip
    facts = describe_baseline_columns(frames.rows.where(KNOWN_TARGET), resolved)
    rows = add_baselines(frames.rows, resolved, choice)
    baselines = list(baseline_columns(resolved, choice).values())
    bundle_folder = models_dir(env, resolved, opened.run, "bundle")
    scored = score_parts(bundle_folder, opened.read.bundle, rows, resolved, baselines)
    return frames, write_scores(scored, models_dir(env, resolved, opened.run, "evaluation")), facts


def _scorer_tables(
    opened: Opened,
    scores: DataFrame,
    facts: dict[str, dict[str, float]],
    population: dict[str, int],
) -> tuple[dict[str, pd.DataFrame], float | None]:
    """Steps 3 and 4 on the scores table. On the rows with a known target: the model's cells
    (`split` from Spark, `all` pooled from them) and, apart, each stratum's, its
    `metric_tables`, `baselines` (the comparison with each baseline) and `cells` (stored,
    `_stored_cells`). On every scored test row, a null target included: the drift reference
    (`drift_*`), on the model's score edges. Returns the tables and train's in-sample
    concordance on test's cells (`_in_sample_concordance`)."""
    resolved = opened.resolved
    known = scores.where(KNOWN_TARGET)
    loss = scorer_loss(resolved, opened.objective)
    edges = score_edges(known, resolved)
    split = score_cells(known, resolved, ["split"], edges, loss=loss)
    cells = {"all": pool_cells(split, "split"), "split": split}
    strata = {variable: score_cells(known, resolved, [variable], edges, loss=loss)
              for variable in resolved.strata.variables}  # fmt: skip
    tables = metric_tables(cells, strata, resolved, opened.base, population, loss=loss)
    metrics = {"model": tables["metrics"], **_baseline_metrics(opened, known, facts)}
    tables["baselines"] = compare_baselines(metrics, resolved, opened.base, facts,
                                            opened.objective)  # fmt: skip
    counts = reference_score_counts(scores, resolved, edges)
    drift = build_drift_reference(opened.read.stage2, counts, opened.read.bundle.features)
    stored = {"cells": _stored_cells(split, strata),
              **{f"{DRIFT_PREFIX}{name}": table for name, table in drift.items()}}  # fmt: skip
    return _merge_tables(tables, stored), _in_sample_concordance(opened.read, edges)


def _in_sample_concordance(read: RunFolder, edges: dict) -> float | None:
    """Train's concordance of its in-sample score on test's cells (`binned_concordance` on the
    score edges and target bins test's concordance reads), so the train-to-test gap compares
    like with like; None for a 0/1 target, whose cells hold the target itself and whose
    in-sample concordance Training reads on rows. A declared limit: in-sample scores above
    test's top edge tie in the last score bin, so the gap reads slightly small."""
    if edges["target"] is None:
        return None
    rows = read_in_sample(read)
    value = binned_concordance(rows["score_in_sample"].to_numpy(), rows["target"].to_numpy(),
                               edges["score"], edges["target"])  # fmt: skip
    return None if pd.isna(value) else float(value)


def _baseline_metrics(
    opened: Opened, scores: DataFrame, facts: dict[str, dict[str, float]]
) -> dict[str, pd.DataFrame | None]:
    """Each ranking baseline's `metric_rows` by form, from its own `all` cells (its own edges,
    the loss `baseline_loss` gives it), and `single_feature` None when it is configured and no
    feature qualified: what `compare_baselines` reads. `scores` holds the rows with a known
    target only."""
    resolved = opened.resolved
    metrics: dict[str, pd.DataFrame | None] = {}
    if "single_feature" in resolved.decision.baselines and opened.choice["single_feature"] is None:
        metrics["single_feature"] = None
    for form, column in baseline_columns(resolved, opened.choice).items():
        loss, _ = baseline_loss(form, resolved, facts.get(form), opened.objective)
        edges = score_edges(scores, resolved, column)
        cells = score_cells(scores, resolved, [], edges, loss=loss, column=column)
        metrics[form] = metric_rows({"all": cells}, resolved, opened.base, loss=loss)
    return metrics


def _explanation_tables(
    opened: Opened, rows: DataFrame, scores: DataFrame, env: EnvironmentConfig, cut: dict
) -> tuple[dict[str, pd.DataFrame], dict, dict]:
    """Step 5, on the rows and scores with a known target: the explanation and permutation
    samples collected at `cut` and their tables. `contributions` (the explanation sample in
    Training's `explanation_sample` shape, its waterfall rows included), then on its sampled
    rows only (`sampled_rows`) `features`, `partial_dependence` (the effect features: EDA's key
    features the model uses and its largest by Training's contribution share, one null on every
    row left out) and `effects` (the mean contribution per EDA group of an effect feature beside
    EDA's lift, from the `stage2/` copy); `permutation_importance` on the permutation sample (per
    redundancy cluster of the `stage2/` ledger, at the decision's metric as a loss; empty with
    its columns when `permutation_unavailable` says why). Returns the tables, the collect's log
    entry, the choices made (`explanation_cut`, `key_features`, `effect_features`,
    `permutation_rows`) and the tables not computed, or not whole, with the reason, both as
    the meta holds them (`choices`, `unavailable`), decided before anything runs."""
    resolved, bundle, stage2 = opened.resolved, opened.read.bundle, opened.read.stage2
    sample, permuted, entry = collect_explanation_sample(rows, scores, resolved, env, cut["score"])
    contributions = compute_contributions(bundle, sample)
    counted = sampled_rows(contributions)
    effects = effect_features(opened.read.run_ledger, stage2["ledger"])
    nulls = all_null_features(counted, effects)
    unavailable = {"partial_dependence": f"{ALL_NULL}: {', '.join(nulls)}"} if nulls else {}
    importance, reason = _permutation_table(opened, permuted, counted)
    if reason:
        unavailable["permutation_importance"] = reason
    kinds = stage2["ledger"].set_index("feature")["kind"]
    tables = {
        "contributions": contributions,
        "features": feature_table(counted, encoding_shares(rows, bundle), opened.read.run_ledger),
        "permutation_importance": importance,
        "partial_dependence": partial_dependence(bundle, counted,
                                                 [name for name in effects if name not in nulls]),
        EFFECTS: effect_table(counted, stage2["bins"], stage2["levels"], stage2["edges"], kinds,
                              effects),
    }  # fmt: skip
    chosen = {"explanation_cut": cut, "key_features": key_features(stage2["ledger"]),
              "effect_features": effects, "permutation_rows": len(permuted)}  # fmt: skip
    return tables, entry, {"choices": chosen, "unavailable": unavailable}


def _permutation_table(
    opened: Opened, permuted: pd.DataFrame, counted: pd.DataFrame
) -> tuple[pd.DataFrame, str | None]:
    """Permutation importance on the permutation sample and None, or, when
    `permutation_unavailable` gives a reason, the empty table with its columns and that
    reason. The loss is the decision's metric; the shares are the explanation sample's
    (`counted`)."""
    resolved, bundle = opened.resolved, opened.read.bundle
    reason = permutation_unavailable(permuted, resolved, opened.objective)
    if reason:
        return pd.DataFrame(columns=PERMUTATION_COLUMNS), reason
    clusters = opened.read.stage2["ledger"][["feature", "cluster"]]
    table = permutation_importance(bundle, permuted, clusters,
                                   contribution_shares(counted, bundle.features),
                                   partial(metric_loss, resolved.decision.metric),
                                   resolved.training.seed)  # fmt: skip
    return table, None


def _merge_tables(*parts: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """The tables of `parts` in one dict, in order; a name two parts hold fails loud, naming
    it, so no table silently replaces another (the drift reference's are prefixed for that)."""
    merged: dict[str, pd.DataFrame] = {}
    for part in parts:
        clashing = sorted(set(merged) & set(part))
        if clashing:
            raise ValueError(f"Evaluation's tables {clashing} are each written by two steps")
        merged.update(part)
    return merged


def _stored_cells(split: pd.DataFrame, strata: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """The model's score cells of replicate 0 (the actual rows) in one long table: the `split`
    cells and each stratum's, with `by` (the column they are cut by) and `level` (its value)
    after `period`. The `all` cells are the `split` cells pooled (`pool_cells`), so not stored.
    The bootstrap replicates are not either: with 20 of them the table reached 53k rows on
    `unit`, and every interval they give is already in `metrics` and `slices`."""
    frames = [frame.loc[frame["replicate"] == 0].rename(columns={by: "level"}).assign(by=by)
              for by, frame in [("split", split), *strata.items()]]  # fmt: skip
    table = pd.concat(frames, ignore_index=True)
    first = ["part", "period", "by", "level"]
    return table[[*first, *[name for name in table.columns if name not in first]]]


def _write(result: StageResult, request: Request, opened: Opened, staged: str, card: dict) -> None:
    """Step 6: `evaluation/` written whole in one `write_stage` (its tables; among the texts
    `report.html` from the views already built, the model card as `model_card.json` and
    `model_card.html`, and the drift reference's sidecar; the staged scores moved in as
    `scores/`; `evaluation.json` is the commit marker), then the audit log's `run` entry with
    the run and the validation period scored."""
    resolved, folder = opened.resolved, models_dir(request.env, opened.resolved, opened.run,
                                                    "evaluation")  # fmt: skip
    decisions = show_decisions(request.cfg, request.entity, request.env)
    sidecar = drift_reference_sidecar(opened.run, opened.read.bundle.model_hash)
    texts = {"report.html": render_views(result.views, result.meta, resolved, result.log,
                                         decisions),
             "model_card.json": json.dumps(card, indent=2, allow_nan=False),
             "model_card.html": render_card(card),
             DRIFT_REFERENCE_FILE: json.dumps(sidecar, indent=2)}  # fmt: skip
    result.paths = write_stage(result, folder, "evaluation", texts=texts,
                               folders={SCORES_FOLDER: staged})  # fmt: skip
    housekeeping = resolved.housekeeping
    record_stage_entry(
        request.cfg, request.entity, request.env, stage="evaluation", op="run",
        reason=RUN_REASON, run_id=opened.run,
        validation_period=result.meta["validation_period"],
        replayed_to=housekeeping["replayed_to"],
        resolved_input_hash=housekeeping["resolved_input_hash"],
    )  # fmt: skip
    print(f"evaluation of {opened.run} written: {folder}")


def _discard(staged: str, error: BaseException) -> None:
    """Remove the scores table an Evaluation that failed staged beside its folder; once moved
    into `evaluation/`, nothing is left to remove. When the removal fails too, `error` stays
    the one raised, with a note naming what is left."""
    path = local_path(staged)
    try:
        if path.exists():
            shutil.rmtree(path)
    except OSError as cleanup:
        error.add_note(f"the staged scores table {path} could not be removed ({cleanup}): "
                       "remove it before rerunning")  # fmt: skip
