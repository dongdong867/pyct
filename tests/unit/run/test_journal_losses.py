"""A recorded run of a loss site crosses the journal in a room of its own: it reads back as written,
and it never takes the room of the input's own facts nor stops the writer. A loss site's dropped
formula crosses it among the input's own facts. An input forked or in a fresh interpreter hands its
loss runs to pyct's process when the run records them, and none when it does not."""

import struct

import pytest

from pyct.core.entry import losses
from pyct.core.entry.recorded import MOST_TEXT
from pyct.core.foundation.branch import (
    Callee,
    Changed,
    DropReason,
    FormulaDrop,
    GoingIn,
    LossKind,
    LossRun,
    Site,
)
from pyct.run.isolation import Inputs, Isolation
from pyct.run.journal import DROP, HEAD, LOSS, RECORDS, RUN_ROOM, JournalWriter
from pyct.run.journal_losses import loss_payload
from pyct.run.journal_reader import read
from pyct.run.target import load_target

SITE = Site(file="té.py", line=3, col=7)
RUN = LossRun(
    SITE,
    "__rshift__",
    LossKind.OPERATION,
    (GoingIn("arg1", "13", tracked=True), GoingIn("arg2", '"é\\""', tracked=False)),
    (Changed("answer", "3"),),
)
CALLED = LossRun(
    Site(file="u.py", line=9, col=0),
    "textwrap.dedent",
    LossKind.CALL,
    (GoingIn("arg1", '"  ab"', tracked=True),),
    (Changed("answer", '"ab"'),),
    Callee("textwrap", "dedent", "/lib/textwrap.py", 414),
)
ROOM = 4096
SHIFTED = "targets.summaries.calls::shifted"


def test_a_loss_run_reads_back_as_it_was_written_among_the_other_facts() -> None:
    buffer = bytearray(RECORDS + 8192 + ROOM)
    writer = JournalWriter(buffer, runs=ROOM)
    in_c = LossRun(SITE, "bin", LossKind.CALL, (), (Changed("answer", '"0b1"'),), Callee("b", "c"))

    writer.line(2)
    writer.loss(RUN)
    writer.line(3)
    writer.loss(CALLED)
    writer.loss(in_c)

    reading = read(buffer)
    assert reading.losses == (RUN, CALLED, in_c)
    assert reading.lines == frozenset({2, 3})
    assert (reading.problem, reading.bound) == (None, None)


def test_a_writer_with_no_room_for_runs_drops_each_and_goes_on() -> None:
    buffer = bytearray(RECORDS + 8192)
    writer = JournalWriter(buffer)

    writer.loss(RUN)
    writer.line(2)

    reading = read(buffer)
    assert (reading.losses, reading.lines, reading.problem) == ((), frozenset({2}), None)


def test_loss_runs_past_the_room_are_dropped_while_the_writer_goes_on() -> None:
    buffer = bytearray(RECORDS + 8192 + ROOM)
    writer = JournalWriter(buffer, runs=ROOM)

    for _ in range(100):
        writer.loss(CALLED)
    writer.line(5)

    reading = read(buffer)
    assert 0 < len(reading.losses) < 100
    assert reading.lines == frozenset({5})
    assert (reading.problem, reading.bound) == (None, None)


def lines_until_full(writer: JournalWriter, *, with_runs: bool) -> None:
    for line in range(10_000):
        writer.line(line)
        if with_runs and line % 7 == 0:
            writer.loss(RUN)


def test_runs_never_take_the_room_of_the_input_s_own_facts() -> None:
    plain, with_runs = bytearray(RECORDS + 8192 + ROOM), bytearray(RECORDS + 8192 + ROOM)

    lines_until_full(JournalWriter(plain, runs=ROOM), with_runs=False)
    lines_until_full(JournalWriter(with_runs, runs=ROOM), with_runs=True)

    alone, beside = read(plain), read(with_runs)
    assert beside.losses
    assert beside.lines == alone.lines
    # the note names the bytes the input's own facts have, as it does with no room for runs
    assert beside.bound == alone.bound == f"the journal is full at {RECORDS + 8192} bytes"


