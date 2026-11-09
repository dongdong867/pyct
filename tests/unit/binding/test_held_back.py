"""The values the walk does not follow, copied whole once every path is walked, and the tuples
they hold: one copy each, shared by every holder, whatever the seed's order."""

import copy
import threading
import time
from collections import deque
from typing import Any

import pytest

from pyct.binding.bind import bind, leaves
from pyct.core.numbers.ints import ConcolicInt


@pytest.mark.parametrize("first", ["a", "t"])
def test_a_value_two_copies_hold_is_one_copy_when_one_starts_inside_the_other(
    first: str,
) -> None:
    x = [1]
    t = (deque([x]), 0)
    a = (deque([x, t]), 0)
    seed: dict[str, object] = {"a": a, "t": t} if first == "a" else {"t": t, "a": a}

    args: dict[str, Any] = bind(seed, [])

    assert args["a"][0][0] is args["t"][0][0]
    assert args["a"][0][1] is args["t"]


def test_a_tuple_a_copy_under_way_reaches_again_is_built_once() -> None:
    q: deque[object] = deque()
    b = (q, 1)
    a = (b, 0)
    q.append(a)
    c = (deque([a]), 2)

    args: dict[str, Any] = bind({"c": c, "a": a}, [])

    made = args["a"]
    assert made[0][0][0] is made and args["c"][0][0] is made


class Owner:
    def meth(self) -> int:
        return 1


@pytest.mark.parametrize("first", ["t2", "t1"])
def test_the_method_that_closes_a_cycle_is_the_value_handed_on_as_it_came(first: str) -> None:
    # the deque's copy begins before it copies what it holds; the method's copies its object
    # first, which holds the tuple that holds the method
    owner: Any = Owner()
    method = owner.meth
    t2 = (method, 0)
    p2 = deque([t2])
    t1 = (p2, 0)
    owner.a = t1
    seed: dict[str, object] = {"t2": t2, "t1": t1} if first == "t2" else {"t1": t1, "t2": t2}

    args: dict[str, Any] = bind(seed, [])

    made_t1, made_t2 = args["t1"], args["t2"]
    assert made_t2[0] is method and isinstance(made_t2[1], ConcolicInt)
    assert made_t1[0] is not p2 and made_t1[0][0] is made_t2
    assert owner.a is t1 and p2[0] is t2


def test_a_copy_refused_after_a_tuple_used_it_leaves_the_tuple_holding_the_value() -> None:
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


def test_objects_sharing_a_parent_that_holds_them_are_walked_in_time_linear_in_them() -> None:
    company = Company()
    staff: list[object] = [Employee(company) for _ in range(2000)]
    company.staff = staff
    started = time.monotonic()

    named = leaves({"staff": staff})

    assert time.monotonic() - started < 2
    assert len(named) == 2000
