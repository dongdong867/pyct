"""The values the walk does not follow, each copied whole where the walk reaches it with nothing
inside tracked, and the copies the walk makes of the objects it follows."""

import copy
import enum
import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest

from pyct.binding.bind import Seed, bind, leaves
from pyct.binding.model import apply
from pyct.core.numbers.ints import ConcolicInt


def test_values_copied_whole_hold_the_walk_s_copy_of_a_list_they_share() -> None:
    x = [1]

    args: dict[str, Any] = bind({"p": deque([x]), "q": deque([x]), "x": x}, [])

    assert args["p"][0] is args["q"][0] is args["x"]
    assert isinstance(list.__getitem__(args["x"], 0), ConcolicInt) and type(x[0]) is int


def test_a_value_deepcopy_refuses_reaches_every_holder_as_it_came() -> None:
    held: deque[object] = deque()
    t = (held, 0)
    held.extend([t, threading.Lock()])

    args: dict[str, Any] = bind({"t": t, "q": held}, [])

    assert args["q"] is held and args["t"][0] is held
    assert isinstance(args["t"][1], ConcolicInt)


class Item:
    def __init__(self) -> None:
        self.n = 0


def test_an_object_inside_a_tuple_inside_an_object_is_the_outer_deepcopy_s_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    deepcopy = copy.deepcopy

    def counted(value: object, memo: Any = None) -> object:
        calls.append(value)
        return deepcopy(value, memo)

    monkeypatch.setattr(copy, "deepcopy", counted)
    item = Item()
    holder: Any = Item()
    holder.t = (item, 1)

    args: dict[str, Any] = bind({"o": holder, "p": item}, [])

    assert args["o"].t[0] is args["p"] and isinstance(args["p"].n, ConcolicInt)
    assert [value for value in calls if value is item] == []


class Company:
    staff: list[object]


class Employee:
    def __init__(self, company: Company) -> None:
        self.company = company
        self.n = 0


def test_two_thousand_objects_sharing_a_parent_that_holds_them_are_walked_within_seconds() -> None:
    company = Company()
    staff: list[object] = [Employee(company) for _ in range(2000)]
    company.staff = staff
    started = time.monotonic()

    named = leaves({"staff": staff})

    assert time.monotonic() - started < 2
    assert len(named) == 2000


class Counter:
    """An object holding a bound method of its own."""

    def __init__(self) -> None:
        self.n = 0
        self.step = self.inc

    def inc(self) -> None:
        self.n += 1


@pytest.mark.parametrize("first", ["c", "f"])
def test_a_method_copied_whole_is_bound_to_the_walk_s_copy_of_its_object(first: str) -> None:
    counter = Counter()
    method = counter.step
    seed: dict[str, object] = (
        {"c": counter, "f": method} if first == "c" else {"f": method, "c": counter}
    )

    args: dict[str, Any] = bind(seed, [])

    made = args["c"]
    assert made.step.__self__ is made and args["f"].__self__ is made
    assert isinstance(made.n, ConcolicInt)
    assert counter.step.__self__ is counter and type(counter.n) is int


class Node:
    def __init__(self) -> None:
        self.n = 0
        self.neighbors: set[object] = set()


@pytest.mark.parametrize("first", ["x", "y"])
def test_a_set_copied_whole_holds_the_walk_s_copies_of_its_members(first: str) -> None:
    x, y = Node(), Node()
    x.neighbors.add(y)
    y.neighbors.add(x)
    seed: dict[str, object] = {"x": x, "y": y} if first == "x" else {"y": y, "x": x}

    args: dict[str, Any] = bind(seed, [])

    made_x, made_y = args["x"], args["y"]
    assert made_x in made_y.neighbors and next(iter(made_x.neighbors)) is made_y
    assert isinstance(made_x.n, ConcolicInt) and isinstance(made_y.n, ConcolicInt)
    assert x.neighbors == {y} and next(iter(x.neighbors)) is y and type(x.n) is int


class Task:
    def __init__(self, n: int) -> None:
        self.n = n


