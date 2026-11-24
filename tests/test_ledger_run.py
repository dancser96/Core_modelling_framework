"""The per-run feature ledger, the sign-off table and Training's views, on constructed tables:
the column set and the sidecar, the record of automated drops, the wrong-sign warning, the
sign-off sections and the search summary (docs/components/feature_ledger.md "The per-run part",
docs/components/training.md "The sign-off view")."""

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest
from conftest import build_entry

from core_modelling.config.identities import feature_signature, resolved_input_hash
from core_modelling.config.replay import Entry, replay, validate_raw
from core_modelling.config.schema import UseCaseConfig
from core_modelling.reporting.training_views import (
    calibration_view,
    search_progress_chart,
    search_summary,
    selection_view,
    signoff_view,
)
from core_modelling.run_artifacts import SIDECAR_FILE, read_run_ledger
from core_modelling.training.ledger_run import build_run_ledger, ledger_warnings, save_run_ledger
from core_modelling.training.signoff import signoff_table

# The features that entered selection; `grade` is an ordered categorical.
ENTERED = ["bal", "bal_6m", "tenure", "prod", "grade", "noise"]
FINAL = ["bal", "tenure", "prod", "grade"]
CANDIDATES = [*ENTERED, "held_f", "excl_f", "fwd"]
MONOTONE = {"bal": "increasing", "tenure": "increasing", "grade": "decreasing",
            "noise": "decreasing", "held_f": "increasing", "excl_f": "increasing"}  # fmt: skip
KEPT = ["tenure"]
META = {"run_id": "r007", "data_definition_hash": "d" * 64,
        "stage2": {"eda": "e1", "feature_checks": "f1"}}  # fmt: skip
ENTRIES = [
    build_entry(1, "flag", finding="time_alignment.client_constant", features=["tenure", "held_f"]),
    build_entry(2, "keep", features=["tenure"], findings=["time_alignment.client_constant"],
                reason="static attribute"),
    build_entry(3, "exclude", features=["excl_f"], reason="set after the offer"),
]  # fmt: skip


def _selection() -> pd.DataFrame:
    """The cluster rule keeps `bal` over `bal_6m` and the kept `tenure` beside it, the floor
    drops `noise` and `prod` passes it on its nulls, pruning protects `tenure` and was undone
    for `prod`."""
    rows = [
        ("bal", "cluster", 0.70, 0.70, "passed", None, None),
        ("bal_6m", "cluster", 0.68, 0.70, "dropped", "bal", None),
        ("tenure", "cluster", 0.60, 0.70, "protected", None, None),
        ("bal", "floor", 0.70, 0.52, "passed", None, "concordance"),
        ("tenure", "floor", 0.60, 0.52, "passed", None, "concordance"),
        ("prod", "floor", 0.55, 0.52, "passed", None, "null_concordance"),
        ("grade", "floor", 0.58, 0.52, "passed", None, "concordance_best_order"),
        ("noise", "floor", 0.501, 0.52, "dropped", None, None),
        ("bal", "prune", 0.6, 0.01, "passed", None, None),
        ("tenure", "prune", 0.005, 0.01, "protected", None, None),
        ("prod", "prune", 0.004, 0.01, "undone", None, None),
        ("grade", "prune", 0.05, 0.01, "passed", None, None),
    ]
    columns = ["feature", "rule", "value", "threshold", "outcome", "represented_by", "cleared_by"]
    return pd.DataFrame(rows, columns=columns)


def _model_inputs(splits: dict | None = None) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """The final model's description (`splits` None as CatBoost's), and contributions and values
    on six train rows: `bal` raises the margin with its value, `tenure` and `grade` lower it."""
    gain = {"bal": 6.0, "tenure": 3.0, "prod": 1.0, "grade": 0.0}
    description = {"trees": 10, "features": FINAL, "gain": gain, "splits": splits}
    contributions = pd.DataFrame({
        "bal": [-0.3, -0.2, -0.1, 0.1, 0.2, 0.0],
        "tenure": [0.1, 0.05, 0.0, -0.05, -0.1, -0.1],
        "prod": [0.01, -0.01, 0.01, -0.01, 0.0, 0.0],
        "grade": [0.03, 0.02, 0.01, -0.01, -0.02, -0.03],
    })  # fmt: skip
    values = pd.DataFrame({
        "bal": [1.0, 2.0, 3.0, 4.0, 5.0, np.nan],
        "tenure": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
        "prod": [1, 2, 1, 2, 0, 3],
        "grade": [0.0, 0.0, 1.0, 1.0, 2.0, 2.0],
    })  # fmt: skip
    return description, contributions, values


