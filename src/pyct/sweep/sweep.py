"""``sweep()``: list a package's entries, run each as its own ``pyct run``, and sum the runs.

Entries run one at a time, so each entry's budget is measured on the same
machine load. ``SweepLimits.total_budget`` bounds the whole sweep, listing
included: an entry starts only while it has time left, with the smaller of
its budget and what is left, and each entry that cannot start gets a
skipped row with the seed it would have run with. Sweep never calls a
target in its own process.
"""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum

from pyct.solver.locate import locate, version
from pyct.sweep.listing import LISTER, list_package
from pyct.sweep.process import hangup_stops_children
from pyct.sweep.result import SweepLimits, SweepResult, SweepStop
from pyct.sweep.rows import Row, Status, covered_and_total
from pyct.sweep.runs import PYCT, run_entry

# the skip reason of an entry the total budget left no time for
SPENT = "the sweep's total budget was spent"


class Mode(Enum):
    """Run each entry, or list the entries and their seeds and run none."""

    RUN = "run"
    LIST = "list"


@dataclass(frozen=True)
class SweepTell:
    """What the sweep says as it goes: ``starting`` before each run, with the run's number and
    how many entries would run, and ``row`` as each row is known, in print order."""

    starting: Callable[[Row, int, int], None] | None = None
    row: Callable[[Row], None] | None = None


@dataclass(frozen=True)
class Programs:
    """The commands that start the lister and ``pyct``, each given its arguments after."""

    lister: tuple[str, ...] = LISTER
    pyct: tuple[str, ...] = PYCT


_DEFAULT_LIMITS = SweepLimits()
_TELL_NOTHING = SweepTell()
_HERE = Programs()


@dataclass
class _Clock:
    """What is left of the total budget, from when the sweep began. None is no bound."""

    total: float | None
    began: float = field(default_factory=time.monotonic)

    def left(self) -> float | None:
        return None if self.total is None else self.total - (time.monotonic() - self.began)


def sweep(
    package: str,
    *,
    limits: SweepLimits = _DEFAULT_LIMITS,
    mode: Mode = Mode.RUN,
    tell: SweepTell = _TELL_NOTHING,
    programs: Programs = _HERE,
) -> SweepResult:
    """Every row of ``package``, each told as it is known, and the summary they make.

    ``package`` is already checked as a module name. Raises
    ``SolverMissingError`` without cvc5 when running, before any row, and
    ``PackageImportError`` when the package itself does not import. A
    Ctrl-C, a SIGTERM, or a SIGHUP stops every process the sweep started.
    """
    clock = _Clock(limits.total_budget)
    with hangup_stops_children():
        cvc5 = None if mode is Mode.LIST else version(locate())
        listed = list_package(package, grace=limits.grace, lister=programs.lister)
        rows = _rows(listed, _Runner(limits, mode, tell, programs, clock))
    covered, total = _summed(rows)
    return SweepResult(package, rows, _stopped(rows, mode), limits, covered, total, cvc5)


@dataclass(frozen=True)
class _Runner:
    """What running one listed entry needs."""

    limits: SweepLimits
    mode: Mode
    tell: SweepTell
    programs: Programs
    clock: _Clock

    def row(self, row: Row, number: int, count: int) -> Row:
        """The row a listed entry ends as: listed, run, or skipped when no time is left."""
        if self.mode is Mode.LIST:
            return row
        left = self.clock.left()
        if left is not None and left <= 0:
            return Row(row.module, row.name, Status.SKIPPED, seed=row.seed, reason=SPENT)
        if self.tell.starting is not None:
            self.tell.starting(row, number, count)
        budget = self.limits.budget if left is None else min(self.limits.budget, left)
        return run_entry(row, self.limits, budget=budget, pyct=self.programs.pyct)


def _rows(listed: tuple[Row, ...], runner: _Runner) -> tuple[Row, ...]:
    """Each row in order, told as soon as it is known, running each listed entry in turn."""
    count = sum(1 for row in listed if row.status is Status.LISTED)
    rows: list[Row] = []
    number = 0
    for row in listed:
        if row.status is Status.LISTED:
            number += 1
            row = runner.row(row, number, count)
        if runner.tell.row is not None:
            runner.tell.row(row)
        rows.append(row)
    return tuple(rows)


def _stopped(rows: tuple[Row, ...], mode: Mode) -> SweepStop:
    if mode is Mode.LIST:
        return SweepStop.LISTED
    if any(row.reason == SPENT for row in rows):
        return SweepStop.TOTAL_BUDGET_SPENT
    return SweepStop.DONE


def _summed(rows: tuple[Row, ...]) -> tuple[Mapping[str, frozenset[int]], Mapping[str, int]]:
    """For each file, every line any entry's run covered, and the line count the runs give."""
    covered: dict[str, set[int]] = {}
    total: dict[str, int] = {}
    for row in rows:
        if row.run is None:
            continue
        lines, counts = covered_and_total(row.run)
        for file, numbers in lines.items():
            covered.setdefault(file, set()).update(numbers)
        for file, number in counts.items():
            total[file] = max(total.get(file, 0), number)
    return {file: frozenset(numbers) for file, numbers in covered.items()}, total
