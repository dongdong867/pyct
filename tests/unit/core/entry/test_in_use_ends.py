"""How a run of a loop in use ends: a run still open when an inner frame dropped its formula
calls it no more, a name the loop changes keeps the loop's value whatever object holds it, and a
run that ends by a ``break``, one with an ``else`` and one inside another loop end through the
formula."""

import contextlib
import types
from collections.abc import Mapping

import pytest

from pyct.core.entry import in_use, pieces
from pyct.core.entry.in_use import LoopInUse, Run
from pyct.core.foundation.branch import Branch, Changed, DropReason, FormulaDrop, Site
from pyct.core.numbers.ints import ConcolicInt
from tests.unit.core.entry.test_in_use import (
    COUNT_Z,
    COUNTS,
    GENEXP,
    LOOP,
    RECURSIVE,
    counted,
    drops,
    forks,
    tracked,
    using,
)
from tests.unit.core.entry.test_pieces import FILE, hooked


def test_a_run_open_in_an_outer_frame_does_not_call_a_formula_an_inner_frame_dropped() -> None:
    calls: list[Mapping[str, object]] = []

    def wrong_at_first(values: Mapping[str, object]) -> Mapping[str, object]:
        calls.append(values)
        return {"t": 99} if len(calls) == 1 else counted(values)

    f = hooked(RECURSIVE)

    with using({LOOP: LoopInUse(("s", "t"), ("t",), wrong_at_first)}) as sink:
        t = f(tracked("zz", "s", sink), 1)

    # the first inner call drops it; the outer run's end leaves the loop's own value
    assert len(calls) == 1
    assert len(drops(sink)) == 1
    assert (type(t), t) == (int, 2)


RECURSIVE_ASSIGNMENT = """\
def f(s, depth):
    t = sum(1 for c in s if c == "z" and (not depth or f(s, 0) >= 0))
    return t
"""


def test_an_assignment_open_in_an_outer_frame_does_not_call_a_dropped_formula() -> None:
    calls: list[Mapping[str, object]] = []

    def wrong_at_first(values: Mapping[str, object]) -> Mapping[str, object]:
        calls.append(values)
        s = values["s"]
        assert isinstance(s, str)
        return {"t": 99} if len(calls) == 1 else {"t": s.count("z")}

    f = hooked(RECURSIVE_ASSIGNMENT)

    # the piece is the generator, at its parenthesis
    with using({(2, 11): LoopInUse(("s",), ("t",), wrong_at_first)}) as sink:
        t = f(tracked("zz", "s", sink), 1)

    # the first inner call drops it; the outer run's end stores the loop's own value
    assert len(calls) == 1
    assert len(drops(sink)) == 1
    assert (type(t), t) == (int, 2)


CHANGED = """\
def f(s, n):
    t = 0
    for c in s:
        if c == "z":
            n = n - n + 5
            t += 1
    if n > 3:
        return t, n
    return t, n
"""


def test_a_changed_name_keeps_the_loop_s_value_when_it_is_the_object_the_start_wrote() -> None:
    f = hooked(CHANGED)

    with using({LOOP: LoopInUse(("n", "s", "t"), ("n", "t"), lambda _: {"t": 9, "n": 5})}) as sink:
        result = f(tracked("az", "s", sink), ConcolicInt.made(5, expression="n", sink=sink))

    assert isinstance(result, tuple)
    _, n = result
    # the loop set n to 5, the object the start wrote; the formula was dropped on t
    assert len(drops(sink)) == 1
    assert type(n) is int
    assert [each.expression for each in sink if type(each) is Branch] == []


BREAK = """\
def f(s):
    t = 0
    for c in s:
        if c == "!":
            break
        if c == "z":
            t += 1
    return t
"""


def test_a_run_that_ends_by_a_break_is_followed_through_the_formula() -> None:
    f = hooked(BREAK)

    with using({LOOP: LoopInUse(("s", "t"), ("t",), counted)}) as sink:
        t = f(tracked("az!b", "s", sink))

    assert type(t) is ConcolicInt
    assert (int.__int__(t), t.expression) == (1, ["+", 0, COUNT_Z])
    assert (forks(sink), drops(sink)) == ([], [])


