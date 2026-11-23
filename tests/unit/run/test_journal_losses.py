"""A recorded run of a loss site crosses the journal in the room of the recorded runs and reads back
as written; an input forked or in a fresh interpreter hands its loss runs to pyct's process when
the run records them, and none when it does not."""

import struct

import pytest

from pyct.core.entry import losses
from pyct.core.foundation.branch import (
    Callee,
    Changed,
    GoingIn,
    LossKind,
    LossRun,
    PieceRun,
    Site,
)
from pyct.run.isolation import Inputs, Isolation
from pyct.run.journal import HEAD, LOSS, RECORDS, JournalWriter
from pyct.run.journal_pieces import loss_payload
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
    writer = JournalWriter(buffer, pieces=ROOM)
    in_c = LossRun(SITE, "bin", LossKind.CALL, (), (Changed("answer", '"0b1"'),), Callee("b", "c"))
    piece = PieceRun(site=SITE, going_in=(), changed=())

    writer.line(2)
    writer.loss(RUN)
    writer.piece(piece)
    writer.loss(CALLED)
    writer.loss(in_c)

    reading = read(buffer)
    assert reading.losses == (RUN, CALLED, in_c)
    assert (reading.pieces, reading.lines) == ((piece,), frozenset({2}))
    assert (reading.problem, reading.bound) == (None, None)


def test_loss_runs_past_the_room_are_dropped_while_the_writer_goes_on() -> None:
    buffer = bytearray(RECORDS + 8192 + ROOM)
    writer = JournalWriter(buffer, pieces=ROOM)

    for _ in range(100):
        writer.loss(CALLED)
    writer.line(5)

    reading = read(buffer)
    assert 0 < len(reading.losses) < 100
    assert reading.lines == frozenset({5})


def test_the_room_for_runs_holds_every_loss_run_an_input_records() -> None:
    # the largest run for what it counts: a file of four-byte characters and one value
    file = "\U0001f600" * 100
    run = LossRun(
        Site(file, 1, 0), "f", LossKind.CALL, (), (Changed("answer", "1"),), CALLED.callee
    )
    record = HEAD.size + len(loss_payload(run))

    assert record <= 4 * losses.size(run)


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
    writer = JournalWriter(buffer, pieces=ROOM)
    writer.line(2)
    writer._record(LOSS, payload)  # noqa: SLF001

    reading = read(buffer)
    assert (reading.losses, reading.lines) == ((), frozenset({2}))
    assert reading.problem == f"could not read the input's facts at byte {RECORDS + HEAD.size + 8}"


@pytest.mark.parametrize("isolation", [Isolation.FORK, Isolation.FRESH, Isolation.IN_PROCESS])
def test_an_input_hands_its_loss_runs_to_pyct_s_process(isolation: Isolation) -> None:
    target = load_target(SHIFTED)

    result = Inputs(target, isolation, losses=True)({"n": 13}, None)

    [run] = result.losses
    assert (run.name, run.kind, run.site.file) == ("__rshift__", LossKind.OPERATION, target.file)
    assert run.going_in == (GoingIn("arg1", "13", tracked=True), GoingIn("arg2", "2", False))
    assert run.changed == (Changed("answer", "3"),)


@pytest.mark.parametrize("isolation", [Isolation.FORK, Isolation.FRESH, Isolation.IN_PROCESS])
def test_an_input_of_a_run_that_records_no_loss_runs_has_none(isolation: Isolation) -> None:
    target = load_target(SHIFTED)

    result = Inputs(target, isolation)({"n": 13}, None)

    assert result.losses == ()
    assert [each.name for each in result.downgrades] == ["__rshift__"]
