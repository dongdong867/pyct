import json
from collections import defaultdict, namedtuple
from typing import Any

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


def test_a_tuple_reached_again_inside_itself_is_one_tuple_as_deepcopy_copies_it() -> None:
    held: list[object] = []
    t = (held, 0)
    held.append(t)

    args: dict[str, Any] = bind({"t": t}, [])

    made = args["t"]
    assert type(made) is tuple and made is not t
    inner = made[0]
    assert isinstance(inner, ConcolicList) and list.__getitem__(inner, 0) is made
    # the values directly in it are plain
    assert type(made[1]) is int
