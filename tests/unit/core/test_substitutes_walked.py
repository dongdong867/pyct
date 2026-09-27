"""`in` on a tuple or a list with a tracked int or bool searched for: the elements in order,
identity first, an int subclass that keeps int's `==` compared with the tracked value on its
left, and every other element compared as Python compares it."""

from collections import namedtuple
from enum import IntEnum

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import SinkItem
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.substitutes import Searched, in_, not_in
from tests.unit.core.test_substitutes import expressions


class Status(IntEnum):
    OK = 0
    BAD = 1


class Loud(int):
    """An int with its own `==`, which says what it was asked and answers False."""

    asked: list[object]

    def __eq__(self, other: object) -> bool:
        Loud.asked.append(other)
        return False

    __hash__ = int.__hash__


class Refusing(int):
    """An int whose `==` raises."""

    def __eq__(self, other: object) -> bool:
        raise ValueError("no compare")

    __hash__ = int.__hash__


class OwnSearch(tuple):
    """A tuple that answers `in` itself."""

    def __contains__(self, item: object) -> bool:
        return True


class OwnWalk(list):
    """A list whose own walk is empty, which Python's `in` never runs."""

    def __iter__(self):  # noqa: ANN204
        return iter(())


Pair = namedtuple("Pair", "low high")


def tracked(value: int, sink: list[SinkItem]) -> ConcolicInt:
    return ConcolicInt.made(value, expression="x", sink=sink)


@pytest.mark.parametrize("container", [(Status.OK, Status.BAD), [Status.OK, Status.BAD]])
def test_enum_members_are_compared_with_the_tracked_value_on_the_left(container: object) -> None:
    sink: list[SinkItem] = []

    assert in_(tracked(7, sink), container) is False
    assert expressions(sink) == [(["==", "x", 0], False), (["==", "x", 1], False)]


def test_the_walk_stops_at_the_first_element_that_holds() -> None:
    sink: list[SinkItem] = []

    assert in_(tracked(0, sink), (Status.OK, Status.BAD)) is True
    assert expressions(sink) == [(["==", "x", 0], True)]


def test_not_in_records_the_same_forks() -> None:
    sink: list[SinkItem] = []

    assert not_in(tracked(3, sink), [Status.OK, Status.BAD, 3]) is False
    assert expressions(sink) == [
        (["==", "x", 0], False),
        (["==", "x", 1], False),
        (["==", "x", 3], True),
    ]


def test_a_bool_element_is_written_as_a_bool() -> None:
    sink: list[SinkItem] = []

    assert in_(tracked(1, sink), (True, 3)) is True
    assert expressions(sink) == [(["==", "x", True], True)]


def test_a_tracked_bool_meets_true_among_the_elements() -> None:
    sink: list[SinkItem] = []
    flag = ConcolicBool.made(False, expression="flag", sink=sink)

    assert in_(flag, (True,)) is False
    assert expressions(sink) == [(["==", "flag", True], False)]


def test_an_element_with_its_own_eq_is_asked_as_python_asks_it() -> None:
    sink: list[SinkItem] = []
    Loud.asked = []
    x = tracked(1, sink)

    assert in_(x, (Loud(1), Status.BAD)) is True
    assert Loud.asked == [x]
    assert expressions(sink) == [(["==", "x", 1], True)]


def test_the_tracked_value_itself_holds_by_identity_with_no_fork() -> None:
    sink: list[SinkItem] = []
    x = tracked(7, sink)

    Loud.asked = []

    assert in_(x, [x, Loud(7)]) is True
    assert Loud.asked == []
    assert expressions(sink) == []


def test_an_element_whose_eq_raises_raises_as_python_does() -> None:
    sink: list[SinkItem] = []

    with pytest.raises(ValueError, match="no compare"):
        in_(tracked(7, sink), (Status.OK, Refusing(1)))
    assert expressions(sink) == [(["==", "x", 0], False)]


def test_a_tuple_subclass_that_keeps_tuple_s_search_is_walked() -> None:
    sink: list[SinkItem] = []

    assert in_(tracked(3, sink), Pair(Status.OK, Status.BAD)) is False
    assert expressions(sink) == [(["==", "x", 0], False), (["==", "x", 1], False)]


def test_a_subclass_with_its_own_search_is_asked() -> None:
    sink: list[SinkItem] = []

    assert in_(tracked(3, sink), OwnSearch((Status.OK,))) is True
    assert expressions(sink) == []


def test_a_list_subclass_s_own_walk_never_runs() -> None:
    sink: list[SinkItem] = []

    assert in_(tracked(1, sink), OwnWalk([Status.OK, Status.BAD])) is True
    assert expressions(sink) == [(["==", "x", 0], False), (["==", "x", 1], True)]


def test_a_tracked_float_is_searched_as_python_searches() -> None:
    sink: list[SinkItem] = []
    f = ConcolicFloat.made(2.0, expression="f", sink=sink)

    # int declines a float, so Python asks the tracked float, which records its fork
    assert in_(f, (Status.OK,)) is False
    assert expressions(sink) == [(["==", "f", 0], False)]


def test_a_chain_link_walks_the_container_it_searches() -> None:
    sink: list[SinkItem] = []

    assert (tracked(1, sink) in Searched((Status.OK, Status.BAD))) is True
    assert expressions(sink) == [(["==", "x", 0], False), (["==", "x", 1], True)]
