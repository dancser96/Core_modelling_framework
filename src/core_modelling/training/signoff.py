"""The sign-off table (docs/components/training.md "The sign-off view").

`signoff_table` is what a person reads before approving the final list: the model's features by
contribution, then the held, the excluded and the constrained features that are not in the
model, with the audit log's reasons; it writes no entry. It reads the per-run ledger
(`ledger_run.py`) and restates its direction rules (`eda_direction`, `monotone_agrees`).
"""

from collections.abc import Callable
from functools import partial

import pandas as pd

from core_modelling.config.replay import Entry, open_flags
from core_modelling.config.schema import UseCaseConfig
from core_modelling.ledger import render_decisions
from core_modelling.run_artifacts import LIST_COLUMNS, SIGNOFF_COLUMNS
from core_modelling.training.ledger_run import eda_direction, monotone_agrees, text_or_none


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
    constraints: EDA's direction (`eda_direction`), the source, Feature Checks' notes, each
    `keep` in force with its reason, the declared constraint and the wrong-sign mark."""
    row = decisions.loc[name]
    keeps = [by_seq[seq] for seq in row["kept"]]
    kept = [f"{', '.join(e.findings) or 'no flag'} (#{e.seq}: {e.reason})" for e in keeps]
    direction = eda_direction(row["kind"], row["direction"])
    agrees = monotone_agrees(monotone.get(name), direction, row["non_monotone"])
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
        table[column] = text_or_none(table[column])
    return table
