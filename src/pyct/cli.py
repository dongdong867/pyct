"""The pyct command line. ``pyct run MODULE::FUNCTION [JSON] [--args JSON]``."""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import NoReturn

from pyct.results.jsonl import render
from pyct.run.run import run
from pyct.run.target import TargetError, load_target

USAGE = "pyct run MODULE::FUNCTION [JSON] [--args JSON]"


class UsageError(Exception):
    """The command line is wrong. Exit 2."""


@dataclass(frozen=True)
class RunCommand:
    """What the command line asked for: the target spec and the seed text, if any."""

    spec: str
    seed_text: str | None


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return the exit code.

    0: the JSON line was printed. 1: the target could not be loaded. 2: usage.
    """
    try:
        command = parse_command(sys.argv[1:] if argv is None else argv)
        target = load_target(command.spec)
        if command.seed_text is None:
            raise UsageError(missing_args_message(target.signature))
        seed = _parse_seed(command.seed_text)
        result = run(target, seed)
    except UsageError as error:
        print(error, file=sys.stderr)
        return 2
    except TargetError as error:
        print(error, file=sys.stderr)
        return 1
    print(render(result.records[0], result.coverage))
    return 0


def parse_command(argv: Sequence[str]) -> RunCommand:
    """Read the argv. The seed may follow the target, or come through ``--args``."""
    parser = _Parser(prog="pyct", usage=USAGE)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", usage=USAGE)
    run_parser.add_argument("target", metavar="MODULE::FUNCTION")
    run_parser.add_argument("seed", nargs="?", metavar="JSON")
    run_parser.add_argument("--args", dest="args_seed", metavar="JSON")
    namespace = parser.parse_args(argv)
    seed_text = namespace.seed if namespace.seed is not None else namespace.args_seed
    return RunCommand(spec=namespace.target, seed_text=seed_text)


def missing_args_message(signature: inspect.Signature) -> str:
    """Name the parameters the seed must give, and both ways to pass it."""
    parameters = ", ".join(signature.parameters) or "no parameters"
    return (
        f"args are required: a JSON object for {parameters}\n"
        f"pass it after the target (pyct run MODULE::FUNCTION JSON) or through --args"
    )


def _parse_seed(seed_text: str) -> Mapping[str, object]:
    return json.loads(seed_text)


class _Parser(argparse.ArgumentParser):
    """An argparse parser that raises UsageError instead of exiting."""

    def error(self, message: str) -> NoReturn:
        raise UsageError(f"{message}\nusage: {USAGE}")
