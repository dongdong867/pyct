"""The plain copy a loop in use takes of a tracked list or dict C code changed runs none of the
methods the target wrote for its containers or keys: it reads each container through its base type
and each class through `type`'s own descriptors, copies a container class the target wrote as its
plain base type, and keeps as it is a dict or set with a key whose hash the target's class defines.
The target's own objects end as the loop as written leaves them, and the run records what the loop
as written records."""

from collections.abc import Mapping
from typing import Any, cast

import pytest

from pyct.binding.bind import bind
from pyct.core.entry.in_use import LoopInUse
from pyct.core.foundation.branch import Branch, Downgrade, Fact
from tests.unit.core.entry.test_in_use import using
from tests.unit.core.entry.test_in_use_going_in import lengthened
from tests.unit.core.entry.test_pieces import hooked

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
HELD = """\
import heapq
def f(xs, p, s):
    heapq.heappush(xs, make(p))
    t = 0
    for c in s:
        t += 1
        len(xs)
    return t, xs
"""


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


def run(made: str, in_use: bool) -> tuple[object, list[Branch | Fact | Downgrade], int]:
    """The target's held object after a call, what the call recorded, and how many times the
    formula ran, with HELD's loop followed as written or in use."""
    calls: list[object] = []

    def counting(values: Mapping[str, object]) -> Mapping[str, object]:
        calls.append(values["xs"])
        return lengthened(values)

    loop = (made.count("\n") + 5, 4)
    loops = {loop: LoopInUse(("s", "t", "xs"), ("t",), counting)} if in_use else {}
    f = hooked(made + HELD)
    with using(loops) as sink:
        _, xs = cast(Any, f(*bind({"xs": [], "p": 7}, sink).values(), "ab"))
        held = state(list.__getitem__(xs, 0), f.__globals__)
    recorded = [each for each in sink if isinstance(each, Branch | Fact | Downgrade)]
    return held, recorded, len(calls)


@pytest.mark.parametrize("made", list(MADE.values()), ids=list(MADE))
def test_the_copy_leaves_the_target_s_objects_as_the_loop_as_written_does(made: str) -> None:
    written, written_records, _ = run(made, in_use=False)
    in_use, in_use_records, calls = run(made, in_use=True)

    assert calls == 1
    assert in_use == written
    assert in_use_records == written_records


KEYED = (
    LOGGED_HASH
    + """\
def f(d, s):
    dict.__setitem__(d, K(), 9)
    t = 0
    for c in s:
        t += 1
        len(d)
    return t, d
"""
)


def test_a_tracked_dict_c_gave_such_a_key_has_no_copy_and_its_run_is_followed_as_written() -> None:
    seen: list[tuple[object, int]] = []
    calls: list[object] = []

    def counting(values: Mapping[str, object]) -> Mapping[str, object]:
        calls.append(values)
        return lengthened(values)

    loop = (LOGGED_HASH.count("\n") + 4, 4)
    for loops in ({}, {loop: LoopInUse(("d", "s", "t"), ("t",), counting)}):
        f = hooked(KEYED)
        with using(loops) as sink:
            f(bind({"d": {"a": 1}}, sink)["d"], "ab")
        hashed = cast(Any, f.__globals__["K"]).logged
        seen.append(
            ([each for each in sink if isinstance(each, Branch | Fact | Downgrade)], len(hashed))
        )

    written, in_use = seen
    assert calls == []
    assert in_use == written
