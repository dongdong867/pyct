"""A tracked str, list, dict or range, and a tracked dict's views, refuse every attribute set and
delete their plain value refuses, in Python's own words, and keep the fields pyct wrote
(tracked-numbers-refuse-attributes-on-a-plain-number)."""

import inspect
import re
from collections.abc import Callable
from pathlib import Path

import pytest

import pyct
from pyct.core.bools import ConcolicBool
from pyct.core.branch import SinkItem
from pyct.core.dict_state import DictState
from pyct.core.dict_views import _View
from pyct.core.dicts import ConcolicDict
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.list_state import ListState
from pyct.core.lists import ConcolicList
from pyct.core.ranges import ConcolicRange, ranged
from pyct.core.strs import ConcolicStr, one_character
from pyct.core.values import raised_by_target

# how each tracked value is built on a sink, beside the plain value Python is asked about, and
# the field pyct keeps on it that must survive every refusal
_BUILT: dict[str, tuple[Callable[[list[SinkItem]], object], object, str]] = {
    "str": (lambda sink: ConcolicStr.made("ab", "s", sink), "ab", "expression"),
    "one character": (lambda sink: one_character("a", "s", sink), "a", "single"),
    "list": (lambda sink: ConcolicList.made([1], "xs", sink), [1], "shadow"),
    "dict": (lambda sink: ConcolicDict.made({"a": 1}, "d", sink), {"a": 1}, "settled"),
    "range": (lambda sink: ranged(ConcolicInt.made(3, "n", sink)), range(3), "held"),
    "keys": (
        lambda sink: ConcolicDict.made({"a": 1}, "d", sink).keys(),
        {"a": 1}.keys(),
        "_mapping",
    ),
    "values": (
        lambda sink: ConcolicDict.made({"a": 1}, "d", sink).values(),
        {"a": 1}.values(),
        "_mapping",
    ),
    "items": (
        lambda sink: ConcolicDict.made({"a": 1}, "d", sink).items(),
        {"a": 1}.items(),
        "_mapping",
    ),
}

# a set and a delete of each kind of name: a new one, pyct's own, and the plumbing Python reads
# a value's attributes through
_SET_OR_DELETE: dict[str, Callable[[object], object]] = {
    "set a new name": lambda x: setattr(x, "foo", 1),
    "delete a new name": lambda x: delattr(x, "foo"),
    "set the sink": lambda x: setattr(x, "sink", None),
    "delete the sink": lambda x: delattr(x, "sink"),
    "set the expression": lambda x: setattr(x, "expression", None),
    "set the shadow": lambda x: setattr(x, "shadow", []),
    "set held": lambda x: setattr(x, "held", range(9)),
    "set the mapping": lambda x: setattr(x, "_mapping", None),
    "delete the mapping": lambda x: delattr(x, "_mapping"),
    "set the dict": lambda x: setattr(x, "__dict__", {}),
}


def _raised(call: Callable[[], object]) -> BaseException:
    """What a call raises, so a tracked value's raise is read beside a plain value's."""
    with pytest.raises(Exception) as raised:
        call()
    return raised.value


@pytest.mark.parametrize("change", _SET_OR_DELETE.values(), ids=_SET_OR_DELETE)
@pytest.mark.parametrize("built", _BUILT.values(), ids=_BUILT)
def test_a_set_or_a_delete_raises_what_the_plain_value_raises(
    built: tuple[Callable[[list[SinkItem]], object], object, str],
    change: Callable[[object], object],
) -> None:
    build, plain, field = built
    sink: list[SinkItem] = []
    tracked = build(sink)
    kept = getattr(tracked, field)
    before = list(sink)

    raised = _raised(lambda: change(tracked))
    expected = _raised(lambda: change(plain))

    assert (type(raised), str(raised)) == (type(expected), str(expected))
    assert raised_by_target(raised)
    # pyct's own field is where it wrote it, and the refusal recorded nothing
    assert getattr(tracked, field) is kept
    assert sink == before


def test_a_range_s_bounds_stay_read_only_as_python_s_are() -> None:
    tracked = ranged(ConcolicInt.made(3, "n", []))

    raised = _raised(lambda: setattr(tracked, "start", 1))
    expected = _raised(lambda: setattr(range(3), "start", 1))

    assert (type(raised), str(raised)) == (type(expected), str(expected))


# the classes whose fields pyct writes past their refusal, and every way it writes one: by key
# into the value's `__dict__`, a local named `fields` holding it, or object's own set, which the
# range's `made` holds as `write`
_REFUSING = (
    ConcolicInt,
    ConcolicBool,
    ConcolicFloat,
    ConcolicStr,
    ListState,
    DictState,
    ConcolicRange,
    _View,
)
_WRITES = re.compile(
    r'(?:__dict__|\bfields)\["(\w+)"\]|(?:object\.__setattr__|\bwrite)\(\w+, "(\w+)"'
)
_SOURCE = Path(pyct.__file__).parent


def _fields() -> set[str]:
    """Each name a refusing class annotates or keeps a slot for, its bases' among them."""
    names: set[str] = set()
    for cls in _REFUSING:
        for kind in cls.__mro__:
            names |= set(inspect.get_annotations(kind))
            names |= set(vars(kind).get("__slots__", ()))
    return names


def test_each_field_pyct_writes_by_name_is_one_a_class_declares() -> None:
    # a write by key escapes the type checker, so a misspelled name is caught here instead
    written = {
        (path.relative_to(_SOURCE).as_posix(), name)
        for path in _SOURCE.rglob("*.py")
        for match in _WRITES.finditer(path.read_text())
        for name in match.groups()
        if name is not None and not name.startswith("__")
    }

    assert len(written) > 40
    assert {entry for entry in written if entry[1] not in _fields()} == set()
