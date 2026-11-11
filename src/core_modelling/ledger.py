"""The feature ledger (D-134, D-136): one row per candidate of a data definition.

EDA creates it (`create_ledger`, then its statistics with `add_columns`), Feature Checks appends
its columns, and both save it with `save_ledger` as `ledger.parquet` + `_ledger.json` in
`<use_case>/04_feature/<ddh>/`, beside the stage folders; the caller passes that folder and the
sidecar records the data-definition hash and, per stage whose columns the file holds, the run
token that stage also wrote into its `<stage>.json`. A stage saves the ledger before it writes
its own folder, so `<stage>.json` is the commit marker, and `read_ledger(..., expect=...)` refuses
a ledger from another run. `read_candidates` gives the rows a step reads. The ledger
decides nothing and stores no decision: `render_decisions` derives `held`, `kept`, `excluded` and
`verdict` from the resolved config and the audit log's entries whenever a view is drawn, and
`resolve_features` gives Training its feature set (candidates − lineage − unsupported − excluded
− held). Local paths only in 0.x, through `artifacts.py` (D-136).
"""

import json
import os

import numpy as np
import pandas as pd

from core_modelling import __version__
from core_modelling.artifacts import local_path, read_parquet, utc_now, write_json, write_parquet
from core_modelling.config.identities import short
from core_modelling.config.replay import Entry, check_resolved, decisions_in_force
from core_modelling.config.schema import UseCaseConfig

LEDGER_SCHEMA_VERSION = 3  # 2: the identity column `source` (11-06); 3: the sidecar's `runs`
LEDGER_FILE = "ledger.parquet"
SIDECAR_FILE = "_ledger.json"  # starts with `_`, never `_metadata` (T21)

# The stored columns by who writes them (`feature_ledger.md`): `identity` at creation, then each
# stage its own. `levels` comes with EDA's statistics, from the snapshot's cells.
COLUMNS_BY_STAGE: dict[str, list[str]] = {
    "identity": ["feature", "kind", "source", "lineage", "unsupported"],
    "eda": [
        "levels", "concordance", "concordance_se", "direction", "concordance_best_order",
        "non_monotone", "concordance_window", "missing_share", "missing_share_window",
        "null_concordance", "null_concordance_window", "zero_share", "zero_share_window",
        "dominant_share", "dominant_share_window", "rank", "key_feature", "represented_by",
    ],
    "feature_checks": [
        "flags", "notes", "lagged_concordance", "signal_kept", "constant_share",
        "concordance_range", "heterogeneity_p", "psi_window", "psi_latest", "new_level_share",
        "cluster", "explained_by_others", "partners",
    ],
}  # fmt: skip
STAGES = ("eda", "feature_checks")  # the keys `add_columns` takes
# Derived when the ledger is read, never stored: a stored decision goes stale with the next entry.
DERIVED_COLUMNS = ["held", "kept", "excluded", "verdict"]
KINDS = ("numeric", "categorical")


def _check_identity(
    candidates: list[str],
    kinds: dict[str, str],
    lineage: list[str],
    unsupported: list[str],
    sources: dict[str, str],
) -> None:
    """Refuse identity inputs the ledger cannot record faithfully, naming the features."""
    repeated = sorted({f for f in candidates if candidates.count(f) > 1})
    if repeated:
        raise ValueError(f"the candidates name {repeated} more than once")
    outside = sorted(set(lineage + unsupported) - set(candidates))
    if outside:
        raise ValueError(
            f"the lineage or unsupported columns {outside} are not among the candidates; each "
            "keeps a row in the ledger, so pass them as candidates"
        )
    odd = {f: kind for f, kind in kinds.items() if kind not in KINDS}
    if odd:
        raise ValueError(f"a kind is one of {KINDS}; refused {odd}")
    no_kind = [f for f in candidates if f not in kinds and f not in unsupported + lineage]
    if no_kind:
        raise ValueError(f"no kind for the candidates {no_kind}")
    clash = {f: kinds[f] for f in unsupported if f in kinds}
    if clash:
        raise ValueError(f"{sorted(clash)} are unsupported but have a kind: {clash}")
    no_source = [f for f in candidates if f not in sources and f not in lineage]
    if no_source:
        raise ValueError(f"no source for the candidates {no_source}")


