"""Every check family in one place, and running them on a written dataset.

A family is one checks module: its check function and the mart and oracle columns it reads, so a
canonical-size dataset is checked from column subsets of the written parquet, never loaded whole.
`run_checks` runs families in this process (the tests on the small preset); `write_checks` runs
each in its own process and saves its table (the CLI's `--checks`, the slow tests), which
`read_checks` and the checking notebook read back. A family that reads every mart column
(`MART_COLUMNS = None`, the mart family) runs at the canonical size on a client sample.
"""

import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd

from synthetic.checks import (
    amount_levels,
    amount_rules,
    holdings,
    mart,
    oracle,
    population,
    seasons,
    traps,
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
    "population": _family(population, "check_population"),
    "holdings": _family(holdings, "check_holdings"),
    "amount_rules": _family(amount_rules, "check_amount_rules"),
    "amount_levels": _family(amount_levels, "check_amount_levels"),
    "seasons": _family(seasons, "check_seasons"),
    "mart": _family(mart, "check_mart"),
    "traps": _family(traps, "check_traps"),
    "oracle": _family(oracle, "check_oracle"),
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


# The mart family reads every column, so it checks a fixed 20% of the clients.
CLIENT_SAMPLES = {"mart": 5}


def write_checks(out_dir: str, families: list[str] | None = None) -> Path:
    """Run each family in its own process and save its table as `<out_dir>/checks/<family>.parquet`.

    At the canonical size one family's working set is several GB (sorting, joining and copying the
    columns it reads), so a separate process gives the memory back after each family. Returns the
    folder.
    """
    folder = Path(out_dir, "checks")
    folder.mkdir(exist_ok=True)
    for family in CHECK_FAMILIES if families is None else families:
        path = folder / f"{family}.parquet"
        command = [sys.executable, "-m", "synthetic.checks.suite", out_dir, family, str(path)]
        subprocess.run(command, check=True)
    return folder


def read_checks(out_dir: str) -> dict[str, pd.DataFrame]:
    """The check tables saved by `write_checks`, every family in `CHECK_FAMILIES` order; raises
    if a family's table is missing."""
    folder = Path(out_dir, "checks")
    missing = [f for f in CHECK_FAMILIES if not (folder / f"{f}.parquet").exists()]
    if missing:
        raise FileNotFoundError(f"{folder} has no check table for {missing}: run write_checks")
    return {f: pd.read_parquet(folder / f"{f}.parquet") for f in CHECK_FAMILIES}


def _write_family_table(out_dir: str, family: str, path: str) -> None:
    """Run one family on the dataset in `out_dir` (the mart family on its client sample) and save
    its table at `path`."""
    table = run_checks(out_dir, [family], CLIENT_SAMPLES.get(family))[family]
    table.astype({"expected": float, "realised": float, "tolerance": float}).to_parquet(path)


if __name__ == "__main__":  # one family in this process (`write_checks`)
    _write_family_table(*sys.argv[1:])
