"""The summaries tool writes the request text from a SummaryRequest, asks about the loss site,
and reads the reply's last code block."""

import dataclasses
from dataclasses import dataclass, field

from pyct.config.llm import DEFAULT_LIMIT
from pyct.llm.connection import Connection
from pyct.llm.summaries import SUMMARIES, LlmSummaries, request_text
from pyct.llm.tool import Tool
from pyct.results.llm_asks import AskCost, Reply, Unanswered, Why
from pyct.run.code_context import marks
from pyct.run.summaries import EarlierFormula, ShownRun, SummaryReply, SummaryRequest
from pyct.run.summary_asks import CallAsk
from pyct.run.summary_checks import answer_form
from tests.acceptance.llm_stub import NO_RECORDING

ABOVE, BELOW = marks("call")
CODE = f"def shifted(n):\n    {ABOVE}\n    k = pow(n, 1, 4)\n    {BELOW}\n    return k"
REQUEST = SummaryRequest(
    place="m:3:8",
    code=CODE,
    parameters=("n",),
    changed=("answer",),
    runs=(
        ShownRun((("n", "3"),), (("answer", "3"),)),
        ShownRun((("n", "6"),), (("answer", "2"),)),
    ),
    call=CallAsk("__pow__", "pow(n, 1, 4)"),
)
COST = AskCost(1, 10, 2, 0.5)
HANDED = dataclasses.replace(COST, tokens_left=DEFAULT_LIMIT - 12)
FORMULA = 'def summary(n):\n    return {"answer": n % 4}\n'


@dataclass
class Answering:
    answer: Reply | Unanswered
    asked: list[tuple[Tool, str, str]] = field(default_factory=list)

    def call(self, tool: Tool, place: str, attempt: int, text: str) -> Reply | Unanswered:
        self.asked.append((tool, place, text))
        return self.answer


def test_a_request_that_holds_runs_back_says_pyct_checks_the_formula_on_them_too() -> None:
    text = request_text(dataclasses.replace(REQUEST, not_shown=1))

    assert (
        "pyct checks the formula on the call's recorded runs, the ones shown below and ones this"
        " request does not show, so a formula that only writes down the runs shown can fail. Then"
        " it checks that it can follow the values the formula gives."
    ) in text


def test_the_form_names_the_function_its_parameters_and_each_changed_name() -> None:
    form = answer_form(("s", "t"), ("t", "u"))

    assert "def summary(s, t):" in form
    assert 'return {"t": ..., "u": ...}' in form


def test_the_form_says_the_def_line_holds_no_annotation_default_or_decorator() -> None:
    form = answer_form(("s", "t"), ("t",))

    assert "Write the def line exactly as shown, with no annotation, default or decorator." in form


def test_a_later_request_holds_each_earlier_formula_and_why_it_failed() -> None:
    tried = (EarlierFormula('def summary(n):\n    return {"answer": n}\n', "at input 1"),)

    text = request_text(dataclasses.replace(REQUEST, tries=tried))

    assert (
        "Your earlier formulas at this call, and why each failed:\n```python\n"
        'def summary(n):\n    return {"answer": n}\n```\nIt failed: at input 1'
    ) in text


def test_a_summaries_ask_asks_about_the_site_and_reads_the_last_code_block() -> None:
    caller = Answering(Reply(f"Sure:\n```python\n{FORMULA}```\n", COST))

    reply = LlmSummaries(Connection(caller, NO_RECORDING)).summarize(REQUEST)

    assert reply == SummaryReply(FORMULA, HANDED)
    assert caller.asked == [(SUMMARIES, "m:3:8", request_text(REQUEST))]
    assert (SUMMARIES.name, SUMMARIES.out_tokens) == ("summaries", 6000)


def test_a_reply_with_no_code_block_is_ignored() -> None:
    caller = Answering(Reply("the answer is n % 4", COST))

    reply = LlmSummaries(Connection(caller, NO_RECORDING)).summarize(REQUEST)

    assert reply == SummaryReply("", HANDED, ignored="no code block")


def test_an_ask_with_no_answer_comes_back_as_it_is() -> None:
    skipped = Unanswered(Why.PROVIDER, "provider error", COST)

    reply = LlmSummaries(Connection(Answering(skipped), NO_RECORDING)).summarize(REQUEST)

    assert isinstance(reply, Unanswered)
    assert reply.why is Why.PROVIDER
