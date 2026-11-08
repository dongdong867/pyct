import json
import time
from collections import defaultdict, namedtuple
from typing import Any

from pyct.binding.bind import Seed, bind, leaves
from pyct.binding.model import apply
from pyct.core.lists.lists import ConcolicList
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr

Pair = namedtuple("Pair", ["left", "right"])


class Counted(Pair):
    """A namedtuple whose own constructor counts each call, with no ``__dict__`` of its own."""

    __slots__ = ()
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


class Table(dict[object, object]):
    """A dict of the caller's own type."""


def test_a_dict_subclass_takes_its_values_under_the_keys_its_copy_holds() -> None:
    # deepcopy copies the keys, and a key equal only to itself is found only as the copy's own
    table = Table({IdentityKey(): 1, "n": 2})

    args: dict[str, Any] = bind({"t": table}, [])

    made = args["t"]
    assert type(made) is Table and len(made) == 2
    assert isinstance(made["n"], ConcolicInt) and made["n"].expression == ["[]", "t", "'n'"]