LGBM_SPLITS = {"bal": 10, "tenure": 5, "prod": 2, "grade": 0}


def _encoder() -> tuple[dict, pd.DataFrame]:
    """The encoder fitted before selection and its shares on the train frame."""
    entries = [
        {"name": "bal", "kind": "numeric"}, {"name": "bal_6m", "kind": "numeric"},
        {"name": "tenure", "kind": "numeric"},
        {"name": "prod", "kind": "unordered", "levels": ["a", "b"], "pooled": []},
        {"name": "grade", "kind": "ordered", "levels": ["A", "B", "C"]},
        {"name": "noise", "kind": "numeric"},
    ]  # fmt: skip
    encoder = {"schema_version": 1, "unordered": "native", "features": entries}
    shares = pd.DataFrame({
        "feature": ENTERED, "kind": [entry["kind"] for entry in entries],
        "null_share": [1 / 6, 0.0, 0.0, 0.0, 0.0, 0.0],
        "infinite_share": [0.0, 0.0, 0.0, None, None, 0.0],
        "other_share": [None, None, None, 1 / 6, None, None],
        "unseen_share": [None, None, None, 0.0, 0.0, None],
    })  # fmt: skip
    return encoder, shares


def _statistics() -> pd.DataFrame:
    """The train-split statistics of the features that entered selection."""
    return pd.DataFrame({
        "feature": ENTERED, "concordance": [0.70, 0.68, 0.60, 0.55, 0.58, 0.501],
        "sign": [1, 1, 1, 1, -1, -1], "se": [0.01] * 6, "concordance_best_order": [np.nan] * 6,
        "value": [0.70, 0.68, 0.60, 0.55, 0.58, 0.501], "unavailable": [None] * 6,
    })  # fmt: skip


def _stage2() -> pd.DataFrame:
    """Every candidate's Stage 2 row: EDA reads `bal` falling, against its declared increase;
    `grade`'s `+` is a categorical's (signal, no order); `noise` has no direction."""
    kinds = ["numeric"] * 3 + ["categorical"] * 2 + ["numeric"] * 4
    return pd.DataFrame({
        "feature": CANDIDATES, "kind": kinds, "source": ["mart"] * 8 + [None],
        "lineage": [False] * 8 + [True], "unsupported": [False] * 9,
        "direction": ["-", "-", "+", "+", "+", None, "+", "+", None],
        "non_monotone": [False] * 9, "notes": [["redundancy.correlated_pair"]] + [[]] * 7 + [None],
        "cluster": pd.array([1, 1, 1, None, None, None, None, None, None], dtype="Int64"),
    })  # fmt: skip


def _run_ledger(splits: dict | None = LGBM_SPLITS) -> pd.DataFrame:
    """The per-run ledger built from the constructed inputs."""
    description, contributions, values = _model_inputs(splits)
    encoder, shares = _encoder()
    return build_run_ledger(_selection(), _statistics(), description, contributions, values,
                            encoder, shares, MONOTONE, _stage2(), KEPT)  # fmt: skip


def _resolved(variant: Callable[..., UseCaseConfig]) -> UseCaseConfig:
    """The config with the constraints, replayed through `ENTRIES` and marked resolved."""
    resolved = validate_raw(replay(variant(training={"monotone": MONOTONE}), ENTRIES), "test")
    resolved.housekeeping = {**resolved.housekeeping, "replayed_to": len(ENTRIES),
                             "resolved_input_hash": resolved_input_hash(resolved)}  # fmt: skip
    return resolved


def _signoff(
    variant: Callable[..., UseCaseConfig], ledger: pd.DataFrame | None = None
) -> pd.DataFrame:
    """The sign-off table of the constructed run (or of `ledger`)."""
    ledger = _run_ledger() if ledger is None else ledger
    return signoff_table(ledger, _stage2(), ENTRIES, _resolved(variant))


