"""Feature Checks' decisions: which `flag` entries a run writes (a first run, an unchanged rerun,
a changed and a closed set, an exclude, a skipped step, a revert, notes), the round trip through
`open_flags`, the review view and its call texts, the held summary, and every refusal. Pure:
entries are built in code, no Spark, no files."""

import ast
from inspect import signature

import pandas as pd
import pytest

from core_modelling.config.audit_log import LOG_SCHEMA_VERSION, _keep_findings, record_stage_entry
from core_modelling.config.identities import HASH_VERSION
from core_modelling.config.replay import Entry, open_flags
from core_modelling.feature_checks.decisions import (
    CLOSING_REASON,
    HELD_COLUMNS,
    REVIEW_COLUMNS,
    flag_entries,
    held_summary,
    proposed_decisions,
)
from core_modelling.feature_checks.findings import FINDING_COLUMNS, FINDINGS, STEP_ORDER

ENTITY = "entity_a"
THRESHOLD = 0.8
LEAK, CONSTANT = "leakage.too_strong", "quality.constant"
STATIC, UNSTABLE = "time_alignment.client_constant", "stability.concordance_unstable"
DRIFT = "stability.psi_latest"  # a note
FIRST_RUN = [
    ("income", LEAK, 0.91),
    ("age", LEAK, 0.85),
    ("age", STATIC, 0.99),
    ("tenure", CONSTANT, 1.0),
    ("age", DRIFT, 0.2),
]
NOT_STABILITY = [step for step in STEP_ORDER if step != "stability"]
BY = {
    "stage": {"kind": "stage", "id": "feature_checks"},
    "person": {"kind": "person", "id": "someone"},
}


def _findings(rows: list[tuple[str, str, float]], **overrides: object) -> pd.DataFrame:
    """A findings table, one row per (feature, finding, value), its step, kind and text from the
    finding table; `overrides` set a column on every row afterwards."""
    records = [
        {
            "feature": feature,
            "step": finding.split(".")[0],
            "finding": finding,
            "kind": FINDINGS[finding]["kind"],
            "value": value,
            "threshold": THRESHOLD,
            "text": FINDINGS[finding]["text"],
            "detail": "",
        }
        for feature, finding, value in rows
    ]
    return pd.DataFrame(records, columns=FINDING_COLUMNS).assign(**overrides)


def _entry(seq: int, op: str, by: str = "stage", **fields: object) -> Entry:
    """Entry `seq` built in code, by Feature Checks or by a person."""
    fields = {"reason": "r", **fields}
    return Entry(
        seq=seq,
        time="2026-11-06T10:00:00+00:00",
        by=BY[by],
        stage="feature_checks",
        op=op,
        data_definition_hash="d_A",
        hash_version=HASH_VERSION,
        log_schema_version=LOG_SCHEMA_VERSION,
        **fields,
    )


def _flag(seq: int, finding: str, features: list[str]) -> Entry:
    """Feature Checks' `flag` entry `seq` for one finding."""
    return _entry(seq, "flag", finding=finding, features=features)


def _logged(entries: list[Entry], written: list[dict]) -> list[Entry]:
    """The log once the stage has passed each written dict to `record_stage_entry`."""
    start = len(entries) + 1
    return entries + [_entry(seq, **fields) for seq, fields in enumerate(written, start=start)]


def _sets(written: list[dict]) -> list[tuple[str, list[str]]]:
    """The written entries as (finding, features)."""
    return [(entry["finding"], entry["features"]) for entry in written]


def _first_run() -> tuple[pd.DataFrame, list[Entry]]:
    """`FIRST_RUN`'s findings and the log after it wrote its entries to an empty log."""
    findings = _findings(FIRST_RUN)
    return findings, _logged([], flag_entries(findings, [], STEP_ORDER))


def _call(text: str) -> dict[str, object]:
    """The keywords of a `record_decision(CONFIG, …, env_path=ENVIRONMENT)` call text, each but
    the last read as a literal."""
    call = ast.parse(text, mode="eval").body
    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    assert call.func.id == "record_decision"
    assert [ast.unparse(arg) for arg in call.args] == ["CONFIG"]
    *literals, env = call.keywords
    assert (env.arg, ast.unparse(env.value)) == ("env_path", "ENVIRONMENT")
    return {keyword.arg: ast.literal_eval(keyword.value) for keyword in literals}


def test_first_run_writes_one_entry_per_raised_flag_finding() -> None:
    """In table order, features sorted, the finding's text as the reason and the step's report
    as the evidence; a flag finding raised on nothing and without history writes nothing; each
    dict holds `record_stage_entry`'s keywords only."""
    written = flag_entries(_findings(FIRST_RUN), [], STEP_ORDER)
    assert _sets(written) == [(CONSTANT, ["tenure"]), (LEAK, ["age", "income"]), (STATIC, ["age"])]
    assert written[1] == {
        "op": "flag",
        "finding": LEAK,
        "features": ["age", "income"],
        "reason": FINDINGS[LEAK]["text"],
        "evidence": ["feature_checks report: leakage"],
    }
    keywords = set(signature(record_stage_entry).parameters)
    assert all(set(entry) <= keywords for entry in written)


