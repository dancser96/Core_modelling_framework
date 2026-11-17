"""Training's gate: no model without data knowledge (`CLAUDE.md` §4.13; training.md → "The
gate").

`read_stage2` refuses to go on unless EDA and Feature Checks artifacts exist for the config's
data definition, with the settings and sources the resolved config has now, and the ledger is
the one those two runs wrote. `feature_set` gives the feature set in force and what Training
opens its log with: the held, excluded and kept features with the entries that set them.
`check_counts` and `check_kinds` compare the panel Training reads with what EDA saw (D-088): the
per-period counts on every client of the window, and each feature's type. `save_stage2` writes
the run's own copy of what it read. Nothing here runs an upstream stage: at `autonomous` that is
`run`'s job (D-132), so the refusals name `run`.
"""

from dataclasses import dataclass

import pandas as pd

from core_modelling.artifacts import local_path, read_upstream, write_json, write_parquet
from core_modelling.config import UseCaseConfig
from core_modelling.config.replay import Entry
from core_modelling.environment import EnvironmentConfig, feature_dir
from core_modelling.ledger import (
    LEDGER_SCHEMA_VERSION,
    read_ledger,
    render_decisions,
    resolve_features,
)

STAGE2 = ("eda", "feature_checks")  # the stages Training needs, in their run order
COUNT_COLUMNS = ["eligible_rows", "known_target", "positive_rows"]  # D-088's, per window period
STAGE2_TABLES = ("cells", "edges", "bins", "levels")  # EDA's tables a run keeps its own copy of
STAGE2_FILE = "_stage2.json"  # which versions and runs the copies in `stage2/` are of


@dataclass
class Stage2:
    """What the gate read: EDA's json and tables, Feature Checks' json, the ledger of the data
    definition (every candidate's row) and the two runs' tokens, `{stage: run_token}`."""

    eda_meta: dict
    eda_tables: dict[str, pd.DataFrame]
    feature_checks_meta: dict
    ledger: pd.DataFrame
    tokens: dict[str, str]


def missing_stage2(resolved: UseCaseConfig, entity: str, env: EnvironmentConfig) -> list[str]:
    """The stages of `STAGE2`, in run order, without a `<stage>.json` for the resolved config's
    data definition: the ones that have not run on it (a stale one is not missing)."""
    return [
        stage
        for stage in STAGE2
        if not (local_path(feature_dir(env, resolved, entity, stage)) / f"{stage}.json").is_file()
    ]


def read_stage2(resolved: UseCaseConfig, entity: str, env: EnvironmentConfig) -> Stage2:
    """EDA's and Feature Checks' artifacts of the resolved config's data definition. A stage
    that has not run is refused naming `run`; a stale one (other settings, other sources, another
    data definition) by `read_upstream`; a ledger from other runs than the two folders by
    `read_ledger`."""
    missing = missing_stage2(resolved, entity, env)
    if missing:
        raise FileNotFoundError(
            f"Training needs the artifacts of {' and '.join(missing)} for this data definition "
            f"and {feature_dir(env, resolved, entity)} holds none (no model without data "
            f"knowledge): run the stages in order with `run --stages {' '.join(STAGE2)} "
            "training`, or notebooks 02 and 03 first"
        )
    eda_meta, eda_tables = read_upstream(env, resolved, entity, "eda")
    feature_checks_meta, _ = read_upstream(env, resolved, entity, "feature_checks")
    tokens = {"eda": eda_meta["run_token"], "feature_checks": feature_checks_meta["run_token"]}
    ddh = resolved.housekeeping["data_definition_hash"]
    ledger = read_ledger(feature_dir(env, resolved, entity), ddh, tokens)
    return Stage2(eda_meta, eda_tables, feature_checks_meta, ledger, tokens)


