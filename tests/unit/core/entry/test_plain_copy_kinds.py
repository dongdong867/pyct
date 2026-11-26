"""The plain copy of a tracked list C code changed (`as_it_went_in`) makes each list, tuple, dict,
set and frozenset it holds plain: a subclass of tuple or frozenset, such as a namedtuple, as its own
type, made by its base type, and Python's own OrderedDict, defaultdict and Counter as their own
types, keeping their order and their default. Another subclass, and a tuple its base type cannot
make, is a plain copy of its base type. It runs none of the methods the target wrote for its
containers, nor a hash or equality it wrote for its keys, and a tracked dict C gave a key whose
hash the target's class defines has no copy."""

import collections
import time
from collections.abc import Callable, Mapping
from typing import Any, cast

import pytest

from pyct.core.entry.in_use import as_it_went_in
from pyct.core.entry.plain_copy import UnhashedKeysError
from tests.unit.core.entry.test_plain_copy import bound_and_changed, copied, pushed

# what the target pushes, made of ``p``, and what the copy of it is
REBUILT: dict[str, tuple[Callable[[Any], object], Callable[[Any], bool]]] = {
    "a namedtuple keeps its fields": (
        lambda p: collections.namedtuple("P", "cost name")(p, "task"),
        lambda held: (type(held).__name__, type(held.cost), held.name) == ("P", int, "task"),
    ),
    "an OrderedDict keeps its order": (
        lambda p: (lambda d: d.move_to_end("a", last=False) or d)(
            collections.OrderedDict(b=1, a=p)
        ),
        lambda held: (
            type(held) is collections.OrderedDict
            and list(held.items()) == [("a", 7), ("b", 1)]
            and type(held["a"]) is int
        ),
    ),
    "a defaultdict keeps its default": (
        lambda p: collections.defaultdict(list, a=p),
        lambda held: held.default_factory is list and type(held["a"]) is int,
    ),
    "a Counter stays a Counter": (
        lambda p: collections.Counter(a=p),
        lambda held: type(held) is collections.Counter and type(held["a"]) is int,
    ),
    "a set stays a set": (
        lambda p: {p, 1},
        lambda held: (
            type(held) is set and held == {7, 1} and {type(each) for each in held} == {int}
        ),
    ),
    "a frozenset stays a frozenset": (
        lambda p: frozenset([p]),
        lambda held: type(held) is frozenset and [type(each) for each in held] == [int],
    ),
    "a list subclass the target wrote is a plain list": (
        lambda p: (lambda xs: setattr(xs, "tag", "x") or xs)(type("L", (list,), {})([p])),
        lambda held: type(held) is list and [type(each) for each in held] == [int],
    ),
    "a set subclass the target wrote is a plain set": (
        lambda p: type("S", (set,), {})([p]),
        lambda held: type(held) is set and [type(each) for each in held] == [int],
    ),
    "a tuple subclass keeps its type and attributes": (
        lambda p: (lambda t: setattr(t, "tag", "x") or t)(type("T", (tuple,), {})((p,))),
        lambda held: (type(held).__name__, held.tag, type(held[0])) == ("T", "x", int),
    ),
    "a struct_time its base cannot make is a plain tuple": (
        lambda p: time.struct_time((p,) * 9),
        lambda held: type(held) is tuple and type(held[0]) is int,
    ),
    "an OrderedDict subclass the target wrote is a plain dict": (
        lambda p: type("O", (collections.OrderedDict,), {})(a=p),
        lambda held: type(held) is dict and held == {"a": 7} and type(held["a"]) is int,
    ),
}


@pytest.mark.parametrize(("made", "rebuilt"), list(REBUILT.values()), ids=list(REBUILT))
def test_the_plain_copy_makes_a_held_subclass_its_own_type_or_its_base_type(
    made: Callable[[Any], object], rebuilt: Callable[[Any], bool]
) -> None:
    args, sink = bound_and_changed({"xs": [], "p": 7}, pushed(made))

    xs = copied(args["xs"], sink)

    assert rebuilt(cast(list[object], xs)[0])


def test_the_struct_time_case_is_one_its_base_cannot_make() -> None:
    with pytest.raises(TypeError):
        cast(Any, tuple).__new__(time.struct_time, (0,) * 9)


