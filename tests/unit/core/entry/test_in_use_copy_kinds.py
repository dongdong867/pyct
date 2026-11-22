"""The plain copy a loop in use takes of a tracked list C code changed rebuilds each subclass of a
list, tuple, dict, set or frozenset it holds as its own type, with its items plain: a namedtuple
keeps its fields, an OrderedDict its order and a defaultdict its default. A subclass its own copy
cannot rebuild is a plain copy of its base type."""

import collections
import time
from collections.abc import Callable, Mapping
from typing import Any, cast

import pytest

from tests.unit.core.entry.test_in_use_going_in import (
    HEAP_OF_HELD,
    lengthened,
    written_and_in_use,
)

# what HEAP_OF_HELD's target pushes, and what the copy of it is
REBUILT: dict[str, tuple[str, Callable[[Any], bool]]] = {
    "a namedtuple keeps its fields": (
        "collections.namedtuple('P', 'cost name')(p, 'task')",
        lambda held: (type(held).__name__, type(held.cost), held.name) == ("P", int, "task"),
    ),
    "an OrderedDict keeps its order": (
        "(lambda d: d.move_to_end('a', last=False) or d)(collections.OrderedDict(b=1, a=p))",
        lambda held: (
            type(held) is collections.OrderedDict
            and list(held.items()) == [("a", 7), ("b", 1)]
            and type(held["a"]) is int
        ),
    ),
    "a defaultdict keeps its default": (
        "collections.defaultdict(list, a=p)",
        lambda held: held.default_factory is list and type(held["a"]) is int,
    ),
    "a Counter stays a Counter": (
        "collections.Counter(a=p)",
        lambda held: type(held) is collections.Counter and type(held["a"]) is int,
    ),
    "a set stays a set": (
        "{p, 1}",
        lambda held: (
            type(held) is set and held == {7, 1} and {type(each) for each in held} == {int}
        ),
    ),
    "a frozenset stays a frozenset": (
        "frozenset([p])",
        lambda held: type(held) is frozenset and [type(each) for each in held] == [int],
    ),
    "a list subclass keeps its type and attributes": (
        "(lambda xs: setattr(xs, 'tag', 'x') or xs)(type('L', (list,), {})([p]))",
        lambda held: (type(held).__name__, held.tag, type(held[0])) == ("L", "x", int),
    ),
    "a tuple subclass keeps its type and attributes": (
        "(lambda t: setattr(t, 'tag', 'x') or t)(type('T', (tuple,), {})((p,)))",
        lambda held: (type(held).__name__, held.tag, type(held[0])) == ("T", "x", int),
    ),
    "a struct_time its base cannot make is a plain tuple": (
        "__import__('time').struct_time((p,) * 9)",
        lambda held: type(held) is tuple and type(held[0]) is int,
    ),
    "an OrderedDict subclass its copy cannot make is a plain dict": (
        "(lambda d: d.update(a=p) or d)("
        "type('O', (collections.OrderedDict,), {'__init__': lambda self, x: None})(0))",
        lambda held: type(held) is dict and held == {"a": 7} and type(held["a"]) is int,
    ),
}


@pytest.mark.parametrize(("held", "rebuilt"), list(REBUILT.values()), ids=list(REBUILT))
def test_the_plain_copy_rebuilds_a_held_subclass_as_its_own_type(
    held: str, rebuilt: Callable[[Any], bool]
) -> None:
    seen: list[object] = []

    def keeping(values: Mapping[str, object]) -> Mapping[str, object]:
        seen.append(cast(list[object], values["xs"])[0])
        return lengthened(values)

    source = HEAP_OF_HELD.format(held=held)
    written, in_use, calls = written_and_in_use(source, {"xs": [], "p": 7}, (5, 4), keeping)

    (copied,) = seen
    assert (calls, in_use) == (1, written)
    assert rebuilt(copied)


def test_the_struct_time_case_is_one_its_base_cannot_make() -> None:
    with pytest.raises(TypeError):
        cast(Any, tuple).__new__(time.struct_time, (0,) * 9)
