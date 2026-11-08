import copy
import enum
import json
import threading
import types
from dataclasses import dataclass
from typing import Any

import pytest

from pyct.binding.bind import Seed, bind, leaves
from pyct.binding.model import apply
from pyct.core.lists.lists import ConcolicList
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr


def name(*steps: str) -> str:
    """The leaf name of an access through attributes, from a parameter."""
    access: object = steps[0]
    for step in steps[1:]:
        access = ["getattr", access, repr(step)]
    return json.dumps(access)


class Rule:
    def __init__(self) -> None:
        self.limit = 10
        self.label = "x"


def test_an_object_s_attributes_are_tracked_in_a_copy_of_its_own_type() -> None:
    rule = Rule()

    args = bind({"rule": rule}, [])

    made = args["rule"]
    assert type(made) is Rule and made is not rule
    assert isinstance(made.limit, ConcolicInt) and made.limit.expression == [
        "getattr",
        "rule",
        "'limit'",
    ]
    assert isinstance(made.label, ConcolicStr)
    assert vars(rule) == {"limit": 10, "label": "x"}
    assert leaves({"rule": rule}) == {name("rule", "limit"): int, name("rule", "label"): str}


class Slotted:
    __slots__ = ("__key", "n", "unset")

    def __init__(self) -> None:
        self.__key = 1
        self.n = 2


class Both(Slotted):
    __slots__ = ("m", "__dict__")

    def __init__(self) -> None:
        super().__init__()
        self.m = 3
        self.own = 4


def test_a_slot_is_an_attribute_under_the_name_python_stores_it_after_the_dict() -> None:
    args = bind({"o": Both()}, [])

    made: Any = args["o"]
    assert isinstance(made.m, ConcolicInt) and isinstance(made._Slotted__key, ConcolicInt)
    assert type(made) is Both
    assert list(leaves({"o": Both()})) == [
        name("o", "own"),
        name("o", "m"),
        name("o", "_Slotted__key"),
        name("o", "n"),
    ]


@dataclass(frozen=True)
class Frozen:
    n: int


@dataclass(frozen=True, slots=True)
class FrozenSlots:
    n: int


def test_a_frozen_dataclass_takes_its_value_as_its_init_stores_it() -> None:
    args: dict[str, Any] = bind({"f": Frozen(0), "g": FrozenSlots(0)}, [])

    assert isinstance(args["f"].n, ConcolicInt) and isinstance(args["g"].n, ConcolicInt)


def test_the_model_writes_into_a_copy_of_the_object_and_never_the_seed_s() -> None:
    seed = Seed.of({"f": Frozen(0), "rule": Rule()})

    answered = apply(seed, {name("f", "n"): 7, name("rule", "limit"): 101})

    f, rule = answered.args["f"], answered.args["rule"]
    assert isinstance(f, Frozen) and f.n == 7
    assert isinstance(rule, Rule) and rule.limit == 101 and rule.label == "x"
    assert seed.args["f"] == Frozen(0) and vars(seed.args["rule"])["limit"] == 10


def test_an_attribute_whose_name_is_no_identifier_is_copied_and_not_named() -> None:
    rule = Rule()
    setattr(rule, "not a name", [0])

    args = bind({"rule": rule}, [])

    made = getattr(args["rule"], "not a name")
    assert made == [0] and made is not getattr(rule, "not a name")
    assert type(made[0]) is int
    assert name("rule", "limit") in leaves({"rule": rule})


class Color(enum.Enum):
    RED = 1


class Holds:
    def __init__(self) -> None:
        self.n = 0

    def method(self) -> int:
        return self.n


def test_what_copies_as_itself_or_cannot_be_copied_is_handed_on_as_it_came() -> None:
    seed: dict[str, object] = {"cls": Rule, "fn": name, "color": Color.RED, "mod": types}

    args = bind(seed, [])

    assert all(args[key] is value for key, value in seed.items())


def test_a_bound_method_is_copied_and_never_followed() -> None:
    method = Holds().method

    args = bind({"m": method}, [])

    made: Any = args["m"]
    held: Any = made.__self__
    assert isinstance(made, types.MethodType) and made is not method
    assert type(held.n) is int and held is not method.__self__
    assert leaves({"m": method}) == {}


class Hooked:
    """An object whose own copy hook gives the copy a lock of its own."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.n = 0

    def __deepcopy__(self, memo: dict[int, object]) -> "Hooked":
        made = Hooked()
        made.n = copy.deepcopy(self.n, memo)
        return made


def test_an_attribute_the_walk_cannot_copy_keeps_what_the_copy_hook_made() -> None:
    hooked = Hooked()

    args = bind({"h": hooked}, [])

    made = args["h"]
    assert isinstance(made, Hooked) and made.lock is not hooked.lock
    assert isinstance(made.n, ConcolicInt)


class Outer:
    def __init__(self) -> None:
        self.inner = Rule()
        self.items = [0]
        self.again = self.inner


def test_an_object_inside_is_the_copy_of_the_outer_one_s_deepcopy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    deepcopy = copy.deepcopy

    def counted(value: object, memo: object = None) -> object:
        calls.append(value)
        return deepcopy(value, memo)  # type: ignore[arg-type]

    monkeypatch.setattr(copy, "deepcopy", counted)
    outer = Outer()

    args = bind({"o": outer}, [])

    made: Any = args["o"]
    limit: Any = made.inner.limit
    assert made.inner is made.again and type(made.inner) is Rule
    assert limit.expression == ["getattr", ["getattr", "o", "'inner'"], "'limit'"]
    # a list inside is the walk's own, tracked whole
    assert isinstance(made.items, ConcolicList)
    assert made.items.expression == ["getattr", "o", "'items'"]
    assert [value for value in calls if isinstance(value, Rule)] == []
