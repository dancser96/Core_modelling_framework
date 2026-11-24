"""Training's gate: no model without data knowledge (`CLAUDE.md` §4.13; training.md → "The
gate").

`read_stage2` refuses to go on unless EDA and Feature Checks artifacts exist for the config's
data definition, with the settings and sources the resolved config has now, and the ledger is
the one those two runs wrote. `feature_set` gives the feature set in force and what Training
opens its log with: the held, excluded and kept features with the entries that set them.
`check_counts` and `check_kinds` compare the panel Training reads with what EDA saw (D-088): the
per-period counts on every client of the window, and each feature's type; `check_target_range`
refuses a target the objective cannot fit. `save_stage2` writes the run's own copy of what it
read, exactly the copy's frozen columns (`run_artifacts.STAGE2_COLUMNS`, which `read_stage2`
checks are there before the run number), and `run_artifacts.read_stage2_copy` reads it back
after checking the copy's own version. Nothing here runs an upstream stage: at `autonomous`
that is `run`'s job (D-132), so the refusals name `run`.
"""

from dataclasses import dataclass

import pandas as pd

from core_modelling.artifacts import local_path, read_upstream, write_json, write_parquet
from core_modelling.config import UseCaseConfig
from core_modelling.config.replay import Entry
from core_modelling.environment import EnvironmentConfig, feature_dir
from core_modelling.ledger import (
    LEDGER_SCHEMA_VERSION,
    STAGES,
    missing_stage2,
    read_ledger,
    render_decisions,
    resolve_features,
)
from core_modelling.run_artifacts import (
    BASE_COLUMN,
    CONTRIBUTION_SUFFIX,
    STAGE2_COLUMNS,
    STAGE2_COPY_SCHEMA_VERSION,
    STAGE2_FILE,
    STAGE2_TABLES,
)
from core_modelling.training.selection import NOISE_COLUMNS

COUNT_COLUMNS = ["eligible_rows", "known_target", "positive_rows"]  # D-088's, per window period
# The objectives whose deviance is defined on targets of 0 and above only (a log link)
NON_NEGATIVE_OBJECTIVES = ("tweedie", "poisson")


@dataclass
class Stage2:
    """What the gate read: EDA's json and tables, Feature Checks' json, the ledger of the data
    definition (every candidate's row) and the two runs' tokens, `{stage: run_token}`."""

    eda_meta: dict
    eda_tables: dict[str, pd.DataFrame]
    feature_checks_meta: dict
    ledger: pd.DataFrame
    tokens: dict[str, str]


def read_stage2(resolved: UseCaseConfig, entity: str, env: EnvironmentConfig) -> Stage2:
    """EDA's and Feature Checks' artifacts of the resolved config's data definition. A stage
    that has not run is refused naming `run`; a stale one (other settings, other sources, another
    data definition) by `read_upstream`; a ledger from other runs than the two folders by
    `read_ledger`; a table without the columns the run's copy keeps by `check_stage2_columns`."""
    missing = missing_stage2(resolved, entity, env)
    if missing:
        raise FileNotFoundError(
            f"Training needs the artifacts of {' and '.join(missing)} for this data definition "
            f"and {feature_dir(env, resolved, entity)} holds none (no model without data "
            f"knowledge): run the stages in order with `run --stages {' '.join(STAGES)} "
            "training`, or notebooks 02 and 03 first"
        )
    eda_meta, eda_tables = read_upstream(env, resolved, entity, "eda")
    feature_checks_meta, _ = read_upstream(env, resolved, entity, "feature_checks")
    tokens = {"eda": eda_meta["run_token"], "feature_checks": feature_checks_meta["run_token"]}
    ddh = resolved.housekeeping["data_definition_hash"]
    ledger = read_ledger(feature_dir(env, resolved, entity), ddh, tokens)
    stage2 = Stage2(eda_meta, eda_tables, feature_checks_meta, ledger, tokens)
    check_stage2_columns(stage2)
    return stage2


def _copied_tables(stage2: Stage2) -> dict[str, pd.DataFrame]:
    """The tables the run's copy is taken from, by `STAGE2_COLUMNS`' names: the ledger and EDA's
    `STAGE2_TABLES`, whole."""
    return {"ledger": stage2.ledger, **{name: stage2.eda_tables[name] for name in STAGE2_TABLES}}


