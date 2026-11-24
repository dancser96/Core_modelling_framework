"""The per-run feature ledger (docs/components/feature_ledger.md "The per-run part").

`build_run_ledger` gives one row per feature that entered selection: what each automated rule
measured and decided, and which statistic cleared the floor (the one record of automated
drops, D-125), what the final model does with
the feature (splits, gain, out-of-fold contributions and their direction), the encoder's shares
on the train frame and the declared monotone constraint against EDA's direction. Everything in it
is train-only evidence (D-031). `save_run_ledger` writes it into the run folder with its sidecar,
the way `ledger.save_ledger` writes the Stage 2 file, and `run_artifacts.read_run_ledger`
refuses another schema version. `ledger_warnings` gives the run's warnings the ledger shows: a
constraint against EDA's direction, a final feature the final model never split on.
`eda_direction` and `monotone_agrees` are the direction rules the sign-off table (`signoff.py`)
restates.
"""

import secrets

import numpy as np
import pandas as pd

from core_modelling import __version__
from core_modelling.artifacts import local_path, utc_now, write_json, write_parquet
from core_modelling.run_artifacts import (
    LEDGER_RUN_FILE,
    LEDGER_RUN_SCHEMA_VERSION,
    OPPOSITE,
    OUTCOMES,
    RULES,
    SIDECAR_FILE,
)

RULE_PARTS = ("value", "threshold", "outcome")
LEDGER_RUN_COLUMNS = [
    "feature", "selected", "dropped_by",
    "cluster_value", "cluster_threshold", "cluster_outcome",
    # `floor_cleared_by`: the statistic that cleared the floor, on a feature that passed it
    "floor_value", "floor_threshold", "floor_outcome", "floor_cleared_by",
    "prune_value", "prune_threshold", "prune_outcome",
    "represents", "protected", "in_model", "splits", "gain_share", "contribution_share",
    "contribution_rank", "direction_model", "direction_agrees", "levels_kept", "null_share",
    "infinite_share", "other_share", "monotone", "monotone_agrees",
    "train_concordance", "train_sign",  # the single-feature baseline of Evaluation reads them
]  # fmt: skip


def text_or_none(series: pd.Series) -> pd.Series:
    """An object column with None for every missing value, as parquet reads it back."""
    series = series.astype(object)
    return series.where(series.notna(), None)


def _check_selection(selection: pd.DataFrame, features: list[str]) -> None:
    """Refuse a selection table that breaks its shape: an unknown feature, rule or outcome, a
    representative that entered no selection, two rows for one feature and rule, or two drops."""
    dropped = selection.loc[selection["outcome"] == "dropped", "feature"]
    problems = {
        "unknown features": sorted(set(selection["feature"]) - set(features)),
        "unknown rules": sorted(set(selection["rule"]) - set(RULES)),
        "unknown outcomes": sorted(set(selection["outcome"]) - set(OUTCOMES)),
        "unknown representatives": sorted(
            set(selection["represented_by"].dropna()) - set(features)
        ),
        "repeated feature and rule": sorted(
            selection.loc[selection.duplicated(["feature", "rule"]), "feature"]
        ),
        "dropped twice": sorted(dropped[dropped.duplicated()]),
    }
    problems = {name: found for name, found in problems.items() if found}
    if problems:
        raise ValueError(
            f"the selection table does not fit the features that entered selection: {problems}"
        )


def _check_model_inputs(
    final: list[str], description: dict, contributions: pd.DataFrame, values: pd.DataFrame
) -> None:
    """Refuse model inputs that are not exactly the final list: the booster's features, the
    contributions' columns and the values' rows and columns."""
    if set(description["features"]) != set(final):
        raise ValueError(
            f"the final model's features {sorted(description['features'])} are not the features "
            f"no rule dropped {sorted(final)}"
        )
    if set(contributions.columns) != set(final):
        raise ValueError(
            f"the out-of-fold contributions hold {sorted(contributions.columns)}, the final list "
            f"is {sorted(final)}: every final feature needs its contributions"
        )
    if not (
        values.columns.equals(contributions.columns) and values.index.equals(contributions.index)
    ):
        raise ValueError("the values need the contributions' rows and columns, in their order")


