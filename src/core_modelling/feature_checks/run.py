"""`run_feature_checks`: the Feature Checks stage for one entity, in the order of
docs/components/feature_checks.md "How one run flows".

It resolves the config (the audit log replayed, D-125), reads EDA's artifacts and the ledger for
the data definition (refusing a missing or stale EDA, whose settings digest no longer matches,
and a ledger whose EDA run token is not `eda.json`'s),
runs the five steps of `steps.py` in their fixed order, a step left out of a present
`feature_checks` mapping skipped, and stacks their findings. It then writes the audit log: the
`flag` entries `decisions.flag_entries` decides (changed feature sets only, so a rerun on
unchanged data writes none) and one `run` entry with the compared periods (D-088). The log read
again gives the held set and the proposed decisions; Feature Checks' ledger columns are
appended, a skipped step's as null so readers always find the column set; the views and the
report (`report.py`) are built before anything is saved; then the ledger is saved and
`feature_checks/` written with `report.html` in it, `feature_checks.json` being the commit
marker (D-136). It orchestrates only: every statistic is in `steps.py` and `measures.py`, and
it reads EDA's artifacts alone, so `spark` is never used. A flag holds a feature out of training
at both automation levels until a person keeps or excludes it; a note never does (D-134).
"""

import time

import numpy as np
import pandas as pd
from pyspark.sql import SparkSession

