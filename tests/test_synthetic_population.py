"""Synthetic data, build step 1: population, client description, day counters, latent traits."""

import pandas as pd
import pytest

from synthetic.check_suite import run_checks
from synthetic.generate import generate_mart
from synthetic.mart import DERIVED_COLUMNS
from synthetic.traps import APPLICATION, LEAK, UPSTREAM

LOOKAHEAD_COLUMNS = [LEAK, UPSTREAM, APPLICATION]  # read up to 3 months ahead


def test_population_rules_hold_on_unit(unit_output: tuple[str, dict]) -> None:
    """On the unit preset, every rule that must always hold (tolerance 0) passes."""
    checks = run_checks(unit_output[0], ["population"])["population"]
    rules = checks[checks["rule"]]
    assert len(rules) and rules["passed"].all(), rules[~rules["passed"]].to_string()


@pytest.mark.slow
def test_population_checks_pass_on_canonical(canonical_output: tuple[str, dict, dict]) -> None:
    """Every row of the step-1 check table passes at the canonical size."""
    checks = run_checks(canonical_output[0], ["population"])["population"]
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


def test_months_do_not_depend_on_later_months(
    unit: tuple[pd.DataFrame, pd.DataFrame, dict],
) -> None:
    """Prefix stability: 20 and 24 months from the same seed agree on months 1–20, in every mart
    column (the rollups, recency and ratios included) and every oracle column, except the three
    look-ahead trap columns in months 18–20, whose windows the shorter panel truncates."""
    mart, oracle, _ = unit
    short_mart, short_oracle, _ = generate_mart("unit", seed=0, n_months=20)
    months = sorted(short_mart["snapshot_month"].unique())
    assert len(months) == 20
    assert set(DERIVED_COLUMNS) <= set(short_mart.columns)
    in_short = (mart["snapshot_month"] <= months[-1]).to_numpy()
    long_mart = mart[in_short].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        long_mart.drop(columns=LOOKAHEAD_COLUMNS), short_mart.drop(columns=LOOKAHEAD_COLUMNS)
    )
    complete = (short_mart["snapshot_month"] < months[-3]).to_numpy()  # months 1–17
    pd.testing.assert_frame_equal(
        long_mart.loc[complete, LOOKAHEAD_COLUMNS], short_mart.loc[complete, LOOKAHEAD_COLUMNS]
    )
    pd.testing.assert_frame_equal(oracle[in_short].reset_index(drop=True), short_oracle)


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
