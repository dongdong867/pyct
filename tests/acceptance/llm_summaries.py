"""A fake ``SummaryProvider`` that answers fixed text, and ``run()`` with summaries on, the
target's package intercepted with the recording of each loop's runs, for the
ask-for-a-stuck-loop-s-summary story's acceptance tests.

The fake reads each reply as ``pyct.llm.summaries`` does and numbers its tries per place as the
connection does, so a test reads the try numbers the stderr lines carry. No test here calls a
model or sends anything off the machine.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from pyct.cli.llm import note_line
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.llm.summaries import summary_reply
from pyct.results.coverage import Coverage
from pyct.results.llm_asks import AskCost, Unanswered
from pyct.results.record import InputRecord, RunResult
from pyct.run import model_runs
from pyct.run.helpers import Helpers
from pyct.run.isolation import Isolation
from pyct.run.notes import Note
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.summaries import SummaryReply, SummaryRequest
from pyct.run.target import interception, load_target
from pyct.run.tell import Tell
from tests.acceptance.harness import REPO_ROOT

# `F` and `G` of the criteria
F = str(REPO_ROOT / "targets" / "why" / "stuck.py")
G = str(REPO_ROOT / "targets" / "summaries" / "loops.py")
COUNTS = "targets.why.stuck::counts"
COUNTED = "targets.why.stuck::counted"
SEED = {"s": "ab"}
# a plateau that ends the run 3 inputs after its first moment, so it holds one moment
ONE_MOMENT = Limits(plateau=Plateau(8))
# the reply `COUNT` of the criteria
COUNT = 'Here it is:\n```python\ndef summary(s, t):\n    return {"t": t + s.count("z")}\n```\n'


def code_reply(code: str) -> str:
    """A reply that holds ``code`` in a fenced block."""
    return f"```python\n{code}\n```"


@dataclass
class FakeSummaries:
    """Answers the n-th ask with the n-th reply, the last one again past the end, and keeps each
    request with the inputs the run had when it came."""

    replies: Sequence[str | Unanswered]
    requests: list[SummaryRequest] = field(default_factory=list)
    inputs_then: list[int] = field(default_factory=list)
    tries: dict[str, int] = field(default_factory=dict)
    records: list[InputRecord] = field(default_factory=list)

    def summarize(self, request: SummaryRequest) -> SummaryReply | Unanswered:
        self.requests.append(request)
        self.inputs_then.append(len(self.records))
        attempt = self.tries.get(request.place, 0) + 1
        self.tries[request.place] = attempt
        reply = self.replies[min(len(self.requests), len(self.replies)) - 1]
        cost = AskCost(attempt)
        if isinstance(reply, Unanswered):
            return dataclasses.replace(reply, cost=cost)
        return summary_reply(reply, cost)


@dataclass
class Summarized:
    """What a run with summaries gave: its result, each input as it finished, and the stderr line
    each note gives, in the order they came."""

    result: RunResult
    records: list[InputRecord]
    said: list[str]

    def llm_said(self) -> list[str]:
        """The ``llm:`` lines alone."""
        return [line for line in self.said if line.startswith("llm: ")]


def run_summaries(
    spec: str,
    seed: Mapping[str, object] | Sequence[Mapping[str, object]],
    provider: FakeSummaries,
    limits: Limits = ONE_MOMENT,
) -> Summarized:
    """``run()`` on ``spec`` from ``seed`` inside the block that substitutes its package and
    records each loop's runs, every input in this process and each formula in a child of it,
    with ``provider`` as the summaries helper."""
    records = provider.records
    said: list[str] = []

    def report(record: InputRecord, _coverage: Coverage) -> None:
        records.append(record)
        said.append(f"input {len(records)}")

    def noted(note: Note) -> None:
        line = note_line(note)
        if line is not None:
            said.append(line)

    setup = Setup(isolation=Isolation.IN_PROCESS, helpers=Helpers(summaries=provider))
    tell = Tell(report=report, noted=noted)
    with interception(spec, pieces=True):
        result = run(load_target(spec), seed, limits=limits, setup=setup, tell=tell)
    return Summarized(result, records, said)


@pytest.fixture(autouse=True)
def one_thread(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """pyct's process as a run has it, one thread: pytest-timeout's watch runs another, and a
    formula's child forks beside it safely, since it takes no lock the call needs. The target's
    substituted code is kept in a cache folder of the test's own."""
    monkeypatch.setattr(model_runs, "running", lambda: 1)
    monkeypatch.setenv("PYCT_CACHE_DIR", str(tmp_path))