from core_modelling.artifacts import (
    StageResult,
    lap,
    new_run_token,
    read_upstream,
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
from core_modelling.config.replay import open_flags
from core_modelling.environment import EnvironmentConfig, feature_dir
from core_modelling.feature_checks.decisions import (
    flag_entries,
    held_summary,
    proposed_decisions,
)
from core_modelling.feature_checks.findings import (
    FINDING_COLUMNS,
    FINDINGS,
    UNAVAILABLE_COLUMNS,
    stack_parts,
    step_findings,
)
from core_modelling.feature_checks.inputs import CheckInputs, check_inputs
from core_modelling.feature_checks.measures import PERIOD_GROUPS
from core_modelling.feature_checks.report import build_views, report_sections
from core_modelling.feature_checks.steps import CLUSTER_COLUMNS, STEP_COLUMNS, STEPS, StepResult
from core_modelling.ledger import (
    COLUMNS_BY_STAGE,
    add_columns,
    read_ledger,
    render_decisions,
    save_ledger,
)
from core_modelling.reporting.html import render_report

# A skipped step's ledger columns are null, typed as the step writes them (float otherwise).
NULL_DTYPES = {"cluster": "Int64", "partners": object}
RUN_REASON = "Feature Checks compared these periods: the window, the gap and the latest period."


def run_feature_checks(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, spark: SparkSession
) -> StageResult:
    """Feature Checks for one entity: the findings, the audit log's `flag` and `run` entries, the
    ledger's columns and `feature_checks/` with `report.html` written under the data definition's
    folder; the result carries the resolved config after the run's entries (the held set in
    `features.held`, D-134). `spark` is never used: it keeps the one shape `run` loops over.

    A render failure raises before the ledger or the folder is written: the audit-log entries
    stay written and the previous ledger and `feature_checks/` stay in place. The next run then
    writes no new `flag` entry, so its `entries_written` lists only its `run` entry; the flags
    the failed run wrote show in the audit log's table.
    """
    seconds: dict[str, float] = {}
    start = time.perf_counter()
    resolved = resolve_config(cfg, entity, env)
    eda_meta, eda_tables, ledger = _read_eda(resolved, entity, env)
    seconds["read"], start = lap(start)
    inputs = check_inputs(ledger, eda_tables, eda_meta, resolved)
    seconds["inputs"], start = lap(start)
    outputs = _run_steps(inputs, resolved, seconds)
    start = time.perf_counter()
    findings = stack_parts([out.findings for out in outputs.values()], FINDING_COLUMNS)
    written = _write_entries(cfg, entity, env, findings, list(outputs), resolved, eda_meta)
    after = resolve_config(cfg, entity, env)
    entries = load_entries(after, entity, env)
    flags = open_flags(entries)
    seconds["audit_log"], start = lap(start)
    tables = {
        "findings": findings,
        "unavailable": stack_parts(
            [out.unavailable for out in outputs.values()], UNAVAILABLE_COLUMNS
        ),
        "per_period": inputs.per_period,
        "clusters": _clusters(outputs),
        "proposed_decisions": proposed_decisions(findings, flags, entity),
    }
    columns = _ledger_columns(inputs.ledger, outputs, findings)
    ledger = add_columns(ledger, columns, "feature_checks")
    held = held_summary(ledger, flags, findings)
    meta = _stage_meta(resolved, eda_meta, list(outputs), findings, held, written)
    meta["timings"] = {"seconds": seconds}
    decided = render_decisions(ledger, after, entries)
    views = build_views(tables, eda_tables["concordance_per_period"], meta, after, decided,
                        held, show_decisions(cfg, entity, env))  # fmt: skip
    result = StageResult(tables=tables, ledger=ledger, log=[], meta=meta, paths={}, views=views,
                         frame=None, config=after)  # fmt: skip
    _write(result, env, entity, eda_meta["run_token"])
    return result


def _read_eda(
    resolved: UseCaseConfig, entity: str, env: EnvironmentConfig
) -> tuple[dict, dict[str, pd.DataFrame], pd.DataFrame]:
    """EDA's json, tables and the ledger of the data definition; a missing artifact is refused
    by its reader ("run the eda stage first", "run EDA first"), an EDA run with other settings
    than the resolved config's by `read_upstream`, naming the changed path, and a ledger from
    another EDA run than `eda/` by `read_ledger` (the run tokens differ)."""
    meta, tables = read_upstream(env, resolved, entity, "eda")
    ddh = resolved.housekeeping["data_definition_hash"]
    ledger = read_ledger(feature_dir(env, resolved, entity), ddh, {"eda": meta["run_token"]})
    return meta, tables, ledger


def _run_steps(
    inputs: CheckInputs, resolved: UseCaseConfig, seconds: dict[str, float]
) -> dict[str, StepResult]:
    """Each step whose `feature_checks` entry is present, in the run order, by name; a step's
    seconds go into `seconds`."""
    outputs = {}
    for name, step in STEPS.items():
        params = getattr(resolved.feature_checks, name)
        if params is None:  # left out of a present mapping: skipped, stated in the report
            continue
        start = time.perf_counter()
        outputs[name] = step(inputs, params)
        seconds[name], _ = lap(start)
    return outputs


def _clusters(outputs: dict[str, StepResult]) -> pd.DataFrame:
    """The redundancy step's clusters; an empty table of `CLUSTER_COLUMNS` when it was skipped."""
    if "redundancy" in outputs:
        return outputs["redundancy"].tables["clusters"]
    return pd.DataFrame(columns=CLUSTER_COLUMNS).astype({"cluster": "Int64"})


def _ledger_columns(
    read: pd.DataFrame, outputs: dict[str, StepResult], findings: pd.DataFrame
) -> pd.DataFrame:
    """Feature Checks' ledger columns for every read candidate, in `COLUMNS_BY_STAGE` order:
    `flags` and `notes` (the full names this run raised, in table order, empty lists when none),
    each step's columns, and a skipped step's as null."""
    columns = read[["feature"]].copy()
    position = {name: i for i, name in enumerate(FINDINGS)}
    raised = findings.assign(position=findings["finding"].map(position))
    raised = raised.sort_values("position", kind="stable")
    for kind, column in (("flag", "flags"), ("note", "notes")):
        names = raised.loc[raised["kind"] == kind].groupby("feature")["finding"]
        by_feature = names.agg(lambda found: list(dict.fromkeys(found))).to_dict()
        columns[column] = [by_feature.get(feature, []) for feature in columns["feature"]]
    for out in outputs.values():
        columns = columns.merge(out.columns, on="feature", how="left", validate="one_to_one")
    skipped = [column for step in STEPS if step not in outputs for column in STEP_COLUMNS[step]]
    for column in skipped:
        dtype = NULL_DTYPES.get(column, float)
        nulls = [None] * len(columns) if dtype is object else np.nan
        columns[column] = pd.Series(nulls, index=columns.index, dtype=dtype)
    return columns[["feature", *COLUMNS_BY_STAGE["feature_checks"]]]


def _write_entries(
    cfg: UseCaseConfig,
    entity: str,
    env: EnvironmentConfig,
    findings: pd.DataFrame,
    ran: list[str],
    resolved: UseCaseConfig,
    eda_meta: dict,
) -> list[dict]:
    """The `flag` entries `flag_entries` decides, then one `run` entry with every compared
    period's label and the `replayed_to` and resolved-input hash of the config the run read;
    each written entry's `seq`, `op` and `finding` (None for the run)."""
    entries = load_entries(resolved, entity, env, warn_if_missing=False)
    written = [
        record_stage_entry(cfg, entity, env, stage="feature_checks", **entry)
        for entry in flag_entries(findings, entries, ran)
    ]
    periods = [label for group in PERIOD_GROUPS for label in eda_meta["compared_periods"][group]]
    housekeeping = resolved.housekeeping
    written.append(record_stage_entry(
        cfg, entity, env, stage="feature_checks", op="run", reason=RUN_REASON, periods=periods,
        replayed_to=housekeeping["replayed_to"],
        resolved_input_hash=housekeeping["resolved_input_hash"],
    ))  # fmt: skip
    return [{"seq": entry.seq, "op": entry.op, "finding": entry.finding} for entry in written]


def _raised_summary(findings: pd.DataFrame, ran: list[str]) -> dict[str, dict]:
    """Per finding of the steps that ran, in table order: its kind, how many features raised it
    and which (the values stay in `tables/findings`)."""
    summary = {}
    for step in ran:
        for name in step_findings(step):
            features = findings.loc[findings["finding"] == name, "feature"].tolist()
            summary[name] = {"kind": FINDINGS[name]["kind"], "count": len(features),
                             "features": features}  # fmt: skip
    return summary


def _stage_meta(
    resolved: UseCaseConfig,
    eda_meta: dict,
    ran: list[str],
    findings: pd.DataFrame,
    held: pd.DataFrame,
    written: list[dict],
) -> dict:
    """`feature_checks.json` without the timings: the hashes, `replayed_to` and the settings
    digest Training checks of the run's input (`stage_identity`: the thresholds the steps ran
    with), the run token, the compared periods, the steps run and skipped, the findings raised,
    the held features, the entries written and EDA's headline."""
    return {
        **stage_identity(resolved, "feature_checks"),
        "run_token": new_run_token(),
        "snapshot_period": eda_meta["snapshot_period"],
        "compared_periods": eda_meta["compared_periods"],
        "steps_run": ran,
        "steps_skipped": [step for step in STEPS if step not in ran],
        "findings": _raised_summary(findings, ran),
        "held": held["feature"].tolist(),
        "entries_written": written,
        "eda_headline": eda_meta["headline"],
    }


def _write(result: StageResult, env: EnvironmentConfig, entity: str, eda_token: str) -> None:
    """Render the report, then write in the commit order: the ledger saved with the run tokens
    of the EDA run it read (`eda_token`) and of this run, `feature_checks/` written with
    `report.html` in it (`feature_checks.json` is the commit marker). A render error leaves the
    previous ledger and folder as they were, the audit-log entries written."""
    resolved, meta = result.config, result.meta
    title = f"Feature Checks: {resolved.use_case} ({entity})"
    page = render_report(title, report_sections(result.views))
    runs = {"eda": eda_token, "feature_checks": meta["run_token"]}
    sidecar = {"data_definition_hash": meta["data_definition_hash"], "runs": runs}
    save_ledger(result.ledger, feature_dir(env, resolved, entity), sidecar)
    folder = feature_dir(env, resolved, entity, "feature_checks")
    result.paths = write_stage(result, folder, "feature_checks", texts={"report.html": page})
