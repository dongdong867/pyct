"""The pyct command line.

``pyct run MODULE::FUNCTION [JSON] [--args JSON] [--budget SECONDS] [--plateau N]
[--solver-timeout SECONDS] [--in-process]``

``pyct sweep PACKAGE [--list] [--budget SECONDS] [--plateau N] [--solver-timeout SECONDS]
[--total-budget SECONDS]``
"""

from __future__ import annotations

import argparse
import functools
import inspect
import json
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import NoReturn

from pyct.binding.annotations import contradictions
from pyct.binding.bind import access_name, leaves
from pyct.binding.call import call_arguments, positional_only
from pyct.binding.resolve import checked_annotations
from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.config.solver_timeout import SolverTimeout
from pyct.execution.deadline import own_the_alarm
from pyct.intercept.cache import CACHE_HELP
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure, FailureKind
from pyct.results.jsonl import render, render_summary
from pyct.results.printed import printed_forks
from pyct.results.record import InputRecord, Miss, RunResult, StopKind
from pyct.results.trace import render_miss, render_stop, render_trace
from pyct.run.import_watch import ImportWatch
from pyct.run.isolation import Isolation
from pyct.run.launch import launch
from pyct.run.run import Tell, run
from pyct.run.target import Target, TargetError, interception, load_target
from pyct.solver.locate import SolverMissingError, locate
from pyct.sweep.listing import PackageImportError
from pyct.sweep.result import SweepLimits, closing, summary_line
from pyct.sweep.rows import Row, row_line, running, told
from pyct.sweep.sweep import Mode, SweepTell, sweep

USAGE = (
    "pyct run MODULE::FUNCTION [JSON] [--args JSON] [--budget SECONDS] [--plateau N]"
    " [--solver-timeout SECONDS] [--in-process]"
)
SWEEP_USAGE = (
    "pyct sweep PACKAGE [--list] [--budget SECONDS] [--plateau N] [--solver-timeout SECONDS]"
    " [--total-budget SECONDS]"
)
# what pyct sweep --help says above the flags, kept as written
SWEEP_WARNING = """\
pyct sweep runs each public function and class of PACKAGE as its own pyct run.
It calls every function and class it runs with inputs it made up. Each entry
runs in a temporary working directory of its own, which takes only the files
an input writes by a relative path, and isolation undoes what an input changes
in its process. Nothing undoes a file an input writes anywhere else or a
request it sends.
"""

# how many levels past the seed's own depth the check writes: room for the line, its forks, one
# fork, its condition, and a few operations the target applies to the value
LINE_NESTING = 8


class UsageError(Exception):
    """The command line is wrong. Exit 2."""


@dataclass(frozen=True)
class RunCommand:
    """What the command line asked for: the target spec, the seed, the three limits, and where.

    ``in_process`` runs every input in pyct's own process rather than one of its own.
    """

    spec: str
    seed_text: str | None
    budget_text: str | None = None
    plateau_text: str | None = None
    solver_timeout_text: str | None = None
    in_process: bool = False


@dataclass(frozen=True)
class SweepCommand:
    """What ``pyct sweep`` was asked for: the package, whether only to list its entries, and the
    limits, as the command line gave them."""

    package: str
    list_only: bool = False
    budget_text: str | None = None
    plateau_text: str | None = None
    solver_timeout_text: str | None = None
    total_budget_text: str | None = None


def entry() -> int:
    """The command line as the shell starts it: ``main`` in a process of its own, watched here.

    A target whose import ends its process, by ``os._exit`` or a signal,
    ends the process ``main`` runs in, so the process the shell started
    outlives it to say so (see ``pyct.run.launch``). Tests call ``main`` in
    their own process instead.
    """
    # pyct owns the processes the shell starts, so its deadline takes SIGALRM for good
    own_the_alarm()
    argv = sys.argv[1:]
    return launch(functools.partial(main, argv), argv)