def create_ledger(
    candidates: list[str],
    kinds: dict[str, str],
    lineage: list[str],
    unsupported: list[str],
    sources: dict[str, str],
) -> pd.DataFrame:
    """A new ledger, one row per candidate with its identity columns. An unsupported column's kind
    is `unsupported`; a lineage column EDA did not read may have none; every other candidate
    needs `numeric` or `categorical`, since Training's encoder reads it. `sources` maps a column
    to the source it comes from (the frames' `meta["column_sources"]`): every candidate has one, a
    lineage column in no source (an upstream target's) none."""
    _check_identity(candidates, kinds, lineage, unsupported, sources)
    return pd.DataFrame(
        {
            "feature": candidates,
            "kind": ["unsupported" if f in unsupported else kinds.get(f) for f in candidates],
            "source": [sources.get(f) for f in candidates],
            "lineage": [f in lineage for f in candidates],
            "unsupported": [f in unsupported for f in candidates],
        }
    )


def _owner(column: str) -> str:
    """Who writes a column, for a refusal's message."""
    if column in DERIVED_COLUMNS:
        return "derived when read"
    owners = [stage for stage, columns in COLUMNS_BY_STAGE.items() if column in columns]
    return owners[0] if owners else "no stage"


def _check_stage_columns(ledger: pd.DataFrame, columns: pd.DataFrame, stage: str) -> None:
    """Refuse a stage's columns that are not its own or not one row per candidate it read."""
    if stage not in STAGES:
        raise ValueError(f"stage {stage!r} writes no ledger columns; the stages are {STAGES}")
    if "feature" not in columns:
        raise ValueError(f"stage {stage}: the columns to add need a `feature` column")
    foreign = [c for c in columns if c != "feature" and c not in COLUMNS_BY_STAGE[stage]]
    if foreign:
        owners = {c: _owner(c) for c in foreign}
        raise ValueError(f"stage {stage} may write only its own ledger columns; refused {owners}")
    repeated = sorted(set(columns.loc[columns["feature"].duplicated(), "feature"]))
    if repeated:
        raise ValueError(f"stage {stage}: the columns to add repeat the features {repeated}")
    unknown = sorted(set(columns["feature"]) - set(ledger["feature"]))
    if unknown:
        raise ValueError(f"stage {stage}: {unknown} are not in the ledger (one row per candidate)")
    missing = [f for f in read_candidates(ledger)["feature"] if f not in set(columns["feature"])]
    if missing:
        raise ValueError(
            f"stage {stage}: no row for the candidates {missing}; every candidate it read needs "
            "one (a null value is fine, a missing feature is not)"
        )


def add_columns(ledger: pd.DataFrame, columns: pd.DataFrame, stage: str) -> pd.DataFrame:
    """The ledger with a stage's columns joined on `feature`. Every column the stage wrote before
    is dropped first, so a rerun leaves none of its earlier columns (a skipped step's included);
    another stage's columns are never touched. The rows the stage has no value for (lineage and
    unsupported) hold None in its object and list columns, as the saved ledger reads back."""
    _check_stage_columns(ledger, columns, stage)
    earlier = [c for c in COLUMNS_BY_STAGE[stage] if c in ledger]
    merged = ledger.drop(columns=earlier).merge(
        columns, on="feature", how="left", validate="one_to_one"
    )
    for column in columns:
        if column != "feature" and merged[column].dtype == object:
            merged[column] = merged[column].where(merged[column].notna(), None)
    return merged


def _check_storable(ledger: pd.DataFrame) -> None:
    """Refuse a derived column (it would go stale with the next entry, V10) or one no stage owns."""
    derived = [c for c in DERIVED_COLUMNS if c in ledger]
    if derived:
        raise ValueError(
            f"the ledger's {derived} are derived when it is read (render_decisions), never "
            "stored: a stored decision goes stale with the next entry (V10)"
        )
    stored = {c for columns in COLUMNS_BY_STAGE.values() for c in columns}
    unknown = [c for c in ledger if c not in stored]
    if unknown:
        raise ValueError(f"the ledger columns {unknown} belong to no stage (COLUMNS_BY_STAGE)")


