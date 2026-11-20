"""The CLI (D-024): `python -m core_modelling run <config>… [--stages …] [--entity …]` runs the
stages, and `run <config> --stages evaluation --run r007` evaluates a named run; `decide
<config> --entity E --reason R …` appends one decision to the audit log (D-125), e.g. `--keep
F… --findings S…`, or the feature sign-off with `--sign-off --run r007`; `runs
<config> --entity E` lists the use case's runs and `show-run <config> --entity E --run r007`
shows one (D-139). Parsing only; the logic is `run`, `record_decision`, `sign_off`, `list_runs`
and `show_run`.
"""

import argparse

import yaml

from core_modelling.config import load_config
from core_modelling.config.audit_log import record_decision
from core_modelling.config.identities import short
from core_modelling.environment import load_environment, models_dir
from core_modelling.run import STAGES, run
from core_modelling.runs import list_runs, show_run, sign_off

ENV_HELP = "the environment file (else $CORE_MODELLING_ENVIRONMENT)"
# The decision operands `--sign-off` takes none of: a sign-off is its own entry (D-125 (c)).
DECISION_OPERANDS = ("exclude", "include", "keep", "findings", "set", "revert_to", "stage")


def _parse_setting(text: str) -> dict[str, object]:
    """`path=value` as a one-item dict, the value read as YAML (so `300` is an int)."""
    path, sep, value = text.partition("=")
    if not sep or not path:
        raise argparse.ArgumentTypeError(f"--set takes path=value, got {text!r}")
    return {path: yaml.safe_load(value)}


def _add_decide(commands: argparse._SubParsersAction) -> None:
    """The `decide` subcommand: one decision, or the sign-off of a run."""
    decide = commands.add_parser("decide", help="append one decision to the audit log")
    decide.add_argument("config", help="the use-case config file")
    decide.add_argument("--entity", required=True)
    decide.add_argument("--reason", required=True)
    decide.add_argument("--exclude", nargs="+", metavar="FEATURE")
    decide.add_argument("--include", nargs="+", metavar="FEATURE")
    decide.add_argument("--keep", nargs="+", metavar="FEATURE")
    decide.add_argument(
        "--findings", nargs="+", metavar="FINDING", help="with --keep: the flags it settles"
    )
    decide.add_argument("--set", type=_parse_setting, metavar="PATH=VALUE")
    decide.add_argument("--revert-to", type=int, metavar="SEQ", help="0: the config as written")
    decide.add_argument(
        "--sign-off", action="store_true", help="sign off the final feature list of --run"
    )
    decide.add_argument("--run", metavar="RUN", help="with --sign-off: the run, e.g. r007")
    decide.add_argument("--evidence", nargs="*", default=(), metavar="TEXT")
    decide.add_argument("--stage")
    decide.add_argument("--env", help=ENV_HELP)


def _build_parser() -> argparse.ArgumentParser:
    """The parser: the subcommands `run`, `decide`, `runs` and `show-run`."""
    parser = argparse.ArgumentParser(prog="python -m core_modelling")
    commands = parser.add_subparsers(dest="command", required=True)
    runner = commands.add_parser("run", help="run the stages of a use case")
    runner.add_argument("config", nargs="+", help="the use-case config file(s)")
    runner.add_argument("--stages", nargs="+", choices=list(STAGES), help="default: all built")
    runner.add_argument("--entity", help="default: every entity the config lists")
    runner.add_argument(
        "--run", metavar="RUN", help="with --stages evaluation: e.g. r007 (default: the latest)"
    )
    runner.add_argument("--env", help=ENV_HELP)
    _add_decide(commands)
    runs = commands.add_parser("runs", help="list the runs of a use case")
    show = commands.add_parser("show-run", help="show one run's record")
    for command in (runs, show):
        command.add_argument("config", help="the use-case config file")
        command.add_argument("--entity", required=True)
        command.add_argument("--env", help=ENV_HELP)
    show.add_argument("--run", required=True, metavar="RUN", help="e.g. r007")
    return parser


def _check_sign_off(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Refuse `--sign-off` without `--run`, or with a decision's operands or evidence, and
    `--run` without `--sign-off`."""
    if not args.sign_off:
        if args.run is not None:
            parser.error("decide: --run goes with --sign-off only")
        return
    extra = [f"--{name.replace('_', '-')}" for name in DECISION_OPERANDS
             if getattr(args, name) is not None]  # fmt: skip
    extra += ["--evidence"] if args.evidence else []
    if args.run is None:
        parser.error("decide --sign-off needs --run, e.g. --run r007")
    if extra:
        parser.error(f"decide --sign-off records a sign-off alone; it takes no {extra}")


def _decide(args: argparse.Namespace) -> None:
    """Record the sign-off or the decision, its number printed."""
    if args.sign_off:
        cfg, env = load_config(args.config), load_environment(args.env)
        entry = sign_off(cfg, args.entity, env, args.run, args.reason)
        print(f"signed off {entry.run_id}: {len(entry.features)} features, signature "
              f"{short(entry.signature)}: {', '.join(entry.features)}")  # fmt: skip
        print(f"entry {entry.seq}: sign_off of {entry.run_id} by {entry.by.id}")
        return
    entry = record_decision(
        args.config,
        args.entity,
        exclude=args.exclude,
        include=args.include,
        keep=args.keep,
        findings=args.findings,
        set=args.set,
        revert_to=args.revert_to,
        reason=args.reason,
        evidence=args.evidence,
        stage=args.stage,
        env_path=args.env,
    )
    print(f"entry {entry.seq}: {entry.op} by {entry.by.id}")


def main(argv: list[str] | None = None) -> None:
    """Parse the arguments and run the stages, record the decision, or list or show runs."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        out = run(
            args.config, env_path=args.env, stages=args.stages, entity=args.entity, run=args.run
        )
        for entity, stages in out.items():
            print(f"{entity}: ran {', '.join(stages)}")
    elif args.command == "decide":
        _check_sign_off(parser, args)
        _decide(args)
    else:
        cfg, env = load_config(args.config), load_environment(args.env)
        if args.command == "show-run":
            print(show_run(env, cfg, args.entity, args.run))
            return
        table = list_runs(env, cfg, args.entity)
        print(table.to_string(index=False) if len(table) else f"no runs at {models_dir(env, cfg)}")


if __name__ == "__main__":
    main()
