"""The run's loop: each seed, then an input per fork the inputs left open, until a pass stops it."""

from __future__ import annotations

import dataclasses
import itertools
import time
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.branches.plan import Plan
from pyct.branches.tree import Tree
from pyct.config.goal import Goal
from pyct.core.foundation.branch import ForkSite
from pyct.execution.execute import ExecutionResult
from pyct.results.causes import WhyEntry
from pyct.results.coverage import Coverage, Progress, no_gain
from pyct.results.record import InputRecord, Miss, Source, Stop, StopKind, why_uncovered
from pyct.run.bounds import Bounds
from pyct.run.collector import collector_paused
from pyct.run.isolation import Call
from pyct.run.process import InputStartError
from pyct.run.records import miss_why, record_of
from pyct.run.stuck import Stuck
from pyct.run.tell import Ask, Told
from pyct.solver.answer import Answer, Error, Sat, Timeout
from pyct.solver.cvc5 import solve
from pyct.solver.given import taking

_NO_FORK = Stop(StopKind.NO_FORK)


@dataclass(frozen=True)
class Start:
    """A seed copied for the loop, and where it came from: the user or the LLM."""

    copy: Seed
    source: Source = Source.SEED


@dataclass(frozen=True)
class Ran:
    """An input that ran: its record, and its arguments as the walk copied them, which a later
    answer on its path starts from."""

    record: InputRecord
    seed: Seed


@dataclass(frozen=True)
class Attempt:
    """What one pass of the loop produced: an input, or a miss, or the reason to stop.

    ``unrun`` is the site of a fork the pass picked and then stopped before it
    ran an input for: the pick spends the fork, so only the pass knows it.
    ``asked`` is the pass's ask of the solver, numbered by the loop.
    """

    stop: Stop | None = None
    ran: Ran | None = None
    miss: Miss | None = None
    unrun: ForkSite | None = None
    asked: Ask | None = None

    @property
    def record(self) -> InputRecord | None:
        """The record of the input that ran, if one did."""
        return None if self.ran is None else self.ran.record


@dataclass(frozen=True)
class Looped:
    """The inputs that ran, the seeds' first, what the solver missed, and why they stopped.

    ``untried`` counts the forks the run never tried at each site.
    """

    records: tuple[InputRecord, ...]
    misses: tuple[Miss, ...]
    stop: Stop
    untried: Mapping[ForkSite, int] = field(default_factory=dict)