def check_stage2_columns(stage2: Stage2) -> None:
    """Fail loud, naming the table and the columns, when the ledger or one of EDA's tables lacks
    a column of `STAGE2_COLUMNS`, the run's copy's frozen columns."""
    for name, table in _copied_tables(stage2).items():
        missing = [column for column in STAGE2_COLUMNS[name] if column not in table]
        if missing:
            raise ValueError(
                f"Stage 2's {name} table lacks the columns {missing} the run's stage2/ copy "
                f"keeps (stage2_copy_schema_version {STAGE2_COPY_SCHEMA_VERSION}): rerun eda, "
                "then feature_checks, with this framework version"
            )


def feature_set(
    stage2: Stage2, resolved: UseCaseConfig, entries: list[Entry]
) -> tuple[list[str], dict, list[str]]:
    """`(the feature set in force, its log entry, the warnings)`.

    The features are `resolve_features`' (candidates − lineage − unsupported − excluded − held).
    The entry names the held, excluded and kept features with the numbers of the audit-log
    entries that set them, beside the count Feature Checks' run held. A feature that run held
    and that now has no decision at all was released by a `revert`: a warning, never a refusal.
    A constraint or a level order on a name that is no candidate fails loud, and so does a
    feature named like a pruning noise column (`check_noise_names`) or like a column Training
    derives from the feature names (`check_derived_names`).
    """
    ledger = stage2.ledger
    features = resolve_features(ledger, resolved)
    check_noise_names(features, resolved.training.selection.prune)
    check_derived_names(features)
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


def check_noise_names(features: list[str], prune: bool) -> None:
    """Fail loud when importance pruning is on (`prune`) and a feature in force carries one of
    the noise columns' reserved names (`selection.NOISE_COLUMNS`), before the run number."""
    clash = sorted(set(NOISE_COLUMNS) & set(features))
    if prune and clash:
        raise ValueError(
            f"the features {clash} carry the reserved names of importance pruning's noise "
            "columns: rename the source columns, or switch training.selection.prune off"
        )


def check_derived_names(features: list[str]) -> None:
    """Fail loud on a feature in force named like a column Training derives from the feature
    names: the contributions' base value (`BASE_COLUMN`), or any name ending in
    `CONTRIBUTION_SUFFIX`, which would collide in the explanation sample at the end of the run."""
    clash = sorted(
        name for name in features if name == BASE_COLUMN or name.endswith(CONTRIBUTION_SUFFIX)
    )
    if clash:
        raise ValueError(
            f"the features {clash} are named like the columns Training derives from feature "
            f"names ({BASE_COLUMN!r}, or a name ending in {CONTRIBUTION_SUFFIX!r}): rename the "
            "source columns"
        )


def check_target_range(train: pd.DataFrame, objective: str) -> None:
    """Fail loud on a negative train `target` under an objective in `NON_NEGATIVE_OBJECTIVES`:
    its deviance is not defined there and every library's first fit would fail. A `forward_sum`
    of net amounts can be negative; such a target needs another objective."""
    lowest = float(train["target"].min())
    if objective in NON_NEGATIVE_OBJECTIVES and lowest < 0:
        raise ValueError(
            f"training.objective is {objective}, which needs a target of 0 or above, and the "
            f"train target's minimum is {lowest:g}: choose squared_error, absolute_error or "
            "huber, or build a non-negative target"
        )


def save_stage2(folder: str, stage2: Stage2, final: list[str]) -> None:
    """Write a run's own copy of what it needs from Stage 2 into `folder` (its `stage2/`, which
    must not exist), so an EDA rerun never changes the run (D-139 (b)): the ledger rows of every
    candidate (the sign-off table lists the held and the excluded ones too) and, for the `final`
    features, EDA's cells (the shares per period), its numeric bin edges and its lift tables
    (`bins`, `levels`), each with exactly its `STAGE2_COLUMNS` (`check_stage2_columns` names a
    missing one). `STAGE2_FILE` records the copy's own `stage2_copy_schema_version`, which a
    later reader checks, and as provenance the versions it is a copy of (EDA's stage version
    and the ledger's, as read) and the two runs' tokens."""
    check_stage2_columns(stage2)
    target = local_path(folder)
    target.mkdir()
    for name, table in _copied_tables(stage2).items():
        rows = table if name == "ledger" else table.loc[table["feature"].isin(final)]
        write_parquet(rows[list(STAGE2_COLUMNS[name])], target / f"{name}.parquet")
    stamp = {
        "stage2_copy_schema_version": STAGE2_COPY_SCHEMA_VERSION,
        "eda_schema_version": stage2.eda_meta["schema_version"],
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
        "runs": stage2.tokens,
    }
    write_json(stamp, target / STAGE2_FILE)


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
