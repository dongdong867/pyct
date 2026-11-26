"""The rewrites tool in a run: the stuck moment's rewrites slot, and the loop's asker, which keeps
the first plan whose ask ran out or was unsat at each condition, and puts a kept rewrite first in
each later ask that holds its condition. A plan whose path already holds its aimed fork's check
on the other side is answered ``unsat`` before any ask, so it is never kept. A request is about a
condition's kept plan, and the solver is asked for each rewrite alone (``pyct.rewrite.tries``).

At a moment, rewrites take each ``not taken`` entry whose tries hold a
``timeout``, an ``unknown`` or an ``unsat``, and each ``no fork`` entry
whose value was not lost at a call, in line order, one condition at a time,
and ask about each up to 4 times (``pyct.rewrite.tries``). A ``no fork``
entry is asked about from the first input in run order that ran its
condition's line, its path that input's forks; with no such input it is
given up, said, unasked. An ask that got no answer is said and ends that
condition's tries; once any tool's reply leaves no token under the limit, or
an ask meets it, no rewrite is asked for again
this run (``pyct.run.token_limit``), and the connection has said so. A
rewrite runs only in a child forked from pyct's process: while pyct's process
runs another thread, before an ask or when the rewrite would run, the
condition is skipped at this moment
(decision llm-model-written-code-runs-only-in-a-forked-child-or-not-at-all).
A condition with no parameter a rewrite may read is given up at this
moment, unasked, so a later tool may take it. A parameter each input builds
as an object, from a seed's form, under a class hint or as a method's
``self``, or an instance a ``run()`` caller hands in, is one a rewrite reads
only as ``name.field`` (``pyct.rewrite.kinds``). The rewrite's child builds
the objects it reads fields of as each input does, with the target's home
module, hints and the build of ``self``, so their constructors run there once
more, and reads each field through pyct's reader, which reads only what the
instance stores (``pyct.binding.stored``); the reader's refusal fails the try
with its reason. A rewrite's run, as each solver ask, gets the solver
timeout, or less when the budget has less.

The rewrite's input, and each input a kept rewrite's ask gives, says
``"source": "rewrite"``. A kept rewrite whose input takes the other side is
dropped, and said.
"""

from __future__ import annotations

import dataclasses
import time
import types
from collections.abc import Mapping

from pyct.binding.bind import Seed
from pyct.binding.stored import FieldUnreadError, read_field
from pyct.branches.plan import Plan
from pyct.config.llm import REWRITES_TOOL
from pyct.core.foundation.branch import Branch, Fact
from pyct.execution.execute import ExecutionResult
from pyct.results.causes import Condition, Reason, WhyEntry
from pyct.results.llm_asks import Why
from pyct.results.record import Aim, InputRecord, Source, Stop
from pyct.rewrite.ask import GivenUp, Unread, holds_its_own_check
from pyct.rewrite.condition import FUNCTION, READER
from pyct.rewrite.kept import Kept
from pyct.rewrite.notes import RewriteDropped, RewriteGivenUp, RewriteNote
from pyct.rewrite.provider import RewriteProvider
from pyct.rewrite.request import About
from pyct.rewrite.tries import Asking, Tried
from pyct.run.code_context import code_around
from pyct.run.loop import Asker, Solved, solver_answer
from pyct.run.model_runs import (
    CANNOT_FORK,
    Building,
    CannotFork,
    ModelCall,
    can_fork,
    run_model,
)
from pyct.run.notes import AskSkipped
from pyct.run.process import InputStartError
from pyct.run.records import miss_why
from pyct.run.stuck import Handled, Kind, Moment, Outcome, Running, going
from pyct.run.target import Target, argument_checks, execution_context
from pyct.run.tell import Ask, Told
from pyct.run.token_limit import TokenLimit
from pyct.solver.answer import Answer, Sat, Timeout, Unknown, Unsat
from pyct.solver.given import Given

# why a no-fork entry is given up when no input ran its condition's line
NO_INPUT_RAN = "no input ran the condition"