class Loop:
    """One run's loop and what it holds between passes: the inputs that ran, the misses, the
    tree, the progress, each input's copy by its path's number, and the bounds.

    Every input's forks join the tree the next pick draws from, so an input
    that raised or left its plan feeds the loop like any other. A miss is
    kept, handed out before the next pick, and the loop goes on: the fork is
    spent either way.

    ``progress`` holds the lines of each input that ran, in run order, the
    seeds' first, and what each reached; a miss ran no input and adds none.
    It applies the scope, because a record carries the tracer's raw lines.
    Each ask is handed out, numbered, the moment its answer is in.

    ``bounds`` is the one place the loop reads its deadline from, for each
    input and each solve; ``pause`` moves it later. ``stuck`` says when the
    run is stuck, and holds each moment between two passes (``pyct.run.stuck``);
    with no tool in it the run is never stuck.
    """

    def __init__(self, call: Call, bounds: Bounds, told: Told, stuck: Stuck | None = None) -> None:
        self.bounds = bounds
        self.told = told
        self.records: list[InputRecord] = []
        self.misses: list[Miss] = []
        self.progress = Progress(told.scope, told.imported)
        self.tree = Tree()
        # each input as the walk copied it, by its path's number: a solver answer starts from the
        # input whose path it extends, not from the seed (see ``Plan.path``)
        self.inputs: dict[int, Seed] = {}
        self._call = call
        self._numbers = itertools.count(1)
        self._stopped: Stop | None = None
        self._stuck = Stuck(()) if stuck is None else stuck

    def go(self, starts: Sequence[Start]) -> Looped:
        """Run each seed, the first before any check, then pick a fork and run what the solver
        answers for it, until a pass says to stop.

        A first seed whose process cannot start stops the run before any input.
        Each seed is copied, and its leaves noted, before the first seed runs.
        Every input, each seed's too, calls the target with ``bind``'s rebuild of
        its copy, so no input changes the leaves the solver reads or the copies
        a later input starts from.
        """
        first = starts[0]
        try:
            seeded = _from(first, self._call(first.copy.args, self.bounds.until))
        except InputStartError as error:
            return Looped((), (), _could_not_start(error))
        self._keep(seeded, first.copy)
        waiting = deque(starts[1:])
        while True:
            _let_go(self.inputs, self.tree.oldest)
            attempt = self._next(waiting)
            _hand_out(attempt, self.told, self._numbers, self.misses)
            if attempt.stop is not None:
                return Looped(
                    tuple(self.records), tuple(self.misses), attempt.stop, self._untried(attempt)
                )
            if attempt.ran is not None:
                self._keep(attempt.ran.record, attempt.ran.seed)

    def run_input(self, seed: Seed, source: Source) -> InputRecord | Stop:
        """Run one input between two passes, labeled ``source``, and keep it as the loop keeps
        every input: measured, handed out, its path added to the tree, its copy kept.

        The budget, then full coverage, stop it before it runs, as they stop a
        solver input; so does an input pyct could not start a process for.
        The plateau does not: a waiting seed runs before the plateau counts,
        and a stuck moment's input is the run's answer to its inputs gaining
        nothing. A stop is kept, and the next pass hands it out; once it is
        kept, no input runs.
        """
        stop = self._stopped or _spent_or_covered(self.bounds, self.progress)
        if stop is None:
            try:
                executed = self._call(seed.args, self.bounds.until)
            except InputStartError as error:
                stop = _could_not_start(error)
            else:
                return self._keep(_labeled(record_of(seed.args, executed), source), seed)
        self._stopped = stop
        return stop

    @property
    def stopped(self) -> Stop | None:
        """The stop an input run between two passes met, which ends the run at the next pass."""
        return self._stopped

    def causes(self, stop_at: float | None) -> tuple[WhyEntry, ...]:
        """Why each line is still missed, from the inputs so far, worked out until ``stop_at``.
        The forks still open count as never tried."""
        with collector_paused():
            untried = self.tree.untried()
        covered = frozenset[int]().union(*(record.covered_lines for record in self.records))
        coverage = Coverage.of(self.told.scope, covered | self.told.imported)
        return why_uncovered(self.records, self.misses, untried, coverage, stop_at)

    def pause(self, seconds: float) -> None:
        """Move the deadline ``seconds`` later: the clock paused for a wait that is not the run's
        own work, such as the LLM's answer."""
        self.bounds = self.bounds.paused(seconds)

    def _next(self, waiting: deque[Start]) -> Attempt:
        """The next pass: the next seed still waiting, or a stuck moment, or a fork to aim at.

        A moment comes before the pick on 5 inputs in a row with no new line,
        and in place of the stop when no fork is left to flip; ``no fork to
        flip`` comes before the pick spends a fork, so the next pass picks
        from what the moment's inputs added.
        """
        if self._stopped is not None:
            return Attempt(stop=self._stopped)
        if waiting:
            start = waiting.popleft()
            return _stopped_by(self.run_input(start.copy, start.source))
        if self._stuck.due(self, self.progress, empty=False):
            return self._moment()
        attempt = _attempt(self._call, self.inputs, self.tree, self.bounds, self.progress)
        if attempt.stop == _NO_FORK and self._stuck.due(self, self.progress, empty=True):
            return self._moment()
        return attempt

    def _moment(self) -> Attempt:
        """Hold a stuck moment; the pass stops the run when an input the moment ran met a stop."""
        self._stuck.hold(self)
        return Attempt(stop=self._stopped)

    def _keep(self, record: InputRecord, seed: Seed) -> InputRecord:
        """Measure an input, hand it out, add its path, and keep its copy under its number."""
        self.inputs[len(self.records)] = seed
        kept = _took(record, self.told, self.tree, self.progress)
        self.records.append(kept)
        return kept

    def _untried(self, attempt: Attempt) -> dict[ForkSite, int]:
        """How many forks the run never tried at each site: the open ones, and one picked but not
        run. Counted with the collector paused, as each input's path was added."""
        with collector_paused():
            counts = self.tree.untried()
        if attempt.unrun is not None:
            counts[attempt.unrun] = counts.get(attempt.unrun, 0) + 1
        return counts


