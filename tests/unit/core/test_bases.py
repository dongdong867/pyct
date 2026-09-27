"""Each tracked class reports its base type as its class, and builds that type's plain value when
called outside pyct's construction (tracked-values-report-their-base-type-as-their-class)."""

import copy
import functools
import pickle

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import SinkItem
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.lists import ConcolicList
from pyct.core.strs import ConcolicStr
from pyct.core.values import BASES, raised_by_target


def tracked_values(sink: list[SinkItem]) -> list[tuple[object, type]]:
    """One tracked value of each tracked type, beside the base type Python's own value has."""
    return [
        (ConcolicInt(1, expression="n", sink=sink), int),
        (ConcolicFloat(2.5, expression="r", sink=sink), float),
        (ConcolicStr("a", expression="s", sink=sink), str),
        (ConcolicBool(True, expression="b", sink=sink), bool),
        (ConcolicList.made([1], "xs", sink), list),
    ]


def test_the_table_holds_each_tracked_class_and_its_base_type() -> None:
    assert {
        ConcolicInt: int,
        ConcolicFloat: float,
        ConcolicStr: str,
        ConcolicBool: bool,
        ConcolicList: list,
    } == BASES


def test_a_tracked_value_reports_its_base_type_as_its_class() -> None:
    sink: list[SinkItem] = []

    for value, base in tracked_values(sink):
        assert value.__class__ is base
        assert isinstance(value, base)
        # pyct tells a tracked value apart by its real type, which stays its own
        assert type(value) is not base
        assert isinstance(value, type(value))
    # reading the class reads no value
    assert sink == []


def test_a_tracked_bool_is_a_bool_and_a_tracked_int_is_not() -> None:
    sink: list[SinkItem] = []
    flag = ConcolicBool(True, expression="b", sink=sink)
    n = ConcolicInt(1, expression="n", sink=sink)

    assert isinstance(flag, bool) and isinstance(flag, int)
    assert isinstance(flag, (str, bool)) and issubclass(flag.__class__, bool)
    assert not isinstance(n, bool) and n.__class__ is not bool
    assert not isinstance(flag, str)
    assert sink == []


def test_singledispatch_picks_the_handler_of_the_base_type() -> None:
    @functools.singledispatch
    def kind(value: object) -> str:
        return "object"

    kind.register(int, lambda value: "int")
    kind.register(bool, lambda value: "bool")
    sink: list[SinkItem] = []

    assert kind(ConcolicBool(True, expression="b", sink=sink)) == "bool"
    assert kind(ConcolicInt(1, expression="n", sink=sink)) == "int"


def test_the_class_itself_is_still_a_class() -> None:
    for tracked in BASES:
        assert tracked.__class__ is type


@pytest.mark.parametrize(
    ("tracked", "args", "expected"),
    [
        (ConcolicInt, (5,), 5),
        (ConcolicInt, ("ff", 16), 255),
        (ConcolicInt, (), 0),
        (ConcolicFloat, (1.5,), 1.5),
        (ConcolicStr, ("hi",), "hi"),
        (ConcolicStr, (b"hi", "ascii"), "hi"),
        (ConcolicBool, (0,), False),
        (ConcolicBool, ([1],), True),
        (ConcolicList, ([1],), [1]),
        (ConcolicList, ("ab",), ["a", "b"]),
        (ConcolicList, (), []),
    ],
)
def test_a_tracked_class_called_with_a_value_builds_the_plain_value(
    tracked: type, args: tuple[object, ...], expected: object
) -> None:
    built = tracked(*args)

    assert built == expected
    assert type(built) is BASES[tracked]


def test_a_tracked_class_called_with_keywords_builds_as_its_base_type_does() -> None:
    assert type(ConcolicInt("10", base=2)) is int
    assert ConcolicInt("10", base=2) == 2


@pytest.mark.parametrize(
    ("tracked", "args", "kwargs"),
    [
        (ConcolicInt, ("abc",), {}),
        (ConcolicFloat, ("abc",), {}),
        (ConcolicInt, (1,), {"expression": "n"}),
        (ConcolicList, (5,), {}),
    ],
)
def test_a_tracked_class_raises_what_its_base_type_raises(
    tracked: type, args: tuple[object, ...], kwargs: dict[str, object]
) -> None:
    base = BASES[tracked]
    with pytest.raises(Exception) as plain:
        base(*args, **kwargs)
    with pytest.raises(type(plain.value)) as raised:
        tracked(*args, **kwargs)

    assert str(raised.value) == str(plain.value)
    # the raise is the target's program failing, not pyct's
    assert raised_by_target(raised.value)


def test_pyct_still_builds_a_tracked_value() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt(3, expression="n", sink=sink)

    assert type(n) is ConcolicInt
    assert n.expression == "n" and n.sink is sink


def test_a_copy_is_the_value_itself_and_a_pickle_the_plain_value() -> None:
    sink: list[SinkItem] = []

    for value, base in tracked_values(sink):
        if base is not list:
            assert copy.copy(value) is value and copy.deepcopy(value) is value
        loaded = pickle.loads(pickle.dumps(value))
        assert type(loaded) is base and loaded == value