class Rewrites(Asker):
    """The rewrites tool for one run: the picks whose asks gave up, by condition, the rewrites
    kept, and the conditions the last pass's kept rewrites stood in for."""

    kind = Kind.REWRITES

    def __init__(
        self,
        provider: RewriteProvider,
        target: Target,
        told: Told,
        limit: TokenLimit | None = None,
    ) -> None:
        self.provider = provider
        self.target = target
        self.told = told
        self.limit = TokenLimit() if limit is None else limit
        self.given_up: dict[Condition, GivenUp] = {}
        self.kept = Kept(target.self_name)
        self._used: tuple[Condition, ...] = ()
        context = execution_context(target)
        # how a rewrite's child builds the objects it reads fields of, as each input does
        self.building = Building(context.home, context.checks, context.self_build)

    @property
    def can_ask(self) -> bool:
        """Whether rewrites may still ask this run: false once the run's token limit is
        reached, by any tool's ask."""
        return not self.limit.reached

    def take(self, entries: tuple[WhyEntry, ...], moment: Moment) -> Handled:
        """Ask about each entry's condition in turn; ``took``, ``gave up`` or ``skipped`` each."""
        outcomes: list[Outcome] = []
        asked = False
        for entry in entries:
            if self.limit.reached or not going(moment.run):
                outcomes.append(Outcome.SKIPPED)
                continue
            given = self._given(entry, moment.run)
            if isinstance(given, Outcome):
                outcomes.append(given)
                continue
            tried = self._asking(given).tries(_Around(moment.run, self.told, self.building))
            asked = asked or tried.asked
            outcomes.append(self._outcome(tried))
        return Handled(tuple(outcomes), asked)

    def _given(self, entry: WhyEntry, run: Running) -> GivenUp | Outcome:
        """What an entry's tries are about: the plan kept for a ``not taken`` entry's condition,
        ``skipped`` when none is; for a ``no fork`` entry, the first input that ran its
        condition's line, or ``gave up``, said, when none did."""
        condition = entry.condition
        if condition is None:
            return Outcome.SKIPPED
        if entry.reason is not Reason.NO_FORK:
            return self.given_up.get(condition, Outcome.SKIPPED)
        ran = next(
            (
                (at, record)
                for at, record in enumerate(run.records)
                if condition.site.line in record.covered_lines
            ),
            None,
        )
        if ran is None:
            self.told.note(RewriteGivenUp(condition.site, NO_INPUT_RAN))
            return Outcome.GAVE_UP
        at, record = ran
        origin = Seed.of(record.args, argument_checks(self.target), self.target.home)
        return GivenUp(condition, None, origin, None, record.forks, entry.lines, at)

    def solved(self, wanted: Plan, origin: Seed, limit: float) -> Solved:
        """The ask with each kept rewrite the plan holds in its condition's place first; then,
        when it gives no input, the plan's own, each within what is left of ``limit``. When
        the kept rewrite, in its run or its ask, used up ``limit``, the plan's own does not run
        and the pick ends as a ``timeout``, its limit run out. The first plan at a condition
        whose ask ended in ``timeout``, ``unknown`` or ``unsat`` is kept. A plan whose path
        already holds its aimed fork's check on the other side, which no input meets, is
        answered ``unsat`` before any ask or kept rewrite runs, so it is never kept."""
        self._used = ()
        if holds_its_own_check(wanted):
            return _unasked(wanted, Unsat())
        started = time.monotonic()
        reused = self.kept.reused(wanted, origin, _Child(started + limit, self.building).run)
        programs: tuple[Given, ...] = ()
        left = _left(started, limit)
        if reused is not None and left > 0:
            rewritten = solver_answer(wanted, origin, left, reused.asked)
            if isinstance(rewritten.answer, Sat):
                self._used = reused.conditions
                return dataclasses.replace(rewritten, source=Source.REWRITE)
            programs = rewritten.asked.programs
        rest = _left(started, limit)
        solved = super().solved(wanted, origin, rest) if rest > 0 else _unasked(wanted, Timeout())
        self._keep(wanted, origin, solved)
        asked = dataclasses.replace(solved.asked, programs=(*programs, *solved.asked.programs))
        return Solved(solved.answer, time.monotonic() - started, asked)

    def ran(self, record: InputRecord, number: int) -> None:
        """Drop each kept rewrite the input's ask used whose condition it took the other side
        of, and say so."""
        for condition in self.kept.judged(record, self._used):
            self.told.note(RewriteDropped(condition.site, number))
        self._used = ()

    def heard(self, record: InputRecord, number: int) -> None:
        """Each input the run keeps: rewrites judge their kept rewrites by a pass's input, in
        ``ran``."""

    def waiting(self, moment: Moment) -> bool:
        """Rewrites ask at a moment only about the entries they are handed."""
        return False

    def _keep(self, wanted: Plan, origin: Seed, solved: Solved) -> None:
        """Keep the plan when it is the first at its condition whose ask ran out or was
        unsat."""
        answer = solved.answer
        aimed = wanted.prefix[-1]
        if aimed.raising or not isinstance(answer, Timeout | Unknown | Unsat):
            return
        condition = Condition(aimed.site, aimed.taken)
        self.given_up.setdefault(condition, GivenUp(condition, wanted, origin, miss_why(answer)))

    def _asking(self, given: GivenUp) -> Asking:
        site = given.condition.site
        files = {site.file, *(fork.site.file for fork in given.earlier)}
        modules = {file: self.target.module_of(file) for file in files}
        about = About(
            place=f"{modules[site.file]}:{site.line}:{site.col}",
            code=code_around(site.file, site.line),
            modules=modules,
        )
        target = self.target
        parameters = tuple(given.origin.args)
        return Asking(self.provider, given, about, parameters, self.kept, target.self_class)

    def _outcome(self, tried: Tried) -> Outcome:
        """What the tries come to, said: an ask that got no answer is skipped, and once the
        token limit is reached, by a reply or a refused ask, no tool asks again."""
        if tried.spent:
            self.limit.reach()
        unanswered = tried.unanswered
        if unanswered is not None:
            if unanswered.why is Why.LIMIT:
                self.limit.reach()
            else:
                self.told.note(AskSkipped(REWRITES_TOOL, unanswered.reason))
            return Outcome.SKIPPED
        if tried.took:
            return Outcome.TOOK
        return Outcome.SKIPPED if tried.ended is not None else Outcome.GAVE_UP


