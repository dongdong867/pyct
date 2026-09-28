"""A journal problem an input's process meets while pyct looks at its journal: the input's line
says pyct failed, with the detail and the facts before the problem that one reading at the end
gives. The input's process is a child this test forks, and it writes its journal by hand.
"""

import mmap
import os
import sys
import time
from collections.abc import Callable

from pyct.core.branch import Branch, Site
from pyct.execution.execute import ExecutionResult
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import DowngradeCount
from pyct.run.journal import NUMBER, RECORDS, JournalWriter
from pyct.run.journal_reader import JournalReader
from pyct.run.process import ending, watched

SITE = Site(file="t.py", line=3, col=7)
FORK = Branch(expression=["<", "x", ["+", "y", 1]], taken=True, site=SITE)
# long enough for pyct's process to look at the journal in between
_PAUSE = 0.05


def _input_writing(size: int, write: Callable[[mmap.mmap, JournalWriter], None]) -> ExecutionResult:
    """What pyct makes of an input whose process runs ``write`` into a journal of ``size`` bytes.

    pyct's process looks at the journal while the process writes, and reads
    the rest once it has ended, as it does for every input it forks.
    """
    with mmap.mmap(-1, size) as buffer:
        reader = JournalReader(buffer)

        def start() -> int:
            pid = os.fork()
            # coverage.py cannot see the child's lines: they run in a frame begun before the fork
            if pid == 0:  # pragma: no cover
                try:
                    write(buffer, JournalWriter(buffer))
                finally:
                    sys.stdout.flush()
                    os._exit(0)
            return pid

        waited = watched(start, None, reader.look)
        return ending(reader.finish(), waited)


def _facts_before(writer: JournalWriter, pause: float = _PAUSE) -> None:
    """The facts before the problem, with a pause after each so pyct looks at them."""
    writer.start()
    writer.line(2)
    writer.fork(FORK)
    time.sleep(pause)
    for count in range(1, 4):
        writer.downgrade("__xor__", SITE, count)
        time.sleep(pause)


def _committed_after_the_facts_before() -> int:
    """Where the facts before the problem end, as the same facts written again lay them out."""
    scratch = bytearray(RECORDS + 4096)
    _facts_before(JournalWriter(scratch), pause=0)
    return int.from_bytes(scratch[0:8], sys.byteorder)


_BEFORE_LINES = frozenset({2})
_BEFORE_DOWNGRADES = (DowngradeCount("__xor__", 3, SITE),)


def test_a_full_journal_ends_its_input_as_a_pyct_bug_with_the_facts_before() -> None:
    def fills(buffer: mmap.mmap, writer: JournalWriter) -> None:
        _facts_before(writer)
        for line in range(3, 10_000):
            writer.line(line)
        time.sleep(_PAUSE)
        writer.end(None)

    size = RECORDS + 4096
    result = _input_writing(size, fills)

    assert result.failure == Failure(FailureKind.PYCT_BUG, f"the journal is full at {size} bytes")
    assert result.branches == (FORK,)
    assert result.downgrades == _BEFORE_DOWNGRADES
    assert result.lines > _BEFORE_LINES
    assert max(result.lines) < 10_000


def test_an_unreadable_record_ends_its_input_as_a_pyct_bug_with_the_facts_before() -> None:
    at = _committed_after_the_facts_before()

    def breaks(buffer: mmap.mmap, writer: JournalWriter) -> None:
        _facts_before(writer)
        # a record of a kind the journal has none of, committed as a whole, then looked at
        writer._record(99, NUMBER.pack(99))
        time.sleep(_PAUSE)
        writer.line(100)
        writer.end(None)

    result = _input_writing(RECORDS + 4096, breaks)

    assert result.failure == Failure(
        FailureKind.PYCT_BUG, f"could not read the input's facts at byte {at}"
    )
    assert result.branches == (FORK,)
    assert result.downgrades == _BEFORE_DOWNGRADES
    assert result.lines == _BEFORE_LINES