def test_unchanged_rerun_writes_nothing() -> None:
    """Idempotent: the same findings against the log they wrote add no entry."""
    findings, entries = _first_run()
    assert flag_entries(findings, entries, STEP_ORDER) == []


def test_changed_set_writes_the_new_set() -> None:
    """A finding raised on other features writes its new set; the unchanged ones nothing."""
    _, entries = _first_run()
    rows = [("income", LEAK, 0.91), ("salary", LEAK, 0.82), ("age", STATIC, 0.99)]
    rows.append(("tenure", CONSTANT, 1.0))
    written = flag_entries(_findings(rows), entries, STEP_ORDER)
    assert _sets(written) == [(LEAK, ["income", "salary"])]


def test_empty_set_closes_the_finding_once() -> None:
    """A finding no longer raised writes an empty entry with the closing reason, `open_flags`
    drops it, and the next unchanged run writes nothing for it."""
    _, entries = _first_run()
    findings = _findings([("income", LEAK, 0.91), ("tenure", CONSTANT, 1.0)])
    written = flag_entries(findings, entries, STEP_ORDER)
    assert _sets(written) == [(LEAK, ["income"]), (STATIC, [])]
    assert written[1]["reason"] == CLOSING_REASON
    entries = _logged(entries, written)
    assert open_flags(entries) == {"income": [LEAK], "tenure": [CONSTANT]}
    assert flag_entries(findings, entries, STEP_ORDER) == []


def test_rerun_after_a_keep_writes_nothing_and_leaves_the_keep_settled() -> None:
    """A person's keep of one feature for a finding stays valid when the same finding returns
    with new values (D-134): the rerun writes nothing and the pair stays settled."""
    _, entries = _first_run()
    entries += [_entry(4, "keep", by="person", features=["income"], findings=[LEAK])]
    rerun = [
        (feature, name, 0.95 if feature == "income" else value)
        for feature, name, value in FIRST_RUN
    ]
    assert flag_entries(_findings(rerun), entries, STEP_ORDER) == []
    assert open_flags(entries) == {"age": [LEAK, STATIC], "tenure": [CONSTANT]}


def test_an_exclude_never_closes_a_flag() -> None:
    """The steps judge excluded candidates too, so after a person's exclude the same findings
    write nothing and the flag entry stands; an include brings the feature back held."""
    findings, entries = _first_run()
    entries += [_entry(len(entries) + 1, "exclude", by="person", features=["income"])]
    assert "income" not in open_flags(entries)
    assert flag_entries(findings, entries, STEP_ORDER) == []
    entries += [_entry(len(entries) + 1, "include", by="person", features=["income"])]
    assert open_flags(entries)["income"] == [LEAK]


def test_skipped_step_leaves_its_flags_as_the_log_has_them() -> None:
    """A step that did not run writes nothing, so its earlier flag stays open; had it run
    without raising the finding, the finding would close."""
    entries = [_flag(1, UNSTABLE, ["login_cnt"])]
    findings = _findings([row for row in FIRST_RUN if row[1] != DRIFT])
    written = flag_entries(findings, entries, NOT_STABILITY)
    assert UNSTABLE not in [entry["finding"] for entry in written]
    assert open_flags(_logged(entries, written))["login_cnt"] == [UNSTABLE]
    assert (UNSTABLE, []) in _sets(flag_entries(findings, entries, STEP_ORDER))


def test_a_revert_that_undid_a_flag_entry_makes_the_run_write_it_again() -> None:
    """The comparison is with the latest effective entry: once a revert undid entry 2, the
    finding's set is entry 1's, so this run's set (entry 2's) is written again."""
    entries = [
        _flag(1, LEAK, ["income"]),
        _flag(2, LEAK, ["age", "income"]),
        _entry(3, "revert", by="person", to_seq=1),
    ]
    findings = _findings([("age", LEAK, 0.85), ("income", LEAK, 0.91)])
    assert _sets(flag_entries(findings, entries, ["leakage"])) == [(LEAK, ["age", "income"])]


def test_notes_are_never_entries() -> None:
    """Every note raised, with no flag, writes nothing."""
    notes = [name for name, spec in FINDINGS.items() if spec["kind"] == "note"]
    assert flag_entries(_findings([("age", name, 0.5) for name in notes]), [], STEP_ORDER) == []