def test_the_run_ledger_has_the_doc_columns_and_round_trips(
    tmp_path: Path, variant: Callable[..., UseCaseConfig]
) -> None:
    """Exactly the documented columns plus the two train ones; the ledger and its sign-off table
    read back as built, a second save is refused, and so is another schema version."""
    ledger = _run_ledger()
    assert list(ledger.columns) == [
        "feature", "selected", "dropped_by", "cluster_value", "cluster_threshold",
        "cluster_outcome", "floor_value", "floor_threshold", "floor_outcome",
        "floor_cleared_by", "prune_value",
        "prune_threshold", "prune_outcome", "represents", "protected", "in_model", "splits",
        "gain_share", "contribution_share", "contribution_rank", "direction_model",
        "direction_agrees", "levels_kept", "null_share", "infinite_share", "other_share",
        "monotone", "monotone_agrees", "train_concordance", "train_sign",
    ]  # fmt: skip
    assert ledger["feature"].tolist() == ENTERED
    save_run_ledger(ledger, str(tmp_path), META)
    read_back = read_run_ledger(str(tmp_path))
    pd.testing.assert_frame_equal(read_back, ledger)
    pd.testing.assert_frame_equal(_signoff(variant, read_back), _signoff(variant, ledger))
    with pytest.raises(FileExistsError, match="written once"):
        save_run_ledger(ledger, str(tmp_path), META)
    sidecar = json.loads((tmp_path / SIDECAR_FILE).read_text())
    assert sidecar["ledger_run_schema_version"] == 2 and sidecar["stage2"] == META["stage2"]
    (tmp_path / SIDECAR_FILE).write_text(json.dumps({**sidecar, "ledger_run_schema_version": 1}))
    with pytest.raises(ValueError, match="ledger_run_schema_version 1.*train a new run"):
        read_run_ledger(str(tmp_path))


def test_the_rule_and_model_columns_follow_selection_and_the_model() -> None:
    """`noise` is dropped by the floor: no prune row, no model numbers; `bal` represents the
    cluster member `bal_6m`; a protected and an undone outcome stay selected; the model columns
    follow the final model."""
    ledger = _run_ledger().set_index("feature")
    noise = ledger.loc["noise"]
    assert noise["dropped_by"] == "floor" and not noise["selected"]
    assert noise["floor_value"] == 0.501 and noise["prune_outcome"] is None
    assert noise["floor_cleared_by"] is None and ledger.loc["bal_6m", "floor_cleared_by"] is None
    assert ledger.loc["prod", "floor_cleared_by"] == "null_concordance"
    assert ledger.loc["bal", "floor_cleared_by"] == "concordance"
    model = ["in_model", "splits", "gain_share", "contribution_share", "contribution_rank",
             "direction_model", "direction_agrees"]  # fmt: skip
    assert noise[model].isna().all()
    assert ledger.loc["bal", "represents"] == ["bal_6m"]
    assert ledger.loc["bal_6m", "dropped_by"] == "cluster"
    tenure, prod = ledger.loc["tenure"], ledger.loc["prod"]
    assert tenure["cluster_outcome"] == "protected" and tenure["selected"] and tenure["protected"]
    assert tenure["represents"] == []
    assert prod["prune_outcome"] == "undone" and prod["selected"] and prod["dropped_by"] is None
    assert ledger.loc["grade", "in_model"] == False  # noqa: E712 (a nullable boolean)
    assert ledger.loc["bal", "contribution_rank"] == 1 and ledger.loc["bal", "gain_share"] == 0.6
    assert ledger.loc["bal", "direction_model"] == "+"
    assert ledger.loc["tenure", "direction_model"] == "-"
    assert prod["direction_model"] is None and prod["levels_kept"] == 2
    assert ledger.loc["grade", "levels_kept"] == 3


def test_the_ledger_warns_on_a_wrong_constraint_and_a_final_feature_without_a_split() -> None:
    """`bal`'s constraint goes against EDA's direction, and the final feature `grade` got no
    split: each is one warning naming the features; a dropped feature is in neither."""
    constraint, unused = ledger_warnings(_run_ledger())
    assert constraint.startswith("the constraints on ['bal'] go against EDA's direction")
    assert unused.startswith("the final features ['grade'] got no split in the final model")
    everywhere = {feature: 1 for feature in FINAL}
    assert ledger_warnings(_run_ledger(everywhere)) == [constraint]


