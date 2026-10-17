"""Command line: write a synthetic dataset to disk (`output.write_mart`).

    python -m synthetic --preset canonical --n-clients 50000 --seed 0 \\
        --out data/01_raw/synthetic_canonical

It prints the size of what it wrote and how long it took; `--checks` also runs every check family
(each in its own process) and saves the tables in `<out>/checks/`, which the checking notebook
reads. The output folder must not hold a dataset already; `conf/local/sources.yml` then points the
logical source at `<out>/mart`.
"""

import argparse
import time

from synthetic.check_suite import read_checks, write_checks
from synthetic.output import read_output, write_mart
from synthetic.presets import PRESETS


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
    """Write the dataset the arguments describe and print its rows, columns, months and time."""
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
    if args.checks:
        write_checks(args.out)
        for family, table in read_checks(args.out).items():
            print(f"checks {family}: {int(table['passed'].sum())} of {len(table)} rows pass")


if __name__ == "__main__":
    main()
