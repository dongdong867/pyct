"""A recorded run of a piece crosses the journal in a room of its own: it reads back as written,
and it never takes the room of the input's own facts nor stops the writer."""

import struct

import pytest

from pyct.core.entry import pieces
from pyct.core.foundation.branch import Changed, GoingIn, PieceRun, Site
from pyct.run.journal import HEAD, PIECE, PIECE_ROOM, RECORDS, JournalWriter
from pyct.run.journal_reader import read

SITE = Site(file="té.py", line=3, col=7)
RUN = PieceRun(
    site=SITE,
    going_in=(GoingIn("n", "2", tracked=True), GoingIn("é", '{"k": ["a\\"b"]}', tracked=False)),
    changed=(Changed("t", "[1.5, null, true]"),),
)
ROOM = 4096


def test_a_recorded_run_reads_back_as_it_was_written_among_the_other_facts() -> None:
    buffer = bytearray(RECORDS + 8192 + ROOM)
    writer = JournalWriter(buffer, pieces=ROOM)
    bare = PieceRun(site=Site(file="u.py", line=9, col=0), going_in=(), changed=())

    writer.line(2)
    writer.piece(RUN)
    writer.line(3)
    writer.piece(bare)

    reading = read(buffer)
    assert reading.pieces == (RUN, bare)
    assert reading.lines == frozenset({2, 3})
    assert (reading.problem, reading.bound) == (None, None)


def test_a_writer_with_no_room_for_runs_drops_each_and_goes_on() -> None:
    buffer = bytearray(RECORDS + 8192)
    writer = JournalWriter(buffer)

    writer.piece(RUN)
    writer.line(2)

    reading = read(buffer)
    assert (reading.pieces, reading.lines, reading.problem) == ((), frozenset({2}), None)


def test_runs_past_their_room_are_dropped_while_the_writer_goes_on() -> None:
    buffer = bytearray(RECORDS + 8192 + ROOM)
    writer = JournalWriter(buffer, pieces=ROOM)

    for _ in range(100):
        writer.piece(RUN)
    writer.line(5)

    reading = read(buffer)
    assert 0 < len(reading.pieces) < 100
    assert reading.lines == frozenset({5})
    assert (reading.problem, reading.bound) == (None, None)


def lines_until_full(writer: JournalWriter, *, with_runs: bool) -> None:
    for line in range(10_000):
        writer.line(line)
        if with_runs and line % 7 == 0:
            writer.piece(RUN)


def test_runs_never_take_the_room_of_the_input_s_own_facts() -> None:
    plain, with_runs = bytearray(RECORDS + 8192 + ROOM), bytearray(RECORDS + 8192 + ROOM)

    lines_until_full(JournalWriter(plain, pieces=ROOM), with_runs=False)
    lines_until_full(JournalWriter(with_runs, pieces=ROOM), with_runs=True)

    alone, beside = read(plain), read(with_runs)
    assert beside.pieces
    assert beside.lines == alone.lines
    # the note names the bytes the input's own facts have, as it does with no room for runs
    assert beside.bound == alone.bound == f"the journal is full at {RECORDS + 8192} bytes"


def test_the_room_for_runs_holds_every_run_an_input_records() -> None:
    # the largest run for what it counts: a file of four-byte characters and no values
    file = "\U0001f600" * 100
    run = PieceRun(site=Site(file=file, line=1, col=0), going_in=(), changed=())
    record = HEAD.size + struct.calcsize("<qqII") + len(file.encode())

    assert record <= 4 * pieces.size(run)
    assert PIECE_ROOM >= 4 * pieces.MOST_TEXT


@pytest.mark.parametrize(
    "payload",
    [
        struct.pack("<qqII", 3, 7, 1, 0) + b"t.py\x00n\x002",
        struct.pack("<qqII", 3, 7, 1, 0) + b"t.py\x00n\x00yes\x002",
        b"\x00",
    ],
    ids=["too few fields", "a mark neither 0 nor 1", "no head"],
)
def test_a_run_record_of_the_wrong_shape_is_a_problem(payload: bytes) -> None:
    buffer = bytearray(RECORDS + 8192 + ROOM)
    writer = JournalWriter(buffer, pieces=ROOM)
    writer.line(2)
    writer._record(PIECE, payload)  # noqa: SLF001

    reading = read(buffer)
    assert reading.lines == frozenset({2})
    assert reading.problem == f"could not read the input's facts at byte {RECORDS + HEAD.size + 8}"
