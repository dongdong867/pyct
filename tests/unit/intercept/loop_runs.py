"""How the loop shapes are run with the switch off and on: the names a shape's module is given,
the values its arguments are made of, and what one run gives back."""

import asyncio
import contextlib
import copy
import types
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass

import pytest

from pyct.intercept.compiled import substituted_code


def g(*values: object) -> object:
    """The call most shapes make: "z" for no argument, an int less one, a raise below zero, and
    any other value as it is."""
    if not values:
        return "z"
    (value,) = values
    if type(value) is int:
        if value < 0:
            raise ValueError(value)
        return value - 1
    return value


def raising() -> None:
    """A call that raises the error a shape catches."""
    raise LookupError("caught")


# the names each shape's module is given, and those a shape needs of its own
NAMES: dict[str, object] = {"g": g, "h": lambda: None, "cm": contextlib.nullcontext}
CAUGHT = LookupError
OWN_NAMES: dict[str, dict[str, object]] = {"while_in_except": {"g": raising}}


class Down(int):
    """An int that iterates over the ints below it, so one name can be a loop's iterable and a
    count."""

    def __iter__(self) -> Iterator[int]:
        return iter(range(self))


@dataclass
class Node:
    """A link of a list a loop walks."""

    v: int
    next: "Node | None"


class Queue:
    """What the queue shape's `self` reads: its bound, how full it is, and a wait that empties
    it by one."""

    maxsize = 2

    def __init__(self, held: int) -> None:
        self.held = held

    def size(self) -> int:
        return self.held

    def wait(self) -> int:
        self.held -= 1
        return self.held


@dataclass
class Numbers:
    """Numbers an ``async for`` iterates over, afresh each time."""

    values: tuple[int, ...]

    def __aiter__(self) -> AsyncIterator[int]:
        return _numbers(self.values)


async def _numbers(values: tuple[int, ...]) -> AsyncIterator[int]:
    for value in values:
        yield value


def run(shape: str, source: str, args: tuple[object, ...], *, pieces: bool) -> object:
    """What the shape's `f` gives back for a copy of the arguments, or the type and text of what
    it raises; a coroutine is run, a generator read to its end, and a module with no `f` gives
    the names it defines."""
    namespace = {**NAMES, "E": CAUGHT, **OWN_NAMES.get(shape, {})}
    exec(substituted_code(source.encode(), "<shape>", pieces=pieces), namespace)  # noqa: S102
    function = namespace.get("f")
    if not isinstance(function, Callable):
        return _defined(namespace)
    try:
        answer = function(*copy.deepcopy(args))
        if asyncio.iscoroutine(answer):
            return asyncio.run(answer)
        return list(answer) if isinstance(answer, Iterator) else answer
    except Exception as error:
        return type(error), str(error)


def hooks(text: str) -> list[tuple[str, int, int]]:
    """The hook calls a text such as "over 3:4, out 3:4" names: each call's kind and site."""
    found = []
    for each in filter(None, text.split(", ")):
        kind, place = each.split()
        line, col = place.split(":")
        found.append((kind, int(line), int(col)))
    return found