def test_round_trip_holds_exactly_the_flagged_features() -> None:
    """`open_flags` over the log plus the written entries holds each feature with this run's
    flags on it, an earlier run's set of a finding replaced."""
    entries = [_flag(1, LEAK, ["tenure"])]
    findings = _findings(FIRST_RUN)
    logged = _logged(entries, flag_entries(findings, entries, STEP_ORDER))
    assert open_flags(logged) == {"age": [LEAK, STATIC], "income": [LEAK], "tenure": [CONSTANT]}


def test_proposed_decisions_list_a_two_flag_feature_in_both_rows() -> None:
    """One row per open flag finding in table order, each feature's value aligned; a keep of
    the two-flag feature for one finding removes only that row."""
    findings, entries = _first_run()
    review = proposed_decisions(findings, open_flags(entries), ENTITY)
    assert list(review.columns) == REVIEW_COLUMNS
    assert review[["finding", "step", "features", "values"]].values.tolist() == [
        [CONSTANT, "quality", ["tenure"], [1.0]],
        [LEAK, "leakage", ["age", "income"], [0.85, 0.91]],
        [STATIC, "time_alignment", ["age"], [0.99]],
    ]
    assert review["threshold"].tolist() == [THRESHOLD] * 3
    assert review["text"].tolist() == [FINDINGS[name]["text"] for name in review["finding"]]
    kept = entries + [_entry(4, "keep", by="person", features=["age"], findings=[STATIC])]
    review = proposed_decisions(findings, open_flags(kept), ENTITY)
    assert review["finding"].tolist() == [CONSTANT, LEAK]
    assert review["features"].tolist() == [["tenure"], ["age", "income"]]


def test_values_are_none_where_the_run_did_not_raise_the_open_flag() -> None:
    """A skipped step's open flag is reviewed with no value and no threshold."""
    entries = [_flag(1, UNSTABLE, ["login_cnt", "age"])]
    findings = _findings([("age", LEAK, 0.85)])
    entries = _logged(entries, flag_entries(findings, entries, NOT_STABILITY))
    review = proposed_decisions(findings, open_flags(entries), ENTITY).set_index("finding")
    assert review.loc[UNSTABLE, "features"] == ["age", "login_cnt"]
    assert review.loc[UNSTABLE, "values"] == [None, None]
    assert pd.isna(review.loc[UNSTABLE, "threshold"])
    assert review.loc[LEAK, "values"] == [0.85]


def test_call_texts_are_python_calls_whose_keep_the_writer_accepts() -> None:
    """Both texts parse as `record_decision(CONFIG, …)` with literal keywords and no suggested
    verb, the exclude's evidence naming the finding; each keep passes the writer's rule (its
    finding open on every listed feature)."""
    findings, entries = _first_run()
    review = proposed_decisions(findings, open_flags(entries), ENTITY)
    for row in review.itertuples():
        keep, exclude = _call(row.keep_call), _call(row.exclude_call)
        assert keep == {
            "entity": ENTITY,
            "keep": row.features,
            "findings": [row.finding],
            "reason": "<why>",
        }
        assert exclude == {
            "entity": ENTITY,
            "exclude": row.features,
            "reason": "<why>",
            "evidence": [f"feature_checks: {row.finding}"],
        }
        assert _keep_findings(entries, keep["keep"], keep["findings"]) == [row.finding]


def test_held_summary_has_one_row_per_held_feature() -> None:
    """Sorted by feature, with its open flags, each flag's measure and value, and the ledger's
    window numbers; an excluded feature is not held."""
    ledger = pd.DataFrame(
        {
            "feature": ["tenure", "income", "age", "segment"],
            "kind": ["numeric", "numeric", "numeric", "categorical"],
            "concordance_window": [0.55, 0.91, 0.85, 0.6],
            "missing_share_window": [0.0, 0.1, 0.0, 0.0],
            "rank": [4, 1, 2, 3],
        }
    )
    findings, entries = _first_run()
    entries += [_entry(4, "exclude", by="person", features=["tenure"])]
    summary = held_summary(ledger, open_flags(entries), findings)
    assert list(summary.columns) == HELD_COLUMNS
    assert summary.values.tolist() == [
        ["age", "numeric", [LEAK, STATIC],
         {"concordance_window_or_best_order": 0.85, "constant_share": 0.99}, 0.85, 0.0],
        ["income", "numeric", [LEAK], {"concordance_window_or_best_order": 0.91}, 0.91, 0.1],
    ]  # fmt: skip
    assert held_summary(ledger, {}, findings).empty


