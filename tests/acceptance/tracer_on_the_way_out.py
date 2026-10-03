"""A program that calls ``run()`` while a tracer of its own acts as the target's call ends.

``python -m tests.acceptance.tracer_on_the_way_out TRACER NAME ACTION HANDLER TRIES`` installs
``HANDLER`` as its SIGALRM handler (``own``, ``ignore`` or ``default``) and, TRIES times,
installs ``TRACER`` (``none``, ``settrace`` or ``monitoring``) and calls ``run()`` on
``targets/isolate/on_the_way_out.py``'s ``NAME`` with ``Isolation.IN_PROCESS``. On the first line
event after the target's function returns or its raise leaves it, the tracer does ``ACTION``:
``spin``, loop in Python until 0.3 s past the run's 0.5 s budget; ``sigint``, send the program a
SIGINT; ``raise``, raise RuntimeError. Otherwise it returns at once, and the budget is 5 s. It
prints one JSON line per try: how the run ended, whether SIGALRM's handler is the program's own
again, whether a SIGALRM the program raises reached it, and the ``pyct deadline`` threads still
alive. It runs without coverage.py, since the deadline raises in the tracer.
"""

import json
import os
import signal
import sys
import threading
import time
import types

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import load_target
from targets.isolate import on_the_way_out

TARGET_FILE = on_the_way_out.__file__
TARGETS = {"returns", "raises", "loops"}
reached: list[int] = []


class _State:
    """What the tracer does on the first line event after the target's call ended, and when."""

    action = "spin"
    ended = False
    until = 0.0


state = _State()


def _own(signal_number: int, frame: types.FrameType | None) -> None:
    reached.append(signal_number)


def _is_target(code: types.CodeType) -> bool:
    return code.co_filename == TARGET_FILE and code.co_name in TARGETS


def _act() -> None:
    """Do the action once, on the first line event after the target's call ended."""
    if not state.ended:
        return
    state.ended = False
    if state.action == "spin":
        while time.monotonic() < state.until:
            pass
    elif state.action == "sigint":
        os.kill(os.getpid(), signal.SIGINT)
    elif state.action == "raise":
        raise RuntimeError("the tracer's own")


def _trace(frame: types.FrameType, event: str, arg: object) -> object:
    if event == "return" and _is_target(frame.f_code):
        state.ended = True
    elif event == "line":
        _act()
    return _trace


def _left(code: types.CodeType, offset: int, value: object) -> None:
    if _is_target(code):
        state.ended = True


def _on_line(code: types.CodeType, line: int) -> None:
    _act()


def install(tracer: str) -> None:
    """Install ``tracer``: ``settrace``, ``monitoring`` or ``none``."""
    if tracer == "settrace":
        sys.settrace(_trace)  # pyrefly: ignore[bad-argument-type]
    elif tracer == "monitoring":
        monitoring = sys.monitoring
        tool, events = monitoring.DEBUGGER_ID, monitoring.events
        if monitoring.get_tool(tool) is None:
            monitoring.use_tool_id(tool, "host")
        monitoring.register_callback(tool, events.PY_RETURN, _left)
        monitoring.register_callback(tool, events.PY_UNWIND, _left)
        monitoring.register_callback(tool, events.LINE, _on_line)
        monitoring.set_events(tool, events.PY_RETURN | events.PY_UNWIND | events.LINE)


def uninstall(tracer: str) -> None:
    """Take ``tracer`` off again, so nothing of it runs while the try is judged."""
    sys.settrace(None)
    if tracer == "monitoring":
        sys.monitoring.set_events(sys.monitoring.DEBUGGER_ID, 0)


def one_try(tracer: str, name: str, handler: object) -> dict[str, object]:
    """One run() of ``name`` under ``tracer``, and what it left behind."""
    budget = 0.5 if state.action == "spin" or name == "loops" else 5.0
    target = load_target(f"targets.isolate.on_the_way_out::{name}")
    state.ended = False
    state.until = time.monotonic() + budget + 0.3
    install(tracer)
    try:
        result = run(
            target, {"x": 0}, limits=Limits(budget=Budget(budget)), isolation=Isolation.IN_PROCESS
        )
        failure = result.records[0].failure
        ended: object = None if failure is None else [failure.kind.value, failure.detail]
    except BaseException as error:  # noqa: BLE001 - every ending is the try's to report
        ended = type(error).__name__
    uninstall(tracer)
    return {"ended": ended, **_left_behind(handler)}


def _left_behind(handler: object) -> dict[str, object]:
    """Whether SIGALRM's handler is the program's again, reaches it, and the watchers alive."""
    back = signal.getsignal(signal.SIGALRM) == handler
    reached.clear()
    if handler is _own:
        signal.raise_signal(signal.SIGALRM)
    watchers = [t.name for t in threading.enumerate() if t.name == "pyct deadline"]
    return {"handler_back": back, "reached": bool(reached), "watchers": watchers}


def main() -> None:
    tracer, name, action, kind, tries = sys.argv[1:6]
    handler = {"own": _own, "ignore": signal.SIG_IGN, "default": signal.SIG_DFL}[kind]
    signal.signal(signal.SIGALRM, handler)
    state.action = action
    for _ in range(int(tries)):
        print(json.dumps(one_try(tracer, name, handler)), flush=True)


if __name__ == "__main__":
    main()
