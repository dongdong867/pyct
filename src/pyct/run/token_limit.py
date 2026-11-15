"""The token limit as a run's LLM asks meet it: one fact for the whole run.

The first answer that says no token is left under ``--llm-limit``, or an
ask the limit refused, reaches it, whichever tool asked, the seeds ask
included. Every tool that takes missed lines reads it in ``can_ask``, so once
it is reached no tool asks again and no stuck moment comes.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyct.results.llm_asks import AskCost, Unanswered
from pyct.run.llm_seeds import SeedProvider, SeedReply, SeedRequest


class TokenLimit:
    """Whether the run's asks reached the token limit; one per run, shared by every tool."""

    def __init__(self) -> None:
        self.reached = False

    def heard(self, cost: AskCost) -> None:
        """An answer's cost: the limit is reached when it says no token is left. An unknown
        count reaches nothing."""
        if cost.tokens_left == 0:
            self.reached = True

    def reach(self) -> None:
        """An ask the limit refused, or a tool's word that its last reply left no token."""
        self.reached = True


@dataclass(frozen=True)
class HeardSeeds:
    """A seeds provider whose answer the run's token limit hears."""

    provider: SeedProvider
    limit: TokenLimit

    def seeds(self, request: SeedRequest) -> SeedReply | Unanswered:
        answer = self.provider.seeds(request)
        self.limit.heard(answer.cost)
        return answer


def heard_seeds(provider: SeedProvider | None, limit: TokenLimit) -> SeedProvider | None:
    """``provider`` with its answer heard by ``limit``; None with no provider."""
    return None if provider is None else HeardSeeds(provider, limit)
