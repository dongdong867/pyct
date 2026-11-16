"""One condition's tries at one stuck moment: ask for a rewrite, check it, ask the solver for it on
the same path, and run its input on the real code, up to 4 asks.

When the solver gives no input for the rewrite on the path of the
condition's first kept visit (``unsat``, ``unknown`` or ``timeout``), the
same try goes on to each later kept visit in turn: the rewrite runs on that
visit's input, is asked on that visit's path, and its input runs aimed at
that visit's plan. A later visit is passed over, unsaid, when the rewrite
reads a name its input lacks, or that is or holds an object there
(``pyct.rewrite.kinds``), raised or did not finish on it, records nothing
to put in the condition's place, or the input already meets it.

A try fails, and the next ask carries it with its reason, when the reply
holds no expression, the rewrite breaks the form or reads a parameter that
is or holds an object, pyct follows no value through an operation in it, it
reads no argument, it raised on the input, the input whose path it extends
already meets it, the solver failed or gave no input for it on any kept
visit, each answer said in the order asked, or its input took the other
side. A reply that got no answer ends the condition's tries at this
moment, and so does a rewrite pyct cannot run, found before an ask or after
it on any kept visit, a spent budget, checked before each visit and after
the rewrite runs on a later one, and an input that met the run's stop.
When no parameter is left that a rewrite may read, each being or holding
an object or the method taking only ``self``, the condition is given up
before the first ask.
Decision llm-rewrites-retry-three-times-after-the-first-ask.
"""

from __future__ import annotations

import functools
import json
import time
import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.branches.plan import Plan
from pyct.core.foundation.branch import Branch, Fact
from pyct.execution.execute import ExecutionResult
from pyct.intercept.model_code import Refused
from pyct.results.llm_asks import Unanswered
from pyct.results.record import InputRecord, Stop
from pyct.rewrite.ask import GivenUp, Recorded, Visit, in_place, recorded, run_on, takes
from pyct.rewrite.condition import NO_EXPRESSION, Rewrite, expression_in, rewrite_code
from pyct.rewrite.kept import Kept
from pyct.rewrite.kinds import Kind, Kinds
from pyct.rewrite.notes import (
    RewriteFailed,
    RewriteGivenUp,
    RewriteNote,
    RewriteRead,
    RewriteSkipped,
    RewriteTook,
)
from pyct.rewrite.provider import EarlierTry, RewriteProvider, RewriteReply
from pyct.rewrite.request import About, args_text, request_for
from pyct.solver.answer import Answer, Error, Sat, Timeout, Unknown, Unsat

# the asks about one condition at one moment: the first and 3 more
ASKS = 4
# the characters of a reply with no expression an earlier try quotes
QUOTED = 200
# why the tries end when the run can no longer go on
BUDGET_SPENT = "budget spent"
# why the condition is given up before an ask when no parameter is left that a rewrite may read,
# each holding an object or the method taking only self
NOTHING_READABLE = "no argument a rewrite may read"


class Around(Protocol):
    """The run as a condition's tries see it: whether to go on, why no rewrite could run now,
    the solver's answer to an ask on a plan's path, the clock paused for the model's wait, a
    note said, a rewrite run in a child of pyct's process, and a real input run aimed at a
    plan."""

    def going(self) -> bool: ...

    def blocked(self) -> str | None:
        """Why no rewrite could run now, so no ask is worth its wait; None when one could."""
        ...

    def ask(self, asked: tuple[Branch | Fact, ...], plan: Plan, origin: Seed) -> Answer | None:
        """The solver's answer to ``asked``, aimed at ``plan``'s fork from ``origin``, within
        the seconds one ask gets; None when no time is left."""
        ...

    def pause(self, seconds: float) -> None: ...

    def note(self, note: RewriteNote) -> None: ...

    def run_rewrite(
        self, code: types.CodeType, args: Mapping[str, object]
    ) -> ExecutionResult | str: ...

    def run_input(self, seed: Seed, plan: Plan) -> InputRecord | Stop: ...


@dataclass(frozen=True)
class Tried:
    """How one condition's tries at a moment ended: whether a rewrite took the wanted side,
    whether the model was asked, and, when the tries ended early, the ask that got no answer
    or why no try could go on. With neither, and nothing taken, the condition is given up at
    this moment, one with no parameter a rewrite may read included. ``spent`` says the last
    reply left no token under the limit."""

    took: bool
    asked: bool
    unanswered: Unanswered | None = None
    ended: str | None = None
    spent: bool = False


