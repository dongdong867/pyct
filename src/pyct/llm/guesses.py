"""The guesses tool: the request text a guesses ask sends, and its reply read as guesses.

It implements ``pyct.run.guess_asks.GuessProvider`` on top of ``Connection.ask``. The place is the
target's spec and the ask's count among the run's guess asks, ``<spec>#<n>``, so each place is
asked once, the connection numbers its try 1, and a replay answers the n-th guess ask with the
n-th recorded guess reply whatever lines each asks about.
"""

from __future__ import annotations

from pyct.config.llm import GUESSES_TOOL
from pyct.llm.connection import Connection
from pyct.llm.replies import json_items
from pyct.llm.seeds import NO_ARRAY, SEED_FORM
from pyct.llm.tool import Tool
from pyct.results.llm_asks import Unanswered
from pyct.rewrite.provider import Side
from pyct.run.guess_asks import AskedLine, GuessReply, GuessRequest
from pyct.run.guesses import MOST_GUESSES

GUESSES = Tool(GUESSES_TOOL, 4000)

# what each cause the request names says about why its lines were missed
CAUSES = (
    "Why each group of lines was missed: `handler` is an `except` block no raise reached;"
    " `ended before` is a line every input that went its way crashed or ended before; `no fork`"
    " is a line behind a condition pyct cannot follow, `no source found` when it found no value"
    " the condition reads; `summary gave up` and `rewrite gave up` are lines whose condition a"
    " model's formula or easier condition did not help; `not taken` is a line whose condition"
    " the solver gave no answer to."
)


class LlmGuesses:
    """Asks the connection for guesses and reads the reply's array, one item per guess."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def guesses(self, request: GuessRequest) -> GuessReply | Unanswered:
        answer = self.connection.ask(GUESSES, request.place, request_text(request))
        if isinstance(answer, Unanswered):
            return answer
        items = json_items(answer.text)
        if items is None:
            return GuessReply((), answer.cost, ignored=NO_ARRAY)
        return GuessReply(items, answer.cost)


def request_text(request: GuessRequest) -> str:
    """The exact text a guesses ask sends: what the guesses are for, the target and its code, the
    classes of its folder when there are any, each group of missed lines with its cause, the
    conditions on its way and the input that got furthest along it, the seed form, and the
    answer's form."""
    parts = [
        "pyct tests one Python function by running it on inputs, which a solver finds by flipping"
        " the branches each input took. Some lines are still missed, and the solver cannot reach"
        " them. Guess inputs that reach them. pyct runs each guess on the real code, so a guess"
        " that misses costs only time.",
        f"Function: {request.place.rpartition('#')[0]}\nSignature: {request.signature}",
        "The function's code, then the code of the functions it calls in its package:\n"
        f"```python\n{request.code}\n```",
    ]
    if request.classes:
        parts.append(
            "The classes of the function's folder, each under a heading that writes its name as"
            f' a seed\'s "__class__" writes it:\n```python\n{request.classes}\n```'
        )
    parts.append(CAUSES)
    parts.append("The missed lines:\n\n" + "\n\n".join(_asked(each) for each in request.lines))
    parts.append(SEED_FORM)
    parts.append(
        f"Answer with a JSON array of at most {MOST_GUESSES} seed objects, which together reach"
        " as many of the missed lines as they can, and nothing else."
    )
    return "\n\n".join(parts)


def _asked(line: AskedLine) -> str:
    """One group of missed lines: its lines and cause, then the conditions on the way to its
    first line, then the input that got furthest."""
    numbers = ", ".join(str(each) for each in line.lines)
    word = "Line" if len(line.lines) == 1 else "Lines"
    shown = [f"{word} {numbers} of {line.module}: {line.cause}"]
    if line.conditions:
        way = "\n".join(f"- {_condition(each)}" for each in line.conditions)
        shown.append(
            f"The conditions on the way to line {line.lines[0]}, in the order a run meets them,"
            f" each with the side the line needs:\n{way}"
        )
    else:
        shown.append(f"pyct found no condition on the way to line {line.lines[0]}.")
    if line.furthest is None:
        shown.append("No input got along that way.")
    else:
        shown.append(
            f"The input that got furthest along that way, which ended {line.ended}:\n"
            f"{line.furthest}"
        )
    return "\n".join(shown)


def _condition(condition: Side) -> str:
    return f"{condition.text}: {'true' if condition.side else 'false'}"
