"""Synthetic data, build step 3: amounts, time effects and segment overlap."""

import pandas as pd
import pytest

from synthetic.check_suite import run_checks
from synthetic.checks_amount_levels import check_amount_levels
from synthetic.generate import generate_mart
from synthetic.presets import PRESETS

FAMILIES = ["amount_rules", "amount_levels", "seasons"]
GAP = "rank corr casa_bal vs spend_cc_vol: pooled"


@pytest.mark.parametrize("family", FAMILIES)
def test_amount_rules_hold_on_unit(unit_output: tuple[str, dict], family: str) -> None:
    """On the unit preset, every rule of the family that must always hold passes."""
    checks = run_checks(unit_output[0], [family])[family]
    rules = checks[checks["rule"]]
    assert rules["passed"].all(), rules[~rules["passed"]].to_string()


@pytest.mark.slow
@pytest.mark.parametrize("family", FAMILIES)
def test_amount_checks_pass_on_canonical(
    canonical_output: tuple[str, dict, dict], family: str
) -> None:
    """Every row of the family's check table passes at the canonical size."""
    checks = run_checks(canonical_output[0], [family])[family]
    assert checks["passed"].all(), checks[~checks["passed"]].to_string()


def _pooled_gap(separation: float, monkeypatch: pytest.MonkeyPatch) -> float:
    """Pooled minus within-subsegment rank correlation of balance with card spend (30k clients)."""
    spec = dict(PRESETS["unit"]["spec"], separation=separation)
    monkeypatch.setitem(PRESETS, "unit", dict(PRESETS["unit"], spec=spec))
    checks: pd.DataFrame = check_amount_levels(*generate_mart("unit", n_clients=30_000))
    return float(checks.loc[checks["check"].str.startswith(GAP), "realised"].iloc[0])


@pytest.mark.slow
def test_lower_separation_shrinks_the_pooled_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pooled relationships inflate less over within-subsegment ones when subsegments overlap."""
    assert _pooled_gap(0.5, monkeypatch) < _pooled_gap(1.0, monkeypatch)
