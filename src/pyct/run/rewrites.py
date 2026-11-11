"""The rewrites tool in a run: the stuck moment's rewrites slot, and the loop's asker, which keeps
the first plan whose ask ran out at each condition and puts a kept rewrite first in each later
ask that holds its condition.

At a moment, rewrites take each ``not taken`` entry whose tries hold a
``timeout`` or an ``unknown``, in line order, one condition at a time, and
ask about each up to 4 times (``pyct.rewrite.tries``). An ask that got no
answer is said and ends that condition's tries; once the token limit is
reached no rewrite is asked for again this run, and the connection has said
so. A rewrite runs only in a child forked from pyct's process: while pyct's
process runs another thread, the condition is skipped at this moment
(decision llm-model-written-code-runs-only-in-a-forked-child-or-not-at-all).
A rewrite's run, as each solver ask, gets the solver timeout, or less when
the budget has less.

The rewrite's input, and each input a kept rewrite's ask gives, says
``"source": "rewrite"``. A kept rewrite whose input takes the other side is
dropped, and said.
"""

from __future__ import annotations

import dataclasses
import sys
import time
import types
from collections.abc import Mapping
from pathlib import Path

from pyct.binding.bind import Seed
from pyct.branches.plan import Plan
from pyct.config.llm import REWRITES_TOOL
from pyct.core.foundation.branch import Branch, Fact
from pyct.execution.execute import ExecutionResult
from pyct.results.causes import Condition, WhyEntry
from pyct.results.llm_asks import Why
from pyct.results.record import InputRecord, MissWhy, Source, Stop
from pyct.rewrite.ask import GivenUp
from pyct.rewrite.condition import FUNCTION
from pyct.rewrite.kept import Kept
from pyct.rewrite.notes import RewriteDropped, RewriteNote
from pyct.rewrite.provider import RewriteProvider
from pyct.rewrite.request import About
from pyct.rewrite.tries import Asking, Tried
from pyct.run.code_context import code_around
from pyct.run.loop import Asker, Solved, solver_answer
from pyct.run.model_runs import CannotFork, ModelCall, run_model
from pyct.run.notes import AskSkipped
from pyct.run.process import InputStartError
from pyct.run.stuck import Handled, Kind, Moment, Outcome, Running
from pyct.run.target import Target
from pyct.run.tell import Ask, Told
from pyct.solver.answer import Answer, Sat, Timeout, Unknown
from pyct.solver.given import Given

# why a rewrite does not run beside a second thread of pyct's process
CANNOT_FORK = "cannot fork"


