"""One condition's tries at one stuck moment: ask for a rewrite, check it, ask the solver for it
alone, and run its input on the real code, up to 4 asks.

The solver's ask holds no kept rewrite of another condition. The input it
gives runs aimed at the condition's kept plan, or with no plan for a
condition that recorded no fork.

A parameter that is an object on the input is read only as ``name.field``
(``pyct.rewrite.condition``); one that holds an object inside a list, tuple
or dict is not read at all. A try fails, and the next ask carries it with
its reason, when the reply holds no expression, the rewrite breaks the form,
which covers how it reads objects, pyct's reader reads no field it
names, pyct follows no value through an operation in it, it reads no
argument or no value an input sets, it raised on the input, the input whose
path it extends already meets it, the solver failed or gave no input for it,
or its input took the other side or, for a condition with no fork, ran none
of the lines that side guards. A reply that got no answer ends the
condition's tries at this moment, and so does a rewrite pyct cannot run,
found before an ask or after it, a spent budget, checked before the solver's
ask, and an input that met the run's stop.
When no parameter is left that a rewrite may read, each holding an object
inside a list, tuple or dict, the condition is given up before the first
ask.
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
from pyct.rewrite.ask import GivenUp, Recorded, Unread, reached, recorded
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
from pyct.solver.answer import Answer, Error, Sat

# the asks about one condition at one moment: the first and 3 more
ASKS = 4
# the characters of a reply with no expression an earlier try quotes
QUOTED = 200
# why the tries end when the run can no longer go on
BUDGET_SPENT = "budget spent"
# why the condition is given up before an ask when no parameter is left that a rewrite may read,
# each holding an object inside a list, tuple or dict
NOTHING_READABLE = "no argument a rewrite may read"
# why a try at a condition that recorded no fork fails when its input ran no missed line
NO_GUARDED_LINE = "ran none of the lines that side guards"


class Around(Protocol):
    """The run as a condition's tries see it: whether to go on, why no rewrite could run now,
    the solver's answer to a rewrite's ask, the clock paused for the model's wait, a note said,
    a rewrite run in a child of pyct's process, and a real input run, aimed at a plan when one
    is given."""

    def going(self) -> bool: ...

    def blocked(self) -> str | None:
        """Why no rewrite could run now, so no ask is worth its wait; None when one could."""
        ...

    def ask(self, asked: tuple[Branch | Fact, ...], given: GivenUp) -> Answer | None:
        """The solver's answer to ``asked`` alone, from ``given``'s input, within the seconds
        one ask gets; None when no time is left."""
        ...

    def pause(self, seconds: float) -> None: ...

    def note(self, note: RewriteNote) -> None: ...

    def run_rewrite(
        self, code: types.CodeType, args: Mapping[str, object]
    ) -> ExecutionResult | Unread | str: ...

    def run_input(self, seed: Seed, plan: Plan | None) -> InputRecord | Stop: ...


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
    function's parameters, the rewrites kept, which name the method's ``self`` parameter, and
    that parameter's class, None for a target that is no method."""

    provider: RewriteProvider
    given: GivenUp
    about: About
    parameters: tuple[str, ...]
    kept: Kept
    self_class: type | None = None

    @property
    def self_name(self) -> str | None:
        """The method's ``self`` parameter, as the kept rewrites name it."""
        return self.kept.self_name

    @functools.cached_property
    def kinds(self) -> Kinds:
        """What tells the given-up input's objects apart: the hints its seed was made with, and
        the method's ``self``."""
        return Kinds.of_seed(self.given.origin, self.self_name, self.self_class)

    @functools.cached_property
    def holders(self) -> tuple[str, ...]:
        """The parameters that hold an object inside a list, tuple or dict on the given-up input
        (``Kinds``), which a rewrite may not read."""
        return self._of_kind(Kind.HOLDS_OBJECT)

    @functools.cached_property
    def objects(self) -> tuple[str, ...]:
        """The parameters that are objects on the given-up input, which a rewrite reads only as
        ``name.field``."""
        return self._of_kind(Kind.OBJECT)

    def _of_kind(self, kind: Kind) -> tuple[str, ...]:
        args = self.given.origin.args
        return tuple(name for name in self.parameters if self.kinds.of(name, args[name]) is kind)

    @property
    def readable(self) -> bool:
        """Whether some parameter holds no object inside a list, tuple or dict, so a rewrite may
        read it."""
        return len(self.holders) < len(self.parameters)

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
        request = request_for(self.given, self.about, earlier, self.holders, self.kinds)
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
        rewrite = rewrite_code(expression, self.parameters, file, self.holders, self.objects)
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
        self, expression: str, rewrite: Rewrite, ran: ExecutionResult | Unread, around: Around
    ) -> EarlierTry | _Ended | None:
        """The rewrite's ask alone: None when its input took the wanted side, else how the try
        failed or why it ended."""
        items = recorded(ran, rewrite)
        if isinstance(items, str):
            return EarlierTry(expression, items)
        if items.met:
            written = _written(self.given.origin.args, self.kinds)
            met = f"the input {written} already meets it, yet took the other side"
            return EarlierTry(expression, met)
        if not around.going():
            return _Ended(BUDGET_SPENT)
        return self._on(expression, items, around)

    def _on(self, expression: str, items: Recorded, around: Around) -> EarlierTry | _Ended | None:
        """The solver's ask for what the rewrite recorded, and its input run on the real code:
        None when the input took the wanted side, else how the try failed or why it ended."""
        given = self.given
        answer = around.ask(items.items, given)
        if answer is None:
            return _Ended(BUDGET_SPENT)
        if isinstance(answer, Error):
            return EarlierTry(expression, f"the solver failed: {answer.detail}")
        if not isinstance(answer, Sat):
            return EarlierTry(expression, f"the solver answered {type(answer).__name__.lower()}")
        record = around.run_input(apply(given.origin, answer.model), given.plan)
        if isinstance(record, Stop):
            return _Ended(record.reason)
        if reached(record, given):
            return None
        written = _written(record.args, self.kinds)
        missed = NO_GUARDED_LINE if given.no_fork else "took the other side"
        return EarlierTry(expression, f"the input {written} {missed}")


def _written(args: Mapping[str, object], kinds: Kinds) -> str:
    """An input's arguments, each name as JSON and each value as ``args_text`` writes it."""
    return (
        "{"
        + ", ".join(f"{json.dumps(name)}: {text}" for name, text in args_text(args, kinds))
        + "}"
    )
