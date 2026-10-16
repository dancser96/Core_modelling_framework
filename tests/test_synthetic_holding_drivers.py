"""Synthetic data, build step 2: what drives adoption (income threshold, churned status)."""

import pytest

from synthetic.check_suite import run_checks


def test_holding_driver_checks_run_on_unit(unit_output: tuple[str, dict]) -> None:
    """On the unit preset the family runs on a written dataset and returns its rows.

    Every row of this family is statistical (none is a rule), so the canonical test judges them.
    """
    checks = run_checks(unit_output[0], ["holding_drivers"])["holding_drivers"]
    assert len(checks) and not checks["rule"].any()


@pytest.mark.slow
def test_holding_driver_checks_pass_on_canonical(canonical_output: tuple[str, dict, dict]) -> None:
    """Every row of the drivers' check table passes at the canonical size."""
    checks = run_checks(canonical_output[0], ["holding_drivers"])["holding_drivers"]
    assert checks["passed"].all(), checks[~checks["passed"]].to_string()
