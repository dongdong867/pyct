"""LINE events through ``sys.monitoring``, under a tool id no one else holds.

The one place pyct takes a tool id for its line tracers and gives it back,
for an input's call (``execute``) and for the target's import (``run``).
A code location a callback answered DISABLE stays disabled for that tool id
after it is freed, so the next tracer that takes the same id gets no event
there either; each tracer disables only code it never keeps lines of.
"""

from __future__ import annotations

import contextlib
import sys
import types
from collections.abc import Callable, Generator

# 3 and 4 are unassigned; 0, 1, 2, 5 belong to a debugger, coverage, a profiler, the optimizer
_TOOL_IDS = (3, 4, 0, 1, 2, 5)

# what sys.monitoring calls on each LINE event: the code and its line, answering DISABLE or None
type OnLine = Callable[[types.CodeType, int], object]


def unused_tool_id() -> int:
    """A ``sys.monitoring`` tool id no one holds, the unassigned ones first."""
    for tool_id in _TOOL_IDS:
        if sys.monitoring.get_tool(tool_id) is None:
            return tool_id
    raise RuntimeError("every sys.monitoring tool id is taken")


def listen(on_line: OnLine) -> int:
    """Take a tool id and send every LINE event to ``on_line`` until ``stop`` gives it back.

    A raise while the events are being set up gives the id back first.
    """
    monitoring = sys.monitoring
    tool_id = unused_tool_id()
    monitoring.use_tool_id(tool_id, "pyct")
    try:
        monitoring.register_callback(tool_id, monitoring.events.LINE, on_line)
        monitoring.set_events(tool_id, monitoring.events.LINE)
    except BaseException:
        stop(tool_id)
        raise
    return tool_id


def stop(tool_id: int) -> None:
    """End the LINE events ``listen`` started and give its tool id back."""
    monitoring = sys.monitoring
    monitoring.set_events(tool_id, 0)
    monitoring.register_callback(tool_id, monitoring.events.LINE, None)
    monitoring.free_tool_id(tool_id)


@contextlib.contextmanager
def line_events(on_line: OnLine) -> Generator[None]:
    """Every LINE event inside the block goes to ``on_line``; the tool id goes back however the
    block ends."""
    tool_id = listen(on_line)
    try:
        yield
    finally:
        stop(tool_id)
