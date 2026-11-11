"""Run one target with its seeds, then with an input per fork their inputs left open."""

from __future__ import annotations

import dataclasses
import itertools
import platform
import time
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.branches.plan import Plan
from pyct.branches.tree import Tree
from pyct.config.goal import Goal
from pyct.config.limits import Limits
from pyct.core.foundation.branch import ForkSite
from pyct.execution.execute import ExecutionResult
from pyct.results.coverage import Coverage, Progress, Scope, no_gain
from pyct.results.record import (
    Environment,
    InputRecord,
    Miss,
    RunResult,
    Source,
    Stop,
    StopKind,
)
from pyct.run.as_found import modules_as_found
from pyct.run.bounds import Bounds
from pyct.run.collector import collector_paused
from pyct.run.defaults import with_defaults
from pyct.run.isolation import Call, Inputs
from pyct.run.llm_seeds import ask_seeds
from pyct.run.process import InputStartError
from pyct.run.records import miss_why, record_of
from pyct.run.setup import Setup
from pyct.run.target import Target, argument_checks
from pyct.run.tell import Ask, Tell, Told
from pyct.solver import walk_keys
from pyct.solver.answer import Answer, Error, Sat, Timeout
from pyct.solver.cvc5 import solve
from pyct.solver.given import taking
from pyct.solver.locate import locate, version

_NO_LIMITS = Limits()


def _platform() -> str:
    """The platform the summary line names, read with ``sys.modules`` left as it was found.

    The first read imports modules of its own, such as plistlib and datetime
    on macOS. Made here, as this module imports, it runs before a target's
    folder joins the import path, so none of them comes from that folder;
    ``modules_as_found`` then drops each one again, so a target that imports
    one gets it from its own path, as plain Python would. platform keeps
    what it read, so no later read imports them again. The read also runs
    one or two short commands, ``uname -p`` among them, about 10 ms in all.
    """
    with modules_as_found():
        return platform.platform()


_PLATFORM = _platform()

_TELL_NOTHING = Tell()

_PLAIN = Setup()


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
class Loop:
    """The inputs that ran, the seeds' first, what the solver missed, and why they stopped.

    ``untried`` counts the forks the run never tried at each site.
    """

    records: tuple[InputRecord, ...]
    misses: tuple[Miss, ...]
    stop: Stop
    untried: Mapping[ForkSite, int] = field(default_factory=dict)


def run(
    target: Target,
    seed: Mapping[str, object] | Sequence[Mapping[str, object]],
    *,
    limits: Limits = _NO_LIMITS,
    setup: Setup = _PLAIN,
    tell: Tell = _TELL_NOTHING,
) -> RunResult:
    """Call the target with each seed, then with an input per fork left open.

    ``seed`` is one seed, or several, which run in their order before any
    solver input, each adding its path to the one tree the solver works from.
    A run needs at least one, or ``setup.helpers.seeds``, which is asked once,
    before the first input, for seeds that run after these (``ask_seeds``),
    with the budget's clock paused while it answers. While a seed waits to run,
    the run does not stop on an empty tree, and the plateau counts only the
    inputs after the last seed; the budget and full coverage stop it as they
    would a solver input.

    ``setup.isolation`` says where each input runs: by default in a process
    of its own, and ``Isolation.IN_PROCESS`` runs every input in the
    caller's process (see ``Isolation``). Each input goes to
    ``tell.report`` as it finishes, with the coverage of that input alone, so
    an input that hangs never hides the lines of the ones before it. Each
    fork the solver could not flip goes to ``tell.missed`` the same way, so a
    reader sees it when its answer comes in, before the next input's trace.

    The run's coverage adds the lines the target's import ran
    (``Target.import_lines``) to the inputs'; the plateau reads the inputs'
    alone. Each seed's constructor arguments, under the ``self`` of a method
    whose instance each input builds, in each object it names with
    ``"__class__"``, and in each JSON object a class hint builds, first take
    the simple defaults it leaves out (``with_defaults``).
    """
    seeds = (seed,) if isinstance(seed, Mapping) else tuple(seed)
    if not seeds and setup.helpers.seeds is None:
        raise ValueError("a run needs at least one seed")
    scope = Scope.of_module(target.file)
    walk_keys.forget()
    inputs = Inputs(target, setup.isolation)
    # before the deadline starts: the probe is the run's setup, not its time
    cvc5 = version(locate())
    bounds = Bounds.of(limits, len(seeds))
    told = Told(scope=scope, tell=tell, imported=target.import_lines)
    starts, bounds = _starts(target, seeds, setup, bounds, told)
    looped = _inputs(inputs, starts, bounds, told)
    covered = frozenset[int]().union(*(record.covered_lines for record in looped.records))
    return RunResult(
        entry=target.spec,
        records=looped.records,
        # the import's lines count once, for the run, and in no input's coverage
        coverage=Coverage.of(scope, covered | target.import_lines),
        stopped=looped.stop,
        environment=_environment(cvc5, inputs.isolated),
        misses=looped.misses,
        untried=looped.untried,
        deadline=bounds.until,
        goal=limits.goal,
    )


def _starts(
    target: Target,
    seeds: Sequence[Mapping[str, object]],
    setup: Setup,
    bounds: Bounds,
    told: Told,
) -> tuple[tuple[Start, ...], Bounds]:
    """Each seed copied, the user's then the LLM's, and the bounds with the LLM's wait paused
    and its seeds counted. With no seeds helper, the user's seeds alone.

    The ask comes once the deadline is set and before the first input, so the first input
    starts with the whole budget left.
    """
    provider = setup.helpers.seeds
    asked = None if provider is None else ask_seeds(provider, target, seeds, bounds.goal, told)
    checks = argument_checks(target)
    starts = [Start(Seed.of(with_defaults(target, each), checks, target.home)) for each in seeds]
    if asked is None:
        return tuple(starts), bounds
    for each in asked.seeds:
        copy = Seed.of(with_defaults(target, each), checks, target.home)
        starts.append(Start(copy, Source.LLM_SEED))
    counted = dataclasses.replace(bounds, seeds=len(starts))
    return tuple(starts), counted.paused(asked.waited)


