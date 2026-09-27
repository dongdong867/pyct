"""`in` on a container Python searches by hash: a set, a frozenset, a dict or a dict's keys.

Python finds an element by its hash, tests identity, and compares with `==`
only on a hash match, so a tracked value that misses records nothing. pyct
compares the tracked value with each element instead, one `==` fork per
element, where that gives Python's own answer: every element is a plain
bool, int, float or str, a subclass of one that keeps its base's `==` and
hash, such as an IntEnum or a StrEnum, a tracked value, or None, and there
are at most `SEARCHED_MOST` of them. Such an element's `==` agrees with its
hash and never raises, so the search and Python's lookup cannot differ.
Any other container is Python's own lookup, and the lost condition is a
downgrade named `__contains__`.
"""

from __future__ import annotations

import math
import operator
from collections.abc import Iterable
from typing import TypeGuard

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Downgrade
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from pyct.core.values import own, plain

type Tracked = ConcolicBool | ConcolicInt | ConcolicFloat | ConcolicStr

# the tracked values a set or dict can hold, and the Python type each stands for
HASHABLE: dict[type, type] = {
    ConcolicBool: bool,
    ConcolicInt: int,
    ConcolicFloat: float,
    ConcolicStr: str,
}

# the containers Python searches by hash rather than element by element
_HASHED: tuple[type, ...] = (set, frozenset, dict, type({}.keys()))

# the most elements or keys a search compares one by one, for every set and dict, a literal
# display's included; past it Python answers, and the search is a downgrade. It bounds the
# forks one `in` records
SEARCHED_MOST = 100

# the plain types whose `==` pyct follows, each agreeing with its own hash
_PLAIN: tuple[type, ...] = (bool, int, float, str)

# what `_compared` answers for an element pyct does not compare
_NOT_COMPARED = object()


def tracked(item: object) -> TypeGuard[Tracked]:
    """Whether the item is a tracked value a set or a dict can hold."""
    return type(item) in HASHABLE


def hashed(container: object) -> type | None:
    """The type Python searches the container as by hash, or None for any other container.

    A subclass counts when it keeps its base's own `__contains__`, as an
    `OrderedDict` or a `Counter` does; one that defines its own is asked, as
    Python asks it.
    """
    kind = next((base for base in _HASHED if isinstance(container, base)), None)
    if kind is None or getattr(type(container), "__contains__", None) is not kind.__contains__:
        return None
    return kind


def looked_up(item: Tracked, container: object, kind: type) -> bool:
    """Whether the tracked item is in the container, as Python answers.

    The base type's own length and order are read, so a subclass's
    `__len__` or `__iter__` never runs where Python's `in` would not run it.
    """
    pairs = None
    if kind.__len__(container) <= SEARCHED_MOST:
        pairs = _pairs(kind.__iter__(container))
    if pairs is None:
        answer = own(operator.contains, container, _key(item))
        # recorded after Python answered, as a downgrade is, so a lookup that raises records
        # nothing
        item.sink.append(Downgrade(name="__contains__"))
        return answer
    return _searched(item, pairs)


def _pairs(elements: Iterable[object]) -> list[tuple[object, object]] | None:
    """Each element beside the value it is compared as, in the base type's order, or None when
    one of them is an element pyct does not compare. None is never equal and is left out."""
    pairs: list[tuple[object, object]] = []
    for element in elements:
        value = _compared(element)
        if value is _NOT_COMPARED:
            return None
        if element is not None:
            pairs.append((element, value))
    return pairs


def _compared(element: object) -> object:
    """The value an element is compared as: itself, or its base's plain value for a subclass
    that keeps its base's `==` and hash; `_NOT_COMPARED` for any other."""
    kind = type(element)
    if kind in HASHABLE or kind in _PLAIN or element is None:
        return element
    for base in _PLAIN:
        if isinstance(element, base) and kind.__eq__ is base.__eq__:
            return plain(element, base) if kind.__hash__ is base.__hash__ else _NOT_COMPARED
    return _NOT_COMPARED


def _searched(item: Tracked, pairs: list[tuple[object, object]]) -> bool:
    """Whether the item is one of the elements, as Python's lookup answers: identity first,
    then one `==` fork per element tried, until one holds."""
    return any(element is item or item == value for element, value in pairs)


def _key(item: Tracked) -> object:
    """What Python's own lookup is handed for the item: its plain value, and a NaN itself.

    A NaN equals nothing, so only its identity finds it, and a plain copy
    would be another object.
    """
    if isinstance(item, ConcolicFloat) and math.isnan(float.__float__(item)):
        return item
    return plain(item, HASHABLE[type(item)])
