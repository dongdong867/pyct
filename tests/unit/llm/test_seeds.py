"""The seeds tool writes the request text from a SeedRequest and reads the reply's array."""

from dataclasses import dataclass, field

from pyct.config.goal import Goal
from pyct.llm.connection import Connection
from pyct.llm.seeds import SEED_FORM, SEEDS, LlmSeeds, request_text
from pyct.llm.tool import Tool
from pyct.results.llm_asks import AskCost, Reply, Unanswered, Why
from pyct.run.llm_seeds import SeedReply, SeedRequest

REQUEST = SeedRequest(
    place="targets.llm.seeds::f",
    code="# targets.llm.seeds.f\ndef f(x: int):\n    return sign(x)\n\n# targets.llm.helpers.sign\n"
    "def sign(x: int) -> int:\n    return 0",
    signature="(x: int)",
    seeds=('{"x": 0}',),
)
COST = AskCost(1, 10, 2, 0.5)


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

    reply = LlmSeeds(Connection(caller)).seeds(REQUEST)

    assert reply == SeedReply(('{"x": 1234}', '{"x": 7}'), COST)
    assert caller.asked == [(SEEDS, "targets.llm.seeds::f", request_text(REQUEST))]


def test_a_reply_with_no_array_is_ignored() -> None:
    reply = LlmSeeds(Connection(Answering(Reply("x should be 1234", COST)))).seeds(REQUEST)

    assert reply == SeedReply((), COST, ignored="no JSON array in the reply")


def test_an_ask_with_no_reply_is_handed_back() -> None:
    unanswered = Unanswered(Why.TIMED_OUT, "no reply in 30 s", COST)

    assert LlmSeeds(Connection(Answering(unanswered))).seeds(REQUEST) == unanswered
