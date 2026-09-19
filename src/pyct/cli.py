"""The pyct command line.

``pyct run MODULE::FUNCTION [JSON] [--args JSON] [--budget SECONDS] [--plateau N]``
"""

from __future__ import annotations

import argparse
import inspect
import json
import math
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import NoReturn

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure, FailureKind
from pyct.results.jsonl import render, render_summary
from pyct.results.record import InputRecord, Miss, RunResult, StopKind
from pyct.results.trace import render_miss, render_stop, render_trace
from pyct.run.run import run
from pyct.run.target import Target, TargetError, load_target
from pyct.solver.answer import SolverAnswerError
from pyct.solver.locate import SolverMissingError, locate

USAGE = "pyct run MODULE::FUNCTION [JSON] [--args JSON] [--budget SECONDS] [--plateau N]"


class UsageError(Exception):
    """The command line is wrong. Exit 2."""


@dataclass(frozen=True)
class RunCommand:
    """What the command line asked for: the target spec, the seed, and the budget and plateau."""

    spec: str
    seed_text: str | None
    budget_text: str | None = None
    plateau_text: str | None = None


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return the exit code.

    0: the lines were printed. 1: cvc5 is missing or crashed, the target
    could not be loaded, or pyct itself broke during the run. 2: usage.

    The run prints each input as it finishes, through ``_report``, and each
    fork the solver could not flip, through ``_missed``, so a second input
    that hangs never hides the first one's line. Why the run stopped is a
    fact about the whole run, so it ends stderr, and the summary line ends
    stdout after it: the readable text comes first, as it does for every
    input.

    Checks run in this order: target form, seed shape, budget, plateau,
    import, seed present, seed fits, seed types, cvc5. Everything the command
    line got wrong is reported first, because a wrong command line is wrong
    whatever the machine has installed; cvc5 is the last check before the run
    for the same reason, as it is the only one about the machine. The import
    comes before the three seed checks because they all read the loaded
    target: its parameters, and the annotations on them.
    """
    try:
        command = parse_command(sys.argv[1:] if argv is None else argv)
        check_spec(command.spec)
        seed = None if command.seed_text is None else parse_seed(command.seed_text)
        budget = parse_budget(command.budget_text)
        plateau = parse_plateau(command.plateau_text)
        target = load_target(command.spec)
        if seed is None:
            raise UsageError(missing_args_message(target.signature))
        check_seed_fits(target.signature, seed)
        check_seed_types(target, seed)
        locate()
        result = run(
            target,
            seed,
            limits=Limits(budget=budget, plateau=plateau),
            report=_report,
            missed=_missed,
        )
    except UsageError as error:
        print(error, file=sys.stderr)
        return 2
    except (SolverMissingError, SolverAnswerError, TargetError) as error:
        print(error, file=sys.stderr)
        return 1
    print(render_stop(result), end="", file=sys.stderr, flush=True)
    print(render_summary(result), flush=True)
    return _exit_code(result)


def _report(record: InputRecord, coverage: Coverage) -> None:
    """The trace a person reads first, then the one line tools read."""
    print(render_trace(record, coverage), end="", file=sys.stderr, flush=True)
    print(render(record, coverage), flush=True)


def _missed(miss: Miss) -> None:
    """The fork the solver gave no input for, printed where its answer came in."""
    print(render_miss(miss), end="", file=sys.stderr, flush=True)


def _exit_code(result: RunResult) -> int:
    """Every line is printed either way; a dead solver or a pyct bug still ends it badly."""
    if result.stopped.kind is StopKind.SOLVER_FAILED:
        return 1
    return 1 if any(_is_a_bug(record.failure) for record in result.records) else 0


def _is_a_bug(failure: Failure | None) -> bool:
    return failure is not None and failure.kind is FailureKind.PYCT_BUG


def parse_command(argv: Sequence[str]) -> RunCommand:
    """Read the argv. The seed may follow the target, or come through ``--args``."""
    parser = _Parser(prog="pyct", usage=USAGE)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", usage=USAGE)
    run_parser.add_argument("target", metavar="MODULE::FUNCTION")
    run_parser.add_argument("seed", nargs="?", metavar="JSON")
    run_parser.add_argument("--args", dest="args_seed", metavar="JSON")
    run_parser.add_argument("--budget", metavar="SECONDS")
    run_parser.add_argument("--plateau", metavar="N")
    namespace = parser.parse_args(argv)
    if namespace.seed is not None and namespace.args_seed is not None:
        raise UsageError(f"give the seed once, after the target or through --args\nusage: {USAGE}")
    seed_text = namespace.seed if namespace.seed is not None else namespace.args_seed
    return RunCommand(
        spec=namespace.target,
        seed_text=seed_text,
        budget_text=namespace.budget,
        plateau_text=namespace.plateau,
    )


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
    # nan fails isfinite; inf passes > 0 and would overflow the timer
    if not (math.isfinite(seconds) and seconds > 0):
        raise UsageError(
            f"budget must be a finite number of seconds above zero, got {budget_text!r}"
        )
    return Budget(seconds=seconds)


def parse_plateau(plateau_text: str | None) -> Plateau:
    """The plateau is a whole number of inputs above zero. No flag is no plateau stop.

    ``int()`` decides what a whole number is: digits with an optional sign.
    ``1.0`` and ``1e2`` are refused like ``2.5``, so the flag never needs a
    float parse.
    """
    if plateau_text is None:
        return Plateau()
    refusal = f"plateau must be a whole number above zero, got {plateau_text!r}"
    try:
        inputs = int(plateau_text)
    except ValueError as error:
        raise UsageError(refusal) from error
    if inputs <= 0:
        raise UsageError(refusal)
    return Plateau(inputs=inputs)


def check_seed_fits(signature: inspect.Signature, seed: Mapping[str, object]) -> None:
    """Refuse a seed whose keys do not fit the parameters. Names only, not types."""
    try:
        signature.bind(**seed)
    except TypeError as error:
        # bind names a missing parameter before an unexpected key, so name the keys too
        given = ", ".join(seed) or "nothing"
        parameters = ", ".join(signature.parameters) or "no parameters"
        raise UsageError(f"args ({given}) do not fit ({parameters}): {error}") from error


def plain_annotations(fn: Callable[..., object]) -> dict[str, type]:
    """The parameters annotated with a bare ``str``, ``int``, ``float`` or ``bool``.

    Each annotation is resolved on its own, so one name that does not resolve
    costs that parameter alone rather than the whole function. An annotation
    kept as text, which is what ``from __future__ import annotations``
    leaves behind, is read in the globals of the function carrying it, where
    its names were written. Anything else the annotation turns out to be,
    ``str | None`` or ``list[int]`` or a class, is not one of the four and is
    not kept. The four are matched by identity, so an annotation that merely
    compares equal to ``str`` is not kept either.

    The parameters come from the signature, the same source ``check_seed_fits``
    reads, so a class target is read at its ``__init__``.
    """
    hints: dict[str, type] = {}
    for name, parameter in inspect.signature(fn).parameters.items():
        if parameter.annotation is inspect.Parameter.empty:
            continue
        resolved = _resolved(parameter.annotation, fn)
        if resolved is str or resolved is int or resolved is float or resolved is bool:
            hints[name] = resolved
    return hints


def _resolved(annotation: object, fn: Callable[..., object]) -> object:
    """The annotation itself, or what its text names. Any failure is no annotation."""
    if not isinstance(annotation, str):
        return annotation
    try:
        return eval(annotation, _names(fn))
    except Exception:
        return None


def _names(fn: Callable[..., object]) -> dict[str, object]:
    """The names the annotation text was written against, read where it lives."""
    # a class carries no __globals__; the text is its __init__'s, which the MRO may
    # take from another module. A slot wrapper __init__ has none, so the module answers
    owner = fn.__init__ if isinstance(fn, type) else fn
    # the signature is read through __wrapped__, so a decorator's own globals are not it
    owner = inspect.unwrap(owner)
    return getattr(owner, "__globals__", None) or vars(sys.modules[fn.__module__])


def contradictions(hints: Mapping[str, type], seed: Mapping[str, object]) -> list[str]:
    """One line per seeded parameter whose value Python's own typing would not accept.

    The lines come in the order of ``hints``, which is signature order. A
    value passes when it is an instance of the annotated type, plus the one
    allowance Python makes itself: an ``int`` stands in where a ``float`` is
    asked for. ``bool`` being a subclass of ``int`` is Python's rule too, so
    ``True`` passes ``int`` while ``1`` fails ``bool``. The value is spelled
    as JSON because the seed was typed as JSON.
    """
    return [
        _refusal(name, hint, seed[name])
        for name, hint in hints.items()
        if name in seed and not _accepts(hint, seed[name])
    ]


def _accepts(hint: type, value: object) -> bool:
    return isinstance(value, hint) or (hint is float and isinstance(value, int))


def _refusal(name: str, hint: type, value: object) -> str:
    article = "an" if hint is int else "a"
    return f"{name} must be {article} {hint.__name__}, got {json.dumps(value)}"


def check_seed_types(target: Target, seed: Mapping[str, object]) -> None:
    """Refuse a seed that contradicts a plain annotation, naming every one at once."""
    lines = contradictions(plain_annotations(target.fn), seed)
    if lines:
        raise UsageError("\n".join(lines))


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
