"""The rule for when the walk goes into an object's deepcopy: a copy only its class's default
route made, of the same type and shape as the original. Each class here breaks one part of it,
and its copy is handed on plain."""

import copy
import copyreg
from collections import OrderedDict, UserDict, UserList
from typing import Any

import pytest

from pyct.binding.bind import bind, leaves


class Plain:
    """An object with an int, whose class copies by Python's default route."""

    def __init__(self) -> None:
        self.n = 0


class OwnDeepcopy(Plain):
    def __deepcopy__(self, memo: dict[int, object]) -> "OwnDeepcopy":
        made = OwnDeepcopy()
        made.n = copy.deepcopy(self.n, memo)
        return made


class OwnReduce(Plain):
    def __reduce__(self) -> tuple[object, ...]:
        return (type(self), (), dict(vars(self)))


class OwnReduceEx(Plain):
    def __reduce_ex__(self, protocol: Any) -> tuple[object, ...]:
        return (type(self), (), dict(vars(self)))


class OwnGetstate(Plain):
    def __getstate__(self) -> dict[str, object]:
        return dict(vars(self))


class OwnSetstate(Plain):
    def __setstate__(self, state: dict[str, object]) -> None:
        vars(self).update(state)


class OwnNew(Plain):
    def __new__(cls) -> "OwnNew":
        return super().__new__(cls)


class Registered(Plain):
    """A class whose copy a reducer registered with copyreg makes."""


def _rebuilt(value: Registered) -> tuple[object, ...]:
    return (Registered, (), dict(vars(value)))


@pytest.mark.parametrize(
    "kind",
    [OwnDeepcopy, OwnReduce, OwnReduceEx, OwnGetstate, OwnSetstate, OwnNew, Registered],
    ids=lambda kind: kind.__name__,
)
def test_an_object_whose_copy_its_class_makes_its_own_way_is_handed_on_plain(
    kind: type[Plain], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(copyreg.dispatch_table, Registered, _rebuilt)
    given = kind()

    args: dict[str, Any] = bind({"o": given}, [])

    made = args["o"]
    assert type(made) is kind and made is not given
    assert type(made.n) is int and vars(given) == {"n": 0}
    assert leaves({"o": given}) == {}


class Lower(dict[str, int]):
    """A dict whose own ``__setitem__`` folds its keys to lower case."""

    def __setitem__(self, key: str, value: int) -> None:
        super().__setitem__(key.lower(), value)


class Unique(list[int]):
    """A list whose own ``append`` skips a value it already holds."""

    def append(self, value: int) -> None:
        if value not in self:
            super().append(value)


def test_a_container_whose_copy_holds_another_shape_is_handed_on_plain() -> None:
    lower = Lower()
    dict.update(lower, {"A": 0, "a": 1})
    unique = Unique([5, 5])

    args: dict[str, Any] = bind({"d": lower, "u": unique}, [])

    assert type(args["d"]) is Lower and args["d"] is not lower
    assert all(type(value) is int for value in dict.values(args["d"]))
    assert type(args["u"]) is Unique and all(type(value) is int for value in args["u"])
    assert dict(lower) == {"A": 0, "a": 1} and list(unique) == [5, 5]
    assert leaves({"d": lower, "u": unique}) == {}


def test_a_container_whose_class_only_copies_itself_shallowly_is_followed() -> None:
    # deepcopy never calls __copy__, so a class that defines only it copies by the default route
    seed: dict[str, object] = {
        "ud": UserDict({"n": 0}),
        "ul": UserList([0]),
        "od": OrderedDict(k=0),
    }

    named = leaves(seed)

    assert named == {
        '["[]", ["getattr", "ud", "\'data\'"], "\'n\'"]': int,
        '["[]", ["getattr", "ul", "\'data\'"], 0]': int,
        '["[]", "od", "\'k\'"]': int,
    }
