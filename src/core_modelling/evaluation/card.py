"""The model card's facts (reporting.md "The model card"): one versioned dict per evaluated run.

`build_card` reads the run folder (`run.json`, the bundle, `training/`, the per-run ledger, the
`stage2/` copy, through `run_artifacts.open_run_folder`) and Evaluation's tables and meta as
`read_stage` returns them, so Evaluation writes the card with its own folder and a written run
folder can rebuild it under the config it was evaluated with; `check_card_inputs` refuses a run
folder it cannot be built from before Evaluation scores anything. Every value is read from
those or from the resolved config: the card writes no sentence and parses none. A
consideration is a code with its values:
Evaluation's warnings copied without their text, and the ones Training's and the audit log's
facts record. Sign-off and lifecycle stay empty until `decide` and `register` fill them
(M2.4); the registered model key, the parent run of a refit and its metrics are None until
then. `reporting/card.py` renders the dict.
"""

import math

import numpy as np
import pandas as pd

from core_modelling import __version__
from core_modelling.artifacts import utc_now
from core_modelling.config.replay import check_resolved
from core_modelling.config.schema import UseCaseConfig
from core_modelling.evaluation.tables import VALIDATION_TEST_CLIENTS
from core_modelling.model.bundle import Bundle
from core_modelling.periods import period_spec
from core_modelling.reporting.card import CARD_SCHEMA_VERSION, CARD_SECTIONS
from core_modelling.run_artifacts import (
    TRAIN_METRIC_KEYS,
    RunFolder,
    open_run_folder,
    read_training_tables,
)
from core_modelling.sources import feature_source_names, source_name
from core_modelling.statistics.score_cells import MEAN, PARTS, POOLED
from core_modelling.tasks import TASK_SPECS

# The card's own versioned format: never derived from `tables.METRIC_COLUMNS` or Training's
# records, so a table or a Training change cannot change the card unannounced
CARD_METRIC_COLUMNS = ["metric", "part", "period", "stratum", "level", "value", "low", "high",
                       "rows", "events", "insufficient"]  # fmt: skip
# The keys of each record in `training.json`'s `folds` and `search`, and the calibration table's
# columns, that the card copies
CARD_FOLD_KEYS = ("dealing", "fold", "rows", "clients", "converting_clients", "positive_rows",
                  "target_min", "target_max")  # fmt: skip
CARD_SEARCH_KEYS = ("family", "trials", "seconds", "seconds_per_trial", "seconds_longest",
                    "best_fold_metric", "best_trial", "share_seconds")  # fmt: skip
CARD_CALIBRATION_COLUMNS = ("method", "chosen", "parameters", "oof_loss", "true_rate",
                            "sampled_rate", "offset", "factor", "factor_low", "factor_high",
                            "half_total_rows")  # fmt: skip
# What every score is conditional on: a declared fact of how the eligibility and the target are
# defined, not read from the run
CONDITIONAL_ON = "staying_through_target_window"
# The score's column: a declared fact of the card, like `CARD_METRIC_COLUMNS`, never derived from
# another module's list
SCORE_COLUMN = "score"
EVALUATION_KEYS = ("run_id", "model_hash", "config_hash", "validation_period", "eligible_rows",
                   "choices", "earlier_validations", "warnings")  # fmt: skip
EVALUATION_TABLES = ("metrics", "baselines", "features")
CARD_TRAINING_TABLES = ("signoff", "calibration", "selection")  # Training's tables the card reads


