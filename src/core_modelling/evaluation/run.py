"""`run_evaluation`: the Evaluation stage for one trained run, in the order of
docs/components/evaluation.md "How one run flows".

1. Resolve the config, check `evaluation.skip_views` and find the run (`find_run`: the latest
   of this data definition, or the one named; another data definition is refused before
   anything is read). Refuse, before any Spark work, what would fail only at the end: a
   leftover of an unfinished write beside `evaluation/`, a run folder the card cannot be built
   from (`check_card_inputs`) and a `training.json` without the keys read later. Load the
   bundle (its hash checked), the per-run ledger, the run's own `stage2/` copy, `training.json`
   (its objective from `run.json`) and the Training tables the report draws.
2. Build the evaluation rows with the bundle's features and the baselines' columns, add the
   baselines' score columns, score inside Spark and write the scores table beside `evaluation/`;
   every later step reads it back, so nothing is scored twice.
3. The model's score cells (per split, pooled, per stratum), its metric tables with intervals,
   each ranking baseline's metrics on its own cells, and the baselines comparison.
4. The drift reference from the model's pooled cells and the `stage2/` copy.
5. The explanation tables on a seeded test sample: contributions, the feature table,
   permutation importance per redundancy cluster, partial dependence and ICE, and the effects
   beside EDA's lift; beside them Training's tables the report draws, so `evaluation/` renders
   alone.
6. Write `evaluation/` whole (its json, tables, the report from `views.py` and
   `views_explain.py`, the model card from `evaluation/card.py`, and the scores table), then
   the audit log's `run` entry with the validation period it scored.

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

from core_modelling.artifacts import (
    StageResult,
    check_siblings,
    lap,
    local_path,
    read_parquet,
    read_stage_meta,
    stage_identity,
    write_stage,
)
from core_modelling.config import UseCaseConfig
from core_modelling.config.audit_log import (
    load_entries,
    record_stage_entry,
    resolve_config,
    show_decisions,
)
from core_modelling.config.identities import short
from core_modelling.config.replay import Entry
from core_modelling.dataset import Frames, build_frames
from core_modelling.environment import EnvironmentConfig, models_dir
from core_modelling.evaluation.baselines import (
    NOT_CHOSEN,
    add_baselines,
    baseline_columns,
    baseline_loss,
    carried_columns,
    choose_single_feature,
    compare_baselines,
    describe_baseline_columns,
)
from core_modelling.evaluation.card import build_card, check_card_inputs
from core_modelling.evaluation.cells import score_cells, score_edges, scorer_loss
from core_modelling.evaluation.drift_reference import (
    DRIFT_REFERENCE_SCHEMA_VERSION,
    build_drift_reference,
)
from core_modelling.evaluation.effects import EFFECTS, effect_table
from core_modelling.evaluation.explain import (
    PERMUTATION_COLUMNS,
    collect_explanation_sample,
    compute_contributions,
    effect_features,
    encoding_shares,
    explanation_cut,
    feature_table,
    partial_dependence,
    permutation_importance,
    permutation_unavailable,
)
from core_modelling.evaluation.report import check_skip_views, render_views, report_views
from core_modelling.evaluation.scores import SCORES_FOLDER, score_parts, write_scores
from core_modelling.evaluation.tables import (
    headline_names,
    metric_key,
    metric_tables,
    pooled_metrics,
)
from core_modelling.evaluation.views import TRAINING_SIGNOFF, TRAINING_TRIALS
from core_modelling.evaluation.views_explain import TRAIN_SAMPLE
from core_modelling.model.bundle import Bundle, load_bundle
from core_modelling.periods import period_spec
from core_modelling.reporting.card import render_card
from core_modelling.runs import find_run, read_run
from core_modelling.statistics.losses import metric_loss
from core_modelling.statistics.score_cells import PARTS, pool_cells
from core_modelling.training.gate import read_stage2_copy
from core_modelling.training.ledger_run import read_run_ledger
from core_modelling.training.tables import train_level

RUN_REASON = "Evaluation scored this run on its test clients and the validation period."
# The drift reference's tables are stored beside the feature table, whose name `features`
# they would otherwise share
DRIFT_PREFIX = "drift_"
# Training's tables the report draws, as written, by the name Evaluation stores them under, so
# `evaluation/` renders alone
TRAINING_TABLES = {TRAINING_SIGNOFF: "signoff", TRAINING_TRIALS: "trials",
                   TRAIN_SAMPLE: "explanation_sample"}  # fmt: skip


@dataclass
class Opened:
    """A run found and read: the resolved config, the audit log's entries, the run number and
    folder, the bundle, the per-run ledger, the run's `stage2/` copy (`read_stage2_copy`),
    `training.json`, Training's tables the report draws (`TRAINING_TABLES`), the run's
    `training.objective` and `config_hash` (from `run.json`: a named run may have been trained
    under another config than the evaluating one), the unsampled train level (`base`) and what
    the baselines read (`choice`: the bundle's `features` and the chosen `single_feature`)."""

    resolved: UseCaseConfig
    entries: list[Entry]
    run: str
    folder: str
    bundle: Bundle
    run_ledger: pd.DataFrame
    stage2: dict[str, pd.DataFrame]
    training: dict
    trained: dict[str, pd.DataFrame]
    objective: str
    training_config_hash: str
    base: float
    choice: dict


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
    without its `run` entry; Evaluation run again replaces it and records the entry.
    """
    seconds: dict[str, float] = {}
    clock = time.perf_counter()
    opened = _open_run(cfg, entity, env, run)
    folder = models_dir(env, opened.resolved, opened.run, "evaluation")
    frames, staged, facts = _score_rows(opened, entity, env, spark, folder)
    seconds["scoring"], clock = lap(clock)
    try:
        scores = spark.read.parquet(staged)
        tables, cells = _scorer_tables(opened, scores, facts, frames.meta["eligible_rows"])
        seconds["metrics"], clock = lap(clock)
        drift = build_drift_reference(opened.folder, cells["all"], opened.bundle.features)
        cut = explanation_cut(tables["slices"], tables["curves"], opened.resolved)
        explained, entry, chosen, unavailable = _explanation_tables(opened, frames.rows, scores,
                                                                    env, cut)  # fmt: skip
        seconds["explanation"], clock = lap(clock)
        tables |= {**explained, **opened.trained, "cells": _stored_cells(cells),
                   **{f"{DRIFT_PREFIX}{name}": table for name, table in drift.items()}}  # fmt: skip
        result = _build_result(opened, frames, tables, chosen, unavailable,
                               [*frames.log, entry], env)  # fmt: skip
        result.meta["timings"] = {"seconds": seconds}
        result.meta["summary"]["seconds"] = round(sum(seconds.values()), 1)
        _write(result, cfg, entity, env, opened, folder, staged)
    except BaseException as error:
        _discard(staged, error)
        raise
    return result


def _open_run(cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, run: str | None) -> Opened:
    """Step 1: the config resolved and its skipped views checked, the run found (a run of
    another data definition refused first, naming both hashes), a leftover beside `evaluation/`
    and a run folder the card cannot be built from refused, then the bundle, the per-run
    ledger, the `stage2/` copy and Training's json and tables read, the single feature chosen
    from the ledgers and the train level taken (`train_level`)."""
    resolved = resolve_config(cfg, entity, env)
    check_skip_views(resolved)
    run_id = find_run(env, resolved, entity, run)
    folder = models_dir(env, resolved, run_id)
    evaluation = local_path(models_dir(env, resolved, run_id, "evaluation"))
    check_siblings(evaluation, "evaluation", {}, (SCORES_FOLDER,))
    check_card_inputs(folder, resolved)
    entries = load_entries(resolved, entity, env)
    bundle = load_bundle(models_dir(env, resolved, run_id, "bundle"))
    run_ledger = read_run_ledger(folder)
    stage2 = read_stage2_copy(folder)
    training, trained = _read_training(models_dir(env, resolved, run_id, "training"))
    record = read_run(env, resolved, run_id)
    settings = record["training_settings"]
    single = choose_single_feature(run_ledger, stage2["ledger"], settings["features.order"])
    choice = {"features": bundle.features, "single_feature": single}
    base = train_level(folder)
    print(
        f"evaluating {run_id} of {resolved.use_case} on {entity}: {len(bundle.features)} "
        f"features, model {short(bundle.model_hash)}"
    )
    return Opened(resolved, entries, run_id, folder, bundle, run_ledger, stage2, training, trained,
                  settings["training"]["objective"], record["config_hash"], base,
                  choice)  # fmt: skip


def _read_training(folder: str) -> tuple[dict, dict[str, pd.DataFrame]]:
    """`training.json`, its schema version and the keys only Evaluation reads checked
    (`written_at`, `timings.seconds`; `check_card_inputs` checks `metrics` with the card's),
    and the Training tables the report draws, keyed by the names Evaluation stores them under
    (`TRAINING_TABLES`); the others stay unread."""
    meta = read_stage_meta(folder, "training")
    missing = [] if "written_at" in meta else ["written_at"]
    missing += [] if "seconds" in meta.get("timings", {}) else ["timings.seconds"]
    if missing:
        raise ValueError(
            f"{folder}/training.json lacks {missing}: the run was written by another framework "
            "version or did not finish; train it again"
        )
    tables = local_path(folder) / "tables"
    return meta, {name: read_parquet(tables / f"{table}.parquet")
                  for name, table in TRAINING_TABLES.items()}  # fmt: skip


def _score_rows(
    opened: Opened,
    entity: str,
    env: EnvironmentConfig,
    spark: SparkSession,
    folder: str,
) -> tuple[Frames, str, dict[str, dict[str, float]]]:
    """Step 2: the evaluation frames with the bundle's features and the baselines' columns, the
    column baselines' facts (before `add_baselines` replaces the columns), the rows scored in
    Spark and written beside `folder` (`write_scores`). Returns the frames, the staged scores'
    path and the facts."""
    resolved, choice = opened.resolved, opened.choice
    frames = build_frames(resolved, entity, env, spark, "evaluation",
                          features=opened.bundle.features,
                          carry=carried_columns(resolved, choice))  # fmt: skip
    facts = describe_baseline_columns(frames.rows, resolved)
    rows = add_baselines(frames.rows, resolved, choice)
    baselines = list(baseline_columns(resolved, choice).values())
    scored = score_parts(models_dir(env, resolved, opened.run, "bundle"), rows, resolved, baselines)
    return frames, write_scores(scored, folder), facts


def _scorer_tables(
    opened: Opened,
    scores: DataFrame,
    facts: dict[str, dict[str, float]],
    population: dict[str, int],
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Step 3: the model's cells (`split` from Spark, `all` pooled from them, each stratum) and
    its `metric_tables`, then `baselines`, the comparison with each baseline. Returns the tables
    and the model's cells by `by`."""
    resolved = opened.resolved
    loss = scorer_loss(resolved, opened.objective)
    edges = score_edges(scores, resolved)
    split = score_cells(scores, resolved, ["split"], edges, loss=loss)
    cells = {"all": pool_cells(split, "split"), "split": split}
    for variable in resolved.strata.variables:
        cells[variable] = score_cells(scores, resolved, [variable], edges, loss=loss)
    tables = metric_tables(cells, resolved, opened.base, population, loss=loss is not None)
    metrics = {"model": tables["metrics"], **_baseline_metrics(opened, scores, facts, population)}
    tables["baselines"] = compare_baselines(metrics, resolved, opened.base, facts,
                                            opened.objective)  # fmt: skip
    return tables, cells


def _baseline_metrics(
    opened: Opened,
    scores: DataFrame,
    facts: dict[str, dict[str, float]],
    population: dict[str, int],
) -> dict[str, pd.DataFrame | None]:
    """Each ranking baseline's `metric_tables(…)["metrics"]` by form, from its own `all` cells
    (its own edges, the loss `baseline_loss` gives it), and `single_feature` None when it is
    configured and no feature qualified: what `compare_baselines` reads."""
    resolved = opened.resolved
    metrics: dict[str, pd.DataFrame | None] = {}
    if "single_feature" in resolved.decision.baselines and opened.choice["single_feature"] is None:
        metrics["single_feature"] = None
    for form, column in baseline_columns(resolved, opened.choice).items():
        loss, _ = baseline_loss(form, resolved, facts.get(form), opened.objective)
        edges = score_edges(scores, resolved, column)
        cells = score_cells(scores, resolved, [], edges, loss=loss, column=column)
        tables = metric_tables({"all": cells}, resolved, opened.base, population,
                               loss=loss is not None)  # fmt: skip
        metrics[form] = tables["metrics"]
    return metrics


def _explanation_tables(
    opened: Opened, rows: DataFrame, scores: DataFrame, env: EnvironmentConfig, cut: dict
) -> tuple[dict[str, pd.DataFrame], dict, dict, dict[str, str]]:
    """Step 5: the explanation sample collected at `cut` and its tables: `contributions` (the
    sample in Training's `explanation_sample` shape), `features`, `permutation_importance` (per
    redundancy cluster of the `stage2/` ledger, at the decision's metric as a loss; empty with
    its columns when `permutation_unavailable` says why, decided before it runs) and
    `partial_dependence` (the effect features: EDA's key features the model uses and its largest
    by Training's contribution share) and `effects` (the sample's mean contribution per EDA
    group of an effect feature beside EDA's lift, from the `stage2/` copy). Returns the tables,
    the collect's log entry, the choices made (`explanation_cut`, `key_features`,
    `effect_features`) and the tables not computed with the reason (`unavailable`)."""
    resolved, bundle, ledger = opened.resolved, opened.bundle, opened.stage2["ledger"]
    sample, entry = collect_explanation_sample(rows, scores, resolved, env, cut["score"])
    contributions = compute_contributions(bundle, sample)
    shares = encoding_shares(rows, bundle)
    loss = partial(metric_loss, resolved.decision.metric)
    clusters = ledger[["feature", "cluster"]]
    keys = ledger.loc[ledger["key_feature"].fillna("").ne(""), "feature"].tolist()
    effects = effect_features(opened.run_ledger, keys)
    reason = permutation_unavailable(contributions)
    importance = (pd.DataFrame(columns=PERMUTATION_COLUMNS) if reason else
                  permutation_importance(bundle, contributions, clusters, loss,
                                         resolved.training.seed))  # fmt: skip
    tables = {
        "contributions": contributions,
        "features": feature_table(contributions, shares, opened.run_ledger),
        "permutation_importance": importance,
        "partial_dependence": partial_dependence(bundle, sample, effects),
        EFFECTS: effect_table(contributions, opened.stage2["bins"], opened.stage2["levels"],
                              opened.stage2["edges"], effects),
    }  # fmt: skip
    chosen = {"explanation_cut": cut, "key_features": keys, "effect_features": effects}
    return tables, entry, chosen, {} if reason is None else {"permutation_importance": reason}


def _stored_cells(cells: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """The model's score cells of replicate 0 (the actual rows) in one long table: the `split`
    cells and each stratum's, with `by` (the column they are cut by) and `level` (its value)
    after `period`. The `all` cells are the `split` cells pooled (`pool_cells`), so not stored.
    The bootstrap replicates are not either: with 20 of them the table reached 53k rows on
    `unit`, and every interval they give is already in `metrics` and `slices`."""
    frames = [frame.loc[frame["replicate"] == 0].rename(columns={by: "level"}).assign(by=by)
              for by, frame in cells.items() if by != "all"]  # fmt: skip
    table = pd.concat(frames, ignore_index=True)
    first = ["part", "period", "by", "level"]
    return table[[*first, *[name for name in table.columns if name not in first]]]


def _summary(metrics: pd.DataFrame, cfg: UseCaseConfig, label: str) -> dict:
    """`evaluation.json`'s flat `summary`, which `list_runs` and `show_run` display: the scored
    validation period and each headline metric pooled per part (`<part>_<metric>`), rounded; a
    metric undefined on a part is None."""
    values = pooled_metrics(metrics).set_index(["part", "metric"])["value"]
    summary: dict[str, object] = {"validation_period": label}
    for part in PARTS:
        for name in headline_names(cfg):
            value = values.loc[(part, metric_key(cfg, name))]
            summary[f"{part}_{name}"] = None if pd.isna(value) else round(float(value), 6)
    return summary


def _earlier_validations(entries: list[Entry]) -> list[dict]:
    """The validation periods earlier Evaluation runs scored, from the audit log's `run` entries
    of stage `evaluation`: `seq, time, run_id, validation_period` each."""
    return [
        {"seq": e.seq, "time": e.time, "run_id": e.run_id, "validation_period": e.validation_period}
        for e in entries
        if e.stage == "evaluation" and e.op == "run"
    ]


def _warnings(opened: Opened, features: pd.DataFrame, cut: dict) -> list[dict]:
    """The run's warnings, the only place they are written: the single-feature baseline's
    (`_single_feature_warnings`), final features with nulls at scoring and none in train, and an
    explanation cut that fell back from the decision's slice (`explanation_cut`). Each is a
    `code`, its values and the `text` printed here, which the report shows; the card copies the
    code and the values. A warning never changes what the run does."""
    notes = _single_feature_warnings(opened)
    unseen = features.loc[features["null_not_in_train"], "feature"].tolist()
    if unseen:
        text = (f"{unseen} hold nulls at scoring and none in train: the model never learnt "
                "where their nulls go; read their contributions with care")  # fmt: skip
        notes.append({"code": "nulls_not_in_train", "features": unseen, "text": text})
    if not cut["available"]:
        text = f"{cut['reason']} on test: the explanation's cut is the {cut['slice']}"
        notes.append({"code": "explanation_cut_not_at_decision_slice", "slice": cut["slice"],
                      "reason": cut["reason"], "text": text})  # fmt: skip
    for note in notes:
        print(f"warning: {note['text']}")
    return notes


def _single_feature_warnings(opened: Opened) -> list[dict]:
    """The single-feature baseline configured but not chosen, or chosen with nulls on train:
    it was chosen on the train rows where it is known, while its nulls score lowest on every
    row. The share is the per-run ledger's `null_share` (the encoder's, on the train frame)."""
    configured = "single_feature" in opened.resolved.decision.baselines
    single = opened.choice["single_feature"]
    if configured and single is None:
        return [{"code": "single_feature_baseline_not_chosen",
                 "text": f"the single-feature baseline is {NOT_CHOSEN}"}]  # fmt: skip
    if single is None:
        return []
    name = single["feature"]
    share = float(opened.run_ledger.set_index("feature").loc[name, "null_share"])
    if not share > 0:
        return []
    text = (f"the single-feature baseline {name} was chosen on the train rows where it is "
            f"known; it is null on {share:.1%} of train rows and nulls score lowest, so the "
            "baseline may be weaker than it looks")  # fmt: skip
    return [{"code": "single_feature_baseline_has_nulls", "feature": name,
             "train_null_share": share, "text": text}]  # fmt: skip


def _build_result(
    opened: Opened,
    frames: Frames,
    tables: dict[str, pd.DataFrame],
    chosen: dict,
    unavailable: dict[str, str],
    log: list[dict],
    env: EnvironmentConfig,
) -> StageResult:
    """The stage result, writing nothing: `evaluation.json`'s content (the identity, the run,
    the run's own `training_config_hash` beside the evaluating config's, `model_hash`, the
    `row_loss` of the model's cells (`scorer_loss`; None without one), the scored validation
    period, the `summary`, the train level, the eligible rows, the choices, the tables not
    computed with their reason (`unavailable`, {} when none), Training's metrics, when it was
    written and its seconds per step, the validation periods earlier Evaluation runs scored,
    the drift reference's schema version and the warnings) and the report's views, built once
    here."""
    resolved = opened.resolved
    label = period_spec(resolved).label(resolved.time.validation_period)
    meta = {
        **stage_identity(resolved, "evaluation", env),
        "run_id": opened.run,
        "training_config_hash": opened.training_config_hash,
        "model_hash": opened.bundle.model_hash,
        "row_loss": scorer_loss(resolved, opened.objective),
        "validation_period": label,
        "summary": _summary(tables["metrics"], resolved, label),
        "base": opened.base,
        "eligible_rows": frames.meta["eligible_rows"],
        "choices": {
            "headline": headline_names(resolved),
            "single_feature": opened.choice["single_feature"],
            **chosen,
        },
        "unavailable": unavailable,
        "training": opened.training["metrics"],
        "trained_at": opened.training["written_at"],
        "training_seconds": opened.training["timings"]["seconds"],
        "earlier_validations": _earlier_validations(opened.entries),
        "drift_reference_schema_version": DRIFT_REFERENCE_SCHEMA_VERSION,
        "warnings": _warnings(opened, tables["features"], chosen["explanation_cut"]),
    }
    views = report_views(tables, meta, resolved)
    return StageResult(tables=tables, ledger=opened.run_ledger, log=log, meta=meta, paths={},
                       views=views, frame=None, config=resolved)  # fmt: skip


def _write(
    result: StageResult,
    cfg: UseCaseConfig,
    entity: str,
    env: EnvironmentConfig,
    opened: Opened,
    folder: str,
    staged: str,
) -> None:
    """Step 6: `evaluation/` written whole in one `write_stage` (its tables; among the texts
    `report.html` from the views already built, and the model card as `model_card.json` and
    `model_card.html`; the staged scores moved in as `scores/`; `evaluation.json` is the commit
    marker), then the audit log's `run` entry with the run and the validation period scored."""
    resolved = opened.resolved
    card = build_card(opened.folder, result.tables, result.meta, resolved)
    decisions = show_decisions(cfg, entity, env)
    texts = {"report.html": render_views(result.views, result.meta, resolved, result.log,
                                         decisions),
             "model_card.json": json.dumps(card, indent=2, allow_nan=False),
             "model_card.html": render_card(card)}  # fmt: skip
    result.paths = write_stage(result, folder, "evaluation", texts=texts,
                               folders={SCORES_FOLDER: staged})  # fmt: skip
    housekeeping = resolved.housekeeping
    record_stage_entry(
        cfg, entity, env, stage="evaluation", op="run", reason=RUN_REASON, run_id=opened.run,
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
