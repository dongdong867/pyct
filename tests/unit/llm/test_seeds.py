"""The seeds tool writes the request text from a SeedRequest and reads the reply's array."""

import dataclasses
from dataclasses import dataclass, field

from pyct.config.goal import Goal
from pyct.config.llm import DEFAULT_LIMIT
from pyct.llm.connection import Connection
from pyct.llm.recording import Recording
from pyct.llm.seeds import SEED_FORM, SEEDS, LlmSeeds, request_text
from pyct.llm.tool import Tool
from pyct.results.llm_asks import AskCost, Reply, Unanswered, Why
from pyct.run.llm_seeds import SeedReply, SeedRequest

# a connection whose replies this test does not read back
NOT_RECORDED = Recording(None, "not recorded in this test")

REQUEST = SeedRequest(
    place="targets.llm.seeds::f",
    code="# targets.llm.seeds.f\ndef f(x: int):\n    return sign(x)\n\n# targets.llm.helpers.sign\n"
    "def sign(x: int) -> int:\n    return 0",
    signature="(x: int)",
    seeds=('{"x": 0}',),
)
COST = AskCost(1, 10, 2, 0.5)
# the cost as the connection hands it on, with the tokens the run has left
HANDED = dataclasses.replace(COST, tokens_left=DEFAULT_LIMIT - 12)


@dataclass
class Answering:
    answer: Reply | Unanswered
    asked: list[tuple[Tool, str, str]] = field(default_factory=list)

    def call(self, tool: Tool, place: str, attempt: int, text: str) -> Reply | Unanswered:
        self.asked.append((tool, place, text))
        return self.answer


def test_the_request_holds_the_code_the_signature_the_seeds_the_goal_and_the_form() -> None:
    text = request_text(REQUEST)

    assert REQUEST.code in text
    assert "Signature: (x: int)" in text
    assert '\n{"x": 0}' in text
    assert "Goal: coverage." in text
    assert SEED_FORM in text
    assert "JSON array of at most 5 seed objects" in text


def test_a_request_with_no_seeds_of_the_user_s_quotes_none() -> None:
    text = request_text(SeedRequest("m::f", "def f(x): pass", "(x)", (), goal=Goal.BUGS))

    assert "user's seeds" not in text
    assert "Goal: bugs." in text


def test_a_seeds_ask_asks_about_the_target_s_spec_with_the_request_text() -> None:
    caller = Answering(Reply('[{"x": 1234}, {"x": 7}]', COST))

    reply = LlmSeeds(Connection(caller, NOT_RECORDED)).seeds(REQUEST)

    assert reply == SeedReply(('{"x": 1234}', '{"x": 7}'), HANDED)
    assert caller.asked == [(SEEDS, "targets.llm.seeds::f", request_text(REQUEST))]


def test_a_reply_with_no_array_is_ignored() -> None:
    connection = Connection(Answering(Reply("x should be 1234", COST)), NOT_RECORDED)

    reply = LlmSeeds(connection).seeds(REQUEST)

    assert reply == SeedReply((), HANDED, ignored="no JSON array pyct can read in the reply")


def test_an_ask_with_no_reply_is_handed_back() -> None:
    unanswered = Unanswered(Why.TIMED_OUT, "no reply in 30 s", AskCost(1, seconds=0.5))

    handed = LlmSeeds(Connection(Answering(unanswered), NOT_RECORDED)).seeds(REQUEST)

    assert handed == dataclasses.replace(
        unanswered, cost=dataclasses.replace(unanswered.cost, tokens_left=DEFAULT_LIMIT)
    )
