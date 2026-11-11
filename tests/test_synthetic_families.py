"""Synthetic data: every check family (`checks.suite.CHECK_FAMILIES`) runs on the unit preset in
the default suite, its rule rows judged, and in full at the canonical size under `-m slow`. A new
family is covered by being in the dict; a family's own tests keep only what its rows do not say."""

from collections.abc import Callable

import pandas as pd
import pytest

from synthetic.checks.suite import CHECK_FAMILIES, run_checks

# Families with no rule row: their statistics need the canonical size, so on unit they only have
# to run.
STATISTICS_ONLY = ("amount_levels", "seasons")
ALL_RULES = ("mart",)  # families whose every row is a rule, so nothing hides in a statistic


@pytest.mark.parametrize("family", CHECK_FAMILIES)
def test_rule_rows_hold_on_unit(unit_output: tuple[str, dict], family: str) -> None:
    """On the unit preset, every rule row of the family passes (the family has some, unless it is
    statistics only)."""
    checks = run_checks(unit_output[0], [family])[family]
    assert len(checks) > 0, f"{family} returned an empty check table"
    rules = checks[checks["rule"]]
    assert len(rules) > 0 or family in STATISTICS_ONLY, f"{family} has no rule rows"
    assert rules["passed"].all(), rules[~rules["passed"]].to_string()
    if family in ALL_RULES:
        assert len(rules) == len(checks), f"{family} has a row that is not a rule"


@pytest.mark.slow
@pytest.mark.parametrize("family", CHECK_FAMILIES)
def test_every_row_passes_on_canonical(
    canonical_checks: Callable[..., pd.DataFrame], family: str
) -> None:
    """Every row of the family's check table passes at the canonical size."""
    checks = canonical_checks(family)
    assert len(checks) > 0, f"{family} returned an empty check table"
    assert checks["passed"].all(), checks[~checks["passed"]].to_string()