def main(argv: Sequence[str] | None = None, watch: ImportWatch | None = None) -> int:
    """Run the command line and return the exit code.

    0: the lines were printed. 1: cvc5 is missing or crashed, the target
    could not be loaded, pyct could not start a process for an input, or
    pyct itself broke during the run. 2: usage.

    The run prints each input as it finishes, through ``_report``, and each
    fork the solver could not flip, through ``_missed``, so a second input
    that hangs never hides the first one's line. Why the run stopped is a
    fact about the whole run, so it ends stderr, and the summary line ends
    stdout after it: the readable text comes first, as it does for every
    input.

    The target's package is substituted from its import to the run's end,
    in this process and in every input's (``pyct.intercept``).

    Checks run in this order: target form, seed shape, budget, plateau,
    solver timeout, import and signature, seed present, seed fits, seed
    types, cvc5.
    Everything the command line got wrong is reported first, because a wrong
    command line is wrong whatever the machine has installed; cvc5 is the
    last check before the run for the same reason, as it is the only one
    about the machine. The import comes before the three seed checks because
    they all read the loaded target: its parameters, and the annotations on
    them.

    While the target imports, ``watch`` names its module for the process
    that watches this one, when ``entry`` started one.
    """
    try:
        command = parse_command(sys.argv[1:] if argv is None else argv)
        if isinstance(command, SweepCommand):
            return _sweep(command)
        with interception(command.spec):
            target, seed, limits = _checked(command, watch)
            result = run(
                target,
                seed,
                limits=limits,
                isolation=Isolation.IN_PROCESS if command.in_process else Isolation.AUTO,
                tell=Tell(report=_report, missed=_missed),
            )
    except UsageError as error:
        print(error, file=sys.stderr)
        return 2
    except (SolverMissingError, TargetError, PackageImportError) as error:
        print(error, file=sys.stderr)
        return 1
    print(render_stop(result), end="", file=sys.stderr, flush=True)
    _line(render_summary(result))
    return _exit_code(result)


def _checked(
    command: RunCommand, watch: ImportWatch | None
) -> tuple[Target, Mapping[str, object], Limits]:
    """Every check before the run, in the order ``main`` gives. Each raises what main reports."""
    check_spec(command.spec)
    seed = None if command.seed_text is None else parse_seed(command.seed_text)
    limits = Limits(
        budget=parse_budget(command.budget_text),
        plateau=parse_plateau(command.plateau_text),
        solver_timeout=parse_solver_timeout(command.solver_timeout_text),
    )
    target = load_target(command.spec, watch)
    if seed is None:
        raise UsageError(missing_args_message(target.signature))
    check_seed_fits(target.signature, seed)
    check_seed_types(target, seed)
    locate()
    return target, seed, limits


def _sweep(command: SweepCommand) -> int:
    """Sweep the package: each row on stdout as it is known, with its stderr line, then the
    closing lines and the summary."""
    check_package(command.package)
    limits = _sweep_limits(command)
    mode = Mode.LIST if command.list_only else Mode.RUN
    result = sweep(command.package, limits=limits, mode=mode, tell=SweepTell(_starting, _row))
    print(closing(result), end="", file=sys.stderr, flush=True)
    _line(summary_line(result))
    return 0


def _sweep_limits(command: SweepCommand) -> SweepLimits:
    """The limits the command line gave, each by ``pyct run``'s rule, or the sweep's defaults."""
    defaults = SweepLimits()
    budget = parse_budget(command.budget_text).seconds
    plateau = parse_plateau(command.plateau_text).inputs
    total = parse_budget(command.total_budget_text, "total budget").seconds
    solver_timeout = command.solver_timeout_text
    return SweepLimits(
        budget=defaults.budget if budget is None else budget,
        plateau=defaults.plateau if plateau is None else plateau,
        solver_timeout=(
            defaults.solver_timeout
            if solver_timeout is None
            else parse_solver_timeout(solver_timeout).seconds
        ),
        total_budget=total,
    )


def _starting(row: Row, number: int, count: int) -> None:
    print(running(row, number, count), file=sys.stderr, flush=True)


def _row(row: Row) -> None:
    _line(row_line(row))
    said = told(row)
    if said is not None:
        print(said, file=sys.stderr, flush=True)


def _report(record: InputRecord, coverage: Coverage) -> None:
    """The trace a person reads first, then the one line tools read.

    Both print each fork's expression cut to the cap, and it is cut once for both.
    An access to one of the input's values is a name, written whole. A seed with
    no value inside an argument has no access to name, and no part is asked.
    """
    names = leaves(record.args)
    if names.keys() <= record.args.keys():
        printed = printed_forks(record.forks)
    else:
        # each part's access, once: a path through a deep dict names every step of its chain
        known: dict[int, str | None] = {}
        printed = printed_forks(record.forks, lambda part: access_name(part, known) in names)
    print(render_trace(record, coverage, printed), end="", file=sys.stderr, flush=True)
    _line(render(record, coverage, printed))


