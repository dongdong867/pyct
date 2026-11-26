"""The plain copy a loss site in use takes of a tracked list or dict going in whose form no longer
describes it (`pyct.core.entry.in_use.as_it_went_in`), made with none of the methods the target
wrote for its containers, and no hash or equality it wrote for its keys, run.

The copy is a new plain list or dict. Each list, tuple, dict, set and frozenset it holds, at every
depth, a subclass of one included, that is tracked or holds a tracked value at some depth is a new
one too, made once, so a list that holds itself holds its copy; each other one is the one it holds,
and so is any other object, such as a dataclass instance. Each tracked int, float, str and bool in
them, a dict's keys included, is its plain value. What each new one is:

- a subclass of tuple or frozenset, such as a namedtuple, is of its own type, made by its base
  type's ``__new__`` as a namedtuple's ``_make`` makes one, with the attributes its ``__dict__``
  holds, read through Python's own descriptor, none when its class replaces that; one its base
  cannot make, such as a struct_time, is a plain one of its base;
- a subclass of list, dict or set that Python itself defines (`_python_s`: an OrderedDict, a
  defaultdict, a Counter) is of its own type, made by `copy.copy`, emptied and refilled by its
  own methods, so an OrderedDict keeps its order and a defaultdict its default;
- any other subclass of list, dict or set, one the target wrote, is a plain one of its base type.

Making a dict, set or frozenset hashes its keys. A key's hash and equality are Python's own when
each is written in C or lies in a file of the standard library, as an Enum member's, a date's, a
Decimal's, a Fraction's and a UUID's are (`_python_s_hash`). A dict, set or frozenset with a key
whose are not, as a frozen dataclass instance's, which dataclasses writes for the class, or an
object's whose class defines its own, is kept as it is (`_hashes_alone`); a tracked dict that
holds such a key has no copy (`UnhashedKeysError`). Each container is read in C through its base
type, and one Python itself defines through its own methods, and each class through `type`'s own
descriptors, so no method the target wrote for its containers runs, nor a hash or equality it
wrote for its keys, and nothing is recorded. A standard-library hash that calls the key's own
methods, as `collections.abc.Set._hash` calls `__len__` and `__iter__`, runs them, and what they
record is recorded. The walk keeps its own stack, so no depth reaches Python's recursion limit.
"""

from __future__ import annotations

import builtins
import collections
import copy
import types
from typing import Any, NamedTuple, cast

from pyct.core.dicts.dict_state import DictState
from pyct.core.dicts.dicts import ConcolicDict
from pyct.core.foundation.standard_library import standard
from pyct.core.lists.list_state import ListState, plain
from pyct.core.lists.lists import ConcolicList
from pyct.core.numbers.bools import ConcolicBool
from pyct.core.numbers.floats import ConcolicFloat
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr

# the tracked values a plain copy makes plain
SCALARS = frozenset({ConcolicInt, ConcolicFloat, ConcolicStr, ConcolicBool})

# the containers a plain copy walks, a subclass of one included, and the ones among them whose
# copy is made empty and then filled
_HOLDERS = (list, tuple, dict, set, frozenset)
_FILLED = (list, dict, set)
# Python's own containers that are read and made with their own type: no subclass
_OWN = frozenset({list, tuple, set, frozenset})
# the base type of Python's own containers and of pyct's tracked ones, whose copy is of it
_BASES: dict[type, type] = {kind: kind for kind in _HOLDERS} | {
    ConcolicList: list,
    ConcolicDict: dict,
}
# the containers with no keys a plain copy hashes
_KEYLESS = frozenset({list, tuple, ConcolicList})
# the modules whose classes' methods are Python's own
_PYTHON_S = (builtins, collections)
# the keys hashed with Python's own code or pyct's, known without a look at their type's classes
_HASHED = frozenset({int, float, complex, str, bytes, bool, type(None), *SCALARS})
# the kinds of callables written in C
_IN_C = frozenset(
    {
        types.WrapperDescriptorType,
        types.MethodDescriptorType,
        types.BuiltinFunctionType,
        types.MethodWrapperType,
    }
)
# a class's classes, its own namespace and its name, read as `type` reads them, so no
# metaclass's code runs
_MRO = type.__dict__["__mro__"].__get__
_NAMESPACE = type.__dict__["__dict__"].__get__
_NAME = type.__dict__["__name__"].__get__
# whether each key type's hash and equality are Python's own (`_python_s_hash`), by the type's
# id, beside the type, which the entry keeps alive so its id names no other
_HASHES: dict[int, tuple[type, bool]] = {}


