"""The stuck moment: a run that is stuck works out why each line is still missed, then hands each
LLM tool the entries it takes, in the order summaries, rewrites, guesses.

A run is stuck when 5 inputs in a row cover no new line, or a quarter of
its budget passes with no new line, both counted from after the last seed
and again from after each moment's last input, or when no fork is left to
flip while a line is still missed. A run with no tool switched on, or
none that can still ask, is never stuck, so it runs as it would with no
LLM at all. Decisions llm-one-stuck-moment-for-summaries-rewrites-and-guesses
and llm-stuck-on-time-as-well-as-inputs.

An entry goes first to the tool its cause names (``owner``): a ``no
fork`` entry with a source to summaries, a ``not taken`` entry whose tries
hold a ``timeout`` or an ``unknown`` to rewrites, and a ``no fork`` entry
with no source, a ``handler`` and an ``ended before`` entry to guesses.
Guesses also take the entries of a tool that is switched off, and each
entry an earlier tool gave up on, at this moment or an earlier one, unless
that tool took it at this moment. Every other entry goes to no tool. Decision
llm-guesses-take-a-switched-off-tool-s-lines-and-no-not-taken-line-the-solver-can-reach.
"""

from __future__ import annotations

import enum
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from pyct.binding.bind import Seed
from pyct.branches.plan import Plan
from pyct.config.goal import Goal
from pyct.results.causes import Condition, Reason, WhyEntry
from pyct.results.coverage import Progress, no_gain
from pyct.results.graphs import LONGEST_STRETCH
from pyct.results.record import InputRecord, Source, Stop
from pyct.run.bounds import Bounds
from pyct.run.tell import Ask

# the most moments of a run in which a tool asked the LLM
MOMENTS = 3

# the inputs in a row that cover no new line before a run is stuck
IN_A_ROW = 5

# the share of the budget that passes with no new line before a run is stuck, as 5 inputs in a
# row do: 11.25 s of the 45 s default
STRETCH_SHARE = 0.25

# how long a moment works out the causes of the missed lines, at most
CAUSE_SECONDS = 2.0


class Kind(enum.StrEnum):
    """An LLM tool a moment hands entries to, in the order the moment hands them out."""

    SUMMARIES = "summaries"
    REWRITES = "rewrites"
    GUESSES = "guesses"


class Outcome(enum.StrEnum):
    """What a tool did with one entry at a moment."""

    TOOK = "took"
    GAVE_UP = "gave up"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class Handled:
    """What a tool did with the entries a moment handed it: one outcome per entry, in the order
    handed, and whether it asked the LLM at all."""

    outcomes: tuple[Outcome, ...]
    asked: bool


class Running(Protocol):
    """The run as a moment and its tools see it part way through: its bounds, the inputs so
    far, the stop one of them met, the causes of the lines still missed, an input run between
    two passes, aimed at a plan when one is given, a solver ask a tool made handed out, and the
    clock paused for a wait that is not the run's own work."""

    @property
    def bounds(self) -> Bounds: ...

    @property
    def records(self) -> Sequence[InputRecord]: ...

    @property
    def stopped(self) -> Stop | None: ...

    def causes(self, stop_at: float | None) -> tuple[WhyEntry, ...]: ...

    def run_input(
        self, seed: Seed, source: Source, wanted: Plan | None = None
    ) -> InputRecord | Stop: ...

    def tell_ask(self, ask: Ask) -> None: ...

    def pause(self, seconds: float) -> None: ...


@dataclass(frozen=True)
class Moment:
    """One stuck moment as a tool sees it: its place among the run's moments, from 1, every
    cause the moment worked out, and the run."""

    number: int
    causes: tuple[WhyEntry, ...]
    run: Running


