"""Every check family in one place, and running them on a written dataset.

A family is one checks module: its check function and the mart and oracle columns it reads, so a
canonical-size dataset is checked from column subsets of the written parquet, never loaded whole.
`run_checks` is what the tests and the checking notebook call. Each build step adds its families.
A family that reads every mart column (`MART_COLUMNS = None`, the mart family) runs at the canonical
size on a client sample (`client_sample`).
"""

import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd

from synthetic import (
    checks_amount_levels,
    checks_amount_mix,
    checks_amount_rules,
    checks_holding_drivers,
    checks_holdings,
    checks_mart,
    checks_oracle,
    checks_population,
    checks_seasons,
    checks_traps,
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
    "traps": _family(checks_traps, "check_traps"),
    "oracle": _family(checks_oracle, "check_oracle"),
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
        command = [sys.executable, "-m", "synthetic.check_suite", out_dir, family, str(path)]
        subprocess.run(command, check=True)
    return folder


def read_checks(out_dir: str) -> dict[str, pd.DataFrame]:
    """The check tables saved by `write_checks`, by family, in `CHECK_FAMILIES` order."""
    folder = Path(out_dir, "checks")
    return {
        f: pd.read_parquet(folder / f"{f}.parquet")
        for f in CHECK_FAMILIES
        if (folder / f"{f}.parquet").exists()
    }


if __name__ == "__main__":  # one family in this process: out_dir, family, output path
    out_dir, family, path = sys.argv[1:]
    table = run_checks(out_dir, [family], CLIENT_SAMPLES.get(family))[family]
    table.astype({"expected": float, "realised": float, "tolerance": float}).to_parquet(path)