class Rewrites(Asker):
    """The rewrites tool for one run: what the solver gave up on, by condition, the rewrites
    kept, and the conditions the last pass's kept rewrites stood in for."""

    kind = Kind.REWRITES

    def __init__(self, provider: RewriteProvider, target: Target, told: Told) -> None:
        self.provider = provider
        self.target = target
        self.told = told
        self.given_up: dict[Condition, GivenUp] = {}
        self.kept = Kept()
        self._used: tuple[Condition, ...] = ()
        self._limit_reached = False

    def take(self, entries: tuple[WhyEntry, ...], moment: Moment) -> Handled:
        """Ask about each entry's condition in turn; ``took``, ``gave up`` or ``skipped`` each."""
        outcomes: list[Outcome] = []
        asked = False
        for entry in entries:
            given = None if entry.condition is None else self.given_up.get(entry.condition)
            if given is None or self._limit_reached or not _going(moment.run):
                outcomes.append(Outcome.SKIPPED)
                continue
            tried = self._asking(given).tries(_Around(moment.run, self.told))
            asked = asked or tried.asked
            outcomes.append(self._outcome(tried))
        return Handled(tuple(outcomes), asked)

    def solved(self, wanted: Plan, origin: Seed, limit: float) -> Solved:
        """The ask with each kept rewrite the plan holds in its condition's place first; then,
        when it gives no input, the plan's own, each within what is left of ``limit``. The
        first plan at a condition whose ask ended in ``timeout`` or ``unknown``, or had no time
        left, is kept."""
        started = time.monotonic()
        self._used = ()
        reused = self.kept.reused(wanted, origin, _Child(started + limit).run)
        programs: tuple[Given, ...] = ()
        if reused is not None and _left(started, limit) > 0:
            rewritten = solver_answer(wanted, origin, _left(started, limit), reused.asked)
            if isinstance(rewritten.answer, Sat):
                self._used = reused.conditions
                return dataclasses.replace(rewritten, source=Source.REWRITE)
            programs = rewritten.asked.programs
        rest = _left(started, limit)
        solved = super().solved(wanted, origin, rest) if rest > 0 else _out_of_time(wanted)
        self._keep(wanted, origin, solved)
        asked = dataclasses.replace(solved.asked, programs=(*programs, *solved.asked.programs))
        return Solved(solved.answer, time.monotonic() - started, asked)

    def ran(self, record: InputRecord, number: int) -> None:
        """Drop each kept rewrite the input's ask used whose condition it took the other side
        of, and say so."""
        for condition in self.kept.judged(record, self._used):
            self.told.note(RewriteDropped(condition.site, number))
        self._used = ()

    def _keep(self, wanted: Plan, origin: Seed, solved: Solved) -> None:
        """Keep the plan when it is the first at its condition whose ask ran out."""
        answer = solved.answer
        aimed = wanted.prefix[-1]
        if aimed.raising or not isinstance(answer, Timeout | Unknown):
            return
        condition = Condition(aimed.site, aimed.taken)
        why = MissWhy.TIMEOUT if isinstance(answer, Timeout) else MissWhy.UNKNOWN
        self.given_up.setdefault(condition, GivenUp(condition, wanted, origin, why))

    def _asking(self, given: GivenUp) -> Asking:
        site = given.condition.site
        about = About(
            place=f"{_module_of(site.file, self.target)}:{site.line}:{site.col}",
            site=f"{site.file}:{site.line}:{site.col}",
            code=code_around(site.file, site.line),
        )
        self_name = self.target.self_name
        parameters = tuple(name for name in given.origin.args if name != self_name)
        return Asking(self.provider, given, about, parameters, self.kept)

    def _outcome(self, tried: Tried) -> Outcome:
        """What the tries come to, said: an ask that got no answer is skipped, and once the
        token limit is reached no condition asks again."""
        unanswered = tried.unanswered
        if unanswered is not None:
            if unanswered.why is Why.LIMIT:
                self._limit_reached = True
            else:
                self.told.note(AskSkipped(REWRITES_TOOL, unanswered.reason))
            return Outcome.SKIPPED
        if tried.took:
            return Outcome.TOOK
        return Outcome.SKIPPED if tried.ended is not None else Outcome.GAVE_UP


class _Around:
    """The run as a condition's tries see it, at one moment."""

    def __init__(self, run: Running, told: Told) -> None:
        self.run = run
        self.told = told

    def going(self) -> bool:
        return _going(self.run)

    def ask(self, asked: tuple[Branch | Fact, ...], plan: Plan, origin: Seed) -> Answer | None:
        """The solver's answer within the seconds one ask gets, its programs handed out as the
        run's asks are; None when no time is left."""
        limit = self._limit()
        if limit <= 0:
            return None
        solved = solver_answer(plan, origin, limit, asked)
        self.run.hand_out(solved.asked)
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
    ) -> ExecutionResult | str:
        return _Child(time.monotonic() + self._limit()).run(code, args)

    def run_input(self, seed: Seed, plan: Plan) -> InputRecord | Stop:
        return self.run.run_input(seed, Source.REWRITE, plan)


class _Child:
    """Runs a rewrite in a child forked from pyct's process, which must end by ``until``."""

    def __init__(self, until: float) -> None:
        self.until = until

    def run(self, code: types.CodeType, args: Mapping[str, object]) -> ExecutionResult | str:
        """What the rewrite's call recorded, or why it did not run."""
        try:
            ran = run_model(ModelCall(code, FUNCTION, args), self.until)
        except InputStartError as error:
            return f"cannot start a child: {error}"
        return CANNOT_FORK if isinstance(ran, CannotFork) else ran.result


def _out_of_time(wanted: Plan) -> Solved:
    """The answer for a plan whose limit a kept rewrite's ask used up: no time left."""
    return Solved(Timeout(), 0.0, Ask(0, wanted.aim, wanted.path, ()))


def _left(started: float, limit: float) -> float:
    """What is left of ``limit`` seconds counted from ``started``."""
    return limit - (time.monotonic() - started)


def _going(run: Running) -> bool:
    """Whether a try may start: the run met no stop and its budget is not spent."""
    until = run.bounds.until
    return run.stopped is None and (until is None or until > time.monotonic())


def _module_of(file: str, target: Target) -> str:
    """The dotted name of the module ``file`` holds: the target's own, or a loaded module's
    whose file it is, or the file's stem when no module is."""
    if file == target.file:
        return target.spec.partition("::")[0]
    for name, module in list(sys.modules.items()):
        if getattr(module, "__file__", None) == file:
            return name
    return Path(file).stem
