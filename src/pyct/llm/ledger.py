"""The run's token ledger: ``--llm-limit``, and per tool what its asks got, spent and waited."""

from __future__ import annotations

from dataclasses import dataclass

from pyct.config.llm import DEFAULT_LIMIT, Model
from pyct.results.llm_asks import LlmUse, Reply, Unanswered


@dataclass
class Tally:
    """One tool's asks: answered by the model, a wrong-form reply included; answered from a
    replay's file; and given no answer. Then the tokens spent in this run and the seconds
    waited."""

    asks: int = 0
    replayed: int = 0
    skipped: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0


class Ledger:
    """One per run, shared by every tool. Every ask lands in exactly one of a tool's three
    counts.

    The limit reads the charged total: the tokens spent, in and out together, plus each replayed
    reply's recorded tokens, so a replay stops asking where the recorded run did. An ask that
    starts under the limit can end over it; asks go one at a time, so by at most one ask.
    """

    def __init__(self, limit: int = DEFAULT_LIMIT) -> None:
        self.limit = limit
        self.charged = 0
        self.tallies: dict[str, Tally] = {}

    @property
    def reached(self) -> bool:
        """Whether the charged total has reached the limit: no ask leaves after this."""
        return self.charged >= self.limit

    @property
    def left(self) -> int:
        """The tokens left under the limit, 0 once it is reached."""
        return max(self.limit - self.charged, 0)

    def count(self, tool: str, answer: Reply | Unanswered) -> None:
        """Count one ask by ``tool`` with its answer, before the answer reaches the tool."""
        tally = self.tallies.setdefault(tool, Tally())
        cost = answer.cost
        tally.seconds += cost.seconds
        if isinstance(answer, Unanswered):
            tally.skipped += 1
            return
        self.charged += cost.tokens_in + cost.tokens_out
        if cost.replayed:
            tally.replayed += 1
            return
        tally.asks += 1
        tally.tokens_in += cost.tokens_in
        tally.tokens_out += cost.tokens_out

    def use(self, model: Model, tools: tuple[str, ...]) -> LlmUse:
        """The totals over every tool, as the summary writes them."""
        tallies = self.tallies.values()
        return LlmUse(
            model=str(model),
            tools=tools,
            asks=sum(tally.asks for tally in tallies),
            replayed=sum(tally.replayed for tally in tallies),
            skipped=sum(tally.skipped for tally in tallies),
            tokens_in=sum(tally.tokens_in for tally in tallies),
            tokens_out=sum(tally.tokens_out for tally in tallies),
            seconds=sum(tally.seconds for tally in tallies),
        )