def build_card(
    run_folder: str,
    tables: dict[str, pd.DataFrame],
    meta: dict,
    resolved: UseCaseConfig,
    read: RunFolder | None = None,
) -> dict:
    """The model card of an evaluated run: `schema_version`, then the sections, both as
    `reporting/card.py` defines them, as plain JSON-ready data. `tables` and `meta`
    are Evaluation's and `resolved` the config it ran with; a missing file, key or table fails
    naming it, and pieces of different runs, models or configs are refused: the run folder's
    as `check_card_inputs` refuses them, Evaluation's own after it. `read` is the run folder
    `check_card_inputs` already read (Evaluation's); without it the folder is read here."""
    read = read or check_card_inputs(run_folder, resolved)
    run, bundle, manifest, training = read.run, read.bundle, read.manifest, read.training
    trained = read_training_tables(read, CARD_TRAINING_TABLES)
    _require(meta, EVALUATION_KEYS, "Evaluation's meta")
    _require(tables, EVALUATION_TABLES, "Evaluation's tables")
    _check_evaluation(run, meta, bundle, resolved.housekeeping["config_hash"])
    stage2, run_ledger = read.stage2["ledger"], read.run_ledger
    kept = list(resolved.features.kept)
    sections = {
        "details": _details(run, bundle, manifest, meta, resolved),
        "intended_use": _intended_use(resolved),
        "data": _data(tables["metrics"], meta, training, resolved),
        "features": _features(
            trained["signoff"], stage2, tables["features"], bundle.features, kept
        ),
        "training": _training(training, trained["calibration"], bundle.content),
        "performance": _performance(tables, meta, resolved),
        "considerations": [
            *_warning_codes(meta["warnings"]),
            *_recorded_considerations(meta, training, trained["selection"], run_ledger),
        ],
        "sign_off": {},
        "lifecycle": {},
    }
    if sections.keys() != set(CARD_SECTIONS):
        raise ValueError(f"the card's sections {sorted(sections)} are not CARD_SECTIONS")
    ordered = {name: sections[name] for name in CARD_SECTIONS}
    return _plain({"schema_version": CARD_SCHEMA_VERSION, **ordered})


def check_card_inputs(run_folder: str, resolved: UseCaseConfig) -> RunFolder:
    """Refuse a run folder the card cannot be built from, before Evaluation scores anything:
    Evaluation's side, a config not resolved, then the run folder's contract
    (`open_run_folder`). Returns what it read, so neither Evaluation nor `build_card` reads a
    piece twice."""
    check_resolved(resolved, "the model card")
    return open_run_folder(run_folder)


def _require(mapping: dict, keys: tuple[str, ...], where: str) -> None:
    """Fail naming the keys of `keys` that `mapping` lacks."""
    missing = [key for key in keys if key not in mapping]
    if missing:
        raise ValueError(f"{where} lacks {missing}: the run was written by another framework "
                         "version or did not finish; rerun the stage that writes it")  # fmt: skip


def _records(records: list[dict], keys: tuple[str, ...], where: str) -> list[dict]:
    """Each record of `records` with only `keys`, in their order; a record without one of them
    fails naming it (`_require`)."""
    for record in records:
        _require(record, keys, where)
    return [{key: record[key] for key in keys} for record in records]


def _check_evaluation(run: dict, meta: dict, bundle: Bundle, config_hash: str) -> None:
    """Refuse an Evaluation of another run, model or config: its meta's run id the run's, its
    `model_hash` the bundle's, and the resolved config's `config_hash` (`config_hash`) the one
    Evaluation ran with, so a config changed since never speaks for this evaluation."""
    if meta["run_id"] != run["run_id"]:
        raise ValueError(
            f"Evaluation's meta names run {meta['run_id']}, the run folder {run['run_id']}: one "
            "card, one run"
        )
    if meta["model_hash"] != bundle.model_hash:
        raise ValueError(
            f"Evaluation scored model {meta['model_hash']}, the bundle holds {bundle.model_hash}: "
            "evaluate the run again"
        )
    if config_hash != meta["config_hash"]:
        raise ValueError(
            f"Evaluation ran with config {meta['config_hash']}, the resolved config is "
            f"{config_hash}: build the card with the config Evaluation ran with, or evaluate the "
            "run again"
        )


def _details(
    run: dict, bundle: Bundle, manifest: dict, meta: dict, resolved: UseCaseConfig
) -> dict:
    """Who and what the model is: the model key (None until register), the run, the family and
    library versions, the framework versions (Training's, and the card's: the framework version
    that writes it), the hashes, the Stage 2 runs and the dates."""
    hashes = ("model_hash", "recipe_hash", "feature_signature", "config_hash",
              "data_definition_hash", "resolved_input_hash", "hash_version")  # fmt: skip
    return {
        "model_key": None,
        "use_case": run["use_case"],
        "domain": resolved.domain,
        "entity": run["entity"],
        "task": bundle.task,
        "run_id": run["run_id"],
        "parent_run": None,
        "parent_metrics": None,
        "family": bundle.family,
        "library_versions": bundle.content["library_version"],
        "framework_versions": {"training": run["framework_version"], "card": __version__},
        "hashes": {**{key: manifest[key] for key in hashes},
                   "evaluation_config_hash": meta["config_hash"]},
        "stage2_runs": run["stage2"],
        "dates": {"run_started_at": run["started_at"], "trained_at": manifest["written_at"],
                  "card_written_at": utc_now()},
    }  # fmt: skip