def test_a_family_without_split_counts_reads_in_model_from_the_gain() -> None:
    """CatBoost's `describe` keeps no split counts: `splits` stays null, `in_model` is gain > 0."""
    ledger = _run_ledger(splits=None).set_index("feature")
    assert ledger.loc[FINAL, "splits"].isna().all()
    assert ledger.loc[FINAL, "in_model"].tolist() == [True, True, True, False]


def test_a_constraint_against_edas_direction_warns(variant: Callable[..., UseCaseConfig]) -> None:
    """`bal` is declared increasing where EDA reads it falling: `monotone_agrees` is False and
    the sign-off view warns; `tenure` agrees; an unconstrained feature has no verdict, and
    neither has an ordered categorical (its EDA `+` says nothing about the order) nor a feature
    without an EDA direction."""
    ledger = _run_ledger().set_index("feature")
    assert ledger.loc["bal", "monotone_agrees"] == False  # noqa: E712 (a nullable boolean)
    assert ledger.loc["tenure", "monotone_agrees"] == True  # noqa: E712
    assert pd.isna(ledger.loc["prod", "monotone_agrees"])
    assert pd.isna(ledger.loc["grade", "monotone_agrees"])
    assert pd.isna(ledger.loc["grade", "direction_agrees"])
    assert pd.isna(ledger.loc["noise", "monotone_agrees"])
    table = _signoff(variant).set_index("feature")
    assert pd.isna(table.loc["grade", "wrong_sign"]) and table.loc["grade", "direction_eda"] is None
    warnings = signoff_view(table.reset_index(), None)["warnings"]
    assert "bal: declared increasing, but EDA&#x27;s direction is -" in warnings
    assert "tenure" not in warnings and "grade" not in warnings


def test_the_signoff_table_has_one_row_per_feature(variant: Callable[..., UseCaseConfig]) -> None:
    """The model's features by contribution with the kept flag's reason, then the held feature
    with its open flag, the excluded one with its reason (both constrained, each listed once),
    and the constrained feature selection dropped; the view's "declared" block lists all three."""
    table = _signoff(variant)
    assert table["feature"].is_unique
    assert table["section"].tolist() == ["model"] * 4 + [
        "held",
        "excluded",
        "declared_not_in_model",
    ]
    model = table.loc[table["section"] == "model"]
    assert model["feature"].tolist() == ["bal", "tenure", "grade", "prod"]
    assert model["cumulative_share"].iloc[-1] == pytest.approx(1.0)
    assert model.iloc[1]["kept_flags"] == ["time_alignment.client_constant (#2: static attribute)"]
    rows = table.set_index("feature")
    assert rows.loc["held_f", "open_flags"] == ["time_alignment.client_constant"]
    assert rows.loc["held_f", "monotone"] == "increasing"
    assert rows.loc["held_f", "wrong_sign"] == False  # noqa: E712 (a nullable boolean)
    assert rows.loc["excl_f", "exclude_reason"] == "set after the offer"
    assert rows.loc["excl_f", "exclude_entry"] == 3
    assert rows.loc["noise", "dropped_by"] == "floor" and pd.isna(rows.loc["noise", "wrong_sign"])
    declared = signoff_view(table, None)["sections"]["declared_not_in_model"].data
    assert declared["feature"].tolist() == ["held_f", "excl_f", "noise"]


def test_search_summary_adds_up_to_the_trials() -> None:
    """The families' seconds add up to the trials' total and their shares to 1; the best trial
    is the first to reach the lowest fold loss, read back as the metric."""
    trials = pd.DataFrame({
        "family": ["lgbm"] * 3 + ["xgboost"] * 2, "trial": [1, 2, 3, 1, 2],
        "fold_loss": [0.30, 0.25, 0.27, 0.28, 0.29], "seconds": [1.0, 2.0, 3.0, 4.0, 0.5],
        "improving": [True, True, False, True, False], "configuration": ["{}"] * 5,
    })  # fmt: skip
    summary = search_summary(trials, "roc_auc").set_index("family")
    assert summary["seconds"].sum() == pytest.approx(trials["seconds"].sum())
    assert summary["share_seconds"].sum() == pytest.approx(1.0)
    assert summary.loc["lgbm", "best_trial"] == 2
    assert summary.loc["lgbm", "best_fold_metric"] == pytest.approx(0.75)
    assert len(search_progress_chart(trials, "roc_auc").data) == 2
    failed = trials.assign(fold_loss=np.where(trials["family"] == "xgboost", np.inf, 0.3))
    with pytest.raises(ValueError, match="'xgboost' has a non-finite fold loss"):
        search_summary(failed, "roc_auc")