def _inputs(call: Call, copies: Sequence[Start], bounds: Bounds, told: Told) -> Loop:
    """The seeds and every input after them, what the solver missed, and why they stopped.

    A first seed whose process cannot start stops the run before any input.

    Each seed is copied, and its leaves noted, before the first seed runs.
    Every input, each seed's too, calls the target with ``bind``'s rebuild of
    its copy, so no input changes the leaves the solver reads or the copies
    a later input starts from.
    """
    first = copies[0]
    try:
        seeded = _from(first, call(first.copy.args, bounds.until))
    except InputStartError as error:
        return Loop((), (), _could_not_start(error))
    return _loop(call, copies, seeded, bounds, told)


def _from(start: Start, executed: ExecutionResult) -> InputRecord:
    """The record of a seed's input, labeled with where the seed came from."""
    return dataclasses.replace(record_of(start.copy.args, executed), source=start.source)


def _could_not_start(error: InputStartError) -> Stop:
    """The stop for an input pyct could not start a process for, with the system's reason."""
    return Stop(StopKind.COULD_NOT_START, str(error))


def _environment(cvc5: str | None, isolated: bool) -> Environment:
    """What the run ran in: the version the solver's cvc5 reported, and where inputs ran.

    A cvc5 that will not say its version leaves the version out; the run is
    the same run either way. ``isolated`` is known only once the inputs ran,
    since a run can move to pyct's own process part way.
    """
    return Environment(
        python=platform.python_version(),
        cvc5=cvc5,
        platform=_PLATFORM,
        isolated=isolated,
    )


def _loop(
    call: Call,
    copies: Sequence[Start],
    seeded: InputRecord,
    bounds: Bounds,
    told: Told,
) -> Loop:
    """Run each seed still waiting, then pick a fork, run what the solver answers for it, until
    a pass says to stop.

    Every input's forks join the tree the next pick draws from, so an input
    that raised or left its plan feeds the loop like any other. A miss is
    kept, handed out before the next pick, and the loop goes on: the fork is
    spent either way.

    ``progress`` holds the lines of each input that ran, in run order, the
    seeds' first, and what each reached; a miss ran no input and adds none.
    It applies the scope, because a record carries the tracer's raw lines.
    Each ask is handed out, numbered, the moment its answer is in.
    """
    misses: list[Miss] = []
    progress = Progress(told.scope, told.imported)
    tree = Tree()
    records = [_took(seeded, told, tree, progress)]
    # each input as the walk copied it, by its path's number: a solver answer starts from the
    # input whose path it extends, not from the seed (see ``Plan.path``)
    inputs = {0: copies[0].copy}
    waiting = deque(copies[1:])
    numbers = itertools.count(1)
    while True:
        _let_go(inputs, tree.oldest)
        attempt = _seed_attempt(call, waiting, bounds, progress)
        if attempt is None:
            attempt = _attempt(call, inputs, tree, bounds, progress)
        _hand_out(attempt, told, numbers, misses)
        if attempt.stop is not None:
            return Loop(tuple(records), tuple(misses), attempt.stop, _untried(tree, attempt))
        if attempt.ran is not None:
            inputs[len(records)] = attempt.ran.seed
            records.append(_took(attempt.ran.record, told, tree, progress))


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


def _seed_attempt(
    call: Call, waiting: deque[Start], bounds: Bounds, progress: Progress
) -> Attempt | None:
    """One pass for the next seed still waiting: the clock, the coverage and the plateau, then
    the seed. None when no seed waits.

    No fork is picked while a seed waits, so ``no fork to flip`` is not
    checked, and the plateau, checked as ``_attempt`` checks it, cannot hold
    before the last seed. The budget and full coverage stop the run as they
    do in ``_attempt``, and the seeds after it do not run.
    """
    if not waiting:
        return None
    start = waiting.popleft()
    if _spent(_seconds_left(bounds.until)):
        return Attempt(stop=Stop(StopKind.BUDGET))
    stop = _covered_or_plateau(bounds, progress)
    if stop is not None:
        return Attempt(stop=stop)
    try:
        record = _from(start, call(start.copy.args, bounds.until))
    except InputStartError as error:
        return Attempt(stop=_could_not_start(error))
    return Attempt(ran=Ran(record, start.copy))


def _solved(wanted: Plan, origin: Seed, limit: float) -> tuple[Answer, float, Ask]:
    """The solver's answer for the fork aimed at, the seconds from the start of writing the ask
    to its answer, and the ask with each program pyct gave cvc5 for it."""
    started = time.monotonic()
    with taking() as programs:
        answer = solve(wanted.asked, origin.leaves, limit, origin.containers(), origin.values)
    asked = Ask(0, wanted.aim, wanted.path, tuple(programs))
    return answer, time.monotonic() - started, asked


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


def _untried(tree: Tree, attempt: Attempt) -> dict[ForkSite, int]:
    """How many forks the run never tried at each site: the open ones, and one picked but not
    run. Counted with the collector paused, as each input's path was added."""
    with collector_paused():
        counts = tree.untried()
    if attempt.unrun is not None:
        counts[attempt.unrun] = counts.get(attempt.unrun, 0) + 1
    return counts


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
