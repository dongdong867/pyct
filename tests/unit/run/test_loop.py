"""The run's loop, a pass at a time: what each pass checks first, and what runs between two."""

import functools
import time
from pathlib import Path

import pytest

from pyct.binding.bind import Seed
from pyct.branches.tree import Tree
from pyct.execution.execute import ExecutionContext, execute
from pyct.results.coverage import Progress, Scope
from pyct.results.record import Stop, StopKind
from pyct.run.bounds import Bounds
from pyct.run.loop import _attempt
from pyct.run.run import run
from pyct.run.target import load_target


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
        call, {0: Seed.of(seed)}, tree, Bounds(until=time.monotonic() - 1), no_input_yet()
    )

    assert attempt.record is None
    assert attempt.stop == Stop(kind=StopKind.BUDGET)
