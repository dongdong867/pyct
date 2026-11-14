"""The summaries tool: the request text a summaries ask sends, and its reply's last code block.

It implements ``pyct.run.summaries.SummaryProvider`` on top of ``Connection.ask``. The place is
the loop's site, ``module:line:col``, so the connection numbers each place's tries across the run;
the request text names the loop by its place too, never by its file's path.
"""

from __future__ import annotations

from pyct.config.llm import SUMMARIES_TOOL
from pyct.llm.connection import Connection
from pyct.llm.replies import last_code_block
from pyct.llm.tool import Tool
from pyct.results.llm_asks import AskCost, Unanswered
from pyct.run.code_context import MARK_END, MARK_START
from pyct.run.summaries import ShownRun, SummaryReply, SummaryRequest
from pyct.run.summary_checks import answer_form

SUMMARIES = Tool(SUMMARIES_TOOL, 6000)

# why a reply with no code block gives no formula
NO_CODE_BLOCK = "no code block"

# the operations pyct follows a value through, checked against core on 2026-11-14
FOLLOWS = (
    "pyct follows a value through these operations, so a formula built from them gives a value"
    " pyct can solve for:\n"
    "- int: compares, + - * / // %, divmod, unary -, abs, x ** n with a plain n, int, float,"
    " str, chr, min, max, sum, sorted, round, math.floor, math.ceil, math.trunc.\n"
    "- float: compares, + - * / // %, divmod, unary -, abs, int, float, round with one"
    " argument, min, max, sum, math.sqrt, math.floor, math.ceil, math.trunc, math.fabs,"
    " math.isnan, math.isinf, math.isfinite.\n"
    "- bool: compares, arithmetic, & | ^ between bools, int, float.\n"
    "- str: compares, len, +, s * k with a plain k, s[i], slices, sep.join, split, rsplit,"
    " partition, splitlines, find, rfind, index, rindex, count, startswith, endswith, upper,"
    " lower, casefold, capitalize, title, swapcase, strip, lstrip and rstrip with plain"
    " characters, zfill, center, ljust, rjust, replace, removeprefix, removesuffix, isdigit,"
    " isdecimal, isnumeric, isalpha, isalnum, isspace, isupper, islower, isascii, isprintable,"
    " int, float, ord.\n"
    "- list: len, L[i], slices, +, L * k, sum, min, max, sorted.\n"
    "- dict: len, d[k], d.get(k).\n"
    "An if statement, and, or and not choose between values rather than compute one. pyct does"
    " not follow bit operations on ints, ~, ** on a float or with a value pyct follows as the"
    " exponent, bin, hex, oct, bit_length, encode, decode, bytes, repr, hash, format, f-strings"
    " with text around the value, the re module, or sets."
)


class LlmSummaries:
    """Asks the connection for a loop's summary and reads the reply's last code block."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def summarize(self, request: SummaryRequest) -> SummaryReply | Unanswered:
        answer = self.connection.ask(SUMMARIES, request.place, request_text(request))
        if isinstance(answer, Unanswered):
            return answer
        return summary_reply(answer.text, answer.cost)


def summary_reply(text: str, cost: AskCost) -> SummaryReply:
    """The reply as the tool reads it: its last code block, or why it gives none."""
    code = last_code_block(text)
    if code is None:
        return SummaryReply("", cost, ignored=NO_CODE_BLOCK)
    return SummaryReply(code, cost)


def request_text(request: SummaryRequest) -> str:
    """The exact text a summaries ask sends: the task, the loop's code, the names going in and
    the changed names, the recorded runs, the earlier tries at this loop, the operations pyct
    follows, and the answer's form."""
    parts = [
        "pyct tests one Python function by running it on inputs a solver finds by flipping the"
        " branches each input took. A line after the loop below is still missed, since a"
        " condition that guards it reads a value the loop changed, which pyct no longer"
        " follows. Write a formula that gives the values the loop leaves in its changed names"
        " from the values going into it, without running the loop. pyct checks the formula on"
        " the loop's recorded runs, then that it can follow the values the formula gives.",
        f"Loop at {request.place}, marked in the code by the comments `{MARK_START}` and"
        f" `{MARK_END}`. The function's code, then the code of the functions it calls in its"
        f" package:\n```python\n{request.code}\n```",
        f"Names going in, the formula's parameters: {', '.join(request.parameters)}\n"
        f"Changed names, the formula's answer: {', '.join(request.changed)}",
        "The loop's recorded runs, each as the values going in at its start, then the changed"
        " values at its end, as JSON:\n" + "\n".join(_run(each) for each in request.runs),
    ]
    if request.tries:
        tried = "\n".join(
            f"```python\n{each.formula.rstrip()}\n```\nIt failed: {each.reason}"
            for each in request.tries
        )
        parts.append(f"Your earlier formulas at this loop, and why each failed:\n{tried}")
    parts.append(FOLLOWS)
    parts.append(answer_form(request.parameters, request.changed))
    return "\n\n".join(parts)


def _run(run: ShownRun) -> str:
    going_in = ", ".join(f"{name} = {value}" for name, value in run.going_in)
    changed = ", ".join(f"{name} = {value}" for name, value in run.changed)
    return f"{going_in}  ->  {changed}"
