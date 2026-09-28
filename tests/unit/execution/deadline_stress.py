"""Deadline blocks that end within 20 µs of their instant, many times, in a process of their own.

``python -m tests.unit.execution.deadline_stress HANDLER WHERE SECONDS`` repeats a
block for SECONDS and prints one JSON line: the blocks, the DeadlineErrors raised
inside them, those that got out after a block had ended, and the calls of the
process's own SIGALRM handler. HANDLER is ``default`` for SIG_DFL, where a
SIGALRM of pyct's that reached it ends the process, or ``counting``. WHERE is
``owned``, the input's own process, or ``borrowed``, any other. It runs without
coverage.py, since the deadline raises inside the block.
"""

import json
import random
import signal
import sys
import time
import types

from pyct.execution.deadline import DeadlineError, deadline, own_the_alarm
from tests.unit.execution.ctrl_c_in_c import spin_until

# how far ahead each block's instant is, and how far from it the block ends
AHEAD = 100e-6
NOISE = 20e-6

calls = [0]


def count(number: int, frame: types.FrameType | None) -> None:
    calls[0] += 1


def block(tally: dict[str, int]) -> None:
    """One block ending near its instant, then a few steps after it, where no alarm belongs.

    The spin runs in a frame of its own (``spin_until``).
    """
    try:
        at = time.monotonic() + AHEAD
        try:
            with deadline(at):
                spin_until(at + random.uniform(-NOISE, NOISE))
        except DeadlineError:
            tally["raised"] += 1
        for _ in range(50):
            pass
    except DeadlineError:
        tally["escaped"] += 1
    tally["blocks"] += 1


def main(handler: str, where: str, seconds: float) -> None:
    signal.signal(signal.SIGALRM, signal.SIG_DFL if handler == "default" else count)
    if where == "owned":
        own_the_alarm()
    tally = {"blocks": 0, "raised": 0, "escaped": 0}
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        block(tally)
    print(json.dumps({**tally, "calls": calls[0]}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]))
