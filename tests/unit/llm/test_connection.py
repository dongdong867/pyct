"""Connection.ask numbers each place's tries and asks through its caller."""

from dataclasses import dataclass, field

from pyct.llm.connection import Connection
from pyct.llm.tool import Tool
from pyct.results.llm_asks import AskCost, Reply, Unanswered, Why

SEEDS = Tool("seeds", 4000)
OTHER = Tool("summaries", 4000)


@dataclass
class FakeCaller:
    calls: list[tuple[str, str, int, str]] = field(default_factory=list)

    def call(self, tool: Tool, place: str, attempt: int, text: str) -> Reply | Unanswered:
        self.calls.append((tool.name, place, attempt, text))
        if attempt == 1:
            return Unanswered(Why.TIMED_OUT, "no reply in 30 s", AskCost(attempt))
        return Reply("[]", AskCost(attempt))


def test_each_tool_and_place_counts_its_own_tries_whatever_they_returned() -> None:
    caller = FakeCaller()
    connection = Connection(caller)

    first = connection.ask(SEEDS, "m::f", "one")
    second = connection.ask(SEEDS, "m::f", "two")
    connection.ask(SEEDS, "m::g", "three")
    connection.ask(OTHER, "m::f", "four")

    assert isinstance(first, Unanswered)
    assert second == Reply("[]", AskCost(2))
    assert caller.calls == [
        ("seeds", "m::f", 1, "one"),
        ("seeds", "m::f", 2, "two"),
        ("seeds", "m::g", 1, "three"),
        ("summaries", "m::f", 1, "four"),
    ]
