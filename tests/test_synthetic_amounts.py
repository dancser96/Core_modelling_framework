"""Synthetic data, build step 3: amounts, time effects and segment overlap."""

from collections.abc import Callable

import pandas as pd
import pytest

from synthetic.check_suite import run_checks
from synthetic.checks_amount_mix import check_amount_mix
from synthetic.generate import generate_mart
from synthetic.presets import PRESETS

FAMILIES = ["amount_rules", "amount_levels", "amount_mix", "seasons"]
RULE_FAMILIES = ["amount_rules"]  # the others have no rule rows: they run only at canonical size
GAP = "rank corr casa_bal vs spend_cc_vol: pooled"
GAP_MONTHS = 8  # up to the reference month, May (`checks_amount_levels.REFERENCE_MONTH`)


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


def _pooled_gap(separation: float, monkeypatch: pytest.MonkeyPatch) -> float:
    """Pooled minus within-subsegment rank correlation of balance with card spend (20k clients).

    The row reads the reference month (May, the panel's 8th month); months never depend on later
    ones, so 8 months give the same value as 24 at a third of the memory.
    """
    spec = dict(PRESETS["unit"]["spec"], separation=separation)
    monkeypatch.setitem(PRESETS, "unit", dict(PRESETS["unit"], spec=spec))
    mart, oracle, truth = generate_mart("unit", n_clients=20_000, n_months=GAP_MONTHS)
    checks: pd.DataFrame = check_amount_mix(mart, oracle, truth)
    return float(checks.loc[checks["check"].str.startswith(GAP), "realised"].iloc[0])


@pytest.mark.slow
def test_lower_separation_shrinks_the_pooled_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pooled relationships inflate less over within-subsegment ones when subsegments overlap."""
    assert _pooled_gap(0.5, monkeypatch) < _pooled_gap(1.0, monkeypatch)
