"""The CLI: `python -m core_modelling decide <config> --entity E --reason R ...` appends one
decision to the audit log (D-125). Parsing only; the logic is `record_decision`. The `run`
command arrives with the dataset stage (plan, minor step 3.5).
"""

import argparse

import yaml

from core_modelling.config.audit_log import record_decision


def _parse_setting(text: str) -> dict[str, object]:
    """`path=value` as a one-item dict, the value read as YAML (so `300` is an int)."""
    path, sep, value = text.partition("=")
    if not sep or not path:
        raise argparse.ArgumentTypeError(f"--set takes path=value, got {text!r}")
    return {path: yaml.safe_load(value)}


def _build_parser() -> argparse.ArgumentParser:
    """The parser: one subcommand, `decide`."""
    parser = argparse.ArgumentParser(prog="python -m core_modelling")
    commands = parser.add_subparsers(dest="command", required=True)
    decide = commands.add_parser("decide", help="append one decision to the audit log")
    decide.add_argument("config", help="the use-case config file")
    decide.add_argument("--entity", required=True)
    decide.add_argument("--reason", required=True)
    decide.add_argument("--exclude", nargs="+", metavar="FEATURE")
    decide.add_argument("--include", nargs="+", metavar="FEATURE")
    decide.add_argument("--keep-despite-flag", nargs="+", metavar="FEATURE")
    decide.add_argument("--set", type=_parse_setting, metavar="PATH=VALUE")
    decide.add_argument("--evidence", nargs="*", default=(), metavar="TEXT")
    decide.add_argument("--stage")
    decide.add_argument("--env", help="the environment file (else $CORE_MODELLING_ENVIRONMENT)")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse the arguments and record the decision; prints the entry's number."""
    args = _build_parser().parse_args(argv)
    entry = record_decision(
        args.config,
        args.entity,
        exclude=args.exclude,
        include=args.include,
        keep_despite_flag=args.keep_despite_flag,
        set=args.set,
        reason=args.reason,
        evidence=args.evidence,
        stage=args.stage,
        env_path=args.env,
    )
    print(f"entry {entry.seq}: {entry.op} by {entry.by.id}")


if __name__ == "__main__":
    main()
