"""The run's loop, a pass at a time: what each pass checks first, and what runs between two."""

import functools
import time
from pathlib import Path

import pytest

from pyct.binding.bind import Seed
from pyct.branches.tree import Tree
from pyct.core.foundation.branch import Site
from pyct.execution.execute import ExecutionContext, execute
from pyct.results.coverage import Progress, Scope
from pyct.results.record import Aim, Stop, StopKind
from pyct.run.bounds import Bounds
from pyct.run.loop import Solved, Ways, _attempt, _site_waits
from pyct.run.run import run
from pyct.run.target import load_target
from pyct.run.tell import Ask
from pyct.solver.answer import Answer, Sat, Timeout, Unknown, Unsat


def no_input_yet() -> Progress:
    """A run's progress before any input, which no stop reads as full; a fresh one per call."""
    return Progress(Scope(file="", lines=frozenset()), frozenset())


def test_a_deadline_that_has_passed_leaves_the_solver_unasked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = load_target("targets.flip.one_check::classify")
    seed = {"x": 3}
    tree = Tree()
    tree.add(run(target, seed).records[0].forks)
    # no cvc5 on the PATH: asking would raise rather than answer
    monkeypatch.setenv("PATH", str(tmp_path))
    call = functools.partial(execute, ExecutionContext(fn=target.fn, file=target.file))

    attempt = _attempt(
        Ways(call), {0: Seed.of(seed)}, tree, Bounds(until=time.monotonic() - 1), no_input_yet()
    )

    assert attempt.record is None
    assert attempt.stop == Stop(kind=StopKind.BUDGET)


# an ask about a fork at line 2, which the answers below are for
ASK = Ask(0, Aim(Site(file="m.py", line=2, col=7), 0), 0, ())


# a-slow-unknown-waits-for-the-last-picks-at-a-quarter-of-the-limit
@pytest.mark.parametrize(
    ("answer", "seconds", "waits"),
    [
        (Unknown(), 2.49, False),
        (Unknown(), 2.5, True),
        (Unknown(), 10.0, True),
        (Unknown(guarded=True), 2.49, False),
        (Unknown(guarded=True), 2.5, True),
        (Timeout(), 0.0, True),
        (Sat({}), 10.0, False),
        (Unsat(), 10.0, False),
    ],
    ids=[
        "unknown-under-a-quarter",
        "unknown-at-a-quarter",
        "unknown-at-the-limit",
        "guarded-unknown-under-a-quarter",
        "guarded-unknown-at-a-quarter",
        "timeout",
        "sat",
        "unsat",
    ],
)
def test_a_site_waits_after_a_timeout_or_an_unknown_that_used_a_quarter_of_its_limit(
    answer: Answer, seconds: float, waits: bool
) -> None:
    assert _site_waits(Solved(answer, seconds, ASK), 10.0) is waits
