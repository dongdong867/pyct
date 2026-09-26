"""The journal's committed mark and a growing count, read while another process writes them."""

import mmap
import os
import signal

from pyct.run.journal import RECORDS, JournalWriter

# how many times the reader looks at the two words while the writer writes them
LOOKS = 300_000


def test_the_mark_and_a_count_never_read_zero_while_they_are_written() -> None:
    with mmap.mmap(-1, 64 * 1024 * 1024) as buffer:
        pid = os.fork()
        if pid == 0:
            writer = JournalWriter(buffer)
            writer.downgrade("__abs__", 1)
            count = 2
            while True:
                writer.line(count)
                writer.downgrade("__abs__", count)
                count += 1
        with memoryview(buffer) as bytes_, bytes_.cast("Q") as words:
            try:
                zeros = _zeros_seen(words)
            finally:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)

    assert zeros == 0


def _zeros_seen(words: memoryview) -> int:
    """How often the mark or the first count read 0 once both were written."""
    # the downgrade record comes first: its count sits right after its 8-byte head
    count_at = (RECORDS + 8) // 8
    while words[0] == 0 or words[count_at] == 0:
        pass
    return sum(1 for _ in range(LOOKS) if words[0] == 0 or words[count_at] == 0)