class UnhashedKeysError(Exception):
    """A tracked dict holds a key whose hash or equality is the target's code, so it has no
    plain copy."""


class _Node(NamedTuple):
    """A container a plain copy reached: the items it holds, a dict's keys before their values,
    the containers among them, whether it is tracked or holds a tracked int, float, str or bool,
    and whether its keys hash with Python's own or pyct's code alone."""

    container: object
    items: list[object]
    inner: list[object]
    tracked: bool
    hashed: bool


def plain_copy(value: ListState | DictState) -> object:
    """A tracked list or dict as a new plain one, as the module says."""
    reached = _reached(value)
    copies = _copies(reached)
    if id(value) not in copies:
        raise UnhashedKeysError
    filled = [key for key in copies if issubclass(type(reached[key].container), _FILLED)]
    made: dict[int, object] = {key: _empty(reached[key].container) for key in filled}
    for key in _frozen_in_order(reached, copies):
        node = reached[key]
        made[key] = _frozen(cast(tuple | frozenset, node.container), _mapped(node.items, made))
    for key in filled:
        _fill(made[key], _mapped(reached[key].items, made))
    return made[id(value)]


def _reached(value: object) -> dict[int, _Node]:
    """Each list, tuple, dict, set and frozenset the value is or holds, at every depth, by id."""
    reached: dict[int, _Node] = {}
    stack = [value]
    while stack:
        each = stack.pop()
        if id(each) in reached:
            continue
        kind = type(each)
        items = _held(each)
        inner: list[object] = [item for item in items if issubclass(type(item), _HOLDERS)]
        tracked = issubclass(kind, (ListState, DictState))
        tracked = tracked or any(type(item) in SCALARS for item in items)
        reached[id(each)] = _Node(each, items, inner, tracked, _hashes_alone(kind, items))
        stack.extend(inner)
    return reached


def _held(value: object) -> list[object]:
    """The items a container holds, a dict's keys before their values, read in C with no key
    hashed: a tracked list's through its storage, a dict Python itself defines through its own
    ``items``, so an OrderedDict's come in its order, any other dict, a tracked one's included,
    through `dict.items`, and another container through its base type's iterator."""
    kind = type(value)
    if kind in _OWN:
        return list(cast(list, value))
    if issubclass(kind, ListState):
        return cast(ListState, value).storage()
    if issubclass(kind, DictState):
        pairs = dict.items(cast(DictState, value))
    elif issubclass(kind, dict):
        pairs = (kind.items if _python_s(kind) else dict.items)(cast(dict, value))
    else:
        return list(cast(Any, _base(kind)).__iter__(value))
    return [each for pair in pairs for each in pair]


def _base(kind: type) -> type:
    """Which of list, tuple, dict, set and frozenset the container's type is."""
    return _BASES.get(kind) or next(base for base in _HOLDERS if issubclass(kind, base))


def _python_s(kind: type) -> bool:
    """Whether Python itself defines the class and each class it derives from: each is the very
    class `builtins` or `collections` names by its name, whatever its ``__module__`` says."""
    return all(
        any(getattr(module, _NAME(each), None) is each for module in _PYTHON_S)
        for each in _MRO(kind)
    )


def _hashes_alone(kind: type, items: list[object]) -> bool:
    """Whether making a container of the type with the items hashes and compares its keys with
    Python's own code or pyct's alone: each key's type is one of `_HASHED` or has Python's own
    hash and equality (`_python_s_hash`), and so does each item of a tuple or frozenset."""
    if kind in _KEYLESS:
        return True
    if issubclass(kind, dict):
        stack = items[::2]
    elif issubclass(kind, set | frozenset):
        stack = list(items)
    else:
        return True
    while stack:
        key = type(each := stack.pop())
        if key in _HASHED:
            continue
        if not _python_s_hash(key):
            return False
        if issubclass(key, tuple | frozenset):
            stack.extend(_held(each))
    return True


