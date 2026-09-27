"""The input's own process, served for real in a child this test forks."""

import mmap
import os
import signal

from pyct.results.failure import FailureKind
from pyct.run.child import serve, settle
from pyct.run.journal import CAPACITY, JournalWriter, read
from pyct.run.process import STOP_SIGNALS


def test_a_raise_out_of_pyct_s_own_code_is_a_pyct_bug_on_the_input_s_line() -> None:
    def broken(watch: JournalWriter) -> None:
        raise RuntimeError("pyct broke")

    with mmap.mmap(-1, CAPACITY) as buffer:
        pid = os.fork()
        if pid == 0:
            serve(JournalWriter(buffer), broken)
        _, status = os.waitpid(pid, 0)
        reading = read(buffer)

    assert os.waitstatus_to_exitcode(status) == 0
    assert reading.ended
    assert reading.end is not None
    assert reading.end.kind is FailureKind.PYCT_BUG
    assert reading.end.detail == "RuntimeError: pyct broke"
    assert reading.end.traceback is not None
    assert "broken" in reading.end.traceback


def test_the_input_s_process_takes_each_stop_signal_by_its_default_action() -> None:
    previous = signal.signal(signal.SIGTERM, lambda number, frame: None)
    try:
        with mmap.mmap(-1, CAPACITY) as buffer:
            pid = os.fork()
            if pid == 0:
                settle(JournalWriter(buffer))
                defaults = all(signal.getsignal(n) is signal.SIG_DFL for n in STOP_SIGNALS)
                unblocked = not signal.pthread_sigmask(signal.SIG_BLOCK, set()) & STOP_SIGNALS
                os._exit(0 if defaults and unblocked else 1)
            _, status = os.waitpid(pid, 0)
    finally:
        signal.signal(signal.SIGTERM, previous)

    assert os.waitstatus_to_exitcode(status) == 0