ELSE = """\
def f(n):
    t = 0
    while n > 0:
        t += 2
        n -= 1
    else:
        t += 1
    return t
"""


def twice(values: Mapping[str, object]) -> Mapping[str, object]:
    n, t = values["n"], values["t"]
    assert isinstance(n, int)
    assert isinstance(t, int)
    return {"n": 0, "t": t + 2 * n}


def test_a_while_s_else_runs_on_the_value_the_formula_hands_on() -> None:
    f = hooked(ELSE)

    with using({LOOP: LoopInUse(("n", "t"), ("n", "t"), twice)}) as sink:
        t = f(ConcolicInt.made(3, expression="n", sink=sink))

    assert type(t) is ConcolicInt
    assert (int.__int__(t), t.expression) == (7, ["+", ["+", 0, ["*", 2, "n"]], 1])
    assert (forks(sink), drops(sink)) == ([], [])


NESTED = """\
def f(s, k):
    total = 0
    for i in range(k):
        t = 0
        for c in s:
            if c == "z":
                t += 1
        total += t
    return total
"""


def test_a_loop_in_use_inside_another_loop_uses_its_formula_on_each_run() -> None:
    calls: list[Mapping[str, object]] = []

    def counting(values: Mapping[str, object]) -> Mapping[str, object]:
        calls.append(values)
        return counted(values)

    f = hooked(NESTED)

    with using({(5, 8): LoopInUse(("s", "t"), ("t",), counting)}) as sink:
        total = f(tracked("zaz", "s", sink), 2)

    assert len(calls) == 2
    assert type(total) is ConcolicInt
    assert int.__int__(total) == 4
    assert (forks(sink), drops(sink)) == ([], [])


class _Stop(BaseException):
    """A raise that is not an ``Exception``, as the deadline's."""


def wrong(_: Mapping[str, object]) -> Mapping[str, object]:
    return {"t": 99}


@pytest.mark.parametrize("raised", [RuntimeError, _Stop], ids=["an Exception", "another raise"])
@pytest.mark.parametrize(
    ("source", "place", "parameters"),
    [(COUNTS, LOOP, ("s", "t")), (GENEXP, (2, 11), ("s",))],
    ids=["a for", "an assignment"],
)
def test_a_drop_reaches_the_sink_when_the_restore_after_it_raises(
    monkeypatch: pytest.MonkeyPatch,
    raised: type[BaseException],
    source: str,
    place: tuple[int, int],
    parameters: tuple[str, ...],
) -> None:
    restore = in_use._rebound

    def raising(frame: types.FrameType, run: Run, made: Mapping[str, object]) -> None:
        if run.drop is not None:
            raise raised
        restore(frame, run, made)

    monkeypatch.setattr(in_use, "_rebound", raising)
    f = hooked(source)

    with using({place: LoopInUse(parameters, ("t",), wrong)}) as sink, contextlib.suppress(_Stop):
        f(tracked("az", "s", sink))

    drop = FormulaDrop(Site(FILE, *place), "t", "1", "99", DropReason.MISMATCH, run=0)
    assert drops(sink) == [drop]


def test_a_drop_reaches_the_sink_when_the_record_of_its_run_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raising(_self: object, _run: Run, _changed: tuple[Changed, ...] | None) -> int | None:
        raise _Stop

    calls: list[Mapping[str, object]] = []

    def wrong_on_the_fourth(values: Mapping[str, object]) -> Mapping[str, object]:
        calls.append(values)
        return wrong(values) if len(calls) == 4 else counted(values)

    monkeypatch.setattr(pieces._Recording, "failed", raising)
    f = hooked(COUNTS)

    with using({LOOP: LoopInUse(("s", "t"), ("t",), wrong_on_the_fourth)}) as sink:
        for _ in range(3):
            f(tracked("az", "s", sink))
        # past the first three runs, the failing run is recorded only by `failed`
        with pytest.raises(_Stop):
            f(tracked("az", "s", sink))

    assert drops(sink) == [FormulaDrop(Site(FILE, *LOOP), "t", "1", "99", DropReason.MISMATCH)]
