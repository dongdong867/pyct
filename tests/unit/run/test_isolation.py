"""One input in a child process, for real: each test forks, and each child takes milliseconds."""

import faulthandler
import gc
import io
import mmap
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from pyct.execution.execute import ExecutionContext, ExecutionResult, execute
from pyct.results.failure import Failure, FailureKind
from pyct.run.isolation import in_a_child
from pyct.run.process import KILL_GRACE, InputStartError

REPO_ROOT = Path(__file__).resolve().parents[3]


def segfault(x: int) -> None:
    # pytest's faulthandler would print this process's stack before the signal ends it
    faulthandler.disable()
    os.kill(os.getpid(), signal.SIGSEGV)


def in_child(fn: Callable[..., object], args: dict[str, object] | None = None) -> ExecutionResult:
    """``fn`` called once in a child process, traced in this file."""
    return in_a_child(ExecutionContext(fn=fn, file=__file__), args or {"x": 5}, None)


def returns(x: int) -> str:
    if x > 3:
        return "big"
    return "small"


def test_a_child_that_returns_reads_as_the_same_call_in_process() -> None:
    ctx = ExecutionContext(fn=returns, file=__file__)

    isolated = in_a_child(ctx, {"x": 5}, None)

    assert isolated == execute(ctx, {"x": 5})
    assert isolated.failure is None
    assert isolated.branches


@pytest.mark.parametrize(
    ("body", "failure"),
    [
        pytest.param(
            lambda x: int("no"),
            Failure(
                kind=FailureKind.TARGET_RAISED,
                detail="ValueError: invalid literal for int() with base 10: 'no'",
            ),
            id="raises",
        ),
        pytest.param(
            lambda x: sys.exit(3),
            Failure(kind=FailureKind.SYSTEM_EXIT, detail="SystemExit: 3"),
            id="raises-system-exit",
        ),
        pytest.param(
            lambda x: os._exit(3),
            Failure(kind=FailureKind.SYSTEM_EXIT, detail="exited with code 3"),
            id="exits-without-raising",
        ),
        pytest.param(
            segfault,
            Failure(kind=FailureKind.CRASHED, detail="killed by SIGSEGV"),
            id="killed-by-a-signal",
        ),
    ],
)
def test_a_child_ends_the_way_its_call_did(body: Callable[[int], object], failure: Failure) -> None:
    assert in_child(body).failure == failure


def test_each_child_starts_from_the_state_before_the_first() -> None:
    calls: list[int] = []

    def count(x: int) -> None:
        calls.append(x)
        if len(calls) > 1:
            calls.append(-1)

    seen_before = count.__code__.co_firstlineno + 3

    first = in_child(count)
    second = in_child(count)

    # the list each child appended to was the child's own copy
    assert calls == []
    assert second.lines == first.lines
    assert seen_before not in second.lines


def test_what_the_target_writes_to_stdout_lands_on_stderr(
    capfd: pytest.CaptureFixture[str],
) -> None:
    def speak(x: int) -> None:
        print("hello")
        os.write(1, b"raw\n")

    in_child(speak)

    out, err = capfd.readouterr()
    assert out == ""
    assert err.splitlines() == ["hello", "raw"]


def test_the_target_reads_an_empty_stdin() -> None:
    result = in_child(lambda x: input())

    failure = result.failure
    assert failure is not None
    assert failure.kind is FailureKind.TARGET_RAISED
    assert failure.detail.startswith("EOFError")


def test_a_process_the_target_forks_writes_nothing_for_the_input() -> None:
    def split(x: int) -> str:
        pid = os.fork()
        if pid == 0:
            # the grandchild's fork and its exit are its own, not the input's
            if x > 3:
                os._exit(7)
            os._exit(7)
        os.waitpid(pid, 0)
        return "joined"

    result = in_child(split)

    assert result.branches == ()
    assert result.failure is None


def doubles(x: int) -> int:
    for _ in range(40):
        x = x + x
    if x > 0:
        return 1
    return 0


def test_a_part_a_loop_reuses_crosses_once_and_arrives_shared() -> None:
    result = in_child(doubles, {"x": 1})

    # written out as a tree, 40 doublings hold 2**40 leaves; shared, one list per pass
    ((branch),) = result.branches
    part = branch.expression
    assert isinstance(part, list)
    part = part[1]
    for _ in range(40):
        assert isinstance(part, list)
        assert part[1] is part[2]
        part = part[1]
    assert part == "x"


