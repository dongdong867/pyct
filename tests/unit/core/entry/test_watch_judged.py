"""Which calls the watch judges: a call into the target's package is not, and any other is,
reached through what wraps it, read without running the target's code."""

import builtins
import functools
import types
from collections.abc import Callable
from typing import Any

import pytest

from pyct.core.entry import watch
from pyct.core.entry.watch import answer, called, given
from pyct.core.foundation import escapes
from pyct.core.foundation.branch import SinkItem
from pyct.core.numbers.ints import ConcolicInt
from pyct.intercept.wrap import bound_builtins
from tests.unit.core.entry.test_watch import lost, tracked


@pytest.fixture(autouse=True)
def no_call_open() -> None:
    watch.forget()


def _in_the_package(source: str, name: str) -> Any:
    """What ``source`` defines under ``name``, run as a module of the target's package runs:
    with the builtins pyct binds."""
    space: dict[str, Any] = {"__builtins__": bound_builtins(), "__name__": "shop.helper"}
    exec(compile(source, "shop/helper.py", "exec"), space)
    return space[name]


# a callee that loses its argument: bin, run inside it unwatched, gives back a plain str
IS_BIG = "def is_big(v):\n    return bin(v).count('1') > 1\n"
HELPER = """
import functools
import types

def is_big(v):
    return bin(v).count('1') > 1

class Sizes:
    def is_big(self, v):
        return bin(v).count('1') > 1

    def __call__(self, v):
        return bin(v).count('1') > 1

partial = functools.partial(is_big)

class Retry:
    def __init__(self, fn):
        functools.update_wrapper(self, fn)

    def __call__(self, v):
        return bin(v).count('1') > 1

retry = Retry(bin)

class Fib:
    @functools.cache
    def __call__(self, v):
        return bin(v).count('1') > 1

fib = Fib()

class Child(Sizes):
    pass

class Static:
    __call__ = staticmethod(is_big)

class Classwide:
    @classmethod
    def __call__(cls, v):
        return bin(v).count('1') > 1

class Kinds:
    @functools.singledispatchmethod
    def is_big(self, v):
        return bin(v).count('1') > 1
"""


