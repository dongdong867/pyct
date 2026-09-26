"""Where a run's inputs run: forked while pyct's process runs one thread, else fresh."""

import dataclasses
import inspect
import logging
import os
import random
import subprocess
import sys
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from pyct.run import isolation
from pyct.run.isolation import Inputs, Isolation
from pyct.run.target import Target, load_target

REPO_ROOT = Path(__file__).resolve().parents[3]

# two runs of one threaded module in one process, as sweep runs one function after another
RUN_A_THREADED_MODULE_TWICE = """
from pyct.run.run import run
from pyct.run.target import load_target

for _ in range(2):
    result = run(load_target("targets.isolate.threaded::count"), {"x": 0})
    print(result.environment.isolated)
"""

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


def one_check() -> Target:
    return load_target("targets.flip.one_check::classify")


@contextmanager
def another_thread() -> Generator[None]:
    """A thread of the test's own, running beside the main one until the block ends."""
    stop = threading.Event()
    thread = threading.Thread(target=stop.wait, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()


def counting(monkeypatch: pytest.MonkeyPatch, *counts: int) -> None:
    """pyct's process runs these many threads before each input, in turn."""
    told = iter(counts)
    monkeypatch.setattr(isolation, "running", lambda: next(told))


def python(script: str) -> subprocess.CompletedProcess[str]:
    """``script`` in a Python of its own, where no test runner's thread runs."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_auto_forks_while_pyct_s_process_runs_one_thread(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    counting(monkeypatch, 1, 1)
    inputs = Inputs(one_check(), Isolation.AUTO)

    with caplog.at_level(logging.WARNING):
        inputs({"x": 3}, None)
        inputs({"x": 20}, None)

    assert inputs.ran == [Isolation.FORK, Isolation.FORK]
    assert inputs.isolated
    assert caplog.messages == []


def test_auto_starts_fresh_interpreters_from_the_first_input_that_finds_a_thread(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    counting(monkeypatch, 1, 2, 1)
    inputs = Inputs(one_check(), Isolation.AUTO)

    with caplog.at_level(logging.WARNING):
        results = [inputs({"x": x}, None) for x in (3, 20, 3)]

    assert inputs.ran == [Isolation.FORK, Isolation.FRESH, Isolation.FRESH]
    assert [len(result.branches) for result in results] == [1, 1, 1]
    assert inputs.isolated
    (said,) = caplog.messages
    assert said == (
        "each input runs in a fresh interpreter, because pyct's process runs other threads"
    )


def test_auto_counts_a_thread_whoever_started_it(caplog: pytest.LogCaptureFixture) -> None:
    inputs = Inputs(one_check(), Isolation.AUTO)

    with another_thread(), caplog.at_level(logging.WARNING):
        inputs({"x": 3}, None)

    assert inputs.ran == [Isolation.FRESH]


def test_forced_fork_forks_while_other_threads_run(caplog: pytest.LogCaptureFixture) -> None:
    inputs = Inputs(one_check(), Isolation.FORK)

    with another_thread(), caplog.at_level(logging.WARNING):
        result = inputs({"x": 3}, None)

    assert inputs.ran == [Isolation.FORK]
    assert [branch.taken for branch in result.branches] == [True]
    assert caplog.messages == []


def test_a_target_no_name_finds_runs_in_process_once_another_thread_runs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[int] = []

    def count(x: int) -> None:
        calls.append(x)

    closure = dataclasses.replace(one_check(), fn=count, signature=inspect.signature(count))
    inputs = Inputs(closure, Isolation.AUTO)

    with another_thread(), caplog.at_level(logging.WARNING):
        inputs({"x": 1}, None)

    assert inputs.ran == [Isolation.IN_PROCESS]
    assert not inputs.isolated
    assert calls == [1]
    (said,) = caplog.messages
    assert said.startswith("each input runs in pyct's process, because pyct's process runs other")


def test_a_fresh_interpreter_needs_a_target_a_name_finds() -> None:
    closure = dataclasses.replace(one_check(), fn=lambda x: x)

    with pytest.raises(ValueError, match="by name"):
        Inputs(closure, Isolation.FRESH)


def test_in_process_says_nothing_about_threads(caplog: pytest.LogCaptureFixture) -> None:
    inputs = Inputs(one_check(), Isolation.IN_PROCESS)

    with another_thread(), caplog.at_level(logging.WARNING):
        inputs({"x": 3}, None)

    assert inputs.ran == [Isolation.IN_PROCESS]
    assert not inputs.isolated
    assert caplog.messages == []


def test_an_input_in_process_leaves_its_state_for_the_next() -> None:
    calls: list[int] = []

    def count(x: int) -> None:
        calls.append(x)

    target = dataclasses.replace(one_check(), fn=count, signature=inspect.signature(count))
    inputs = Inputs(target, Isolation.IN_PROCESS)

    inputs({"x": 1}, None)
    inputs({"x": 2}, None)

    assert calls == [1, 2]


def test_a_module_imported_earlier_that_left_a_thread_sends_later_runs_fresh() -> None:
    finished = python(RUN_A_THREADED_MODULE_TWICE)

    assert finished.returncode == 0, finished.stderr
    assert finished.stdout.splitlines() == ["True", "True"]
    said = [line for line in finished.stderr.splitlines() if "fresh interpreter" in line]
    # the second run finds the thread the first import left, and says so for its own inputs
    assert len(said) == 2, finished.stderr


def test_a_run_in_process_for_want_of_a_name_says_so_once_on_stderr() -> None:
    finished = python(RUN_A_CLOSURE_FROM_A_THREADED_IMPORT)

    assert finished.returncode == 0, finished.stderr
    assert finished.stdout == "False\n"
    said = [line for line in finished.stderr.splitlines() if "threads" in line]
    assert len(said) == 1, finished.stderr
    assert said[0].startswith("each input runs in pyct's process")


def test_setting_up_a_run_leaves_the_target_s_random_alone() -> None:
    before = random.getstate()

    Inputs(one_check(), Isolation.AUTO)

    assert random.getstate() == before
