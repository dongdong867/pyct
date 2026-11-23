"""The plain copy a loop in use takes of a tracked list C code changed makes a dict it holds plain
when each key's hash and equality are Python's own: defined in C or in a file of the standard
library, as an Enum member's, a date's, a Decimal's or a UUID's are. A dict keyed by a frozen
dataclass instance, whose hash dataclasses writes for the target, or by an object whose class
defines its own hash, is kept as it is. So a loop that changes such a record in place leaves the
copy of a plain one as it went in."""

from collections.abc import Mapping
from typing import Any, cast

import pytest

from pyct.binding.bind import bind
from pyct.core.entry.in_use import LoopInUse
from pyct.core.foundation.branch import FormulaDrop
from tests.unit.core.entry.test_in_use import using
from tests.unit.core.entry.test_in_use_going_in import lengthened
from tests.unit.core.entry.test_pieces import hooked

KEYED = """\
import dataclasses, datetime, decimal, enum, fractions, heapq, uuid
class Color(enum.Enum):
    RED = 1
class Base(enum.Enum):
    pass
class Shade(Base):
    DARK = 1
class Level(enum.IntEnum):
    LOW = 1
@dataclasses.dataclass(frozen=True)
class Point:
    x: int
class Own:
    def __hash__(self):
        return 1
K = {key}
def f(xs, p, s):
    heapq.heappush(xs, {{K: p}})
    t = 0
    for c in s:
        t += 1
        list.__getitem__(xs, 0)[K] = 0
    return t, xs
"""
# the loop's line and column in KEYED
LOOP = (20, 4)

COPIED = {
    "an Enum member": "Color.RED",
    "a member of an Enum the target derives": "Shade.DARK",
    "an IntEnum member": "Level.LOW",
    "a date": "datetime.date(2026, 1, 1)",
    "a Decimal": "decimal.Decimal('1.5')",
    "a Fraction": "fractions.Fraction(1, 3)",
    "a UUID": "uuid.UUID(int=1)",
    "a tuple of an Enum member and a str": "(Color.RED, 'a')",
    "a tuple of two members of one Enum": "(Color.RED, Color.RED)",
}
KEPT = {
    "a frozen dataclass instance": "Point(1)",
    "an object whose class defines its hash": "Own()",
    "a tuple of two such objects": "(Own(), Own())",
}


def keyed_run(key: str) -> tuple[object, object, list[FormulaDrop]]:
    """The record the formula read, the target's own record, and the drops, for a stale heap
    holding ``{key: p}`` whose record the loop changes in place."""
    seen: list[object] = []

    def reading(values: Mapping[str, object]) -> Mapping[str, object]:
        record = cast(dict[object, int], list.__getitem__(cast(list, values["xs"]), 0))
        seen.append(record)
        made = dict(lengthened(values))
        made["t"] = cast(int, made["t"]) + (next(iter(dict.values(record))) == 7) - 1
        return made

    f = hooked(KEYED.format(key=key))
    with using({LOOP: LoopInUse(("s", "t", "xs"), ("t",), reading)}) as sink:
        _, xs = cast(Any, f(*bind({"xs": [], "p": 7}, sink).values(), "ab"))
    (record,) = seen
    return record, list.__getitem__(xs, 0), [each for each in sink if type(each) is FormulaDrop]


@pytest.mark.parametrize("key", list(COPIED.values()), ids=list(COPIED))
def test_a_record_keyed_by_python_s_own_type_is_copied_plain(key: str) -> None:
    record, own, drops = keyed_run(key)

    assert record is not own
    assert type(record) is dict
    assert [type(each) for each in dict.values(record)] == [int]
    assert drops == []


@pytest.mark.parametrize("key", list(KEPT.values()), ids=list(KEPT))
def test_a_record_keyed_by_a_hash_the_target_s_class_has_is_kept_as_it_is(key: str) -> None:
    record, own, _ = keyed_run(key)

    assert record is own