def _line(text: str) -> None:
    """One stdout line: the text and its end go out in one write, so a Ctrl-C between two
    writes cannot leave the line without its end."""
    sys.stdout.write(f"{text}\n")
    sys.stdout.flush()


def _missed(miss: Miss) -> None:
    """The fork the solver gave no input for, printed where its answer came in."""
    print(render_miss(miss), end="", file=sys.stderr, flush=True)


def _exit_code(result: RunResult) -> int:
    """Every line is printed either way; a dead solver, an input that could not start, or a
    pyct bug still ends it badly."""
    if result.stopped.kind in (StopKind.SOLVER_FAILED, StopKind.COULD_NOT_START):
        return 1
    return 1 if any(_is_a_bug(record.failure) for record in result.records) else 0


def _is_a_bug(failure: Failure | None) -> bool:
    return failure is not None and failure.kind is FailureKind.PYCT_BUG


def parse_command(argv: Sequence[str]) -> RunCommand | SweepCommand:
    """Read the argv. The seed may follow the target, or come through ``--args``."""
    parser = _Parser(prog="pyct", usage=f"{USAGE}\n       {SWEEP_USAGE}")
    commands = parser.add_subparsers(dest="command", required=True)
    _sweep_parser(commands)
    run_parser = commands.add_parser("run", usage=USAGE, epilog=CACHE_HELP)
    run_parser.add_argument("target", metavar="MODULE::FUNCTION")
    run_parser.add_argument("seed", nargs="?", metavar="JSON")
    run_parser.add_argument("--args", dest="args_seed", metavar="JSON")
    run_parser.add_argument("--budget", metavar="SECONDS")
    run_parser.add_argument("--plateau", metavar="N")
    run_parser.add_argument("--solver-timeout", metavar="SECONDS")
    run_parser.add_argument("--in-process", action="store_true")
    namespace = parser.parse_args(argv)
    if namespace.command == "sweep":
        return _sweep_command(namespace)
    if namespace.seed is not None and namespace.args_seed is not None:
        raise UsageError(f"give the seed once, after the target or through --args\nusage: {USAGE}")
    seed_text = namespace.seed if namespace.seed is not None else namespace.args_seed
    return RunCommand(
        spec=namespace.target,
        seed_text=seed_text,
        budget_text=namespace.budget,
        plateau_text=namespace.plateau,
        solver_timeout_text=namespace.solver_timeout,
        in_process=namespace.in_process,
    )


