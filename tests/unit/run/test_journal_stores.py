"""The journal's committed mark and a growing count, read while another process writes them."""

import contextlib
import dataclasses
import mmap
import os
import signal
import time
from typing import NoReturn

import pytest

from pyct.core.branch import Branch, Expression, Fact, Site
from pyct.run.journal import RECORDS, JournalWriter
from pyct.run.journal_reader import read

SITE = Site(file="t.py", line=3, col=7)

# how long the reader looks at the two words while the writer writes them
SAMPLING = 1.0
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
    writer.downgrade("__abs__", SITE, 1)
    count = 2
    while os.getppid() == parent:
        for _ in range(1024):
            writer.downgrade("__abs__", SITE, count)
            if count % 16 == 0:
                writer.line(count)
            count += 1


def started(words: memoryview) -> None:
    """Wait until the writer wrote the mark and the count, within ``STARTS_WITHIN``."""
    deadline = time.monotonic() + STARTS_WITHIN
    while words[0] == 0 or words[COUNT_AT] == 0:
        assert time.monotonic() < deadline, "the writer wrote nothing"


def zeros_seen(words: memoryview) -> int:
    """How often the mark or the count read 0 over ``SAMPLING`` seconds of looking."""
    zeros = 0
    stop = time.monotonic() + SAMPLING
    while time.monotonic() < stop:
        for _ in range(10_000):
            if words[0] == 0 or words[COUNT_AT] == 0:
                zeros += 1
    return zeros


def test_a_fact_crosses_the_journal_placed_after_the_forks_before_it() -> None:
    buffer = bytearray(1 << 16)
    config: list[Expression] = ["len", "config"]
    passed = Branch(expression=[">", config, 1], taken=True, site=Site("m.py", 2, 4))
    plain = Branch(expression=["!=", config, 0], taken=False, site=Site("m.py", 3, 4))
    decided = Fact([">", config, 0], True, Site("m.py", 2, 4), place=["walked", "config", "'a'"])
    placed = Fact(None, True, Site("m.py", 2, 4), place=["walked", "config", "'b'"])

    writer = JournalWriter(buffer)
    writer.fact(decided)
    writer.fork(passed)
    writer.fact(placed)
    writer.fork(plain)
    reading = read(buffer)

    assert reading.branches == (passed, plain)
    assert reading.facts == (decided, dataclasses.replace(placed, after=1))
    # one part, however many records name it
    assert reading.facts[0].expression[1] is reading.branches[0].expression[1]  # type: ignore[index]


@pytest.mark.parametrize(
    "seventh", [b"1", b"false", b"true, true"], ids=["a number", "false", "two"]
)
def test_a_fork_record_holds_six_items_or_a_split_walk_s_mark(seventh: bytes) -> None:
    buffer = bytearray(1 << 16)
    writer = JournalWriter(buffer)
    writer.fork(Branch(expression="abcdefghijklmnop", taken=True, site=Site("m.py", 2, 4)))
    written = b'"abcdefghijklmnop", true, "m.py", 2, 4, false]'
    at = buffer.index(written)
    rewritten = b'"a", true, "m.py", 2, 4, false, ' + seventh
    buffer[at : at + len(written)] = rewritten.ljust(len(written) - 1) + b"]"

    reading = read(buffer)

    assert reading.branches == () and reading.problem is not None


def test_a_split_walk_s_fork_keeps_its_mark() -> None:
    buffer = bytearray(1 << 16)
    writer = JournalWriter(buffer)
    walk = Branch([">", ["len", ["splitlines", "s"]], 0], True, Site("m.py", 2, 4), split_walk=True)
    writer.fork(walk)
    writer.fork(Branch(expression="t", taken=False, site=Site("m.py", 3, 4)))

    reading = read(buffer)

    assert [branch.split_walk for branch in reading.branches] == [True, False]
    assert reading.branches[0] == walk


def test_a_fact_with_more_than_a_place_beside_it_is_unreadable() -> None:
    buffer = bytearray(1 << 16)
    writer = JournalWriter(buffer)
    writer.fact(Fact("x", True, Site("m.py", 2, 4), place="y"))
    at = buffer.index(b'"y"')
    buffer[at : at + 3] = b"1,2"

    reading = read(buffer)

    assert reading.facts == () and reading.problem is not None
