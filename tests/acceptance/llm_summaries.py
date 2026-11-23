"""A fake ``SummaryProvider`` that answers fixed text, and ``run()`` with summaries on, the
target's package intercepted with the recording of each loop's runs and each input forked, for
the acceptance tests of the ask-for-a-stuck-loop-s-summary and
track-a-value-through-a-loop-summary stories.

The fake reads each reply as ``pyct.llm.summaries`` does, and numbers its tries per place and
charges each reply's tokens against a limit as the connection does, so a test reads the try
numbers the stderr lines carry and can reach the limit. No test here calls a model or sends
anything off the machine.
"""

from __future__ import annotations

import contextlib
import dataclasses
import sys
from collections.abc import Generator, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from pyct.cli.llm import note_line
from pyct.config.limits import Limits
from pyct.config.llm import DEFAULT_LIMIT
from pyct.config.plateau import Plateau
from pyct.llm.summaries import summary_reply
from pyct.results.coverage import Coverage
from pyct.results.jsonl import render
from pyct.results.llm_asks import AskCost, Unanswered, Why
from pyct.results.record import InputRecord, RunResult
from pyct.run import isolation, model_runs
from pyct.run.helpers import Helpers
from pyct.run.isolation import Isolation
from pyct.run.notes import Note
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.summaries import ShownRun, SummaryReply, SummaryRequest
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
# the tokens in and out each reply the fake gives costs
TOKENS = (120, 30)


def code_reply(code: str) -> str:
    """A reply that holds ``code`` in a fenced block."""
    return f"```python\n{code}\n```"


@dataclass
class FakeSummaries:
    """Answers the n-th ask with the n-th reply, the last one again past the end, and keeps each
    request with the inputs the run had when it came. Each reply costs ``TOKENS``; once they
    reach ``limit`` an ask gets ``limit`` back, as the connection's does."""

    replies: Sequence[str | Unanswered]
    limit: int = DEFAULT_LIMIT
    requests: list[SummaryRequest] = field(default_factory=list)
    inputs_then: list[int] = field(default_factory=list)
    tries: dict[str, int] = field(default_factory=dict)
    records: list[InputRecord] = field(default_factory=list)
    charged: int = 0

    def summarize(self, request: SummaryRequest) -> SummaryReply | Unanswered:
        self.requests.append(request)
        self.inputs_then.append(len(self.records))
        attempt = self.tries.get(request.place, 0) + 1
        self.tries[request.place] = attempt
        if self.charged >= self.limit:
            return Unanswered(Why.LIMIT, "token limit reached", AskCost(attempt))
        reply = self.replies[min(len(self.requests), len(self.replies)) - 1]
        if isinstance(reply, Unanswered):
            return dataclasses.replace(reply, cost=self._cost(attempt, 0, 0))
        return summary_reply(reply, self._cost(attempt, *TOKENS))

    def _cost(self, attempt: int, tokens_in: int, tokens_out: int) -> AskCost:
        self.charged += tokens_in + tokens_out
        left = max(self.limit - self.charged, 0)
        return AskCost(attempt, tokens_in, tokens_out, tokens_left=left)


def held_back(runs: Sequence[ShownRun]) -> tuple[tuple[str, str], ...]:
    """The values going in a request holds back from these runs, written as it shows them, in
    run order, as the story refuse-a-summary-that-only-repeats-its-runs picks them: the latest
    run whose changed values no run with other values going in has and that moved a changed
    name, else the latest that moved one, else the latest whose changed values are its own,
    else the latest."""

    def alone(run: ShownRun) -> bool:
        return all(other.changed != run.changed for other in runs if other.going_in != run.going_in)

    def moved(run: ShownRun) -> bool:
        return any(dict(run.going_in).get(name) != value for name, value in run.changed)

    for kind in (lambda run: alone(run) and moved(run), moved, alone):
        found = [each for each in runs if kind(each)]
        if found:
            return found[-1].going_in
    return runs[-1].going_in