# each run of each shape: its arguments, the hook calls it makes in order, and how it ends. A
# shape left as written, at module level or with no piece makes none
_RUNS: list[tuple[str, tuple[object, ...], str, str]] = [
    ("for", ([1, 2],), "over 3:4, out 3:4", "exhausted"),
    ("for", ([],), "over 3:4, out 3:4", "nothing to iterate"),
    ("while", (3,), "in 3:4, out 3:4", "test false"),
    ("while", (0,), "in 3:4, out 3:4", "never true"),
    ("while_true_break", (2,), "in 3:4, out 3:4", "break"),
    ("while_1_break_last", (3,), "in 3:4, out 3:4", "break"),
    ("for_continue", ([1, -1, 2],), "over 3:4, out 3:4", "continue"),
    ("for_else_break", ([1, 3, 5],), "over 2:4, out 2:4", "break"),
    ("for_else_break", ([1],), "over 2:4, out 2:4", "else"),
    ("while_else_break", (0,), "in 2:4, out 2:4", "break"),
    ("while_else_break", (5,), "in 2:4, out 2:4", "else"),
    (
        "nested_break_in_else",
        ([[0, 1], [2]],),
        "over 3:4, over 4:8, out 4:8, over 4:8, out 4:8, out 3:4",
        "inner breaks",
    ),
    ("nested_break_in_else", ([[0]],), "over 3:4, over 4:8, out 4:8, out 3:4", "inner else breaks"),
    ("for_last_in_function", ([1, 2], 0), "over 3:4, out 3:4", "exhausted"),
    ("while_last_in_function", (2,), "in 3:4, out 3:4", "test false"),
    ("for_last_in_if", ([1, 2], True), "over 3:8, out 3:8", "if"),
    ("for_last_in_if", ([1], False), "", "else raises"),
    ("while_last_in_if", (2, True), "in 3:8, out 3:8", "if"),
    ("while_last_in_if", (2, False), "", "else"),
    ("while_last_in_if_no_else", (2, True), "in 3:8, out 3:8", "if"),
    ("while_last_in_if_no_else", (2, False), "", "skipped"),
    (
        "for_last_in_for",
        ([[1], [2, 3]],),
        "over 2:4, over 3:8, out 3:8, over 3:8, out 3:8, out 2:4",
        "exhausted",
    ),
    ("while_last_in_for", ([2, 1],), "over 2:4, out 2:4", "inner while left"),
    (
        "for_last_in_while",
        (2, [1]),
        "in 2:4, over 4:8, out 4:8, over 4:8, out 4:8, out 2:4",
        "test false",
    ),
    ("while_last_in_while", (2, 3), "in 2:4, out 2:4", "inner while left"),
    ("for_last_in_try", ([1],), "over 3:8, out 3:8", "exhausted"),
    ("for_last_in_try", ([],), "over 3:8, out 3:8", "return raises"),
    ("while_last_in_try_finally", (2,), "in 3:8, out 3:8", "test false"),
    ("for_last_in_with", ([1],), "over 3:8, out 3:8", "exhausted"),
    ("while_last_in_with", (2,), "in 3:8, out 3:8", "test false"),
    ("for_followed_later", ([1],), "over 2:4, out 2:4", "exhausted"),
    ("while_followed_later", (2,), "in 2:4, out 2:4", "test false"),
    ("one_line", (Down(3),), "over 2:4, out 2:4, in 3:4, out 3:4", "exhausted"),
    ("one_line_break", (Down(3),), "over 2:4, out 2:4, in 3:4, out 3:4", "break"),
    ("return_raise_in_body", ([0, 5],), "over 2:4", "return"),
    ("return_raise_in_body", ([0, None],), "over 2:4", "raise"),
    ("while_return_in_body", (5,), "in 2:4", "return"),
    ("while_return_in_body", (2,), "in 2:4, out 2:4", "test false"),
    ("generator", ([1, 2],), "over 3:4, out 3:4, in 6:4, out 6:4", "drained"),
    ("async_for", (Numbers((1, 2)),), "over 3:4, out 3:4", "exhausted"),
    ("async_for_last_break", (Numbers((0, 1, 2)), 5), "over 3:4, out 3:4", "break"),
    ("async_for_last_break", (Numbers((0,)), 5), "over 3:4, out 3:4", "exhausted"),
    ("module_level", (), "", "no piece"),
    ("module_level_last", (), "", "no piece"),
    ("class_body", (), "", "no piece"),
    ("spread_headers", (3, 0), "over 2:4, out 2:4, in 5:4, out 5:4", "exhausted"),
    ("while_and_or", ("abz", 0, 3), "in 2:4, out 2:4", "test false"),
    ("while_not", ("",), "in 2:4, out 2:4", "test false"),
    ("while_not", ("a",), "in 2:4, out 2:4", "never true"),
    ("break_in_try_finally", ([0, 1],), "over 2:4, out 2:4", "break"),
    ("break_in_with", (4,), "in 2:4, out 2:4", "break"),
    ("break_in_with", (1,), "in 2:4, out 2:4", "test false"),
    ("else_returns", ([0, 1],), "over 2:4, out 2:4", "break"),
    ("else_returns", ([0],), "over 2:4, out 2:4", "else returns"),
    ("loop_last_in_match", (1, [5]), "over 4:12, out 4:12", "for"),
    ("loop_last_in_match", (2, [5, 6]), "in 7:12, out 7:12", "while"),
    ("while_last_in_else", (False, 2), "in 5:8, out 5:8", "else"),
    ("while_last_in_else", (True, 2), "", "if"),
    ("while_last_in_if_in_for", ([2], True), "over 2:4, out 2:4", "inner while left"),
    (
        "while_then_continue",
        ([2, 1],),
        "over 2:4, in 3:8, out 3:8, in 3:8, out 3:8, out 2:4",
        "exhausted",
    ),
    ("for_last_in_while_true", ([1, -1], 0), "in 3:4, over 4:8", "raise"),
    ("while_true_no_break_last", (2,), "in 3:4", "raise"),
    ("while_in_except", (2,), "in 5:8, out 5:8", "test false"),
    ("while_chained", (8, 4), "", "left"),
    ("while_last_in_elif_in_with", (Queue(3), True, None), "", "left"),
    ("while_last_in_elif_in_with", (Queue(3), True, 1), "", "else"),
    ("while_and_last_in_if_in_for", (2, "x", [1]), "over 3:4, out 3:4", "inner while left"),
    ("while_and_last_in_if_in_try", (True, Node(1, Node(0, None))), "", "left"),
    ("while_and_last_in_if_in_try", (False, None), "", "else"),
    ("while_or_last_in_if_in_try", (True, Node(1, None)), "", "left, raises"),
    ("while_or_last_in_if_in_try", (False, None), "", "else"),
    ("while_genexp_if", ([1, 5], 0), "", "left"),
    ("while_listcomp_if", ([1, 5], 0), "", "left"),
    (
        "while_and_assign_hooked",
        (2, [0, 1, 2]),
        "in 2:4, in 4:12, value 4:12, in 4:12, value 4:12, out 2:4",
        "test false",
    ),
    ("assign genexp_sum", ("abz",), "in 2:11, value 2:11", "sum"),
    ("assign listcomp", ("ab",), "in 2:8, value 2:8", "list"),
    ("assign dictcomp_ann", ("ab",), "in 2:14, value 2:14", "dict"),
    ("assign augassign", ("ab", 1), "", "no piece"),
    ("assign spread", ("a b",), "in 2:11, value 2:11", "spread"),
    ("assign method_value", ("ab",), "in 3:13, value 3:13", "method"),
    ("assign attr_first", (types.SimpleNamespace(m=len), "ab"), "in 3:13, value 3:13", "attr"),
    ("assign module_level", (), "", "no piece"),
    ("assign last_in_function", ("ab",), "in 2:8, value 2:8", "last"),
    ("assign unpack_target", ("abc",), "", "no piece"),
]
RUNS = [
    pytest.param(shape, args, hooks(calls), id=f"{shape}: {how}")
    for shape, args, calls, how in _RUNS
]


def _defined(namespace: dict[str, object]) -> dict[str, object]:
    """The names a module defines beside those it was given, a class's as its own names."""
    found: dict[str, object] = {}
    for name, value in namespace.items():
        if name.startswith("__") or name in NAMES or name == "E":
            continue
        if isinstance(value, type):
            value = {key: each for key, each in vars(value).items() if not key.startswith("__")}
        elif isinstance(value, types.ModuleType):
            continue
        found[name] = value
    return found
