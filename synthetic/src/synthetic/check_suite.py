"""Every check family in one place, and running them on a written dataset.

A family is one checks module: its check function and the mart and oracle columns it reads, so a
canonical-size dataset is checked from column subsets of the written parquet, never loaded whole.
`run_checks` is what the tests and the checking notebook call. Each build step adds its families.
"""

import pandas as pd

from synthetic import checks_holding_drivers, checks_holdings, checks_population
from synthetic.output import load_truth, read_output

CHECK_FAMILIES = {
    "population": dict(
        check=checks_population.check_population,
        mart_columns=checks_population.MART_COLUMNS,
        oracle_columns=checks_population.ORACLE_COLUMNS,
    ),
    "holdings": dict(
        check=checks_holdings.check_holdings,
        mart_columns=checks_holdings.MART_COLUMNS,
        oracle_columns=checks_holdings.ORACLE_COLUMNS,
    ),
    "holding_drivers": dict(
        check=checks_holding_drivers.check_holding_drivers,
        mart_columns=checks_holding_drivers.MART_COLUMNS,
        oracle_columns=checks_holding_drivers.ORACLE_COLUMNS,
    ),
}


def run_checks(out_dir: str, families: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """The check table of each family (all by default), from a dataset written by `write_mart`."""
    truth = load_truth(out_dir)
    tables = {}
    for name in CHECK_FAMILIES if families is None else families:
        family = CHECK_FAMILIES[name]  # an unknown family raises KeyError
        mart = read_output(out_dir, "mart", family["mart_columns"])
        oracle = read_output(out_dir, "oracle", family["oracle_columns"])
        tables[name] = family["check"](mart, oracle, truth)
    return tables