class StuckTool(Protocol):
    """An LLM tool the moment hands entries to. ``take`` returns one outcome per entry;
    ``can_ask`` is false once the tool will ask no more this run, such as when the token limit is
    reached. ``heard`` takes each input the run keeps, with its number in the run, from 1.
    ``waiting`` says whether the tool asks at the moment about something no entry it is handed
    names: it is then handed the moment, with no entry when none is its own."""

    @property
    def kind(self) -> Kind: ...

    @property
    def can_ask(self) -> bool: ...

    def take(self, entries: tuple[WhyEntry, ...], moment: Moment) -> Handled: ...

    def heard(self, record: InputRecord, number: int) -> None: ...

    def waiting(self, moment: Moment) -> bool: ...


# an entry as moments tell it apart: by its file and condition, which stay as they were when
# later inputs leave fewer of its lines missed, or by its file and lines when it has none
type _Key = tuple[str, Condition | tuple[int, ...]]


def owner(entry: WhyEntry) -> Kind | None:
    """The tool an entry's cause names first, or None for a cause no tool takes."""
    if entry.reason is Reason.NOT_TAKEN:
        tries = entry.tries
        return Kind.REWRITES if tries is not None and (tries.timeout or tries.unknown) else None
    if entry.reason is Reason.NO_FORK:
        return Kind.SUMMARIES if entry.sources else Kind.GUESSES
    if entry.reason in (Reason.HANDLER, Reason.ENDED_BEFORE):
        return Kind.GUESSES
    return None


