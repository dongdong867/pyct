"""The rewrites tool: the request text a rewrites ask sends, and its reply handed back as it came.

It implements ``pyct.rewrite.provider.RewriteProvider`` on top of ``Connection.ask``. The place
is the condition's site, ``module:line:col``, so the connection numbers each place's tries across
the run; the request text names the condition by its place too, never by its file's path.
"""

from __future__ import annotations

import re

from pyct.config.llm import REWRITES_TOOL
from pyct.llm.connection import Connection
from pyct.llm.tool import Tool
from pyct.results.causes import Reason
from pyct.results.llm_asks import Unanswered
from pyct.results.record import MissWhy
from pyct.rewrite.condition import FORM
from pyct.rewrite.provider import RewriteReply, RewriteRequest, Side

REWRITES = Tool(REWRITES_TOOL, 6000)

# how the code reads a plain dict's key that seed JSON writes escaped (``pyct.binding.seed_keys``)
ESCAPED_KEY = (
    'A dict key shown as "!__class__" is the key "__class__" the code reads, so a condition'
    ' writes it d["__class__"], and a key shown with more "!" before "__class__" holds one "!"'
    " fewer."
)
# a quoted key of one or more "!" then "__class__", as JSON or Python writes it
_ESCAPED = re.compile(r"[\"']!+__class__[\"']")
# what a request says of a condition that recorded no fork, in place of the solver's answer
NOT_FOLLOWED = (
    "pyct does not follow the value the condition below reads, so it recorded no branch there"
    " for the solver to flip."
)
# what a request asks once the solver answered unsat for the condition on the input's path, or
# the condition recorded no fork
OTHER_PATH = (
    "The input's path cannot reach the wanted side as it stands. Write an expression whose"
    " inputs reach it along another path, one you read from the code."
)


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
    not read, the solver's answer, and for ``unsat`` and ``no fork`` the ask for another path,
    this moment's earlier tries, and the answer's form. For ``no fork`` the opening says pyct
    does not follow the value the condition reads, in place of the solver's answer, and the path
    and the input are those of an input that ran the condition."""
    no_fork = request.answer == Reason.NO_FORK
    opening = NOT_FOLLOWED if no_fork else "The solver could not answer for the condition below."
    parts = [
        "pyct tests one Python function by running it on inputs a solver finds by flipping the"
        f" branches each input took. {opening}"
        " Write an expression on the parameters that is equivalent to the condition or narrower,"
        " so that each input meeting it reaches the condition and takes the wanted side, and"
        ' that fixes each value it reads to a concrete one, such as `s == "1e-30"`. pyct'
        " solves your expression alone, with none of the path's earlier conditions, then runs"
        " its input on the real code, and keeps it only when the input takes the wanted side.",
        f"Condition at {request.place}: {request.condition.text}\n"
        f"Wanted side: {_side(request.condition)}",
    ]
    if request.earlier:
        listed = "\n".join(f"{each.text}: {_side(each)}" for each in request.earlier)
        took = "that input's path took" if no_fork else "the path took before it"
        parts.append(f"The conditions {took}, nearest last:\n{listed}")
    parts.append(f"The function's code:\n```python\n{request.code}\n```")
    parts.append(_input(request))
    if request.holders:
        parts.append(
            "Parameters your condition may not read, since each holds an object inside a list,"
            " tuple or dict: " + ", ".join(request.holders)
        )
    parts.extend(_answer(request.answer))
    if request.tries:
        tried = "\n".join(f"{each.rewrite}  ->  {each.reason}" for each in request.tries)
        parts.append(f"Your earlier rewrites at this condition, and why each failed:\n{tried}")
    parts.append(FORM)
    return "\n\n".join(parts)


def _answer(answer: str) -> tuple[str, ...]:
    """The solver's answer, none for ``no fork``, and for ``unsat`` and ``no fork`` the ask for
    another path."""
    if answer == Reason.NO_FORK:
        return (OTHER_PATH,)
    said = f"The solver's answer for the condition: {answer}"
    return (said, OTHER_PATH) if answer == MissWhy.UNSAT else (said,)


def _input(request: RewriteRequest) -> str:
    """The input's values, and how the code reads a plain dict's escaped key when a value or an
    earlier try's reason shows one."""
    values = "\n".join(f"{name} = {value}" for name, value in request.args)
    shown = [value for _, value in request.args] + [each.reason for each in request.tries]
    said = f"\n{ESCAPED_KEY}" if any(_ESCAPED.search(text) for text in shown) else ""
    no_fork = request.answer == Reason.NO_FORK
    whose = (
        "An input that ran the condition" if no_fork else "The input whose path the solver extended"
    )
    return (
        f"{whose}, each value as JSON, or as Python writes it"
        " when JSON cannot hold it, an object as <Name object, built from ARGS>, ARGS the"
        " arguments pyct builds it from, or as <Name object>, and a value that holds an object"
        f" inside a list, tuple or dict as <holds an object>:\n{values}{said}"
    )


def _side(side: Side) -> str:
    return "true" if side.side else "false"
