"""Why each uncovered line was not run: one cause a line, each cause pointing at one party.

A line the import runs is the import's; a line in a function no input
entered names the function; otherwise the line's way, from ``way``, is
walked in the order the function tests it, and the first place no input
got past names the cause (``README.md › Rules › the summary line``).
"""

from __future__ import annotations

import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum, StrEnum

from pyct.core.branch import Branch, Site
from pyct.results.coverage import compiled
from pyct.results.way import Flow, Step, StepKind, owners


class Reason(StrEnum):
    """Why a line was not run. The values are the words on the summary line."""

    IMPORT = "import"
    NOT_CALLED = "not called"
    NOT_TAKEN = "not taken"
    NO_FORK = "no fork"
    HANDLER = "handler"
    ENDED_BEFORE = "ended before"


@dataclass(frozen=True)
class Tries:
    """What happened each time the run could have flipped the forks at one site."""

    not_tried: int = 0
    unsat: int = 0
    unknown: int = 0
    timeout: int = 0
    left_the_plan: int = 0


@dataclass(frozen=True)
class Condition:
    """A condition on a line's way, by its site, and the side the line needs."""

    site: Site
    side: bool


@dataclass(frozen=True)
class WhyEntry:
    """One cause, and the lines of one file it accounts for, ascending.

    ``function`` is set for ``not called``, ``condition`` for ``not taken``
    and ``no fork``, and ``tries`` for ``not taken``.
    """

    file: str
    lines: tuple[int, ...]
    reason: Reason
    function: str | None = None
    condition: Condition | None = None
    tries: Tries | None = None


@dataclass(frozen=True)
class Walked:
    """One input as the cause reads it: its forks in order, and whether it ended in a failure."""

    forks: tuple[Branch, ...]
    failed: bool


def explain(
    file: str,
    uncovered: frozenset[int],
    covered: frozenset[int],
    walked: Sequence[Walked],
    tries: Mapping[Site, Tries],
) -> tuple[WhyEntry, ...]:
    """One entry per cause, for the lines of ``file`` no input ran, the earliest line's first.

    The module's code is read only when a line is left, so a run that
    covered everything reads nothing.
    """
    if not uncovered:
        return ()
    seen = _Seen.of(file, covered, walked, tries)
    by_cause: dict[WhyEntry, list[int]] = {}
    for line in sorted(uncovered):
        by_cause.setdefault(seen.cause(line), []).append(line)
    entries = [_with_lines(cause, lines) for cause, lines in by_cause.items()]
    return tuple(sorted(entries, key=lambda entry: entry.lines[0]))


def _with_lines(cause: WhyEntry, lines: list[int]) -> WhyEntry:
    return WhyEntry(
        file=cause.file,
        lines=tuple(lines),
        reason=cause.reason,
        function=cause.function,
        condition=cause.condition,
        tries=cause.tries,
    )


@dataclass
class _Seen:
    """What the run showed about one file: its lines, the sides its forks took, and its code."""

    file: str
    covered: frozenset[int]
    taken: dict[tuple[int, int], set[bool]]
    raising: frozenset[tuple[int, int]]
    tries: Mapping[Site, Tries]
    owners: dict[int, types.CodeType | None]
    entered: frozenset[types.CodeType]
    flows: dict[types.CodeType, Flow] = field(default_factory=dict)

    @classmethod
    def of(
        cls,
        file: str,
        covered: frozenset[int],
        walked: Sequence[Walked],
        tries: Mapping[Site, Tries],
    ) -> _Seen:
        taken: dict[tuple[int, int], set[bool]] = {}
        went_on: set[tuple[int, int]] = set()
        for each in walked:
            for at, branch in enumerate(each.forks):
                if branch.site.file != file:
                    continue
                position = (branch.site.line, branch.site.col)
                taken.setdefault(position, set()).add(branch.taken)
                last = at == len(each.forks) - 1
                if not branch.taken and not (last and each.failed):
                    went_on.add(position)
        # a fork an input went on past on its false side was a truth test, not an operation
        # that raised there
        raising = frozenset(taken) - went_on
        held = _owners(file)
        entered = frozenset(code for line, code in held.items() if code and line in covered)
        return cls(file, covered, taken, raising, tries, held, entered)

    def cause(self, line: int) -> WhyEntry:
        """The one cause of an uncovered line. A line no function holds is the import's."""
        code = self.owners.get(line)
        if code is None:
            return WhyEntry(file=self.file, lines=(), reason=Reason.IMPORT)
        if code not in self.entered:
            return WhyEntry(self.file, (), Reason.NOT_CALLED, function=code.co_qualname)
        return self._on_the_way(self._flow(code), line)

    def _flow(self, code: types.CodeType) -> Flow:
        if code not in self.flows:
            self.flows[code] = Flow(code, self.raising)
        return self.flows[code]

    def _on_the_way(self, flow: Flow, line: int) -> WhyEntry:
        """The first step on the line's way no input got past, or why none stopped them."""
        entered_a_handler = False
        for step in flow.way(line):
            if step.kind is StepKind.HANDLER:
                if not self._reached(step.reaches):
                    return WhyEntry(self.file, (), Reason.HANDLER)
                entered_a_handler = True
                continue
            verdict = self._judged(step)
            if verdict is _Verdict.PASSED:
                continue
            if verdict is _Verdict.UNREACHED:
                break
            return verdict
        if flow.only_in_handlers(line) and not entered_a_handler:
            return WhyEntry(self.file, (), Reason.HANDLER)
        return WhyEntry(self.file, (), Reason.ENDED_BEFORE)

    def _judged(self, step: Step) -> WhyEntry | _Verdict:
        """Whether a run got past a condition's side, or the cause when none did."""
        site = Site(file=self.file, line=step.line, col=step.col)
        condition = Condition(site=site, side=step.side)
        sides = self.taken.get((step.line, step.col))
        if sides is not None:
            if step.side in sides:
                return _Verdict.PASSED
            tries = self.tries.get(site, Tries())
            return WhyEntry(self.file, (), Reason.NOT_TAKEN, condition=condition, tries=tries)
        if step.line not in self.covered:
            return _Verdict.UNREACHED
        if self._reached(step.reaches):
            return _Verdict.PASSED
        return WhyEntry(self.file, (), Reason.NO_FORK, condition=condition)

    def _reached(self, line: int | None) -> bool:
        """Whether a run reached ``line``. None is a side that stays on its step's line."""
        return line is None or line in self.covered


def _owners(file: str) -> dict[int, types.CodeType | None]:
    """Each line's code, from the module as it reads now.

    A module that no longer reads, such as one deleted during the run,
    places no line in a function, so each of its lines is the import's: no
    call is known to hold it.
    """
    try:
        return owners(compiled(file))
    except (OSError, SyntaxError, ValueError):
        return {}


class _Verdict(Enum):
    """A step's verdict that names no cause: a run got past it, or no run reached it."""

    PASSED = "passed"
    UNREACHED = "unreached"
