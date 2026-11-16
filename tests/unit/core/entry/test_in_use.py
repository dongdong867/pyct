"""A loop in use runs on plain values, and at its end its formula, run on the tracked values that
went in, stands for what the loop did: each changed name holds the loop's own value with the
formula's term, and the names that went in get their tracked values back. A formula that does not
match is dropped for the rest of the input, and the input carries the drop."""

import contextlib
from collections.abc import Callable, Iterator, Mapping
from typing import Any, cast

import pytest

from pyct.core.entry import in_use, pieces
from pyct.core.entry.in_use import LoopInUse
from pyct.core.foundation.branch import (
    Branch,
    Changed,
    DropReason,
    FormulaDrop,
    GoingIn,
    SinkItem,
    Site,
)
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr
from tests.unit.core.entry.test_pieces import FILE, hooked, recorded

COUNTS = """\
def f(s):
    t = 0
    for c in s:
        if c == "z":
            t += 1
    if t > 3:
        return t, "many"
    return t, "few"
"""
# the loop's line and column in each target below but two
LOOP = (3, 4)

type Formula = Callable[[Mapping[str, object]], Mapping[str, object]]


def counted(values: Mapping[str, object]) -> Mapping[str, object]:
    """The formula of COUNTS's loop."""
    s, t = values["s"], values["t"]
    assert isinstance(s, str)
    assert isinstance(t, int)
    return {"t": t + s.count("z")}


@contextlib.contextmanager
def using(
    loops: Mapping[tuple[int, int], LoopInUse], *, alone: bool = True
) -> Iterator[list[SinkItem]]:
    """A live input, with each loop at its line and column in use, whose sink is the list
    yielded, in a call that runs in a process of its own unless ``alone`` is False."""
    in_use.IN_USE.update({(FILE, line, col): loop for (line, col), loop in loops.items()})
    sink: list[SinkItem] = []
    pieces.start(sink, alone=alone)
    try:
        yield sink
    finally:
        pieces.forget()
        in_use.IN_USE.clear()


def tracked(value: str, name: str, sink: list[SinkItem]) -> ConcolicStr:
    return ConcolicStr.made(value, expression=name, sink=sink)


def forks(sink: list[SinkItem]) -> list[tuple[object, int, bool]]:
    """Each fork in the sink: its condition, its line and the side it took."""
    return [(each.expression, each.site.line, each.taken) for each in sink if type(each) is Branch]


def drops(sink: list[SinkItem]) -> list[FormulaDrop]:
    return [each for each in sink if type(each) is FormulaDrop]


COUNT_Z = ["count", "s", "'z'"]


def test_a_for_over_a_tracked_str_records_no_fork_inside_and_hands_on_a_tracked_value() -> None:
    f = hooked(COUNTS)

    with using({LOOP: LoopInUse(("s", "t"), ("t",), counted)}) as sink:
        t, said = cast(tuple[Any, ...], f(tracked("azbz", "s", sink)))

    # each check of the tracked value below goes through its base type, and records nothing
    assert forks(sink) == [([">", ["+", 0, COUNT_Z], 3], 6, False)]
    assert drops(sink) == []
    assert said == "few"
    assert type(t) is ConcolicInt
    assert (int.__int__(t), t.expression) == (2, ["+", 0, COUNT_Z])


def test_a_call_that_does_not_run_alone_follows_the_loop_as_written() -> None:
    f = hooked(COUNTS)
    with using({}) as written:
        f(tracked("az", "s", written))

    with using({LOOP: LoopInUse(("s", "t"), ("t",), counted)}, alone=False) as sink:
        f(tracked("az", "s", sink))

    assert forks(sink) == forks(written)
    assert any(line == 4 for _, line, _ in forks(sink))


WHILE = """\
def f(n):
    t = 0
    while n > 0:
        t += 2
        n -= 1
    if t > 4:
        return t, n
    return t, n
"""


def test_a_while_changing_two_names_hands_on_a_term_and_a_constant_stays_plain() -> None:
    def twice(values: Mapping[str, object]) -> Mapping[str, object]:
        n, t = values["n"], values["t"]
        assert isinstance(n, int)
        assert isinstance(t, int)
        return {"n": 0, "t": t + 2 * n}

    f = hooked(WHILE)

    with using({LOOP: LoopInUse(("n", "t"), ("n", "t"), twice)}) as sink:
        t, n = cast(tuple[Any, ...], f(ConcolicInt.made(3, expression="n", sink=sink)))

    assert forks(sink) == [([">", ["+", 0, ["*", 2, "n"]], 4], 6, True)]
    assert (int.__int__(t), n) == (6, 0)
    assert type(n) is int


