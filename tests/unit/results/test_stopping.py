"""The stop timer: the cause analysis ends at its stop wherever it is, and leaves nothing armed."""

import gc
import os
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from pyct.results import why as why_module
from pyct.results.graphs import OutOfTimeError
from pyct.results.stopping import stopping
from pyct.results.way import Flow
from pyct.results.why import Reason, Run, Walked, explain
from tests.unit.deadline_fires import DEADLINE_FIRES

SOURCE = """\
def f(x):
    y = int("x")
    if x > 0:
        return y
    return 0
"""


def module(tmp_path: Path) -> str:
    file = tmp_path / "m.py"
    file.write_text(textwrap.dedent(SOURCE))
    return str(file)


def armed() -> float:
    """The seconds left on the real-time timer, 0 when none is armed."""
    return signal.getitimer(signal.ITIMER_REAL)[0]


@DEADLINE_FIRES
def test_a_slow_step_still_ends_at_the_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = module(tmp_path)
    handler = signal.getsignal(signal.SIGALRM)
    slow = Flow.marked

    def sleeping(flow: Flow, *args: object) -> frozenset[int]:
        # a step that checks no clock and would run for ten seconds
        time.sleep(10)
        return slow(flow, *args)  # pyrefly: ignore[bad-argument-type]

    monkeypatch.setattr(Flow, "marked", sleeping)
    walked = [Walked(forks=(), failed=True, lines=frozenset({2}))]
    stop_at = time.monotonic() + 0.2

    entries = explain(file, frozenset({3, 4, 5}), frozenset({2}), Run(walked, {}, stop_at=stop_at))
    ended = time.monotonic()

    assert [(entry.lines, entry.reason) for entry in entries] == [
        ((3, 4, 5), Reason.NOT_WORKED_OUT)
    ]
    assert ended - stop_at < 0.1, ended - stop_at
    assert armed() == 0
    assert signal.getsignal(signal.SIGALRM) is handler


def test_a_run_with_no_stop_arms_nothing() -> None:
    handler = signal.getsignal(signal.SIGALRM)
    threads = threading.active_count()

    with stopping(None, time.monotonic):
        assert armed() == 0
        assert signal.getsignal(signal.SIGALRM) is handler
        assert threading.active_count() == threads


def test_the_stop_is_disarmed_and_the_handler_restored_when_the_block_raises() -> None:
    handler = signal.getsignal(signal.SIGALRM)
    threads = threading.active_count()

    with pytest.raises(ValueError), stopping(time.monotonic() + 60, time.monotonic):
        # the stop's own handler, and the watcher that will send its signal
        assert signal.getsignal(signal.SIGALRM) is not handler
        assert threading.active_count() == threads + 1
        raise ValueError

    assert threading.active_count() == threads
    assert armed() == 0
    assert signal.getsignal(signal.SIGALRM) is handler


def test_another_pending_timer_is_left_alone() -> None:
    # pyct's deadline alarm, or anyone's: the stop does not take the timer over
    signal.setitimer(signal.ITIMER_REAL, 60)
    try:
        with stopping(time.monotonic() + 1, time.monotonic):
            assert 59 < armed() <= 60
        assert 59 < armed() <= 60
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


@DEADLINE_FIRES
def test_a_stop_already_past_fires_at_once_and_only_inside_the_block() -> None:
    with pytest.raises(OutOfTimeError), stopping(time.monotonic() - 1, time.monotonic):
        time.sleep(1)

    assert armed() == 0


@DEADLINE_FIRES
def test_the_lines_left_by_a_stop_that_fired_are_each_in_one_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = module(tmp_path)
    walked = [Walked(forks=(), failed=True, lines=frozenset({2}))]
    # the timer fires at once; the steps' own clock checks see no stop
    monkeypatch.setattr(why_module, "clock", lambda: 0.0)

    entries = explain(file, frozenset({1, 3, 4, 5}), frozenset({2}), Run(walked, {}, stop_at=-1.0))

    assert sorted(line for entry in entries for line in entry.lines) == [1, 3, 4, 5]
    assert {entry.reason for entry in entries} == {Reason.NOT_WORKED_OUT}


class _Finalized:
    """An object a target left behind, whose finalizer runs when the collector finds it."""

    def __del__(self) -> None:
        # the stop lands here, where Python prints and drops what a finalizer raises
        time.sleep(0.3)


