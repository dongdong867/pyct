"""Calls that spend their time in one C call that holds the GIL and checks for signals.

The regular expression backtracks for about 2.6 s and the power takes about
2.4 s where they were measured, each in one C call. Both are built from plain values at import,
so pyct follows nothing inside them.
"""

import re

BACKTRACKS = re.compile(r"(a+)+$")
TEXT = "a" * 27 + "b"
EXPONENT = 7_000_000


def backtrack(x: int) -> bool:
    return BACKTRACKS.match(TEXT) is not None


def power(x: int) -> int:
    # one C call: the % after it takes no time next to the power
    return 7**EXPONENT % 10
