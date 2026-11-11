"""The one way any LLM tool reaches a model: ``Connection.ask``."""

from __future__ import annotations

from pyct.llm.caller import Caller
from pyct.llm.tool import Tool
from pyct.results.llm_asks import Reply, Unanswered


class Connection:
    """Asks through its caller, and numbers each place's tries.

    The try number is the connection's: the first ask a run makes about one tool and place is
    try 1, the next about the same tool and place try 2, whatever the earlier tries returned.
    """

    def __init__(self, caller: Caller) -> None:
        self.caller = caller
        self.tries: dict[tuple[str, str], int] = {}

    def ask(self, tool: Tool, place: str, text: str) -> Reply | Unanswered:
        """Ask about ``place`` with ``text``, the exact request. ``place`` stays the same between
        two runs of the same code: no absolute path, time or count."""
        key = (tool.name, place)
        attempt = self.tries.get(key, 0) + 1
        self.tries[key] = attempt
        return self.caller.call(tool, place, attempt, text)
