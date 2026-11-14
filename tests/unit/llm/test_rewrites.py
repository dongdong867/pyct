"""The rewrites tool writes the request text from a RewriteRequest and hands the reply back as it
came, asking about the condition's site."""

import dataclasses
from dataclasses import dataclass, field

from pyct.config.llm import DEFAULT_LIMIT
from pyct.llm.connection import Connection
from pyct.llm.rewrites import REWRITES, LlmRewrites, request_text
from pyct.llm.tool import Tool
from pyct.results.llm_asks import AskCost, Reply, Unanswered, Why
from pyct.rewrite.condition import FORM
from pyct.rewrite.provider import EarlierTry, RewriteReply, RewriteRequest, Side
from tests.acceptance.llm_stub import NO_RECORDING

REQUEST = RewriteRequest(
    place="m:3:11",
    condition=Side("float(s) == -1e-30", True),
    earlier=(Side('s.startswith("-")', True),),
    code='def negative(s):\n    if s.startswith("-"):\n        if float(s) == -1e-30:',
    args=(("s", '"-1"'),),
    answer="timeout",
)
COST = AskCost(1, 10, 2, 0.5)
HANDED = dataclasses.replace(COST, tokens_left=DEFAULT_LIMIT - 12)


@dataclass
class Answering:
    answer: Reply | Unanswered
    asked: list[tuple[Tool, str, str]] = field(default_factory=list)

    def call(self, tool: Tool, place: str, attempt: int, text: str) -> Reply | Unanswered:
        self.asked.append((tool, place, text))
        return self.answer


def test_the_request_holds_the_condition_its_path_the_code_the_input_and_the_form() -> None:
    text = request_text(REQUEST)

    assert "could not answer for the condition below." in text
    assert "Condition at m:3:11: float(s) == -1e-30\nWanted side: true" in text
    assert 'nearest last:\ns.startswith("-"): true' in text
    assert REQUEST.code in text
    assert (
        "each value as JSON, or as Python writes it when JSON cannot hold it, and one that holds"
        ' an object as a placeholder in angle brackets:\ns = "-1"'
    ) in text
    assert "The solver's answer for the condition: timeout" in text
    assert "earlier rewrites" not in text
    assert text.endswith(FORM)


def test_the_request_names_the_parameters_a_rewrite_may_not_read() -> None:
    request = dataclasses.replace(REQUEST, unreadable=("o", "l"))

    assert "may not read" not in request_text(REQUEST)
    assert (
        's = "-1"\n\nParameters your condition may not read, since each holds an object: o, l'
        in request_text(request)
    )


def test_a_retry_s_request_holds_each_earlier_try_and_why_it_failed() -> None:
    tried = (EarlierTry('s == "1e-29"', 'the input {"s": "1e-29"} took the other side'),)
    request = dataclasses.replace(REQUEST, earlier=(), tries=tried)

    text = request_text(request)

    assert 's == "1e-29"  ->  the input {"s": "1e-29"} took the other side' in text
    assert "before it" not in text


# what the request says once a value or a reason it shows writes a plain dict's escaped key
ESCAPE_SAID = 'A dict key shown as "!__class__" is the key "__class__" the code reads'


def test_a_request_whose_input_writes_an_escaped_key_says_how_the_code_reads_it() -> None:
    escaped = dataclasses.replace(REQUEST, args=(("d", '{"a": 1, "!__class__": 0}'),))

    assert ESCAPE_SAID not in request_text(REQUEST)
    assert f'd = {{"a": 1, "!__class__": 0}}\n{ESCAPE_SAID}' in request_text(escaped)


def test_a_request_whose_earlier_try_writes_an_escaped_key_says_how_the_code_reads_it() -> None:
    reason = 'the input {"d": {"!!__class__": 0}} took the other side'
    tried = dataclasses.replace(REQUEST, tries=(EarlierTry('d["a"] == 1', reason),))

    assert ESCAPE_SAID in request_text(tried)


def test_a_rewrites_ask_asks_about_the_site_and_hands_the_reply_back() -> None:
    caller = Answering(Reply('s == "-1e-30"', COST))

    reply = LlmRewrites(Connection(caller, NO_RECORDING)).rewrite(REQUEST)

    assert reply == RewriteReply('s == "-1e-30"', HANDED)
    assert caller.asked == [(REWRITES, "m:3:11", request_text(REQUEST))]
    assert (REWRITES.name, REWRITES.out_tokens) == ("rewrites", 6000)


def test_an_ask_with_no_answer_comes_back_as_it_is() -> None:
    skipped = Unanswered(Why.PROVIDER, "provider error", COST)

    reply = LlmRewrites(Connection(Answering(skipped), NO_RECORDING)).rewrite(REQUEST)

    assert isinstance(reply, Unanswered)
    assert reply.why is Why.PROVIDER
