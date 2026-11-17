"""The per-run feature ledger and the sign-off table (docs/components/feature_ledger.md "The
per-run part", docs/components/training.md "The sign-off view").

`build_run_ledger` gives one row per feature that entered selection: what each automated rule
measured and decided (the one record of automated drops, D-125), what the final model does with
the feature (splits, gain, out-of-fold contributions and their direction), the encoder's shares
on the train frame and the declared monotone constraint against EDA's direction. Everything in it
is train-only evidence (D-031). `save_run_ledger` writes it into the run folder with its sidecar,
the way `ledger.save_ledger` writes the Stage 2 file, and `read_run_ledger` refuses another schema
version. `signoff_table` is what a person reads before approving the final list: the model's
features by contribution, then the held, the excluded and the constrained features that are not
in the model, with the audit log's reasons; it writes no entry.
"""

import json
import os
from collections.abc import Callable
from functools import partial

import numpy as np
import pandas as pd

from core_modelling import __version__
from core_modelling.artifacts import local_path, read_parquet, utc_now, write_json, write_parquet
from core_modelling.config.replay import Entry, open_flags
from core_modelling.config.schema import UseCaseConfig
from core_modelling.ledger import render_decisions

LEDGER_RUN_SCHEMA_VERSION = 1
LEDGER_RUN_FILE = "ledger_run.parquet"
SIDECAR_FILE = "_ledger_run.json"  # starts with `_`, never `_metadata` (T21)
RULES = ("cluster", "floor", "prune")  # in the order they run
OUTCOMES = ("passed", "dropped", "protected", "undone")
RULE_PARTS = ("value", "threshold", "outcome")
LEDGER_RUN_COLUMNS = [
    "feature", "selected", "dropped_by",
    *[f"{rule}_{part}" for rule in RULES for part in RULE_PARTS],
    "represents", "protected", "in_model", "splits", "gain_share", "contribution_share",
    "contribution_rank", "direction_model", "direction_agrees", "levels_kept", "null_share",
    "infinite_share", "other_share", "monotone", "monotone_agrees",
    "train_concordance", "train_sign",  # the single-feature baseline of Evaluation reads them
]  # fmt: skip
SECTIONS = ("model", "held", "excluded", "declared_not_in_model")
SIGNOFF_COLUMNS = [
    "section", "feature", "contribution_share", "cumulative_share", "direction_model",
    "direction_eda", "direction_agrees", "monotone", "wrong_sign", "represents", "source",
    "notes", "kept_flags", "open_flags", "exclude_entry", "exclude_reason", "dropped_by",
]  # fmt: skip
OPPOSITE = {"increasing": "-", "decreasing": "+"}  # EDA's direction that contradicts a constraint
LIST_COLUMNS = ("represents", "notes", "kept_flags", "open_flags")  # the sign-off's list columns


