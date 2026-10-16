"""What an input reached beyond its lines crosses the journal: the functions it entered, with
their lines and branches, and each way a branch went."""

import json

from pyct.results.coverage import Reach
from pyct.run.journal import ENTERED, WENT, JournalWriter
from pyct.run.journal_reader import read
from pyct.run.process import Waited, ending


def test_each_function_entered_and_each_way_reads_back_as_written() -> None:
    buffer = bytearray(1 << 16)
    writer = JournalWriter(buffer)

    writer.line(2)
    writer.entered(frozenset({1, 2, 3, 4}), {2: frozenset({3, 4})})
    writer.went(2, 4)
    writer.entered(frozenset({7, 8}), {})
    writer.went(2, 3)

    reading = read(buffer)
    assert reading.lines == {2}
    assert reading.reach == Reach(
        lines=frozenset({1, 2, 3, 4, 7, 8}),
        branches={2: frozenset({3, 4})},
        went=frozenset({(2, 4), (2, 3)}),
    )


def test_an_untouched_journal_reached_nothing() -> None:
    assert read(bytearray(1 << 16)).reach == Reach()


def test_an_input_s_result_carries_what_its_journal_reached() -> None:
    buffer = bytearray(1 << 16)
    writer = JournalWriter(buffer)
    writer.start()
    writer.entered(frozenset({1, 2}), {})
    writer.went(1, 2)
    writer.end(None)

    result = ending(read(buffer), Waited.of(0))

    assert result.reach == Reach(lines=frozenset({1, 2}), went=frozenset({(1, 2)}))


def test_a_reach_record_of_the_wrong_shape_stops_the_reading() -> None:
    for kind, payload in (
        # a branch line with no lines its ways lead to
        (ENTERED, json.dumps([[1, 2], [[2]]]).encode()),
        # lines that are no list, and a line that is a bool
        (ENTERED, json.dumps([1, []]).encode()),
        (ENTERED, json.dumps([[True], []]).encode()),
        # a way with one line
        (WENT, b"\x01" * 8),
    ):
        buffer = bytearray(1 << 16)
        JournalWriter(buffer)._record(kind, payload)

        assert read(buffer).problem is not None, kind