GENEXP = """\
def f(s):
    t = sum(1 for c in s if c == "z")
    if t > 1:
        return t
    return t
"""


def test_an_assignment_of_a_generator_hands_on_the_tracked_value_it_stores() -> None:
    def summed(values: Mapping[str, object]) -> Mapping[str, object]:
        s = values["s"]
        assert isinstance(s, str)
        return {"t": s.count("z")}

    f = hooked(GENEXP)

    # the piece is the generator, at its parenthesis
    with using({(2, 11): LoopInUse(("s",), ("t",), summed)}) as sink:
        t = f(tracked("azbz", "s", sink))

    assert type(t) is ConcolicInt
    assert forks(sink) == [([">", COUNT_Z, 1], 3, True)]


def test_an_assignment_past_the_first_three_runs_whose_formula_fails_is_recorded() -> None:
    def wrong_past_three(values: Mapping[str, object]) -> Mapping[str, object]:
        s = values["s"]
        assert isinstance(s, str)
        return {"t": s.count("z") + (str.__len__(s) > 4)}

    f = hooked(GENEXP)

    with using({(2, 11): LoopInUse(("s",), ("t",), wrong_past_three)}) as sink:
        stored = [f(tracked(s, "s", sink)) for s in ["az", "az", "az", "azzzz"]]

    assert [type(t) for t in stored] == [ConcolicInt] * 3 + [int]
    assert [each.going_in[0].value for each in recorded(sink)] == ['"az"'] * 3 + ['"azzzz"']
    drop = FormulaDrop(Site(FILE, 2, 11), "t", "4", "5", DropReason.MISMATCH, run=3)
    assert drops(sink) == [drop]


def test_a_formula_s_own_fork_is_placed_at_the_loop_before_the_later_condition() -> None:
    def cased(values: Mapping[str, object]) -> Mapping[str, object]:
        s, t = values["s"], values["t"]
        assert isinstance(s, str)
        assert isinstance(t, int)
        found = t
        if s.count("z") > 0:
            found = t + s.count("z")
        return {"t": found}

    f = hooked(COUNTS)

    with using({LOOP: LoopInUse(("s", "t"), ("t",), cased)}) as sink:
        f(tracked("azbz", "s", sink))

    assert [each.site for each in sink if type(each) is Branch][0] == Site(FILE, *LOOP)
    assert forks(sink) == [([">", COUNT_Z, 0], 3, True), ([">", ["+", 0, COUNT_Z], 3], 6, False)]


def test_a_formula_that_gives_a_constant_leaves_the_loop_s_value_plain() -> None:
    f = hooked(COUNTS)

    with using({LOOP: LoopInUse(("s", "t"), ("t",), lambda _: {"t": 2})}) as sink:
        t, _ = cast(tuple[Any, ...], f(tracked("azbz", "s", sink)))

    assert type(t) is int
    assert (forks(sink), drops(sink)) == ([], [])


AFTER = """\
def f(s):
    t = 0
    for c in s:
        if c == "z":
            t += 1
    if s == "q":
        return t
    return t
"""


def wrong(values: Mapping[str, object]) -> Mapping[str, object]:
    s, t = values["s"], values["t"]
    assert isinstance(s, str)
    assert isinstance(t, int)
    return {"t": t + s.count("a")}


