import enum
import json
import time
from collections import OrderedDict, defaultdict, deque, namedtuple
from typing import Any

import pytest

from pyct.binding.bind import Seed, bind, leaves
from pyct.binding.model import apply
from pyct.core.lists.lists import ConcolicList
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr

Pair = namedtuple("Pair", ["left", "right"])


class Counted(Pair):
    """A namedtuple whose own constructor counts each call."""

    made = 0

    def __new__(cls, left: object, right: object) -> "Counted":
        Counted.made += 1
        return super().__new__(cls, left, right)


class Row(list[object]):
    """A list of the caller's own type."""


def test_a_tuple_s_items_are_tracked_by_index_in_a_tuple_of_its_own_type() -> None:
    seed: dict[str, object] = {"point": (1, "a"), "pair": Pair(2, [3])}

    args: dict[str, Any] = bind(seed, [])

    point, pair = args["point"], args["pair"]
    assert type(point) is tuple and type(pair) is Pair
    assert isinstance(point[0], ConcolicInt) and isinstance(point[1], ConcolicStr)
    assert point[0].expression == ["[]", "point", 0]
    # a list inside a tuple is tracked whole, as an argument's is
    assert isinstance(pair.right, ConcolicList)
    assert leaves(seed) == {
        json.dumps(["[]", "point", 0]): int,
        json.dumps(["[]", "point", 1]): str,
        json.dumps(["[]", "pair", 0]): int,
        json.dumps(["[]", ["[]", "pair", 1], 0]): int,
    }


def test_a_namedtuple_is_built_without_its_own_constructor() -> None:
    given = Counted(0, 1)

    args: dict[str, Any] = bind({"pair": given}, [])

    assert type(args["pair"]) is Counted and isinstance(args["pair"].left, ConcolicInt)
    assert Counted.made == 1


def test_the_model_rebuilds_a_tuple_with_its_answer() -> None:
    seed = Seed.of({"pair": Pair(0, 1)})

    answered = apply(seed, {json.dumps(["[]", "pair", 0]): 7})

    assert answered.args["pair"] == Pair(7, 1) and type(answered.args["pair"]) is Pair
    assert seed.args["pair"] == Pair(0, 1)


def test_a_subclass_of_list_or_dict_keeps_its_type_its_state_and_its_shape() -> None:
    table: defaultdict[str, int] = defaultdict(int, k=0)
    seed: dict[str, object] = {"row": Row([0]), "table": table}

    args: dict[str, Any] = bind(seed, [])

    row, made = args["row"], args["table"]
    assert type(row) is Row and not isinstance(row, ConcolicList)
    assert isinstance(row[0], ConcolicInt) and row[0].expression == ["[]", "row", 0]
    assert type(made) is defaultdict and made.default_factory is int
    assert isinstance(made["k"], ConcolicInt) and made is not table


def test_a_tuple_reached_again_inside_itself_is_one_tuple_with_its_values_tracked() -> None:
    held: list[object] = []
    t = (held, 0)
    held.append(t)

    args: dict[str, Any] = bind({"t": t}, [])

    made = args["t"]
    assert type(made) is tuple and made is not t
    inner = made[0]
    assert isinstance(inner, ConcolicList) and list.__getitem__(inner, 0) is made
    assert isinstance(made[1], ConcolicInt) and made[1].expression == ["[]", "t", 1]
    # what the leaves name is what bind tracks
    assert leaves({"t": t}) == {json.dumps(["[]", "t", 1]): int}


def test_a_tuple_reached_again_through_a_tuple_inside_itself_stays_one_tuple() -> None:
    held: list[object] = []
    t = (held, 0)
    u = (t,)
    held.append(u)

    args: dict[str, Any] = bind({"t": t}, [])

    made = args["t"]
    again = list.__getitem__(made[0], 0)
    assert type(again) is tuple and again[0] is made


def test_a_tuple_first_reached_under_a_key_no_access_names_is_named_by_a_later_path() -> None:
    t = (0, [1])
    seed: dict[str, object] = {"a": {1.5: t}, "b": t}

    args: dict[str, Any] = bind(seed, [])

    a, b = args["a"], args["b"]
    assert dict.__getitem__(a, 1.5) is b and type(b) is tuple
    assert isinstance(b[0], ConcolicInt) and b[0].expression == ["[]", "b", 0]
    assert leaves(seed) == {
        json.dumps(["[]", "b", 0]): int,
        json.dumps(["[]", ["[]", "b", 1], 0]): int,
    }


class Version(tuple[int, ...]):
    """A tuple subclass that keeps an attribute in its own ``__dict__``."""


