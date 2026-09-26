"""A raise at any line of pyct's code, as the deadline's SIGALRM handler can land.

A trace function counts the lines one source file runs and raises at the n-th, the way
the alarm raises wherever Python happens to be. A test runs a step for every n it has
and checks what comes after.
"""

import sys
import types
from collections.abc import Callable
from typing import Any


class Alarm(BaseException):
    """What the deadline raises, landing inside pyct's code."""


def interrupted(step: Callable[[], object], at: int, source: str) -> bool:
    """Run ``step``, raising Alarm at the ``at``-th line it runs in ``source``.

    False when the step ran fewer lines there and finished. coverage.py
    traces through the same hook, so the tracer found here comes back after.
    """
    lines = [0]

    def trace(frame: types.FrameType, event: str, arg: Any) -> Any:
        if frame.f_code.co_filename != source:
            return None
        if event == "line":
            lines[0] += 1
            if lines[0] == at:
                raise Alarm
        return trace

    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        step()
    except Alarm:
        return True
    finally:
        sys.settrace(previous)
    return False
