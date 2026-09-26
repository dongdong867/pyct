"""A write the alarm interrupts at any line leaves every later fact reading back as written.

The deadline's SIGALRM handler raises wherever Python happens to be, which can be inside
the journal's writer. Here a trace function raises at the n-th line the journal runs, for
every n a write has, and the facts written after it must still read back exactly.
"""

import functools
from pathlib import Path

from pyct.core.branch import Branch, Expression, Site
from pyct.results.record import DowngradeCount
from pyct.run import journal
from pyct.run.journal import JournalWriter, read
from tests.unit.interrupted import interrupted

SITE = Site(file="t.py", line=3, col=7)
SHARED: list[Expression] = ["+", "x", 1]
FIRST = Branch(expression=[">", SHARED, 10], taken=False, site=SITE)
# shares a part with the first fork, so the part written for it must still be found
LATER = Branch(expression=["==", ["-", ["*", "x", 3], 7], SHARED], taken=False, site=SITE)


JOURNAL = str(Path(journal.__file__))


def test_a_fork_after_an_interrupted_fork_reads_back_as_written() -> None:
    at = 1
    while True:
        buffer = bytearray(1 << 16)
        writer = JournalWriter(buffer)
        landed = interrupted(functools.partial(writer.fork, FIRST), at, JOURNAL)
        writer.fork(LATER)

        reading = read(buffer)
        assert reading.problem is None, at
        assert reading.branches[-1] == LATER, at
        assert all(branch == FIRST for branch in reading.branches[:-1]), at
        if not landed:
            break
        at += 1


def test_counts_after_an_interrupted_downgrade_land_on_their_own_entry() -> None:
    at = 1
    while True:
        buffer = bytearray(1 << 16)
        writer = JournalWriter(buffer)
        writer.downgrade("__abs__", 1)
        landed = interrupted(functools.partial(writer.downgrade, "__neg__", 1), at, JOURNAL)
        writer.downgrade("__neg__", 2)
        writer.downgrade("__neg__", 3)
        writer.downgrade("__abs__", 1)

        assert read(buffer).downgrades == (
            DowngradeCount(name="__abs__", count=1),
            DowngradeCount(name="__neg__", count=3),
            DowngradeCount(name="__abs__", count=1),
        ), at
        if not landed:
            break
        at += 1


def test_an_entry_lost_between_two_entries_of_one_name_keeps_them_apart() -> None:
    at = 1
    while True:
        buffer = bytearray(1 << 16)
        writer = JournalWriter(buffer)
        writer.downgrade("__rshift__", 1)
        writer.downgrade("__rshift__", 2)
        landed = interrupted(functools.partial(writer.downgrade, "__or__", 1), at, JOURNAL)
        writer.downgrade("__rshift__", 1)

        downgrades = read(buffer).downgrades
        # the interrupted entry may be missing; the two around it stay two, with their counts
        assert downgrades in (
            (
                DowngradeCount(name="__rshift__", count=2),
                DowngradeCount(name="__or__", count=1),
                DowngradeCount(name="__rshift__", count=1),
            ),
            (
                DowngradeCount(name="__rshift__", count=2),
                DowngradeCount(name="__rshift__", count=1),
            ),
        ), at
        if not landed:
            break
        at += 1