def test_a_tuple_python_cannot_build_from_its_items_is_copied_whole_and_plain() -> None:
    stamp = time.localtime()
    version: Any = Version((1, 2))
    version.raw = "1.2"
    seed: dict[str, object] = {"stamp": stamp, "version": version, "again": version}

    args: dict[str, Any] = bind(seed, [])

    assert args["stamp"] == stamp and type(args["stamp"]) is time.struct_time
    made: Any = args["version"]
    assert made.raw == "1.2" and type(made) is Version
    assert args["version"] is args["again"] and args["version"] is not version
    assert type(args["version"][0]) is int
    assert leaves(seed) == {}


class IdentityKey:
    """A key equal only to itself, as an object with no ``__eq__`` of its own is."""


class Clause:
    """What a ``Column`` compares to: a value that refuses to be a bool."""

    def __bool__(self) -> bool:
        raise TypeError("a clause is no bool")


class Column:
    """A key whose ``==`` builds a ``Clause``, as a query builder's column does."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> Any:
        return Clause()


class Table(dict[object, object]):
    """A dict of the caller's own type."""


@pytest.mark.parametrize(
    "key",
    [IdentityKey(), (IdentityKey(), 1), Column("id")],
    ids=["identity", "tuple holding an object", "eq gives no bool"],
)
def test_a_dict_subclass_takes_its_values_under_the_keys_its_copy_holds(key: object) -> None:
    # deepcopy copies the keys; each value goes in under the key deepcopy made of its own
    table = Table({key: 1, "n": 2})

    args: dict[str, Any] = bind({"t": table}, [])

    made = args["t"]
    assert type(made) is Table and dict.__len__(made) == 2
    n = dict.__getitem__(made, "n")
    assert isinstance(n, ConcolicInt) and n.expression == ["[]", "t", "'n'"]
    assert leaves({"t": table}) == {json.dumps(["[]", "t", "'n'"]): int}


def test_an_ordered_dict_is_walked_in_its_own_order() -> None:
    ordered = OrderedDict(a=1, b=2)
    ordered.move_to_end("a")

    args: dict[str, Any] = bind({"od": ordered}, [])

    made = args["od"]
    assert list(made) == ["b", "a"] and isinstance(made["a"], ConcolicInt)
    assert list(leaves({"od": ordered})) == [
        json.dumps(["[]", "od", "'b'"]),
        json.dumps(["[]", "od", "'a'"]),
    ]


class Point(Pair):
    """A namedtuple subclass with a method and no ``__slots__``, so its ``__dict__`` is empty."""

    def total(self) -> int:
        return self.left + self.right


def test_a_namedtuple_subclass_with_an_empty_dict_is_built_from_its_items() -> None:
    args: dict[str, Any] = bind({"p": Point(1, 2)}, [])

    assert type(args["p"]) is Point and isinstance(args["p"].left, ConcolicInt)
    assert leaves({"p": Point(1, 2)}) == {
        json.dumps(["[]", "p", 0]): int,
        json.dumps(["[]", "p", 1]): int,
    }


class Owner:
    def __init__(self, held: object) -> None:
        self.held = held

    def method(self) -> object:
        return self.held


def test_a_tuple_named_late_is_the_one_tuple_every_holder_holds() -> None:
    t = (0,)
    seed: dict[str, object] = {
        "a": {1.5: t},
        "s": frozenset({t}),
        "q": deque([t]),
        "f": Owner(t).method,
        "b": t,
    }

    args: dict[str, Any] = bind(seed, [])

    b = args["b"]
    assert isinstance(b[0], ConcolicInt)
    assert dict.__getitem__(args["a"], 1.5) is b
    assert next(iter(args["s"])) is b and args["q"][0] is b
    assert args["f"].__self__.held is b


def test_a_tuple_a_set_holds_before_its_name_is_the_one_tuple_its_name_gives() -> None:
    point = (1, 2)
    seed: dict[str, object] = {"seen": {point}, "box": Owner({point}), "p": point}

    args: dict[str, Any] = bind(seed, [])

    p = args["p"]
    assert isinstance(p[0], ConcolicInt)
    assert next(iter(args["seen"])) is p and next(iter(args["box"].held)) is p


def test_tuples_shared_at_every_level_are_built_once_each() -> None:
    # each level holds the one below twice, and the innermost is named last: a build again
    # per place it was put would cost 2 ** 24 builds
    inner = (0,)
    level: tuple[object, ...] = inner
    for _ in range(24):
        level = (level, level)
    started = time.monotonic()

    named = leaves({"a": {1.5: level}, "b": inner})

    assert time.monotonic() - started < 2
    assert len(named) == 1


class Color(enum.Enum):
    RED = 1


