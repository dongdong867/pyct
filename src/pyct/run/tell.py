"""What a caller hears of a run the moment each fact of it happens."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pyct.results.coverage import Coverage, Scope
from pyct.results.record import Aim, InputRecord, Miss
from pyct.solver.given import Given

# what a caller does with an input the moment it is finished
type Report = Callable[[InputRecord, Coverage], None]

# what a caller does with a fork the solver could not flip, the moment the answer comes in
type Missed = Callable[[Miss], None]


@dataclass(frozen=True)
class Ask:
    """One ask of the solver: its number among the run's asks, from 1, the fork aimed at, the
    input whose path it extends by that input's place among the run's inputs, the seed's 0, and
    each program pyct gave cvc5 for it, in order."""

    number: int
    aim: Aim
    path: int
    programs: tuple[Given, ...]


# what a caller does with each ask the moment its answer comes in
type Asked = Callable[[Ask], None]


@dataclass(frozen=True)
class Tell:
    """What a caller does with each fact of the run the moment it happens.

    ``report`` takes each finished input with the lines that input alone
    covered; ``missed`` takes each fork the solver gave no input for;
    ``asked`` takes each ask with the programs pyct gave cvc5. One object
    rather than a keyword per kind of fact, so ``run()`` and the loop keep
    to five parameters: a later kind of fact widens this instead of their
    signatures. A Tell with nothing set hands nothing out.
    """

    report: Report | None = None
    missed: Missed | None = None
    asked: Asked | None = None


@dataclass(frozen=True)
class Told:
    """The caller's Tell, with the scope each reported input's coverage is measured in, and the
    lines the target's import ran, which the stop on full coverage counts as covered."""

    scope: Scope
    tell: Tell
    imported: frozenset[int] = frozenset()

    def record(self, record: InputRecord) -> None:
        """Hand out a finished input, with the lines that one input covered."""
        if self.tell.report is not None:
            self.tell.report(record, Coverage.of(self.scope, record.covered_lines))

    def miss(self, miss: Miss) -> None:
        """Hand out a fork the solver gave no input for."""
        if self.tell.missed is not None:
            self.tell.missed(miss)

    def ask(self, ask: Ask) -> None:
        """Hand out an ask once its answer is in."""
        if self.tell.asked is not None:
            self.tell.asked(ask)
