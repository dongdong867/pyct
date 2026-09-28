"""Calls that end at a time their caller sets, for the tests that race the deadline's alarm.

The caller sets ``SECONDS`` before each run. An input's process forked from
the caller's starts with the value the caller set.
"""

import time

# how long each call runs, from its start; the caller sets it before each run
SECONDS = 0.0


def spin() -> str:
    """Spin until ``SECONDS`` have passed since the call began."""
    end = time.monotonic() + SECONDS
    while time.monotonic() < end:
        pass
    return "done"


def outlive() -> str:
    """Spin until ``SECONDS`` have passed, catching the deadline's alarm and spinning on.

    The inner spin runs in a frame of its own: on 3.13 an alarm handled at a
    ``while`` loop's backward jump would skip the ``except`` around it.
    """
    end = time.monotonic() + SECONDS
    while time.monotonic() < end:
        try:
            _spin_until(end)
        except BaseException:
            pass
    return "done"


def _spin_until(end: float) -> None:
    while time.monotonic() < end:
        pass
