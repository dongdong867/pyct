"""A hook rebinds names in its caller's frame: each name the frame has bound then takes the value
given, and a name the frame has not bound stays unbound. The same with a tracer and with line
events on."""

import contextlib
import sys
import types
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from pyct.core.entry.frames import rebind


def hook(**values: object) -> None:
    """Rebind the caller's names, as a piece's hook does from the target's own frame."""
    rebind(sys._getframe(1), values)


def plain_local() -> object:
    t, u = 1, 2
    hook(t=10)
    return t, u


def parameter(s: str, u: str) -> object:
    hook(s="P")
    return s, u


def cell_variable() -> object:
    t = 1

    def read() -> int:
        return t

    hook(t=10)
    return t, read()


def free_variable() -> object:
    t = 1

    def inner() -> int:
        nonlocal t
        hook(t=10)
        return t

    return inner(), t


def generator() -> Iterator[int]:
    t = 1
    hook(t=10)
    yield t
    yield t
    hook(t=20)
    yield t


def maybe_bound(bound: bool) -> object:
    if bound:
        y = 1
    hook(y=10)
    try:
        return y  # pyrefly: ignore[unbound-name] - unbound is the case
    except UnboundLocalError:
        return "unbound"


def several() -> object:
    a, b, c, d = 1, 2, 3, 4
    hook(a=10, c=30, d=40)
    return a, b, c, d


def bound_late(late: bool) -> object:
    hook(t=10)
    t = 1
    if late:
        hook(t=20)
    return t


def module_names() -> object:
    names: dict[str, object] = {"hook": hook}
    exec("t, u = 1, 2\nhook(t=10)\n", names)  # noqa: S102
    return names["t"], names["u"]


CASES: list[tuple[str, Callable[[], object], object]] = [
    ("a plain local", plain_local, (10, 2)),
    ("a parameter", lambda: parameter("s", "u"), ("P", "u")),
    ("a cell variable, which the inner function shares", cell_variable, (10, 10)),
    ("a free variable, which the outer function shares", free_variable, (10, 10)),
    ("a generator across its yields", lambda: list(generator()), [10, 10, 20]),
    ("a name not bound stays unbound", lambda: maybe_bound(False), "unbound"),
    ("a name bound on one path", lambda: maybe_bound(True), 10),
    ("several names at once, the others kept", several, (10, 2, 30, 40)),
    ("a name bound after the first hook", lambda: bound_late(True), 20),
    ("a name bound after the only hook keeps its own value", lambda: bound_late(False), 1),
    ("a module's own names", module_names, (10, 2)),
]


@contextlib.contextmanager
def no_watcher() -> Iterator[None]:
    yield


@contextlib.contextmanager
def tracer() -> Iterator[None]:
    """A ``sys.settrace`` tracer that reads each frame's locals, as a debugger does."""

    def trace(frame: types.FrameType, event: str, arg: Any) -> Any:
        frame.f_locals  # noqa: B018 - a debugger's read of the frame
        return trace

    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        yield
    finally:
        sys.settrace(previous)


@contextlib.contextmanager
def line_events() -> Iterator[None]:
    """``sys.monitoring`` line events on, as pyct's own coverage turns them on."""
    monitoring = sys.monitoring
    tool = next(tool for tool in (3, 4, 5) if monitoring.get_tool(tool) is None)
    monitoring.use_tool_id(tool, "line events")
    monitoring.register_callback(tool, monitoring.events.LINE, lambda code, line: None)
    monitoring.set_events(tool, monitoring.events.LINE)
    try:
        yield
    finally:
        monitoring.set_events(tool, 0)
        monitoring.register_callback(tool, monitoring.events.LINE, None)
        monitoring.free_tool_id(tool)


WATCHERS = {"no watcher": no_watcher, "a tracer": tracer, "line events": line_events}


@pytest.mark.parametrize("watcher", WATCHERS.values(), ids=WATCHERS.keys())
@pytest.mark.parametrize(
    ("case", "expected"), [(c, e) for _, c, e in CASES], ids=[i for i, *_ in CASES]
)
def test_a_hook_rebinds_each_name_its_caller_has_bound(
    watcher: Callable[[], contextlib.AbstractContextManager[None]],
    case: Callable[[], object],
    expected: object,
) -> None:
    with watcher():
        got = case()

    assert got == expected
