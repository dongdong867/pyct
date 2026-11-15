"""A fake ``RewriteProvider`` that answers fixed text, and ``run()`` on a target in
``targets/rewrites/`` with rewrites on, for the rewrites story's acceptance tests.

The fake numbers its tries per place and charges each reply's tokens against a limit as the
connection does, so a test reads the try numbers the stderr lines carry and can reach the limit.
No test here calls a model or sends anything off the machine.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from pyct.cli.llm import note_line
from pyct.config.limits import Limits
from pyct.config.llm import DEFAULT_LIMIT
from pyct.config.solver_timeout import SolverTimeout
from pyct.results.coverage import Coverage
from pyct.results.llm_asks import AskCost, Unanswered, Why
from pyct.results.record import InputRecord, RunResult
from pyct.rewrite.provider import RewriteReply, RewriteRequest
from pyct.run import model_runs
from pyct.run.helpers import Helpers
from pyct.run.isolation import Isolation
from pyct.run.notes import Note
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import interception, load_target
from pyct.run.tell import Tell
from tests.acceptance.harness import REPO_ROOT

# a solver limit short enough that `float(s) == 1e-30` runs out of it at once
SHORT = Limits(solver_timeout=SolverTimeout(1.0))
# the tokens in and out each reply the fake gives costs
TOKENS = (120, 30)


def file_of(name: str) -> str:
    """The file of the target module ``targets.rewrites.<name>``, as its sites name it."""
    return str(REPO_ROOT / "targets" / "rewrites" / f"{name}.py")


@dataclass
class FakeRewrites:
    """Answers the n-th ask with the n-th reply, the last one again past the end, after
    ``delay`` seconds, and keeps each request. Each reply costs ``TOKENS``; once they reach
    ``limit`` an ask gets ``limit`` back, as the connection's does."""

    replies: Sequence[str | Unanswered]
    delay: float = 0.0
    limit: int = DEFAULT_LIMIT
    requests: list[RewriteRequest] = field(default_factory=list)
    tries: dict[str, int] = field(default_factory=dict)
    charged: int = 0

    def rewrite(self, request: RewriteRequest) -> RewriteReply | Unanswered:
        self.requests.append(request)
        attempt = self.tries.get(request.place, 0) + 1
        self.tries[request.place] = attempt
        if self.charged >= self.limit:
            return Unanswered(Why.LIMIT, "token limit reached", AskCost(attempt))
        time.sleep(self.delay)
        reply = self.replies[min(len(self.requests), len(self.replies)) - 1]
        if isinstance(reply, Unanswered):
            return dataclasses.replace(reply, cost=self._cost(attempt, 0, 0))
        return RewriteReply(reply, self._cost(attempt, *TOKENS))

    def _cost(self, attempt: int, tokens_in: int, tokens_out: int) -> AskCost:
        self.charged += tokens_in + tokens_out
        left = max(self.limit - self.charged, 0)
        return AskCost(attempt, tokens_in, tokens_out, self.delay, tokens_left=left)


@dataclass
class Rewritten:
    """What a run with rewrites gave: its result, each input as it finished, and the stderr line
    each note gives, in the order they came."""

    result: RunResult
    records: list[InputRecord]
    said: list[str]


def run_rewrites(
    spec: str,
    seed: Mapping[str, object],
    provider: FakeRewrites | None,
    limits: Limits = SHORT,
) -> Rewritten:
    """``run()`` on ``spec`` from ``seed`` inside the block that substitutes its package, every
    input in this process and each rewrite in a child of it, with ``provider`` as the rewrites
    helper (none for a plain run)."""
    records: list[InputRecord] = []
    said: list[str] = []

    def report(record: InputRecord, _coverage: Coverage) -> None:
        records.append(record)
        said.append(f"input {len(records)}")

    def noted(note: Note) -> None:
        line = note_line(note)
        if line is not None:
            said.append(line)

    setup = Setup(isolation=Isolation.IN_PROCESS, helpers=Helpers(rewrites=provider))
    tell = Tell(report=report, noted=noted)
    with interception(spec):
        result = run(load_target(spec), seed, limits=limits, setup=setup, tell=tell)
    return Rewritten(result, records, said)


def llm_said(said: Sequence[str]) -> list[str]:
    """The ``llm:`` lines alone."""
    return [line for line in said if line.startswith("llm: ")]


@pytest.fixture(autouse=True)
def one_thread(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """pyct's process as a run has it, one thread: pytest-timeout's watch runs another, and a
    rewrite's child forks beside it safely, since it takes no lock the call needs. The target's
    substituted code is kept in a cache folder of the test's own."""
    monkeypatch.setattr(model_runs, "running", lambda: 1)
    monkeypatch.setenv("PYCT_CACHE_DIR", str(tmp_path))
