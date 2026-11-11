"""Synthetic data: the feature-store extract (`fs_extract`) beside the mart: its keys, types,
coverage and look-ahead trap column (pandas only, no Spark); its check rows run in
`test_synthetic_families`."""

import numpy as np
import pandas as pd
import pytest

from synthetic.checks.extract import check_extract
from synthetic.generate import generate_extract
from synthetic.output import HOLDINGS_COLUMNS, read_output

LOOKAHEAD = "holding_cnt_trap_lookahead"


@pytest.fixture(scope="module")
def extract(unit: tuple[pd.DataFrame, pd.DataFrame, dict]) -> pd.DataFrame:
    """The unit preset's extract, built in memory."""
    return generate_extract(*unit)


def test_written_extract_is_the_in_memory_one(
    unit_output: tuple[str, dict], extract: pd.DataFrame
) -> None:
    """`write_mart` writes the extract `generate_extract` builds from the same panel."""
    pd.testing.assert_frame_equal(read_output(unit_output[0], "fs_extract"), extract)


def test_extract_keys_lead_and_months_end_on_every_last_day(
    unit: tuple[pd.DataFrame, pd.DataFrame, dict], extract: pd.DataFrame
) -> None:
    """The keys are the first two columns, the months cover every last day (28, 30, 31) and about
    85% of the clients are in the extract. (The ids as strings, the months as last days and a
    client in all its months or none are the extract family's rule rows.)"""
    assert list(extract.columns[:2]) == ["customer_no", "as_of_date"]
    assert {d.day for d in extract["as_of_date"]} >= {28, 30, 31}
    n = unit[0]["client_id"].nunique()
    share = extract["customer_no"].nunique() / n
    assert abs(share - 0.85) <= 4.5 * np.sqrt(0.85 * 0.15 / n)


def test_lookahead_is_the_last_months_holding_count(
    unit: tuple[pd.DataFrame, pd.DataFrame, dict], extract: pd.DataFrame
) -> None:
    """The look-ahead column holds the flags held in the client's last month on every month, and
    the family's rule fails when it holds the first month's count instead."""
    mart, oracle, truth = unit
    flags = HOLDINGS_COLUMNS[1:]
    by_client = mart.sort_values(["client_id", "snapshot_month"]).groupby("client_id")[flags]
    ids = extract["customer_no"].astype(np.int64)
    assert extract[LOOKAHEAD].equals(ids.map(by_client.last().sum(axis=1)))
    first = extract.assign(**{LOOKAHEAD: ids.map(by_client.first().sum(axis=1))})
    assert (extract[LOOKAHEAD] != first[LOOKAHEAD]).any()
    checks = check_extract(mart, oracle, truth, first).set_index("check")
    assert not checks.loc["extract: look-ahead = flags held in the client's last month", "passed"]
