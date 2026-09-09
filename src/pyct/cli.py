"""The pyct command line. ``pyct run MODULE::FUNCTION [JSON] [--args JSON] [--budget SECONDS]``."""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import NoReturn

from pyct.config.budget import Budget
from pyct.results.coverage import Coverage
from pyct.results.failure import FailureKind
from pyct.results.jsonl import render
from pyct.results.record import InputRecord
from pyct.results.trace import render_trace
from pyct.run.run import run
from pyct.run.target import TargetError, load_target

USAGE = "pyct run MODULE::FUNCTION [JSON] [--args JSON] [--budget SECONDS]"


class UsageError(Exception):
    """The command line is wrong. Exit 2."""


@dataclass(frozen=True)
class RunCommand:
    """What the command line asked for: the target spec, and the seed and budget text, if any."""

    spec: str
    seed_text: str | None
    budget_text: str | None = None


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return the exit code.

    0: the JSON line was printed. 1: the target could not be loaded, or pyct
    itself broke during the run. 2: usage.

    Checks run in this order: target form, seed shape, budget, import, seed
    present, seed fits. The import comes before the seed-present check because
    that message names the target's parameters, which only the loaded target
    knows.
    """
    try:
        command = parse_command(sys.argv[1:] if argv is None else argv)
        check_spec(command.spec)
        seed = None if command.seed_text is None else parse_seed(command.seed_text)
        budget = parse_budget(command.budget_text)
        target = load_target(command.spec)
        if seed is None:
            raise UsageError(missing_args_message(target.signature))
        check_seed_fits(target.signature, seed)
        result = run(target, seed, budget=budget)
    except UsageError as error:
        print(error, file=sys.stderr)
        return 2
    except TargetError as error:
        print(error, file=sys.stderr)
        return 1
    record = result.records[0]
    _report(record, result.coverage)
    return _exit_code(record)


def _report(record: InputRecord, coverage: Coverage) -> None:
    """The trace a person reads first, then the one line tools read."""
    print(render_trace(record, coverage), end="", file=sys.stderr)
    print(render(record, coverage))


def _exit_code(record: InputRecord) -> int:
    """The line is printed either way; a pyct bug still ends the command badly."""
    return 1 if record.failure is not None and record.failure.kind is FailureKind.PYCT_BUG else 0


def parse_command(argv: Sequence[str]) -> RunCommand:
    """Read the argv. The seed may follow the target, or come through ``--args``."""
    parser = _Parser(prog="pyct", usage=USAGE)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", usage=USAGE)
    run_parser.add_argument("target", metavar="MODULE::FUNCTION")
    run_parser.add_argument("seed", nargs="?", metavar="JSON")
    run_parser.add_argument("--args", dest="args_seed", metavar="JSON")
    run_parser.add_argument("--budget", metavar="SECONDS")
    namespace = parser.parse_args(argv)
    if namespace.seed is not None and namespace.args_seed is not None:
        raise UsageError(f"give the seed once, after the target or through --args\nusage: {USAGE}")
    seed_text = namespace.seed if namespace.seed is not None else namespace.args_seed
    return RunCommand(spec=namespace.target, seed_text=seed_text, budget_text=namespace.budget)


def check_spec(spec: str) -> None:
    """Refuse anything but ``module::function``, each part a name. A path is not a module."""
    module, separator, function = spec.partition("::")
    parts = [*module.split("."), function]
    named = bool(separator) and all(part.isidentifier() for part in parts)
    # `mod.py` is every part a name, and still a file path rather than a module
    if not named or module.endswith(".py"):
        raise UsageError(f"target must be MODULE::FUNCTION, got {spec!r}")


def parse_seed(seed_text: str) -> Mapping[str, object]:
    """The seed is a JSON object, one key per parameter."""
    try:
        seed = json.loads(seed_text)
    except json.JSONDecodeError as error:
        raise UsageError(f"args must be a JSON object: {error}") from error
    if not isinstance(seed, dict):
        raise UsageError(f"args must be a JSON object, got {type(seed).__name__}")
    return seed


def parse_budget(budget_text: str | None) -> Budget:
    """The budget is a positive number of seconds. No flag is no deadline."""
    if budget_text is None:
        return Budget()
    try:
        seconds = float(budget_text)
    except ValueError as error:
        raise UsageError(f"budget must be a number of seconds, got {budget_text!r}") from error
    # `not > 0` rather than `<= 0`, because every compare against nan is False
    if not seconds > 0:
        raise UsageError(f"budget must be more than zero seconds, got {budget_text!r}")
    return Budget(seconds=seconds)


def check_seed_fits(signature: inspect.Signature, seed: Mapping[str, object]) -> None:
    """Refuse a seed whose keys do not fit the parameters. Names only, not types."""
    try:
        signature.bind(**seed)
    except TypeError as error:
        # bind names a missing parameter before an unexpected key, so name the keys too
        given = ", ".join(seed) or "nothing"
        parameters = ", ".join(signature.parameters) or "no parameters"
        raise UsageError(f"args ({given}) do not fit ({parameters}): {error}") from error


def missing_args_message(signature: inspect.Signature) -> str:
    """Name the parameters the seed must give, and both ways to pass it."""
    parameters = ", ".join(signature.parameters) or "no parameters"
    return (
        f"args are required: a JSON object for {parameters}\n"
        f"pass it after the target (pyct run MODULE::FUNCTION JSON) or through --args"
    )


class _Parser(argparse.ArgumentParser):
    """An argparse parser that raises UsageError instead of exiting."""

    def error(self, message: str) -> NoReturn:
        raise UsageError(f"{message}\nusage: {USAGE}")