def _rule_columns(selection: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """The selection columns per feature (indexed by `feature`): each rule's value, threshold and
    outcome (null when the rule has no row for it), `floor_cleared_by`, `dropped_by`,
    `selected` and `represents`, the cluster members dropped in its favour."""
    out = pd.DataFrame(index=pd.Index(features, name="feature"))
    for rule in RULES:
        rows = selection.loc[selection["rule"] == rule].set_index("feature").reindex(features)
        out[f"{rule}_value"] = rows["value"].astype(float)
        out[f"{rule}_threshold"] = rows["threshold"].astype(float)
        out[f"{rule}_outcome"] = text_or_none(rows["outcome"])
        if rule == "floor":
            out["floor_cleared_by"] = text_or_none(rows["cleared_by"])
    dropped = selection.loc[selection["outcome"] == "dropped"].set_index("feature")["rule"]
    out["dropped_by"] = text_or_none(dropped.reindex(features))
    out["selected"] = out["dropped_by"].isna()
    members = selection.loc[(selection["rule"] == "cluster") & (selection["outcome"] == "dropped")]
    represents = members.groupby("represented_by", sort=False)["feature"].agg(list)
    out["represents"] = [represents.get(name, []) for name in features]
    return out


def _model_direction(values: pd.Series, contributions: pd.Series) -> str | None:
    """`+` or `-`: the sign of the Spearman rank correlation between a feature's values and its
    out-of-fold contributions on the rows with a value; None when it is undefined (a constant)."""
    known = values.notna()
    if values[known].nunique() < 2 or contributions[known].nunique() < 2:
        return None  # a constant has no direction, and its correlation is a division by zero
    correlation = values[known].rank().corr(contributions[known].rank())
    if correlation == 0:
        return None
    return "+" if correlation > 0 else "-"


def _model_columns(
    final: list[str],
    description: dict,
    contributions: pd.DataFrame,
    values: pd.DataFrame,
    kinds: dict[str, str],
) -> pd.DataFrame:
    """The model columns of the final features (indexed by `feature`): the split count and its
    use, the gain share, the share and rank of the mean absolute out-of-fold contribution, and
    the model's direction (None for an unordered categorical, whose codes have no order). A
    family that keeps no split counts (CatBoost: `splits` None) reads `in_model` from the gain."""
    gain = pd.Series(description["gain"], dtype=float).reindex(final)
    mean_abs = contributions[final].abs().mean()
    if not (gain.sum() > 0 and mean_abs.sum() > 0):
        raise ValueError(
            "the final model made no split: its total gain or its mean absolute out-of-fold "
            "contribution is 0, so no feature has a share"
        )
    if description["splits"] is None:
        splits, in_model = pd.Series(np.nan, index=final), gain > 0
    else:
        splits = pd.Series(description["splits"], dtype=float).reindex(final)
        in_model = splits > 0
    share = mean_abs / mean_abs.sum()
    directions = [
        None if kinds[name] == "unordered" else _model_direction(values[name], contributions[name])
        for name in final
    ]
    return pd.DataFrame(
        {
            "in_model": in_model,
            "splits": splits,
            "gain_share": gain / gain.sum(),
            "contribution_share": share,
            "contribution_rank": share.rank(ascending=False, method="min"),
            "direction_model": directions,
        },
        index=pd.Index(final, name="feature"),
    )


def _agrees(left: object, right: object) -> bool | None:
    """Whether two directions agree; None when either is missing."""
    if left is None or right is None or pd.isna(left) or pd.isna(right):
        return None
    return left == right


def monotone_agrees(
    constraint: str | None, direction: str | None, non_monotone: object
) -> bool | None:
    """The declared constraint against EDA: False when EDA marked the feature `non_monotone` or
    its direction (`eda_direction`) is the opposite (the wrong-sign warning); None without a
    constraint, or with nothing to compare it with (no direction and no mark)."""
    if constraint is None:
        return None
    if non_monotone is not None and not pd.isna(non_monotone) and bool(non_monotone):
        return False
    if direction is None:
        return None
    return direction != OPPOSITE[constraint]


def eda_direction(kind: str, direction: object) -> str | None:
    """EDA's direction where it is a sign along the values' order: a numeric's. A categorical's
    comes from a cross-fitted target encoding and reads `+` whenever there is signal, so it says
    nothing about the order of an ordered categorical; None then, and when EDA gave none."""
    if kind != "numeric" or direction is None or pd.isna(direction):
        return None
    return direction


def _stage2_rows(stage2: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """The Stage 2 rows of `features`, indexed by `feature`; a feature without one fails."""
    missing = sorted(set(features) - set(stage2["feature"]))
    if missing:
        raise ValueError(f"the Stage 2 ledger has no row for {missing}")
    return stage2.set_index("feature").loc[features]


def build_run_ledger(
    selection: pd.DataFrame,
    statistics: pd.DataFrame,
    description: dict,
    contributions: pd.DataFrame,
    values: pd.DataFrame,
    encoder: dict,
    encoder_shares: pd.DataFrame,
    monotone: dict[str, str],
    stage2: pd.DataFrame,
    kept: list[str],
) -> pd.DataFrame:
    """The per-run ledger: one row per feature of `encoder_shares` (the features that entered
    selection), in its order, with `LEDGER_RUN_COLUMNS`. `selection` is Training's long table,
    `statistics` the train-split statistics, `description` the final model's `describe`,
    `contributions` and `values` the out-of-fold contributions and encoded values of the final
    features on the train rows, `kept` the features with a `keep` in force. The model columns
    are null for a feature not in the final list."""
    features = encoder_shares["feature"].tolist()
    _check_selection(selection, features)
    out = _rule_columns(selection, features)
    final = [name for name in features if out.loc[name, "selected"]]
    _check_model_inputs(final, description, contributions, values)
    entries = {entry["name"]: entry for entry in encoder["features"]}
    missing = sorted((set(features) - set(entries)) | (set(features) - set(statistics["feature"])))
    if missing:
        raise ValueError(f"the encoder or the train statistics lack the features {missing}")
    kinds = {name: entries[name]["kind"] for name in features}
    out = out.join(_model_columns(final, description, contributions, values, kinds))
    out["protected"] = [name in kept for name in features]
    out = out.astype({"in_model": "boolean", "splits": "Int64", "contribution_rank": "Int64"})
    out["direction_model"] = text_or_none(out["direction_model"])
    rows = _stage2_rows(stage2, features)
    directions = list(map(eda_direction, rows["kind"], rows["direction"]))
    agrees = map(_agrees, out["direction_model"], directions)
    out["direction_agrees"] = pd.array(list(agrees), dtype="boolean")
    levels = [
        None if kinds[name] == "numeric" else len(entries[name]["levels"]) for name in features
    ]
    out["levels_kept"] = pd.array(levels, dtype="Int64")
    shares = encoder_shares.set_index("feature")
    for column in ("null_share", "infinite_share", "other_share"):
        out[column] = shares[column].astype(float)
    constraints = [monotone.get(name) for name in features]
    out["monotone"] = pd.Series(constraints, index=out.index, dtype=object)
    agree = map(monotone_agrees, constraints, directions, rows["non_monotone"])
    out["monotone_agrees"] = pd.array(list(agree), dtype="boolean")
    trained = statistics.set_index("feature").loc[features]
    out["train_concordance"] = trained["concordance"].astype(float)
    out["train_sign"] = trained["sign"]
    return out.reset_index()[LEDGER_RUN_COLUMNS]


def ledger_warnings(run_ledger: pd.DataFrame) -> list[str]:
    """The run's warnings the per-run ledger shows: constraints against EDA's direction or its
    `non_monotone` mark (they hold: a person may know more than the window shows), and final
    features the final model never split on (in the bundle's list, they change no score)."""
    notes = []
    wrong = run_ledger.loc[run_ledger["monotone_agrees"].eq(False).fillna(False), "feature"]
    if len(wrong):
        notes.append(
            f"the constraints on {wrong.tolist()} go against EDA's direction or its "
            "non_monotone mark; they hold: a person may know more than the window shows"
        )
    unused = run_ledger.loc[
        run_ledger["selected"] & run_ledger["in_model"].eq(False).fillna(False), "feature"
    ]
    if len(unused):
        notes.append(
            f"the final features {unused.tolist()} got no split in the final model: they stay "
            "in the bundle's feature list and change no score"
        )
    return notes


def _sidecar(meta: dict) -> dict:
    """`_ledger_run.json`'s content: the version stamp, the `run_id`, the data-definition hash and
    `stage2`, the Stage 2 run tokens the run paired with."""
    keys = {"run_id", "data_definition_hash", "stage2"}
    missing, other = sorted(keys - set(meta)), sorted(set(meta) - keys)
    if missing or other:
        raise ValueError(
            f"save_run_ledger's meta holds run_id, data_definition_hash and stage2; it lacks "
            f"{missing} and may not set {other}"
        )
    return {
        "ledger_run_schema_version": LEDGER_RUN_SCHEMA_VERSION,
        "framework_version": __version__,
        "written_at": utc_now(),
        **meta,
    }


def save_run_ledger(ledger: pd.DataFrame, run_folder: str, meta: dict) -> None:
    """Write `ledger_run.parquet` and `_ledger_run.json` into the run folder, each to a temporary
    name first (removed when a write fails), then renamed. A run's ledger is written once: an
    existing one is refused, and so is a ledger whose columns are not exactly
    `LEDGER_RUN_COLUMNS`."""
    if list(ledger.columns) != LEDGER_RUN_COLUMNS:
        raise ValueError(
            f"the per-run ledger's columns are {LEDGER_RUN_COLUMNS}, in that order; got "
            f"{list(ledger.columns)}"
        )
    sidecar = _sidecar(meta)
    target = local_path(run_folder)
    existing = [name for name in (LEDGER_RUN_FILE, SIDECAR_FILE) if (target / name).exists()]
    if existing:
        raise FileExistsError(
            f"the run folder {run_folder} holds {existing} already: a run's ledger is written "
            "once, never rewritten"
        )
    target.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(8)  # unique across hosts and processes, unlike a process id
    parquet = target / f"{LEDGER_RUN_FILE}.tmp-{token}"
    stamp = target / f"{SIDECAR_FILE}.tmp-{token}"
    try:
        write_parquet(ledger, parquet)
        write_json(sidecar, stamp)
    except BaseException:
        parquet.unlink(missing_ok=True)
        stamp.unlink(missing_ok=True)
        raise
    # The sidecar last: it is what `read_run_ledger` looks for, so a crash between the two
    # renames leaves no readable ledger.
    parquet.replace(target / LEDGER_RUN_FILE)
    stamp.replace(target / SIDECAR_FILE)
