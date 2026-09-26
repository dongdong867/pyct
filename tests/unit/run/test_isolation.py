"""One input in a child process, for real: each test forks, and each child takes milliseconds."""

import dataclasses
import faulthandler
import inspect
import logging
import mmap
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from pyct.execution.execute import ExecutionContext, ExecutionResult, execute
from pyct.results.failure import Failure, FailureKind
from pyct.run.isolation import in_a_child, isolation
from pyct.run.process import KILL_GRACE, InputStartError
from pyct.run.target import Target, load_target

REPO_ROOT = Path(__file__).resolve().parents[3]

# run() on a closure from a module whose import left a thread, printing whether it isolated
RUN_A_CLOSURE_FROM_A_THREADED_IMPORT = """
import dataclasses, inspect
from pyct.run.run import run
from pyct.run.target import load_target

loaded = load_target("targets.isolate.threaded_closure::make")
count = loaded.fn()
target = dataclasses.replace(loaded, fn=count, signature=inspect.signature(count))
print(run(target, {"x": 0}).environment.isolated)
"""


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


def one_check() -> Target:
    return load_target("targets.flip.one_check::classify")


def test_a_run_isolates_its_inputs_unless_told_not_to() -> None:
    assert isolation(one_check(), isolated=True).isolated is True
    assert isolation(one_check(), isolated=False).isolated is False


def test_an_input_in_process_leaves_its_state_for_the_next() -> None:
    calls: list[int] = []

    def count(x: int) -> None:
        calls.append(x)

    target = Target(spec="m::count", fn=count, file=__file__, signature=one_check().signature)
    call = isolation(target, isolated=False).call

    call({"x": 1}, None)
    call({"x": 2}, None)

    assert calls == [1, 2]


def test_a_run_forks_each_input_when_the_import_added_no_thread(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # pytest-timeout's watchdog was running before the import, so it does not count
    watchdogs = [
        thread for thread in threading.enumerate() if thread.name.startswith("pytest_timeout")
    ]
    assert watchdogs

    with caplog.at_level(logging.WARNING):
        chosen = isolation(one_check(), isolated=True)

    assert chosen.isolated is True
    assert chosen.call.func is in_a_child  # pyrefly: ignore[missing-attribute]
    assert caplog.messages == []


def test_a_run_whose_import_left_a_thread_starts_a_fresh_interpreter_per_input(
    caplog: pytest.LogCaptureFixture,
) -> None:
    target = load_target("targets.isolate.threaded::count")

    with caplog.at_level(logging.WARNING):
        chosen = isolation(target, isolated=True)
        result = chosen.call({"x": 5}, None)

    assert chosen.isolated is True
    assert chosen.call.func is not in_a_child  # pyrefly: ignore[missing-attribute]
    assert [branch.taken for branch in result.branches] == [True]
    (said,) = caplog.messages
    assert "fresh interpreter" in said
    assert "threads" in said


def test_a_target_no_name_finds_runs_in_process_when_its_import_left_a_thread(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[int] = []

    def count(x: int) -> None:
        calls.append(x)

    closure = dataclasses.replace(one_check(), fn=count, signature=inspect.signature(count))
    closure = dataclasses.replace(closure, threads=1)

    with caplog.at_level(logging.WARNING):
        chosen = isolation(closure, isolated=True)
        chosen.call({"x": 1}, None)

    assert chosen.isolated is False
    assert calls == [1]
    (said,) = caplog.messages
    assert "pyct's process" in said
    assert "threads" in said


def test_a_run_in_process_says_nothing_about_threads(caplog: pytest.LogCaptureFixture) -> None:
    threaded = dataclasses.replace(one_check(), threads=1)

    with caplog.at_level(logging.WARNING):
        chosen = isolation(threaded, isolated=False)

    assert chosen.isolated is False
    assert caplog.messages == []


def test_a_run_in_process_for_want_of_a_name_says_so_once_on_stderr() -> None:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    finished = subprocess.run(
        [sys.executable, "-c", RUN_A_CLOSURE_FROM_A_THREADED_IMPORT],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert finished.returncode == 0, finished.stderr
    assert finished.stdout == "False\n"
    said = [line for line in finished.stderr.splitlines() if "threads" in line]
    assert len(said) == 1, finished.stderr
    assert said[0].startswith("each input runs in pyct's process")


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