def _stopped_by(ran: InputRecord | Stop) -> Attempt:
    """The pass of an input already kept: nothing more, or the stop it met."""
    return Attempt(stop=ran) if isinstance(ran, Stop) else Attempt()


def _from(start: Start, executed: ExecutionResult) -> InputRecord:
    """The record of a seed's input, labeled with where the seed came from."""
    return _labeled(record_of(start.copy.args, executed), start.source)


def _labeled(record: InputRecord, source: Source) -> InputRecord:
    """The record, labeled with where its input came from."""
    return dataclasses.replace(record, source=source)


def _could_not_start(error: InputStartError) -> Stop:
    """The stop for an input pyct could not start a process for, with the system's reason."""
    return Stop(StopKind.COULD_NOT_START, str(error))


def _hand_out(attempt: Attempt, told: Told, numbers: Iterator[int], misses: list[Miss]) -> None:
    """Hand out the pass's ask, numbered, and its miss, which the run keeps. A pass that stops
    has no miss."""
    if attempt.asked is not None:
        told.ask(dataclasses.replace(attempt.asked, number=next(numbers)))
    if attempt.miss is not None:
        misses.append(attempt.miss)
        told.miss(attempt.miss)


def _took(record: InputRecord, told: Told, tree: Tree, progress: Progress) -> InputRecord:
    """Measure an input, hand it out and add its path, then turn the path its pick
    extended when the input left the plan and covered no line no earlier input had.

    Such an input likely left on what the solver does not model, as a
    cache that compares keys only on equal hashes, and the deeper forks of
    that path sit on more of it, so the rest of the path's new sides go
    shallowest first (`Tree.turn`). How the input ended does not matter.
    An input that left and covered a new line turns nothing, and a seed
    follows no plan. Decision
    fork-order-shallowest-first-after-a-leave-without-gain.
    """
    record = _measured(record, progress)
    _handled(record, told, tree)
    if record.mismatch_at is not None and no_gain(progress.covered, 1):
        tree.turn()
    return record


def _measured(record: InputRecord, progress: Progress) -> InputRecord:
    """The record, with the lines it covered first, once the run's progress has added it."""
    first = progress.add(record.covered_lines, record.reach)
    return dataclasses.replace(record, first_covered=first)


def _handled(record: InputRecord, told: Told, tree: Tree) -> None:
    """Hand out a finished input, then add its path to the tree, with the collector paused."""
    with collector_paused():
        told.record(record)
        tree.add(record.forks, record.facts)


