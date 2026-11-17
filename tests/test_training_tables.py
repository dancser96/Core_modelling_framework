"""Training's row tables, train-side metrics and the gate's two panel checks, on constructed
frames (training/tables.py, training/gate.py)."""

import numpy as np
import pandas as pd
import pytest

from core_modelling.model.calibration import apply_calibration
from core_modelling.statistics.losses import metric_loss
from core_modelling.training.gate import check_counts, check_kinds
from core_modelling.training.tables import (
    EXPLANATION_ROWS,
    explanation_sample,
    oof_table,
    sample_contributions,
    train_metrics,
)

PLATT = {"link": "logit", "method": "platt", "parameters": {"a": 1.2, "b": -0.1}, "offset": -2.0}


def _train(rows: int = 600) -> tuple[pd.DataFrame, np.ndarray]:
    """A train frame of `rows` rows (two periods per client, five folds by client) with two
    features and a 0/1 target, and a margin that follows the target."""
    rng = np.random.default_rng(0)
    clients = np.repeat(np.arange(rows // 2), 2)
    target = (rng.random(rows) < 0.2).astype(int)
    train = pd.DataFrame(
        {
            "unit_id": clients,
            "period": np.tile(["2025-01", "2025-02"], rows // 2),
            "age": rng.normal(40, 10, rows),
            "segment": rng.choice(["a", "b", None], rows),
            "target": target,
            "cv_fold": clients % 5,
        }
    )
    return train, rng.normal(size=rows) + 1.5 * target - 2


def test_the_oof_table_holds_every_train_row_with_its_three_scores() -> None:
    """One row per train row with the keys, the fold, the target and `margin`, `score_raw`,
    `score` as `apply_calibration` gives them; a non-finite margin fails loud."""
    train, margins = _train()
    table = oof_table(train, margins, PLATT, "binary")
    columns = ["unit_id", "period", "cv_fold", "target", "margin", "score_raw", "score"]
    assert list(table.columns) == columns and len(table) == len(train)
    score_raw, score = apply_calibration(margins, PLATT, "binary")
    assert np.array_equal(table["score_raw"], score_raw) and np.array_equal(table["score"], score)
    margins[3] = np.inf
    with pytest.raises(ValueError, match="1 of 600 out-of-fold rows have a non-finite margin"):
        oof_table(train, margins, PLATT, "binary")


def test_the_explanation_sample_is_seeded_and_never_larger_than_its_cap() -> None:
    """Every row when train has fewer than the cap; else the cap's rows, the same for a seed, in
    row order, each with its raw values and its own contributions."""
    train, _ = _train()
    features = ["age", "segment"]
    values = np.arange(len(train) * 3, dtype=float).reshape(len(train), 3)
    contributions = pd.DataFrame(values, columns=[*features, "base_value"])
    sample = explanation_sample(train, contributions, seed=1)
    assert len(sample) == len(train)
    assert list(sample.columns) == ["unit_id", "period", "age", "segment", "age__contribution",
                                    "segment__contribution", "base_value"]  # fmt: skip
    assert sample_contributions(sample, features).equals(contributions[features])
    big = pd.concat([train] * 10, ignore_index=True)
    big_values = np.arange(len(big) * 3, dtype=float).reshape(len(big), 3)
    big_contributions = pd.DataFrame(big_values, columns=[*features, "base_value"])
    first = explanation_sample(big, big_contributions, seed=1)
    assert len(first) == EXPLANATION_ROWS
    assert first.equals(explanation_sample(big, big_contributions, seed=1))
    assert not first.equals(explanation_sample(big, big_contributions, seed=2))
    assert first["base_value"].is_monotonic_increasing  # row order: base_value rises by row
    row = int(first["base_value"].iloc[7] // 3)
    assert first["age"].iloc[7] == big["age"].iloc[row]


def test_the_out_of_fold_metric_is_taken_without_the_offset() -> None:
    """The fold metric reads the calibrated score before the prior-shift offset (the rows are
    at the sampled rate), so the offset does not move it; the concordance is rank-only."""
    train, margins = _train()
    y, fold = train["target"].to_numpy(), train["cv_fold"].to_numpy()
    metrics = train_metrics("log_loss", "binary", y, fold, margins, PLATT, margins + 1)
    unshifted = train_metrics(
        "log_loss", "binary", y, fold, margins, {**PLATT, "offset": 0.0}, margins + 1
    )
    assert metrics == unshifted and metrics["metric"] == "log_loss"
    _, score = apply_calibration(margins, {**PLATT, "offset": 0.0}, "binary")
    by_fold = [metric_loss("log_loss", y[fold == k], score[fold == k]) for k in range(5)]
    assert metrics["out_of_fold"] == pytest.approx(np.mean(by_fold))
    assert 0.5 < metrics["out_of_fold_concordance"] < 1
    assert metrics["in_sample_concordance"] == pytest.approx(
        1 - metric_loss("roc_auc", y, margins), abs=1e-12
    )


def test_the_gate_refuses_a_panel_that_changed_under_the_data_definition() -> None:
    """Equal counts pass; one more positive row in a window period, a period EDA never saw, a
    window period EDA counted that the panel no longer holds and a feature whose type changed
    are each refused, naming what differs and the stages to rerun."""
    population = pd.DataFrame(
        {"period": ["2025-01", "2025-02"], "rows": [120, 130], "eligible_rows": [100, 110],
         "known_target": [100, 108], "positive_rows": [7, 9]}
    )  # fmt: skip
    stored = population.to_dict("records") + [
        {"period": "2025-04", "rows": 90, "eligible_rows": 80, "known_target": None,
         "positive_rows": None}
    ]  # fmt: skip
    check_counts(population, stored)
    changed = population.assign(positive_rows=[7, 10])
    with pytest.raises(ValueError, match="2025-02 positive_rows: EDA 9, now 10.*rerun eda"):
        check_counts(changed, stored)
    with pytest.raises(ValueError, match="2025-02: not among EDA's periods"):
        check_counts(population, stored[:1])
    with pytest.raises(
        ValueError, match="2025-02: EDA counted it, the panel holds no row of it now"
    ):
        check_counts(population.iloc[:1], stored)
    ledger = pd.DataFrame({"feature": ["age", "segment"], "kind": ["numeric", "categorical"]})
    check_kinds(ledger, {"age": "numeric", "segment": "categorical"})
    with pytest.raises(ValueError, match="age: numeric in the ledger, categorical now"):
        check_kinds(ledger, {"age": "categorical"})
