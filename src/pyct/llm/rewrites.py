"""The rewrites tool: the request text a rewrites ask sends, and its reply handed back as it came.

It implements ``pyct.rewrite.provider.RewriteProvider`` on top of ``Connection.ask``. The place
is the condition's site, ``module:line:col``, so the connection numbers each place's tries across
the run; the request text names the condition by its place too, never by its file's path.
"""

from __future__ import annotations

from pyct.config.llm import REWRITES_TOOL
from pyct.llm.connection import Connection
from pyct.llm.tool import Tool
from pyct.results.llm_asks import Unanswered
from pyct.rewrite.condition import FORM
from pyct.rewrite.provider import RewriteReply, RewriteRequest, Side

REWRITES = Tool(REWRITES_TOOL, 6000)


class LlmRewrites:
    """Asks the connection for a rewrite; ``pyct.rewrite.condition`` reads the reply."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def rewrite(self, request: RewriteRequest) -> RewriteReply | Unanswered:
        answer = self.connection.ask(REWRITES, request.place, request_text(request))
        if isinstance(answer, Unanswered):
            return answer
        return RewriteReply(answer.text, answer.cost)


def request_text(request: RewriteRequest) -> str:
    """The exact text a rewrites ask sends: the task, the condition and the side its line needs,
    the path's earlier conditions, the function's code, the input, the parameters a rewrite may
    not read, the solver's answer, this moment's earlier tries, and the answer's form."""
    parts = [
        "pyct tests one Python function by running it on inputs a solver finds by flipping the"
        " branches each input took. The solver could not answer for the condition below."
        " Rewrite it as an easier condition on the parameters that the inputs taking"
        " the wanted side meet. pyct solves your condition instead, then runs its input on the"
        " real code, and keeps it only when the input takes the wanted side.",
        f"Condition at {request.place}: {request.condition.text}\n"
        f"Wanted side: {_side(request.condition)}",
    ]
    if request.earlier:
        listed = "\n".join(f"{each.text}: {_side(each)}" for each in request.earlier)
        parts.append(f"The conditions the path took before it, nearest last:\n{listed}")
    parts.append(f"The function's code:\n```python\n{request.code}\n```")
    values = "\n".join(f"{name} = {value}" for name, value in request.args)
    parts.append(
        "The input whose path the solver extended, each value as JSON, or as Python writes it"
        f" when JSON cannot hold it:\n{values}"
    )
    if request.unreadable:
        parts.append(
            "Parameters your condition may not read, since each holds an object: "
            + ", ".join(request.unreadable)
        )
    parts.append(f"The solver's answer for the condition: {request.answer}")
    if request.tries:
        tried = "\n".join(f"{each.rewrite}  ->  {each.reason}" for each in request.tries)
        parts.append(f"Your earlier rewrites at this condition, and why each failed:\n{tried}")
    parts.append(FORM)
    return "\n\n".join(parts)


def _side(side: Side) -> str:
    return "true" if side.side else "false"