def _attempt(
    call: Call,
    inputs: Mapping[int, Seed],
    tree: Tree,
    bounds: Bounds,
    progress: Progress,
) -> Attempt:
    """One pass of the loop: the clock, a fork to aim at, the coverage, the plateau, the solver,
    the input.

    The four reasons come in the README's order. The budget first, because a
    run that spent it has paths cut short, so ``no fork to flip`` would claim
    more than the run knows; the clock alone decides it, because the alarm
    fires only at the deadline, so an input's timeout failure would say the
    same thing twice, and a target that swallows the alarm leaves no failure
    for a second rule to read. Then the tree, so a run that emptied the tree
    says so even when another reason also holds, then every line and branch
    covered, then the plateau (``_covered_or_plateau``).

    Each solve gets the solver timeout, or what is left of the budget when
    that is less, so the budget still bounds the solver. A solver that
    crashed ends the run as a failure, and so does an input pyct could not
    start a process for. Any other answer is an input to run, or a miss on
    that fork.
    """
    left = _seconds_left(bounds.until)
    if _spent(left):
        return Attempt(stop=Stop(StopKind.BUDGET))
    wanted = tree.next()
    if wanted is None:
        return Attempt(stop=Stop(StopKind.NO_FORK))
    unrun = ForkSite(wanted.aim.site, wanted.aim.raising)
    stop = _covered_or_plateau(bounds, progress)
    if stop is not None:
        return Attempt(stop=stop, unrun=unrun)
    origin = inputs[wanted.path]
    answer, seconds, asked = _solved(wanted, origin, _solve_limit(bounds, left))
    if isinstance(answer, Timeout):
        tree.timed_out()
    if isinstance(answer, Error):
        stop = Stop(StopKind.SOLVER_FAILED, answer.detail)
        return Attempt(stop=stop, unrun=unrun, asked=asked)
    if not isinstance(answer, Sat):
        miss = Miss(wanted.aim.site, miss_why(answer), wanted.aim.raising, seconds)
        return Attempt(miss=miss, asked=asked)
    solved = apply(origin, answer.model)
    try:
        record = record_of(solved.args, call(solved.args, bounds.until), wanted, seconds)
    except InputStartError as error:
        return Attempt(stop=_could_not_start(error), unrun=unrun, asked=asked)
    return Attempt(ran=Ran(record, solved), asked=asked)


def _solved(wanted: Plan, origin: Seed, limit: float) -> tuple[Answer, float, Ask]:
    """The solver's answer for the fork aimed at, the seconds from the start of writing the ask
    to its answer, and the ask with each program pyct gave cvc5 for it."""
    started = time.monotonic()
    with taking() as programs:
        answer = solve(wanted.asked, origin.leaves, limit, origin.containers(), origin.values)
    asked = Ask(0, wanted.aim, wanted.path, tuple(programs))
    return answer, time.monotonic() - started, asked


def _spent_or_covered(bounds: Bounds, progress: Progress) -> Stop | None:
    """The stop on a spent budget, then on every line and branch covered, for the coverage
    goal, as ``_attempt`` checks them. None when neither holds."""
    if _spent(_seconds_left(bounds.until)):
        return Stop(StopKind.BUDGET)
    if bounds.goal is Goal.COVERAGE and progress.full():
        return Stop(StopKind.FULL)
    return None


def _covered_or_plateau(bounds: Bounds, progress: Progress) -> Stop | None:
    """The stop on every line and branch covered, for the coverage goal, then the plateau, which
    counts only the inputs after the last seed and so never holds while one waits. None when
    neither holds."""
    if bounds.goal is Goal.COVERAGE and progress.full():
        return Stop(StopKind.FULL)
    plateau = bounds.plateau
    after_the_seeds = len(progress.covered) - bounds.seeds
    if plateau is not None and after_the_seeds >= plateau and no_gain(progress.covered, plateau):
        return Stop(StopKind.NO_GAIN, plateau=plateau)
    return None


def _let_go(inputs: dict[int, Seed], oldest: int) -> None:
    """Let go of each input whose path no later pick can extend: an answer holding a long list
    is kept only while an answer may still start from it."""
    for path in [path for path in inputs if path < oldest]:
        del inputs[path]


def _seconds_left(until: float | None) -> float | None:
    """The seconds the deadline still allows. No deadline, no limit."""
    return None if until is None else until - time.monotonic()


def _spent(left: float | None) -> bool:
    """Whether the budget is spent. A deadline that has passed is no time at all; cvc5 reads
    ``--tlimit-per=0`` as no limit."""
    return left is not None and left <= 0


def _solve_limit(bounds: Bounds, left: float | None) -> float:
    """The seconds one solve gets: the solver timeout, or ``left`` when the budget has less.

    ``left`` is read once, before the budget check, so a solve always gets
    the same time the check found above zero.
    """
    return bounds.solver_timeout if left is None else min(bounds.solver_timeout, left)
