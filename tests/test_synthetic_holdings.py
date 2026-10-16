"""Synthetic data, build step 2: holdings, statuses, loan accounts and usage states."""

import pandas as pd
import pytest

from synthetic.checks_holdings import check_holdings


def test_holdings_checks_pass(canonical: tuple[pd.DataFrame, pd.DataFrame, dict]) -> None:
    """Every row of the step-2 check table passes at the canonical size."""
    checks = check_holdings(*canonical)
    assert checks["passed"].all(), checks[~checks["passed"]].to_string()


def test_misaligned_oracle_fails_loud(canonical: tuple[pd.DataFrame, pd.DataFrame, dict]) -> None:
    """The checks read mart and oracle side by side, so rows out of line must raise."""
    mart, oracle, truth = canonical
    shuffled = oracle.iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValueError, match="line up"):
        check_holdings(mart, shuffled, truth)
