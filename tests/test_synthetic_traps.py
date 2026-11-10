"""Synthetic data: the traps (`checks.traps`) and the monthly control columns (`checks.controls`),
both of which need the oracle's window probabilities, the off-by-default switches (dirty data,
extra columns) and the trap list in truth."""

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest

from synthetic.checks.suite import run_checks
from synthetic.checks.switches import OUTAGE_COLUMNS, check_dirty, check_extra_columns
from synthetic.generate import generate_mart
from synthetic.mechanisms.traps import trap_summary
from synthetic.output import read_output, write_mart
from synthetic.spec.traps import TRAPS

DEFECT_COLUMNS = ["income", "casa_bal", *OUTAGE_COLUMNS]
FAMILIES = ["traps", "controls"]


@pytest.mark.parametrize("family", FAMILIES)
def test_trap_rules_hold_on_unit(unit_output: tuple[str, dict], family: str) -> None:
    """On the unit preset, every rule row of the family passes."""
    checks = run_checks(unit_output[0], [family])[family]
    rules = checks[checks["rule"]]
    assert len(rules) > 0, f"{family} has no rule rows"
    assert rules["passed"].all(), rules[~rules["passed"]].to_string()


@pytest.mark.slow
@pytest.mark.parametrize("family", FAMILIES)
def test_trap_checks_pass_on_canonical(
    canonical_checks: Callable[..., pd.DataFrame], family: str
) -> None:
    """Every row of the family passes at the canonical size."""
    checks = canonical_checks(family)
    assert checks["passed"].all(), checks[~checks["passed"]].to_string()


@pytest.fixture(scope="module")
def dirty_unit() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """The unit preset (seed 0) with dirty data on, in memory."""
    return generate_mart("unit", seed=0, dirty=True)


def test_dirty_data_is_present_as_recorded(
    dirty_unit: tuple[pd.DataFrame, pd.DataFrame, dict],
) -> None:
    """Every defect is in the mart exactly as `truth["dirty"]` records it."""
    mart, _, truth = dirty_unit
    checks = check_dirty(mart, truth)
    assert checks["passed"].all(), checks[~checks["passed"]].to_string()


def test_dirty_data_changes_nothing_else(
    dirty_unit: tuple[pd.DataFrame, pd.DataFrame, dict],
    unit: tuple[pd.DataFrame, pd.DataFrame, dict],
) -> None:
    """Without its duplicates and outside the defect columns, the dirty mart is the clean one; the
    oracle stays clean, and a clean dataset has no dirty record."""
    mart, oracle, truth = dirty_unit
    clean = mart.drop_duplicates(["client_id", "snapshot_month"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(
        clean.drop(columns=DEFECT_COLUMNS), unit[0].drop(columns=DEFECT_COLUMNS)
    )
    pd.testing.assert_frame_equal(oracle, unit[1])
    assert truth["dirty"]["duplicate_rows"] == len(mart) - len(clean)
    assert "dirty" not in unit[2]


def test_written_dirty_data_reads_back_as_generated(
    dirty_unit: tuple[pd.DataFrame, pd.DataFrame, dict], tmp_path: Path
) -> None:
    """`write_mart` with dirty data on writes the same mart and record as `generate_mart`."""
    truth = write_mart(str(tmp_path), preset="unit", seed=0, dirty=True)
    pd.testing.assert_frame_equal(read_output(str(tmp_path), "mart"), dirty_unit[0])
    assert truth["dirty"] == dirty_unit[2]["dirty"]


def test_extra_columns_are_weak_or_noise(unit: tuple[pd.DataFrame, pd.DataFrame, dict]) -> None:
    """50 extra columns: 5 weak ones track a hidden trait, 45 track none; they come after the
    snapshot's columns and change no other column."""
    mart, oracle, _ = generate_mart("unit", seed=0, n_extra_columns=50)
    checks = check_extra_columns(mart, oracle)
    assert len(checks) == 50 and checks["passed"].all(), checks[~checks["passed"]].to_string()
    extra = [c for c in mart.columns if c.startswith("extra_")]
    assert sum(c.endswith("_trap_weak") for c in extra) == 5
    assert list(mart.columns[-50:]) == extra
    pd.testing.assert_frame_equal(mart.drop(columns=extra), unit[0])


def test_truth_lists_every_trap(unit: tuple[pd.DataFrame, pd.DataFrame, dict]) -> None:
    """Truth's spec holds the trap list; the summary table has one row per trap, and the trap
    columns are the mart's columns with a `_trap_` suffix plus the extract's look-ahead."""
    traps = unit[2]["spec"]["traps"]
    assert [t["kind"] for t in traps] == [t["kind"] for t in TRAPS]
    summary = trap_summary(unit[2]["spec"])
    assert len(summary) == len(TRAPS) and summary["column"].tolist() == [t["column"] for t in TRAPS]
    listed = {t["column"] for t in TRAPS if t["trap_column"] and t["column"]}
    in_extract = {"holding_cnt_trap_lookahead"}  # the feature-store extract's look-ahead column
    assert listed == {c for c in unit[0].columns if "_trap_" in c} | in_extract
