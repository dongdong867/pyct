"""A raise at any line of pyct's code, as the deadline's SIGALRM handler can land.

A trace function counts the lines one source file runs and raises at the n-th, the way
the alarm raises wherever Python happens to be. ``at_every_line`` runs a test's trial
once for every n its step has, and checks that at least one raise landed at all.
"""

import functools
import sys
import types
from collections.abc import Callable
from typing import Any

# runs one step with the raise landing in it, as the trial hands it over
type Interrupt = Callable[[Callable[[], object]], None]


class Alarm(BaseException):
    """What the deadline raises, landing inside pyct's code."""


def at_every_line(source: str, trial: Callable[[Interrupt, int], None]) -> None:
    """Run ``trial`` once for each line its step runs in ``source``, the raise landing there.

    ``trial(interrupt, at)`` sets up, runs its step through ``interrupt`` and
    checks what comes after; ``at`` names the line, for the trial's messages.
    The trials stop at the first step that finished without a raise. Some
    raise must land: none means ``source`` named no file the step runs.
    """
    at = 1
    while True:
        landed: list[bool] = []
        trial(functools.partial(_landing, landed, at, source), at)
        if not any(landed):
            break
        at += 1
    assert at > 1, f"no line of {source} ran under the step"


def _landing(landed: list[bool], at: int, source: str, step: Callable[[], object]) -> None:
    landed.append(interrupted(step, at, source))


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