def test_the_room_for_runs_holds_every_loss_run_an_input_records() -> None:
    # the largest run for what it counts: a file of four-byte characters and one value
    file = "\U0001f600" * 100
    run = LossRun(
        Site(file, 1, 0), "f", LossKind.CALL, (), (Changed("answer", "1"),), CALLED.callee
    )
    record = HEAD.size + len(loss_payload(run))

    assert record <= 4 * losses.size(run)
    assert RUN_ROOM >= 4 * MOST_TEXT


@pytest.mark.parametrize(
    "payload",
    [
        struct.pack("<qqII", 3, 7, 1, 0) + b"t.py\x00f\x00call\x00n\x001",
        struct.pack("<qqII", 3, 7, 0, 0) + b"t.py\x00f\x00lost\x001",
        struct.pack("<qqII", 3, 7, 0, 2) + b"t.py\x00f\x00call\x001",
        struct.pack("<qqII", 3, 7, 0, 1) + b"t.py\x00f\x00call\x001\x00m\x00q\x00\x00x",
    ],
    ids=[
        "too few fields",
        "no kind of a loss",
        "a callee mark neither 0 nor 1",
        "a line no number",
    ],
)
def test_a_loss_record_of_the_wrong_shape_is_a_problem(payload: bytes) -> None:
    buffer = bytearray(RECORDS + 8192 + ROOM)
    writer = JournalWriter(buffer, runs=ROOM)
    writer.line(2)
    writer._record(LOSS, payload)  # noqa: SLF001

    reading = read(buffer)
    assert (reading.losses, reading.lines) == ((), frozenset({2}))
    assert reading.problem == f"could not read the input's facts at byte {RECORDS + HEAD.size + 8}"


DROPPED = FormulaDrop(SITE, "answer", "[1.5]", '"1.5"', DropReason.MISMATCH, run=2)


def test_a_dropped_formula_reads_back_as_it_was_written_among_the_other_facts() -> None:
    buffer = bytearray(RECORDS + 8192 + ROOM)
    writer = JournalWriter(buffer, runs=ROOM)
    raised = FormulaDrop(Site("u.py", 9, 0), "é", "", "ZeroDivisionError", DropReason.RAISED)

    writer.line(2)
    writer.drop(DROPPED)
    writer.loss(RUN)
    writer.drop(raised)

    reading = read(buffer)
    assert reading.drops == (DROPPED, raised)
    assert (reading.losses, reading.lines) == ((RUN,), frozenset({2}))
    assert (reading.problem, reading.bound) == (None, None)


@pytest.mark.parametrize(
    "payload",
    [
        b'["t.py", 3, 7, "t", "2", "3", "mismatch"]',
        b'["t.py", 3, 7, "t", "2", "3", "lost", 0]',
        b'["t.py", 3, 7, "t", "2", "3", "mismatch", "0"]',
        b"[1]",
    ],
    ids=["too few fields", "no reason of a drop", "a run that is no number", "no fields"],
)
def test_a_drop_record_of_the_wrong_shape_is_a_problem(payload: bytes) -> None:
    buffer = bytearray(RECORDS + 8192)
    writer = JournalWriter(buffer)
    writer.line(2)
    writer._record(DROP, payload)  # noqa: SLF001

    reading = read(buffer)
    assert (reading.drops, reading.lines) == ((), frozenset({2}))
    assert reading.problem == f"could not read the input's facts at byte {RECORDS + HEAD.size + 8}"


@pytest.mark.parametrize("isolation", [Isolation.FORK, Isolation.FRESH, Isolation.IN_PROCESS])
def test_an_input_hands_its_loss_runs_to_pyct_s_process(isolation: Isolation) -> None:
    target = load_target(SHIFTED)

    result = Inputs(target, isolation, losses=True)({"n": 13}, None)

    [run] = result.losses
    assert (run.name, run.kind, run.site.file) == ("__pow__", LossKind.OPERATION, target.file)
    assert run.going_in == (
        GoingIn("arg1", "13", tracked=True),
        GoingIn("arg2", "1", False),
        GoingIn("arg3", "4", False),
    )
    assert run.changed == (Changed("answer", "1"),)


@pytest.mark.parametrize("isolation", [Isolation.FORK, Isolation.FRESH, Isolation.IN_PROCESS])
def test_an_input_of_a_run_that_records_no_loss_runs_has_none(isolation: Isolation) -> None:
    target = load_target(SHIFTED)

    result = Inputs(target, isolation)({"n": 13}, None)

    assert result.losses == ()
    assert [each.name for each in result.downgrades] == ["__pow__"]
