"""The values the walk does not follow, each copied whole where the walk reaches it with nothing
inside tracked, and the copies the walk makes of the objects it follows."""

import copy
import threading
import time
from collections import deque
from typing import Any

import pytest

from pyct.binding.bind import bind, leaves
from pyct.core.numbers.ints import ConcolicInt


def test_two_values_copied_whole_that_hold_one_list_hold_one_copy_of_it() -> None:
    x = [1]

    args: dict[str, Any] = bind({"p": deque([x]), "q": deque([x]), "x": x}, [])

    assert args["p"][0] is args["q"][0] and args["p"][0] is not args["x"]
    assert type(args["p"][0][0]) is int and isinstance(args["x"][0], ConcolicInt)


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