def _sidecar(ledger: pd.DataFrame, meta: dict) -> dict:
    """`_ledger.json`'s content: the version stamp, the `data_definition_hash` and `runs`, the
    run token of each stage whose columns the file holds, in `STAGES` order."""
    keys = {"data_definition_hash", "runs"}
    missing, other = sorted(keys - set(meta)), sorted(set(meta) - keys)
    if missing or other:
        raise ValueError(
            f"save_ledger's meta holds data_definition_hash and runs; it lacks {missing} and may "
            f"not set {other}"
        )
    present = [stage for stage in STAGES if set(COLUMNS_BY_STAGE[stage]) & set(ledger)]
    if sorted(meta["runs"]) != sorted(present):
        raise ValueError(
            f"save_ledger's runs name {sorted(meta['runs'])}, but the ledger holds the columns of "
            f"{present}: one run token per stage whose columns it holds"
        )
    return {
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
        "framework_version": __version__,
        "written_at": utc_now(),
        "data_definition_hash": meta["data_definition_hash"],
        "runs": {stage: meta["runs"][stage] for stage in present},
    }


def save_ledger(ledger: pd.DataFrame, folder: str, meta: dict) -> None:
    """Write `ledger.parquet` and `_ledger.json` into the data definition's folder, each to a
    temporary name first (removed when a write fails) and then renamed, so a crash never leaves
    half a file. `meta` holds the `data_definition_hash` and `runs`, `{stage: run_token}` for
    every stage whose columns the ledger holds (EDA: its own; Feature Checks: the EDA run's it
    read and its own). A stage calls it before `write_stage`, so `<stage>.json` is the commit
    marker: a crash in between leaves a new ledger beside the old json, whose tokens differ and
    the next reader's `read_ledger(..., expect=...)` refuses, never an old ledger beside a new
    json."""
    _check_storable(ledger)
    sidecar = _sidecar(ledger, meta)
    target = local_path(folder)
    target.mkdir(parents=True, exist_ok=True)
    parquet = target / f"{LEDGER_FILE}.tmp-{os.getpid()}"
    stamp = target / f"{SIDECAR_FILE}.tmp-{os.getpid()}"
    try:
        write_parquet(ledger, parquet)
        write_json(sidecar, stamp)
    except BaseException:
        parquet.unlink(missing_ok=True)
        stamp.unlink(missing_ok=True)
        raise
    # The sidecar first: a crash between the two then leaves the new run's tokens beside the
    # old table, which `read_ledger(..., expect=...)` refuses; the other order would pass the
    # new table under the old tokens.
    stamp.replace(target / SIDECAR_FILE)
    parquet.replace(target / LEDGER_FILE)


def read_ledger(
    folder: str, data_definition_hash: str | None = None, expect: dict[str, str] | None = None
) -> pd.DataFrame:
    """The saved ledger; a missing one asks for an EDA run, another `ledger_schema_version` is
    refused before the parquet is read, and so is a ledger written for another data definition
    than `data_definition_hash` when one is given. `expect`, `{stage: run_token}` from the stage
    jsons the caller read, refuses a ledger whose runs differ: it and that stage's folder come
    from different runs (a crash between the ledger's save and the folder's write)."""
    target = local_path(folder)
    if not (target / SIDECAR_FILE).is_file():
        raise FileNotFoundError(f"no feature ledger at {folder}: run EDA first")
    sidecar = json.loads((target / SIDECAR_FILE).read_text())
    version = sidecar.get("ledger_schema_version")
    if version != LEDGER_SCHEMA_VERSION:
        raise ValueError(
            f"the feature ledger at {folder} has ledger_schema_version {version} (written by "
            f"framework {sidecar.get('framework_version')}); this version reads "
            f"{LEDGER_SCHEMA_VERSION}: rerun EDA, or raise the use case's framework pin when it "
            "is newer"
        )
    stored = sidecar.get("data_definition_hash")
    if data_definition_hash is not None and stored != data_definition_hash:
        raise ValueError(
            f"the feature ledger at {folder} was written for data definition "
            f"{short(str(stored))}, the config's is {short(data_definition_hash)}: rerun EDA"
        )
    runs = sidecar.get("runs", {})
    for stage, token in (expect or {}).items():
        if runs.get(stage) != token:
            raise ValueError(
                f"the feature ledger at {folder} and {stage}/ come from different runs (the "
                f"ledger's {stage} run token is {runs.get(stage)}, {stage}.json's {token}): "
                f"rerun {stage}"
            )
    return read_parquet(target / LEDGER_FILE)