def raises(values: Mapping[str, object]) -> Mapping[str, object]:
    return {"t": 1 // 0}


FAILING: dict[str, tuple[Formula, str, DropReason]] = {
    "a mismatch": (wrong, "1", DropReason.MISMATCH),
    "a raise": (raises, "ZeroDivisionError", DropReason.RAISED),
    "another kind": (lambda _: {"t": "2"}, '"2"', DropReason.MISMATCH),
    "a missing name": (lambda _: {}, "", DropReason.MISSING),
}


@pytest.mark.parametrize(("formula", "got", "reason"), FAILING.values(), ids=FAILING.keys())
def test_a_formula_that_fails_restores_the_names_and_is_dropped_for_the_input(
    formula: Formula, got: str, reason: DropReason
) -> None:
    calls: list[object] = []

    def counting(values: Mapping[str, object]) -> Mapping[str, object]:
        calls.append(values)
        return formula(values)

    f = hooked(AFTER)

    with using({LOOP: LoopInUse(("s", "t"), ("t",), counting)}) as sink:
        assert f(tracked("azbz", "s", sink)) == 2
        first = list(sink)
        assert f(tracked("az", "s", sink)) == 1

    # the loop's value stays plain, the str going in is tracked again, and the second run follows
    # the loop as written
    assert drops(first) == [FormulaDrop(Site(FILE, *LOOP), "t", "2", got, reason, run=0)]
    assert [line for _, line, _ in forks(first)] == [6]
    assert len(calls) == 1
    assert 4 in [line for _, line, _ in forks(sink[len(first) :])]


class Stopped(BaseException):
    """A raise that is not an `Exception`, as the deadline's."""


def test_a_raise_that_is_not_an_exception_passes_through_the_hook() -> None:
    def stops(values: Mapping[str, object]) -> Mapping[str, object]:
        raise Stopped

    f = hooked(COUNTS)

    with using({LOOP: LoopInUse(("s", "t"), ("t",), stops)}) as sink, pytest.raises(Stopped):
        f(tracked("az", "s", sink))


KEPT = """\
def f(s, u):
    t = 0
    for c in s:
        u = c
        if c == "z":
            t += 1
    return t, u, s
"""


def test_a_name_the_loop_binds_again_keeps_the_loop_s_value_and_the_others_come_back() -> None:
    f = hooked(KEPT)

    with using({LOOP: LoopInUse(("s", "t", "u"), ("t",), counted)}) as sink:
        t, u, s = cast(tuple[Any, ...], f(tracked("az", "s", sink), tracked("q", "u", sink)))

    assert (t, u, s) == (1, "z", "az")
    assert type(u) is str
    assert type(s) is ConcolicStr


UNBOUND = """\
def f(s):
    for c in s:
        last = c
    return last
"""


def test_a_name_the_loop_leaves_unbound_stays_unbound() -> None:
    f = hooked(UNBOUND)

    with (
        using({(2, 4): LoopInUse(("s",), ("last",), lambda _: {"last": "z"})}) as sink,
        pytest.raises(UnboundLocalError),
    ):
        f(tracked("", "s", sink))

    assert drops(sink) == []


RECURSIVE = """\
def f(s, depth):
    t = 0
    for c in s:
        if depth:
            f(s, 0)
        if c == "z":
            t += 1
    return t
"""


def test_two_frames_in_one_loop_each_run_their_own_formula() -> None:
    calls: list[bool] = []

    def counting(values: Mapping[str, object]) -> Mapping[str, object]:
        calls.append(type(values["s"]) is ConcolicStr)
        return counted(values)

    f = hooked(RECURSIVE)

    with using({LOOP: LoopInUse(("s", "t"), ("t",), counting)}) as sink:
        t = f(tracked("zz", "s", sink), 1)

    # the inner calls run on the plain str the outer run is given, then the outer run ends
    assert calls == [False, False, True]
    assert type(t) is ConcolicInt
    assert t.expression == ["+", 0, COUNT_Z]
    assert drops(sink) == []


def test_every_run_of_a_loop_in_use_uses_its_formula_and_the_first_three_are_recorded() -> None:
    calls: list[object] = []

    def counting(values: Mapping[str, object]) -> Mapping[str, object]:
        calls.append(values)
        return counted(values)

    f = hooked(COUNTS)
    with pieces_live() as written:
        for _ in range(5):
            f(tracked("az", "s", written))

    with using({LOOP: LoopInUse(("s", "t"), ("t",), counting)}) as sink:
        for _ in range(5):
            f(tracked("az", "s", sink))

    assert len(calls) == 5
    assert forks(sink) == [([">", ["+", 0, COUNT_Z], 3], 6, False)] * 5
    assert recorded(sink) == recorded(written)
    assert len(recorded(sink)) == 3
    assert recorded(sink)[0].going_in == (GoingIn("s", '"az"', True), GoingIn("t", "0", False))


@contextlib.contextmanager
def pieces_live() -> Iterator[list[SinkItem]]:
    """A live input with no loop in use."""
    with using({}) as sink:
        yield sink


def test_a_run_past_the_first_three_whose_formula_fails_is_recorded() -> None:
    def long_wrong(values: Mapping[str, object]) -> Mapping[str, object]:
        s = values["s"]
        assert isinstance(s, str)
        # str's own length, which a tracked str answers with no fork
        return {"t": s.count("z") + (str.__len__(s) > 4)}

    f = hooked(COUNTS)

    with using({LOOP: LoopInUse(("s", "t"), ("t",), long_wrong)}) as sink:
        for s in ["az", "az", "az", "az", "azzzz"]:
            f(tracked(s, "s", sink))

    assert [each.going_in[0].value for each in recorded(sink)] == ['"az"'] * 3 + ['"azzzz"']
    assert recorded(sink)[-1].changed == (Changed("t", "4"),)
    drop = FormulaDrop(Site(FILE, *LOOP), "t", "4", "5", DropReason.MISMATCH, run=3)
    assert drops(sink) == [drop]
