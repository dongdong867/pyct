"""pyct's process looks at an input's facts while it waits for the input's process to end."""

import signal
import time

import pytest

from pyct.run import process
from pyct.run.process import KILL_GRACE, LOOK_EVERY, Waited, watched
from tests.unit.run.test_process import sleeper


def test_pyct_looks_while_the_process_runs() -> None:
    looks: list[float] = []

    waited = watched(lambda: sleeper(0.3), None, lambda: looks.append(time.monotonic()))

    assert waited == Waited(signal=None, code=0, killed=False)
    # a look every 10 ms over 0.3 s; a loaded machine makes fewer, never none
    assert 2 <= len(looks) <= 0.3 / LOOK_EVERY + 1


def test_pyct_looks_until_it_kills_a_process_past_its_deadline() -> None:
    looks: list[float] = []
    started = time.monotonic()

    waited = watched(lambda: sleeper(10), started + 0.05, lambda: looks.append(time.monotonic()))

    assert waited == Waited(signal=signal.SIGKILL, code=None, killed=True)
    # looks stop at the kill, give or take how late a loaded machine wakes pyct's process
    assert looks
    assert looks[-1] < started + 0.05 + KILL_GRACE + 0.25


def test_pyct_looks_where_the_system_gives_no_notice_of_an_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(process, "ends_by", lambda pid, instant: None)
    looks: list[float] = []

    waited = watched(lambda: sleeper(0.2), None, lambda: looks.append(time.monotonic()))

    assert waited == Waited(signal=None, code=0, killed=False)
    assert len(looks) >= 2


def test_a_look_that_raises_ends_the_process_on_the_way_out() -> None:
    def broken() -> None:
        raise KeyboardInterrupt

    started = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        watched(lambda: sleeper(10), None, broken)

    # the process was killed and reaped at once, not waited for
    assert time.monotonic() - started < 5
