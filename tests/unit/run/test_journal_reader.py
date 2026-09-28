"""Reading a journal while its writer still writes: a look at a time, then the rest at the end.

The writer and the reader share a plain bytearray here, and the test moves between them by
hand, so each case pins what a look has read by what reading the journal at the end finds.
"""

import mmap

import pytest

from pyct.core.branch import Branch, Site
from pyct.results.record import DowngradeCount
from pyct.run import journal_reader
from pyct.run.journal import LINE, RECORDS, JournalWriter
from pyct.run.journal_reader import LOOK_BYTES, JournalReader, read

SITE = Site(file="t.py", line=3, col=7)
FORK = Branch(expression=["<", "x", ["+", "y", 1]], taken=True, site=SITE)
# a line record is an 8-byte head and an 8-byte number; its kind is the head's fifth byte
LINE_RECORD = 16
KIND = 4


def shared() -> tuple[bytearray, JournalWriter, JournalReader]:
    buffer = bytearray(1 << 16)
    return buffer, JournalWriter(buffer), JournalReader(buffer)


def test_a_look_reads_nothing_the_look_before_it_did_not_see_committed() -> None:
    buffer, writer, reader = shared()
    writer.line(2)
    reader.look()
    # were the look to have read the line, breaking it now would change nothing
    buffer[RECORDS + KIND] = 99

    reading = reader.finish()

    assert reading.lines == frozenset()
    assert reading.problem == f"could not read the input's facts at byte {RECORDS}"


def test_a_record_a_look_read_is_kept_and_not_read_again() -> None:
    buffer, writer, reader = shared()
    writer.line(2)
    writer.fork(FORK)
    reader.look()
    reader.look()
    buffer[RECORDS + KIND] = 99
    writer.line(3)

    reading = reader.finish()

    assert reading.lines == frozenset({2, 3})
    assert reading.branches == (FORK,)
    assert reading.problem is None


def test_looks_and_the_end_read_back_what_one_reading_at_the_end_reads() -> None:
    buffer, writer, reader = shared()
    for line in range(2, 40):
        writer.line(line)
        writer.fork(Branch(expression=[">", ["+", "x", line], 0], taken=True, site=SITE))
        writer.downgrade("__xor__", SITE, 1)
        reader.look()
    writer.end(None)

    assert reader.finish() == read(buffer)


def test_a_count_that_grows_after_a_look_read_its_entry_reads_back_grown() -> None:
    _, writer, reader = shared()
    writer.downgrade("__abs__", SITE, 1)
    writer.line(2)
    reader.look()
    reader.look()
    for count in range(2, 6):
        writer.downgrade("__abs__", SITE, count)
    reader.look()

    reading = reader.finish()

    assert reading.downgrades == (DowngradeCount("__abs__", 5, SITE),)
    assert reading.lines == frozenset({2})


def test_a_carried_on_count_that_grows_after_a_look_reads_back_grown() -> None:
    buffer, writer, reader = shared()
    writer.downgrade("__abs__", SITE, 1)
    # the alarm cut the writer's note of its entry short, so the next count carries it on
    writer._counting = None
    writer.downgrade("__abs__", SITE, 2)
    reader.look()
    reader.look()
    writer.downgrade("__abs__", SITE, 3)

    reading = reader.finish()

    assert reading.downgrades == (DowngradeCount("__abs__", 3, SITE),)
    assert reading == read(buffer)


def test_a_record_a_look_cannot_read_is_read_again_once_the_writer_ended() -> None:
    buffer, writer, reader = shared()
    writer.line(2)
    writer.line(3)
    # the second line's kind not there yet, as a look can find a record on a busy machine
    buffer[RECORDS + LINE_RECORD + KIND] = 0
    reader.look()
    reader.look()
    buffer[RECORDS + LINE_RECORD + KIND] = LINE
    writer.line(4)
    reader.look()

    reading = reader.finish()

    assert reading.lines == frozenset({2, 3, 4})
    assert reading.problem is None


def test_a_look_that_finds_no_mark_it_can_read_reads_on_from_the_last_it_could() -> None:
    buffer, writer, reader = shared()
    writer.line(2)
    reader.look()
    committed = bytes(buffer[0:8])
    buffer[0:8] = (len(buffer) + 8).to_bytes(8, "little")
    reader.look()
    buffer[0:8] = committed
    reader.look()

    reading = reader.finish()

    assert reading.lines == frozenset({2})
    assert reading.problem is None


