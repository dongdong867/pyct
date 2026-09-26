"""The journal over a plain bytearray: no mapping and no process, only the bytes."""

import enum
import sys

from pyct.core.branch import Branch, Expression, Site
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import DowngradeCount
from pyct.run.journal import RECORDS, JournalWriter, read

SITE = Site(file="t.py", line=3, col=7)
FORK = Branch(expression=["<", "x", ["+", "y", 1]], taken=True, site=SITE)
# a line record is an 8-byte head and an 8-byte number
LINE_RECORD = 16


class Size(enum.IntEnum):
    SMALL = 10


def journal(size: int = 1 << 16) -> bytearray:
    return bytearray(size)


def test_an_untouched_journal_holds_nothing_and_no_ending() -> None:
    reading = read(journal())

    assert reading.lines == frozenset()
    assert reading.branches == ()
    assert reading.downgrades == ()
    assert not reading.ended
    assert reading.problem is None


def test_each_fact_reads_back_as_it_was_written() -> None:
    buffer = journal()
    writer = JournalWriter(buffer)

    writer.line(2)
    writer.fork(FORK)
    writer.downgrade("__rshift__", 1)
    writer.line(3)

    reading = read(buffer)
    assert reading.lines == frozenset({2, 3})
    assert reading.branches == (FORK,)
    assert reading.downgrades == (DowngradeCount(name="__rshift__", count=1),)
    assert not reading.ended


def test_a_repeated_downgrade_grows_its_one_entry() -> None:
    buffer = journal()
    writer = JournalWriter(buffer)

    writer.downgrade("__abs__", 1)
    writer.downgrade("__abs__", 2)
    writer.downgrade("__abs__", 3)
    writer.downgrade("__neg__", 1)

    assert read(buffer).downgrades == (
        DowngradeCount(name="__abs__", count=3),
        DowngradeCount(name="__neg__", count=1),
    )


def test_a_call_that_returned_ends_with_no_failure() -> None:
    buffer = journal()

    JournalWriter(buffer).end(None)

    reading = read(buffer)
    assert reading.ended
    assert reading.end is None


def test_a_call_that_failed_ends_with_its_failure_and_traceback() -> None:
    buffer = journal()
    failure = Failure(kind=FailureKind.PYCT_BUG, detail="RuntimeError: x", traceback="tb\n")

    JournalWriter(buffer).end(failure)

    reading = read(buffer)
    assert reading.ended
    assert reading.end == failure


def test_an_int_subclass_in_a_fork_arrives_as_a_plain_int() -> None:
    buffer = journal()

    JournalWriter(buffer).fork(Branch(expression=["<", "x", Size.SMALL], taken=False, site=SITE))

    expression = read(buffer).branches[0].expression
    assert expression == ["<", "x", 10]
    assert isinstance(expression, list)
    assert type(expression[2]) is int


def test_bytes_past_the_committed_mark_are_not_read() -> None:
    buffer = journal()
    JournalWriter(buffer).line(2)
    # a second record's head, written by a process that died before it committed the record
    buffer[RECORDS + LINE_RECORD : RECORDS + LINE_RECORD + 5] = b"\x08\x00\x00\x00\x01"

    reading = read(buffer)

    assert reading.lines == frozenset({2})
    assert reading.problem is None


def test_a_full_journal_keeps_what_came_before_and_says_it_is_full() -> None:
    buffer = journal(RECORDS + LINE_RECORD)
    writer = JournalWriter(buffer)

    writer.line(2)
    writer.line(3)
    writer.end(None)

    reading = read(buffer)
    assert reading.lines == frozenset({2})
    assert not reading.ended
    assert reading.problem is not None
    assert "full" in reading.problem


def test_a_fork_that_cannot_be_encoded_stops_the_journal() -> None:
    buffer = journal()
    writer = JournalWriter(buffer)
    writer.line(2)

    writer.fork(Branch(expression=["<", "x", object()], taken=True, site=SITE))  # type: ignore[list-item]
    writer.line(3)
    writer.end(None)

    reading = read(buffer)
    assert reading.lines == frozenset({2})
    assert not reading.ended
    assert reading.problem is not None
    assert reading.problem == "could not keep a fork the input took: a leaf of type object"