@pytest.mark.parametrize(
    "held", [Color.RED, b"k", frozenset({1})], ids=["enum", "bytes", "frozenset"]
)
def test_a_tuple_holding_a_value_copied_whole_is_one_tuple_for_every_holder(held: object) -> None:
    p = (held, 1)

    args: dict[str, Any] = bind({"seen": {p}, "q": deque([p]), "p": p}, [])

    made = args["p"]
    assert isinstance(made[1], ConcolicInt)
    assert next(iter(args["seen"])) is made and args["q"][0] is made


@pytest.mark.parametrize("first", ["q", "t"])
def test_a_value_copied_whole_holds_the_tuple_the_walk_builds(first: str) -> None:
    t = (0, deque())
    q = deque([t])
    seed: dict[str, object] = {"q": q, "t": t} if first == "q" else {"t": t, "q": q}

    args: dict[str, Any] = bind(seed, [])

    made = args["t"]
    assert args["q"][0] is made and isinstance(made[0], ConcolicInt)
    assert type(t[0]) is int and q[0] is t


class Item:
    def __init__(self) -> None:
        self.n = 0


class Folding(dict[str, object]):
    """A dict whose own ``__setitem__`` folds its keys to lower case."""

    def __setitem__(self, key: str, value: object) -> None:
        super().__setitem__(key.lower(), value)


def test_a_copy_handed_on_plain_at_any_depth_is_not_gone_into() -> None:
    item = Item()
    folding = Folding()
    dict.update(folding, {"A": 0, "a": item})
    holder = Item()
    holder.d = folding  # type: ignore[attr-defined]

    args: dict[str, Any] = bind({"o": holder, "p": item}, [])

    inside = dict.__getitem__(args["o"].d, "a")
    assert inside is not args["p"] and type(inside.n) is int
    assert isinstance(args["p"].n, ConcolicInt)


@pytest.mark.parametrize("first", ["t", "ti"])
@pytest.mark.parametrize(
    ("held", "around"),
    [
        (frozenset({1}), lambda ti: deque([ti])),
        (b"k", lambda ti: frozenset({ti})),
        (frozenset({1}), lambda ti: frozenset({ti})),
        (b"k", lambda ti: deque([ti])),
    ],
    ids=["deque", "frozenset", "frozenset holding frozenset", "deque holding bytes"],
)
def test_a_value_copied_whole_inside_a_tuple_holds_the_tuple_the_walk_builds(
    first: str, held: object, around: Any
) -> None:
    ti = (0, held)
    t = (around(ti), 1)
    seed: dict[str, object] = {"t": t, "ti": ti} if first == "t" else {"ti": ti, "t": t}

    args: dict[str, Any] = bind(seed, [])

    inside = next(iter(args["t"][0]))
    assert inside is args["ti"] and isinstance(inside[0], ConcolicInt)


def test_a_deque_that_holds_the_tuple_it_sits_in_is_one_cycle() -> None:
    held: deque[object] = deque()
    t = (held, 0)
    held.append(t)

    args: dict[str, Any] = bind({"t": t, "q": held}, [])

    made = args["t"]
    assert made[0] is args["q"] and made[0][0] is made
    assert isinstance(made[1], ConcolicInt) and held[0] is t


class Method:
    def meth(self) -> int:
        return 1


@pytest.mark.parametrize("first", ["t", "m"])
def test_a_method_whose_object_holds_the_tuple_it_sits_in_is_handed_on_as_it_came(
    first: str,
) -> None:
    # deepcopy reaches the tuple while it copies the method's object, before the method's own
    # copy exists, so the tuple cannot hold that copy: the method reaches every holder as it
    # came
    owner: Any = Method()
    method = owner.meth
    t = (method, 0)
    owner.t = t
    seed: dict[str, object] = {"t": t, "m": method} if first == "t" else {"m": method, "t": t}

    args: dict[str, Any] = bind(seed, [])

    assert args["m"] is method and args["t"][0] is method
    assert isinstance(args["t"][1], ConcolicInt) and owner.t is t


class Lazy(dict[str, int]):
    """A dict that iterates its keys sorted and refuses to hand out a value."""

    def __iter__(self) -> Any:
        return iter(sorted(dict.keys(self)))

    def __getitem__(self, key: str) -> int:
        raise LookupError(f"{key} not loaded")


def test_a_dict_subclass_is_read_through_dict_s_own_methods() -> None:
    lazy = Lazy()
    dict.update(lazy, {"b": 0, "a": 1})

    args: dict[str, Any] = bind({"d": lazy}, [])

    made = args["d"]
    assert type(made) is Lazy and isinstance(dict.__getitem__(made, "b"), ConcolicInt)
    assert list(leaves({"d": lazy})) == [
        json.dumps(["[]", "d", "'b'"]),
        json.dumps(["[]", "d", "'a'"]),
    ]
