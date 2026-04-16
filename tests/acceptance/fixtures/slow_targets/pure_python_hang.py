"""Fixture target that hangs in a pure-Python loop.

``run_llm_only`` had no per-seed timeout, so a seed like
``sympy.ntheory.egyptian_fraction.egypt_takenouchi(15, 7)``'s
non-converging ``while`` loop would hang the whole benchmark
indefinitely. This fixture reproduces that pattern: a simple busy
loop that ``signal.SIGALRM`` can interrupt (pure Python, no C
extensions blocking the eval loop).
"""

from __future__ import annotations

import time


def slow_spin(n: int) -> int:
    """Busy-wait for ``n`` seconds via a Python-level polling loop.

    Uses ``time.monotonic`` instead of ``time.sleep`` so the loop
    keeps executing bytecodes — SIGALRM fires between bytecodes and
    will raise ``TimeoutError`` out of the loop if the harness
    installed a per-seed alarm.
    """
    deadline = time.monotonic() + n
    count = 0
    while time.monotonic() < deadline:
        count += 1
    return count
