"""The one way any LLM tool reaches a model: ``Connection.ask``."""

from __future__ import annotations

import dataclasses

from pyct.llm.caller import Caller
from pyct.llm.ledger import Ledger
from pyct.llm.recording import Recording
from pyct.llm.tool import Tool
from pyct.results.llm_asks import AskCost, Reply, Unanswered, Why
from pyct.run.notes import LimitReached
from pyct.run.tell import Noted

# why an ask is refused once the run's tokens reach --llm-limit
LIMIT_REACHED = "token limit reached"


class Connection:
    """Asks through its caller, numbers each place's tries, records each reply, and counts each
    ask in the run's ledger, which refuses an ask once the run's tokens reach the limit.

    The try number is the connection's: the first ask a run makes about one tool and place is
    try 1, the next about the same tool and place try 2, whatever the earlier tries returned.
    """

    def __init__(
        self,
        caller: Caller,
        ledger: Ledger | None = None,
        recording: Recording | None = None,
        noted: Noted | None = None,
    ) -> None:
        self.caller = caller
        self.ledger = Ledger() if ledger is None else ledger
        self.recording = recording
        self.noted = noted
        self.tries: dict[tuple[str, str], int] = {}

    def ask(self, tool: Tool, place: str, text: str) -> Reply | Unanswered:
        """Ask about ``place`` with ``text``, the exact request. ``place`` stays the same between
        two runs of the same code: no absolute path, time or count.

        Once the limit is reached the answer is ``LIMIT`` and no request leaves. A reply is
        recorded, then counted; the ask whose tokens reach the limit says so once, through
        ``noted``. A replayed reply reaches the tool with no tokens, as a replay spends none.
        """
        key = (tool.name, place)
        attempt = self.tries.get(key, 0) + 1
        self.tries[key] = attempt
        reached = self.ledger.reached
        if reached:
            answer = Unanswered(Why.LIMIT, LIMIT_REACHED, AskCost(attempt))
        else:
            answer = self.caller.call(tool, place, attempt, text)
        if isinstance(answer, Reply) and self.recording is not None:
            self.recording.write(tool, place, text, answer)
        self.ledger.count(tool.name, answer)
        if not reached and self.ledger.reached and self.noted is not None:
            self.noted(LimitReached())
        return self._handed(answer)

    def _handed(self, answer: Reply | Unanswered) -> Reply | Unanswered:
        """The answer as its tool reads it: the tokens left, and a replay's spent tokens 0."""
        cost = dataclasses.replace(answer.cost, tokens_left=self.ledger.left)
        if cost.replayed:
            cost = dataclasses.replace(cost, tokens_in=0, tokens_out=0)
        return dataclasses.replace(answer, cost=cost)
