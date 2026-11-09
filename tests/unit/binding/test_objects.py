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
    given: Any = Both()

    args = bind({"o": given}, [])

    made: Any = args["o"]
    assert isinstance(made.m, ConcolicInt) and isinstance(made._Slotted__key, ConcolicInt)
    assert type(made) is Both
    assert list(leaves({"o": Both()})) == [
        name("o", "own"),
        name("o", "m"),
        name("o", "_Slotted__key"),
        name("o", "n"),
    ]
    assert type(given.m) is int and type(given._Slotted__key) is int and type(given.own) is int


@dataclass(frozen=True)
class Frozen:
    n: int


@dataclass(frozen=True, slots=True)
class FrozenSlots:
    n: int


def test_a_frozen_dataclass_takes_its_value_as_its_init_stores_it() -> None:
    f = Frozen(0)

    args: dict[str, Any] = bind({"f": f}, [])

    assert isinstance(args["f"].n, ConcolicInt) and type(f.n) is int


def test_a_frozen_dataclass_with_slots_copies_by_its_own_hooks_and_stays_plain() -> None:
    # dataclasses gives a frozen class with slots a __getstate__ and __setstate__ of its own
    g = FrozenSlots(0)

    args: dict[str, Any] = bind({"g": g}, [])

    assert type(args["g"]) is FrozenSlots and args["g"] is not g and type(args["g"].n) is int


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
    """An object whose own copy hook gives the copy a lock of its own, and copies its int."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.n = 0

    def __deepcopy__(self, memo: dict[int, object]) -> "Hooked":
        made = Hooked()
        made.n = copy.deepcopy(self.n, memo)
        return made


class Reordered(dict[str, object]):
    """A dict whose own copy hook gives back its keys in another order."""

    def __deepcopy__(self, memo: dict[int, object]) -> "Reordered":
        return Reordered(b="x", a=0)


DEFAULT: list[object] = []


class Shared:
    """An object whose own copy hook gives back another object the caller holds."""

    def __init__(self) -> None:
        self.n = 0

    def __deepcopy__(self, memo: dict[int, object]) -> "Shared":
        made = DEFAULT[0]
        assert isinstance(made, Shared)
        return made


def test_a_class_with_a_copy_hook_of_its_own_is_handed_on_as_its_hook_made_it() -> None:
    hooked, other = Hooked(), Shared()
    DEFAULT[:] = [other]

    args: dict[str, Any] = bind({"h": hooked, "r": Reordered(a=0, b="x"), "s": Shared()}, [])

    assert isinstance(args["h"], Hooked) and args["h"].lock is not hooked.lock
    assert type(args["h"].n) is int
    assert dict(args["r"]) == {"b": "x", "a": 0} and type(dict.__getitem__(args["r"], "a")) is int
    assert args["s"] is other and type(other.n) is int


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


class State(enum.IntEnum):
    NEW = 1


class Tag(enum.StrEnum):
    A = "a"


class Job:
    def __init__(self) -> None:
        self.state = State.NEW
        self.tag = Tag.A


def test_an_enum_member_inside_an_argument_reaches_the_target_as_the_member() -> None:
    seed: dict[str, object] = {"job": Job(), "pair": (State.NEW, Tag.A)}

    args: dict[str, Any] = bind(seed, [])

    assert args["job"].state is State.NEW and args["job"].tag is Tag.A
    assert args["pair"][0] is State.NEW and args["pair"][1] is Tag.A
    assert leaves(seed) == {}


def test_an_int_or_str_subclass_inside_a_dict_or_a_list_passes_through_as_it_came() -> None:
    seed: dict[str, object] = {"d": {"k": State.NEW}, "xs": [Tag.A, 2]}

    args = bind(seed, [])

    d, xs = args["d"], args["xs"]
    assert isinstance(d, dict) and isinstance(xs, list)
    assert dict.__getitem__(d, "k") is State.NEW and list.__getitem__(xs, 0) is Tag.A
    assert leaves(seed) == {json.dumps(["[]", "xs", 1]): int}


class Cache(dict[str, int]):
    """A dict whose own copy hook hands back an empty one."""

    def __deepcopy__(self, memo: dict[int, object]) -> "Cache":
        return Cache()


class Bag(list[int]):
    """A list whose own copy hook hands back an empty one."""

    def __deepcopy__(self, memo: dict[int, object]) -> "Bag":
        return Bag()


class Other:
    __slots__ = ("x",)


class Reduced:
    """An object whose pickling hook builds an object of another type."""

    __slots__ = ("n",)

    def __init__(self) -> None:
        self.n = 0

    def __reduce__(self) -> tuple[type, tuple[()]]:
        return (Other, ())


def test_a_copy_unlike_its_original_is_handed_on_as_deepcopy_made_it() -> None:
    args: dict[str, Any] = bind({"c": Cache(k=0), "b": Bag([0]), "r": Reduced()}, [])

    assert type(args["c"]) is Cache and len(args["c"]) == 0
    assert type(args["b"]) is Bag and len(args["b"]) == 0
    assert type(args["r"]) is Other


class Single:
    """An object whose own copy hook hands back the object itself."""

    def __init__(self) -> None:
        self.n = 0

    def __deepcopy__(self, memo: dict[int, object]) -> "Single":
        memo[id(self)] = self
        return self


def test_an_object_that_copies_as_itself_is_never_written_into_by_a_second_path() -> None:
    given = Single()

    args = bind({"a": given, "b": given}, [])

    assert args["a"] is given and args["b"] is given
    assert type(given.n) is int


class Owner:
    def __init__(self) -> None:
        self.items = [0]

    def method(self) -> int:
        return len(self.items)


def test_a_list_an_object_holds_is_tracked_whichever_path_reaches_it_first() -> None:
    owner = Owner()

    for seed in ({"f": owner.method, "o": owner}, {"o": owner, "f": owner.method}):
        args: dict[str, Any] = bind(seed, [])

        assert isinstance(args["o"].items, ConcolicList), list(seed)


def test_an_attribute_named_by_a_keyword_is_copied_and_not_named() -> None:
    rule = Rule()
    setattr(rule, "class", 0)

    args = bind({"rule": rule}, [])

    made = args["rule"]
    assert made is not rule and type(getattr(made, "class")) is int
    assert leaves({"rule": rule}) == {name("rule", "limit"): int, name("rule", "label"): str}