class _Around:
    """The run as a condition's tries see it, at one moment, and how a rewrite's child builds
    the objects it reads fields of."""

    def __init__(self, run: Running, told: Told, building: Building) -> None:
        self.run = run
        self.told = told
        self.building = building

    def going(self) -> bool:
        return going(self.run)

    def blocked(self) -> str | None:
        """Why no rewrite can run now: pyct's process runs another thread; None when one can."""
        return None if can_fork() else CANNOT_FORK

    def ask(self, asked: tuple[Branch | Fact, ...], given: GivenUp) -> Answer | None:
        """The solver's answer to ``asked`` alone, from ``given``'s input, within the seconds
        one ask gets, its programs handed out as the run's asks are; None when no time is
        left."""
        limit = self._limit()
        if limit <= 0:
            return None
        wanted = given.plan or _own_fork_plan(asked, given.path)
        solved = solver_answer(wanted, given.origin, limit, asked)
        self.run.tell_ask(solved.asked)
        return solved.answer

    def _limit(self) -> float:
        """The solver timeout, or the budget's rest when that is less."""
        bounds = self.run.bounds
        if bounds.until is None:
            return bounds.solver_timeout
        return min(bounds.solver_timeout, bounds.until - time.monotonic())

    def pause(self, seconds: float) -> None:
        self.run.pause(seconds)

    def note(self, note: RewriteNote) -> None:
        self.told.note(note)

    def run_rewrite(
        self, code: types.CodeType, args: Mapping[str, object]
    ) -> ExecutionResult | Unread | str:
        return _Child(time.monotonic() + self._limit(), self.building).run(code, args)

    def run_input(self, seed: Seed, plan: Plan | None) -> InputRecord | Stop:
        return self.run.run_input(seed, Source.REWRITE, plan)


class _Child:
    """Runs a rewrite in a child forked from pyct's process, which must end by ``until``, and
    builds the objects it reads fields of as ``building`` says, its fields read by pyct's
    reader."""

    def __init__(self, until: float, building: Building) -> None:
        self.until = until
        self.building = building

    def run(
        self, code: types.CodeType, args: Mapping[str, object]
    ) -> ExecutionResult | Unread | str:
        """What the rewrite's call recorded, why the reader read no field, or why it did not
        run."""
        call = ModelCall(
            code, FUNCTION, args, {READER: read_field}, self.building, (FieldUnreadError,)
        )
        try:
            ran = run_model(call, self.until)
        except InputStartError as error:
            return f"cannot start a child: {error}"
        if isinstance(ran, CannotFork):
            return CANNOT_FORK
        return ran.result if ran.ended is None else Unread(ran.ended)


def _own_fork_plan(asked: tuple[Branch | Fact, ...], path: int) -> Plan:
    """The plan that names a rewrite's ask, its own fork last, on the input ``path`` names."""
    forks = tuple(item for item in asked if isinstance(item, Branch))
    return Plan(forks, Aim(forks[-1].site, len(forks) - 1), path)


def _unasked(wanted: Plan, answer: Answer) -> Solved:
    """The answer for a plan the solver was not asked about: ``unsat`` for one whose path holds
    its aimed fork's check on the other side, or ``timeout`` for one whose limit a kept rewrite
    used up, in its run or its ask, before the plan's own ask could run."""
    return Solved(answer, 0.0, Ask(0, wanted.aim, wanted.path, ()))


def _left(started: float, limit: float) -> float:
    """What is left of ``limit`` seconds counted from ``started``."""
    return limit - (time.monotonic() - started)