def _sweep_parser(commands: argparse._SubParsersAction[_Parser]) -> None:
    """The ``sweep`` command, with the warning ``--help`` gives above its flags."""
    parser = commands.add_parser(
        "sweep",
        usage=SWEEP_USAGE,
        description=SWEEP_WARNING,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("package", metavar="PACKAGE", help="a module name, such as a.b")
    parser.add_argument(
        "--list", dest="list_only", action="store_true", help="list the entries; run none"
    )
    parser.add_argument("--budget", metavar="SECONDS", help="each entry's budget; 30 by default")
    parser.add_argument("--plateau", metavar="N", help="each entry's plateau; 5 by default")
    parser.add_argument(
        "--solver-timeout", metavar="SECONDS", help="each solve's limit; 10 by default"
    )
    parser.add_argument(
        "--total-budget", metavar="SECONDS", help="the whole sweep's bound; none by default"
    )


def _sweep_command(namespace: argparse.Namespace) -> SweepCommand:
    return SweepCommand(
        package=namespace.package,
        list_only=namespace.list_only,
        budget_text=namespace.budget,
        plateau_text=namespace.plateau,
        solver_timeout_text=namespace.solver_timeout,
        total_budget_text=namespace.total_budget,
    )


def check_package(package: str) -> None:
    """Refuse a name with a part that is not a Python name, such as a path, and a file path given
    for a module name, which ends in ``.py``, as ``pyct run`` refuses one."""
    if not all(part.isidentifier() for part in package.split(".")) or package.endswith(".py"):
        raise UsageError(f"PACKAGE must be a module name, got {package!r}")


def check_spec(spec: str) -> None:
    """Refuse anything but ``module::function``, each part a name. A path is not a module."""
    module, separator, function = spec.partition("::")
    parts = [*module.split("."), function]
    named = bool(separator) and all(part.isidentifier() for part in parts)
    # `mod.py` is every part a name, and still a file path rather than a module
    if not named or module.endswith(".py"):
        raise UsageError(f"target must be MODULE::FUNCTION, got {spec!r}")


def parse_seed(seed_text: str) -> Mapping[str, object]:
    """The seed is a JSON object, one key per parameter, nested no deeper than a line can hold."""
    try:
        seed = json.loads(seed_text)
    except json.JSONDecodeError as error:
        raise UsageError(f"args must be a JSON object: {error}") from error
    except RecursionError as error:
        raise UsageError("args nest too deep for Python to read") from error
    if not isinstance(seed, dict):
        raise UsageError(f"args must be a JSON object, got {type(seed).__name__}")
    _check_writable(seed)
    return seed


def _check_writable(seed: Mapping[str, object]) -> None:
    """Refuse a seed too deep for a line to hold a fork a few operations deep on its deepest value.

    The line holds each fork on a value inside the seed a few levels below
    the value, and Python's JSON writer stops at a depth of its own. So the
    check writes a list nested ``LINE_NESTING`` levels past the seed before
    any input runs, which allows for a few operations on the value.
    """
    depth = _depth(seed)
    probe: list[object] = [0]
    for _ in range(depth + LINE_NESTING - 1):
        probe = [probe]
    try:
        json.dumps(probe)
    except RecursionError as error:
        raise UsageError(
            f"args nest {depth} levels deep, too deep for pyct to write each input's line"
        ) from error


def _depth(value: object) -> int:
    """How many objects and arrays deep a JSON value nests, read in a loop, not a call per level."""
    deepest = 0
    pending: list[tuple[object, int]] = [(value, 1)]
    while pending:
        item, level = pending.pop()
        if isinstance(item, dict):
            item = list(item.values())
        if isinstance(item, list):
            deepest = max(deepest, level)
            pending.extend((child, level + 1) for child in item)
    return deepest


def parse_budget(budget_text: str | None, flag: str = "budget") -> Budget:
    """The budget is a positive number of seconds. No flag is no deadline.

    ``flag`` names it in a refusal, so a sweep's total budget is refused in the budget's words.
    """
    if budget_text is None:
        return Budget()
    return Budget(seconds=_positive_seconds(budget_text, flag))


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


def parse_solver_timeout(solver_timeout_text: str | None) -> SolverTimeout:
    """The seconds each solve may take, a positive number. No flag is the default limit.

    Checked as the budget is, finite and above zero, so no value turns the
    limit off.
    """
    if solver_timeout_text is None:
        return SolverTimeout()
    return SolverTimeout(seconds=_positive_seconds(solver_timeout_text, "solver timeout"))


def _positive_seconds(text: str, flag: str) -> float:
    """``text`` as a finite number of seconds above zero. ``flag`` names it in a refusal.

    The budget and the solver timeout share this one rule. ``inf`` passes
    ``> 0``, so ``isfinite`` is what refuses it along with ``nan``.
    """
    try:
        seconds = float(text)
    except ValueError as error:
        raise UsageError(f"{flag} must be a number of seconds, got {text!r}") from error
    if not (math.isfinite(seconds) and seconds > 0):
        raise UsageError(f"{flag} must be a finite number of seconds above zero, got {text!r}")
    return seconds


def check_seed_fits(signature: inspect.Signature, seed: Mapping[str, object]) -> None:
    """Refuse a seed whose keys do not fit the parameters. Names only, not types.

    A positional-only parameter is named too, and bound by position, as the
    call will pass it.
    """
    positional, keywords = call_arguments(positional_only(signature), seed)
    try:
        signature.bind(*positional, **keywords)
    except TypeError as error:
        # bind names a missing parameter before an unexpected key, so name the keys too
        given = ", ".join(seed) or "nothing"
        parameters = ", ".join(signature.parameters) or "no parameters"
        raise UsageError(f"args ({given}) do not fit ({parameters}): {error}") from error


def check_seed_types(target: Target, seed: Mapping[str, object]) -> None:
    """Refuse a seed that contradicts an annotation, naming every value at once."""
    lines = contradictions(checked_annotations(target.signature, target.fn), seed)
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
        raise UsageError(f"{message}\nusage: {self.usage}")