def _decorated(function: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """``function`` behind a wrapper of a decorator outside the target's package, as a library
    writes one."""

    @functools.wraps(function)
    def wrapper(value: Any) -> Any:
        return function(value)

    return wrapper


class _Answers:
    """A callable outside the target's package whose every other attribute is a function of
    the package's, as a mock's would be."""

    def __call__(self, value: object) -> int:
        return bin(value).count("1")  # pyrefly: ignore[bad-argument-type]

    def __getattr__(self, name: str) -> object:
        return _in_the_package(HELPER, "is_big")


@pytest.mark.parametrize(
    "callee",
    [
        pytest.param(lambda: _in_the_package(HELPER, "is_big"), id="a function"),
        pytest.param(lambda: _in_the_package(HELPER, "Sizes")().is_big, id="a bound method"),
        pytest.param(lambda: _in_the_package(HELPER, "partial"), id="a partial"),
        pytest.param(lambda: _in_the_package(HELPER, "Sizes")(), id="an object's __call__"),
        pytest.param(
            lambda: _decorated(_in_the_package(HELPER, "is_big")), id="a library's decorator"
        ),
        pytest.param(
            lambda: functools.lru_cache(_in_the_package(HELPER, "is_big")), id="lru_cache"
        ),
        pytest.param(
            lambda: functools.singledispatch(_in_the_package(HELPER, "is_big")),
            id="singledispatch",
        ),
        pytest.param(
            lambda: _in_the_package(HELPER, "retry"), id="an object that wraps a C function"
        ),
        pytest.param(lambda: _in_the_package(HELPER, "fib"), id="a cached __call__"),
        pytest.param(lambda: _in_the_package(HELPER, "Child")(), id="an inherited __call__"),
        pytest.param(lambda: _in_the_package(HELPER, "Static")(), id="a static __call__"),
        pytest.param(lambda: _in_the_package(HELPER, "Classwide")(), id="a class's __call__"),
        pytest.param(
            lambda: _in_the_package(HELPER, "Kinds")().is_big, id="a singledispatchmethod"
        ),
        pytest.param(lambda: _chained(watch._MOST_WRAPPED), id="the most wrappers read"),
    ],
)
def test_a_call_into_the_target_s_package_is_not_judged(callee: Callable[[], Any]) -> None:
    sink: list[SinkItem] = []
    function = callee()

    answer(called(function)(given(tracked(3, sink))), "is_big")

    assert lost(sink) == []


class _Dispatching(functools.singledispatchmethod):
    """A subclass of the target's, whose namespace the watch does not read."""


def test_a_singledispatchmethod_s_method_is_read_from_what_functools_writes() -> None:
    method = _in_the_package(HELPER, "is_big")

    held = types.SimpleNamespace(_unbound=functools.singledispatchmethod(method))
    subclassed = types.SimpleNamespace(_unbound=_Dispatching(method))

    assert watch._dispatched(held) is method
    assert watch._dispatched(subclassed) is None
    assert watch._dispatched(types.SimpleNamespace()) is None


class _Guarded:
    """A callable outside the target's package whose ``__dict__`` raises, as a proxy's may."""

    def __call__(self, value: object) -> int:
        return bin(value).count("1")  # pyrefly: ignore[bad-argument-type]

    @property
    def __dict__(self) -> dict[str, object]:  # pyrefly: ignore[bad-override]
        raise RuntimeError("no dict")


def test_a_callable_s_own_dict_is_not_read() -> None:
    sink: list[SinkItem] = []

    answer(called(_Guarded())(given(tracked(3, sink))), "guarded")

    assert [name for name, _ in lost(sink)] == ["guarded"]


def test_a_callable_s_own_attribute_lookup_does_not_place_it() -> None:
    sink: list[SinkItem] = []

    answer(called(_Answers())(given(tracked(3, sink))), "answers")

    assert [name for name, _ in lost(sink)] == ["answers"]


@pytest.mark.parametrize(
    ("name", "replacement", "callee"),
    [
        ("len", lambda _value: 0, lambda: _in_the_package(HELPER, "is_big")),
        ("isinstance", lambda _value, _kind: False, lambda: _in_the_package(HELPER, "is_big")),
        ("staticmethod", lambda function: function, lambda: _in_the_package(HELPER, "Static")()),
    ],
    ids=["len", "isinstance", "staticmethod"],
)
def test_a_call_into_the_target_s_package_is_not_judged_while_a_builtin_is_replaced(
    name: str, replacement: object, callee: Callable[[], Any]
) -> None:
    sink: list[SinkItem] = []
    function = callee()
    python_own = getattr(builtins, name)
    # the target puts a function of its own in `builtins`, which its modules then find
    setattr(builtins, name, replacement)
    try:
        answer(called(function)(given(tracked(3, sink))), "is_big")
    finally:
        setattr(builtins, name, python_own)

    assert lost(sink) == []


def test_a_dict_argument_is_read_while_dict_is_replaced() -> None:
    sink: list[SinkItem] = []
    python_dict = builtins.dict
    builtins.dict = list  # pyrefly: ignore[bad-assignment]
    try:
        answer(called(str)(given({"k": tracked(3, sink)})), "str")
    finally:
        builtins.dict = python_dict

    assert [name for name, _ in lost(sink)] == ["str"]


def _counted(value: object) -> dict[str, str]:
    """A function outside the target's package that answers a plain dict."""
    return {"bits": bin(value)}  # pyrefly: ignore[bad-argument-type]


def test_a_dict_answer_is_plain_while_dict_is_replaced() -> None:
    sink: list[SinkItem] = []
    python_dict = builtins.dict
    builtins.dict = list  # pyrefly: ignore[bad-assignment]
    try:
        answer(called(_counted)(given(tracked(3, sink))), "counted")
    finally:
        builtins.dict = python_dict

    assert [name for name, _ in lost(sink)] == ["counted"]


class _Disguised(dict[str, object]):
    """A builtins mapping whose ``__class__`` raises, as a function's globals may hold one."""

    @property
    def __class__(self) -> type:  # pyrefly: ignore[bad-override]
        raise RuntimeError("no class")


def test_a_function_s_builtins_are_told_without_reading_them() -> None:
    sink: list[SinkItem] = []
    held = _Disguised(vars(builtins))
    function = types.FunctionType(_cycling.__code__, {"__builtins__": held})

    answer(called(function)(given(tracked(3, sink))), "disguised")

    assert [name for name, _ in lost(sink)] == ["disguised"]


def _cycling(value: int) -> int:
    return bin(value).count("1")


_cycling.__wrapped__ = _cycling  # pyrefly: ignore[missing-attribute]


def _chained(count: int) -> Callable[[Any], Any]:
    """A package function behind ``count`` wrappers of a library's decorator."""
    function = _in_the_package(HELPER, "is_big")
    for _ in range(count):
        function = _decorated(function)
    return function


@pytest.mark.parametrize(
    "callee",
    [
        pytest.param(lambda: _cycling, id="a wrapper that wraps itself"),
        pytest.param(lambda: _chained(watch._MOST_WRAPPED + 1), id="past the wrappers read"),
    ],
)
def test_a_wrapper_the_watch_cannot_read_to_its_end_is_judged(callee: Callable[[], Any]) -> None:
    sink: list[SinkItem] = []

    answer(called(callee())(given(tracked(3, sink))), "wrapped")

    assert [name for name, _ in lost(sink)] == ["wrapped"]


class _Placed(type):
    """A metaclass whose attribute lookup raises, as a proxy class's may."""

    def __getattribute__(cls, name: str) -> object:
        raise RuntimeError("no lookup")


class _Proxy(metaclass=_Placed):
    def __call__(self, value: object) -> int:
        return bin(value).count("1")  # pyrefly: ignore[bad-argument-type]


def test_a_callable_s_class_attribute_lookup_does_not_run() -> None:
    sink: list[SinkItem] = []

    answer(called(_Proxy())(given(tracked(3, sink))), "proxy")

    assert [name for name, _ in lost(sink)] == ["proxy"]


def test_a_call_outside_the_target_s_package_is_judged() -> None:
    sink: list[SinkItem] = []
    # the same function, run with Python's own builtins, as a library's module runs
    space: dict[str, Any] = {}
    exec(compile(IS_BIG, "lib/helper.py", "exec"), space)

    answer(called(space["is_big"])(given(tracked(3, sink))), "is_big")

    assert [name for name, _ in lost(sink)] == ["is_big"]


def test_a_callee_that_forked_inside_adds_no_downgrade() -> None:
    sink: list[SinkItem] = []

    def forks(_value: object) -> int:
        # a fork the call made, as the tally counts it
        escapes.RECORDED[0] += 1
        return 1

    answer(called(forks)(given(tracked(3, sink))), "forks")

    assert lost(sink) == []


@pytest.mark.parametrize(
    ("argument", "counts"),
    [
        pytest.param(lambda x: [x, 1], True, id="a list"),
        pytest.param(lambda x: (1, x), True, id="a tuple"),
        pytest.param(lambda x: {x: 1}, True, id="a dict's key"),
        pytest.param(lambda x: {"k": x}, True, id="a dict's value"),
        pytest.param(lambda x: [[x]], False, id="nested two levels"),
        pytest.param(lambda x: {x}, False, id="a set"),
        pytest.param(lambda x: [0] * (watch.MOST_ITEMS - 1) + [x], True, id="the last item read"),
        pytest.param(lambda x: [0] * watch.MOST_ITEMS + [x], False, id="past the items read"),
    ],
)
def test_a_list_tuple_or_dict_passed_to_the_call_counts_one_level_deep(
    argument: Callable[[ConcolicInt], Any], counts: bool
) -> None:
    sink: list[SinkItem] = []

    answer(called(str)(given(argument(tracked(3, sink)))), "str")

    assert [name for name, _ in lost(sink)] == (["str"] if counts else [])


def test_a_bytes_answer_is_plain() -> None:
    sink: list[SinkItem] = []
    x = tracked(3, sink)

    answer(called(bytes)(given([x, 1])), "bytes")

    assert [name for name, _ in lost(sink)] == ["bytes"]
