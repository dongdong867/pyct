"""`in` on a set, a frozenset or a dict's keys, however the target built it, and the two
containers a chained compare's `in` and `is` links search."""

import math
from collections import Counter, OrderedDict
from decimal import Decimal
from enum import IntEnum, StrEnum

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Downgrade, SinkItem
from pyct.core.floats import ConcolicFloat
from pyct.core.hashed import SEARCHED_MOST
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from pyct.core.substitutes import Identity, Searched, in_, not_in
from tests.unit.core.test_substitutes import expressions, tracked_bool


def test_a_tracked_value_in_a_set_is_compared_with_each_element_in_its_own_order() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(0, expression="n", sink=sink)
    held = {3, 1, 2}

    assert in_(n, held) is False
    assert not_in(n, held) is True
    # one `==` fork per element, as the set iterates, for `in` and `not in` alike
    tried = [(["==", "n", element], False) for element in held]
    assert expressions(sink) == tried + tried


def test_the_search_stops_at_the_first_element_that_holds() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(2, expression="n", sink=sink)

    assert in_(n, frozenset({1, 2, 3})) is True
    tried = expressions(sink)
    assert tried[-1] == (["==", "n", 2], True)
    assert all(side == (["==", "n", 1], False) for side in tried[:-1])


@pytest.mark.parametrize(
    "keys",
    [
        {"a": 1, "b": 2},
        {"a": 1, "b": 2}.keys(),
        OrderedDict(a=1, b=2),
        Counter(a=1, b=2),
    ],
    ids=["dict", "keys", "OrderedDict", "Counter"],
)
def test_a_tracked_value_in_a_dict_is_compared_with_each_key(keys: object) -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr.made("b", expression="s", sink=sink)

    assert in_(s, keys) is True
    assert expressions(sink) == [(["==", "s", "'a'"], False), (["==", "s", "'b'"], True)]


def test_an_empty_container_compares_with_nothing() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(0, expression="n", sink=sink)

    assert in_(n, set()) is False
    assert not_in(n, {}) is True
    assert sink == []


def test_a_hundred_elements_are_each_compared() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(-1, expression="n", sink=sink)

    assert in_(n, set(range(SEARCHED_MOST))) is False
    assert expressions(sink) == [(["==", "n", k], False) for k in range(SEARCHED_MOST)]


@pytest.mark.parametrize(("value", "answer"), [(-1, False), (5, True)])
def test_past_a_hundred_elements_python_answers_and_the_loss_is_named(
    value: int, answer: bool
) -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(value, expression="n", sink=sink)
    held = dict.fromkeys(range(SEARCHED_MOST + 1))

    assert in_(n, held) is answer
    assert not_in(n, held) is not answer
    # Python's own lookup reads the plain value, so even a match records no fork
    assert sink == [Downgrade(name="__contains__")] * 2


def test_an_element_pyct_does_not_compare_leaves_the_answer_to_python_and_names_the_loss() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(1, expression="n", sink=sink)

    # Decimal(1) equals the int 1 and hashes as it does, so Python finds it; pyct follows no
    # element of such a container, and says so
    assert in_(n, {Decimal(1), 7}) is True
    assert not_in(n, {Decimal(2), 7}) is True
    assert sink == [Downgrade(name="__contains__")] * 2


class Raising:
    """An element that hashes as the int 1 and whose `==` raises once armed, as a target's may."""

    armed = False

    def __hash__(self) -> int:
        return 1

    def __eq__(self, other: object) -> bool:
        if Raising.armed:
            raise RuntimeError("the element's own raise")
        return False


def test_an_element_s_own_raise_comes_as_python_s_lookup_raises_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    n = ConcolicInt.made(1, expression="n", sink=[])
    held = {Raising(), 1}
    monkeypatch.setattr(Raising, "armed", True)

    with pytest.raises(RuntimeError, match="the element's own raise"):
        1 in held  # noqa: B015 - the plain answer the tracked one must match
    with pytest.raises(RuntimeError, match="the element's own raise"):
        in_(n, held)


def test_a_nan_is_found_by_its_identity_as_python_finds_it() -> None:
    sink: list[SinkItem] = []
    f = ConcolicFloat.made(math.nan, expression="f", sink=sink)

    # a NaN equals nothing, itself included, and Python tests identity before `==`
    assert in_(f, {f}) is True
    assert in_(f, {f: 1, 2.5: 2}) is True
    assert not_in(f, frozenset({math.nan})) is True
    # the plain NaN is another object, so it is compared, and equals nothing
    assert [repr(side) for side in expressions(sink)] == ["(['==', 'f', nan], False)"]
    beyond = set(range(SEARCHED_MOST)) | {f}
    assert in_(f, beyond) is True


def test_a_nan_before_its_own_element_records_no_fork_for_the_element_it_is() -> None:
    sink: list[SinkItem] = []
    f = ConcolicFloat.made(math.nan, expression="f", sink=sink)

    assert in_(f, {f}) is True
    assert sink == []


class Level(IntEnum):
    LOW = 1
    HIGH = 2


class Method(StrEnum):
    GET = "GET"
    POST = "POST"


