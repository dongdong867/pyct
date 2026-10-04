"""The note an `is` keeps on its fork, through the journal: a seventh item, never a sixth."""

import json

import pytest

from pyct.core.branch import Branch, Site
from pyct.run.journal import FORK, HEAD, RECORDS, JournalWriter
from pyct.run.journal_reader import read

SITE = Site(file="t.py", line=3, col=7)


def _fork_record(buffer: bytearray) -> list[object]:
    """The first fork record's items, past the parts written before it, each padded to 8 bytes."""
    at = RECORDS
    while True:
        length, kind = HEAD.unpack_from(buffer, at)
        payload = at + HEAD.size
        if kind == FORK:
            return json.loads(bytes(buffer[payload : payload + length]))
        at = payload + (length + 7) // 8 * 8


def written(branch: Branch) -> tuple[list[object], tuple[Branch, ...], list[bool | None]]:
    """The fork's record as written, and the forks read back with their notes."""
    buffer = bytearray(1 << 16)
    JournalWriter(buffer).fork(branch)
    record = _fork_record(buffer)
    branches = read(buffer).branches
    return record, branches, [each.is_held for each in branches]


@pytest.mark.parametrize("held", [True, False])
def test_a_noted_fork_reads_back_with_its_note(held: bool) -> None:
    branch = Branch(["<", "x", 9], True, SITE, is_held=held)

    record, branches, notes = written(branch)

    assert record[6:] == [held]
    assert branches == (branch,)
    assert notes == [held]


def test_a_fork_with_no_note_is_written_in_six_items() -> None:
    branch = Branch(["<", "x", 9], True, SITE)

    record, branches, notes = written(branch)

    assert len(record) == 6
    assert branches == (branch,)
    assert notes == [None]
