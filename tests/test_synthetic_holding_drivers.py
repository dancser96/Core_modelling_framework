"""Synthetic data, build step 2: what drives adoption (income threshold, churned status)."""

import pytest

from synthetic.check_suite import run_checks


def test_holding_driver_checks_run_on_unit(unit_output: tuple[str, dict]) -> None:
    """On the unit preset the family runs and its rules (tolerance 0) pass.

    Every row of this family is statistical, so there may be no rule to pass: the unit preset
    only proves the checks run on a written dataset.
    """
    checks = run_checks(unit_output[0], ["holding_drivers"])["holding_drivers"]
    rules = checks[checks["tolerance"] == 0]
    assert len(checks) and rules["passed"].all(), rules[~rules["passed"]].to_string()


@pytest.mark.slow
def test_holding_driver_checks_pass_on_canonical(canonical_output: tuple[str, dict, dict]) -> None:
    """Every row of the drivers' check table passes at the canonical size."""
    checks = run_checks(canonical_output[0], ["holding_drivers"])["holding_drivers"]
    assert checks["passed"].all(), checks[~checks["passed"]].to_string()
