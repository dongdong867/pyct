"""Why each uncovered line was not run: one cause a line, each cause pointing at one party.

A line the import runs is the import's; a line in a function no input
entered names the function; otherwise the line's way, from ``way``, is
walked in the order the function tests it, and the first place no input
got past names the cause (``README.md › Rules › the summary line``).
"""

from __future__ import annotations

import contextlib
import functools
import logging
import time
import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from pyct.core.branch import Branch, ForkSite, Site
from pyct.results.blocks import owners
from pyct.results.coverage import compiled
from pyct.results.graphs import OutOfTimeError, Pace, UnaffordableError
from pyct.results.senses import At, against_the_forks, heads_of
from pyct.results.way import Flow, Fork, Place, Step, StepKind

logger = logging.getLogger(__name__)

# what pyct logs for a line no cause explains; a run should never say it
UNEXPLAINED = "no cause explains line %d of %s; it is put down as ended before"


class Reason(StrEnum):
    """Why a line was not run. The values are the words on the summary line."""

    IMPORT = "import"
    NOT_CALLED = "not called"
    NOT_TAKEN = "not taken"
    NO_FORK = "no fork"
    HANDLER = "handler"
    ENDED_BEFORE = "ended before"
    SUSPENDED = "suspended"
    NOT_WORKED_OUT = "not worked out"


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
    and ``no fork``, ``tries`` for ``not taken``, and ``at_yield``, the line
    of the ``yield`` the function was left at, for ``suspended``.
    """

    file: str
    lines: tuple[int, ...]
    reason: Reason
    function: str | None = None
    condition: Condition | None = None
    tries: Tries | None = None
    at_yield: int | None = None


@dataclass(frozen=True)
class Walked:
    """One input as the cause reads it: its forks in order, whether it ended in a failure,
    and the lines it covered."""

    forks: tuple[Branch, ...]
    failed: bool
    lines: frozenset[int] = frozenset()


# what the analysis reads the time from; a test sets another
clock = time.monotonic


@dataclass(frozen=True)
class Run:
    """What the run gave the analysis: its inputs, what it tried at each site, and when to stop.

    ``stop_at`` is the monotonic instant past which no more causes are
    worked out, or None for a run with no deadline, which works out every line.
    """

    walked: Sequence[Walked]
    tries: Mapping[ForkSite, Tries]
    stop_at: float | None = None

    def late(self, ahead: float = 0.0) -> bool:
        """Whether the stop comes within ``ahead`` seconds, or has come."""
        return self.stop_at is not None and clock() + ahead > self.stop_at


def explain(
    file: str, uncovered: frozenset[int], covered: frozenset[int], run: Run
) -> tuple[WhyEntry, ...]:
    """One entry per cause, for the lines of ``file`` no input ran, the earliest line's first.

    The module's code is read only when a line is left, so a run that
    covered everything reads nothing. The lines left when the run's stop
    comes share one ``not worked out`` entry.
    """
    if not uncovered:
        return ()
    lines = sorted(uncovered)
    by_cause: dict[WhyEntry, list[int]] = {}
    with contextlib.suppress(OutOfTimeError):
        _work_out(file, lines, covered, run, by_cause)
    # a line is placed once its cause is known; whatever the stop left is not worked out
    placed = {line for held in by_cause.values() for line in held}
    left = [line for line in lines if line not in placed]
    if left:
        by_cause[WhyEntry(file, (), Reason.NOT_WORKED_OUT)] = left
    entries = [_with_lines(cause, held) for cause, held in by_cause.items() if held]
    return tuple(sorted(entries, key=lambda entry: entry.lines[0]))


def _work_out(
    file: str,
    lines: list[int],
    covered: frozenset[int],
    run: Run,
    by_cause: dict[WhyEntry, list[int]],
) -> None:
    """Work out each line's cause into ``by_cause``, until the stop comes.

    The stop comes as ``OutOfTimeError``, raised only where the analysis
    looks at its clock: before each line, at each step of a walk whose work
    grows with the function, the lines or the inputs (``graphs.Pace``), and
    before dis's label pass, which no step can break into.
    """
    # reading every input's forks grows with the inputs, and past the stop no line is worked out
    if run.late():
        raise OutOfTimeError
    seen = _Seen.of(file, covered, run)
    for line in lines:
        if run.late():
            raise OutOfTimeError
        cause = seen.cause(line)
        if cause is not None:
            by_cause.setdefault(cause, []).append(line)


def _with_lines(cause: WhyEntry, lines: list[int]) -> WhyEntry:
    return WhyEntry(
        file=cause.file,
        lines=tuple(lines),
        reason=cause.reason,
        function=cause.function,
        condition=cause.condition,
        tries=cause.tries,
        at_yield=cause.at_yield,
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
    run: Run
    owners: dict[int, types.CodeType | None]
    # the operator of each fork recorded at each site, raising forks aside (`senses.heads_of`)
    heads: dict[At, frozenset[str]]
    # keyed by the code's id: a large function's code is slow to hash, and `owners` keeps each
    # one alive for as long as this is
    flows: dict[int, _Walk] = field(default_factory=dict)
    # the ids of the functions too large to read before the stop
    left: set[int] = field(default_factory=set)

    @classmethod
    def of(cls, file: str, covered: frozenset[int], run: Run) -> _Seen:
        # inputs that took one path are one input to every question asked of them; a step an
        # input and a fork, since one input may hold many
        pace = Pace(run.late)
        inputs = tuple(
            dict.fromkeys(
                _Input(
                    each.lines,
                    tuple(
                        _fork(branch)
                        for branch in pace.each(each.forks)
                        if branch.site.file == file
                    ),
                    each.failed,
                )
                for each in pace.each(run.walked)
            )
        )
        heads = heads_of(
            ((branch.site.line, branch.site.col), branch.expression)
            for each in pace.each(run.walked)
            for branch in pace.each(each.forks)
            if branch.site.file == file and not branch.raising
        )
        return cls(file, covered, inputs, run, _owners(file), heads)

    @functools.cached_property
    def _called(self) -> frozenset[int]:
        """The ids of the functions a covered line of which ran."""
        return frozenset(id(self.owners.get(line)) for line in self.covered)

    def cause(self, line: int) -> WhyEntry | None:
        """The one cause of an uncovered line. A line no function holds is the import's.

        None for a line of a function too large to read before the stop: it
        stays unplaced, so it is not worked out, and the next line goes on.
        """
        code = self.owners.get(line)
        if code is None:
            return WhyEntry(file=self.file, lines=(), reason=Reason.IMPORT)
        if id(code) not in self._called:
            return WhyEntry(self.file, (), Reason.NOT_CALLED, function=code.co_qualname)
        if id(code) in self.left:
            return None
        if id(code) not in self.flows:
            try:
                self.flows[id(code)] = _Walk.of(self, code)
            except UnaffordableError:
                self.left.add(id(code))
                return None
        return self.flows[id(code)].cause_of(line)


def _fork(branch: Branch) -> Fork:
    return (branch.site.line, branch.site.col, branch.taken, branch.raising)


@dataclass
class _Walk:
    """One function's flow, and the nodes the run's lines and forks prove some input passed."""

    seen: _Seen
    flow: Flow
    passed: frozenset[int]
    forked: frozenset[tuple[int, int, bool]]
    causes: dict[tuple[int, ...], WhyEntry] = field(default_factory=dict)
    _lasts: dict[tuple[frozenset[int], tuple[int, ...]], list[int]] = field(default_factory=dict)

    @classmethod
    def of(cls, seen: _Seen, code: types.CodeType) -> _Walk:
        each = Pace(seen.run.late).each
        forks = [fork for one in each(seen.inputs) for fork in one.forks]
        raising = frozenset((line, col) for line, col, _, is_raising in each(forks) if is_raising)
        flow = Flow(code, raising, late=seen.run.late)
        # each `in` and `is` test's sides read as the forks recorded there, before any is marked
        flow.swap(against_the_forks(flow, seen.heads, [(i.lines, i.forks) for i in seen.inputs]))
        passed = flow.marked(seen.covered, forks)
        forked = frozenset((line, col, is_raising) for line, col, _, is_raising in each(forks))
        return cls(seen, flow, passed, forked)

    def cause_of(self, line: int) -> WhyEntry:
        """The line's cause, found once for every line along one straight run."""
        run = self.flow.run_of(line)
        if run not in self.causes:
            self.causes[run] = self.cause(line)
        return self.causes[run]

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
        at_yield = self._suspended(line)
        if at_yield is not None:
            return WhyEntry(self.seen.file, (), Reason.SUSPENDED, at_yield=at_yield)
        # no input ended, so the line waits on a condition the run cannot show a side of, as a
        # ternary's, which joins again at once: the first such on the way, else reaching it
        return self._first_unshown(line)

    def _no_raise_reached(self, line: int) -> bool:
        """Whether the line is in an except block that no raise on its way reached."""
        places = self.flow.places(line)
        into = [place for place in places if place.step.kind is StepKind.HANDLER]
        return self.flow.only_in_handlers(line) and any(p.node not in self.passed for p in into)

    def _first_unshown(self, line: int) -> WhyEntry:
        """The first condition on the way no run shows it passed, else the first reaching side.

        What is left when no side is shown untaken and no input ended: never
        ``ended before``, which needs an input that ended.
        """
        conditions = [p for p in self.flow.places(line) if p.step.kind is StepKind.CONDITION]
        unshown = [p for p in conditions if p.node not in self.passed]
        reaching = [p for p in self.flow.reaching(line) if p.node not in self.passed]
        place = next(iter([*unshown, *reaching, *conditions]), None)
        if place is None:
            # no condition leads to the line, and no input ended or was suspended on the way,
            # so every input ran the line: the run's facts contradict each other
            logger.warning(UNEXPLAINED, line, self.seen.file)
            return self._entry(Reason.ENDED_BEFORE)
        return self._named(place.step)

    def _suspended(self, line: int) -> int | None:
        """The line of the yield an input was left at on its way to the line, if one was.

        The input did not end, and the last line it ran toward the line holds a
        yield: its frame stopped there and never came back, because its caller
        stopped asking for values.
        """
        yields = self.flow.yield_lines()
        found = [
            last
            for each in self.seen.inputs
            if not each.failed
            for last in self._last_lines(each, line)
            if last in yields
        ]
        return max(found, default=None)

    def _raised_out(self, line: int) -> bool:
        """Whether an input's frame left the function by a raise its caller caught.

        The input did not fail, and the last line it ran toward the line goes on
        to the line with no condition between: only a raise out of the frame, or
        a yield it stayed at, kept it from the line.
        """
        yields = self.flow.yield_lines()
        return any(
            True
            for each in self.seen.inputs
            if not each.failed
            for last in self._last_lines(each, line)
            if last not in yields and self.flow.straight(last, line)
        )

    def _last_lines(self, each: _Input, line: int) -> list[int]:
        """The lines an input ran toward the line that no later line it ran came after.

        Asked once per input by ``_suspended`` and ``_raised_out``, so it checks
        the stop: the loop grows with the inputs.
        """
        if self.seen.run.late():
            raise OutOfTimeError
        ran = each.lines & self.flow.reaching_lines(line)
        key = (ran, self.flow.run_of(line))
        if key not in self._lasts:
            self._lasts[key] = sorted(self.flow.last_among(ran))
        return self._lasts[key]

    def _frontier(self, line: int) -> int | None:
        """The deepest node on the line's way some input is shown to have passed."""
        chain = [node for node in self.flow.chain(line) if node in self.passed]
        return chain[-1] if chain else None

    def _reached(self, place: Place) -> bool:
        """Whether an input reached a condition: its block ran, or a fork was recorded there.

        Two tests can share one site, as ``x < 5 < x`` does; a fork there proves
        only what both share, so the fork itself says the second test ran.
        """
        return place.source in self.passed or self._forks_at(place.step)

    def _on_the_way(self, line: int) -> WhyEntry | None:
        for place in self.flow.places(line):
            if place.node in self.passed:
                continue
            if not self._reached(place):
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
            if place.node in self.passed or not self._reached(place):
                continue
            knowable = self._forks_at(place.step) or self.flow.knowable(place)
            if knowable == shown:
                return self._named(place.step)
        return None

    def _ended(self, line: int) -> bool:
        """Whether an input that went as far toward the line as any did ended there.

        It failed, or it raised on the way to the line, even when the function
        caught the raise and went on: a raise entered from a block the line can
        still be reached from, or a raise out of the frame its caller caught.
        """
        frontier = self._frontier(line)
        away = self.flow.raises_toward(line)
        for each, marked in zip(self.seen.inputs, self._marks, strict=True):
            if frontier is not None and frontier not in marked:
                continue
            if each.failed or marked & away:
                return True
        return self._raised_out(line)

    @functools.cached_property
    def _marks(self) -> list[frozenset[int]]:
        """The nodes each input's own lines and forks prove it passed, found once."""
        marks = []
        for each in self.seen.inputs:
            # a step per input: the loop grows with the run's inputs
            if self.seen.run.late():
                raise OutOfTimeError
            marks.append(self.flow.marked(each.lines, each.forks))
        return marks

    def _forks_at(self, step: Step) -> bool:
        return (step.line, step.col, step.raising) in self.forked

    def _named(self, step: Step) -> WhyEntry:
        """A condition no input took the side of: not taken when it forked there, else no fork."""
        site = Site(file=self.seen.file, line=step.line, col=step.col)
        condition = Condition(site=site, side=step.side)
        if not self._forks_at(step):
            return WhyEntry(self.seen.file, (), Reason.NO_FORK, condition=condition)
        tries = self.seen.run.tries.get(ForkSite(site, step.raising), Tries())
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
