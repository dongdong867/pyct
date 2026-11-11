"""Connection.ask numbers each place's tries, asks through its caller, and counts each ask in
the ledger, which refuses an ask once the run's tokens reach the limit."""

from dataclasses import dataclass, field
from pathlib import Path

from pyct.cli.llm import note_line
from pyct.config.llm import DEFAULT_LIMIT, LlmSettings, Model
from pyct.llm.connection import Connection
from pyct.llm.ledger import Ledger
from pyct.llm.replay import ReplayCaller, read_replay
from pyct.llm.tool import Tool
from pyct.results.llm_asks import AskCost, Reply, Unanswered, Why
from pyct.run.notes import LimitReached, Note
from tests.acceptance.llm_stub import write_recording

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
    assert second == Reply("[]", AskCost(2, tokens_left=DEFAULT_LIMIT))
    assert caller.calls == [
        ("seeds", "m::f", 1, "one"),
        ("seeds", "m::f", 2, "two"),
        ("seeds", "m::g", 1, "three"),
        ("summaries", "m::f", 1, "four"),
    ]


@dataclass
class SpendingCaller:
    """Answers each ask with a reply that spent the next of ``spends``, in and out."""

    spends: list[tuple[int, int]]
    calls: int = 0

    def call(self, tool: Tool, place: str, attempt: int, text: str) -> Reply | Unanswered:
        tokens_in, tokens_out = self.spends[self.calls]
        self.calls += 1
        return Reply("[]", AskCost(attempt, tokens_in, tokens_out, seconds=0.5))


def asked(connection: Connection, times: int) -> list[Reply | Unanswered]:
    return [connection.ask(SEEDS, "m::f", "text") for _ in range(times)]


# llm-token-limit-no-more-asks
def test_past_the_limit_no_request_leaves_and_the_limit_is_said_once() -> None:
    caller = SpendingCaller([(1000, 500)])
    notes: list[Note] = []
    connection = Connection(caller, Ledger(1000), noted=notes.append)

    first, second, third = asked(connection, 3)

    assert isinstance(first, Reply)
    assert caller.calls == 1
    for refused in (second, third):
        assert isinstance(refused, Unanswered)
        assert (refused.why, refused.reason) == (Why.LIMIT, "token limit reached")
    assert notes == [LimitReached()]
    assert note_line(LimitReached()) == "llm: token limit reached; no more asks"


# llm-token-limit-default
def test_the_default_limit_refuses_the_ask_after_the_one_that_reached_100_000() -> None:
    caller = SpendingCaller([(99_000, 999), (5, 5)])
    connection = Connection(caller, Ledger(LlmSettings(("seeds",)).limit))

    first, second, third = asked(connection, 3)

    assert isinstance(first, Reply) and isinstance(second, Reply)
    assert first.cost.tokens_left == 1
    assert isinstance(third, Unanswered) and third.why is Why.LIMIT


# llm-token-limit-replay-stops-where-the-recording-did
def test_a_replay_counts_each_reply_at_its_recorded_tokens(tmp_path: Path) -> None:
    recording = write_recording(
        tmp_path / "r.jsonl",
        [
            {"place": "m::f", "try": 1, "tokens": {"in": 1200, "out": 300}},
            {"place": "m::f", "try": 2},
        ],
    )
    notes: list[Note] = []
    ledger = Ledger(1000)
    connection = Connection(ReplayCaller(read_replay(recording)), ledger, noted=notes.append)

    first, second = asked(connection, 2)

    assert isinstance(first, Reply)
    assert isinstance(second, Unanswered) and second.why is Why.LIMIT
    assert notes == [LimitReached()]
    use = ledger.use(Model("openai", "gpt-6-luna"), ("seeds",))
    assert (use.asks, use.replayed, use.skipped) == (0, 1, 1)
    assert (use.tokens_in, use.tokens_out) == (0, 0)


# llm-tokens-reported-skipped
def test_every_ask_counts_once_as_asked_replayed_or_skipped() -> None:
    ledger = Ledger()
    connection = Connection(FakeCaller(), ledger)

    asked(connection, 3)

    use = ledger.use(Model("openai", "gpt-6-luna"), ("seeds",))
    assert (use.asks, use.replayed, use.skipped) == (2, 0, 1)
