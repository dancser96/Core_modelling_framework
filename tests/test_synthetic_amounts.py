"""Synthetic data: amounts, time effects and segment overlap."""

from collections.abc import Callable

import pandas as pd
import pytest

from synthetic.checks.suite import run_checks

FAMILIES = ["amount_rules", "amount_levels", "seasons"]
RULE_FAMILIES = ["amount_rules"]  # the others have no rule rows: they run only at canonical size


@pytest.mark.parametrize("family", RULE_FAMILIES)
def test_amount_rules_hold_on_unit(unit_output: tuple[str, dict], family: str) -> None:
    """On the unit preset, every rule of the family that must always hold passes."""
    checks = run_checks(unit_output[0], [family])[family]
    rules = checks[checks["rule"]]
    assert len(rules) > 0, f"{family} has no rule rows"
    assert rules["passed"].all(), rules[~rules["passed"]].to_string()


@pytest.mark.slow
@pytest.mark.parametrize("family", FAMILIES)
def test_amount_checks_pass_on_canonical(
    canonical_checks: Callable[..., pd.DataFrame], family: str
) -> None:
    """Every row of the family's check table passes at the canonical size."""
    checks = canonical_checks(family)
    assert checks["passed"].all(), checks[~checks["passed"]].to_string()