def test_a_detached_writer_writes_nothing() -> None:
    buffer = journal()
    writer = JournalWriter(buffer)
    writer.downgrade("__abs__", 1)

    writer.detach()
    writer.line(2)
    writer.downgrade("__abs__", 2)
    writer.end(None)

    reading = read(buffer)
    assert reading.lines == frozenset()
    assert reading.downgrades == (DowngradeCount(name="__abs__", count=1),)
    assert not reading.ended


def test_an_unknown_record_stops_the_reading_where_it_sits() -> None:
    buffer = journal()
    writer = JournalWriter(buffer)
    writer.line(2)
    writer.line(3)
    buffer[RECORDS + LINE_RECORD + 4] = 99

    reading = read(buffer)

    assert reading.lines == frozenset({2})
    assert reading.problem == f"could not read the input's facts at byte {RECORDS + LINE_RECORD}"


def test_a_fork_of_the_wrong_shape_is_unreadable() -> None:
    buffer = journal()
    writer = JournalWriter(buffer)
    writer.fork(FORK)
    # the fork's taken side, true, becomes the number 1
    at = buffer.index(b"true")
    buffer[at : at + 4] = b"1   "

    reading = read(buffer)

    assert reading.branches == ()
    assert reading.problem is not None
    assert reading.problem.startswith("could not read the input's facts at byte ")


def doubled(times: int) -> list[Expression]:
    """``x + x`` taken ``times`` times: each pass uses the last one twice, as one shared list."""
    expression: Expression = "x"
    for _ in range(times):
        expression = ["+", expression, expression]
    assert isinstance(expression, list)
    return expression


def test_a_shared_part_is_written_once_and_read_back_shared() -> None:
    buffer = journal()
    writer = JournalWriter(buffer)

    writer.fork(Branch(expression=["<", doubled(60), 0], taken=True, site=SITE))

    # written out as a tree it would hold 2**60 leaves; as written, one node per pass
    assert int.from_bytes(buffer[0:8], "little") < RECORDS + 64 * 64
    expression = read(buffer).branches[0].expression
    assert isinstance(expression, list)
    part = expression[1]
    for _ in range(60):
        assert isinstance(part, list)
        assert part[0] == "+"
        assert part[1] is part[2]
        part = part[1]
    assert part == "x"


def test_a_part_two_forks_share_is_one_part_in_both() -> None:
    buffer = journal()
    writer = JournalWriter(buffer)
    shared = doubled(3)

    writer.fork(Branch(expression=["<", shared, 0], taken=True, site=SITE))
    writer.fork(Branch(expression=[">", shared, 9], taken=False, site=SITE))

    first, second = read(buffer).branches
    assert isinstance(first.expression, list)
    assert isinstance(second.expression, list)
    assert first.expression[1] is second.expression[1]
    assert first.expression[1] == shared


def test_a_leaf_of_no_kind_an_expression_holds_stops_the_journal() -> None:
    buffer = journal()
    writer = JournalWriter(buffer)

    writer.fork(Branch(expression=["<", "x", 1.5], taken=True, site=SITE))  # type: ignore[list-item]

    reading = read(buffer)
    assert reading.branches == ()
    assert reading.problem == "could not keep a fork the input took: a leaf of type float"


def test_an_expression_that_holds_itself_stops_the_journal() -> None:
    buffer = journal()
    writer = JournalWriter(buffer)
    looped: list[Expression] = ["-", "x"]
    looped.append(looped)

    writer.fork(Branch(expression=looped, taken=True, site=SITE))

    reading = read(buffer)
    assert reading.branches == ()
    assert reading.problem == "could not keep a fork the input took: it holds itself"


def test_a_part_named_before_it_was_written_is_unreadable() -> None:
    buffer = journal()
    JournalWriter(buffer).fork(FORK)
    # the fork's expression names part 0; point it at a part the journal never wrote
    at = buffer.index(b"[[1]")
    buffer[at : at + 4] = b"[[7]"

    reading = read(buffer)

    assert reading.branches == ()
    assert reading.problem is not None
    assert reading.problem.startswith("could not read the input's facts at byte ")


def test_a_committed_mark_past_the_journal_is_unreadable() -> None:
    buffer = journal(RECORDS + LINE_RECORD)
    buffer[0:8] = (len(buffer) + 8).to_bytes(8, "little")

    reading = read(buffer)

    assert reading.problem == "could not read the input's facts at byte 0"