def _intended_use(resolved: UseCaseConfig) -> dict:
    """What the score is for: the decision, the slices, the population (each eligibility step,
    `list` naming its list), the target and its window, and what the score estimates."""
    eligibility = resolved.data.eligibility.model_dump(mode="json")
    time = resolved.time
    return {
        "decision": resolved.decision.model_dump(mode="json"),
        "slices": resolved.evaluation.slices.model_dump(mode="json"),
        "population": [{"list": name, **step} for name, steps in eligibility.items()
                       for step in steps],
        "target": {**resolved.data.target.model_dump(mode="json"),
                   "window_periods": time.target_window, "period": time.period},
        "score": {"column": SCORE_COLUMN, "estimate": TASK_SPECS[resolved.task]["estimate_noun"],
                  "conditional_on": CONDITIONAL_ON},
    }  # fmt: skip


def _data(metrics: pd.DataFrame, meta: dict, training: dict, resolved: UseCaseConfig) -> dict:
    """What the model was built and measured on: the logical sources, the window, the validation
    period, the eligible rows per period, the rows and events of the metrics' unstratified rows
    (`rows_per_period`: each part's per period; `rows_pooled`: each part's over its periods;
    `rows_validation_test_clients`: the validation period's test-split clients, pooled), the
    split, the sampling and the train folds."""
    entity = resolved.housekeeping["entity"]
    targets = resolved.entities[entity].sources.targets
    spec, window = period_spec(resolved), resolved.time.observation_window
    plain = metrics.loc[metrics["stratum"].isna() & (metrics["period"] != MEAN)]
    counts = plain.drop_duplicates(["part", "period"])[["part", "period", "rows", "events"]]
    pooled, own = counts["period"] == POOLED, counts["part"].isin(PARTS)
    clients = counts.loc[pooled & (counts["part"] == VALIDATION_TEST_CLIENTS), ["rows", "events"]]
    return {
        "sources": {"features": feature_source_names(resolved, entity),
                    "target": source_name(targets) if targets else None,
                    "model_input": resolved.data.model_input},
        "period": resolved.time.period,
        "observation_window": {"first": spec.label(window.first), "last": spec.label(window.last)},
        "validation_period": meta["validation_period"],
        "eligible_rows": [{"period": p, "rows": n} for p, n in meta["eligible_rows"].items()],
        "rows_per_period": counts.loc[own & ~pooled].to_dict("records"),
        "rows_pooled": counts.loc[own & pooled].drop(columns="period").to_dict("records"),
        "rows_validation_test_clients": clients.to_dict("records"),
        "split": resolved.data.split.model_dump(mode="json"),
        "sampling": {k: v for k, v in training["sampling"].items() if k != "step"},
        "train_folds": _records(training["folds"], CARD_FOLD_KEYS, "training.json's folds"),
    }  # fmt: skip


def _features(
    signoff: pd.DataFrame,
    stage2: pd.DataFrame,
    explained: pd.DataFrame,
    final: list[str],
    kept: list[str],
) -> dict:
    """The feature lists, from Training's sign-off table: the final list in its order (kind,
    source, out-of-fold and test contribution share, the model's and EDA's direction, the
    constraint), the held with their open flags, the excluded with the `exclude` entry and its
    recorded reason, and the kept with Feature Checks' flags. A final list that is not the
    bundle's fails."""
    model = signoff.loc[signoff["section"] == "model"]
    if sorted(model["feature"]) != sorted(final):
        raise ValueError("Training's sign-off table does not list the bundle's final features")
    by_feature = stage2.set_index("feature")
    test_share = explained.set_index("feature")["contribution_share"]
    rows = model.rename(columns={"contribution_share": "share_train_oof"})
    rows = rows.assign(kind=rows["feature"].map(by_feature["kind"]),
                       share_test=rows["feature"].map(test_share))  # fmt: skip
    columns = ["feature", "kind", "source", "share_train_oof", "share_test", "direction_model",
               "direction_eda", "monotone"]  # fmt: skip
    held = signoff.loc[signoff["section"] == "held", ["feature", "source", "open_flags"]]
    excluded = signoff.loc[signoff["section"] == "excluded",
                           ["feature", "source", "exclude_entry", "exclude_reason"]]  # fmt: skip
    return {
        "final": rows[columns].to_dict("records"),
        "held": held.to_dict("records"),
        "excluded": excluded.rename(columns={"exclude_entry": "entry",
                                             "exclude_reason": "reason"}).to_dict("records"),
        "kept": [{"feature": name, "flags": by_feature.loc[name, "flags"],
                  "in_model": name in final} for name in kept],
    }  # fmt: skip