def test_an_enum_element_is_compared_as_the_plain_value_python_compares() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt.made(2, expression="n", sink=sink)
    s = ConcolicStr.made("PUT", expression="s", sink=sink)

    assert in_(n, {Level.LOW, Level.HIGH}) is True
    assert in_(s, frozenset({Method.GET, Method.POST})) is False
    assert expressions(sink) == [
        (["==", "n", 1], False),
        (["==", "n", 2], True),
        *[(["==", "s", repr(str(m))], False) for m in frozenset({Method.GET, Method.POST})],
    ]
    written = [item.expression[2] for item in sink]  # pyrefly: ignore[missing-attribute]
    assert [type(value) for value in written] == [int, int, str, str]


def test_none_among_the_elements_is_never_equal_and_records_nothing() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr.made("a", expression="s", sink=sink)

    assert in_(s, {None, "a"}) is True
    assert expressions(sink) == [(["==", "s", "'a'"], True)]


def test_a_subclass_s_own_len_is_never_run() -> None:
    class Sized(dict[int, int]):
        def __len__(self) -> int:
            raise RuntimeError("len called")

    sink: list[SinkItem] = []
    n = ConcolicInt.made(0, expression="n", sink=sink)

    assert in_(n, Sized({1: 1})) is False
    assert expressions(sink) == [(["==", "n", 1], False)]


def test_a_tracked_bool_and_a_tracked_float_are_searched_too() -> None:
    sink: list[SinkItem] = []
    b = tracked_bool(True, sink)
    f = ConcolicFloat.made(2.5, expression="f", sink=sink)

    assert in_(b, {1}) is True
    assert in_(f, frozenset({2.5})) is True
    assert expressions(sink) == [(["==", [">", "x", 5], 1], True), (["==", "f", 2.5], True)]


def test_a_container_with_its_own_contains_is_pythons_own_in() -> None:
    asked: list[object] = []

    class Everything(set[int]):
        def __contains__(self, item: object) -> bool:
            asked.append(item)
            return True

    sink: list[SinkItem] = []
    n = ConcolicInt.made(0, expression="n", sink=sink)

    assert in_(n, Everything({1})) is True
    assert asked == [n]
    assert sink == []


def test_a_plain_value_in_a_set_is_pythons_own_lookup() -> None:
    assert in_(3, {1, 2, 3}) is True
    assert not_in("a", {"b": 1}) is True


def test_a_chained_in_link_searches_its_container_as_in_does() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt.made(5, expression="x", sink=sink)

    # a set display of constants hands over its constants, in the order written
    assert (x in Searched(frozenset({9, 5, 1}), (1, 5, 9))) is True
    assert (x not in Searched([4])) is True
    assert expressions(sink) == [
        (["==", "x", 1], False),
        (["==", "x", 5], True),
        (["==", "x", 4], False),
    ]


def test_a_chained_in_link_on_a_tracked_string_tests_its_condition_where_it_runs() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr.made("abc", expression="s", sink=sink)

    assert ("b" in Searched(s)) is True
    assert expressions(sink) == [(["in", "'b'", "s"], True)]


def test_a_link_hands_the_next_link_the_operand_it_holds() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt.made(5, expression="x", sink=sink)
    held = Searched(x)

    # a compare runs on the operand, and pyct's own `in` and `is` read it
    below = held < 7
    assert isinstance(below, ConcolicBool) and below.expression == ["<", "x", 7]
    unequal = held != 5
    assert isinstance(unequal, ConcolicBool) and unequal.expression == ["!=", "x", 5]
    assert repr(unequal) == "False"
    assert (held in Searched([5])) is True
    assert (held in Identity(x)) is True
    assert (held in Identity(True)) is False
    assert expressions(sink) == [(["==", "x", 5], True)]


def test_a_chained_is_link_answers_from_the_value() -> None:
    sink: list[SinkItem] = []
    flag = ConcolicBool.made(False, expression="flag", sink=sink)

    assert (flag in Identity(True)) is False
    assert (flag not in Identity(False)) is False
    assert (None in Identity(True)) is False
    assert (True in Identity(True)) is True
    # True or False on the link's left meets the operand the call holds on its right
    assert (True in Identity(flag)) is False
    # a tracked bool is tested for truth, as `if flag:` tests it
    assert expressions(sink) == [("flag", False)] * 3


def test_a_subclass_that_hashes_otherwise_leaves_the_answer_to_python() -> None:
    class Odd(int):
        def __hash__(self) -> int:
            return 7

    class Loud(str):
        def __eq__(self, other: object) -> bool:
            return str.__eq__(self, other)

        __hash__ = str.__hash__

    sink: list[SinkItem] = []
    n = ConcolicInt.made(1, expression="n", sink=sink)
    s = ConcolicStr.made("a", expression="s", sink=sink)

    # its `==` may no longer agree with its hash, so pyct compares nothing and names the loss
    assert in_(n, {Odd(1)}) is (1 in {Odd(1)})
    assert in_(s, {Loud("a")}) is True
    assert sink == [Downgrade(name="__contains__")] * 2
