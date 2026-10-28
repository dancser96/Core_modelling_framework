"""The contract checks on the eligible window before any sampling (§4.8, D-050).

Hand-made panels (keys, `target`, `null_in_window`, `eligible`) check each refusal with its
numbers, that ineligible rows and the validation month never count, that every window month and
the validation month must have eligible rows, the per-task entries of the log, and the null
callout that never stops the run.
"""

from collections.abc import Callable
from datetime import date

import pytest
from pyspark.sql import DataFrame, SparkSession

from core_modelling.config import UseCaseConfig
from core_modelling.dataset.contract import check_contract

MARCH, APRIL, JULY = date(2025, 3, 31), date(2025, 4, 30), date(2025, 7, 31)
# The window is March and April, the validation month July (w = 3).
TIME = {
    "train_months": {"first": "2025-03-01", "last": "2025-04-01"},
    "validation_month": "2025-07-01",
}
SCHEMA = "unit_id string, month date, target {}, null_in_window boolean, eligible int"


@pytest.fixture
def cfg(variant: Callable[..., UseCaseConfig]) -> UseCaseConfig:
    """The skeleton's config on the two-month window."""
    return variant(time=TIME)


def _panel(spark: SparkSession, rows: list[tuple], target_type: str = "int") -> DataFrame:
    """A panel from `(unit_id, month, target, null_in_window, eligible)` rows, with one eligible
    row at the validation month unless the rows bring their own."""
    if not any(row[1] == JULY for row in rows):
        rows = [*rows, ("v", JULY, None, False, 1)]
    return spark.createDataFrame(rows, SCHEMA.format(target_type))


def test_binary_window_passes_with_both_classes_under_the_band(
    spark: SparkSession, cfg: UseCaseConfig
) -> None:
    """Unique keys, both classes, the pooled rate under the band: one entry per check, the rate
    per month in the log, ineligible rows and the validation month never counted."""
    march = [("a", MARCH, 1, False, 1), ("b", MARCH, 0, False, 1), ("c", MARCH, None, False, 1)]
    april = [("a", APRIL, 0, False, 1), ("b", APRIL, 0, False, 1), ("z", APRIL, 1, True, 0)]
    july = [("a", JULY, 1, False, 1)]
    log = check_contract(_panel(spark, [*march, *april, *july]), cfg)
    checks = [entry["check"] for entry in log]
    assert checks == ["eligible_rows", "unique_keys", "positive_rate", "null_in_window"]
    assert log[0]["per_month"] == {"2025-03": 3, "2025-04": 2, "2025-07": 1}
    rate = log[2]
    assert rate["positive_rows"] == 1 and rate["known"] == 4 and rate["rate"] == 0.25
    assert rate["per_month"] == {"2025-03": 0.5, "2025-04": 0.0} and rate["max"] == 0.5
    assert log[3] == {"step": "contract", "check": "null_in_window", "share": 0.0, "callout": None}


def test_month_without_eligible_rows_is_refused(spark: SparkSession, cfg: UseCaseConfig) -> None:
    """A window month, or the validation month, with no eligible row fails naming the months."""
    rows = [("a", MARCH, 1, False, 1), ("b", MARCH, 0, False, 1), ("c", APRIL, 0, False, 0)]
    with pytest.raises(ValueError, match=r"no eligible row in the months \['2025-04'\]"):
        check_contract(_panel(spark, rows), cfg)
    rows = [("a", MARCH, 1, False, 1), ("b", APRIL, 0, False, 1), ("v", JULY, None, False, 0)]
    with pytest.raises(ValueError, match=r"no eligible row in the months \['2025-07'\]"):
        check_contract(_panel(spark, rows), cfg)


def test_repeated_keys_are_refused(spark: SparkSession, cfg: UseCaseConfig) -> None:
    """Two eligible rows for one unit and month fail naming the key."""
    rows = [("a", MARCH, 1, False, 1), ("a", MARCH, 0, False, 1), ("b", APRIL, 0, False, 1)]
    with pytest.raises(ValueError, match=r"repeated \(unit_id, month\) keys, e.g. \(a, 2025-03-31"):
        check_contract(_panel(spark, rows), cfg)


