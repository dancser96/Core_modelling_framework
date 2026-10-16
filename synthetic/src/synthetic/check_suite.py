"""Every check family in one place, and running them on a written dataset.

A family is one checks module: its check function and the mart and oracle columns it reads, so a
canonical-size dataset is checked from column subsets of the written parquet, never loaded whole.
`run_checks` is what the tests and the checking notebook call. Each build step adds its families.
"""

from types import ModuleType

import pandas as pd

from synthetic import (
    checks_amount_levels,
    checks_amount_rules,
    checks_holding_drivers,
    checks_holdings,
    checks_population,
    checks_seasons,
)
from synthetic.output import load_truth, read_output


def _family(module: ModuleType, check: str) -> dict:
    """A family's check function and the columns its module declares."""
    return dict(
        check=getattr(module, check),
        mart_columns=module.MART_COLUMNS,
        oracle_columns=module.ORACLE_COLUMNS,
    )


CHECK_FAMILIES = {
    "population": _family(checks_population, "check_population"),
    "holdings": _family(checks_holdings, "check_holdings"),
    "holding_drivers": _family(checks_holding_drivers, "check_holding_drivers"),
    "amount_rules": _family(checks_amount_rules, "check_amount_rules"),
    "amount_levels": _family(checks_amount_levels, "check_amount_levels"),
    "seasons": _family(checks_seasons, "check_seasons"),
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
