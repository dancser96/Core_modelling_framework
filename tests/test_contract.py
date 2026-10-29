"""The contract checks on the eligible window before any sampling (§4.8, D-050).

Hand-made panels (keys, `target`, `eligible`) check each refusal with its numbers, that
ineligible rows and the validation period never count, that every window period and the
validation period must have eligible rows, the per-task entries of the log, and the null
callout, fed the share from the join log, that never stops the run.
"""

from collections.abc import Callable
from datetime import date

import pytest
from pyspark.sql import DataFrame, SparkSession

from core_modelling.config import UseCaseConfig
from core_modelling.dataset.contract import NULL_POPULATION, check_contract

MARCH, APRIL, JULY = date(2025, 3, 31), date(2025, 4, 30), date(2025, 7, 31)
# The window is March and April, the validation period July (w = 3).
TIME = {
    "observation_window": {"first": "2025-03-01", "last": "2025-04-01"},
    "validation_period": "2025-07-01",
}
SCHEMA = "unit_id string, period date, target {}, eligible int"


@pytest.fixture
def cfg(variant: Callable[..., UseCaseConfig]) -> UseCaseConfig:
    """The skeleton's config on the two-period window."""
    return variant(time=TIME)


def _panel(spark: SparkSession, rows: list[tuple], target_type: str = "int") -> DataFrame:
    """A panel from `(unit_id, period, target, eligible)` rows, with one eligible row at the
    validation period unless the rows bring their own."""
    if not any(row[1] == JULY for row in rows):
        rows = [*rows, ("v", JULY, None, 1)]
    return spark.createDataFrame(rows, SCHEMA.format(target_type))


def test_binary_window_passes_with_both_classes_under_the_band(
    spark: SparkSession, cfg: UseCaseConfig
) -> None:
    """Unique keys, both classes, the pooled rate under the band: one entry per check, the rate
    per period in the log, ineligible rows, the validation period and a labelled gap period
    never counted."""
    march = [("a", MARCH, 1, 1), ("b", MARCH, 0, 1), ("c", MARCH, None, 1)]
    april = [("a", APRIL, 0, 1), ("b", APRIL, 0, 1), ("z", APRIL, 1, 0)]
    gap = [("a", date(2025, 5, 31), 1, 1)]  # a labelled gap period: never counted
    july = [("a", JULY, 1, 1)]
    log = check_contract(_panel(spark, [*march, *april, *gap, *july]), cfg, 0.0)
    checks = [entry["check"] for entry in log]
    assert checks == ["eligible_rows", "unique_keys", "positive_rate", "null_in_window"]
    assert log[0]["per_period"] == {"2025-03": 3, "2025-04": 2, "2025-07": 1}
    assert log[0]["min_rows"] == 1  # the thinnest period, here the validation period
    rate = log[2]
    assert rate["positive_rows"] == 1 and rate["known"] == 4 and rate["rate"] == 0.25
    assert rate["per_period"] == {"2025-03": 0.5, "2025-04": 0.0} and rate["max"] == 0.5
    assert log[3] == {"step": "contract", "check": "null_in_window", "share": 0.0,
                      "callout": None, "population": NULL_POPULATION}  # fmt: skip


def test_period_without_eligible_rows_is_refused(spark: SparkSession, cfg: UseCaseConfig) -> None:
    """A window period, or the validation period, with no eligible row fails naming the
    periods."""
    rows = [("a", MARCH, 1, 1), ("b", MARCH, 0, 1), ("c", APRIL, 0, 0)]
    with pytest.raises(ValueError, match=r"no eligible row in the periods \['2025-04'\]"):
        check_contract(_panel(spark, rows), cfg, 0.0)
    rows = [("a", MARCH, 1, 1), ("b", APRIL, 0, 1), ("v", JULY, None, 0)]
    with pytest.raises(ValueError, match=r"no eligible row in the periods \['2025-07'\]"):
        check_contract(_panel(spark, rows), cfg, 0.0)


def test_repeated_keys_are_refused(spark: SparkSession, cfg: UseCaseConfig) -> None:
    """Two eligible rows for one unit and period fail naming the key."""
    rows = [("a", MARCH, 1, 1), ("a", MARCH, 0, 1), ("b", APRIL, 0, 1)]
    with pytest.raises(
        ValueError, match=r"repeated \(unit_id, period\) keys, e.g. \(a, 2025-03-31"
    ):
        check_contract(_panel(spark, rows), cfg, 0.0)


@pytest.mark.parametrize("flag", [0, 1], ids=["all 0", "all 1"])
def test_constant_binary_target_is_refused(
    spark: SparkSession, cfg: UseCaseConfig, flag: int
) -> None:
    """One class only fails with the counts; an ineligible row of the other class doesn't help."""
    rows = [("a", MARCH, flag, 1), ("b", APRIL, flag, 1), ("c", MARCH, 1 - flag, 0)]
    with pytest.raises(ValueError, match=f"constant .*: {2 * flag} positive rows in 2 known rows"):
        check_contract(_panel(spark, rows), cfg, 0.0)


def test_rate_above_the_band_is_refused(
    spark: SparkSession, variant: Callable[..., UseCaseConfig]
) -> None:
    """A pooled positive rate above `data.rate_band.max` fails with the numbers."""
    cfg = variant(time=TIME, data={"rate_band": {"max": 0.4}})
    rows = [("a", MARCH, 1, 1), ("b", APRIL, 0, 1)]
    with pytest.raises(ValueError, match="rate 0.5000 is above data.rate_band.max 0.4: 1 positive"):
        check_contract(_panel(spark, rows), cfg, 0.0)


def test_null_callout_follows_the_share(spark: SparkSession, cfg: UseCaseConfig) -> None:
    """A share above 0 gives the callout with the share, pointing upstream; None (an upstream
    target) a note and no callout; the panel is never scanned for it."""
    rows = [("a", MARCH, 1, 1), ("b", APRIL, 0, 1)]
    entry = check_contract(_panel(spark, rows), cfg, 0.5)[3]
    assert entry["share"] == 0.5 and "fill it upstream" in entry["callout"]
    assert entry["callout"].startswith(
        "50.0% of the target source's rows in the window with a complete target window (before "
        "eligibility) had a null in 'cc_flag' at t or in the window; "
    )
    assert entry["population"] == (
        "target-source rows in the window with a complete target window, before eligibility"
    )
    unknown = check_contract(_panel(spark, rows), cfg, None)[3]
    assert unknown["share"] is None and unknown["callout"] is None
    assert unknown["note"] == "unknown for an upstream target"


def test_regression_window_needs_a_finite_varying_target(
    spark: SparkSession, variant: Callable[..., UseCaseConfig]
) -> None:
    """NaN, infinity and a constant target are refused with their numbers; a varying finite one
    gives the range entry."""
    target = {"rule": "forward_sum", "column": "spend"}
    cfg = variant(task="regression", time=TIME, data={"target": target})
    good = [("a", MARCH, 1.5, 1), ("b", APRIL, 3.0, 1), ("c", MARCH, None, 1)]
    log = check_contract(_panel(spark, good, "double"), cfg, 0.0)
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
        ([("a", MARCH, float("nan"), 1), ("b", APRIL, 1.0, 1)], "1 NaN or infinite"),
        ([("a", MARCH, float("inf"), 1), ("b", APRIL, 1.0, 1)], "1 NaN or infinite"),
        ([("a", MARCH, 2.0, 1), ("b", APRIL, 2.0, 1)], r"constant \(2.0\) .* 2 known"),
    ):
        with pytest.raises(ValueError, match=message):
            check_contract(_panel(spark, bad, "double"), cfg, 0.0)
