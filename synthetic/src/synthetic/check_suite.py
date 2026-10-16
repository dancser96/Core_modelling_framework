"""Every check family in one place, and running them on a written dataset.

A family is one checks module: its check function and the mart and oracle columns it reads, so a
canonical-size dataset is checked from column subsets of the written parquet, never loaded whole.
`run_checks` is what the tests and the checking notebook call. Each build step adds its families.
A family that reads every mart column (`MART_COLUMNS = None`, the mart family) runs at the canonical
size on a client sample (`client_sample`).
"""

from types import ModuleType

import pandas as pd

from synthetic import (
    checks_amount_levels,
    checks_amount_mix,
    checks_amount_rules,
    checks_holding_drivers,
    checks_holdings,
    checks_mart,
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
    "amount_mix": _family(checks_amount_mix, "check_amount_mix"),
    "seasons": _family(checks_seasons, "check_seasons"),
    "mart": _family(checks_mart, "check_mart"),
}


def run_checks(
    out_dir: str, families: list[str] | None = None, client_sample: int | None = None
) -> dict[str, pd.DataFrame]:
    """The check table of each family (all by default), from a dataset written by `write_mart`.

    `client_sample` n checks only the clients whose id is a multiple of n (`read_output`).
    """
    truth = load_truth(out_dir)
    tables = {}
    for name in CHECK_FAMILIES if families is None else families:
        family = CHECK_FAMILIES[name]  # an unknown family raises KeyError
        mart = read_output(out_dir, "mart", family["mart_columns"], client_sample)
        oracle = read_output(out_dir, "oracle", family["oracle_columns"], client_sample)
        tables[name] = family["check"](mart, oracle, truth)
    return tables
