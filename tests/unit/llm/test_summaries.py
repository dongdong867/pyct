"""The summaries tool writes the request text from a SummaryRequest, asks about the loop's site,
and reads the reply's last code block."""

import dataclasses
from dataclasses import dataclass, field

from pyct.config.llm import DEFAULT_LIMIT
from pyct.llm.connection import Connection
from pyct.llm.summaries import FOLLOWS, SUMMARIES, LlmSummaries, request_text
from pyct.llm.tool import Tool
from pyct.results.llm_asks import AskCost, Reply, Unanswered, Why
from pyct.run.code_context import MARK_END, MARK_START
from pyct.run.summaries import EarlierFormula, ShownRun, SummaryReply, SummaryRequest
from pyct.run.summary_checks import answer_form
from tests.acceptance.llm_stub import NO_RECORDING

CODE = (
    f"def counts(s):\n    t = 0\n    {MARK_START}\n    for c in s:\n        t += 1\n    {MARK_END}"
)
REQUEST = SummaryRequest(
    place="m:10:4",
    code=CODE,
    parameters=("s", "t"),
    changed=("t",),
    runs=(
        ShownRun((("s", '"ab"'), ("t", "0")), (("t", "0"),)),
        ShownRun((("s", '"zz"'), ("t", "0")), (("t", "2"),)),
    ),
)
COST = AskCost(1, 10, 2, 0.5)
HANDED = dataclasses.replace(COST, tokens_left=DEFAULT_LIMIT - 12)
FORMULA = 'def summary(s, t):\n    return {"t": t + s.count("z")}\n'


@dataclass
class Answering:
    answer: Reply | Unanswered
    asked: list[tuple[Tool, str, str]] = field(default_factory=list)

    def call(self, tool: Tool, place: str, attempt: int, text: str) -> Reply | Unanswered:
        self.asked.append((tool, place, text))
        return self.answer


def test_the_request_holds_the_loop_its_names_its_runs_what_pyct_follows_and_the_form() -> None:
    text = request_text(REQUEST)

    assert "Write a formula that gives the values the loop leaves in its changed names" in text
    assert f"Loop at m:10:4, marked in the code by the comments `{MARK_START}`" in text
    assert f"```python\n{CODE}\n```" in text
    assert "Names going in, the formula's parameters: s, t\n" in text
    assert "Changed names, the formula's answer: t" in text
    assert 'as JSON:\ns = "ab", t = 0  ->  t = 0\ns = "zz", t = 0  ->  t = 2' in text
    assert "earlier formulas" not in text
    assert text.endswith(f"{FOLLOWS}\n\n{answer_form(('s', 't'), ('t',))}")


def test_the_form_names_the_function_its_parameters_and_each_changed_name() -> None:
    form = answer_form(("s", "t"), ("t", "u"))

    assert "def summary(s, t):" in form
    assert 'return {"t": ..., "u": ...}' in form


def test_the_form_says_the_def_line_holds_no_annotation_default_or_decorator() -> None:
    form = answer_form(("s", "t"), ("t",))

    assert "Write the def line exactly as shown, with no annotation, default or decorator." in form


def test_a_later_request_holds_each_earlier_formula_and_why_it_failed() -> None:
    tried = (EarlierFormula('def summary(s, t):\n    return {"t": len(s)}\n', "at input 1"),)

    text = request_text(dataclasses.replace(REQUEST, tries=tried))

    assert (
        "Your earlier formulas at this loop, and why each failed:\n```python\n"
        'def summary(s, t):\n    return {"t": len(s)}\n```\nIt failed: at input 1'
    ) in text


def test_a_summaries_ask_asks_about_the_loop_and_reads_the_last_code_block() -> None:
    caller = Answering(Reply(f"Sure:\n```python\n{FORMULA}```\n", COST))

    reply = LlmSummaries(Connection(caller, NO_RECORDING)).summarize(REQUEST)

    assert reply == SummaryReply(FORMULA, HANDED)
    assert caller.asked == [(SUMMARIES, "m:10:4", request_text(REQUEST))]
    assert (SUMMARIES.name, SUMMARIES.out_tokens) == ("summaries", 6000)


def test_a_reply_with_no_code_block_is_ignored() -> None:
    caller = Answering(Reply("t counts the z in s", COST))

    reply = LlmSummaries(Connection(caller, NO_RECORDING)).summarize(REQUEST)

    assert reply == SummaryReply("", HANDED, ignored="no code block")


def test_an_ask_with_no_answer_comes_back_as_it_is() -> None:
    skipped = Unanswered(Why.PROVIDER, "provider error", COST)

    reply = LlmSummaries(Connection(Answering(skipped), NO_RECORDING)).summarize(REQUEST)

    assert isinstance(reply, Unanswered)
    assert reply.why is Why.PROVIDER
