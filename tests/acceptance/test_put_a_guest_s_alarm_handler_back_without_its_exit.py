"""Acceptance tests for put-a-guest-s-alarm-handler-back-without-its-exit, one per criterion.

Each runs ``tests/acceptance/tracer_on_the_way_out.py``, a program that calls ``run()`` on
``targets/isolate/on_the_way_out.py`` while a tracer of its own acts as the target's call ends,
in a process of its own without coverage.py, since the deadline raises in the tracer. The
criteria that depend on where the alarm lands are marked ``serial``.
"""

import json
import os
import subprocess
import sys

import pytest

from tests.acceptance.harness import COVERAGE_STARTUP, REPO_ROOT

TRACERS = ["settrace", "monitoring"]
TIMEOUT = ["timeout", "deadline passed"]


def tries(tracer: str, name: str, action: str, handler: str, count: int) -> list[dict]:
    """The program's tries, one dict each, once it exited 0."""
    left_out = {"PYTHONPATH", *COVERAGE_STARTUP}
    ran = subprocess.run(
        [sys.executable, "-m", "tests.acceptance.tracer_on_the_way_out"]
        + [tracer, name, action, handler, str(count)],
        cwd=REPO_ROOT,
        env={k: v for k, v in os.environ.items() if k not in left_out},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert ran.returncode == 0, ran.stderr
    return [json.loads(line) for line in ran.stdout.splitlines()]


def assert_given_back(each: list[dict]) -> None:
    """The program's own handler is back after each try, gets its SIGALRM, and no watcher lives."""
    assert all(one["handler_back"] and one["reached"] for one in each), each
    assert all(one["watchers"] == [] for one in each), each


# put-a-guest-s-alarm-handler-back-without-its-exit-after-a-call-that-returned
@pytest.mark.serial
@pytest.mark.parametrize("tracer", TRACERS)
def test_after_a_call_that_returned(tracer: str) -> None:
    each = tries(tracer, "returns", "spin", "own", 3)

    assert [one["ended"] for one in each] == [TIMEOUT] * 3, each
    assert_given_back(each)


# put-a-guest-s-alarm-handler-back-without-its-exit-after-a-call-that-raised
@pytest.mark.serial
@pytest.mark.parametrize("tracer", TRACERS)
def test_after_a_call_that_raised(tracer: str) -> None:
    each = tries(tracer, "raises", "spin", "own", 1)

    assert [one["ended"] for one in each] == [TIMEOUT], each
    assert_given_back(each)


# put-a-guest-s-alarm-handler-back-without-its-exit-for-ignore-and-default
@pytest.mark.serial
@pytest.mark.parametrize("handler", ["ignore", "default"])
@pytest.mark.parametrize("tracer", TRACERS)
def test_for_ignore_and_default(tracer: str, handler: str) -> None:
    each = tries(tracer, "returns", "spin", handler, 1)

    assert [one["handler_back"] for one in each] == [True], each


# put-a-guest-s-alarm-handler-back-without-its-exit-with-no-tracer
@pytest.mark.serial
@pytest.mark.parametrize("name", ["returns", "loops"])
def test_with_no_tracer(name: str) -> None:
    each = tries("none", name, "none", "own", 1)

    if name == "loops":
        assert [one["ended"] for one in each] == [TIMEOUT], each
    assert_given_back(each)


# put-a-guest-s-alarm-handler-back-without-its-exit-after-a-ctrl-c-on-the-way-out
@pytest.mark.parametrize("tracer", TRACERS)
def test_after_a_ctrl_c_on_the_way_out(tracer: str) -> None:
    each = tries(tracer, "returns", "sigint", "own", 3)

    assert [one["ended"] for one in each] == ["KeyboardInterrupt"] * 3, each
    assert_given_back(each)


# put-a-guest-s-alarm-handler-back-without-its-exit-after-a-tracer-s-own-raise
@pytest.mark.parametrize("tracer", TRACERS)
def test_after_a_tracer_s_own_raise(tracer: str) -> None:
    each = tries(tracer, "returns", "raise", "own", 3)

    # as at a52588ab: the target's call ended by the tracer's raise, which pyct records as the
    # target's
    raised = ["target_raised", "RuntimeError: the tracer's own"]
    assert [one["ended"] for one in each] == [raised] * 3, each
    assert_given_back(each)
