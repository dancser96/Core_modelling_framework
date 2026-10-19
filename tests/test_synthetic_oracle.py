"""Synthetic data: the oracle (window probabilities, regression oracle, metrics), truth.json."""

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest

from synthetic.checks.events import values_at
from synthetic.checks.suite import run_checks
from synthetic.truth.oracle import BINARY_TARGETS, STANDARD_TARGETS, window_probability
from synthetic.truth.regression import COLUMNS as REGRESSION_COLUMNS

KEYS = ["client_id", "snapshot_month"]


def test_oracle_rules_hold_on_unit(unit_output: tuple[str, dict]) -> None:
    """On the unit preset, every rule row of the oracle family passes."""
    checks = run_checks(unit_output[0], ["oracle"])["oracle"]
    rules = checks[checks["rule"]]
    assert len(rules) > 0, "the oracle family has no rule rows"
    assert rules["passed"].all(), rules[~rules["passed"]].to_string()


@pytest.mark.slow
def test_oracle_checks_pass_on_canonical(canonical_checks: Callable[..., pd.DataFrame]) -> None:
    """Every row of the oracle family passes at the canonical size."""
    checks = canonical_checks("oracle")
    assert checks["passed"].all(), checks[~checks["passed"]].to_string()


@pytest.mark.parametrize("target", BINARY_TARGETS)
def test_one_month_window_is_the_generators_chance(
    unit: tuple[pd.DataFrame, pd.DataFrame, dict], target: str
) -> None:
    """With w = 1 the frozen state is the real state at t, so the window probability equals the
    chance the generator applied in t+1 (`p_<event>` in the oracle row of t+1); for loans, times
    "no account matures in t+1", which hides an opening."""
    mart, oracle, truth = unit
    chance = window_probability(mart, oracle, truth, target, 1).to_numpy()
    spec = STANDARD_TARGETS[target]
    event = {"acquire": "acquire", "open": "open", "activate": "activate"}[spec["kind"]]
    recorded = values_at(oracle, f"p_{spec['product']}_{event}", [1])[:, 0]
    if spec["kind"] == "open":
        maturing = values_at(mart, f"{spec['product']}_maturity_months", [0])[:, 0] == 1
        recorded = np.nan_to_num(recorded) * ~maturing
    set_ = ~np.isnan(chance)
    assert set_.any()
    np.testing.assert_allclose(chance[set_], recorded[set_], rtol=1e-12, atol=1e-15)


def test_regression_oracle_is_set_for_card_holders(
    unit: tuple[pd.DataFrame, pd.DataFrame, dict],
) -> None:
    """The regression columns are set exactly for card holders, with q10 ≤ q50 ≤ q90."""
    mart, oracle, _ = unit
    holder = mart["cc_flag"].to_numpy() == 1
    values = oracle[REGRESSION_COLUMNS].to_numpy()
    assert (~np.isnan(values).any(axis=1) == holder).all()
    _, q10, q50, q90 = values[holder].T
    assert (q10 <= q50).all() and (q50 <= q90).all()