def feature_set(
    stage2: Stage2, resolved: UseCaseConfig, entries: list[Entry]
) -> tuple[list[str], dict, list[str]]:
    """`(the feature set in force, its log entry, the warnings)`.

    The features are `resolve_features`' (candidates − lineage − unsupported − excluded − held).
    The entry names the held, excluded and kept features with the numbers of the audit-log
    entries that set them, beside the count Feature Checks' run held. A feature that run held
    and that now has no decision at all was released by a `revert`: a warning, never a refusal.
    A constraint or a level order on a name that is no candidate fails loud.
    """
    ledger = stage2.ledger
    features = resolve_features(ledger, resolved)
    named = {**resolved.training.monotone, **resolved.features.order}
    unknown = sorted(set(named) - set(ledger["feature"]))
    if unknown:
        raise ValueError(
            f"training.monotone or features.order names {unknown}, which are no candidates of "
            "this data definition; name candidates only"
        )
    decided = render_decisions(ledger, resolved, entries).set_index("feature")
    by_verdict = {
        verdict: decided.index[decided["verdict"] == verdict].tolist()
        for verdict in ("held", "excluded", "kept")
    }
    held_then = stage2.feature_checks_meta["held"]
    released = [name for name in held_then if decided.loc[name, "verdict"] == "pass"]
    entry = {
        "step": "feature_set",
        "features": len(features),
        "held": by_verdict["held"],
        "excluded": {name: int(decided.loc[name, "excluded"]) for name in by_verdict["excluded"]},
        "kept": {name: list(decided.loc[name, "kept"]) for name in by_verdict["kept"]},
        "held_by_feature_checks": len(held_then),
        "released": released,
    }
    warnings = []
    if released:
        warnings.append(
            f"{len(released)} features Feature Checks' run held are in training with no decision "
            f"({', '.join(released)}): a revert undid their flags; rerun feature_checks to hold "
            "them again, or record a keep or an exclude"
        )
    return features, entry, warnings


def save_stage2(folder: str, stage2: Stage2, final: list[str]) -> None:
    """Write a run's own copy of what it needs from Stage 2 into `folder` (its `stage2/`, which
    must not exist), so an EDA rerun never changes the run (D-139 (b)): the ledger rows of every
    candidate (the sign-off table lists the held and the excluded ones too) and, for the `final`
    features, EDA's cells (the shares per period), its numeric bin edges and its lift tables
    (`bins`, `levels`). `STAGE2_FILE` records which versions the copies are of (EDA's stage
    version and the ledger's, as read) and the two runs' tokens: a copy carries no sidecar of
    its own, and a later reader must refuse one it cannot read."""
    target = local_path(folder)
    target.mkdir()
    write_parquet(stage2.ledger, target / "ledger.parquet")
    for name in STAGE2_TABLES:
        table = stage2.eda_tables[name]
        write_parquet(table.loc[table["feature"].isin(final)], target / f"{name}.parquet")
    versions = {
        "eda_schema_version": stage2.eda_meta["schema_version"],
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
        "runs": stage2.tokens,
    }
    write_json(versions, target / STAGE2_FILE)


def check_counts(population: pd.DataFrame, eda_population: list[dict]) -> None:
    """Fail loud unless each window period's `COUNT_COLUMNS` on the panel Training read equal
    the ones EDA stored (D-088): a panel that changed under an unchanged data definition is
    other data than EDA described. `population` is the frames' (one row per window period, every
    client, before the split and any sampling); `eda_population` is `eda.json`'s, whose window
    periods are the ones with a `known_target` (its other compared periods have none). A window
    period EDA counted and the panel no longer holds differs too."""
    stored = pd.DataFrame(eda_population).set_index("period")
    counted = stored.index[stored["known_target"].notna()]
    differing = [
        f"{period}: EDA counted it, the panel holds no row of it now"
        for period in counted
        if period not in set(population["period"])
    ]
    for row in population.itertuples():
        if row.period not in stored.index:
            differing.append(f"{row.period}: not among EDA's periods")
            continue
        for column in COUNT_COLUMNS:
            then, now = stored.loc[row.period, column], getattr(row, column)
            if pd.isna(then) or int(then) != int(now):
                stored_count = "none" if pd.isna(then) else int(then)
                differing.append(f"{row.period} {column}: EDA {stored_count}, now {int(now)}")
    if differing:
        raise ValueError(
            "the panel is not the one EDA described, although the data definition is the same "
            f"({'; '.join(differing[:6])}): a source changed after it was read; rerun eda, then "
            "feature_checks, before training"
        )


def check_kinds(ledger: pd.DataFrame, kinds: dict[str, str]) -> None:
    """Fail loud when a feature's kind on the panel (`kinds`, from the Spark schema with the
    config's overrides) is not the ledger's: a column changed type since EDA ran."""
    stored = ledger.set_index("feature")["kind"]
    changed = [
        f"{name}: {stored[name]} in the ledger, {kind} now"
        for name, kind in kinds.items()
        if stored[name] != kind
    ]
    if changed:
        raise ValueError(
            f"feature types changed since EDA ran ({'; '.join(changed)}): rerun eda, then "
            "feature_checks, before training"
        )
