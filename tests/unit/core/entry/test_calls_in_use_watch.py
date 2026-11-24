"""A loss site in use at a watched call and at a `math` call pyct does not follow: the formula
runs on the arguments as the watch was given them, each list as a copy made then, or on the
`math` call's arguments, and on a match the target gets the real answer tracked."""

import contextlib
import math
import sys
import textwrap
from collections.abc import Callable, Iterator, Mapping

import pytest

from pyct.core.entry import losses, pieces, substitutes, watch
from pyct.core.entry.calls_in_use import CALLS_IN_USE, CallInUse
from pyct.core.entry.watch import answer, called, given
from pyct.core.foundation import escapes
from pyct.core.foundation.branch import Downgrade, FormulaDrop, SinkItem
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr

type Formula = Callable[[Mapping[str, object]], Mapping[str, object]]


@pytest.fixture(autouse=True)
def no_call_open() -> None:
    watch.forget()


@contextlib.contextmanager
def using(line: int, col: int, call: CallInUse, *, alone: bool = True) -> Iterator[list[SinkItem]]:
    """A live input whose call runs alone unless ``alone`` is False, ``call`` in use at the line
    and column of this file, whose sink is the list yielded."""
    CALLS_IN_USE[(__file__, line, col)] = call
    sink: list[SinkItem] = []
    pieces.start(sink, alone=alone)
    losses.start(sink, alone=alone)
    try:
        yield sink
    finally:
        losses.forget()
        pieces.forget()
        escapes.forget()
        CALLS_IN_USE.clear()


def here() -> int:
    """The line after the one that called this."""
    return sys._getframe(1).f_lineno + 1


def stripped(values: Mapping[str, object]) -> Mapping[str, object]:
    s = values["s"]
    assert isinstance(s, str)
    return {"answer": s.strip()}


def downgrades(sink: list[SinkItem]) -> list[Downgrade]:
    return [item for item in sink if type(item) is Downgrade]


def test_a_watched_call_s_formula_runs_on_its_arguments_as_given() -> None:
    line = here() + 2
    with using(line, 12, CallInUse("textwrap.dedent", ("s",), stripped)) as sink:
        s = ConcolicStr.made("  ab", "s", sink)
        t = answer(called(textwrap.dedent)(given(s)), "textwrap.dedent")

    assert type(t) is ConcolicStr
    assert (str(t), t.expression) == ("ab", ["strip", "s"])
    assert downgrades(sink) == []


def grown(items: list[object]) -> int:
    """A Python function outside the target's package, which adds to its list."""
    items.append(0)
    return len(items)


def test_a_watched_call_s_formula_reads_each_list_as_it_was_given() -> None:
    seen: list[int] = []

    def counted(values: Mapping[str, object]) -> Mapping[str, object]:
        items = values["items"]
        assert isinstance(items, list)
        seen.append(len(items))
        return {"answer": len(items) + 1}

    line = here() + 2
    with using(line, 12, CallInUse("grown", ("items",), counted)) as sink:
        items: list[object] = [ConcolicInt.made(3, expression="x", sink=sink)]
        n = answer(called(grown)(given(items)), "grown")

    assert (n, items[1:], seen) == (2, [0], [1])
    assert [item for item in sink if type(item) is FormulaDrop] == []


def gave_n(values: Mapping[str, object]) -> Mapping[str, object]:
    return {"answer": values["n"]}


def test_a_math_call_s_formula_runs_on_its_arguments() -> None:
    gcd = substitutes.call(math.gcd)
    line = here() + 2
    with using(line, 12, CallInUse("gcd", ("n", None), gave_n)) as sink:
        n = ConcolicInt.made(12, expression="n", sink=sink)
        k = gcd(n, 0)

    assert type(k) is ConcolicInt
    assert (int.__int__(k), k.expression) == (12, "n")
    assert downgrades(sink) == []


def test_a_watched_call_in_a_call_that_does_not_run_alone_keeps_its_downgrade() -> None:
    line = here() + 2
    with using(line, 12, CallInUse("d", ("s",), stripped), alone=False) as sink:
        s = ConcolicStr.made("  ab", "s", sink)
        t = answer(called(textwrap.dedent)(given(s)), "d")

    assert type(t) is str
    assert [each.name for each in downgrades(sink)] == ["d"]
