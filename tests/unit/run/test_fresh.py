"""One input in a fresh interpreter, for real: each test starts a new Python."""

import os
import time

import pytest

from pyct.execution.execute import ExecutionContext, execute
from pyct.results.failure import Failure, FailureKind
from pyct.run.fresh import in_a_fresh_interpreter
from pyct.run.process import KILL_GRACE, InputStartError
from pyct.run.target import load_target

ONE_CHECK = "targets.flip.one_check::classify"
SEGFAULT = "targets.isolate.segfault::fault"
SWALLOWS_ALARM = "targets.isolate.swallows_alarm::swallow"
BASE_RAISES = "targets.isolate.base_raises::stop"


def test_a_fresh_interpreter_runs_the_call_as_pyct_s_process_would() -> None:
    target = load_target(ONE_CHECK)
    ctx = ExecutionContext(fn=target.fn, file=target.file)

    fresh = in_a_fresh_interpreter(target.spec, target.file, {"x": 3}, None)

    assert fresh == execute(ctx, {"x": 3})


def test_a_fresh_interpreter_ends_the_way_its_call_did() -> None:
    target = load_target(SEGFAULT)

    fresh = in_a_fresh_interpreter(target.spec, target.file, {"x": 7, "y": 0}, None)

    assert fresh.failure == Failure(kind=FailureKind.CRASHED, detail="killed by SIGSEGV")
    assert [branch.taken for branch in fresh.branches] == [False, True]


def test_a_fresh_interpreter_is_alone_in_its_process() -> None:
    target = load_target(BASE_RAISES)

    fresh = in_a_fresh_interpreter(target.spec, target.file, {"x": 5, "y": 0}, None)

    assert fresh.failure == Failure(kind=FailureKind.TARGET_RAISED, detail="KeyboardInterrupt")


@pytest.mark.usefixtures("deadline_fires_in_a_child")
def test_a_fresh_interpreter_past_the_deadline_is_killed() -> None:
    target = load_target(SWALLOWS_ALARM)
    started = time.monotonic()

    fresh = in_a_fresh_interpreter(target.spec, target.file, {"x": 5}, started + 0.2)

    assert fresh.failure == Failure(kind=FailureKind.TIMEOUT, detail="deadline passed")
    assert time.monotonic() - started < 0.2 + KILL_GRACE + 0.5


def test_a_fresh_interpreter_that_cannot_start_is_an_input_that_could_not_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = load_target(ONE_CHECK)

    def refuse(*args: object, **kwargs: object) -> int:
        raise BlockingIOError(35, "Resource temporarily unavailable")

    monkeypatch.setattr(os, "posix_spawn", refuse)

    with pytest.raises(InputStartError, match="Resource temporarily unavailable"):
        in_a_fresh_interpreter(target.spec, target.file, {"x": 3}, None)


def test_arguments_a_fresh_interpreter_cannot_be_handed_are_an_input_that_could_not_start() -> None:
    target = load_target(ONE_CHECK)

    with pytest.raises(InputStartError, match="could not hand the input"):
        in_a_fresh_interpreter(target.spec, target.file, {"x": lambda: 3}, None)
