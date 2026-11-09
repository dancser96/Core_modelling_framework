"""From findings to the audit log and the review (docs/components/feature_checks.md "Flags act:
the hold-out").

`flag_entries` decides which `flag` entries a run writes: per flag finding of the steps that ran,
one entry when this run's feature set differs from that finding's latest effective entry, so a
rerun on unchanged data writes nothing, and an empty set closes the finding; a skipped step and
every note write nothing (D-134). The stage passes each dict to `audit_log.record_stage_entry`;
`replay.open_flags` then reads the flags still open, the new entries included. From that map
`proposed_decisions` builds the review: one row per open flag finding with the two
`record_decision` calls a person copies, each taking any subset of the finding's features, the
verb left to them (an exclude's evidence names the finding, as a keep's `findings` does);
`held_summary` lists the held features, for Training excluded features without a final decision,
each with the statistic behind each open flag. Finding names and kinds are part
of the audit-log format (`CLAUDE.md` §2): renaming or removing one, or turning a flag into a note,
needs a log migration, else its open flags are refused here.
"""

import json

import pandas as pd

from core_modelling.config.replay import Entry, effective_entries, open_flags
from core_modelling.feature_checks.findings import FINDINGS, step_findings

CLOSING_REASON = "No feature raises this finding any more: the entry closes it."
REASON_PLACEHOLDER = "<why>"  # the person's reason, written into the call they copy
REVIEW_COLUMNS = [
    "finding", "step", "features", "values", "threshold", "text", "keep_call", "exclude_call",
]  # fmt: skip
HELD_COLUMNS = [
    "feature", "kind", "findings", "flag_values", "concordance_window", "missing_share_window",
]  # fmt: skip


def _labels(rows: pd.DataFrame) -> list[str]:
    """The rows as `feature: finding`, for a refusal."""
    return (rows["feature"] + ": " + rows["finding"]).tolist()


def _check_rows(findings: pd.DataFrame) -> None:
    """Refuse a findings row the finding table does not know or whose kind or step is not its
    finding's, and a flag raised twice on one feature or with two thresholds: the review aligns
    one value per feature and states one threshold per finding."""
    unknown = sorted(set(findings["finding"]) - set(FINDINGS))
    if unknown:
        raise ValueError(f"findings {unknown} are not in the finding table (`FINDINGS`)")
    expected = {
        "kind": findings["finding"].map({name: spec["kind"] for name, spec in FINDINGS.items()}),
        "step": findings["finding"].map({name: name.split(".")[0] for name in FINDINGS}),
    }
    for column, values in expected.items():
        wrong = findings.loc[findings[column] != values]
        if not wrong.empty:
            raise ValueError(f"findings whose {column} is not their finding's: {_labels(wrong)}")
    flags = findings.loc[findings["kind"] == "flag"]
    twice = flags.loc[flags.duplicated(["feature", "finding"])]
    if not twice.empty:
        raise ValueError(f"flags raised twice on one feature: {_labels(twice)}")
    thresholds = flags.groupby("finding")["threshold"].nunique(dropna=False)
    if (thresholds > 1).any():
        raise ValueError(
            f"flags with two thresholds in one run: {list(thresholds.index[thresholds > 1])}"
        )


def _check_known_flags(flags: dict[str, list[str]]) -> None:
    """Refuse an open flag whose finding is not in the finding table (renamed or removed in a later
    version), or is a note there now: the first cannot be compared with this run or placed in the
    review, and no run could close the second, since only flags are written. `flags` is
    `replay.open_flags`' map."""
    names = {name for names in flags.values() for name in names}
    unknown = sorted(names - set(FINDINGS))
    if unknown:
        raise ValueError(
            f"the audit log holds open flags {unknown} that are not in the finding table "
            "(`FINDINGS`); settle them with a keep naming them, or an exclude"
        )
    notes = sorted(name for name in names if FINDINGS[name]["kind"] != "flag")
    if notes:
        raise ValueError(
            f"the audit log holds open flags {notes} that are notes in the finding table "
            "(`FINDINGS`); settle them with a keep naming them, or an exclude"
        )


def flag_entries(findings: pd.DataFrame, entries: list[Entry], steps: list[str]) -> list[dict]:
    """The `flag` entries this run writes, in table order: per flag finding of the steps that
    ran, this run's features (sorted) when they differ from those of the finding's latest
    effective entry (a revert that undid one is seen, as `open_flags` sees it). An empty set
    closes the finding; without an earlier entry it writes nothing. Each dict is
    `record_stage_entry`'s keywords besides `stage`. A skipped step's flags stay as the log has
    them; notes are never entries (D-134). An open flag of a finding not in the table is refused
    before anything is written.

    `findings` has `FINDING_COLUMNS`; `steps` are the steps that ran, a subset of `STEP_ORDER`.
    `findings` covers every read candidate of each step that ran, excluded ones included, so a
    person's `exclude` never closes a flag and a later `include` finds it still open.
    """
    ran = {name for step in steps for name in step_findings(step)}  # refuses an unknown step
    _check_rows(findings)
    _check_known_flags(open_flags(entries))
    outside = sorted(set(findings["step"]) - set(steps))
    if outside:
        raise ValueError(f"findings of steps {outside}, which did not run (steps: {steps})")
    latest = {e.finding: set(e.features) for e in effective_entries(entries) if e.op == "flag"}
    written = []
    for name, spec in FINDINGS.items():
        if name not in ran or spec["kind"] != "flag":
            continue
        features = sorted(set(findings.loc[findings["finding"] == name, "feature"]))
        if set(features) == latest.get(name, set()):
            continue
        written.append(
            {
                "op": "flag",
                "finding": name,
                "features": features,
                "reason": spec["text"] if features else CLOSING_REASON,
                "evidence": [f"feature_checks report: {name.split('.')[0]}"],
            }
        )
    return written


