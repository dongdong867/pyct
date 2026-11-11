"""A call on model-written code runs in a child of pyct's process, with a time limit, and hands
back its answer as JSON with what it recorded, or how the child ended."""

import operator
import os
import signal
import threading
import time
import types

import pytest

from pyct.intercept.model_code import compile_model_code
from pyct.results.failure import Failure, FailureKind
from pyct.run import model_runs
from pyct.run.model_runs import ANSWER_CAPACITY, CannotFork, ModelCall, ModelRun, run_model

FILE = "<model m:2:7>"


@pytest.fixture(autouse=True)
def _one_thread(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """The process as pyct's own is in a run, one thread: pytest-timeout's watch runs another,
    and a fork beside it is safe, since it takes no lock the call needs."""
    if "second_thread" not in request.node.name:
        monkeypatch.setattr(model_runs, "running", lambda: 1)


def code_of(text: str) -> types.CodeType:
    code = compile_model_code(text, FILE, lambda tree: tree)
    assert isinstance(code, types.CodeType)
    return code


def ran(text: str, args: dict[str, object], seconds: float = 5.0, **names: object) -> ModelRun:
    call = ModelCall(code_of(text), "f", args, names)
    done = run_model(call, time.monotonic() + seconds)
    assert isinstance(done, ModelRun)
    return done


def test_the_answer_comes_back_as_json_with_the_forks_the_call_recorded() -> None:
    text = "def f(n, s):\n    if n > 3:\n        return [n, n > 4, s + 'x', None]\n    return []\n"

    done = ran(text, {"n": 5, "s": "a"})

    assert done.answer == '[5, true, "ax", null]'
    assert done.unencoded is None
    assert done.result.failure is None
    assert [(fork.expression, fork.taken) for fork in done.result.branches] == [
        ([">", "n", 3], True)
    ]


def test_the_facts_and_downgrades_the_call_recorded_come_back() -> None:
    # `n ^ 0` is int's own, which leaves the value plain and says so; the walk of a dict that
    # holds a key once it is stored takes its first pass as a fact
    text = (
        "def f(n, d):\n    d['a'] = n ^ 0\n    count = 0\n"
        "    for k in d:\n        count += 1\n    return [count, d]\n"
    )

    done = ran(text, {"n": 5, "d": {}})

    assert done.answer == '[1, {"a": 5}]'
    assert [entry.name for entry in done.result.downgrades] == ["__xor__"]
    assert [(fact.expression, fact.taken) for fact in done.result.facts] == [
        ([">", ["+", ["len", "d"], 1], 0], True)
    ]


def test_a_raise_is_the_call_s_with_python_s_own_words() -> None:
    # the words plain Python gives this raise
    with pytest.raises(ZeroDivisionError) as plain:
        operator.floordiv(5, 0)
    said = f"ZeroDivisionError: {plain.value}"

    done = ran("def f(n):\n    return n // 0\n", {"n": 5})

    assert done.answer is None
    assert done.result.failure == Failure(kind=FailureKind.TARGET_RAISED, detail=said)


@pytest.mark.usefixtures("deadline_fires_in_a_child")
def test_a_call_past_its_limit_is_ended_and_said_so() -> None:
    started = time.monotonic()

    done = ran("def f(n):\n    while True:\n        n = n + 1\n", {"n": 0}, seconds=0.3)

    assert done.answer is None
    assert done.result.failure == Failure(kind=FailureKind.TIMEOUT, detail="deadline passed")
    assert time.monotonic() - started < 3


def test_a_crash_ends_the_child_alone() -> None:
    text = "def f(n):\n    os.kill(os.getpid(), signal.SIGKILL)\n"

    done = ran(text, {"n": 0}, os=os, signal=signal)

    assert done.answer is None
    assert done.result.failure == Failure(kind=FailureKind.CRASHED, detail="killed by SIGKILL")


def test_what_the_call_changes_stays_in_the_child() -> None:
    kept: list[int] = []

    done = ran("def f(n):\n    kept.append(n)\n    return len(kept)\n", {"n": 1}, kept=kept)

    assert done.answer == "1"
    assert kept == []


def test_an_answer_json_cannot_hold_is_said_so() -> None:
    done = ran("def f(n):\n    return {n}\n", {"n": 1})

    assert done.answer is None
    assert done.unencoded == "set is not a JSON value"
    assert done.result.failure is None


def test_an_object_key_json_cannot_hold_is_said_so() -> None:
    done = ran("def f(n):\n    return {n: 1}\n", {"n": 1})

    assert done.unencoded == "a key of type int is not one a JSON object holds"


def test_an_answer_past_the_capacity_is_said_so() -> None:
    done = ran("def f(n):\n    return 'x' * n\n", {"n": ANSWER_CAPACITY})

    assert done.answer is None
    assert done.unencoded == f"the answer's {ANSWER_CAPACITY + 2} bytes are over {ANSWER_CAPACITY}"


def test_a_process_running_a_second_thread_cannot_fork() -> None:
    release = threading.Event()
    thread = threading.Thread(target=release.wait)
    thread.start()
    try:
        done = run_model(
            ModelCall(code_of("def f():\n    return 1\n"), "f", {}), time.monotonic() + 5
        )
    finally:
        release.set()
        thread.join()

    assert done == CannotFork()
