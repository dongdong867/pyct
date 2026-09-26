"""The journal's committed mark and a growing count, read while another process writes them."""

import contextlib
import mmap
import os
import signal
import time
from typing import NoReturn

from pyct.run.journal import RECORDS, JournalWriter

# how many times the reader looks at the two words while the writer writes them
LOOKS = 300_000
# how long the writer may take to write the two words at all
STARTS_WITHIN = 5.0
# where the first count sits: the downgrade record comes first, its count after its 8-byte head
COUNT_AT = (RECORDS + 8) // 8


def test_the_mark_and_a_count_never_read_zero_while_they_are_written() -> None:
    parent = os.getpid()
    with mmap.mmap(-1, 64 * 1024 * 1024) as buffer:
        pid = os.fork()
        if pid == 0:
            write_while_watched(buffer, parent)
        try:
            with memoryview(buffer) as bytes_, bytes_.cast("Q") as words:
                started(words)
                zeros = zeros_seen(words)
        finally:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)

    assert zeros == 0


def write_while_watched(buffer: mmap.mmap, parent: int) -> NoReturn:
    """Write in this child until the test's process is gone, then exit: never back into pytest."""
    with contextlib.suppress(BaseException):
        write(buffer, parent)
    os._exit(0)


def write(buffer: mmap.mmap, parent: int) -> None:
    """Grow one count in place, and add a line now and then, while ``parent`` is alive."""
    writer = JournalWriter(buffer)
    writer.downgrade("__abs__", 1)
    count = 2
    while os.getppid() == parent:
        for _ in range(1024):
            writer.downgrade("__abs__", count)
            if count % 16 == 0:
                writer.line(count)
            count += 1


def started(words: memoryview) -> None:
    """Wait until the writer wrote the mark and the count, within ``STARTS_WITHIN``."""
    deadline = time.monotonic() + STARTS_WITHIN
    while words[0] == 0 or words[COUNT_AT] == 0:
        assert time.monotonic() < deadline, "the writer wrote nothing"


def zeros_seen(words: memoryview) -> int:
    """How often the mark or the count read 0 over ``LOOKS`` looks."""
    return sum(1 for _ in range(LOOKS) if words[0] == 0 or words[COUNT_AT] == 0)
