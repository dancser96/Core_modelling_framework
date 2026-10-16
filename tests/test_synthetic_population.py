"""Synthetic data, build step 1: population, client description, day counters, latent traits."""

import pandas as pd
import pytest

from synthetic.checks_population import check_population
from synthetic.generate import generate_mart


@pytest.fixture(scope="module")
def unit() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """The unit preset with seed 0, generated once for the module."""
    return generate_mart("unit", seed=0)


def test_population_checks_pass(canonical: tuple[pd.DataFrame, pd.DataFrame, dict]) -> None:
    """Every row of the step-1 check table passes at the canonical size."""
    checks = check_population(*canonical)
    assert checks["passed"].all(), checks[~checks["passed"]].to_string()


def test_same_seed_same_data_other_seed_differs(
    unit: tuple[pd.DataFrame, pd.DataFrame, dict],
) -> None:
    """Generation is deterministic in the seed, and the seed matters."""
    mart, oracle, _ = unit
    again_mart, again_oracle, _ = generate_mart("unit", seed=0)
    other_mart, _, _ = generate_mart("unit", seed=1)
    pd.testing.assert_frame_equal(mart, again_mart)
    pd.testing.assert_frame_equal(oracle, again_oracle)
    assert not mart.equals(other_mart)


def test_mart_holds_no_hidden_truth(unit: tuple[pd.DataFrame, pd.DataFrame, dict]) -> None:
    """No oracle column (hidden truth) ever appears in the mart."""
    mart, oracle, _ = unit
    hidden = [c for c in oracle.columns if c not in ("client_id", "snapshot_month")]
    assert not set(hidden) & set(mart.columns)


def test_small_population_survives_months_without_new_clients() -> None:
    """200 clients see many months with no new client; every draw must handle empty batches."""
    mart, _, truth = generate_mart("unit", n_clients=200, seed=0)
    entries_per_month = pd.DataFrame(truth["turnover"]).groupby("month")["entries"].sum()
    assert (entries_per_month == 0).any()  # the empty-batch path really ran
    assert mart["snapshot_month"].nunique() == 24
