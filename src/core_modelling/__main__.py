"""The CLI (D-024): `python -m core_modelling run <config>… [--stages …] [--entity …]` runs the
stages, and `decide <config> --entity E --reason R …` appends one decision to the audit log
(D-125). Parsing only; the logic is `run` and `record_decision`.
"""

import argparse

import yaml

from core_modelling.config.audit_log import record_decision
from core_modelling.run import STAGES, run


def _parse_setting(text: str) -> dict[str, object]:
    """`path=value` as a one-item dict, the value read as YAML (so `300` is an int)."""
    path, sep, value = text.partition("=")
    if not sep or not path:
        raise argparse.ArgumentTypeError(f"--set takes path=value, got {text!r}")
    return {path: yaml.safe_load(value)}


def _build_parser() -> argparse.ArgumentParser:
    """The parser: the subcommands `run` and `decide`."""
    parser = argparse.ArgumentParser(prog="python -m core_modelling")
    commands = parser.add_subparsers(dest="command", required=True)
    runner = commands.add_parser("run", help="run the stages of a use case")
    runner.add_argument("config", nargs="+", help="the use-case config file(s)")
    runner.add_argument("--stages", nargs="+", choices=list(STAGES), help="default: all built")
    runner.add_argument("--entity", help="default: every entity the config lists")
    runner.add_argument("--env", help="the environment file (else $CORE_MODELLING_ENVIRONMENT)")
    decide = commands.add_parser("decide", help="append one decision to the audit log")
    decide.add_argument("config", help="the use-case config file")
    decide.add_argument("--entity", required=True)
    decide.add_argument("--reason", required=True)
    decide.add_argument("--exclude", nargs="+", metavar="FEATURE")
    decide.add_argument("--include", nargs="+", metavar="FEATURE")
    decide.add_argument("--keep-despite-flag", nargs="+", metavar="FEATURE")
    decide.add_argument("--set", type=_parse_setting, metavar="PATH=VALUE")
    decide.add_argument("--revert-to", type=int, metavar="SEQ", help="0: the config as written")
    decide.add_argument("--evidence", nargs="*", default=(), metavar="TEXT")
    decide.add_argument("--stage")
    decide.add_argument("--env", help="the environment file (else $CORE_MODELLING_ENVIRONMENT)")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse the arguments and run the stages, or record the decision (its number printed)."""
    args = _build_parser().parse_args(argv)
    if args.command == "run":
        out = run(args.config, env_path=args.env, stages=args.stages, entity=args.entity)
        for entity, stages in out.items():
            print(f"{entity}: ran {', '.join(stages)}")
        return
    entry = record_decision(
        args.config,
        args.entity,
        exclude=args.exclude,
        include=args.include,
        keep_despite_flag=args.keep_despite_flag,
        set=args.set,
        revert_to=args.revert_to,
        reason=args.reason,
        evidence=args.evidence,
        stage=args.stage,
        env_path=args.env,
    )
    print(f"entry {entry.seq}: {entry.op} by {entry.by.id}")


if __name__ == "__main__":
    main()