LOGGED_HASH = """\
class K:
    logged = []
    def __hash__(self):
        K.logged.append(1)
        return 1
    def __eq__(self, other):
        return self is other
"""
# what the target defines and makes from a tracked int, by the class it writes
MADE = {
    "a dict that logs its item setting": """\
class H(dict):
    def __init__(self, *a, **k):
        self.history = []
        super().__init__(*a, **k)
    def __setitem__(self, k, v):
        self.history.append(k)
        dict.__setitem__(self, k, v)
def make(p):
    d = H()
    d['a'] = p
    return d
""",
    "a list whose clear clears its index": """\
class I(list):
    def __init__(self, items):
        super().__init__(items)
        self.index = {each: n for n, each in enumerate(items)}
    def clear(self):
        self.index.clear()
        list.clear(self)
def make(p):
    return I([p, 3])
""",
    "a dict whose copy is itself": """\
class S(dict):
    def __copy__(self):
        return self
def make(p):
    return S(a=p)
""",
    "a list kept sorted by its own append": """\
import bisect
class Sorted(list):
    def append(self, x):
        bisect.insort(self, x)
def make(p):
    xs = Sorted()
    list.extend(xs, [3, p])
    return xs
""",
    "a dict whose items logs": """\
class V(dict):
    logged = []
    def items(self):
        V.logged.append(1)
        return dict.items(self)
def make(p):
    return V(a=p)
""",
    "a dict keyed by an object whose hash logs": LOGGED_HASH
    + """\
def make(p):
    return {K(): p}
""",
    "a dict keyed by a tuple of an object whose hash logs": LOGGED_HASH
    + """\
def make(p):
    return {(K(), 1): p}
""",
    "a tuple whose __dict__ is a property that logs": """\
class D(tuple):
    logged = []
    @property
    def __dict__(self):
        D.logged.append(1)
        return {}
def make(p):
    return D((p,))
""",
    "a dict keyed by an object whose metaclass logs its reads": """\
class Meta(type):
    logged = []
    def __getattribute__(cls, name):
        Meta.logged.append(name)
        return type.__getattribute__(cls, name)
class Key(metaclass=Meta):
    pass
def make(p):
    return {Key(): p}
""",
    "a set of objects whose hash logs": LOGGED_HASH
    + """\
def make(p):
    return {K(), p}
""",
}


def kind(value: object) -> str:
    """Whether a value is tracked: a tracked int or str is not of Python's own type."""
    return "plain" if type(value) in (int, str) else "tracked"


def state(held: object, namespace: Mapping[str, object]) -> object:
    """The target's held object, read through its base type, with what its attributes hold and
    how many calls the target's classes logged."""
    if isinstance(held, dict):
        items = [each for pair in dict.items(held) for each in pair]
    elif isinstance(held, set):
        items = sorted(map(kind, set.__iter__(held)))
    elif isinstance(held, tuple):
        items = list(tuple.__iter__(held))
    else:
        items = list(list.__iter__(cast(list, held)))
    attributes = {name: repr(each) for name, each in getattr(held, "__dict__", {}).items()}
    logged = sum(
        len(getattr(each, "logged", ())) for each in namespace.values() if isinstance(each, type)
    )
    return type(held).__name__, [kind(each) for each in items], attributes, logged


def defined(source: str) -> dict[str, Any]:
    """The names the target's source defines."""
    namespace: dict[str, Any] = {}
    exec(source, namespace)  # noqa: S102 - one of the sources above
    return namespace


def held_after(made: str, *, copying: bool) -> object:
    """The state of the target's held object once a stale heap holds it, with a copy of the heap
    taken or none."""
    namespace = defined(made)
    args, sink = bound_and_changed({"xs": [], "p": 7}, pushed(namespace["make"]))
    if copying:
        copied(args["xs"], sink)
    return state(list.__getitem__(cast(list[object], args["xs"]), 0), namespace)


@pytest.mark.parametrize("made", list(MADE.values()), ids=list(MADE))
def test_the_copy_leaves_the_target_s_objects_as_they_were(made: str) -> None:
    assert held_after(made, copying=True) == held_after(made, copying=False)


def test_a_tracked_dict_c_gave_such_a_key_has_no_copy() -> None:
    namespace = defined(LOGGED_HASH)
    args, sink = bound_and_changed(
        {"d": {"a": 1}}, lambda args: dict.__setitem__(args["d"], namespace["K"](), 9)
    )
    hashed = len(namespace["K"].logged)

    with pytest.raises(UnhashedKeysError):
        as_it_went_in(args["d"])

    assert (len(namespace["K"].logged), sink) == (hashed, [])
