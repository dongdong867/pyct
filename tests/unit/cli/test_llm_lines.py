"""The lines that end stderr's run summary with ``--llm``: the counts, then the recording."""

from pyct.cli.llm import Started, counts_line
from pyct.config.llm import Model
from pyct.llm.build import Built, Unusable
from pyct.llm.connection import Connection
from pyct.llm.providers import PROVIDERS
from pyct.llm.tool import Tool
from pyct.results.llm_asks import AskCost, LlmUse, Reply, Unanswered, Why
from pyct.run.helpers import Helpers

MODEL = Model("openai", "gpt-6-luna")


# llm-tokens-reported-summary-and-stderr
def test_the_counts_line_says_the_asks_the_tokens_and_the_wait() -> None:
    use = LlmUse(
        "openai:gpt-6-luna", ("seeds",), asks=1, tokens_in=1200, tokens_out=300, seconds=12.3
    )

    assert counts_line(use) == (
        "llm: 1 asks, 0 replayed, 0 skipped, 1200 tokens in, 300 out, 12.3 s waiting"
    )


class Answering:
    def call(self, tool: Tool, place: str, attempt: int, text: str) -> Reply | Unanswered:
        return Reply("[]", AskCost(attempt, 1200, 300, 12.3))


def test_a_connection_with_no_recording_closes_on_the_counts_alone() -> None:
    connection = Connection(Answering())
    connection.ask(Tool("seeds", 4000), "m::f", "text")
    started = Started(Helpers(), "llm: start", Built(Helpers(), MODEL, connection), ("seeds",))

    assert started.closing() == (
        "llm: 1 asks, 0 replayed, 0 skipped, 1200 tokens in, 300 out, 12.3 s waiting",
    )


def test_an_llm_that_could_not_be_used_closes_on_no_line() -> None:
    unusable = Unusable(Why.NO_KEY, PROVIDERS["openai"])
    built = Built(Helpers(), MODEL, unusable=unusable)
    started = Started(Helpers(), "llm: no key", built, ("seeds",))

    assert started.closing() == ()
    assert started.use() == LlmUse("openai:gpt-6-luna", ("seeds",))
