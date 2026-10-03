"""Calls that run under a Python-level tracer, for the tests where the deadline's alarm lands in
the tracer's own frame.

As it is imported, the module installs the tracer ``PYCT_TEST_TRACER`` names: ``settrace``, a
``sys.settrace`` function that traces every line, or ``monitoring``, a ``sys.monitoring`` tool
with LINE events on. Unset or ``none`` installs nothing, for a program that installs its own
with ``install``. Each callback returns at once, except on the line ``in_the_tracer`` marks,
where it loops forever. Each call that has a ``finally`` writes ``MARKER`` to stderr there.
Before its C call, a call creates the file ``PYCT_TEST_CALLING`` names, if any, so a test
knows when to send its signal.
"""

import os
import sys
import types

from targets.isolate.long_sum import TERMS

# what each finally block writes
MARKER = "the call's finally block ran"


def _hangs_here(code: types.CodeType, line: int) -> bool:
    """Whether the tracer loops forever at ``line`` of ``code``: ``in_the_tracer``'s mark."""
    return code is in_the_tracer.__code__ and line == in_the_tracer.__code__.co_firstlineno + 3


def _trace(frame: types.FrameType, event: str, arg: object) -> object:
    if event == "line" and _hangs_here(frame.f_code, frame.f_lineno):
        while True:
            pass
    return _trace


def _on_line(code: types.CodeType, line: int) -> object:
    if _hangs_here(code, line):
        while True:
            pass
    return None


def install(tracer: str) -> None:
    """Install ``tracer``, ``settrace``, ``monitoring`` or ``none``, again if it was already."""
    if tracer == "settrace":
        sys.settrace(_trace)
    elif tracer == "monitoring":
        monitoring = sys.monitoring
        if monitoring.get_tool(monitoring.DEBUGGER_ID) is None:
            monitoring.use_tool_id(monitoring.DEBUGGER_ID, "host")
        monitoring.register_callback(monitoring.DEBUGGER_ID, monitoring.events.LINE, _on_line)
        monitoring.set_events(monitoring.DEBUGGER_ID, monitoring.events.LINE)


def _calling() -> None:
    """Say the C call is about to begin, in the file ``PYCT_TEST_CALLING`` names."""
    told = os.environ.get("PYCT_TEST_CALLING")
    if told:
        with open(told, "w"):
            pass


def _said_on_the_way_out() -> None:
    print(MARKER, file=sys.stderr, flush=True)


def total(x: int) -> int:
    _calling()
    return sum(range(TERMS))


def total_then_finally(x: int) -> int:
    _calling()
    try:
        return sum(range(TERMS))
    finally:
        _said_on_the_way_out()


def _spin() -> None:
    while True:
        pass


def loop(x: int) -> int:
    try:
        _spin()
    finally:
        _said_on_the_way_out()
    return x


def in_the_tracer(x: int) -> int:
    try:
        # the tracer loops forever on the next line
        x += 1
    finally:
        _said_on_the_way_out()
    return x


install(os.environ.get("PYCT_TEST_TRACER", "none"))