@pytest.mark.parametrize("first", ["tasks", "ready"])
def test_a_deque_copied_whole_holds_the_walk_s_copies_of_a_list_s_objects(first: str) -> None:
    tasks = [Task(0), Task(1)]
    ready = deque(tasks)
    seed: dict[str, object] = (
        {"tasks": tasks, "ready": ready} if first == "tasks" else {"ready": ready, "tasks": tasks}
    )

    args: dict[str, Any] = bind(seed, [])

    assert args["ready"][0] is args["tasks"][0] and args["ready"][1] is args["tasks"][1]
    assert isinstance(args["tasks"][0].n, ConcolicInt)
    assert ready[0] is tasks[0] and type(tasks[0].n) is int


class Cart:
    def __init__(self) -> None:
        self.n = 0

    def total(self) -> int:
        return self.n


@pytest.mark.parametrize("first", ["cart", "cb"])
def test_a_method_given_beside_its_object_is_bound_to_the_walk_s_copy(first: str) -> None:
    cart = Cart()
    seed: dict[str, object] = (
        {"cart": cart, "cb": cart.total} if first == "cart" else {"cb": cart.total, "cart": cart}
    )

    args: dict[str, Any] = bind(seed, [])

    assert args["cb"].__self__ is args["cart"] and isinstance(args["cart"].n, ConcolicInt)
    assert type(cart.n) is int


@dataclass(frozen=True)
class Edge:
    ends: tuple[int, int]


class Graph:
    """An object holding a frozen dataclass and a set that holds it, hashed by its tuple."""

    def __init__(self) -> None:
        self.e = Edge((0, 0))
        self.index = {self.e}


def test_a_set_copied_whole_hashes_the_walk_s_copy_with_its_tuples_built() -> None:
    graph = Graph()
    ends_0 = json.dumps(["[]", ["getattr", ["getattr", "g", "'e'"], "'ends'"], 0])

    bound: dict[str, Any] = bind({"g": graph}, [])
    answered = apply(Seed.of({"g": graph}), {ends_0: 5})

    assert bound["g"].e in bound["g"].index
    made: Any = answered.args["g"]
    assert made.e.ends == (5, 0) and made.e in made.index
    assert graph.e.ends == (0, 0) and graph.e in graph.index and type(graph.e.ends[0]) is int


class Suit(enum.Enum):
    HEART = 1


@dataclass(frozen=True)
class Card:
    key: tuple[int, object]


class Hand:
    """A frozen dataclass whose tuple mixes an int with a value copied whole, and a set that
    holds it, hashed by that tuple."""

    def __init__(self, other: object) -> None:
        self.c = Card((0, other))
        self.seen = {self.c}


@pytest.mark.parametrize("other", [Suit.HEART, date(2026, 1, 1)], ids=["enum", "date"])
def test_a_set_copied_whole_hashes_a_tuple_that_holds_a_value_copied_whole(other: object) -> None:
    hand = Hand(other)
    key_0 = json.dumps(["[]", ["getattr", ["getattr", "h", "'c'"], "'key'"], 0])

    bound: dict[str, Any] = bind({"h": hand}, [])
    answered = apply(Seed.of({"h": hand}), {key_0: 5})

    assert bound["h"].c in bound["h"].seen and isinstance(bound["h"].c.key[0], ConcolicInt)
    made: Any = answered.args["h"]
    assert made.c.key == (5, other) and made.c in made.seen
    assert hand.c.key == (0, other) and type(hand.c.key[0]) is int and hand.c in hand.seen


class K(enum.Enum):
    A = 1


def test_a_tuple_holding_a_tuple_that_holds_a_value_copied_whole_is_built_after_it() -> None:
    args: dict[str, Any] = bind({"t": ((1, K.A), 2)}, [])

    made = args["t"]
    assert made == ((1, K.A), 2) and made[0][1] is K.A
    assert isinstance(made[0][0], ConcolicInt) and isinstance(made[1], ConcolicInt)