def _text_or_none(series: pd.Series) -> pd.Series:
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
    outcome (null when the rule has no row for it), `dropped_by`, `selected` and `represents`,
    the cluster members dropped in its favour."""
    out = pd.DataFrame(index=pd.Index(features, name="feature"))
    for rule in RULES:
        rows = selection.loc[selection["rule"] == rule].set_index("feature").reindex(features)
        out[f"{rule}_value"] = rows["value"].astype(float)
        out[f"{rule}_threshold"] = rows["threshold"].astype(float)
        out[f"{rule}_outcome"] = _text_or_none(rows["outcome"])
    dropped = selection.loc[selection["outcome"] == "dropped"].set_index("feature")["rule"]
    out["dropped_by"] = _text_or_none(dropped.reindex(features))
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


def _monotone_agrees(
    constraint: str | None, direction: str | None, non_monotone: object
) -> bool | None:
    """The declared constraint against EDA: False when EDA marked the feature `non_monotone` or
    its direction (`_eda_direction`) is the opposite (the wrong-sign warning); None without a
    constraint, or with nothing to compare it with (no direction and no mark)."""
    if constraint is None:
        return None
    if non_monotone is not None and not pd.isna(non_monotone) and bool(non_monotone):
        return False
    if direction is None:
        return None
    return direction != OPPOSITE[constraint]


def _eda_direction(kind: str, direction: object) -> str | None:
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
    out["direction_model"] = _text_or_none(out["direction_model"])
    rows = _stage2_rows(stage2, features)
    directions = list(map(_eda_direction, rows["kind"], rows["direction"]))
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
    agree = map(_monotone_agrees, constraints, directions, rows["non_monotone"])
    out["monotone_agrees"] = pd.array(list(agree), dtype="boolean")
    trained = statistics.set_index("feature").loc[features]
    out["train_concordance"] = trained["concordance"].astype(float)
    out["train_sign"] = trained["sign"]
    return out.reset_index()[LEDGER_RUN_COLUMNS]


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
    parquet = target / f"{LEDGER_RUN_FILE}.tmp-{os.getpid()}"
    stamp = target / f"{SIDECAR_FILE}.tmp-{os.getpid()}"
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


def read_run_ledger(run_folder: str) -> pd.DataFrame:
    """The saved per-run ledger; a missing one and another `ledger_run_schema_version` are refused
    before the parquet is read."""
    target = local_path(run_folder)
    if not (target / SIDECAR_FILE).is_file():
        raise FileNotFoundError(
            f"no per-run ledger at {run_folder}: the run crashed before writing it, or this is no "
            "run folder"
        )
    sidecar = json.loads((target / SIDECAR_FILE).read_text())
    version = sidecar.get("ledger_run_schema_version")
    if version != LEDGER_RUN_SCHEMA_VERSION:
        raise ValueError(
            f"the per-run ledger at {run_folder} has ledger_run_schema_version {version} (written "
            f"by framework {sidecar.get('framework_version')}); this version reads "
            f"{LEDGER_RUN_SCHEMA_VERSION}: read the run with the framework version that wrote it "
            "(the use case's pin), or train a new run"
        )
    return read_parquet(target / LEDGER_RUN_FILE)


def _listed(value: object) -> list:
    """A list cell as a list; a missing one is []."""
    if isinstance(value, list):
        return list(value)
    if value is None or pd.isna(value):
        return []
    raise TypeError(f"a list cell holds a {type(value).__name__}, not a list")


def _stage2_fields(
    name: str, decisions: pd.DataFrame, by_seq: dict[int, Entry], monotone: dict[str, str]
) -> dict:
    """The sign-off fields every section reads from the Stage 2 row, the audit log and the
    constraints: EDA's direction (`_eda_direction`), the source, Feature Checks' notes, each
    `keep` in force with its reason, the declared constraint and the wrong-sign mark."""
    row = decisions.loc[name]
    keeps = [by_seq[seq] for seq in row["kept"]]
    kept = [f"{', '.join(e.findings) or 'no flag'} (#{e.seq}: {e.reason})" for e in keeps]
    direction = _eda_direction(row["kind"], row["direction"])
    agrees = _monotone_agrees(monotone.get(name), direction, row["non_monotone"])
    return {
        "feature": name,
        "direction_eda": direction,
        "source": row["source"],
        "notes": _listed(row["notes"]),
        "kept_flags": kept,
        "monotone": monotone.get(name),
        "wrong_sign": None if agrees is None else not agrees,
    }


def _model_rows(run_ledger: pd.DataFrame, fields: Callable[[str], dict]) -> list[dict]:
    """The final list by out-of-fold contribution, largest first, with the running total."""
    final = run_ledger.loc[run_ledger["selected"]]
    final = final.sort_values("contribution_share", ascending=False, kind="stable")
    rows, total = [], 0.0
    for row in final.itertuples():
        total += row.contribution_share
        rows.append({
            **fields(row.feature), "section": "model",
            "contribution_share": row.contribution_share, "cumulative_share": total,
            "direction_model": row.direction_model, "direction_agrees": row.direction_agrees,
            "represents": _listed(row.represents),
        })  # fmt: skip
    return rows


def _held_and_excluded_rows(
    decisions: pd.DataFrame,
    by_seq: dict,
    flags: dict[str, list[str]],
    fields: Callable[[str], dict],
) -> list[dict]:
    """The held features with their open flags, then the excluded ones with the number and
    reason of the `exclude` in force, each in the Stage 2 order (lineage and unsupported columns,
    excluded automatically, are not listed)."""
    held = decisions.index[decisions["verdict"] == "held"]
    excluded = decisions.loc[decisions["verdict"] == "excluded", "excluded"]
    rows = [{**fields(name), "section": "held", "open_flags": flags[name]} for name in held]
    for name, seq in excluded.items():
        rows.append({
            **fields(name), "section": "excluded", "exclude_entry": seq,
            "exclude_reason": by_seq[seq].reason,
        })  # fmt: skip
    return rows


def _declared_rows(
    run_ledger: pd.DataFrame,
    decisions: pd.DataFrame,
    monotone: dict[str, str],
    fields: Callable[[str], dict],
) -> list[dict]:
    """The constrained features neither in the final list nor held nor excluded ("declared, not
    in the model"): dropped by selection, or out for another reason, in the Stage 2 order."""
    unknown = sorted(set(monotone) - set(decisions.index))
    if unknown:
        raise ValueError(f"training.monotone names {unknown}, which are no candidates")
    final = set(run_ledger.loc[run_ledger["selected"], "feature"])
    dropped_by = run_ledger.set_index("feature")["dropped_by"]
    decided = decisions["verdict"].isin(["held", "excluded"])
    out = [n for n in decisions.index[~decided] if n in monotone and n not in final]
    return [
        {**fields(name), "section": "declared_not_in_model", "dropped_by": dropped_by.get(name)}
        for name in out
    ]


def signoff_table(
    run_ledger: pd.DataFrame, stage2: pd.DataFrame, entries: list[Entry], resolved: UseCaseConfig
) -> pd.DataFrame:
    """The sign-off table (`SIGNOFF_COLUMNS`), one row per feature, in `SECTIONS` order: `model`
    (the final list by contribution), `held` with their open flags, `excluded` with the reason of
    the `exclude` in force, then `declared_not_in_model` (a constrained feature that is none of
    these). Every row carries its constraint and wrong-sign mark. `stage2` holds every
    candidate's Stage 2 row, `entries` are the ones `resolved` was replayed from; nulls where a
    column does not apply."""
    decisions = render_decisions(stage2, resolved, entries).set_index("feature")
    by_seq = {entry.seq: entry for entry in entries}
    monotone = resolved.training.monotone
    fields = partial(_stage2_fields, decisions=decisions, by_seq=by_seq, monotone=monotone)
    rows = [
        *_model_rows(run_ledger, fields),
        *_held_and_excluded_rows(decisions, by_seq, open_flags(entries), fields),
        *_declared_rows(run_ledger, decisions, monotone, fields),
    ]
    table = pd.DataFrame(rows, columns=SIGNOFF_COLUMNS)
    for column in ("contribution_share", "cumulative_share"):
        table[column] = table[column].astype(float)
    for column in ("direction_agrees", "wrong_sign"):
        table[column] = table[column].astype("boolean")
    table["exclude_entry"] = table["exclude_entry"].astype("Int64")
    for column in LIST_COLUMNS:
        table[column] = table[column].map(_listed)
    texts = ["section", "feature", "direction_model", "direction_eda", "monotone", "source",
             "exclude_reason", "dropped_by"]  # fmt: skip
    for column in texts:
        table[column] = _text_or_none(table[column])
    return table
