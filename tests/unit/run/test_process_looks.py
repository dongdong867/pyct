"""pyct's process looks at an input's facts while it waits for the input's process to end."""

import mmap
import os
import signal
import time
from collections.abc import Callable

import pytest

from pyct.run import process
from pyct.run.journal import COMMITTED, HEAD, LINE, NUMBER, RECORDS, WORD
from pyct.run.journal_reader import JournalReader
from pyct.run.process import KILL_GRACE, LOOK_EVERY, Waited, watched
from tests.unit.run.test_process import sleeper


def _noting(looks: list[float]) -> Callable[[], bool]:
    """A look that notes when it ran, and never falls behind."""

    def look() -> bool:
        looks.append(time.monotonic())
        return False

    return look


def test_pyct_looks_while_the_process_runs() -> None:
    looks: list[float] = []
    started = time.monotonic()

    waited = watched(lambda: sleeper(0.3), None, _noting(looks))

    waited_for = time.monotonic() - started
    assert waited == Waited(signal=None, code=0, killed=False)
    # a look every 10 ms at most over the wait; a loaded machine makes fewer, never none
    assert 2 <= len(looks) <= waited_for / LOOK_EVERY + 1


def test_pyct_looks_until_it_kills_a_process_past_its_deadline() -> None:
    looks: list[float] = []
    started = time.monotonic()

    waited = watched(lambda: sleeper(10), started + 0.05, _noting(looks))

    assert waited == Waited(signal=signal.SIGKILL, code=None, killed=True)
    # looks stop at the kill, give or take how late a loaded machine wakes pyct's process
    assert looks
    assert looks[-1] < started + 0.05 + KILL_GRACE + 0.25


def test_pyct_looks_where_the_system_gives_no_notice_of_an_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(process, "ends_by", lambda pid, instant: None)
    looks: list[float] = []

    waited = watched(lambda: sleeper(0.2), None, _noting(looks))

    assert waited == Waited(signal=None, code=0, killed=False)
    assert len(looks) >= 2


def test_a_look_that_raises_ends_the_process_on_the_way_out() -> None:
    def broken() -> bool:
        raise KeyboardInterrupt

    started = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        watched(lambda: sleeper(10), None, broken)

    # the process was killed and reaped at once, not waited for
    assert time.monotonic() - started < 5


def _journal_of_lines(count: int) -> bytes:
    """``count`` committed line records, as a writer far ahead of pyct's looks leaves them."""
    records = (HEAD.pack(NUMBER.size, LINE) + NUMBER.pack(2)) * count
    header = bytearray(RECORDS)
    WORD.pack_into(header, COMMITTED * WORD.size, RECORDS + len(records))
    return bytes(header) + records


def test_the_kill_lands_on_time_while_the_looks_fall_behind() -> None:
    # about 96 MB of records, which one look took about 1.3 s to read through
    written = _journal_of_lines(6_000_000)
    with mmap.mmap(-1, len(written)) as buffer:
        reader = JournalReader(buffer)

        def writes_then_hangs() -> int:
            pid = os.fork()
            if pid == 0:  # pragma: no cover
                buffer[:] = written
                time.sleep(10)
                os._exit(0)
            return pid

        started = time.monotonic()
        waited = watched(writes_then_hangs, started + 0.05, reader.look)
        took = time.monotonic() - started
        reader.finish()

    assert waited.killed
    # the kill waits for one look at most, and a look reads a bounded stretch
    assert took < 0.05 + KILL_GRACE + 0.3, took