@DEADLINE_FIRES
# the finalizer's swallowed stop is the point of the test: Python reports it as unraisable
def test_a_stop_a_finalizer_swallowed_comes_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = module(tmp_path)
    # what Python drops from a finalizer, which a stop that landed there becomes
    swallowed: list[type[BaseException] | None] = []
    monkeypatch.setattr(sys, "unraisablehook", lambda raised: swallowed.append(raised.exc_type))
    slow = Flow.marked

    def collecting(flow: Flow, *args: object) -> frozenset[int]:
        # a long step with no clock check, during which the target's garbage is collected
        left = _Finalized()
        left.me = left  # pyrefly: ignore[missing-attribute]
        del left
        gc.collect()
        time.sleep(1.5)
        return slow(flow, *args)  # pyrefly: ignore[bad-argument-type]

    monkeypatch.setattr(Flow, "marked", collecting)
    walked = [Walked(forks=(), failed=True, lines=frozenset({2}))]
    stop_at = time.monotonic() + 0.1

    entries = explain(file, frozenset({3, 4, 5}), frozenset({2}), Run(walked, {}, stop_at=stop_at))
    ended = time.monotonic()

    assert {entry.reason for entry in entries} == {Reason.NOT_WORKED_OUT}
    # the first stop was lost in the finalizer's 0.3 s sleep; the next came soon after it
    assert OutOfTimeError in swallowed
    assert ended - stop_at < 0.5, ended - stop_at
    assert armed() == 0


# stop after stop landing around the block's end, under the previous handler the test names,
# which a signal delivered after the handler is restored would reach. "near" ends each block
# within 50 µs of its stop instant; "sent" ends it 5 to 9 ms after, where the watcher's signal
# lands, so the stop comes on the way out
RACE = """\
import random, signal, sys, threading, time
from pyct.results.graphs import OutOfTimeError
from pyct.results.stopping import stopping

ran = [0]
previous = signal.SIG_DFL if sys.argv[1] == "default" else (lambda *_: ran.__setitem__(0, 1))
late = (-50e-6, 50e-6) if sys.argv[2] == "near" else (5e-3, 9e-3)
signal.signal(signal.SIGALRM, previous)
until = time.monotonic() + {seconds}
blocks = 0
while time.monotonic() < until:
    blocks += 1
    stop_at = time.monotonic() + random.uniform(0, 200e-6)
    try:
        with stopping(stop_at, time.monotonic):
            end = stop_at + random.uniform(*late)
            while time.monotonic() < end:
                pass
    except OutOfTimeError:
        pass
    # after every block: the watcher is gone and the handler is back
    assert threading.active_count() == 1, threading.enumerate()
    assert signal.getsignal(signal.SIGALRM) is previous
assert not ran[0], "the previous handler ran for the stop's signal"
print(blocks)
"""


@pytest.mark.parametrize("window", ["near", "sent"])
@pytest.mark.parametrize("previous", ["default", "counting"])
def test_no_stop_outlives_its_block(previous: str, window: str) -> None:
    # coverage stays out: a signal in its tracer can hang the process (deadline_fires.py)
    env = {k: v for k, v in os.environ.items() if not k.startswith("COVERAGE_")}

    finished = subprocess.run(
        [sys.executable, "-c", RACE.format(seconds=3), previous, window],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )

    # a SIGALRM that arrives once the default handler is back ends the process by SIGALRM
    assert finished.returncode == 0, (finished.returncode, finished.stderr[-2000:])
    assert int(finished.stdout) > 100


def test_a_ctrl_c_on_the_way_out_still_finishes_the_way_out_and_reaches_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = signal.getsignal(signal.SIGALRM)
    threads = threading.active_count()
    restore = signal.signal
    landed = [False]

    def interrupted(number: int, action: object) -> object:
        # a Ctrl-C that lands the first time the way out puts the handler back
        if not landed[0] and action is handler:
            landed[0] = True
            raise KeyboardInterrupt
        return restore(number, action)  # pyrefly: ignore[bad-argument-type]

    monkeypatch.setattr(signal, "signal", interrupted)
    with pytest.raises(KeyboardInterrupt), stopping(time.monotonic() + 60, time.monotonic):
        pass

    assert landed[0]
    assert threading.active_count() == threads
    assert restore(signal.SIGALRM, handler) is handler