def checked_on(provider: FakeSummaries, ask: int = 0) -> str:
    """The text the ``checked on`` line holds for the formula of ``provider``'s ask numbered
    ``ask``, from 0: the complete runs of its loop the inputs then held, and those whose values
    going in no run its request showed has, as the story
    refuse-a-summary-that-only-repeats-its-runs counts them."""
    request = provider.requests[ask]
    line, col = (int(part) for part in request.place.rsplit(":", 2)[1:])
    runs = [
        each
        for record in provider.records[: provider.inputs_then[ask]]
        for each in record.pieces
        if (each.site.line, each.site.col) == (line, col)
        and set(request.changed) <= {changed.name for changed in each.changed}
    ]
    seen = {shown.going_in for shown in request.runs}
    hidden = sum(
        tuple(
            (going.name, going.value) for going in each.going_in if going.name in request.parameters
        )
        not in seen
        for each in runs
    )
    text = f"checked on {len(runs)} past runs"
    return f"{text}, {hidden} of them not shown" if hidden else text


@dataclass
class Summarized:
    """What a run with summaries gave: its result, each input as it finished, the stderr line each
    note gives, in the order they came, and each input's stdout line as it was rendered when it
    finished, with the coverage it was rendered with."""

    result: RunResult
    records: list[InputRecord]
    said: list[str]
    printed: list[tuple[str, Coverage]] = field(default_factory=list)

    def llm_said(self) -> list[str]:
        """The ``llm:`` lines alone."""
        return [line for line in self.said if line.startswith("llm: ")]


def run_summaries(
    spec: str,
    seed: Mapping[str, object] | Sequence[Mapping[str, object]],
    provider: FakeSummaries,
    limits: Limits = ONE_MOMENT,
    isolation: Isolation = Isolation.AUTO,
) -> Summarized:
    """``run()`` on ``spec`` from ``seed`` inside the block that substitutes its package and
    records each loop's runs, every input and each formula check in a child forked from this
    process, with ``provider`` as the summaries helper. ``isolation`` says where each input runs
    instead, such as in a fresh interpreter."""
    records = provider.records
    said: list[str] = []
    printed: list[tuple[str, Coverage]] = []

    def report(record: InputRecord, coverage: Coverage) -> None:
        records.append(record)
        said.append(f"input {len(records)}")
        printed.append((render(record, coverage), coverage))

    def noted(note: Note) -> None:
        line = note_line(note)
        if line is not None:
            said.append(line)

    setup = Setup(isolation=isolation, helpers=Helpers(summaries=provider))
    tell = Tell(report=report, noted=noted)
    with interception(spec, pieces=True):
        result = run(load_target(spec), seed, limits=limits, setup=setup, tell=tell)
    return Summarized(result, records, said, printed)


@contextlib.contextmanager
def targets_imported_afresh() -> Generator[None]:
    """Each ``targets`` module dropped from ``sys.modules`` for the block, so that the block
    imports it again. After it, each ``targets`` module the block imported is dropped, so that
    none compiled with the loop hooks reaches a later test, and each one dropped is back."""
    before = {name: module for name, module in sys.modules.items() if _in_targets(name)}
    for name in before:
        del sys.modules[name]
    try:
        yield
    finally:
        for name in [name for name in sys.modules if _in_targets(name)]:
            del sys.modules[name]
        sys.modules.update(before)


def _in_targets(name: str) -> bool:
    return name.split(".")[0] == "targets"


@pytest.fixture(autouse=True)
def one_thread(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """pyct's process as a run has it, one thread: pytest-timeout's watch runs another, and an
    input's or a formula's child forks beside it safely, since it takes no lock the call needs,
    so no input moves to a fresh interpreter. The target's
    substituted code is kept in a cache folder of the test's own, and each target module is
    imported again under the interception that records loops (``targets_imported_afresh``)."""
    monkeypatch.setattr(model_runs, "running", lambda: 1)
    monkeypatch.setattr(isolation, "running", lambda: 1)
    monkeypatch.setenv("PYCT_CACHE_DIR", str(tmp_path))
    with targets_imported_afresh():
        yield