class Stuck:
    """When a run is stuck, and what each moment hands each tool. It keeps the moments' count,
    where the inputs in a row and the stretch with no new line start, and the entries a tool
    gave up on. ``clock`` is the one the run's deadline is read on."""

    def __init__(
        self, tools: Sequence[StuckTool], clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._tools = {tool.kind: tool for tool in tools}
        self._clock = clock
        self._held = 0
        self._asked = 0
        # the inputs the run had when the last moment ended, None before the first
        self._ended: int | None = None
        self._gave_up: set[_Key] = set()
        self._gains = _Gains()
        # where the stretch with no new line starts: the inputs the run had then, and the
        # budget left, None before the first pass after the seeds
        self._mark: tuple[int, float] | None = None

    def due(self, run: Running, progress: Progress, *, empty: bool) -> bool:
        """Whether a moment comes now: a tool that can still ask is on, a moment that asks is
        left, the budget is not spent, a line is still missed and the run would not stop on full
        coverage.

        ``empty`` says no fork is left to flip; a moment then comes when an
        input ran since the last one ended, so one that ran none ends the run.
        Otherwise it comes on 5 inputs in a row with no new line, or on a
        stretch of the budget with no new line (``_stretched``), each counted
        from the last moment's end, or from after the last seed.
        """
        asking = any(tool.can_ask for tool in self._tools.values())
        if not asking or self._asked >= MOMENTS or not _goes_on(run, progress, self._clock()):
            return False
        inputs = len(run.records)
        if empty:
            return self._ended is None or inputs > self._ended
        since = run.bounds.seeds if self._ended is None else self._ended
        in_a_row = inputs - since >= IN_A_ROW and no_gain(progress.covered, IN_A_ROW)
        return in_a_row or self._stretched(run.bounds, progress, since)

    def heard(self, record: InputRecord, number: int) -> None:
        """Tell each tool of an input the run kept as its input ``number``, from 1: a seed's, a
        pass's, or one run between two passes."""
        for tool in self._tools.values():
            tool.heard(record, number)

    def hold(self, run: Running) -> None:
        """Hold one moment: work out the causes, within ``CAUSE_SECONDS`` of now and the run's
        deadline, then hand each tool its entries in turn, until a tool meets the run's stop.
        The moment counts toward ``MOMENTS`` when a tool asked."""
        self._held += 1
        moment = Moment(self._held, run.causes(_cause_stop(run.bounds.until)), run)
        outcomes: dict[_Key, Outcome] = {}
        asked = False
        for kind in Kind:
            tool = self._tools.get(kind)
            if tool is None or run.stopped is not None:
                continue
            entries = tuple(each for each in moment.causes if self._takes(kind, each, outcomes))
            if entries or tool.waiting(moment):
                asked = self._handed(tool, entries, moment, outcomes) or asked
        self._asked += asked
        self._ended = len(run.records)
        left = _left(run.bounds.until, self._clock())
        self._mark = None if left is None else (self._ended, left)

    def _stretched(self, bounds: Bounds, progress: Progress, since: int) -> bool:
        """Whether ``STRETCH_SHARE`` of the budget passed with no new line, since the later of
        ``since`` and the last input that covered one. A run with no budget has no stretch.

        The stretch is read on the deadline, which each wait for the model
        moves later, so the wait does not count. It starts as the next pass
        starts, right after the last seed's input or an input that covered a
        new line ended, or as a moment ends. A pick in flight as it ends runs
        to its end, and the moment comes before the next pick, unless the
        pick's input covered a new line.
        """
        left = _left(bounds.until, self._clock())
        if bounds.budget is None or left is None:
            return False
        start = max(since, self._gains.last(progress.covered))
        if self._mark is None or self._mark[0] < start:
            self._mark = (start, left)
        return self._mark[1] - left >= bounds.budget * STRETCH_SHARE

    def _handed(
        self,
        tool: StuckTool,
        entries: tuple[WhyEntry, ...],
        moment: Moment,
        outcomes: dict[_Key, Outcome],
    ) -> bool:
        """Hand a tool its entries and keep what it did with each. Whether it asked."""
        handled = tool.take(entries, moment)
        for entry, outcome in zip(entries, handled.outcomes, strict=True):
            outcomes[_key(entry)] = outcome
            if outcome is Outcome.GAVE_UP:
                self._gave_up.add(_key(entry))
        return handled.asked

    def _takes(self, kind: Kind, entry: WhyEntry, outcomes: Mapping[_Key, Outcome]) -> bool:
        """Whether ``kind`` takes the entry at this moment, given what the earlier tools did."""
        first = owner(entry)
        if first is None or first is kind:
            return first is kind
        if kind is not Kind.GUESSES:
            return False
        if first not in self._tools:
            return True
        outcome = outcomes.get(_key(entry))
        return outcome is Outcome.GAVE_UP or (
            outcome is Outcome.SKIPPED and _key(entry) in self._gave_up
        )


class _Gains:
    """Which of a run's inputs last covered a line no earlier input had, read as ``no_gain``
    reads them, each input looked at once."""

    def __init__(self) -> None:
        self._looked = 0
        self._seen: set[int] = set()
        self._last = 0

    def last(self, covered: Sequence[frozenset[int]]) -> int:
        """The number, from 1, of the last input in ``covered`` that covered a new line, 0 when
        none did. ``covered`` is the run's, one set per input, which only grows."""
        for lines in covered[self._looked :]:
            self._looked += 1
            if lines - self._seen:
                self._last = self._looked
            self._seen |= lines
        return self._last


def going(run: Running) -> bool:
    """Whether a tool's ask or try may start: the run met no stop and its budget is not spent."""
    until = run.bounds.until
    return run.stopped is None and (until is None or until > time.monotonic())


def _goes_on(run: Running, progress: Progress, now: float) -> bool:
    """Whether the run goes on with a line to win: no stop met, the budget not spent at ``now``,
    a line missed, and not every line and branch covered for the coverage goal."""
    bounds = run.bounds
    if run.stopped is not None or (bounds.until is not None and bounds.until <= now):
        return False
    full = bounds.goal is Goal.COVERAGE and progress.full()
    return progress.missed() and not full


def _left(until: float | None, now: float) -> float | None:
    """The seconds of budget left at ``now``. No deadline, none."""
    return None if until is None else until - now


def _cause_stop(until: float | None) -> float:
    """When a moment starting now stops working out causes: ``CAUSE_SECONDS`` from now, or the
    run's deadline when it comes first, less the stretch the analysis may see its stop late."""
    stop = time.monotonic() + CAUSE_SECONDS
    if until is not None:
        stop = min(stop, until)
    return stop - LONGEST_STRETCH


def _key(entry: WhyEntry) -> _Key:
    return (entry.file, entry.condition if entry.condition is not None else entry.lines)