def test_a_failed_fork_is_an_input_that_could_not_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse() -> int:
        raise BlockingIOError(35, "Resource temporarily unavailable")

    monkeypatch.setattr(os, "fork", refuse)

    with pytest.raises(InputStartError, match="Resource temporarily unavailable"):
        in_child(returns)


def test_a_journal_that_cannot_be_mapped_is_an_input_that_could_not_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*args: object) -> mmap.mmap:
        raise OSError(12, "Cannot allocate memory")

    monkeypatch.setattr(mmap, "mmap", refuse)

    with pytest.raises(InputStartError, match="Cannot allocate memory"):
        in_child(returns)


def spins_then_cleans_up(x: int) -> int:
    try:
        while True:
            x ^= 1
    finally:
        x = 0


@pytest.mark.usefixtures("deadline_fires_in_a_child")
def test_a_python_hang_ends_by_its_own_alarm_before_pyct_kills_it() -> None:
    cleaned_up = spins_then_cleans_up.__code__.co_firstlineno + 5
    started = time.monotonic()

    result = in_a_child(
        ExecutionContext(fn=spins_then_cleans_up, file=__file__, alone=True),
        {"x": 1},
        started + 0.2,
    )

    # the call wrote its own ending, finally block included, well before the kill was due
    assert result.failure == Failure(kind=FailureKind.TIMEOUT, detail="deadline passed")
    assert cleaned_up in result.lines
    assert time.monotonic() - started < 0.2 + KILL_GRACE


# a caller whose target replaces os._exit, as a mock does; the caller says when it goes on
RUN_A_TARGET_THAT_REPLACES_EXIT = """
import os
from pyct.execution.execute import ExecutionContext
from pyct.run.isolation import in_a_child

def replaces_exit(x):
    os._exit = lambda code: None
    return x

try:
    in_a_child(ExecutionContext(fn=replaces_exit, file="<string>", alone=True), {"x": 1}, None)
finally:
    print("the caller went on")
"""


def test_a_target_that_replaces_exit_cannot_send_its_process_back_to_the_caller() -> None:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    finished = subprocess.run(
        [sys.executable, "-c", RUN_A_TARGET_THAT_REPLACES_EXIT],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    # only the caller's own process goes on; the input's process ended where pyct ended it.
    # An input's process writes its stdout to stderr, so both streams are counted
    said = (finished.stdout + finished.stderr).count("the caller went on")
    assert said == 1, finished.stderr
    assert finished.returncode == 0, finished.stderr


def test_text_a_caller_left_in_the_real_stdout_is_written_once(
    capfd: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    real = io.TextIOWrapper(os.fdopen(os.dup(1), "wb"), encoding="utf-8")
    # a caller that points sys.stdout elsewhere and leaves text in the real stdout's buffer
    monkeypatch.setattr(sys, "__stdout__", real)
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    real.write("held\n")

    in_child(returns)
    in_child(returns)
    real.flush()

    out, err = capfd.readouterr()
    assert out.count("held") == 1
    assert "held" not in err


def test_a_freeze_the_caller_made_outlasts_an_input() -> None:
    before = gc.get_freeze_count()
    gc.freeze()
    try:
        in_child(returns)

        # an unfreeze would leave nothing frozen; objects freed since leave it one by one
        assert gc.get_freeze_count() > before
    finally:
        gc.unfreeze()


def test_an_input_leaves_pyct_s_freeze_as_it_found_it() -> None:
    frozen = gc.get_freeze_count()

    in_child(returns)

    assert gc.get_freeze_count() == frozen


def test_a_failed_start_leaves_pyct_s_freeze_as_it_found_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = gc.get_freeze_count()

    def refuse() -> int:
        raise BlockingIOError(35, "Resource temporarily unavailable")

    monkeypatch.setattr(os, "fork", refuse)

    with pytest.raises(InputStartError):
        in_child(returns)

    assert gc.get_freeze_count() == frozen


def test_the_input_s_process_freezes_what_it_started_with() -> None:
    frozen = gc.get_freeze_count()

    def frozen_there(x: int) -> None:
        if gc.get_freeze_count() <= frozen:
            raise AssertionError("nothing was frozen")

    assert in_child(frozen_there).failure is None
