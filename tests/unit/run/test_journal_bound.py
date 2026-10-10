"""A journal that fills is the bound on what pyct keeps for one input, so the input's own: its
line ends `too_long` with the facts before it, while a fact pyct cannot encode stays pyct's.
"""

from pyct.core.branch import Branch, Fact, Site
from pyct.results.failure import Failure, FailureKind
from pyct.run.journal import END_ROOM, RECORDS, JournalWriter
from pyct.run.journal_reader import read

SITE = Site(file="t.py", line=3, col=7)


def test_a_full_journal_is_the_input_s_bound_not_a_problem() -> None:
    size = RECORDS + 4096
    buffer = bytearray(size)
    writer = JournalWriter(buffer)

    for line in range(10_000):
        writer.line(line)

    reading = read(buffer)
    assert reading.problem is None
    assert reading.bound == f"the journal is full at {size} bytes"


def test_an_unencodable_fact_stays_a_problem_and_sets_no_bound() -> None:
    buffer = bytearray(RECORDS + 4096)
    writer = JournalWriter(buffer)

    writer.fork(Branch(expression=["==", "x", object()], taken=True, site=SITE))  # type: ignore[list-item]

    reading = read(buffer)
    assert reading.bound is None
    assert reading.problem == "could not keep a fork the input took: a leaf of type object"


def test_a_bound_the_call_passed_is_noted_while_the_writer_goes_on() -> None:
    buffer = bytearray(RECORDS + 4096)
    writer = JournalWriter(buffer)

    writer.line(2)
    writer.bound("the input took more than 2 forks, the most pyct keeps for one input")
    writer.line(5)

    reading = read(buffer)
    assert reading.bound == "the input took more than 2 forks, the most pyct keeps for one input"
    assert reading.problem is None
    assert reading.lines == frozenset({2, 5})


def test_a_full_journal_still_takes_the_call_s_ending() -> None:
    buffer = bytearray(RECORDS + 4 * END_ROOM)
    writer = JournalWriter(buffer)
    for line in range(1_000_000):
        writer.line(line)
    bug = Failure(FailureKind.PYCT_BUG, "RuntimeError: boom", "Traceback ...\nRuntimeError: boom\n")

    writer.end(bug)

    reading = read(buffer)
    assert reading.bound is not None
    assert reading.ended
    assert reading.end == bug


def test_an_ending_too_long_for_the_room_left_is_kept_without_its_traceback() -> None:
    buffer = bytearray(RECORDS + 4 * END_ROOM)
    writer = JournalWriter(buffer)
    for line in range(1_000_000):
        writer.line(line)

    writer.end(Failure(FailureKind.PYCT_BUG, "RuntimeError: boom", "x" * (2 * END_ROOM)))

    assert read(buffer).end == Failure(FailureKind.PYCT_BUG, "RuntimeError: boom")


def test_a_pyct_bug_whose_detail_overflows_the_room_still_lands_cut() -> None:
    buffer = bytearray(RECORDS + 4 * END_ROOM)
    writer = JournalWriter(buffer)
    for line in range(1_000_000):
        writer.line(line)
    detail = "RuntimeError: " + "x" * 70_000

    writer.end(Failure(FailureKind.PYCT_BUG, detail, "Traceback ..."))

    end = read(buffer).end
    assert end is not None
    assert end.kind is FailureKind.PYCT_BUG
    assert detail.startswith(end.detail)
    assert end.detail.startswith("RuntimeError: ")


def test_a_bound_then_a_full_journal_keeps_the_bound_s_note_and_takes_the_ending() -> None:
    buffer = bytearray(RECORDS + 4 * END_ROOM)
    writer = JournalWriter(buffer)
    note = "the input took more than 2 forks, the most pyct keeps for one input"

    writer.bound(note)
    for line in range(1_000_000):
        writer.line(line)
    writer.end(None)

    reading = read(buffer)
    assert reading.bound == note
    assert reading.problem is None
    assert reading.ended


def test_an_unencodable_fact_after_the_bound_is_still_a_problem() -> None:
    buffer = bytearray(RECORDS + 4096)
    writer = JournalWriter(buffer)

    writer.bound("the input took more than 2 forks, the most pyct keeps for one input")
    writer.fact(Fact(expression=["==", "x", object()], taken=True, site=SITE))  # type: ignore[list-item]

    assert read(buffer).problem == (
        "could not keep a fact the input's path holds: a leaf of type object"
    )
