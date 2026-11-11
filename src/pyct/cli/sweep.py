"""The ``pyct sweep`` command: its flags, its limits, and the lines it prints."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from pyct.cli.shared import Parser, line
from pyct.config.budget import SWEEP_SECONDS
from pyct.config.command_line import (
    NO_DEADLINE,
    UsageError,
    parse_budget,
    parse_goal,
    parse_plateau,
    parse_solver_timeout,
    parse_total_budget,
)
from pyct.sweep.result import SweepLimits, closing, summary_line
from pyct.sweep.rows import Row, row_line, running, told
from pyct.sweep.sweep import Mode, SweepTell, sweep

SWEEP_USAGE = (
    "pyct sweep PACKAGE [--list] [--budget SECONDS] [--plateau N] [--solver-timeout SECONDS]"
    " [--total-budget SECONDS] [--goal coverage|bugs]"
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
    goal_text: str | None = None


def run_sweep(command: SweepCommand) -> int:
    """Sweep the package: each row on stdout as it is known, with its stderr line, then the
    closing lines and the summary."""
    check_package(command.package)
    limits = _sweep_limits(command)
    mode = Mode.LIST if command.list_only else Mode.RUN
    result = sweep(command.package, limits=limits, mode=mode, tell=SweepTell(_starting, _row))
    print(closing(result), end="", file=sys.stderr, flush=True)
    line(summary_line(result))
    return 0


def _sweep_limits(command: SweepCommand) -> SweepLimits:
    """The limits the command line gave, each by ``pyct run``'s rule, or the sweep's defaults."""
    defaults = SweepLimits()
    budget = parse_budget(command.budget_text, defaults.budget).seconds
    plateau = parse_plateau(command.plateau_text).inputs
    total = parse_total_budget(command.total_budget_text)
    solver_timeout = command.solver_timeout_text
    return SweepLimits(
        budget=budget,
        plateau=defaults.plateau if plateau is None else plateau,
        solver_timeout=(
            defaults.solver_timeout
            if solver_timeout is None
            else parse_solver_timeout(solver_timeout).seconds
        ),
        goal=parse_goal(command.goal_text),
        total_budget=total,
    )


def _starting(row: Row, number: int, count: int) -> None:
    print(running(row, number, count), file=sys.stderr, flush=True)


def _row(row: Row) -> None:
    line(row_line(row))
    said = told(row)
    if said is not None:
        print(said, file=sys.stderr, flush=True)


def sweep_parser(commands: argparse._SubParsersAction[Parser]) -> None:
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
    parser.add_argument(
        "--budget",
        metavar="SECONDS",
        help=f"each entry's budget; {SWEEP_SECONDS:g} by default, {NO_DEADLINE} for no deadline",
    )
    parser.add_argument("--plateau", metavar="N", help="each entry's plateau; 5 by default")
    parser.add_argument(
        "--solver-timeout", metavar="SECONDS", help="each solve's limit; 10 by default"
    )
    parser.add_argument(
        "--total-budget", metavar="SECONDS", help="the whole sweep's bound; no bound by default"
    )
    parser.add_argument("--goal", metavar="coverage|bugs", help="each entry's goal; coverage")


def sweep_command(namespace: argparse.Namespace) -> SweepCommand:
    return SweepCommand(
        package=namespace.package,
        list_only=namespace.list_only,
        budget_text=namespace.budget,
        plateau_text=namespace.plateau,
        solver_timeout_text=namespace.solver_timeout,
        total_budget_text=namespace.total_budget,
        goal_text=namespace.goal,
    )


def check_package(package: str) -> None:
    """Refuse a name with a part that is not a Python name, such as a path, and a file path given
    for a module name, which ends in ``.py``, as ``pyct run`` refuses one."""
    if not all(part.isidentifier() for part in package.split(".")) or package.endswith(".py"):
        raise UsageError(f"PACKAGE must be a module name, got {package!r}")