def committed_to(buffer: bytearray, mark: int) -> None:
    """Move the committed mark, as a writer that died mid-record could have left it."""
    buffer[0:8] = mark.to_bytes(8, "little")


def test_a_fork_whose_expression_is_a_leaf_reads_back() -> None:
    buffer = journal()

    JournalWriter(buffer).fork(Branch(expression="flag", taken=True, site=SITE))

    assert read(buffer).branches == (Branch(expression="flag", taken=True, site=SITE),)


def test_a_downgrade_that_does_not_fit_is_not_grown_later() -> None:
    buffer = journal(RECORDS)
    writer = JournalWriter(buffer)

    writer.downgrade("__abs__", 1)
    writer.downgrade("__abs__", 2)

    reading = read(buffer)
    assert reading.downgrades == ()
    assert reading.problem is not None
    assert "full" in reading.problem


def test_a_part_that_does_not_fit_leaves_its_fork_out() -> None:
    buffer = journal(RECORDS + 8)

    JournalWriter(buffer).fork(FORK)

    reading = read(buffer)
    assert reading.branches == ()
    assert reading.problem is not None
    assert "full" in reading.problem


def test_the_first_reason_the_writer_stopped_is_the_one_kept() -> None:
    buffer = journal(RECORDS)
    writer = JournalWriter(buffer)

    writer.line(2)
    # a fork whose expression is a leaf of no kind it holds, which stops the writer again
    writer.fork(Branch(expression=1.5, taken=True, site=SITE))  # type: ignore[arg-type]

    reading = read(buffer)
    assert reading.problem is not None
    assert "full" in reading.problem


def test_a_state_of_no_known_kind_is_unreadable() -> None:
    buffer = journal()
    buffer[8] = 7

    assert read(buffer).problem == "could not read the input's facts at byte 8"


def test_a_committed_mark_inside_a_record_head_is_unreadable() -> None:
    buffer = journal()
    JournalWriter(buffer).line(2)
    committed_to(buffer, RECORDS + 4)

    assert read(buffer).problem == f"could not read the input's facts at byte {RECORDS}"


def test_a_record_longer_than_what_was_committed_is_unreadable() -> None:
    buffer = journal()
    JournalWriter(buffer).line(2)
    buffer[RECORDS : RECORDS + 4] = (999).to_bytes(4, "little")

    assert read(buffer).problem == f"could not read the input's facts at byte {RECORDS}"


def test_a_part_that_is_not_a_list_is_unreadable() -> None:
    buffer = journal()
    JournalWriter(buffer).fork(FORK)
    # the first part, numbered 0, becomes a number of the same length
    at = buffer.index(b'[0, "+", "y", 1]')
    buffer[at : at + 16] = b"7               "

    reading = read(buffer)

    assert reading.branches == ()
    assert reading.problem == f"could not read the input's facts at byte {RECORDS}"


def test_an_ending_of_the_wrong_shape_is_unreadable() -> None:
    buffer = journal()
    JournalWriter(buffer).end(None)
    at = buffer.index(b"null")
    buffer[at : at + 4] = b"true"

    reading = read(buffer)

    assert not reading.ended
    assert reading.problem == f"could not read the input's facts at byte {RECORDS}"


def test_an_int_too_long_to_write_out_stops_the_journal_without_raising() -> None:
    buffer = journal()
    writer = JournalWriter(buffer)
    writer.line(2)

    writer.fork(Branch(expression=["<", "x", 10**5000], taken=True, site=SITE))

    reading = read(buffer)
    assert reading.lines == frozenset({2})
    assert reading.branches == ()
    assert reading.problem is not None
    assert reading.problem.startswith("could not keep a fork the input took: ")


def test_an_int_past_a_limit_the_target_lowered_stops_the_journal_without_raising() -> None:
    buffer = journal()
    writer = JournalWriter(buffer)
    limit = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(640)
    try:
        writer.fork(Branch(expression=["<", "x", 10**700], taken=True, site=SITE))
    finally:
        sys.set_int_max_str_digits(limit)

    reading = read(buffer)
    assert reading.branches == ()
    assert reading.problem is not None
    assert reading.problem.startswith("could not keep a fork the input took: ")


def test_a_call_that_began_says_so() -> None:
    buffer = journal()

    JournalWriter(buffer).start()

    assert read(buffer).started
    assert not read(journal()).started
