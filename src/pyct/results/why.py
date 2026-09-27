"""Why each uncovered line was not run: one cause a line, each cause pointing at one party.

A line the import runs is the import's; a line in a function no input
entered names the function; otherwise the line's way, from ``way``, is
walked in the order the function tests it, and the first place no input
got past names the cause (``README.md › Rules › the summary line``).
"""

from __future__ import annotations

import functools
import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from pyct.core.branch import Branch, ForkSite, Site
from pyct.results.coverage import compiled
from pyct.results.way import Flow, Fork, Step, StepKind, owners


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
    """One input as the cause reads it: its forks in order, whether it ended in a failure,
    and the lines it covered."""

    forks: tuple[Branch, ...]
    failed: bool
    lines: frozenset[int] = frozenset()


def explain(
    file: str,
    uncovered: frozenset[int],
    covered: frozenset[int],
    walked: Sequence[Walked],
    tries: Mapping[ForkSite, Tries],
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


@dataclass(frozen=True)
class _Input:
    """One input as a file's flow reads it: its lines, its forks there, and how it ended."""

    lines: frozenset[int]
    forks: tuple[Fork, ...]
    failed: bool


@dataclass
class _Seen:
    """What the run showed about one file: its lines, its inputs' forks, and its code."""

    file: str
    covered: frozenset[int]
    inputs: tuple[_Input, ...]
    tries: Mapping[ForkSite, Tries]
    owners: dict[int, types.CodeType | None]
    flows: dict[types.CodeType, _Walk] = field(default_factory=dict)

    @classmethod
    def of(
        cls,
        file: str,
        covered: frozenset[int],
        walked: Sequence[Walked],
        tries: Mapping[ForkSite, Tries],
    ) -> _Seen:
        inputs = tuple(
            _Input(
                each.lines,
                tuple(_fork(branch) for branch in each.forks if branch.site.file == file),
                each.failed,
            )
            for each in walked
        )
        return cls(file, covered, inputs, tries, _owners(file))

    def cause(self, line: int) -> WhyEntry:
        """The one cause of an uncovered line. A line no function holds is the import's."""
        code = self.owners.get(line)
        if code is None:
            return WhyEntry(file=self.file, lines=(), reason=Reason.IMPORT)
        if not any(owner is code and at in self.covered for at, owner in self.owners.items()):
            return WhyEntry(self.file, (), Reason.NOT_CALLED, function=code.co_qualname)
        if code not in self.flows:
            self.flows[code] = _Walk.of(self, code)
        return self.flows[code].cause(line)


def _fork(branch: Branch) -> Fork:
    return (branch.site.line, branch.site.col, branch.taken, branch.raising)


@dataclass
class _Walk:
    """One function's flow, and the nodes the run's lines and forks prove some input passed."""

    seen: _Seen
    flow: Flow
    passed: frozenset[int]
    forked: frozenset[tuple[int, int, bool]]

    @classmethod
    def of(cls, seen: _Seen, code: types.CodeType) -> _Walk:
        forks = [fork for each in seen.inputs for fork in each.forks]
        raising = frozenset((line, col) for line, col, _, is_raising in forks if is_raising)
        flow = Flow(code, raising)
        passed = flow.marked(seen.covered, forks)
        forked = frozenset((line, col, is_raising) for line, col, _, is_raising in forks)
        return cls(seen, flow, passed, forked)

    def cause(self, line: int) -> WhyEntry:
        """The first place on the line's way no input got past, else the first reaching side
        no input took, else a handler no raise reached, else the inputs that ended before it."""
        found = self._on_the_way(line) or self._reaching(line, shown=True)
        if found is not None:
            return found
        if self._no_raise_reached(line):
            return self._entry(Reason.HANDLER)
        if self._ended(line):
            return self._entry(Reason.ENDED_BEFORE)
        # a side that joins again at once, as a ternary's, shows no run took it, so it is named
        # only when nothing else explains the line
        found = self._reaching(line, shown=False)
        # otherwise no condition leads to the line and no input ended on the way: the run
        # shows nothing more, and the line is put down to its inputs ending before it
        return found or self._entry(Reason.ENDED_BEFORE)

    def _no_raise_reached(self, line: int) -> bool:
        """Whether the line is in an except block that no raise on its way reached."""
        places = self.flow.places(line)
        into = [place for place in places if place.step.kind is StepKind.HANDLER]
        return self.flow.only_in_handlers(line) and any(p.node not in self.passed for p in into)

    def _on_the_way(self, line: int) -> WhyEntry | None:
        for place in self.flow.places(line):
            if place.node in self.passed:
                continue
            if place.source not in self.passed:
                return None
            if place.step.kind is StepKind.HANDLER:
                return self._entry(Reason.HANDLER)
            return self._named(place.step)
        return None

    def _reaching(self, line: int, *, shown: bool) -> WhyEntry | None:
        """The first reaching side no input took, of a condition an input reached.

        ``shown`` asks only for a side a run would show it took, by a fork or
        by a line or a fork only that side leads to.
        """
        for place in self.flow.reaching(line):
            if place.node in self.passed or place.source not in self.passed:
                continue
            knowable = self._forks_at(place.step) or self.flow.knowable(place)
            if knowable == shown:
                return self._named(place.step)
        return None

    def _ended(self, line: int) -> bool:
        """Whether an input that went as far toward the line as any did ended there.

        It failed, or a raise took it into a handler from which the line
        cannot be reached.
        """
        chain = [node for node in self.flow.chain(line) if node in self.passed]
        frontier = chain[-1] if chain else None
        away = self.flow.raises() - self.flow.toward(line)
        for each, marked in zip(self.seen.inputs, self._marks, strict=True):
            if frontier is not None and frontier not in marked:
                continue
            if each.failed or marked & away:
                return True
        return False

    @functools.cached_property
    def _marks(self) -> list[frozenset[int]]:
        """The nodes each input's own lines and forks prove it passed, found once."""
        return [self.flow.marked(each.lines, each.forks) for each in self.seen.inputs]

    def _forks_at(self, step: Step) -> bool:
        return (step.line, step.col, step.raising) in self.forked

    def _named(self, step: Step) -> WhyEntry:
        """A condition no input took the side of: not taken when it forked there, else no fork."""
        site = Site(file=self.seen.file, line=step.line, col=step.col)
        condition = Condition(site=site, side=step.side)
        if not self._forks_at(step):
            return WhyEntry(self.seen.file, (), Reason.NO_FORK, condition=condition)
        tries = self.seen.tries.get(ForkSite(site, step.raising), Tries())
        return WhyEntry(self.seen.file, (), Reason.NOT_TAKEN, condition=condition, tries=tries)

    def _entry(self, reason: Reason) -> WhyEntry:
        return WhyEntry(self.seen.file, (), reason)


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