def _literal(value: str | list[str]) -> str:
    """A string or a list of strings as Python source: JSON's double-quoted form is valid Python
    for both, so a name holding a quote or a backslash stays copyable."""
    return json.dumps(value, ensure_ascii=False)


def _review_row(raised: pd.DataFrame, finding: str, features: list[str], entity: str) -> dict:
    """One open flag finding's review row; `raised` holds this run's findings rows of it."""
    value_of = dict(zip(raised["feature"], raised["value"], strict=True))
    head = f"record_decision(CONFIG, entity={_literal(entity)}"
    listed, why = _literal(features), _literal(REASON_PLACEHOLDER)
    tail = ", env_path=ENVIRONMENT)"
    return {
        "finding": finding,
        "step": finding.split(".")[0],
        "features": features,
        "values": [float(value_of[f]) if f in value_of else None for f in features],
        "threshold": raised["threshold"].iloc[0] if len(raised) else None,
        "text": FINDINGS[finding]["text"],
        "keep_call": f"{head}, keep={listed}, findings={_literal([finding])}, reason={why}{tail}",
        "exclude_call": f"{head}, exclude={listed}, reason={why}, "
        f"evidence={_literal([f'feature_checks: {finding}'])}{tail}",
    }


def proposed_decisions(
    findings: pd.DataFrame, open_flags: dict[str, list[str]], entity: str
) -> pd.DataFrame:
    """The review view (`tables/proposed_decisions`, `REVIEW_COLUMNS`): one row per open flag
    finding, in table order, with its features (sorted), this run's value of each (None where
    the run did not raise it, e.g. a skipped step), this run's threshold (NaN without a row),
    the finding's text and the `keep` and `exclude` calls to copy, each listing every feature for
    the person to split between them (the exclude's evidence naming the finding), `CONFIG` and
    `ENVIRONMENT` being the names notebook 03's setup cell defines. A feature with two open
    flags is in both rows, and keeping it in one settles only that finding; each keep call names
    a finding open on every listed feature, so the writer accepts it.

    `open_flags` is `replay.open_flags`' map, feature → its open findings.
    """
    _check_rows(findings)
    _check_known_flags(open_flags)
    features_of: dict[str, list[str]] = {}
    for feature, names in sorted(open_flags.items()):
        for name in names:
            features_of.setdefault(name, []).append(feature)
    rows = [
        _review_row(findings.loc[findings["finding"] == name], name, features_of[name], entity)
        for name in FINDINGS
        if name in features_of
    ]
    return pd.DataFrame(rows, columns=REVIEW_COLUMNS).astype({"threshold": float})


def _flag_values(findings: pd.DataFrame, feature: str, names: list[str]) -> dict:
    """Per open flag of `feature`, its `measure` → this run's value (None: not raised now). Two
    open flags sharing a measure (`all_null` and `high_missing` across a revert) read the same
    statistic, so a value this run raised wins over a None."""
    rows = findings.loc[findings["feature"] == feature]
    value_of = dict(zip(rows["finding"], rows["value"], strict=True))
    values: dict = {}
    for name in names:
        value = float(value_of[name]) if name in value_of else None
        measure = FINDINGS[name]["measure"]
        values[measure] = value if values.get(measure) is None else values[measure]
    return values


def held_summary(
    ledger: pd.DataFrame, open_flags: dict[str, list[str]], findings: pd.DataFrame
) -> pd.DataFrame:
    """One row per held feature (`open_flags`' keys, so no excluded one), sorted, as
    `HELD_COLUMNS`: its kind, its open flags, `flag_values` (per open flag in `open_flags`'
    order, its `measure` → the value this run's `findings` hold, None when this run did not
    raise it, e.g. a skipped step) and the window's concordance and missing share from the
    ledger. A held feature that is no ledger row is refused, naming it."""
    _check_rows(findings)
    _check_known_flags(open_flags)
    missing = sorted(set(open_flags) - set(ledger["feature"]))
    if missing:
        raise ValueError(
            f"held features {missing} have no ledger row for this data definition: a flag entry "
            "names a feature that is no longer a candidate, or the ledger is stale (rerun EDA)"
        )
    held = ledger.loc[ledger["feature"].isin(list(open_flags))]
    values = [_flag_values(findings, f, open_flags[f]) for f in held["feature"]]
    held = held.assign(findings=held["feature"].map(open_flags), flag_values=values)
    held = held[HELD_COLUMNS]
    return held.sort_values("feature", ignore_index=True)