@pytest.mark.parametrize("flag", [0, 1], ids=["all 0", "all 1"])
def test_constant_binary_target_is_refused(
    spark: SparkSession, cfg: UseCaseConfig, flag: int
) -> None:
    """One class only fails with the counts; an ineligible row of the other class doesn't help."""
    rows = [
        ("a", MARCH, flag, False, 1),
        ("b", APRIL, flag, False, 1),
        ("c", MARCH, 1 - flag, False, 0),
    ]
    with pytest.raises(ValueError, match=f"constant .*: {2 * flag} positive rows in 2 known rows"):
        check_contract(_panel(spark, rows), cfg)


def test_rate_above_the_band_is_refused(
    spark: SparkSession, variant: Callable[..., UseCaseConfig]
) -> None:
    """A pooled positive rate above `data.rate_band.max` fails with the numbers."""
    cfg = variant(time=TIME, data={"rate_band": {"max": 0.4}})
    rows = [("a", MARCH, 1, False, 1), ("b", APRIL, 0, False, 1)]
    with pytest.raises(ValueError, match="rate 0.5000 is above data.rate_band.max 0.4: 1 positive"):
        check_contract(_panel(spark, rows), cfg)


def test_null_callout_when_windows_held_nulls_without_null_as(
    spark: SparkSession, cfg: UseCaseConfig, variant: Callable[..., UseCaseConfig]
) -> None:
    """Nulls in the target column without `null_as` give the callout with the share; with
    `null_as` no callout; an upstream target (unknown) a note and no callout."""
    rows = [("a", MARCH, 1, True, 1), ("b", APRIL, 0, False, 1), ("c", MARCH, 0, True, 0)]
    entry = check_contract(_panel(spark, rows), cfg)[3]
    assert entry["share"] == 0.5 and "50.0% of the eligible window's rows" in entry["callout"]
    assert "data.target.null_as: 0" in entry["callout"]
    filled = variant(time=TIME, data={"target": {"null_as": 0}})
    assert check_contract(_panel(spark, rows), filled)[3]["callout"] is None
    upstream = [("a", MARCH, 1, None, 1), ("b", APRIL, 0, None, 1), ("v", JULY, None, None, 1)]
    unknown = check_contract(_panel(spark, upstream), cfg)[3]
    assert unknown["share"] is None and unknown["callout"] is None
    assert unknown["note"] == "unknown for an upstream target"


def test_regression_window_needs_a_finite_varying_target(
    spark: SparkSession, variant: Callable[..., UseCaseConfig]
) -> None:
    """NaN, infinity and a constant target are refused with their numbers; a varying finite one
    gives the range entry."""
    target = {"rule": "forward_sum", "column": "spend"}
    cfg = variant(task="regression", time=TIME, data={"target": target})
    good = [("a", MARCH, 1.5, False, 1), ("b", APRIL, 3.0, False, 1), ("c", MARCH, None, False, 1)]
    log = check_contract(_panel(spark, good, "double"), cfg)
    checks = [entry["check"] for entry in log]
    assert checks == ["eligible_rows", "unique_keys", "target_range", "null_in_window"]
    assert log[2] == {
        "step": "contract",
        "check": "target_range",
        "known": 2,
        "min": 1.5,
        "max": 3.0,
    }
    for bad, message in (
        ([("a", MARCH, float("nan"), False, 1), ("b", APRIL, 1.0, False, 1)], "1 NaN or infinite"),
        ([("a", MARCH, float("inf"), False, 1), ("b", APRIL, 1.0, False, 1)], "1 NaN or infinite"),
        (
            [("a", MARCH, 2.0, False, 1), ("b", APRIL, 2.0, False, 1)],
            r"constant \(2.0\) .* 2 known",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            check_contract(_panel(spark, bad, "double"), cfg)