def test_held_flag_values_are_none_where_the_run_did_not_raise_the_flag() -> None:
    """A flag open from an earlier run (here a skipped step's) shows its measure with None."""
    ledger = pd.DataFrame(
        {"feature": ["age"], "kind": ["numeric"], "concordance_window": [0.85]}
    ).assign(missing_share_window=0.0)
    findings = _findings([("age", LEAK, 0.85)])
    summary = held_summary(ledger, {"age": [UNSTABLE, LEAK]}, findings)
    expected = {"heterogeneity_p": None, "concordance_window_or_best_order": 0.85}
    assert summary.at[0, "flag_values"] == expected


def test_held_summary_refuses_a_held_feature_without_a_ledger_row() -> None:
    """A held name the ledger lacks is refused, naming it."""
    ledger = pd.DataFrame(
        {"feature": ["age"], "kind": ["numeric"], "concordance_window": [0.85]}
    ).assign(missing_share_window=0.0)
    with pytest.raises(ValueError, match=r"held features \['incme'\] have no ledger row"):
        held_summary(ledger, {"age": [LEAK], "incme": [LEAK]}, _findings([]))


def test_proposed_decisions_refuse_an_open_flag_outside_the_finding_table() -> None:
    """An open finding this version does not know cannot be placed in table order."""
    with pytest.raises(ValueError, match=r"open flags \['leakage.too_weak'\] that are not"):
        proposed_decisions(_findings([]), {"age": ["leakage.too_weak"]}, ENTITY)


def test_flag_entries_refuse_an_open_flag_outside_the_finding_table() -> None:
    """A log flag whose finding a later version renamed is refused before anything is written,
    with the review's message; once a keep settles it, the run goes ahead."""
    entries = [_flag(1, "leakage.too_weak", ["age"])]
    with pytest.raises(ValueError, match=r"open flags \['leakage.too_weak'\] that are not"):
        flag_entries(_findings([]), entries, STEP_ORDER)
    entries += [_entry(2, "keep", by="person", features=["age"], findings=["leakage.too_weak"])]
    assert flag_entries(_findings([]), entries, STEP_ORDER) == []


def test_an_open_flag_whose_finding_is_now_a_note_is_refused() -> None:
    """A log flag of a finding a later version made a note could never be closed (only flags are
    written), so the run and the review refuse it until a keep settles it."""
    entries = [_flag(1, DRIFT, ["age"])]
    with pytest.raises(ValueError, match=r"open flags \['stability.psi_latest'\] that are notes"):
        flag_entries(_findings([]), entries, STEP_ORDER)
    with pytest.raises(ValueError, match=r"open flags \['stability.psi_latest'\] that are notes"):
        proposed_decisions(_findings([]), open_flags(entries), ENTITY)
    entries += [_entry(2, "keep", by="person", features=["age"], findings=[DRIFT])]
    assert flag_entries(_findings([]), entries, STEP_ORDER) == []


def test_proposed_decisions_check_the_findings_rows() -> None:
    """The review refuses the rows `flag_entries` refuses, e.g. a flag raised twice."""
    twice = _findings([("age", LEAK, 0.9), ("age", LEAK, 0.85)])
    with pytest.raises(ValueError, match="raised twice"):
        proposed_decisions(twice, {"age": [LEAK]}, ENTITY)


REFUSALS = {
    "unknown finding": (
        _findings([("age", LEAK, 0.9)], finding="leakage.too_weak"),
        STEP_ORDER,
        r"findings \['leakage.too_weak'\] are not in the finding table",
    ),
    "kind": (
        _findings([("age", LEAK, 0.9)], kind="note"),
        STEP_ORDER,
        r"whose kind is not their finding's: \['age: leakage.too_strong'\]",
    ),
    "step not the finding's": (
        _findings([("age", LEAK, 0.9)], step="quality"),
        STEP_ORDER,
        r"whose step is not their finding's: \['age: leakage.too_strong'\]",
    ),
    "step did not run": (
        _findings([("age", UNSTABLE, 0.001)]),
        ["quality", "leakage"],
        r"findings of steps \['stability'\], which did not run",
    ),
    "unknown step": (_findings([]), ["quality", "leakge"], "unknown Feature Checks step 'leakge'"),
    "flag raised twice": (
        _findings([("age", LEAK, 0.9), ("age", LEAK, 0.85)]),
        STEP_ORDER,
        r"flags raised twice on one feature: \['age: leakage.too_strong'\]",
    ),
    "two thresholds": (
        pd.concat(
            [_findings([("age", LEAK, 0.9)]), _findings([("income", LEAK, 0.85)], threshold=0.7)],
            ignore_index=True,
        ),
        STEP_ORDER,
        r"flags with two thresholds in one run: \['leakage.too_strong'\]",
    ),
}


@pytest.mark.parametrize("case", list(REFUSALS))
def test_flag_entries_refusals(case: str) -> None:
    """Each malformed findings table or step list is refused, naming the offender."""
    findings, steps, match = REFUSALS[case]
    with pytest.raises(ValueError, match=match):
        flag_entries(findings, [], steps)