@dataclass(frozen=True)
class _Ended:
    """A try that ends the condition's tries at this moment, and why."""

    reason: str


@dataclass(frozen=True)
class _NoInput:
    """A visit on whose path the solver gave no input for the rewrite, so the try goes on to the
    next kept visit, and what it answered."""

    answer: Unsat | Unknown | Timeout


@dataclass(frozen=True)
class Asking:
    """One condition's tries: the provider, what the solver gave up on, where it sits, the
    function's parameters, the rewrites kept, and the method's ``self`` parameter, None for a
    target that is no method."""

    provider: RewriteProvider
    given: GivenUp
    about: About
    parameters: tuple[str, ...]
    kept: Kept
    self_name: str | None = None

    @functools.cached_property
    def kinds(self) -> Kinds:
        """What tells the given-up input's objects apart: the hints its seed was made with, and
        the method's ``self``."""
        return Kinds.of_seed(self.given.origin, self.self_name)

    @functools.cached_property
    def objects(self) -> tuple[str, ...]:
        """The parameters that are or hold an object on the given-up input (``Kinds``), which a
        rewrite may not read."""
        args = self.given.origin.args
        return tuple(
            name for name in self.parameters if self.kinds.of(name, args[name]) is not Kind.PLAIN
        )

    @property
    def readable(self) -> bool:
        """Whether some parameter holds no object, so a rewrite may read it."""
        return len(self.objects) < len(self.parameters)

    def tries(self, around: Around) -> Tried:
        """Ask up to ``ASKS`` times, each carrying the earlier tries, until a rewrite's input
        takes the wanted side or the tries end; with no parameter a rewrite may read, ask
        nothing, say so and give the condition up."""
        if not self.readable:
            around.note(RewriteGivenUp(self.given.condition.site, NOTHING_READABLE))
            return Tried(False, False)
        return self._tries(around)

    def _tries(self, around: Around) -> Tried:
        """The asks, each carrying the earlier tries."""
        earlier: list[EarlierTry] = []
        asked = spent = False
        while len(earlier) < ASKS and around.going():
            answer = self._ask(tuple(earlier), around)
            if isinstance(answer, _Ended):
                return Tried(False, asked, ended=answer.reason, spent=spent)
            asked = True
            if isinstance(answer, Unanswered):
                return Tried(False, asked, unanswered=answer)
            spent = answer.cost.tokens_left == 0
            outcome = self._try(answer, around)
            if outcome is None:
                return Tried(True, asked, spent=spent)
            if isinstance(outcome, _Ended):
                return Tried(False, asked, ended=outcome.reason, spent=spent)
            site = self.given.condition.site
            around.note(RewriteFailed(site, answer.cost.attempt, outcome.reason))
            earlier.append(outcome)
        return Tried(False, asked, spent=spent)

    def _ask(
        self, earlier: tuple[EarlierTry, ...], around: Around
    ) -> RewriteReply | Unanswered | _Ended:
        """The provider's reply, its wait paused; no ask, said, when no rewrite could run."""
        blocked = around.blocked()
        if blocked is not None:
            around.note(RewriteSkipped(self.given.condition.site, blocked))
            return _Ended(blocked)
        request = request_for(self.given, self.about, earlier, self.objects, self.kinds)
        started = time.monotonic()
        answer = self.provider.rewrite(request)
        around.pause(time.monotonic() - started)
        return answer

    def _try(self, reply: RewriteReply, around: Around) -> EarlierTry | _Ended | None:
        """One try: None when its input took the wanted side, else how it failed."""
        site = self.given.condition.site
        expression = expression_in(reply.text, self.parameters)
        if expression is None:
            return EarlierTry(reply.text.strip()[:QUOTED], NO_EXPRESSION)
        around.note(RewriteRead(site, expression))
        file = f"<rewrite {self.about.place}>"
        rewrite = rewrite_code(expression, self.parameters, file, self.objects)
        if isinstance(rewrite, Refused):
            return EarlierTry(expression, rewrite.reason)
        ran = around.run_rewrite(rewrite.code, rewrite.handed(self.given.origin.args))
        if isinstance(ran, str):
            around.note(RewriteSkipped(site, ran))
            return _Ended(ran)
        failed = self._input(expression, rewrite, ran, around)
        if failed is None:
            around.note(RewriteTook(site))
            self.kept.keep(self.given.condition, rewrite)
        return failed

    def _input(
        self, expression: str, rewrite: Rewrite, ran: ExecutionResult, around: Around
    ) -> EarlierTry | _Ended | None:
        """The rewrite's ask on the first kept visit's path, then on each later visit's while
        the solver gives no input: None when an input took the wanted side, else how the try
        failed or why it ended."""
        given = self.given
        items = recorded(ran, rewrite.code.co_filename)
        if isinstance(items, str):
            return EarlierTry(expression, items)
        if items.met:
            written = _written(given.origin.args, self.kinds)
            met = f"the input {written} already meets it, yet took the other side"
            return EarlierTry(expression, met)
        return self._on_visits(expression, rewrite, items, around)

    def _on_visits(
        self, expression: str, rewrite: Rewrite, first: Recorded, around: Around
    ) -> EarlierTry | _Ended | None:
        """The rewrite's ask on each kept visit's path in turn while the solver gives no input,
        the first with what its run recorded there, each later one run on its own input
        (``_later``): None when an input took the wanted side, else how the try failed, with
        each answer when no visit gave an input, or why the tries end."""
        answers: list[Unsat | Unknown | Timeout] = []
        for at, visit in enumerate(self.given.visits):
            if not around.going():
                return _Ended(BUDGET_SPENT)
            items = first if at == 0 else self._later(rewrite, visit, around)
            if isinstance(items, _Ended):
                return items
            if items is None:
                continue
            outcome = self._on(expression, visit, items, around)
            if not isinstance(outcome, _NoInput):
                return outcome
            answers.append(outcome.answer)
        return _no_input(expression, answers)

    def _later(self, rewrite: Rewrite, visit: Visit, around: Around) -> Recorded | _Ended | None:
        """What the rewrite, run on a later visit's input, puts in that visit's ask. None passes
        the visit over: the rewrite reads a name the input lacks, or that is or holds an object
        there, raised or did not finish on it, records nothing to put in the condition's place,
        or the input already meets it. A rewrite pyct cannot run ends the tries, said, as on the
        first, and a spent budget, found once the rewrite has run, ends them unsaid."""
        ran = run_on(rewrite, visit.origin, around.run_rewrite)
        if ran is None:
            return None
        if isinstance(ran, str):
            around.note(RewriteSkipped(self.given.condition.site, ran))
            return _Ended(ran)
        if not around.going():
            return _Ended(BUDGET_SPENT)
        items = recorded(ran, rewrite.code.co_filename)
        return None if isinstance(items, str) or items.met else items

    def _on(
        self, expression: str, visit: Visit, items: Recorded, around: Around
    ) -> EarlierTry | _Ended | _NoInput | None:
        """The rewrite's ask on one visit's path, each kept rewrite in its own condition's
        place, and its input run on the real code: None when the input took the wanted side,
        ``_NoInput`` when the solver gave none, else how the try failed or why it ended."""
        condition = self.given.condition
        reused = self.kept.reused(visit.plan, visit.origin, around.run_rewrite)
        held = visit.plan.asked if reused is None else reused.asked
        answer = around.ask(in_place(held, condition, items.items), visit.plan, visit.origin)
        if answer is None:
            return _Ended(BUDGET_SPENT)
        if isinstance(answer, Error):
            return EarlierTry(expression, f"the solver failed: {answer.detail}")
        if not isinstance(answer, Sat):
            return _NoInput(answer)
        record = around.run_input(apply(visit.origin, answer.model), visit.plan)
        if isinstance(record, Stop):
            return _Ended(record.reason)
        if takes(record, condition):
            return None
        written = _written(record.args, self.kinds)
        return EarlierTry(expression, f"the input {written} took the other side")


def _no_input(expression: str, answers: Sequence[Unsat | Unknown | Timeout]) -> EarlierTry:
    """The failed try for a rewrite the solver gave no input for on any kept visit: each answer
    in the order asked, and whether any was ``timeout`` or ``unknown``."""
    said = ", then ".join(type(answer).__name__.lower() for answer in answers)
    gave_up = any(isinstance(answer, Timeout | Unknown) for answer in answers)
    return EarlierTry(expression, f"the solver answered {said}", solver_gave_up=gave_up)


def _written(args: Mapping[str, object], kinds: Kinds) -> str:
    """An input's arguments, each name as JSON and each value as ``value_text`` writes it."""
    return (
        "{"
        + ", ".join(f"{json.dumps(name)}: {text}" for name, text in args_text(args, kinds))
        + "}"
    )
