"""Synthetic data: holdings, drivers, statuses, loan accounts and usage states."""

import pytest

from synthetic.checks.holdings import MART_COLUMNS, ORACLE_COLUMNS, check_holdings
from synthetic.output import read_output


def test_misaligned_oracle_fails_loud(unit_output: tuple[str, dict]) -> None:
    """Mart and oracle rows are matched by key: tables with different client-months raise."""
    out_dir, truth = unit_output
    mart = read_output(out_dir, "mart", MART_COLUMNS)
    short = read_output(out_dir, "oracle", ORACLE_COLUMNS).iloc[:-1]  # one client-month missing
    with pytest.raises(ValueError, match="line up"):
        check_holdings(mart, short, truth)