def _python_s_hash(kind: type) -> bool:
    """Whether the type's hash and equality are Python's own: each, found where Python finds
    it among the type's classes, is written in C or is a function whose code lies in a file of
    the standard library (`standard`). An Enum member's, a date's, a Decimal's and a UUID's are;
    a frozen dataclass's, which dataclasses writes for the class, and those of a class that
    defines its own, are not."""
    known = _HASHES.get(id(kind))
    if known is not None:
        return known[1]
    found = all(_python_s_code(_found(kind, name)) for name in ("__hash__", "__eq__"))
    _HASHES[id(kind)] = (kind, found)
    return found


def _found(kind: type, name: str) -> object:
    """What the type's classes hold under the name, the first that holds it, read through each
    class's own namespace, or None when none does."""
    for each in _MRO(kind):
        namespace = _NAMESPACE(each)
        if name in namespace:
            return namespace[name]
    return None


def _python_s_code(method: object) -> bool:
    """Whether the method is written in C or is a function whose code lies in a file of the
    standard library."""
    if type(method) in _IN_C:
        return True
    return type(method) is types.FunctionType and standard(method.__code__.co_filename)


def _copies(reached: dict[int, _Node]) -> set[int]:
    """The id of each container reached that is tracked or holds a tracked value at some depth,
    and whose keys hash with Python's own or pyct's code alone."""
    # the containers that hold each container, among those that are neither tracked nor hold a
    # tracked int, float, str or bool
    above: dict[int, list[int]] = {}
    for key, node in reached.items():
        if not node.tracked:
            for each in node.inner:
                above.setdefault(id(each), []).append(key)
    copies = {key for key, node in reached.items() if node.tracked}
    marked = [key for key in copies if key in above]
    while marked:
        for each in above.get(marked.pop(), ()):
            if each not in copies:
                copies.add(each)
                marked.append(each)
    return {key for key in copies if reached[key].hashed}


def _frozen_in_order(reached: dict[int, _Node], copies: set[int]) -> list[int]:
    """The id of each tuple and frozenset to copy, each after the tuples and frozensets it
    holds: Python code makes neither hold itself but through a list, dict or set."""
    order: list[int] = []
    entered: set[int] = set()
    frozen = [key for key in copies if not issubclass(type(reached[key].container), _FILLED)]
    stack = [(key, False) for key in frozen]
    while stack:
        key, done = stack.pop()
        if done:
            order.append(key)
        elif key not in entered:
            entered.add(key)
            stack.append((key, True))
            held = (id(each) for each in reached[key].inner if not issubclass(type(each), _FILLED))
            stack.extend((each, False) for each in held if each in copies)
    return order


def _empty(value: object) -> object:
    """A new empty list, dict or set for a container that is one: of its own type when it is a
    subclass Python itself defines, made by `copy.copy` and emptied by its own ``clear``, so a
    defaultdict keeps its default; else, a tracked one's included, a plain one of its base type."""
    kind = type(value)
    base = _base(kind)
    if kind in _BASES or not _python_s(kind):
        return base()
    made = copy.copy(value)
    cast(Any, made).clear()
    return made


def _fill(copied: object, items: list[object]) -> None:
    """Fill a new empty list, dict or set with the items, a dict's keys before their values,
    a subclass of dict through its own item setting, so an OrderedDict keeps their order."""
    if type(copied) is dict:
        dict.update(copied, zip(items[::2], items[1::2], strict=True))
    elif isinstance(copied, dict):
        for key, each in zip(items[::2], items[1::2], strict=True):
            copied[key] = each
    elif isinstance(copied, list):
        list.extend(copied, items)
    else:
        set.update(cast(set, copied), items)


def _frozen(value: tuple | frozenset, items: list[object]) -> object:
    """A new tuple or frozenset with the items. A subclass's is of its own type, made by its
    base type's ``__new__``, with the attributes its ``__dict__`` holds, read through the C
    descriptor Python gives its class, none when its class replaces that; Python's own, and one
    its base cannot make, a plain one of its base."""
    kind = type(value)
    if kind in _OWN:
        return kind(items)
    base = tuple if issubclass(kind, tuple) else frozenset
    try:
        made = cast(Any, base).__new__(kind, items)
    except Exception:
        return base(items)
    slot = _found(kind, "__dict__")
    if type(slot) is types.GetSetDescriptorType:
        slot.__get__(made).update(slot.__get__(value))
    return made


def _mapped(items: list[object], made: dict[int, object]) -> list[object]:
    """The items of a plain copy: each container's copy when it has one, else the item plain."""
    return [
        made.get(id(each), each) if issubclass(type(each), _HOLDERS) else plain(each)
        for each in items
    ]