def _calibration(task: str) -> pd.DataFrame:
    """Training's calibration table for the task, the bundle's method marked chosen."""
    if task == "binary":
        return pd.DataFrame({
            "method": ["none", "platt", "beta"], "chosen": [False, True, False],
            "parameters": ["{}", '{"a": 1.1, "b": -0.2}', "{}"],
            "oof_loss": [0.21, 0.20, 0.199], "true_rate": [0.02] * 3,
            "sampled_rate": [0.1] * 3, "offset": [-1.69] * 3, "factor": [None] * 3,
            "factor_low": [None] * 3, "factor_high": [None] * 3, "half_total_rows": [None] * 3,
        })  # fmt: skip
    return pd.DataFrame({
        "method": ["mean"], "chosen": [True], "parameters": ['{"factor": 1.02}'],
        "oof_loss": [None], "true_rate": [None], "sampled_rate": [None], "offset": [None],
        "factor": [1.02], "factor_low": [0.97], "factor_high": [1.08], "half_total_rows": [41],
    })  # fmt: skip


@pytest.mark.parametrize("task", ["binary", "regression"])
def test_every_view_builds_for_both_tasks(task: str, variant: Callable[..., UseCaseConfig]) -> None:
    """Each view returns its keys; the selection view says what was dropped and how many passed
    the floor on their nulls, the sign-off view whether the list is signed and by which entry."""
    ledger = _run_ledger()
    selection = selection_view(ledger, _selection())
    assert set(selection) == {"summary", "counts", "dropped"}
    assert "4 of the 6 features" in selection["summary"]
    assert "1 of the 5 features the floor measured passed it on their nulls" in selection["summary"]
    assert "Pruning was undone" in selection["dropped"][-1]
    calibration = calibration_view(_calibration(task), task)
    assert set(calibration) == {"methods", "summary"}
    assert ("offset" in calibration["summary"]) == (task == "binary")
    signoff = _signoff(variant)
    signed: Entry = build_entry(4, "sign_off", stage="sign_off", run_id="r007",
                                signature=feature_signature(FINAL), features=FINAL)  # fmt: skip
    for entry, line in ((None, "not signed off"), (signed, "signed off by entry #4 on run r007")):
        view = signoff_view(signoff, entry)
        assert set(view) == {"status", "sections", "warnings"} and line in view["status"]
        assert list(view["sections"]) == ["model", "held", "excluded", "declared_not_in_model"]
    assert isinstance(search_progress_chart(_one_trial(), "rmse"), go.Figure)


def _one_trial() -> pd.DataFrame:
    """A trials table of one family and one trial."""
    return pd.DataFrame({"family": ["lgbm"], "trial": [1], "fold_loss": [3.2], "seconds": [1.0],
                         "improving": [True], "configuration": ["{}"]})  # fmt: skip


def test_inputs_that_break_a_shape_fail_loud() -> None:
    """A selection row for an unknown feature, a final feature without contributions and a
    final model without a split."""
    description, contributions, values = _model_inputs(LGBM_SPLITS)
    encoder, shares = _encoder()
    ghost = pd.concat([_selection(), pd.DataFrame([{"feature": "ghost", "rule": "floor",
                       "value": 0.6, "threshold": 0.5, "outcome": "passed"}])])  # fmt: skip
    with pytest.raises(ValueError, match=r"unknown features.*ghost"):
        build_run_ledger(ghost, _statistics(), description, contributions, values, encoder,
                         shares, MONOTONE, _stage2(), KEPT)  # fmt: skip
    short = contributions.drop(columns="prod")
    with pytest.raises(ValueError, match="every final feature needs its contributions"):
        build_run_ledger(_selection(), _statistics(), description, short, values[short.columns],
                         encoder, shares, MONOTONE, _stage2(), KEPT)  # fmt: skip
    no_gain = {**description, "gain": dict.fromkeys(FINAL, 0.0)}
    with pytest.raises(ValueError, match="made no split"):
        build_run_ledger(_selection(), _statistics(), no_gain, contributions, values, encoder,
                         shares, MONOTONE, _stage2(), KEPT)  # fmt: skip
