"""The rule for when the walk goes into an object's deepcopy: a copy only its class's default
route made, of the same type and shape as the original. A class that breaks one part of the
rule has its copy handed on plain; a class that keeps to it, UserDict, UserList and OrderedDict
among them, is followed."""

import copy
import copyreg
from collections import OrderedDict, UserDict, UserList
from collections.abc import Iterable
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


class OwnGetnewargs(Plain):
    def __getnewargs__(self) -> tuple[()]:
        return ()


class OwnGetnewargsEx(Plain):
    def __getnewargs_ex__(self) -> tuple[tuple[()], dict[str, object]]:
        return (), {}


class Answering(Plain):
    """An object whose ``__getattr__`` answers deepcopy's look-up of ``__deepcopy__``."""

    def __getattr__(self, name: str) -> object:
        if name == "__deepcopy__":
            return lambda memo: Answering()
        raise AttributeError(name)


class Registered(Plain):
    """A class whose copy a reducer registered with copyreg makes."""


def _rebuilt(value: Registered) -> tuple[object, ...]:
    return (Registered, (), dict(vars(value)))


class FromRegistered(Registered):
    """A subclass of a registered class: deepcopy reads the table for the exact class only."""


def plain_ints(values: Iterable[object]) -> bool:
    """Whether every value is an int itself: a tracked int is of a subclass of int."""
    return all(type(value) is int for value in values)


@pytest.mark.parametrize(
    "kind",
    [
        OwnDeepcopy,
        OwnReduce,
        OwnReduceEx,
        OwnGetstate,
        OwnSetstate,
        OwnNew,
        OwnGetnewargs,
        OwnGetnewargsEx,
        Answering,
        Registered,
    ],
    ids=lambda kind: kind.__name__,
)
def test_an_object_whose_copy_its_class_makes_its_own_way_is_handed_on_plain(
    kind: type[Plain], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(copyreg.dispatch_table, Registered, _rebuilt)
    given = kind()
    fields = vars(given)

    args: dict[str, Any] = bind({"o": given}, [])

    made = args["o"]
    assert type(made) is kind and made is not given
    assert type(made.n) is int
    assert vars(given) is fields and list(fields) == ["n"] and plain_ints(fields.values())
    assert leaves({"o": given}) == {}


def test_a_subclass_of_a_class_registered_with_copyreg_is_followed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(copyreg.dispatch_table, Registered, _rebuilt)

    assert leaves({"o": FromRegistered()}) == {'["getattr", "o", "\'n\'"]': int}


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
    assert plain_ints(dict.values(args["d"]))
    assert type(args["u"]) is Unique and plain_ints(args["u"])
    assert list(dict.keys(lower)) == ["A", "a"] and plain_ints(dict.values(lower))
    assert list.__len__(unique) == 2 and plain_ints(unique)
    assert leaves({"d": lower, "u": unique}) == {}


class Recording(list[int]):
    """A list whose own ``append`` notes the last value in its ``__dict__``."""

    def append(self, value: int) -> None:
        self.last = value
        super().append(value)


def test_a_copy_whose_dict_holds_other_keys_is_handed_on_plain() -> None:
    recording: Any = Recording()
    list.extend(recording, [1, 2])
    recording.n = 0

    args: dict[str, Any] = bind({"r": recording}, [])

    assert type(args["r"]) is Recording and plain_ints(args["r"])
    assert vars(recording) == {"n": 0} and plain_ints(recording)
    assert leaves({"r": recording}) == {}


def test_userdict_userlist_and_ordereddict_are_followed() -> None:
    # deepcopy never calls __copy__, which UserDict and UserList define, and OrderedDict's
    # own __reduce__ is built into Python
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