def read_candidates(ledger: pd.DataFrame) -> pd.DataFrame:
    """The rows a step reads: the candidates that are neither lineage nor unsupported (the
    automatic exclusions), in the ledger's order."""
    return ledger.loc[~(ledger["lineage"] | ledger["unsupported"])]


def _check_named_features(ledger: pd.DataFrame, resolved: UseCaseConfig) -> None:
    """Refuse a name in `features.excluded`, `held` or `kept` that is no ledger row: a mistyped
    entry would otherwise change nothing (the candidate patterns accept any name)."""
    rows = set(ledger["feature"])
    unknown = {
        f"features.{name}": sorted(set(getattr(resolved.features, name)) - rows)
        for name in ("excluded", "held", "kept")
    }
    unknown = {path: names for path, names in unknown.items() if names}
    if unknown:
        raise ValueError(
            f"the resolved config names features that are not candidates of this data "
            f"definition (no ledger row): {unknown}; correct the entries' feature names"
        )


def render_decisions(
    ledger: pd.DataFrame, resolved: UseCaseConfig, entries: list[Entry]
) -> pd.DataFrame:
    """The ledger with its derived columns, for a view: `held` (an open flag, not excluded),
    `kept` (the numbers of the `keep` entries in force), `excluded` (the number of the `exclude`
    in force, null when none) and `verdict` (`auto_excluded`, else `excluded`, else `held`, else
    `kept`, else `pass`). `entries` are the ones `resolved` was replayed from."""
    check_resolved(resolved, "render_decisions")
    replayed_to, last = resolved.housekeeping["replayed_to"], entries[-1].seq if entries else 0
    if replayed_to != last:
        raise ValueError(
            f"the config was resolved to entry {replayed_to} and the entries end at {last}: the "
            "entry numbers would describe another state than the verdicts; pass the entries the "
            "config was resolved from"
        )
    _check_named_features(ledger, resolved)
    kept, excluded = decisions_in_force(entries)
    view = ledger.copy()
    feature = view["feature"]
    is_excluded = feature.isin(resolved.features.excluded)
    view["held"] = feature.isin(resolved.features.held) & ~is_excluded
    view["kept"] = [kept.get(name, []) for name in feature]
    view["excluded"] = pd.array([excluded.get(name) for name in feature], dtype="Int64")
    view["verdict"] = np.select(
        [
            view["lineage"] | view["unsupported"],
            is_excluded,
            view["held"],
            feature.isin(resolved.features.kept),
        ],
        ["auto_excluded", "excluded", "held", "kept"],
        default="pass",
    )
    return view


def resolve_features(ledger: pd.DataFrame, resolved: UseCaseConfig) -> list[str]:
    """Training's feature set: candidates − lineage − unsupported − excluded − held, in the
    ledger's order. In effect, for Training, a held feature is an excluded feature without a
    final decision: the model is built without it until a person keeps or excludes it (§4.6,
    D-134). A name in the decisions that is no ledger row is refused, and so is a config that was
    only loaded: its held and excluded lists are empty until the replay fills them."""
    check_resolved(resolved, "resolve_features")
    _check_named_features(ledger, resolved)
    out = set(resolved.features.excluded) | set(resolved.features.held)
    read = read_candidates(ledger)
    return read.loc[~read["feature"].isin(out), "feature"].tolist()
