"""A downgrade's site through the journal: each entry keeps where its calls were made."""

import sys

from pyct.core.branch import Site
from pyct.results.record import DowngradeCount
from pyct.run.journal import JournalWriter, read

SITE = Site(file="t.py", line=3, col=7)


def journal(size: int = 1 << 16) -> bytearray:
    return bytearray(size)


def test_one_name_at_another_site_starts_its_own_entry() -> None:
    buffer = journal()
    writer = JournalWriter(buffer)
    other = Site(file="u.py", line=9, col=4)

    writer.downgrade("__abs__", SITE, 1)
    writer.downgrade("__abs__", SITE, 2)
    writer.downgrade("__abs__", other, 1)
    writer.downgrade("__abs__", other, 2)

    assert read(buffer).downgrades == (
        DowngradeCount(name="__abs__", count=2, site=SITE),
        DowngradeCount(name="__abs__", count=2, site=other),
    )


def test_a_carried_on_count_at_another_site_stays_its_own_entry() -> None:
    buffer = journal()
    writer = JournalWriter(buffer)
    other = Site(file="u.py", line=9, col=4)

    writer.downgrade("__abs__", SITE, 1)
    # what a writer whose note of the last entry the alarm cut short writes for a later count
    JournalWriter.__init__(writer, buffer)
    writer._at = read_end(buffer)
    writer.downgrade("__abs__", other, 2)

    assert read(buffer).downgrades == (
        DowngradeCount(name="__abs__", count=1, site=SITE),
        DowngradeCount(name="__abs__", count=2, site=other),
    )


def test_a_site_in_a_file_whose_name_is_not_utf8_reads_back_as_written() -> None:
    buffer = journal()
    writer = JournalWriter(buffer)
    # how Python holds a file name whose bytes are not UTF-8
    site = Site(file="caf\udce9.py", line=1, col=0)

    writer.downgrade("__abs__", site, 1)

    assert read(buffer).downgrades == (DowngradeCount(name="__abs__", count=1, site=site),)


def read_end(buffer: bytearray) -> int:
    """Where the next record goes: the committed mark the header's first word holds."""
    return int.from_bytes(buffer[:8], sys.byteorder)