def _training(training: dict, calibration: pd.DataFrame, content: dict) -> dict:
    """How the model was fitted: the path, each family's search (trials, seconds, best fold
    metric), the train-side metrics, the recipe (the family and the best configuration among it)
    without the encoder and the features, which the recipe hash covers, the calibration fitted
    and each method compared, and what the run reproduces to."""
    recipe = {k: v for k, v in content["recipe"].items() if k not in ("encoder", "features")}
    return {
        "path": training["settings"]["training"]["path"],
        "families_searched": _records(
            training["search"], CARD_SEARCH_KEYS, "training.json's search"
        ),
        "train_metrics": {key: training["metrics"][key] for key in TRAIN_METRIC_KEYS},
        "recipe": recipe,
        "calibration": content["calibration"],
        "calibration_methods": calibration[list(CARD_CALIBRATION_COLUMNS)].to_dict("records"),
        "reproducible_to": training["reproducible_to"],
    }


def _performance(tables: dict[str, pd.DataFrame], meta: dict, resolved: UseCaseConfig) -> dict:
    """The headline metrics' names, the intervals' level and replicates, the long metric rows and
    the baselines comparison (`available` where the comparison names no reason); no gate."""
    baselines = tables["baselines"]
    baselines = baselines.assign(available=baselines["unavailable"].eq(""))
    columns = ["scorer", "part", "metric", "value", "low", "high", "available"]
    return {
        "headline": meta["choices"]["headline"],
        "intervals": resolved.evaluation.intervals.model_dump(mode="json"),
        "metrics": tables["metrics"][CARD_METRIC_COLUMNS].to_dict("records"),
        "baselines": baselines[columns].to_dict("records"),
    }


def _warning_codes(warnings: list) -> list[dict]:
    """Evaluation's warnings as considerations: each warning's code and values, its `text`
    dropped. A warning that is not a mapping with a `code` (a sentence from an older run) fails."""
    codes = []
    for warning in warnings:
        if not (isinstance(warning, dict) and "code" in warning):
            raise ValueError(
                f"Evaluation's warning {warning!r} carries no code: the run was evaluated by an "
                "older framework version; evaluate it again"
            )
        codes.append({key: value for key, value in warning.items() if key != "text"})
    return codes


def _recorded_considerations(
    meta: dict, training: dict, selection: pd.DataFrame, run_ledger: pd.DataFrame
) -> list[dict]:
    """The considerations that recorded facts raise: validation periods earlier Evaluation runs
    scored other than this one's (the audit log, a moved validation period), a run reproducible
    to the recipe only (a time budget), constraints against EDA's direction, pruning undone."""
    raised = []
    earlier = {entry["validation_period"] for entry in meta["earlier_validations"]}
    moved = sorted(earlier - {meta["validation_period"]})
    if moved:
        raised.append({"code": "validation_period_moved", "earlier_periods": moved})
    if training["reproducible_to"] == "recipe":
        budget = training["settings"]["training"]["time_budget_s"]
        raised.append({"code": "reproducible_to_recipe", "time_budget_s": budget})
    against = run_ledger.loc[run_ledger["monotone_agrees"].eq(False).fillna(False), "feature"]
    if len(against):
        raised.append({"code": "monotone_against_eda", "features": against.tolist()})
    undone = selection.loc[selection["outcome"] == "undone", "feature"].tolist()
    if undone:
        raised.append({"code": "pruning_undone", "features": undone})
    return raised


def _plain(value: object) -> object:
    """`value` as JSON's own types, recursively: numpy values as Python, tuples and arrays as
    lists, a missing value (None, NaN, `pd.NA`, `pd.NaT`) as None; an infinity or any other type
    fails naming it."""
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple | np.ndarray):
        return [_plain(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, float) and math.isinf(value):
        raise ValueError("the model card holds an infinite value; a fact is finite or None")
    if isinstance(value, bool | int | float | str):
        return value
    raise TypeError(f"the model card cannot hold a {type(value).__name__}: {value!r}")
