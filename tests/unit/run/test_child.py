"""The input's own process, served for real in a child this test forks."""

import mmap
import os

from pyct.results.failure import FailureKind
from pyct.run.child import serve
from pyct.run.journal import CAPACITY, JournalWriter, read


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
