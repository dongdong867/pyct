"""One condition's tries at one stuck moment: ask for a rewrite, check it, ask the solver for it on
the same path, and run its input on the real code, up to 4 asks.

A try fails, and the next ask carries it with its reason, when the reply
holds no expression, the rewrite breaks the form or reads a parameter that
holds an object, pyct follows no value through an operation in it, it
reads no argument, it raised on the input, the input whose path it extends
already meets it, the solver gives no input for it, or its input took the
other side. A reply that got no answer ends the condition's tries at this
moment, and so does a rewrite pyct cannot run, found before an ask or after
it, a spent budget and an input that met the run's stop. When no parameter
is left that a rewrite may read, each holding an object or the method
taking only ``self``, the condition is given up before the first ask.
Decision llm-rewrites-retry-three-times-after-the-first-ask.
"""

from __future__ import annotations

import functools
import json
import time
import types
from collections.abc import Mapping
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
from pyct.rewrite.ask import GivenUp, in_place, recorded, takes
from pyct.rewrite.condition import NO_EXPRESSION, expression_in, holds_object, rewrite_code
from pyct.rewrite.kept import Kept
from pyct.rewrite.notes import (
    RewriteFailed,
    RewriteGivenUp,
    RewriteNote,
    RewriteRead,
    RewriteSkipped,
    RewriteTook,
)
from pyct.rewrite.provider import EarlierTry, RewriteProvider, RewriteReply
from pyct.rewrite.request import About, request_for, value_text
from pyct.solver.answer import Answer, Error, Sat

# the asks about one condition at one moment: the first and 3 more
ASKS = 4
# the characters of a reply with no expression an earlier try quotes
QUOTED = 200
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
class Asking:
    """One condition's tries: the provider, what the solver gave up on, where it sits, the
    function's parameters, and the rewrites kept."""

    provider: RewriteProvider
    given: GivenUp
    about: About
    parameters: tuple[str, ...]
    kept: Kept

    @functools.cached_property
    def objects(self) -> tuple[str, ...]:
        """The parameters whose input value holds an object (``holds_object``), which a rewrite
        may not read."""
        args = self.given.origin.args
        return tuple(name for name in self.parameters if holds_object(args[name]))

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
        request = request_for(self.given, self.about, earlier, self.objects)
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
        args = self.given.origin.args
        ran = around.run_rewrite(rewrite.code, {name: args[name] for name in rewrite.reads})
        if isinstance(ran, str):
            around.note(RewriteSkipped(site, ran))
            return _Ended(ran)
        failed = self._input(rewrite.code, ran, around)
        if failed is None:
            around.note(RewriteTook(site))
            self.kept.keep(self.given.condition, rewrite)
            return None
        return failed if isinstance(failed, _Ended) else EarlierTry(expression, failed)

    def _input(
        self, code: types.CodeType, ran: ExecutionResult, around: Around
    ) -> str | _Ended | None:
        """The rewrite's ask on the plan's path, each kept rewrite in its own condition's place,
        and its input on the real code: None when the input took the wanted side, else why the
        try failed or ended."""
        given = self.given
        items = recorded(ran, code.co_filename)
        if isinstance(items, str):
            return items
        if items.met:
            written = _written(given.origin.args)
            return f"the input {written} already meets it, yet took the other side"
        if not around.going():
            return _Ended("budget spent")
        origin = given.origin
        reused = self.kept.reused(given.plan, origin, around.run_rewrite)
        held = given.plan.asked if reused is None else reused.asked
        answer = around.ask(in_place(held, given.condition, items.items), given.plan, origin)
        if answer is None:
            return _Ended("budget spent")
        if isinstance(answer, Error):
            return f"the solver failed: {answer.detail}"
        if not isinstance(answer, Sat):
            return f"the solver answered {type(answer).__name__.lower()}"
        record = around.run_input(apply(origin, answer.model), given.plan)
        if isinstance(record, Stop):
            return _Ended(record.reason)
        if takes(record, given.condition):
            return None
        return f"the input {_written(record.args)} took the other side"


def _written(args: Mapping[str, object]) -> str:
    """An input's arguments, each name as JSON and each value as ``value_text`` writes it."""
    return (
        "{"
        + ", ".join(f"{json.dumps(name)}: {value_text(value)}" for name, value in args.items())
        + "}"
    )
