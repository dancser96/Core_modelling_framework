"""Synthetic data, build step 2: holdings, statuses, loan accounts and usage states."""

from collections.abc import Callable

import pandas as pd
import pytest

from synthetic.check_suite import run_checks
from synthetic.checks_holdings import MART_COLUMNS, ORACLE_COLUMNS, check_holdings
from synthetic.output import read_output


def test_holdings_rules_hold_on_unit(unit_output: tuple[str, dict]) -> None:
    """On the unit preset, every rule that must always hold (tolerance 0) passes."""
    checks = run_checks(unit_output[0], ["holdings"])["holdings"]
    rules = checks[checks["rule"]]
    assert len(rules) and rules["passed"].all(), rules[~rules["passed"]].to_string()


@pytest.mark.slow
def test_holdings_checks_pass_on_canonical(canonical_checks: Callable[..., pd.DataFrame]) -> None:
    """Every row of the step-2 check table passes at the canonical size."""
    checks = canonical_checks("holdings")
    assert checks["passed"].all(), checks[~checks["passed"]].to_string()


def test_misaligned_oracle_fails_loud(unit_output: tuple[str, dict]) -> None:
    """The checks read mart and oracle side by side, so rows out of line must raise."""
    out_dir, truth = unit_output
    mart = read_output(out_dir, "mart", MART_COLUMNS)
    shuffled = read_output(out_dir, "oracle", ORACLE_COLUMNS).iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValueError, match="line up"):
        check_holdings(mart, shuffled, truth)