def test_a_mark_the_end_cannot_read_keeps_no_fact_a_look_read() -> None:
    buffer, writer, reader = shared()
    writer.line(2)
    reader.look()
    reader.look()
    buffer[0:8] = (len(buffer) + 8).to_bytes(8, "little")

    reading = reader.finish()

    assert reading.lines == frozenset()
    assert reading.problem == "could not read the input's facts at byte 0"
    assert reading == read(buffer)


def test_a_state_the_end_cannot_read_keeps_no_fact_a_look_read() -> None:
    buffer, writer, reader = shared()
    writer.line(2)
    reader.look()
    reader.look()
    buffer[8] = 7

    reading = reader.finish()

    assert reading.lines == frozenset()
    assert reading.problem == "could not read the input's facts at byte 8"


def test_the_forks_of_one_place_share_one_site() -> None:
    _, writer, reader = shared()
    writer.fork(FORK)
    writer.fork(Branch(expression=["<", "x", 2], taken=False, site=Site("t.py", 3, 7)))

    first, second = reader.finish().branches

    assert first.site is second.site


def test_a_count_that_grew_after_a_look_keeps_its_growth_when_another_entry_follows() -> None:
    buffer, writer, reader = shared()
    writer.downgrade("__xor__", SITE, 1)
    writer.line(2)
    reader.look()
    reader.look()
    for count in range(2, 1001):
        writer.downgrade("__xor__", SITE, count)
    writer.downgrade("__abs__", Site("t.py", 4, 1), 1)
    reader.look()
    reader.look()

    reading = reader.finish()

    assert reading.downgrades == (
        DowngradeCount("__xor__", 1000, SITE),
        DowngradeCount("__abs__", 1, Site("t.py", 4, 1)),
    )
    assert reading == read(buffer)


def test_the_forks_a_look_read_before_a_record_it_cannot_read_are_kept_once() -> None:
    buffer, writer, reader = shared()
    reader.look()
    writer.fork(FORK)
    writer.fork(FORK)
    at = int.from_bytes(buffer[0:8], "little")
    writer.line(3)
    writer.fork(FORK)
    buffer[at + KIND] = 99
    reader.look()
    reader.look()

    reading = reader.finish()

    assert reading.branches == (FORK, FORK)
    assert reading.problem == f"could not read the input's facts at byte {at}"
    assert reading == read(buffer)


def test_a_stop_during_a_look_leaves_the_journal_free_to_unmap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def stopped(payload: memoryview) -> object:
        raise KeyboardInterrupt

    # written apart, as the input's process writes it, so only the reader holds a view here
    written, _, _ = shared()
    JournalWriter(written).fork(FORK)
    buffer = mmap.mmap(-1, len(written))
    buffer[:] = written
    reader = JournalReader(buffer)
    reader.look()
    monkeypatch.setattr(journal_reader, "_decoded", stopped)

    try:
        reader.look()
    except KeyboardInterrupt:
        # the stop's frames still hold what the look was reading when it landed
        buffer.close()

    assert buffer.closed


def test_a_look_reads_a_bounded_stretch_and_says_when_it_fell_behind() -> None:
    buffer = bytearray(RECORDS + 4 * LOOK_BYTES)
    writer, reader = JournalWriter(buffer), JournalReader(buffer)
    for line in range(2, 2 + 2 * LOOK_BYTES // LINE_RECORD + 10):
        writer.line(line)
    beyond = RECORDS + LOOK_BYTES + LINE_RECORD
    assert reader.look() is False

    assert reader.look() is True
    # the record past the look's bound is still unread, so breaking it now shows at the end
    buffer[beyond + KIND] = 99
    reading = reader.finish()

    assert reading.problem == f"could not read the input's facts at byte {beyond}"
    assert max(reading.lines) == 2 + LOOK_BYTES // LINE_RECORD


def test_looks_that_fell_behind_catch_up() -> None:
    buffer = bytearray(RECORDS + 4 * LOOK_BYTES)
    writer, reader = JournalWriter(buffer), JournalReader(buffer)
    for line in range(2, 2 + 3 * LOOK_BYTES // LINE_RECORD):
        writer.line(line)
    reader.look()

    behind = [reader.look() for _ in range(4)]

    assert behind == [True, True, False, False]
    assert reader.finish() == read(buffer)
