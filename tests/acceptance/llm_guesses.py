"""A fake ``GuessProvider`` that answers fixed guesses, and ``run()`` on a target in
``targets/guesses/`` with guesses on, for the guess-inputs-when-stuck story's acceptance tests.

The fake charges each reply's tokens against a limit as the connection does. Summaries and
rewrites join the run when a test hands in their fakes. No test here calls a model or sends
anything off the machine.
"""

from __future__ import annotations

import dataclasses
import json
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from pyct.cli.llm import note_line
from pyct.config.limits import Limits
from pyct.config.llm import DEFAULT_LIMIT
from pyct.results.coverage import Coverage
from pyct.results.llm_asks import AskCost, Unanswered, Why
from pyct.results.record import InputRecord, RunResult
from pyct.run import isolation, model_runs
from pyct.run.guess_asks import GuessReply, GuessRequest
from pyct.run.helpers import Helpers
from pyct.run.isolation import Isolation
from pyct.run.notes import Note
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.target import interception, load_target
from pyct.run.tell import Tell
from tests.acceptance.harness import REPO_ROOT
from tests.acceptance.llm_rewrites import FakeRewrites
from tests.acceptance.llm_summaries import FakeSummaries, targets_imported_afresh

# the tokens in and out each reply the fake gives costs
TOKENS = (200, 40)

# one reply: each guess as a seed, or as the JSON text the model wrote
type Guessed = Sequence[Mapping[str, object] | str]

_PLAIN = Limits()


def file_of(name: str) -> str:
    """The file of the target module ``targets.guesses.<name>``, as its sites name it."""
    return str(REPO_ROOT / "targets" / "guesses" / f"{name}.py")


def line_of(name: str, text: str) -> int:
    """The line of ``targets/guesses/<name>.py`` that holds ``text``, the first such."""
    lines = Path(file_of(name)).read_text(encoding="utf-8").splitlines()
    return next(number for number, line in enumerate(lines, 1) if text in line)


@dataclass
class FakeGuesses:
    """Answers the n-th ask with the n-th reply, the last one again past the end, after
    ``delay`` seconds, and keeps each request with when it came and when its answer went back.
    Each reply costs ``TOKENS``; once they reach ``limit`` an ask gets ``limit`` back, as the
    connection's does."""

    replies: Sequence[Guessed | Unanswered]
    delay: float = 0.0
    limit: int = DEFAULT_LIMIT
    requests: list[GuessRequest] = field(default_factory=list)
    asked_at: list[float] = field(default_factory=list)
    answered_at: list[float] = field(default_factory=list)
    charged: int = 0

    def guesses(self, request: GuessRequest) -> GuessReply | Unanswered:
        self.requests.append(request)
        self.asked_at.append(time.monotonic())
        try:
            return self._answer()
        finally:
            self.answered_at.append(time.monotonic())

    def _answer(self) -> GuessReply | Unanswered:
        if self.charged >= self.limit:
            return Unanswered(Why.LIMIT, "token limit reached", AskCost(1))
        time.sleep(self.delay)
        reply = self.replies[min(len(self.requests), len(self.replies)) - 1]
        if isinstance(reply, Unanswered):
            return dataclasses.replace(reply, cost=self._cost(0, 0))
        items = tuple(each if isinstance(each, str) else json.dumps(each) for each in reply)
        return GuessReply(items, self._cost(*TOKENS))

    def _cost(self, tokens_in: int, tokens_out: int) -> AskCost:
        self.charged += tokens_in + tokens_out
        left = max(self.limit - self.charged, 0)
        return AskCost(1, tokens_in, tokens_out, self.delay, tokens_left=left)


@dataclass
class Ran:
    """What a run with guesses gave: its result, each input as it finished, and the stderr line
    each note gives, in the order they came, each input as ``input N``."""

    result: RunResult
    records: list[InputRecord]
    said: list[str]

    def llm_said(self) -> list[str]:
        """The ``llm:`` lines alone."""
        return [line for line in self.said if line.startswith("llm: ")]

    def guess_lines(self) -> list[str]:
        """The ``llm:`` lines of the guesses tool alone."""
        words = ("llm: guesses ", "llm: guess ", "llm: dropped guess ")
        return [line for line in self.said if line.startswith(words)]


@dataclass(frozen=True)
class Others:
    """The other tools a run with guesses switches on, by their fakes."""

    summaries: FakeSummaries | None = None
    rewrites: FakeRewrites | None = None


def run_guesses(
    spec: str,
    seed: Mapping[str, object],
    provider: FakeGuesses,
    limits: Limits = _PLAIN,
    others: Others | None = None,
) -> Ran:
    """``run()`` on ``spec`` from ``seed`` inside the block that substitutes its package, with
    ``provider`` as the guesses helper and the fakes of ``others`` as theirs. Every input runs in
    this process, or, with summaries, in a child forked from it, the package intercepted with
    the recording of each loop's runs, as summaries need."""
    records: list[InputRecord] = []
    said: list[str] = []

    def report(record: InputRecord, _coverage: Coverage) -> None:
        records.append(record)
        said.append(f"input {len(records)}")

    def noted(note: Note) -> None:
        line = note_line(note)
        if line is not None:
            said.append(line)

    others = Others() if others is None else others
    helpers = Helpers(summaries=others.summaries, rewrites=others.rewrites, guesses=provider)
    pieces = others.summaries is not None
    where = Isolation.AUTO if pieces else Isolation.IN_PROCESS
    setup = Setup(isolation=where, helpers=helpers)
    tell = Tell(report=report, noted=noted)
    with interception(spec, pieces=pieces):
        result = run(load_target(spec), seed, limits=limits, setup=setup, tell=tell)
    return Ran(result, records, said)


@pytest.fixture(autouse=True)
def one_thread(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """pyct's process as a run has it, one thread: pytest-timeout's watch runs another, and an
    input's, a formula's or a rewrite's child forks beside it safely, since it takes no lock the
    call needs. The target's substituted code is kept in a cache folder of the test's own, and
    each target module is imported again under the run's interception
    (``targets_imported_afresh``)."""
    monkeypatch.setattr(model_runs, "running", lambda: 1)
    monkeypatch.setattr(isolation, "running", lambda: 1)
    monkeypatch.setenv("PYCT_CACHE_DIR", str(tmp_path))
    with targets_imported_afresh():
        yield
