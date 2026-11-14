"""The summaries tool: the request text a summaries ask sends, and its reply's last code block.

It implements ``pyct.run.summaries.SummaryProvider`` on top of ``Connection.ask``. The place is
the loop's site, ``module:line:col``, so the connection numbers each place's tries across the run.
"""

from __future__ import annotations

from pyct.config.llm import SUMMARIES_TOOL
from pyct.llm.connection import Connection
from pyct.llm.tool import Tool
from pyct.results.llm_asks import Unanswered
from pyct.run.summaries import SummaryReply, SummaryRequest

SUMMARIES = Tool(SUMMARIES_TOOL, 6000)


class LlmSummaries:
    """Asks the connection for a loop's summary and reads the reply's last code block."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def summarize(self, request: SummaryRequest) -> SummaryReply | Unanswered:
        answer = self.connection.ask(SUMMARIES, request.place, request_text(request))
        if isinstance(answer, Unanswered):
            return answer
        return SummaryReply(answer.text, answer.cost)


def request_text(request: SummaryRequest) -> str:
    """The exact text a summaries ask sends."""
    return f"Loop at {request.place}:\n```python\n{request.code}\n```"
