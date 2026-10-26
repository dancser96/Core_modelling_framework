"""Command line: write a synthetic dataset to disk (`output.write_mart`).

    python -m synthetic --preset canonical --n-clients 50000 --seed 0 \\
        --out data/01_raw/synthetic_canonical

It prints the size of what it wrote and how long it took; `--checks` also runs every check family
(each in its own process), saves the tables in `<out>/checks/`, which the checking notebook reads,
prints each family's pass count and exits with status 1 if any row fails. The output folder must
not hold a dataset already; the environment file `conf/local/environment.yml` then maps
the sources to `<out>/mart` and `<out>/holdings`.
"""

import argparse
import sys
import time

from synthetic.checks.suite import read_checks, write_checks
from synthetic.output import read_output, write_mart
from synthetic.spec.presets import PRESETS


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """The command line's arguments (`argv` None reads `sys.argv`)."""
    parser = argparse.ArgumentParser(
        prog="python -m synthetic", description="Write a synthetic dataset to disk."
    )
    parser.add_argument("--preset", choices=list(PRESETS), default="canonical")
    parser.add_argument("--n-clients", type=int, help="default: the preset's")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-months", type=int, help="default: the preset's")
    parser.add_argument("--out", required=True, help="an empty or new folder")
    parser.add_argument("--dirty", action="store_true", help="plant the dirty-data defects")
    parser.add_argument("--extra-columns", type=int, default=0, help="extra weak or noise columns")
    parser.add_argument("--checks", action="store_true", help="run and save every check family")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Write the dataset the arguments describe and print its rows, columns, months and time;
    with `--checks`, exit with status 1 if a check row fails."""
    args = parse_args(argv)
    start = time.perf_counter()
    truth = write_mart(
        args.out,
        preset=args.preset,
        n_clients=args.n_clients,
        seed=args.seed,
        n_months=args.n_months,
        dirty=args.dirty,
        n_extra_columns=args.extra_columns,
    )
    seconds = time.perf_counter() - start
    keys = read_output(args.out, "mart", ["client_id", "snapshot_month"])
    print(
        f"wrote {args.out}: {len(keys):,} rows, {len(truth['columns'])} columns, "
        f"{keys['snapshot_month'].nunique()} months in {seconds:.0f} s "
        f"(preset {args.preset}, {truth['n_clients']:,} clients, seed {args.seed})"
    )
    if not args.checks:
        return
    write_checks(args.out)
    tables = read_checks(args.out)
    for family, table in tables.items():
        print(f"checks {family}: {int(table['passed'].sum())} of {len(table)} rows pass")
    if not all(table["passed"].all() for table in tables.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
