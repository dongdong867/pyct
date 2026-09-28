"""A plain key Python's lookup makes the same as an int, looked up as that int, and a key pyct
does not follow that turns a `dict[int, X]` plain, since it may equal a made-up key."""

import enum
from decimal import Decimal
from fractions import Fraction

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade
from pyct.core.dict_reads import int_key
from pyct.core.dicts import ConcolicDict
from pyct.core.floats import ConcolicFloat


class Color(enum.IntEnum):
    RED = 0


class Flag(enum.IntFlag):
    ON = 1


class OwnHash(int):
    def __hash__(self) -> int:
        return int.__hash__(self)


@pytest.mark.parametrize(
    ("key", "looked"),
    [(Color.RED, 0), (Flag.ON, 1), (True, 1), (False, 0), (1.0, 1), (-0.0, 0), (7, 7)],
)
def test_a_key_python_looks_up_as_an_int_is_that_int(key: object, looked: int) -> None:
    found = int_key(key)

    assert type(found) is int and found == looked


@pytest.mark.parametrize("key", [0.5, float("inf"), float("nan"), OwnHash(0), "0", None], ids=repr)
def test_any_other_key_is_itself(key: object) -> None:
    assert int_key(key) is key


def test_a_tracked_bool_is_not_read_as_an_int() -> None:
    flag = ConcolicBool.made(True, "b", [])

    assert int_key(flag) is flag


def test_an_int_equal_key_records_the_int_s_fork() -> None:
    sink: list[object] = []
    d = ConcolicDict.made({1: 5}, "d", sink, int_keyed=True)

    assert Color.RED not in d and d[True] == 5
    assert [(b.expression, b.taken) for b in sink if isinstance(b, Branch)] == [
        (["in", 0, "d"], False),
        (["in", 1, "d"], True),
    ]


@pytest.mark.parametrize("int_keyed", [True, False])
def test_a_key_that_may_equal_a_made_up_int_turns_only_an_int_keyed_dict_plain(
    int_keyed: bool,
) -> None:
    sink: list[object] = []
    d = ConcolicDict.made({}, "d", sink, int_keyed=int_keyed)

    assert OwnHash(0) not in d
    assert ConcolicFloat.made(1.0, "x", sink) not in d
    assert (d.expression is None) is int_keyed
    assert [item.name for item in sink if isinstance(item, Downgrade)][:1] == ["__contains__"]


class Loose:
    def __eq__(self, other: object) -> bool:
        return other == 0

    def __hash__(self) -> int:
        return 0


@pytest.mark.parametrize(
    ("key", "plain"),
    [
        (Fraction(0), True),
        (Decimal(0), True),
        (0.5, False),
        (ConcolicFloat.made(0.5, "x", []), True),
        (Loose(), True),
        ((0,), False),
        (None, False),
        (b"0", False),
        (frozenset(), False),
    ],
    ids=[
        "fraction",
        "decimal",
        "half",
        "tracked float",
        "own eq",
        "tuple",
        "none",
        "bytes",
        "frozenset",
    ],
)
def test_a_key_turns_an_int_keyed_dict_plain_when_it_may_equal_an_int(
    key: object, plain: bool
) -> None:
    d = ConcolicDict.made({}, "d", [], int_keyed=True)

    assert key not in d
    assert (d.expression is None) is plain
