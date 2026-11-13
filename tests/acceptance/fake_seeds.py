"""A ``SeedProvider`` for tests through ``run()``: it answers each seeds ask with the reply it is
given and keeps each request, so no test calls a model."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from pyct.results.llm_asks import AskCost, Unanswered
from pyct.results.record import InputRecord
from pyct.run.llm_seeds import SeedReply, SeedRequest

# the cost a fake reply reports
COST = AskCost(attempt=1)


@dataclass
class FakeSeeds:
    """A SeedProvider that answers each ask with ``answer``, after ``delay`` seconds, and keeps
    each request, with how many inputs had been reported when it came."""

    answer: SeedReply | Unanswered
    delay: float = 0.0
    requests: list[SeedRequest] = field(default_factory=list)
    reported_before: list[int] = field(default_factory=list)
    reported: list[InputRecord] = field(default_factory=list)

    def seeds(self, request: SeedRequest) -> SeedReply | Unanswered:
        self.requests.append(request)
        self.reported_before.append(len(self.reported))
        time.sleep(self.delay)
        return self.answer


def replying(*seeds: object, delay: float = 0.0) -> FakeSeeds:
    """A provider whose reply gives ``seeds``, each as its own JSON item."""
    return FakeSeeds(SeedReply(tuple(json.dumps(seed) for seed in seeds), COST), delay)
